"""The order line behind each bill line, and the offers it names (L7 step 9).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` sections 3.9 and 4. A bill
keeps no offer rows of its own: it reads them through the order line it
continues, directly or through a delivery note's line, so the order and the
bill are one record rather than two that can disagree. The print and the
bill's view both ask here, each once for the lines they hold.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_order.models import SalesOrderOffer

APPLIED = "APPLIED"


def order_lines_behind(
    session: Session, lines: Sequence[SalesInvoiceLine]
) -> dict[UUID, UUID]:
    """Return, by bill line id, the order line each bill line continues.

    A line raised from an order names its line; one raised from a delivery
    note reaches it through the note's line, read in one statement and only
    where a note line is billed. A line with neither is left out.
    """
    of_order_line: dict[UUID, UUID] = {
        line.id: line.source_document_line_id
        for line in lines
        if line.source_document_type == "SALES_ORDER"
    }
    from_notes = {
        line.id: line.source_document_line_id
        for line in lines
        if line.source_document_type == "DELIVERY_NOTE"
    }
    if from_notes:
        order_line_of = {
            note_line_id: order_line_id
            for note_line_id, order_line_id in session.execute(
                select(DeliveryNoteLine.id, DeliveryNoteLine.sales_order_line_id).where(
                    DeliveryNoteLine.id.in_(list(set(from_notes.values())))
                )
            )
            if order_line_id is not None
        }
        of_order_line.update(
            {
                line_id: order_line_of[note_line_id]
                for line_id, note_line_id in from_notes.items()
                if note_line_id in order_line_of
            }
        )
    return of_order_line


def offers_behind(
    session: Session, of_order_line: Mapping[UUID, UUID]
) -> dict[UUID, list[SalesOrderOffer]]:
    """Return, by bill line id, the offer rows of the order line behind it.

    One statement for every line asked about, in sequence: the APPLIED rows
    first and any REFUSED ones after, as the order lists them. A bill line
    whose order line holds no rows -- one saved before L7 -- is left out.
    """
    if not of_order_line:
        return {}
    by_order_line: dict[UUID, list[SalesOrderOffer]] = {}
    for row in session.scalars(
        select(SalesOrderOffer)
        .where(
            SalesOrderOffer.sales_order_line_id.in_(list(set(of_order_line.values()))),
            SalesOrderOffer.is_deleted.is_(False),
        )
        .order_by(SalesOrderOffer.sequence.asc())
    ):
        if row.sales_order_line_id is not None:
            by_order_line.setdefault(row.sales_order_line_id, []).append(row)
    return {
        line_id: by_order_line[order_line_id]
        for line_id, order_line_id in of_order_line.items()
        if order_line_id in by_order_line
    }


def printed_offer_codes(rows: Sequence[SalesOrderOffer]) -> tuple[str, ...]:
    """Return the codes a print names under a line: "Offer: TEA-11".

    Only an offer the line was given -- an APPLIED promotion row with a
    discount or free goods. Never a price list, a standing rate or an offer
    passed over: a print states the deal, not the choice (design section 4).
    """
    codes = (
        row.code
        for row in rows
        if row.state == APPLIED
        and row.source == "promotion"
        and (row.discount_amount > 0 or row.free_quantity > 0)
    )
    return tuple(dict.fromkeys(codes))
