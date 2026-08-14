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
    """The movement types the service writes.

    This is the vocabulary, not a wish list. It previously declared fourteen
    members of which six were written and three of the written ones were
    absent: the service recorded RESERVE, UNRESERVE and DISPATCH while the enum
    offered RESERVATION, RESERVATION_RELEASE, GOODS_ISSUE, TRANSFER_IN,
    TRANSFER_OUT, PHYSICAL_COUNT, DAMAGE, EXPIRY, QUARANTINE and CORRECTION --
    none of which anything ever emitted. Filtering the transaction list by
    RESERVE was rejected as invalid, and filtering by RESERVATION was accepted
    and matched nothing.

    Physical counts and damage write-offs are still not built, and are named in
    ``docs/INVENTORY_FRAMEWORK.md`` as absent rather than here, where naming
    them would make the API advertise them. `TRANSFER_OUT` and `TRANSFER_IN`
    were in that category until warehouse transfers were built.
    """

    OPENING_STOCK = "OPENING_STOCK"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    SALES_RETURN = "SALES_RETURN"
    RESERVE = "RESERVE"
    UNRESERVE = "UNRESERVE"
    DISPATCH = "DISPATCH"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    WRITE_OFF = "WRITE_OFF"
    QUARANTINE_HOLD = "QUARANTINE_HOLD"
    QUARANTINE_RELEASE = "QUARANTINE_RELEASE"


#: Appended by ``reverse_transaction`` to the type it reverses.
#:
#: The stored vocabulary is therefore open-ended: a reversal is
#: "DISPATCH_REVERSAL", and reversing *that* is legal -- the service only
#: refuses to reverse the same row twice -- so no closed set can enumerate what
#: the column holds. Filters and responses both take a plain string for that
#: reason.
REVERSAL_SUFFIX = "_REVERSAL"


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
    #: The batch this row holds, or null where the product is not tracked.
    #: A stock row has been identified by its batch since the grain changed,
    #: and the list endpoint returns the individual rows precisely because
    #: which batch stock is in is the reason it changed -- but it could not say
    #: which, so two rows of one product in one bay were indistinguishable.
    #: The number and expiry travel with it because every caller that wants the
    #: batch wants to show it, and expiry is what decides which goes first.
    batch_id: UUID | None = None
    batch_number: str | None = None
    batch_expiry_date: date | None = None
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


class BatchStockTotals(InventorySchema):
    """What one batch is actually holding, summed from the stock rows.

    A batch is held per location, so its total is a sum across however many
    `inventories` rows carry it. ``batches`` used to keep its own copy of these
    six numbers, maintained by the batch API and reconciled against the stock
    projection by nothing; this is the derived answer that replaced them.
    """

    current_quantity: Decimal = Decimal("0")
    available_quantity: Decimal = Decimal("0")
    reserved_quantity: Decimal = Decimal("0")
    blocked_quantity: Decimal = Decimal("0")
    damaged_quantity: Decimal = Decimal("0")
    quarantine_quantity: Decimal = Decimal("0")


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
    #: The batch this movement moved, or null where the stock is untracked.
    #: The ledger has recorded it since the grain changed -- that is what makes
    #: batch cost and a recall answerable -- but no response carried it, so the
    #: question could only be asked in SQL.
    batch_id: UUID | None = None
    batch_number: str | None = None
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

    # A stored value, not a closed set -- see REVERSAL_SUFFIX. This was typed
    # as the enum, which rejected RESERVE, UNRESERVE and DISPATCH outright and
    # accepted names no row has ever carried. A caller filtering for something
    # unwritten gets an empty page, which is the truthful answer.
    transaction_type: str | None = Field(default=None, max_length=40)
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
    #: What the stock was worth per unit on day one. Optional, because a firm
    #: that does not know is better served recording the quantity than nothing
    #: -- but stock entered without it is worth nothing, in the valuation and
    #: in the ledger alike, and nothing posts.
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=18)
    entered_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18)
    entered_uom_id: UUID | None = None
    conversion_version: int | None = Field(default=None, ge=1)
    #: The batch this day-one stock is in, read off the carton the same way a
    #: goods receipt reads it. Opening stock is stock arriving, so an unknown
    #: number registers the batch rather than being refused.
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
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
    batch_number: str | None = None
    batch_id: UUID | None = None
    expiry_date: date | None = None
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


class WriteOffReason(StrEnum):
    """Why stock stopped being stock.

    A generic `ADJUSTMENT` reached all of these buckets, so "we lost 40,000 of
    stock this year" was answerable and "to what" was not. The reason is on the
    movement and on the journal narration, which is where somebody reading the
    ledger asks it.
    """

    DAMAGE = "DAMAGE"
    EXPIRY = "EXPIRY"
    LOSS = "LOSS"


class StockWriteOffCreate(InventorySchema):
    """Take stock off the books, and say why."""

    branch_id: UUID
    warehouse_id: UUID
    storage_node_id: UUID | None = None
    product_id: UUID
    batch_id: UUID | None = None
    reason: WriteOffReason
    quantity: Decimal = Field(gt=0, max_digits=18)
    entered_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18)
    entered_uom_id: UUID | None = None
    reference_number: str = Field(min_length=2, max_length=80)
    transaction_date: date
    remarks: str | None = None


class QuarantineAction(StrEnum):
    """Whether stock is being held back or let go."""

    HOLD = "HOLD"
    RELEASE = "RELEASE"


class StockQuarantineCreate(InventorySchema):
    """Hold stock back from sale, or release it again.

    Quarantined stock is still owned and still worth what it was, so this moves
    quantity between buckets and **posts nothing**. Writing it off is a
    different decision, taken later and separately, once somebody has looked at
    the goods.
    """

    branch_id: UUID
    warehouse_id: UUID
    storage_node_id: UUID | None = None
    product_id: UUID
    batch_id: UUID | None = None
    action: QuarantineAction
    quantity: Decimal = Field(gt=0, max_digits=18)
    reference_number: str = Field(min_length=2, max_length=80)
    transaction_date: date
    remarks: str | None = None


class StockTransferCreate(InventorySchema):
    """Move stock from one warehouse to another.

    The firm still owns the same goods at the same value afterwards, so a
    transfer writes two stock movements and **no journal**: there is one
    inventory control account, and debiting and crediting it for the same
    amount would be noise in the ledger rather than information.
    """

    branch_id: UUID
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    from_storage_node_id: UUID | None = None
    to_storage_node_id: UUID | None = None
    product_id: UUID
    #: Carried across so a batch stays traceable through the move, which is the
    #: whole point of batch tracking for anyone who has to answer a recall.
    batch_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=18)
    entered_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18)
    entered_uom_id: UUID | None = None
    reference_number: str = Field(min_length=2, max_length=80)
    transaction_date: date
    remarks: str | None = None

    @model_validator(mode="after")
    def _somewhere_else(self) -> "StockTransferCreate":
        """Refuse a transfer that goes nowhere."""
        same_warehouse = self.from_warehouse_id == self.to_warehouse_id
        same_node = self.from_storage_node_id == self.to_storage_node_id
        if same_warehouse and same_node:
            raise ValueError(
                "A transfer must move stock somewhere else than where it is."
            )
        return self


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


class PhysicalCountLineWrite(InventorySchema):
    """Carry one counted line into a request."""

    product_id: UUID
    batch_id: UUID | None = None
    #: What was on the shelf. Left out for a line nobody has walked yet, which
    #: is how a half-finished sheet is told apart from one that found nothing.
    counted_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18)
    remarks: str | None = None


class PhysicalCountCreate(InventorySchema):
    """Open a count sheet for one warehouse."""

    branch_id: UUID
    warehouse_id: UUID
    count_date: date
    reference_number: str | None = Field(default=None, max_length=60)
    remarks: str | None = None
    #: Left empty to draw the sheet up from what the warehouse currently holds,
    #: which is what a counter walks out with. Naming lines explicitly is for
    #: counting part of a warehouse.
    lines: list[PhysicalCountLineWrite] = Field(default_factory=list)


class PhysicalCountUpdate(InventorySchema):
    """Replace the counted quantities on a draft sheet."""

    lines: list[PhysicalCountLineWrite] = Field(min_length=1, max_length=2000)
    remarks: str | None = None


class PhysicalCountLineResponse(InventorySchema):
    """Return one line of a count sheet."""

    id: UUID
    line_number: int
    product_id: UUID
    batch_id: UUID | None
    expected_quantity: Decimal
    counted_quantity: Decimal | None
    variance_quantity: Decimal | None
    transaction_id: UUID | None
    remarks: str | None


class PhysicalCountResponse(InventorySchema):
    """Return one count sheet."""

    id: UUID
    branch_id: UUID
    warehouse_id: UUID
    count_number: str
    count_date: date
    status: str
    remarks: str | None
    posted_at: datetime | None
    lines: list[PhysicalCountLineResponse]
    version: int
