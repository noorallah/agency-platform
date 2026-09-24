"""Request and response models for tax collected at source."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TcsSchema(BaseModel):
    """Shared configuration for every TCS payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TcsSettingsWrite(TcsSchema):
    """Change a firm's TCS policy.

    Every field is optional and the service dumps with ``exclude_unset``, so
    an omitted field means *leave it alone*. A write model that dumps in full
    turns an omission into an instruction, which has shipped in this repo
    often enough to be a rule -- and here it would silently reset a rate or a
    threshold that a Finance Act had moved.
    """

    is_enabled: bool | None = None
    threshold_amount: Decimal | None = Field(default=None, ge=0, max_digits=18)
    rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    rate_without_pan_percent: Decimal | None = Field(default=None, ge=0, le=100)
    preceding_year_turnover: Decimal | None = Field(default=None, ge=0, max_digits=18)
    seller_turnover_threshold: Decimal | None = Field(default=None, ge=0, max_digits=18)


class TcsSettingsResponse(TcsSchema):
    """A firm's TCS policy as it stands."""

    section_code: str
    is_enabled: bool
    threshold_amount: Decimal
    rate_percent: Decimal
    rate_without_pan_percent: Decimal
    preceding_year_turnover: Decimal
    seller_turnover_threshold: Decimal
    #: Whether the stated turnover puts the firm in scope at all. Derived
    #: rather than stored: it is a comparison of two columns on this row, and
    #: storing it would let the two disagree.
    seller_in_scope: bool


class TcsBuyerPosition(TcsSchema):
    """One buyer's year: what the section made due against what was charged.

    Collections are never rewritten, so after a reversal or a back-dated
    receipt a buyer can stand over- or under-collected until their next
    receipt squares it (D-CMP-16). This is where that shows (D-CMP-21).
    """

    customer_id: UUID
    customer_code: str
    customer_name: str
    financial_year_start: date
    #: Consideration received in the year: receipts net of refunds and of the
    #: part that paid tax already collected.
    consideration_received: Decimal
    threshold_amount: Decimal
    #: What the section made chargeable -- the excess over the threshold,
    #: counting only receipts dated while the section stood.
    taxable_due: Decimal
    rate_percent: Decimal
    tcs_due: Decimal
    #: What standing collections charged, on what.
    taxable_charged: Decimal
    tcs_charged: Decimal
    #: Charged less due: above zero is over-collected, below is short.
    difference: Decimal
    #: OVER, SHORT or SQUARE.
    position: str


class TcsCollectionResponse(TcsSchema):
    """One receipt's worth of tax collected, and why it came to that."""

    id: UUID
    customer_id: UUID
    customer_name: str | None = None
    settlement_id: UUID
    settlement_number: str | None = None
    financial_year_start: date
    collected_on: date
    consideration_amount: Decimal
    cumulative_before: Decimal
    taxable_amount: Decimal
    rate_percent: Decimal
    without_pan: bool
    tcs_amount: Decimal
    status: str
    journal_entry_id: UUID | None = None
    reversal_journal_entry_id: UUID | None = None
    version: int = 0


class TcsPreview(TcsSchema):
    """What a receipt of a given size would attract, before it is recorded.

    The answer to "how much do I ask this buyer for" has to be available
    *before* the receipt exists, or the figure is only ever discovered after
    the money has been taken.
    """

    applicable: bool
    #: Why not, where it is not. A blank string would leave a salesman with a
    #: zero and no way to tell a buyer under the threshold from a firm that
    #: has not switched the section on.
    reason: str
    financial_year_start: date
    cumulative_before: Decimal
    threshold_amount: Decimal
    taxable_amount: Decimal
    rate_percent: Decimal
    without_pan: bool
    tcs_amount: Decimal
