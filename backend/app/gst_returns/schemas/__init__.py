"""GST settlement request and response schemas (backlog 63)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GstSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class GstHeadRow(GstSchema):
    """One head of a month's settlement: owed, credit, paid, carried."""

    #: IGST, CGST, SGST or CESS.
    head: str
    liability: Decimal
    credit_brought_forward: Decimal
    credit_available: Decimal
    paid_by_credit: Decimal
    cash: Decimal
    credit_used: Decimal
    carried_forward: Decimal
    #: Reverse charge on inward supplies (3.1(d)): paid in cash only, never
    #: by credit, on top of `cash` (backlog 68 row 8).
    reverse_charge: Decimal = Decimal("0")


class GstUtilisationRow(GstSchema):
    """How much of one head's credit paid one head's liability."""

    credit_head: str
    liability_head: str
    amount: Decimal


class GstPaymentPreviewResponse(GstSchema):
    """What a month owes, what its credit pays, what is left to pay in cash."""

    return_period: str
    due_date: date
    #: False when no settlement of the month before is recorded, so the
    #: brought-forward credit is what was stated as the opening credit.
    previous_settled: bool
    days_late: int
    #: Section 50 interest at 18% a year on the cash, for the days late.
    suggested_interest: Decimal
    cash_total: Decimal
    heads: list[GstHeadRow]
    utilisation: list[GstUtilisationRow]


class GstPaymentCreate(GstSchema):
    """Record a month's challan: the set-off and the cash paid."""

    return_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    payment_date: date
    money_account_id: UUID
    challan_cpin: str | None = Field(default=None, max_length=20)
    challan_cin: str | None = Field(default=None, max_length=30)
    interest_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    interest_account_id: UUID | None = None
    late_fee_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    late_fee_account_id: UUID | None = None
    #: The credit brought forward on the firm's first month here, from the
    #: portal's electronic credit ledger. Ignored once a month is recorded.
    opening_credit_igst: Decimal | None = Field(default=None, ge=0)
    opening_credit_cgst: Decimal | None = Field(default=None, ge=0)
    opening_credit_sgst: Decimal | None = Field(default=None, ge=0)
    opening_credit_cess: Decimal | None = Field(default=None, ge=0)
    narration: str | None = Field(default=None, max_length=2000)


class GstPaymentReverse(GstSchema):
    """Why a month's settlement is being taken back."""

    reason: str = Field(min_length=1, max_length=500)


class GstPaymentResponse(GstSchema):
    """One recorded month's settlement."""

    id: UUID
    return_period: str
    payment_date: date
    status: str
    challan_cpin: str | None
    challan_cin: str | None
    money_account_id: UUID
    heads: list[GstHeadRow]
    cash_total: Decimal
    interest_amount: Decimal
    late_fee_amount: Decimal
    narration: str | None
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    reversal_reason: str | None
    reversed_at: datetime | None
    version: int


__all__ = [
    "GstHeadRow",
    "GstPaymentCreate",
    "GstPaymentPreviewResponse",
    "GstPaymentResponse",
    "GstPaymentReverse",
    "GstUtilisationRow",
]
