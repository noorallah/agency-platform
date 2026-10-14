"""The switch-over from Average to costing by lot (L2 step 9).

`docs/design/LOT_COST_DESIGN.md`, section 4.4. Every item's stock becomes
lots at its average on the day named, adding up to its value to the paisa
with the rounding on the largest lot; no journal is posted; stock may not
move on an earlier day afterwards; and the switch is one way.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.batch_serial.services import BatchSerialService
from app.branches.models import Warehouse
from app.common.firm_metadata import firm_today
from app.core.exceptions import BusinessRuleError, ValidationError
from app.delivery_note.models import DeliveryNoteLineBatch
from app.finance.models import JournalEntry
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    InventoryTransaction,
    ProductValuation,
    StockLotSettings,
)
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.inventory.services.lot_switch_over import LotSwitchOverService
from app.products.models import Product
from app.sales_invoice.services import SalesInvoiceService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

SWITCH_DAY = date(2026, 8, 3)


class _Trader(_Firm):
    """A firm on Average with stock in two warehouses, batched and not.

    SKU-001 holds 100 at 60 in the first warehouse and 30 at 70 in a second,
    neither in a batch. SKU-BAT holds three batches: one each at 2.00 in B1
    and B2, four at 1.50 in B3 -- ten for six, an average that does not
    divide evenly.
    """

    def __init__(self, session: Session | None = None) -> None:
        """Build the firm and its stock, all dated before the switch day."""
        super().__init__(session or _session_factory()())
        self.stages(quotation=False, sales_order=False, delivery_note=False)
        self.actor = uuid4()
        self.stock = InventoryService(self.session)
        self.second = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="WH-002",
            name="Warehouse WH-002",
            display_name="Warehouse WH-002",
            status="ACTIVE",
        )
        self.session.add(self.second)
        self.session.commit()
        self.receive(self.product.id, "30", "70", warehouse_id=self.second.id)
        self.batched = Product(
            firm_id=self.firm.id,
            code="SKU-BAT",
            name="Batched item",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.session.add(self.batched)
        self.session.commit()
        self.batches = {
            number: self.batch_in(number, quantity, cost)
            for number, quantity, cost in (
                ("B1", "1", "2"),
                ("B2", "1", "2"),
                ("B3", "4", "1.5"),
            )
        }
        self.service = LotSwitchOverService(self.session)

    def receive(
        self,
        product_id: UUID,
        quantity: str,
        cost: str,
        *,
        warehouse_id: UUID | None = None,
        batch_id: UUID | None = None,
        on: date = date(2026, 8, 2),
    ) -> None:
        """Take goods in as a receipt does, on Average."""
        self.stock.record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=self.actor,
            branch_id=self.branch.id,
            warehouse_id=warehouse_id or self.warehouse.id,
            storage_node_id=None,
            product_id=product_id,
            reference_number=f"GRN-{uuid4().hex[:6]}",
            transaction_date=on,
            total_quantity=Decimal(quantity),
            unit_cost=Decimal(cost),
            batch_id=batch_id,
        )
        self.session.commit()

    def batch_in(self, number: str, quantity: str, cost: str) -> BatchRecord:
        """Register a batch the way an Average firm's receipt does, and stock it."""
        batch = BatchSerialService(self.session).resolve_for_receipt(
            firm_scope=self.firm.id,
            actor_id=self.actor,
            product_id=self.batched.id,
            batch_number=number,
        )
        self.receive(self.batched.id, quantity, cost, batch_id=batch.id)
        return batch

    def valuation(self, product_id: UUID) -> ProductValuation:
        """Return an item's running valuation."""
        self.session.expire_all()
        return self.session.scalars(
            select(ProductValuation).where(ProductValuation.product_id == product_id)
        ).one()

    def lot_values(self, product_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return each lot of an item: what it holds and what it is worth."""
        self.session.expire_all()
        return {
            row.batch_id: (Decimal(row.quantity_on_hand), Decimal(row.total_value))
            for row in self.session.scalars(
                select(BatchValuation).where(BatchValuation.product_id == product_id)
            )
        }

    def adjust(self, quantity: str, on: date) -> None:
        """Post a stock adjustment of the plain item, on a day."""
        self.stock.create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.product.id,
                quantity=Decimal(quantity),
                reference_number=f"ADJ-{uuid4().hex[:6]}",
                reference_type="ADJUSTMENT",
                transaction_date=on,
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
        )


def test_the_preview_counts_what_the_switch_would_carry() -> None:
    """Two items, three batches plus one new lot, 136 units, 8,110.00."""
    firm = _Trader()

    preview = firm.service.preview(firm.firm.id, SWITCH_DAY)

    assert preview.refusals == ()
    assert preview.items == 2
    assert preview.lots == 4
    assert preview.quantity == Decimal("136")
    assert preview.stock_value == Decimal("8110")
    assert preview.suggested_on == date(2026, 8, 2)
    assert (
        firm.session.scalar(select(func.count(BatchValuation.id))) == 0
    ), "a preview writes nothing"


def test_the_suggested_day_is_one_the_switch_accepts() -> None:
    """D-STK-73: stock moved after the year began, so that day is suggested.

    The year start was suggested and then refused as earlier than the last
    movement; the suggestion is now the later of the two.
    """
    firm = _Trader()

    suggested = firm.service.suggested_day(firm.firm.id)

    assert suggested == date(2026, 8, 2)
    assert firm.service.preview(firm.firm.id, suggested).refusals == ()


def test_with_no_movement_since_the_year_began_its_first_day_is_suggested() -> None:
    """D-STK-73: stock last moved in the year before, so the year start."""
    firm = _Trader()
    firm.session.execute(
        update(InventoryTransaction).values(transaction_date=date(2025, 12, 1))
    )
    firm.session.commit()

    assert firm.service.suggested_day(firm.firm.id) == date(2026, 4, 1)


def test_the_switch_carries_every_item_into_lots_at_its_average() -> None:
    """Batches become lots, unbatched stock one lot, values exact, no journal."""
    firm = _Trader()
    plain_before = firm.valuation(firm.product.id)
    plain_value = Decimal(plain_before.total_value)
    journals = firm.session.scalar(select(func.count(JournalEntry.id)))

    view = firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)

    assert (view.costing_method, view.switched_on) == ("BY_LOT", SWITCH_DAY)
    # The batched item: the residual of 10.00 / 6 on its largest lot.
    lots = firm.lot_values(firm.batched.id)
    b1, b2, b3 = (firm.batches[number].id for number in ("B1", "B2", "B3"))
    assert set(lots) == {b1, b2, b3}
    assert lots[b1] == (Decimal("1"), Decimal("1.6667"))
    assert lots[b2] == (Decimal("1"), Decimal("1.6667"))
    assert lots[b3] == (Decimal("4"), Decimal("6.6666")), "the residual goes here"
    assert sum(value for _, value in lots.values()) == Decimal("10")
    for number in ("B1", "B2", "B3"):
        batch = firm.session.get(BatchRecord, firm.batches[number].id)
        assert batch is not None
        assert batch.source_document_type == "CARRIED_FORWARD"
        assert batch.received_on == SWITCH_DAY
    # The plain item: one new lot, named by both warehouses' rows.
    [(lot_id, (quantity, value))] = firm.lot_values(firm.product.id).items()
    assert (quantity, value) == (Decimal("130"), plain_value)
    lot = firm.session.get(BatchRecord, lot_id)
    assert lot is not None
    assert (lot.has_printed_batch, lot.source_document_type) == (
        False,
        "CARRIED_FORWARD",
    )
    assert lot.batch_number == lot.lot_reference
    rows = firm.session.scalars(
        select(InventoryRecord).where(InventoryRecord.product_id == firm.product.id)
    ).all()
    assert {row.warehouse_id for row in rows} == {firm.warehouse.id, firm.second.id}
    assert {row.batch_id for row in rows} == {lot_id}
    # Nothing re-valued, nothing posted, every item stamped.
    after = firm.valuation(firm.product.id)
    assert Decimal(after.total_value) == plain_value
    assert Decimal(after.quantity_on_hand) == Decimal("130")
    assert {
        row.costing_method for row in firm.session.scalars(select(ProductValuation))
    } == {"BY_LOT"}
    assert firm.session.scalar(select(func.count(JournalEntry.id))) == journals


def test_after_the_switch_a_sale_leaves_from_the_carried_lot() -> None:
    """Four sold leave the carried lot at the carried average."""
    firm = _Trader()
    firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)
    [lot_id] = firm.lot_values(firm.product.id)
    average = Decimal(firm.valuation(firm.product.id).average_cost)

    bills = SalesInvoiceService(firm.session)
    draft = bills.create_invoice(
        firm.bare_bill(Decimal("4")), firm_id=firm.firm.id, actor_id=firm.actor
    )
    bills.approve_invoice(draft.id, firm_scope=firm.firm.id, actor_id=firm.actor)

    [pick] = firm.session.scalars(select(DeliveryNoteLineBatch)).all()
    assert pick.batch_id == lot_id
    assert Decimal(pick.quantity) == Decimal("4")
    assert Decimal(pick.cost_amount or 0) == (Decimal("4") * average).quantize(
        Decimal("0.0001")
    )
    assert firm.lot_values(firm.product.id)[lot_id][0] == Decimal("126")


def test_a_movement_before_the_switch_day_is_refused_afterwards() -> None:
    """Dated before the day: refused, naming it; on the day: allowed."""
    firm = _Trader()
    firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)

    with pytest.raises(ValidationError, match="costing by lot on 2026-08-03"):
        firm.adjust("5", SWITCH_DAY - timedelta(days=1))
    firm.session.rollback()
    firm.adjust("5", SWITCH_DAY)


def test_a_firm_on_average_may_still_date_a_movement_back() -> None:
    """No switch, no day: an earlier date is accepted as before."""
    firm = _Trader()

    firm.adjust("5", date(2026, 7, 1))


def test_each_reason_to_refuse_is_named() -> None:
    """A future day, a day before the last movement, an item below zero."""
    firm = _Trader()
    tomorrow = firm_today(firm.session, firm.firm.id) + timedelta(days=1)

    assert any(
        "after today" in reason
        for reason in firm.service.preview(firm.firm.id, tomorrow).refusals
    )
    assert any(
        "last moved on 2026-08-02" in reason
        for reason in firm.service.preview(firm.firm.id, date(2026, 8, 1)).refusals
    )

    row = firm.session.scalars(
        select(InventoryRecord).where(
            InventoryRecord.product_id == firm.product.id,
            InventoryRecord.warehouse_id == firm.second.id,
        )
    ).one()
    row.current_quantity = Decimal("-1")
    firm.session.commit()
    refusals = firm.service.preview(firm.firm.id, SWITCH_DAY).refusals
    assert any(
        "below zero" in reason and "SKU-001" in reason for reason in refusals
    ), refusals
    with pytest.raises(BusinessRuleError, match="below zero"):
        firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)
    assert firm.service.settings(firm.firm.id).costing_method == "AVERAGE"
    assert firm.session.scalar(select(func.count(BatchValuation.id))) == 0


def test_unbatched_stock_held_for_an_order_is_refused() -> None:
    """Reserved stock with no batch could not be released into a lot."""
    firm = _Trader()
    row = firm.session.scalars(
        select(InventoryRecord).where(
            InventoryRecord.product_id == firm.product.id,
            InventoryRecord.warehouse_id == firm.warehouse.id,
        )
    ).one()
    row.reserved_quantity = Decimal("2")
    firm.session.commit()

    refusals = firm.service.preview(firm.firm.id, SWITCH_DAY).refusals

    assert any("reserved" in reason and "SKU-001" in reason for reason in refusals)


def test_the_switch_is_one_way() -> None:
    """Switched once: the preview says so and a second switch is refused."""
    firm = _Trader()
    firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)

    refusals = firm.service.preview(firm.firm.id, SWITCH_DAY).refusals
    assert any("already costs its stock by lot" in reason for reason in refusals)
    with pytest.raises(BusinessRuleError, match="already costs"):
        firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)


def test_billing_without_stock_is_set_only_on_a_by_lot_firm() -> None:
    """Refused on Average; on by lot it saves, and nothing else is writable."""
    firm = _Trader()
    settings = firm.service.settings(firm.firm.id)
    assert (settings.costing_method, settings.version) == ("AVERAGE", None)

    with pytest.raises(BusinessRuleError, match="on Average"):
        firm.service.update_settings(
            firm_id=firm.firm.id,
            actor_id=firm.actor,
            allow_billing_without_stock=True,
        )
    assert firm.session.scalar(select(func.count(StockLotSettings.id))) == 0

    switched = firm.service.switch(firm.firm.id, SWITCH_DAY, firm.actor)
    saved = firm.service.update_settings(
        firm_id=firm.firm.id,
        actor_id=firm.actor,
        allow_billing_without_stock=True,
        expected_version=switched.version,
    )
    assert saved.allow_billing_without_stock is True
    assert (saved.costing_method, saved.switched_on) == ("BY_LOT", SWITCH_DAY)
    assert saved.version is not None and switched.version is not None
    assert saved.version > switched.version
