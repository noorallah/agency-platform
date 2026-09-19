"""What is still in flight against a master record, and the stock it holds.

Every master delete guard used to answer its own narrow question -- a customer
looked at invoices, a vendor at bills, a warehouse at stock -- and a product or
a storage area asked nothing at all (D-MST-1, D-MST-4, D-MST-7, D-MST-8). The
documents they missed are the same documents each time, so the question is
asked here once: **which documents still have something to do** that names
this product, party or place?

"Open" means the document still has to move stock or be billed:

* a sales order that is DRAFT, APPROVED or PARTIALLY_DELIVERED;
* a delivery note not yet dispatched, or dispatched and **not yet billed**;
* a DRAFT sales invoice or sales return, or a return approved and not received;
* a purchase order anywhere before RECEIVED;
* a DRAFT goods receipt, or a completed one **not yet billed** -- the goods are
  in and goods-received-not-invoiced holds what the firm owes for them;
* a DRAFT purchase invoice or purchase return, or a return approved and not
  sent back.

CANCELLED and CLOSED are never open: closing a document is how somebody says
its business is finished, and it is the way out when one of these is stuck.
Quotations and proformas are deliberately not counted -- neither reserves
stock, posts to a ledger or commits either side.

Billing is judged in **rows, not quantity**, the way
``SalesInvoiceService._already_invoiced`` judges it: a line is billed once a
live invoice line names it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

#: How many document numbers a refusal spells out before it says "and N more".
_SHOWN = 5


@dataclass(frozen=True)
class OpenDocuments:
    """The open documents of one kind that name the record being asked about."""

    label: str
    plural: str
    numbers: tuple[str, ...]

    def describe(self) -> str:
        """Render as ``2 sales orders (SO-1, SO-2)``."""
        count = len(self.numbers)
        shown = ", ".join(self.numbers[:_SHOWN])
        more = count - _SHOWN
        tail = f" and {more} more" if more > 0 else ""
        noun = self.label if count == 1 else self.plural
        return f"{count} {noun} ({shown}{tail})"


@dataclass(frozen=True)
class StockHolding:
    """Stock one place holds of one product."""

    place: str
    on_hand: Decimal
    reserved: Decimal

    def describe(self) -> str:
        """Render as ``45 in MAIN (2 reserved)``."""
        reserved = f" ({_plain(self.reserved)} reserved)" if self.reserved != 0 else ""
        return f"{_plain(self.on_hand)} in {self.place}{reserved}"


def _plain(value: Decimal) -> str:
    """Render a quantity without trailing zeros or an exponent."""
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class _Kind:
    """One document type: its header, its lines, and when it is still open."""

    label: str
    plural: str
    header: Any
    line: Any
    line_header_column: str
    number_column: str
    open_statuses: tuple[str, ...]
    party_column: str | None
    #: Statuses that are open only while some line has not been billed, with
    #: the invoice header and line that would bill it.
    unbilled_statuses: tuple[str, ...] = ()
    billing_header: Any = None
    billing_line: Any = None
    billing_line_header_column: str = ""
    #: A header column that, when set, says the document was raised by its own
    #: bill and is therefore billed already.
    raised_by_bill_column: str | None = None
    #: A line column that must be positive for the line to be billable at all:
    #: a receipt line that accepted nothing will never be named by a bill.
    billable_quantity_column: str | None = None


def _kinds() -> tuple[_Kind, ...]:
    """Return the document kinds, importing their models on first use.

    Imported here rather than at module level: several of these modules import
    the master services that call this one.
    """
    from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
    from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
    from app.purchase.models import PurchaseOrder, PurchaseOrderLine
    from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
    from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
    from app.sales_order.models import SalesOrder, SalesOrderLine
    from app.sales_return.models import SalesReturn, SalesReturnLine

    return (
        _Kind(
            "sales order",
            "sales orders",
            SalesOrder,
            SalesOrderLine,
            "sales_order_id",
            "order_number",
            ("DRAFT", "APPROVED", "PARTIALLY_DELIVERED"),
            "customer_id",
        ),
        _Kind(
            "delivery note",
            "delivery notes",
            DeliveryNote,
            DeliveryNoteLine,
            "delivery_note_id",
            "delivery_note_number",
            ("DRAFT", "APPROVED"),
            "customer_id",
            unbilled_statuses=("DISPATCHED", "COMPLETED"),
            billing_header=SalesInvoice,
            billing_line=SalesInvoiceLine,
            billing_line_header_column="sales_invoice_id",
            raised_by_bill_column="raised_by_sales_invoice_id",
        ),
        _Kind(
            "draft sales invoice",
            "draft sales invoices",
            SalesInvoice,
            SalesInvoiceLine,
            "sales_invoice_id",
            "invoice_number",
            ("DRAFT",),
            "customer_id",
        ),
        _Kind(
            "sales return",
            "sales returns",
            SalesReturn,
            SalesReturnLine,
            "sales_return_id",
            "return_number",
            ("DRAFT", "APPROVED"),
            "customer_id",
        ),
        _Kind(
            "purchase order",
            "purchase orders",
            PurchaseOrder,
            PurchaseOrderLine,
            "purchase_order_id",
            "po_number",
            (
                "DRAFT",
                "SUBMITTED",
                "APPROVED",
                "PARTIALLY_ORDERED",
                "ORDERED",
                "PARTIALLY_RECEIVED",
            ),
            "vendor_id",
        ),
        _Kind(
            "goods receipt",
            "goods receipts",
            GoodsReceipt,
            GoodsReceiptLine,
            "goods_receipt_id",
            "grn_number",
            ("DRAFT",),
            "vendor_id",
            unbilled_statuses=("COMPLETED",),
            billing_header=PurchaseInvoice,
            billing_line=PurchaseInvoiceLine,
            billing_line_header_column="purchase_invoice_id",
            billable_quantity_column="accepted_quantity",
        ),
        _Kind(
            "draft purchase invoice",
            "draft purchase invoices",
            PurchaseInvoice,
            PurchaseInvoiceLine,
            "purchase_invoice_id",
            "invoice_number",
            ("DRAFT",),
            "vendor_id",
        ),
        _Kind(
            "purchase return",
            "purchase returns",
            PurchaseReturn,
            PurchaseReturnLine,
            "purchase_return_id",
            "return_number",
            ("DRAFT", "APPROVED"),
            "vendor_id",
        ),
    )


def _unbilled(kind: _Kind, firm_id: UUID) -> ColumnElement[bool]:
    """Match a line of ``kind`` that no live invoice line names."""
    bill = kind.billing_header
    bill_line = kind.billing_line
    billed = exists(
        select(bill_line.id)
        .join(bill, bill.id == getattr(bill_line, kind.billing_line_header_column))
        .where(
            bill.firm_id == firm_id,
            bill.is_deleted.is_(False),
            bill.status != "CANCELLED",
            bill_line.is_deleted.is_(False),
            bill_line.source_document_line_id == kind.line.id,
        )
    )
    clauses: list[ColumnElement[bool]] = [
        kind.header.status.in_(kind.unbilled_statuses),
        ~billed,
    ]
    if kind.raised_by_bill_column is not None:
        clauses.append(getattr(kind.header, kind.raised_by_bill_column).is_(None))
    if kind.billable_quantity_column is not None:
        clauses.append(getattr(kind.line, kind.billable_quantity_column) > 0)
    return and_(*clauses)


def find_open_documents(
    session: Session,
    firm_id: UUID,
    *,
    product_id: UUID | None = None,
    customer_id: UUID | None = None,
    vendor_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
) -> list[OpenDocuments]:
    """Return the open documents naming the given record, grouped by kind.

    Exactly the filters supplied are applied, and a kind that cannot name the
    record at all -- a purchase order has no customer -- is skipped rather
    than matched against nothing.
    """
    found: list[OpenDocuments] = []
    for kind in _kinds():
        header, line = kind.header, kind.line
        filters: list[ColumnElement[bool]] = []
        if customer_id is not None or vendor_id is not None:
            wanted = customer_id if kind.party_column == "customer_id" else vendor_id
            if wanted is None or kind.party_column is None:
                continue
            filters.append(getattr(header, kind.party_column) == wanted)
        if product_id is not None:
            filters.append(line.product_id == product_id)
        if branch_id is not None:
            filters.append(header.branch_id == branch_id)
        if warehouse_id is not None:
            places = [line.warehouse_id == warehouse_id]
            if hasattr(header, "warehouse_id"):
                places.append(header.warehouse_id == warehouse_id)
            filters.append(or_(*places))
        if storage_node_id is not None:
            filters.append(line.storage_node_id == storage_node_id)

        is_open: ColumnElement[bool] = header.status.in_(kind.open_statuses)
        if kind.unbilled_statuses:
            is_open = or_(is_open, _unbilled(kind, firm_id))
        number = getattr(header, kind.number_column)
        numbers = session.execute(
            select(number, func.min(header.created_at))
            .join(line, getattr(line, kind.line_header_column) == header.id)
            .where(
                header.firm_id == firm_id,
                header.is_deleted.is_(False),
                line.is_deleted.is_(False),
                is_open,
                *filters,
            )
            .group_by(number)
            .order_by(func.min(header.created_at).asc(), number.asc())
        ).all()
        if numbers:
            found.append(
                OpenDocuments(
                    label=kind.label,
                    plural=kind.plural,
                    numbers=tuple(str(row[0]) for row in numbers),
                )
            )
    return found


def find_stock_holdings(
    session: Session,
    firm_id: UUID,
    *,
    product_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    branch_id: UUID | None = None,
) -> list[StockHolding]:
    """Return every place still holding stock of the given record.

    A row counts when any of its buckets is non-zero -- on hand, reserved,
    blocked, damaged, quarantined or in transit -- because each of them is
    quantity somebody will have to account for. The place is named as
    ``warehouse`` or ``warehouse / storage area``; when the question is about a
    place rather than a product, the product's code is what is named instead.
    """
    from app.branches.models import Warehouse, WarehouseStorageNode
    from app.inventory.models import InventoryRecord
    from app.products.models import Product

    record = InventoryRecord
    filters: list[ColumnElement[bool]] = []
    if product_id is not None:
        filters.append(record.product_id == product_id)
    if warehouse_id is not None:
        filters.append(record.warehouse_id == warehouse_id)
    if storage_node_id is not None:
        filters.append(record.storage_node_id == storage_node_id)
    if branch_id is not None:
        filters.append(record.branch_id == branch_id)
    rows = session.execute(
        select(
            Warehouse.code,
            WarehouseStorageNode.code,
            Product.code,
            func.sum(record.current_quantity),
            func.sum(record.reserved_quantity),
        )
        # Outer joins throughout: a stock row whose warehouse or product row
        # cannot be read is still quantity on the books, and must still refuse.
        .outerjoin(Warehouse, Warehouse.id == record.warehouse_id)
        .outerjoin(Product, Product.id == record.product_id)
        .outerjoin(
            WarehouseStorageNode, WarehouseStorageNode.id == record.storage_node_id
        )
        .where(
            record.firm_id == firm_id,
            record.is_deleted.is_(False),
            or_(
                record.current_quantity != 0,
                record.reserved_quantity != 0,
                record.blocked_quantity != 0,
                record.damaged_quantity != 0,
                record.quarantine_quantity != 0,
                record.in_transit_quantity != 0,
            ),
            *filters,
        )
        .group_by(Warehouse.code, WarehouseStorageNode.code, Product.code)
        .order_by(Warehouse.code, WarehouseStorageNode.code, Product.code)
    ).all()
    holdings: list[StockHolding] = []
    for warehouse_code, node_code, product_code, on_hand, reserved in rows:
        place = str(warehouse_code or "an unknown warehouse")
        if node_code:
            place = f"{place} / {node_code}"
        if product_id is None:
            place = f"{place} ({product_code or 'an unknown product'})"
        holdings.append(
            StockHolding(
                place=place,
                on_hand=Decimal(on_hand or 0),
                reserved=Decimal(reserved or 0),
            )
        )
    return holdings


def describe_stock(holdings: list[StockHolding]) -> str:
    """Render holdings as ``holds 45 in MAIN, 5 in MAIN / BIN-1``."""
    shown = ", ".join(holding.describe() for holding in holdings[:_SHOWN])
    more = len(holdings) - _SHOWN
    return f"{shown}{f' and {more} more places' if more > 0 else ''}"


def describe_documents(found: list[OpenDocuments]) -> str:
    """Render open documents as ``1 sales order (SO-1), 2 goods receipts (…)``."""
    return ", ".join(group.describe() for group in found)
