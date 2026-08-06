"""Validated contracts for sales invoices."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SalesInvoiceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SalesInvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class SalesInvoiceSourceType(StrEnum):
    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_ORDER = "SALES_ORDER"
    MANUAL = "MANUAL"


class SalesInvoiceAccountingEventType(StrEnum):
    SALES_REVENUE = "SALES_REVENUE"
    OUTPUT_TAX = "OUTPUT_TAX"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"


class SalesInvoiceAttachmentWrite(SalesInvoiceSchema):
    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(default="SALES_INVOICE_FILE", min_length=1, max_length=40)


class SalesInvoiceNoteWrite(SalesInvoiceSchema):
    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class SalesInvoiceSourceWrite(SalesInvoiceSchema):
    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID


class SalesInvoiceLineWrite(SalesInvoiceSchema):
    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID
    source_document_line_id: UUID
    line_number: int = Field(ge=1)
    current_invoice_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, max_digits=9, decimal_places=4)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    charges_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    order_uom_id: UUID | None = None
    invoice_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None


class SalesInvoiceCreate(SalesInvoiceSchema):
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    route_id: UUID | None = None
    invoice_date: date
    customer_invoice_number: str | None = Field(default=None, max_length=120)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    payment_terms: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_direct_sales_order: bool = False
    allow_over_invoice: bool = False
    over_invoice_percent: Decimal = Field(default=Decimal("0"), ge=0, max_digits=9, decimal_places=4)
    additional_charges: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    invoice_number: str | None = Field(default=None, max_length=60)
    source_documents: list[SalesInvoiceSourceWrite] = Field(default_factory=list, max_length=100)
    lines: list[SalesInvoiceLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[SalesInvoiceAttachmentWrite] = Field(default_factory=list, max_length=500)
    notes: list[SalesInvoiceNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class SalesInvoiceUpdate(SalesInvoiceCreate):
    pass


class SalesInvoiceImportRequest(SalesInvoiceSchema):
    records: list[SalesInvoiceCreate] = Field(min_length=1, max_length=500)


class SalesInvoiceAttachmentResponse(SalesInvoiceSchema):
    id: UUID
    sales_invoice_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class SalesInvoiceNoteResponse(SalesInvoiceSchema):
    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class SalesInvoiceSourceResponse(SalesInvoiceSchema):
    id: UUID
    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_date: date
    customer_id: UUID
    branch_id: UUID
    created_at: datetime
    updated_at: datetime


class SalesInvoiceAccountingEventResponse(SalesInvoiceSchema):
    id: UUID
    event_type: SalesInvoiceAccountingEventType
    account_name: str
    direction: str
    amount: Decimal
    narration: str | None
    source_line_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SalesInvoiceLineResponse(SalesInvoiceSchema):
    id: UUID
    sales_invoice_id: UUID
    line_number: int
    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    description: str | None
    delivered_quantity: Decimal
    already_invoiced_quantity: Decimal
    current_invoice_quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    charges_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    packaging_type_id: UUID | None
    order_uom_id: UUID | None
    invoice_uom_id: UUID | None
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


class SalesInvoiceResponse(SalesInvoiceSchema):
    id: UUID
    firm_id: UUID
    customer_id: UUID
    salesman_id: UUID | None
    territory_id: UUID | None
    route_id: UUID | None
    branch_id: UUID
    business_profile_id: UUID | None
    invoice_number: str
    invoice_date: date
    customer_invoice_number: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    payment_terms: str | None
    due_date: date | None
    reference_number: str | None
    remarks: str | None
    allow_direct_sales_order: bool
    allow_over_invoice: bool
    over_invoice_percent: Decimal
    status: SalesInvoiceStatus
    total_source_quantity: Decimal
    total_already_invoiced_quantity: Decimal
    total_current_invoice_quantity: Decimal
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
    lines: list[SalesInvoiceLineResponse] = Field(default_factory=list)
    sources: list[SalesInvoiceSourceResponse] = Field(default_factory=list)
    attachments: list[SalesInvoiceAttachmentResponse] = Field(default_factory=list)
    notes: list[SalesInvoiceNoteResponse] = Field(default_factory=list)
    accounting_events: list[SalesInvoiceAccountingEventResponse] = Field(default_factory=list)
    duplicate_warning: str | None = None


class SalesInvoiceListFilters(SalesInvoiceSchema):
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    status: SalesInvoiceStatus | None = None
    invoice_from: date | None = None
    invoice_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    include_deleted: bool = False


class SalesInvoiceSummary(SalesInvoiceSchema):
    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_invoices: int
    overdue_invoices: int


class SalesInvoiceRegisterRecord(SalesInvoiceSchema):
    invoice_id: UUID
    invoice_number: str
    customer_invoice_number: str | None
    customer_id: UUID
    branch_id: UUID
    invoice_date: date
    due_date: date | None
    grand_total: Decimal
    status: SalesInvoiceStatus


class SalesInvoiceReconciliationRecord(SalesInvoiceSchema):
    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    delivered_quantity: Decimal
    already_invoiced_quantity: Decimal
    current_invoice_quantity: Decimal
    pending_quantity: Decimal


class SalesInvoiceCustomerOutstandingRecord(SalesInvoiceSchema):
    customer_id: UUID
    customer_name: str
    outstanding_amount: Decimal
    invoice_count: int
