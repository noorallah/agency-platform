"""Staff advances: an account per employee, an advance and its recovery.

No payroll (row P4). What matters is that the list of who owes what is the
ledger's own balance, that every entry is a posted journal, and that an
employee's account is never offered as somewhere money is paid from.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.firm_metadata import firm_today
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.expenses.services import ExpenseService
from app.finance.models import (
    AccountGroup,
    AccountingPeriod,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.general_ledger_service import GeneralLedgerService
from app.finance.services.money_accounts import (
    STAFF_ADVANCES_GROUP_CODE,
    money_accounts,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.staff_advances.api.router import (
    add_employee,
    cancel_staff_advance,
    list_employees,
    list_staff_advances,
    record_staff_advance,
    staff_advance_account_choices,
)
from app.staff_advances.models import StaffAdvanceEntry, StaffAdvanceStatus
from app.staff_advances.schemas import (
    EmployeeCreate,
    StaffAdvanceCancelRequest,
    StaffAdvanceCreate,
)
from app.staff_advances.services import StaffAdvanceService
from tests.unit.report_windows import report_scope

#: Inside the seeded 2026-2027 financial year.
WHEN = date(2026, 4, 20)
CASH = "1000"
BANK = "1010"
SALARY = "6100"


def _session() -> Session:
    """Create one shared in-memory database and open a session on it."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _Books:
    """A firm whose books are open, with its seeded chart of accounts."""

    def __init__(self) -> None:
        """Open the books the way the Set up panel does."""
        self.session = _session()
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Acme Firm",
            code="ACME",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        seed_finance_setup(
            self.session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.session.commit()
        self.service = StaffAdvanceService(self.session)

    def account(self, code: str) -> UUID:
        """Return the id of the account with this code."""
        account_id = self.session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.firm_id == self.firm.id, LedgerAccount.code == code
            )
        )
        assert account_id is not None, code
        return account_id

    def hire(self, name: str) -> UUID:
        """Open an employee's account and commit."""
        row = self.service.add_employee(
            name, firm_id=self.firm.id, actor_id=self.actor_id
        )
        self.session.commit()
        return row.account.id

    def record(
        self,
        kind: str,
        employee: UUID,
        amount: str,
        *,
        other: str = CASH,
        when: date = WHEN,
        ask: bool = False,
    ) -> StaffAdvanceEntry:
        """Record one advance or recovery and commit, the way the router does."""
        row = self.service.record(
            StaffAdvanceCreate(
                kind=kind,
                entry_date=when,
                employee_account_id=employee,
                other_account_id=self.account(other),
                amount=Decimal(amount),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
            ask_before_cash_below_zero=ask,
        )
        self.session.commit()
        return row

    def owes(self, employee: UUID) -> Decimal:
        """Return what the list says one employee owes."""
        return self.service.employee(employee, firm_id=self.firm.id).owes

    def net(self, account_id: UUID) -> Decimal:
        """Return debits less credits posted to one account."""
        value = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            ).where(GLPosting.ledger_account_id == account_id)
        )
        return Decimal(str(value))


def test_the_first_employee_opens_the_staff_advances_group() -> None:
    """The group is opened under Current Assets with the first employee."""
    books = _Books()
    assert books.service.employees(books.firm.id) == []

    first = books.hire("  Ravi   Kumar ")
    second = books.hire("Suresh")

    group = books.session.scalar(
        select(AccountGroup).where(AccountGroup.code == STAFF_ADVANCES_GROUP_CODE)
    )
    assert group is not None
    parent = books.session.get(AccountGroup, group.parent_group_id)
    assert parent is not None
    assert parent.code == "CA"
    accounts = [books.session.get(LedgerAccount, row) for row in (first, second)]
    assert [(row.code, row.name) for row in accounts if row is not None] == [
        ("ADV-001", "Ravi Kumar"),
        ("ADV-002", "Suresh"),
    ]
    assert all(
        row is not None
        and row.account_type == "ASSET"
        and row.is_balance_sheet
        and row.account_group_id == group.id
        for row in accounts
    )
    assert (
        books.session.scalar(
            select(func.count())
            .select_from(AccountGroup)
            .where(AccountGroup.code == STAFF_ADVANCES_GROUP_CODE)
        )
        == 1
    )


def test_two_employees_of_one_name_are_refused() -> None:
    """A second account of the same name would be picked by mistake."""
    books = _Books()
    books.hire("Ravi Kumar")
    with pytest.raises(ValidationError, match="already has an account"):
        books.hire("ravi kumar")
    with pytest.raises(ValidationError, match="Type the employee's name"):
        books.hire("   ")


def test_an_advance_and_a_recovery_leave_what_is_still_owed() -> None:
    """The row's own case: 5,000 from Cash, 2,000 recovered, 3,000 owed."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")

    advance = books.record("ADVANCE", ravi, "5000.00", other=CASH)
    recovery = books.record("RECOVERY", ravi, "2000.00", other=SALARY)

    assert advance.entry_number.startswith("SADV")
    assert advance.entry_number != recovery.entry_number
    entry = books.session.get(JournalEntry, advance.journal_entry_id)
    assert entry is not None
    assert entry.status == "POSTED"
    assert entry.source_module == "staff_advances"
    assert entry.source_id == advance.id
    assert books.net(ravi) == Decimal("3000.00")
    assert books.net(books.account(CASH)) == Decimal("-5000.00")
    # The salary expense carries the part of the salary the advance paid.
    assert books.net(books.account(SALARY)) == Decimal("2000.00")

    listed = books.service.employees(books.firm.id)
    assert [(row.advanced, row.recovered, row.owes) for row in listed] == [
        (Decimal("5000.00"), Decimal("2000.00"), Decimal("3000.00"))
    ]
    period = books.session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.firm_id == books.firm.id,
            AccountingPeriod.starts_on <= WHEN,
            AccountingPeriod.ends_on >= WHEN,
        )
    )
    assert period is not None
    report = GeneralLedgerService(books.session).trial_balance(
        firm_id=books.firm.id, accounting_period_id=period.id
    )
    line = next(row for row in report.lines if row.ledger_account_id == ravi)
    assert line.closing_debit == Decimal("3000.00")
    assert report.is_balanced
    audit = books.session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == advance.id,
            AuditLog.action == "staff_advance.recorded",
        )
    )
    assert audit is not None


def test_money_paid_back_goes_into_the_cash_or_bank_account() -> None:
    """A recovery may also be money handed back: Dr the money, Cr the man."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    books.record("ADVANCE", ravi, "5000.00", other=BANK)
    books.record("RECOVERY", ravi, "1500.00", other=CASH)

    assert books.owes(ravi) == Decimal("3500.00")
    assert books.net(books.account(CASH)) == Decimal("1500.00")
    assert books.net(books.account(BANK)) == Decimal("-5000.00")


def test_an_advance_posted_another_way_is_owed_too() -> None:
    """What is owed is the account's balance, whoever posted to it."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    books.record("ADVANCE", ravi, "1000.00")
    # The same journal a cheque to his account, or a hand entry, would write.
    books.service._posting.post_staff_advance(
        firm_id=books.firm.id,
        entry_id=uuid4(),
        entry_number="JV-OTHER-1",
        entry_date=WHEN,
        amount=Decimal("400.00"),
        debit_account_id=ravi,
        credit_account_id=books.account(BANK),
        description="By cheque",
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.owes(ravi) == Decimal("1400.00")


def test_more_than_he_owes_cannot_be_recovered() -> None:
    """A recovery past the balance would say the firm owes the employee."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    books.record("ADVANCE", ravi, "5000.00")
    with pytest.raises(ValidationError, match=r"owes 5,000\.00; 5,000\.01 cannot"):
        books.record("RECOVERY", ravi, "5000.01", other=SALARY)
    books.session.rollback()
    books.record("RECOVERY", ravi, "5000.00", other=SALARY)
    assert books.owes(ravi) == Decimal("0.00")


def test_the_other_account_must_be_of_the_right_kind() -> None:
    """An advance leaves a money account; a recovery names salary or money."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    suresh = books.hire("Suresh")
    with pytest.raises(ValidationError, match="not a cash or bank account"):
        books.record("ADVANCE", ravi, "100.00", other=SALARY)
    books.session.rollback()
    books.record("ADVANCE", ravi, "100.00")
    with pytest.raises(ValidationError, match="cannot take a recovery"):
        books.service.record(
            StaffAdvanceCreate(
                kind="RECOVERY",
                entry_date=WHEN,
                employee_account_id=ravi,
                other_account_id=suresh,
                amount=Decimal("50.00"),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()
    with pytest.raises(ResourceNotFoundError, match="Employee not found"):
        books.record("ADVANCE", books.account(BANK), "100.00")


def test_a_future_date_and_a_zero_amount_are_refused() -> None:
    """The money has already moved, and it is more than nothing."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    tomorrow = firm_today(books.session, books.firm.id) + timedelta(days=1)
    with pytest.raises(ValidationError, match="future date"):
        books.record("ADVANCE", ravi, "100.00", when=tomorrow)
    with pytest.raises(PydanticValidationError):
        StaffAdvanceCreate(
            kind="ADVANCE",
            entry_date=WHEN,
            employee_account_id=ravi,
            other_account_id=books.account(CASH),
            amount=Decimal("0"),
        )


def test_an_advance_out_of_cash_that_is_not_there_is_asked_about() -> None:
    """Cash cannot hold less than nothing: the save is a question first."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    with pytest.raises(ConflictError) as raised:
        books.record("ADVANCE", ravi, "5000.00", other=CASH, ask=True)
    assert raised.value.details["reason"] == "cash_below_zero"
    books.session.rollback()
    assert books.owes(ravi) == Decimal("0.00")
    # A bank account may be overdrawn and is never asked about.
    books.record("ADVANCE", ravi, "5000.00", other=BANK, ask=True)
    assert books.owes(ravi) == Decimal("5000.00")


def test_cancelling_puts_the_ledger_back() -> None:
    """A mirror journal takes the entry back and both stay on the record."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    advance = books.record("ADVANCE", ravi, "5000.00")
    recovery = books.record("RECOVERY", ravi, "5000.00", other=SALARY)

    # The advance has been recovered: cancelling it alone is refused.
    with pytest.raises(ValidationError, match="Cancel the recovery"):
        books.service.cancel(
            advance.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="x"
        )
    books.session.rollback()
    with pytest.raises(ValidationError, match="Say why"):
        books.service.cancel(
            recovery.id, firm_id=books.firm.id, actor_id=books.actor_id, reason=" "
        )
    books.service.cancel(
        recovery.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Wrong man"
    )
    books.session.commit()
    assert books.owes(ravi) == Decimal("5000.00")
    assert books.net(books.account(SALARY)) == Decimal("0.00")
    cancelled = books.service.cancel(
        advance.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Not paid"
    )
    books.session.commit()

    assert cancelled.status == StaffAdvanceStatus.CANCELLED.value
    assert cancelled.reversal_journal_entry_id is not None
    mirror = books.session.get(JournalEntry, cancelled.reversal_journal_entry_id)
    assert mirror is not None
    assert mirror.reference_number == f"{advance.entry_number}-CAN"
    assert books.net(ravi) == Decimal("0.00")
    assert books.net(books.account(CASH)) == Decimal("0.00")
    with pytest.raises(ValidationError, match="already been cancelled"):
        books.service.cancel(
            advance.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="again"
        )


def test_an_employee_is_not_somewhere_money_is_paid_from() -> None:
    """The expense form offers the firm's own asset accounts: not a person."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    books.record("ADVANCE", ravi, "100.00")

    offered = {
        row.id
        for row in ExpenseService(books.session).paid_from_accounts(books.firm.id)
    }
    assert ravi not in offered
    assert books.account(CASH) in offered
    assert ravi not in {
        row.id for row, _ in money_accounts(books.session, books.firm.id)
    }


def test_an_account_switched_off_stays_listed_while_it_owes() -> None:
    """A man who left owing money still owes it; a settled one drops off."""
    books = _Books()
    ravi = books.hire("Ravi Kumar")
    suresh = books.hire("Suresh")
    books.record("ADVANCE", ravi, "700.00")
    for account_id in (ravi, suresh):
        account = books.session.get(LedgerAccount, account_id)
        assert account is not None
        account.is_active = False
    books.session.commit()

    assert [row.account.id for row in books.service.employees(books.firm.id)] == [ravi]
    with pytest.raises(ValidationError, match="switched off"):
        books.record("ADVANCE", ravi, "100.00")
    books.session.rollback()
    # Switched on again he pays back what he owes, and then drops off.
    account = books.session.get(LedgerAccount, ravi)
    assert account is not None
    account.is_active = True
    books.record("RECOVERY", ravi, "700.00", other=CASH)
    account.is_active = False
    books.session.commit()
    assert books.service.employees(books.firm.id) == []


def test_the_routes_answer_the_screen() -> None:
    """Add, choose, record, list, read and cancel through the handlers."""
    books = _Books()
    scope = report_scope(books.firm.id)
    db = books.session

    added = add_employee(EmployeeCreate(name="Ravi Kumar"), scope, db).data
    assert added is not None
    assert (added.code, added.owes) == ("ADV-001", Decimal("0"))
    choices = staff_advance_account_choices(scope, db).data
    assert choices is not None
    kinds = {row.code: row.kind for row in choices.money_accounts}
    assert kinds[CASH] == "CASH"
    assert kinds[BANK] == "BANK"
    assert SALARY in {row.code for row in choices.salary_accounts}

    advance = record_staff_advance(
        StaffAdvanceCreate(
            kind="ADVANCE",
            entry_date=WHEN,
            employee_account_id=added.account_id,
            other_account_id=books.account(BANK),
            amount=Decimal("5000.00"),
            narration=" Festival advance ",
        ),
        scope,
        Response(),
        db,
    ).data
    assert advance is not None
    assert advance.employee_name == "Ravi Kumar"
    assert advance.other_side == "MONEY"
    assert advance.narration == "Festival advance"
    recovery = record_staff_advance(
        StaffAdvanceCreate(
            kind="RECOVERY",
            entry_date=WHEN,
            employee_account_id=added.account_id,
            other_account_id=books.account(SALARY),
            amount=Decimal("2000.00"),
        ),
        scope,
        Response(),
        db,
    ).data
    assert recovery is not None
    assert recovery.other_side == "SALARY"

    employees = list_employees(scope, db).data
    assert employees is not None
    assert [row.owes for row in employees] == [Decimal("3000.00")]
    page = list_staff_advances(scope, db=db, employee_account_id=added.account_id)
    assert page.pagination.total_records == 2
    assert {row.kind for row in page.data} == {"ADVANCE", "RECOVERY"}
    assert (
        list_staff_advances(scope, db=db, search="festival").pagination.total_records
        == 1
    )
    assert list_staff_advances(scope, db=db, employee_account_id=uuid4()).data == []

    done = cancel_staff_advance(
        recovery.id,
        StaffAdvanceCancelRequest(reason="Keyed twice"),
        scope,
        Response(),
        None,
        db,
    ).data
    assert done is not None
    assert done.status == "CANCELLED"
    employees = list_employees(scope, db).data
    assert employees is not None
    assert [row.owes for row in employees] == [Decimal("5000.00")]
    assert (
        list_staff_advances(
            scope, db=db, status_filter="POSTED"
        ).pagination.total_records
        == 1
    )
