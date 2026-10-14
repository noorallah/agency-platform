"""The rest of stock by lot (L2 step 7).

`docs/design/LOT_COST_DESIGN.md`, section 3.6, one test per row. A transfer
carries the lot and moves no value; a write-off, an adjustment down and a
hold name a lot -- the first in the order goods leave when the person named
none -- and go at its cost; stock found is a new lot at a typed cost or the
newest lot's; a repack makes a new lot at the value used; and a firm costing
by lot never runs below zero. A firm on Average moves exactly as before.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.branches.models import Warehouse
from app.core.exceptions import ValidationError
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    InventoryTransaction,
    StockLedgerEntry,
)
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    QuarantineAction,
    StockQuarantineCreate,
    StockTransferCreate,
    StockWriteOffCreate,
)
from app.inventory.services import InventoryService
from app.inventory.services.repacking import (
    RepackLineWrite,
    RepackService,
    RepackWrite,
)
from app.inventory.services.stock_transfers import (
    StockTransferDispatch,
    StockTransferLineWrite,
    StockTransferReceive,
    StockTransferService,
    StockTransferWrite,
)
from app.products.models import Product
from tests.unit.test_lot_selling import _ByLot

ON = date(2026, 8, 5)


class _Shop(_ByLot):
    """The by-lot counter firm with a second warehouse and a pack product.

    EARLY (expiring first) holds ten units valued at 40 and LATE ten at 36;
    each stock row also holds the parent's ten from before the switch.
    """

    def __init__(self, *, by_lot: bool = True) -> None:
        """Add the depot and the product a repack makes."""
        super().__init__(by_lot=by_lot)
        self.depot = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="WH-002",
            name="Depot",
            display_name="Depot",
            status="ACTIVE",
            is_default=False,
        )
        self.pack = Product(
            firm_id=self.firm.id,
            code="SKU-PACK",
            name="Pack",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.session.add_all([self.depot, self.pack])
        self.session.commit()
        self.stock = InventoryService(self.session)

    def worth(self, name: str) -> tuple[Decimal, Decimal]:
        """Return what one lot holds and is worth."""
        return self.lot_worth(self.batches[name].id)

    def lot_worth(self, lot_id: UUID) -> tuple[Decimal, Decimal]:
        """Return what a lot, by id, holds and is worth."""
        self.session.expire_all()
        row = self.session.scalars(
            select(BatchValuation).where(BatchValuation.batch_id == lot_id)
        ).one()
        return Decimal(row.quantity_on_hand), Decimal(row.total_value)

    def cost_of(self, movement: InventoryTransaction) -> Decimal:
        """Return the value one movement carried."""
        return Decimal(
            self.session.scalars(
                select(StockLedgerEntry.total_cost).where(
                    StockLedgerEntry.transaction_id == movement.id
                )
            ).one()
        )

    def write_off(self, quantity: str, **extra: object) -> InventoryTransaction:
        """Write off some of the item as damaged."""
        return self.stock.write_off_stock(
            StockWriteOffCreate.model_validate(
                {
                    "branch_id": self.branch.id,
                    "warehouse_id": self.warehouse.id,
                    "product_id": self.drug.id,
                    "reason": "DAMAGE",
                    "quantity": quantity,
                    "transaction_date": ON,
                }
                | extra
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
        )

    def adjust(self, quantity: str, **extra: object) -> InventoryTransaction:
        """Adjust the item by a signed quantity."""
        return self.stock.create_adjustment(
            InventoryAdjustmentCreate.model_validate(
                {
                    "branch_id": self.branch.id,
                    "warehouse_id": self.warehouse.id,
                    "product_id": self.drug.id,
                    "quantity": quantity,
                    "transaction_date": ON,
                }
                | extra
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
            enforce_limit=False,
        )


def test_a_transfer_carries_the_lot_and_moves_no_value() -> None:
    """Four of the first lot go to the depot; the lot is worth what it was."""
    shop = _Shop()

    outbound, inbound = shop.stock.transfer_stock(
        StockTransferCreate(
            branch_id=shop.branch.id,
            from_warehouse_id=shop.warehouse.id,
            to_warehouse_id=shop.depot.id,
            product_id=shop.drug.id,
            quantity=Decimal("4"),
            transaction_date=ON,
        ),
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
    )

    early = shop.batches["EARLY"].id
    assert (outbound.batch_id, inbound.batch_id) == (early, early)
    assert shop.cost_of(outbound) == shop.cost_of(inbound) == Decimal("160")
    assert shop.worth("EARLY") == (Decimal("10"), Decimal("400"))
    at_depot = shop.session.scalars(
        select(InventoryRecord).where(InventoryRecord.warehouse_id == shop.depot.id)
    ).one()
    assert (at_depot.batch_id, at_depot.current_quantity) == (early, Decimal("4"))


def test_a_transfer_document_sends_a_lot_and_its_value_through_transit() -> None:
    """A line naming no lot is sent from the first; dispatch and receipt are even."""
    shop = _Shop()
    service = StockTransferService(shop.session)
    draft = service.create(
        StockTransferWrite(
            transfer_date=ON,
            from_warehouse_id=shop.warehouse.id,
            to_warehouse_id=shop.depot.id,
            lines=[
                StockTransferLineWrite(product_id=shop.drug.id, quantity=Decimal("3"))
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )

    service.dispatch(
        draft.id, StockTransferDispatch(), firm_id=shop.firm.id, actor_id=shop.actor
    )
    assert draft.dispatched_value == Decimal("120")
    assert shop.worth("EARLY") == (Decimal("10"), Decimal("400"))
    service.receive(
        draft.id, StockTransferReceive(), firm_id=shop.firm.id, actor_id=shop.actor
    )

    (line,) = service.lines(draft.id)
    assert line.batch_id == shop.batches["EARLY"].id
    assert shop.worth("EARLY") == (Decimal("10"), Decimal("400"))


def test_a_write_off_naming_no_lot_leaves_the_first_at_its_cost() -> None:
    """Four written off leave EARLY at 40, not the item's average."""
    shop = _Shop()

    movement = shop.write_off("4")

    assert movement.batch_id == shop.batches["EARLY"].id
    assert shop.cost_of(movement) == Decimal("160")
    assert shop.worth("EARLY") == (Decimal("6"), Decimal("240"))


def test_more_than_one_lot_holds_is_refused_with_the_lots_named() -> None:
    """Twenty-five is in no one lot: each movement names one."""
    shop = _Shop()

    with pytest.raises(ValidationError) as refused:
        shop.write_off("25")

    assert "EARLY 20" in refused.value.message
    assert "LATE 20" in refused.value.message


def test_an_adjustment_down_naming_no_lot_leaves_the_first_at_its_cost() -> None:
    """Two taken off by an adjustment leave EARLY at 40 each."""
    shop = _Shop()

    movement = shop.adjust("-2")

    assert movement.batch_id == shop.batches["EARLY"].id
    assert shop.cost_of(movement) == Decimal("80")
    assert shop.worth("EARLY") == (Decimal("8"), Decimal("320"))


def test_an_adjustment_up_into_a_named_lot_comes_in_at_its_cost() -> None:
    """Two found in LATE are worth 36 each; a typed cost there is refused."""
    shop = _Shop()

    movement = shop.adjust("2", batch_id=str(shop.batches["LATE"].id))

    assert shop.cost_of(movement) == Decimal("72")
    assert shop.worth("LATE") == (Decimal("12"), Decimal("432"))
    with pytest.raises(ValidationError, match="new lot"):
        shop.adjust("1", batch_id=str(shop.batches["LATE"].id), unit_cost="30")


def test_stock_found_with_no_lot_named_is_a_new_lot() -> None:
    """At the typed cost; the next one, left blank, at the newest lot's."""
    shop = _Shop()

    first = shop.adjust("3", unit_cost="30")
    second = shop.adjust("2")

    lot = shop.session.get(BatchRecord, first.batch_id)
    assert lot is not None
    assert lot.source_document_type == "ADJUSTMENT"
    assert lot.source_document_id == first.id
    assert lot.received_on == ON
    assert lot.has_printed_batch is False
    assert shop.lot_worth(lot.id) == (Decimal("3"), Decimal("90"))
    assert second.batch_id not in {first.batch_id, None}
    assert shop.cost_of(second) == Decimal("60")


def test_a_hold_naming_no_lot_holds_the_first_and_moves_no_value() -> None:
    """Quarantine is a bucket inside the lot's own row."""
    shop = _Shop()

    movement = shop.stock.quarantine_stock(
        StockQuarantineCreate(
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            product_id=shop.drug.id,
            action=QuarantineAction.HOLD,
            quantity=Decimal("3"),
            transaction_date=ON,
        ),
        firm_scope=shop.firm.id,
        actor_id=shop.actor,
    )

    assert movement.batch_id == shop.batches["EARLY"].id
    assert shop.worth("EARLY") == (Decimal("10"), Decimal("400"))


def test_a_repack_makes_a_new_lot_at_the_value_used() -> None:
    """Four of EARLY (160) make two packs, a lot of their own; cancel removes it."""
    shop = _Shop()
    service = RepackService(shop.session)

    repack = service.post(
        RepackWrite(
            repack_date=ON,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            lines=[
                RepackLineWrite(
                    kind="CONSUME", product_id=shop.drug.id, quantity=Decimal("4")
                ),
                RepackLineWrite(
                    kind="PRODUCE", product_id=shop.pack.id, quantity=Decimal("2")
                ),
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )

    lines = service.lines(repack.id)
    consumed, produced = lines
    assert consumed.batch_id == shop.batches["EARLY"].id
    assert consumed.value == Decimal("160")
    lot = shop.session.get(BatchRecord, produced.batch_id)
    assert lot is not None
    assert (lot.source_document_type, lot.source_document_id) == ("REPACK", repack.id)
    assert lot.source_document_line_id == produced.id
    assert shop.lot_worth(lot.id) == (Decimal("2"), Decimal("160"))

    service.cancel(repack.id, "wrong pack", firm_id=shop.firm.id, actor_id=shop.actor)

    shop.session.expire_all()
    assert lot.is_deleted is True
    assert shop.worth("EARLY") == (Decimal("10"), Decimal("400"))


def test_a_firm_costing_by_lot_never_runs_below_zero() -> None:
    """The item allows negative stock, but no lot holds the units."""
    shop = _Shop()
    shop.drug.allow_negative_stock = True
    shop.session.commit()

    with pytest.raises(ValidationError, match="cannot be taken off"):
        shop.adjust("-25", batch_id=str(shop.batches["EARLY"].id))


def test_a_firm_on_average_moves_as_before() -> None:
    """No lot is chosen, a typed cost is refused and negative stock is allowed."""
    shop = _Shop(by_lot=False)
    shop.drug.allow_negative_stock = True
    shop.session.commit()

    with pytest.raises(ValidationError, match="holds 0"):
        shop.write_off("4")
    with pytest.raises(ValidationError, match="new lot"):
        shop.adjust("1", unit_cost="30")
    movement = shop.adjust("-25", batch_id=str(shop.batches["EARLY"].id))
    assert movement.batch_id == shop.batches["EARLY"].id
