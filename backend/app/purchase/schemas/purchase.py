"""Validated API contracts for enterprise purchase management."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseSchema(BaseModel):
    """Purchase Schema contract."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PurchaseOrderStatus(StrEnum):
    """Purchase Order Status contract."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PARTIALLY_ORDERED = "PARTIALLY_ORDERED"
    ORDERED = "ORDERED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class PurchaseType(StrEnum):
    """Purchase Type contract."""

    STANDARD_PURCHASE = "STANDARD_PURCHASE"
    LOCAL_PURCHASE = "LOCAL_PURCHASE"
    IMPORT_PURCHASE = "IMPORT_PURCHASE"
    CONSIGNMENT = "CONSIGNMENT"
    INTER_BRANCH = "INTER_BRANCH"
    INTER_COMPANY = "INTER_COMPANY"
    CAPITAL_GOODS = "CAPITAL_GOODS"
    SERVICES = "SERVICES"


class PurchaseNoteType(StrEnum):
    """Purchase Note Type contract."""

    INTERNAL = "INTERNAL"
    VENDOR = "VENDOR"
    SYSTEM = "SYSTEM"


class PurchaseLineWrite(PurchaseSchema):
    """Purchase Line Write contract."""

    product_id: UUID
    description: str | None = Field(default=None, max_length=500)
    vendor_product_code: str | None = Field(default=None, max_length=120)
    purchase_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    ordered_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    batch_required: bool = False
    expiry_required: bool = False
    serial_required: bool = False
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    remarks: str | None = None


class PurchaseDeliveryScheduleWrite(PurchaseSchema):
    """Purchase Delivery Schedule Write contract."""

    line_number: int = Field(ge=1, le=100000)
    delivery_date: date
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    remarks: str | None = None


class PurchaseAttachmentWrite(PurchaseSchema):
    """Purchase Attachment Write contract."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(default="PURCHASE_FILE", min_length=1, max_length=40)


class PurchaseNoteWrite(PurchaseSchema):
    """Purchase Note Write contract."""

    note_type: PurchaseNoteType = PurchaseNoteType.INTERNAL
    note: str = Field(min_length=1)


class PurchaseOrderWrite(PurchaseSchema):
    """Purchase Order Write contract."""

    branch_id: UUID
    warehouse_id: UUID
    vendor_id: UUID
    buyer_id: UUID | None = None
    tax_profile_id: UUID | None = None
    vendor_contact: str | None = Field(default=None, max_length=200)
    vendor_address: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=120)
    purchase_type: PurchaseType = PurchaseType.STANDARD_PURCHASE
    purchase_category: str | None = Field(default=None, max_length=120)
    purchase_date: date
    expected_delivery_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    reference_number: str | None = Field(default=None, max_length=80)
    external_reference: str | None = Field(default=None, max_length=80)
    priority: str = Field(default="NORMAL", max_length=20)
    remarks: str | None = None
    status: PurchaseOrderStatus = PurchaseOrderStatus.DRAFT
    header_discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    lines: list[PurchaseLineWrite] = Field(min_length=1, max_length=1000)
    delivery_schedules: list[PurchaseDeliveryScheduleWrite] = Field(
        default_factory=list, max_length=2000
    )
    attachments: list[PurchaseAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[PurchaseNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("purchase_type", mode="before")
    @classmethod
    def normalize_type(cls, value: str | PurchaseType) -> str | PurchaseType:
        """Normalize type."""
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: str) -> str:
        """Normalize priority."""
        return value.strip().upper()


class PurchaseOrderCreate(PurchaseOrderWrite):
    """Purchase Order Create contract."""

    po_number: str | None = Field(default=None, max_length=60)


class PurchaseOrderUpdate(PurchaseOrderWrite):
    """Purchase Order Update contract."""

    pass


class PurchaseOrderImportRequest(PurchaseSchema):
    """Purchase Order Import Request contract."""

    records: list[PurchaseOrderCreate] = Field(min_length=1, max_length=500)


class PurchaseOrderLineResponse(PurchaseSchema):
    """Purchase Order Line Response contract."""

    id: UUID
    purchase_order_id: UUID
    line_number: int
    product_id: UUID
    description: str | None
    vendor_product_code: str | None
    purchase_uom_id: UUID | None
    inventory_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    ordered_quantity: Decimal
    free_quantity: Decimal
    base_quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    batch_required: bool
    expiry_required: bool
    serial_required: bool
    manufacturing_date: date | None
    expiry_date: date | None
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    remarks: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class PurchaseDeliveryScheduleResponse(PurchaseSchema):
    """Purchase Delivery Schedule Response contract."""

    id: UUID
    purchase_order_line_id: UUID
    line_number: int
    delivery_date: date
    quantity: Decimal
    status: str
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseAttachmentResponse(PurchaseSchema):
    """Purchase Attachment Response contract."""

    id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class PurchaseNoteResponse(PurchaseSchema):
    """Purchase Note Response contract."""

    id: UUID
    note_type: PurchaseNoteType
    note: str
    created_at: datetime
    updated_at: datetime


class PurchaseOrderHistoryResponse(PurchaseSchema):
    """Purchase Order History Response contract."""

    id: UUID
    action: str
    from_status: str | None
    to_status: str | None
    remarks: str | None
    details_json: str | None
    created_by: UUID | None
    created_at: datetime


class PurchaseOrderResponse(PurchaseSchema):
    """Purchase Order Response contract."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    vendor_id: UUID
    buyer_id: UUID | None
    tax_profile_id: UUID | None
    po_number: str
    vendor_contact: str | None
    vendor_address: str | None
    department: str | None
    purchase_type: PurchaseType
    purchase_category: str | None
    purchase_date: date
    expected_delivery_date: date | None
    payment_terms: str | None
    delivery_terms: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    reference_number: str | None
    external_reference: str | None
    priority: str
    remarks: str | None
    status: PurchaseOrderStatus
    subtotal: Decimal
    line_discount_total: Decimal
    header_discount_amount: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    close_reason: str | None
    cancel_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseOrderLineResponse] = Field(default_factory=list)
    delivery_schedules: list[PurchaseDeliveryScheduleResponse] = Field(
        default_factory=list
    )
    attachments: list[PurchaseAttachmentResponse] = Field(default_factory=list)
    notes: list[PurchaseNoteResponse] = Field(default_factory=list)


class PurchaseOrderListFilters(PurchaseSchema):
    """Purchase Order List Filters contract."""

    vendor_id: UUID | None = None
    status: PurchaseOrderStatus | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    buyer_id: UUID | None = None
    purchase_type: PurchaseType | None = None
    created_from: date | None = None
    created_to: date | None = None
    include_deleted: bool = False


class PurchaseSummary(PurchaseSchema):
    """Purchase Summary contract."""

    total: int
    draft: int
    open: int
    cancelled: int
    closed: int
    total_value: Decimal
    overdue_delivery: int
