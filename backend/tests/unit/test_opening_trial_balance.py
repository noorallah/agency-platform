"""The opening trial balance: day-one cash, bank, loans and taxes (backlog 36).

A firm arriving from another tool could enter those only as one hand journal
each. These pin the statement: entered by account code, the difference to
opening balance equity, replaced whole by reversing the one standing, all
or nothing with every bad row named, and closed to the sub-ledger accounts
that have their own opening paths.
"""

# ruff: noqa: D101,D102,D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import optional_firm_scope, required_firm_scope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.api.router import (
    get_opening_trial_balance,
    replace_opening_trial_balance,
)
from app.finance.models import JournalEntry, JournalLine, JournalStatus, LedgerAccount
from app.finance.schemas import OpeningBalanceLineInput, OpeningTrialBalanceReplace
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.opening_balances import (
    OpeningLineInput,
    OpeningTrialBalanceService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import UserFirm

pytestmark = pytest.mark.typed_document_numbers

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")
_CUTOVER = date(2026, 4, 1)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    firm = Firm(
        name="Acme",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=_ACTOR
    )
    session.commit()
    return firm


def _line(code: str, debit: str = "0", credit: str = "0") -> OpeningLineInput:
    return OpeningLineInput(
        account_code=code, debit_amount=Decimal(debit), credit_amount=Decimal(credit)
    )


def _balance(session: Session, firm: Firm, code: str) -> Decimal:
    """Debit minus credit on an account across everything posted."""
    total = session.scalar(
        select(func.sum(JournalLine.debit_amount - JournalLine.credit_amount))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(
            JournalEntry.firm_id == firm.id,
            LedgerAccount.code == code,
            JournalEntry.status.in_(
                [JournalStatus.POSTED.value, JournalStatus.REVERSED.value]
            ),
        )
    )
    return Decimal(total or 0)


def _replace(
    session: Session, firm: Firm, *lines: OpeningLineInput, on: date = _CUTOVER
) -> None:
    OpeningTrialBalanceService(session).replace(
        firm_id=firm.id, as_of_date=on, lines=list(lines), actor_id=_ACTOR
    )
    session.commit()


class TestPosting:
    def test_the_difference_goes_to_opening_balance_equity(self) -> None:
        session = _session()
        firm = _firm(session)

        _replace(
            session,
            firm,
            _line("1000", debit="15000"),
            _line("1010", debit="235000"),
            _line("2700", credit="4000"),
        )

        view = OpeningTrialBalanceService(session).current(firm.id)
        assert view.as_of_date == _CUTOVER
        assert view.reference_number == "OTB-1"
        assert [row.account_code for row in view.lines] == ["1000", "1010", "2700"]
        assert view.total_debit == Decimal("250000")
        assert view.total_credit == Decimal("4000")
        assert view.equity_difference == Decimal("246000")
        assert _balance(session, firm, "1010") == Decimal("235000")
        assert _balance(session, firm, "3000") == Decimal("-246000")

    def test_more_credit_than_debit_debits_the_equity(self) -> None:
        session = _session()
        firm = _firm(session)

        _replace(session, firm, _line("1000", debit="100"), _line("2700", credit="300"))

        view = OpeningTrialBalanceService(session).current(firm.id)
        assert view.equity_difference == Decimal("-200")
        assert _balance(session, firm, "3000") == Decimal("200")

    def test_nothing_entered_reads_as_empty(self) -> None:
        session = _session()
        firm = _firm(session)

        view = OpeningTrialBalanceService(session).current(firm.id)

        assert view.journal_entry_id is None
        assert view.lines == []


class TestReplacing:
    def test_a_second_statement_reverses_the_first(self) -> None:
        session = _session()
        firm = _firm(session)
        _replace(session, firm, _line("1000", debit="500"))

        _replace(session, firm, _line("1000", debit="800"), on=date(2026, 4, 2))

        view = OpeningTrialBalanceService(session).current(firm.id)
        assert view.reference_number == "OTB-2"
        assert view.as_of_date == date(2026, 4, 2)
        assert _balance(session, firm, "1000") == Decimal("800")
        first = session.scalar(
            select(JournalEntry).where(JournalEntry.reference_number == "OTB-1")
        )
        assert first is not None
        assert first.status == JournalStatus.REVERSED.value
        reversal = session.scalar(
            select(JournalEntry).where(JournalEntry.reference_number == "OTB-1-REV")
        )
        assert reversal is not None
        assert reversal.journal_date == _CUTOVER

    def test_an_empty_statement_takes_it_off(self) -> None:
        session = _session()
        firm = _firm(session)
        _replace(session, firm, _line("1000", debit="500"))

        _replace(session, firm)

        assert OpeningTrialBalanceService(session).current(firm.id).lines == []
        assert _balance(session, firm, "1000") == Decimal("0")
        assert _balance(session, firm, "3000") == Decimal("0")

    def test_the_journal_screen_cannot_reverse_it(self) -> None:
        session = _session()
        firm = _firm(session)
        _replace(session, firm, _line("1000", debit="500"))
        entry_id = OpeningTrialBalanceService(session).current(firm.id).journal_entry_id
        assert entry_id is not None

        with pytest.raises(ValidationError, match="opening trial balance"):
            JournalEntryEngine(session).reverse_by_hand(
                entry_id,
                firm_id=firm.id,
                reference_number="JV-9",
                actor_id=_ACTOR,
            )


class TestRefusals:
    def test_every_bad_row_is_named_and_nothing_is_written(self) -> None:
        session = _session()
        firm = _firm(session)
        _replace(session, firm, _line("1000", debit="500"))

        with pytest.raises(ValidationError) as caught:
            _replace(
                session,
                firm,
                _line("1000", debit="900"),
                _line("9999", debit="1"),
                _line("1000", debit="2"),
                _line("1100", debit="3"),
                _line("2100", credit="4"),
                _line("1200", debit="5"),
                _line("3000", credit="6"),
                _line("1010"),
            )
        session.rollback()

        message = str(caught.value)
        assert "row 2: no ledger account has code '9999'" in message
        assert "row 3: 1000 appears more than once" in message
        assert "row 4: 1100" in message
        assert "row 5: 2100" in message
        assert "row 6: 1200" in message
        assert "row 7: 3000" in message and "opening balance equity" in message
        assert "row 8: 1010 needs either a debit or a credit, not neither" in message
        # The first statement still stands, untouched.
        view = OpeningTrialBalanceService(session).current(firm.id)
        assert view.reference_number == "OTB-1"
        assert _balance(session, firm, "1000") == Decimal("500")

    def test_a_date_with_no_open_period_leaves_the_old_statement(self) -> None:
        session = _session()
        firm = _firm(session)
        _replace(session, firm, _line("1000", debit="500"))

        with pytest.raises(ValidationError):
            _replace(session, firm, _line("1000", debit="1"), on=date(2020, 1, 1))
        session.rollback()

        assert OpeningTrialBalanceService(session).current(
            firm.id
        ).reference_number == ("OTB-1")


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset({"ACCOUNTANT"}),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def test_the_routes_read_and_replace_it() -> None:
    session = _session()
    firm = _firm(session)
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    scope = required_firm_scope(
        optional_firm_scope(
            principal=_principal(user_id, {"JOURNAL_VIEW", "JOURNAL_POST"}),
            db=session,
            x_firm_id=firm.id,
        )
    )

    saved = replace_opening_trial_balance(
        OpeningTrialBalanceReplace(
            as_of_date=_CUTOVER,
            lines=[
                OpeningBalanceLineInput(
                    account_code="1010", debit_amount=Decimal("1000")
                )
            ],
        ),
        scope,
        session,
    )
    assert saved.message == "Opening trial balance saved as OTB-1."

    read = get_opening_trial_balance(scope, session).data
    assert read.lines[0].account_name == "Bank"
    assert read.equity_difference == Decimal("1000")
