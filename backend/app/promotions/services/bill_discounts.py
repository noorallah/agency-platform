"""What the offers' discount came to on each bill line, and what came back.

An order line records what the firm's offers took off it. Part of that is
**passed on** by every bill line that continues it, and part of what was
passed on **comes back** when the goods are returned or the bill is credited.
Two readers need both figures and must never work them differently:

* a claim on a principal, which asks for its share of what the customer kept
  (`app/principal_claims/services/passed_on.py`, D-PRC-27);
* an offer's own use -- its money budget and every report of it -- which
  counted a returned sale's discount as still given (D-PRC-45).

`discount_on_bills` is the one statement both read: a row per standing bill
line of an order, with the discount it carried (``passed``), the share of the
line that has come back (``returned``, between nothing and all of it) and
what the offers took off the whole order (``whole``).

**The share a bill line took** is the part of the note line it billed times
the part of the order line that note shipped (or the part of the order line
it billed directly, for a firm that types no notes). That share of what the
offers took off the order line -- its line discount where the line says an
offer set it, its part of the bill discount where the order says an offer set
that (`offer_took_off`, here as a column), and the delivery charge an offer
waived, by value -- is what the bill passed on.

**What came back** is summed over three routes and never more than the line:
a completed return of the bill line, a completed return of the note line it
billed (the billed part of it), and an approved credit note against it, by
value.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, literal_column, or_, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.credit_note.models import CreditNote, CreditNoteLine
from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.models import SalesReturn, SalesReturnLine

#: A bill that stands: a draft has charged nobody and a cancelled one gave
#: its discount back with everything else.
BILLED = ("APPROVED", "CLOSED")
#: A return whose goods are back and whose credit is given.
RETURNED = ("COMPLETED", "CLOSED")

#: Multiplied in before a division, so SQLite does not divide two whole
#: numbers as integers (2 / 4 = 0); PostgreSQL divides numerics either way.
_EXACT: ColumnElement[Any] = literal_column("1.0")


#: A numeric column of a model or of a subquery.
_Number = ColumnElement[Any] | InstrumentedAttribute[Any]


def _part(part: _Number, whole: _Number) -> ColumnElement[Any]:
    """Return ``part`` of ``whole`` as a share between nothing and all of it."""
    return case(
        (or_(part.is_(None), whole.is_(None)), 0),
        (or_(part <= 0, whole <= 0), 0),
        (part >= whole, 1),
        else_=part * _EXACT / whole,
    )


def offers_took_off_line() -> ColumnElement[Any]:
    """Return what the firm's offers took off an order line, as a column.

    The reading `offer_use.offer_took_off` makes of a row already loaded, for
    a statement joining ``SalesOrderLine`` to its ``SalesOrder``.
    """
    return case(
        (
            SalesOrderLine.discount_source == "promotion",
            func.coalesce(SalesOrderLine.discount_amount, 0),
        ),
        else_=0,
    ) + case(
        (
            SalesOrder.bill_discount_source == "promotion",
            func.coalesce(SalesOrderLine.bill_discount_amount, 0),
        ),
        else_=0,
    )


def discount_on_bills(firm_id: UUID, *where: ColumnElement[bool]) -> Select[Any]:
    """Select the offers' discount on every standing bill line of an order.

    Columns: ``bill_line_id``, ``invoice_id``, ``invoice_number``,
    ``invoice_date``, ``order_id``, ``order_number``, ``passed`` (the offers'
    discount the bill line carried), ``returned`` (the share of the line that
    came back, 0 to 1) and ``whole`` (what the offers took off the whole
    order; its worth where its lines carry no offer's figure).

    Args:
        firm_id: The firm whose bills to read.
        *where: Further conditions on ``SalesInvoice``, ``SalesInvoiceLine``
            or ``SalesOrderLine`` -- a period, a set of orders.

    Returns:
        The statement, for the caller to run or to group.

    """
    from_a_note = SalesInvoiceLine.source_document_type == "DELIVERY_NOTE"
    order_line_id = case(
        (from_a_note, DeliveryNoteLine.sales_order_line_id),
        else_=SalesInvoiceLine.source_document_line_id,
    )
    took_line = offers_took_off_line()
    per_order = (
        select(
            SalesOrderLine.sales_order_id.label("order_id"),
            func.sum(took_line).label("took"),
            func.sum(func.coalesce(SalesOrderLine.gross_amount, 0)).label("worth"),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(SalesOrder.firm_id == firm_id, SalesOrderLine.is_deleted.is_(False))
        .group_by(SalesOrderLine.sales_order_id)
        .subquery("order_offers")
    )
    done = (
        SalesReturn.firm_id == firm_id,
        SalesReturn.is_deleted.is_(False),
        SalesReturn.status.in_(RETURNED),
        SalesReturnLine.is_deleted.is_(False),
    )
    off_bill = (
        select(
            SalesReturnLine.source_document_line_id.label("line_id"),
            func.sum(SalesReturnLine.current_return_quantity).label("units"),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(*done, SalesReturnLine.source_document_type == "SALES_INVOICE")
        .group_by(SalesReturnLine.source_document_line_id)
        .subquery("returned_off_bill")
    )
    # A return off the note: only the part of it that had been billed took
    # any discount back, and each bill of that note line gave it in the
    # proportion it billed.
    off_note = (
        select(
            SalesReturnLine.source_document_line_id.label("line_id"),
            func.sum(
                SalesReturnLine.current_return_quantity
                - func.coalesce(SalesReturnLine.unbilled_quantity, 0)
            ).label("units"),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(*done, SalesReturnLine.source_document_type == "DELIVERY_NOTE")
        .group_by(SalesReturnLine.source_document_line_id)
        .subquery("returned_off_note")
    )
    credited = (
        select(
            CreditNoteLine.sales_invoice_line_id.label("line_id"),
            func.sum(CreditNoteLine.taxable_amount).label("amount"),
        )
        .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
        .where(
            CreditNote.firm_id == firm_id,
            CreditNote.is_deleted.is_(False),
            CreditNote.status == "APPROVED",
            CreditNoteLine.is_deleted.is_(False),
            CreditNoteLine.sales_invoice_line_id.is_not(None),
        )
        .group_by(CreditNoteLine.sales_invoice_line_id)
        .subquery("credited")
    )
    share = _part(
        SalesInvoiceLine.current_invoice_quantity, SalesInvoiceLine.delivered_quantity
    ) * case(
        (
            from_a_note,
            _part(
                DeliveryNoteLine.current_delivery_quantity,
                DeliveryNoteLine.ordered_quantity,
            ),
        ),
        else_=1,
    )
    waived = func.coalesce(SalesOrder.freight_waived_amount, 0)
    worth_line = func.coalesce(SalesOrderLine.gross_amount, 0)
    by_value = worth_line * share
    passed = case(
        # Nothing on the order's lines says what the offer took (a benefit
        # the lines do not carry): the bill's share by value.
        (
            per_order.c.took + waived <= 0,
            case((per_order.c.worth > 0, by_value), else_=took_line * share),
        ),
        else_=took_line * share
        + case(
            (
                and_(waived > 0, per_order.c.worth > 0),
                waived * by_value * _EXACT / per_order.c.worth,
            ),
            else_=0,
        ),
    )
    charged = (
        func.coalesce(SalesInvoiceLine.gross_amount, 0)
        - func.coalesce(SalesInvoiceLine.discount_amount, 0)
        - func.coalesce(SalesInvoiceLine.bill_discount_amount, 0)
    )
    came_back = (
        _part(off_bill.c.units, SalesInvoiceLine.current_invoice_quantity)
        + case(
            (
                from_a_note,
                _part(off_note.c.units, SalesInvoiceLine.delivered_quantity),
            ),
            else_=0,
        )
        + _part(credited.c.amount, charged)
    )
    return (
        select(
            SalesInvoiceLine.id.label("bill_line_id"),
            SalesInvoice.id.label("invoice_id"),
            SalesInvoice.invoice_number.label("invoice_number"),
            SalesInvoice.invoice_date.label("invoice_date"),
            SalesOrder.id.label("order_id"),
            SalesOrder.order_number.label("order_number"),
            passed.label("passed"),
            case((came_back >= 1, 1), else_=came_back).label("returned"),
            case(
                (per_order.c.took + waived > 0, per_order.c.took + waived),
                else_=per_order.c.worth,
            ).label("whole"),
        )
        .select_from(SalesInvoiceLine)
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .outerjoin(
            DeliveryNoteLine,
            and_(
                from_a_note,
                DeliveryNoteLine.id == SalesInvoiceLine.source_document_line_id,
            ),
        )
        .join(SalesOrderLine, SalesOrderLine.id == order_line_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .join(per_order, per_order.c.order_id == SalesOrder.id)
        .outerjoin(off_bill, off_bill.c.line_id == SalesInvoiceLine.id)
        .outerjoin(
            off_note,
            and_(
                from_a_note,
                off_note.c.line_id == SalesInvoiceLine.source_document_line_id,
            ),
        )
        .outerjoin(credited, credited.c.line_id == SalesInvoiceLine.id)
        .where(
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(BILLED),
            SalesInvoiceLine.is_deleted.is_(False),
            *where,
        )
    )


def discount_came_back(firm_id: UUID, *where: ColumnElement[bool]) -> Select[Any]:
    """Select, per order, the share of its offers' discount that came back.

    Columns: ``order_id`` and ``share`` (0 to 1): what completed returns and
    approved credit notes took back of the discount the order's bills passed
    on, over what the offers took off the whole order. A claim on an offer
    gave that share of its benefit back. Orders nothing came back on are not
    in it.
    """
    lines = discount_on_bills(firm_id, *where).subquery("bill_discounts")
    back = func.sum(lines.c.passed * lines.c.returned)
    return (
        select(
            lines.c.order_id.label("order_id"),
            case(
                (lines.c.whole <= 0, 0),
                (back >= lines.c.whole, 1),
                else_=back * _EXACT / lines.c.whole,
            ).label("share"),
        )
        .where(lines.c.returned > 0)
        .group_by(lines.c.order_id, lines.c.whole)
    )
