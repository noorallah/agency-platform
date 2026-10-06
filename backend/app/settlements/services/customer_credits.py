"""Customer credit: what a sales return or a credit note left on the customer.

A completed sales return and an approved credit note post Cr receivable and
come off the bill they name (``credited_against``). Where that bill was
already paid there is nothing left on it to come off: the customer's account
shows money held, and it belonged to no receipt, so ``allocate`` -- which
spends one receipt's unapplied money -- could never set it against a later
bill. The customer owed 826.00 on one line and was owed 826.00 on another
until somebody paid it out and took it back (D-PRC-75, PRCQ-74).

It is now a customer credit -- the receivable twin of
``supplier_credits``. What a source has to give is derived, never stored:
what its own bills could not absorb, less the live
``CustomerCreditApplication`` rows that set it against another bill or name
the refund that paid it back. A bill that cannot absorb everything taken off
it turns the newest return or credit note into credit first: the earlier
ones fitted when they were made.

**Applying posts no journal.** The return already credited receivables and
the bill already debited them; one customer, one control account. What moves
is the customer's own two figures, and only by the part the credit was
actually holding as an advance: a credit note is applied up to what the
customer owes when it posts and only the rest becomes an advance, and the
receivable row it wrote remembers the split. The part that already came off
the balance needs no movement -- applying it only says which bill it
cleared -- and the part held as an advance posts one ``ADVANCE_APPLY`` row
named after the application, so taking the application back returns exactly
what it moved.

**A refund draws on the credit too.** Money handed back out of what a return
left is that return's credit gone, so a refund names its source or takes the
oldest credit held on account first, and a credit that was paid back cannot
be applied as well.

Should the source's own bill owe more again once its credit is used -- the
receipt that paid it reversed -- the part used goes back on that bill
(``drawn_back_onto_bills``), as it does for a supplier.

**An advance its source no longer gives goes back on the source's own bill.**
A credit held as an advance is only credit while its bill stays settled past
its total. When the bill owes again, the part still on the customer's account
is no longer money held for them: it is part of what the bill does not owe.
``absorb_credit_no_longer_given`` takes it off both of the customer's
figures -- one ``ADVANCE_APPLY`` row referenced ``customer_credit_absorbed``
to the source -- whenever a receipt, a refund or an application is reversed,
so the account goes on agreeing with the bills in whichever order those
happen (D-PRC-88). Cancelling the source undoes those rows first, as it
withdraws its applications.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_day_after, firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.chunks import chunks, whole_past_a_chunk
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.customers.models import (
    Customer,
    CustomerOpeningBill,
    CustomerReceivableTransaction,
)
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.settlements.models import CustomerCreditApplication

#: The return states whose posting stands: completing credits the customer,
#: a cancelled return has taken that back, and a draft has not posted.
CREDITING_RETURN_STATES = ("COMPLETED", "CLOSED")

SALES_RETURN = "SALES_RETURN"
CREDIT_NOTE = "CREDIT_NOTE"
SALES_INVOICE = "SALES_INVOICE"
OPENING_BILL = "CUSTOMER_OPENING_BILL"
REFUND = "REFUND"
POSTED = "POSTED"
REVERSED = "REVERSED"

#: What the receivable row an application writes is referenced as.
REFERENCE_TYPE = "customer_credit_application"
#: What the receivable row is referenced as that takes a source's advance
#: back onto its own bill; its ``reference_id`` is the source.
ABSORBED = "customer_credit_absorbed"


@dataclass(frozen=True)
class _Source:
    """A document that can give customer credit."""

    kind: str
    id: UUID
    number: str
    on: date
    customer_id: UUID


@dataclass(frozen=True)
class _Part:
    """What one source took off one bill."""

    on: date
    number: str
    source_id: UUID
    bill_id: UUID
    amount: Decimal


@dataclass
class CustomerCreditUse:
    """One live row saying where part of a credit went."""

    id: UUID
    target_type: str
    target_id: UUID
    target_number: str
    amount: Decimal
    applied_on: date
    version: int


@dataclass
class CustomerCredit:
    """One source's credit on the customer's account, and what is left of it."""

    source_type: str
    source_id: UUID
    source_number: str
    source_date: date
    customer_id: UUID
    #: What the source's own bills could not absorb.
    credit_amount: Decimal
    applied_amount: Decimal = ZERO
    refunded_amount: Decimal = ZERO
    #: How much of it became an advance when the source posted, and how much
    #: of that its applications and refunds have since moved.
    advance_given: Decimal = ZERO
    advance_used: Decimal = ZERO
    #: How much of that advance went back on the source's own bill, because
    #: the bill came to owe again (``absorb_credit_no_longer_given``).
    advance_absorbed: Decimal = ZERO
    uses: list[CustomerCreditUse] = field(default_factory=list)

    @property
    def applied_to(self) -> list[str]:
        """Return the bills it has been set against, oldest application first."""
        return [use.target_number for use in self.uses if use.target_type != REFUND]

    @property
    def available_amount(self) -> Decimal:
        """Return what can still be set against a bill or paid back."""
        return max(
            self.credit_amount - self.applied_amount - self.refunded_amount, ZERO
        )

    @property
    def held_amount(self) -> Decimal:
        """Return the part of what is left that is held as an advance.

        The rest already came off what the customer owes, when the source
        posted, and can only be set against a bill.
        """
        return max(min(self.advance_on_account, self.available_amount), ZERO)

    @property
    def advance_on_account(self) -> Decimal:
        """Return what its posting put on the account that nothing has moved.

        More than ``held_amount`` once the source gives less credit than it
        did: the difference is no longer the customer's to hold.
        """
        return max(self.advance_given - self.advance_used - self.advance_absorbed, ZERO)


def _live() -> tuple[Any, ...]:
    """Match the application rows that stand."""
    return (
        CustomerCreditApplication.is_deleted.is_(False),
        CustomerCreditApplication.status == POSTED,
    )


def _standing_absorptions() -> tuple[Any, ...]:
    """Match the receivable rows that took an advance back onto its bill.

    The ones that stand: cancelling the source reverses them, and a reversed
    row has a ``reversal`` row naming it.
    """
    undone = aliased(CustomerReceivableTransaction)
    return (
        CustomerReceivableTransaction.reference_type == ABSORBED,
        CustomerReceivableTransaction.transaction_type
        == CustomerReceivableTransactionType.ADVANCE_APPLY.value,
        CustomerReceivableTransaction.is_deleted.is_(False),
        ~select(undone.id)
        .where(
            undone.reference_type == "reversal",
            undone.reference_id == CustomerReceivableTransaction.id,
            undone.is_deleted.is_(False),
        )
        .exists(),
    )


# ---------------------------------------------------------------------------
# What a bill has had set against it
# ---------------------------------------------------------------------------


@whole_past_a_chunk("bill_ids")
def credit_applied_to_bills(
    session: Session,
    *,
    firm_id: UUID,
    bill_ids: Sequence[UUID] | None,
    target_type: str = SALES_INVOICE,
    as_of: date | None = None,
) -> dict[UUID, Decimal]:
    """Sum the customer credit set against each bill.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        bill_ids: The bills to ask about; None asks about every bill of the
            firm in one grouped read.
        target_type: ``SALES_INVOICE``, or ``CUSTOMER_OPENING_BILL`` to read
            the ids as opening bills.
        as_of: Count only what stood at the end of this day: applied on or
            before it, and not taken back until after it.

    Returns:
        The amount per bill, for those with any.

    """
    if bill_ids is not None and not bill_ids:
        return {}
    statement = select(
        CustomerCreditApplication.target_id,
        func.coalesce(func.sum(CustomerCreditApplication.amount), 0),
    ).where(
        CustomerCreditApplication.firm_id == firm_id,
        CustomerCreditApplication.target_type == target_type,
        CustomerCreditApplication.is_deleted.is_(False),
    )
    if bill_ids is not None:
        statement = statement.where(CustomerCreditApplication.target_id.in_(bill_ids))
    if as_of is None:
        statement = statement.where(CustomerCreditApplication.status == POSTED)
    else:
        statement = statement.where(
            CustomerCreditApplication.applied_on <= as_of,
            or_(
                CustomerCreditApplication.status == POSTED,
                and_(
                    CustomerCreditApplication.status == REVERSED,
                    CustomerCreditApplication.reversed_at
                    >= firm_day_after(session, firm_id, as_of),
                ),
            ),
        )
    return {
        bill_id: quantize_ledger(Decimal(str(total)))
        for bill_id, total in session.execute(
            statement.group_by(CustomerCreditApplication.target_id)
        ).all()
    }


def credit_numbers_against(
    session: Session, *, firm_id: UUID, bill_id: UUID
) -> list[str]:
    """Name the returns and credit notes whose credit is set against a bill.

    What stops the bill being cancelled: the credit would be left clearing a
    debt that no longer exists, as a receipt would.
    """
    sources = list(
        session.scalars(
            select(CustomerCreditApplication.source_id)
            .where(
                CustomerCreditApplication.firm_id == firm_id,
                CustomerCreditApplication.target_id == bill_id,
                CustomerCreditApplication.target_type.in_(
                    (SALES_INVOICE, OPENING_BILL)
                ),
                *_live(),
            )
            .distinct()
        ).all()
    )
    return sorted(
        source.number for source in _sources(session, firm_id, sources).values()
    )


# ---------------------------------------------------------------------------
# What a source has to give
# ---------------------------------------------------------------------------


def _sources(
    session: Session,
    firm_id: UUID,
    source_ids: Sequence[UUID] | None,
    *,
    customer_id: UUID | None = None,
    standing_only: bool = False,
) -> dict[UUID, _Source]:
    """Read returns and credit notes as sources, by id."""
    # Imported here: both modules import settlement-adjacent models.
    from app.credit_note.models import CreditNote, CreditNoteStatus
    from app.sales_return.models import SalesReturn

    returns = select(
        SalesReturn.id,
        SalesReturn.return_number,
        SalesReturn.return_date,
        SalesReturn.customer_id,
    ).where(SalesReturn.firm_id == firm_id, SalesReturn.is_deleted.is_(False))
    notes = select(
        CreditNote.id,
        CreditNote.credit_note_number,
        CreditNote.credit_note_date,
        CreditNote.customer_id,
    ).where(CreditNote.firm_id == firm_id, CreditNote.is_deleted.is_(False))
    if standing_only:
        returns = returns.where(SalesReturn.status.in_(CREDITING_RETURN_STATES))
        notes = notes.where(CreditNote.status == CreditNoteStatus.APPROVED.value)
    if customer_id is not None:
        returns = returns.where(SalesReturn.customer_id == customer_id)
        notes = notes.where(CreditNote.customer_id == customer_id)
    found: dict[UUID, _Source] = {}
    groups: list[list[UUID] | None] = (
        [None] if source_ids is None else list(chunks(list(source_ids)))
    )
    for group in groups:
        for kind, statement, column in (
            (SALES_RETURN, returns, SalesReturn.id),
            (CREDIT_NOTE, notes, CreditNote.id),
        ):
            narrowed = (
                statement if group is None else statement.where(column.in_(group))
            )
            for row in session.execute(narrowed).all():
                found[row[0]] = _Source(
                    kind=kind,
                    id=row[0],
                    number=row[1],
                    on=row[2],
                    customer_id=row[3],
                )
    return found


def _bills_of(
    session: Session, firm_id: UUID, source_ids: Sequence[UUID]
) -> list[UUID]:
    """Return the bills these returns and credit notes took something off."""
    from app.credit_note.models import CreditNote
    from app.sales_return.models import SalesReturnBillPlacement, SalesReturnLine

    bills: set[UUID] = set()
    for group in chunks(list(source_ids)):
        bills.update(
            session.scalars(
                select(SalesReturnLine.source_document_id)
                .where(
                    SalesReturnLine.sales_return_id.in_(group),
                    SalesReturnLine.source_document_type == "SALES_INVOICE",
                    SalesReturnLine.is_deleted.is_(False),
                )
                .distinct()
            ).all()
        )
        bills.update(
            session.scalars(
                select(SalesReturnBillPlacement.sales_invoice_id)
                .where(
                    SalesReturnBillPlacement.sales_return_id.in_(group),
                    SalesReturnBillPlacement.is_deleted.is_(False),
                )
                .distinct()
            ).all()
        )
        # A return off a note completed before placements were kept: any
        # bill of the note lines it names may have charged its units.
        bills.update(
            session.scalars(
                select(SalesInvoiceLine.sales_invoice_id)
                .where(
                    SalesInvoiceLine.source_document_type == "DELIVERY_NOTE",
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoiceLine.source_document_line_id.in_(
                        select(SalesReturnLine.source_document_line_id).where(
                            SalesReturnLine.sales_return_id.in_(group),
                            SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                            SalesReturnLine.is_deleted.is_(False),
                            SalesReturnLine.current_return_quantity
                            > SalesReturnLine.unbilled_quantity,
                        )
                    ),
                )
                .distinct()
            ).all()
        )
        bills.update(
            session.scalars(
                select(CreditNote.sales_invoice_id)
                .where(CreditNote.id.in_(group), CreditNote.firm_id == firm_id)
                .distinct()
            ).all()
        )
    return sorted((bill for bill in bills if bill is not None), key=str)


def _bill_parts(
    session: Session, firm_id: UUID, bill_ids: Sequence[UUID]
) -> list[_Part]:
    """Return what every standing return and credit note took off these bills.

    Newest document first, returns and credit notes together: the order in
    which a bill that cannot absorb them all turns them into credit. The same
    reads ``credited_against`` sums -- a return's own lines on the bill, its
    units placed on the bill from a delivery note, its header figures, and
    the credit notes against the bill -- kept apart by source.
    """
    from app.credit_note.models import CreditNote, CreditNoteStatus
    from app.sales_return.billing import (
        header_credit_parts,
        returns_off_notes_against,
    )
    from app.sales_return.models import SalesReturn, SalesReturnLine
    from app.settlements.services.settlement_service import _returns_off_bills

    amounts: dict[tuple[UUID, UUID], Decimal] = {}
    named: dict[UUID, tuple[date, str]] = {}

    def add(source_id: UUID, bill_id: UUID, amount: object) -> None:
        """Count one figure, rounded to the ledger as the bill counts it."""
        key = (source_id, bill_id)
        amounts[key] = amounts.get(key, ZERO) + quantize_ledger(
            Decimal(str(amount or 0))
        )

    for group in chunks(list(bill_ids)):
        for return_id, bill_id, total in session.execute(
            select(
                SalesReturnLine.sales_return_id,
                SalesReturnLine.source_document_id,
                func.coalesce(func.sum(SalesReturnLine.net_amount), 0),
            )
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(*_returns_off_bills(firm_id, group, None))
            .group_by(
                SalesReturnLine.sales_return_id, SalesReturnLine.source_document_id
            )
        ).all():
            add(return_id, bill_id, total)
        shares = returns_off_notes_against(session, firm_id=firm_id, invoice_ids=group)
        off_notes: dict[tuple[UUID, UUID], Decimal] = {}
        for share in shares:
            if share.return_id is None:
                continue
            key = (share.return_id, share.invoice_id)
            off_notes[key] = off_notes.get(key, ZERO) + share.net
        for (return_id, bill_id), total in off_notes.items():
            add(return_id, bill_id, total)
        for return_id, by_bill in header_credit_parts(
            session,
            firm_id=firm_id,
            invoice_ids=group,
            worked_out=[share for share in shares if not share.placed],
        ).items():
            for bill_id, total in by_bill.items():
                add(return_id, bill_id, total)
        for note_id, bill_id, total, on, number in session.execute(
            select(
                CreditNote.id,
                CreditNote.sales_invoice_id,
                CreditNote.total_amount,
                CreditNote.credit_note_date,
                CreditNote.credit_note_number,
            ).where(
                CreditNote.firm_id == firm_id,
                CreditNote.sales_invoice_id.in_(group),
                CreditNote.status == CreditNoteStatus.APPROVED.value,
                CreditNote.is_deleted.is_(False),
            )
        ).all():
            add(note_id, bill_id, total)
            named[note_id] = (on, number)
    unnamed = sorted({source for source, _ in amounts} - set(named), key=str)
    for source in _sources(session, firm_id, unnamed).values():
        named[source.id] = (source.on, source.number)
    parts = [
        _Part(
            on=named[source_id][0],
            number=named[source_id][1],
            source_id=source_id,
            bill_id=bill_id,
            amount=amount,
        )
        for (source_id, bill_id), amount in amounts.items()
        if source_id in named and amount > ZERO
    ]
    parts.sort(key=lambda part: (part.on, part.number, str(part.bill_id)), reverse=True)
    return parts


def _over_settled(
    session: Session, firm_id: UUID, bill_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Return how far past its own total each bill has been settled.

    A bill owes its total less everything that came off it. Where more came
    off than it was worth -- it was paid, and then goods came back -- the
    excess is the customer's, and it is what the bill's returns and credit
    notes have to give.
    """
    from app.settlements.services.settlement_service import settled_against

    over: dict[UUID, Decimal] = {}
    for group in chunks(list(bill_ids)):
        # Without what was drawn back: that is worked out from this.
        settled = settled_against(
            session, firm_id=firm_id, invoice_ids=group, drawn_back=False
        )
        for bill_id, total in session.execute(
            select(SalesInvoice.id, SalesInvoice.grand_total).where(
                SalesInvoice.id.in_(group), SalesInvoice.firm_id == firm_id
            )
        ).all():
            excess = settled.get(bill_id, ZERO) - quantize_ledger(Decimal(str(total)))
            if excess > ZERO:
                over[bill_id] = excess
    return over


def _target_numbers(
    session: Session, rows: Sequence[CustomerCreditApplication]
) -> dict[UUID, str]:
    """Name the bills and refunds a page of rows points at, one read each."""
    from app.customers.services.opening_bill_service import opening_bill_label
    from app.settlements.models import Settlement

    by_type: dict[str, set[UUID]] = {}
    for row in rows:
        by_type.setdefault(row.target_type, set()).add(row.target_id)
    names: dict[UUID, str] = {}
    for group in chunks(sorted(by_type.get(SALES_INVOICE, ()), key=str)):
        for bill_id, number in session.execute(
            select(SalesInvoice.id, SalesInvoice.invoice_number).where(
                SalesInvoice.id.in_(group)
            )
        ).all():
            names[bill_id] = number
    for group in chunks(sorted(by_type.get(OPENING_BILL, ()), key=str)):
        for bill in session.scalars(
            select(CustomerOpeningBill).where(CustomerOpeningBill.id.in_(group))
        ).all():
            names[bill.id] = opening_bill_label(bill)
    for group in chunks(sorted(by_type.get(REFUND, ()), key=str)):
        for refund_id, number in session.execute(
            select(Settlement.id, Settlement.settlement_number).where(
                Settlement.id.in_(group)
            )
        ).all():
            names[refund_id] = number
    return names


def _work(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID | None = None,
    source_ids: Sequence[UUID] | None = None,
) -> tuple[list[CustomerCredit], list[_Part]]:
    """Work out every standing source's credit, and the parts behind it.

    Returns:
        One entry per completed return and approved credit note asked about,
        a credit of nothing too, oldest first; and what each took off each
        of the bills involved, newest first.

    """
    sources = _sources(
        session, firm_id, source_ids, customer_id=customer_id, standing_only=True
    )
    if not sources:
        return [], []
    ids = sorted(sources, key=str)
    bills = _bills_of(session, firm_id, ids)
    parts = _bill_parts(session, firm_id, bills) if bills else []
    left = _over_settled(session, firm_id, bills) if bills else {}
    spilled: dict[UUID, Decimal] = {}
    for part in parts:
        share = min(part.amount, left.get(part.bill_id, ZERO))
        if share <= ZERO:
            continue
        left[part.bill_id] -= share
        spilled[part.source_id] = spilled.get(part.source_id, ZERO) + share

    rows: list[CustomerCreditApplication] = []
    given: dict[UUID, Decimal] = {}
    absorbed: dict[UUID, Decimal] = {}
    for group in chunks(ids):
        rows.extend(
            session.scalars(
                select(CustomerCreditApplication)
                .where(
                    CustomerCreditApplication.firm_id == firm_id,
                    CustomerCreditApplication.source_id.in_(group),
                    *_live(),
                )
                .order_by(
                    CustomerCreditApplication.created_at.asc(),
                    CustomerCreditApplication.id.asc(),
                )
            ).all()
        )
        # How the source's own posting split between the balance and an
        # advance: only the row it wrote remembers.
        for source_id, advance in session.execute(
            select(
                CustomerReceivableTransaction.reference_id,
                func.coalesce(func.sum(CustomerReceivableTransaction.advance_delta), 0),
            )
            .where(
                CustomerReceivableTransaction.reference_type.in_(
                    (SALES_RETURN, CREDIT_NOTE)
                ),
                CustomerReceivableTransaction.reference_id.in_(group),
                CustomerReceivableTransaction.transaction_type
                == CustomerReceivableTransactionType.CREDIT_NOTE.value,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
            .group_by(CustomerReceivableTransaction.reference_id)
        ).all():
            given[source_id] = quantize_ledger(Decimal(str(advance)))
        for source_id, advance in session.execute(
            select(
                CustomerReceivableTransaction.reference_id,
                func.coalesce(func.sum(CustomerReceivableTransaction.advance_delta), 0),
            )
            .where(
                CustomerReceivableTransaction.reference_id.in_(group),
                *_standing_absorptions(),
            )
            .group_by(CustomerReceivableTransaction.reference_id)
        ).all():
            absorbed[source_id] = quantize_ledger(-Decimal(str(advance)))
    numbers = _target_numbers(session, rows)
    credits: dict[UUID, CustomerCredit] = {
        source.id: CustomerCredit(
            source_type=source.kind,
            source_id=source.id,
            source_number=source.number,
            source_date=source.on,
            customer_id=source.customer_id,
            credit_amount=spilled.get(source.id, ZERO),
            advance_given=given.get(source.id, ZERO),
            advance_absorbed=absorbed.get(source.id, ZERO),
        )
        for source in sources.values()
    }
    for row in rows:
        credit = credits[row.source_id]
        amount = quantize_ledger(Decimal(str(row.amount)))
        if row.target_type == REFUND:
            credit.refunded_amount += amount
        else:
            credit.applied_amount += amount
        credit.advance_used += quantize_ledger(Decimal(str(row.advance_amount)))
        credit.uses.append(
            CustomerCreditUse(
                id=row.id,
                target_type=row.target_type,
                target_id=row.target_id,
                target_number=numbers.get(row.target_id, ""),
                amount=amount,
                applied_on=row.applied_on,
                version=row.version,
            )
        )
    ordered = sorted(
        credits.values(), key=lambda item: (item.source_date, item.source_number)
    )
    return ordered, parts


def customer_credits(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
) -> list[CustomerCredit]:
    """Return each standing source's credit for one customer, oldest first.

    One entry per completed return and approved credit note that gives any
    credit or has had any used. Money already handed back with no source
    named -- a refund recorded before credits were tracked -- is taken off
    the credits it paid back (``_standing_credits``).

    Args:
        session: The firm's store.
        firm_id: The firm.
        customer_id: The customer.

    Returns:
        The credits, applied or not.

    """
    return [
        credit
        for credit in _standing_credits(
            session, firm_id=firm_id, customer_id=customer_id
        )
        if credit.credit_amount > ZERO or credit.uses
    ]


def _standing_credits(
    session: Session, *, firm_id: UUID, customer_id: UUID
) -> list[CustomerCredit]:
    """Return every standing source of one customer, a credit of nothing too.

    With the money handed back before credits were tracked taken off them: a
    refund that names no credit, by any row, paid back the credits held on
    account when it was made, oldest first (``_untracked_refunds``). And
    whatever the records then say, the customer cannot be holding more as
    credit than the account says they hold, so any excess is taken off the
    oldest credits too.

    The second rule alone used to carry both, and it only bites while the
    account holds nothing else: 500.00 received on account afterwards read
    as 500.00 of a credit paid back long ago being available again, and
    applying it spent the receipt's money (D-PRC-91).
    """
    credits, _ = _work(session, firm_id=firm_id, customer_id=customer_id)
    if not any(credit.advance_on_account > ZERO for credit in credits):
        return credits
    paid_back = _untracked_refunds(
        session, firm_id=firm_id, customer_id=customer_id, credits=credits
    )
    for credit in credits:
        taken = min(paid_back.get(credit.source_id, ZERO), credit.advance_on_account)
        if taken > ZERO:
            credit.refunded_amount += taken
            credit.advance_used += taken
    held = sum((credit.held_amount for credit in credits), ZERO)
    if held > ZERO:
        on_account = quantize_ledger(
            Decimal(
                str(
                    session.scalar(
                        select(Customer.unapplied_advance_balance).where(
                            Customer.id == customer_id
                        )
                    )
                    or 0
                )
            )
        )
        gone = held - on_account
        for credit in credits:
            if gone <= ZERO:
                break
            taken = min(gone, credit.held_amount)
            credit.refunded_amount += taken
            credit.advance_used += taken
            gone -= taken
    return credits


def _untracked_refunds(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    credits: Sequence[CustomerCredit],
) -> dict[UUID, Decimal]:
    """Return what refunds that name no credit paid back of each source.

    A refund draws on the credits held on account, oldest first, and says so
    in rows (``draw_refund_on_credits``). One recorded before those rows
    were kept says nothing, and what it paid back can only be told from when
    it happened: the customer's account moves are walked in the order they
    were made, keeping what each source's advance stood at, and a refund
    with no row takes what the credits were holding **at that moment**.
    Money that reached the account afterwards -- a receipt on account, most
    of all -- is not in it, so it cannot make a credit paid back look held
    again; and a refund made before a credit existed took none of it.

    Two statements, whatever the customer holds: their applications, and
    the account rows that move a credit's advance or hand money back.

    Returns:
        The amount per source, for those with any.

    """
    kinds = CustomerReceivableTransactionType
    account = CustomerReceivableTransaction
    applied: dict[UUID, UUID] = {}
    draws: dict[UUID, list[tuple[UUID, Decimal]]] = {}
    for row_id, source_id, target_type, target_id, advance in session.execute(
        select(
            CustomerCreditApplication.id,
            CustomerCreditApplication.source_id,
            CustomerCreditApplication.target_type,
            CustomerCreditApplication.target_id,
            CustomerCreditApplication.advance_amount,
        ).where(
            CustomerCreditApplication.firm_id == firm_id,
            CustomerCreditApplication.customer_id == customer_id,
            CustomerCreditApplication.is_deleted.is_(False),
        )
    ).all():
        applied[row_id] = source_id
        if target_type == REFUND:
            draws.setdefault(target_id, []).append(
                (source_id, quantize_ledger(Decimal(str(advance or 0))))
            )
    moves = session.execute(
        select(
            account.id,
            account.transaction_type,
            account.advance_delta,
            account.reference_type,
            account.reference_id,
            account.created_at,
        ).where(
            account.firm_id == firm_id,
            account.customer_id == customer_id,
            account.is_deleted.is_(False),
            or_(
                account.transaction_type.in_(
                    (kinds.REFUND.value, kinds.REVERSAL.value)
                ),
                account.reference_type.in_(
                    (SALES_RETURN, CREDIT_NOTE, REFERENCE_TYPE, ABSORBED)
                ),
            ),
        )
    ).all()
    # Rows of one request share an instant, and within one what puts money
    # on the account comes before what takes it off.
    ordered = sorted(
        moves, key=lambda move: (move[5], Decimal(str(move[2] or 0)) < ZERO)
    )
    oldest_first = [credit.source_id for credit in credits]
    holding: dict[UUID, Decimal] = {}
    paid_back: dict[UUID, Decimal] = {}
    #: What each row did, so its reversal undoes exactly that: the source,
    #: what it moved, and whether it was a refund naming nothing.
    did: dict[UUID, list[tuple[UUID, Decimal, bool]]] = {}
    for row_id, kind, delta, reference_type, reference_id, _at in ordered:
        moved = quantize_ledger(Decimal(str(delta or 0)))
        if kind == kinds.REVERSAL.value:
            for source_id, amount, unnamed in did.pop(reference_id, []):
                holding[source_id] = holding.get(source_id, ZERO) - amount
                if unnamed:
                    paid_back[source_id] = paid_back.get(source_id, ZERO) + amount
            continue
        effects: list[tuple[UUID, Decimal, bool]] = []
        if kind == kinds.REFUND.value:
            named = draws.get(reference_id) if reference_id is not None else None
            if named:
                effects = [(source_id, -amount, False) for source_id, amount in named]
            else:
                left = -moved
                for source_id in oldest_first:
                    taken = min(left, max(holding.get(source_id, ZERO), ZERO))
                    if taken <= ZERO:
                        continue
                    effects.append((source_id, -taken, True))
                    paid_back[source_id] = paid_back.get(source_id, ZERO) + taken
                    left -= taken
        elif reference_type == REFERENCE_TYPE:
            source_id = applied.get(reference_id) if reference_id else None
            if source_id is not None:
                effects = [(source_id, moved, False)]
        elif reference_id is not None and (
            reference_type == ABSORBED or kind == kinds.CREDIT_NOTE.value
        ):
            effects = [(reference_id, moved, False)]
        for source_id, amount, _unnamed in effects:
            holding[source_id] = holding.get(source_id, ZERO) + amount
        if effects:
            did[row_id] = effects
    return {
        source_id: amount for source_id, amount in paid_back.items() if amount > ZERO
    }


@whole_past_a_chunk("invoice_ids")
def drawn_back_onto_bills(
    session: Session, *, firm_id: UUID, invoice_ids: Sequence[UUID] | None
) -> dict[UUID, Decimal]:
    """Return what goes back on each bill from credit its sources no longer give.

    The part of a return or credit note its paid bill could not absorb is
    credit. Once that credit has been set against another bill or paid back,
    and the first bill then owes more again -- the receipt that paid it
    reversed -- the source gives less credit than was used. The difference
    came off the first bill twice, so it goes back on it, and what the bills
    owe and the customer's account agree.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        invoice_ids: The sales invoices to ask about; None asks about every
            invoice of the firm.

    Returns:
        The amount per bill, for those with any.

    """
    if invoice_ids is not None and not invoice_ids:
        return {}
    used = set(
        session.scalars(
            select(CustomerCreditApplication.source_id)
            .where(CustomerCreditApplication.firm_id == firm_id, *_live())
            .distinct()
        ).all()
    )
    if not used:
        return {}
    if invoice_ids is not None:
        used &= {
            part.source_id for part in _bill_parts(session, firm_id, list(invoice_ids))
        }
        if not used:
            return {}
    credits, parts = _work(session, firm_id=firm_id, source_ids=sorted(used, key=str))
    short = {
        credit.source_id: max(
            credit.applied_amount + credit.refunded_amount - credit.credit_amount, ZERO
        )
        for credit in credits
    }
    wanted = None if invoice_ids is None else set(invoice_ids)
    drawn: dict[UUID, Decimal] = {}
    for part in parts:
        share = min(part.amount, short.get(part.source_id, ZERO))
        if share <= ZERO:
            continue
        short[part.source_id] -= share
        if wanted is None or part.bill_id in wanted:
            drawn[part.bill_id] = drawn.get(part.bill_id, ZERO) + share
    return drawn


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def _locked_source(session: Session, *, firm_id: UUID, source_id: UUID) -> _Source:
    """Return the return or credit note giving a credit, locked.

    What is left of a credit is a sum, and two applications racing would each
    see the whole of it -- a guard on a sum takes a lock on the thing consumed.

    Raises:
        ResourceNotFoundError: If the firm has neither with that id.

    """
    from app.credit_note.models import CreditNote
    from app.sales_return.models import SalesReturn

    found = session.scalar(
        select(SalesReturn)
        .where(
            SalesReturn.id == source_id,
            SalesReturn.firm_id == firm_id,
            SalesReturn.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if found is not None:
        return _Source(
            kind=SALES_RETURN,
            id=found.id,
            number=found.return_number,
            on=found.return_date,
            customer_id=found.customer_id,
        )
    note = session.scalar(
        select(CreditNote)
        .where(
            CreditNote.id == source_id,
            CreditNote.firm_id == firm_id,
            CreditNote.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if note is None:
        raise ResourceNotFoundError("Sales return or credit note not found.")
    return _Source(
        kind=CREDIT_NOTE,
        id=note.id,
        number=note.credit_note_number,
        on=note.credit_note_date,
        customer_id=note.customer_id,
    )


def _locked_customer(session: Session, *, firm_id: UUID, customer_id: UUID) -> Customer:
    """Return the customer, locked: both of their balances are being judged."""
    customer = session.scalar(
        select(Customer)
        .where(
            Customer.id == customer_id,
            Customer.firm_id == firm_id,
            Customer.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if customer is None:
        raise ResourceNotFoundError("Customer not found.")
    return customer


def _lock_bill(session: Session, *, firm_id: UUID, bill_id: UUID) -> None:
    """Lock the bill a credit is being set against, invoice or opening bill.

    What it still owes is a sum over everything set against it, and no row
    is updated when one more thing is: without the lock two applications
    would each see the whole of it.
    """
    locked = session.scalar(
        select(SalesInvoice.id)
        .where(SalesInvoice.id == bill_id, SalesInvoice.firm_id == firm_id)
        .with_for_update()
    )
    if locked is None:
        session.scalar(
            select(CustomerOpeningBill.id)
            .where(
                CustomerOpeningBill.id == bill_id,
                CustomerOpeningBill.firm_id == firm_id,
            )
            .with_for_update()
        )


def _no_credit_message(source: _Source) -> str:
    """Say why a source gives nothing to apply or pay back."""
    if source.kind == CREDIT_NOTE:
        return (
            f"{source.number} leaves no credit on the customer's account: it is "
            "not approved, or its bill still owed all of it."
        )
    return (
        f"{source.number} leaves no credit on the customer's account: it is not "
        "completed, or its bill still owed everything it credited."
    )


def _credit_of(
    session: Session, *, firm_id: UUID, source: _Source
) -> CustomerCredit | None:
    """Return one source's credit, read with the rest of its customer's."""
    return next(
        (
            credit
            for credit in customer_credits(
                session, firm_id=firm_id, customer_id=source.customer_id
            )
            if credit.source_id == source.id
        ),
        None,
    )


def apply_customer_credit(
    session: Session,
    *,
    firm_id: UUID,
    source_id: UUID,
    invoice_id: UUID,
    amount: Decimal,
    actor_id: UUID,
    applied_on: date | None = None,
) -> CustomerCredit:
    """Set part of a customer credit against another of the customer's bills.

    ``source_id`` is the sales return or credit note that gave the credit.
    ``invoice_id`` is a sales invoice or an opening bill -- whichever Record
    Receipt offers for the customer. Nothing is posted to the ledger. Does
    not commit.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        source_id: The return or credit note.
        invoice_id: The bill to set it against.
        amount: How much of it.
        actor_id: The user applying it.
        applied_on: The day it met the bill; blank is the later of the
            source's date and the bill's, as an advance applied to a bill
            raised since is dated.

    Returns:
        The credit, with what is left of it.

    Raises:
        ResourceNotFoundError: If the firm has no such return or credit note.
        ValidationError: If it gives no credit, has less left than asked, the
            bill is not the customer's, not approved, or owes less, or the
            date is wrong.

    """
    # Imported here: the settlement service imports this module.
    from app.customers.services.customer_service import CustomerService
    from app.settlements.services.settlement_service import ReceiptService

    asked = quantize_ledger(amount)
    if asked <= ZERO:
        raise ValidationError("An application must be for more than nothing.")
    source = _locked_source(session, firm_id=firm_id, source_id=source_id)
    customer = _locked_customer(
        session, firm_id=firm_id, customer_id=source.customer_id
    )
    _lock_bill(session, firm_id=firm_id, bill_id=invoice_id)
    credit = _credit_of(session, firm_id=firm_id, source=source)
    if credit is None or credit.credit_amount <= ZERO:
        raise ValidationError(_no_credit_message(source))
    if asked > credit.available_amount:
        raise ValidationError(
            f"{source.number} has only {credit.available_amount} of credit "
            "left to set against a bill."
        )
    bill = next(
        (
            record
            for record in ReceiptService(session).outstanding_invoices(
                firm_id=firm_id, party_id=source.customer_id
            )
            if record.invoice_id == invoice_id
        ),
        None,
    )
    if bill is None:
        raise ValidationError(
            "That bill is not this customer's, is not approved, or is already "
            "settled in full."
        )
    if asked > bill.outstanding_amount:
        raise ValidationError(
            f"{bill.invoice_number} owes only {bill.outstanding_amount}."
        )
    earliest = max(source.on, bill.invoice_date)
    on = applied_on or earliest
    # The firm's own today (D-CFG-25), never the UTC day.
    if on > max(firm_today(session, firm_id), earliest):
        raise ValidationError("A credit cannot be applied on a future date.")
    if on < earliest:
        raise ValidationError(
            f"{source.number} is dated {source.on.isoformat()} and "
            f"{bill.invoice_number} {bill.invoice_date.isoformat()}: the credit "
            "meets the bill on or after both."
        )
    # The part of what is left that already came off the customer's balance
    # goes first and moves nothing; only what is held as an advance does.
    from_advance = max(asked - (credit.available_amount - credit.held_amount), ZERO)
    on_account = quantize_ledger(Decimal(str(customer.unapplied_advance_balance)))
    if from_advance > on_account:
        raise ValidationError(
            f"{customer.display_name} holds only {on_account} on account, so "
            f"{from_advance} of {source.number} cannot come out of it: the "
            "rest has been paid back or applied."
        )
    # Never more than the account says is owed: another credit that already
    # came off the balance, and names no bill yet, has covered the rest.
    moved = min(
        from_advance, quantize_ledger(Decimal(str(customer.current_outstanding)))
    )
    application = CustomerCreditApplication(
        id=uuid4(),
        firm_id=firm_id,
        customer_id=source.customer_id,
        source_type=source.kind,
        source_id=source.id,
        target_type=OPENING_BILL if bill.is_opening_bill else SALES_INVOICE,
        target_id=invoice_id,
        applied_on=on,
        amount=asked,
        advance_amount=moved,
        status=POSTED,
        created_by=actor_id,
        updated_by=actor_id,
    )
    if moved > ZERO:
        written = CustomerService(session).post_receivable_transaction(
            source.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.ADVANCE_APPLY,
                amount=moved,
                transaction_date=on,
                reference_type=REFERENCE_TYPE,
                reference_id=application.id,
                reference_number=source.number,
                remarks=f"{source.number} set against {bill.invoice_number}.",
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            commit=False,
        )
        application.receivable_transaction_id = written.id
    session.add(application)
    session.flush()
    record_audit(
        session,
        action="customer_credit.applied",
        entity_type="customer_credit_application",
        entity_id=application.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={
            "source": source.kind,
            "source_number": source.number,
            "bill": bill.invoice_number,
            "amount": str(asked),
            "advance_amount": str(moved),
            "applied_on": on.isoformat(),
        },
    )
    found = _credit_of(session, firm_id=firm_id, source=source)
    assert found is not None
    return found


def _take_back(
    session: Session,
    row: CustomerCreditApplication,
    *,
    firm_id: UUID,
    actor_id: UUID,
    reason: str,
    action: str,
) -> None:
    """Reverse one row: the balances by its own deltas, the row by status."""
    from app.customers.services.customer_service import CustomerService

    if row.receivable_transaction_id is not None:
        CustomerService(session).reverse_receivable_transaction(
            row.receivable_transaction_id,
            firm_scope=firm_id,
            actor_id=actor_id,
            remarks=reason,
            commit=False,
            on=max(firm_today(session, firm_id), row.applied_on),
        )
    row.status = REVERSED
    row.reversed_at = utc_now()
    row.reversed_by = actor_id
    row.reversal_reason = reason
    row.updated_by = actor_id
    record_audit(
        session,
        action=action,
        entity_type="customer_credit_application",
        entity_id=row.id,
        actor_id=actor_id,
        firm_id=firm_id,
        before_data={
            "source_type": row.source_type,
            "source_id": str(row.source_id),
            "target_type": row.target_type,
            "target_id": str(row.target_id),
            "amount": str(row.amount),
            "advance_amount": str(row.advance_amount),
        },
        after_data={"status": REVERSED, "reason": reason},
    )


def reverse_customer_credit_application(
    session: Session,
    *,
    firm_id: UUID,
    application_id: UUID,
    reason: str,
    actor_id: UUID,
) -> CustomerCreditApplication:
    """Take back a credit set against a bill in error; does not commit.

    The bill owes that much again and the credit is free again; the
    customer's balances go back by what the application moved. Nothing is
    posted, as nothing was.

    Raises:
        ResourceNotFoundError: If the firm has no such application.
        ValidationError: If it is already reversed, or is the record of a
            refund -- that is taken back by reversing the refund.

    """
    if not reason.strip():
        raise ValidationError("Say why the credit is being taken off the bill.")
    row = session.scalar(
        select(CustomerCreditApplication)
        .where(
            CustomerCreditApplication.id == application_id,
            CustomerCreditApplication.firm_id == firm_id,
            CustomerCreditApplication.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if row is None:
        raise ResourceNotFoundError("Credit application not found.")
    if row.status != POSTED:
        raise ValidationError("This credit has already been taken off the bill.")
    if row.target_type == REFUND:
        raise ValidationError(
            "This credit was paid back to the customer. Reverse the refund to "
            "free it."
        )
    _locked_source(session, firm_id=firm_id, source_id=row.source_id)
    _locked_customer(session, firm_id=firm_id, customer_id=row.customer_id)
    _take_back(
        session,
        row,
        firm_id=firm_id,
        actor_id=actor_id,
        reason=reason.strip(),
        action="customer_credit.reversed",
    )
    session.flush()
    # The advance is back by what the application moved. Where the source's
    # own bill has come to owe again since -- its receipt reversed -- that
    # advance is no longer credit, and goes back on that bill (D-PRC-88).
    absorb_credit_no_longer_given(
        session, firm_id=firm_id, customer_id=row.customer_id, actor_id=actor_id
    )
    return row


def absorb_credit_no_longer_given(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    actor_id: UUID,
    on: date | None = None,
) -> Decimal:
    """Take back onto its own bill an advance its source no longer gives.

    A return on a paid bill leaves its value on the customer's account as an
    advance, and that advance is credit only while the bill stays settled
    past its total. When the bill owes again -- the receipt that paid it was
    reversed -- what a bill owes already reads the return as coming off it
    (``credited_against``), so the same money stood on the account twice:
    owed on no bill, and held from no source. With the bills paid as they
    read the customer owed 826.00 and held 826.00, and the 826.00 could be
    paid out in cash (D-PRC-88).

    Called once a receipt, a refund or an application has been reversed:
    each of those can leave a source holding more on the account than it
    gives. The excess comes off what the customer owes and off what they
    hold, by one ``ADVANCE_APPLY`` row referenced to the source
    (``ABSORBED``). No journal: receivables did not move. Should the bill be
    settled past its total again nothing is put back -- money arriving then
    makes its own advance. Cancelling the source reverses the rows
    (``withdraw_credit_applications``). Does not commit.

    Args:
        session: The firm's session.
        firm_id: The owning firm.
        customer_id: The customer whose credits to settle up.
        actor_id: The user whose action left them unsettled.
        on: The day it happened; blank is the firm's today.

    Returns:
        How much went back on bills.

    """
    # Imported here: the customer service imports settlement-adjacent models.
    from app.customers.services.customer_service import CustomerService

    customer = _locked_customer(session, firm_id=firm_id, customer_id=customer_id)
    day = on or firm_today(session, firm_id)
    absorbed = ZERO
    for credit in _standing_credits(session, firm_id=firm_id, customer_id=customer_id):
        excess = min(
            credit.advance_on_account - credit.held_amount,
            # Never more than the account holds or is owed: the rest of it
            # has been paid back, or covered by something else.
            quantize_ledger(Decimal(str(customer.unapplied_advance_balance))),
            quantize_ledger(Decimal(str(customer.current_outstanding))),
        )
        if excess <= ZERO:
            continue
        CustomerService(session).post_receivable_transaction(
            customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.ADVANCE_APPLY,
                amount=excess,
                transaction_date=max(day, credit.source_date),
                reference_type=ABSORBED,
                reference_id=credit.source_id,
                reference_number=credit.source_number,
                remarks=(
                    f"{credit.source_number} comes off its own bill again: the "
                    "bill owes, so this is no longer held on account."
                ),
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            commit=False,
        )
        record_audit(
            session,
            action="customer_credit.absorbed",
            entity_type="customer",
            entity_id=customer_id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "source": credit.source_type,
                "source_number": credit.source_number,
                "amount": str(excess),
            },
        )
        absorbed += excess
    if absorbed > ZERO:
        session.flush()
    return absorbed


def withdraw_credit_applications(
    session: Session,
    *,
    firm_id: UUID,
    source_id: UUID,
    actor_id: UUID,
    reason: str,
) -> int:
    """Withdraw everything a credit was used for, when its source is cancelled.

    Cancelling the return or the credit note takes its credit to receivables
    back, so the credit it gave is gone: each bill it was set against owes
    that part again, and the customer's balances go back by what each
    application moved -- before the source's own row is undone, which needs
    the advance it made to be there. A refund drawn on it stops naming it;
    the refund itself stands, against whatever else the customer holds.

    Returns:
        How many rows were withdrawn.

    """
    rows = session.scalars(
        select(CustomerCreditApplication)
        .where(
            CustomerCreditApplication.firm_id == firm_id,
            CustomerCreditApplication.source_id == source_id,
            *_live(),
        )
        .order_by(
            CustomerCreditApplication.created_at.desc(),
            CustomerCreditApplication.id.desc(),
        )
    ).all()
    for row in rows:
        _take_back(
            session,
            row,
            firm_id=firm_id,
            actor_id=actor_id,
            reason=reason,
            action="customer_credit.withdrawn",
        )
    # And what went back on its own bill when that bill came to owe again
    # (``absorb_credit_no_longer_given``): the source's own row put that
    # advance on the account, and can only be undone with it there.
    from app.customers.services.customer_service import CustomerService

    for absorbed_id in session.scalars(
        select(CustomerReceivableTransaction.id)
        .where(
            CustomerReceivableTransaction.firm_id == firm_id,
            CustomerReceivableTransaction.reference_id == source_id,
            *_standing_absorptions(),
        )
        .order_by(CustomerReceivableTransaction.created_at.desc())
    ).all():
        CustomerService(session).reverse_receivable_transaction(
            absorbed_id,
            firm_scope=firm_id,
            actor_id=actor_id,
            remarks=reason,
            commit=False,
        )
    session.flush()
    return len(rows)


def draw_refund_on_credits(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    refund_id: UUID,
    refund_number: str,
    amount: Decimal,
    refunded_on: date,
    actor_id: UUID,
    source_id: UUID | None = None,
) -> Decimal:
    """Record which credits a refund to a customer paid back; does not commit.

    Called before the refund moves the customer's advance. A refund that
    names its source uses that much of it, and is refused past what it has
    left. One that names none takes the credits held on account, oldest
    first; what they do not cover is the customer's unapplied receipts'
    money, as it always was. Either way the credit paid back can no longer
    be set against a bill.

    Returns:
        How much of the refund was drawn from credits.

    Raises:
        ResourceNotFoundError: If a named source is not this firm's.
        ValidationError: If a named source is another customer's, gives no
            credit, or has less left than the refund.

    """
    asked = quantize_ledger(amount)
    # The source before the customer, the order applying takes them in.
    source = (
        None
        if source_id is None
        else _locked_source(session, firm_id=firm_id, source_id=source_id)
    )
    _locked_customer(session, firm_id=firm_id, customer_id=customer_id)
    credits = customer_credits(session, firm_id=firm_id, customer_id=customer_id)
    takes: list[tuple[CustomerCredit, Decimal]] = []
    if source is not None:
        if source.customer_id != customer_id:
            raise ValidationError(f"{source.number} is another customer's.")
        named = next((item for item in credits if item.source_id == source.id), None)
        if named is None or named.credit_amount <= ZERO:
            raise ValidationError(_no_credit_message(source))
        if asked > named.available_amount:
            raise ValidationError(
                f"{source.number} has only {named.available_amount} of credit "
                "left to be paid back."
            )
        takes.append((named, asked))
    else:
        remaining = asked
        for credit in credits:
            taken = min(remaining, credit.held_amount)
            if taken <= ZERO:
                continue
            takes.append((credit, taken))
            remaining -= taken
    drawn = ZERO
    for credit, taken in takes:
        row = CustomerCreditApplication(
            firm_id=firm_id,
            customer_id=customer_id,
            source_type=credit.source_type,
            source_id=credit.source_id,
            target_type=REFUND,
            target_id=refund_id,
            applied_on=refunded_on,
            amount=taken,
            # A refund always comes out of the advance; the refund's own
            # receivable row moves it, so this row names none.
            advance_amount=min(taken, credit.held_amount),
            status=POSTED,
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(row)
        session.flush()
        record_audit(
            session,
            action="customer_credit.refunded",
            entity_type="customer_credit_application",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "source": credit.source_type,
                "source_number": credit.source_number,
                "refund": refund_number,
                "amount": str(taken),
            },
        )
        drawn += taken
    return drawn


def release_refund_draws(
    session: Session, *, firm_id: UUID, refund_id: UUID, actor_id: UUID, reason: str
) -> int:
    """Free the credits a refund paid back, when the refund is reversed.

    The refund's own reversal puts the customer's advance back; this only
    stops the rows naming it, so the credits can be applied or refunded
    again.

    Returns:
        How many rows were released.

    """
    rows = session.scalars(
        select(CustomerCreditApplication).where(
            CustomerCreditApplication.firm_id == firm_id,
            CustomerCreditApplication.target_type == REFUND,
            CustomerCreditApplication.target_id == refund_id,
            *_live(),
        )
    ).all()
    for row in rows:
        _take_back(
            session,
            row,
            firm_id=firm_id,
            actor_id=actor_id,
            reason=reason,
            action="customer_credit.refund_reversed",
        )
    return len(rows)


def application_record(
    session: Session, row: CustomerCreditApplication
) -> CustomerCreditUse:
    """Describe one application row, with the name of what it points at."""
    return CustomerCreditUse(
        id=row.id,
        target_type=row.target_type,
        target_id=row.target_id,
        target_number=_target_numbers(session, [row]).get(row.target_id, ""),
        amount=quantize_ledger(Decimal(str(row.amount))),
        applied_on=row.applied_on,
        version=row.version,
    )
