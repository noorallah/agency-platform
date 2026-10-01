"""One quantity picture per purchase order line (backlog 69 row 5).

Receipts, bills and returns each kept their own idea of how much of an order
line they had dealt with, and the order itself showed none of it: a buyer
asking "how much of line 3 has arrived, been rejected, gone back, been
billed?" had to open every document downstream. This answers it once, for a
page of orders, in a fixed number of statements:

* **received / accepted / rejected / damaged** -- completed or closed goods
  receipts against the line;
* **returned** -- completed or closed purchase returns raised off the line
  itself, off a receipt of it, or off a bill of it;
* **invoiced** -- approved or closed bills raised off the line or off a
  receipt of it;
* **pending receipt** -- ordered less received;
* **to invoice** -- accepted, less returned, less invoiced.

Every figure is in the order line's own unit, which the receipt carries and a
bill line raised from it inherits. Derived on every read, never stored: a
counter on the line is one more thing to disagree with the documents
(docs/SALES_CHAIN_RULES.md -- a status is derived by summing what happened).

The order's **billing status** comes from the same figures, beside its
lifecycle status rather than in it, so that billing never overwrites how far
receiving got (docs/OWNER_DECISIONS.md A33).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.purchase.models import PurchaseOrderLine

ZERO = Decimal("0")

#: Documents that count: a draft has not happened and a cancelled one undid.
_LIVE_RECEIPT = ("COMPLETED", "CLOSED")
_LIVE_BILL = ("APPROVED", "CLOSED")
_LIVE_RETURN = ("COMPLETED", "CLOSED")


@dataclass(frozen=True, slots=True)
class LineQuantities:
    """What has happened to one order line, in its own unit."""

    ordered: Decimal = ZERO
    received: Decimal = ZERO
    accepted: Decimal = ZERO
    rejected: Decimal = ZERO
    damaged: Decimal = ZERO
    returned: Decimal = ZERO
    invoiced: Decimal = ZERO

    @property
    def pending_receipt(self) -> Decimal:
        """Return what the supplier still owes."""
        return max(self.ordered - self.received, ZERO)

    @property
    def to_invoice(self) -> Decimal:
        """Return what was kept and has not been billed yet."""
        return max(self.accepted - self.returned - self.invoiced, ZERO)


def billing_status(quantities: Sequence[LineQuantities]) -> str:
    """Return ``NOT_INVOICED``, ``PARTIALLY_INVOICED`` or ``INVOICED``.

    Invoiced once nothing is left to receive or to bill on any line; partly,
    while anything has been billed and something is still to come.
    """
    if sum((line.invoiced for line in quantities), ZERO) <= ZERO:
        return "NOT_INVOICED"
    if any(
        line.pending_receipt > ZERO or line.to_invoice > ZERO for line in quantities
    ):
        return "PARTIALLY_INVOICED"
    return "INVOICED"


def is_complete(quantities: Sequence[LineQuantities]) -> bool:
    """Return whether every line was received in full and nothing is left to bill."""
    return bool(quantities) and all(
        line.received > ZERO
        and line.pending_receipt <= ZERO
        and line.to_invoice <= ZERO
        for line in quantities
    )


def order_line_quantities(
    session: Session, lines: Sequence[PurchaseOrderLine]
) -> dict[UUID, LineQuantities]:
    """Return the quantity picture of each given order line, by its id."""
    from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
    from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    if not lines:
        return {}
    po_lines = [line.id for line in lines]
    sums: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

    # Receipts: every receipt line of these order lines, live or not, so a
    # bill or a return raised off any of them can be traced back.
    receipt_of: dict[UUID, UUID] = {}
    for (
        receipt_line_id,
        po_line_id,
        received,
        accepted,
        rejected,
        damaged,
        status,
        deleted,
    ) in session.execute(
        select(
            GoodsReceiptLine.id,
            GoodsReceiptLine.purchase_order_line_id,
            GoodsReceiptLine.current_receipt_quantity,
            GoodsReceiptLine.accepted_quantity,
            GoodsReceiptLine.rejected_quantity,
            GoodsReceiptLine.damaged_quantity,
            GoodsReceipt.status,
            GoodsReceipt.is_deleted,
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .where(
            GoodsReceiptLine.purchase_order_line_id.in_(po_lines),
            GoodsReceiptLine.is_deleted.is_(False),
        )
    ).all():
        receipt_of[receipt_line_id] = po_line_id
        if deleted or status not in _LIVE_RECEIPT:
            continue
        line_sums = sums[po_line_id]
        line_sums["received"] += Decimal(str(received))
        line_sums["accepted"] += Decimal(str(accepted))
        line_sums["rejected"] += Decimal(str(rejected))
        line_sums["damaged"] += Decimal(str(damaged))

    # Bills raised off the order line or off a receipt of it.
    bill_sources = [
        and_(
            PurchaseInvoiceLine.source_document_type == "PURCHASE_ORDER",
            PurchaseInvoiceLine.source_document_line_id.in_(po_lines),
        )
    ]
    if receipt_of:
        bill_sources.append(
            and_(
                PurchaseInvoiceLine.source_document_type == "GOODS_RECEIPT",
                PurchaseInvoiceLine.source_document_line_id.in_(list(receipt_of)),
            )
        )
    bill_of: dict[UUID, UUID] = {}
    for (
        bill_line_id,
        kind,
        source_line_id,
        quantity,
        status,
        deleted,
    ) in session.execute(
        select(
            PurchaseInvoiceLine.id,
            PurchaseInvoiceLine.source_document_type,
            PurchaseInvoiceLine.source_document_line_id,
            PurchaseInvoiceLine.current_invoice_quantity,
            PurchaseInvoice.status,
            PurchaseInvoice.is_deleted,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(PurchaseInvoiceLine.is_deleted.is_(False), or_(*bill_sources))
    ).all():
        po_line_id = (
            source_line_id if kind == "PURCHASE_ORDER" else receipt_of[source_line_id]
        )
        bill_of[bill_line_id] = po_line_id
        if deleted or status not in _LIVE_BILL:
            continue
        sums[po_line_id]["invoiced"] += Decimal(str(quantity))

    # Returns raised off the order line, a receipt of it, or a bill of it.
    return_sources = [
        and_(
            PurchaseReturnLine.source_document_type == "PURCHASE_ORDER",
            PurchaseReturnLine.source_document_line_id.in_(po_lines),
        )
    ]
    if receipt_of:
        return_sources.append(
            and_(
                PurchaseReturnLine.source_document_type == "GOODS_RECEIPT",
                PurchaseReturnLine.source_document_line_id.in_(list(receipt_of)),
            )
        )
    if bill_of:
        return_sources.append(
            and_(
                PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                PurchaseReturnLine.source_document_line_id.in_(list(bill_of)),
            )
        )
    for kind, source_line_id, quantity in session.execute(
        select(
            PurchaseReturnLine.source_document_type,
            PurchaseReturnLine.source_document_line_id,
            PurchaseReturnLine.current_return_quantity,
        )
        .join(
            PurchaseReturn,
            PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
        )
        .where(
            PurchaseReturnLine.is_deleted.is_(False),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(_LIVE_RETURN),
            or_(*return_sources),
        )
    ).all():
        if kind == "PURCHASE_ORDER":
            po_line_id = source_line_id
        elif kind == "GOODS_RECEIPT":
            po_line_id = receipt_of[source_line_id]
        else:
            po_line_id = bill_of[source_line_id]
        sums[po_line_id]["returned"] += Decimal(str(quantity))

    return {
        line.id: LineQuantities(
            ordered=Decimal(str(line.ordered_quantity)),
            received=sums[line.id]["received"],
            accepted=sums[line.id]["accepted"],
            rejected=sums[line.id]["rejected"],
            damaged=sums[line.id]["damaged"],
            returned=sums[line.id]["returned"],
            invoiced=sums[line.id]["invoiced"],
        )
        for line in lines
    }


__all__ = [
    "LineQuantities",
    "billing_status",
    "is_complete",
    "order_line_quantities",
]
