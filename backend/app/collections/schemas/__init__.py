"""Collection follow-up request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class HandoverState(StrEnum):
    """Where a handed-out bill is. Read off ``returned_at``, never stored."""

    #: With the collector.
    OUT = "OUT"
    #: Taken back; the row stays as history.
    RETURNED = "RETURNED"


class HandedFilter(StrEnum):
    """Which unpaid bills to list, by whether somebody carries them."""

    ALL = "ALL"
    #: Out with a collector.
    OUT = "OUT"
    #: In the office: free to hand out.
    NOT_OUT = "NOT_OUT"


class HandoverMatching(CollectionSchema):
    """Name a bundle of unpaid bills by what they have in common.

    At least one of the fields: nothing named would be every unpaid bill of
    the firm, which is never what was meant.
    """

    #: Bills dated from this day ...
    date_from: date | None = None
    #: ... to this day, both counted.
    date_to: date | None = None
    #: Part of the customer's area or city, any case.
    area: str | None = Field(default=None, max_length=100)
    #: A run of bill numbers of one series, both ends counted.
    number_from: str | None = Field(default=None, max_length=60)
    number_to: str | None = Field(default=None, max_length=60)
    customer_id: UUID | None = None

    @field_validator("area", "number_from", "number_to", mode="before")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """Read a blank box as nothing asked."""
        return (value.strip() or None) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _names_something(self) -> "HandoverMatching":
        """Refuse a bundle that names nothing, and a period that ends early."""
        if not self.model_dump(exclude_none=True):
            raise ValueError(
                "Say which bills: a date, an area, a customer or bill numbers."
            )
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("The last day is before the first.")
        return self


class HandoverCreate(CollectionSchema):
    """Hand unpaid bills to a collector: the ones ticked, or a bundle."""

    collector_id: UUID
    #: The day they go out; the firm's today when omitted, never later.
    handed_on: date | None = None
    #: The bills ticked. Every one must owe something and be in the office.
    invoice_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=2000)
    #: Or the bundle by date, area, customer or a run of numbers. Bills of it
    #: already out with somebody are left with them and counted.
    matching: HandoverMatching | None = None

    @model_validator(mode="after")
    def _one_way_of_naming(self) -> "HandoverCreate":
        """Take the ticked bills or a bundle, never both and never neither."""
        if (self.invoice_ids is None) == (self.matching is None):
            raise ValueError("Send the bills ticked or a bundle to match, one of them.")
        return self


class HandoverTakeBack(CollectionSchema):
    """Take handed-out bills back into the office."""

    handover_ids: list[UUID] = Field(min_length=1, max_length=2000)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def _blank_note(cls, value: str | None) -> str | None:
        """Store a blank note as none."""
        return (value or "").strip() or None


class HandoverBillRow(CollectionSchema):
    """One unpaid bill, and who carries it if anybody does."""

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    due_date: date | None
    #: Days past the due date today; 0 for a bill not yet due.
    days_overdue: int
    #: A bill owed from before the firm started here, not a sales invoice.
    is_opening_bill: bool
    customer_id: UUID
    customer_code: str
    customer_name: str
    #: "Area, City" of the customer's billing address; blank where it has none.
    customer_place: str
    invoice_total: Decimal
    outstanding: Decimal
    #: The live handover; null for a bill in the office.
    handover_id: UUID | None
    collector_id: UUID | None
    collector_name: str | None
    handed_on: date | None


class MyBillRow(CollectionSchema):
    """One unpaid bill on a collector's own list (backlog 123).

    Either a bill handed to them, or another unpaid bill of a customer whose
    bill they carry, which is listed so they can ask for it at the same door
    and is marked apart: it is not in their bag.
    """

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    due_date: date | None
    #: Days past the due date today; 0 for a bill not yet due.
    days_overdue: int
    #: A bill owed from before the firm started here, not a sales invoice.
    is_opening_bill: bool
    customer_id: UUID
    customer_code: str
    customer_name: str
    #: "Area, City" of the customer's billing address; blank where it has none.
    customer_place: str
    invoice_total: Decimal
    outstanding: Decimal
    #: True for a bill handed to the reader; false for the customer's others.
    handed_to_me: bool
    #: The reader's own handover and its day; null on the customer's others.
    handover_id: UUID | None
    handed_on: date | None


class HandoverResponse(CollectionSchema):
    """One bill handed to one collector, out or taken back."""

    id: UUID
    state: HandoverState
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    is_opening_bill: bool
    customer_id: UUID
    customer_code: str
    customer_name: str
    customer_place: str
    collector_id: UUID
    collector_name: str
    handed_on: date
    handed_by: UUID
    handed_by_name: str
    #: What the bill owed as it went out.
    outstanding_at_handover: Decimal
    #: What it owes now, from the receipts; 0.00 once paid.
    outstanding: Decimal
    returned_at: datetime | None
    returned_by_name: str | None
    return_note: str | None
    version: int


class HandoverResult(CollectionSchema):
    """What handing out, or taking back, did."""

    #: Bills that changed hands in this request.
    bills: int
    #: What those bills owed at that moment, together.
    amount: Decimal
    #: Bills of a matched bundle left where they were: already out.
    already_out: int = 0


__all__ = [
    "CollectionSheetRow",
    "HandedFilter",
    "HandoverBillRow",
    "HandoverCreate",
    "HandoverMatching",
    "HandoverResponse",
    "HandoverResult",
    "HandoverState",
    "HandoverTakeBack",
    "MyBillRow",
    "PaymentPromiseCreate",
    "PaymentPromiseResponse",
    "PaymentPromiseWithdraw",
    "PromiseStatus",
]
