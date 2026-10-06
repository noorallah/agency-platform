"""A price above a batch's MRP is refused where it is struck, not on the bill.

D-PRC-7, driven 2026-10-06: an order of one, pinned to a batch printed 120.00,
at 130 (145.60 with tax) was saved and approved, its delivery note was
dispatched, and only the bill was refused -- "Line 1: charges 145.60 a unit
with tax, above the MRP of 120.00 printed on the batch it ships." -- with the
goods already out. The same check, in the same words, now runs when an order
line is saved with a pinned batch, when a counter bill is saved with the
batches it chose, and at dispatch before any stock moves.

Every case runs with the session shaped as a request's is: autoflush off.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote
from app.inventory.models import InventoryTransaction
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_batch_picker import NOTE_DATE, _Shop
from tests.unit.test_counter_bill_batches import _Counter

ABOVE = "Line 1: charges 100.00 a unit with tax, above the MRP of 90.00 printed"


def _shop(**mrps: str) -> _Shop:
    """Return the three-batch shop on a request-shaped session, MRPs printed."""
    shop = _Shop()
    shop.session.autoflush = False
    for name, mrp in mrps.items():
        shop.batches[name].mrp = Decimal(mrp)
    shop.session.commit()
    return shop


def _order_of(
    shop: _Shop, *, pinned: str | None, price: str = "100"
) -> SalesOrderCreate:
    """Describe an order of five at a price, pinned to a batch or not."""
    return SalesOrderCreate(
        customer_id=shop.order.customer_id,
        branch_id=shop.order.branch_id,
        warehouse_id=shop.warehouse_id,
        order_date=NOTE_DATE,
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=shop.product.id,
                quantity=Decimal("5"),
                unit_price=Decimal(price),
                pinned_batch_id=None if pinned is None else shop.batches[pinned].id,
            )
        ],
    )


def _dispatches(shop: _Shop) -> int:
    """Count the movements that took goods out of the warehouse."""
    shop.session.expire_all()
    return len(
        shop.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH"
            )
        ).all()
    )


def test_an_order_line_pinned_to_a_batch_is_refused_above_its_mrp() -> None:
    """The order is where the price is first struck: it is not saved."""
    shop = _shop(JUNE="90.00")
    orders_before = len(shop.session.scalars(select(SalesOrder)).all())

    with pytest.raises(ValidationError) as refused:
        SalesOrderService(shop.session).create_order(
            _order_of(shop, pinned="JUNE"),
            firm_id=shop.firm_id,
            actor_id=shop.actor_id,
        )
    shop.session.rollback()

    assert refused.value.message == f"{ABOVE} on the batch it ships."
    assert len(shop.session.scalars(select(SalesOrder)).all()) == orders_before


def test_an_edit_that_raises_the_price_past_the_mrp_is_refused() -> None:
    """The same check on a save that changes the price."""
    shop = _shop(JUNE="90.00")
    service = SalesOrderService(shop.session)
    order = service.create_order(
        _order_of(shop, pinned="JUNE", price="90"),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )

    with pytest.raises(ValidationError, match="above the MRP of 90.00"):
        service.update_order(
            order.id,
            _order_of(shop, pinned="JUNE", price="100"),
            firm_scope=shop.firm_id,
            actor_id=shop.actor_id,
        )
    shop.session.rollback()


def test_a_pinned_batch_with_no_mrp_is_judged_on_the_products() -> None:
    """The product's MRP stands in for a batch that carries none."""
    shop = _shop()
    shop.product.mrp = Decimal("80.00")
    shop.session.commit()

    with pytest.raises(ValidationError, match="above the MRP of 80.00"):
        SalesOrderService(shop.session).create_order(
            _order_of(shop, pinned="JUNE"),
            firm_id=shop.firm_id,
            actor_id=shop.actor_id,
        )
    shop.session.rollback()


def test_an_order_with_no_pin_names_no_batch_and_is_saved() -> None:
    """No batch is known yet, so there is nothing to compare the price with."""
    shop = _shop(MARCH="90.00", JUNE="90.00")

    order = SalesOrderService(shop.session).create_order(
        _order_of(shop, pinned=None),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )

    assert order.status == "DRAFT"


def test_dispatch_refuses_a_batch_it_allocated_before_any_stock_leaves() -> None:
    """The note of the shop's order of eight draws MARCH, printed 90.

    Nobody chose the batch: the allocator did, earliest expiry first, and
    that is the first moment the price can be compared with a pack.
    """
    shop = _shop(MARCH="90.00")
    note = shop.note(None)
    moved = _dispatches(shop)
    held = shop.stock("MARCH").current_quantity

    with pytest.raises(ValidationError) as refused:
        shop.dispatch(note)
    shop.session.rollback()

    assert refused.value.message == f"{ABOVE} on the batch it ships."
    assert _dispatches(shop) == moved
    assert shop.stock("MARCH").current_quantity == held
    reread = shop.session.get(DeliveryNote, note.id)
    assert reread is not None and reread.status != "DISPATCHED"


def test_dispatch_refuses_a_batch_a_person_chose() -> None:
    """Chosen on the note: JUNE, printed 90, and eight at 100."""
    shop = _shop(JUNE="90.00")
    note = shop.note(shop.picks(JUNE="8"))
    moved = _dispatches(shop)

    with pytest.raises(ValidationError, match="above the MRP of 90.00"):
        shop.dispatch(note)
    shop.session.rollback()

    assert _dispatches(shop) == moved


def test_a_line_from_two_batches_is_held_to_the_lower_mrp() -> None:
    """Three of MARCH at 120 and five of JUNE at 90: the 90 is the ceiling."""
    shop = _shop(MARCH="120.00", JUNE="90.00")
    note = shop.note(shop.picks(MARCH="3", JUNE="5"))

    with pytest.raises(ValidationError, match="above the MRP of 90.00"):
        shop.dispatch(note)
    shop.session.rollback()


def test_within_the_mrp_the_note_is_dispatched() -> None:
    """At the MRP exactly is not above it."""
    shop = _shop(MARCH="100.00")
    note = shop.note(None)

    shop.dispatch(note)

    assert shop.drawn(note) == {"MARCH": Decimal("8.0000")}


def _counter(**mrps: str) -> _Counter:
    """Return the counter firm on a request-shaped session, MRPs printed."""
    shop = _Counter()
    shop.session.autoflush = False
    for name, mrp in mrps.items():
        shop.batches[name].mrp = Decimal(mrp)
    shop.session.commit()
    return shop


def test_a_counter_bill_is_refused_at_save_not_at_approval() -> None:
    """One batch chosen: the draft is not written, and nothing is left behind."""
    shop = _counter(LATE="90.00")

    with pytest.raises(ValidationError) as refused:
        shop.bills.create_invoice(
            shop.bill([shop.pick("LATE")]), firm_id=shop.firm.id, actor_id=shop.actor
        )
    shop.session.rollback()

    assert refused.value.message == f"{ABOVE} on the batch it ships."
    assert shop.session.scalars(select(SalesInvoice)).all() == []
    assert shop.session.scalars(select(SalesOrder)).all() == []


def test_a_counter_bill_from_two_batches_is_refused_at_save_too() -> None:
    """Two batches pin neither, so the bill's own choice is what is judged."""
    shop = _counter(EARLY="120.00", LATE="90.00")

    with pytest.raises(ValidationError, match="above the MRP of 90.00"):
        shop.bills.create_invoice(
            shop.bill([shop.pick("EARLY", "1"), shop.pick("LATE", "3")]),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )
    shop.session.rollback()

    assert shop.session.scalars(select(SalesInvoice)).all() == []
