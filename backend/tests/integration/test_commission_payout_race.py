"""One live payout per person per period, held by the database.

`_assert_period_is_free` reads and then `accrue` writes, with nothing between
them, so two requests that both check before either commits both pass. Found by
the 2026-09-03 module review and driven on WHOLE01 before it was fixed: two
interleaved sessions left one salesman holding **two live payouts for the same
period**, which pays the same collections twice and leaves nothing downstream
able to say which was the real one.

The service check stays -- it gives the message somebody can act on, and it
covers *overlapping* periods, which a unique key cannot express. What these
pin is the partial unique index behind it, which is what holds when two
requests interleave.

Integration rather than unit, for the reason the file's siblings are: the unit
suite is one SQLite connection on a `StaticPool`, so there is no second
transaction to interleave with, and SQLite has no partial index at all.

Every statement names its schema rather than relying on `SET search_path`.
That setting rides on the pooled connection into whichever test gets it next,
by which time the disposable schema has been dropped -- which is why these
passed one at a time and failed together on the first attempt.
"""

# ruff: noqa: D103

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

_START, _END = date(2026, 9, 1), date(2026, 9, 30)


@pytest.fixture
def sessions(engine: Engine) -> Iterator[Callable[[], Session]]:
    """Hand out sessions on a pool of this file's own.

    Deliberately not the shared `engine`: these tests hold two connections at
    once and hand them back without a `search_path`, and a sibling that sets
    one on its session then relies on getting the same pooled connection back
    fails when the pool has been shuffled. `NullPool` keeps nothing, so
    nothing of ours reaches anybody else's test.
    """
    own = create_engine(engine.url, poolclass=NullPool)
    made: list[Session] = []

    def factory() -> Session:
        session = sessionmaker(bind=own, expire_on_commit=False)()
        made.append(session)
        return session

    try:
        yield factory
    finally:
        for session in made:
            session.close()
        own.dispose()


def _add_salesman(session: Session, schema: str) -> UUID:
    """Add a person for the payout to belong to.

    `commission_payouts.salesman_id` carries a real foreign key to `users`,
    and `create_all` builds that table in the disposable schema too, so a
    payout cannot be written without one.
    """
    salesman_id = uuid4()
    session.execute(
        text(
            f"""
            INSERT INTO "{schema}".users (
                id, email, full_name, password_hash,
                is_deleted, version, created_at, updated_at
            ) VALUES (
                :id, :email, 'Probe Salesman', 'x',
                false, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {"id": salesman_id, "email": f"{salesman_id}@probe.local"},
    )
    session.commit()
    return salesman_id


def _add_payout(
    session: Session,
    schema: str,
    *,
    firm_id: UUID,
    salesman_id: UUID,
    status: str = "DRAFT",
    start: date = _START,
    end: date = _END,
) -> None:
    """Write one payout row, the way an accrual does."""
    session.execute(
        text(
            f"""
            INSERT INTO "{schema}".commission_payouts (
                id, firm_id, salesman_id, period_start, period_end,
                basis, measured_amount, earned_amount,
                adjustment_amount, payable_amount, status, accrued_on,
                is_deleted, version, created_at, updated_at
            ) VALUES (
                :id, :firm, :salesman, :start, :end,
                'COLLECTED', 1000, 100,
                0, 100, :status, :accrued,
                false, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": uuid4(),
            "firm": firm_id,
            "salesman": salesman_id,
            "start": start,
            "end": end,
            "status": status,
            "accrued": _END,
        },
    )


def _live(session: Session, schema: str, firm_id: UUID) -> int:
    """How many of this firm's payouts still hold a claim."""
    return int(
        session.execute(
            text(
                f"""
                SELECT count(*) FROM "{schema}".commission_payouts
                WHERE firm_id = :f AND is_deleted = false
                  AND status <> 'CANCELLED'
                """
            ),
            {"f": firm_id},
        ).scalar()
        or 0
    )


def test_two_interleaved_accruals_leave_only_one_live_payout(
    sessions: Callable[[], Session], temp_schema: str
) -> None:
    """Both check, both write, and the database refuses the second.

    The interleaving two clients pressing one month-end button produce: the
    second session cannot see the first's uncommitted row, so the service's
    own read finds a free period and lets it through.
    """
    firm_id = uuid4()
    with sessions() as setup:
        salesman_id = _add_salesman(setup, temp_schema)

    one, two = sessions(), sessions()
    try:
        # Session two does its check first and finds the period free -- this
        # is the read `_assert_period_is_free` makes, and the whole race.
        assert _live(two, temp_schema, firm_id) == 0

        # Session one then accrues and commits.
        _add_payout(one, temp_schema, firm_id=firm_id, salesman_id=salesman_id)
        one.commit()

        # Session two now writes on the strength of a check that was true when
        # it made it. Deliberately in this order: with both inserts pending,
        # PostgreSQL makes the second one *wait* on the first transaction
        # rather than fail, so a test that inserted both before either
        # committed would simply hang -- which is what the first version did.
        # The violation lands on the INSERT rather than the commit, because
        # by now the conflicting row is committed and visible to the index.
        with pytest.raises(IntegrityError):
            _add_payout(two, temp_schema, firm_id=firm_id, salesman_id=salesman_id)
            two.commit()
        two.rollback()
    finally:
        one.close()
        two.close()

    with sessions() as check:
        assert (
            _live(check, temp_schema, firm_id) == 1
        ), "the same collections must not be payable twice"


def test_a_cancelled_payout_leaves_the_period_free_to_run_again(
    sessions: Callable[[], Session], temp_schema: str
) -> None:
    """A withdrawn accrual holds no claim.

    Which is what makes a period accrued at the wrong rate correctable, so the
    index has to let a second row in once the first is CANCELLED -- a bare
    unique key on the four columns would not.
    """
    firm_id = uuid4()
    with sessions() as session:
        salesman_id = _add_salesman(session, temp_schema)
        _add_payout(
            session,
            temp_schema,
            firm_id=firm_id,
            salesman_id=salesman_id,
            status="CANCELLED",
        )
        _add_payout(session, temp_schema, firm_id=firm_id, salesman_id=salesman_id)
        session.commit()

        assert _live(session, temp_schema, firm_id) == 1


def test_a_different_period_is_not_blocked(
    sessions: Callable[[], Session], temp_schema: str
) -> None:
    """The key is per period, so next month accrues normally."""
    firm_id = uuid4()
    with sessions() as session:
        salesman_id = _add_salesman(session, temp_schema)
        _add_payout(session, temp_schema, firm_id=firm_id, salesman_id=salesman_id)
        _add_payout(
            session,
            temp_schema,
            firm_id=firm_id,
            salesman_id=salesman_id,
            start=_END + timedelta(days=1),
            end=_END + timedelta(days=31),
        )
        session.commit()

        assert _live(session, temp_schema, firm_id) == 2


def test_two_people_can_each_be_paid_for_the_same_period(
    sessions: Callable[[], Session], temp_schema: str
) -> None:
    """The key is per person as well, or one accrual would block the team."""
    firm_id = uuid4()
    with sessions() as session:
        first = _add_salesman(session, temp_schema)
        second = _add_salesman(session, temp_schema)
        _add_payout(session, temp_schema, firm_id=firm_id, salesman_id=first)
        _add_payout(session, temp_schema, firm_id=firm_id, salesman_id=second)
        session.commit()

        assert _live(session, temp_schema, firm_id) == 2


def test_the_amounts_are_untouched_by_any_of_this(
    sessions: Callable[[], Session], temp_schema: str
) -> None:
    """A guard that changed a figure would be worse than none."""
    firm_id = uuid4()
    with sessions() as session:
        salesman_id = _add_salesman(session, temp_schema)
        _add_payout(session, temp_schema, firm_id=firm_id, salesman_id=salesman_id)
        session.commit()

        payable = session.execute(
            text(
                f'SELECT payable_amount FROM "{temp_schema}".commission_payouts '
                "WHERE firm_id = :f"
            ),
            {"f": firm_id},
        ).scalar()
        assert Decimal(str(payable)) == Decimal("100")
