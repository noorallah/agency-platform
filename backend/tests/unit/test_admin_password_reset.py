"""A platform administrator sets somebody else's password.

The self-service change needs the current password. This is for the cases
where nobody can supply it -- forgotten, locked out, or the person has left
and the account is being handed over. It clears a login lock and revokes
every session, defaults to forcing a change at the next sign-in so a password
an administrator chose is a way in rather than a password kept, and refuses
the caller's own account, which has My profile for that.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.security.password import PasswordSecurity
from app.core.utils.dates import utc_now
from app.identity.models import PasswordHistory, RefreshToken, User
from app.identity.schemas.api import UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

OLD = "Old-Passw0rd!!"
NEW = "New-Passw0rd!!"
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


def _user(service: IdentityService, email: str) -> User:
    """Create one user on the old password."""
    return service.create_user(
        UserCreate(email=email, full_name="Person", password=OLD), actor_id=ACTOR
    )


def _history(session: Session, user_id: UUID) -> int:
    """How many old hashes are kept for one user."""
    return len(
        session.scalars(
            select(PasswordHistory.id).where(PasswordHistory.user_id == user_id)
        ).all()
    )


def test_the_new_password_works_and_the_old_one_does_not() -> None:
    """The point of it: a way in for somebody who has none."""
    service, session = _service()
    person = _user(service, "person@example.com")

    service.reset_password(person.id, NEW, ACTOR)

    row = session.get(User, person.id)
    passwords = PasswordSecurity()
    assert passwords.verify_password(NEW, row.password_hash)
    assert not passwords.verify_password(OLD, row.password_hash)


def test_a_reset_forces_a_change_by_default_and_can_be_told_not_to() -> None:
    """A password an administrator chose is a way in, not a password kept."""
    service, session = _service()
    person = _user(service, "person@example.com")

    service.reset_password(person.id, NEW, ACTOR)
    assert session.get(User, person.id).force_password_change is True

    service.reset_password(person.id, "Other-Passw0rd!!", ACTOR, force_change=False)
    assert session.get(User, person.id).force_password_change is False


def test_a_reset_clears_a_lock_and_revokes_every_session() -> None:
    """What a locked-out person is asking for, and what a leaver loses."""
    service, session = _service()
    person = _user(service, "person@example.com")
    row = session.get(User, person.id)
    row.failed_login_attempts, row.locked_until = 5, utc_now() + timedelta(minutes=15)
    version = row.authorization_version
    session.add(
        RefreshToken(
            user_id=person.id,
            token_hash="x" * 64,
            expires_at=utc_now() + timedelta(days=7),
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()

    service.reset_password(person.id, NEW, ACTOR)

    row = session.get(User, person.id)
    assert (row.failed_login_attempts, row.locked_until) == (0, None)
    assert row.authorization_version == version + 1
    live = session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == person.id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    assert live == []


def test_the_old_hash_is_kept_so_the_reset_cannot_be_undone() -> None:
    """Changing back to the old password afterwards is refused as a reuse."""
    service, session = _service()
    person = _user(service, "person@example.com")

    service.reset_password(person.id, NEW, ACTOR)

    assert _history(session, person.id) == 1
    with pytest.raises(BusinessRuleError, match="recent password"):
        service.change_password(person.id, NEW, OLD)


def test_the_policy_still_applies() -> None:
    """An administrator cannot hand out a weak password either."""
    service, session = _service()
    person = _user(service, "person@example.com")

    with pytest.raises(ValidationError):
        service.reset_password(person.id, "short", ACTOR)


def test_ones_own_account_is_refused() -> None:
    """My profile is that route, and it asks for the current password."""
    service, session = _service()
    me = _user(service, "me@example.com")

    with pytest.raises(BusinessRuleError, match="My profile"):
        service.reset_password(me.id, NEW, me.id)
