"""Rules other modules apply to a delivery note they are about to build on."""

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote

#: The states a note can be in once its goods have left. A note is completed
#: or closed from here, so all three can mean the goods are with the customer.
SHIPPED_STATES = frozenset({"DISPATCHED", "COMPLETED", "CLOSED"})


def goods_have_left(note: DeliveryNote) -> bool:
    """Say whether a note's goods actually went out.

    The status alone is not enough: a note can be closed from APPROVED without
    ever being dispatched. `dispatched_at` is stamped by the dispatch that
    takes the stock out, and only by it.
    """
    return note.status in SHIPPED_STATES and note.dispatched_at is not None


def require_dispatched_note(note: DeliveryNote, verb: str) -> None:
    """Refuse a note whose goods never left, or were never meant to.

    A bill names a note because the goods went out. It checked only that the
    note existed, so a DRAFT, APPROVED or CANCELLED note could be billed and
    the bill approved -- revenue and a receivable with no stock out and no
    cost of goods behind them (D-SELL-3, driven 2026-09-19; the twin of
    D-BUY-5's `app/goods_receipt/rules.py`).

    Args:
        note: The note being built on.
        verb: What is being done to it, for the refusal ("billed").

    Raises:
        ValidationError: When the note's goods have not left.

    """
    if not goods_have_left(note):
        raise ValidationError(
            f"{note.delivery_note_number} is {note.status.lower()}, so it cannot "
            f"be {verb}: only a dispatched delivery note can. Dispatch it first."
        )
