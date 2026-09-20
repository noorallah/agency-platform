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


class SalesTargetUpdate(SalesTargetSchema):
    """Change some of one target.

    Every field is optional and none has a default, and the service dumps
    this with ``exclude_unset=True``: **absent means leave alone, and an
    explicit ``null`` still clears.** The write model above was used for
    updates until D-TER-8, and its defaults -- ``None``, ``None``, MONTHLY,
    INVOICED, ACTIVE -- turned every omission into an instruction: a PUT
    naming only the dates and the amount cleared the person the target was
    for, made it the firm's own number, and stopped their bonus.

    Only the three nullable columns -- the person, the round and the notes
    -- can be cleared by ``null``; the service refuses ``null`` for the
    rest, because a target with no period, basis or amount is not a target.
    The period is checked for order on the **merged** row, since a body
    moving only the end date has nothing of its own to compare against.

    ``status`` stays writable here. It is a plain flag -- in force or not --
    with no transition endpoint of its own and nothing that reads it but the
    achievement report, and the desktop's editor sends it on every save.
    """

    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_type: SalesTargetPeriod | None = None
    basis: SalesTargetBasis | None = None
    target_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    notes: str | None = None
    status: str | None = Field(default=None, max_length=20)


class SalesTargetResponse(SalesTargetSchema):
    """Expose one stored target."""

    id: UUID
    salesman_id: UUID | None
    salesman_name: str | None
    territory_id: UUID | None
    territory_code: str | None
    territory_name: str | None
    #: Who the target is for, ready to print: the person, the territory by
    #: code and name, both, or "Whole firm". A client that derived this from
    #: `salesman_name` alone called every territory target the firm's own.
    scope_label: str
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
    #: The person's name, or the scope label where the target names none:
    #: the column older clients print under "For".
    salesman_name: str
    territory_id: UUID | None
    territory_code: str | None
    territory_name: str | None
    #: Who the target is for, ready to print -- see `SalesTargetResponse`.
    scope_label: str
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
