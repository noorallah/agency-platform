"""Validated contracts for sales returns."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SalesReturnSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SalesReturnStatus(StrEnum):
    """Supported sales return lifecycle statuses."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class SalesReturnSourceType(StrEnum):
    """Documents a sales return can be raised from.

    The goods physically left on a delivery note and the money was billed on a
    sales invoice, so either is a legitimate starting point: a customer who
    returns goods before being invoiced has a delivery note and nothing else.
    """

    DELIVERY_NOTE = "DELIVERY_NOTE"
    SALES_INVOICE = "SALES_INVOICE"


class SalesReturnAttachmentWrite(SalesReturnSchema):
    """Carry one sales return attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(
        default="SALES_RETURN_FILE", min_length=1, max_length=40
    )


class SalesReturnNoteWrite(SalesReturnSchema):
    """Carry one sales return note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class SalesReturnSourceWrite(SalesReturnSchema):
    """Carry one sales return source into a request."""

    source_document_type: SalesReturnSourceType
    source_document_id: UUID


class SalesReturnLineWrite(SalesReturnSchema):
    """Carry one sales return line into a request."""

    source_document_type: SalesReturnSourceType
    source_document_id: UUID
    source_document_line_id: UUID
    line_number: int = Field(ge=1)
    current_return_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    #: How much of it can be sold again. Defaults to all of it on the reading
    #: that goods come back fit unless somebody says otherwise, which is what a
    #: warehouse clerk booking a return in a hurry means.
    restock_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    damaged_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    scrap_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    reason_code: str | None = Field(default=None, max_length=80)
    item_condition: str | None = Field(default=None, max_length=80)
    is_damaged: bool = False
    is_expired: bool = False
    #: Left unset, the line is credited at what the source document charged.
    #: Sent explicitly -- zero included -- that is what the customer gets: a
    #: free replacement is credited at nothing, not at the price of the goods
    #: it replaced.
    unit_price: Decimal | None = Field(
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
    sales_uom_id: UUID | None = None
    return_uom_id: UUID | None = None
    conversion_factor: Decimal | None = Field(
        default=None, gt=0, max_digits=24, decimal_places=10
    )
    warehouse_id: UUID | None = None
    storage_node_id: UUID | None = None
    batch_number: str | None = Field(default=None, max_length=120)
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _condition_adds_up(self) -> "SalesReturnLineWrite":
        """Refuse a line that says more came back than came back.

        The three buckets decide where the goods land and what the firm can
        sell, so a line whose parts exceed its whole would put stock on the
        shelf that never arrived.
        """
        restock = (
            self.current_return_quantity - self.damaged_quantity - self.scrap_quantity
            if self.restock_quantity is None
            else self.restock_quantity
        )
        if restock < 0:
            raise ValueError(
                "Damaged and scrap quantities cannot exceed the returned quantity."
            )
        total = restock + self.damaged_quantity + self.scrap_quantity
        if total != self.current_return_quantity:
            raise ValueError(
                "Restock, damaged and scrap quantities must add up to the "
                f"returned quantity ({self.current_return_quantity})."
            )
        return self


class SalesReturnCreate(SalesReturnSchema):
    """Create one sales return."""

    customer_id: UUID | None = None
    branch_id: UUID | None = None
    business_profile_id: UUID | None = None
    warehouse_id: UUID
    return_date: date
    customer_return_number: str | None = Field(default=None, max_length=120)
    customer_return_date: date | None = None
    reference_delivery_note_number: str | None = Field(default=None, max_length=80)
    reference_invoice_number: str | None = Field(default=None, max_length=80)
    return_reason: str | None = Field(default=None, max_length=80)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    allow_over_return: bool = False
    over_return_percent: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=9, decimal_places=4
    )
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    return_number: str | None = Field(default=None, max_length=60)
    source_documents: list[SalesReturnSourceWrite] = Field(
        default_factory=list, max_length=100
    )
    lines: list[SalesReturnLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[SalesReturnAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[SalesReturnNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("return_number", mode="before")
    @classmethod
    def _normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None


class SalesReturnUpdate(SalesReturnCreate):
    """Replace one sales return."""


class SalesReturnImportRequest(SalesReturnSchema):
    """Import a validated batch of sales returns.

    Bounded at 500 for the same reason the purchase-return batch is: every
    record resolves its source delivery note or invoice, prices its lines and
    simulates tax per line, so a batch is not a cheap loop over inserts.
    """

    records: list[SalesReturnCreate] = Field(min_length=1, max_length=500)


class SalesReturnListFilters(SalesReturnSchema):
    """Narrow a sales return list."""

    customer_id: UUID | None = None
    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    status: SalesReturnStatus | None = None
    return_from: date | None = None
    return_to: date | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def _dates_are_in_order(self) -> "SalesReturnListFilters":
        """Refuse a window that ends before it starts."""
        if (
            self.return_from is not None
            and self.return_to is not None
            and self.return_to < self.return_from
        ):
            raise ValueError("return_to cannot be earlier than return_from.")
        return self


class SalesReturnAttachmentResponse(SalesReturnSchema):
    """Return one sales return attachment."""

    id: UUID
    sales_return_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class SalesReturnNoteResponse(SalesReturnSchema):
    """Return one sales return note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class SalesReturnSourceResponse(SalesReturnSchema):
    """Return one sales return source."""

    id: UUID
    source_document_type: SalesReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_date: date
    customer_id: UUID
    branch_id: UUID
    created_at: datetime
    updated_at: datetime


class SalesReturnLineResponse(SalesReturnSchema):
    """Return one sales return line."""

    id: UUID
    sales_return_id: UUID
    line_number: int
    source_document_type: SalesReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    description: str | None
    dispatched_quantity: Decimal
    already_returned_quantity: Decimal
    current_return_quantity: Decimal
    restock_quantity: Decimal
    damaged_quantity: Decimal
    scrap_quantity: Decimal
    reason_code: str | None
    item_condition: str | None
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
    sales_uom_id: UUID | None
    return_uom_id: UUID | None
    conversion_factor: Decimal
    conversion_version: int | None
    warehouse_id: UUID | None
    storage_node_id: UUID | None
    batch_number: str | None
    batch_id: UUID | None
    expiry_date: date | None
    manufacturing_date: date | None
    inventory_transaction_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class SalesReturnResponse(SalesReturnSchema):
    """Return one sales return."""

    id: UUID
    firm_id: UUID
    customer_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    salesman_id: UUID | None
    territory_id: UUID | None
    business_profile_id: UUID | None
    return_number: str
    return_date: date
    customer_return_number: str | None
    customer_return_date: date | None
    reference_delivery_note_number: str | None
    reference_invoice_number: str | None
    return_reason: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    reference_number: str | None
    remarks: str | None
    allow_over_return: bool
    over_return_percent: Decimal
    status: SalesReturnStatus
    total_source_quantity: Decimal
    total_already_returned_quantity: Decimal
    total_current_return_quantity: Decimal
    total_restock_quantity: Decimal
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    journal_entry_id: UUID | None
    cost_journal_entry_id: UUID | None
    approved_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    close_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    version: int
    lines: list[SalesReturnLineResponse]
    sources: list[SalesReturnSourceResponse]
    attachments: list[SalesReturnAttachmentResponse]
    notes: list[SalesReturnNoteResponse]


class SalesReturnSummary(SalesReturnSchema):
    """Summarise sales returns for one firm."""

    total_returns: int
    draft_returns: int
    approved_returns: int
    completed_returns: int
    cancelled_returns: int
    total_return_value: Decimal
    total_restock_quantity: Decimal


class SalesReturnRegisterRecord(SalesReturnSchema):
    """One row of the sales return register report."""

    return_id: UUID
    return_number: str
    customer_return_number: str | None
    customer_id: UUID
    branch_id: UUID
    warehouse_id: UUID
    return_date: date
    grand_total: Decimal
    status: SalesReturnStatus


class SalesReturnByCustomerRecord(SalesReturnSchema):
    """Returned value and count per customer."""

    customer_id: UUID
    customer_name: str
    return_amount: Decimal
    return_count: int


class SalesReturnByProductRecord(SalesReturnSchema):
    """Returned quantity and value per product."""

    product_id: UUID
    product_code: str
    product_name: str
    return_quantity: Decimal
    restock_quantity: Decimal
    return_amount: Decimal
    return_count: int


class SalesReturnReconciliationRecord(SalesReturnSchema):
    """One return line set against the document it was dispatched on."""

    return_id: UUID
    return_number: str
    return_date: date
    source_document_type: SalesReturnSourceType
    source_document_id: UUID
    source_document_number: str
    source_document_line_id: UUID
    source_document_line_number: int
    product_id: UUID
    product_name: str
    dispatched_quantity: Decimal
    already_returned_quantity: Decimal
    current_return_quantity: Decimal
    pending_quantity: Decimal
    restock_quantity: Decimal
    reason_code: str | None
    is_damaged: bool
    is_expired: bool
