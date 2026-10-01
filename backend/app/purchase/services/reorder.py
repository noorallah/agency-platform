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

**The supplier** is the one last billed for the product (there is no
preferred-supplier field), and the rate that bill's rate when it was billed in
the stock unit, else the product's purchase price.

Raising orders stages one DRAFT per supplier per warehouse through
``PurchaseService.stage_order`` -- numbering, tax, audit and history exactly as
a typed order -- and commits once: a row that cannot be ordered refuses the
whole batch by name, as an import does.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import (
    PurchaseLineWrite,
    PurchaseOrderCreate,
    PurchaseOrderStatus,
)
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.vendors.models import Vendor

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
        level = func.max(
            func.coalesce(InventoryRecord.reorder_level, InventoryRecord.minimum_level)
        )
        available = func.coalesce(func.sum(InventoryRecord.available_quantity), 0)
        statement = (
            select(
                InventoryRecord.warehouse_id,
                InventoryRecord.product_id,
                func.max(InventoryRecord.branch_id),
                available,
                level,
                func.max(InventoryRecord.maximum_level),
            )
            .where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(InventoryRecord.warehouse_id, InventoryRecord.product_id)
            .having(level.is_not(None), available <= level)
        )
        if warehouse_id is not None:
            statement = statement.where(InventoryRecord.warehouse_id == warehouse_id)
        stock = self._session.execute(statement).all()
        if not stock:
            return []
        product_ids = {row[1] for row in stock}
        warehouse_ids = {row[0] for row in stock}
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
        suppliers = self._last_supplier(firm_id, products)
        names: dict[UUID, str] = {
            row_id: name
            for row_id, name in self._session.execute(
                select(Vendor.id, Vendor.name).where(
                    Vendor.id.in_({v for v, _ in suppliers.values()})
                )
            ).all()
        }
        result: list[ReorderRow] = []
        for warehouse, product_id, branch, held, reorder, maximum in stock:
            product = products.get(product_id)
            if product is None:
                continue
            held = Decimal(str(held))
            reorder = Decimal(str(reorder))
            maximum = None if maximum is None else Decimal(str(maximum))
            coming = on_order.get((warehouse, product_id), ZERO)
            target = maximum if maximum is not None else reorder
            suggested = max(target - held - coming, ZERO).quantize(QUANTUM)
            supplier, rate = suppliers.get(product_id, (None, None))
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
                )
            )
        result.sort(key=lambda row: (row.warehouse_code, row.product_code))
        return result

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

        In stock units: each line's ordered quantity less what its completed
        receipts took in, times its conversion factor. One grouped read for
        the lines and one for the receipts, never one per row.
        """
        line_warehouse = func.coalesce(
            PurchaseOrderLine.warehouse_id, PurchaseOrder.warehouse_id
        )
        lines = self._session.execute(
            select(
                PurchaseOrderLine.id,
                line_warehouse,
                PurchaseOrderLine.product_id,
                PurchaseOrderLine.ordered_quantity,
                PurchaseOrderLine.conversion_factor,
            )
            .join(
                PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
            )
            .where(
                PurchaseOrder.firm_id == firm_id,
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.status.in_(OPEN_ORDER_STATUSES),
                PurchaseOrderLine.is_deleted.is_(False),
                PurchaseOrderLine.product_id.in_(product_ids),
                or_(
                    PurchaseOrderLine.warehouse_id.in_(warehouse_ids),
                    PurchaseOrder.warehouse_id.in_(warehouse_ids),
                ),
            )
        ).all()
        if not lines:
            return {}
        received: dict[UUID, Decimal] = {
            line_id: Decimal(str(quantity))
            for line_id, quantity in self._session.execute(
                select(
                    GoodsReceiptLine.purchase_order_line_id,
                    func.coalesce(
                        func.sum(GoodsReceiptLine.current_receipt_quantity), 0
                    ),
                )
                .join(
                    GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id
                )
                .join(
                    PurchaseOrderLine,
                    PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id,
                )
                .join(
                    PurchaseOrder,
                    PurchaseOrder.id == PurchaseOrderLine.purchase_order_id,
                )
                .where(
                    GoodsReceipt.firm_id == firm_id,
                    GoodsReceipt.status.in_(RECEIVED_STATUSES),
                    GoodsReceipt.is_deleted.is_(False),
                    GoodsReceiptLine.is_deleted.is_(False),
                    PurchaseOrder.status.in_(OPEN_ORDER_STATUSES),
                    PurchaseOrderLine.product_id.in_(product_ids),
                )
                .group_by(GoodsReceiptLine.purchase_order_line_id)
            ).all()
        }
        result: dict[tuple[UUID, UUID], Decimal] = defaultdict(lambda: ZERO)
        for line_id, warehouse, product_id, ordered, factor in lines:
            outstanding = Decimal(str(ordered)) - received.get(line_id, ZERO)
            if outstanding > ZERO:
                result[(warehouse, product_id)] += outstanding * Decimal(
                    str(factor or 1)
                )
        return dict(result)

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
