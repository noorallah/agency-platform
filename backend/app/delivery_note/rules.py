"""Rules other modules apply to a delivery note they are about to build on."""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine

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


def goods_have_left_clause() -> ColumnElement[bool]:
    """Say the same as `goods_have_left`, as a filter for a query."""
    return and_(
        DeliveryNote.status.in_(sorted(SHIPPED_STATES)),
        DeliveryNote.dispatched_at.is_not(None),
    )


def delivered_by_order_line(
    session: Session, *, firm_id: UUID, sales_order_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Sum what has actually left the warehouse against each order line.

    One grouped read for a set of orders, over the notes whose goods went out
    (`goods_have_left_clause`), which is the derivation the order's own status
    follows (`_resync_order_status`). The reports used to count what was
    typed instead -- a DRAFT note's quantity in the by-warehouse total, an
    APPROVED note as delivered in the progress report, and an order still
    owing stock left out of "not yet delivered" because only DRAFT and
    APPROVED were asked for (D-RPT-7, D-RPT-9).

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        sales_order_ids: The orders whose lines to sum for.

    Returns:
        Delivered quantity per `sales_order_line_id`, for lines with any.

    """
    ids = list(sales_order_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(
            DeliveryNoteLine.sales_order_line_id,
            func.coalesce(func.sum(DeliveryNoteLine.delivered_quantity), 0),
        )
        .join(DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id)
        .where(
            DeliveryNoteLine.firm_id == firm_id,
            DeliveryNote.sales_order_id.in_(ids),
            DeliveryNoteLine.is_deleted.is_(False),
            DeliveryNote.is_deleted.is_(False),
            goods_have_left_clause(),
        )
        .group_by(DeliveryNoteLine.sales_order_line_id)
    ).all()
    return {line_id: Decimal(str(total)) for line_id, total in rows if line_id}


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
