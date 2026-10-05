"""Collection follow-up request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CollectionSchema(BaseModel):
    """Refuse unknown fields; read responses off plain values."""

    model_config = ConfigDict(extra="forbid")


class PromiseStatus(StrEnum):
    """What became of a promise. Derived on every read, never stored."""

    #: Its day has not come and the money has not arrived.
    PENDING = "PENDING"
    #: Promised for today and not yet paid.
    DUE_TODAY = "DUE_TODAY"
    #: The receipts dated from the day it was taken to the day it was
    #: promised for cover the amount.
    KEPT = "KEPT"
    #: Its day has passed and they do not.
    BROKEN = "BROKEN"
    #: Taken back; the row stays as history.
    WITHDRAWN = "WITHDRAWN"


class PaymentPromiseCreate(CollectionSchema):
    """Record what a customer promised to pay, and by when."""

    customer_id: UUID
    #: The bill the promise is for; blank is a promise for the account.
    sales_invoice_id: UUID | None = None
    #: The day the payment is promised for; today or later.
    promised_on: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)
    #: Who took the promise; blank takes the customer's collector.
    collector_id: UUID | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _blank_note(cls, value: str | None) -> str | None:
        """Store a blank note as none."""
        return (value or "").strip() or None


class PaymentPromiseWithdraw(CollectionSchema):
    """Take a promise back, saying why."""

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _trim_reason(cls, value: str) -> str:
        """Drop the spaces around the reason, so a blank one is refused."""
        return value.strip() if isinstance(value, str) else value


class PaymentPromiseResponse(CollectionSchema):
    """One promise, with what became of it."""

    id: UUID
    customer_id: UUID
    customer_code: str
    customer_name: str
    sales_invoice_id: UUID | None
    #: The bill's number; null for a promise on the account.
    invoice_number: str | None
    promised_on: date
    amount: Decimal
    #: What the bill -- or, for an account promise, the customer -- paid in
    #: receipts dated from ``recorded_on`` to ``promised_on``.
    received_amount: Decimal
    status: PromiseStatus
    note: str | None
    recorded_on: date
    recorded_by: UUID
    recorded_by_name: str
    collector_id: UUID | None
    collector_name: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    version: int


class CollectionSheetRow(CollectionSchema):
    """One bill a collector is to chase."""

    #: The customer's collector, else its account manager; null is nobody.
    collector_id: UUID | None
    collector_name: str | None
    customer_id: UUID
    customer_code: str
    customer_name: str
    customer_phone: str | None
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    due_date: date | None
    #: Days past the due date on the sheet's day; 0 for a bill not yet due.
    days_overdue: int
    invoice_total: Decimal
    outstanding: Decimal
    #: A bill owed from before the firm started here, not a sales invoice.
    is_opening_bill: bool
    #: The latest live promise on the bill, else on the customer's account.
    promise_id: UUID | None
    promised_on: date | None
    promised_amount: Decimal | None
    promise_status: PromiseStatus | None
    promise_note: str | None
    #: True where that promise is for the account rather than this bill.
    promise_is_for_account: bool


__all__ = [
    "CollectionSheetRow",
    "PaymentPromiseCreate",
    "PaymentPromiseResponse",
    "PaymentPromiseWithdraw",
    "PromiseStatus",
]
