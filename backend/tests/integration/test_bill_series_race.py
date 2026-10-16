"""Two bills racing for one series never take the same number (backlog 157).

`docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md` section 11 item 2. The counter
row of a bill series is read ``with_for_update`` inside the bill's own
transaction, so a second bill for the same prefix and year waits for the first
and reads the number after it. A row not there yet is inserted under a
savepoint; the second inserter fails on the unique key and reads the winner's
row. Neither bill fails.

Integration rather than unit: the unit suite is one SQLite connection on a
`StaticPool`, which has no second transaction to wait and no row lock to wait
on. Skipped cleanly without PostgreSQL.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.document_framework.models import BillSeriesCounter
from app.document_framework.services.bill_series import BillSeriesCounters
from app.firms.models import Firm

_YEAR = "2026-2027"


@pytest.fixture
def sessions(engine: Engine, temp_schema: str) -> Iterator[Callable[[], Session]]:
    """Hand out sessions on the disposable schema, on a pool of this file's own.

    `NullPool`, so two connections are really two transactions and nothing of
    ours is handed back to a sibling test.
    """
    own = create_engine(engine.url, poolclass=NullPool).execution_options(
        schema_translate_map={None: temp_schema}
    )
    made: list[Session] = []

    def factory() -> Session:
        """Return a new session on its own connection."""
        session = sessionmaker(bind=own, expire_on_commit=False)()
        made.append(session)
        return session

    try:
        yield factory
    finally:
        for session in made:
            session.close()
        own.dispose()


def _firm(factory: Callable[[], Session]) -> UUID:
    """Add the firm the counters belong to."""
    with factory() as session:
        firm = Firm(
            name="Race Firm",
            code=f"RACE-{uuid4().hex[:6]}",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(firm)
        session.commit()
        return firm.id


def _race(
    factory: Callable[[], Session], firm_id: UUID, bills: int, *, hold: float
) -> tuple[list[int], list[BaseException]]:
    """Issue ``bills`` numbers at once, each held ``hold`` seconds before commit."""
    issued: list[int] = []
    failures: list[BaseException] = []
    lock = threading.Lock()
    start = threading.Barrier(bills)

    def one_bill() -> None:
        """Issue one number the way a bill does, inside its own transaction."""
        session = factory()
        try:
            start.wait()
            number = BillSeriesCounters(session).issue(
                firm_id, "AS", _YEAR, floor=1, actor_id=None
            )
            time.sleep(hold)
            session.commit()
            with lock:
                issued.append(number)
        except BaseException as error:  # noqa: BLE001 - reported below
            session.rollback()
            with lock:
                failures.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=one_bill) for _ in range(bills)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return issued, failures


def test_two_bills_racing_for_a_new_series_take_one_and_two(
    sessions: Callable[[], Session],
) -> None:
    """Both insert the year's first row; the loser reads the winner's and waits."""
    firm_id = _firm(sessions)

    issued, failures = _race(sessions, firm_id, 2, hold=0.5)

    assert failures == []
    assert sorted(issued) == [1, 2]


def test_many_bills_racing_for_one_series_never_repeat_a_number(
    sessions: Callable[[], Session],
) -> None:
    """Eight bills queue on the counter row and take eight numbers."""
    firm_id = _firm(sessions)
    with sessions() as session:
        BillSeriesCounters(session).issue(firm_id, "AS", _YEAR, floor=1, actor_id=None)
        session.commit()

    issued, failures = _race(sessions, firm_id, 8, hold=0.05)

    assert failures == []
    assert sorted(issued) == list(range(2, 10))
    with sessions() as session:
        counter = session.scalar(
            select(BillSeriesCounter).where(BillSeriesCounter.firm_id == firm_id)
        )
        assert counter is not None
        assert counter.next_sequence == 10
