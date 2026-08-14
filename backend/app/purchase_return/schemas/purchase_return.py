"""Validated contracts for purchase returns."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseReturnSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PurchaseReturnStatus(StrEnum):
    """Supported purchase return lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class PurchaseReturnSourceType(StrEnum):
    """Documents a purchase return can be raised from."""

    GOODS_RECEIPT = "GOODS_RECEIPT"
    PURCHASE_INVOICE = "PURCHASE_INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    MANUAL = "MANUAL"


class PurchaseReturnAccountingEventType(StrEnum):
    """Accounting events a purchase return can raise."""

    PURCHASE_RETURN = "PURCHASE_RETURN"
    INPUT_TAX_REVERSAL = "INPUT_TAX_REVERSAL"
    VENDOR_RECEIVABLE = "VENDOR_RECEIVABLE"


class PurchaseReturnAttachmentWrite(PurchaseReturnSchema):
    """Carry one purchase return attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="PURCHASE_RETURN_FILE", min_length=1, max_length=40
    )


class PurchaseReturnNoteWrite(PurchaseReturnSchema):
    """Carry one purchase return note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class PurchaseReturnSourceWrite(PurchaseReturnSchema):
    """Carry one purchase return source into a request."""

    source_document_type: PurchaseReturnSourceType
    source_document_id: UUID


class PurchaseReturnLineWrite(PurchaseReturnSchema):
    """Carry one purchase return line into a request."""

    source_document_type: PurchaseReturnSourceType
    source_document_id: UUID
    source_document_line_id: UUID
    line_number: int = Field(ge=1)
    current_return_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    reason_code: str | None = Field(default=None, max_length=80)
    item_condition: str | None = Field(default=None, max_length=80)
    replacement_required: bool = False
    refund_required: bool = False
    is_scrap: bool = False
    is_damaged: bool = False
    is_expired: bool = False
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    charges_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    return_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None


class PurchaseReturnCreate(PurchaseReturnSchema):
    """Create one purchase return."""

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    warehouse_id: UUID
    return_date: date
    supplier_return_number: str | None = Field(default=None, max_length=120)
    supplier_return_date: date | None = None
    reference_grn_number: str | None = Field(default=None, max_length=80)
    reference_invoice_number: str | None = Field(default=None, max_length=80)
    return_reason: str | None = Field(default=None, max_length=80)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    payment_terms: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_direct_purchase_order: bool = False
    allow_over_return: bool = False
    over_return_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    return_number: str | None = Field(default=None, max_length=60)
    source_documents: list[PurchaseReturnSourceWrite] = Field(
        default_factory=list, max_length=100
    )
    lines: list[PurchaseReturnLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[PurchaseReturnAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[PurchaseReturnNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("return_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class PurchaseReturnUpdate(PurchaseReturnCreate):
    """Replace one purchase return."""

    pass


class PurchaseReturnImportRequest(PurchaseReturnSchema):
    """Import a validated batch of purchase returns."""

    records: list[PurchaseReturnCreate] = Field(min_length=1, max_length=500)


class PurchaseReturnAttachmentResponse(PurchaseReturnSchema):
    """Return one purchase return attachment."""

    id: UUID
    purchase_return_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class PurchaseReturnNoteResponse(PurchaseReturnSchema):
    """Return one purchase return note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class PurchaseReturnSourceResponse(PurchaseReturnSchema):
    """Return one purchase return source."""

    id: UUID
    source_document_type: PurchaseReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_date: date
    vendor_id: UUID
    branch_id: UUID
    created_at: datetime
    updated_at: datetime


class PurchaseReturnAccountingEventResponse(PurchaseReturnSchema):
    """Return one purchase return accounting event."""

    id: UUID
    event_type: PurchaseReturnAccountingEventType
    account_name: str
    direction: str
    amount: Decimal
    narration: str | None
    source_line_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PurchaseReturnLineResponse(PurchaseReturnSchema):
    """Return one purchase return line."""

    id: UUID
    purchase_return_id: UUID
    line_number: int
    source_document_type: PurchaseReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    description: str | None
    received_quantity: Decimal
    already_returned_quantity: Decimal
    current_return_quantity: Decimal
    rejected_quantity: Decimal
    reason_code: str | None
    item_condition: str | None
    replacement_required: bool
    refund_required: bool
    is_scrap: bool
    is_damaged: bool
    is_expired: bool
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    charges_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    packaging_type_id: UUID | None
    purchase_uom_id: UUID | None
    return_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str | None
    expiry_date: date | None
    manufacturing_date: date | None
    remarks: str | None
    accounting_event_reference: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseReturnResponse(PurchaseReturnSchema):
    """Return one purchase return."""

    id: UUID
    firm_id: UUID
    vendor_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None
    return_number: str
    return_date: date
    supplier_return_number: str | None
    supplier_return_date: date | None
    reference_grn_number: str | None
    reference_invoice_number: str | None
    return_reason: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    payment_terms: str | None
    due_date: date | None
    reference_number: str | None
    remarks: str | None
    allow_direct_purchase_order: bool
    allow_over_return: bool
    over_return_percent: Decimal
    status: PurchaseReturnStatus
    total_source_quantity: Decimal
    total_already_returned_quantity: Decimal
    total_current_return_quantity: Decimal
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    approved_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseReturnLineResponse] = Field(default_factory=list)
    sources: list[PurchaseReturnSourceResponse] = Field(default_factory=list)
    attachments: list[PurchaseReturnAttachmentResponse] = Field(default_factory=list)
    notes: list[PurchaseReturnNoteResponse] = Field(default_factory=list)
    accounting_events: list[PurchaseReturnAccountingEventResponse] = Field(
        default_factory=list
    )
    duplicate_warning: str | None = None


class PurchaseReturnListFilters(PurchaseReturnSchema):
    """Narrow a purchase return list to the rows a caller asked for."""

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    status: PurchaseReturnStatus | None = None
    return_from: date | None = None
    return_to: date | None = None
    warehouse_id: UUID | None = None
    include_deleted: bool = False


class PurchaseReturnSummary(PurchaseReturnSchema):
    """Aggregate purchase return counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal
    completed: int


class PurchaseReturnRegisterRecord(PurchaseReturnSchema):
    """One row of the purchase return register report."""

    return_id: UUID
    return_number: str
    supplier_return_number: str | None
    vendor_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    return_date: date
    grand_total: Decimal
    status: PurchaseReturnStatus


class PurchaseReturnReconciliationRecord(PurchaseReturnSchema):
    """One line of a return set against the receipt it came from.

    Carries the product and the condition flags because the damaged and expired
    reports are this record filtered, and a row that does not say which product
    was sent back or why cannot answer either question.
    """

    return_id: UUID
    return_number: str
    return_date: date
    source_document_type: PurchaseReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    product_name: str
    received_quantity: Decimal
    already_returned_quantity: Decimal
    current_return_quantity: Decimal
    pending_quantity: Decimal
    reason_code: str | None
    is_damaged: bool
    is_expired: bool


class PurchaseReturnByVendorRecord(PurchaseReturnSchema):
    """Returned value and count per vendor.

    Named for what it holds. It was ``PurchaseReturnVendorOutstandingRecord``,
    which described a balance still owing -- a thing purchase returns do not
    have -- while carrying the value returned.
    """

    vendor_id: UUID
    vendor_name: str
    return_amount: Decimal
    return_count: int


class PurchaseReturnByProductRecord(PurchaseReturnSchema):
    """Returned quantity and value per product."""

    product_id: UUID
    product_code: str
    product_name: str
    return_quantity: Decimal
    return_amount: Decimal
    return_count: int
