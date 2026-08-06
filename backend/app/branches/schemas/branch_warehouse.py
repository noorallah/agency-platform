"""Validated request and response contracts for branch and warehouse management."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import validate_email, validate_phone


class BranchStatus(StrEnum):
    """Supported branch lifecycle statuses."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class WarehouseStatus(StrEnum):
    """Supported warehouse lifecycle statuses."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class StorageNodeType(StrEnum):
    """Supported storage structure node types."""

    STORAGE_AREA = "STORAGE_AREA"
    RACK = "RACK"
    SHELF = "SHELF"
    BIN = "BIN"
    RECEIVING_AREA = "RECEIVING_AREA"


class BranchWarehouseSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class BranchTypeWrite(BranchWarehouseSchema):
    """Create or update one branch type."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class WarehouseTypeWrite(BranchWarehouseSchema):
    """Create or update one warehouse type."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class BranchWrite(BranchWarehouseSchema):
    """Shared branch write fields."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    business_profile_id: UUID | None = None
    branch_type_id: UUID | None = None
    branch_manager_id: UUID | None = None
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=20)
    mobile: str | None = Field(default=None, max_length=20)
    country_id: UUID | None = None
    state_id: UUID | None = None
    district_id: UUID | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    address_line1: str | None = Field(default=None, max_length=250)
    address_line2: str | None = Field(default=None, max_length=250)
    timezone: str | None = Field(default=None, max_length=100)
    currency_code: str | None = Field(default=None, max_length=3)
    gst_registration: bool = False
    pan: str | None = Field(default=None, max_length=32)
    license_number: str | None = Field(default=None, max_length=64)
    working_hours: dict[str, object] = Field(default_factory=dict)
    is_default: bool = False
    status: BranchStatus = BranchStatus.ACTIVE

    @field_validator("code", "pan", "license_number", "currency_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("name", "display_name", mode="before")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return validate_email(value) if value else None

    @field_validator("phone", "mobile")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return validate_phone(value) if value else None


class BranchCreate(BranchWrite):
    """Create one branch."""


class BranchUpdate(BranchWrite):
    """Update one branch."""


class WarehouseWrite(BranchWarehouseSchema):
    """Shared warehouse write fields."""

    branch_id: UUID
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    warehouse_type_id: UUID | None = None
    warehouse_manager_id: UUID | None = None
    business_profile_id: UUID | None = None
    country_id: UUID | None = None
    state_id: UUID | None = None
    district_id: UUID | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    address_line1: str | None = Field(default=None, max_length=250)
    address_line2: str | None = Field(default=None, max_length=250)
    capacity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    capacity_unit: str | None = Field(default=None, max_length=20)
    is_default: bool = False
    temperature_controlled: bool = False
    cold_storage: bool = False
    hazardous_storage: bool = False
    has_receiving_area: bool = False
    has_dispatch_area: bool = False
    has_returns_area: bool = False
    has_inspection_area: bool = False
    has_packing_area: bool = False
    has_loading_dock: bool = False
    status: WarehouseStatus = WarehouseStatus.ACTIVE

    @field_validator("code", "capacity_unit", mode="before")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("name", "display_name", mode="before")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class WarehouseCreate(WarehouseWrite):
    """Create one warehouse."""


class WarehouseUpdate(WarehouseWrite):
    """Update one warehouse."""


class StorageNodeWrite(BranchWarehouseSchema):
    """Create or update one storage hierarchy node."""

    warehouse_id: UUID
    parent_id: UUID | None = None
    node_type: StorageNodeType
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0, le=99999)
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class StorageNodeCreate(StorageNodeWrite):
    """Create one storage node."""


class StorageNodeUpdate(StorageNodeWrite):
    """Update one storage node."""


class BranchImportRequest(BranchWarehouseSchema):
    """Batch branch import payload."""

    records: list[BranchCreate] = Field(min_length=1, max_length=1000)


class WarehouseImportRequest(BranchWarehouseSchema):
    """Batch warehouse import payload."""

    records: list[WarehouseCreate] = Field(min_length=1, max_length=1000)


class BranchTypeResponse(BranchWarehouseSchema):
    """Expose persisted branch type."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_deleted: bool


class BranchResponse(BranchWarehouseSchema):
    """Expose persisted branch."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    display_name: str
    description: str | None
    business_profile_id: UUID | None
    branch_type_id: UUID | None
    branch_manager_id: UUID | None
    email: str | None
    phone: str | None
    mobile: str | None
    country_id: UUID | None
    state_id: UUID | None
    district_id: UUID | None
    city_id: UUID | None
    postal_code_id: UUID | None
    locality_id: UUID | None
    address_line1: str | None
    address_line2: str | None
    timezone: str | None
    currency_code: str | None
    gst_registration: bool
    pan: str | None
    license_number: str | None
    working_hours: dict[str, object]
    is_default: bool
    status: BranchStatus
    is_deleted: bool
    warehouse_count: int = 0


class WarehouseTypeResponse(BranchWarehouseSchema):
    """Expose persisted warehouse type."""

    id: UUID
    firm_id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    is_deleted: bool


class WarehouseResponse(BranchWarehouseSchema):
    """Expose persisted warehouse."""

    id: UUID
    firm_id: UUID
    branch_id: UUID
    code: str
    name: str
    display_name: str
    description: str | None
    warehouse_type_id: UUID | None
    warehouse_manager_id: UUID | None
    business_profile_id: UUID | None
    country_id: UUID | None
    state_id: UUID | None
    district_id: UUID | None
    city_id: UUID | None
    postal_code_id: UUID | None
    locality_id: UUID | None
    address_line1: str | None
    address_line2: str | None
    capacity: Decimal | None
    capacity_unit: str | None
    is_default: bool
    temperature_controlled: bool
    cold_storage: bool
    hazardous_storage: bool
    has_receiving_area: bool
    has_dispatch_area: bool
    has_returns_area: bool
    has_inspection_area: bool
    has_packing_area: bool
    has_loading_dock: bool
    status: WarehouseStatus
    is_deleted: bool


class StorageNodeResponse(BranchWarehouseSchema):
    """Expose persisted storage node."""

    id: UUID
    warehouse_id: UUID
    parent_id: UUID | None
    node_type: StorageNodeType
    code: str
    name: str
    description: str | None
    path: str
    sort_order: int
    is_active: bool
    is_deleted: bool


class BranchListFilters(BranchWarehouseSchema):
    """Validated branch collection filters."""

    status: BranchStatus | None = None
    branch_type_id: UUID | None = None
    manager_id: UUID | None = None
    business_profile_id: UUID | None = None
    city_id: UUID | None = None
    state_id: UUID | None = None
    country_id: UUID | None = None
    include_deleted: bool = False
    created_from: date | None = None
    created_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "BranchListFilters":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to.")
        return self


class WarehouseListFilters(BranchWarehouseSchema):
    """Validated warehouse collection filters."""

    status: WarehouseStatus | None = None
    branch_id: UUID | None = None
    warehouse_type_id: UUID | None = None
    manager_id: UUID | None = None
    business_profile_id: UUID | None = None
    city_id: UUID | None = None
    state_id: UUID | None = None
    country_id: UUID | None = None
    include_deleted: bool = False
    created_from: date | None = None
    created_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "WarehouseListFilters":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to.")
        return self


class BranchSummary(BranchWarehouseSchema):
    """Expose aggregate branch counts."""

    total: int
    active: int
    inactive: int
    draft: int
    archived: int
    deleted: int


class WarehouseSummary(BranchWarehouseSchema):
    """Expose aggregate warehouse counts."""

    total: int
    active: int
    inactive: int
    draft: int
    archived: int
    deleted: int


class BulkIdsRequest(BranchWarehouseSchema):
    """Bulk operation payload containing entity IDs."""

    ids: list[UUID] = Field(min_length=1, max_length=5000)


class BulkBranchStatusRequest(BulkIdsRequest):
    """Bulk branch status update payload."""

    status: BranchStatus


class BulkWarehouseStatusRequest(BulkIdsRequest):
    """Bulk warehouse status update payload."""

    status: WarehouseStatus
