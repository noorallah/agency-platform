"""The post-dated cheque register (backlog 42.3, ACC-2, decision A80).

A cheque dated ahead is **held**, not posted: it clears no bill, moves no bank
book and counts as no collection until it can be banked. Depositing it records
the receipt (or, for the firm's own cheque, the payment) through the
settlement service a person would use, dated the day it was banked, so
everything downstream -- allocations, the customer's balance, TCS, the
collection reports -- treats it as the receipt it now is.

From there the bank answers. **Cleared** posts nothing more, as TallyPrime and
BUSY treat a PDC once it is converted. **Bounced** reverses the settlement
through its own reversal, dated the day the bank returned it, so the bills owe
again; the bank's fee for the return (Dr bank charges, Cr bank) and any charge
the firm makes the customer (Dr receivable, Cr cheque return charges -- outside
GST, CBIC circular 178/10/2022) post together in one journal of their own, and
the customer's charge is written to their account so the statement shows it.

A held cheque can be **cancelled** -- handed back, or replaced -- and nothing is
undone because nothing was posted. Re-presenting a bounced cheque is a new
cheque in the register, which is what the bank sees too.

**The firm's own cheque pays any account** (row F13, COL-11): a supplier, a
customer, an expense account or any other ledger account. `write` is the one
way in for all four, and the cheque becomes what that kind of payment already
is -- a payment, a refund, an expense, each through the service a person would
use, or for any other account a payment voucher (Dr the account, Cr the bank).
Dated today or before, it is presented in the same transaction; dated ahead,
it is held like any post-dated cheque and posts nothing until presented. A
returned cheque takes back whichever of those it became.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.customers.models import Customer
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.expenses.models import Expense
from app.expenses.schemas import ExpenseCreate
from app.expenses.services.expense_service import ExpenseService
from app.finance.models import AccountType, FirmControlAccount, LedgerAccount
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.money_accounts import KIND_BANK, money_accounts
from app.settlements.models import Settlement, SettlementDirection
from app.settlements.models.post_dated_cheque import (
    LIVE_STATUSES,
    ChequePaidTo,
    PostDatedCheque,
    PostDatedChequeStatus,
)
from app.settlements.schemas import (
    SettlementCreate,
    SettlementMethodEnum,
    SettlementModeEnum,
)
from app.settlements.schemas.post_dated_cheque import (
    ChequePaidToEnum,
    ChequeWrite,
    PostDatedChequeBounce,
    PostDatedChequeCreate,
    PostDatedChequeDeposit,
    PostDatedChequeResponse,
    PostDatedChequeStatusEnum,
)
from app.settlements.services.settlement_service import (
    PaymentService,
    ReceiptService,
    RefundService,
    SettlementService,
)
from app.vendors.models import Vendor

_HELD = PostDatedChequeStatus.HELD.value
_DEPOSITED = PostDatedChequeStatus.DEPOSITED.value
_SUPPLIER = ChequePaidTo.SUPPLIER.value
_CUSTOMER = ChequePaidTo.CUSTOMER.value
_EXPENSE = ChequePaidTo.EXPENSE.value
_ACCOUNT = ChequePaidTo.ACCOUNT.value

#: Account types a cheque is never written to as "any other account": an
#: expense account goes by the expense it becomes, and the other two hold no
#: balance a payee could be paid out of.
_NOT_PAYABLE_TYPES = frozenset(
    {
        AccountType.EXPENSE.value,
        AccountType.MEMO.value,
        AccountType.CONTROL.value,
    }
)


class PostDatedChequeService:
    """Hold a cheque dated ahead, bank it, and record the bank's answer."""

    def __init__(self, session: Session, *, direction: SettlementDirection) -> None:
        """Bind the service to a session and to one direction of cheque."""
        if direction not in (SettlementDirection.RECEIPT, SettlementDirection.PAYMENT):
            raise ValueError("A post-dated cheque is a receipt or a payment.")
        self._session = session
        self._direction = direction
        self._is_receipt = direction == SettlementDirection.RECEIPT

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _scoped(self, firm_id: UUID) -> Select[tuple[PostDatedCheque]]:
        """Select this firm's live rows in this service's direction."""
        return select(PostDatedCheque).where(
            PostDatedCheque.firm_id == firm_id,
            PostDatedCheque.direction == self._direction.value,
            PostDatedCheque.is_deleted.is_(False),
        )

    def list_cheques(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        status: str | None = None,
        party_id: UUID | None = None,
        due_on: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
    ) -> tuple[Sequence[PostDatedCheque], int]:
        """Return one page of the register in cheque-date order, and the total.

        ``due_on`` narrows to what can be banked that day: cheques still held
        whose date has come, the "deposit today" list.
        """
        statement = self._scoped(firm_id)
        if status:
            statement = statement.where(PostDatedCheque.status == status)
        if due_on is not None:
            statement = statement.where(
                PostDatedCheque.status == _HELD,
                PostDatedCheque.cheque_date <= due_on,
            )
        if party_id is not None:
            # The firm's own cheque pays a supplier, a customer or an account.
            statement = statement.where(
                PostDatedCheque.customer_id == party_id
                if self._is_receipt
                else or_(
                    PostDatedCheque.vendor_id == party_id,
                    PostDatedCheque.customer_id == party_id,
                    PostDatedCheque.paid_account_id == party_id,
                )
            )
        if date_from is not None:
            statement = statement.where(PostDatedCheque.cheque_date >= date_from)
        if date_to is not None:
            statement = statement.where(PostDatedCheque.cheque_date <= date_to)
        if search:
            statement = statement.where(
                PostDatedCheque.cheque_number.ilike(f"%{search.strip()}%")
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                PostDatedCheque.cheque_date.asc(),
                PostDatedCheque.cheque_number.asc(),
                PostDatedCheque.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, cheque_id: UUID, *, firm_id: UUID) -> PostDatedCheque:
        """Return one cheque.

        Raises:
            ResourceNotFoundError: If the firm has no such cheque this way.

        """
        row = self._session.scalar(
            self._scoped(firm_id).where(PostDatedCheque.id == cheque_id)
        )
        if row is None:
            raise ResourceNotFoundError("Post-dated cheque not found.")
        return row

    def responses(
        self, rows: Sequence[PostDatedCheque]
    ) -> list[PostDatedChequeResponse]:
        """Build the responses for a page, one read per table."""
        if not rows:
            return []
        parties: dict[UUID, tuple[str, str]] = {}
        wanted: tuple[
            tuple[type[Customer] | type[Vendor] | type[LedgerAccount], set[UUID]],
            ...,
        ] = (
            (Customer, {row.customer_id for row in rows if row.customer_id}),
            (Vendor, {row.vendor_id for row in rows if row.vendor_id}),
            (
                LedgerAccount,
                {
                    account_id
                    for row in rows
                    for account_id in (row.paid_account_id, row.bank_account_id)
                    if account_id
                },
            ),
        )
        for model, ids in wanted:
            if not ids:
                continue
            for party_id, code, name in self._session.execute(
                select(model.id, model.code, model.name).where(model.id.in_(ids))
            ):
                parties[party_id] = (code, name)
        settlement_ids = {row.settlement_id for row in rows if row.settlement_id}
        numbers: dict[UUID, str] = (
            {
                settlement_id: number
                for settlement_id, number in self._session.execute(
                    select(Settlement.id, Settlement.settlement_number).where(
                        Settlement.id.in_(settlement_ids)
                    )
                )
            }
            if settlement_ids
            else {}
        )
        expense_ids = {row.expense_id for row in rows if row.expense_id}
        expense_numbers: dict[UUID, str] = (
            {
                expense_id: number
                for expense_id, number in self._session.execute(
                    select(Expense.id, Expense.expense_number).where(
                        Expense.id.in_(expense_ids)
                    )
                )
            }
            if expense_ids
            else {}
        )
        today = firm_today(self._session, rows[0].firm_id if rows else None)
        answer: list[PostDatedChequeResponse] = []
        for row in rows:
            party_id = self._party_id(row)
            code, name = parties.get(party_id, ("", ""))
            kind = self._kind(row)
            answer.append(
                PostDatedChequeResponse(
                    id=row.id,
                    firm_id=row.firm_id,
                    direction=row.direction,
                    party_id=party_id,
                    party_code=code,
                    party_name=name,
                    paid_to_kind=(None if kind is None else ChequePaidToEnum(kind)),
                    payee_name=row.payee_name,
                    bank_account_id=row.bank_account_id,
                    bank_account_name=(
                        None
                        if row.bank_account_id is None
                        else parties.get(row.bank_account_id, ("", ""))[1]
                    ),
                    cheque_number=row.cheque_number,
                    cheque_date=row.cheque_date,
                    drawn_on_bank=row.drawn_on_bank,
                    amount=row.amount,
                    received_on=row.received_on,
                    narration=row.narration,
                    status=PostDatedChequeStatusEnum(row.status),
                    is_due=row.status == _HELD and row.cheque_date <= today,
                    settlement_id=row.settlement_id,
                    settlement_number=(
                        None
                        if row.settlement_id is None
                        else numbers.get(row.settlement_id)
                    ),
                    expense_id=row.expense_id,
                    expense_number=(
                        None
                        if row.expense_id is None
                        else expense_numbers.get(row.expense_id)
                    ),
                    journal_entry_id=row.journal_entry_id,
                    deposited_on=row.deposited_on,
                    cleared_on=row.cleared_on,
                    bounced_on=row.bounced_on,
                    bounce_reason=row.bounce_reason,
                    bank_charges_amount=row.bank_charges_amount,
                    customer_charge_amount=row.customer_charge_amount,
                    charges_journal_entry_id=row.charges_journal_entry_id,
                    cancelled_at=row.cancelled_at,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return answer

    # ------------------------------------------------------------------
    # Writes. Each flushes; the router commits.
    # ------------------------------------------------------------------

    def create(
        self, data: PostDatedChequeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Hold a cheque dated ahead. Nothing is posted.

        Raises:
            ValidationError: If the cheque is dated before it was received, or
                the same party's same cheque is already in the register.

        """
        settlements = self._settlements()
        party = settlements._require_party(firm_id=firm_id, party_id=data.party_id)
        if data.cheque_date < data.received_on:
            raise ValidationError(
                "The cheque is dated before it was received, so it is not "
                "post-dated: record it as a receipt or payment."
            )
        number = data.cheque_number.strip()
        if not number:
            raise ValidationError("Give the cheque number.")
        party_column = (
            PostDatedCheque.customer_id
            if self._is_receipt
            else PostDatedCheque.vendor_id
        )
        clash = self._session.scalar(
            self._scoped(firm_id).where(
                party_column == data.party_id,
                PostDatedCheque.cheque_number == number,
                PostDatedCheque.status.in_(LIVE_STATUSES),
            )
        )
        if clash is not None:
            raise ValidationError(
                f"Cheque {number} from {party.name} is already in the register."
            )
        row = PostDatedCheque(
            firm_id=firm_id,
            direction=self._direction.value,
            customer_id=data.party_id if self._is_receipt else None,
            vendor_id=None if self._is_receipt else data.party_id,
            paid_to_kind=None if self._is_receipt else _SUPPLIER,
            cheque_number=number,
            cheque_date=data.cheque_date,
            drawn_on_bank=(data.drawn_on_bank or "").strip() or None,
            amount=quantize_ledger(data.amount),
            received_on=data.received_on,
            narration=data.narration,
            status=_HELD,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit(
            row,
            "recorded",
            actor_id=actor_id,
            after={
                "cheque_number": number,
                "cheque_date": data.cheque_date.isoformat(),
                "amount": str(row.amount),
                "party": party.code,
            },
        )
        return row

    def deposit(
        self,
        cheque_id: UUID,
        data: PostDatedChequeDeposit,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PostDatedCheque:
        """Bank a held cheque: it becomes a posted receipt or payment.

        Raises:
            ValidationError: If it is not held, or is banked before its date.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _HELD, "banked")
        if data.deposited_on < row.cheque_date:
            raise ValidationError(
                f"Cheque {row.cheque_number} is dated "
                f"{row.cheque_date.isoformat()}; the bank will not take it "
                "before then."
            )
        return self._present(row, data, firm_id=firm_id, actor_id=actor_id)

    def account_choices(
        self, *, firm_id: UUID
    ) -> tuple[list[LedgerAccount], list[LedgerAccount], list[LedgerAccount]]:
        """Return what *Write a cheque* offers: banks, expenses, other accounts.

        The bank accounts are what a cheque can be drawn on. The other two
        lists are what one can pay besides a supplier or a customer, and they
        are the lists `write` holds a cheque to.
        """
        banks = [
            account
            for account, kind in money_accounts(self._session, firm_id)
            if kind == KIND_BANK
        ]
        expenses = ExpenseService(self._session).expense_accounts(firm_id)
        return banks, expenses, self._other_accounts(firm_id)

    def kind_of_account(self, account_id: UUID | None, *, firm_id: UUID) -> str:
        """Say what a cheque to this ledger account is: an expense, or not.

        The router asks before it writes, because the right a cheque needs
        follows from who it pays.
        """
        return self._require_paid_account(firm_id, account_id)[1]

    def _other_accounts(self, firm_id: UUID) -> list[LedgerAccount]:
        """Return the ledger accounts a cheque may pay that no document keeps.

        A loan, a deposit, capital, the owner's drawings, a fixed asset. Left
        out: the firm's own cash and bank accounts (money between them is a
        contra entry), expense accounts (those are an expense), and every
        account a control purpose claims -- receivables, payables, stock,
        tax -- because its balance is what its documents say, and a cheque
        straight to it would put the party's account and the ledger apart.
        """
        claimed = set(
            self._session.scalars(
                select(FirmControlAccount.ledger_account_id).where(
                    FirmControlAccount.firm_id == firm_id,
                    FirmControlAccount.is_deleted.is_(False),
                )
            )
        )
        money = {account.id for account, _ in money_accounts(self._session, firm_id)}
        rows = self._session.scalars(
            select(LedgerAccount)
            .where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                LedgerAccount.is_active.is_(True),
                LedgerAccount.account_type.not_in(_NOT_PAYABLE_TYPES),
            )
            .order_by(LedgerAccount.code.asc())
        ).all()
        return [row for row in rows if row.id not in claimed | money]

    def write(
        self, data: ChequeWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Write one of the firm's cheques, to any account (row F13).

        The cheque is recorded first, so it is never printed without a
        record. Dated today or before, it is presented in the same
        transaction and becomes the payment, refund, expense or payment
        voucher its payee makes it; dated ahead, it is held and posts
        nothing.

        Raises:
            ValidationError: If the bank account is not one of the firm's
                bank accounts, the account paid is not one a cheque may pay,
                the cheque number was already written on that bank account,
                or the payment it becomes is refused.

        """
        if self._is_receipt:
            raise ValueError("Only the firm's own cheque is written.")
        bank = self._require_bank(firm_id, data.bank_account_id)
        number = data.cheque_number.strip()
        if not number:
            raise ValidationError("Give the cheque number.")
        vendor_id = customer_id = paid_account_id = None
        if data.supplier_id is not None:
            vendor = PaymentService(self._session)._require_party(
                firm_id=firm_id, party_id=data.supplier_id
            )
            kind, vendor_id, code = _SUPPLIER, vendor.id, vendor.code
            name = getattr(vendor, "legal_name", None) or vendor.name
        elif data.customer_id is not None:
            customer = RefundService(self._session)._require_party(
                firm_id=firm_id, party_id=data.customer_id
            )
            kind, customer_id, code = _CUSTOMER, customer.id, customer.code
            name = customer.name
        else:
            account, kind = self._require_paid_account(firm_id, data.account_id)
            paid_account_id, code, name = account.id, account.code, account.name
        payee = (data.payee_name or "").strip() or name
        clash = self._session.scalar(
            self._scoped(firm_id).where(
                PostDatedCheque.bank_account_id == bank.id,
                PostDatedCheque.cheque_number == number,
                PostDatedCheque.status.in_(LIVE_STATUSES),
            )
        )
        if clash is not None:
            raise ValidationError(
                f"Cheque {number} on {bank.name} has already been written."
            )
        today = firm_today(self._session, firm_id)
        row = PostDatedCheque(
            firm_id=firm_id,
            direction=self._direction.value,
            customer_id=customer_id,
            vendor_id=vendor_id,
            paid_to_kind=kind,
            paid_account_id=paid_account_id,
            bank_account_id=bank.id,
            payee_name=payee[:200],
            cheque_number=number,
            cheque_date=data.cheque_date,
            drawn_on_bank=bank.name[:120],
            amount=quantize_ledger(data.amount),
            received_on=min(today, data.cheque_date),
            narration=(data.narration or "").strip() or None,
            status=_HELD,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._audit(
            row,
            "written",
            actor_id=actor_id,
            after={
                "cheque_number": number,
                "cheque_date": data.cheque_date.isoformat(),
                "amount": str(row.amount),
                "paid_to_kind": kind,
                "paid_to": code,
                "payee_name": row.payee_name,
                "bank_account": bank.code,
            },
        )
        if data.cheque_date <= today:
            # Not dated ahead, so it is the payment already.
            self._present(
                row,
                PostDatedChequeDeposit(deposited_on=data.cheque_date),
                firm_id=firm_id,
                actor_id=actor_id,
            )
        return row

    def _present(
        self,
        row: PostDatedCheque,
        data: PostDatedChequeDeposit,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PostDatedCheque:
        """Record a held cheque as the money it now is, by who it pays.

        A customer's cheque is a receipt. The firm's own is a payment to a
        supplier, a refund to a customer, an expense, or a payment voucher to
        any other account -- each through the service that already records
        it, so there is one way of posting each.
        """
        kind = self._kind(row)
        if data.allocations and kind not in (None, _SUPPLIER):
            raise ValidationError(
                "Only a cheque to a supplier or from a customer clears bills."
            )
        narration = row.narration or (
            f"Post-dated cheque {row.cheque_number}"
            if row.cheque_date > row.received_on
            else f"Cheque {row.cheque_number}"
        )
        became: dict[str, object]
        if kind in (None, _SUPPLIER, _CUSTOMER):
            settlement = self._settlements(row).create(
                SettlementCreate(
                    party_id=self._party_id(row),
                    settlement_date=data.deposited_on,
                    amount=row.amount,
                    method=SettlementMethodEnum.BANK,
                    payment_mode=SettlementModeEnum.CHEQUE,
                    instrument_reference=row.cheque_number,
                    instrument_date=row.cheque_date,
                    narration=narration,
                    allocations=data.allocations,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
                money_account_id=row.bank_account_id,
            )
            row.settlement_id = settlement.id
            became = {"settlement_number": settlement.settlement_number}
        elif kind == _EXPENSE:
            expense = ExpenseService(self._session).create(
                ExpenseCreate(
                    expense_date=data.deposited_on,
                    expense_account_id=self._paid_account_id(row),
                    paid_from_account_id=self._bank_account_id(row),
                    amount=row.amount,
                    payee=row.payee_name,
                    reference=f"Cheque {row.cheque_number}",
                    narration=row.narration,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            row.expense_id = expense.id
            became = {"expense_number": expense.expense_number}
        else:
            entry = DocumentPostingService(self._session).post_cheque_payment(
                firm_id=firm_id,
                cheque_id=row.id,
                reference=f"CHQ-{row.cheque_number}-{row.id.hex[:6].upper()}",
                paid_on=data.deposited_on,
                bank_account_id=self._bank_account_id(row),
                paid_account_id=self._paid_account_id(row),
                amount=row.amount,
                description=(
                    f"{narration} - {row.payee_name}" if row.payee_name else narration
                )[:500],
                actor_id=actor_id,
            )
            row.journal_entry_id = entry.id
            became = {"journal_reference": entry.reference_number}
        row.status = _DEPOSITED
        row.deposited_on = data.deposited_on
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "deposited",
            actor_id=actor_id,
            before={"status": _HELD},
            after={
                "status": _DEPOSITED,
                "deposited_on": data.deposited_on.isoformat(),
                **became,
            },
        )
        return row

    def clear(
        self, cheque_id: UUID, *, cleared_on: date, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Record that the bank honoured it. Nothing more is posted.

        Raises:
            ValidationError: If it was not banked, or clears before it was.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _DEPOSITED, "cleared")
        if row.deposited_on is not None and cleared_on < row.deposited_on:
            raise ValidationError(
                "A cheque cannot clear before the day it was banked "
                f"({row.deposited_on.isoformat()})."
            )
        row.status = PostDatedChequeStatus.CLEARED.value
        row.cleared_on = cleared_on
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "cleared",
            actor_id=actor_id,
            before={"status": _DEPOSITED},
            after={"status": row.status, "cleared_on": cleared_on.isoformat()},
        )
        return row

    def bounce(
        self,
        cheque_id: UUID,
        data: PostDatedChequeBounce,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PostDatedCheque:
        """Record a returned cheque: reverse what it posted, and its charges.

        Raises:
            ValidationError: If it was not banked, is returned before it was,
                or charges a supplier for the firm's own cheque.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _DEPOSITED, "returned")
        if row.deposited_on is not None and data.bounced_on < row.deposited_on:
            raise ValidationError(
                "A cheque cannot come back before the day it was banked "
                f"({row.deposited_on.isoformat()})."
            )
        bank_charges = quantize_ledger(data.bank_charges_amount or ZERO)
        customer_charge = quantize_ledger(data.customer_charge_amount or ZERO)
        if customer_charge > ZERO and not self._is_receipt:
            raise ValidationError(
                "Only a customer's cheque carries a return charge to the party."
            )
        reason = data.reason.strip()
        reference, bank_account_id = self._take_back(
            row,
            reason=f"Cheque {row.cheque_number} returned: {reason}",
            on=data.bounced_on,
            firm_id=firm_id,
            actor_id=actor_id,
        )
        if bank_charges > ZERO or customer_charge > ZERO:
            self._post_charges(
                row,
                reference=f"{reference}-RTN",
                bank_account_id=bank_account_id,
                bounced_on=data.bounced_on,
                bank_charges=bank_charges,
                customer_charge=customer_charge,
                firm_id=firm_id,
                actor_id=actor_id,
            )
        row.status = PostDatedChequeStatus.BOUNCED.value
        row.bounced_on = data.bounced_on
        row.bounce_reason = reason
        row.bank_charges_amount = bank_charges
        row.customer_charge_amount = customer_charge
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "bounced",
            actor_id=actor_id,
            before={"status": _DEPOSITED},
            after={
                "status": row.status,
                "bounced_on": data.bounced_on.isoformat(),
                "reason": reason,
                "bank_charges_amount": str(bank_charges),
                "customer_charge_amount": str(customer_charge),
            },
        )
        return row

    def cancel(
        self, cheque_id: UUID, *, reason: str, firm_id: UUID, actor_id: UUID
    ) -> PostDatedCheque:
        """Take a held cheque out of the register. Nothing was posted.

        Raises:
            ValidationError: If it has already been banked or cancelled.

        """
        row = self.get(cheque_id, firm_id=firm_id)
        self._require_status(row, _HELD, "cancelled")
        row.status = PostDatedChequeStatus.CANCELLED.value
        row.cancelled_at = utc_now()
        row.cancel_reason = reason.strip()
        row.updated_by = actor_id
        self._session.flush()
        self._audit(
            row,
            "cancelled",
            actor_id=actor_id,
            before={"status": _HELD},
            after={"status": row.status, "reason": row.cancel_reason},
        )
        return row

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _settlements(self, row: PostDatedCheque | None = None) -> SettlementService:
        """Return the settlement service a cheque is recorded through.

        A customer's cheque is a receipt; the firm's own is a payment, or a
        refund where it pays a customer.
        """
        if self._is_receipt:
            return ReceiptService(self._session)
        if row is not None and self._kind(row) == _CUSTOMER:
            return RefundService(self._session)
        return PaymentService(self._session)

    def _kind(self, row: PostDatedCheque) -> str | None:
        """Return who the firm's cheque pays; None for a customer's cheque.

        A cheque issued before the kind was kept is to a supplier.
        """
        if self._is_receipt:
            return None
        return row.paid_to_kind or _SUPPLIER

    def _party_id(self, row: PostDatedCheque) -> UUID:
        """Return the customer, supplier or account the cheque is with."""
        party = (
            row.customer_id
            if self._is_receipt
            else row.vendor_id or row.customer_id or row.paid_account_id
        )
        if party is None:  # pragma: no cover - the check constraint forbids it
            raise ValidationError("The cheque has no party.")
        return party

    @staticmethod
    def _paid_account_id(row: PostDatedCheque) -> UUID:
        """Return the ledger account a cheque to an account pays."""
        if row.paid_account_id is None:  # pragma: no cover - set by `write`
            raise ValidationError("The cheque names no account.")
        return row.paid_account_id

    @staticmethod
    def _bank_account_id(row: PostDatedCheque) -> UUID:
        """Return the bank account a written cheque is drawn on."""
        if row.bank_account_id is None:  # pragma: no cover - set by `write`
            raise ValidationError("The cheque names no bank account.")
        return row.bank_account_id

    def _require_bank(self, firm_id: UUID, account_id: UUID) -> LedgerAccount:
        """Return one of the firm's bank accounts or refuse.

        Raises:
            ResourceNotFoundError: If the firm keeps no such money account.
            ValidationError: If it is a cash account.

        """
        for account, kind in money_accounts(self._session, firm_id):
            if account.id != account_id:
                continue
            if kind != KIND_BANK:
                raise ValidationError(
                    f"{account.name} is a cash account; a cheque is drawn on "
                    "a bank account."
                )
            return account
        raise ResourceNotFoundError("Bank account not found.")

    def _require_paid_account(
        self, firm_id: UUID, account_id: UUID | None
    ) -> tuple[LedgerAccount, str]:
        """Return the account a cheque pays and the kind that makes it.

        Raises:
            ResourceNotFoundError: If the firm has no such account.
            ValidationError: If a cheque may not be written to it.

        """
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Account not found.")
        if account.account_type == AccountType.EXPENSE.value:
            offered = ExpenseService(self._session).expense_accounts(firm_id)
            if account.id in {row.id for row in offered}:
                return account, _EXPENSE
        elif account.id in {row.id for row in self._other_accounts(firm_id)}:
            return account, _ACCOUNT
        if account.id in {row.id for row, _ in money_accounts(self._session, firm_id)}:
            raise ValidationError(
                f"{account.name} is one of the firm's own cash or bank "
                "accounts: money moved between them is a contra entry, not a "
                "cheque to a payee."
            )
        raise ValidationError(
            f"A cheque cannot be written to {account.name}: it is kept by its "
            "own documents, or is not in use."
        )

    def _take_back(
        self,
        row: PostDatedCheque,
        *,
        reason: str,
        on: date,
        firm_id: UUID,
        actor_id: UUID,
    ) -> tuple[str, UUID]:
        """Undo what a returned cheque became.

        Returns the number of what was undone, which the charges' journal is
        referenced from, and the bank account the money moved through.
        """
        if row.settlement_id is not None:
            settlement = self._settlements(row).reverse(
                row.settlement_id,
                firm_id=firm_id,
                actor_id=actor_id,
                reason=reason,
                on=on,
            )
            return settlement.settlement_number, settlement.ledger_account_id
        if row.expense_id is not None:
            expense = ExpenseService(self._session).cancel(
                row.expense_id, firm_id=firm_id, actor_id=actor_id, reason=reason
            )
            return expense.expense_number, expense.paid_from_account_id
        if row.journal_entry_id is not None:
            journals = JournalEntryEngine(self._session)
            entry = journals.get_entry(row.journal_entry_id, firm_id=firm_id)
            mirror = journals.reverse_entry(
                entry.id,
                firm_id=firm_id,
                reference_number=f"{entry.reference_number}-REV",
                journal_date=on,
                actor_id=actor_id,
            )
            row.reversal_journal_entry_id = mirror.id
            return entry.reference_number, self._bank_account_id(row)
        # One of the three is set together with DEPOSITED.
        raise ValidationError(  # pragma: no cover
            "The cheque was banked without a record."
        )

    @staticmethod
    def _require_status(row: PostDatedCheque, wanted: str, action: str) -> None:
        """Refuse a transition from any state but the one it starts from."""
        if row.status != wanted:
            raise ValidationError(
                f"Cheque {row.cheque_number} is {row.status.lower()}, so it "
                f"cannot be {action}."
            )

    def _post_charges(
        self,
        row: PostDatedCheque,
        *,
        reference: str,
        bank_account_id: UUID,
        bounced_on: date,
        bank_charges: Decimal,
        customer_charge: Decimal,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Post the return's charges, and put the customer's on their account."""
        entry = DocumentPostingService(self._session).post_cheque_return_charges(
            firm_id=firm_id,
            cheque_id=row.id,
            reference=reference,
            bounced_on=bounced_on,
            bank_account_id=bank_account_id,
            bank_charges_amount=bank_charges,
            customer_charge_amount=customer_charge,
            description=f"Cheque {row.cheque_number} returned",
            actor_id=actor_id,
        )
        row.charges_journal_entry_id = entry.id
        if customer_charge > ZERO and row.customer_id is not None:
            transaction = CustomerService(self._session).post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=(
                        CustomerReceivableTransactionType.CHEQUE_RETURN_CHARGE
                    ),
                    amount=customer_charge,
                    transaction_date=bounced_on,
                    reference_type="post_dated_cheque",
                    reference_id=row.id,
                    reference_number=reference,
                    remarks=f"Charge for cheque {row.cheque_number} returned.",
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
                commit=False,
            )
            row.charge_receivable_transaction_id = transaction.id

    def _audit(
        self,
        row: PostDatedCheque,
        event: str,
        *,
        actor_id: UUID,
        after: dict[str, object],
        before: dict[str, object] | None = None,
    ) -> None:
        """Write one audit row for a step in the cheque's life."""
        record_audit(
            self._session,
            action=f"post_dated_cheque.{event}",
            entity_type="post_dated_cheque",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=before,
            after_data=after,
        )
