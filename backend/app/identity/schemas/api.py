"""Request and response contracts for identity administration APIs."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiSchema(BaseModel):
    """Forbid undeclared API payload fields."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LoginRequest(ApiSchema):
    """Credentials submitted to start a session."""

    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(ApiSchema):
    """Refresh token submitted for rotation or revocation."""

    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(ApiSchema):
    """Authenticated user's current and replacement password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class TokenResponse(ApiSchema):
    """A signed access/refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool


ThemeName = Literal["light", "dark", "blue", "green", "high_contrast"]
DateFormat = Literal["yyyy-MM-dd", "dd/MM/yyyy", "MM/dd/yyyy"]
TimeFormat = Literal["12h", "24h"]
NumberFormat = Literal["1,234.56", "1.234,56"]
CurrencyFormat = Literal["symbol", "code"]


class UserPreferencesUpdate(ApiSchema):
    """Mutable, versioned preferences owned by the authenticated user."""

    preferences_version: int | None = Field(default=None, ge=1, le=1000)
    preferred_theme: ThemeName | None = None
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")
    date_format: DateFormat | None = None
    time_format: TimeFormat | None = None
    number_format: NumberFormat | None = None
    currency_format: CurrencyFormat | None = None
    default_firm_id: UUID | None = None
    default_landing_page: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9._/-]+$"
    )
    rows_per_page: int | None = Field(default=None, ge=10, le=100)
    notification_preferences: dict[str, Any] | None = Field(
        default=None, max_length=100
    )
    dashboard_layout: dict[str, Any] | None = Field(default=None, max_length=100)


class UserPreferencesResponse(ApiSchema):
    """Safe response contract for the authenticated user's preferences."""

    preferences_version: int
    preferred_theme: ThemeName
    language: str
    date_format: DateFormat
    time_format: TimeFormat
    number_format: NumberFormat
    currency_format: CurrencyFormat
    default_firm_id: UUID | None
    default_landing_page: str
    rows_per_page: int
    notification_preferences: dict[str, Any]
    dashboard_layout: dict[str, Any]


class UserCreate(ApiSchema):
    """Administrator-provisioned user details."""

    email: str = Field(max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)
    is_active: bool = True
    force_password_change: bool = True
    expires_at: datetime | None = None


class UserUpdate(ApiSchema):
    """Mutable administrator-controlled user details."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    expires_at: datetime | None = None
    unlock: bool = False


class UserResponse(ApiSchema):
    """Safe user representation that never exposes password hashes."""

    id: UUID
    email: str
    full_name: str
    is_active: bool
    force_password_change: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoleCreate(ApiSchema):
    """Details for a custom role."""

    code: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_active: bool = True


class RoleUpdate(ApiSchema):
    """Mutable custom-role details."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class RoleResponse(ApiSchema):
    """Role details with the immutable system/custom classification."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_system: bool
    firm_id: UUID | None


class PermissionCreate(ApiSchema):
    """Details for a permission capability."""

    code: str = Field(min_length=2, max_length=150, pattern=r"^[a-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_active: bool = True


class PermissionUpdate(ApiSchema):
    """Mutable permission details."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class PermissionResponse(ApiSchema):
    """Permission details."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_system: bool


class IdentifierList(ApiSchema):
    """A replacement set of related resource identifiers."""

    ids: list[UUID] = Field(default_factory=list, max_length=100)


class UserFirmAssignment(ApiSchema):
    """One user-to-firm membership declaration."""

    firm_id: UUID
    is_primary: bool = False
    is_active: bool = True


class UserFirmAssignments(ApiSchema):
    """Replacement set of user firm memberships."""

    assignments: list[UserFirmAssignment] = Field(max_length=100)


class UserFirmResponse(ApiSchema):
    """Persisted user-to-firm membership."""

    id: UUID
    user_id: UUID
    firm_id: UUID
    is_primary: bool
    is_active: bool


class MyFirmResponse(ApiSchema):
    """Firm identity and membership metadata available to the current user."""

    id: UUID
    code: str
    name: str
    is_primary: bool


class FinancialYearStart(ApiSchema):
    """A date value retained for generated API documentation reuse."""

    value: date
