"""Rules other modules apply to a goods receipt they are about to build on."""

from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt

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
