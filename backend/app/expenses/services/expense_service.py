"""Record money the firm spent, and put it in the ledger in the same act.

The gap this closes: rent, fuel and salaries reached the profit and loss only
through a journal typed by hand, which needs the authority to post journals.
Tally's payment voucher and Zoho Books' *Expenses* let a clerk say what was
spent, how much, and where it came from, and write the journal for them. This
is that.

Like a settlement, an expense is a document that posts, and the posting is
what makes it real: if the journal cannot be written -- no open period, an
account that needs a cost centre -- the expense is refused rather than recorded
half-way. The service stages and flushes; the router commits once.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.expenses.models import Expense, ExpenseStatus
from app.expenses.schemas import ExpenseCreate
from app.finance.models import AccountType, FirmControlAccount, LedgerAccount
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.journal_engine import quantize_money as quantize_ledger

#: The control purposes a paid-from account may carry. Cash and bank are what
#: money is paid out of; every other purpose belongs to the documents that
#: keep it -- paying rent "from" Inventory or Trade Receivables would move a
#: balance its sub-ledger knows nothing about.
_MONEY_PURPOSES = frozenset({"CASH", "BANK"})


class ExpenseService(TransactionalDocumentService):
    """Record an expense, post it, and cancel it."""

    DOCUMENT = DocumentTypeSpec(
        code="EXPENSE",
        name="Expense",
        description="Money spent on running the firm",
        category="FINANCE",
        module="expenses",
        prefix="EXP",
        states=(
            DocumentStateSpec("POSTED", "Posted", 1),
            DocumentStateSpec("CANCELLED", "Cancelled", 2, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus the ledger collaborators."""
        super().__init__(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ------------------------------------------------------------------
    # Accounts the form offers
    # ------------------------------------------------------------------

    def _purposes_by_account(self, firm_id: UUID) -> dict[UUID, set[str]]:
        """Return every control purpose each of the firm's accounts is mapped to."""
        mapped: dict[UUID, set[str]] = {}
        for account_id, purpose in self._session.execute(
            select(
                FirmControlAccount.ledger_account_id, FirmControlAccount.purpose
            ).where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
            )
        ).all():
            mapped.setdefault(account_id, set()).add(purpose)
        return mapped

    def _live_accounts(self, firm_id: UUID, account_type: str) -> list[LedgerAccount]:
        """Return the firm's active accounts of one type, by code."""
        return list(
            self._session.scalars(
                select(LedgerAccount)
                .where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.account_type == account_type,
                    LedgerAccount.is_active.is_(True),
                    LedgerAccount.is_deleted.is_(False),
                )
                .order_by(LedgerAccount.code.asc())
            ).all()
        )

    def expense_accounts(self, firm_id: UUID) -> list[LedgerAccount]:
        """Return the EXPENSE accounts an expense may be booked to.

        An account a document posts to -- Purchases, Cost of Goods Sold,
        Commission, Loyalty -- is left out: its balance is what those
        documents say, and rent booked to Cost of Goods Sold would misstate
        the gross margin with nothing on the record to explain it.
        """
        mapped = self._purposes_by_account(firm_id)
        return [
            account
            for account in self._live_accounts(firm_id, AccountType.EXPENSE.value)
            if account.id not in mapped
        ]

    def paid_from_accounts(self, firm_id: UUID) -> list[LedgerAccount]:
        """Return the ASSET accounts an expense may be paid out of.

        Cash and Bank, and any asset account the firm opened itself (a second
        bank account, petty cash). Receivables, inventory and input tax are
        mapped to their own purposes and left out.
        """
        mapped = self._purposes_by_account(firm_id)
        return [
            account
            for account in self._live_accounts(firm_id, AccountType.ASSET.value)
            if mapped.get(account.id, set()) <= _MONEY_PURPOSES
        ]

    def _require_account(
        self,
        account_id: UUID,
        *,
        firm_id: UUID,
        offered: Sequence[LedgerAccount],
        role: str,
        expected: str,
    ) -> LedgerAccount:
        """Return the chosen account, or refuse it by name and say why."""
        for candidate in offered:
            if candidate.id == account_id:
                return candidate
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ValidationError(f"The {role} account was not found in this firm.")
        if not account.is_active:
            raise ValidationError(
                f"{account.code} {account.name} is inactive and cannot be the "
                f"{role} account."
            )
        if account.account_type != expected:
            raise ValidationError(
                f"{account.code} {account.name} is an {account.account_type} "
                f"account; the {role} account must be an {expected} account."
            )
        raise ValidationError(
            f"{account.code} {account.name} is kept by the firm's documents and "
            f"cannot be the {role} account of an expense."
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def _scoped(
        statement: Select[tuple[Expense]], firm_id: UUID
    ) -> Select[tuple[Expense]]:
        """Restrict a query to this firm's live expenses."""
        return statement.where(
            Expense.firm_id == firm_id, Expense.is_deleted.is_(False)
        )

    def list_expenses(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str = "",
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[Expense], int]:
        """Return one page of expenses, newest first.

        The search matches the number, the payee, the reference, the narration
        and the expense account's code or name; ``date_from`` / ``date_to``
        bound the expense date inclusively.
        """
        statement = self._scoped(select(Expense), firm_id)
        if status:
            statement = statement.where(Expense.status == status.strip().upper())
        if date_from is not None:
            statement = statement.where(Expense.expense_date >= date_from)
        if date_to is not None:
            statement = statement.where(Expense.expense_date <= date_to)
        if search.strip():
            pattern = f"%{search.strip()}%"
            accounts = select(LedgerAccount.id).where(
                LedgerAccount.firm_id == firm_id,
                or_(
                    LedgerAccount.name.ilike(pattern),
                    LedgerAccount.code.ilike(pattern),
                ),
            )
            statement = statement.where(
                or_(
                    Expense.expense_number.ilike(pattern),
                    Expense.payee.ilike(pattern),
                    Expense.reference.ilike(pattern),
                    Expense.narration.ilike(pattern),
                    Expense.expense_account_id.in_(accounts),
                )
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                Expense.expense_date.desc(), Expense.expense_number.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, expense_id: UUID, *, firm_id: UUID) -> Expense:
        """Return one expense or raise when it is unavailable."""
        row = self._session.scalar(
            self._scoped(select(Expense), firm_id).where(Expense.id == expense_id)
        )
        if row is None:
            raise ResourceNotFoundError("Expense not found.")
        return row

    def accounts_named(self, rows: Sequence[Expense]) -> dict[UUID, LedgerAccount]:
        """Return every account the given expenses name, in one read."""
        ids = {row.expense_account_id for row in rows} | {
            row.paid_from_account_id for row in rows
        }
        if not ids:
            return {}
        return {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount).where(LedgerAccount.id.in_(ids))
            ).all()
        }

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(self, data: ExpenseCreate, *, firm_id: UUID, actor_id: UUID) -> Expense:
        """Record one expense and post its journal. Staged; the caller commits."""
        expense_account = self._require_account(
            data.expense_account_id,
            firm_id=firm_id,
            offered=self.expense_accounts(firm_id),
            role="expense",
            expected=AccountType.EXPENSE.value,
        )
        paid_from = self._require_account(
            data.paid_from_account_id,
            firm_id=firm_id,
            offered=self.paid_from_accounts(firm_id),
            role="paid-from",
            expected=AccountType.ASSET.value,
        )
        amount = quantize_ledger(data.amount)
        if amount <= Decimal("0"):
            raise ValidationError("An expense must be for more than zero.")
        tds_amount = quantize_ledger(data.tds_amount or Decimal("0"))
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        number = self._issue_number(
            numbering_rule,
            typed=None,
            number_column=Expense.expense_number,
            firm_id=firm_id,
            document_date=data.expense_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        payee = data.payee.strip() if data.payee and data.payee.strip() else None
        reference = (
            data.reference.strip()
            if data.reference and data.reference.strip()
            else None
        )
        narration = (
            data.narration.strip()
            if data.narration and data.narration.strip()
            else None
        )
        description = narration or " ".join(
            part for part in (expense_account.name, payee and f"- {payee}") if part
        )

        # Both directions of the link are set before either row is written:
        # the journal names the expense as its source and the expense names
        # the journal. If posting is refused, nothing is left behind.
        expense_id = uuid4()
        entry = self._posting.post_expense(
            firm_id=firm_id,
            expense_id=expense_id,
            expense_number=number,
            expense_date=data.expense_date,
            amount=amount,
            expense_account_id=expense_account.id,
            paid_from_account_id=paid_from.id,
            description=description[:500],
            actor_id=actor_id,
            tds_amount=tds_amount,
        )
        row = Expense(
            id=expense_id,
            firm_id=firm_id,
            expense_number=number,
            expense_date=data.expense_date,
            expense_account_id=expense_account.id,
            paid_from_account_id=paid_from.id,
            amount=amount,
            tds_amount=tds_amount,
            tds_section=data.tds_section if tds_amount > 0 else None,
            payee_pan=data.payee_pan,
            payee=payee,
            reference=reference,
            narration=narration,
            status=ExpenseStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict(f"Expense number {number} is already in use.")
        record_audit(
            self._session,
            action="expense.recorded",
            entity_type="expense",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "expense_number": number,
                "expense_date": data.expense_date.isoformat(),
                "amount": str(amount),
                "tds_amount": str(tds_amount),
                "expense_account": expense_account.code,
                "paid_from_account": paid_from.code,
                "journal_entry_id": str(entry.id),
            },
        )
        self._session.flush()
        return row

    def cancel(
        self,
        expense_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> Expense:
        """Take an expense back with a mirror journal. Staged; the caller commits.

        Nothing is edited or deleted: the original journal stays and a mirror
        under ``<number>-CAN`` cancels it -- its own reference, because journal
        references are unique per firm. The mirror carries today's date in the
        period open today, never before the original.

        Raises:
            ValidationError: If the expense is already cancelled, or no reason
                is given.

        """
        row = self.get(expense_id, firm_id=firm_id)
        if row.status == ExpenseStatus.CANCELLED.value:
            raise ValidationError(f"{row.expense_number} has already been cancelled.")
        why = reason.strip()
        if not why:
            raise ValidationError("Say why the expense is being cancelled.")
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.expense_number}-CAN",
            actor_id=actor_id,
        )
        row.status = ExpenseStatus.CANCELLED.value
        row.reversal_journal_entry_id = mirror.id
        row.cancel_reason = why
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="expense.cancelled",
            entity_type="expense",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": ExpenseStatus.POSTED.value},
            after_data={
                "status": ExpenseStatus.CANCELLED.value,
                "reversal_journal_entry_id": str(mirror.id),
                "reason": why,
            },
        )
        self._session.flush()
        return row
