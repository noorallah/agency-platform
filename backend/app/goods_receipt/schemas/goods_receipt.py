"""Validated contracts for goods receipt notes."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoodsReceiptSchema(BaseModel):
    """Goods Receipt Schema contract."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class GoodsReceiptStatus(StrEnum):
    """Goods Receipt Status contract."""

    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class GoodsReceiptNoteType(StrEnum):
    """Goods Receipt Note Type contract."""

    INTERNAL = "INTERNAL"
    VENDOR = "VENDOR"
    SYSTEM = "SYSTEM"


class GoodsReceiptAttachmentWrite(GoodsReceiptSchema):
    """Goods Receipt Attachment Write contract."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(default="GRN_FILE", min_length=1, max_length=40)


class GoodsReceiptNoteWrite(GoodsReceiptSchema):
    """Goods Receipt Note Write contract."""

    note_type: GoodsReceiptNoteType = GoodsReceiptNoteType.INTERNAL
    note: str = Field(min_length=1)


class GoodsReceiptLineWrite(GoodsReceiptSchema):
    """Goods Receipt Line Write contract."""

    purchase_order_line_id: UUID
    line_number: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)
    current_receipt_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    damaged_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None


class GoodsReceiptCreate(GoodsReceiptSchema):
    """Goods Receipt Create contract."""

    purchase_order_id: UUID
    receipt_date: date
    received_by_id: UUID | None = None
    transport_details: str | None = Field(default=None, max_length=250)
    vehicle_number: str | None = Field(default=None, max_length=80)
    invoice_reference: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_over_receipt: bool = False
    over_receipt_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    lines: list[GoodsReceiptLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[GoodsReceiptAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[GoodsReceiptNoteWrite] = Field(default_factory=list, max_length=500)
    grn_number: str | None = Field(default=None, max_length=60)

    @field_validator("grn_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        """Uppercase and trim the document number."""
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class GoodsReceiptUpdate(GoodsReceiptCreate):
    """Goods Receipt Update contract."""

    pass


class GoodsReceiptImportRequest(GoodsReceiptSchema):
    """Goods Receipt Import Request contract."""

    records: list[GoodsReceiptCreate] = Field(min_length=1, max_length=500)


class GoodsReceiptAttachmentResponse(GoodsReceiptSchema):
    """Goods Receipt Attachment Response contract."""

    id: UUID
    goods_receipt_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class GoodsReceiptNoteResponse(GoodsReceiptSchema):
    """Goods Receipt Note Response contract."""

    id: UUID
    note_type: GoodsReceiptNoteType
    note: str
    created_at: datetime
    updated_at: datetime


class GoodsReceiptLineResponse(GoodsReceiptSchema):
    """Goods Receipt Line Response contract."""

    id: UUID
    goods_receipt_id: UUID
    line_number: int
    purchase_order_line_id: UUID
    purchase_order_line_number: int
    product_id: UUID
    ordered_quantity: Decimal
    previously_received_quantity: Decimal
    current_receipt_quantity: Decimal
    accepted_quantity: Decimal
    unit_price: Decimal
    description: str | None
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    rejected_quantity: Decimal
    damaged_quantity: Decimal
    free_quantity: Decimal
    packaging_type_id: UUID | None
    purchase_uom_id: UUID | None
    inventory_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    warehouse_id: UUID
    storage_node_id: UUID | None
    batch_number: str | None
    expiry_date: date | None
    manufacturing_date: date | None
    inventory_transaction_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class GoodsReceiptResponse(GoodsReceiptSchema):
    """Goods Receipt Response contract."""

    id: UUID
    #: The optimistic-concurrency version, published so a client can send
    #: it back as ``If-Match``. It rides in the body as well as the ETag
    #: header because a list carries many records and a header carries
    #: one — and this desktop edits from list rows.
    version: int
    firm_id: UUID
    purchase_order_id: UUID
    purchase_order_number: str
    vendor_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    received_by_id: UUID | None
    grn_number: str
    receipt_date: date
    transport_details: str | None
    vehicle_number: str | None
    invoice_reference: str | None
    remarks: str | None
    allow_over_receipt: bool
    over_receipt_percent: Decimal
    status: GoodsReceiptStatus
    total_ordered_quantity: Decimal
    total_previous_received_quantity: Decimal
    total_current_receipt_quantity: Decimal
    total_accepted_quantity: Decimal
    total_rejected_quantity: Decimal
    total_damaged_quantity: Decimal
    total_free_quantity: Decimal
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    completed_at: datetime | None
    closed_reason: str | None
    cancel_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[GoodsReceiptLineResponse] = Field(default_factory=list)
    attachments: list[GoodsReceiptAttachmentResponse] = Field(default_factory=list)
    notes: list[GoodsReceiptNoteResponse] = Field(default_factory=list)
    duplicate_warning: str | None = None


class GoodsReceiptListFilters(GoodsReceiptSchema):
    """Goods Receipt List Filters contract."""

    purchase_order_id: UUID | None = None
    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    status: GoodsReceiptStatus | None = None
    created_from: date | None = None
    created_to: date | None = None
    include_deleted: bool = False


class GoodsReceiptSummary(GoodsReceiptSchema):
    """Goods Receipt Summary contract."""

    total: int
    draft: int
    completed: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_purchase_orders: int
    partial_purchase_orders: int


class GoodsReceiptPurchaseOrderReport(GoodsReceiptSchema):
    """Goods Receipt Purchase Order Report contract."""

    purchase_order_id: UUID
    purchase_order_number: str
    vendor_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    ordered_quantity: Decimal
    received_quantity: Decimal
    pending_quantity: Decimal
    receipt_count: int
    status: str
