"""Exercise the token-to-Principal chain that every other test bypasses.

The unit suite calls route functions directly with a hand-built ``Principal``,
which is fast and keeps the business tests about business rules -- but it means
``get_current_principal`` is never called, and that function is where a request
is actually authenticated. Before this file it had no test at all.

The gap mattered most for ``authorization_version``. Other tests confirm the
counter goes up when a user's access changes, and that the token carries it.
Nothing confirmed the half that gives it its purpose: that a token minted
*before* the change stops working. That is what revokes a session when somebody
is removed from a role, and it was the whole mechanism behind "a permission
change takes effect".
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_any_permission,
    require_permission,
    require_platform_admin,
    require_role,
)
from app.core.security.jwt import JwtService
from app.core.utils.dates import utc_now
from app.identity.models import User


def _session_factory() -> sessionmaker[Session]:
    """Create one in-memory database for the chain under test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _user(session: Session, **overrides: object) -> User:
    """Store one active user."""
    row = User(
        email=f"{uuid4().hex[:8]}@agency.local",
        full_name="Test User",
        password_hash="x",
        is_active=True,
        authorization_version=1,
        force_password_change=False,
    )
    for field, value in overrides.items():
        setattr(row, field, value)
    session.add(row)
    session.commit()
    return row


class _Credentials:
    """Stand in for the bearer credentials FastAPI would have parsed."""

    def __init__(self, token: str) -> None:
        self.credentials = token
        self.scheme = "Bearer"


def _request(settings: Settings, firm_header: str | None = None) -> Request:
    """Build the minimum request the dependency reads."""
    headers: list[tuple[bytes, bytes]] = []
    if firm_header is not None:
        headers.append((b"x-firm-id", firm_header.encode()))
    request = Request(
        {"type": "http", "method": "GET", "headers": headers, "path": "/"}
    )
    request.scope["app"] = type("App", (), {"state": type("State", (), {})()})()
    request.app.state.settings = settings
    return request


def _token(settings: Settings, user: User, **claims: object) -> str:
    """Mint an access token the way the identity service does."""
    payload: dict[str, object] = {
        "roles": ["FIRM_ADMIN"],
        "permissions": ["CUSTOMER_VIEW"],
        "firm_permissions": {},
        "authorization_version": user.authorization_version,
        "password_change_required": user.force_password_change,
    }
    payload.update(claims)
    return JwtService(settings.jwt).generate_access_token(user.id, claims=payload)


@pytest.fixture
def settings() -> Settings:
    """Return application settings for token signing."""
    return Settings()


def test_a_valid_token_produces_the_principal_the_routers_expect(
    settings: Settings,
) -> None:
    """The happy path, which nothing else in the suite covers."""
    session = _session_factory()()
    user = _user(session)

    principal = get_current_principal(
        _request(settings), _Credentials(_token(settings, user)), session
    )

    assert principal.subject == user.id
    assert "CUSTOMER_VIEW" in principal.permissions
    assert "FIRM_ADMIN" in principal.roles
    assert principal.firm_id is None


def test_a_token_minted_before_a_permission_change_stops_working(
    settings: Settings,
) -> None:
    """Revoking a live session is exactly what this does.

    Changing a user's roles bumps ``authorization_version``. The token carries
    the value it was minted with, so an older token no longer matches and the
    request is refused -- which is why a permission change takes effect without
    waiting for the token to expire. Other tests check the counter increments;
    this checks the increment actually costs the old token its access.
    """
    session = _session_factory()()
    user = _user(session)
    stale = _token(settings, user)

    # An administrator changes what this user may do.
    user.authorization_version += 1
    session.commit()

    with pytest.raises(AuthenticationError):
        get_current_principal(_request(settings), _Credentials(stale), session)

    # A token minted after the change works again.
    fresh = _token(settings, user)
    assert (
        get_current_principal(_request(settings), _Credentials(fresh), session).subject
        == user.id
    )


def test_a_deactivated_user_cannot_use_a_token_they_already_hold(
    settings: Settings,
) -> None:
    """Deactivation has to bite immediately, not at token expiry."""
    session = _session_factory()()
    user = _user(session)
    token = _token(settings, user)

    user.is_active = False
    session.commit()

    with pytest.raises(AuthenticationError):
        get_current_principal(_request(settings), _Credentials(token), session)


def test_a_soft_deleted_user_cannot_authenticate(settings: Settings) -> None:
    """Soft delete removes access, not just visibility."""
    session = _session_factory()()
    user = _user(session)
    token = _token(settings, user)

    user.is_deleted = True
    session.commit()

    with pytest.raises(AuthenticationError):
        get_current_principal(_request(settings), _Credentials(token), session)


def test_an_expired_account_cannot_authenticate(settings: Settings) -> None:
    """``expires_at`` is a hard stop, for a contractor account that has run out."""
    session = _session_factory()()
    user = _user(session, expires_at=utc_now() - timedelta(minutes=1))

    with pytest.raises(AuthenticationError):
        get_current_principal(
            _request(settings), _Credentials(_token(settings, user)), session
        )


def test_an_account_expiring_later_still_authenticates(settings: Settings) -> None:
    """The boundary the other way, so the check is not simply always-on."""
    session = _session_factory()()
    user = _user(session, expires_at=utc_now() + timedelta(days=1))

    principal = get_current_principal(
        _request(settings), _Credentials(_token(settings, user)), session
    )

    assert principal.subject == user.id


def test_a_missing_bearer_token_is_refused(settings: Settings) -> None:
    """No credentials is an authentication failure, not a crash."""
    session = _session_factory()()

    with pytest.raises(AuthenticationError):
        get_current_principal(_request(settings), None, session)


def test_a_refresh_token_cannot_be_used_as_an_access_token(
    settings: Settings,
) -> None:
    """The two token types are not interchangeable."""
    session = _session_factory()()
    user = _user(session)
    refresh = JwtService(settings.jwt).generate_refresh_token(user.id)

    with pytest.raises(Exception) as error:
        get_current_principal(_request(settings), _Credentials(refresh), session)
    assert error.type is not AssertionError


def test_the_firm_header_reaches_the_principal(settings: Settings) -> None:
    """``X-Firm-ID`` is how every firm-owned request says which firm it means."""
    session = _session_factory()()
    user = _user(session)
    firm_id = uuid4()

    principal = get_current_principal(
        _request(settings, firm_header=str(firm_id)),
        _Credentials(_token(settings, user)),
        session,
    )

    assert principal.firm_id == firm_id


def test_a_malformed_firm_header_is_refused_rather_than_ignored(
    settings: Settings,
) -> None:
    """Ignoring it would silently act in the wrong firm, or in none."""
    session = _session_factory()()
    user = _user(session)

    with pytest.raises(AuthorizationError):
        get_current_principal(
            _request(settings, firm_header="not-a-uuid"),
            _Credentials(_token(settings, user)),
            session,
        )


def test_firm_permissions_from_the_token_are_parsed_per_firm(
    settings: Settings,
) -> None:
    """A user may hold different permissions in different firms."""
    session = _session_factory()()
    user = _user(session)
    firm_a, firm_b = uuid4(), uuid4()
    token = _token(
        settings,
        user,
        firm_permissions={
            str(firm_a): ["CUSTOMER_UPDATE"],
            str(firm_b): ["CUSTOMER_VIEW"],
            "not-a-uuid": ["IGNORED"],
        },
    )

    principal = get_current_principal(_request(settings), _Credentials(token), session)

    assert principal.firm_permissions[firm_a] == frozenset({"CUSTOMER_UPDATE"})
    assert principal.firm_permissions[firm_b] == frozenset({"CUSTOMER_VIEW"})
    assert len(principal.firm_permissions) == 2, "a bad firm id must be dropped"


def test_a_password_change_token_cannot_be_used_for_ordinary_work(
    settings: Settings,
) -> None:
    """A user forced to change their password gets a token good for that alone.

    Every guard checks it -- ``require_permission``, ``require_role``,
    ``require_platform_admin`` and ``require_any_permission`` -- and
    ``firm_permission_scope`` inherits the check through ``require_permission``.
    """
    session = _session_factory()()
    user = _user(session, force_password_change=True)
    principal = get_current_principal(
        _request(settings), _Credentials(_token(settings, user)), session
    )
    assert "CUSTOMER_VIEW" in principal.permissions

    guard = require_permission("CUSTOMER_VIEW")
    with pytest.raises(AuthorizationError):
        guard(principal)


def test_a_subject_that_is_not_a_user_id_is_refused(settings: Settings) -> None:
    """Tokens carry a UUID subject; anything else is not a user."""
    session = _session_factory()()
    token = JwtService(settings.jwt).generate_access_token(
        UUID(int=0), claims={"authorization_version": 0}
    )
    # A well-formed token for a user that does not exist.
    with pytest.raises(AuthenticationError):
        get_current_principal(_request(settings), _Credentials(token), session)


def _principal_for(settings: Settings, session: Session, **claims: object) -> Principal:
    """Return a Principal built through the real chain, not by hand."""
    user = _user(session, force_password_change=bool(claims.pop("force", False)))
    return get_current_principal(
        _request(settings), _Credentials(_token(settings, user, **claims)), session
    )


def test_require_role_accepts_one_of_the_declared_roles(settings: Settings) -> None:
    """Any one of the listed roles is enough."""
    session = _session_factory()()
    principal = _principal_for(settings, session, roles=["ACCOUNTANT"])

    assert require_role("SALES_MANAGER", "ACCOUNTANT")(principal) is principal
    with pytest.raises(AuthorizationError):
        require_role("PLATFORM_ADMIN")(principal)


def test_require_any_permission_needs_only_one(settings: Settings) -> None:
    """Unlike require_permission, which needs all of them."""
    session = _session_factory()()
    principal = _principal_for(settings, session, permissions=["CUSTOMER_VIEW"])

    assert (
        require_any_permission("CUSTOMER_VIEW", "VENDOR_VIEW")(principal) is principal
    )
    with pytest.raises(AuthorizationError):
        require_any_permission("VENDOR_VIEW")(principal)


def test_require_permission_needs_all_of_them(settings: Settings) -> None:
    """The distinction from require_any_permission, pinned."""
    session = _session_factory()()
    principal = _principal_for(
        settings, session, permissions=["CUSTOMER_VIEW", "CUSTOMER_UPDATE"]
    )

    assert require_permission("CUSTOMER_VIEW", "CUSTOMER_UPDATE")(principal)
    with pytest.raises(AuthorizationError):
        require_permission("CUSTOMER_VIEW", "CUSTOMER_DELETE")(principal)


def test_platform_admin_is_a_role_claim_not_a_permission(settings: Settings) -> None:
    """It is deliberately not configurable, so it cannot be granted by a role edit."""
    session = _session_factory()()
    admin = _principal_for(settings, session, roles=["platform_admin"])
    ordinary = _principal_for(settings, session, roles=["FIRM_ADMIN"])

    assert require_platform_admin()(admin) is admin
    with pytest.raises(AuthorizationError):
        require_platform_admin()(ordinary)


def test_every_guard_refuses_a_password_change_token(settings: Settings) -> None:
    """One table of guards, so a new one added without the check is noticed."""
    session = _session_factory()()
    principal = _principal_for(
        settings,
        session,
        force=True,
        roles=["platform_admin", "ACCOUNTANT"],
        permissions=["CUSTOMER_VIEW"],
    )

    guards = (
        require_permission("CUSTOMER_VIEW"),
        require_any_permission("CUSTOMER_VIEW"),
        require_role("ACCOUNTANT"),
        require_platform_admin(),
    )
    for guard in guards:
        with pytest.raises(AuthorizationError):
            guard(principal)


def test_a_guard_declared_with_no_codes_is_a_programming_error(
    settings: Settings,
) -> None:
    """Empty means "everyone", which is never what the author meant."""
    for factory in (require_permission, require_any_permission, require_role):
        with pytest.raises(ValueError):
            factory()
