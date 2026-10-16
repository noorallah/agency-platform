"""The support account is marked, and so is everything it does (29s, part c).

`users.is_support_account` replaces the department stand-in; every audit row
written while that account is signed in carries `by_support`, set by
`record_audit` from the request so no module has to remember; and the trail
filters on it, so the customer can list exactly what the vendor did.
"""

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.audit.api.router import AuditScope, list_audit_logs
from app.common.audit.models import AuditLog
from app.common.audit.services import record_audit
from app.core.config.settings import Settings
from app.core.context import (
    RequestContext,
    get_request_context,
    reset_request_context,
    set_request_context,
)
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope, TokenType
from app.core.exceptions import ConflictError
from app.core.security.authorization import Principal, get_current_principal
from app.core.security.jwt import JwtService, TokenClaims
from app.core.utils.dates import utc_now
from app.identity.models import PlatformAdmin, User
from app.identity.services import IdentityService
from app.identity.services.support_admin import ensure_support_admin
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Supp0rt-Passw0rd!"


@pytest.fixture
def session() -> Iterator[Session]:
    """Yield a seeded in-memory platform store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_system_rbac(db)
    db.commit()
    yield db
    db.close()


@pytest.fixture
def context() -> Iterator[RequestContext]:
    """Run the test inside a request context, as the middleware would."""
    current = RequestContext(
        request_id="r", correlation_id="c", client_ip=None, requested_at=utc_now()
    )
    token = set_request_context(current)
    yield current
    reset_request_context(token)


def _support(session: Session) -> User:
    """Create the support account the way the CLI does."""
    ensure_support_admin(
        session, email="support@vendor.example", full_name="Support", password=PASSWORD
    )
    user = session.scalar(select(User).where(User.email == "support@vendor.example"))
    assert user is not None
    return user


def _ordinary(session: Session) -> User:
    """Store an ordinary active user."""
    user = User(
        email="clerk@example.com",
        full_name="Clerk",
        password_hash="x",
        is_active=True,
        force_password_change=False,
    )
    session.add(user)
    session.commit()
    return user


def _request(settings: Settings) -> Request:
    """Build the minimum request `get_current_principal` reads."""
    request = Request({"type": "http", "method": "GET", "headers": [], "path": "/"})
    request.scope["app"] = type("App", (), {"state": type("State", (), {})()})()
    request.app.state.settings = settings
    return request


class _Credentials:
    """Stand in for the bearer credentials FastAPI would have parsed."""

    def __init__(self, token: str) -> None:
        """Hold the token."""
        self.credentials = token
        self.scheme = "Bearer"


def _authenticate(session: Session, user: User) -> None:
    """Authenticate a request as ``user`` through the real dependency."""
    settings = Settings()
    token = JwtService(settings.jwt).generate_access_token(
        user.id, claims={"authorization_version": user.authorization_version}
    )
    get_current_principal(_request(settings), _Credentials(token), session)  # type: ignore[arg-type]


def _write(session: Session, actor_id: UUID | None) -> AuditLog:
    """Record one audit event and return it."""
    entity_id = uuid4()
    record_audit(
        session,
        action="customer.updated",
        entity_type="customer",
        entity_id=entity_id,
        actor_id=actor_id,
    )
    session.commit()
    row = session.scalar(select(AuditLog).where(AuditLog.entity_id == entity_id))
    assert row is not None
    return row


def _platform_reader(user_id: UUID) -> AuditScope:
    """Return the platform-trail scope for an ALL_FIRMS administrator."""
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset({"AUDIT_LOG_VIEW"}),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            platform_admin=True,
            platform_admin_scope="ALL_FIRMS",
        ),
    )
    return AuditScope(principal, None)


# -- the marker ---------------------------------------------------------------
def test_the_command_marks_the_account_and_nothing_else(session: Session) -> None:
    """Only the account `create-support-admin` makes carries the column."""
    support = _support(session)
    clerk = _ordinary(session)

    assert support.is_support_account
    assert not clerk.is_support_account


def test_a_customers_all_firms_administrator_is_not_taken_over(
    session: Session,
) -> None:
    """Their address is refused, even in a department called Support."""
    head = User(
        email="head@example.com",
        full_name="Head",
        password_hash="x",
        is_active=True,
        department="Support",
    )
    session.add(head)
    session.flush()
    session.add(
        PlatformAdmin(user_id=head.id, scope=PlatformAdminScope.ALL_FIRMS.value)
    )
    session.commit()

    with pytest.raises(ConflictError, match="not the support account"):
        ensure_support_admin(
            session, email="head@example.com", full_name="Head", password=PASSWORD
        )
    assert not head.is_support_account


# -- the audit flag -----------------------------------------------------------
def test_a_request_signed_in_as_support_marks_what_it_writes(
    session: Session, context: RequestContext
) -> None:
    """Whatever store the row lands in, the request says who acted."""
    support = _support(session)
    _authenticate(session, support)

    assert _write(session, support.id).by_support


def test_an_ordinary_request_marks_nothing(
    session: Session, context: RequestContext
) -> None:
    """Somebody else signed in writes ordinary rows."""
    clerk = _ordinary(session)
    _authenticate(session, clerk)

    assert not _write(session, clerk.id).by_support


def test_a_write_outside_any_request_is_not_support(session: Session) -> None:
    """The CLI and the scripts have nobody signed in."""
    assert get_request_context() is None
    assert not _write(session, None).by_support


def test_signing_in_as_support_is_marked(
    session: Session, context: RequestContext
) -> None:
    """The sign-in comes before any token, so the account itself says."""
    support = _support(session)
    IdentityService(session, Settings()).login(
        support.email, PASSWORD, client_ip=None, user_agent=None
    )

    row = session.scalar(
        select(AuditLog).where(
            AuditLog.action == "identity.login", AuditLog.entity_id == support.id
        )
    )
    assert row is not None and row.by_support


# -- the filter ---------------------------------------------------------------
def test_the_trail_filters_on_support_access(
    session: Session, context: RequestContext
) -> None:
    """True lists what support did, false the rest, absent both."""
    clerk = _ordinary(session)
    ordinary = _write(session, clerk.id)
    support = _support(session)
    context.actor.by_support = True
    by_support = _write(session, support.id)
    scope = _platform_reader(support.id)

    def ids(**filters: object) -> set[UUID]:
        page = list_audit_logs(
            scope,
            entity_type="customer",
            db=session,
            platform_db=session,
            **filters,  # type: ignore[arg-type]
        )
        return {row.id for row in page.data}

    assert ids(by_support=True) == {by_support.id}
    assert ids(by_support=False) == {ordinary.id}
    assert ids() == {ordinary.id, by_support.id}
    page = list_audit_logs(
        scope, by_support=True, entity_type="customer", db=session, platform_db=session
    )
    assert [row.by_support for row in page.data] == [True]


# -- the migration ------------------------------------------------------------
def _migration() -> object:
    """Load the migration module by path."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261017_0396_support_account_marker.py"
    )
    spec = importlib.util.spec_from_file_location("support_marker_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_marks_the_account_the_stand_in_named(
    session: Session,
) -> None:
    """Department Support + live ALL_FIRMS only, and a replay changes nothing."""
    support = _support(session)
    lookalike = User(
        email="help@example.com",
        full_name="Help",
        password_hash="x",
        is_active=True,
        department="Support",
    )
    session.add(lookalike)
    _write(session, None)
    # As a store looked before the migration: neither column.
    session.execute(text("ALTER TABLE users DROP COLUMN is_support_account"))
    session.execute(text("ALTER TABLE audit_logs DROP COLUMN by_support"))
    session.commit()

    migration = _migration()
    connection = session.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()  # type: ignore[attr-defined]
        migration.upgrade()  # type: ignore[attr-defined]
    session.commit()

    marked = dict(
        session.execute(text("SELECT email, is_support_account FROM users")).all()
    )
    assert bool(marked[support.email]) is True
    assert bool(marked[lookalike.email]) is False
    flags = session.scalars(text("SELECT by_support FROM audit_logs")).all()
    assert flags and not any(flags)
