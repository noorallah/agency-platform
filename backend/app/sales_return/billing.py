"""What a sales return credits, and what it leaves to bill (D-SELL-55).

Goods can come back against a delivery note before any bill has charged for
them -- the note was never billed, or its bill was cancelled. Nothing was
charged, so nothing is credited: such goods move stock and cost only, reverse
no output tax, and lower what the note may still be billed for. The selling
twin of ``app/goods_receipt/billing.py`` (D-BUY-26).

The split is decided when the return completes and stored on the return line
(``unbilled_quantity``): returned goods are taken first from the part of the
note line no approved bill has reached, and only the rest is a credit note.
Everything that asks "what did this return credit" -- the journal, the
customer's account, GSTR-1, the GST sales register, the sales analysis --
reads it from here, so they cannot disagree.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.credit_note.models import CreditNote, CreditNoteLine, CreditNoteStatus
from app.delivery_note.models import DeliveryNoteLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import SalesReturn, SalesReturnLine, SalesReturnLineTax

ZERO = Decimal("0")
_FOUR = Decimal("0.0001")

#: A return in one of these has brought its goods back and split them.
_COMPLETED = ("COMPLETED", "CLOSED")
#: A bill in one of these has charged the customer.
_CHARGED = ("APPROVED", "CLOSED")
#: A return in one of these still claims the goods it names: everything but
#: a cancelled one.
_LIVE = ("DRAFT", "APPROVED", "COMPLETED", "CLOSED")


def billed_share(line: SalesReturnLine) -> Decimal:
    """Return the part of a line that reverses a bill, as a fraction of it.

    What came back before billing (``unbilled_quantity``) was never charged,
    so it credits nothing and reverses no tax.
    """
    quantity = Decimal(str(line.current_return_quantity))
    if quantity <= ZERO:
        return Decimal("1")
    unbilled = min(Decimal(str(line.unbilled_quantity or ZERO)), quantity)
    return (quantity - unbilled) / quantity


def billed_part(
    amount: ColumnElement[Any] | InstrumentedAttribute[Any],
) -> ColumnElement[Any]:
    """Return the billed share of a return line's figure, for a query.

    The SQL form of :func:`billed_share`, for reports that group in the
    database: the figure, scaled by how much of the line reversed a bill.
    """
    quantity = SalesReturnLine.current_return_quantity
    unbilled = SalesReturnLine.unbilled_quantity
    return case(
        # Left exactly as stored where nothing came back before billing --
        # every line but the rare one -- so no division touches it.
        (unbilled <= 0, amount),
        (quantity > 0, amount * (quantity - unbilled) / quantity),
        else_=amount,
    )


def credits_a_bill() -> ColumnElement[bool]:
    """Match the returns that credited something: not wholly before billing.

    A return whose every line came back before billing is no credit note, so
    GSTR-1 and the GST sales register leave it out.
    """
    return SalesReturn.id.in_(
        select(SalesReturnLine.sales_return_id).where(
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLine.current_return_quantity > SalesReturnLine.unbilled_quantity,
        )
    )


def unbilled_taxable() -> ScalarSelect[Any]:
    """Return, per return in the outer query, the pre-tax value never billed.

    A correlated subquery over ``SalesReturn``: what its lines are worth
    before tax, for the part that came back before billing.
    """
    quantity = SalesReturnLine.current_return_quantity
    return (
        select(
            func.coalesce(
                func.sum(
                    (SalesReturnLine.net_amount - SalesReturnLine.tax_amount)
                    * SalesReturnLine.unbilled_quantity
                    / quantity
                ),
                0,
            )
        )
        .where(
            SalesReturnLine.sales_return_id == SalesReturn.id,
            SalesReturnLine.is_deleted.is_(False),
            quantity > 0,
        )
        .correlate(SalesReturn)
        .scalar_subquery()
    )


def unbilled_quantities(
    session: Session, return_ids: Iterable[UUID]
) -> dict[UUID, Decimal]:
    """Return how much of each return came back before billing, in all."""
    ids = list(set(return_ids))
    if not ids:
        return {}
    return {
        return_id: Decimal(str(quantity))
        for return_id, quantity in session.execute(
            select(
                SalesReturnLine.sales_return_id,
                func.coalesce(func.sum(SalesReturnLine.unbilled_quantity), 0),
            )
            .where(
                SalesReturnLine.sales_return_id.in_(ids),
                SalesReturnLine.is_deleted.is_(False),
            )
            .group_by(SalesReturnLine.sales_return_id)
        ).all()
    }


def return_billed_amounts(
    session: Session, rows: Sequence[SalesReturn]
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return what each return takes off the customer's account, and its tax.

    The credit-note part only: the document total and its tax, less the value
    of what came back before any bill charged for it. A return wholly against
    unbilled goods credits nothing -- its rounding and charges included. The
    journal and the customer's account both read this, so they cannot drift.
    """
    if not rows:
        return {}
    parts: dict[UUID, list[SalesReturnLine]] = defaultdict(list)
    for line in session.scalars(
        select(SalesReturnLine).where(
            SalesReturnLine.sales_return_id.in_([row.id for row in rows]),
            SalesReturnLine.is_deleted.is_(False),
        )
    ).all():
        parts[line.sales_return_id].append(line)
    amounts: dict[UUID, tuple[Decimal, Decimal]] = {}
    for row in rows:
        total = Decimal(str(row.grand_total))
        tax_total = Decimal(str(row.tax_total))
        lines = parts.get(row.id, [])
        if lines and all(billed_share(line) == ZERO for line in lines):
            amounts[row.id] = (ZERO, ZERO)
            continue
        for line in lines:
            unbilled = Decimal("1") - billed_share(line)
            if unbilled == ZERO:
                continue
            total -= (Decimal(str(line.net_amount)) * unbilled).quantize(_FOUR)
            tax_total -= (Decimal(str(line.tax_amount)) * unbilled).quantize(_FOUR)
        amounts[row.id] = (max(total, ZERO), max(tax_total, ZERO))
    return amounts


def billed_tax_by_component(session: Session, return_id: UUID) -> dict[str, Decimal]:
    """Sum the tax a return reverses per component code, billed part only.

    Tax inside a price is left out, as the return's own tax total leaves it
    out. Empty when the lines recorded no components.
    """
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for line, component in session.execute(
        select(SalesReturnLine, SalesReturnLineTax)
        .join(
            SalesReturnLineTax,
            SalesReturnLineTax.sales_return_line_id == SalesReturnLine.id,
        )
        .where(
            SalesReturnLine.sales_return_id == return_id,
            SalesReturnLine.is_deleted.is_(False),
            SalesReturnLineTax.is_deleted.is_(False),
            SalesReturnLineTax.included_in_price.is_(False),
        )
    ).all():
        share = billed_share(line)
        if share == ZERO:
            continue
        totals[component.component_code] += Decimal(str(component.amount)) * share
    return dict(totals)


@dataclass(frozen=True, slots=True)
class NoteLineBilling:
    """Where one delivery note line stands against billing."""

    delivered: Decimal
    #: What bills that charged the customer (approved or closed) took.
    charged: Decimal
    #: What completed returns took off the line before any bill reached it.
    returned_unbilled: Decimal

    @property
    def left_to_bill(self) -> Decimal:
        """Return what a bill may still charge for on this line."""
        return max(self.delivered - self.charged - self.returned_unbilled, ZERO)


def returned_unbilled(
    session: Session,
    note_line_ids: Iterable[UUID],
    *,
    exclude_return_id: UUID | None = None,
) -> dict[UUID, Decimal]:
    """Return what came back before billing, per delivery note line.

    Only completed returns count: the split is written at completion and
    cleared when a completed return is cancelled.
    """
    ids = list(set(note_line_ids))
    if not ids:
        return {}
    statement = (
        select(
            SalesReturnLine.source_document_line_id,
            func.coalesce(func.sum(SalesReturnLine.unbilled_quantity), 0),
        )
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(
            SalesReturnLine.source_document_type == "DELIVERY_NOTE",
            SalesReturnLine.source_document_line_id.in_(ids),
            SalesReturnLine.is_deleted.is_(False),
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(_COMPLETED),
        )
        .group_by(SalesReturnLine.source_document_line_id)
    )
    if exclude_return_id is not None:
        statement = statement.where(SalesReturn.id != exclude_return_id)
    return {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(statement).all()
        if Decimal(str(quantity)) > ZERO
    }


def note_line_billing(
    session: Session,
    note_line_ids: Iterable[UUID],
    *,
    exclude_return_id: UUID | None = None,
    exclude_invoice_id: UUID | None = None,
) -> dict[UUID, NoteLineBilling]:
    """Return where each of these delivery note lines stands against billing.

    Judged on bills that **charged** the customer. A draft bill has charged
    nothing, so goods returned while one is waiting are returned before
    billing, and the draft is then refused at approval for what came back.
    """
    ids = list(set(note_line_ids))
    if not ids:
        return {}
    delivered = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(
            select(
                DeliveryNoteLine.id, DeliveryNoteLine.current_delivery_quantity
            ).where(DeliveryNoteLine.id.in_(ids))
        ).all()
    }
    bills = (
        select(
            SalesInvoiceLine.source_document_line_id,
            func.coalesce(func.sum(SalesInvoiceLine.current_invoice_quantity), 0),
        )
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .where(
            SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
            SalesInvoiceLine.source_document_line_id.in_(ids),
            SalesInvoiceLine.is_deleted.is_(False),
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(_CHARGED),
        )
        .group_by(SalesInvoiceLine.source_document_line_id)
    )
    if exclude_invoice_id is not None:
        bills = bills.where(SalesInvoice.id != exclude_invoice_id)
    charged = {
        line_id: Decimal(str(quantity))
        for line_id, quantity in session.execute(bills).all()
    }
    back = returned_unbilled(session, ids, exclude_return_id=exclude_return_id)
    return {
        line_id: NoteLineBilling(
            delivered=quantity,
            charged=charged.get(line_id, ZERO),
            returned_unbilled=back.get(line_id, ZERO),
        )
        for line_id, quantity in delivered.items()
    }


# ---- what a bill line is still worth (D-SELL-88) ----------------------------
#
# A sales return and a credit note both credit a bill line, and neither read
# the other: a bill of 2,832.00 took a rate-difference credit note of 472.00
# and was then returned in full for 2,832.00 -- 3,304.00 credited against a
# bill of 2,832.00. Both documents now read what has already come off the line
# from here, so a customer is never credited more than they were billed.


@dataclass(frozen=True, slots=True)
class BillLineCredits:
    """What has already come off one bill line, before tax."""

    #: Billed units that returns took, in the bill line's own unit.
    returned_quantity: Decimal
    #: What those returns credited, before tax.
    returned_taxable: Decimal
    #: What approved credit notes credited, before tax.
    credited_taxable: Decimal


def charging_bill_line(session: Session, note_line_id: UUID) -> SalesInvoiceLine | None:
    """Return the bill line that charged a delivery note line's goods.

    The live bill that charged the note's line, the earliest if it was billed
    in parts; a note nobody has billed has none. A return raised off the note
    reverses that line's tax, so that line is the one its credit is counted
    against.
    """
    return session.scalar(
        select(SalesInvoiceLine)
        .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        .where(
            SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
            SalesInvoiceLine.source_document_line_id == note_line_id,
            SalesInvoiceLine.is_deleted.is_(False),
            SalesInvoice.status.in_(_CHARGED),
            SalesInvoice.is_deleted.is_(False),
        )
        .order_by(SalesInvoice.invoice_date.asc(), SalesInvoice.invoice_number)
        .limit(1)
    )


def bill_line_credits(
    session: Session,
    charged: SalesInvoiceLine,
    *,
    completed_only: bool,
    exclude_return_id: UUID | None = None,
) -> BillLineCredits:
    """Return what returns and credit notes have already taken off a bill line.

    **Returns** by either route: raised on the bill line itself, or on the
    delivery note line it billed where this is the bill those returns reverse
    (``charging_bill_line``). Only the billed part of each counts; what came
    back before billing credited nothing. **Credit notes** once approved,
    which is when one posts.

    Args:
        session: The firm's session.
        charged: The bill line being asked about.
        completed_only: Count only returns that have credited the customer
            (completed or closed), which is what a credit note's cap wants.
            A return being priced asks for every live one instead, drafts
            included, so two returns of one line cannot both take the same
            remaining worth.
        exclude_return_id: A return being priced or completed, whose own
            lines are not "already".

    Returns:
        The quantity and value returned, and the value credited by notes.

    """
    routes = [
        and_(
            SalesReturnLine.source_document_type == "SALES_INVOICE",
            SalesReturnLine.source_document_line_id == charged.id,
        )
    ]
    if charged.source_document_type == "DELIVERY_NOTE":
        first = charging_bill_line(session, charged.source_document_line_id)
        if first is not None and first.id == charged.id:
            routes.append(
                and_(
                    SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                    SalesReturnLine.source_document_line_id
                    == charged.source_document_line_id,
                )
            )
    statement = (
        select(SalesReturnLine)
        .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
        .where(
            SalesReturnLine.firm_id == charged.firm_id,
            SalesReturnLine.is_deleted.is_(False),
            SalesReturn.is_deleted.is_(False),
            SalesReturn.status.in_(_COMPLETED if completed_only else _LIVE),
            or_(*routes),
        )
    )
    if exclude_return_id is not None:
        statement = statement.where(SalesReturn.id != exclude_return_id)
    quantity = ZERO
    taxable = ZERO
    for line in session.scalars(statement).all():
        share = billed_share(line)
        quantity += Decimal(str(line.current_return_quantity)) * share
        taxable += (
            Decimal(str(line.net_amount)) - Decimal(str(line.tax_amount))
        ) * share
    credited = session.scalar(
        select(func.coalesce(func.sum(CreditNoteLine.taxable_amount), 0))
        .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
        .where(
            CreditNoteLine.firm_id == charged.firm_id,
            CreditNoteLine.sales_invoice_line_id == charged.id,
            CreditNoteLine.is_deleted.is_(False),
            CreditNote.is_deleted.is_(False),
            CreditNote.status == CreditNoteStatus.APPROVED.value,
        )
    )
    return BillLineCredits(
        returned_quantity=quantity.quantize(_FOUR),
        returned_taxable=taxable.quantize(_FOUR),
        credited_taxable=Decimal(str(credited or 0)).quantize(_FOUR),
    )


def goods_charged(charged: SalesInvoiceLine) -> Decimal:
    """Return what a bill line charged for its goods, before tax.

    Gross, less both discounts, plus the line's own charges -- without its
    share of the delivery charge, which is not goods and does not come back
    with them.
    """
    return (
        Decimal(str(charged.gross_amount))
        - Decimal(str(charged.discount_amount))
        - Decimal(str(charged.bill_discount_amount))
        + Decimal(str(charged.charges_amount))
    ).quantize(_FOUR)


def still_worth(
    charged: SalesInvoiceLine,
    credits: BillLineCredits,
    *,
    quantity: Decimal,
    taken_quantity: Decimal = ZERO,
    taken_taxable: Decimal = ZERO,
) -> Decimal:
    """Return what some units of a bill line are still worth, before tax.

    What the line charged for its goods, less what credit notes and earlier
    returns have taken off it, spread over the units still out: 2 boxes
    charged 2,400.00 and credited 400.00 are worth 1,000.00 each, and once
    one has come back the other is worth all of what is left. So the returns
    of a line and its credit notes add up to what it charged and no more,
    whichever came first.

    Args:
        charged: The bill line.
        credits: What has already come off it.
        quantity: The units coming back, in the bill line's unit.
        taken_quantity: Units earlier lines of the same return bring back.
        taken_taxable: What those earlier lines credit.

    Returns:
        The most these units may credit, never below nothing.

    """
    left = (
        goods_charged(charged)
        - credits.credited_taxable
        - credits.returned_taxable
        - taken_taxable
    )
    units = (
        Decimal(str(charged.current_invoice_quantity))
        - credits.returned_quantity
        - taken_quantity
    )
    if left <= ZERO or units <= ZERO or quantity <= ZERO:
        return ZERO
    return (left * quantity / units).quantize(_FOUR)
