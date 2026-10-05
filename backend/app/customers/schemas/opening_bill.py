"""API contracts for what customers owed on the firm's first day here."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.customers.schemas.customer import CustomerSchema


class CustomerOpeningBillWrite(CustomerSchema):
    """One bill a customer owed at cutover."""

    #: The bill's number as the old books held it.
    reference_number: str | None = Field(default=None, max_length=60)
    bill_date: date
    #: Omitted, the bill date plus the customer's payment terms.
    due_date: date | None = None
    #: The day the firm's books here start. Omitted, it is today.
    posting_date: date | None = None
    #: What was still owed on the bill at cutover.
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    narration: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates_in_order(self) -> "CustomerOpeningBillWrite":
        """Refuse a bill due before it was raised, or raised after cutover."""
        if self.due_date is not None and self.due_date < self.bill_date:
            raise ValueError("A bill cannot fall due before its own date.")
        if self.posting_date is not None and self.bill_date > self.posting_date:
            raise ValueError(
                "An opening bill is one raised before the books here start, so "
                "its date cannot be after the posting date."
            )
        return self


class CustomerOpeningBillImportRow(CustomerOpeningBillWrite):
    """One opening bill in a file, naming its customer by code."""

    customer_code: str = Field(min_length=1, max_length=50)


class CustomerOpeningBillImportRequest(CustomerSchema):
    """A batch of opening bills, written all together or not at all."""

    records: list[CustomerOpeningBillImportRow] = Field(min_length=1, max_length=1000)


class CustomerOpeningBillCancel(CustomerSchema):
    """Why an opening bill is being taken back."""

    reason: str = Field(min_length=1, max_length=500)


class CustomerOpeningBillResponse(CustomerSchema):
    """One opening bill, with what has been received against it since."""

    id: UUID
    customer_id: UUID
    customer_code: str
    customer_name: str
    bill_number: str
    reference_number: str | None
    bill_date: date
    due_date: date | None
    posting_date: date
    amount: Decimal
    received_amount: Decimal
    outstanding_amount: Decimal
    narration: str | None
    status: str
    journal_entry_id: UUID
    #: True for the bill that stands for the opening balance typed on the
    #: customer: it is changed there, and cannot be cancelled here.
    covers_master_balance: bool = False
    cancelled_at: datetime | None
    cancellation_reason: str | None
    version: int
    created_at: datetime
