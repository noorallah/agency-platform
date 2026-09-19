"""An administrator acts on another account only when their reach is as wide.

D-IDN-2. `POST /users/{id}/password` is `require_platform_admin()` of either
reach and `reset_password` never looked at the target's designation, so a
`PLATFORM` operator could set an `ALL_FIRMS` administrator's password with no
forced change and sign in as them -- every firm's books. `PATCH /users/{id}`
likewise let them rename, switch off or expire one. Only deletion checked the
designation.

The rule now: reach is ranked none < `PLATFORM` < `ALL_FIRMS`, and an
administrator may reset or edit another account only when their own rank is
at least the target's. Nobody switches off or expires their own account
through these routes, and the bootstrap administrator's password is its
holder's alone.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope
from app.core.exceptions import AuthorizationError, BusinessRuleError
from app.core.security.password import PasswordSecurity
from app.core.utils.dates import utc_now
from app.identity.models import PlatformAdmin, User
from app.identity.schemas.api import UserCreate, UserUpdate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

OLD = "Old-Passw0rd!!"
NEW = "New-Passw0rd!!"
ACTOR = uuid4()
#: The id migration `20260728_0001` gives `platform-admin@agency.local`.
BOOTSTRAP_ADMIN_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


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


def _account(
    service: IdentityService,
    session: Session,
    email: str,
    scope: PlatformAdminScope | None = None,
) -> User:
    """Create an account, designated at the given reach or not at all."""
    user = service.create_user(
        UserCreate(email=email, full_name="Person", password=OLD), actor_id=ACTOR
    )
    if scope is not None:
        session.add(
            PlatformAdmin(
                user_id=user.id, scope=scope.value, created_by=ACTOR, updated_by=ACTOR
            )
        )
        session.commit()
    return user


def _still_on_old_password(session: Session, user: User) -> bool:
    """Return whether the account's password is untouched."""
    session.expire_all()
    row = session.get(User, user.id)
    assert row is not None
    return PasswordSecurity().verify_password(OLD, row.password_hash)


# --------------------------------------------------------------------------
# The takeover
# --------------------------------------------------------------------------


def test_a_platform_operator_cannot_reset_an_all_firms_administrators_password() -> (
    None
):
    """The defect: the narrow tier signing in as the wide one."""
    service, session = _service()
    operator = _account(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    wider = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.reset_password(wider.id, NEW, operator.id, force_change=False)

    assert _still_on_old_password(session, wider)


@pytest.mark.parametrize(
    "change",
    [
        UserUpdate(full_name="Renamed"),
        UserUpdate(is_active=False),
        UserUpdate(expires_at=utc_now() + timedelta(minutes=1)),
    ],
    ids=["rename", "switch-off", "expire"],
)
def test_a_platform_operator_cannot_edit_an_all_firms_administrator(
    change: UserUpdate,
) -> None:
    """Rename, switch off and expire go the same way as the password."""
    service, session = _service()
    operator = _account(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    wider = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.update_user(wider.id, change, operator.id, None)

    session.expire_all()
    row = session.get(User, wider.id)
    assert row is not None
    assert (row.full_name, row.is_active, row.expires_at) == ("Person", True, None)


def test_an_undesignated_caller_cannot_touch_a_platform_operator() -> None:
    """The service holds even for a caller who reached it without a designation."""
    service, session = _service()
    clerk = _account(service, session, "clerk@example.com")
    operator = _account(service, session, "op@example.com", PlatformAdminScope.PLATFORM)

    with pytest.raises(AuthorizationError):
        service.update_user(operator.id, UserUpdate(is_active=False), clerk.id, None)


# --------------------------------------------------------------------------
# What each reach may still do
# --------------------------------------------------------------------------


def test_the_wider_reach_administers_the_narrower() -> None:
    """An `ALL_FIRMS` administrator still resets an operator's password."""
    service, session = _service()
    wider = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)
    operator = _account(service, session, "op@example.com", PlatformAdminScope.PLATFORM)

    service.reset_password(operator.id, NEW, wider.id)

    assert not _still_on_old_password(session, operator)


def test_peers_administer_peers() -> None:
    """Same reach, same standing: nobody is left without somebody to help."""
    service, session = _service()
    one = _account(service, session, "one@example.com", PlatformAdminScope.PLATFORM)
    two = _account(service, session, "two@example.com", PlatformAdminScope.PLATFORM)

    service.update_user(two.id, UserUpdate(full_name="Renamed"), one.id, None)
    service.reset_password(two.id, NEW, one.id)

    assert session.get(User, two.id).full_name == "Renamed"  # type: ignore[union-attr]


def test_anybody_with_the_route_administers_an_ordinary_account() -> None:
    """The ordinary job of the operator tier is unchanged."""
    service, session = _service()
    operator = _account(service, session, "op@example.com", PlatformAdminScope.PLATFORM)
    person = _account(service, session, "person@example.com")

    service.reset_password(person.id, NEW, operator.id)
    service.update_user(person.id, UserUpdate(is_active=False), operator.id, None)

    assert not _still_on_old_password(session, person)


# --------------------------------------------------------------------------
# Your own account, and the bootstrap one
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        UserUpdate(is_active=False),
        UserUpdate(expires_at=utc_now() + timedelta(days=1)),
    ],
    ids=["switch-off", "expire"],
)
def test_nobody_switches_off_or_expires_themselves(change: UserUpdate) -> None:
    """Locking yourself out is somebody else's decision to make, and to see."""
    service, session = _service()
    admin = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(BusinessRuleError, match="your own account"):
        service.update_user(admin.id, change, admin.id, None)


def test_a_person_may_still_correct_their_own_name() -> None:
    """Only the two lockout fields are refused on your own row."""
    service, session = _service()
    admin = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)

    service.update_user(admin.id, UserUpdate(full_name="Corrected"), admin.id, None)

    assert session.get(User, admin.id).full_name == "Corrected"  # type: ignore[union-attr]


def test_the_bootstrap_administrators_password_is_its_holders_alone() -> None:
    """Not even a peer of the same reach may set it."""
    service, session = _service()
    bootstrap = User(
        id=BOOTSTRAP_ADMIN_USER_ID,
        email="platform-admin@agency.local",
        full_name="Platform Administrator",
        password_hash=PasswordSecurity().hash_password(OLD),
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(bootstrap)
    session.flush()
    session.add(
        PlatformAdmin(
            user_id=bootstrap.id,
            scope=PlatformAdminScope.ALL_FIRMS.value,
            created_by=ACTOR,
            updated_by=ACTOR,
        )
    )
    session.commit()
    peer = _account(service, session, "peer@example.com", PlatformAdminScope.ALL_FIRMS)

    with pytest.raises(BusinessRuleError, match="bootstrap"):
        service.reset_password(bootstrap.id, NEW, peer.id)

    assert _still_on_old_password(session, bootstrap)
