"""A firm's rules for which batches go out on a sale (backlog 79 row 6, A2).

The shop from ``test_batch_picker``: STALE (expired), MARCH (196 days left on
the note's date) and JUNE (287), ten each, and an order for eight holding
MARCH. A 200-day window makes MARCH near expiry and leaves JUNE fresh.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.batch_serial.schemas import BatchSaleSettingsWrite
from app.batch_serial.services import BatchSalePolicyService, BatchSerialService
from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.document_framework.models import DocumentLifecycleEvent
from app.inventory.models import InventoryTransaction
from app.sales_order.models import PriceFloorSettings, SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_order.services.price_floor import PricedLine, PriceFloorService
from tests.unit.test_batch_picker import NOTE_DATE, _Shop


def _rules(
    shop: _Shop,
    *,
    days: int = 200,
    near: str = "WARN",
    skip: str = "RECORD",
    below_floor: bool = True,
) -> None:
    """Write the firm's batch-sale rules."""
    BatchSalePolicyService(shop.session).update_settings(
        BatchSaleSettingsWrite(
            near_expiry_days=days,
            near_expiry_policy=near,  # type: ignore[arg-type]
            fefo_skip_policy=skip,  # type: ignore[arg-type]
            near_expiry_below_floor=below_floor,
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )


def _audit(shop: _Shop, action: str) -> list[AuditLog]:
    """Return the trail's rows for one action."""
    return list(
        shop.session.scalars(select(AuditLog).where(AuditLog.action == action)).all()
    )


def _event(shop: _Shop, document_id: object, action: str) -> DocumentLifecycleEvent:
    """Return a document's one lifecycle event of a kind."""
    row = shop.session.scalar(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == document_id,
            DocumentLifecycleEvent.action == action,
        )
    )
    assert row is not None
    return row


def _approved(shop: _Shop, note: DeliveryNote) -> DeliveryNote:
    """Approve a note."""
    return shop.notes.approve_note(
        note.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )


def _floor(shop: _Shop, *, minimum: str = "150") -> None:
    """Refuse a sale below a minimum price the product's rate is under."""
    shop.product.minimum_selling_price = Decimal(minimum)
    shop.session.add(
        PriceFloorSettings(
            firm_id=shop.firm_id, enforcement="BLOCK", include_cost=False
        )
    )
    shop.session.commit()


def _order(shop: _Shop, quantity: str) -> SalesOrder:
    """Raise a second order at 100 a unit, below a floor of 150."""
    return SalesOrderService(shop.session).create_order(
        SalesOrderCreate(
            customer_id=shop.order.customer_id,
            branch_id=shop.order.branch_id,
            warehouse_id=shop.warehouse_id,
            order_date=NOTE_DATE,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )


# -- The rules -----------------------------------------------------------------


def test_a_firm_that_never_chose_shares_the_defaults() -> None:
    """Thirty days, warn, record, and the floor exemption on."""
    shop = _Shop()

    rules = BatchSalePolicyService(shop.session).settings_response(shop.firm_id)

    assert rules.near_expiry_days == 30
    assert rules.near_expiry_policy == "WARN"
    assert rules.fefo_skip_policy == "RECORD"
    assert rules.near_expiry_below_floor is True
    assert rules.is_configured is False


def test_writing_the_rules_is_audited_with_what_they_were() -> None:
    """The first write creates the row; the second keeps the before."""
    shop = _Shop()
    _rules(shop)
    _rules(shop, days=60, near="REASON")

    rules = BatchSalePolicyService(shop.session).settings_response(shop.firm_id)
    assert (rules.near_expiry_days, rules.near_expiry_policy) == (60, "REASON")
    assert rules.is_configured is True
    assert len(_audit(shop, "batch_sale_settings.created")) == 1
    updated = _audit(shop, "batch_sale_settings.updated")
    assert len(updated) == 1
    assert updated[0].before_data is not None
    assert updated[0].before_data["near_expiry_days"] == 200


# -- Dispatch ------------------------------------------------------------------


def test_a_near_expiry_batch_leaving_is_recorded_under_warn() -> None:
    """MARCH goes out, and the trail and the timeline both say it was short."""
    shop = _Shop()
    _rules(shop)
    note = shop.note(None)

    shop.dispatch(note)

    rows = _audit(shop, "delivery_note.near_expiry_dispatched")
    assert len(rows) == 1
    assert rows[0].after_data is not None
    assert "batch MARCH (expires 2027-03-31, 196 days left)" in str(
        rows[0].after_data["described"]
    )
    details = _event(shop, note.id, "DISPATCHED").details_json
    assert details is not None and "batch_warnings" in details


def test_outside_the_window_nothing_is_recorded() -> None:
    """The default thirty days: MARCH is six months out, so it is just stock."""
    shop = _Shop()
    note = shop.note(None)

    shop.dispatch(note)

    assert _audit(shop, "delivery_note.near_expiry_dispatched") == []


def test_reason_policy_refuses_a_near_expiry_dispatch_without_one() -> None:
    """Refused by line and batch, and nothing leaves."""
    shop = _Shop()
    _rules(shop, near="REASON")
    note = _approved(shop, shop.note(None))

    with pytest.raises(ValidationError, match="Line 1: batch MARCH"):
        shop.notes.dispatch_note(
            note.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
        )
    shop.session.rollback()

    assert shop.stock("MARCH").current_quantity == Decimal("10.0000")
    assert shop.session.get(DeliveryNote, note.id).status == "APPROVED"  # type: ignore[union-attr]


def test_a_reason_given_is_kept_beside_the_batch() -> None:
    """With a reason the near-expiry batch goes, and the trail says why."""
    shop = _Shop()
    _rules(shop, near="REASON")
    note = _approved(shop, shop.note(None))

    shop.notes.dispatch_note(
        note.id,
        firm_scope=shop.firm_id,
        actor_id=shop.actor_id,
        batch_reason="Customer clears short-dated stock",
    )

    rows = _audit(shop, "delivery_note.near_expiry_dispatched")
    assert rows[0].after_data is not None
    assert rows[0].after_data["reason"] == "Customer clears short-dated stock"
    details = _event(shop, note.id, "DISPATCHED").details_json
    assert details is not None
    assert details["batch_reason"] == "Customer clears short-dated stock"


def test_reason_policy_for_a_fefo_skip() -> None:
    """Choosing JUNE over MARCH wants a reason; given, it is kept with both."""
    shop = _Shop()
    _rules(shop, days=30, skip="REASON")
    note = _approved(shop, shop.note(shop.picks(JUNE="8")))

    with pytest.raises(ValidationError, match="skip an earlier-expiring batch"):
        shop.notes.dispatch_note(
            note.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
        )
    shop.session.rollback()

    shop.notes.dispatch_note(
        note.id,
        firm_scope=shop.firm_id,
        actor_id=shop.actor_id,
        batch_reason="Customer asked for the June batch",
    )
    skips = shop.fefo_skips()
    assert len(skips) == 1
    assert skips[0].after_data is not None
    assert skips[0].after_data["reason"] == "Customer asked for the June batch"


def test_the_check_says_beforehand_what_dispatch_will_ask() -> None:
    """The screen can ask for the reason before dispatch refuses."""
    shop = _Shop()
    _rules(shop, near="REASON", skip="REASON")
    fefo = _approved(shop, shop.note(None))

    check = shop.notes.batch_check(fefo.id, firm_scope=shop.firm_id)

    assert check.needs_reason is True
    assert [(item.line_number, item.kind) for item in check.findings] == [
        (1, "NEAR_EXPIRY")
    ]


def test_the_check_names_a_skip_and_is_quiet_when_nothing_applies() -> None:
    """JUNE chosen at thirty days: a skip and nothing near expiry."""
    shop = _Shop()
    _rules(shop, days=30)
    note = _approved(shop, shop.note(shop.picks(JUNE="8")))

    check = shop.notes.batch_check(note.id, firm_scope=shop.firm_id)

    assert [item.kind for item in check.findings] == ["FEFO_SKIP"]
    assert check.needs_reason is False, "RECORD wants no reason"


# -- The price floor (decision A2) ---------------------------------------------


def test_a_near_expiry_line_may_be_sold_below_the_floor() -> None:
    """Two of MARCH at 100 against a floor of 150: approved, and kept."""
    shop = _Shop()
    _rules(shop)
    _floor(shop)
    order = _order(shop, "2")

    SalesOrderService(shop.session).approve_order(
        order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )

    details = _event(shop, order.id, "APPROVED").details_json
    assert details is not None
    assert "price_warning" not in details
    kept = details["price_near_expiry"]
    assert isinstance(kept, dict)
    assert "batch MARCH" in str(kept["findings"])


def test_a_line_partly_from_a_fresh_batch_is_still_judged() -> None:
    """Eight takes MARCH's free two and six of JUNE, which is not near expiry."""
    shop = _Shop()
    _rules(shop)
    _floor(shop)
    order = _order(shop, "8")

    with pytest.raises(ValidationError, match="below its minimum price"):
        SalesOrderService(shop.session).approve_order(
            order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
        )


def test_a_firm_may_turn_the_exemption_off() -> None:
    """Off, the near-expiry line is judged like any other."""
    shop = _Shop()
    _rules(shop, below_floor=False)
    _floor(shop)
    order = _order(shop, "2")

    with pytest.raises(ValidationError, match="below its minimum price"):
        SalesOrderService(shop.session).approve_order(
            order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
        )


@pytest.mark.parametrize(("picked", "exempt"), [("MARCH", True), ("JUNE", False)])
def test_a_bill_is_judged_on_the_batches_its_note_shipped(
    picked: str, exempt: bool
) -> None:
    """A bill line from a dispatched note takes the batches the note recorded.

    MARCH is what expiry order would draw either way, so JUNE -- shipped by
    choice -- is judged as fresh stock: the recorded split, not a guess.
    """
    shop = _Shop()
    _rules(shop)
    note = shop.note(shop.picks(**{picked: "8"}))
    shop.dispatch(note)
    _floor(shop)
    line = shop.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None

    result = PriceFloorService(shop.session).check(
        shop.firm_id,
        [
            PricedLine(
                line_number=1,
                product_id=shop.product.id,
                stock_quantity=Decimal("8"),
                net_amount=Decimal("800"),
                warehouse_id=shop.warehouse_id,
                delivery_note_line_id=line.id,
            )
        ],
        as_of=NOTE_DATE,
    )

    assert len(result.findings) == 1
    assert (result.findings[0].exemption is not None) is exempt
    assert result.would_block is not exempt


# -- A customer's minimum shelf life (row 6) --------------------------------------


def _wants(shop: _Shop, days: int, *, policy: str = "BLOCK") -> None:
    """Give the order's customer a minimum shelf life, and the firm a rule."""
    from app.customers.models import Customer

    customer = shop.session.get(Customer, shop.order.customer_id)
    assert customer is not None
    customer.minimum_shelf_life_days = days
    shop.session.commit()
    BatchSalePolicyService(shop.session).update_settings(
        BatchSaleSettingsWrite(
            near_expiry_days=30,
            near_expiry_policy="WARN",
            fefo_skip_policy="RECORD",
            near_expiry_below_floor=True,
            shelf_life_policy=policy,  # type: ignore[arg-type]
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )


def test_earliest_expiry_passes_over_a_batch_too_short_for_the_customer() -> None:
    """MARCH has 196 days, the customer wants 200: JUNE goes instead."""
    shop = _Shop()
    _wants(shop, 200)
    note = shop.note(None)

    shop.dispatch(note)

    assert shop.drawn(note) == {"JUNE": Decimal("8.0000")}
    assert shop.stock("MARCH").reserved_quantity == Decimal("0.0000")


def test_a_short_batch_chosen_by_hand_is_refused_under_block() -> None:
    """The customer's rule is not a question for whoever dispatches."""
    shop = _Shop()
    _wants(shop, 200)
    note = _approved(shop, shop.note(shop.picks(MARCH="8")))

    check = shop.notes.batch_check(note.id, firm_scope=shop.firm_id)
    assert check.would_block is True
    assert [item.kind for item in check.findings][0] == "SHORT_SHELF_LIFE"
    with pytest.raises(ValidationError, match="minimum shelf life"):
        shop.notes.dispatch_note(
            note.id,
            firm_scope=shop.firm_id,
            actor_id=shop.actor_id,
            batch_reason="it is what we have",
        )


def test_under_warn_a_short_batch_goes_and_is_recorded() -> None:
    """WARN lets it through, with the trail saying so."""
    shop = _Shop()
    _wants(shop, 200, policy="WARN")
    note = shop.note(shop.picks(MARCH="8"))

    shop.dispatch(note)

    assert shop.drawn(note) == {"MARCH": Decimal("8.0000")}
    assert len(_audit(shop, "delivery_note.short_shelf_life_dispatched")) == 1


def test_the_picker_flags_a_short_batch_and_never_prefills_it() -> None:
    """Availability for the customer: MARCH flagged, the pre-fill on JUNE."""
    from app.batch_serial.services import BatchSerialService

    shop = _Shop()
    _wants(shop, 200)
    rows = BatchSerialService(shop.session).batch_availability(
        firm_scope=shop.firm_id,
        product_id=shop.product.id,
        warehouse_id=shop.warehouse_id,
        as_of=NOTE_DATE,
        quantity=Decimal("8"),
        sales_order_line_id=shop.order_line_id,
        keep_until=BatchSalePolicyService(shop.session).keep_until(
            shop.order.customer_id, on=NOTE_DATE
        ),
    )
    by_name = {row.batch_number: row for row in rows}

    assert by_name["MARCH"].short_for_customer is True
    assert by_name["MARCH"].fefo == Decimal("0")
    assert by_name["JUNE"].fefo == Decimal("8")


def test_approval_reserves_the_batch_the_customers_shelf_life_allows() -> None:
    """D-SELL-58: the hold went on a batch dispatch would never ship them.

    Driven 2026-10-05: a customer wanting 180 days ordered 8 and approval
    held the earlier, short-dated batch; the next order took the only batch
    that suited, and the first order's dispatch was refused "short by 6" with
    20 on the shelf. MARCH has 196 days and this customer wants 200, so the
    hold belongs on JUNE -- the batch the note will draw.
    """
    shop = _Shop()
    _wants(shop, 200)
    march_before = shop.stock("MARCH").reserved_quantity
    order = _order(shop, "6")

    SalesOrderService(shop.session).approve_order(
        order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )

    assert shop.stock("JUNE").reserved_quantity == Decimal("6.0000")
    assert shop.stock("MARCH").reserved_quantity == march_before


def test_a_hold_short_of_suitable_stock_names_the_batch_passed_over() -> None:
    """More than JUNE holds: the rest is a back order that says why."""
    shop = _Shop()
    _wants(shop, 200)
    order = _order(shop, "12")

    SalesOrderService(shop.session).approve_order(
        order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )

    assert shop.stock("JUNE").reserved_quantity == Decimal("10.0000")
    held = shop.session.scalars(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_number == order.order_number,
            InventoryTransaction.batch_id.is_(None),
        )
    ).all()
    assert [row.reserved_quantity_delta for row in held] == [Decimal("2.0000")]
    assert "Too short-dated for this customer's minimum shelf life: MARCH" in (
        held[0].remarks or ""
    )


def test_the_back_order_report_counts_no_expired_stock_and_knows_a_pin() -> None:
    """D-SELL-60: twelve pinned to a batch of ten read as covered.

    The report summed the product's stock in every batch, expired ones
    included. STALE's ten are no stock an order can have; a line pinned to
    JUNE can have only JUNE's.
    """
    shop = _Shop()
    orders = SalesOrderService(shop.session)
    pinned = orders.create_order(
        SalesOrderCreate(
            customer_id=shop.order.customer_id,
            branch_id=shop.order.branch_id,
            warehouse_id=shop.warehouse_id,
            order_date=NOTE_DATE,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal("12"),
                    unit_price=Decimal("100"),
                    pinned_batch_id=shop.batches["JUNE"].id,
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    orders.approve_order(pinned.id, firm_scope=shop.firm_id, actor_id=shop.actor_id)

    rows = {
        row.order_number: row for row in orders.back_orders(firm_scope=shop.firm_id)
    }

    assert rows[pinned.order_number].back_order_quantity == Decimal("2.0000")
    # MARCH and JUNE, ten each; STALE's ten have expired and are not counted.
    assert rows[pinned.order_number].available_stock == Decimal("20.0000")
    assert shop.order.order_number not in rows, "eight of MARCH's ten is covered"


def test_dispatch_lets_go_of_the_orders_own_hold_not_anothers() -> None:
    """D-SELL-58: 8 reserved on the later batch, dispatch refused "short by 6".

    Driven 2026-10-05, twice: a customer wanting shelf life had its 8 held on
    the batch it can take, another order held the earlier batch, and the
    first order's untouched note was refused for stock it had itself
    reserved. A stock row's reserved figure is every order's; dispatch let go
    by expiry, freed the other order's batch and kept its own hold in its
    own way. On a request's session, which does not flush on a read.
    """
    shop = _Shop()
    shop.session.autoflush = False
    # The shop's own order already holds eight of MARCH, the earlier batch.
    assert shop.stock("MARCH").reserved_quantity == Decimal("8.0000")
    _wants(shop, 200)
    order = _order(shop, "8")
    orders = SalesOrderService(shop.session)
    orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id)
    assert shop.stock("JUNE").reserved_quantity == Decimal("8.0000")
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None

    picker = {
        row.batch_number: row
        for row in BatchSerialService(shop.session).batch_availability(
            firm_scope=shop.firm_id,
            product_id=shop.product.id,
            warehouse_id=shop.warehouse_id,
            as_of=NOTE_DATE,
            quantity=Decimal("8"),
            sales_order_line_id=line.id,
            keep_until=BatchSalePolicyService(shop.session).keep_until(
                order.customer_id, on=NOTE_DATE
            ),
        )
    }
    assert picker["JUNE"].fefo == Decimal("8"), "the picker offers its own eight"
    assert picker["MARCH"].available_to_line == Decimal("2.0000")

    note = shop.notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=NOTE_DATE,
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("8"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    shop.dispatch(note)

    assert shop.drawn(note) == {"JUNE": Decimal("8.0000")}
    shop.session.expire_all()
    assert shop.stock("JUNE").reserved_quantity == Decimal("0.0000")
    assert shop.stock("MARCH").reserved_quantity == Decimal(
        "8.0000"
    ), "the other order still holds what it reserved"
