"""Validated contracts for sales targets."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SalesTargetSchema(BaseModel):
    """Apply strict input and ORM response behavior."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SalesTargetPeriod(StrEnum):
    """How long a target runs for.

    A label for reading and grouping. The dates on the row are what is
    measured, because a firm's quarter does not always start where the
    calendar's does.
    """

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class SalesTargetBasis(StrEnum):
    """What a firm counts as having been sold.

    Firms genuinely differ, which is why this is configuration: one measures a
    salesman on what they sold, another on what they were paid for.
    """

    INVOICED = "INVOICED"
    COLLECTED = "COLLECTED"


class SalesTargetWrite(SalesTargetSchema):
    """Set one target."""

    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    period_start: date
    period_end: date
    period_type: SalesTargetPeriod = SalesTargetPeriod.MONTHLY
    basis: SalesTargetBasis = SalesTargetBasis.INVOICED
    target_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    notes: str | None = None
    status: str = Field(default="ACTIVE", max_length=20)

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "SalesTargetWrite":
        """Refuse a period that ends before it starts."""
        if self.period_end < self.period_start:
            raise ValueError("A target cannot end before it starts.")
        return self


class SalesTargetResponse(SalesTargetSchema):
    """Expose one stored target."""

    id: UUID
    salesman_id: UUID | None
    salesman_name: str | None
    territory_id: UUID | None
    period_start: date
    period_end: date
    period_type: str
    basis: str
    target_amount: Decimal
    notes: str | None
    status: str
    version: int


class SalesTargetAchievement(SalesTargetSchema):
    """One target, and what actually happened against it."""

    target_id: UUID
    salesman_id: UUID | None
    salesman_name: str
    territory_id: UUID | None
    period_start: date
    period_end: date
    period_type: str
    basis: str
    target_amount: Decimal
    achieved_amount: Decimal
    #: What is left to sell, floored at zero -- a target beaten is not a
    #: shortfall of a negative amount, and a report that says so reads wrong.
    shortfall_amount: Decimal
    achieved_percent: Decimal
