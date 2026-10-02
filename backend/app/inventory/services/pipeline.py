"""What is coming in and going out, beside what is on the shelf (STK-10).

*Incoming* is what open purchase orders still bring: each line's ordered
quantity less what its completed receipts took in. *Outgoing* is what open
sales orders have promised and not yet set aside: each line's quantity less
what has left the warehouse against it and less what is still reserved for it
-- the reserved part already sits outside *available*, so counting it again
would promise the same goods twice. Both are in stock units, keyed by
warehouse and product, and both are derived on every read: nothing here is
stored.

*Projected* is available + incoming - outgoing: what will be free once the
open orders on both sides have run their course, as ERPNext's projected
quantity and Tally's "available after orders" read.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ZERO = Decimal("0")

#: A purchase order approved and still expecting goods. A draft or one
#: awaiting approval is not yet a commitment to the supplier, so it is not
#: counted coming in -- reorder planning counts those itself, so as not to
#: order the same goods twice.
OPEN_PURCHASE_ORDER_STATUSES = (
    "APPROVED",
    "PARTIALLY_ORDERED",
    "ORDERED",
    "PARTIALLY_RECEIVED",
)
#: A receipt whose goods were taken into stock.
RECEIVED_STATUSES = ("COMPLETED", "CLOSED")
#: A sales order still owing goods.
OPEN_SALES_ORDER_STATUSES = ("APPROVED", "PARTIALLY_DELIVERED")

Keyed = dict[tuple[UUID, UUID], Decimal]


def incoming(
    session: Session,
    *,
    firm_id: UUID,
    product_ids: Collection[UUID] | None = None,
    open_statuses: Collection[str] = OPEN_PURCHASE_ORDER_STATUSES,
) -> Keyed:
    """Return what open purchase orders still bring, per warehouse and product.

    One grouped read for the lines and one for the receipts. ``product_ids``
    None asks for the whole firm.
    """
    # Imported here: the purchase modules import inventory.
    from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
    from app.purchase.models import PurchaseOrder, PurchaseOrderLine

    if product_ids is not None and not product_ids:
        return {}
    line_warehouse = func.coalesce(
        PurchaseOrderLine.warehouse_id, PurchaseOrder.warehouse_id
    )
    query = (
        select(
            PurchaseOrderLine.id,
            line_warehouse,
            PurchaseOrderLine.product_id,
            PurchaseOrderLine.ordered_quantity,
            PurchaseOrderLine.conversion_factor,
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(
            PurchaseOrder.firm_id == firm_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status.in_(tuple(open_statuses)),
            PurchaseOrderLine.is_deleted.is_(False),
        )
    )
    if product_ids is not None:
        query = query.where(PurchaseOrderLine.product_id.in_(list(product_ids)))
    lines = session.execute(query).all()
    if not lines:
        return {}
    received_query = (
        select(
            GoodsReceiptLine.purchase_order_line_id,
            func.coalesce(func.sum(GoodsReceiptLine.current_receipt_quantity), 0),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(
            PurchaseOrderLine,
            PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id,
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.status.in_(RECEIVED_STATUSES),
            GoodsReceipt.is_deleted.is_(False),
            GoodsReceiptLine.is_deleted.is_(False),
            PurchaseOrder.status.in_(tuple(open_statuses)),
        )
        .group_by(GoodsReceiptLine.purchase_order_line_id)
    )
    if product_ids is not None:
        received_query = received_query.where(
            PurchaseOrderLine.product_id.in_(list(product_ids))
        )
    received: dict[UUID, Decimal] = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(received_query).all()
    }
    result: Keyed = defaultdict(lambda: ZERO)
    for line_id, warehouse, product_id, ordered, factor in lines:
        outstanding = Decimal(str(ordered)) - received.get(line_id, ZERO)
        if outstanding > ZERO:
            result[(warehouse, product_id)] += outstanding * Decimal(str(factor or 1))
    return dict(result)


def outgoing(
    session: Session,
    *,
    firm_id: UUID,
    product_ids: Collection[UUID] | None = None,
) -> Keyed:
    """Return what open sales orders promise and have not set aside.

    Per line: the quantity in stock units, less what has left the warehouse
    against it, less what is still reserved for it. One grouped read for the
    lines and one for the notes. ``product_ids`` None asks for the whole firm.
    """
    # Imported here: the sales modules import inventory.
    from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
    from app.delivery_note.rules import goods_have_left_clause
    from app.sales_order.models import SalesOrder, SalesOrderLine

    if product_ids is not None and not product_ids:
        return {}
    query = (
        select(
            SalesOrderLine.id,
            func.coalesce(SalesOrderLine.warehouse_id, SalesOrder.warehouse_id),
            SalesOrderLine.product_id,
            SalesOrderLine.reservable_quantity,
            SalesOrderLine.reserved_quantity,
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(
            SalesOrder.firm_id == firm_id,
            SalesOrder.is_deleted.is_(False),
            SalesOrder.status.in_(OPEN_SALES_ORDER_STATUSES),
            SalesOrderLine.is_deleted.is_(False),
        )
    )
    if product_ids is not None:
        query = query.where(SalesOrderLine.product_id.in_(list(product_ids)))
    lines = session.execute(query).all()
    if not lines:
        return {}
    delivered_query = (
        select(
            DeliveryNoteLine.sales_order_line_id,
            func.coalesce(func.sum(DeliveryNoteLine.delivered_quantity), 0),
        )
        .join(DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id)
        .join(SalesOrder, SalesOrder.id == DeliveryNote.sales_order_id)
        .where(
            DeliveryNoteLine.firm_id == firm_id,
            DeliveryNoteLine.is_deleted.is_(False),
            DeliveryNote.is_deleted.is_(False),
            SalesOrder.status.in_(OPEN_SALES_ORDER_STATUSES),
            goods_have_left_clause(),
        )
        .group_by(DeliveryNoteLine.sales_order_line_id)
    )
    delivered: dict[UUID, Decimal] = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(delivered_query).all()
        if line_id is not None
    }
    result: Keyed = defaultdict(lambda: ZERO)
    for line_id, warehouse, product_id, promised, reserved in lines:
        owed = (
            Decimal(str(promised))
            - delivered.get(line_id, ZERO)
            - Decimal(str(reserved or 0))
        )
        if owed > ZERO and warehouse is not None:
            result[(warehouse, product_id)] += owed
    return dict(result)


def by_product(keyed: Keyed) -> dict[UUID, Decimal]:
    """Add a per-warehouse figure up to one per product."""
    totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for (_, product_id), quantity in keyed.items():
        totals[product_id] += quantity
    return dict(totals)


def by_warehouse(keyed: Keyed) -> dict[UUID, Decimal]:
    """Add a per-product figure up to one per warehouse."""
    totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for (warehouse_id, _), quantity in keyed.items():
        totals[warehouse_id] += quantity
    return dict(totals)
