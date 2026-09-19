"""Rules other modules apply to a goods receipt they are about to build on."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine

#: The states in which a receipt's stock has been posted. A receipt is closed
#: only once it is complete, so both mean the goods are on the shelf.
POSTED_STATES = frozenset({"COMPLETED", "CLOSED"})


def require_posted_receipt(receipt: GoodsReceipt, verb: str) -> None:
    """Refuse a receipt whose stock was never posted, or was taken back.

    A bill or a return names a receipt because the goods arrived. Neither
    checked that they had: a DRAFT receipt could be billed and the bill
    approved -- a payable, and an accrual cleared, for goods nobody had
    received -- and returned against, taking out stock that was never put in
    (D-BUY-5, driven on TEST01 on 2026-09-18). A cancelled receipt is the same
    case after the fact.

    Args:
        receipt: The receipt being built on.
        verb: What is being done to it, for the refusal ("billed", "returned").

    Raises:
        ValidationError: When the receipt is not completed.

    """
    if receipt.status not in POSTED_STATES:
        raise ValidationError(
            f"{receipt.grn_number} is {receipt.status.lower()}, so it cannot be "
            f"{verb}: only a completed goods receipt can. Complete it first."
        )


def posted_receipt_line(
    session: Session,
    *,
    firm_id: UUID,
    receipt_id: UUID,
    line_id: UUID,
    verb: str,
) -> GoodsReceiptLine:
    """Return the receipt line a bill or a return names, and only that.

    A bill line and a return line each name a receipt and one of its lines.
    The line used to be loaded by its id alone, so a line naming a completed
    receipt could carry the id of *another* receipt's line -- a draft one, or
    another firm's -- and the cap, the product and the price were all taken
    from whichever line the caller pointed at (D-BUY-17, the purchasing twin
    of D-SELL-6). Driven on TEST01 on 2026-09-19: a bill naming a completed
    receipt of 6 billed 10 off a DRAFT receipt of another order, and a return
    the same way took the shelf to -10.

    Args:
        session: The firm's store.
        firm_id: The firm acting.
        receipt_id: The receipt the bill or return line names.
        line_id: The receipt line it names.
        verb: What is being done to it, for the refusal ("billed", "returned").

    Returns:
        The line, which belongs to that receipt, in that firm.

    Raises:
        ResourceNotFoundError: When the firm has no such receipt.
        ValidationError: When the receipt is not completed, or the line is not
            one of its lines.

    """
    receipt = session.scalar(
        select(GoodsReceipt).where(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.is_deleted.is_(False),
        )
    )
    if receipt is None:
        raise ResourceNotFoundError("Goods receipt not found.")
    require_posted_receipt(receipt, verb)
    line = session.scalar(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.id == line_id,
            GoodsReceiptLine.goods_receipt_id == receipt.id,
            GoodsReceiptLine.firm_id == firm_id,
            GoodsReceiptLine.is_deleted.is_(False),
        )
    )
    if line is None:
        raise ValidationError(
            f"{receipt.grn_number} has no line {line_id}, so it cannot be "
            f"{verb} against it: a line is {verb} against the goods receipt it "
            "belongs to."
        )
    return line
