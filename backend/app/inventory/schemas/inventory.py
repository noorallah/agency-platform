"""Validated contracts for enterprise inventory foundation APIs."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryStatus(StrEnum):
    """Supported inventory lifecycle statuses."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class InventoryTransactionType(StrEnum):
    """Supported immutable inventory movement types."""

    OPENING_STOCK = "OPENING_STOCK"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    GOODS_ISSUE = "GOODS_ISSUE"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    ADJUSTMENT = "ADJUSTMENT"
    PHYSICAL_COUNT = "PHYSICAL_COUNT"
    RESERVATION = "RESERVATION"
    RESERVATION_RELEASE = "RESERVATION_RELEASE"
    DAMAGE = "DAMAGE"
    EXPIRY = "EXPIRY"
    QUARANTINE = "QUARANTINE"
    RETURN = "RETURN"
    CORRECTION = "CORRECTION"


class OpeningStockStatus(StrEnum):
    """Supported opening-stock document states."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"


class InventorySchema(BaseModel):
    """Apply strict validation and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class InventoryWrite(InventorySchema):
    """Shared writable fields for inventory master configuration."""

    branch_id: UUID
    warehouse_id: UUID
    storage_node_id: UUID | None = None
    product_id: UUID
    minimum_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    maximum_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    reorder_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    safety_stock: Decimal | None = Field(default=None, ge=0, max_digits=18)
    status: InventoryStatus = InventoryStatus.ACTIVE

    @model_validator(mode="after")
    def validate_thresholds(self) -> "InventoryWrite":
        """Reject a maximum level below the minimum."""
        if (
            self.maximum_level is not None
            and self.minimum_level is not None
            and self.maximum_level < self.minimum_level
        ):
            raise ValueError(
                "Maximum level must be greater than or equal to minimum level."
            )
        if (
            self.reorder_level is not None
            and self.maximum_level is not None
            and self.reorder_level > self.maximum_level
        ):
            raise ValueError("Reorder level cannot exceed maximum level.")
        return self


class InventoryCreate(InventoryWrite):
    """Create one inventory master projection without changing stock."""


class InventoryUpdate(InventoryWrite):
    """Update one inventory master configuration."""


class InventoryResponse(InventorySchema):
    """Expose one inventory projection row."""

    id: UUID
    firm_id: UUID
    branch_id: UUID
    branch_code: str
    branch_name: str
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    storage_node_id: UUID | None
    storage_node_code: str | None = None
    storage_node_name: str | None = None
    product_id: UUID
    product_code: str
    product_name: str
    business_profile_id: UUID | None
    business_profile_code: str | None = None
    current_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    blocked_quantity: Decimal
    damaged_quantity: Decimal
    quarantine_quantity: Decimal
    in_transit_quantity: Decimal
    display_quantity: Decimal
    display_uom_id: UUID | None
    minimum_level: Decimal | None
    maximum_level: Decimal | None
    reorder_level: Decimal | None
    safety_stock: Decimal | None
    last_transaction_at: date | None
    status: InventoryStatus
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class InventorySummary(InventorySchema):
    """Aggregate summary for inventory search results."""

    total_records: int
    current_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    blocked_quantity: Decimal
    damaged_quantity: Decimal
    quarantine_quantity: Decimal
    in_transit_quantity: Decimal
    low_stock_count: int
    out_of_stock_count: int
    negative_stock_count: int


class InventoryLocationSummary(InventorySchema):
    """Aggregate stock summary grouped by firm, branch, or warehouse."""

    scope_id: UUID
    scope_code: str
    scope_name: str
    current_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    blocked_quantity: Decimal
    damaged_quantity: Decimal
    quarantine_quantity: Decimal
    in_transit_quantity: Decimal


class InventoryListFilters(InventorySchema):
    """Validated filters for inventory projection listing."""

    status: InventoryStatus | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    product_id: UUID | None = None
    business_profile_id: UUID | None = None
    low_stock_only: bool = False
    out_of_stock_only: bool = False
    negative_only: bool = False
    include_deleted: bool = False


class InventoryTransactionResponse(InventorySchema):
    """Expose one immutable inventory transaction."""

    id: UUID
    inventory_id: UUID
    firm_id: UUID
    branch_id: UUID
    branch_code: str
    branch_name: str
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    storage_node_id: UUID | None
    storage_node_code: str | None = None
    storage_node_name: str | None = None
    product_id: UUID
    product_code: str
    product_name: str
    business_profile_id: UUID | None
    # A recorded movement type, not a closed set. The ledger is an immutable
    # historical record: it already holds RESERVE, UNRESERVE and DISPATCH,
    # and reverse_transaction writes "<TYPE>_REVERSAL", which no enum can
    # enumerate. Validating history against InventoryTransactionType made both
    # the ledger and the transaction list fail with a 500 for any firm that had
    # reserved, dispatched or reversed stock. The enum still types the filters,
    # where a closed set is what a caller should be held to.
    transaction_type: str
    reference_number: str
    reference_type: str
    transaction_date: date
    quantity: Decimal
    current_quantity_delta: Decimal
    reserved_quantity_delta: Decimal
    blocked_quantity_delta: Decimal
    damaged_quantity_delta: Decimal
    quarantine_quantity_delta: Decimal
    in_transit_quantity_delta: Decimal
    previous_current_quantity: Decimal
    new_current_quantity: Decimal
    previous_reserved_quantity: Decimal
    new_reserved_quantity: Decimal
    previous_available_quantity: Decimal
    new_available_quantity: Decimal
    previous_blocked_quantity: Decimal
    new_blocked_quantity: Decimal
    previous_damaged_quantity: Decimal
    new_damaged_quantity: Decimal
    previous_quarantine_quantity: Decimal
    new_quarantine_quantity: Decimal
    previous_in_transit_quantity: Decimal
    new_in_transit_quantity: Decimal
    remarks: str | None
    entered_quantity: Decimal | None = None
    entered_uom_id: UUID | None = None
    conversion_version: int | None = None
    created_at: datetime


class InventoryTransactionListFilters(InventorySchema):
    """Validated filters for inventory transaction listing."""

    transaction_type: InventoryTransactionType | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    product_id: UUID | None = None
    reference_number: str | None = Field(default=None, max_length=80)
    reference_type: str | None = Field(default=None, max_length=40)
    transaction_from: date | None = None
    transaction_to: date | None = None


class StockLedgerResponse(InventoryTransactionResponse):
    """Expose one immutable stock-ledger row."""

    transaction_id: UUID


class StockLedgerListFilters(InventoryTransactionListFilters):
    """Validated filters for stock-ledger listing."""


class OpeningStockLineWrite(InventorySchema):
    """Shared opening-stock line payload."""

    product_id: UUID
    storage_node_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=18)
    entered_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18)
    entered_uom_id: UUID | None = None
    conversion_version: int | None = Field(default=None, ge=1)
    minimum_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    maximum_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    reorder_level: Decimal | None = Field(default=None, ge=0, max_digits=18)
    safety_stock: Decimal | None = Field(default=None, ge=0, max_digits=18)
    remarks: str | None = None


class OpeningStockLineCreate(OpeningStockLineWrite):
    """Create one opening-stock line."""


class OpeningStockLineResponse(InventorySchema):
    """Expose one opening-stock line."""

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    storage_node_id: UUID | None
    storage_node_code: str | None = None
    storage_node_name: str | None = None
    business_profile_id: UUID | None
    quantity: Decimal
    entered_quantity: Decimal | None = None
    entered_uom_id: UUID | None = None
    conversion_version: int | None = None
    minimum_level: Decimal | None
    maximum_level: Decimal | None
    reorder_level: Decimal | None
    safety_stock: Decimal | None
    remarks: str | None
    transaction_id: UUID | None


class OpeningStockBatchWrite(InventorySchema):
    """Shared opening-stock document payload."""

    branch_id: UUID
    warehouse_id: UUID
    reference_number: str = Field(min_length=2, max_length=80)
    posting_date: date
    remarks: str | None = None
    lines: list[OpeningStockLineCreate] = Field(default_factory=list, max_length=5000)


class OpeningStockBatchCreate(OpeningStockBatchWrite):
    """Create one opening-stock document."""


class OpeningStockUpdate(OpeningStockBatchWrite):
    """Replace one draft opening-stock document."""


class OpeningStockBatchResponse(InventorySchema):
    """Expose one opening-stock batch."""

    id: UUID
    firm_id: UUID
    branch_id: UUID
    branch_code: str
    branch_name: str
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    reference_number: str
    posting_date: date
    source_format: str
    status: OpeningStockStatus
    remarks: str | None
    posted_at: date | None
    lines: list[OpeningStockLineResponse]
    created_at: datetime
    updated_at: datetime


class OpeningStockBatchListFilters(InventorySchema):
    """Validated filters for opening-stock batch listing."""

    status: OpeningStockStatus | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    posting_from: date | None = None
    posting_to: date | None = None
    include_deleted: bool = False


class OpeningStockImportRequest(InventorySchema):
    """JSON import payload for opening stock."""

    reference_number: str = Field(min_length=2, max_length=80)
    posting_date: date
    branch_id: UUID
    warehouse_id: UUID
    remarks: str | None = None
    auto_post: bool = True
    lines: list[OpeningStockLineCreate] = Field(min_length=1, max_length=5000)


class InventoryAdjustmentCreate(InventorySchema):
    """Create one inventory adjustment transaction."""

    branch_id: UUID
    warehouse_id: UUID
    storage_node_id: UUID | None = None
    product_id: UUID
    quantity: Decimal = Field(max_digits=18)
    entered_quantity: Decimal | None = Field(default=None, max_digits=18)
    entered_uom_id: UUID | None = None
    reference_number: str = Field(min_length=2, max_length=80)
    reference_type: str = Field(default="ADJUSTMENT", min_length=2, max_length=40)
    transaction_date: date
    remarks: str | None = None

    @model_validator(mode="after")
    def validate_quantity(self) -> "InventoryAdjustmentCreate":
        """Reject an adjustment that moves nothing."""
        if self.quantity == 0:
            raise ValueError("Adjustment quantity cannot be zero.")
        return self
