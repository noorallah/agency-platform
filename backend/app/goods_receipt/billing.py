"""What is left to bill on a goods receipt line (D-BUY-26).

A receipt line is billed by bills raised off it and can be returned before any
bill reaches it. Goods sent back before billing never become a payable: the
supplier bills what the firm kept. So what is left to bill is

    accepted - billed on approved or closed bills - returned before billing

and the part of a return taken against what was still to bill is recorded on
the return line (``unbilled_quantity``) when the return completes. That part
reverses the receipt's accrual, Dr goods received not invoiced / Cr inventory,
at the receipt's own cost (``grni_amount``); only the rest of the return is a
debit note against a bill.

The bill (its cap and the accrual it clears), the return (its split) and the
receipt's response all read the figures here, so the three cannot disagree.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.goods_receipt.models import GoodsReceiptLine
from app.inventory.models import StockLedgerEntry

ZERO = Decimal("0")

#: A bill counts once it is approved: a draft has billed nothing yet.
BILLED_STATES = ("APPROVED", "CLOSED")
#: A return counts once its goods have gone back.
RETURNED_STATES = ("COMPLETED", "CLOSED")


@dataclass(frozen=True, slots=True)
class ReceiptLineBilling:
    """Where one receipt line stands against its bills and returns."""

    accepted: Decimal
    billed: Decimal = ZERO
    returned_unbilled: Decimal = ZERO
    #: What those returns took off goods received not invoiced.
    returned_cost: Decimal = ZERO

    @property
    def left_to_bill(self) -> Decimal:
        """Return what the supplier may still bill on the line."""
        return max(self.accepted - self.billed - self.returned_unbilled, ZERO)


def receipt_line_billing(
    session: Session,
    lines: Iterable[GoodsReceiptLine],
    *,
    except_invoice_id: UUID | None = None,
) -> dict[UUID, ReceiptLineBilling]:
    """Return each receipt line's billing position, by its id.

    Two statements whatever the number of lines.

    Args:
        session: The firm's store.
        lines: The receipt lines asked about.
        except_invoice_id: A bill to leave out of ``billed`` -- the one being
            approved, which is counted by its caller.

    Returns:
        One position per line given.

    """
    from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    accepted = {line.id: Decimal(str(line.accepted_quantity)) for line in lines}
    if not accepted:
        return {}
    billed: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    bills = (
        select(
            PurchaseInvoiceLine.source_document_line_id,
            func.coalesce(func.sum(PurchaseInvoiceLine.current_invoice_quantity), 0),
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(
            PurchaseInvoiceLine.source_document_type == "GOODS_RECEIPT",
            PurchaseInvoiceLine.source_document_line_id.in_(list(accepted)),
            PurchaseInvoiceLine.is_deleted.is_(False),
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(BILLED_STATES),
        )
        .group_by(PurchaseInvoiceLine.source_document_line_id)
    )
    if except_invoice_id is not None:
        bills = bills.where(PurchaseInvoice.id != except_invoice_id)
    for line_id, quantity in session.execute(bills).all():
        billed[line_id] = Decimal(str(quantity))
    returned: dict[UUID, tuple[Decimal, Decimal]] = {}
    for line_id, quantity, cost in session.execute(
        select(
            PurchaseReturnLine.source_document_line_id,
            func.coalesce(func.sum(PurchaseReturnLine.unbilled_quantity), 0),
            func.coalesce(func.sum(PurchaseReturnLine.grni_amount), 0),
        )
        .join(
            PurchaseReturn,
            PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
        )
        .where(
            PurchaseReturnLine.source_document_type == "GOODS_RECEIPT",
            PurchaseReturnLine.source_document_line_id.in_(list(accepted)),
            PurchaseReturnLine.is_deleted.is_(False),
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(RETURNED_STATES),
        )
        .group_by(PurchaseReturnLine.source_document_line_id)
    ).all():
        returned[line_id] = (Decimal(str(quantity)), Decimal(str(cost)))
    return {
        line_id: ReceiptLineBilling(
            accepted=quantity,
            billed=billed[line_id],
            returned_unbilled=returned.get(line_id, (ZERO, ZERO))[0],
            returned_cost=returned.get(line_id, (ZERO, ZERO))[1],
        )
        for line_id, quantity in accepted.items()
    }


def receipt_line_costs(
    session: Session, lines: Iterable[GoodsReceiptLine]
) -> dict[UUID, Decimal]:
    """Return what each receipt line's movement cost -- what it accrued."""
    movements = {
        line.inventory_transaction_id: line.id
        for line in lines
        if line.inventory_transaction_id is not None
    }
    costs: dict[UUID, Decimal] = {}
    if not movements:
        return costs
    for transaction_id, cost in session.execute(
        select(
            StockLedgerEntry.transaction_id,
            func.coalesce(func.sum(StockLedgerEntry.total_cost), 0),
        )
        .where(
            StockLedgerEntry.transaction_id.in_(list(movements)),
            StockLedgerEntry.is_deleted.is_(False),
        )
        .group_by(StockLedgerEntry.transaction_id)
    ).all():
        costs[movements[transaction_id]] = Decimal(str(cost))
    return costs


__all__ = [
    "BILLED_STATES",
    "RETURNED_STATES",
    "ReceiptLineBilling",
    "receipt_line_billing",
    "receipt_line_costs",
]
