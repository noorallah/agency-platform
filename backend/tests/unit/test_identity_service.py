"""Focused authentication-service policy tests."""

from contextlib import suppress
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ResourceNotFoundError,
)
from app.core.security import PasswordSecurity
from app.core.security.authorization import Principal, require_platform_admin
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import (
    LoginHistory,
    Permission,
    PlatformAdmin,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserFirm,
    UserPreferences,
    UserRole,
)
from app.identity.schemas import (
    PermissionUpdate,
    UserFirmAssignment,
    UserPreferencesUpdate,
    UserUpdate,
)
from app.identity.services import IdentityService
from app.identity.system_seed import (
    HIDDEN_SYSTEM_ROLE_CODES,
    ROLE_PERMISSION_CODES,
    SYSTEM_PERMISSION_CODES,
    SYSTEM_ROLE_CODES,
    seed_system_rbac,
)


def _session() -> Session:
    """Create a portable in-memory unit-test session for service policies."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _settings() -> Settings:
    """Build explicit non-development settings without environment dependence."""
    return Settings(
        environment=Environment.TESTING,
        bootstrap_admin_password="Test-Bootstrap-Only1!",
    )


def test_bootstrap_login_rotates_sentinel_password_and_forces_change() -> None:
    """Ensure a bootstrap secret alone can initialize the sentinel password."""
    session = _session()
    user = User(
        email="platform-admin@agency.local",
        full_name="Platform Administrator",
        password_hash="*",
        force_password_change=True,
    )
    session.add(user)
    session.add(PlatformAdmin(user=user))
    session.commit()

    response = IdentityService(session, _settings()).login(
        user.email,
        "Test-Bootstrap-Only1!",
        client_ip=None,
        user_agent=None,
    )

    assert response.must_change_password is True
    assert user.password_hash != "*"
    assert response.access_token
    assert session.query(RefreshToken).count() == 1


def test_platform_admin_access_tokens_include_all_active_permissions() -> None:
    """Ensure platform-admin designation is sufficient for permission endpoints."""
    session = _session()
    seed_system_rbac(session)
    password = "Secure-Passphrase1!"
    user = User(
        email="designated-admin@example.com",
        full_name="Designated Administrator",
        password_hash=PasswordSecurity().hash_password(password),
    )
    custom_active = Permission(code="CUSTOM_ACTIVE", name="Custom Active")
    custom_inactive = Permission(
        code="CUSTOM_INACTIVE", name="Custom Inactive", is_active=False
    )
    custom_deleted = Permission(
        code="CUSTOM_DELETED", name="Custom Deleted", is_deleted=True
    )
    session.add_all(
        [
            user,
            PlatformAdmin(user=user),
            custom_active,
            custom_inactive,
            custom_deleted,
        ]
    )
    session.commit()

    service = IdentityService(session, _settings())
    response = service.login(user.email, password, client_ip=None, user_agent=None)
    claims = service._jwt.validate_token(response.access_token)
    extra_claims = claims.model_extra or {}

    assert "platform_admin" in extra_claims["roles"]
    assert set(extra_claims["permissions"]) == {
        permission.code
        for permission in session.scalars(
            select(Permission).where(
                Permission.is_active.is_(True),
                Permission.is_deleted.is_(False),
            )
        )
    }


def test_non_admin_access_tokens_keep_role_granted_permissions() -> None:
    """Ensure ordinary users do not receive permissions outside active roles."""
    session = _session()
    password = "Secure-Passphrase1!"
    user = User(
        email="role-user@example.com",
        full_name="Role User",
        password_hash=PasswordSecurity().hash_password(password),
    )
    role = Role(code="limited", name="Limited")
    permission = Permission(code="USER_VIEW", name="View users")
    unassigned = Permission(code="FIRM_VIEW", name="View firms")
    session.add_all([user, role, permission, unassigned])
    session.flush()
    session.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id),
            RolePermission(role_id=role.id, permission_id=permission.id),
        ]
    )
    session.commit()

    response = IdentityService(session, _settings()).login(
        user.email, password, client_ip=None, user_agent=None
    )
    claims = IdentityService(session, _settings())._jwt.validate_token(
        response.access_token
    )
    extra_claims = claims.model_extra or {}

    assert extra_claims["permissions"] == ["USER_VIEW"]
    assert "platform_admin" not in extra_claims["roles"]

    role.is_active = False
    session.commit()
    inactive_role_response = IdentityService(session, _settings()).login(
        user.email, password, client_ip=None, user_agent=None
    )
    inactive_role_claims = IdentityService(session, _settings())._jwt.validate_token(
        inactive_role_response.access_token
    )
    assert (inactive_role_claims.model_extra or {})["permissions"] == []


def test_system_rbac_seed_is_idempotent_and_creates_default_mappings() -> None:
    """Ensure installation seeding preserves one complete system RBAC model."""
    session = _session()

    seed_system_rbac(session)
    session.commit()
    seed_system_rbac(session)
    session.commit()

    roles = session.scalars(select(Role)).all()
    permissions = session.scalars(select(Permission)).all()
    platform_admin = next(role for role in roles if role.code == "PLATFORM_ADMIN")
    platform_assignments = session.scalars(
        select(RolePermission).where(RolePermission.role_id == platform_admin.id)
    ).all()
    role_codes = {role.id: role.code for role in roles}
    permission_codes = {permission.id: permission.code for permission in permissions}
    assignments_by_role: dict[str, set[str]] = {role.code: set() for role in roles}
    for assignment in session.scalars(select(RolePermission)):
        assignments_by_role[role_codes[assignment.role_id]].add(
            permission_codes[assignment.permission_id]
        )

    assert {role.code for role in roles} == set(SYSTEM_ROLE_CODES)
    assert {permission.code for permission in permissions} == set(
        SYSTEM_PERMISSION_CODES
    )
    assert all(role.is_system for role in roles)
    assert all(permission.is_system for permission in permissions)
    assert len(platform_assignments) == len(ROLE_PERMISSION_CODES["PLATFORM_ADMIN"])
    assert assignments_by_role == ROLE_PERMISSION_CODES
    visible_roles, visible_total = IdentityService(session, _settings()).list_roles(
        1, 20, None, "code", False
    )
    assert {role.code for role in visible_roles}.isdisjoint(HIDDEN_SYSTEM_ROLE_CODES)
    assert visible_total == len(SYSTEM_ROLE_CODES) - len(HIDDEN_SYSTEM_ROLE_CODES)


def test_system_permissions_cannot_be_modified_or_deleted() -> None:
    """Ensure seeded permissions retain stable system identifiers."""
    session = _session()
    seed_system_rbac(session)
    session.commit()
    permission = session.scalar(
        select(Permission).where(Permission.code == "PLATFORM_VIEW")
    )
    assert permission is not None
    service = IdentityService(session, _settings())

    with pytest.raises(BusinessRuleError, match="cannot be modified"):
        service.update_permission(
            permission.id, PermissionUpdate(name="Changed"), uuid4()
        )
    with pytest.raises(BusinessRuleError, match="cannot be deleted"):
        service.delete_permission(permission.id, uuid4())


def test_failed_logins_lock_account_at_configured_threshold() -> None:
    """Ensure failures are recorded and enforce the configured lockout rule."""
    session = _session()
    user = User(
        email="user@example.com",
        full_name="Example User",
        password_hash="not-a-valid-password-hash",
    )
    session.add(user)
    session.commit()
    service = IdentityService(session, _settings())

    for _ in range(5):
        with suppress(AuthenticationError):
            service.login(user.email, "wrong-password", client_ip=None, user_agent=None)

    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert session.query(LoginHistory).count() == 5


def test_refresh_token_is_single_use_after_rotation() -> None:
    """Ensure a rotated refresh token cannot issue a second replacement pair."""
    session = _session()
    password = "Secure-Passphrase1!"
    user = User(
        email="refresh@example.com",
        full_name="Refresh User",
        password_hash=PasswordSecurity().hash_password(password),
    )
    session.add(user)
    session.commit()
    service = IdentityService(session, _settings())
    initial = service.login(user.email, password, client_ip=None, user_agent=None)

    replacement = service.refresh(initial.refresh_token)

    assert replacement.refresh_token != initial.refresh_token
    with pytest.raises(AuthenticationError):
        service.refresh(initial.refresh_token)


def test_production_rejects_the_known_development_jwt_key() -> None:
    """Ensure deployments cannot accidentally sign tokens with the public default."""
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            environment=Environment.PRODUCTION,
            bootstrap_admin_password="Production-bootstrap-secret",
        )

    settings = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret_key="production-secret-not-the-default",
        database_password="production-database-secret",
        bootstrap_admin_password="Production-bootstrap-secret",
    )
    assert (
        settings.jwt.secret_key.get_secret_value()
        == "production-secret-not-the-default"
    )


def test_firm_admin_has_no_platform_permissions_or_platform_access() -> None:
    """Prevent firm roles from crossing the immutable platform boundary."""
    assert ROLE_PERMISSION_CODES["FIRM_ADMIN"].isdisjoint(
        {
            "PLATFORM_VIEW",
            "PLATFORM_SETTINGS",
            "SYSTEM_CONFIGURATION",
            "LICENSE_MANAGE",
            "FIRM_CREATE",
            "FIRM_VIEW",
            "AUDIT_LOG_VIEW",
        }
    )
    user_id = uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset({"FIRM_ADMIN"}),
        permissions=ROLE_PERMISSION_CODES["FIRM_ADMIN"],
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )
    with pytest.raises(AuthorizationError):
        require_platform_admin()(principal)


def test_role_and_firm_changes_invalidate_existing_sessions() -> None:
    """Increment authorization state and revoke refresh tokens on grant changes."""
    session = _session()
    password = "Secure-Passphrase1!"
    user = User(
        email="invalidate@example.com",
        full_name="Invalidate User",
        password_hash=PasswordSecurity().hash_password(password),
    )
    role = Role(code="invalidate-role", name="Invalidate Role")
    firm = Firm(
        name="Invalidate Firm",
        code="INVALIDATE_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([user, role, firm])
    session.commit()
    service = IdentityService(session, _settings())
    tokens = service.login(user.email, password, client_ip=None, user_agent=None)

    service.set_user_roles(user.id, [role.id], uuid4())

    assert user.authorization_version == 1
    assert session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash.is_not(None),
            RefreshToken.revoked_at.is_not(None),
        )
    )
    claims = service._jwt.validate_token(tokens.access_token)
    assert (claims.model_extra or {})["authorization_version"] == 0


def test_firm_admin_identity_scope_blocks_cross_firm_and_platform_roles() -> None:
    """Keep user discovery and role assignment inside the selected firm."""
    session = _session()
    seed_system_rbac(session)
    firm_a = Firm(
        name="Firm A",
        code="BOUNDARY_A",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    firm_b = Firm(
        name="Firm B",
        code="BOUNDARY_B",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    user_a = User(
        email="firm-a@example.com",
        full_name="Firm A User",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    user_b = User(
        email="firm-b@example.com",
        full_name="Firm B User",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    session.add_all([firm_a, firm_b, user_a, user_b])
    session.flush()
    session.add_all(
        [
            UserFirm(user_id=user_a.id, firm_id=firm_a.id, is_primary=True),
            UserFirm(user_id=user_b.id, firm_id=firm_b.id, is_primary=True),
        ]
    )
    session.commit()
    service = IdentityService(session, _settings())

    users, total = service.list_users(
        1, 20, None, "email", False, firm_scope=firm_a.id
    )

    assert total == 1
    assert [user.id for user in users] == [user_a.id]
    with pytest.raises(ResourceNotFoundError):
        service.update_user(
            user_b.id,
            data=UserUpdate(full_name="Escalated"),
            actor_id=user_a.id,
            firm_scope=firm_a.id,
        )

    platform_role = session.scalar(
        select(Role).where(Role.code == "PLATFORM_ADMIN")
    )
    firm_role = session.scalar(select(Role).where(Role.code == "FIRM_ADMIN"))
    assert platform_role is not None
    assert firm_role is not None
    with pytest.raises(BusinessRuleError, match="Platform or cross-firm"):
        service.set_user_roles(
            user_a.id, [platform_role.id], user_a.id, firm_scope=firm_a.id
        )
    service.set_user_roles(
        user_a.id, [firm_role.id], user_a.id, firm_scope=firm_a.id
    )
    assignment = session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_a.id,
            UserRole.role_id == firm_role.id,
        )
    )
    assert assignment is not None
    assert assignment.firm_id == firm_a.id


def test_assignment_replacement_reuses_existing_rows() -> None:
    """Ensure unchanged, removed, and restored assignments reconcile safely."""
    session = _session()
    user = User(
        email="assignments@example.com",
        full_name="Assignments User",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    role_one = Role(code="role-one", name="Role One")
    role_two = Role(code="role-two", name="Role Two")
    permission_one = Permission(code="permission.one", name="Permission One")
    permission_two = Permission(code="permission.two", name="Permission Two")
    firm_one = Firm(
        name="Firm One",
        code="FIRM_ONE",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    firm_two = Firm(
        name="Firm Two",
        code="FIRM_TWO",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all(
        [
            user,
            role_one,
            role_two,
            permission_one,
            permission_two,
            firm_one,
            firm_two,
        ]
    )
    session.commit()
    service = IdentityService(session, _settings())

    service.set_user_roles(user.id, [role_one.id], user.id)
    user_role = session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id, UserRole.role_id == role_one.id
        )
    )
    assert user_role is not None
    original_user_role_id = user_role.id
    service.set_user_roles(user.id, [role_one.id], user.id)
    assert session.scalar(select(UserRole).where(UserRole.id == original_user_role_id))
    assert len(session.scalars(select(UserRole)).all()) == 1

    service.set_user_roles(user.id, [role_two.id], user.id)
    service.set_user_roles(user.id, [role_one.id, role_two.id], user.id)
    user_roles = {
        item.role_id: item for item in session.scalars(select(UserRole)).all()
    }
    assert user_roles[role_one.id].id == original_user_role_id
    assert user_roles[role_one.id].is_deleted is False
    assert user_roles[role_two.id].is_deleted is False

    service.set_role_permissions(role_one.id, [permission_one.id], user.id)
    role_permission = session.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_one.id,
            RolePermission.permission_id == permission_one.id,
        )
    )
    assert role_permission is not None
    original_role_permission_id = role_permission.id
    service.set_role_permissions(role_one.id, [permission_one.id], user.id)
    service.set_role_permissions(role_one.id, [permission_two.id], user.id)
    service.set_role_permissions(
        role_one.id, [permission_one.id, permission_two.id], user.id
    )
    role_permissions = {
        item.permission_id: item
        for item in session.scalars(select(RolePermission)).all()
    }
    assert role_permissions[permission_one.id].id == original_role_permission_id
    assert role_permissions[permission_one.id].is_deleted is False
    assert role_permissions[permission_two.id].is_deleted is False

    first_assignment = UserFirmAssignment(
        firm_id=firm_one.id, is_primary=True, is_active=True
    )
    service.set_user_firms(user.id, [first_assignment], user.id)
    user_firm = session.scalar(
        select(UserFirm).where(
            UserFirm.user_id == user.id, UserFirm.firm_id == firm_one.id
        )
    )
    assert user_firm is not None
    original_user_firm_id = user_firm.id
    original_created_by = user_firm.created_by
    service.set_user_firms(user.id, [first_assignment], user.id)

    second_assignment = UserFirmAssignment(
        firm_id=firm_two.id, is_primary=True, is_active=True
    )
    service.set_user_firms(user.id, [second_assignment], user.id)
    restored_assignment = UserFirmAssignment(
        firm_id=firm_one.id, is_primary=False, is_active=True
    )
    service.set_user_firms(user.id, [restored_assignment, second_assignment], user.id)
    user_firms = {
        item.firm_id: item for item in session.scalars(select(UserFirm)).all()
    }
    assert len(user_firms) == 2
    assert user_firms[firm_one.id].id == original_user_firm_id
    assert user_firms[firm_one.id].created_by == original_created_by
    assert user_firms[firm_one.id].is_deleted is False
    assert user_firms[firm_one.id].is_primary is False
    assert user_firms[firm_two.id].is_deleted is False

    service.set_user_firms(
        user.id,
        [
            UserFirmAssignment(firm_id=firm_one.id, is_primary=False, is_active=True),
            UserFirmAssignment(firm_id=firm_two.id, is_primary=False, is_active=True),
        ],
        user.id,
    )
    assert not any(
        item.is_primary
        for item in session.scalars(
            select(UserFirm).where(
                UserFirm.user_id == user.id, UserFirm.is_deleted.is_(False)
            )
        )
    )
    with pytest.raises(BusinessRuleError, match="Only one active firm"):
        service.set_user_firms(
            user.id,
            [
                UserFirmAssignment(
                    firm_id=firm_one.id, is_primary=True, is_active=True
                ),
                UserFirmAssignment(
                    firm_id=firm_two.id, is_primary=True, is_active=True
                ),
            ],
            user.id,
        )


def test_primary_switch_respects_partial_unique_index() -> None:
    """Ensure replacement-first A-to-B primary switches do not violate uniqueness."""
    session = _session()
    user = User(
        email="primary-switch@example.com",
        full_name="Primary Switch User",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    firm_one = Firm(
        name="Primary Firm",
        code="PRIMARY_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    firm_two = Firm(
        name="Replacement Firm",
        code="REPLACEMENT_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([user, firm_one, firm_two])
    session.commit()
    session.execute(
        text(
            "CREATE UNIQUE INDEX UQ_user_firms_active_primary "
            "ON user_firms (user_id) "
            "WHERE is_active = 1 AND is_primary = 1 AND is_deleted = 0"
        )
    )
    session.commit()
    service = IdentityService(session, _settings())
    service.set_user_firms(
        user.id,
        [UserFirmAssignment(firm_id=firm_one.id, is_primary=True, is_active=True)],
        user.id,
    )

    service.set_user_firms(
        user.id,
        [
            UserFirmAssignment(firm_id=firm_two.id, is_primary=True, is_active=True),
            UserFirmAssignment(firm_id=firm_one.id, is_primary=False, is_active=True),
        ],
        user.id,
    )

    memberships = {
        item.firm_id: item
        for item in session.scalars(
            select(UserFirm).where(
                UserFirm.user_id == user.id, UserFirm.is_deleted.is_(False)
            )
        )
    }
    assert memberships[firm_one.id].is_primary is False
    assert memberships[firm_two.id].is_primary is True


def test_user_preferences_are_versioned_and_require_active_firm_membership() -> None:
    """Ensure self-managed preferences default safely and validate default firms."""
    session = _session()
    user = User(
        email="preferences@example.com",
        full_name="Preferences User",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    active_firm = Firm(
        name="Active Firm",
        code="ACTIVE_PREF_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    inactive_firm = Firm(
        name="Inactive Firm",
        code="INACTIVE_PREF_FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([user, active_firm, inactive_firm])
    session.commit()
    service = IdentityService(session, _settings())

    defaults = service.get_user_preferences(user.id)
    assert defaults.preferences_version == 1
    assert defaults.preferred_theme == "light"
    assert session.query(UserPreferences).count() == 1

    service.set_user_firms(
        user.id,
        [
            UserFirmAssignment(firm_id=active_firm.id, is_primary=True, is_active=True),
            UserFirmAssignment(
                firm_id=inactive_firm.id, is_primary=False, is_active=False
            ),
        ],
        user.id,
    )
    updated = service.update_user_preferences(
        user.id,
        UserPreferencesUpdate(
            preferred_theme="green",
            default_firm_id=active_firm.id,
            rows_per_page=50,
            dashboard_layout={"widgets": ["summary"]},
        ),
    )
    assert updated.preferred_theme == "green"
    assert updated.default_firm_id == active_firm.id
    assert updated.rows_per_page == 50

    with pytest.raises(BusinessRuleError, match="active firm membership"):
        service.update_user_preferences(
            user.id, UserPreferencesUpdate(default_firm_id=inactive_firm.id)
        )

    reset = service.reset_user_preferences(user.id)
    assert reset.preferred_theme == "light"
    assert reset.default_firm_id is None
    assert reset.dashboard_layout == {}


def test_authenticated_user_firms_only_include_active_visible_memberships() -> None:
    """Ensure the firm switcher cannot discover unauthorized or inactive firms."""
    session = _session()
    user = User(
        email="firm-switcher@example.com",
        full_name="Firm Switcher",
        password_hash=PasswordSecurity().hash_password("Secure-Passphrase1!"),
    )
    primary = Firm(
        name="Primary Firm",
        code="SWITCH_PRIMARY",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    secondary = Firm(
        name="Secondary Firm",
        code="SWITCH_SECONDARY",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    inactive = Firm(
        name="Inactive Firm",
        code="SWITCH_INACTIVE",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=False,
    )
    unauthorized = Firm(
        name="Unauthorized Firm",
        code="SWITCH_UNAUTHORIZED",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([user, primary, secondary, inactive, unauthorized])
    session.flush()
    session.add_all(
        [
            UserFirm(
                user_id=user.id,
                firm_id=primary.id,
                is_primary=True,
                is_active=True,
            ),
            UserFirm(
                user_id=user.id,
                firm_id=secondary.id,
                is_primary=False,
                is_active=True,
            ),
            UserFirm(
                user_id=user.id,
                firm_id=inactive.id,
                is_primary=False,
                is_active=True,
            ),
        ]
    )
    session.commit()

    rows = IdentityService(session, _settings()).list_my_firms(user.id)

    assert [(firm.code, membership.is_primary) for membership, firm in rows] == [
        ("SWITCH_PRIMARY", True),
        ("SWITCH_SECONDARY", False),
    ]
