"""Supplier credit: what a purchase return or a debit note left on the vendor.

A completed purchase return debits accounts payable with its whole total. A
return raised from the supplier's **bill** takes that off the bill (D-BUY-6).
A return raised from the **goods receipt** names no bill, so the debit stood in
the ledger with nothing on the purchasing side tracking it per supplier: the
payment screen still offered the whole bill, and the vendor could be deleted
with the credit in payables belonging to nobody (D-FIN-19, driven on TEST01 on
2026-09-19).

It is now a supplier credit -- the payable twin of a customer's advance. What
a return has to give is derived, never stored: its ledger total, less what its
bill-sourced lines already took off their bills, less the live
`SupplierCreditApplication` rows setting it against a bill. Applying posts no
journal, for the reason applying a customer's advance posts none: the return
already debited payables and the bill already credited them, so the only thing
left to say is which bill the debit belongs to.

A return off a bill that was already paid has nothing left on that bill to
come off, so the part the bill cannot absorb is credit too (D-BUY-20); should
the bill owe more again once that credit is used, the part used goes back on
the bill (`drawn_back_onto_bills`).

**A debit note is a second source (decision A4, 2026-10-02).** An approved
debit note debits payables against its bill exactly as a return off the bill's
lines does, so the same arithmetic applies: what its bill cannot absorb --
already paid, say -- is credit on the supplier's account, to set against
another bill or be paid back. Bill parts from returns and from debit notes are
one list, newest first, so a bill that cannot absorb them all turns the newest
into credit whichever kind it is. A credit is named by its **source id** -- the
return's id or the debit note's -- and an application or refund row carries
exactly one of the two.

**An opening bill is a second target (BUY-17, decision A52).** A supplier's
bill brought over from the old software is owed in payables exactly as a
purchase bill is, so a credit is set against it the same way: the row names
the opening bill instead of a purchase invoice, posts nothing, and the opening
bill's derived outstanding counts it (`opening_bill_payments`). Returns and
debit notes are only ever raised against purchase bills, so the spill-over and
draw-back arithmetic below never meets an opening bill.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.chunks import over_chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_money
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.models import (
    SettlementMethod,
    SupplierCreditApplication,
    SupplierCreditRefund,
)
from app.vendors.models import VendorOpeningBill
from app.vendors.services.opening_bill_service import opening_bill_label

#: The return states whose posting stands: completing debits payables, a
#: cancelled return has taken that back, and a draft has not posted.
CREDITING_RETURN_STATES = ("COMPLETED", "CLOSED")
#: The debit note state whose posting stands: approval is what posts.
CREDITING_DEBIT_NOTE_STATES = ("APPROVED",)

PURCHASE_RETURN = "PURCHASE_RETURN"
DEBIT_NOTE = "DEBIT_NOTE"


@dataclass
class SupplierCredit:
    """One source's credit on the vendor's account, and what is left of it.

    The source is a purchase return or, since A4, a debit note: exactly one of
    ``purchase_return_id`` and ``debit_note_id`` is set. ``return_number`` and
    ``return_date`` are that document's number and date.
    """

    purchase_return_id: UUID | None
    return_number: str
    return_date: date
    vendor_id: UUID
    credit_amount: Decimal
    applied_amount: Decimal
    applied_to: list[str] = field(default_factory=list)
    #: What the supplier has paid back against it (backlog 69 row 7).
    refunded_amount: Decimal = ZERO
    #: CREDIT, REPLACEMENT or REFUND: what the return comes back as. A debit
    #: note's credit is always CREDIT -- set against a bill or paid back.
    outcome: str = "CREDIT"
    debit_note_id: UUID | None = None

    @property
    def source_id(self) -> UUID:
        """Return the id of the document that gave the credit."""
        source = self.purchase_return_id or self.debit_note_id
        assert source is not None
        return source

    @property
    def source_type(self) -> str:
        """Return PURCHASE_RETURN or DEBIT_NOTE."""
        return PURCHASE_RETURN if self.purchase_return_id else DEBIT_NOTE

    @property
    def available_amount(self) -> Decimal:
        """Return what can still be set against a bill or paid back."""
        return max(
            self.credit_amount - self.applied_amount - self.refunded_amount, ZERO
        )


@dataclass(frozen=True)
class _Source:
    """A document that can give supplier credit, read for a lock or a check."""

    kind: str
    id: UUID
    number: str
    on: date
    vendor_id: UUID
    outcome: str


def _source_column() -> "ColumnElement[UUID]":
    """Return the expression naming an application's source, whichever kind."""
    return func.coalesce(
        SupplierCreditApplication.purchase_return_id,
        SupplierCreditApplication.debit_note_id,
    )


def supplier_credits(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID | None = None,
    source_ids: Sequence[UUID] | None = None,
) -> list[SupplierCredit]:
    """Return each standing source's supplier credit, oldest first.

    A return's credit is what its posting debited payables with, less what its
    bill-sourced lines took off their own bills -- so a return raised from a
    goods receipt gives all of it -- plus whatever of those lines the bill
    could not absorb because it was already paid (D-BUY-20). A debit note's
    is only the part its bill could not absorb (A4).

    Args:
        session: The firm's store.
        firm_id: The firm.
        vendor_id: Only this vendor's documents, where given.
        source_ids: Only these returns and debit notes, where given.

    Returns:
        One entry per source that gives any credit, applied or not.

    """
    return [
        credit
        for credit in _all_credits(
            session, firm_id=firm_id, vendor_id=vendor_id, source_ids=source_ids
        )
        if credit.credit_amount > ZERO
    ]


def _all_credits(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID | None = None,
    source_ids: Sequence[UUID] | None = None,
) -> list[SupplierCredit]:
    """Return every standing source's credit figures, a credit of nothing too.

    Args:
        session: The firm's store.
        firm_id: The firm.
        vendor_id: Only this vendor's documents, where given.
        source_ids: Only these returns and debit notes, where given.

    Returns:
        One entry per completed return and approved debit note.

    """
    # Imported here: both modules import settlement-adjacent models.
    from app.debit_note.models import DebitNote
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    statement = select(PurchaseReturn).where(
        PurchaseReturn.firm_id == firm_id,
        PurchaseReturn.is_deleted.is_(False),
        PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
    )
    notes_statement = select(DebitNote).where(
        DebitNote.firm_id == firm_id,
        DebitNote.is_deleted.is_(False),
        DebitNote.status.in_(CREDITING_DEBIT_NOTE_STATES),
    )
    if vendor_id is not None:
        statement = statement.where(PurchaseReturn.vendor_id == vendor_id)
        notes_statement = notes_statement.where(DebitNote.vendor_id == vendor_id)
    if source_ids is not None:
        statement = statement.where(PurchaseReturn.id.in_(source_ids))
        notes_statement = notes_statement.where(DebitNote.id.in_(source_ids))
    returns = session.scalars(statement).all()
    notes = session.scalars(notes_statement).all()
    if not returns and not notes:
        return []
    ids = [row.id for row in returns] + [row.id for row in notes]
    billed = {
        return_id: Decimal(str(total))
        for return_id, total in session.execute(
            select(
                PurchaseReturnLine.purchase_return_id,
                func.coalesce(func.sum(PurchaseReturnLine.net_amount), 0),
            )
            .where(
                PurchaseReturnLine.purchase_return_id.in_([row.id for row in returns]),
                PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                PurchaseReturnLine.is_deleted.is_(False),
            )
            .group_by(PurchaseReturnLine.purchase_return_id)
        ).all()
    }
    applied: dict[UUID, Decimal] = {}
    applied_to: dict[UUID, list[str]] = {}
    source = _source_column()
    for source_id, amount, number, opening in session.execute(
        select(
            source,
            SupplierCreditApplication.amount,
            PurchaseInvoice.invoice_number,
            VendorOpeningBill,
        )
        .outerjoin(
            PurchaseInvoice,
            PurchaseInvoice.id == SupplierCreditApplication.purchase_invoice_id,
        )
        .outerjoin(
            VendorOpeningBill,
            VendorOpeningBill.id == SupplierCreditApplication.vendor_opening_bill_id,
        )
        .where(
            SupplierCreditApplication.firm_id == firm_id,
            source.in_(ids),
            SupplierCreditApplication.is_deleted.is_(False),
        )
        .order_by(SupplierCreditApplication.created_at.asc())
    ).all():
        applied[source_id] = applied.get(source_id, ZERO) + quantize_ledger(
            Decimal(str(amount))
        )
        applied_to.setdefault(source_id, []).append(
            opening_bill_label(opening) if opening is not None else number
        )
    refunded: dict[UUID, Decimal] = {}
    refund_source = func.coalesce(
        SupplierCreditRefund.purchase_return_id, SupplierCreditRefund.debit_note_id
    )
    for source_id, amount in session.execute(
        select(refund_source, SupplierCreditRefund.amount).where(
            SupplierCreditRefund.firm_id == firm_id,
            refund_source.in_(ids),
            SupplierCreditRefund.is_deleted.is_(False),
            SupplierCreditRefund.status == "POSTED",
        )
    ).all():
        refunded[source_id] = refunded.get(source_id, ZERO) + quantize_ledger(
            Decimal(str(amount))
        )
    spilled = _spilled_over(session, firm_id=firm_id, source_ids=ids)
    credits: list[SupplierCredit] = []
    for row in returns:
        # What the posting debited payables with, at the ledger's scale.
        posted = quantize_ledger(quantize_money(row.grand_total))
        credit = max(posted - quantize_ledger(billed.get(row.id, ZERO)), ZERO)
        credit += spilled.get(row.id, ZERO)
        credits.append(
            SupplierCredit(
                purchase_return_id=row.id,
                return_number=row.return_number,
                return_date=row.return_date,
                vendor_id=row.vendor_id,
                credit_amount=credit,
                applied_amount=applied.get(row.id, ZERO),
                applied_to=applied_to.get(row.id, []),
                refunded_amount=refunded.get(row.id, ZERO),
                outcome=row.outcome or "CREDIT",
            )
        )
    for note in notes:
        # All of a debit note came off its bill; only the part the bill
        # could not absorb is the supplier's to give back (A4).
        credits.append(
            SupplierCredit(
                purchase_return_id=None,
                debit_note_id=note.id,
                return_number=note.debit_note_number,
                return_date=note.debit_note_date,
                vendor_id=note.vendor_id,
                credit_amount=spilled.get(note.id, ZERO),
                applied_amount=applied.get(note.id, ZERO),
                applied_to=applied_to.get(note.id, []),
                refunded_amount=refunded.get(note.id, ZERO),
            )
        )
    credits.sort(key=lambda item: (item.return_date, item.return_number))
    return credits


def _bill_parts(
    session: Session,
    *,
    firm_id: UUID,
    source_ids: Sequence[UUID] | None = None,
    invoice_ids: Sequence[UUID] | None = None,
) -> list[tuple[UUID, UUID, Decimal]]:
    """Return (source, bill, amount) for what returns and debit notes took off.

    Newest document first, returns and debit notes together, the order in
    which a bill that cannot absorb them all turns them into credit. Narrowed
    to some sources, some bills, or both.
    """
    from app.debit_note.models import DebitNote
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    statement = (
        select(
            PurchaseReturnLine.purchase_return_id,
            PurchaseReturnLine.source_document_id,
            func.coalesce(func.sum(PurchaseReturnLine.net_amount), 0),
            PurchaseReturn.return_date,
            PurchaseReturn.return_number,
        )
        .join(
            PurchaseReturn, PurchaseReturn.id == PurchaseReturnLine.purchase_return_id
        )
        .where(
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
            PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
            PurchaseReturnLine.is_deleted.is_(False),
        )
        .group_by(
            PurchaseReturnLine.purchase_return_id,
            PurchaseReturnLine.source_document_id,
            PurchaseReturn.return_date,
            PurchaseReturn.return_number,
        )
    )
    notes = select(
        DebitNote.id,
        DebitNote.purchase_invoice_id,
        DebitNote.taxable_amount,
        DebitNote.tax_amount,
        DebitNote.debit_note_date,
        DebitNote.debit_note_number,
    ).where(
        DebitNote.firm_id == firm_id,
        DebitNote.is_deleted.is_(False),
        DebitNote.status.in_(CREDITING_DEBIT_NOTE_STATES),
    )
    if source_ids is not None:
        statement = statement.where(
            PurchaseReturnLine.purchase_return_id.in_(source_ids)
        )
        notes = notes.where(DebitNote.id.in_(source_ids))
    if invoice_ids is not None:
        statement = statement.where(
            PurchaseReturnLine.source_document_id.in_(invoice_ids)
        )
        notes = notes.where(DebitNote.purchase_invoice_id.in_(invoice_ids))
    parts: list[tuple[date, str, UUID, UUID, Decimal]] = [
        (on, number, return_id, bill_id, quantize_ledger(Decimal(str(amount))))
        for return_id, bill_id, amount, on, number in session.execute(statement).all()
    ]
    # Counted as the bill counts it: each part rounded to the ledger, summed.
    parts.extend(
        (
            on,
            number,
            note_id,
            bill_id,
            quantize_ledger(Decimal(str(taxable))) + quantize_ledger(Decimal(str(tax))),
        )
        for note_id, bill_id, taxable, tax, on, number in session.execute(notes).all()
    )
    parts.sort(key=lambda part: (part[0], part[1], str(part[3])), reverse=True)
    return [(source_id, bill_id, amount) for _, _, source_id, bill_id, amount in parts]


def _spilled_over(
    session: Session, *, firm_id: UUID, source_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Return what of each source its bills could not absorb (D-BUY-20, A4).

    A bill already paid has nothing left for a return off its lines, or a
    debit note against it, to come off, so the excess of everything taken off
    the bill over its total is the supplier's to give back. It falls to the
    bill's returns and debit notes newest first -- the earlier ones fitted when
    they were made -- each up to what it took off that bill.
    """
    from app.settlements.services.settlement_service import PaymentService

    bills = sorted(
        {
            bill_id
            for _, bill_id, _ in _bill_parts(
                session, firm_id=firm_id, source_ids=source_ids
            )
        }
    )
    if not bills:
        return {}
    positions = PaymentService(session).purchase_bill_positions(
        firm_id=firm_id, invoice_ids=bills
    )
    left = {
        bill_id: max(already - total, ZERO)
        for bill_id, (total, already) in positions.items()
    }
    spilled: dict[UUID, Decimal] = {}
    for source_id, bill_id, amount in _bill_parts(
        session, firm_id=firm_id, invoice_ids=bills
    ):
        share = min(amount, left.get(bill_id, ZERO))
        if share <= ZERO:
            continue
        left[bill_id] -= share
        spilled[source_id] = spilled.get(source_id, ZERO) + share
    return spilled


@over_chunks("invoice_ids")
def drawn_back_onto_bills(
    session: Session, *, firm_id: UUID, invoice_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Return what goes back on each bill from credit its sources no longer give.

    The part of a return or debit note its paid bill could not absorb is
    credit (D-BUY-20, A4). Once that credit has been set against another bill
    or paid back, and the first bill then owes more again -- its payment
    reversed -- the source gives less credit than was used. The difference was
    taken off the first bill twice, so it goes back on it, and the payables
    list and the ledger agree.
    """
    if not invoice_ids:
        return {}
    used = set(
        session.scalars(
            select(_source_column()).where(
                SupplierCreditApplication.firm_id == firm_id,
                SupplierCreditApplication.is_deleted.is_(False),
            )
        ).all()
    ) | set(
        session.scalars(
            select(
                func.coalesce(
                    SupplierCreditRefund.purchase_return_id,
                    SupplierCreditRefund.debit_note_id,
                )
            ).where(
                SupplierCreditRefund.firm_id == firm_id,
                SupplierCreditRefund.is_deleted.is_(False),
                SupplierCreditRefund.status == "POSTED",
            )
        ).all()
    )
    if not used:
        return {}
    sources = sorted(
        {
            source_id
            for source_id, _, _ in _bill_parts(
                session, firm_id=firm_id, invoice_ids=invoice_ids
            )
            if source_id in used
        }
    )
    if not sources:
        return {}
    short = {
        credit.source_id: max(
            credit.applied_amount + credit.refunded_amount - credit.credit_amount,
            ZERO,
        )
        for credit in _all_credits(session, firm_id=firm_id, source_ids=sources)
    }
    wanted = set(invoice_ids)
    drawn: dict[UUID, Decimal] = {}
    for source_id, bill_id, amount in _bill_parts(
        session, firm_id=firm_id, source_ids=sources
    ):
        share = min(amount, short.get(source_id, ZERO))
        if share <= ZERO:
            continue
        short[source_id] -= share
        if bill_id in wanted:
            drawn[bill_id] = drawn.get(bill_id, ZERO) + share
    return drawn


@over_chunks("invoice_ids")
def credit_applied_against(
    session: Session,
    *,
    firm_id: UUID,
    invoice_ids: Sequence[UUID],
    opening: bool = False,
) -> dict[UUID, Decimal]:
    """Sum the supplier credit set against each bill.

    ``opening`` reads the ids as opening bills rather than purchase bills
    (BUY-17).
    """
    if not invoice_ids:
        return {}
    column = (
        SupplierCreditApplication.vendor_opening_bill_id
        if opening
        else SupplierCreditApplication.purchase_invoice_id
    )
    return {
        invoice_id: quantize_ledger(Decimal(str(total)))
        for invoice_id, total in session.execute(
            select(column, func.coalesce(func.sum(SupplierCreditApplication.amount), 0))
            .where(
                SupplierCreditApplication.firm_id == firm_id,
                column.in_(invoice_ids),
                SupplierCreditApplication.is_deleted.is_(False),
            )
            .group_by(column)
        ).all()
        if invoice_id is not None
    }


def withdraw_credit_applications(
    session: Session,
    *,
    firm_id: UUID,
    actor_id: UUID,
    purchase_return_id: UUID | None = None,
    purchase_invoice_id: UUID | None = None,
    debit_note_id: UUID | None = None,
    vendor_opening_bill_id: UUID | None = None,
) -> int:
    """Withdraw the credit set against a bill, when its source or bill goes.

    Cancelling the return or the debit note takes its payables debit back, so
    the credit it gave is gone and the bill owes that part again. Cancelling
    the bill -- a purchase bill or an opening bill -- takes its payable back,
    so the credit set against it is free again. Nothing posts: each document's
    own cancellation already reversed its journal.

    Returns:
        How many applications were withdrawn.

    """
    statement = select(SupplierCreditApplication).where(
        SupplierCreditApplication.firm_id == firm_id,
        SupplierCreditApplication.is_deleted.is_(False),
    )
    if purchase_return_id is not None:
        statement = statement.where(
            SupplierCreditApplication.purchase_return_id == purchase_return_id
        )
    if debit_note_id is not None:
        statement = statement.where(
            SupplierCreditApplication.debit_note_id == debit_note_id
        )
    if purchase_invoice_id is not None:
        statement = statement.where(
            SupplierCreditApplication.purchase_invoice_id == purchase_invoice_id
        )
    if vendor_opening_bill_id is not None:
        statement = statement.where(
            SupplierCreditApplication.vendor_opening_bill_id == vendor_opening_bill_id
        )
    rows = session.scalars(statement).all()
    now = utc_now()
    for row in rows:
        row.is_deleted = True
        row.deleted_at = now
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            session,
            action="supplier_credit.withdrawn",
            entity_type="supplier_credit_application",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={
                "purchase_return_id": (
                    str(row.purchase_return_id) if row.purchase_return_id else None
                ),
                "debit_note_id": str(row.debit_note_id) if row.debit_note_id else None,
                "purchase_invoice_id": (
                    str(row.purchase_invoice_id) if row.purchase_invoice_id else None
                ),
                "vendor_opening_bill_id": (
                    str(row.vendor_opening_bill_id)
                    if row.vendor_opening_bill_id
                    else None
                ),
                "amount": str(row.amount),
            },
        )
    return len(rows)


def _locked_source(session: Session, *, firm_id: UUID, source_id: UUID) -> _Source:
    """Return the return or debit note giving a credit, locked.

    What is left of a credit is a sum, and two applications racing would each
    see the whole of it -- a guard on a sum takes a lock on the thing consumed.

    Raises:
        ResourceNotFoundError: If the firm has neither with that id.

    """
    from app.debit_note.models import DebitNote
    from app.purchase_return.models import PurchaseReturn

    found = session.scalar(
        select(PurchaseReturn)
        .where(
            PurchaseReturn.id == source_id,
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if found is not None:
        return _Source(
            kind=PURCHASE_RETURN,
            id=found.id,
            number=found.return_number,
            on=found.return_date,
            vendor_id=found.vendor_id,
            outcome=found.outcome or "CREDIT",
        )
    note = session.scalar(
        select(DebitNote)
        .where(
            DebitNote.id == source_id,
            DebitNote.firm_id == firm_id,
            DebitNote.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if note is None:
        raise ResourceNotFoundError("Purchase return or debit note not found.")
    return _Source(
        kind=DEBIT_NOTE,
        id=note.id,
        number=note.debit_note_number,
        on=note.debit_note_date,
        vendor_id=note.vendor_id,
        outcome="CREDIT",
    )


def _no_credit_message(source: _Source) -> str:
    """Say why a source gives nothing to apply or pay back."""
    if source.kind == DEBIT_NOTE:
        return (
            f"{source.number} leaves no credit on the supplier's account: it is "
            "not approved, or its bill still owed all of it."
        )
    return (
        f"{source.number} leaves no credit on the supplier's account: it is not "
        "completed, or its lines already came off the bill they were returned "
        "against."
    )


def _source_columns(source: _Source) -> dict[str, UUID | None]:
    """Return the application or refund columns naming a source."""
    return {
        "purchase_return_id": source.id if source.kind == PURCHASE_RETURN else None,
        "debit_note_id": source.id if source.kind == DEBIT_NOTE else None,
    }


def apply_supplier_credit(
    session: Session,
    *,
    firm_id: UUID,
    source_id: UUID,
    invoice_id: UUID,
    amount: Decimal,
    actor_id: UUID,
) -> SupplierCredit:
    """Set part of a supplier credit against one of the vendor's bills.

    ``source_id`` is the purchase return or debit note that gave the credit,
    locked for the check. ``invoice_id`` is a purchase bill or, since BUY-17,
    an opening bill -- whichever Record Payment offers for the supplier.

    Raises:
        ResourceNotFoundError: If the firm has no such return or debit note.
        ValidationError: If it gives no credit, has less left than asked, or
            the bill is not the vendor's, not approved, or owes less.

    """
    # Imported here: the payment service imports this module.
    from app.settlements.services.settlement_service import PaymentService

    asked = quantize_ledger(amount)
    if asked <= ZERO:
        raise ValidationError("An application must be for more than nothing.")
    source = _locked_source(session, firm_id=firm_id, source_id=source_id)
    found = supplier_credits(session, firm_id=firm_id, source_ids=[source.id])
    if not found:
        raise ValidationError(_no_credit_message(source))
    credit = found[0]
    if asked > credit.available_amount:
        raise ValidationError(
            f"{source.number} has only {credit.available_amount} of credit "
            "left to set against a bill."
        )
    bill = next(
        (
            record
            for record in PaymentService(session).outstanding_invoices(
                firm_id=firm_id, party_id=source.vendor_id
            )
            if record.invoice_id == invoice_id
        ),
        None,
    )
    if bill is None:
        raise ValidationError(
            "That bill is not this supplier's, is not approved, or is already "
            "settled in full."
        )
    if asked > bill.outstanding_amount:
        raise ValidationError(
            f"{bill.invoice_number} owes only {bill.outstanding_amount}."
        )
    application = SupplierCreditApplication(
        firm_id=firm_id,
        vendor_id=source.vendor_id,
        purchase_invoice_id=None if bill.is_opening_bill else invoice_id,
        vendor_opening_bill_id=invoice_id if bill.is_opening_bill else None,
        applied_on=utc_now().date(),
        amount=asked,
        created_by=actor_id,
        updated_by=actor_id,
        **_source_columns(source),
    )
    session.add(application)
    session.flush()
    record_audit(
        session,
        action="supplier_credit.applied",
        entity_type="supplier_credit_application",
        entity_id=application.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={
            "source": source.kind,
            "source_number": source.number,
            "purchase_invoice": bill.invoice_number,
            "amount": str(asked),
        },
    )
    return supplier_credits(session, firm_id=firm_id, source_ids=[source.id])[0]


def refund_supplier_credit(
    session: Session,
    *,
    firm_id: UUID,
    source_id: UUID,
    amount: Decimal,
    refunded_on: date,
    method: SettlementMethod,
    actor_id: UUID,
    reference: str | None = None,
    remarks: str | None = None,
) -> SupplierCreditRefund:
    """Receive money a supplier paid back against a credit (69.7, A4).

    Posts ``Dr cash or bank / Cr accounts payable`` and uses that much of the
    credit, under a lock on its source for the same reason applying it takes
    one. A return is paid back only when its outcome is a refund; one meant to
    be replaced or set against a bill is refused by name. A debit note's
    credit has no outcome: the supplier may set it off or pay it back. Does
    not commit.

    Raises:
        ResourceNotFoundError: If the firm has no such return or debit note.
        ValidationError: If a return is not a refund, the source gives no
            credit or has less left than asked, or the date is wrong.

    """
    from app.finance.services.control_accounts import ControlAccountService
    from app.finance.services.document_posting import DocumentPostingService
    from app.settlements.services.settlement_service import METHOD_PURPOSE

    asked = quantize_ledger(amount)
    if asked <= ZERO:
        raise ValidationError("A refund must be for more than nothing.")
    if refunded_on > utc_now().date():
        raise ValidationError("A refund cannot be received on a future date.")
    source = _locked_source(session, firm_id=firm_id, source_id=source_id)
    if source.kind == PURCHASE_RETURN and source.outcome != "REFUND":
        raise ValidationError(
            f"{source.number} is to come back as {source.outcome.lower()}, not a "
            "refund; change its outcome first."
        )
    found = supplier_credits(session, firm_id=firm_id, source_ids=[source.id])
    if not found:
        raise ValidationError(_no_credit_message(source))
    credit = found[0]
    if asked > credit.available_amount:
        raise ValidationError(
            f"{source.number} has only {credit.available_amount} of credit "
            "left to be paid back."
        )
    if refunded_on < source.on:
        raise ValidationError(
            "A refund is received on or after the "
            f"{'return' if source.kind == PURCHASE_RETURN else 'debit note'}, "
            f"{source.on.isoformat()}."
        )
    money_account_id = ControlAccountService(session).resolve(
        firm_id, METHOD_PURPOSE[method]
    )
    refund_id = uuid4()
    count = session.scalar(
        select(func.count())
        .select_from(SupplierCreditRefund)
        .where(
            SupplierCreditRefund.firm_id == firm_id,
            or_(
                SupplierCreditRefund.purchase_return_id == source.id,
                SupplierCreditRefund.debit_note_id == source.id,
            ),
        )
    )
    reference_number = f"{source.number}-RF{int(count or 0) + 1}"
    entry = DocumentPostingService(session).post_supplier_refund(
        firm_id=firm_id,
        refund_id=refund_id,
        reference_number=reference_number,
        refunded_on=refunded_on,
        amount=asked,
        money_account_id=money_account_id,
        actor_id=actor_id,
    )
    refund = SupplierCreditRefund(
        id=refund_id,
        firm_id=firm_id,
        vendor_id=source.vendor_id,
        refunded_on=refunded_on,
        amount=asked,
        method=method.value,
        ledger_account_id=money_account_id,
        reference=(reference or "").strip() or None,
        remarks=(remarks or "").strip() or None,
        status="POSTED",
        journal_entry_id=entry.id,
        created_by=actor_id,
        updated_by=actor_id,
        **_source_columns(source),
    )
    session.add(refund)
    session.flush()
    record_audit(
        session,
        action="supplier_credit.refunded",
        entity_type="supplier_credit_refund",
        entity_id=refund.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={
            "source": source.kind,
            "source_number": source.number,
            "amount": str(asked),
            "method": method.value,
            "refunded_on": refunded_on.isoformat(),
        },
    )
    return refund


def reverse_supplier_refund(
    session: Session,
    *,
    firm_id: UUID,
    refund_id: UUID,
    reason: str,
    actor_id: UUID,
) -> SupplierCreditRefund:
    """Take back a supplier refund recorded in error; does not commit.

    Posts the mirror of its journal and frees that much of the credit again.
    Refused once already reversed.
    """
    from app.finance.services.journal_engine import JournalEntryEngine

    if not reason.strip():
        raise ValidationError("Say why the refund is being reversed.")
    refund = session.get(SupplierCreditRefund, refund_id)
    if refund is None or refund.firm_id != firm_id or refund.is_deleted:
        raise ResourceNotFoundError("Supplier refund not found.")
    if refund.status != "POSTED":
        raise ValidationError("This refund has already been reversed.")
    source_id = refund.purchase_return_id or refund.debit_note_id
    assert source_id is not None
    _locked_source(session, firm_id=firm_id, source_id=source_id)
    mirror = JournalEntryEngine(session).reverse_entry(
        refund.journal_entry_id,
        firm_id=firm_id,
        reference_number=f"{refund.id.hex[:8].upper()}-REV",
        actor_id=actor_id,
    )
    refund.status = "REVERSED"
    refund.reversal_journal_entry_id = mirror.id
    refund.reversed_at = utc_now()
    refund.reversal_reason = reason.strip()
    refund.updated_by = actor_id
    session.flush()
    record_audit(
        session,
        action="supplier_credit.refund_reversed",
        entity_type="supplier_credit_refund",
        entity_id=refund.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={"amount": str(refund.amount), "reason": refund.reversal_reason},
    )
    return refund


def live_refunds(
    session: Session, *, firm_id: UUID, source_id: UUID
) -> list[SupplierCreditRefund]:
    """Return a return's or debit note's refunds, oldest first, reversed too."""
    return list(
        session.scalars(
            select(SupplierCreditRefund)
            .where(
                SupplierCreditRefund.firm_id == firm_id,
                or_(
                    SupplierCreditRefund.purchase_return_id == source_id,
                    SupplierCreditRefund.debit_note_id == source_id,
                ),
                SupplierCreditRefund.is_deleted.is_(False),
            )
            .order_by(SupplierCreditRefund.created_at.asc())
        ).all()
    )
