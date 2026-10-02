"""Customer debit note request and response schemas."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CustomerDebitNoteSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CustomerDebitNoteStatusEnum(StrEnum):
    """Where a debit note has got to."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class CustomerDebitNoteReasonEnum(StrEnum):
    """Why the customer is being charged more."""

    PRICE_INCREASE = "PRICE_INCREASE"
    SHORT_BILLED = "SHORT_BILLED"
    ADDITIONAL_CHARGES = "ADDITIONAL_CHARGES"
    OTHER = "OTHER"


class CustomerDebitNoteLineWrite(CustomerDebitNoteSchema):
    """Carry one invoice line being charged more into a request.

    `taxable_amount` is the extra being charged before tax, as the caller
    states it -- a price increase charges value, not a number of units. The
    quantity is carried alongside for the customer to recognise the line, and
    may be zero.
    """

    sales_invoice_line_id: UUID
    line_number: int = Field(ge=1)
    quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    taxable_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    description: str | None = Field(default=None, max_length=500)


def _distinct_line_numbers(lines: list[CustomerDebitNoteLineWrite] | None) -> None:
    """Refuse two lines claiming the same position.

    Raises:
        ValueError: If a line number is repeated.

    """
    seen = [line.line_number for line in lines or []]
    if len(set(seen)) != len(seen):
        raise ValueError("Line numbers must be distinct.")


class CustomerDebitNoteCreate(CustomerDebitNoteSchema):
    """Raise one debit note against one invoice."""

    sales_invoice_id: UUID
    debit_note_date: date
    reason: CustomerDebitNoteReasonEnum = CustomerDebitNoteReasonEnum.OTHER
    debit_note_number: str | None = Field(default=None, max_length=80)
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    lines: list[CustomerDebitNoteLineWrite] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _line_numbers_are_distinct(self) -> "CustomerDebitNoteCreate":
        """Refuse two lines claiming the same position.

        Returns:
            The validated payload.

        """
        _distinct_line_numbers(self.lines)
        return self


class CustomerDebitNoteUpdate(CustomerDebitNoteSchema):
    """Change a debit note that has not been approved.

    Every field is optional and the service dumps with ``exclude_unset``, so
    an omitted field means *leave it alone*.
    """

    debit_note_date: date | None = None
    reason: CustomerDebitNoteReasonEnum | None = None
    reference_number: str | None = None
    remarks: str | None = None
    #: Omitted leaves the lines alone; a list replaces them all.
    lines: list[CustomerDebitNoteLineWrite] | None = Field(
        default=None, min_length=1, max_length=200
    )

    @model_validator(mode="after")
    def _line_numbers_are_distinct(self) -> "CustomerDebitNoteUpdate":
        """Refuse two lines claiming the same position.

        Returns:
            The validated payload.

        """
        _distinct_line_numbers(self.lines)
        return self


class CustomerDebitNoteLineResponse(CustomerDebitNoteSchema):
    """Return one charged line."""

    id: UUID
    line_number: int
    sales_invoice_line_id: UUID
    product_id: UUID
    product_name: str
    description: str | None
    quantity: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_rate_percent: Decimal


class CustomerDebitNoteResponse(CustomerDebitNoteSchema):
    """Return one debit note."""

    id: UUID
    firm_id: UUID
    customer_id: UUID
    customer_name: str
    branch_id: UUID
    sales_invoice_id: UUID
    sales_invoice_number: str
    debit_note_number: str
    debit_note_date: date
    reason: CustomerDebitNoteReasonEnum
    status: CustomerDebitNoteStatusEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    reference_number: str | None
    remarks: str | None
    journal_entry_id: UUID | None
    version: int
    lines: list[CustomerDebitNoteLineResponse]


class CustomerDebitNoteRegisterRecord(CustomerDebitNoteSchema):
    """One debit note, as the register lists it."""

    debit_note_id: UUID
    debit_note_number: str
    debit_note_date: date
    customer_id: UUID
    customer_name: str
    sales_invoice_id: UUID
    sales_invoice_number: str
    reason: CustomerDebitNoteReasonEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: CustomerDebitNoteStatusEnum
