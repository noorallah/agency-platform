"""The unit a sales bill line is typed in, resolved once.

A bill line can name a unit in two fields. ``invoice_uom_id`` is the unit the
line is billed in. ``order_uom_id`` is the unit of the line it bills -- the
note's or the order's -- and on a line typed straight onto a bill, where
there is no such line, it can only mean the unit the goods are sold in.

Only ``invoice_uom_id`` was read. A counter bill line naming ``order_uom_id``
BOX and nothing else was taken as pieces: 2 at 100.00, 236.00 with tax, two
pieces off the shelf, and the line came back with no unit -- the unit asked
for dropped without a word (D-PRC-44). **A line that names a unit by either
field means that unit**, and a pair that cannot both be true is refused
rather than one of the two being quietly ignored.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.uom.models import Uom


def _code(session: Session, uom_id: UUID) -> str:
    """Return a unit's code for a refusal."""
    unit = session.get(Uom, uom_id)
    return unit.code if unit is not None else "an unknown unit"


def unit_of_a_bare_line(
    session: Session,
    *,
    line_number: int,
    order_uom_id: UUID | None,
    invoice_uom_id: UUID | None,
) -> UUID | None:
    """Return the unit a line typed straight onto a bill is sold in.

    Whichever of the two fields names one; None where neither does, which is
    the product's own unit. There is no line behind a bare line for
    ``order_uom_id`` to describe, so the two fields say the same thing and
    two different answers cannot both be meant.

    Raises:
        ValidationError: The line names two different units.

    """
    if (
        order_uom_id is not None
        and invoice_uom_id is not None
        and order_uom_id != invoice_uom_id
    ):
        raise ValidationError(
            f"Line {line_number} names two units: {_code(session, order_uom_id)} "
            f"as the unit it is ordered in and {_code(session, invoice_uom_id)} "
            "as the unit it is billed in. A line typed straight onto a bill is "
            "sold in one unit; name that unit once.",
            details={"field": "lines"},
        )
    return invoice_uom_id or order_uom_id


def unit_of_a_line_billing_a_document(
    session: Session,
    *,
    line_number: int,
    order_uom_id: UUID | None,
    invoice_uom_id: UUID | None,
    source_uom_id: UUID | None,
    source_label: str,
) -> UUID | None:
    """Return the unit a line billing a note or an order is typed in.

    ``invoice_uom_id`` where the line names it. Then ``order_uom_id`` must be
    true of the line billed: it is that line's unit, and a line saying it
    bills pieces of a line delivered by the box describes another document.
    Where only ``order_uom_id`` is named it is the unit the line is in, and
    is converted like any typed unit if the source line's is another. None
    where neither is named: the source line's own unit.

    Raises:
        ValidationError: ``order_uom_id`` contradicts the line being billed.

    """
    if invoice_uom_id is None:
        return order_uom_id
    if (
        order_uom_id is not None
        and source_uom_id is not None
        and order_uom_id != source_uom_id
    ):
        raise ValidationError(
            f"Line {line_number} says the line it bills is in "
            f"{_code(session, order_uom_id)}, and {source_label} is in "
            f"{_code(session, source_uom_id)}. Leave the ordered unit off, or "
            f"send {_code(session, source_uom_id)}; the unit the line is billed "
            "in is the other field.",
            details={"field": "lines"},
        )
    return invoice_uom_id
