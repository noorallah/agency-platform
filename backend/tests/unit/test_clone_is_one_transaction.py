"""Hiring like somebody is one transaction, not three commits.

D-IDN-8. `clone_user` called `create_user`, which commits, then
`set_user_roles`, which commits, then copied the memberships and audited --
"a chain of committing services is not a transaction". A failure after the
first left an account holding the address with no roles and no firms, and the
retry was then refused 409 on the email. Live: the `t0919subq` clone's rows
committed at 11:50:39.660, .846 and .943 IST.

The fix is the shape this repository uses everywhere else: `stage_*` internals
that flush, public wrappers that commit, and one commit for the whole act.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.firms.models import Firm
from app.identity.models import Role, User, UserFirm, UserRole
from app.identity.schemas.api import UserCloneRequest, UserCreate
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


def _firm(session: Session, code: str) -> Firm:
    """Create one active firm."""
    firm = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=True,
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(firm)
    session.commit()
    return firm


def _source(service: IdentityService, session: Session, firm: Firm) -> User:
    """Create the person whose access is being copied."""
    user = service.create_user(
        UserCreate(email="asha@example.com", full_name="Asha", password=PASSWORD),
        actor_id=ACTOR,
    )
    session.add(
        UserFirm(
            user_id=user.id,
            firm_id=firm.id,
            is_primary=True,
            is_active=True,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()
    role = session.scalar(select(Role).where(Role.code == "CASHIER"))
    assert role is not None
    service.set_user_roles(user.id, [role.id], ACTOR, None)
    return user


def _request() -> UserCloneRequest:
    """Build the new person's own details."""
    return UserCloneRequest(
        email="new.hire@example.com", full_name="New Hire", password=PASSWORD
    )


def _clone_row(session: Session) -> User | None:
    """Return the clone's account, if one was written."""
    session.expire_all()
    return session.scalar(
        select(User).where(
            User.email == "new.hire@example.com", User.is_deleted.is_(False)
        )
    )


def test_a_failure_half_way_leaves_no_account_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect: the account committed before the roles and firms did."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _source(service, session, firm)

    def _fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the copy failed after the account was written")

    monkeypatch.setattr(service, "_copy_memberships", _fail)

    with pytest.raises(RuntimeError):
        service.clone_user(source.id, _request(), ACTOR, None)
    session.rollback()

    assert _clone_row(session) is None
    # Nor the roles, nor the row saying a clone happened.
    assert (
        session.scalar(select(UserRole.id).where(UserRole.user_id != source.id)) is None
    )
    assert (
        session.scalar(select(AuditLog.id).where(AuditLog.action == "user.cloned"))
        is None
    )


def test_the_address_is_free_for_the_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """The consequence people actually met: a 409 on their own second attempt."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _source(service, session, firm)

    def _fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the copy failed after the account was written")

    monkeypatch.setattr(service, "_copy_memberships", _fail)
    with pytest.raises(RuntimeError):
        service.clone_user(source.id, _request(), ACTOR, None)
    session.rollback()
    monkeypatch.undo()

    clone = service.clone_user(source.id, _request(), ACTOR, None)

    assert clone.email == "new.hire@example.com"


def test_a_successful_clone_still_carries_the_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One commit, and everything in it."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _source(service, session, firm)
    commits: list[int] = []
    original = session.commit

    def _counted() -> None:
        commits.append(1)
        original()

    monkeypatch.setattr(session, "commit", _counted)

    clone = service.clone_user(source.id, _request(), ACTOR, None)

    assert len(commits) == 1
    roles = set(
        session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == clone.id, UserRole.is_deleted.is_(False))
        )
    )
    assert roles == {"CASHIER"}
    firms = set(
        session.scalars(select(UserFirm.firm_id).where(UserFirm.user_id == clone.id))
    )
    assert firms == {firm.id}


def test_the_public_writers_still_commit_on_their_own() -> None:
    """Splitting the internals must not leave a route writing nothing."""
    service, session = _service()
    role = session.scalar(select(Role).where(Role.code == "VIEWER"))
    assert role is not None

    user = service.create_user(
        UserCreate(email="solo@example.com", full_name="Solo", password=PASSWORD),
        actor_id=ACTOR,
    )
    service.set_user_roles(user.id, [role.id], ACTOR, None)
    session.rollback()

    assert service.list_user_role_ids(user.id) == [role.id]
    with pytest.raises(ConflictError):
        service.create_user(
            UserCreate(email="solo@example.com", full_name="Twin", password=PASSWORD),
            actor_id=ACTOR,
        )


def test_the_clone_of_a_deleted_address_is_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A staged create still answers 409 for a live address, as it always did."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _source(service, session, firm)
    service.create_user(
        UserCreate(
            email="new.hire@example.com", full_name="Already", password=PASSWORD
        ),
        actor_id=ACTOR,
    )

    with pytest.raises(ConflictError):
        service.clone_user(source.id, _request(), ACTOR, None)


def test_the_clone_id_is_returned_after_the_single_commit() -> None:
    """The route returns the row, so it must survive the commit that wrote it."""
    service, session = _service()
    firm = _firm(session, "T1")
    source = _source(service, session, firm)

    clone = service.clone_user(source.id, _request(), ACTOR, None)

    assert isinstance(clone.id, UUID)
    assert _clone_row(session) is not None
