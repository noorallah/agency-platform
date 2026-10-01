"""The profit and loss over a whole year or any run of months (backlog 50).

One month at a time was all there was: a full year could only be read as the
last month's year-to-date column, and a quarter not at all. These pin the
range: each month as a column, the total, and the same months of last year.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import (
    AccountingPeriod,
    FinancialYear,
    JournalType,
    LedgerAccount,
    VoucherType,
)
from app.finance.services.general_ledger_service import GeneralLedgerService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm


class _Books:
    """A firm with two financial years open, 2025-26 and 2026-27."""

    def __init__(self) -> None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        self.session: Session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.actor = uuid4()
        self.firm = Firm(
            name="Acme",
            code="ACME",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2025, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        for start in (date(2025, 4, 1), date(2026, 4, 1)):
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

    def sale(self, on: date, amount: str) -> None:
        self._post(on, credit="4000", debit="1000", amount=amount)

    def rent(self, on: date, amount: str) -> None:
        self._post(on, credit="1000", debit="6000", amount=amount)

    def _post(self, on: date, *, credit: str, debit: str, amount: str) -> None:
        engine = JournalEntryEngine(self.session)
        value = Decimal(amount)
        dr, cr = debit, credit
        entry = engine.create_entry(
            firm_id=self.firm.id,
            journal_type_id=self.session.scalars(select(JournalType.id)).first(),  # type: ignore[arg-type]
            voucher_type_id=self.session.scalars(select(VoucherType.id)).first(),
            accounting_period_id=self.period(on).id,
            journal_date=on,
            reference_number=f"JV-{uuid4().hex[:8]}",
            description="test",
            lines=[
                JournalLineData(ledger_account_id=self.account(dr), debit_amount=value),
                JournalLineData(
                    ledger_account_id=self.account(cr), credit_amount=value
                ),
            ],
            actor_id=self.actor,
        )
        engine.post_entry(entry.id, firm_id=self.firm.id, actor_id=self.actor)
        self.session.commit()


def test_a_quarter_shows_each_month_and_the_total() -> None:
    books = _Books()
    books.sale(date(2026, 4, 10), "100.00")
    books.sale(date(2026, 5, 10), "60.00")
    books.rent(date(2026, 6, 5), "40.00")
    books.sale(date(2026, 7, 1), "999.00")  # outside the quarter

    report = GeneralLedgerService(books.session).profit_and_loss_range(
        firm_id=books.firm.id,
        from_period_id=books.period(date(2026, 4, 1)).id,
        to_period_id=books.period(date(2026, 6, 1)).id,
    )

    assert len(report.months) == 3
    [sales] = report.income
    assert sales.months == [Decimal("100.00"), Decimal("60.00"), Decimal("0.00")]
    assert sales.amount == Decimal("160.00")
    [rent] = report.expenses
    assert rent.amount == Decimal("40.00")
    assert report.net_profit == Decimal("120.00")
    assert report.monthly_net_profit == [
        Decimal("100.00"),
        Decimal("60.00"),
        Decimal("-40.00"),
    ]
    assert report.comparison_net_profit is None


def test_last_year_s_same_months_sit_beside_this_year_s() -> None:
    books = _Books()
    books.sale(date(2025, 4, 15), "70.00")  # April last year
    books.sale(date(2025, 8, 15), "500.00")  # outside the compared months
    books.sale(date(2026, 4, 15), "100.00")

    report = GeneralLedgerService(books.session).profit_and_loss_range(
        firm_id=books.firm.id,
        from_period_id=books.period(date(2026, 4, 1)).id,
        to_period_id=books.period(date(2026, 5, 1)).id,
        compare_previous_year=True,
    )

    [sales] = report.income
    assert sales.amount == Decimal("100.00")
    assert sales.comparison_amount == Decimal("70.00")
    assert report.comparison_net_profit == Decimal("70.00")
    previous = books.session.scalar(
        select(FinancialYear).where(FinancialYear.starts_on == date(2025, 4, 1))
    )
    assert previous is not None and report.comparison_year_id == previous.id


def test_a_whole_year_is_twelve_columns() -> None:
    books = _Books()
    books.sale(date(2027, 3, 31), "10.00")
    report = GeneralLedgerService(books.session).profit_and_loss_range(
        firm_id=books.firm.id,
        from_period_id=books.period(date(2026, 4, 1)).id,
        to_period_id=books.period(date(2027, 3, 1)).id,
    )
    assert len(report.months) == 12
    assert report.income[0].months[-1] == Decimal("10.00")


def test_a_span_across_two_years_or_backwards_is_refused() -> None:
    books = _Books()
    service = GeneralLedgerService(books.session)
    with pytest.raises(ValidationError, match="within one financial year"):
        service.profit_and_loss_range(
            firm_id=books.firm.id,
            from_period_id=books.period(date(2026, 2, 1)).id,
            to_period_id=books.period(date(2026, 5, 1)).id,
        )
    with pytest.raises(ValidationError, match="before the last"):
        service.profit_and_loss_range(
            firm_id=books.firm.id,
            from_period_id=books.period(date(2026, 6, 1)).id,
            to_period_id=books.period(date(2026, 4, 1)).id,
        )
