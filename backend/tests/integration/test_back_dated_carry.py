"""A back-dated posting moves every later period in one statement (PLT-5).

The carry into later periods became one set-based ``UPDATE`` with a subquery
over the periods; SQLite and PostgreSQL treat ``IN (subquery)`` and the
session refresh differently enough that the deployment target has to see it.
May is posted first, April's sale arrives afterwards, and May's stored
opening must carry it -- then a reversal in April takes it back out.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models import JournalEntry, LedgerBalance
from app.finance.schemas import AccountingPeriodCreate
from app.finance.services import FinanceService, JournalEntryEngine
from tests.unit.test_finance_module import _Book, _firm, _sale_lines


def test_a_back_dated_posting_moves_later_periods_on_postgres(
    temp_session: Session,
) -> None:
    """April's sale, posted after May's, is carried into May's opening."""
    session = temp_session
    firm = _firm(session)
    actor_id = uuid4()
    book = _Book(session, firm.id, actor_id)
    engine = JournalEntryEngine(session)
    may = FinanceService(session).create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=book.year.id,
            period_number=2,
            code="P2",
            name="May 2026",
            starts_on=date(2026, 5, 1),
            ends_on=date(2026, 5, 31),
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    def post(period_id: UUID, on: date, reference: str, amount: str) -> None:
        """Post one cash sale and commit."""
        entry = engine.create_entry(
            firm_id=firm.id,
            journal_type_id=book.journal_type.id,
            voucher_type_id=book.voucher_type.id,
            accounting_period_id=period_id,
            journal_date=on,
            reference_number=reference,
            description="Cash sale",
            lines=_sale_lines(book, amount),
            actor_id=actor_id,
        )
        engine.post_entry(entry.id, firm_id=firm.id, actor_id=actor_id)
        session.commit()

    post(may.id, date(2026, 5, 10), "JV-MAY", "40.00")
    post(book.period.id, date(2026, 4, 20), "JV-APR", "100.00")
    cash = session.scalar(
        select(LedgerBalance).where(
            LedgerBalance.accounting_period_id == may.id,
            LedgerBalance.ledger_account_id == book.cash.id,
        )
    )
    assert cash is not None
    assert (cash.opening_balance, cash.closing_balance) == (
        Decimal("100.00"),
        Decimal("140.00"),
    )

    april = session.scalar(
        select(JournalEntry).where(JournalEntry.reference_number == "JV-APR")
    )
    assert april is not None
    engine.reverse_entry(
        april.id,
        firm_id=firm.id,
        reference_number="JV-APR-REV",
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 30),
        actor_id=actor_id,
    )
    session.commit()
    session.refresh(cash)
    assert (cash.opening_balance, cash.closing_balance) == (
        Decimal("0.00"),
        Decimal("40.00"),
    )
