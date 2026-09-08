"""Who am I, and where do I start: the two self-service reads and writes.

The login response carries tokens only, the token carries roles and
permissions and never a name, and ``GET /users/{id}`` needs ``USER_VIEW`` --
so until ``GET /me`` existed the desktop could show a signed-in person nothing
but the address they typed at the login form, and after a restored session not
even that. And the primary firm, which decides where a sign-in lands, could be
set only by an administrator through ``PUT /users/{id}/firms``, which replaces
the whole membership list and is held to the caller's reach. Where a person
lands is their own decision, so ``PUT /me/primary-firm`` touches that one flag,
for the caller alone, among the firms they belong to.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import BusinessRuleError
from app.firms.models import Firm
from app.identity.models import PlatformAdmin, User, UserFirm
from app.identity.schemas.api import UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Str0ng-Passw0rd!"
ACTOR = uuid4()


def _service() -> tuple[IdentityService, Session]:
    """Build the service over a seeded in-memory schema."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_system_rbac(session)
    session.commit()
    return IdentityService(session, Settings()), session


def _firm(session: Session, code: str, *, active: bool = True) -> Firm:
    """Create one firm."""
    firm = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=active,
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(firm)
    session.commit()
    return firm


def _user(service: IdentityService, email: str) -> User:
    """Create one user, in no firm."""
    return service.create_user(
        UserCreate(email=email, full_name="Asha Rao", password=PASSWORD),
        actor_id=ACTOR,
    )


def _member(session: Session, user: User, firm: Firm, *, primary: bool = False) -> None:
    """Put a user in a firm."""
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=primary,
            is_active=True,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()


def _primaries(session: Session, user_id: UUID) -> set[UUID]:
    """Return the firms flagged primary for one user."""
    return set(
        session.scalars(
            select(UserFirm.firm_id).where(
                UserFirm.user_id == user_id,
                UserFirm.is_primary.is_(True),
                UserFirm.is_deleted.is_(False),
            )
        )
    )


def test_me_names_the_person_and_where_they_start() -> None:
    """Name, address, designation and primary firm -- and nothing needing a code."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "asha@example.com")
    _member(session, person, one)
    _member(session, person, two, primary=True)

    user, is_platform_admin, primary = service.describe_me(person.id)

    assert (user.email, user.full_name) == ("asha@example.com", "Asha Rao")
    assert is_platform_admin is False
    assert primary == two.id


def test_me_says_when_somebody_is_a_platform_administrator() -> None:
    """The designation is a fact about the person, so the menu may show it."""
    service, session = _service()
    boss = _user(service, "boss@example.com")
    session.add(PlatformAdmin(user_id=boss.id, created_by=ACTOR, updated_by=ACTOR))
    session.commit()

    _, is_platform_admin, primary = service.describe_me(boss.id)

    assert is_platform_admin is True
    assert primary is None


def test_a_person_moves_their_own_primary_and_only_one_remains() -> None:
    """The flag moves; the memberships stay; exactly one primary results."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "asha@example.com")
    _member(session, person, one, primary=True)
    _member(session, person, two)

    service.set_own_primary_firm(person.id, two.id)

    assert _primaries(session, person.id) == {two.id}
    memberships = set(
        session.scalars(
            select(UserFirm.firm_id).where(
                UserFirm.user_id == person.id, UserFirm.is_deleted.is_(False)
            )
        )
    )
    assert memberships == {one.id, two.id}, "nothing but the flag moved"


def test_a_firm_they_do_not_belong_to_is_refused_by_name() -> None:
    """Not silently ignored: the person is choosing, and the choice is wrong."""
    service, session = _service()
    mine, theirs = _firm(session, "F1"), _firm(session, "F2")
    person = _user(service, "asha@example.com")
    _member(session, person, mine, primary=True)

    with pytest.raises(BusinessRuleError) as refusal:
        service.set_own_primary_firm(person.id, theirs.id)

    assert "belong to" in str(refusal.value)
    assert _primaries(session, person.id) == {mine.id}


def test_a_retired_firm_cannot_be_chosen() -> None:
    """A membership of a firm that no longer trades is not a place to land."""
    service, session = _service()
    live, retired = _firm(session, "F1"), _firm(session, "F2", active=False)
    person = _user(service, "asha@example.com")
    _member(session, person, live, primary=True)
    _member(session, person, retired)

    with pytest.raises(BusinessRuleError):
        service.set_own_primary_firm(person.id, retired.id)


def test_choosing_the_current_primary_changes_nothing() -> None:
    """Idempotent, so a repeated save is not a second audit row."""
    service, session = _service()
    one = _firm(session, "F1")
    person = _user(service, "asha@example.com")
    _member(session, person, one, primary=True)

    service.set_own_primary_firm(person.id, one.id)

    assert _primaries(session, person.id) == {one.id}
