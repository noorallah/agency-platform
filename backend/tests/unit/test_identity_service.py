"""Focused authentication-service policy tests."""

from contextlib import suppress
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config.settings import Environment, Settings
from app.core.database.base import Base
from app.core.exceptions import AuthenticationError, BusinessRuleError
from app.core.security import PasswordSecurity
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
    UserRole,
)
from app.identity.schemas import UserFirmAssignment
from app.identity.services import IdentityService


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
        bootstrap_admin_password="Production-bootstrap-secret",
    )
    assert (
        settings.jwt.secret_key.get_secret_value()
        == "production-secret-not-the-default"
    )


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
