"""SQLAlchemy models for the platform identity and dynamic RBAC system."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class User(BaseEntity):
    """Represent an interactive platform user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    force_password_change: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    platform_admin: Mapped["PlatformAdmin | None"] = relationship(
        back_populates="user", uselist=False
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_history: Mapped[list["PasswordHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    login_history: Mapped[list["LoginHistory"]] = relationship(back_populates="user")


class PlatformAdmin(BaseEntity):
    """Designate a user as a platform-level administrator without a role name."""

    __tablename__ = "platform_admins"

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), unique=True, nullable=False
    )
    user: Mapped[User] = relationship(back_populates="platform_admin")


class Role(BaseEntity):
    """Represent a configurable collection of permissions."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class Permission(BaseEntity):
    """Represent one configurable capability granted through roles."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )


class UserRole(BaseEntity):
    """Associate a user with a configurable role."""

    __tablename__ = "user_roles"
    __table_args__ = (
        Index("IX_user_roles_user_id", "user_id"),
        Index("IX_user_roles_role_id", "role_id"),
        UniqueConstraint("user_id", "role_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("roles.id"), nullable=False
    )
    user: Mapped[User] = relationship(back_populates="user_roles")
    role: Mapped[Role] = relationship(back_populates="user_roles")


class RolePermission(BaseEntity):
    """Associate a role with a configurable permission."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        Index("IX_role_permissions_role_id", "role_id"),
        Index("IX_role_permissions_permission_id", "permission_id"),
        UniqueConstraint("role_id", "permission_id"),
    )

    role_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("roles.id"), nullable=False
    )
    permission_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("permissions.id"), nullable=False
    )
    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_permissions")


class PasswordHistory(BaseEntity):
    """Retain prior password hashes for future password-reuse checks."""

    __tablename__ = "password_history"
    __table_args__ = (
        Index("IX_password_history_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    user: Mapped[User] = relationship(back_populates="password_history")


class RefreshToken(BaseEntity):
    """Store a hashed, revocable refresh-token secret."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("IX_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("refresh_tokens.id")
    )
    user: Mapped[User] = relationship(back_populates="refresh_tokens")
    replaced_by: Mapped["RefreshToken | None"] = relationship(
        remote_side="RefreshToken.id", foreign_keys=[replaced_by_id]
    )


class LoginHistory(BaseEntity):
    """Audit successful, failed, and locked login attempts."""

    __tablename__ = "login_history"
    __table_args__ = (
        Index("IX_login_history_user_id_created_at", "user_id", "created_at"),
        Index("IX_login_history_attempted_email", "attempted_email"),
    )

    user_id: Mapped[UUID | None] = mapped_column(UUIDType(), ForeignKey("users.id"))
    attempted_email: Mapped[str] = mapped_column(String(320), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    user: Mapped[User | None] = relationship(back_populates="login_history")


class UserFirm(BaseEntity):
    """Associate a user with a firm and designate its primary active firm."""

    __tablename__ = "user_firms"
    __table_args__ = (
        Index("IX_user_firms_user_id", "user_id"),
        Index("IX_user_firms_firm_id", "firm_id"),
        UniqueConstraint("user_id", "firm_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), nullable=False
    )
    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
