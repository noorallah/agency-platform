"""Credit note request and response schemas."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreditNoteSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CreditNoteStatusEnum(StrEnum):
    """Where a credit note has got to."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class CreditNoteReasonEnum(StrEnum):
    """Why the customer is being credited."""

    RATE_DIFFERENCE = "RATE_DIFFERENCE"
    POST_SALE_DISCOUNT = "POST_SALE_DISCOUNT"
    DEFICIENCY_IN_SERVICE = "DEFICIENCY_IN_SERVICE"
    OTHER = "OTHER"


class CreditNoteLineWrite(CreditNoteSchema):
    """Carry one credited invoice line into a request.

    `taxable_amount` is what is being credited before tax, and it is what the
    caller states -- not a quantity times a rate. A rate difference credits
    value, and a post-sale discount credits value; neither is a number of
    units. The quantity is carried alongside for the tax authority and for the
    customer to recognise the line, and may be zero.
    """

    sales_invoice_line_id: UUID
    line_number: int = Field(ge=1)
    quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    taxable_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    description: str | None = Field(default=None, max_length=500)


class CreditNoteCreate(CreditNoteSchema):
    """Raise one credit note against one invoice."""

    sales_invoice_id: UUID
    credit_note_date: date
    reason: CreditNoteReasonEnum = CreditNoteReasonEnum.OTHER
    credit_note_number: str | None = Field(default=None, max_length=80)
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    lines: list[CreditNoteLineWrite] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _line_numbers_are_distinct(self) -> "CreditNoteCreate":
        """Refuse two lines claiming the same position.

        Returns:
            The validated payload.

        Raises:
            ValueError: If a line number is repeated.

        """
        seen = [line.line_number for line in self.lines]
        if len(set(seen)) != len(seen):
            raise ValueError("Line numbers must be distinct.")
        return self


class CreditNoteUpdate(CreditNoteSchema):
    """Change a credit note that has not been approved.

    Every field is optional and the service dumps with ``exclude_unset``, so
    an omitted field means *leave it alone* -- a write model that dumps in
    full turns an omission into an instruction, which has shipped here often
    enough to be a rule.
    """

    credit_note_date: date | None = None
    reason: CreditNoteReasonEnum | None = None
    reference_number: str | None = None
    remarks: str | None = None
    #: Omitted leaves the lines alone; a list replaces them all. There is no
    #: merging: the lines are what is being credited, and reconciling them by
    #: position would let a removed line stay in force.
    lines: list[CreditNoteLineWrite] | None = Field(default=None, max_length=200)


class CreditNoteLineResponse(CreditNoteSchema):
    """Return one credited line."""

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


class CreditNoteResponse(CreditNoteSchema):
    """Return one credit note."""

    id: UUID
    firm_id: UUID
    customer_id: UUID
    customer_name: str
    branch_id: UUID
    sales_invoice_id: UUID
    sales_invoice_number: str
    credit_note_number: str
    credit_note_date: date
    reason: CreditNoteReasonEnum
    status: CreditNoteStatusEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    reference_number: str | None
    remarks: str | None
    journal_entry_id: UUID | None
    version: int
    lines: list[CreditNoteLineResponse]


__all__ = [
    "CreditNoteCreate",
    "CreditNoteLineResponse",
    "CreditNoteLineWrite",
    "CreditNoteReasonEnum",
    "CreditNoteResponse",
    "CreditNoteSchema",
    "CreditNoteStatusEnum",
    "CreditNoteUpdate",
]


class CreditNoteRegisterRecord(CreditNoteSchema):
    """One credit note, as the register lists it."""

    credit_note_id: UUID
    credit_note_number: str
    credit_note_date: date
    customer_id: UUID
    customer_name: str
    sales_invoice_id: UUID
    sales_invoice_number: str
    reason: CreditNoteReasonEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: CreditNoteStatusEnum


class CreditNoteByCustomerRecord(CreditNoteSchema):
    """Credited value and count per customer.

    Cancelled notes are left out: a withdrawn credit is one the customer never
    had, and counting it would overstate what the firm gave back.
    """

    customer_id: UUID
    customer_name: str
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    note_count: int


class CreditNoteByReasonRecord(CreditNoteSchema):
    """What the firm is crediting for, and how much of it.

    The question the register cannot answer on its own. A month of rate
    differences is a pricing problem and a month of short supply is a
    warehouse one, and they are fixed by different people.
    """

    reason: CreditNoteReasonEnum
    total_amount: Decimal
    note_count: int
