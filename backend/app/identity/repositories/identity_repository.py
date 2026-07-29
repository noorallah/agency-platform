"""SQLAlchemy persistence adapter for identity, RBAC, and token data."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.entity import BaseEntity
from app.identity.models import (
    LoginHistory,
    PasswordHistory,
    Permission,
    PlatformAdmin,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserFirm,
    UserRole,
)


class IdentityRepository:
    """Encapsulate identity-domain persistence queries."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to one unit-of-work session."""
        self._session = session

    def get_user(self, user_id: UUID) -> User | None:
        """Return a non-deleted user by identifier."""
        return self._session.scalar(
            select(User).where(User.id == user_id, User.is_deleted.is_(False))
        )

    def get_user_by_email(self, email: str) -> User | None:
        """Return a non-deleted user by normalized email address."""
        return self._session.scalar(
            select(User).where(User.email == email, User.is_deleted.is_(False))
        )

    def get_platform_admin(self, user_id: UUID) -> PlatformAdmin | None:
        """Return the non-deleted platform-admin designation for a user."""
        return self._session.scalar(
            select(PlatformAdmin).where(
                PlatformAdmin.user_id == user_id,
                PlatformAdmin.is_deleted.is_(False),
            )
        )

    def get_role(self, role_id: UUID) -> Role | None:
        """Return a non-deleted role by identifier."""
        return self._session.scalar(
            select(Role).where(Role.id == role_id, Role.is_deleted.is_(False))
        )

    def get_permission(self, permission_id: UUID) -> Permission | None:
        """Return a non-deleted permission by identifier."""
        return self._session.scalar(
            select(Permission).where(
                Permission.id == permission_id, Permission.is_deleted.is_(False)
            )
        )

    def permissions_for_user(self, user_id: UUID) -> list[str]:
        """Return active permissions granted through non-deleted associations."""
        statement = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.is_active.is_(True),
                Role.is_deleted.is_(False),
                Permission.is_active.is_(True),
                Permission.is_deleted.is_(False),
                UserRole.is_deleted.is_(False),
                RolePermission.is_deleted.is_(False),
            )
            .distinct()
            .order_by(Permission.code)
        )
        return list(self._session.scalars(statement))

    def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        """Return a non-deleted refresh-token record by its stored hash."""
        return self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_deleted.is_(False),
            )
        )

    def add_refresh_token(self, refresh_token: RefreshToken) -> None:
        """Stage a new refresh token for persistence."""
        self._session.add(refresh_token)

    def add(self, entity: BaseEntity) -> None:
        """Stage any identity-domain entity for persistence."""
        self._session.add(entity)

    def add_password_history(self, entry: PasswordHistory) -> None:
        """Stage a historical password hash for persistence."""
        self._session.add(entry)

    def add_login_history(self, entry: LoginHistory) -> None:
        """Stage a login audit record for persistence."""
        self._session.add(entry)

    def flush(self) -> None:
        """Flush staged state when a generated identifier is required."""
        self._session.flush()

    def list_login_history(self, user_id: UUID) -> Sequence[LoginHistory]:
        """Return login history for one user."""
        return self._session.scalars(
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
        ).all()

    def list_user_roles(self, user_id: UUID) -> Sequence[UserRole]:
        """Return non-deleted role associations for a user."""
        return self._session.scalars(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.is_deleted.is_(False)
            )
        ).all()

    def list_role_permissions(self, role_id: UUID) -> Sequence[RolePermission]:
        """Return non-deleted permission associations for a role."""
        return self._session.scalars(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.is_deleted.is_(False),
            )
        ).all()

    def list_password_history(self, user_id: UUID) -> Sequence[PasswordHistory]:
        """Return password history newest first for a user."""
        return self._session.scalars(
            select(PasswordHistory)
            .where(
                PasswordHistory.user_id == user_id,
                PasswordHistory.is_deleted.is_(False),
            )
            .order_by(PasswordHistory.created_at.desc())
        ).all()

    def list_user_firms(self, user_id: UUID) -> Sequence[UserFirm]:
        """Return active firm associations for a user."""
        return self._session.scalars(
            select(UserFirm).where(
                UserFirm.user_id == user_id, UserFirm.is_deleted.is_(False)
            )
        ).all()
