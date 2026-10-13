"""The year after the firm's last one, started by the firm itself (D-FIN-32).

Found trying year end on a fixture firm: the bill numbers of the next year
start by themselves, off the document's date, but the year and its months do
not, and nothing a firm's own people could reach made them. On the first of
April every document would have been refused for want of a period.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.api.router import start_next_financial_year
from app.finance.models import AccountingPeriod, FinancialYear
from app.finance.schemas import AccountingPeriodCreate, FinancialYearCreate
from app.finance.services import FinanceService
from app.finance.services import finance_service as module
from app.firms.models import Firm


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    """Store one Indian firm whose year begins in April."""
    firm = Firm(
        name="Acme Firm",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _year(
    session: Session,
    firm_id: UUID,
    actor_id: UUID,
    *,
    code: str,
    starts_on: date,
    ends_on: date,
) -> FinancialYear:
    """Make one year with a single month in it, as a firm in use has."""
    service = FinanceService(session)
    year = service.create_financial_year(
        FinancialYearCreate(code=code, name=code, starts_on=starts_on, ends_on=ends_on),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    service.create_accounting_period(
        AccountingPeriodCreate(
            financial_year_id=year.id,
            period_number=1,
            code="P01",
            name="First month",
            starts_on=starts_on,
            ends_on=date(starts_on.year, starts_on.month, 28),
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    return year


def _today(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    """Fix the firm's own day, so the test reads the same next April."""
    monkeypatch.setattr(module, "firm_today", lambda session, firm_id: day)


def _periods(session: Session, year_id: UUID) -> list[AccountingPeriod]:
    """Return a year's months in order."""
    return list(
        session.scalars(
            select(AccountingPeriod)
            .where(AccountingPeriod.financial_year_id == year_id)
            .order_by(AccountingPeriod.period_number)
        )
    )


def test_the_next_year_runs_on_with_its_twelve_months(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """April to March follows April to March, and the year in hand stays open."""
    session = _session()
    firm = _firm(session)
    actor_id = uuid4()
    current = _year(
        session,
        firm.id,
        actor_id,
        code="FY2026",
        starts_on=date(2026, 4, 1),
        ends_on=date(2027, 3, 31),
    )
    _today(monkeypatch, date(2027, 3, 20))

    year = FinanceService(session).start_next_financial_year(
        firm_id=firm.id, actor_id=actor_id
    )

    assert (year.code, year.name) == ("FY2027", "Financial Year 2027-2028")
    assert (year.starts_on, year.ends_on) == (date(2027, 4, 1), date(2028, 3, 31))
    assert year.is_locked is False
    months = _periods(session, year.id)
    assert [month.code for month in months] == [f"P{n:02d}" for n in range(1, 13)]
    assert (months[0].name, months[0].starts_on, months[0].ends_on) == (
        "April 2027",
        date(2027, 4, 1),
        date(2027, 4, 30),
    )
    # February of a leap year, and no day between two months.
    assert months[10].ends_on == date(2028, 2, 29)
    assert months[11].ends_on == year.ends_on
    for earlier, later in zip(months, months[1:], strict=False):
        assert (later.starts_on - earlier.ends_on).days == 1
    assert {month.status for month in months} == {"OPEN"}
    # Starting the next year closes nothing of this one.
    assert current.is_locked is False
    assert [month.status for month in _periods(session, current.id)] == ["OPEN"]
    actions = set(
        session.scalars(select(AuditLog.action).where(AuditLog.entity_id == year.id))
    )
    assert "finance.financial_year.created" in actions


def test_a_year_that_has_not_begun_is_not_followed_by_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressed twice in March, the second is refused; in April it is not."""
    session = _session()
    firm = _firm(session)
    actor_id = uuid4()
    _year(
        session,
        firm.id,
        actor_id,
        code="FY2026",
        starts_on=date(2026, 4, 1),
        ends_on=date(2027, 3, 31),
    )
    service = FinanceService(session)
    _today(monkeypatch, date(2027, 3, 20))
    service.start_next_financial_year(firm_id=firm.id, actor_id=actor_id)

    with pytest.raises(ValidationError, match="FY2027 is already there"):
        service.start_next_financial_year(firm_id=firm.id, actor_id=actor_id)

    _today(monkeypatch, date(2027, 4, 1))
    later = service.start_next_financial_year(firm_id=firm.id, actor_id=actor_id)
    assert (later.code, later.starts_on) == ("FY2028", date(2028, 4, 1))


def test_a_firm_with_no_year_is_told_where_its_first_one_comes_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is nothing to run on from until the books are opened."""
    session = _session()
    firm = _firm(session)
    _today(monkeypatch, date(2026, 10, 13))

    with pytest.raises(ValidationError, match="no financial year to run on from"):
        FinanceService(session).start_next_financial_year(
            firm_id=firm.id, actor_id=uuid4()
        )


def test_a_code_already_taken_is_not_asked_for_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A firm that names a year by the year it ends in already holds FY2027."""
    session = _session()
    firm = _firm(session)
    actor_id = uuid4()
    _year(
        session,
        firm.id,
        actor_id,
        code="FY2027",
        starts_on=date(2026, 4, 1),
        ends_on=date(2027, 3, 31),
    )
    _today(monkeypatch, date(2026, 10, 13))

    year = FinanceService(session).start_next_financial_year(
        firm_id=firm.id, actor_id=actor_id
    )

    assert year.code == "FY2027-28"
    assert year.starts_on == date(2027, 4, 1)


def test_a_calendar_year_is_named_by_its_one_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """January to December follows January to December."""
    session = _session()
    firm = _firm(session)
    actor_id = uuid4()
    _year(
        session,
        firm.id,
        actor_id,
        code="FY2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
    )
    _today(monkeypatch, date(2026, 10, 13))

    year = FinanceService(session).start_next_financial_year(
        firm_id=firm.id, actor_id=actor_id
    )

    assert (year.code, year.name) == ("FY2027", "Financial Year 2027")
    assert (year.starts_on, year.ends_on) == (date(2027, 1, 1), date(2027, 12, 31))
    assert _periods(session, year.id)[1].ends_on == date(2027, 2, 28)


def test_the_route_answers_with_the_year_and_says_what_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The firm's own people start it: no platform administrator is asked."""
    session = _session()
    firm = _firm(session)
    actor_id = uuid4()
    _year(
        session,
        firm.id,
        actor_id,
        code="FY2026",
        starts_on=date(2026, 4, 1),
        ends_on=date(2027, 3, 31),
    )
    session.commit()
    _today(monkeypatch, date(2026, 10, 13))
    permissions = ["FINANCIAL_YEAR_CREATE"]
    scope = ResolvedFirmScope(
        principal=Principal(
            subject=actor_id,
            roles=frozenset(),
            permissions=frozenset(permissions),
            claims=TokenClaims(
                sub=str(actor_id),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                permissions=permissions,
            ),
        ),
        firm_id=firm.id,
    )

    answer = start_next_financial_year(scope=scope, db=session)

    assert answer.data is not None
    assert answer.data.code == "FY2027"
    assert answer.message == "Financial year FY2027 started, with its twelve months."
    assert len(_periods(session, answer.data.id)) == 12
