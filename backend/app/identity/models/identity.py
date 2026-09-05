"""SQLAlchemy models for the platform identity and dynamic RBAC system."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType
from app.core.enums import PlatformAdminScope


class User(BaseEntity):
    """Represent an interactive platform user."""

    __tablename__ = "users"
    __table_args__ = (
        # Uniqueness applies to live accounts only, so an address is released
        # when its user is soft deleted and a leaver can be re-onboarded.
        # PostgreSQL and SQLite honour the predicate; MySQL ignores it, so
        # IdentityService.create_user remains the authoritative check.
        Index(
            "UQ_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
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
    authorization_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Optional HR/profile enrichment fields (Phase 9). These are purely
    # informational and are never consulted by authentication/authorization —
    # login continues to rely solely on email/password_hash/roles above.
    personal_mobile: Mapped[str | None] = mapped_column(String(32))
    alternate_mobile: Mapped[str | None] = mapped_column(String(32))
    personal_email: Mapped[str | None] = mapped_column(String(320))
    office_email: Mapped[str | None] = mapped_column(String(320))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_mobile: Mapped[str | None] = mapped_column(String(32))
    emergency_relationship: Mapped[str | None] = mapped_column(String(100))
    employee_code: Mapped[str | None] = mapped_column(String(64))
    joining_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leaving_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department: Mapped[str | None] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(200))
    reporting_manager: Mapped[str | None] = mapped_column(String(200))
    employment_type: Mapped[str | None] = mapped_column(String(100))
    cost_center: Mapped[str | None] = mapped_column(String(100))
    profile_photo_url: Mapped[str | None] = mapped_column(String(1000))
    # Structured, optional profile sub-records. Modeled as JSON for now since
    # no shared cross-module address/attachment framework exists yet; this is
    # the reference shape future modules should normalize toward.
    profile_addresses: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    profile_documents: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)

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
    preferences: Mapped["UserPreferences | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class PlatformAdmin(BaseEntity):
    """Designate a user as a platform-level administrator without a role name."""

    __tablename__ = "platform_admins"

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), unique=True, nullable=False
    )
    #: How far the designation reaches. See `PlatformAdminScope`.
    #:
    #: NOT NULL with a Python-side default and **no server default**, the shape
    #: `einvoice.mode` uses and for the same reason: a server default is one
    #: migration away from silently handing somebody every firm's books. The
    #: default is the *narrow* value, so a row written by a route that has not
    #: thought about reach gets the safe answer; the migration backfills the
    #: rows that already exist to `ALL_FIRMS`, because that is what they have
    #: today and demoting a live administrator without being asked would lock
    #: whoever runs the platform out of it.
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PlatformAdminScope.PLATFORM.value
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
    firm_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("firms.id", ondelete="RESTRICT"), index=True
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class UserTemplate(BaseEntity):
    """A named bundle of roles for one job, so a firm hires by naming the job.

    A firm administrator setting up a new counter clerk should not have to
    reassemble a permission set from twelve roles and remember which. The
    template is that decision, made once and given a name the firm uses.

    Deliberately a **role bundle and not a dormant user row**. Cloning a user
    carries everything a user has -- an email, a password, memberships, an
    audit trail, a login history -- and the clone quietly inherits any of it
    that was edited after the template was written. A bundle carries only what
    the job needs, and applying one is a plain `set_user_roles` call whose
    result the administrator is then free to edit: a template is where you
    start, not a thing you stay inside.

    `firm_id` NULL means platform-provided and offered to every firm. A firm's
    own templates are visible only to it.
    """

    __tablename__ = "user_templates"
    __table_args__ = (
        Index("IX_user_templates_firm_id", "firm_id"),
        # Codes are unique among live rows, per scope. Two indexes rather than
        # one on `(firm_id, code)`, because PostgreSQL treats NULLs as
        # distinct -- so a single key would let the platform hold ten
        # templates all called `counter-sales`.
        Index(
            "UQ_user_templates_platform_code_active",
            "code",
            unique=True,
            postgresql_where=text("firm_id IS NULL AND is_deleted = false"),
            sqlite_where=text("firm_id IS NULL AND is_deleted = 0"),
        ),
        Index(
            "UQ_user_templates_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("firm_id IS NOT NULL AND is_deleted = false"),
            sqlite_where=text("firm_id IS NOT NULL AND is_deleted = 0"),
        ),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    firm_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("firms.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    template_roles: Mapped[list["UserTemplateRole"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class UserTemplateRole(BaseEntity):
    """One role in a template's bundle."""

    __tablename__ = "user_template_roles"
    __table_args__ = (
        Index("IX_user_template_roles_template_id", "template_id"),
        UniqueConstraint(
            "template_id", "role_id", name="UQ_user_template_roles_template_role"
        ),
    )

    template_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("user_templates.id"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    template: Mapped[UserTemplate] = relationship(back_populates="template_roles")
    #: One-way. `Role` needs no collection of the templates naming it -- the
    #: question "which templates use this role" has no caller, and a cascade
    #: from that side would make deleting a role reach into templates.
    role: Mapped["Role"] = relationship()


class Permission(BaseEntity):
    """Represent one configurable capability granted through roles."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
        Index("IX_user_roles_firm_id", "firm_id"),
        UniqueConstraint(
            "user_id",
            "role_id",
            "firm_id",
            name="UQ_user_roles_user_role_firm",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("roles.id"), nullable=False
    )
    firm_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("firms.id", ondelete="RESTRICT"), nullable=True
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


class UserPreferences(BaseEntity):
    """Persist versioned, user-owned desktop and workspace preferences."""

    __tablename__ = "user_preferences"

    user_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id"), unique=True, nullable=False
    )
    preferences_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    #: The accent identity. Retains its column name and its existing values so
    #: an older client keeps working; "light" now means "no accent chosen".
    preferred_theme: Mapped[str] = mapped_column(
        String(32), nullable=False, default="light", server_default="light"
    )
    #: Light, dark, or defer to the operating system.
    #:
    #: A separate column rather than another value in ``preferred_theme``:
    #: brightness and accent are independent, and folding "system" into the
    #: existing set would leave "dark" ambiguous about which of the two it
    #: meant. Defaults to ``system`` because until now nobody could express a
    #: brightness preference, so a stored "light" was never a choice anyone
    #: made -- it was the absence of one.
    preferred_theme_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="system", server_default="system"
    )
    preferred_high_contrast: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    language: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en", server_default="en"
    )
    date_format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="yyyy-MM-dd", server_default="yyyy-MM-dd"
    )
    time_format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="24h", server_default="24h"
    )
    number_format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1,234.56", server_default="1,234.56"
    )
    currency_format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="symbol", server_default="symbol"
    )
    default_firm_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("firms.id")
    )
    default_landing_page: Mapped[str] = mapped_column(
        String(100), nullable=False, default="dashboard", server_default="dashboard"
    )
    rows_per_page: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    notification_preferences: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    dashboard_layout: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    user: Mapped[User] = relationship(back_populates="preferences")
