"""What an offer's discount came to on the bills, for a claim on its principal.

A redemption is the **order's**: it is claimed when the order is approved and
says what the offer took off that order. A principal owes its share of what
the firm actually gave a customer, and nothing is given until it is billed --
an order approved and never delivered gave nothing, one closed after half was
delivered gave half, and one billed and returned in full gave nothing after
all (D-PRC-27). So the scheme money on a claim is read here, off the bills.

**The share a bill line took.** A bill line continues a delivery note line,
which continues an order line (or the order line directly, for a firm that
types no notes), each for part of its quantity. The product of those parts
is the share of the order line the bill line billed, and that share of what
the offer took off the order line -- its line discount where the order line
says an offer set it, its part of the bill discount where the order says an
offer set that, and the delivery charge an offer waived, by value -- is the
discount the bill passed on. It is what the bill line inherited
(`continued_share`), read from the order's own figures so a discount somebody
typed over on the way down is not charged to the principal.

**Less what came back.** A completed sales return of the bill line (or of the
note line it billed), and an approved credit note against it, take the same
share of that discount back: half the units returned is half of it.

**One order, several offers.** An order line records one discount, not which
offer gave how much of it, so each redemption on the order takes the order's
passed-on discount in proportion to its own benefit. With one offer on the
order -- the usual case -- that is the discount exactly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.utils.money import ZERO
from app.credit_note.models import CreditNote, CreditNoteLine
from app.delivery_note.models import DeliveryNoteLine
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.services.offer_use import offer_took_off
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.models import SalesReturn, SalesReturnLine

#: A bill that stands: a draft has charged nobody and a cancelled one gave
#: its discount back with everything else.
BILLED = ("APPROVED", "CLOSED")
#: A return whose goods are back and whose credit is given.
_RETURNED = ("COMPLETED", "CLOSED")
#: Fixed, so one redemption on one bill always makes the same source id --
#: which is what lets the claim lines' unique index refuse a second claim for
#: the same discount.
_SCHEME_BILLS = UUID("3d1b0c52-8a67-4f0e-9d6b-51b7a2c9e4f3")


def scheme_bill_source(redemption_id: UUID, invoice_id: UUID) -> UUID:
    """Return the source an offer's discount on one bill is claimed under."""
    return uuid5(_SCHEME_BILLS, f"{redemption_id}:{invoice_id}")


@dataclass(frozen=True)
class PassedOn:
    """What one redemption's offer took off one bill, before any share."""

    redemption_id: UUID
    promotion_id: UUID
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    order_number: str
    #: The offer's discount the bill carried when it was approved.
    billed: Decimal
    #: The part of it completed returns and credit notes have taken back.
    came_back: Decimal

    @property
    def given(self) -> Decimal:
        """What the customer kept: the discount billed less what came back."""
        return max(self.billed - self.came_back, ZERO)


def _dec(value: object) -> Decimal:
    """Read a stored number as a Decimal; nothing is zero."""
    return Decimal(str(value or 0))


def passed_on_bills(
    session: Session,
    *,
    firm_id: UUID,
    principal_id: UUID,
    start: date,
    end: date,
) -> list[PassedOn]:
    """Return what the principal's offers took off the bills dated in a period.

    One row per live redemption and bill, in bill date order. Read over the
    period's bills in a fixed number of statements, never per bill and never
    by a list of ids.
    """
    funded = (
        select(PromotionRedemption.document_id)
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .where(
            PromotionRedemption.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            PromotionRedemption.status == "CLAIMED",
            PromotionRedemption.document_type == "SALES_ORDER",
            Promotion.principal_id == principal_id,
        )
    )
    from_a_note = SalesInvoiceLine.source_document_type == "DELIVERY_NOTE"
    order_line_id = case(
        (from_a_note, DeliveryNoteLine.sales_order_line_id),
        else_=SalesInvoiceLine.source_document_line_id,
    )
    in_period: tuple[ColumnElement[bool], ...] = (
        SalesInvoice.firm_id == firm_id,
        SalesInvoice.is_deleted.is_(False),
        SalesInvoice.status.in_(BILLED),
        SalesInvoice.invoice_date >= start,
        SalesInvoice.invoice_date <= end,
        SalesInvoiceLine.is_deleted.is_(False),
    )
    joined = (
        select(SalesOrderLine.sales_order_id)
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
        .where(*in_period, SalesOrderLine.sales_order_id.in_(funded))
    )
    billed = session.execute(
        select(
            SalesInvoiceLine.id,
            SalesInvoiceLine.current_invoice_quantity,
            SalesInvoiceLine.delivered_quantity,
            SalesInvoiceLine.gross_amount,
            SalesInvoiceLine.discount_amount,
            SalesInvoiceLine.bill_discount_amount,
            SalesInvoice.id,
            SalesInvoice.invoice_number,
            SalesInvoice.invoice_date,
            DeliveryNoteLine.id,
            DeliveryNoteLine.current_delivery_quantity,
            DeliveryNoteLine.ordered_quantity,
            SalesOrderLine.id,
            SalesOrderLine.sales_order_id,
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .outerjoin(
            DeliveryNoteLine,
            and_(
                from_a_note,
                DeliveryNoteLine.id == SalesInvoiceLine.source_document_line_id,
            ),
        )
        .join(SalesOrderLine, SalesOrderLine.id == order_line_id)
        .where(*in_period, SalesOrderLine.sales_order_id.in_(funded))
        .order_by(SalesInvoice.invoice_date, SalesInvoice.invoice_number)
    ).all()
    if not billed:
        return []
    orders = {
        row.id: row
        for row in session.execute(
            select(
                SalesOrder.id,
                SalesOrder.order_number,
                SalesOrder.bill_discount_source,
                SalesOrder.freight_waived_amount,
            ).where(SalesOrder.id.in_(joined))
        ).all()
    }
    # What the offers took off each order line, and what the line is worth.
    took: dict[UUID, Decimal] = {}
    worth: dict[UUID, Decimal] = {}
    order_took: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    order_worth: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for line_id, order_id, source, discount, bill_share, gross in session.execute(
        select(
            SalesOrderLine.id,
            SalesOrderLine.sales_order_id,
            SalesOrderLine.discount_source,
            SalesOrderLine.discount_amount,
            SalesOrderLine.bill_discount_amount,
            SalesOrderLine.gross_amount,
        ).where(
            SalesOrderLine.sales_order_id.in_(joined),
            SalesOrderLine.is_deleted.is_(False),
        )
    ).all():
        order = orders.get(order_id)
        off = offer_took_off(
            discount_source=source,
            discount_amount=discount,
            bill_discount_amount=bill_share,
            bill_discount_source=(
                None if order is None else order.bill_discount_source
            ),
        )
        took[line_id] = off
        worth[line_id] = _dec(gross)
        order_took[order_id] += off
        order_worth[order_id] += _dec(gross)
    back = _came_back(session, firm_id=firm_id, in_period=in_period)
    # Per order and bill: the offers' discount billed, and the part returned.
    sums: dict[tuple[UUID, UUID], list[Decimal]] = {}
    bills: dict[UUID, tuple[str, date]] = {}
    for (
        bill_line_id,
        quantity,
        of,
        _gross,
        _discount,
        _bill_share,
        invoice_id,
        number,
        dated,
        note_line_id,
        shipped,
        ordered,
        order_line_id_,
        order_id,
    ) in billed:
        order = orders.get(order_id)
        if order is None or order_line_id_ not in took:
            continue
        share = _part(_dec(quantity), _dec(of))
        if note_line_id is not None:
            share *= _part(_dec(shipped), _dec(ordered))
        waived = _dec(order.freight_waived_amount)
        whole = order_worth[order_id]
        passed = took[order_line_id_] * share
        if waived > ZERO and whole > ZERO:
            passed += waived * worth[order_line_id_] * share / whole
        if order_took[order_id] + waived <= ZERO and whole > ZERO:
            # Nothing on the order's lines says what the offer took (a
            # benefit the lines do not carry): the bill's share by value.
            passed = worth[order_line_id_] * share
        returned = min(back.get(bill_line_id, ZERO), Decimal("1"))
        entry = sums.setdefault((order_id, invoice_id), [ZERO, ZERO])
        entry[0] += passed
        entry[1] += passed * returned
        bills[invoice_id] = (number, dated)
    found: list[PassedOn] = []
    redemptions = session.execute(
        select(
            PromotionRedemption.id,
            PromotionRedemption.promotion_id,
            PromotionRedemption.document_id,
            PromotionRedemption.benefit_amount,
        )
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .where(
            PromotionRedemption.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            PromotionRedemption.status == "CLAIMED",
            PromotionRedemption.document_type == "SALES_ORDER",
            PromotionRedemption.benefit_amount > 0,
            Promotion.principal_id == principal_id,
            PromotionRedemption.document_id.in_(joined),
        )
        .order_by(PromotionRedemption.id)
    ).all()
    by_order: dict[UUID, list[tuple[UUID, UUID, Decimal]]] = defaultdict(list)
    for redemption_id, promotion_id, order_id, benefit in redemptions:
        by_order[order_id].append((redemption_id, promotion_id, _dec(benefit)))
    for (order_id, invoice_id), (passed, returned) in sums.items():
        order = orders[order_id]
        whole = order_took[order_id] + _dec(order.freight_waived_amount)
        if whole <= ZERO:
            whole = order_worth[order_id]
        if whole <= ZERO:
            continue
        number, dated = bills[invoice_id]
        for redemption_id, promotion_id, benefit in by_order.get(order_id, []):
            found.append(
                PassedOn(
                    redemption_id=redemption_id,
                    promotion_id=promotion_id,
                    invoice_id=invoice_id,
                    invoice_number=number,
                    invoice_date=dated,
                    order_number=order.order_number,
                    billed=benefit * min(passed / whole, Decimal("1")),
                    came_back=benefit * min(returned / whole, Decimal("1")),
                )
            )
    found.sort(key=lambda row: (row.invoice_date, row.invoice_number))
    return found


def _part(part: Decimal, whole: Decimal) -> Decimal:
    """Return ``part`` of ``whole`` as a share between nothing and all of it."""
    if part <= ZERO or whole <= ZERO:
        return ZERO
    return min(part / whole, Decimal("1"))


def _came_back(
    session: Session, *, firm_id: UUID, in_period: tuple[ColumnElement[bool], ...]
) -> dict[UUID, Decimal]:
    """Return the share of each of the period's bill lines that came back.

    Three routes, summed: a completed return of the bill line, a completed
    return of the note line it billed (the billed part of it, spread over
    that note line's bills by what each billed), and an approved credit note
    against the bill line, by value. Grouped in SQL over the period's bills.
    """
    share: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    done = (
        SalesReturn.firm_id == firm_id,
        SalesReturn.is_deleted.is_(False),
        SalesReturn.status.in_(_RETURNED),
        SalesReturnLine.is_deleted.is_(False),
    )
    for bill_line_id, billed, units in session.execute(
        select(
            SalesInvoiceLine.id,
            SalesInvoiceLine.current_invoice_quantity,
            func.sum(SalesReturnLine.current_return_quantity),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .join(
            SalesReturnLine,
            and_(
                SalesReturnLine.source_document_type == "SALES_INVOICE",
                SalesReturnLine.source_document_line_id == SalesInvoiceLine.id,
            ),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(*in_period, *done)
        .group_by(SalesInvoiceLine.id, SalesInvoiceLine.current_invoice_quantity)
    ).all():
        share[bill_line_id] += _part(_dec(units), _dec(billed))
    # A return off the note: only the part of it that had been billed took
    # any discount back, and each bill of that note line gave it in the
    # proportion it billed.
    for bill_line_id, shipped, units in session.execute(
        select(
            SalesInvoiceLine.id,
            SalesInvoiceLine.delivered_quantity,
            func.sum(
                SalesReturnLine.current_return_quantity
                - func.coalesce(SalesReturnLine.unbilled_quantity, 0)
            ),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .join(
            SalesReturnLine,
            and_(
                SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                SalesReturnLine.source_document_line_id
                == SalesInvoiceLine.source_document_line_id,
            ),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(*in_period, *done)
        .group_by(SalesInvoiceLine.id, SalesInvoiceLine.delivered_quantity)
    ).all():
        share[bill_line_id] += _part(_dec(units), _dec(shipped))
    for bill_line_id, gross, discount, bill_share, credited in session.execute(
        select(
            SalesInvoiceLine.id,
            SalesInvoiceLine.gross_amount,
            SalesInvoiceLine.discount_amount,
            SalesInvoiceLine.bill_discount_amount,
            func.sum(CreditNoteLine.taxable_amount),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .join(
            CreditNoteLine,
            CreditNoteLine.sales_invoice_line_id == SalesInvoiceLine.id,
        )
        .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
        .where(
            *in_period,
            CreditNote.firm_id == firm_id,
            CreditNote.is_deleted.is_(False),
            CreditNote.status == "APPROVED",
            CreditNoteLine.is_deleted.is_(False),
        )
        .group_by(
            SalesInvoiceLine.id,
            SalesInvoiceLine.gross_amount,
            SalesInvoiceLine.discount_amount,
            SalesInvoiceLine.bill_discount_amount,
        )
    ).all():
        charged = _dec(gross) - _dec(discount) - _dec(bill_share)
        share[bill_line_id] += _part(_dec(credited), charged)
    return dict(share)
