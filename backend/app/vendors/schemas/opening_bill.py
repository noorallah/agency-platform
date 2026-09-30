"""API contracts for what suppliers were owed on the firm's first day here."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.vendors.schemas.vendor import VendorSchema


class VendorOpeningBillWrite(VendorSchema):
    """One bill a supplier was owed at cutover."""

    #: The supplier's own bill number, as the old books held it.
    reference_number: str | None = Field(default=None, max_length=60)
    bill_date: date
    due_date: date | None = None
    #: The day the firm's books here start. Omitted, it is today.
    posting_date: date | None = None
    #: What was still owed on the bill at cutover.
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    narration: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates_in_order(self) -> "VendorOpeningBillWrite":
        """Refuse a bill due before it was raised, or raised after cutover."""
        if self.due_date is not None and self.due_date < self.bill_date:
            raise ValueError("A bill cannot fall due before its own date.")
        if self.posting_date is not None and self.bill_date > self.posting_date:
            raise ValueError(
                "An opening bill is one raised before the books here start, so "
                "its date cannot be after the posting date."
            )
        return self


class VendorOpeningBillImportRow(VendorOpeningBillWrite):
    """One opening bill in a file, naming its supplier by code."""

    vendor_code: str = Field(min_length=1, max_length=50)


class VendorOpeningBillImportRequest(VendorSchema):
    """A batch of opening bills, written all together or not at all."""

    records: list[VendorOpeningBillImportRow] = Field(min_length=1, max_length=1000)


class VendorOpeningBillCancel(VendorSchema):
    """Why an opening bill is being taken back."""

    reason: str = Field(min_length=1, max_length=500)


class VendorOpeningBillResponse(VendorSchema):
    """One opening bill, with what has been paid against it since."""

    id: UUID
    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    bill_number: str
    reference_number: str | None
    bill_date: date
    due_date: date | None
    posting_date: date
    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    narration: str | None
    status: str
    journal_entry_id: UUID
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_at: datetime
