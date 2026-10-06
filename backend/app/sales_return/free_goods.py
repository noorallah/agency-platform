"""Free goods that came back, for the readers that counted them going out.

A sales return line can bring back free goods beside its charged units
(`sales_return_lines.free_quantity`, D-PRC-8). Two readers count free goods
on the way *out* and have to net what came back, or they overstate what was
given: an offer's free-unit budget (`budget_rooms` in `app/promotions`) and a
principal's claim for free goods (`app/principal_claims`).

Both ask the same question -- which note line did these goods leave on --
and a return names either that note line or the bill line that billed it, so
the join is written once here. Only a return that has **completed** has
brought anything back.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, and_, case, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_return.models import SalesReturn, SalesReturnLine

#: A return that has put its goods back on the shelf.
RETURNED_STATUSES = ("COMPLETED", "CLOSED")


def free_goods_returned(
    *columns: ColumnElement[Any] | InstrumentedAttribute[Any],
) -> Select[Any]:
    """Select ``columns`` over the free goods completed returns brought back.

    Joined to ``DeliveryNoteLine`` -- the line the goods left on -- whichever
    document the return line named: the note line itself, or a bill line
    that billed it. The caller adds its own joins, filters and grouping, and
    sums ``SalesReturnLine.free_quantity``.
    """
    on_a_bill = SalesReturnLine.source_document_type == "SALES_INVOICE"
    note_line_id = case(
        (on_a_bill, SalesInvoiceLine.source_document_line_id),
        else_=SalesReturnLine.source_document_line_id,
    )
    return (
        select(*columns)
        .select_from(SalesReturnLine)
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .outerjoin(
            SalesInvoiceLine,
            and_(
                on_a_bill,
                SalesInvoiceLine.id == SalesReturnLine.source_document_line_id,
                SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
            ),
        )
        .join(DeliveryNoteLine, DeliveryNoteLine.id == note_line_id)
        .where(
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(RETURNED_STATUSES),
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLine.free_quantity > 0,
        )
    )
