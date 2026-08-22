"""Validated contracts for delivery notes."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryNoteSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DeliveryNoteStatus(StrEnum):
    """Supported delivery note lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class DeliveryNoteAttachmentWrite(DeliveryNoteSchema):
    """Carry one delivery note attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="DELIVERY_NOTE_FILE", min_length=1, max_length=40
    )


class DeliveryNoteNoteWrite(DeliveryNoteSchema):
    """Carry one delivery note note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class DeliveryNoteLineWrite(DeliveryNoteSchema):
    """Carry one delivery note line into a request."""

    sales_order_line_id: UUID
    line_number: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)
    current_delivery_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    damaged_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    #: None means the caller said nothing, so the customer's standing
    #: discount applies. Zero means they said no discount.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    sales_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    serial_numbers: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None


class DeliveryNoteCreate(DeliveryNoteSchema):
    """Create one delivery note."""

    sales_order_id: UUID
    delivery_date: date
    vehicle: str | None = Field(default=None, max_length=120)
    driver: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_over_delivery: bool = False
    over_delivery_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    delivery_note_number: str | None = Field(default=None, max_length=60)
    lines: list[DeliveryNoteLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[DeliveryNoteAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[DeliveryNoteNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("delivery_note_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class DeliveryNoteUpdate(DeliveryNoteCreate):
    """Replace one delivery note."""

    pass


class DeliveryNoteImportRequest(DeliveryNoteSchema):
    """Import a validated batch of delivery notes."""

    records: list[DeliveryNoteCreate] = Field(min_length=1, max_length=500)


class DeliveryNoteAttachmentResponse(DeliveryNoteSchema):
    """Return one delivery note attachment."""

    id: UUID
    delivery_note_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class DeliveryNoteNoteResponse(DeliveryNoteSchema):
    """Return one delivery note note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class DeliveryNoteLineResponse(DeliveryNoteSchema):
    """Return one delivery note line."""

    id: UUID
    delivery_note_id: UUID
    line_number: int
    sales_order_line_id: UUID
    product_id: UUID
    description: str | None
    ordered_quantity: Decimal
    reserved_quantity: Decimal
    previously_delivered_quantity: Decimal
    current_delivery_quantity: Decimal
    free_quantity: Decimal
    delivered_quantity: Decimal
    remaining_quantity: Decimal
    damaged_quantity: Decimal
    short_shipment_quantity: Decimal
    sales_uom_id: UUID | None
    inventory_uom_id: UUID | None
    packaging_type_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str | None
    serial_numbers: str | None
    manufacturing_date: date | None
    expiry_date: date | None
    released_reservation_transaction_id: UUID | None
    inventory_transaction_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class DeliveryNoteResponse(DeliveryNoteSchema):
    """Return one delivery note."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    sales_order_id: UUID
    customer_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None
    salesman_id: UUID | None
    territory_id: UUID | None
    route_id: UUID | None
    delivery_note_number: str
    delivery_date: date
    sales_order_reference: str
    vehicle: str | None
    driver: str | None
    remarks: str | None
    allow_over_delivery: bool
    over_delivery_percent: Decimal
    status: DeliveryNoteStatus
    total_ordered_quantity: Decimal
    total_previously_delivered_quantity: Decimal
    total_current_delivery_quantity: Decimal
    total_free_quantity: Decimal
    #: The customer's standing discount on the day this was raised.
    customer_discount_percent: Decimal
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    approved_at: datetime | None
    dispatched_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[DeliveryNoteLineResponse] = Field(default_factory=list)
    attachments: list[DeliveryNoteAttachmentResponse] = Field(default_factory=list)
    notes: list[DeliveryNoteNoteResponse] = Field(default_factory=list)
    duplicate_warning: str | None = None


class DeliveryNoteListFilters(DeliveryNoteSchema):
    """Narrow a delivery note list to the rows a caller asked for."""

    sales_order_id: UUID | None = None
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    status: DeliveryNoteStatus | None = None
    delivery_from: date | None = None
    delivery_to: date | None = None
    include_deleted: bool = False


class DeliveryNoteSummary(DeliveryNoteSchema):
    """Aggregate delivery note counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    dispatched: int
    completed: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_orders: int
    partial_orders: int


class DeliveryNoteRegisterRecord(DeliveryNoteSchema):
    """One row of the delivery note register report."""

    delivery_note_id: UUID
    delivery_note_number: str
    delivery_date: date
    sales_order_id: UUID
    sales_order_number: str
    customer_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    status: DeliveryNoteStatus
    grand_total: Decimal


class DeliveryNoteByDimensionRecord(DeliveryNoteSchema):
    """One row of the delivery note by dimension report."""

    dimension_id: UUID | None
    dimension_name: str
    note_count: int
    delivered_quantity: Decimal
    total_value: Decimal


class DeliveryNoteOrderProgressRecord(DeliveryNoteSchema):
    """One row of the delivery note order progress report."""

    sales_order_id: UUID
    sales_order_number: str
    ordered_quantity: Decimal
    delivered_quantity: Decimal
    pending_quantity: Decimal
    status: str
