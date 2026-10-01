"""The day book, cash and bank books, and statements over a run of months.

Backlog 55 M9 and 50 item 5. The day book lists every journal in the books in
date order; the cash and bank books carry an opening, a balance after every
posting computed in date order, and a closing; the trial balance and the
ledger statement take a From and a To month as the profit and loss does.
"""

# ruff: noqa: D103

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportWindow
from app.finance.api.router import bank_book, cash_book, day_book, router
from app.finance.models import (
    AccountGroup,
    AccountingPeriod,
    FirmControlAccount,
    JournalType,
    LedgerAccount,
    VoucherType,
)
from app.finance.services.books_register import BooksRegisterService
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.general_ledger_service import GeneralLedgerService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from tests.unit.report_windows import assert_page_size_is_bounded, report_scope


class _Books:
    """A firm with the 2026-27 books open and the seeded chart."""

    def __init__(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session: Session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.actor = uuid4()
        self.firm = Firm(
            name="Acme",
            code="ACME",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        for start in (date(2026, 4, 1), date(2027, 4, 1)):
            seed_finance_setup(
                self.session,
                firm_id=self.firm.id,
                year_starts_on=start,
                actor_id=self.actor,
            )
        self.session.commit()

    def account(self, code: str) -> UUID:
        found = self.session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.firm_id == self.firm.id, LedgerAccount.code == code
            )
        )
        assert found is not None, code
        return found

    def period(self, on: date) -> AccountingPeriod:
        found = self.session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.firm_id == self.firm.id,
                AccountingPeriod.starts_on <= on,
                AccountingPeriod.ends_on >= on,
            )
        )
        assert found is not None, on
        return found

    def post(
        self,
        on: date,
        *,
        debit: str,
        credit: str,
        amount: str,
        reference: str | None = None,
        post: bool = True,
    ) -> UUID:
        engine = JournalEntryEngine(self.session)
        value = Decimal(amount)
        entry = engine.create_entry(
            firm_id=self.firm.id,
            journal_type_id=self.session.scalars(select(JournalType.id)).first(),  # type: ignore[arg-type]
            voucher_type_id=self.session.scalars(select(VoucherType.id)).first(),
            accounting_period_id=self.period(on).id,
            journal_date=on,
            reference_number=reference or f"JV-{uuid4().hex[:8]}",
            description=f"{debit} from {credit}",
            lines=[
                JournalLineData(
                    ledger_account_id=self.account(debit), debit_amount=value
                ),
                JournalLineData(
                    ledger_account_id=self.account(credit), credit_amount=value
                ),
            ],
            actor_id=self.actor,
        )
        if post:
            engine.post_entry(entry.id, firm_id=self.firm.id, actor_id=self.actor)
        self.session.commit()
        return entry.id

    @contextmanager
    def statements(self) -> Iterator[list[str]]:
        """Count the statements sent while the block runs."""
        seen: list[str] = []

        def record(*args: object) -> None:
            seen.append(str(args[2]))

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            yield seen
        finally:
            event.remove(self.engine, "before_cursor_execute", record)


# ----------------------------------------------------------------------
# Day book
# ----------------------------------------------------------------------


def test_the_day_book_lists_posted_journals_in_date_order() -> None:
    books = _Books()
    books.post(
        date(2026, 5, 3), debit="6000", credit="1000", amount="40", reference="B"
    )
    books.post(
        date(2026, 4, 10), debit="1000", credit="4000", amount="100", reference="A"
    )
    books.post(
        date(2026, 4, 12), debit="1000", credit="4000", amount="9", post=False
    )  # a draft is not in the books
    books.post(date(2026, 6, 1), debit="1000", credit="4000", amount="7")  # later

    rows = BooksRegisterService(books.session).day_book(
        books.firm.id, ReportWindow(date(2026, 4, 1), date(2026, 5, 31))
    )

    assert [row.voucher for row in rows] == ["A", "B"]
    assert rows[0].debit == rows[0].credit == Decimal("100.00")
    assert rows[0].source == "Journal"
    assert rows[0].status == "POSTED"


def test_the_day_book_route_pages_in_sql_and_names_the_journal() -> None:
    books = _Books()
    ids = [
        books.post(date(2026, 4, day), debit="1000", credit="4000", amount="1")
        for day in (1, 2, 3)
    ]
    page = day_book(
        report_scope(books.firm.id),
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        page=2,
        page_size=2,
        db=books.session,
    )
    assert page.pagination is not None and page.pagination.total_records == 3
    assert [row.journal_entry_id for row in page.data] == [ids[2]]


# ----------------------------------------------------------------------
# Cash and bank books
# ----------------------------------------------------------------------


def test_the_cash_book_opens_runs_and_closes_in_date_order() -> None:
    books = _Books()
    books.post(date(2026, 4, 2), debit="1000", credit="4000", amount="50")  # before
    # Entered out of order: the balance follows the dates, not the keying.
    books.post(
        date(2026, 5, 20), debit="6000", credit="1000", amount="30", reference="R2"
    )
    books.post(
        date(2026, 5, 5), debit="1000", credit="4000", amount="100", reference="R1"
    )
    books.post(date(2026, 5, 7), debit="1010", credit="4000", amount="999")  # bank

    rows = BooksRegisterService(books.session).money_book(
        books.firm.id,
        ControlAccountPurpose.CASH,
        ReportWindow(date(2026, 5, 1), date(2026, 5, 31)),
    )

    assert [row.row_type for row in rows] == ["OPENING", "ENTRY", "ENTRY", "CLOSING"]
    opening, first, second, closing = rows
    assert opening.balance == Decimal("50.00")
    assert (first.voucher, first.receipt, first.balance) == (
        "R1",
        Decimal("100.00"),
        Decimal("150.00"),
    )
    assert (second.voucher, second.payment, second.balance) == (
        "R2",
        Decimal("30.00"),
        Decimal("120.00"),
    )
    assert first.particulars == "Sales"
    assert closing.balance == Decimal("120.00")


def test_a_later_page_of_the_cash_book_carries_the_running_balance() -> None:
    books = _Books()
    for day in range(1, 6):
        books.post(date(2026, 4, day), debit="1000", credit="4000", amount="10")
    page = cash_book(
        report_scope(books.firm.id),
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        page=2,
        page_size=3,
        db=books.session,
    )
    assert page.pagination is not None and page.pagination.total_records == 7
    assert [row.row_type for row in page.data] == ["ENTRY", "ENTRY", "ENTRY"]
    assert [row.balance for row in page.data] == [
        Decimal("30.00"),
        Decimal("40.00"),
        Decimal("50.00"),
    ]
    last = cash_book(
        report_scope(books.firm.id),
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        page=3,
        page_size=3,
        db=books.session,
    )
    assert [row.row_type for row in last.data] == ["CLOSING"]
    assert last.data[0].balance == Decimal("50.00")


def test_a_cash_book_page_costs_the_same_statements_at_any_length() -> None:
    books = _Books()
    for day in range(1, 4):
        books.post(date(2026, 4, day), debit="1000", credit="4000", amount="1")
    window = ReportWindow(date(2026, 4, 1), date(2026, 4, 30), 1, 100)
    service = BooksRegisterService(books.session)
    with books.statements() as few:
        service.money_book(books.firm.id, ControlAccountPurpose.CASH, window)
    for day in range(4, 16):
        books.post(date(2026, 4, day), debit="1000", credit="4000", amount="1")
    with books.statements() as many:
        service.money_book(books.firm.id, ControlAccountPurpose.CASH, window)
    assert len(many) == len(few)


def test_the_bank_book_reads_every_asset_in_a_group_of_its_own() -> None:
    books = _Books()
    group = AccountGroup(
        firm_id=books.firm.id, code="BANKS", name="Bank accounts", account_type="ASSET"
    )
    books.session.add(group)
    books.session.flush()
    main, second = (
        LedgerAccount(
            firm_id=books.firm.id,
            account_group_id=group.id,
            code=code,
            name=name,
            account_type="ASSET",
        )
        for code, name in (("1020", "HDFC Current"), ("1021", "SBI Current"))
    )
    books.session.add_all([main, second])
    mapping = books.session.scalar(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == books.firm.id,
            FirmControlAccount.purpose == ControlAccountPurpose.BANK.value,
        )
    )
    assert mapping is not None
    mapping.ledger_account_id = main.id
    books.session.commit()
    books.post(date(2026, 4, 3), debit="1020", credit="4000", amount="70")
    books.post(date(2026, 4, 4), debit="1021", credit="4000", amount="30")

    service = BooksRegisterService(books.session)
    assert set(service.money_accounts(books.firm.id, ControlAccountPurpose.BANK)) == {
        main.id,
        second.id,
    }
    # Cash sits in Current Assets beside receivables: its book is Cash alone.
    assert service.money_accounts(books.firm.id, ControlAccountPurpose.CASH) == [
        books.account("1000")
    ]
    page = bank_book(
        report_scope(books.firm.id),
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        page=1,
        page_size=100,
        db=books.session,
    )
    assert [row.account for row in page.data if row.row_type == "ENTRY"] == [
        "HDFC Current",
        "SBI Current",
    ]
    assert page.data[-1].balance == Decimal("100.00")


def test_a_book_with_no_account_mapped_says_where_to_map_one() -> None:
    books = _Books()
    for row in books.session.scalars(
        select(FirmControlAccount).where(
            FirmControlAccount.purpose == ControlAccountPurpose.BANK.value
        )
    ):
        books.session.delete(row)
    books.session.commit()
    with pytest.raises(ValidationError, match="Control Accounts"):
        BooksRegisterService(books.session).money_book(
            books.firm.id, ControlAccountPurpose.BANK, ReportWindow()
        )


def test_the_book_routes_bound_their_page() -> None:
    assert_page_size_is_bounded(
        router,
        "/api/v1/finance/reports/day-book",
        "/api/v1/finance/reports/cash-book",
        "/api/v1/finance/reports/bank-book",
    )


# ----------------------------------------------------------------------
# Trial balance and ledger statement over a run of months (50 item 5)
# ----------------------------------------------------------------------


def _three_months(books: _Books) -> None:
    books.post(date(2026, 4, 10), debit="1000", credit="4000", amount="100")
    books.post(date(2026, 5, 10), debit="1000", credit="4000", amount="60")
    books.post(date(2026, 6, 5), debit="6000", credit="1000", amount="40")
    books.post(date(2026, 7, 1), debit="1000", credit="4000", amount="999")  # after


def test_a_trial_balance_over_a_quarter() -> None:
    books = _Books()
    _three_months(books)
    report = GeneralLedgerService(books.session).trial_balance(
        firm_id=books.firm.id,
        accounting_period_id=books.period(date(2026, 4, 1)).id,
        to_period_id=books.period(date(2026, 6, 1)).id,
    )
    cash = next(line for line in report.lines if line.account_code == "1000")
    assert cash.opening_balance == Decimal("0.00")
    assert (cash.period_debit, cash.period_credit) == (
        Decimal("160.00"),
        Decimal("40.00"),
    )
    assert cash.closing_balance == Decimal("120.00")
    assert report.is_balanced
    assert report.to_period_id == books.period(date(2026, 6, 1)).id

    later = GeneralLedgerService(books.session).trial_balance(
        firm_id=books.firm.id,
        accounting_period_id=books.period(date(2026, 5, 1)).id,
        to_period_id=books.period(date(2026, 6, 1)).id,
    )
    cash = next(line for line in later.lines if line.account_code == "1000")
    assert cash.opening_balance == Decimal("100.00")
    assert cash.closing_balance == Decimal("120.00")
    assert later.total_opening_debit == later.total_opening_credit


def test_one_month_on_its_own_is_unchanged_by_the_range() -> None:
    books = _Books()
    _three_months(books)
    service = GeneralLedgerService(books.session)
    may = books.period(date(2026, 5, 1)).id
    alone = service.trial_balance(firm_id=books.firm.id, accounting_period_id=may)
    same = service.trial_balance(
        firm_id=books.firm.id, accounting_period_id=may, to_period_id=may
    )
    assert alone.lines == same.lines
    assert alone.to_period_id is None


def test_a_ledger_statement_over_a_quarter_runs_in_date_order() -> None:
    books = _Books()
    _three_months(books)
    statement = GeneralLedgerService(books.session).general_ledger(
        firm_id=books.firm.id,
        ledger_account_id=books.account("1000"),
        accounting_period_id=books.period(date(2026, 4, 1)).id,
        to_period_id=books.period(date(2026, 6, 1)).id,
    )
    assert [line.running_balance for line in statement.lines] == [
        Decimal("100.00"),
        Decimal("160.00"),
        Decimal("120.00"),
    ]
    assert statement.opening_balance == Decimal("0.00")
    assert (statement.total_debit, statement.total_credit) == (
        Decimal("160.00"),
        Decimal("40.00"),
    )
    assert statement.closing_balance == Decimal("120.00")


def test_a_statement_span_across_years_or_backwards_is_refused() -> None:
    books = _Books()
    service = GeneralLedgerService(books.session)
    with pytest.raises(ValidationError, match="A trial balance runs within one"):
        service.trial_balance(
            firm_id=books.firm.id,
            accounting_period_id=books.period(date(2027, 3, 1)).id,
            to_period_id=books.period(date(2027, 4, 1)).id,
        )
    with pytest.raises(ValidationError, match="before the last"):
        service.general_ledger(
            firm_id=books.firm.id,
            ledger_account_id=books.account("1000"),
            accounting_period_id=books.period(date(2026, 6, 1)).id,
            to_period_id=books.period(date(2026, 4, 1)).id,
        )
