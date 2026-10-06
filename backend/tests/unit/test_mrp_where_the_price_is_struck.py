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

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.batch_serial.models.batch_serial import BatchRecord
from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.delivery_note.services import DeliveryNoteService
from app.inventory.models import InventoryTransaction
from app.inventory.services import InventoryService
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.models.sales_order import SalesWorkflowSettings
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.uom.models import ConversionRule, Uom
from tests.unit.test_batch_picker import NOTE_DATE, _Shop
from tests.unit.test_counter_bill_batches import _Counter
from tests.unit.test_sales_chain_synthesis import _request_session
from tests.unit.test_sales_order_module import _tax_group

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


# ---- a line sold in another unit than the pack the MRP is printed on --------
#
# D-PRC-36, the third live check (2026-10-06): AMX, kept in pieces, 12 to a
# box, GST 12%, a batch printed 120.00. 1 BOX at 1,200.00 is 1,344.00 with
# tax, 112.00 a piece. The order, the note and the dispatch passed, 12 pieces
# left, and the bill's approval was refused "charges 1344.00 a unit with tax,
# above the MRP of 120.00"; billed as 12 PIECE it read "16134.45 a unit".

BILL_DAY = date(2026, 8, 4)
ABOVE_120 = "above the MRP of 120.00 printed on the batch it ships."


class _Pharmacy(_Counter):
    """The counter firm with AMX in a batch of 48 printed 120.00, 12 to a box."""

    def __init__(self, *, counter: bool = False) -> None:
        """Build it on a request-shaped session; ``counter`` types only bills."""
        super().__init__(_request_session())
        self.session.autoflush = False
        if not counter:
            stages = self.session.scalars(select(SalesWorkflowSettings)).one()
            stages.sales_order_stage = True
            stages.delivery_note_stage = True
        piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
        box = Uom(
            code="BOX",
            name="Box",
            dimension="COUNT",
            status="ACTIVE",
            is_decimal_allowed=False,
        )
        self.session.add_all([piece, box])
        self.session.flush()
        self.piece: UUID = piece.id
        self.box: UUID = box.id
        self.drug.base_uom_id = piece.id
        self.drug.inventory_uom_id = piece.id
        self.drug.selling_price = Decimal("100")
        self.drug.tax_profile_group_code = "GST_STANDARD"
        self.session.add(
            ConversionRule(
                firm_id=self.firm.id,
                product_id=self.drug.id,
                from_uom_id=box.id,
                to_uom_id=piece.id,
                conversion_factor=Decimal("12"),
                rounding_mode="HALF_UP",
                precision_scale=4,
                effective_from=date(2026, 4, 1),
                version_number=1,
            )
        )
        batch = BatchRecord(
            firm_id=self.firm.id,
            product_id=self.drug.id,
            batch_number="BM",
            expiry_date=date(2028, 3, 31),
            status="AVAILABLE",
            mrp=Decimal("120.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.session.add(batch)
        self.session.flush()
        self.batches["BM"] = batch
        self.receive("BM", "48")
        _tax_group(
            self.session,
            firm_id=self.firm.id,
            percent="12",
            starts=date(2026, 4, 1),
            ends=None,
        )
        self.orders = SalesOrderService(self.session)
        self.notes = DeliveryNoteService(self.session)

    def receive(self, name: str, quantity: str) -> None:
        """Put more pieces of a batch on the shelf."""
        InventoryService(self.session).record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=self.actor,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.drug.id,
            reference_number=f"GRN-{name}-{quantity}",
            transaction_date=date(2026, 8, 1),
            total_quantity=Decimal(quantity),
            unit_cost=Decimal("50"),
            batch_id=self.batches[name].id,
        )
        self.session.commit()

    def order(self, *, pinned: bool = True, **line: object) -> SalesOrder:
        """Save an order of one line of AMX, pinned to BM unless told not to."""
        if pinned:
            line = {"pinned_batch_id": self.batches["BM"].id} | line
        return self.orders.create_order(
            SalesOrderCreate.model_validate(
                {
                    "customer_id": self.customer.id,
                    "branch_id": self.branch.id,
                    "warehouse_id": self.warehouse.id,
                    "order_date": BILL_DAY,
                    "lines": [{"line_number": 1, "product_id": self.drug.id} | line],
                }
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )

    def note_of(self, order: SalesOrder, quantity: str) -> DeliveryNote:
        """Approve the order and raise an approved note of its one line."""
        self.orders.approve_order(
            order.id, firm_scope=self.firm.id, actor_id=self.actor
        )
        line = self.session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        ).one()
        note = self.notes.create_note(
            DeliveryNoteCreate.model_validate(
                {
                    "sales_order_id": order.id,
                    "delivery_date": BILL_DAY,
                    "lines": [
                        {
                            "sales_order_line_id": line.id,
                            "line_number": 1,
                            "current_delivery_quantity": quantity,
                        }
                    ],
                }
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        return self.notes.approve_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def shipped(
        self, quantity: str = "1", *, pinned: bool = True, **line: object
    ) -> DeliveryNote:
        """Order, deliver and dispatch one line; return its note."""
        order = self.order(pinned=pinned, quantity=quantity, **line)
        note = self.note_of(order, quantity)
        return self.notes.dispatch_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def bill_of(
        self, note: DeliveryNote, quantity: str, **line: object
    ) -> SalesInvoice:
        """Save a draft bill of the note's one line."""
        self.session.expire_all()
        note_line = self.session.scalars(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        ).one()
        return self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.customer.id,
                    "invoice_date": BILL_DAY,
                    "lines": [
                        {
                            "source_document_type": "DELIVERY_NOTE",
                            "source_document_id": note.id,
                            "source_document_line_id": note_line.id,
                            "line_number": 1,
                            "current_invoice_quantity": quantity,
                        }
                        | line
                    ],
                }
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )

    def approve(self, bill: SalesInvoice) -> SalesInvoice:
        """Approve a bill."""
        return self.bills.approve_invoice(
            bill.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def left(self) -> Decimal:
        """Return how many pieces of BM have been dispatched."""
        return self.drawn().get("BM", Decimal("0"))


def test_a_box_shipped_from_a_batch_with_an_mrp_is_billed_in_boxes() -> None:
    """1 BOX at 1,200.00 is 112.00 a piece with tax: the bill is approved."""
    shop = _Pharmacy()
    note = shop.shipped(sales_uom_id=shop.box, unit_price="1200")
    assert shop.left() == Decimal("12.0000")

    bill = shop.approve(shop.bill_of(note, "1"))

    assert bill.status == "APPROVED"
    assert bill.grand_total == Decimal("1344.0000")


def test_the_same_box_billed_as_twelve_pieces_is_approved_too() -> None:
    """Typed 12 PIECE against the note's 1 BOX: still 112.00 a piece."""
    shop = _Pharmacy()
    note = shop.shipped(sales_uom_id=shop.box, unit_price="1200")

    bill = shop.approve(shop.bill_of(note, "12", invoice_uom_id=shop.piece))

    assert bill.status == "APPROVED"
    assert bill.grand_total == Decimal("1344.0000")


def test_a_line_in_pieces_is_judged_as_it_always_was() -> None:
    """12 PIECE at 100.00 from the same batch: ordered, shipped and billed."""
    shop = _Pharmacy()
    note = shop.shipped("12", unit_price="100")

    assert shop.approve(shop.bill_of(note, "12")).grand_total == Decimal("1344.0000")


def test_a_bill_reaches_the_verdict_its_dispatch_reached() -> None:
    """The pack is reprinted 111.99 after the box left: one paisa over.

    The bill is still the last line of defence, and it names the price of a
    piece -- 112.00 -- not of the box.
    """
    shop = _Pharmacy()
    note = shop.shipped(sales_uom_id=shop.box, unit_price="1200")
    draft = shop.bill_of(note, "1")
    shop.batches["BM"].mrp = Decimal("111.99")
    shop.session.commit()

    with pytest.raises(ValidationError) as refused:
        shop.approve(draft)
    shop.session.rollback()

    assert refused.value.message == (
        "Line 1: charges 112.00 a unit with tax, above the MRP of 111.99 "
        "printed on the batch it ships."
    )
    # At the MRP exactly it goes.
    shop.batches["BM"].mrp = Decimal("112.00")
    shop.session.commit()
    assert shop.approve(draft).status == "APPROVED"


@pytest.mark.parametrize(
    ("boxed", "quantity", "price", "rate"),
    [
        (True, "1", "1320", "123.20"),
        (False, "12", "110", "123.20"),
        # One paisa over: 1,285.82 a box is 1,440.1184 with tax, 120.01 a piece.
        (True, "1", "1285.82", "120.01"),
    ],
)
def test_a_pinned_order_is_refused_on_the_price_of_a_piece(
    boxed: bool, quantity: str, price: str, rate: str
) -> None:
    """A box at 1,320.00 and 12 pieces at 110.00 are refused in the same words."""
    shop = _Pharmacy()
    unit = {"sales_uom_id": shop.box} if boxed else {}

    with pytest.raises(ValidationError) as refused:
        shop.order(quantity=quantity, unit_price=price, **unit)
    shop.session.rollback()

    assert refused.value.message == (
        f"Line 1: charges {rate} a unit with tax, {ABOVE_120}"
    )


def test_a_pinned_box_at_the_mrp_to_the_paisa_is_saved() -> None:
    """1,285.71 a box is 1,439.9952 with tax: 120.00 a piece, not above it."""
    shop = _Pharmacy()

    order = shop.order(quantity="1", sales_uom_id=shop.box, unit_price="1285.71")

    assert order.status == "DRAFT"


def test_dispatch_of_an_unpinned_box_judges_the_price_of_a_piece() -> None:
    """No pin: the allocator draws the batches, each printed 120.00.

    A box at 1,200.00 leaves; a box at 1,320.00 is refused before any stock
    moves, as 123.20 a piece. EARLY and LATE are topped up to a whole box
    each, so each box is drawn from one batch.
    """
    shop = _Pharmacy()
    for name in ("EARLY", "LATE"):
        shop.batches[name].mrp = Decimal("120.00")
        shop.receive(name, "2")

    shop.shipped(pinned=False, sales_uom_id=shop.box, unit_price="1200")
    moved = sum(shop.drawn().values())
    assert moved == Decimal("12.0000")

    dear = shop.note_of(
        shop.order(
            pinned=False, quantity="1", sales_uom_id=shop.box, unit_price="1320"
        ),
        "1",
    )
    with pytest.raises(ValidationError) as refused:
        shop.notes.dispatch_note(dear.id, firm_scope=shop.firm.id, actor_id=shop.actor)
    shop.session.rollback()

    assert refused.value.message == (
        f"Line 1: charges 123.20 a unit with tax, {ABOVE_120}"
    )
    assert sum(shop.drawn().values()) == moved


def _counter_box(shop: _Pharmacy, price: str) -> SalesInvoiceCreate:
    """Describe a counter bill of 1 BOX of AMX from BM at a price."""
    return SalesInvoiceCreate.model_validate(
        {
            "customer_id": shop.customer.id,
            "invoice_date": BILL_DAY,
            "lines": [
                {
                    "product_id": shop.drug.id,
                    "line_number": 1,
                    "current_invoice_quantity": "1",
                    "invoice_uom_id": shop.box,
                    "unit_price": price,
                    "batches": [{"batch_id": shop.batches["BM"].id, "quantity": "12"}],
                }
            ],
        }
    )


def test_a_counter_bill_by_the_box_is_saved_and_approved_within_the_mrp() -> None:
    """Stages off: 1 BOX at 1,200.00 from BM is approved and 12 pieces leave."""
    shop = _Pharmacy(counter=True)

    draft = shop.bills.create_invoice(
        _counter_box(shop, "1200"), firm_id=shop.firm.id, actor_id=shop.actor
    )
    bill = shop.approve(draft)

    assert bill.status == "APPROVED"
    assert bill.grand_total == Decimal("1344.0000")
    assert shop.left() == Decimal("12.0000")


def test_a_counter_bill_by_the_box_above_the_mrp_is_refused_at_save() -> None:
    """1 BOX at 1,320.00 is 123.20 a piece: nothing is written."""
    shop = _Pharmacy(counter=True)

    with pytest.raises(ValidationError) as refused:
        shop.bills.create_invoice(
            _counter_box(shop, "1320"), firm_id=shop.firm.id, actor_id=shop.actor
        )
    shop.session.rollback()

    assert refused.value.message == (
        f"Line 1: charges 123.20 a unit with tax, {ABOVE_120}"
    )
    assert shop.session.scalars(select(SalesInvoice)).all() == []
