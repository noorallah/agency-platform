"""Validated request and response contracts for vendor management."""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import validate_email, validate_phone


class VendorStatus(StrEnum):
    """Supported vendor lifecycle statuses."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class AddressType(StrEnum):
    """Supported reusable address classifications."""

    BILLING = "BILLING"
    SHIPPING = "SHIPPING"
    OFFICE = "OFFICE"
    WAREHOUSE = "WAREHOUSE"
    HEAD_OFFICE = "HEAD_OFFICE"
    OTHER = "OTHER"


class VendorSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class VendorContactInput(VendorSchema):
    """Create or replace one vendor contact person."""

    id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    mobile: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    is_primary: bool = False
    status: str = Field(default="ACTIVE", max_length=20)

    @field_validator("phone", "mobile")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """Validate an optional phone number."""
        return validate_phone(value) if value else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """Validate an optional email address."""
        return validate_email(value) if value else None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        """Normalize status."""
        return value.strip().upper()


class VendorAddressInput(VendorSchema):
    """Create or replace one geo-referenced vendor address."""

    id: UUID | None = None
    address_type: AddressType
    address_line1: str = Field(min_length=1, max_length=250)
    address_line2: str | None = Field(default=None, max_length=250)
    country_id: UUID | None = None
    state_id: UUID | None = None
    district_id: UUID | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    is_primary: bool = False


class VendorBankInput(VendorSchema):
    """Create or replace one vendor bank account."""

    id: UUID | None = None
    bank_name: str = Field(min_length=1, max_length=150)
    account_name: str = Field(min_length=1, max_length=150)
    account_number: str = Field(min_length=1, max_length=64)
    ifsc: str | None = Field(default=None, max_length=16)
    branch: str | None = Field(default=None, max_length=120)
    upi_id: str | None = Field(default=None, max_length=120)
    swift_code: str | None = Field(default=None, max_length=16)
    is_primary: bool = False

    @field_validator("ifsc", "swift_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        """Normalize codes."""
        return value.strip().upper() if value else None


class VendorTaxInput(VendorSchema):
    """Create or replace one vendor tax profile."""

    id: UUID | None = None
    gstin: str | None = Field(default=None, max_length=32)
    pan: str | None = Field(default=None, max_length=32)
    tan: str | None = Field(default=None, max_length=32)
    fssai: str | None = Field(default=None, max_length=32)
    drug_license: str | None = Field(default=None, max_length=64)
    import_export_code: str | None = Field(default=None, max_length=32)
    extra_fields: dict[str, object] = Field(default_factory=dict)
    is_primary: bool = False

    @field_validator(
        "gstin",
        "pan",
        "tan",
        "fssai",
        "drug_license",
        "import_export_code",
        mode="before",
    )
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        """Normalize codes."""
        return value.strip().upper() if value else None


class VendorAttachmentInput(VendorSchema):
    """Create or replace one attachment row."""

    id: UUID | None = None
    file_name: str = Field(min_length=1, max_length=255)
    file_url: str = Field(min_length=1, max_length=1000)
    mime_type: str | None = Field(default=None, max_length=120)
    description: str | None = None


class VendorNoteInput(VendorSchema):
    """Create or replace one vendor note row."""

    id: UUID | None = None
    note: str = Field(min_length=1)
    note_type: str = Field(default="GENERAL", max_length=30)

    @field_validator("note_type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        """Normalize type."""
        return value.strip().upper()


class VendorWrite(VendorSchema):
    """Fields shared by create and complete update requests."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    type_id: UUID | None = None
    status: VendorStatus = VendorStatus.ACTIVE
    business_profile_id: UUID | None = None
    gst_registration: bool = False
    gstin: str | None = Field(default=None, max_length=32)
    pan: str | None = Field(default=None, max_length=32)
    license_number: str | None = Field(default=None, max_length=64)
    registration_number: str | None = Field(default=None, max_length=64)
    website: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=20)
    mobile: str | None = Field(default=None, max_length=20)
    remarks: str | None = None
    business_attributes: dict[str, object] = Field(default_factory=dict)
    contacts: list[VendorContactInput] = Field(default_factory=list, max_length=50)
    addresses: list[VendorAddressInput] = Field(default_factory=list, max_length=50)
    banking: list[VendorBankInput] = Field(default_factory=list, max_length=20)
    tax: list[VendorTaxInput] = Field(default_factory=list, max_length=20)
    attachments: list[VendorAttachmentInput] = Field(
        default_factory=list, max_length=50
    )
    notes: list[VendorNoteInput] = Field(default_factory=list, max_length=200)

    @field_validator(
        "code",
        "gstin",
        "pan",
        "license_number",
        "registration_number",
        mode="before",
    )
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        """Normalize codes."""
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("name", "legal_name", "display_name", mode="before")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        """Normalize names."""
        return value.strip() if value else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """Validate an optional email address."""
        return validate_email(value) if value else None

    @field_validator("phone", "mobile")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """Validate an optional phone number."""
        return validate_phone(value) if value else None

    @field_validator("website", mode="before")
    @classmethod
    def normalize_website(cls, value: str | None) -> str | None:
        """Normalize website."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_nested_defaults(self) -> "VendorWrite":
        """Validate nested defaults."""
        if sum(contact.is_primary for contact in self.contacts) > 1:
            raise ValueError("Only one primary contact is allowed.")
        if sum(address.is_primary for address in self.addresses) > 1:
            raise ValueError("Only one primary address is allowed.")
        if sum(account.is_primary for account in self.banking) > 1:
            raise ValueError("Only one primary bank account is allowed.")
        if sum(detail.is_primary for detail in self.tax) > 1:
            raise ValueError("Only one primary tax detail row is allowed.")
        return self


class VendorCreate(VendorWrite):
    """Create one vendor and nested records."""


class VendorUpdate(VendorWrite):
    """Replace editable vendor data and nested records."""


class VendorImportRequest(VendorSchema):
    """Batch of validated vendor records imported atomically."""

    records: list[VendorCreate] = Field(min_length=1, max_length=1000)


class VendorCategoryWrite(VendorSchema):
    """Create or update one vendor category."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Uppercase and trim an identifier code."""
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Trim a display name."""
        return value.strip()


class VendorTypeWrite(VendorSchema):
    """Create or update one vendor type."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Uppercase and trim an identifier code."""
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Trim a display name."""
        return value.strip()


class VendorContactResponse(VendorContactInput):
    """Expose one persisted vendor contact."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorAddressResponse(VendorAddressInput):
    """Expose one persisted vendor address."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorBankResponse(VendorBankInput):
    """Expose one persisted vendor bank account."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorTaxResponse(VendorTaxInput):
    """Expose one persisted vendor tax row."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorAttachmentResponse(VendorAttachmentInput):
    """Expose one persisted vendor attachment row."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorNoteResponse(VendorNoteInput):
    """Expose one persisted vendor note row."""

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorCategoryResponse(VendorSchema):
    """Expose one persisted vendor category."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_deleted: bool


class VendorTypeResponse(VendorSchema):
    """Expose one persisted vendor type."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_deleted: bool


class VendorResponse(VendorSchema):
    """Expose a complete vendor record."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    legal_name: str | None
    display_name: str
    category_id: UUID | None
    type_id: UUID | None
    status: VendorStatus
    business_profile_id: UUID | None
    gst_registration: bool
    gstin: str | None
    pan: str | None
    license_number: str | None
    registration_number: str | None
    website: str | None
    email: str | None
    phone: str | None
    mobile: str | None
    remarks: str | None
    business_attributes: dict[str, object]
    created_by: UUID | None
    created_at: datetime
    updated_by: UUID | None
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    contacts: list[VendorContactResponse]
    addresses: list[VendorAddressResponse]
    bank_accounts: list[VendorBankResponse]
    tax_details: list[VendorTaxResponse]
    attachments: list[VendorAttachmentResponse]
    notes: list[VendorNoteResponse]


class VendorSummary(VendorSchema):
    """Expose aggregate vendor lifecycle counts."""

    total: int
    active: int
    inactive: int
    draft: int
    archived: int
    deleted: int


class VendorListFilters(VendorSchema):
    """Validated collection filters shared by routes and services."""

    status: VendorStatus | None = None
    category_id: UUID | None = None
    type_id: UUID | None = None
    business_profile_id: UUID | None = None
    city_id: UUID | None = None
    state_id: UUID | None = None
    country_id: UUID | None = None
    firm_id: UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> "VendorListFilters":
        """Reject a date window that ends before it starts."""
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to.")
        return self
