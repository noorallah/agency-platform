"""The line companions every document's preview carries.

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
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.inventory.models import InventoryRecord
from app.sales.schemas.document_preview import DocumentPreviewLine

#: One line to describe: its number, its product and where it ships from.
PreviewLineKey = tuple[int, UUID, UUID | None]


#: What the party was last billed for one product: the rate, the bill's
#: number and date, and the line's discount rate.
LastBilled = tuple[Decimal, str, date, Decimal]


def _last_billed(
    session: Session,
    *,
    header: Any,  # noqa: ANN401 -- a sales or a purchase invoice model
    line: Any,  # noqa: ANN401 -- that invoice's line model
    link: Any,  # noqa: ANN401 -- the line's column naming its invoice
    party: Any,  # noqa: ANN401 -- the invoice's customer or vendor column
    party_id: UUID,
    firm_id: UUID,
    product_ids: set[UUID],
) -> dict[UUID, LastBilled]:
    """Return the newest approved bill line per product, in one statement.

    A window ranks each product's billed lines newest first -- by the bill's
    date, then when it was recorded, then the line's position -- and only
    the first is read, so the answer costs one row per product however many
    years of bills the party has (backlog 55 G6).
    """
    if not product_ids:
        return {}
    ranked = (
        select(
            line.product_id.label("product_id"),
            line.unit_price.label("unit_price"),
            header.invoice_number.label("invoice_number"),
            header.invoice_date.label("invoice_date"),
            line.discount_percent.label("discount_percent"),
            func.row_number()
            .over(
                partition_by=line.product_id,
                order_by=(
                    header.invoice_date.desc(),
                    header.created_at.desc(),
                    line.line_number.asc(),
                ),
            )
            .label("position"),
        )
        .join(header, header.id == link)
        .where(
            header.firm_id == firm_id,
            party == party_id,
            header.is_deleted.is_(False),
            line.is_deleted.is_(False),
            header.status.in_(["APPROVED", "CLOSED"]),
            line.product_id.in_(product_ids),
        )
        .subquery()
    )
    return {
        product_id: (price, number, on, rate)
        for product_id, price, number, on, rate in session.execute(
            select(
                ranked.c.product_id,
                ranked.c.unit_price,
                ranked.c.invoice_number,
                ranked.c.invoice_date,
                ranked.c.discount_percent,
            ).where(ranked.c.position == 1)
        ).all()
    }


def purchase_line_companions(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    lines: Iterable[PreviewLineKey],
) -> list[DocumentPreviewLine]:
    """Return each line's last price billed by this vendor and its free stock.

    The purchase twin of `line_companions`: the last supplier bill the vendor
    raised for the product, not the last sale.
    """
    from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine

    keys = list(lines)
    last = _last_billed(
        session,
        header=PurchaseInvoice,
        line=PurchaseInvoiceLine,
        link=PurchaseInvoiceLine.purchase_invoice_id,
        party=PurchaseInvoice.vendor_id,
        party_id=vendor_id,
        firm_id=firm_id,
        product_ids={product_id for _, product_id, _ in keys},
    )
    return _with_stock(session, firm_id=firm_id, keys=keys, last=last)


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
    last = _last_billed(
        session,
        header=SalesInvoice,
        line=SalesInvoiceLine,
        link=SalesInvoiceLine.sales_invoice_id,
        party=SalesInvoice.customer_id,
        party_id=customer_id,
        firm_id=firm_id,
        product_ids={product_id for _, product_id, _ in keys},
    )
    return _with_stock(session, firm_id=firm_id, keys=keys, last=last)


def _with_stock(
    session: Session,
    *,
    firm_id: UUID,
    keys: list[PreviewLineKey],
    last: dict[UUID, LastBilled],
) -> list[DocumentPreviewLine]:
    """Join each line's last price to the stock free where it ships from."""
    product_ids = {product_id for _, product_id, _ in keys}
    warehouse_ids = {warehouse for _, _, warehouse in keys if warehouse}
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
    # Imported here: the inventory services read the sales models.
    from app.inventory.services import pipeline

    coming = pipeline.incoming(session, firm_id=firm_id, product_ids=product_ids)
    going = pipeline.outgoing(session, firm_id=firm_id, product_ids=product_ids)
    coming_firm_wide = pipeline.by_product(coming)
    going_firm_wide = pipeline.by_product(going)
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
                last_discount_percent=previous[3] if previous else None,
                available_quantity=(
                    stock.get((product_id, warehouse_id), Decimal("0"))
                    if warehouse_id
                    else firm_wide.get(product_id, Decimal("0"))
                ),
                incoming_quantity=(
                    coming.get((warehouse_id, product_id), Decimal("0"))
                    if warehouse_id
                    else coming_firm_wide.get(product_id, Decimal("0"))
                ),
                outgoing_quantity=(
                    going.get((warehouse_id, product_id), Decimal("0"))
                    if warehouse_id
                    else going_firm_wide.get(product_id, Decimal("0"))
                ),
            )
        )
    return result
