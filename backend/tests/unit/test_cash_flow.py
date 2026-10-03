"""The cash flow statement, by the indirect method (ACC-9, decision A87).

In April 2026 the owner puts in 1,00,000 of capital, the firm sells 50,000 on
credit and collects 30,000 of it, buys furniture for 20,000 and borrows 40,000.
The bank ends 1,50,000 up, and the statement explains every rupee of it:
operating 30,000 (profit 50,000, receivables up 20,000), investing -20,000,
financing 1,40,000.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.finance.models import AccountingPeriod, LedgerAccount
from app.finance.schemas import (
    AccountGroupCreate,
    AccountTypeEnum,
    LedgerAccountCreate,
)
from app.finance.services import FinanceService
from app.finance.services.cash_flow import CashFlowService
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from tests.unit.test_settlements import _Books, _session_factory

D = Decimal
APRIL = date(2026, 4, 15)


def _account(books: _Books, code: str) -> UUID:
    found = books.session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == books.firm.id, LedgerAccount.code == code
        )
    )
    assert found is not None, code
    return found


def _new_account(
    books: _Books, group: str, name: str, kind: AccountTypeEnum, code: str
) -> UUID:
    finance = FinanceService(books.session)
    made = finance.create_account_group(
        AccountGroupCreate(code=group, name=name, account_type=kind),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    account = finance.create_ledger_account(
        LedgerAccountCreate(
            account_group_id=made.id, code=code, name=name, account_type=kind
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return account.id


def _post(
    books: _Books, reference: str, debit: UUID, credit: UUID, amount: str
) -> None:
    context = DocumentPostingService(books.session).context_for(books.firm.id, APRIL)
    engine = JournalEntryEngine(books.session)
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=context.journal_type_id,
        voucher_type_id=context.voucher_type_id,
        accounting_period_id=context.accounting_period_id,
        journal_date=APRIL,
        reference_number=reference,
        description=reference,
        lines=[
            JournalLineData(ledger_account_id=debit, debit_amount=D(amount)),
            JournalLineData(ledger_account_id=credit, credit_amount=D(amount)),
        ],
        actor_id=books.actor_id,
    )
    engine.post_entry(entry.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()


def test_the_statement_explains_the_change_in_cash_and_bank() -> None:
    books = _Books(_session_factory()())
    bank = _account(books, "1010")
    receivables = _account(books, "1100")
    sales = _account(books, "4000")
    capital = _account(books, "3000")
    furniture = _new_account(books, "FA", "Furniture", AccountTypeEnum.ASSET, "1590")
    loan = _new_account(books, "LTL", "Bank Loan", AccountTypeEnum.LIABILITY, "2590")
    _post(books, "CAPITAL", bank, capital, "100000")
    _post(books, "SALE", receivables, sales, "50000")
    _post(books, "COLLECT", bank, receivables, "30000")
    _post(books, "FURNITURE", furniture, bank, "20000")
    _post(books, "LOAN", bank, loan, "40000")

    period = books.session.scalar(
        select(AccountingPeriod.id).where(
            AccountingPeriod.firm_id == books.firm.id,
            AccountingPeriod.starts_on <= APRIL,
            AccountingPeriod.ends_on >= APRIL,
        )
    )
    assert period is not None
    found = CashFlowService(books.session).statement(
        firm_id=books.firm.id, from_period_id=period, to_period_id=period
    )
    assert found.net_profit == D("50000.00")
    assert [(line.account_code, line.amount) for line in found.operating] == [
        ("1100", D("-20000.00"))
    ], "receivables up 20,000: sold but not collected"
    assert found.operating_total == D("30000.00")
    assert [(line.account_code, line.amount) for line in found.investing] == [
        ("1590", D("-20000.00"))
    ]
    assert sorted((line.account_code, line.amount) for line in found.financing) == [
        ("2590", D("40000.00")),
        ("3000", D("100000.00")),
    ]
    assert (found.opening_cash, found.closing_cash) == (D("0.00"), D("150000.00"))
    assert found.net_change == D("150000.00")
    assert found.is_reconciled
