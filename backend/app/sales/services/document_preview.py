"""The line companions every sales document's preview carries.

A quotation, an order and an invoice are each priced for their screen by
staging them through their own save path and rolling it back; what they
share is read here -- the last price this customer paid for each product,
and the stock free where each line ships from -- so the three screens say
the same thing about the same line.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.inventory.models import InventoryRecord
from app.sales.schemas.document_preview import DocumentPreviewLine

#: One line to describe: its number, its product and where it ships from.
PreviewLineKey = tuple[int, UUID, UUID | None]


def line_companions(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    lines: Iterable[PreviewLineKey],
) -> list[DocumentPreviewLine]:
    """Return each line's last price to this customer and its free stock.

    Grouped reads for the whole document, not one per line. A line that
    names no warehouse -- an invoice line billed from a note -- is given
    the firm's stock across every warehouse.
    """
    # Imported here: the sales invoice module reads the sales services.
    from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

    keys = list(lines)
    product_ids = {product_id for _, product_id, _ in keys}
    warehouse_ids = {warehouse for _, _, warehouse in keys if warehouse}
    last: dict[UUID, tuple[Decimal, str, date]] = {}
    if product_ids:
        billed = session.execute(
            select(
                SalesInvoiceLine.product_id,
                SalesInvoiceLine.unit_price,
                SalesInvoice.invoice_number,
                SalesInvoice.invoice_date,
            )
            .join(
                SalesInvoice,
                SalesInvoice.id == SalesInvoiceLine.sales_invoice_id,
            )
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.customer_id == customer_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoice.status.in_(["APPROVED", "CLOSED"]),
                SalesInvoiceLine.product_id.in_(product_ids),
            )
            .order_by(
                SalesInvoice.invoice_date.desc(),
                SalesInvoice.created_at.desc(),
            )
        ).all()
        for product_id, price, number, on in billed:
            last.setdefault(product_id, (price, number, on))
    stock: dict[tuple[UUID, UUID], Decimal] = {}
    if product_ids and warehouse_ids:
        for product_id, warehouse_id, available in session.execute(
            select(
                InventoryRecord.product_id,
                InventoryRecord.warehouse_id,
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
            )
            .where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.warehouse_id.in_(warehouse_ids),
                InventoryRecord.is_deleted.is_(False),
                InventoryRecord.product_id.in_(product_ids),
            )
            .group_by(InventoryRecord.product_id, InventoryRecord.warehouse_id)
        ).all():
            stock[(product_id, warehouse_id)] = Decimal(str(available))
    firm_wide: dict[UUID, Decimal] = {}
    if any(warehouse is None for _, _, warehouse in keys):
        for product_id, available in session.execute(
            select(
                InventoryRecord.product_id,
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
            )
            .where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.is_deleted.is_(False),
                InventoryRecord.product_id.in_(product_ids),
            )
            .group_by(InventoryRecord.product_id)
        ).all():
            firm_wide[product_id] = Decimal(str(available))
    result: list[DocumentPreviewLine] = []
    for line_number, product_id, warehouse_id in keys:
        previous = last.get(product_id)
        result.append(
            DocumentPreviewLine(
                line_number=line_number,
                product_id=product_id,
                last_price=previous[0] if previous else None,
                last_invoice_number=previous[1] if previous else None,
                last_invoice_date=previous[2] if previous else None,
                available_quantity=(
                    stock.get((product_id, warehouse_id), Decimal("0"))
                    if warehouse_id
                    else firm_wide.get(product_id, Decimal("0"))
                ),
            )
        )
    return result
