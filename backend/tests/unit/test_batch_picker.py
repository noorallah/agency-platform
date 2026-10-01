"""Choosing batches on a delivery line (backlog 79, decision A38).

With no choice, dispatch draws earliest expiry first, as it always has. With
one, it draws exactly the batches named, after checking each is the product's,
in date on the note's own date and adds up to what the line delivers -- and a
choice that is not the earliest-expiry split is kept in the audit trail.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.services import BatchSerialService
from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import (
    DeliveryNoteBatchPick,
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
)
from app.delivery_note.services import DeliveryNoteService
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_delivery_note_module import (
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _warehouse,
)

NOTE_DATE = date(2026, 9, 16)


class _Shop:
    """One firm with three batches on the shelf and an order for eight."""

    def __init__(self) -> None:
        """Stock STALE (expired), MARCH and JUNE, ten each; approve an order."""
        self.session: Session = _session_factory()()
        firm = _firm(self.session)
        branch = _branch(self.session, firm_id=firm.id)
        warehouse = _warehouse(self.session, firm_id=firm.id, branch_id=branch.id)
        customer = _customer(self.session, firm_id=firm.id)
        self.product = _product(self.session, firm_id=firm.id)
        self.firm_id: UUID = firm.id
        self.warehouse_id: UUID = warehouse.id
        self.actor_id = uuid4()
        inventory = InventoryService(self.session)
        self.batches: dict[str, BatchRecord] = {}
        for number, expiry in (
            ("STALE", date(2026, 8, 17)),
            ("MARCH", date(2027, 3, 31)),
            ("JUNE", date(2027, 6, 30)),
        ):
            batch = BatchRecord(
                firm_id=firm.id,
                product_id=self.product.id,
                batch_number=number,
                expiry_date=expiry,
                status="AVAILABLE",
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
            self.session.add(batch)
            self.session.flush()
            self.batches[number] = batch
            inventory.record_goods_receipt(
                firm_scope=firm.id,
                actor_id=self.actor_id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                storage_node_id=None,
                product_id=self.product.id,
                reference_number=f"GRN-{number}",
                transaction_date=date(2026, 8, 3),
                total_quantity=Decimal("10"),
                unit_cost=Decimal("0"),
                batch_id=batch.id,
            )
        self.session.commit()
        sales = SalesOrderService(self.session)
        created = sales.create_order(
            SalesOrderCreate(
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                order_date=NOTE_DATE,
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=self.product.id,
                        quantity=Decimal("8"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=self.actor_id,
        )
        self.order: SalesOrder = sales.approve_order(
            created.id, firm_scope=firm.id, actor_id=self.actor_id
        )
        source = self.session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == created.id)
        )
        assert source is not None
        self.order_line_id: UUID = source.id
        self.notes = DeliveryNoteService(self.session)

    def picks(self, **quantities: str) -> list[DeliveryNoteBatchPick]:
        """Return picks by batch name, e.g. ``picks(JUNE="8")``."""
        return [
            DeliveryNoteBatchPick(
                batch_id=self.batches[name].id, quantity=Decimal(quantity)
            )
            for name, quantity in quantities.items()
        ]

    def note(
        self,
        batches: list[DeliveryNoteBatchPick] | None,
        *,
        delivery_date: date = NOTE_DATE,
    ) -> DeliveryNote:
        """Raise a note for the whole eight, with these batches chosen."""
        return self.notes.create_note(
            DeliveryNoteCreate(
                sales_order_id=self.order.id,
                delivery_date=delivery_date,
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=self.order_line_id,
                        line_number=1,
                        current_delivery_quantity=Decimal("8"),
                        unit_price=Decimal("100"),
                        batches=batches,
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor_id,
        )

    def dispatch(self, note: DeliveryNote) -> None:
        """Approve and dispatch a note."""
        approved = self.notes.approve_note(
            note.id, firm_scope=self.firm_id, actor_id=self.actor_id
        )
        self.notes.dispatch_note(
            approved.id, firm_scope=self.firm_id, actor_id=self.actor_id
        )

    def drawn(self, note: DeliveryNote) -> dict[str, Decimal]:
        """Return what dispatch drew, by batch name."""
        names = {batch.id: name for name, batch in self.batches.items()}
        rows = self.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH",
                InventoryTransaction.reference_number == note.delivery_note_number,
            )
        ).all()
        return {
            names[row.batch_id]: abs(row.current_quantity_delta)
            for row in rows
            if row.batch_id is not None
        }

    def stock(self, name: str) -> InventoryRecord:
        """Return a batch's stock row."""
        row = self.session.scalar(
            select(InventoryRecord).where(
                InventoryRecord.batch_id == self.batches[name].id
            )
        )
        assert row is not None
        return row

    def fefo_skips(self) -> list[AuditLog]:
        """Return the FEFO-skip rows in the trail."""
        return list(
            self.session.scalars(
                select(AuditLog).where(AuditLog.action == "delivery_note.fefo_skipped")
            ).all()
        )


def test_availability_lists_every_batch_nearest_expiry_first() -> None:
    """The picker sees all three, the expired one flagged and not offered.

    MARCH holds the order's eight, so only two of it are free to anybody --
    but all ten are free to this order's own line, whose hold dispatch lets go
    first. The pre-fill is the split dispatch would draw unprompted.
    """
    shop = _Shop()

    rows = BatchSerialService(shop.session).batch_availability(
        firm_scope=shop.firm_id,
        product_id=shop.product.id,
        warehouse_id=shop.warehouse_id,
        as_of=NOTE_DATE,
        quantity=Decimal("8"),
        sales_order_line_id=shop.order_line_id,
        near_expiry_days=200,
    )

    by_name = {row.batch_number: row for row in rows}
    assert [row.batch_number for row in rows] == ["STALE", "MARCH", "JUNE"]
    assert by_name["STALE"].expired
    assert by_name["STALE"].available_to_line == Decimal("0")
    assert by_name["STALE"].fefo == Decimal("0"), "an expired batch is never filled"
    assert by_name["MARCH"].reserved == Decimal("8")
    assert by_name["MARCH"].available == Decimal("2")
    assert by_name["MARCH"].available_to_line == Decimal("10")
    assert by_name["MARCH"].fefo == Decimal("8")
    assert by_name["MARCH"].near_expiry, "196 days left, inside a 200-day window"
    assert by_name["MARCH"].days_to_expiry == 196
    assert by_name["JUNE"].available_to_line == Decimal("10")
    assert by_name["JUNE"].fefo == Decimal("0")
    assert not by_name["JUNE"].near_expiry


def test_availability_without_the_line_counts_every_hold() -> None:
    """Asked by nobody in particular, the order's hold is somebody else's."""
    shop = _Shop()

    rows = BatchSerialService(shop.session).batch_availability(
        firm_scope=shop.firm_id,
        product_id=shop.product.id,
        warehouse_id=shop.warehouse_id,
        as_of=NOTE_DATE,
    )

    march = next(row for row in rows if row.batch_number == "MARCH")
    assert march.available_to_line == Decimal("2")


def test_a_chosen_batch_is_the_batch_that_leaves() -> None:
    """Asked for JUNE, dispatch ships JUNE and gives MARCH back to the shelf."""
    shop = _Shop()
    note = shop.note(shop.picks(JUNE="8"))
    response = shop.notes.note_response(note)
    assert [(p.batch_id, p.quantity) for p in response.lines[0].batches] == [
        (shop.batches["JUNE"].id, Decimal("8.0000"))
    ]

    shop.dispatch(note)

    assert shop.drawn(note) == {"JUNE": Decimal("8.0000")}
    assert shop.stock("MARCH").reserved_quantity == Decimal("0.0000")
    assert shop.stock("MARCH").available_quantity == Decimal("10.0000")
    assert shop.stock("JUNE").current_quantity == Decimal("2.0000")
    skips = shop.fefo_skips()
    assert len(skips) == 1, "passing over the earlier batch is on the record"
    assert skips[0].after_data == {
        "line_number": 1,
        "chosen": {str(shop.batches["JUNE"].id): "8.0000"},
    }


def test_a_line_may_split_across_batches() -> None:
    """Five from MARCH and three from JUNE leave as two movements."""
    shop = _Shop()
    note = shop.note(shop.picks(MARCH="5", JUNE="3"))

    shop.dispatch(note)

    assert shop.drawn(note) == {"MARCH": Decimal("5.0000"), "JUNE": Decimal("3.0000")}
    assert shop.stock("MARCH").reserved_quantity == Decimal("0.0000")


def test_choosing_the_earliest_expiry_split_records_no_skip() -> None:
    """Confirming what dispatch would do anyway is not a decision to audit."""
    shop = _Shop()
    note = shop.note(shop.picks(MARCH="8"))

    shop.dispatch(note)

    assert shop.drawn(note) == {"MARCH": Decimal("8.0000")}
    assert shop.fefo_skips() == []


def test_no_choice_still_draws_earliest_expiry_first() -> None:
    """A note with no batches named behaves exactly as it did."""
    shop = _Shop()
    note = shop.note(None)

    shop.dispatch(note)

    assert shop.drawn(note) == {"MARCH": Decimal("8.0000")}
    assert shop.fefo_skips() == []


def test_batches_that_do_not_add_up_are_refused_at_dispatch() -> None:
    """Six chosen for a line of eight is refused, and nothing moves."""
    shop = _Shop()
    note = shop.note(shop.picks(JUNE="6"))

    with pytest.raises(ValidationError, match="add up to 6.0000"):
        shop.dispatch(note)


def test_a_batch_expired_on_the_notes_own_date_is_refused() -> None:
    """MARCH expires on the 31st; a note dated the 31st cannot ship it."""
    shop = _Shop()
    note = shop.note(shop.picks(MARCH="8"), delivery_date=date(2027, 3, 31))

    with pytest.raises(ValidationError, match="batch MARCH expired on 2027-03-31"):
        shop.dispatch(note)


def test_another_products_batch_is_refused_when_written() -> None:
    """A batch belongs to one product; naming another's is refused by line."""
    shop = _Shop()
    other = Product(
        firm_id=shop.firm_id,
        code="SKU-002",
        name="Product SKU-002",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    shop.session.add(other)
    shop.session.flush()
    stranger = BatchRecord(
        firm_id=shop.firm_id,
        product_id=other.id,
        batch_number="ELSEWHERE",
        status="AVAILABLE",
    )
    shop.session.add(stranger)
    shop.session.commit()

    with pytest.raises(ValidationError, match="not this product's"):
        shop.note([DeliveryNoteBatchPick(batch_id=stranger.id, quantity=Decimal("8"))])


def test_a_batch_named_twice_is_refused() -> None:
    """Two picks of one batch is one pick written badly."""
    shop = _Shop()

    with pytest.raises(ValidationError, match="named twice"):
        shop.note(
            [
                DeliveryNoteBatchPick(
                    batch_id=shop.batches["JUNE"].id, quantity=Decimal("4")
                ),
                DeliveryNoteBatchPick(
                    batch_id=shop.batches["JUNE"].id, quantity=Decimal("4")
                ),
            ]
        )


def test_an_empty_list_clears_the_choice_and_absent_keeps_it() -> None:
    """Absent leaves the picks alone; an empty list goes back to expiry order."""
    shop = _Shop()
    note = shop.note(shop.picks(JUNE="8"))

    def _rewrite(batches: list[DeliveryNoteBatchPick] | None) -> list[UUID]:
        """Rewrite the note with these picks; return the line's batch ids."""
        shop.notes.update_note(
            note.id,
            DeliveryNoteCreate(
                sales_order_id=shop.order.id,
                delivery_date=NOTE_DATE,
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=shop.order_line_id,
                        line_number=1,
                        current_delivery_quantity=Decimal("8"),
                        unit_price=Decimal("100"),
                        batches=batches,
                    )
                ],
            ),
            firm_scope=shop.firm_id,
            actor_id=shop.actor_id,
        )
        response = shop.notes.note_response(note)
        return [pick.batch_id for pick in response.lines[0].batches]

    assert _rewrite(None) == [shop.batches["JUNE"].id]
    assert _rewrite([]) == []
