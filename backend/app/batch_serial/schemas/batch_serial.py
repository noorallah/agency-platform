"""Validated contracts for enterprise batch, lot, serial number, and expiry APIs."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BatchStatus(StrEnum):
    """Supported batch lifecycle statuses."""

    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    BLOCKED = "BLOCKED"
    QUARANTINE = "QUARANTINE"
    EXPIRED = "EXPIRED"
    DAMAGED = "DAMAGED"
    RECALLED = "RECALLED"
    RETURNED = "RETURNED"
    DESTROYED = "DESTROYED"


class LotStatus(StrEnum):
    """Supported production lot statuses."""

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class LotType(StrEnum):
    """Supported production lot types."""

    PRODUCTION = "PRODUCTION"
    MIXING = "MIXING"
    MANUFACTURING = "MANUFACTURING"


class SerialStatus(StrEnum):
    """Supported serial number statuses."""

    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"
    INSTALLED = "INSTALLED"
    RETURNED = "RETURNED"
    REPAIRED = "REPAIRED"
    SCRAPPED = "SCRAPPED"
    LOST = "LOST"


class BatchSchema(BaseModel):
    """Apply strict validation and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class BatchCreate(BatchSchema):
    """Fields accepted when recording a batch."""

    product_id: UUID
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    vendor_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str = Field(min_length=1, max_length=100)
    supplier_batch: str | None = None
    internal_batch: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    best_before_date: date | None = None
    status: BatchStatus = BatchStatus.AVAILABLE
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    shelf_life_days: int | None = Field(default=None, ge=1)
    remarks: str | None = None


class BatchUpdate(BatchSchema):
    """Fields that may be changed on a batch."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    vendor_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    supplier_batch: str | None = None
    internal_batch: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    best_before_date: date | None = None
    status: BatchStatus | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    shelf_life_days: int | None = Field(default=None, ge=1)
    remarks: str | None = None


class BatchResponse(BatchSchema):
    """A batch as exposed by the API."""

    id: UUID
    firm_id: UUID
    product_id: UUID
    product_code: str | None = None
    product_name: str | None = None
    warehouse_id: UUID | None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    branch_id: UUID | None
    branch_code: str | None = None
    branch_name: str | None = None
    vendor_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str
    supplier_batch: str | None
    internal_batch: str | None
    manufacturing_date: date | None
    expiry_date: date | None
    best_before_date: date | None
    status: str
    quantity: Decimal
    available_quantity: Decimal
    reserved_quantity: Decimal
    blocked_quantity: Decimal
    damaged_quantity: Decimal
    quarantine_quantity: Decimal
    shelf_life_days: int | None
    remarks: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class BatchListFilters(BatchSchema):
    """Validated filters for batch listing."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    status: BatchStatus | None = None
    expiry_before: date | None = None
    expiry_after: date | None = None


class BatchSummary(BatchSchema):
    """Aggregate batch counts for the firm."""

    total_batches: int
    near_expiry: int
    expired: int
    quarantine: int


class ExpiryDashboard(BatchSchema):
    """Expiry counts across the reporting windows."""

    expired_today: int
    expire_in_7_days: int
    expire_in_30_days: int
    total_expired: int
    quarantine: int
    recalled: int


# ── Lot schemas ──────────────────────────────────────────────────────────────


class LotSchema(BaseModel):
    """Apply strict validation and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LotCreate(LotSchema):
    """Fields accepted when recording a lot."""

    product_id: UUID
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    parent_lot_id: UUID | None = None
    lot_number: str = Field(min_length=1, max_length=100)
    lot_type: LotType = LotType.PRODUCTION
    status: LotStatus = LotStatus.ACTIVE
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    production_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None


class LotUpdate(LotSchema):
    """Fields that may be changed on a lot."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    parent_lot_id: UUID | None = None
    lot_number: str | None = Field(default=None, min_length=1, max_length=100)
    lot_type: LotType | None = None
    status: LotStatus | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    production_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None


class LotResponse(LotSchema):
    """A production lot as exposed by the API."""

    id: UUID
    firm_id: UUID
    product_id: UUID
    warehouse_id: UUID | None
    branch_id: UUID | None
    parent_lot_id: UUID | None
    lot_number: str
    lot_type: str
    status: str
    quantity: Decimal
    available_quantity: Decimal
    production_date: date | None
    expiry_date: date | None
    remarks: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class LotListFilters(LotSchema):
    """Validated filters for lot listing."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    status: LotStatus | None = None
    lot_type: LotType | None = None


# ── Serial schemas ────────────────────────────────────────────────────────────


class SerialSchema(BaseModel):
    """Apply strict validation and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SerialCreate(SerialSchema):
    """Fields accepted when recording a serial number."""

    product_id: UUID
    inventory_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    batch_id: UUID | None = None
    serial_number: str = Field(min_length=1, max_length=200)
    status: SerialStatus = SerialStatus.AVAILABLE
    manufactured_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    current_owner: str | None = None
    asset_reference: str | None = None
    remarks: str | None = None


class SerialUpdate(SerialSchema):
    """Fields that may be changed on a serial number."""

    product_id: UUID | None = None
    inventory_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    batch_id: UUID | None = None
    serial_number: str | None = Field(default=None, min_length=1, max_length=200)
    status: SerialStatus | None = None
    manufactured_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    current_owner: str | None = None
    asset_reference: str | None = None
    remarks: str | None = None


class SerialResponse(SerialSchema):
    """A serial number as exposed by the API."""

    id: UUID
    firm_id: UUID
    product_id: UUID
    inventory_id: UUID | None
    warehouse_id: UUID | None
    branch_id: UUID | None
    batch_id: UUID | None
    serial_number: str
    status: str
    manufactured_date: date | None
    warranty_start: date | None
    warranty_end: date | None
    current_owner: str | None
    asset_reference: str | None
    remarks: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class SerialListFilters(SerialSchema):
    """Validated filters for serial number listing."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    batch_id: UUID | None = None
    status: SerialStatus | None = None
