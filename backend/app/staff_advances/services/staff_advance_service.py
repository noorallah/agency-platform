"""Give an employee an advance, take it back, and say what each still owes.

No payroll (row P4, backlog 153). The pieces were all in the ledger already:
an asset account per person, a payment out of cash, a journal that books the
salary. What was missing was a way to do it without the chart of accounts and
the journal screen, and one list of who owes what.

**An employee is a ledger account** in the *Staff Advances* group
(``CA-STAFF``, under Current Assets), opened the first time one is added, the
way Cash-in-Hand and Bank Accounts are opened with their first account. His
account is on the trial balance and the balance sheet like any other.

**What he owes is the balance of that account**, summed from the ledger on
every read and stored nowhere. An advance paid by a cheque to his account
(row F13) or by a journal typed by hand counts exactly as one recorded here.

**An advance** is Dr the employee, Cr cash or a bank account. **A recovery**
is Cr the employee and Dr either the expense account his salary is booked to
-- the part of the month's salary he had already been paid, so the salary
expense comes to the full salary once the rest is recorded as an expense --
or the cash or bank account he paid it back into.

The service stages and flushes; the router commits once.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.expenses.services import ExpenseService
from app.finance.models import AccountGroup, AccountType, GLPosting, LedgerAccount
from app.finance.schemas import (
    AccountGroupCreate,
    AccountTypeEnum,
    LedgerAccountCreate,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.finance_service import FinanceService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.journal_engine import quantize_money as quantize_ledger
from app.finance.services.money_accounts import (
    STAFF_ADVANCES_GROUP_CODE,
    ask_before_cash_goes_below_zero,
    money_accounts,
    staff_advance_account_ids,
)
from app.staff_advances.models import (
    StaffAdvanceEntry,
    StaffAdvanceKind,
    StaffAdvanceStatus,
)
from app.staff_advances.schemas import StaffAdvanceCreate

_GROUP_NAME = "Staff Advances"
#: The group it is opened under where the firm's chart has one.
_PARENT_GROUP_CODE = "CA"
#: An employee's account code: ``ADV-001``. A prefix of its own, so it cannot
#: collide with the numbered chart or with a code the firm chose.
_CODE_PREFIX = "ADV-"

SIDE_SALARY = "SALARY"
SIDE_MONEY = "MONEY"


@dataclass(frozen=True)
class EmployeeBalance:
    """One employee's account with what was advanced and taken back."""

    account: LedgerAccount
    advanced: Decimal
    recovered: Decimal

    @property
    def owes(self) -> Decimal:
        """Return what the employee still owes; negative when over-recovered."""
        return self.advanced - self.recovered


def _money(value: Decimal) -> str:
    """Format an amount for a sentence."""
    return f"{value:,.2f}"


class StaffAdvanceService(TransactionalDocumentService):
    """Open employee accounts, record advances and recoveries, cancel them."""

    DOCUMENT = DocumentTypeSpec(
        code="STAFF_ADVANCE",
        name="Staff Advance",
        description="An advance paid to an employee, or its recovery",
        category="FINANCE",
        module="staff_advances",
        prefix="SADV",
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
        self._finance = FinanceService(session)

    # ------------------------------------------------------------------
    # Employees
    # ------------------------------------------------------------------

    def _group(self, firm_id: UUID) -> AccountGroup | None:
        """Return the firm's Staff Advances group, if it has been opened."""
        return self._session.scalar(
            select(AccountGroup).where(
                AccountGroup.firm_id == firm_id,
                AccountGroup.code == STAFF_ADVANCES_GROUP_CODE,
                AccountGroup.is_deleted.is_(False),
            )
        )

    def _ensure_group(self, firm_id: UUID, actor_id: UUID) -> AccountGroup:
        """Return the Staff Advances group, opening it with the first employee."""
        group = self._group(firm_id)
        if group is not None:
            return group
        parent = self._session.scalar(
            select(AccountGroup).where(
                AccountGroup.firm_id == firm_id,
                AccountGroup.code == _PARENT_GROUP_CODE,
                AccountGroup.account_type == AccountType.ASSET.value,
                AccountGroup.is_deleted.is_(False),
            )
        )
        return self._finance.create_account_group(
            AccountGroupCreate(
                code=STAFF_ADVANCES_GROUP_CODE,
                name=_GROUP_NAME,
                account_type=AccountTypeEnum.ASSET,
                parent_group_id=None if parent is None else parent.id,
                description="One account per employee: what each was advanced.",
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _accounts(self, firm_id: UUID) -> list[LedgerAccount]:
        """Return every employee account, by name."""
        group = self._group(firm_id)
        if group is None:
            return []
        return list(
            self._session.scalars(
                select(LedgerAccount)
                .where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.account_group_id == group.id,
                    LedgerAccount.is_deleted.is_(False),
                )
                .order_by(func.lower(LedgerAccount.name).asc(), LedgerAccount.code)
            ).all()
        )

    def _totals(
        self, firm_id: UUID, account_ids: Sequence[UUID]
    ) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return what was debited and credited to each account, in one read."""
        if not account_ids:
            return {}
        rows = self._session.execute(
            select(
                GLPosting.ledger_account_id,
                func.coalesce(func.sum(GLPosting.debit_amount), 0),
                func.coalesce(func.sum(GLPosting.credit_amount), 0),
            )
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id.in_(account_ids),
            )
            .group_by(GLPosting.ledger_account_id)
        ).all()
        return {
            account_id: (
                quantize_ledger(Decimal(str(debit or 0))),
                quantize_ledger(Decimal(str(credit or 0))),
            )
            for account_id, debit, credit in rows
        }

    def employees(self, firm_id: UUID) -> list[EmployeeBalance]:
        """Return every employee with what he was advanced and still owes.

        An account switched off stays on the list while it carries a balance:
        a man who left owing money still owes it.
        """
        accounts = self._accounts(firm_id)
        totals = self._totals(firm_id, [account.id for account in accounts])
        rows: list[EmployeeBalance] = []
        for account in accounts:
            advanced, recovered = totals.get(account.id, (ZERO, ZERO))
            if not account.is_active and advanced == recovered:
                continue
            rows.append(EmployeeBalance(account, advanced, recovered))
        return rows

    def employee(self, account_id: UUID, *, firm_id: UUID) -> EmployeeBalance:
        """Return one employee with his balance, or raise when unknown."""
        account = self._employee_account(account_id, firm_id=firm_id)
        advanced, recovered = self._totals(firm_id, [account.id]).get(
            account.id, (ZERO, ZERO)
        )
        return EmployeeBalance(account, advanced, recovered)

    def _next_code(self, firm_id: UUID) -> str:
        """Return the next free ``ADV-`` code.

        Every row counts, deleted ones too: the code is unique per firm
        whether or not the account that held it is still live.
        """
        taken = set(
            self._session.scalars(
                select(LedgerAccount.code).where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.code.like(f"{_CODE_PREFIX}%"),
                )
            ).all()
        )
        number = len(taken) + 1
        while f"{_CODE_PREFIX}{number:03d}" in taken:
            number += 1
        return f"{_CODE_PREFIX}{number:03d}"

    def add_employee(
        self, name: str, *, firm_id: UUID, actor_id: UUID
    ) -> EmployeeBalance:
        """Open an account for one employee. Staged; the caller commits.

        Raises:
            ValidationError: If the name is blank, or an employee of that
                name already has an account.

        """
        clean = " ".join(name.split())
        if not clean:
            raise ValidationError("Type the employee's name.")
        group = self._ensure_group(firm_id, actor_id)
        duplicate = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.account_group_id == group.id,
                func.lower(LedgerAccount.name) == clean.lower(),
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if duplicate is not None:
            raise ValidationError(
                f"{duplicate.name} already has an account ({duplicate.code}). "
                "Add something to the name to tell two people apart."
            )
        account = self._finance.create_ledger_account(
            LedgerAccountCreate(
                account_group_id=group.id,
                code=self._next_code(firm_id),
                name=clean,
                account_type=AccountTypeEnum.ASSET,
                description="Employee: salary advances.",
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        return EmployeeBalance(account, ZERO, ZERO)

    def _employee_account(
        self, account_id: UUID, *, firm_id: UUID, lock: bool = False
    ) -> LedgerAccount:
        """Return an employee's account, or refuse one that is not an employee."""
        group = self._group(firm_id)
        statement = select(LedgerAccount).where(
            LedgerAccount.id == account_id,
            LedgerAccount.firm_id == firm_id,
            LedgerAccount.is_deleted.is_(False),
        )
        if lock:
            # What he owes is a sum, and a recovery is an insert: no row's
            # version moves, so two recoveries at once would both read the
            # same balance. The lock is on the one employee.
            statement = statement.with_for_update()
        account = self._session.scalar(statement)
        if account is None or group is None or account.account_group_id != group.id:
            raise ResourceNotFoundError("Employee not found.")
        return account

    # ------------------------------------------------------------------
    # Accounts the forms offer
    # ------------------------------------------------------------------

    def money_accounts(self, firm_id: UUID) -> list[tuple[LedgerAccount, str]]:
        """Return the firm's cash and bank accounts, each with its kind."""
        return money_accounts(self._session, firm_id)

    def salary_accounts(self, firm_id: UUID) -> list[LedgerAccount]:
        """Return the expense accounts a recovery out of salary may name."""
        return ExpenseService(self._session).expense_accounts(firm_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def _scoped(
        statement: Select[tuple[StaffAdvanceEntry]], firm_id: UUID
    ) -> Select[tuple[StaffAdvanceEntry]]:
        """Restrict a query to this firm's live entries."""
        return statement.where(
            StaffAdvanceEntry.firm_id == firm_id,
            StaffAdvanceEntry.is_deleted.is_(False),
        )

    def list_entries(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        search: str = "",
        employee_account_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[Sequence[StaffAdvanceEntry], int]:
        """Return one page of entries, newest first.

        The search matches the number, the narration and the employee's name.
        """
        statement = self._scoped(select(StaffAdvanceEntry), firm_id)
        if employee_account_id is not None:
            statement = statement.where(
                StaffAdvanceEntry.employee_account_id == employee_account_id
            )
        if status:
            statement = statement.where(
                StaffAdvanceEntry.status == status.strip().upper()
            )
        if date_from is not None:
            statement = statement.where(StaffAdvanceEntry.entry_date >= date_from)
        if date_to is not None:
            statement = statement.where(StaffAdvanceEntry.entry_date <= date_to)
        if search.strip():
            pattern = f"%{search.strip()}%"
            named = select(LedgerAccount.id).where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.name.ilike(pattern),
            )
            statement = statement.where(
                or_(
                    StaffAdvanceEntry.entry_number.ilike(pattern),
                    StaffAdvanceEntry.narration.ilike(pattern),
                    StaffAdvanceEntry.employee_account_id.in_(named),
                )
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                StaffAdvanceEntry.entry_date.desc(),
                StaffAdvanceEntry.entry_number.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get(self, entry_id: UUID, *, firm_id: UUID) -> StaffAdvanceEntry:
        """Return one entry or raise when it is unavailable."""
        row = self._session.scalar(
            self._scoped(select(StaffAdvanceEntry), firm_id).where(
                StaffAdvanceEntry.id == entry_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Staff advance entry not found.")
        return row

    def accounts_named(
        self, rows: Sequence[StaffAdvanceEntry]
    ) -> dict[UUID, LedgerAccount]:
        """Return every account the given entries name, in one read."""
        ids = {row.employee_account_id for row in rows} | {
            row.other_account_id for row in rows
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

    def _other_account(
        self, account_id: UUID, *, firm_id: UUID, kind: StaffAdvanceKind
    ) -> LedgerAccount:
        """Return the other side of an entry, or refuse it by name."""
        for account, _ in self.money_accounts(firm_id):
            if account.id == account_id:
                return account
        if kind is StaffAdvanceKind.RECOVERY:
            for account in self.salary_accounts(firm_id):
                if account.id == account_id:
                    return account
        found = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if found is None:
            raise ValidationError("The account was not found in this firm.")
        if kind is StaffAdvanceKind.ADVANCE:
            raise ValidationError(
                f"{found.code} {found.name} is not a cash or bank account; "
                "an advance is paid out of one."
            )
        raise ValidationError(
            f"{found.code} {found.name} cannot take a recovery: choose the "
            "expense account the salary is booked to, or the cash or bank "
            "account the money was paid back into."
        )

    def record(
        self,
        data: StaffAdvanceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        ask_before_cash_below_zero: bool = False,
    ) -> StaffAdvanceEntry:
        """Record one advance or recovery and post it. Staged; caller commits.

        Raises:
            ValidationError: If the date is ahead of today, the other account
                is of the wrong kind, the employee's account is switched off,
                or a recovery is for more than he owes.
            ResourceNotFoundError: If the account is not an employee's.

        """
        employee = self._employee_account(
            data.employee_account_id, firm_id=firm_id, lock=True
        )
        other = self._other_account(
            data.other_account_id, firm_id=firm_id, kind=data.kind
        )
        if data.entry_date > firm_today(self._session, firm_id):
            raise ValidationError(
                "This cannot be recorded on a future date: it is for money "
                "that has already moved."
            )
        amount = quantize_ledger(data.amount)
        if amount <= ZERO:
            raise ValidationError("The amount must be more than zero.")
        is_advance = data.kind is StaffAdvanceKind.ADVANCE
        if not employee.is_active:
            # The ledger posts nothing to an account that is switched off,
            # so say it in the screen's words before the journal refuses.
            raise ValidationError(
                f"{employee.name}'s account is switched off; switch it on in "
                "the chart of accounts before recording anything on it."
            )
        if not is_advance:
            advanced, recovered = self._totals(firm_id, [employee.id]).get(
                employee.id, (ZERO, ZERO)
            )
            owes = advanced - recovered
            if amount > owes:
                raise ValidationError(
                    f"{employee.name} owes {_money(max(owes, ZERO))}; "
                    f"{_money(amount)} cannot be recovered."
                )
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        number = self._issue_number(
            numbering_rule,
            typed=None,
            number_column=StaffAdvanceEntry.entry_number,
            firm_id=firm_id,
            document_date=data.entry_date,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
        narration = (
            data.narration.strip()
            if data.narration and data.narration.strip()
            else None
        )
        description = narration or (
            f"Advance to {employee.name}"
            if is_advance
            else f"Advance recovered from {employee.name}"
        )
        entry_id = uuid4()
        journal = self._posting.post_staff_advance(
            firm_id=firm_id,
            entry_id=entry_id,
            entry_number=number,
            entry_date=data.entry_date,
            amount=amount,
            debit_account_id=employee.id if is_advance else other.id,
            credit_account_id=other.id if is_advance else employee.id,
            description=description[:500],
            actor_id=actor_id,
        )
        row = StaffAdvanceEntry(
            id=entry_id,
            firm_id=firm_id,
            entry_number=number,
            entry_date=data.entry_date,
            kind=data.kind.value,
            employee_account_id=employee.id,
            other_account_id=other.id,
            amount=amount,
            narration=narration,
            status=StaffAdvanceStatus.POSTED.value,
            journal_entry_id=journal.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict(f"Number {number} is already in use.")
        record_audit(
            self._session,
            action="staff_advance.recorded",
            entity_type="staff_advance_entry",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "entry_number": number,
                "entry_date": data.entry_date.isoformat(),
                "kind": data.kind.value,
                "amount": str(amount),
                "employee_account": employee.code,
                "other_account": other.code,
                "journal_entry_id": str(journal.id),
            },
        )
        self._session.flush()
        if is_advance and ask_before_cash_below_zero:
            ask_before_cash_goes_below_zero(
                self._session,
                firm_id=firm_id,
                account_id=other.id,
                journal_entry_id=journal.id,
                on=data.entry_date,
            )
        return row

    def cancel(
        self,
        entry_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> StaffAdvanceEntry:
        """Take an entry back with a mirror journal. Staged; caller commits.

        The original journal stays and a mirror under ``<number>-CAN`` cancels
        it. An advance whose money has since been recovered is not cancelled:
        the account would say the firm owes the employee.

        Raises:
            ValidationError: If the entry is already cancelled, no reason is
                given, or cancelling an advance would leave the employee
                having paid back more than he was given.

        """
        row = self.get(entry_id, firm_id=firm_id)
        if row.status == StaffAdvanceStatus.CANCELLED.value:
            raise ValidationError(f"{row.entry_number} has already been cancelled.")
        why = reason.strip()
        if not why:
            raise ValidationError("Say why the entry is being cancelled.")
        if row.kind == StaffAdvanceKind.ADVANCE.value:
            employee = self._employee_account(
                row.employee_account_id, firm_id=firm_id, lock=True
            )
            advanced, recovered = self._totals(firm_id, [employee.id]).get(
                employee.id, (ZERO, ZERO)
            )
            owes = advanced - recovered
            if row.amount > owes:
                raise ValidationError(
                    f"{row.entry_number} cannot be cancelled: {employee.name} "
                    f"owes {_money(max(owes, ZERO))}, less than this advance of "
                    f"{_money(row.amount)}. Cancel the recovery taken against "
                    "it first."
                )
        mirror = self._journals.reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"{row.entry_number}-CAN",
            actor_id=actor_id,
        )
        row.status = StaffAdvanceStatus.CANCELLED.value
        row.reversal_journal_entry_id = mirror.id
        row.cancel_reason = why
        row.cancelled_at = utc_now()
        row.cancelled_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="staff_advance.cancelled",
            entity_type="staff_advance_entry",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": StaffAdvanceStatus.POSTED.value},
            after_data={
                "status": StaffAdvanceStatus.CANCELLED.value,
                "reversal_journal_entry_id": str(mirror.id),
                "reason": why,
            },
        )
        self._session.flush()
        return row


__all__ = [
    "SIDE_MONEY",
    "SIDE_SALARY",
    "STAFF_ADVANCES_GROUP_CODE",
    "EmployeeBalance",
    "StaffAdvanceService",
    "staff_advance_account_ids",
]
