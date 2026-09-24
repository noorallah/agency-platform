"""The identity and firm Low rows D-IDN-9 and D-IDN-10, each pinned.

D-IDN-9: a role code was unique across every firm for ever. D-IDN-10: the
identity and firms "small ones" -- codes no route enforced, a global-roles read
that answered for anybody, a directory listing switched-off accounts, an
exclusivity check that ignored suspended memberships, refresh reuse detection
that fired on sign-out, an access token that outlived sign-out, a firm PUT that
turned omissions into instructions, no firm restore, and job templates copied
into every firm store.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.firm_metadata import FirmMetadataReader
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
)
from app.core.security import JwtService
from app.core.security.authorization import _session_ended
from app.core.tenancy.lifecycle import _PLATFORM_TABLES
from app.firms.schemas import FirmCreate, FirmUpdate
from app.firms.services import FirmService
from app.identity.models import (
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserFirm,
)
from app.identity.schemas.api import RoleCreate, UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import (
    DESIGNATION_ONLY_PERMISSION_CODES,
    ROLE_PERMISSION_CODES,
    seed_system_rbac,
)

PASSWORD = "Str0ng-Passw0rd!"
_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _service(session: Session) -> IdentityService:
    """Return the identity service over ``session``."""
    return IdentityService(session, Settings())


def _user(service: IdentityService, session: Session, email: str) -> User:
    """Create a signed-in-able user with no forced password change."""
    user = service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD),
        actor_id=uuid4(),
    )
    user.force_password_change = False
    session.commit()
    return user


# --- D-IDN-9 -----------------------------------------------------------------


def test_a_deleted_role_gives_its_code_back() -> None:
    """Re-creating a role under a retired role's code is allowed."""
    session = _session()
    service = _service(session)
    firm = uuid4()
    role = service.create_role(
        RoleCreate(code="counter-staff", name="Counter"), _ACTOR, firm
    )
    service.delete_role(role.id, _ACTOR, firm)

    again = service.create_role(
        RoleCreate(code="counter-staff", name="Counter"), _ACTOR, firm
    )

    assert again.id != role.id


def test_a_role_code_is_unique_per_firm_not_across_firms() -> None:
    """Two firms may each have a `cashier-2`; one firm may not have two."""
    session = _session()
    service = _service(session)
    first, second = uuid4(), uuid4()
    service.create_role(RoleCreate(code="cashier-2", name="A"), _ACTOR, first)
    service.create_role(RoleCreate(code="cashier-2", name="B"), _ACTOR, second)

    with pytest.raises(ConflictError, match="This firm already has a role"):
        service.create_role(RoleCreate(code="cashier-2", name="C"), _ACTOR, first)


def test_the_role_keys_are_partial_over_live_rows() -> None:
    """The database agrees with the service, under SQLite as well."""
    session = _session()
    firm = uuid4()
    session.add_all(
        [
            Role(code="dup", name="Old", firm_id=firm, is_deleted=True),
            Role(code="dup", name="New", firm_id=firm),
            Role(code="dup", name="Other firm", firm_id=uuid4()),
        ]
    )
    session.commit()
    session.add(Role(code="dup", name="Clash", firm_id=firm))
    with pytest.raises(IntegrityError):
        session.commit()


# --- D-IDN-10: permission codes no route enforces -----------------------------


def test_no_role_holds_a_designation_only_code() -> None:
    """Seeded roles are given none of the eleven."""
    assert len(DESIGNATION_ONLY_PERMISSION_CODES) == 11
    for role, codes in ROLE_PERMISSION_CODES.items():
        assert not codes & DESIGNATION_ONLY_PERMISSION_CODES, role


def test_a_designation_only_code_cannot_be_granted_to_a_role() -> None:
    """`set_role_permissions` refuses one by name, platform-wide too."""
    session = _session()
    seed_system_rbac(session)
    session.commit()
    service = _service(session)
    role = service.create_role(RoleCreate(code="ops", name="Ops"), _ACTOR)
    code = session.scalar(select(Permission).where(Permission.code == "FIRM_CREATE"))
    assert code is not None

    with pytest.raises(BusinessRuleError, match="FIRM_CREATE"):
        service.set_role_permissions(role.id, [code.id], _ACTOR)


def test_seeding_retires_a_grant_written_before_the_rule() -> None:
    """A role already holding one loses it the next time the seed runs."""
    session = _session()
    seed_system_rbac(session)
    session.commit()
    role = Role(code="legacy", name="Legacy")
    session.add(role)
    session.flush()
    permission = session.scalar(
        select(Permission).where(Permission.code == "USER_LOCK")
    )
    assert permission is not None
    session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    session.commit()

    seed_system_rbac(session)
    session.commit()

    grant = session.scalar(
        select(RolePermission).where(RolePermission.role_id == role.id)
    )
    assert grant is not None and grant.is_deleted


def test_a_firm_is_not_shown_a_designation_only_code() -> None:
    """The catalogue a firm administrator picks from leaves them out."""
    session = _session()
    seed_system_rbac(session)
    session.commit()
    rows, _ = _service(session).list_permissions(1, 500, None, "code", False, uuid4())
    assert not {row.code for row in rows} & DESIGNATION_ONLY_PERMISSION_CODES


# --- D-IDN-10: reads held to the caller's firm --------------------------------


def test_global_roles_of_somebody_outside_the_firm_are_not_found() -> None:
    """A firm administrator asking about a stranger gets a 404."""
    session = _session()
    service = _service(session)
    stranger = _user(service, session, "stranger@example.com")

    with pytest.raises(ResourceNotFoundError):
        service.list_user_global_role_ids(stranger.id, firm_scope=uuid4())
    assert service.list_user_global_role_ids(stranger.id) == []


def test_the_firm_directory_leaves_out_a_switched_off_account() -> None:
    """`/firm-members` lists only people who can sign in."""
    session = _session()
    service = _service(session)
    firm = uuid4()
    on = _user(service, session, "on@example.com")
    off = _user(service, session, "off@example.com")
    off.is_active = False
    session.add_all(
        [
            UserFirm(user_id=on.id, firm_id=firm, created_by=_ACTOR),
            UserFirm(user_id=off.id, firm_id=firm, created_by=_ACTOR),
        ]
    )
    session.commit()

    members = FirmMetadataReader(session).active_members(firm)

    assert [member.user_id for member in members] == [on.id]
    assert FirmMetadataReader(session).active_member_count(firm, [off.id]) == 0


def test_a_suspended_membership_elsewhere_still_makes_the_user_shared() -> None:
    """Another firm's switched-off membership is still that firm's person."""
    session = _session()
    service = _service(session)
    person = _user(service, session, "shared@example.com")
    mine, theirs = uuid4(), uuid4()
    session.add_all(
        [
            UserFirm(user_id=person.id, firm_id=mine, created_by=_ACTOR),
            UserFirm(
                user_id=person.id,
                firm_id=theirs,
                is_active=False,
                created_by=_ACTOR,
            ),
        ]
    )
    session.commit()

    with pytest.raises(BusinessRuleError, match="another firm"):
        service._assert_exclusive_firm_user(person.id, mine)


# --- D-IDN-10: sessions ---------------------------------------------------------


def test_refreshing_after_sign_out_does_not_sign_out_everywhere() -> None:
    """A token revoked by sign-out has no successor, so it is not a theft."""
    session = _session()
    service = _service(session)
    user = _user(service, session, "leaver@example.com")
    here = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    there = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    service.logout(here.refresh_token)
    version = user.authorization_version

    with pytest.raises(AuthenticationError):
        service.refresh(here.refresh_token)

    session.expire_all()
    assert session.get(User, user.id).authorization_version == version
    assert service.refresh(there.refresh_token).access_token


def test_two_refreshes_racing_do_not_sign_out_everywhere() -> None:
    """The loser of a race inside the grace window is refused, nothing more."""
    session = _session()
    service = _service(session)
    user = _user(service, session, "racer@example.com")
    first = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    winner = service.refresh(first.refresh_token)

    with pytest.raises(AuthenticationError):
        service.refresh(first.refresh_token)

    assert service.refresh(winner.refresh_token).access_token


def test_signing_out_ends_the_access_token_too() -> None:
    """The access token names its session, which sign-out ends."""
    session = _session()
    settings = Settings()
    service = IdentityService(session, settings)
    user = _user(service, session, "out@example.com")
    tokens = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    claims = JwtService(settings.jwt).validate_token(
        tokens.access_token, expected_type=TokenType.ACCESS
    )
    sid = (claims.model_extra or {})["sid"]
    assert not _session_ended(session, sid)

    rotated = service.refresh(tokens.refresh_token)
    # Rotation carries the session on: the old access token still stands.
    assert not _session_ended(session, sid)

    service.logout(rotated.refresh_token)
    assert _session_ended(session, sid)
    # A token minted before `sid` existed is judged by its version alone.
    assert not _session_ended(session, None)


# --- D-IDN-10: the firm registry -------------------------------------------------


def _firm(service: FirmService, **overrides: object) -> FirmCreate:
    """Build a valid firm body."""
    payload: dict[str, object] = {
        "name": "Acme Distributors",
        "code": "ACME",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": date(2026, 4, 1),
        "gst_number": "29ABCDE1234F1Z5",
        "pan_number": "ABCDE1234F",
    }
    payload.update(overrides)
    return FirmCreate.model_validate(payload)


def _required(**overrides: object) -> FirmUpdate:
    """Build an edit carrying only the required fields."""
    payload: dict[str, object] = {
        "name": "Acme Renamed",
        "code": "ACME",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": date(2026, 4, 1),
    }
    payload.update(overrides)
    return FirmUpdate.model_validate(payload)


def test_a_firm_edit_leaves_alone_what_it_did_not_send() -> None:
    """An omitted `is_active`, GST or PAN is kept, not reset."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_firm(service, is_active=False), _ACTOR)
    assert firm.status == "INACTIVE"

    edited = service.update(firm.id, _required(), _ACTOR)

    assert edited.is_active is False
    assert edited.status == "INACTIVE"
    assert edited.gst_number == "29ABCDE1234F1Z5"
    assert edited.pan_number == "ABCDE1234F"
    assert edited.name == "Acme Renamed"
    # An explicit null still clears.
    cleared = service.update(firm.id, _required(gst_number=None), _ACTOR)
    assert cleared.gst_number is None


def test_firm_status_mirrors_the_active_flag() -> None:
    """A status alone sets the flag; a pair that disagrees is refused."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_firm(service), _ACTOR)

    switched = service.update(firm.id, _required(status="inactive"), _ACTOR)
    assert (switched.is_active, switched.status) == (False, "INACTIVE")

    with pytest.raises(BusinessRuleError, match="disagree"):
        service.update(firm.id, _required(status="ACTIVE", is_active=False), _ACTOR)
    with pytest.raises(ValueError):
        _required(status="SUSPENDED")


def test_a_deleted_firm_can_be_restored_unless_its_code_was_taken() -> None:
    """Restore brings the firm back, audited; a reused code refuses it."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_firm(service), _ACTOR)
    service.delete(firm.id, _ACTOR)

    restored = service.restore(firm.id, _ACTOR)
    assert restored.is_deleted is False
    assert session.scalar(select(AuditLog.id).where(AuditLog.action == "firm.restored"))

    service.delete(firm.id, _ACTOR)
    service.create(
        _firm(service, gst_number=None, pan_number=None, name="Usurper"), _ACTOR
    )
    with pytest.raises(ConflictError):
        service.restore(firm.id, _ACTOR)


def test_job_templates_are_platform_tables() -> None:
    """Pruned from every firm store, which kept a copy nothing read."""
    assert {"user_templates", "user_template_roles"} <= set(_PLATFORM_TABLES)


def test_a_refresh_token_row_carries_the_session_id() -> None:
    """The row's id is the `sid` the access token names."""
    session = _session()
    settings = Settings()
    service = IdentityService(session, settings)
    user = _user(service, session, "sid@example.com")
    tokens = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    claims = JwtService(settings.jwt).validate_token(
        tokens.access_token, expected_type=TokenType.ACCESS
    )
    row = session.get(RefreshToken, UUID((claims.model_extra or {})["sid"]))
    assert row is not None and row.user_id == user.id
    assert row.expires_at is not None
