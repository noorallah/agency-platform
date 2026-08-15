"""Validated contracts for sales quotations."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QuotationSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class QuotationStatus(StrEnum):
    """What has happened to an offer.

    ``EXPIRED`` is derived rather than stored on a schedule: nothing sweeps the
    table at midnight, so a quotation past ``valid_until`` reads as expired
    from its date and is refused conversion. Storing it would need a job, and a
    job that has not run yet would let a stale quote through.
    """

    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    CONVERTED = "CONVERTED"
    CANCELLED = "CANCELLED"


class QuotationAttachmentWrite(QuotationSchema):
    """Carry one quotation attachment into a request."""

    file_name: str = Field(min_length=1, max_length=260)
    mime_type: str | None = Field(default=None, max_length=120)
    file_path: str = Field(min_length=1, max_length=1024)
    attachment_kind: str = Field(default="QUOTATION_FILE", min_length=1, max_length=40)


class QuotationNoteWrite(QuotationSchema):
    """Carry one quotation note into a request."""

    note_type: str = Field(default="INTERNAL", min_length=1, max_length=30)
    note: str = Field(min_length=1)


class QuotationLineWrite(QuotationSchema):
    """Carry one quotation line into a request."""

    line_number: int = Field(ge=1)
    product_id: UUID
    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    free_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    sales_uom_id: UUID | None = None
    inventory_uom_id: UUID | None = None
    packaging_type_id: UUID | None = None
    unit_price: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    discount_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    tax_profile_id: UUID | None = None
    warehouse_id: UUID | None = None
    remarks: str | None = None


class QuotationCreate(QuotationSchema):
    """Create one quotation."""

    customer_id: UUID
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None = None
    quotation_date: date
    valid_until: date
    customer_reference: str | None = Field(default=None, max_length=80)
    reference_number: str | None = Field(default=None, max_length=80)
    payment_terms: str | None = Field(default=None, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=200)
    currency_code: str | None = Field(default=None, max_length=10)
    exchange_rate: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=6
    )
    remarks: str | None = None
    additional_charges: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    round_off: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=4)
    quotation_number: str | None = Field(default=None, max_length=60)
    lines: list[QuotationLineWrite] = Field(min_length=1, max_length=1000)
    attachments: list[QuotationAttachmentWrite] = Field(
        default_factory=list, max_length=500
    )
    notes: list[QuotationNoteWrite] = Field(default_factory=list, max_length=500)

    @field_validator("quotation_number", "currency_code", mode="before")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        if value is None:
            return None
        token = value.strip().upper()
        return token or None

    @model_validator(mode="after")
    def _validity_outlasts_the_offer(self) -> "QuotationCreate":
        """Refuse a quotation that has already expired when it is written."""
        if self.valid_until < self.quotation_date:
            raise ValueError("valid_until cannot be earlier than the quotation date.")
        return self


class QuotationUpdate(QuotationCreate):
    """Replace one quotation."""


class QuotationImportRequest(QuotationSchema):
    """Import a validated batch of quotations."""

    records: list[QuotationCreate] = Field(min_length=1, max_length=500)


class QuotationListFilters(QuotationSchema):
    """Narrow a quotation list."""

    customer_id: UUID | None = None
    branch_id: UUID | None = None
    salesman_id: UUID | None = None
    status: QuotationStatus | None = None
    quotation_from: date | None = None
    quotation_to: date | None = None
    include_deleted: bool = False

    @model_validator(mode="after")
    def _dates_are_in_order(self) -> "QuotationListFilters":
        """Refuse a window that ends before it starts."""
        if (
            self.quotation_from is not None
            and self.quotation_to is not None
            and self.quotation_to < self.quotation_from
        ):
            raise ValueError("quotation_to cannot be earlier than quotation_from.")
        return self


class QuotationDecision(QuotationSchema):
    """Record what the customer said."""

    reason: str | None = Field(default=None, max_length=500)


class QuotationConvertRequest(QuotationSchema):
    """Turn an accepted quotation into a sales order."""

    order_date: date | None = None
    delivery_date: date | None = None


class QuotationAttachmentResponse(QuotationSchema):
    """Return one quotation attachment."""

    id: UUID
    sales_quotation_id: UUID
    file_name: str
    mime_type: str | None
    file_path: str
    attachment_kind: str
    created_at: datetime
    updated_at: datetime


class QuotationNoteResponse(QuotationSchema):
    """Return one quotation note."""

    id: UUID
    note_type: str
    note: str
    created_at: datetime
    updated_at: datetime


class QuotationLineResponse(QuotationSchema):
    """Return one quotation line."""

    id: UUID
    sales_quotation_id: UUID
    line_number: int
    product_id: UUID
    description: str | None
    quantity: Decimal
    free_quantity: Decimal
    sales_uom_id: UUID | None
    inventory_uom_id: UUID | None
    packaging_type_id: UUID | None
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    gross_amount: Decimal
    tax_profile_id: UUID | None
    tax_amount: Decimal
    net_amount: Decimal
    warehouse_id: UUID | None
    remarks: str | None
    created_at: datetime
    updated_at: datetime


class QuotationResponse(QuotationSchema):
    """Return one quotation."""

    id: UUID
    firm_id: UUID
    customer_id: UUID
    salesman_id: UUID | None
    territory_id: UUID | None
    branch_id: UUID
    warehouse_id: UUID
    business_profile_id: UUID | None
    quotation_number: str
    quotation_date: date
    valid_until: date
    customer_reference: str | None
    reference_number: str | None
    payment_terms: str | None
    delivery_terms: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    remarks: str | None
    status: QuotationStatus
    line_discount_total: Decimal
    subtotal: Decimal
    tax_total: Decimal
    additional_charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    sent_at: datetime | None
    decided_at: datetime | None
    converted_at: datetime | None
    converted_sales_order_id: UUID | None
    converted_sales_order_number: str | None
    decline_reason: str | None
    cancel_reason: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    version: int
    lines: list[QuotationLineResponse]
    attachments: list[QuotationAttachmentResponse]
    notes: list[QuotationNoteResponse]

    #: Whether the prices have lapsed, worked out from the date rather than
    #: stored: nothing sweeps the table, so a stored flag would be stale for as
    #: long as nobody had run the sweep.
    is_expired: bool

    #: Whether it can still become an order. Answered here so a client does not
    #: reimplement the rule and disagree with the server about it.
    can_convert: bool


class QuotationSummary(QuotationSchema):
    """Summarise quotations for one firm."""

    total_quotations: int
    draft_quotations: int
    sent_quotations: int
    accepted_quotations: int
    declined_quotations: int
    converted_quotations: int
    expired_quotations: int
    total_quoted_value: Decimal
    total_converted_value: Decimal


class QuotationRegisterRecord(QuotationSchema):
    """One row of the quotation register."""

    quotation_id: UUID
    quotation_number: str
    customer_id: UUID
    quotation_date: date
    valid_until: date
    status: QuotationStatus
    grand_total: Decimal
    converted_sales_order_number: str | None


class QuotationConversionRecord(QuotationSchema):
    """How many quotations turned into orders, per customer.

    The question a sales manager asks of a quotation module, and one no other
    report can answer: a register says what was offered and an order register
    says what was sold, but neither joins them.
    """

    customer_id: UUID
    customer_name: str
    quoted_count: int
    quoted_value: Decimal
    converted_count: int
    converted_value: Decimal
    declined_count: int
