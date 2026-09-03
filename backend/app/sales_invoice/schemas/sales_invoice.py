"""Validated contracts for sales invoices."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SalesInvoiceSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SalesInvoiceStatus(StrEnum):
    """Supported sales invoice lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class SalesInvoiceSourceType(StrEnum):
    """Documents a sales invoice can be raised from."""

    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_ORDER = "SALES_ORDER"
    MANUAL = "MANUAL"


class SalesInvoiceAccountingEventType(StrEnum):
    """Accounting events a sales invoice can raise."""

    SALES_REVENUE = "SALES_REVENUE"
    OUTPUT_TAX = "OUTPUT_TAX"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"


class SalesInvoiceAttachmentWrite(SalesInvoiceSchema):
    """Carry one sales invoice attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="SALES_INVOICE_FILE", min_length=1, max_length=40
    )


class SalesInvoiceNoteWrite(SalesInvoiceSchema):
    """Carry one sales invoice note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class SalesInvoiceSourceWrite(SalesInvoiceSchema):
    """Carry one sales invoice source into a request."""

    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID


class BillableLine(SalesInvoiceSchema):
    """One line of a document that still has something left to bill."""

    source_document_line_id: UUID
    line_number: int
    product_id: UUID | None
    description: str | None

    #: What the source document committed -- dispatched on a delivery note,
    #: ordered on a sales order.
    source_quantity: Decimal

    #: What earlier invoices already billed against this line. Cancelled
    #: invoices do not count, so cancelling one makes its quantity billable
    #: again.
    already_invoiced_quantity: Decimal

    #: The difference, and what an invoice line should default to.
    remaining_quantity: Decimal

    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal

    #: Goods the source line gave away. An invoice may state up to this much
    #: free and no more.
    free_quantity: Decimal


class BillableDocument(SalesInvoiceSchema):
    """A dispatched delivery note or approved order with something left to bill.

    Nothing exposed this, so a client had no way to know which documents were
    already invoiced -- it could only offer all of them and let the save be
    refused. On a firm with 58 delivery notes and 49 invoices that is a refusal
    nine times in ten.
    """

    source_document_type: SalesInvoiceSourceType
    source_document_id: UUID
    source_document_number: str
    document_date: date
    customer_id: UUID
    customer_name: str
    branch_id: UUID | None
    lines: list[BillableLine]


class SalesInvoiceLineWrite(SalesInvoiceSchema):
    """Carry one sales invoice line into a request.

    A line either bills something already raised -- naming the source document
    and the line within it -- or names a bare `product_id`, which only a firm
    whose configuration synthesises the earlier stages may do. The two forms
    are exclusive: a line carrying both says two different things about where
    the goods came from, and nothing could decide which to believe.
    """

    #: All three together, or none of them. Absent means the firm's
    #: configuration is expected to supply the document this line bills.
    source_document_type: SalesInvoiceSourceType | None = None
    source_document_id: UUID | None = None
    source_document_line_id: UUID | None = None
    #: Required only on a bare line, where there is no source line to read the
    #: product off.
    product_id: UUID | None = None
    line_number: int = Field(ge=1)
    current_invoice_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    #: None means the caller said nothing, so the price is inherited from the
    #: line being billed. Zero is an answer: goods given away.
    unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: Supplied free with this line. None inherits whatever the source line
    #: offered, pro-rated by the share being billed; zero refuses it.
    free_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )

    #: None means the caller said nothing, so the customer's standing
    #: discount applies. Zero means they said no discount.
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
    order_uom_id: UUID | None = None
    invoice_uom_id: UUID | None = None
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _one_provenance(self) -> "SalesInvoiceLineWrite":
        """Refuse a line that names both a source and a product, or neither."""
        source_fields = (
            self.source_document_type,
            self.source_document_id,
            self.source_document_line_id,
        )
        named = [field is not None for field in source_fields]
        if any(named) and not all(named):
            raise ValueError(
                "A line billing a source document must name its type, its id "
                "and its line together."
            )
        if all(named) and self.product_id is not None:
            raise ValueError(
                "A line names either the source document it bills or a "
                "product, never both."
            )
        if not any(named) and self.product_id is None:
            raise ValueError(
                "A line must name either the source document it bills or a " "product."
            )
        return self


class SalesInvoiceCreate(SalesInvoiceSchema):
    """Create one sales invoice."""

    customer_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    route_id: UUID | None = None
    invoice_date: date
    customer_invoice_number: str | None = Field(default=None, max_length=120)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    payment_terms: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_over_invoice: bool = False
    over_invoice_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    invoice_number: str | None = Field(default=None, max_length=60)
    source_documents: list[SalesInvoiceSourceWrite] = Field(
        default_factory=list, max_length=100
    )
    #: A discount on the whole document, taken off what the lines discounted
    #: to and split across them so the tax is charged on the reduced value.
    #: An amount beats a rate, exactly as on a line.
    bill_discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=9, decimal_places=4
    )
    bill_discount_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    #: What the customer is charged for delivery. Part of the taxable value:
    #: it is split across the lines and taxed with them, because delivery
    #: charged by the seller is ancillary to the supply of the goods.
    #: `additional_charges` stays outside the tax, for additions that really
    #: are outside it.
    freight_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    lines: list[SalesInvoiceLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[SalesInvoiceAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[SalesInvoiceNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class SalesInvoiceUpdate(SalesInvoiceCreate):
    """Replace one sales invoice."""

    pass


class SalesInvoiceImportRequest(SalesInvoiceSchema):
    """Import a validated batch of sales invoices."""

    records: list[SalesInvoiceCreate] = Field(min_length=1, max_length=500)


class SalesInvoiceAttachmentResponse(SalesInvoiceSchema):
    """Return one sales invoice attachment."""

    id: UUID
    sales_invoice_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class SalesInvoiceNoteResponse(SalesInvoiceSchema):
    """Return one sales invoice note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class SalesInvoiceSourceResponse(SalesInvoiceSchema):
    """Return one sales invoice source."""

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
    """Return one sales invoice accounting event."""

    id: UUID
    event_type: SalesInvoiceAccountingEventType
    account_name: str
    direction: str
    amount: Decimal
    narration: str | None
    source_line_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SalesInvoiceLineTaxResponse(SalesInvoiceSchema):
    """One tax component the line was charged, as it was charged.

    Read from the invoice rather than recomputed: rules are effective-dated,
    so asking the engine again a year later can answer differently from what
    the customer was billed.
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


class SalesInvoiceLineResponse(SalesInvoiceSchema):
    """Return one sales invoice line."""

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
    #: Supplied free with this line, charged for at nothing.
    free_quantity: Decimal

    #: This line's share of the document's bill discount.
    bill_discount_amount: Decimal
    #: This line's share of the document's freight.
    freight_amount: Decimal = Decimal("0")
    #: What the goods cost, or null where no dispatch could be traced. Null
    #: is not zero: zero would mean the goods were free.
    cost_amount: Decimal | None = None
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
    #: What the customer was charged, component by component.
    taxes: list[SalesInvoiceLineTaxResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SalesInvoiceResponse(SalesInvoiceSchema):
    """Return one sales invoice."""

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
    #: The state the supply was made in, fixed when the invoice was raised.
    place_of_supply: str | None = None
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
    #: The optimistic-concurrency counter this record was read at. A
    #: client echoes it back as `If-Match`; the list carries it because
    #: the desktop opens its editor from a list row rather than
    #: re-reading the record, so an ETag alone could never reach it.
    version: int

    #: How much was supplied free across the document.
    total_free_quantity: Decimal

    #: What was taken off the whole document, and the rate it represents.
    bill_discount_percent: Decimal
    bill_discount_amount: Decimal
    #: What was charged for delivery, split across the lines and taxed there.
    freight_amount: Decimal = Decimal("0")
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
    accounting_events: list[SalesInvoiceAccountingEventResponse] = Field(
        default_factory=list
    )
    duplicate_warning: str | None = None


class SalesInvoiceListFilters(SalesInvoiceSchema):
    """Narrow a sales invoice list to the rows a caller asked for."""

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
    """Aggregate sales invoice counts for the visible firm scope."""

    total: int
    draft: int
    approved: int
    cancelled: int
    closed: int
    total_value: Decimal
    pending_invoices: int
    overdue_invoices: int


class SalesInvoiceRegisterRecord(SalesInvoiceSchema):
    """One row of the sales invoice register report."""

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
    """One row of the sales invoice reconciliation report."""

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
    """One row of the sales invoice customer outstanding report."""

    customer_id: UUID
    customer_name: str
    outstanding_amount: Decimal
    invoice_count: int
