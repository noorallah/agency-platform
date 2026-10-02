"""Validated contracts for enterprise batch, lot, serial number, and expiry APIs."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
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
    shelf_life_days: int | None = Field(default=None, ge=1)
    #: Per stock unit: MRP with tax, selling price before it (79 row 7).
    mrp: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    selling_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
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
    shelf_life_days: int | None = Field(default=None, ge=1)
    #: Per stock unit: MRP with tax, selling price before it (79 row 7).
    mrp: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    selling_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
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
    #: What the batch is holding, summed from `inventories` by
    #: ``BatchSerialService.batch_responses``. The batch itself stores none of
    #: these -- it is a register entry, and how much of it is on the shelf is a
    #: consequence of the movements that put it there. They default to zero so
    #: the response can be validated from a record that has no such columns;
    #: every endpoint fills them through the builder.
    quantity: Decimal = Decimal("0")
    available_quantity: Decimal = Decimal("0")
    reserved_quantity: Decimal = Decimal("0")
    blocked_quantity: Decimal = Decimal("0")
    damaged_quantity: Decimal = Decimal("0")
    quarantine_quantity: Decimal = Decimal("0")
    shelf_life_days: int | None
    mrp: Decimal | None = None
    selling_price: Decimal | None = None
    remarks: str | None
    is_deleted: bool
    #: Optimistic-concurrency counter, echoed back as ``If-Match``.
    version: int
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


class BatchAvailability(BatchSchema):
    """One batch of a product in one warehouse, as a batch picker shows it (79).

    Quantities are stock units. ``available`` is on hand less every order's
    hold; ``available_to_line`` adds back what the asking order line holds
    itself, because dispatch lets that hold go before it draws. ``fefo`` is
    what dispatch would take with nobody choosing -- the picker's pre-fill.
    """

    batch_id: UUID
    batch_number: str
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    days_to_expiry: int | None = None
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    available_to_line: Decimal
    expired: bool
    near_expiry: bool
    fefo: Decimal = Decimal("0")
    #: Expires before the customer's minimum shelf life asks the goods to
    #: last (backlog 79 row 6): never pre-filled.
    short_for_customer: bool = False
    #: The batch's own MRP and rate, per stock unit, where it carries them
    #: (backlog 79 row 7): shown in the picker, and the rate a line takes
    #: where the firm prices from the batch.
    mrp: Decimal | None = None
    selling_price: Decimal | None = None


NearExpiryPolicy = Literal["WARN", "REASON"]
FefoSkipPolicy = Literal["RECORD", "REASON"]
ShelfLifePolicy = Literal["WARN", "BLOCK"]


class BatchSaleSettingsWrite(BatchSchema):
    """Replace the firm's batch-sale rules (backlog 79 row 6). All sent."""

    near_expiry_days: int = Field(ge=0, le=730)
    near_expiry_policy: NearExpiryPolicy
    fefo_skip_policy: FefoSkipPolicy
    near_expiry_below_floor: bool
    #: A hand-chosen batch short of the customer's minimum shelf life.
    shelf_life_policy: ShelfLifePolicy = "BLOCK"
    #: A line whose batch is chosen takes the batch's selling price as its
    #: rate, before the price list (backlog 79 row 7). Off by default.
    price_from_batch: bool = False
    #: A customer return goes to quarantine until checked (STK-13). Off by
    #: default.
    hold_returns_for_check: bool = False


class BatchSaleSettingsResponse(BatchSaleSettingsWrite):
    """The firm's rules, and whether the firm actually chose them."""

    is_configured: bool


class DispatchBatchFinding(BatchSchema):
    """One line of a delivery note whose batches a rule has something to say on."""

    line_number: int
    #: NEAR_EXPIRY, FEFO_SKIP or SHORT_SHELF_LIFE.
    kind: Literal["NEAR_EXPIRY", "FEFO_SKIP", "SHORT_SHELF_LIFE"]
    message: str


class DispatchBatchCheck(BatchSchema):
    """What dispatching a note would meet under the firm's batch rules (79)."""

    findings: list[DispatchBatchFinding]
    #: True when a finding's rule is REASON: dispatch needs ``batch_reason``.
    needs_reason: bool
    message: str | None
    #: True when dispatch will be refused whatever reason is given: a batch
    #: short of the customer's minimum shelf life under BLOCK.
    would_block: bool = False


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
    #: Optimistic-concurrency counter, echoed back as ``If-Match``.
    version: int
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
    #: Optimistic-concurrency counter, echoed back as ``If-Match``.
    version: int
    created_at: datetime
    updated_at: datetime


class SerialListFilters(SerialSchema):
    """Validated filters for serial number listing."""

    product_id: UUID | None = None
    warehouse_id: UUID | None = None
    branch_id: UUID | None = None
    batch_id: UUID | None = None
    status: SerialStatus | None = None


class PickedSerial(SerialSchema):
    """One serialised unit a document line names, as a line shows it."""

    serial_id: UUID
    serial_number: str
    #: Where the unit is now, which is not necessarily what this line did to
    #: it: a unit dispatched on a note and since returned reads AVAILABLE.
    status: str


class ReturnableSerials(SerialSchema):
    """The units a return line may name, for the picker on the return."""

    product_id: UUID
    #: False for a product nobody tracks by serial: the line names none.
    serial_tracked: bool
    serials: list[PickedSerial]
