"""Request and response contracts for firm administration."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.tenancy.models import DeploymentMode
from app.core.validation import validate_email, validate_phone


class FirmSchema(BaseModel):
    """Base configuration for firm API contracts."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class FirmCreate(FirmSchema):
    """Required and optional fields for a new firm."""

    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    gst_number: str | None = Field(default=None, max_length=32)
    pan_number: str | None = Field(default=None, max_length=32)
    address_line1: str | None = Field(default=None, max_length=250)
    address_line2: str | None = Field(default=None, max_length=250)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=24)
    country: str = Field(min_length=2, max_length=2)
    state: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=20)
    currency_code: str = Field(min_length=3, max_length=3)
    financial_year_start: date
    deployment_mode: DeploymentMode | None = None
    database_name: str | None = Field(default=None, max_length=128)
    schema_name: str | None = Field(default=None, max_length=128)
    database_type: str | None = Field(default="postgresql", max_length=32)
    connection_profile: str | None = Field(default=None, max_length=64)
    status: str = Field(default="ACTIVE", max_length=32)
    is_active: bool = True
    notes: str | None = None

    @field_validator("code", "country", "currency_code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize identifiers consistently before persistence."""
        return value.strip().upper()

    @field_validator("deployment_mode", mode="before")
    @classmethod
    def normalize_deployment_mode(
        cls, value: str | DeploymentMode | None
    ) -> DeploymentMode | None:
        """Normalize deployment mode case consistently."""
        if value is None:
            return None
        if isinstance(value, DeploymentMode):
            return value
        return DeploymentMode(value.strip().upper())

    @field_validator(
        "database_name",
        "schema_name",
        "database_type",
        "connection_profile",
        "status",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional textual tenancy metadata."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("status", mode="after")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        """Keep registry status values uppercase."""
        return value.upper()

    @field_validator("database_type", mode="after")
    @classmethod
    def normalize_database_type(cls, value: str | None) -> str | None:
        """Keep database type canonicalized for resolver matching."""
        return value.lower() if value is not None else None

    @field_validator("connection_profile", mode="after")
    @classmethod
    def normalize_connection_profile(cls, value: str | None) -> str | None:
        """Match the upper-cased keys connection profiles are parsed under."""
        return value.upper() if value is not None else None

    @field_validator("contact_email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """Validate an optional contact email."""
        return validate_email(value) if value else None

    @field_validator("contact_phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """Validate an optional contact phone number."""
        return validate_phone(value) if value else None


class FirmUpdate(FirmCreate):
    """Complete replacement representation for an existing firm."""


class FirmProvisionResponse(FirmSchema):
    """Outcome of building a firm's dedicated storage."""

    firm_id: UUID
    deployment_mode: DeploymentMode
    database_name: str | None
    schema_name: str | None
    connection_profile: str | None
    provisioned_at: datetime | None
    already_provisioned: bool


class FirmResponse(FirmSchema):
    """A persisted firm safe to expose via the REST API."""

    id: UUID
    name: str
    code: str
    gst_number: str | None
    pan_number: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    postal_code: str | None
    country: str
    state: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    currency_code: str
    financial_year_start: date
    deployment_mode: DeploymentMode
    database_name: str | None
    schema_name: str | None
    database_type: str
    connection_profile: str | None
    provisioned_at: datetime | None
    status: str
    created_date: datetime | None
    updated_date: datetime | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
