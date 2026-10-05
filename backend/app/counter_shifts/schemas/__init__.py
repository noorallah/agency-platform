"""Counter shift request and response schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.counter_shifts.models import CounterShiftStatus


class CounterShiftSchema(BaseModel):
    """Refuse unknown fields; read responses off plain values."""

    model_config = ConfigDict(extra="forbid")


class CounterShiftOpen(CounterShiftSchema):
    """Open the caller's till."""

    #: Blank takes the firm's default branch.
    branch_id: UUID | None = None
    #: The cash put in the drawer to give change from.
    opening_float: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=2
    )
    #: Blank takes the firm's cash control account.
    cash_account_id: UUID | None = None


class CounterShiftClose(CounterShiftSchema):
    """Close a till on what was counted in it."""

    counted_cash: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def _blank_note(cls, value: str | None) -> str | None:
        """Store a blank note as none."""
        return (value or "").strip() or None


class CounterShiftSummary(CounterShiftSchema):
    """What a shift took, derived from its bills on every read."""

    #: Bills approved in the shift and not cancelled since.
    bills: int = 0
    total_billed: Decimal = Decimal("0.00")
    #: What was received by mode -- CASH, UPI, CARD, BANK_TRANSFER, every key
    #: always present -- from the receipts that still stand.
    tenders: dict[str, Decimal] = Field(default_factory=dict)
    #: Bills this cashier parked during the shift that are still held: a
    #: warning at the close, never a refusal.
    held_bills: int = 0


class CounterShiftResponse(CounterShiftSchema):
    """One shift with what it took."""

    id: UUID
    version: int
    firm_id: UUID
    branch_id: UUID
    cashier_id: UUID
    cashier_name: str | None = None
    cash_account_id: UUID
    shift_number: str
    status: CounterShiftStatus
    opened_at: datetime
    opening_float: Decimal
    #: What the drawer should hold: the float and the cash tenders. Live
    #: while the shift is open; the figure the count was judged against once
    #: it is closed.
    expected_cash: Decimal
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    closed_by_name: str | None = None
    counted_cash: Decimal | None = None
    #: Counted less expected: negative is short, positive is over.
    difference: Decimal | None = None
    difference_journal_entry_id: UUID | None = None
    closing_note: str | None = None
    summary: CounterShiftSummary


__all__ = [
    "CounterShiftClose",
    "CounterShiftOpen",
    "CounterShiftResponse",
    "CounterShiftSummary",
]
