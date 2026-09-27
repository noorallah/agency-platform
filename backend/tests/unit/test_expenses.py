"""Expenses: rent, fuel and salaries recorded without the journal screen.

The point of the module is that recording an expense and posting its journal
are one act. These tests are mostly about the two staying together: the
journal is there and balanced, the accounts are the right kind, and a
cancelled expense leaves the ledger where it started.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.expenses.api.router import (
    cancel_expense,
    expense_account_choices,
    get_expense,
    list_expenses,
    record_expense,
)
from app.expenses.models import Expense, ExpenseStatus
from app.expenses.schemas import ExpenseCancelRequest, ExpenseCreate
from app.expenses.services import ExpenseService
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from tests.unit.report_windows import report_scope

#: Inside the seeded 2026-2027 financial year.
WHEN = date(2026, 4, 20)


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

    def account(self, code: str) -> UUID:
        """Return the id of the account with this code."""
        account_id = self.session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.firm_id == self.firm.id, LedgerAccount.code == code
            )
        )
        assert account_id is not None, code
        return account_id

    def record(
        self,
        amount: str,
        *,
        expense: str = "6000",
        paid_from: str = "1010",
        when: date = WHEN,
        payee: str | None = None,
        reference: str | None = None,
    ) -> Expense:
        """Record one expense and commit, the way the router does."""
        row = ExpenseService(self.session).create(
            ExpenseCreate(
                expense_date=when,
                expense_account_id=self.account(expense),
                paid_from_account_id=self.account(paid_from),
                amount=Decimal(amount),
                payee=payee,
                reference=reference,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def postings(self, journal_entry_id: UUID) -> dict[str, tuple[Decimal, Decimal]]:
        """Return debit and credit by account code for one journal."""
        rows = self.session.execute(
            select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
            .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
            .where(GLPosting.journal_entry_id == journal_entry_id)
        ).all()
        return {code: (debit, credit) for code, debit, credit in rows}

    def net(self, code: str) -> Decimal:
        """Return debits less credits posted to one account."""
        value = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            ).where(GLPosting.ledger_account_id == self.account(code))
        )
        return Decimal(str(value))


def test_recording_an_expense_posts_dr_expense_cr_money() -> None:
    """The journal is written and posted with the expense, and balances."""
    books = _Books()
    row = books.record("25000.00", expense="6000", paid_from="1010")

    assert row.status == ExpenseStatus.POSTED.value
    assert row.expense_number.startswith("EXP")
    entry = books.session.get(JournalEntry, row.journal_entry_id)
    assert entry is not None
    assert entry.status == "POSTED"
    assert entry.source_module == "expenses"
    assert entry.source_id == row.id
    assert entry.reference_number == row.expense_number
    assert books.postings(row.journal_entry_id) == {
        "6000": (Decimal("25000.00"), Decimal("0.00")),
        "1010": (Decimal("0.00"), Decimal("25000.00")),
    }
    audit = books.session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == row.id, AuditLog.action == "expense.recorded"
        )
    )
    assert audit is not None


def test_each_expense_takes_the_next_number() -> None:
    """Numbers come from the firm's own series, one after another."""
    books = _Books()
    first = books.record("100.00")
    second = books.record("200.00")
    assert first.expense_number != second.expense_number
    assert first.expense_number.startswith("EXP")
    assert first.expense_number[-6:] == "000001"
    assert second.expense_number[-6:] == "000002"


def test_an_account_that_is_not_an_expense_is_refused() -> None:
    """Rent cannot be booked to Sales, nor to an account a document keeps."""
    books = _Books()
    with pytest.raises(ValidationError, match="must be an EXPENSE account"):
        books.record("100.00", expense="1000")
    books.session.rollback()
    # Cost of Goods Sold is an expense account the dispatch documents keep.
    cogs = books.session.scalar(
        select(LedgerAccount.code).where(
            LedgerAccount.firm_id == books.firm.id,
            LedgerAccount.name == "Cost of Goods Sold",
        )
    )
    assert cogs is not None
    with pytest.raises(ValidationError, match="kept by the firm's documents"):
        books.record("100.00", expense=cogs)
    assert books.session.scalar(select(func.count()).select_from(Expense)) == 0


def test_money_cannot_come_out_of_an_account_that_does_not_hold_it() -> None:
    """Paid-from must be cash or bank, not an expense or a receivable."""
    books = _Books()
    with pytest.raises(ValidationError, match="must be an ASSET account"):
        books.record("100.00", paid_from="6100")
    books.session.rollback()
    with pytest.raises(ValidationError, match="kept by the firm's documents"):
        books.record("100.00", paid_from="1100")
    assert books.session.scalar(select(func.count()).select_from(Expense)) == 0


def test_the_amount_must_be_more_than_zero() -> None:
    """A zero or negative expense is refused at the door."""
    for amount in ("0", "-5.00"):
        with pytest.raises(PydanticValidationError):
            ExpenseCreate(
                expense_date=WHEN,
                expense_account_id=uuid4(),
                paid_from_account_id=uuid4(),
                amount=Decimal(amount),
            )


def test_cancelling_reverses_the_journal_and_cannot_happen_twice() -> None:
    """The ledger nets back to zero, the original stays, and once is enough."""
    books = _Books()
    row = books.record("3000.00", expense="6400", paid_from="1000")
    assert books.net("6400") == Decimal("3000.00")
    assert books.net("1000") == Decimal("-3000.00")

    service = ExpenseService(books.session)
    cancelled = service.cancel(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Typed twice"
    )
    books.session.commit()

    assert cancelled.status == ExpenseStatus.CANCELLED.value
    assert cancelled.cancel_reason == "Typed twice"
    assert cancelled.cancelled_at is not None
    assert cancelled.reversal_journal_entry_id is not None
    mirror = books.session.get(JournalEntry, cancelled.reversal_journal_entry_id)
    assert mirror is not None
    assert mirror.reference_number == f"{row.expense_number}-CAN"
    assert books.net("6400") == Decimal("0.00")
    assert books.net("1000") == Decimal("0.00")

    with pytest.raises(ValidationError, match="already been cancelled"):
        service.cancel(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Again"
        )


def test_a_cancel_needs_a_reason() -> None:
    """A blank reason is refused, by the schema and by the service."""
    with pytest.raises(PydanticValidationError):
        ExpenseCancelRequest(reason="")
    books = _Books()
    row = books.record("100.00")
    with pytest.raises(ValidationError, match="Say why"):
        ExpenseService(books.session).cancel(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="   "
        )


def test_the_list_searches_and_filters_by_date() -> None:
    """Search reaches payee, reference and the account; the period bounds it."""
    books = _Books()
    books.record("25000.00", expense="6000", payee="Sharma Estates", when=WHEN)
    books.record(
        "3000.00",
        expense="6400",
        paid_from="1000",
        reference="DIESEL-77",
        when=date(2026, 5, 10),
    )
    books.record("900.00", expense="6300", when=date(2026, 6, 2))
    scope = report_scope(books.firm.id)

    def numbers(**filters: object) -> list[str]:
        """Return the numbers the list endpoint answers with."""
        answer = list_expenses(
            scope=scope,
            page=1,
            page_size=20,
            search=str(filters.get("search", "")),
            status_filter=None,
            expense_from=filters.get("expense_from"),  # type: ignore[arg-type]
            expense_to=filters.get("expense_to"),  # type: ignore[arg-type]
            db=books.session,
        )
        return [item.expense_account_code for item in answer.data]

    assert numbers() == ["6300", "6400", "6000"]
    assert numbers(search="sharma") == ["6000"]
    assert numbers(search="diesel") == ["6400"]
    assert numbers(search="Telephone") == ["6300"]
    assert numbers(expense_from=date(2026, 5, 1), expense_to=date(2026, 5, 31)) == [
        "6400"
    ]


def test_the_endpoints_record_read_and_cancel() -> None:
    """The router commits once per act and publishes the version."""
    books = _Books()
    scope = report_scope(books.firm.id)
    choices = expense_account_choices(scope=scope, db=books.session).data
    assert choices is not None
    offered = {row.code for row in choices.expense_accounts}
    assert {"6000", "6100", "6700"} <= offered
    assert "1000" not in offered
    money = {row.code for row in choices.paid_from_accounts}
    assert {"1000", "1010"} <= money
    assert not money & {"1100", "1200", "1320"}

    response = Response()
    created = record_expense(
        payload=ExpenseCreate(
            expense_date=WHEN,
            expense_account_id=books.account("6000"),
            paid_from_account_id=books.account("1010"),
            amount=Decimal("25000.00"),
            payee="Sharma Estates",
        ),
        scope=scope,
        response=response,
        db=books.session,
    ).data
    assert created is not None
    assert created.expense_account_name == "Rent"
    assert created.paid_from_account_name == "Bank"
    assert response.headers["ETag"] == f'"{created.version}"'

    read = get_expense(
        expense_id=created.id, scope=scope, response=Response(), db=books.session
    ).data
    assert read is not None
    assert read.journal_entry_id == created.journal_entry_id

    cancelled = cancel_expense(
        expense_id=created.id,
        payload=ExpenseCancelRequest(reason="Wrong month"),
        scope=scope,
        response=Response(),
        expected_version=created.version,
        db=books.session,
    ).data
    assert cancelled is not None
    assert cancelled.status == ExpenseStatus.CANCELLED.value
    assert cancelled.reversal_journal_entry_id is not None
