"""Commission payout request and response schemas."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PayoutSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CommissionPayoutStatusEnum(StrEnum):
    """Where a payout has got to."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class CommissionPayoutAccrue(PayoutSchema):
    """Accrue what a period earned, for one salesman or for everybody.

    Omitting `salesman_id` accrues one payout per person who earned anything,
    which is the ordinary month-end action. Naming one accrues only theirs,
    which is what a correction after the fact needs.
    """

    period_start: date
    period_end: date
    #: Null accrues for everybody who earned something in the period.
    salesman_id: UUID | None = None
    #: The date the accrual is booked on, and the date its journal will carry.
    #: Defaults to the last day of the period, which is where the cost belongs
    #: -- booking it on the day somebody happened to run the accrual would put
    #: a March cost in whichever month the clerk got round to it.
    accrued_on: date | None = None

    @model_validator(mode="after")
    def _period_runs_forwards(self) -> "CommissionPayoutAccrue":
        """Refuse a period that ends before it starts.

        Returns:
            The validated payload.

        Raises:
            ValueError: If the period runs backwards.

        """
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be before period_start.")
        return self


class CommissionPayoutUpdate(PayoutSchema):
    """Adjust or annotate a payout that has not been approved.

    Every field is optional and the service dumps with ``exclude_unset``, so
    an omitted field means *leave it alone* while an explicit null still
    clears a reason.
    """

    adjustment_amount: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=2
    )
    adjustment_reason: str | None = None
    notes: str | None = None


class CommissionPaymentMethodEnum(StrEnum):
    """How the money left: the firm's cash box or its bank."""

    CASH = "CASH"
    BANK = "BANK"


class CommissionPayoutPay(PayoutSchema):
    """Record that an approved payout has been paid.

    Commission leaves through the firm's **cash or bank** account -- the ones
    it nominated under `firm_control_accounts`, exactly as a receipt or a
    payment resolves its own. Say which with `method`, or name the account
    with `money_account_id`; either way it has to be one of those two, so a
    payment can no longer land on Trade Receivables, on Sales, or on
    Commission Payable itself (D-TER-5).
    """

    paid_on: date
    #: CASH or BANK, resolved through the firm's control accounts.
    method: CommissionPaymentMethodEnum | None = None
    #: The cash or bank account the money left, for a client that names it.
    #: It must be the firm's CASH or BANK control account.
    money_account_id: UUID | None = None

    @model_validator(mode="after")
    def _says_where_the_money_left(self) -> "CommissionPayoutPay":
        """Require exactly one of the two ways of saying it.

        Returns:
            The validated payload.

        Raises:
            ValueError: If neither or both are given.

        """
        if (self.method is None) == (self.money_account_id is None):
            raise ValueError("Give either method (CASH or BANK) or money_account_id.")
        return self


class CommissionPayoutResponse(PayoutSchema):
    """Return one payout."""

    id: UUID
    salesman_id: UUID
    salesman_name: str
    period_start: date
    period_end: date
    basis: str
    measured_amount: Decimal
    earned_amount: Decimal
    adjustment_amount: Decimal
    adjustment_reason: str | None
    payable_amount: Decimal
    status: CommissionPayoutStatusEnum
    accrued_on: date
    paid_on: date | None
    money_account_id: UUID | None
    journal_entry_id: UUID | None
    payment_journal_entry_id: UUID | None
    notes: str | None
    version: int


__all__ = [
    "CommissionPaymentMethodEnum",
    "CommissionPayoutAccrue",
    "CommissionPayoutPay",
    "CommissionPayoutResponse",
    "CommissionPayoutStatusEnum",
    "CommissionPayoutUpdate",
    "PayoutSchema",
]
