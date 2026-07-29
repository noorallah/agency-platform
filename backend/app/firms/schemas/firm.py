"""Request and response contracts for firm administration."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    is_active: bool = True
    notes: str | None = None

    @field_validator("code", "country", "currency_code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize identifiers consistently before persistence."""
        return value.strip().upper()

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
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
