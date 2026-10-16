"""The customer's administrator switches the support account off and on (29s b).

The support account holds `ALL_FIRMS`, so the rank rule alone would let only
another `ALL_FIRMS` administrator touch it -- and the installation's owner,
who may be designated `PLATFORM`, must always be able to shut the vendor out.
The exemption is narrow: any platform administrator but the account itself,
`is_active` and nothing else, with a reason the trail keeps under its own
event name. Switching it off ends its sessions.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.identity.models import PlatformAdmin, RefreshToken, User
from app.identity.schemas.api import UserCreate, UserUpdate
from app.identity.services import IdentityService
from app.identity.services.support_admin import ensure_support_admin
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Old-Passw0rd!!"
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


def _account(
    service: IdentityService,
    session: Session,
    email: str,
    scope: PlatformAdminScope | None = None,
    department: str | None = None,
) -> User:
    """Create an account, designated at the given reach or not at all."""
    user = service.create_user(
        UserCreate(
            email=email, full_name="Person", password=PASSWORD, department=department
        ),
        actor_id=ACTOR,
    )
    if scope is not None:
        session.add(
            PlatformAdmin(
                user_id=user.id, scope=scope.value, created_by=ACTOR, updated_by=ACTOR
            )
        )
        session.commit()
    return user


def _support(session: Session) -> User:
    """Create the support account the way the CLI does."""
    ensure_support_admin(
        session, email="support@vendor.example", full_name="Support", password=PASSWORD
    )
    user = session.scalar(select(User).where(User.email == "support@vendor.example"))
    assert user is not None
    return user


def _events(session: Session, user: User) -> list[AuditLog]:
    """Return the support switch events written for this account."""
    return list(
        session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_id == user.id,
                AuditLog.action.like("identity.support_admin_%abled"),
            )
            .order_by(AuditLog.created_at)
        )
    )


def test_a_platform_administrator_switches_the_support_account_off() -> None:
    """The customer's PLATFORM administrator can; the trail says who and why."""
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    support = _support(session)
    session.add(
        RefreshToken(
            user_id=support.id,
            token_hash="a" * 64,
            expires_at=utc_now() + timedelta(days=1),
        )
    )
    session.commit()
    version = support.authorization_version

    service.update_user(
        support.id, UserUpdate(is_active=False, reason="Visit finished"), owner.id
    )

    session.expire_all()
    row = session.get(User, support.id)
    assert row is not None
    assert not row.is_active
    assert row.authorization_version > version
    token = session.scalar(select(RefreshToken).where(RefreshToken.user_id == row.id))
    assert token is not None and token.revoked_at is not None
    [event] = _events(session, row)
    assert event.action == "identity.support_admin_disabled"
    assert event.actor_id == owner.id
    assert event.after_data == {"is_active": False, "reason": "Visit finished"}
    # The switch is its own event, not a second `user.updated` beside it.
    assert (
        session.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == row.id, AuditLog.action == "user.updated"
            )
        )
        is None
    )


def test_switching_it_back_on_is_its_own_event() -> None:
    """On again, with a reason, as `identity.support_admin_enabled`."""
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    support = _support(session)
    service.update_user(support.id, UserUpdate(is_active=False, reason="Off"), owner.id)

    service.update_user(
        support.id, UserUpdate(is_active=True, reason="Ticket 42"), owner.id
    )

    session.expire_all()
    row = session.get(User, support.id)
    assert row is not None and row.is_active
    events = _events(session, row)
    assert [event.action for event in events] == [
        "identity.support_admin_disabled",
        "identity.support_admin_enabled",
    ]
    assert events[-1].after_data == {"is_active": True, "reason": "Ticket 42"}


@pytest.mark.parametrize("reason", [None, "", "   "], ids=["absent", "empty", "blank"])
def test_a_reason_is_required(reason: str | None) -> None:
    """No reason, no switch."""
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    support = _support(session)

    with pytest.raises(ValidationError, match="Say why"):
        service.update_user(
            support.id, UserUpdate(is_active=False, reason=reason), owner.id
        )

    session.rollback()
    row = session.get(User, support.id)
    assert row is not None and row.is_active


def test_a_reason_longer_than_500_characters_is_refused() -> None:
    """The schema bounds it."""
    with pytest.raises(SchemaValidationError):
        UserUpdate(is_active=False, reason="x" * 501)
    assert UserUpdate(is_active=False, reason="x" * 500).reason == "x" * 500


def test_the_support_account_cannot_switch_itself_off() -> None:
    """It is the customer's switch, not the vendor's."""
    service, session = _service()
    support = _support(session)

    with pytest.raises(BusinessRuleError, match="cannot switch itself"):
        service.update_user(
            support.id, UserUpdate(is_active=False, reason="Leaving"), support.id
        )


def test_an_undesignated_account_cannot_switch_it() -> None:
    """The exemption is for platform administrators only."""
    service, session = _service()
    clerk = _account(service, session, "clerk@example.com")
    support = _support(session)

    with pytest.raises(AuthorizationError, match="platform administrator"):
        service.update_user(
            support.id, UserUpdate(is_active=False, reason="Why not"), clerk.id
        )


def test_the_exemption_covers_the_switch_and_nothing_else() -> None:
    """A PLATFORM administrator still cannot rename it, switching or not."""
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    support = _support(session)

    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.update_user(
            support.id,
            UserUpdate(is_active=False, reason="Off", full_name="Renamed"),
            owner.id,
        )
    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.update_user(support.id, UserUpdate(full_name="Renamed"), owner.id)


def test_another_all_firms_administrator_is_not_the_support_account() -> None:
    """An ALL_FIRMS admin in a department called Support is still ranked."""
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    other = _account(
        service,
        session,
        "all@example.com",
        PlatformAdminScope.ALL_FIRMS,
        department="Sales",
    )
    lookalike = _account(service, session, "help@example.com", department="Support")
    support = _support(session)

    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.update_user(
            other.id, UserUpdate(is_active=False, reason="Off"), owner.id
        )
    assert service.support_account_ids([other.id, lookalike.id, support.id]) == {
        support.id
    }


def test_an_all_firms_administrator_in_support_is_not_the_support_account() -> None:
    """The department was the stand-in; the column is the marker (part c).

    A customer's own top administrator working in a department called Support
    looked exactly like the support account to the stand-in, so any PLATFORM
    operator could have switched them off.
    """
    service, session = _service()
    owner = _account(service, session, "owner@example.com", PlatformAdminScope.PLATFORM)
    namesake = _account(
        service,
        session,
        "head@example.com",
        PlatformAdminScope.ALL_FIRMS,
        department="Support",
    )
    support = _support(session)

    assert support.is_support_account
    assert not namesake.is_support_account
    assert service.support_account_ids([namesake.id, support.id]) == {support.id}
    with pytest.raises(AuthorizationError, match="reach is wider"):
        service.update_user(
            namesake.id, UserUpdate(is_active=False, reason="Off"), owner.id
        )


def test_a_marked_account_without_its_designation_is_not_the_support_account() -> None:
    """The marker names the account; the ALL_FIRMS row is still its reach."""
    service, session = _service()
    support = _support(session)
    designation = session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.user_id == support.id)
    )
    assert designation is not None
    designation.is_deleted = True
    session.commit()

    assert service.support_account_ids([support.id]) == set()


def test_an_all_firms_administrator_switches_it_too() -> None:
    """A peer may as well, and still has to say why."""
    service, session = _service()
    peer = _account(service, session, "all@example.com", PlatformAdminScope.ALL_FIRMS)
    support = _support(session)

    with pytest.raises(ValidationError):
        service.update_user(support.id, UserUpdate(is_active=False), peer.id)
    service.update_user(support.id, UserUpdate(is_active=False, reason="Done"), peer.id)

    [event] = _events(session, support)
    assert event.actor_id == peer.id
