"""Leaving a firm takes the person off that firm's rounds.

D-TER-17. #575 fixed the **read** -- `_derived_salesman` and
`_inherited_salesman` skip an assignee who is no longer an active member, so an
order is no longer raised in the name of somebody who has left and then refused
at the delivery note, which does check (D-TER-11). It did not fix the rows:
`territory_salesman_assignments` still named them, so the round's Salespeople
tab went on listing a departed person and the coverage report went on counting
them.

**Only `tests/integration/` can prove the cross-store half.** The write is a
platform screen reaching into each firm's own store, and the unit suite builds
one SQLite schema holding every table, where `firm_store_session` and `get_db`
would resolve to the same place. What is provable here is each half on its own:
that `retire_salesman_assignments` retires exactly this firm's rows and audits
them, and that `IdentityService` announces a departure precisely when the
membership stops being active -- deactivated in place as much as deleted.
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.identity.schemas.api import UserFirmAssignment
from app.identity.services import IdentityService
from app.sales.models import SalesTerritoryNode, TerritorySalesmanAssignment
from app.sales.services.assignment_lifecycle import retire_salesman_assignments

ADMIN = uuid4()


def _session() -> Session:
    """Build one in-memory schema holding every table."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Create one firm."""
    row = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _member(session: Session, *, firm_ids: list[UUID], email: str) -> User:
    """Create one person, active in each firm named."""
    user = User(email=email, full_name="Asha Rao", password_hash="x", is_active=True)
    session.add(user)
    session.flush()
    for firm_id in firm_ids:
        session.add(UserFirm(user_id=user.id, firm_id=firm_id, is_active=True))
    session.commit()
    return user


def _round(session: Session, *, firm_id: UUID, code: str, user_id: UUID) -> UUID:
    """Put one person on one firm's round."""
    node = SalesTerritoryNode(
        firm_id=firm_id,
        hierarchy_level_id=uuid4(),
        code=code,
        name=f"{code} round",
        path=code,
    )
    session.add(node)
    session.flush()
    session.add(
        TerritorySalesmanAssignment(
            territory_id=node.id, user_id=user_id, is_primary=True
        )
    )
    session.commit()
    return node.id


def _live_assignments(session: Session, user_id: UUID) -> list[UUID]:
    """Return the territories this person is still live on."""
    return list(
        session.scalars(
            select(TerritorySalesmanAssignment.territory_id).where(
                TerritorySalesmanAssignment.user_id == user_id,
                TerritorySalesmanAssignment.is_deleted.is_(False),
            )
        )
    )


def test_retiring_takes_the_person_off_this_firms_rounds_only() -> None:
    """The firm is read through the node, because the assignment carries none.

    `territory_salesman_assignments` has no `firm_id` of its own, so in the
    shared store a query on the person alone would also reach the rounds of
    another firm they still work for.
    """
    session = _session()
    mine = _firm(session, "MINE")
    theirs = _firm(session, "THEIRS")
    user = _member(session, firm_ids=[mine.id, theirs.id], email="asha@example.com")
    left = _round(session, firm_id=mine.id, code="RT01", user_id=user.id)
    kept = _round(session, firm_id=theirs.id, code="RT02", user_id=user.id)

    retired = retire_salesman_assignments(
        session, firm_id=mine.id, user_id=user.id, actor_id=ADMIN
    )

    assert retired == 1
    assert _live_assignments(session, user.id) == [kept]
    (row,) = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_territory.salesman_retired")
    )
    assert row.entity_id == left
    assert row.firm_id == mine.id
    assert row.before_data is not None
    assert row.before_data["is_primary"] is True


def test_retiring_a_round_nobody_is_on_writes_nothing() -> None:
    """A departure from a firm that runs no rounds is not an event."""
    session = _session()
    firm = _firm(session, "QUIET")
    user = _member(session, firm_ids=[firm.id], email="bala@example.com")

    assert (
        retire_salesman_assignments(
            session, firm_id=firm.id, user_id=user.id, actor_id=ADMIN
        )
        == 0
    )
    assert session.scalars(select(AuditLog)).all() == []


def _departures(
    session: Session, user: User, assignments: list[UserFirmAssignment]
) -> list[UUID]:
    """Save the memberships and return the firms the listener was told about."""
    told: list[UUID] = []
    IdentityService(session, Settings()).set_user_firms(
        user.id, assignments, ADMIN, None, told.append
    )
    return told


def test_a_membership_deactivated_in_place_is_a_departure() -> None:
    """Both endings count, and only `is_active` decides.

    Every read-side check asks `active_member_count`, which filters
    `is_active` as well as `is_deleted`, so a membership switched off in
    place leaves the person as unable to act as one that was removed -- and
    their rounds as wrong.
    """
    session = _session()
    stays = _firm(session, "STAYS")
    switched = _firm(session, "OFF")
    removed = _firm(session, "GONE")
    user = _member(
        session,
        firm_ids=[stays.id, switched.id, removed.id],
        email="asha@example.com",
    )

    told = _departures(
        session,
        user,
        [
            UserFirmAssignment(firm_id=stays.id, is_active=True, is_primary=False),
            UserFirmAssignment(firm_id=switched.id, is_active=False, is_primary=False),
        ],
    )

    assert sorted(told, key=str) == sorted([switched.id, removed.id], key=str)


def test_a_membership_merely_reshuffled_is_no_departure() -> None:
    """Promoting a membership to primary must not retire anybody's rounds."""
    session = _session()
    firm = _firm(session, "SAME")
    user = _member(session, firm_ids=[firm.id], email="asha@example.com")

    told = _departures(
        session,
        user,
        [UserFirmAssignment(firm_id=firm.id, is_active=True, is_primary=True)],
    )

    assert told == []


def test_deleting_the_account_ends_every_membership() -> None:
    """Every `active_member_count` filters `users.is_deleted` too."""
    session = _session()
    first = _firm(session, "F1")
    second = _firm(session, "F2")
    user = _member(session, firm_ids=[first.id, second.id], email="asha@example.com")
    told: list[UUID] = []

    IdentityService(session, Settings()).delete_user(user.id, ADMIN, None, told.append)

    assert sorted(told, key=str) == sorted([first.id, second.id], key=str)


def test_the_two_halves_meet() -> None:
    """The whole path on one schema: a departure takes the round off.

    A unit test cannot open two stores, so the listener is handed this one
    session -- which is what the router hands it for a SHARED firm anyway.
    What the integration suite has to prove is that a DATABASE-mode firm's
    rows are reached at all.
    """
    session = _session()
    firm = _firm(session, "WHOLE")
    user = _member(session, firm_ids=[firm.id], email="asha@example.com")
    _round(session, firm_id=firm.id, code="RT01", user_id=user.id)

    IdentityService(session, Settings()).set_user_firms(
        user.id,
        [],
        ADMIN,
        None,
        lambda firm_id: retire_salesman_assignments(
            session, firm_id=firm_id, user_id=user.id, actor_id=ADMIN
        ),
    )

    assert _live_assignments(session, user.id) == []
