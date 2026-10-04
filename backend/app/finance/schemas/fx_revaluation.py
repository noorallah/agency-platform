"""Request and response contracts for the period-end exchange revaluation.

PG-12 part A: open payables in another currency restated at the period end's
rate, posted as an unrealised gain or loss and reversed the next day.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FxRevaluationRequest(BaseModel):
    """The period end and the rate of each currency on it."""

    model_config = ConfigDict(extra="forbid")

    as_of: date
    #: Rupees per unit on ``as_of``, by ISO code, e.g. ``{"USD": 84.1}``. A
    #: currency left out is not revalued.
    rates: dict[str, Decimal] = Field(min_length=1, max_length=50)

    @field_validator("rates")
    @classmethod
    def _check_rates(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        """Key each rate by its upper-case ISO code; refuse one not above 0."""
        checked: dict[str, Decimal] = {}
        for code, rate in value.items():
            token = code.strip().upper()
            if len(token) != 3 or not token.isalpha():
                raise ValueError(f"{code} is not a three-letter currency code.")
            if token == "INR":
                raise ValueError("Rupees are the books' own currency.")
            if rate <= 0:
                raise ValueError(f"The rate for {token} must be above 0.")
            checked[token] = rate
        return checked


class FxRevaluationLine(BaseModel):
    """One open bill as it was restated."""

    invoice_id: UUID
    invoice_number: str
    vendor_id: UUID | None
    currency_code: str
    #: What the bill still owes in its currency.
    currency_outstanding: Decimal
    #: The rupees the books carry it at -- the bill's own rate.
    carried_amount: Decimal
    #: The rupees it is worth at the period end's rate.
    revalued_amount: Decimal
    #: Revalued less carried: a loss above zero, a gain below.
    difference: Decimal


class FxRevaluationResponse(BaseModel):
    """What one revaluation restated and the two journals it posted."""

    as_of: date
    reference: str
    lines: list[FxRevaluationLine]
    #: The net of every line: a loss above zero, a gain below.
    total_difference: Decimal
    #: Null when nothing moved, so nothing was posted.
    journal_entry_id: UUID | None = None
    reversal_journal_entry_id: UUID | None = None
