"""The switch-over: a firm trading on Average moves to costing by lot.

`docs/design/LOT_COST_DESIGN.md`, section 4.4 (L2 step 9). Every item's
stock on hand becomes lots at the item's average on the day named: a batch
that holds stock becomes a lot of its own, and stock with no batch becomes
one new lot per item whose stock rows then name it. Nothing is re-valued and
no journal is posted -- each item's lots add up to its value before the
switch to the paisa, and the switch rolls back if one does not. The switch
is one way, and no saved bill line is touched.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.utils.money import quantize_money
from app.finance.models import FinancialYear
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    InventoryTransaction,
    ProductValuation,
    StockLotSettings,
)
from app.inventory.schemas.inventory import InventoryTransactionType
from app.inventory.services.lots import FIRM_BY_LOT, LotSource
from app.products.models import Product

#: What ``stock_lot_settings.costing_method`` reads for a firm on Average.
FIRM_AVERAGE = "AVERAGE"
#: What ``product_valuations.costing_method`` reads for an item costed by lot;
#: the value `InventoryService` reads (``COSTING_BY_LOT``).
ITEM_BY_LOT = "BY_LOT"
#: The source every lot the switch-over makes, or turns a batch into, carries.
CARRIED_FORWARD = "CARRIED_FORWARD"
#: Movements that change only which bucket holds the goods, never what the
#: firm owns, and so never what a lot holds (``_Movement.revalues``).
_NOT_OWNING = (
    InventoryTransactionType.QUARANTINE_HOLD.value,
    InventoryTransactionType.QUARANTINE_RELEASE.value,
)
ZERO = Decimal("0")
#: The scale of ``batch_valuations.unit_cost``.
UNIT_COST_SCALE = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class LotSettingsView:
    """A firm's costing method as the settings screen shows it."""

    costing_method: str
    switched_on: date | None
    allow_billing_without_stock: bool
    #: The settings row's version; None while the firm has no row.
    version: int | None


@dataclass(frozen=True, slots=True)
class SwitchPreview:
    """What a switch on a day would do, and what stops it, if anything."""

    on: date
    suggested_on: date
    items: int
    lots: int
    quantity: Decimal
    stock_value: Decimal
    refusals: tuple[str, ...]


@dataclass(slots=True)
class _ItemPlan:
    """One item's stock as the switch carries it into lots."""

    product_id: UUID
    quantity: Decimal
    value: Decimal
    average: Decimal
    #: What each lot will hold, keyed by batch; None is the stock no batch
    #: names, which becomes one new lot.
    lots: dict[UUID | None, Decimal] = field(default_factory=dict)


@dataclass(slots=True)
class _Plan:
    """Every item the switch carries, and the refusals that stop it."""

    items: list[_ItemPlan]
    refusals: list[str]


class LotSwitchOverService:
    """Read and change a firm's lot settings, and switch it to by lot."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it commits on its own actions."""
        self._session = session

    # ---- settings --------------------------------------------------------

    def settings(self, firm_id: UUID) -> LotSettingsView:
        """Return the firm's lot settings, or Average's defaults with no row."""
        row = self._row(firm_id)
        if row is None:
            return LotSettingsView(
                costing_method=FIRM_AVERAGE,
                switched_on=None,
                allow_billing_without_stock=False,
                version=None,
            )
        return self._view(row)

    def settings_row(self, firm_id: UUID) -> StockLotSettings | None:
        """Return the firm's live settings row, if it has one."""
        return self._row(firm_id)

    def update_settings(
        self,
        *,
        firm_id: UUID,
        actor_id: UUID,
        allow_billing_without_stock: bool,
        expected_version: int | None = None,
    ) -> LotSettingsView:
        """Set whether the firm may bill goods no lot holds (section 3.7).

        The only writable setting: the costing method and its day change only
        by the switch. Refused while the firm is on Average, where it has no
        effect.

        Raises:
            BusinessRuleError: If the firm is on Average.
            ConflictError: If the row moved past ``expected_version``.

        """
        from app.core.concurrency import assert_version

        row = self._row(firm_id)
        if row is None or row.costing_method != FIRM_BY_LOT:
            raise BusinessRuleError(
                "Billing without stock applies only to a firm that costs its "
                "stock by lot. This firm is on Average; switch it first."
            )
        assert_version(row.version, expected_version)
        before = self._snapshot(row)
        if row.allow_billing_without_stock != allow_billing_without_stock:
            row.allow_billing_without_stock = allow_billing_without_stock
            row.updated_by = actor_id
            self._session.flush()
            record_audit(
                self._session,
                action="stock_lot_settings.updated",
                entity_type="stock_lot_settings",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=before,
                after_data=self._snapshot(row),
            )
            self._session.commit()
        return self._view(row)

    # ---- the switch ------------------------------------------------------

    def preview(self, firm_id: UUID, on: date) -> SwitchPreview:
        """Say what switching on ``on`` would do; writes nothing."""
        plan = self._plan(firm_id, on)
        return SwitchPreview(
            on=on,
            suggested_on=self.suggested_day(firm_id),
            items=len(plan.items),
            lots=sum(len(item.lots) for item in plan.items),
            quantity=sum((item.quantity for item in plan.items), ZERO),
            stock_value=quantize_money(sum((item.value for item in plan.items), ZERO)),
            refusals=tuple(plan.refusals),
        )

    def switch(self, firm_id: UUID, on: date, actor_id: UUID) -> LotSettingsView:
        """Carry every item's stock into lots and cost the firm by lot.

        One transaction: staged, checked item by item, then committed once.

        Raises:
            BusinessRuleError: If anything in the preview refuses it, or an
                item's lots would not add up to what it held before.

        """
        plan = self._plan(firm_id, on)
        if plan.refusals:
            raise BusinessRuleError(
                "The firm cannot switch to costing by lot. " + " ".join(plan.refusals),
                details={"refusals": plan.refusals},
            )
        try:
            row = self._locked_row(firm_id, actor_id)
            if row.costing_method == FIRM_BY_LOT:
                raise BusinessRuleError(self._already_by_lot(row))
            before = self._snapshot(row)
            source = LotSource(
                document_type=CARRIED_FORWARD,
                document_id=row.id,
                line_id=row.id,
                document_number=f"CARRIED FORWARD {on.isoformat()}",
                received_on=on,
            )
            for item in plan.items:
                self._carry(item, firm_id=firm_id, actor_id=actor_id, source=source)
            for valuation in self._session.scalars(
                select(ProductValuation).where(
                    ProductValuation.firm_id == firm_id,
                    ProductValuation.is_deleted.is_(False),
                )
            ):
                valuation.costing_method = ITEM_BY_LOT
                valuation.updated_by = actor_id
            row.costing_method = FIRM_BY_LOT
            row.switched_on = on
            row.updated_by = actor_id
            self._session.flush()
            self._assert_carried_exactly(firm_id, plan.items)
            record_audit(
                self._session,
                action="stock_lot_settings.switched_to_by_lot",
                entity_type="stock_lot_settings",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=before,
                after_data={
                    **self._snapshot(row),
                    "items": len(plan.items),
                    "lots": sum(len(item.lots) for item in plan.items),
                    "stock_value": str(
                        quantize_money(sum((i.value for i in plan.items), ZERO))
                    ),
                },
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return self._view(row)

    def suggested_day(self, firm_id: UUID) -> date:
        """Return the first day of the firm's current financial year.

        The year the books hold for today, where one is set up; otherwise
        the year the firm's own start month gives (section 4.4, rule 6).
        """
        today = firm_today(self._session, firm_id)
        starts_on = self._session.scalar(
            select(FinancialYear.starts_on)
            .where(
                FinancialYear.firm_id == firm_id,
                FinancialYear.is_deleted.is_(False),
                FinancialYear.starts_on <= today,
                FinancialYear.ends_on >= today,
            )
            .order_by(FinancialYear.starts_on.desc())
            .limit(1)
        )
        if starts_on is not None:
            return starts_on
        year_start = FirmMetadataReader(self._session).get(firm_id).financial_year_start
        month = year_start.month if year_start is not None else 4
        year = today.year if today.month >= month else today.year - 1
        return date(year, month, 1)

    # ---- planning --------------------------------------------------------

    def _plan(self, firm_id: UUID, on: date) -> _Plan:
        """Work out every item's lots and every reason the switch is refused."""
        refusals: list[str] = []
        row = self._row(firm_id)
        if row is not None and row.costing_method == FIRM_BY_LOT:
            refusals.append(self._already_by_lot(row))
        today = firm_today(self._session, firm_id)
        if on > today:
            refusals.append(
                f"The switch-over day {on.isoformat()} is after today "
                f"({today.isoformat()})."
            )
        latest = self._session.scalar(
            select(func.max(InventoryTransaction.transaction_date)).where(
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
            )
        )
        if latest is not None and on < latest:
            refusals.append(
                f"Stock last moved on {latest.isoformat()}, so the switch-over "
                "day cannot be earlier: the average carried has to be the "
                "average on that day."
            )

        valuations = {
            valuation.product_id: valuation
            for valuation in self._session.scalars(
                select(ProductValuation).where(
                    ProductValuation.firm_id == firm_id,
                    ProductValuation.is_deleted.is_(False),
                )
            )
        }
        held: dict[UUID, dict[UUID | None, Decimal]] = defaultdict(dict)
        for product_id, batch_id, quantity in self._session.execute(
            select(
                InventoryTransaction.product_id,
                InventoryTransaction.batch_id,
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            InventoryTransaction.owned_quantity_delta,
                            InventoryTransaction.current_quantity_delta,
                        )
                    ),
                    0,
                ),
            )
            .where(
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
                InventoryTransaction.transaction_type.not_in(_NOT_OWNING),
            )
            .group_by(InventoryTransaction.product_id, InventoryTransaction.batch_id)
        ):
            amount = Decimal(str(quantity))
            if amount != ZERO:
                held[product_id][batch_id] = amount
        below_zero = set(
            self._session.scalars(
                select(InventoryRecord.product_id).where(
                    InventoryRecord.firm_id == firm_id,
                    InventoryRecord.is_deleted.is_(False),
                    InventoryRecord.current_quantity < 0,
                )
            )
        )
        held_up = set(
            self._session.scalars(
                select(InventoryRecord.product_id).where(
                    InventoryRecord.firm_id == firm_id,
                    InventoryRecord.is_deleted.is_(False),
                    InventoryRecord.batch_id.is_(None),
                    (InventoryRecord.reserved_quantity > 0)
                    | (InventoryRecord.in_transit_quantity > 0),
                )
            )
        )

        items: list[_ItemPlan] = []
        negative: list[UUID] = []
        disagreeing: list[UUID] = []
        stocked = set(held) | {
            product_id
            for product_id, valuation in valuations.items()
            if Decimal(str(valuation.quantity_on_hand)) != ZERO
        }
        for product_id in stocked:
            lots = held.get(product_id, {})
            valuation = valuations.get(product_id)
            quantity = (
                ZERO if valuation is None else Decimal(str(valuation.quantity_on_hand))
            )
            if (
                product_id in below_zero
                or quantity < ZERO
                or any(amount < ZERO for amount in lots.values())
            ):
                negative.append(product_id)
                continue
            if valuation is None or sum(lots.values(), ZERO) != quantity:
                disagreeing.append(product_id)
                continue
            if quantity == ZERO:
                continue
            items.append(
                _ItemPlan(
                    product_id=product_id,
                    quantity=quantity,
                    value=Decimal(str(valuation.total_value)),
                    # As stored: the unit cost column holds six places.
                    average=Decimal(str(valuation.average_cost)).quantize(
                        UNIT_COST_SCALE, rounding=ROUND_HALF_UP
                    ),
                    lots=dict(lots),
                )
            )
        waiting = sorted(
            product_id
            for product_id in held_up
            if product_id in stocked and None in held.get(product_id, {})
        )
        names = self._names(set(negative) | set(disagreeing) | set(waiting))
        if negative:
            refusals.append(
                "A lot cannot hold below zero, and these items are below zero: "
                f"{self._listed(negative, names)}. Bring their stock to zero or "
                "above first."
            )
        if disagreeing:
            refusals.append(
                "The stock movements of these items do not add up to the "
                f"quantity they are valued at: {self._listed(disagreeing, names)}. "
                "Their lots could not carry their value exactly."
            )
        if waiting:
            refusals.append(
                "These items have stock with no batch that is reserved for an "
                "order or on its way between warehouses: "
                f"{self._listed(waiting, names)}. "
                "Dispatch or release the orders and receive the transfers first."
            )
        return _Plan(items=items, refusals=refusals)

    def _names(self, product_ids: set[UUID]) -> dict[UUID, str]:
        """Return each item's code and name, as a person knows it."""
        if not product_ids:
            return {}
        return {
            row.id: f"{row.code} {row.name}"
            for row in self._session.execute(
                select(Product.id, Product.code, Product.name).where(
                    Product.id.in_(product_ids)
                )
            )
        }

    @staticmethod
    def _listed(product_ids: list[UUID], names: dict[UUID, str]) -> str:
        """Return the items named in a sentence, in a stable order."""
        return ", ".join(sorted(names.get(pid, str(pid)) for pid in product_ids))

    @staticmethod
    def _already_by_lot(row: StockLotSettings) -> str:
        """Say the firm already costs by lot, and since when."""
        since = (
            f" since {row.switched_on.isoformat()}"
            if row.switched_on is not None
            else ""
        )
        return (
            f"The firm already costs its stock by lot{since}. The switch is one "
            "way and cannot be made again."
        )

    # ---- carrying --------------------------------------------------------

    def _carry(
        self,
        item: _ItemPlan,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source: LotSource,
    ) -> None:
        """Turn one item's stock into lots, each valued at its average.

        Every lot is valued at the item's average to the paisa; what rounding
        leaves over goes on the largest lot, so the lots add up to the item's
        value exactly. Every lot keeps the average as its unit cost: the issue
        that empties a lot takes all of its value, residual included.
        """
        lot_ids: dict[UUID | None, UUID] = {}
        for batch_id in item.lots:
            if batch_id is None:
                lot_ids[None] = self._new_lot(
                    item, firm_id=firm_id, actor_id=actor_id, source=source
                )
            else:
                lot_ids[batch_id] = self._existing_lot(
                    batch_id, firm_id=firm_id, actor_id=actor_id, source=source
                )
        values = {
            key: quantize_money(quantity * item.average)
            for key, quantity in item.lots.items()
        }
        largest = max(
            item.lots,
            key=lambda key: (item.lots[key], str(lot_ids[key])),
        )
        values[largest] += quantize_money(item.value) - sum(values.values(), ZERO)
        for key, quantity in item.lots.items():
            lot_id = lot_ids[key]
            lot = self._session.scalar(
                select(BatchValuation).where(
                    BatchValuation.batch_id == lot_id,
                    BatchValuation.is_deleted.is_(False),
                )
            )
            if lot is None:
                lot = BatchValuation(
                    firm_id=firm_id,
                    batch_id=lot_id,
                    product_id=item.product_id,
                    created_by=actor_id,
                )
                self._session.add(lot)
            lot.quantity_on_hand = quantity
            lot.unit_cost = item.average
            lot.total_value = values[key]
            lot.updated_by = actor_id

    def _new_lot(
        self,
        item: _ItemPlan,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source: LotSource,
    ) -> UUID:
        """Open one lot for an item's stock that names no batch, and name it.

        Our own reference, no printed batch. Every stock row of the item that
        named no batch now names the lot, in whichever warehouse it is.
        """
        from app.batch_serial.services import BatchSerialService

        lot = BatchSerialService(self._session).open_lot(
            firm_scope=firm_id,
            actor_id=actor_id,
            product_id=item.product_id,
            source=source,
        )
        for row in self._session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.product_id == item.product_id,
                InventoryRecord.batch_id.is_(None),
                InventoryRecord.is_deleted.is_(False),
            )
        ):
            row.batch_id = lot.id
            row.updated_by = actor_id
        return lot.id

    def _existing_lot(
        self,
        batch_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source: LotSource,
    ) -> UUID:
        """Make a batch that holds stock a lot of its own, carried forward."""
        batch = self._session.get(BatchRecord, batch_id)
        if batch is None or batch.firm_id != firm_id:
            raise ValidationError(f"Batch {batch_id} holds stock but was not found.")
        before: dict[str, object] = {
            "source_document_type": batch.source_document_type,
            "received_on": (
                batch.received_on.isoformat() if batch.received_on else None
            ),
        }
        batch.source_document_type = source.document_type
        batch.source_document_id = source.document_id
        batch.source_document_line_id = source.line_id
        batch.source_document_number = source.document_number
        if batch.received_on is None:
            batch.received_on = source.received_on
        batch.updated_by = actor_id
        record_audit(
            self._session,
            action="batch.carried_forward",
            entity_type="batch",
            entity_id=batch.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "source_document_type": batch.source_document_type,
                "received_on": batch.received_on.isoformat(),
            },
        )
        return batch.id

    def _assert_carried_exactly(self, firm_id: UUID, items: list[_ItemPlan]) -> None:
        """Refuse the switch if any item's lots differ from what it held.

        Section 4.4, rule 3: compared item by item, value to the paisa and
        quantity exactly, against the item's running valuation.

        Raises:
            BusinessRuleError: Naming the first item that differs.

        """
        sums = {
            product_id: (Decimal(str(quantity)), Decimal(str(value)))
            for product_id, quantity, value in self._session.execute(
                select(
                    BatchValuation.product_id,
                    func.sum(BatchValuation.quantity_on_hand),
                    func.sum(BatchValuation.total_value),
                )
                .where(
                    BatchValuation.firm_id == firm_id,
                    BatchValuation.is_deleted.is_(False),
                )
                .group_by(BatchValuation.product_id)
            )
        }
        for item in items:
            quantity, value = sums.get(item.product_id, (ZERO, ZERO))
            valuation = self._session.scalar(
                select(ProductValuation).where(
                    ProductValuation.firm_id == firm_id,
                    ProductValuation.product_id == item.product_id,
                    ProductValuation.is_deleted.is_(False),
                )
            )
            held = (
                (ZERO, ZERO)
                if valuation is None
                else (
                    Decimal(str(valuation.quantity_on_hand)),
                    quantize_money(Decimal(str(valuation.total_value))),
                )
            )
            if (
                quantity != item.quantity
                or quantize_money(value) != quantize_money(item.value)
                or held != (item.quantity, quantize_money(item.value))
            ):
                name = self._names({item.product_id}).get(
                    item.product_id, str(item.product_id)
                )
                raise BusinessRuleError(
                    f"The switch was undone: the lots of {name} would hold "
                    f"{quantity} worth {quantize_money(value)}, but it held "
                    f"{item.quantity} worth {quantize_money(item.value)}."
                )

    # ---- rows ------------------------------------------------------------

    def _row(self, firm_id: UUID) -> StockLotSettings | None:
        """Return the firm's live settings row, if any."""
        return self._session.scalar(
            select(StockLotSettings).where(
                StockLotSettings.firm_id == firm_id,
                StockLotSettings.is_deleted.is_(False),
            )
        )

    def _locked_row(self, firm_id: UUID, actor_id: UUID) -> StockLotSettings:
        """Return the firm's settings row under lock, making it if missing.

        Two switches at once: the second waits on the lock and then finds the
        firm already by lot. Where neither had a row, the one-live-row index
        refuses the second insert.
        """
        row = self._session.scalar(
            select(StockLotSettings)
            .where(
                StockLotSettings.firm_id == firm_id,
                StockLotSettings.is_deleted.is_(False),
            )
            .with_for_update()
        )
        if row is None:
            row = StockLotSettings(
                firm_id=firm_id,
                costing_method=FIRM_AVERAGE,
                allow_billing_without_stock=False,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
            self._session.flush()
        return row

    @staticmethod
    def _view(row: StockLotSettings) -> LotSettingsView:
        """Return the settings row as the screen reads it."""
        return LotSettingsView(
            costing_method=row.costing_method,
            switched_on=row.switched_on,
            allow_billing_without_stock=row.allow_billing_without_stock,
            version=row.version,
        )

    @staticmethod
    def _snapshot(row: StockLotSettings) -> dict[str, object]:
        """Return the audited fields of the settings row."""
        return {
            "costing_method": row.costing_method,
            "switched_on": (
                row.switched_on.isoformat() if row.switched_on is not None else None
            ),
            "allow_billing_without_stock": row.allow_billing_without_stock,
        }
