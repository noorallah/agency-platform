"""Debit note request and response schemas."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DebitNoteSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DebitNoteStatusEnum(StrEnum):
    """Where a debit note has got to."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class DebitNoteReasonEnum(StrEnum):
    """Why the supplier is being debited."""

    PRICE_DIFFERENCE = "PRICE_DIFFERENCE"
    SHORT_SUPPLY = "SHORT_SUPPLY"
    OTHER = "OTHER"


class DebitNoteLineWrite(DebitNoteSchema):
    """Carry one claimed bill line into a request.

    `taxable_amount` is what is being claimed before tax, stated by the
    caller. The quantity is carried for the supplier to recognise the line
    and may be zero.
    """

    purchase_invoice_line_id: UUID
    line_number: int = Field(ge=1)
    quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=4
    )
    taxable_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    description: str | None = Field(default=None, max_length=500)


def _distinct(lines: list[DebitNoteLineWrite] | None) -> None:
    """Refuse two lines claiming the same position."""
    if lines is None:
        return
    seen = [line.line_number for line in lines]
    if len(set(seen)) != len(seen):
        raise ValueError("Line numbers must be distinct.")


class DebitNoteCreate(DebitNoteSchema):
    """Raise one debit note against one supplier bill."""

    purchase_invoice_id: UUID
    debit_note_date: date
    reason: DebitNoteReasonEnum = DebitNoteReasonEnum.OTHER
    debit_note_number: str | None = Field(default=None, max_length=80)
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    lines: list[DebitNoteLineWrite] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _line_numbers_are_distinct(self) -> "DebitNoteCreate":
        """Refuse two lines claiming the same position.

        Returns:
            The validated payload.

        """
        _distinct(self.lines)
        return self


class DebitNoteUpdate(DebitNoteSchema):
    """Change a debit note that has not been approved.

    Every field is optional and dumped with ``exclude_unset``: absent means
    leave it alone. The status is deliberately absent -- it belongs to the
    approve and cancel endpoints.
    """

    debit_note_date: date | None = None
    reason: DebitNoteReasonEnum | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    remarks: str | None = None
    #: Omitted leaves the lines alone; a list replaces them all.
    lines: list[DebitNoteLineWrite] | None = Field(
        default=None, min_length=1, max_length=200
    )

    @model_validator(mode="after")
    def _line_numbers_are_distinct(self) -> "DebitNoteUpdate":
        """Refuse two lines claiming the same position.

        Returns:
            The validated payload.

        """
        _distinct(self.lines)
        return self


class DebitNoteCancel(DebitNoteSchema):
    """Say why a debit note is being withdrawn; the trail keeps it."""

    reason: str = Field(min_length=1, max_length=500)


class DebitNoteLineResponse(DebitNoteSchema):
    """Return one claimed line."""

    id: UUID
    line_number: int
    purchase_invoice_line_id: UUID
    product_id: UUID
    product_name: str
    description: str | None
    quantity: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_rate_percent: Decimal


class DebitNoteResponse(DebitNoteSchema):
    """Return one debit note."""

    id: UUID
    firm_id: UUID
    vendor_id: UUID
    vendor_name: str
    branch_id: UUID
    purchase_invoice_id: UUID
    purchase_invoice_number: str
    supplier_invoice_number: str
    debit_note_number: str
    debit_note_date: date
    reason: DebitNoteReasonEnum
    status: DebitNoteStatusEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    reference_number: str | None
    remarks: str | None
    cancel_reason: str | None
    journal_entry_id: UUID | None
    version: int
    lines: list[DebitNoteLineResponse]


class DebitNoteClaimableLine(DebitNoteSchema):
    """One line of a bill, and how much of it may still be claimed.

    What the editor offers: the line's taxable value as billed, what earlier
    debit notes and purchase returns have already taken off it, and the rate
    its tax was charged at.
    """

    purchase_invoice_line_id: UUID
    line_number: int
    product_id: UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    billed_taxable: Decimal
    already_claimed: Decimal
    already_returned: Decimal
    claimable: Decimal
    tax_rate_percent: Decimal


class DebitNoteRegisterRecord(DebitNoteSchema):
    """One debit note, as the register lists it."""

    debit_note_id: UUID
    debit_note_number: str
    debit_note_date: date
    vendor_id: UUID
    vendor_name: str
    purchase_invoice_id: UUID
    purchase_invoice_number: str
    reason: DebitNoteReasonEnum
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: DebitNoteStatusEnum


__all__ = [
    "DebitNoteCancel",
    "DebitNoteClaimableLine",
    "DebitNoteCreate",
    "DebitNoteLineResponse",
    "DebitNoteLineWrite",
    "DebitNoteReasonEnum",
    "DebitNoteRegisterRecord",
    "DebitNoteResponse",
    "DebitNoteSchema",
    "DebitNoteStatusEnum",
    "DebitNoteUpdate",
]
