"""Pydantic representations of persisted identity-domain records."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IdentitySchema(BaseModel):
    """Base schema configuration for SQLAlchemy identity entities."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class UserSchema(IdentitySchema):
    """Safe representation of an interactive user."""

    id: UUID
    email: str
    full_name: str
    is_active: bool
    force_password_change: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    expires_at: datetime | None


class PlatformAdminSchema(IdentitySchema):
    """Representation of a platform administrator designation."""

    id: UUID
    user_id: UUID


class RoleSchema(IdentitySchema):
    """Representation of a configurable role."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_system: bool


class PermissionSchema(IdentitySchema):
    """Representation of a configurable permission."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_system: bool


class UserRoleSchema(IdentitySchema):
    """Representation of a user-to-role association."""

    id: UUID
    user_id: UUID
    role_id: UUID


class UserFirmSchema(IdentitySchema):
    """Representation of a user-to-firm membership."""

    id: UUID
    user_id: UUID
    firm_id: UUID
    is_primary: bool
    is_active: bool


class RolePermissionSchema(IdentitySchema):
    """Representation of a role-to-permission association."""

    id: UUID
    role_id: UUID
    permission_id: UUID


class PasswordHistorySchema(IdentitySchema):
    """Metadata representation of a historical password record."""

    id: UUID
    user_id: UUID
    created_at: datetime


class RefreshTokenSchema(IdentitySchema):
    """Metadata representation of a persisted refresh-token record."""

    id: UUID
    user_id: UUID
    expires_at: datetime
    revoked_at: datetime | None
    replaced_by_id: UUID | None


class LoginHistorySchema(IdentitySchema):
    """Representation of a recorded login attempt."""

    id: UUID
    user_id: UUID | None
    attempted_email: str
    outcome: str
    client_ip: str | None
    user_agent: str | None
    failure_reason: str | None
    created_at: datetime
