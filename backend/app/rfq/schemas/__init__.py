"""Contracts for RFQs, supplier quotations and the comparison (PG-8)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RfqSchema(BaseModel):
    """Base contract: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class RfqLineWrite(RfqSchema):
    """One product asked about."""

    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    uom_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=500)


class RfqCreate(RfqSchema):
    """Raise a draft RFQ: the whole document."""

    branch_id: UUID
    warehouse_id: UUID
    rfq_date: date
    required_by: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[RfqLineWrite] = Field(min_length=1, max_length=500)
    #: The suppliers invited to quote.
    vendor_ids: list[UUID] = Field(default_factory=list, max_length=100)


class RfqUpdate(RfqSchema):
    """Change a draft RFQ; a field left out is left alone."""

    branch_id: UUID | None = None
    warehouse_id: UUID | None = None
    rfq_date: date | None = None
    required_by: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    #: Replaces the lines whole when sent, reconciled on line number.
    lines: list[RfqLineWrite] | None = Field(default=None, min_length=1, max_length=500)
    #: Replaces the invited suppliers whole when sent.
    vendor_ids: list[UUID] | None = Field(default=None, max_length=100)


class RfqCancel(RfqSchema):
    """Why an RFQ is called off."""

    reason: str = Field(min_length=1, max_length=1000)


class RfqLineResponse(RfqSchema):
    """One RFQ line with its product named and its chosen quote."""

    id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    quantity: Decimal
    uom_id: UUID | None
    notes: str | None
    selected_quotation_line_id: UUID | None
    selection_reason: str | None


class RfqSupplierResponse(RfqSchema):
    """One invited supplier, whether they quoted, and the order raised."""

    id: UUID
    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    quotation_id: UUID | None
    purchase_order_id: UUID | None


class RfqResponse(RfqSchema):
    """One RFQ, its lines and its suppliers."""

    id: UUID
    rfq_number: str
    rfq_date: date
    required_by: date | None
    branch_id: UUID
    warehouse_id: UUID
    status: str
    notes: str | None
    source_requisition_id: UUID | None
    sent_at: datetime | None
    closed_at: datetime | None
    cancel_reason: str | None
    version: int
    lines: list[RfqLineResponse]
    suppliers: list[RfqSupplierResponse]


class SupplierQuotationLineWrite(RfqSchema):
    """The rate quoted for one RFQ line."""

    rfq_line_id: UUID
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)

    @field_validator("rate")
    @classmethod
    def _a_rate_above_nothing(cls, value: Decimal) -> Decimal:
        """Refuse a quoted rate of 0 in plain words (D-BUY-53).

        A line the supplier did not quote is left out, not quoted at nothing:
        a rate of 0 would win every comparison.
        """
        if value <= 0:
            raise ValueError(
                "A quoted rate is above 0. Leave out a line the supplier did "
                "not quote."
            )
        return value

    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=9, decimal_places=4
    )
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    notes: str | None = Field(default=None, max_length=500)


class SupplierQuotationWrite(RfqSchema):
    """One supplier's quotation, entered or replaced whole."""

    quote_ref: str | None = Field(default=None, max_length=80)
    quote_date: date
    valid_until: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    #: A line the supplier did not quote is simply left out.
    lines: list[SupplierQuotationLineWrite] = Field(min_length=1, max_length=500)


class SupplierQuotationLineResponse(RfqSchema):
    """One quoted rate."""

    id: UUID
    rfq_line_id: UUID
    rate: Decimal
    discount_percent: Decimal
    landed_rate: Decimal
    lead_time_days: int | None
    notes: str | None


class SupplierQuotationResponse(RfqSchema):
    """One supplier's quotation."""

    id: UUID
    rfq_id: UUID
    vendor_id: UUID
    vendor_name: str
    quote_ref: str | None
    quote_date: date
    valid_until: date | None
    notes: str | None
    version: int
    lines: list[SupplierQuotationLineResponse]


class ComparisonQuote(RfqSchema):
    """One supplier's offer for one RFQ line."""

    quotation_id: UUID
    quotation_line_id: UUID
    vendor_id: UUID
    vendor_name: str
    rate: Decimal
    discount_percent: Decimal
    #: The rate after the discount, before tax.
    landed_rate: Decimal
    lead_time_days: int | None
    valid_until: date | None
    notes: str | None
    is_lowest: bool


class ComparisonLine(RfqSchema):
    """Every supplier's offer for one RFQ line, cheapest first."""

    rfq_line_id: UUID
    line_number: int
    product_id: UUID
    product_code: str
    product_name: str
    quantity: Decimal
    uom_id: UUID | None
    lowest_quotation_line_id: UUID | None
    selected_quotation_line_id: UUID | None
    selection_reason: str | None
    quotes: list[ComparisonQuote]


class RfqComparisonResponse(RfqSchema):
    """The side-by-side comparison of an RFQ's quotes."""

    rfq_id: UUID
    rfq_number: str
    status: str
    version: int
    lines: list[ComparisonLine]


class RfqSelectionWrite(RfqSchema):
    """The quote chosen for one RFQ line."""

    rfq_line_id: UUID
    quotation_line_id: UUID
    #: Required when the chosen quote is not the lowest landed rate.
    reason: str | None = Field(default=None, max_length=1000)


class RfqSelectionsWrite(RfqSchema):
    """Every choice on the RFQ; a line left out has nothing chosen."""

    selections: list[RfqSelectionWrite] = Field(max_length=500)
