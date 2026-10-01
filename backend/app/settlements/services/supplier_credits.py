"""Supplier credit: what a purchase return left on the vendor's account.

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
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.chunks import over_chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_money
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.purchase_invoice.models import PurchaseInvoice

if TYPE_CHECKING:
    from app.purchase_return.models import PurchaseReturn

from app.settlements.models import (
    SettlementMethod,
    SupplierCreditApplication,
    SupplierCreditRefund,
)

#: The return states whose posting stands: completing debits payables, a
#: cancelled return has taken that back, and a draft has not posted.
CREDITING_RETURN_STATES = ("COMPLETED", "CLOSED")


@dataclass
class SupplierCredit:
    """One return's credit on the vendor's account, and what is left of it."""

    purchase_return_id: UUID
    return_number: str
    return_date: date
    vendor_id: UUID
    credit_amount: Decimal
    applied_amount: Decimal
    applied_to: list[str] = field(default_factory=list)
    #: What the supplier has paid back against it (backlog 69 row 7).
    refunded_amount: Decimal = ZERO
    #: CREDIT, REPLACEMENT or REFUND: what the return comes back as.
    outcome: str = "CREDIT"

    @property
    def available_amount(self) -> Decimal:
        """Return what can still be set against a bill or paid back."""
        return max(
            self.credit_amount - self.applied_amount - self.refunded_amount, ZERO
        )


def supplier_credits(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID | None = None,
    purchase_return_ids: Sequence[UUID] | None = None,
) -> list[SupplierCredit]:
    """Return each standing return's supplier credit, oldest first.

    A return's credit is what its posting debited payables with, less what its
    bill-sourced lines took off their own bills -- so a return raised from a
    goods receipt gives all of it -- plus whatever of those lines the bill
    could not absorb because it was already paid (D-BUY-20).

    Args:
        session: The firm's store.
        firm_id: The firm.
        vendor_id: Only this vendor's returns, where given.
        purchase_return_ids: Only these returns, where given.

    Returns:
        One entry per return that gives any credit, applied or not.

    """
    return [
        credit
        for credit in _all_credits(
            session,
            firm_id=firm_id,
            vendor_id=vendor_id,
            purchase_return_ids=purchase_return_ids,
        )
        if credit.credit_amount > ZERO
    ]


def _all_credits(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID | None = None,
    purchase_return_ids: Sequence[UUID] | None = None,
) -> list[SupplierCredit]:
    """Return every standing return's credit figures, a credit of nothing too.

    Args:
        session: The firm's store.
        firm_id: The firm.
        vendor_id: Only this vendor's returns, where given.
        purchase_return_ids: Only these returns, where given.

    Returns:
        One entry per completed return, whatever it gives.

    """
    # Imported here: the return module imports settlement-adjacent models.
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    statement = select(PurchaseReturn).where(
        PurchaseReturn.firm_id == firm_id,
        PurchaseReturn.is_deleted.is_(False),
        PurchaseReturn.status.in_(CREDITING_RETURN_STATES),
    )
    if vendor_id is not None:
        statement = statement.where(PurchaseReturn.vendor_id == vendor_id)
    if purchase_return_ids is not None:
        statement = statement.where(PurchaseReturn.id.in_(purchase_return_ids))
    returns = session.scalars(
        statement.order_by(
            PurchaseReturn.return_date.asc(), PurchaseReturn.return_number.asc()
        )
    ).all()
    if not returns:
        return []
    ids = [row.id for row in returns]
    billed = {
        return_id: Decimal(str(total))
        for return_id, total in session.execute(
            select(
                PurchaseReturnLine.purchase_return_id,
                func.coalesce(func.sum(PurchaseReturnLine.net_amount), 0),
            )
            .where(
                PurchaseReturnLine.purchase_return_id.in_(ids),
                PurchaseReturnLine.source_document_type == "PURCHASE_INVOICE",
                PurchaseReturnLine.is_deleted.is_(False),
            )
            .group_by(PurchaseReturnLine.purchase_return_id)
        ).all()
    }
    applied: dict[UUID, Decimal] = {}
    applied_to: dict[UUID, list[str]] = {}
    for return_id, amount, number in session.execute(
        select(
            SupplierCreditApplication.purchase_return_id,
            SupplierCreditApplication.amount,
            PurchaseInvoice.invoice_number,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == SupplierCreditApplication.purchase_invoice_id,
        )
        .where(
            SupplierCreditApplication.firm_id == firm_id,
            SupplierCreditApplication.purchase_return_id.in_(ids),
            SupplierCreditApplication.is_deleted.is_(False),
        )
        .order_by(SupplierCreditApplication.created_at.asc())
    ).all():
        applied[return_id] = applied.get(return_id, ZERO) + quantize_ledger(
            Decimal(str(amount))
        )
        applied_to.setdefault(return_id, []).append(number)
    refunded: dict[UUID, Decimal] = {}
    for return_id, amount in session.execute(
        select(
            SupplierCreditRefund.purchase_return_id, SupplierCreditRefund.amount
        ).where(
            SupplierCreditRefund.firm_id == firm_id,
            SupplierCreditRefund.purchase_return_id.in_(ids),
            SupplierCreditRefund.is_deleted.is_(False),
            SupplierCreditRefund.status == "POSTED",
        )
    ).all():
        refunded[return_id] = refunded.get(return_id, ZERO) + quantize_ledger(
            Decimal(str(amount))
        )
    spilled = _spilled_over(session, firm_id=firm_id, purchase_return_ids=ids)
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
    return credits


def _bill_parts(
    session: Session,
    *,
    firm_id: UUID,
    purchase_return_ids: Sequence[UUID] | None = None,
    invoice_ids: Sequence[UUID] | None = None,
) -> list[tuple[UUID, UUID, Decimal]]:
    """Return (return, bill, amount) for what standing returns took off bills.

    Newest return first, the order in which a bill that cannot absorb them all
    turns them into credit. Narrowed to some returns, some bills, or both.
    """
    from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

    statement = (
        select(
            PurchaseReturnLine.purchase_return_id,
            PurchaseReturnLine.source_document_id,
            func.coalesce(func.sum(PurchaseReturnLine.net_amount), 0),
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
        .order_by(
            PurchaseReturn.return_date.desc(),
            PurchaseReturn.return_number.desc(),
            PurchaseReturnLine.source_document_id.asc(),
        )
    )
    if purchase_return_ids is not None:
        statement = statement.where(
            PurchaseReturnLine.purchase_return_id.in_(purchase_return_ids)
        )
    if invoice_ids is not None:
        statement = statement.where(
            PurchaseReturnLine.source_document_id.in_(invoice_ids)
        )
    return [
        (return_id, bill_id, quantize_ledger(Decimal(str(amount))))
        for return_id, bill_id, amount in session.execute(statement).all()
    ]


def _spilled_over(
    session: Session, *, firm_id: UUID, purchase_return_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Return what of each return its bills could not absorb (D-BUY-20).

    A bill already paid has nothing left for a return off its lines to come
    off, so the excess of everything taken off the bill over its total is the
    supplier's to give back. It falls to the bill's returns newest first --
    the earlier ones fitted when they were made -- each up to what it took off
    that bill.
    """
    from app.settlements.services.settlement_service import PaymentService

    bills = sorted(
        {
            bill_id
            for _, bill_id, _ in _bill_parts(
                session, firm_id=firm_id, purchase_return_ids=purchase_return_ids
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
    for return_id, bill_id, amount in _bill_parts(
        session, firm_id=firm_id, invoice_ids=bills
    ):
        share = min(amount, left.get(bill_id, ZERO))
        if share <= ZERO:
            continue
        left[bill_id] -= share
        spilled[return_id] = spilled.get(return_id, ZERO) + share
    return spilled


@over_chunks("invoice_ids")
def drawn_back_onto_bills(
    session: Session, *, firm_id: UUID, invoice_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Return what goes back on each bill from credit its returns no longer give.

    The part of a return its paid bill could not absorb is credit (D-BUY-20).
    Once that credit has been set against another bill or paid back, and the
    first bill then owes more again -- its payment reversed -- the return gives
    less credit than was used. The difference was taken off the first bill
    twice, so it goes back on it, and the payables list and the ledger agree.
    """
    if not invoice_ids:
        return {}
    used = set(
        session.scalars(
            select(SupplierCreditApplication.purchase_return_id).where(
                SupplierCreditApplication.firm_id == firm_id,
                SupplierCreditApplication.is_deleted.is_(False),
            )
        ).all()
    ) | set(
        session.scalars(
            select(SupplierCreditRefund.purchase_return_id).where(
                SupplierCreditRefund.firm_id == firm_id,
                SupplierCreditRefund.is_deleted.is_(False),
                SupplierCreditRefund.status == "POSTED",
            )
        ).all()
    )
    if not used:
        return {}
    returns = sorted(
        {
            return_id
            for return_id, _, _ in _bill_parts(
                session, firm_id=firm_id, invoice_ids=invoice_ids
            )
            if return_id in used
        }
    )
    if not returns:
        return {}
    short = {
        credit.purchase_return_id: max(
            credit.applied_amount + credit.refunded_amount - credit.credit_amount,
            ZERO,
        )
        for credit in _all_credits(
            session, firm_id=firm_id, purchase_return_ids=returns
        )
    }
    wanted = set(invoice_ids)
    drawn: dict[UUID, Decimal] = {}
    for return_id, bill_id, amount in _bill_parts(
        session, firm_id=firm_id, purchase_return_ids=returns
    ):
        share = min(amount, short.get(return_id, ZERO))
        if share <= ZERO:
            continue
        short[return_id] -= share
        if bill_id in wanted:
            drawn[bill_id] = drawn.get(bill_id, ZERO) + share
    return drawn


@over_chunks("invoice_ids")
def credit_applied_against(
    session: Session, *, firm_id: UUID, invoice_ids: Sequence[UUID]
) -> dict[UUID, Decimal]:
    """Sum the supplier credit set against each bill."""
    if not invoice_ids:
        return {}
    return {
        invoice_id: quantize_ledger(Decimal(str(total)))
        for invoice_id, total in session.execute(
            select(
                SupplierCreditApplication.purchase_invoice_id,
                func.coalesce(func.sum(SupplierCreditApplication.amount), 0),
            )
            .where(
                SupplierCreditApplication.firm_id == firm_id,
                SupplierCreditApplication.purchase_invoice_id.in_(invoice_ids),
                SupplierCreditApplication.is_deleted.is_(False),
            )
            .group_by(SupplierCreditApplication.purchase_invoice_id)
        ).all()
    }


def withdraw_credit_applications(
    session: Session,
    *,
    firm_id: UUID,
    actor_id: UUID,
    purchase_return_id: UUID | None = None,
    purchase_invoice_id: UUID | None = None,
) -> int:
    """Withdraw the credit set against a bill, when the return or bill goes.

    Cancelling the return takes its payables debit back, so the credit it gave
    is gone and the bill owes that part again. Cancelling the bill takes its
    payable back, so the credit set against it is free again. Nothing posts:
    each document's own cancellation already reversed its journal.

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
    if purchase_invoice_id is not None:
        statement = statement.where(
            SupplierCreditApplication.purchase_invoice_id == purchase_invoice_id
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
                "purchase_return_id": str(row.purchase_return_id),
                "purchase_invoice_id": str(row.purchase_invoice_id),
                "amount": str(row.amount),
            },
        )
    return len(rows)


def apply_supplier_credit(
    session: Session,
    *,
    firm_id: UUID,
    purchase_return_id: UUID,
    invoice_id: UUID,
    amount: Decimal,
    actor_id: UUID,
) -> SupplierCredit:
    """Set part of a return's supplier credit against one of the vendor's bills.

    The return is locked for the check, because what is left of it is a sum
    and two applications racing would each see the whole of it (a guard on a
    sum takes a lock on the thing consumed).

    Raises:
        ResourceNotFoundError: If the firm has no such return.
        ValidationError: If the return gives no credit, has less left than
            asked, or the bill is not the vendor's, not approved, or owes less.

    """
    # Imported here: the return module imports settlement-adjacent models, and
    # the payment service imports this one.
    from app.purchase_return.models import PurchaseReturn
    from app.settlements.services.settlement_service import PaymentService

    asked = quantize_ledger(amount)
    if asked <= ZERO:
        raise ValidationError("An application must be for more than nothing.")
    row = session.scalar(
        select(PurchaseReturn)
        .where(
            PurchaseReturn.id == purchase_return_id,
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if row is None:
        raise ResourceNotFoundError("Purchase return not found.")
    found = supplier_credits(session, firm_id=firm_id, purchase_return_ids=[row.id])
    if not found:
        raise ValidationError(
            f"{row.return_number} leaves no credit on the supplier's account: "
            "it is not completed, or its lines already came off the bill they "
            "were returned against."
        )
    credit = found[0]
    if asked > credit.available_amount:
        raise ValidationError(
            f"{row.return_number} has only {credit.available_amount} of credit "
            "left to set against a bill."
        )
    bill = next(
        (
            record
            for record in PaymentService(session).outstanding_invoices(
                firm_id=firm_id, party_id=row.vendor_id
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
    if bill.is_opening_bill:
        # The application names a purchase invoice, and an opening bill is not
        # one. Setting a return's credit against day-one debt is a real need
        # but a separate change; until then it is refused by name rather than
        # failing on the foreign key.
        raise ValidationError(
            f"{bill.invoice_number} is an opening bill; supplier credit is set "
            "against purchase bills only."
        )
    if asked > bill.outstanding_amount:
        raise ValidationError(
            f"{bill.invoice_number} owes only {bill.outstanding_amount}."
        )
    application = SupplierCreditApplication(
        firm_id=firm_id,
        vendor_id=row.vendor_id,
        purchase_return_id=row.id,
        purchase_invoice_id=invoice_id,
        applied_on=utc_now().date(),
        amount=asked,
        created_by=actor_id,
        updated_by=actor_id,
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
            "purchase_return": row.return_number,
            "purchase_invoice": bill.invoice_number,
            "amount": str(asked),
        },
    )
    return supplier_credits(session, firm_id=firm_id, purchase_return_ids=[row.id])[0]


def _locked_return(
    session: Session, *, firm_id: UUID, purchase_return_id: UUID
) -> "PurchaseReturn":
    """Return the purchase return, locked: what is left of it is a sum."""
    from app.purchase_return.models import PurchaseReturn

    row = session.scalar(
        select(PurchaseReturn)
        .where(
            PurchaseReturn.id == purchase_return_id,
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if row is None:
        raise ResourceNotFoundError("Purchase return not found.")
    return row


def refund_supplier_credit(
    session: Session,
    *,
    firm_id: UUID,
    purchase_return_id: UUID,
    amount: Decimal,
    refunded_on: date,
    method: SettlementMethod,
    actor_id: UUID,
    reference: str | None = None,
    remarks: str | None = None,
) -> SupplierCreditRefund:
    """Receive money a supplier paid back against a return's credit (69.7).

    Posts ``Dr cash or bank / Cr accounts payable`` and uses that much of the
    credit, under a lock on the return for the same reason applying it takes
    one. Only a return whose outcome is a refund is paid back; one meant to be
    replaced or set against a bill is refused by name. Does not commit.

    Raises:
        ResourceNotFoundError: If the firm has no such return.
        ValidationError: If the return is not a refund, gives no credit, has
            less left than asked, or the date is in the future.

    """
    from app.finance.services.control_accounts import ControlAccountService
    from app.finance.services.document_posting import DocumentPostingService
    from app.settlements.services.settlement_service import METHOD_PURPOSE

    asked = quantize_ledger(amount)
    if asked <= ZERO:
        raise ValidationError("A refund must be for more than nothing.")
    if refunded_on > utc_now().date():
        raise ValidationError("A refund cannot be received on a future date.")
    row = _locked_return(
        session, firm_id=firm_id, purchase_return_id=purchase_return_id
    )
    if (row.outcome or "CREDIT") != "REFUND":
        raise ValidationError(
            f"{row.return_number} is to come back as "
            f"{(row.outcome or 'CREDIT').lower()}, not a refund; change its "
            "outcome first."
        )
    found = supplier_credits(session, firm_id=firm_id, purchase_return_ids=[row.id])
    if not found:
        raise ValidationError(
            f"{row.return_number} leaves no credit on the supplier's account: "
            "it is not completed, or its lines already came off the bill they "
            "were returned against."
        )
    credit = found[0]
    if asked > credit.available_amount:
        raise ValidationError(
            f"{row.return_number} has only {credit.available_amount} of credit "
            "left to be paid back."
        )
    if refunded_on < row.return_date:
        raise ValidationError(
            f"A refund is received on or after the return, "
            f"{row.return_date.isoformat()}."
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
            SupplierCreditRefund.purchase_return_id == row.id,
        )
    )
    reference_number = f"{row.return_number}-RF{int(count or 0) + 1}"
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
        vendor_id=row.vendor_id,
        purchase_return_id=row.id,
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
            "purchase_return": row.return_number,
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

    Posts the mirror of its journal and frees that much of the return's
    credit again. Refused once already reversed.
    """
    from app.finance.services.journal_engine import JournalEntryEngine

    if not reason.strip():
        raise ValidationError("Say why the refund is being reversed.")
    refund = session.get(SupplierCreditRefund, refund_id)
    if refund is None or refund.firm_id != firm_id or refund.is_deleted:
        raise ResourceNotFoundError("Supplier refund not found.")
    if refund.status != "POSTED":
        raise ValidationError("This refund has already been reversed.")
    _locked_return(
        session, firm_id=firm_id, purchase_return_id=refund.purchase_return_id
    )
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
    session: Session, *, firm_id: UUID, purchase_return_id: UUID
) -> list[SupplierCreditRefund]:
    """Return a return's refunds, oldest first, reversed ones included."""
    return list(
        session.scalars(
            select(SupplierCreditRefund)
            .where(
                SupplierCreditRefund.firm_id == firm_id,
                SupplierCreditRefund.purchase_return_id == purchase_return_id,
                SupplierCreditRefund.is_deleted.is_(False),
            )
            .order_by(SupplierCreditRefund.created_at.asc())
        ).all()
    )
