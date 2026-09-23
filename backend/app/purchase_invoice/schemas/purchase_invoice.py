"""Validated contracts for purchase invoices."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PurchaseInvoiceSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PurchaseInvoiceStatus(StrEnum):
    """Supported purchase invoice lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class PurchaseInvoiceSourceType(StrEnum):
    """Documents a purchase invoice can be raised from."""

    GOODS_RECEIPT = "GOODS_RECEIPT"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    MANUAL = "MANUAL"


class PurchaseInvoiceAccountingEventType(StrEnum):
    """Accounting events a purchase invoice can raise."""

    PURCHASE_EXPENSE = "PURCHASE_EXPENSE"
    INPUT_TAX = "INPUT_TAX"
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"


class PurchaseInvoiceAttachmentWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="PURCHASE_INVOICE_FILE", min_length=1, max_length=40
    )


class PurchaseInvoiceNoteWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class PurchaseInvoiceSourceWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice source into a request."""

    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID


class PurchaseInvoiceLineWrite(PurchaseInvoiceSchema):
    """Carry one purchase invoice line into a request."""

    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_line_id: UUID
    line_number: int = Field(ge=1)
    current_invoice_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    #: None means the caller said nothing, so the price on the source line
    #: carries over. Zero is an instruction, not a default: it defaulted to
    #: zero once, and a bill sent without prices was valued at nothing
    #: (D-BUY-3).
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: None means the caller said nothing, so the rate on the source line
    #: carries over. Zero means they said no discount on this one.
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    charges_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    packaging_type_id: UUID | None = None
    purchase_uom_id: UUID | None = None
    invoice_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None


class PurchaseInvoiceCreate(PurchaseInvoiceSchema):
    """Create one purchase invoice."""

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    invoice_date: date
    supplier_invoice_number: str = Field(min_length=1, max_length=120)
    supplier_invoice_date: date
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    payment_terms: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    invoice_number: str | None = Field(default=None, max_length=60)
    source_documents: list[PurchaseInvoiceSourceWrite] = Field(
        default_factory=list, max_length=100
    )
    lines: list[PurchaseInvoiceLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[PurchaseInvoiceAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[PurchaseInvoiceNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class PurchaseInvoiceUpdate(PurchaseInvoiceCreate):
    """Replace one purchase invoice."""

    pass


class PurchaseInvoiceImportRequest(PurchaseInvoiceSchema):
    """Import a validated batch of purchase invoices."""

    records: list[PurchaseInvoiceCreate] = Field(min_length=1, max_length=500)


class PurchaseInvoiceAttachmentResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice attachment."""

    id: UUID
    purchase_invoice_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceNoteResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceSourceResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice source."""

    id: UUID
    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_date: date
    vendor_id: UUID
    branch_id: UUID
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceAccountingEventResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice accounting event."""

    id: UUID
    event_type: PurchaseInvoiceAccountingEventType
    account_name: str
    direction: str
    amount: Decimal
    narration: str | None
    source_line_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceLineTaxResponse(PurchaseInvoiceSchema):
    """One tax component the line was charged, as it was charged.

    Read from the bill rather than recomputed: rules are effective-dated, so
    asking the engine again a year later can answer differently from what the
    supplier charged, and the input credit claimed against it.
    """

    id: UUID
    sequence: int
    tax_component_id: UUID | None
    component_code: str
    component_label: str
    percentage: Decimal
    base_amount: Decimal
    amount: Decimal
    included_in_price: bool
    recoverable: bool


class PurchaseInvoiceLineResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice line."""

    id: UUID
    purchase_invoice_id: UUID
    line_number: int
    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    description: str | None
    received_quantity: Decimal
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
    purchase_uom_id: UUID | None
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
    taxes: list[PurchaseInvoiceLineTaxResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PurchaseInvoiceResponse(PurchaseInvoiceSchema):
    """Return one purchase invoice."""

    id: UUID
    firm_id: UUID
    vendor_id: UUID
    branch_id: UUID
    business_profile_id: UUID | None
    invoice_number: str
    invoice_date: date
    supplier_invoice_number: str
    supplier_invoice_date: date
    currency_code: str | None
    exchange_rate: Decimal | None
    payment_terms: str | None
    due_date: date | None
    reference_number: str | None
    remarks: str | None
    status: PurchaseInvoiceStatus
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
    lines: list[PurchaseInvoiceLineResponse] = Field(default_factory=list)
    sources: list[PurchaseInvoiceSourceResponse] = Field(default_factory=list)
    attachments: list[PurchaseInvoiceAttachmentResponse] = Field(default_factory=list)
    notes: list[PurchaseInvoiceNoteResponse] = Field(default_factory=list)
    accounting_events: list[PurchaseInvoiceAccountingEventResponse] = Field(
        default_factory=list
    )
    duplicate_warning: str | None = None


class PurchaseInvoiceListFilters(PurchaseInvoiceSchema):
    """Narrow a purchase invoice list to the rows a caller asked for."""

    vendor_id: UUID | None = None
    branch_id: UUID | None = None
    status: PurchaseInvoiceStatus | None = None
    invoice_from: date | None = None
    invoice_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    include_deleted: bool = False


class PurchaseInvoiceSummary(PurchaseInvoiceSchema):
    """Aggregate purchase invoice counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_invoices: int
    overdue_invoices: int


class PurchaseInvoiceRegisterRecord(PurchaseInvoiceSchema):
    """One row of the purchase invoice register report."""

    invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str
    vendor_id: UUID
    #: Each id keeps a name beside it: the grid derives its columns from the
    #: row, so a register of ids alone showed two columns of UUIDs (D-RPT-17).
    vendor_name: str
    branch_id: UUID
    branch_name: str
    invoice_date: date
    due_date: date | None
    grand_total: Decimal
    status: PurchaseInvoiceStatus


class PurchaseInvoiceReconciliationRecord(PurchaseInvoiceSchema):
    """One source line and what has been billed against it.

    One row per goods-receipt line, not per invoice line: the quantities are
    summed over the live invoices that bill it -- `invoiced_quantity` from
    APPROVED and CLOSED ones, `draft_quantity` from DRAFT -- and `pending` is
    what is left. The report used to answer one row per invoice line carrying
    the three quantities snapshotted on that line when it was written, so a
    source billed twice appeared twice with the older `pending` stale, and a
    cancelled invoice's line still claimed its quantity billed (D-RPT-13).
    """

    source_document_type: PurchaseInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    #: The product named as well as identified, in one read for the report
    #: (D-RPT-17): a reconciliation whose only product column is a UUID
    #: cannot be read against the receipt it reconciles.
    product_code: str
    product_name: str
    received_quantity: Decimal
    invoiced_quantity: Decimal
    draft_quantity: Decimal
    pending_quantity: Decimal
    invoice_numbers: str


class PurchaseInvoiceVendorOutstandingRecord(PurchaseInvoiceSchema):
    """One row of the purchase invoice vendor outstanding report.

    ``outstanding_amount`` is what the supplier's bills still owe once every
    posted payment, completed return and applied credit is taken off -- the
    same derivation Record Payment offers -- and ``invoice_count`` counts only
    the bills still owing anything. The report used to sum ``grand_total`` of
    every non-cancelled bill and count them all, so a supplier paid in full was
    owed the whole bill for ever (D-RPT-2).
    """

    vendor_id: UUID
    vendor_name: str
    outstanding_amount: Decimal
    invoice_count: int


class PurchaseInvoiceOverdueRecord(PurchaseInvoiceSchema):
    """One bill past its due date and still owing something.

    A flat row rather than the whole document: the desktop showed six columns
    of it and the endpoint answered forty fields, lines, attachments and notes
    per bill (D-RPT-16). ``outstanding_amount`` is derived as Record Payment
    derives it, so a bill paid in full leaves the list the day it is paid, and
    a DRAFT -- not yet a debt -- was never on it.
    """

    invoice_id: UUID
    invoice_number: str
    supplier_invoice_number: str | None
    vendor_id: UUID
    vendor_name: str
    invoice_date: date
    due_date: date
    days_overdue: int
    grand_total: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal
