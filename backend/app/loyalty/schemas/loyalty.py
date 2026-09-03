"""Request and response models for the loyalty ledger."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoyaltySchema(BaseModel):
    """Shared configuration for every loyalty payload."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LoyaltyEntryKindEnum(StrEnum):
    """Why points moved."""

    EARNED = "EARNED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    ADJUSTED = "ADJUSTED"
    REVERSED = "REVERSED"


class LoyaltySettingsWrite(LoyaltySchema):
    """Change a firm's scheme.

    Every field is optional and the service dumps with ``exclude_unset``, so an
    omitted field means *leave it alone* -- a write model that dumps in full
    turns an omission into an instruction, and here it would silently reset a
    conversion rate a firm had agreed with its customers.
    """

    is_enabled: bool | None = None
    points_per_amount: Decimal | None = Field(default=None, ge=0, max_digits=12)
    amount_per_point: Decimal | None = Field(default=None, ge=0, max_digits=12)
    minimum_redemption_points: int | None = Field(default=None, ge=0)
    #: Explicitly null means points do not expire, which is a real choice.
    #: Zero would mean they expire the day they are earned.
    expiry_months: int | None = Field(default=None, ge=1, le=600)


class LoyaltySettingsResponse(LoyaltySchema):
    """A firm's scheme as it stands."""

    is_enabled: bool
    points_per_amount: Decimal
    amount_per_point: Decimal
    minimum_redemption_points: int
    expiry_months: int | None


class LoyaltyEntryResponse(LoyaltySchema):
    """One movement of a customer's credit."""

    id: UUID
    customer_id: UUID
    customer_name: str | None = None
    kind: LoyaltyEntryKindEnum
    #: Signed: positive earns, negative spends.
    points: Decimal
    amount: Decimal
    sales_invoice_id: UUID | None = None
    sales_invoice_number: str | None = None
    earned_on: date
    expires_on: date | None = None
    remarks: str | None = None


class LoyaltyBalance(LoyaltySchema):
    """What a customer holds, and what they could spend today."""

    customer_id: UUID
    customer_name: str | None = None
    #: The sum of the ledger. Derived, never stored: a balance column would be
    #: a second copy of the entries, wrong the first time anything wrote one
    #: without going through the service.
    points: Decimal
    #: What those points are worth at today's rate. The rate changes, so this
    #: is what they would fetch now rather than what they were worth when
    #: earned -- which is why every entry stores its own amount.
    amount: Decimal
    #: False where the balance is below the firm's floor, so a screen can say
    #: "not yet" rather than offering a redemption the service refuses.
    redeemable: bool
    #: Points that will lapse within ninety days, so a customer can be told
    #: before rather than after.
    expiring_soon: Decimal


class LoyaltyRedeem(LoyaltySchema):
    """Spend credit against a bill."""

    sales_invoice_id: UUID
    #: How many points to spend. The service caps it at what the balance holds
    #: and at what the invoice still owes, and refuses rather than silently
    #: trimming -- a customer told their points cleared a bill and finding
    #: otherwise is worse than being refused.
    points: Decimal = Field(gt=0, max_digits=18)


class LoyaltyAdjust(LoyaltySchema):
    """Correct a balance by hand, saying why."""

    customer_id: UUID
    #: Signed. A goodwill gesture is positive; taking back points credited in
    #: error is negative.
    points: Decimal = Field(max_digits=18)
    reason: str = Field(min_length=1, max_length=500)
