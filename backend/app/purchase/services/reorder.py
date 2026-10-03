"""Below reorder level, and the draft purchase orders that put it right (42.9).

``inventory_records`` carries ``reorder_level`` and ``maximum_level`` per stock
row, and the stock list could already filter to low stock -- but nothing said
what to order, from whom, or raised the order. This does both.

**One row per warehouse and product.** A product's stock in a warehouse may sit
on several rows (storage nodes, batches); their available quantities are added
and the highest level set on any of them is the level. ``minimum_level`` stands
in where no reorder level is set, as the stock list's low-stock filter already
does.

**What is already coming counts.** Quantity on open purchase orders for that
warehouse -- drafts included, so raising drafts twice does not order twice --
less what their receipts have taken in, is subtracted from the suggestion.

**The suggestion** is the maximum level less available less on order; with no
maximum level set, the shortfall to the reorder level. Never negative: a row
whose need is already on order is listed with zero, so the buyer can see why
nothing is suggested.

**Or from what sold** (backlog 69 row 12, A39). A firm planning on SALES
gets a derived level for every product with none typed: net sales over the
window as a daily rate, a reorder point of that times lead plus safety days and
a target of the point plus the cover days -- see ``ReorderPlanningSettings``.
A typed level always wins, and a derived suggestion rounds up to whole units.

**The supplier** is the product's preferred supplier (decision A18) where one
is set and still live and active, else the one last billed for the product.
The rate is the last bill's rate when that bill was the same supplier's and in
the stock unit, else the product's purchase price.

Raising orders stages one DRAFT per supplier per warehouse through
``PurchaseService.stage_order`` -- numbering, tax, audit and history exactly as
a typed order -- and commits once: a row that cannot be ordered refuses the
whole batch by name, as an import does.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.inventory.schemas import REVERSAL_SUFFIX
from app.inventory.services.pipeline import incoming
from app.products.models import Product
from app.purchase.models import (
    PurchaseOrder,
    ReorderPlanningSettings,
)
from app.purchase.schemas import (
    PurchaseLineWrite,
    PurchaseOrderCreate,
    PurchaseOrderStatus,
)
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.vendors.models import Vendor
from app.vendors.models.supplier_product import SupplierProduct
from app.vendors.services.order_quantities import rounded_quantity
from app.vendors.services.supplier_catalogue import current_rows

ZERO = Decimal("0")
QUANTUM = Decimal("0.0001")

#: Orders whose goods may still come: everything short of received, cancelled
#: or closed. Drafts count, so a second run does not order the same goods.
OPEN_ORDER_STATUSES = (
    PurchaseOrderStatus.DRAFT.value,
    PurchaseOrderStatus.SUBMITTED.value,
    PurchaseOrderStatus.APPROVED.value,
    PurchaseOrderStatus.PARTIALLY_ORDERED.value,
    PurchaseOrderStatus.ORDERED.value,
    PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
)
RECEIVED_STATUSES = ("COMPLETED", "CLOSED")
BILLED_STATUSES = ("APPROVED", "CLOSED")


@dataclass(frozen=True)
class ReorderRow:
    """One product in one warehouse at or below its reorder level."""

    branch_id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_code: str
    product_name: str
    available_quantity: Decimal
    reorder_level: Decimal
    maximum_level: Decimal | None
    on_order_quantity: Decimal
    suggested_quantity: Decimal
    supplier_id: UUID | None
    supplier_name: str | None
    unit_price: Decimal
    #: ``LEVEL`` when typed on the stock row, ``SALES`` when derived from what
    #: sold (backlog 69 row 12); then ``reorder_level`` and ``maximum_level``
    #: are the derived reorder point and order-up-to level.
    basis: str = "LEVEL"
    average_daily_sales: Decimal | None = None


@dataclass(frozen=True)
class PlanningSettings:
    """A firm's reorder planning, with the defaults where it set none."""

    basis: str = "LEVELS"
    sales_window_days: int = 90
    lead_time_days: int = 7
    safety_days: int = 7
    cover_days: int = 30
    is_configured: bool = False


#: The movements that are a sale or its undoing: stock out to customers, back
#: from them, and the reversal of either. Their deltas, summed and negated,
#: are what the customers kept.
SALES_MOVEMENTS = (
    "DISPATCH",
    "DISPATCH" + REVERSAL_SUFFIX,
    "SALES_RETURN",
    "SALES_RETURN" + REVERSAL_SUFFIX,
)


@dataclass(frozen=True)
class _Level:
    """One warehouse and product due for reorder, and the level that says so."""

    warehouse_id: UUID
    product_id: UUID
    branch_id: UUID
    held: Decimal
    reorder: Decimal
    maximum: Decimal | None
    basis: str = "LEVEL"
    daily: Decimal | None = None


def _planning_snapshot(values: PlanningSettings) -> dict[str, object]:
    """Return the planning figures as the audit trail keeps them."""
    return {
        "basis": values.basis,
        "sales_window_days": values.sales_window_days,
        "lead_time_days": values.lead_time_days,
        "safety_days": values.safety_days,
        "cover_days": values.cover_days,
    }


@dataclass(frozen=True)
class ReorderPick:
    """One row a buyer chose to order, optionally with their own quantity."""

    warehouse_id: UUID
    product_id: UUID
    quantity: Decimal | None = None
    supplier_id: UUID | None = None


class ReorderService:
    """Find stock below its reorder level and raise draft orders for it."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def below_reorder(
        self, firm_id: UUID, *, warehouse_id: UUID | None = None
    ) -> list[ReorderRow]:
        """Return every warehouse and product at or below its reorder level."""
        planning = self.planning(firm_id)
        by_sales = planning.basis == "SALES"
        level = func.max(
            func.coalesce(InventoryRecord.reorder_level, InventoryRecord.minimum_level)
        )
        available = func.coalesce(func.sum(InventoryRecord.available_quantity), 0)
        statement = (
            select(
                InventoryRecord.warehouse_id,
                InventoryRecord.product_id,
                # As text: PostgreSQL has no max(uuid), and SQLite -- the
                # unit suite -- does not mind, so only a running server saw
                # the report fail (found by the quick check, 2026-10-02).
                func.max(cast(InventoryRecord.branch_id, String(36))),
                available,
                level,
                func.max(InventoryRecord.maximum_level),
            )
            .where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(InventoryRecord.warehouse_id, InventoryRecord.product_id)
        )
        if not by_sales:
            # Only typed levels count, so let the database drop the rest.
            statement = statement.having(level.is_not(None), available <= level)
        if warehouse_id is not None:
            statement = statement.where(InventoryRecord.warehouse_id == warehouse_id)
        demand = (
            self._sales_by_location(firm_id, planning, warehouse_id) if by_sales else {}
        )
        # The supplier's own lead time, where its catalogue quotes one, sets
        # the reorder point rather than the firm-wide figure (BUY-6).
        lead_for = self._supplier_lead_times(firm_id, {p for _, p in demand})
        stock: list[_Level] = []
        for found in self._session.execute(statement).all():
            warehouse, product_id, branch_text, held_raw, typed, maximum = found
            branch = UUID(str(branch_text))
            held = Decimal(str(held_raw))
            if typed is not None:
                if held <= Decimal(str(typed)):
                    stock.append(
                        _Level(
                            warehouse,
                            product_id,
                            branch,
                            held,
                            Decimal(str(typed)),
                            None if maximum is None else Decimal(str(maximum)),
                        )
                    )
                continue
            sold = demand.get((warehouse, product_id))
            if sold is None:
                continue
            daily = sold / planning.sales_window_days
            lead = lead_for.get(product_id, planning.lead_time_days)
            point = daily * (lead + planning.safety_days)
            if held > point:
                continue
            stock.append(
                _Level(
                    warehouse,
                    product_id,
                    branch,
                    held,
                    point.quantize(QUANTUM),
                    (point + daily * planning.cover_days).quantize(QUANTUM),
                    basis="SALES",
                    daily=daily.quantize(QUANTUM),
                )
            )
        if not stock:
            return []
        product_ids = {row.product_id for row in stock}
        warehouse_ids = {row.warehouse_id for row in stock}
        on_order = self._on_order(firm_id, warehouse_ids, product_ids)
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            )
        }
        warehouses: dict[UUID, str] = {
            row_id: code
            for row_id, code in self._session.execute(
                select(Warehouse.id, Warehouse.code).where(
                    Warehouse.id.in_(warehouse_ids)
                )
            ).all()
        }
        suppliers = self._suppliers(firm_id, products)
        names: dict[UUID, str] = {
            row_id: name
            for row_id, name in self._session.execute(
                select(Vendor.id, Vendor.name).where(
                    Vendor.id.in_({v for v, _ in suppliers.values()})
                )
            ).all()
        }
        terms = self._supplier_terms(firm_id, suppliers)
        result: list[ReorderRow] = []
        for entry in stock:
            warehouse, product_id = entry.warehouse_id, entry.product_id
            product = products.get(product_id)
            # Only what a purchase order would take: a discontinued product
            # is sold out, not reordered (STK-17).
            if product is None or product.status != "ACTIVE":
                continue
            held, reorder, maximum = entry.held, entry.reorder, entry.maximum
            coming = on_order.get((warehouse, product_id), ZERO)
            target = maximum if maximum is not None else reorder
            gap = max(target - held - coming, ZERO)
            # A derived level orders whole units; a typed one orders exactly
            # the gap, as it always has.
            suggested = (
                gap.to_integral_value(rounding=ROUND_CEILING)
                if entry.basis == "SALES"
                else gap
            ).quantize(QUANTUM)
            branch = entry.branch_id
            supplier, rate = suppliers.get(product_id, (None, None))
            # The supplier's minimum and multiple round it up (BUY-5).
            listed = terms.get(product_id)
            if listed is not None and suggested > ZERO:
                suggested = rounded_quantity(
                    suggested,
                    minimum=listed.minimum_order_quantity,
                    multiple=listed.order_multiple,
                ).quantize(QUANTUM)
            result.append(
                ReorderRow(
                    branch_id=branch,
                    warehouse_id=warehouse,
                    warehouse_code=str(warehouses.get(warehouse, "")),
                    product_id=product_id,
                    product_code=product.code,
                    product_name=product.name,
                    available_quantity=held.quantize(QUANTUM),
                    reorder_level=reorder,
                    maximum_level=maximum,
                    on_order_quantity=coming.quantize(QUANTUM),
                    suggested_quantity=suggested,
                    supplier_id=supplier,
                    supplier_name=None if supplier is None else names.get(supplier),
                    unit_price=(
                        rate
                        if rate is not None
                        else Decimal(str(product.purchase_price or 0))
                    ),
                    basis=entry.basis,
                    average_daily_sales=entry.daily,
                )
            )
        result.sort(key=lambda row: (row.warehouse_code, row.product_code))
        return result

    def planning(self, firm_id: UUID) -> PlanningSettings:
        """Return the firm's reorder planning, or the defaults (LEVELS)."""
        row = self._planning_row(firm_id)
        if row is None:
            return PlanningSettings()
        return PlanningSettings(
            basis=row.basis,
            sales_window_days=row.sales_window_days,
            lead_time_days=row.lead_time_days,
            safety_days=row.safety_days,
            cover_days=row.cover_days,
            is_configured=True,
        )

    def save_planning(
        self, firm_id: UUID, values: PlanningSettings, *, actor_id: UUID
    ) -> PlanningSettings:
        """Replace the firm's reorder planning and keep the change in the trail.

        Raises:
            ValidationError: When the basis is not LEVELS or SALES, or a number
                of days is out of range.

        """
        if values.basis not in ("LEVELS", "SALES"):
            raise ValidationError("Reorder on LEVELS or on SALES.")
        if not 7 <= values.sales_window_days <= 365:
            raise ValidationError("Read sales over 7 to 365 days.")
        for label, days in (
            ("Lead time", values.lead_time_days),
            ("Safety stock", values.safety_days),
        ):
            if not 0 <= days <= 365:
                raise ValidationError(f"{label} is 0 to 365 days.")
        if not 1 <= values.cover_days <= 365:
            raise ValidationError("Order enough for 1 to 365 days.")
        before = self.planning(firm_id)
        row = self._planning_row(firm_id)
        if row is None:
            row = ReorderPlanningSettings(
                firm_id=firm_id, created_by=actor_id, updated_by=actor_id
            )
            self._session.add(row)
        row.basis = values.basis
        row.sales_window_days = values.sales_window_days
        row.lead_time_days = values.lead_time_days
        row.safety_days = values.safety_days
        row.cover_days = values.cover_days
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="purchase.reorder_planning_updated",
            entity_type="reorder_planning_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=_planning_snapshot(before),
            after_data=_planning_snapshot(values),
        )
        self._session.commit()
        return self.planning(firm_id)

    def _planning_row(self, firm_id: UUID) -> ReorderPlanningSettings | None:
        """Return the firm's live planning row, if it has one."""
        return self._session.scalar(
            select(ReorderPlanningSettings).where(
                ReorderPlanningSettings.firm_id == firm_id,
                ReorderPlanningSettings.is_deleted.is_(False),
            )
        )

    def _sales_by_location(
        self,
        firm_id: UUID,
        planning: PlanningSettings,
        warehouse_id: UUID | None,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return what customers kept per warehouse and product over the window.

        Dispatches less returns, each net of its reversals, in stock units,
        dated within the last ``sales_window_days`` up to today. Only what
        actually went out counts: an order nobody shipped is not demand yet.
        """
        today = utc_now().date()
        since = today - timedelta(days=planning.sales_window_days)
        kept = -func.sum(InventoryTransaction.current_quantity_delta)
        statement = (
            select(
                InventoryTransaction.warehouse_id,
                InventoryTransaction.product_id,
                kept,
            )
            .where(
                InventoryTransaction.firm_id == firm_id,
                InventoryTransaction.is_deleted.is_(False),
                InventoryTransaction.transaction_type.in_(SALES_MOVEMENTS),
                InventoryTransaction.transaction_date > since,
                InventoryTransaction.transaction_date <= today,
            )
            .group_by(
                InventoryTransaction.warehouse_id, InventoryTransaction.product_id
            )
            .having(kept > 0)
        )
        if warehouse_id is not None:
            statement = statement.where(
                InventoryTransaction.warehouse_id == warehouse_id
            )
        return {
            (warehouse, product): Decimal(str(quantity))
            for warehouse, product, quantity in self._session.execute(statement).all()
        }

    def raise_drafts(
        self, firm_id: UUID, picks: list[ReorderPick], *, actor_id: UUID
    ) -> list[PurchaseOrder]:
        """Raise one DRAFT order per supplier per warehouse for ``picks``.

        Staged through the order's own save path and committed once. A pick
        that is not below its reorder level, names no supplier the firm has
        billed, or comes to nothing, refuses the batch by name.
        """
        from app.purchase.services import PurchaseService

        if not picks:
            raise ValidationError("Choose at least one row to order.")
        rows = {
            (row.warehouse_id, row.product_id): row
            for row in self.below_reorder(firm_id)
        }
        grouped: dict[tuple[UUID, UUID, UUID], list[tuple[ReorderRow, Decimal]]]
        grouped = defaultdict(list)
        problems: list[str] = []
        for pick in picks:
            row = rows.get((pick.warehouse_id, pick.product_id))
            if row is None:
                problems.append(
                    f"{pick.product_id} is no longer below its reorder level in "
                    "that warehouse."
                )
                continue
            supplier = pick.supplier_id or row.supplier_id
            quantity = (
                pick.quantity if pick.quantity is not None else row.suggested_quantity
            )
            if supplier is None:
                problems.append(
                    f"{row.product_code} in {row.warehouse_code}: no supplier has "
                    "billed it yet, so choose one."
                )
                continue
            if quantity <= ZERO:
                problems.append(
                    f"{row.product_code} in {row.warehouse_code}: nothing to "
                    "order -- what is needed is already on order."
                )
                continue
            grouped[(supplier, row.branch_id, row.warehouse_id)].append((row, quantity))
        if problems:
            raise ValidationError("No order was raised. " + " ".join(problems))
        service = PurchaseService(self._session)
        today = utc_now().date()
        orders: list[PurchaseOrder] = []
        for (supplier, branch, warehouse), lines in grouped.items():
            orders.append(
                service.stage_order(
                    PurchaseOrderCreate(
                        branch_id=branch,
                        warehouse_id=warehouse,
                        vendor_id=supplier,
                        purchase_date=today,
                        remarks="Raised from Below reorder level.",
                        lines=[
                            PurchaseLineWrite(
                                product_id=row.product_id,
                                ordered_quantity=quantity,
                                unit_price=row.unit_price,
                            )
                            for row, quantity in lines
                        ],
                    ),
                    firm_id=firm_id,
                    actor_id=actor_id,
                )
            )
        self._session.commit()
        return orders

    def _on_order(
        self, firm_id: UUID, warehouse_ids: set[UUID], product_ids: set[UUID]
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return what open orders still bring, per warehouse and product.

        In stock units, through the derivation the stock screen's *incoming*
        reads (STK-10) -- with drafts counted here, so a second run does not
        order the same goods.
        """
        return {
            key: quantity
            for key, quantity in incoming(
                self._session,
                firm_id=firm_id,
                product_ids=product_ids,
                open_statuses=OPEN_ORDER_STATUSES,
            ).items()
            if key[0] in warehouse_ids
        }

    def _supplier_lead_times(
        self, firm_id: UUID, product_ids: set[UUID]
    ) -> dict[UUID, int]:
        """Return, per product, the lead time its chosen supplier quotes."""
        if not product_ids:
            return {}
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            )
        }
        terms = self._supplier_terms(firm_id, self._suppliers(firm_id, products))
        return {
            product_id: row.lead_time_days
            for product_id, row in terms.items()
            if row.lead_time_days is not None
        }

    def _supplier_terms(
        self, firm_id: UUID, suppliers: dict[UUID, tuple[UUID, Decimal | None]]
    ) -> dict[UUID, SupplierProduct]:
        """Return each product's catalogue row with its chosen supplier.

        One read per supplier, not per product (BUY-5).
        """
        by_supplier: dict[UUID, list[UUID]] = {}
        for product_id, (supplier, _) in suppliers.items():
            by_supplier.setdefault(supplier, []).append(product_id)
        today = utc_now().date()
        found: dict[UUID, SupplierProduct] = {}
        for supplier, product_ids in by_supplier.items():
            found.update(
                current_rows(
                    self._session,
                    firm_id=firm_id,
                    vendor_id=supplier,
                    product_ids=product_ids,
                    on=today,
                )
            )
        return found

    def _suppliers(
        self, firm_id: UUID, products: dict[UUID, Product]
    ) -> dict[UUID, tuple[UUID, Decimal | None]]:
        """Return, per product, the supplier to order from and a rate, if any.

        The preferred supplier wins where it is live and active (A18); the
        last bill's rate goes with it only when that bill was the same
        supplier's. Otherwise the supplier last billed, as before.
        """
        last = self._last_supplier(firm_id, products)
        wanted = {
            product.preferred_vendor_id
            for product in products.values()
            if product.preferred_vendor_id is not None
        }
        usable = (
            set(
                self._session.scalars(
                    select(Vendor.id).where(
                        Vendor.id.in_(wanted),
                        Vendor.firm_id == firm_id,
                        Vendor.is_deleted.is_(False),
                        Vendor.status == "ACTIVE",
                    )
                )
            )
            if wanted
            else set()
        )
        chosen: dict[UUID, tuple[UUID, Decimal | None]] = {}
        for product_id, product in products.items():
            preferred = product.preferred_vendor_id
            billed = last.get(product_id)
            if preferred is not None and preferred in usable:
                rate = billed[1] if billed and billed[0] == preferred else None
                chosen[product_id] = (preferred, rate)
            elif billed is not None:
                chosen[product_id] = billed
        return chosen

    def _last_supplier(
        self, firm_id: UUID, products: dict[UUID, Product]
    ) -> dict[UUID, tuple[UUID, Decimal | None]]:
        """Return, per product, the supplier last billed and that bill's rate.

        The rate is kept only where the bill was entered in the product's
        stock unit; a rate per carton is not a rate per piece.
        """
        if not products:
            return {}
        ranked = (
            select(
                PurchaseInvoiceLine.product_id,
                PurchaseInvoice.vendor_id,
                PurchaseInvoiceLine.unit_price,
                PurchaseInvoiceLine.purchase_uom_id,
                func.row_number()
                .over(
                    partition_by=PurchaseInvoiceLine.product_id,
                    order_by=(
                        PurchaseInvoice.invoice_date.desc(),
                        PurchaseInvoice.created_at.desc(),
                        PurchaseInvoiceLine.line_number.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(BILLED_STATUSES),
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.product_id.in_(set(products)),
            )
            .subquery()
        )
        found: dict[UUID, tuple[UUID, Decimal | None]] = {}
        for product_id, vendor_id, price, unit in self._session.execute(
            select(
                ranked.c.product_id,
                ranked.c.vendor_id,
                ranked.c.unit_price,
                ranked.c.purchase_uom_id,
            ).where(ranked.c.rank == 1)
        ).all():
            product = products[product_id]
            stock_units = {None, product.inventory_uom_id, product.base_uom_id}
            found[product_id] = (
                vendor_id,
                Decimal(str(price)) if unit in stock_units else None,
            )
        return found
