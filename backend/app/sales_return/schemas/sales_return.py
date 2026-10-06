"""Validated contracts for sales returns."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.batch_serial.schemas import PickedSerial
from app.sales.schemas.document_preview import DocumentPreviewLine


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
    #: Everything coming back on this line, free goods included.
    current_return_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    #: How many of ``current_return_quantity`` are free goods (D-PRC-8).
    #: Blank takes the charged units first and counts as free only what comes
    #: back beyond them; a number says so outright -- the free unit of a
    #: "buy 12 get 1" coming back on its own. Free goods are credited nothing.
    free_quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
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
    #: Which serialised units are coming back, for a serial-tracked product:
    #: units sold on the source line (``GET /returnable-serials`` lists
    #: them), one per unit returned -- completing the return refuses until
    #: the count matches. None (or absent) keeps the line's picks as they
    #: were; an empty list clears them.
    serial_ids: list[UUID] | None = Field(default=None, max_length=10000)

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
    #: Everything coming back, free goods included, as it was typed.
    current_return_quantity: Decimal
    #: The free goods among them, credited nothing (D-PRC-8).
    free_quantity: Decimal = Decimal("0")
    #: The part of the quantity that came back before any bill charged for
    #: it (D-SELL-55): stock and cost only, no credit and no tax reversed.
    #: Decided at completion; zero before it.
    unbilled_quantity: Decimal = Decimal("0")
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
    #: This line's share of the document's bill discount.
    bill_discount_amount: Decimal
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
    #: The serialised units this line names -- picked while it is a draft,
    #: back on the shelf once it is completed.
    serials: list[PickedSerial] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    #: The tax rule that decided the line and its version; null when the
    #: profile alone did (GST-8).
    tax_rule_code: str | None = None
    tax_rule_version: int | None = None


class SalesReturnResponse(SalesReturnSchema):
    """Return one sales return."""

    #: How many uploaded files the return carries (SG-6), so a list can show
    #: a paper clip without asking per row. Counted once for the page.
    attached_file_count: int = 0

    id: UUID
    firm_id: UUID
    customer_id: UUID
    #: Whose return it is, so the list can say so (owner, 2026-09-27).
    #: Empty for a customer since removed.
    customer_name: str = ""
    customer_code: str = ""
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
    # Set when the return is dated past 30 November after the year of an
    # invoice it credits, so it can no longer reduce tax (s.34(2), GST-1).
    time_limit_warning: str | None = None


class SalesReturnSummary(SalesReturnSchema):
    """Summarise sales returns for one firm."""

    total_returns: int
    draft_returns: int
    approved_returns: int
    completed_returns: int
    cancelled_returns: int
    #: What the firm's **completed** returns credited: a return's total, less
    #: the value of goods that came back before any bill charged for them
    #: (D-SELL-74). The register's ``credited_amount`` summed over the same
    #: returns; a draft or approved return adds nothing here (D-SELL-84).
    total_return_value: Decimal
    #: The stated totals of the returns still on their way -- draft or
    #: approved -- which have credited nobody yet (D-SELL-84).
    pending_return_value: Decimal = Decimal("0")
    total_restock_quantity: Decimal


class SalesReturnRegisterRecord(SalesReturnSchema):
    """One row of the sales return register report."""

    return_id: UUID
    return_number: str
    customer_return_number: str | None
    customer_id: UUID
    #: Each id keeps a name beside it: the grid derives its columns from the
    #: row, so a register of ids alone showed three columns of UUIDs
    #: (D-RPT-17).
    customer_name: str
    branch_id: UUID
    branch_name: str
    warehouse_id: UUID
    warehouse_name: str
    return_date: date
    #: The document's own total, at the prices the goods went out at.
    grand_total: Decimal
    #: What the customer was credited: nothing until the return completes,
    #: and nothing for goods that came back before billing (D-SELL-74).
    credited_amount: Decimal = Decimal("0")
    #: The quantity that came back before billing: stock and cost only.
    unbilled_quantity: Decimal = Decimal("0")
    status: SalesReturnStatus


class SalesReturnByCustomerRecord(SalesReturnSchema):
    """Returned value and count per customer."""

    customer_id: UUID
    customer_name: str
    #: What the customer was credited (D-SELL-74), not the documents' totals.
    return_amount: Decimal
    #: The quantity that came back before billing, which credited nothing.
    unbilled_quantity: Decimal = Decimal("0")
    return_count: int


class SalesReturnByProductRecord(SalesReturnSchema):
    """Returned quantity and value per product."""

    product_id: UUID
    product_code: str
    product_name: str
    #: Everything that came back, free goods included.
    return_quantity: Decimal
    #: The free goods among them: quantity with no value (D-PRC-8).
    free_quantity: Decimal = Decimal("0")
    restock_quantity: Decimal
    #: What was credited for the product (D-SELL-74): the billed part only.
    return_amount: Decimal
    #: The part of ``return_quantity`` that came back before billing.
    unbilled_quantity: Decimal = Decimal("0")
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


class SalesReturnPreview(SalesReturnSchema):
    """A sales return priced exactly as saving it would, without saving it.

    ``interstate`` says how its tax splits: IGST for a customer in another
    state, CGST and SGST for one in the firm's own. ``lines`` carries each
    line's last price to this customer and the stock where it comes back.
    """

    sales_return: SalesReturnResponse
    interstate: bool
    lines: list[DocumentPreviewLine]
