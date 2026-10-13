"""Paying out of cash that is not there is asked about, never refused (row F2).

An expense, a payment to a supplier and a refund to a customer each answer a
question when they would leave a **cash** account below zero on their own
date, and save nothing; the same request sent again confirmed saves. A bank
account is never asked about, and neither is money coming in.

Each case goes through the router, because the router is what turns the
request's ``cash_below_zero_confirmed`` into the question: a service called by
another service (a payment run) is not asked anything.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.customers.models import Customer
from app.expenses.api.router import record_expense
from app.expenses.models import Expense
from app.expenses.schemas import ExpenseCreate
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.money_accounts import (
    CASH_BELOW_ZERO,
    KIND_BANK,
    KIND_CASH,
    money_accounts,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.settlements.api.router import record_payment, record_refund
from app.settlements.models import Settlement
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import PaymentService, ReceiptService
from app.vendors.models import Vendor
from tests.unit.report_windows import report_scope

#: Inside the seeded 2026-2027 financial year.
WHEN = date(2026, 4, 20)

CASH = "1000"
PETTY_CASH = "1005"
BANK = "1010"
RENT = "6000"


class _Books:
    """A firm whose books are open, with a customer and a supplier."""

    def __init__(self) -> None:
        """Open the books the way the Set up panel does."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session: Session = sessionmaker(bind=engine, expire_on_commit=False)()
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
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.vendor = Vendor(
            firm_id=self.firm.id,
            code="V1",
            name="Vendor One",
            display_name="Vendor One",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add_all([self.customer, self.vendor])
        self.session.commit()
        self.scope = report_scope(self.firm.id)

    def account(self, code: str) -> UUID:
        """Return the id of the account with this code."""
        account_id = self.session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.firm_id == self.firm.id, LedgerAccount.code == code
            )
        )
        assert account_id is not None, code
        return account_id

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

    def count(self, model: type) -> int:
        """Return how many rows of one table exist."""
        return int(self.session.scalar(select(func.count()).select_from(model)) or 0)

    def take_in(
        self,
        amount: str,
        *,
        method: SettlementMethodEnum = SettlementMethodEnum.CASH,
        when: date = WHEN,
    ) -> None:
        """Receive money from the customer, held on their account."""
        ReceiptService(self.session).create(
            SettlementCreate(
                party_id=self.customer.id,
                settlement_date=when,
                amount=Decimal(amount),
                method=method,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def expense(
        self,
        amount: str,
        *,
        paid_from: str,
        confirmed: bool = False,
        tds: str | None = None,
        when: date = WHEN,
    ) -> Expense:
        """Record an expense through the router; a refusal is rolled back."""
        try:
            answer = record_expense(
                payload=ExpenseCreate(
                    expense_date=when,
                    expense_account_id=self.account(RENT),
                    paid_from_account_id=self.account(paid_from),
                    amount=Decimal(amount),
                    payee="Sharma Estates",
                    tds_amount=Decimal(tds) if tds else None,
                    tds_section="194I" if tds else None,
                    cash_below_zero_confirmed=confirmed,
                ),
                scope=self.scope,
                response=Response(),
                db=self.session,
            )
        except ConflictError:
            self.session.rollback()
            raise
        assert answer.data is not None
        row = self.session.get(Expense, answer.data.id)
        assert row is not None
        return row

    def settle(
        self,
        handler: object,
        amount: str,
        *,
        party_id: UUID,
        method: SettlementMethodEnum,
        confirmed: bool = False,
    ) -> Settlement:
        """Record a payment or refund through its router handler."""
        assert callable(handler)
        try:
            answer = handler(
                payload=SettlementCreate(
                    party_id=party_id,
                    settlement_date=WHEN,
                    amount=Decimal(amount),
                    method=method,
                    cash_below_zero_confirmed=confirmed,
                ),
                scope=self.scope,
                db=self.session,
            )
        except ConflictError:
            self.session.rollback()
            raise
        row = self.session.get(Settlement, answer.data.id)
        assert row is not None
        return row


def test_petty_cash_and_cash_are_cash_and_the_bank_is_not() -> None:
    """The kind the question turns on, for the seeded chart."""
    books = _Books()
    kinds = {
        account.code: kind
        for account, kind in money_accounts(books.session, books.firm.id)
    }
    assert kinds[CASH] == KIND_CASH
    assert kinds[PETTY_CASH] == KIND_CASH
    assert kinds[BANK] == KIND_BANK


def test_an_expense_beyond_what_cash_holds_is_asked_about_and_not_saved() -> None:
    """The answer names the account, what it holds and what is being paid."""
    books = _Books()
    books.take_in("500.00")
    journals = books.count(JournalEntry)

    with pytest.raises(ConflictError) as refused:
        books.expense("800.00", paid_from=CASH)

    assert refused.value.status_code == 409
    assert refused.value.message == (
        "Cash holds 500.00 on 20-04-2026 and this pays 800.00 out of it, "
        "which leaves it 300.00 below zero. Save anyway?"
    )
    details = refused.value.details
    assert isinstance(details, dict)
    assert details["reason"] == CASH_BELOW_ZERO
    assert details["account_name"] == "Cash"
    assert details["holds"] == "500.00"
    assert details["paying"] == "800.00"
    assert books.count(Expense) == 0, "nothing is saved until it is confirmed"
    assert books.count(JournalEntry) == journals
    assert books.net(CASH) == Decimal("500.00")


def test_a_confirmed_expense_saves_and_posts() -> None:
    """Yes is an answer: the same request confirmed goes through."""
    books = _Books()
    books.take_in("500.00")

    row = books.expense("800.00", paid_from=CASH, confirmed=True)

    assert row.status == "POSTED"
    assert books.net(CASH) == Decimal("-300.00")
    assert books.net(RENT) == Decimal("800.00")


def test_petty_cash_is_asked_about_too() -> None:
    """An account with no purpose of its own, cash by where it sits."""
    books = _Books()

    with pytest.raises(ConflictError) as refused:
        books.expense("120.00", paid_from=PETTY_CASH)

    assert refused.value.message.startswith(
        "Petty Cash holds 0.00 on 20-04-2026 and this pays 120.00 out of it"
    )
    assert books.expense("120.00", paid_from=PETTY_CASH, confirmed=True).id


def test_an_account_already_below_zero_says_so() -> None:
    """Nothing is held, so the sentence does not say it holds a minus."""
    books = _Books()
    books.expense("300.00", paid_from=CASH, confirmed=True)

    with pytest.raises(ConflictError) as refused:
        books.expense("1.00", paid_from=CASH)

    assert refused.value.message == (
        "Cash is already 300.00 below zero on 20-04-2026 and this pays 1.00 "
        "more out of it. Save anyway?"
    )
    details = refused.value.details
    assert isinstance(details, dict)
    assert details["holds"] == "-300.00"


def test_an_expense_cash_covers_is_not_asked_about() -> None:
    """Exactly what the account holds leaves it at zero, which is not below."""
    books = _Books()
    books.take_in("500.00")

    books.expense("500.00", paid_from=CASH)

    assert books.net(CASH) == Decimal("0.00")


def test_a_bank_account_goes_below_zero_without_a_question() -> None:
    """An overdraft is the bank's business; nothing is asked."""
    books = _Books()

    books.expense("25000.00", paid_from=BANK)

    assert books.net(BANK) == Decimal("-25000.00")


def test_only_the_money_that_leaves_is_judged() -> None:
    """Tax deducted at source never left the cash box."""
    books = _Books()
    books.take_in("900.00")

    books.expense("1000.00", paid_from=CASH, tds="100.00")

    assert books.net(CASH) == Decimal("0.00")


def test_the_day_judged_is_the_expenses_own() -> None:
    """Money that arrived the next day was not there to pay with."""
    books = _Books()
    books.take_in("500.00", when=WHEN + timedelta(days=1))

    with pytest.raises(ConflictError) as refused:
        books.expense("100.00", paid_from=CASH)

    assert "Cash holds 0.00 on 20-04-2026" in refused.value.message


def test_a_cash_payment_to_a_supplier_is_asked_about_then_saved() -> None:
    """The supplier's payment, on account: asked, confirmed, posted."""
    books = _Books()
    books.take_in("200.00")

    with pytest.raises(ConflictError) as refused:
        books.settle(
            record_payment,
            "700.00",
            party_id=books.vendor.id,
            method=SettlementMethodEnum.CASH,
        )

    details = refused.value.details
    assert isinstance(details, dict)
    assert details["reason"] == CASH_BELOW_ZERO
    assert details["holds"] == "200.00"
    assert details["paying"] == "700.00"
    assert books.count(Settlement) == 1, "only the receipt that put 200 in"

    paid = books.settle(
        record_payment,
        "700.00",
        party_id=books.vendor.id,
        method=SettlementMethodEnum.CASH,
        confirmed=True,
    )
    assert paid.settlement_number.startswith("PY")
    assert books.net(CASH) == Decimal("-500.00")


def test_a_bank_payment_to_a_supplier_is_not_asked_about() -> None:
    """Paid from the bank with nothing in it, saved without a question."""
    books = _Books()

    books.settle(
        record_payment,
        "700.00",
        party_id=books.vendor.id,
        method=SettlementMethodEnum.BANK,
    )

    assert books.net(BANK) == Decimal("-700.00")
    assert books.net(CASH) == Decimal("0.00")


def test_a_cash_refund_is_asked_about_then_saved() -> None:
    """The customer paid into the bank and is handed cash back."""
    books = _Books()
    books.take_in("200.00", method=SettlementMethodEnum.BANK)

    with pytest.raises(ConflictError) as refused:
        books.settle(
            record_refund,
            "200.00",
            party_id=books.customer.id,
            method=SettlementMethodEnum.CASH,
        )

    assert refused.value.message.startswith("Cash holds 0.00 on 20-04-2026")
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("200.00")

    refund = books.settle(
        record_refund,
        "200.00",
        party_id=books.customer.id,
        method=SettlementMethodEnum.CASH,
        confirmed=True,
    )
    assert refund.settlement_number.startswith("RF")
    assert books.net(CASH) == Decimal("-200.00")
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("0.00")


def test_money_coming_in_is_never_asked_about() -> None:
    """A receipt into cash already below zero only makes it better."""
    books = _Books()
    books.expense("300.00", paid_from=CASH, confirmed=True)

    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("100.00"),
            method=SettlementMethodEnum.CASH,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ask_before_cash_below_zero=True,
    )
    books.session.commit()

    assert books.net(CASH) == Decimal("-200.00")


def test_a_service_called_without_the_question_saves() -> None:
    """A payment run, an import: nobody is there to answer, so none is asked."""
    books = _Books()

    PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("700.00"),
            method=SettlementMethodEnum.CASH,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.net(CASH) == Decimal("-700.00")
