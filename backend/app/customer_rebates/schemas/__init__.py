"""Customer rebate request and response models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RebateSchema(BaseModel):
    """Strict input, ORM-friendly output."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class RebateSlabWrite(RebateSchema):
    """From this turnover, this rate on all of it."""

    threshold: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    rate_percent: Decimal = Field(gt=0, le=100, max_digits=7, decimal_places=4)


def _slabs_rise(slabs: list[RebateSlabWrite] | None) -> None:
    """Refuse two slabs at one threshold."""
    if slabs is None:
        return
    thresholds = [slab.threshold for slab in slabs]
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("Two slabs cannot start at the same turnover.")


class CustomerRebateCreate(RebateSchema):
    """Agree a rebate with one customer, or one customer group, for a period."""

    customer_id: UUID | None = None
    customer_group_id: UUID | None = None
    #: Thirty characters, not the column's forty: the accrual's journal
    #: reference is built from it and a reference holds fifty.
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    period_from: date
    period_to: date
    #: Whether it was promised before the supplies it rewards (s.15(3)(b)).
    agreed_before_sale: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    slabs: list[RebateSlabWrite] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _shape(self) -> "CustomerRebateCreate":
        """Refuse two parties or none, a backwards period, a repeated slab."""
        if (self.customer_id is None) == (self.customer_group_id is None):
            raise ValueError(
                "Name one customer or one customer group, not both and not neither."
            )
        if self.period_to < self.period_from:
            raise ValueError("The period must not end before it starts.")
        self.code = self.code.strip().upper()
        _slabs_rise(self.slabs)
        return self


class CustomerRebateUpdate(RebateSchema):
    """Change an agreement still counting. Absent fields are left alone.

    The party, the code and the status are not here: the party decides whose
    bills are counted, and the status belongs to cancel, accrue and reverse.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    period_from: date | None = None
    period_to: date | None = None
    agreed_before_sale: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    slabs: list[RebateSlabWrite] | None = Field(
        default=None, min_length=1, max_length=20
    )

    @model_validator(mode="after")
    def _shape(self) -> "CustomerRebateUpdate":
        """Refuse a repeated threshold."""
        _slabs_rise(self.slabs)
        return self


class RebateSlabResponse(RebateSchema):
    """One slab."""

    id: UUID
    line_number: int
    threshold: Decimal
    rate_percent: Decimal


class CustomerRebateResponse(RebateSchema):
    """One agreement, with where it stands."""

    id: UUID
    version: int
    customer_id: UUID | None
    customer_name: str | None
    customer_group_id: UUID | None
    customer_group_name: str | None
    code: str
    name: str
    period_from: date
    period_to: date
    status: str
    agreed_before_sale: bool
    notes: str | None
    slabs: list[RebateSlabResponse]
    #: Sales counted so far, and what they earn at the slab reached.
    turnover: Decimal
    rate_percent: Decimal
    earned: Decimal
    #: The next slab, and how much more must be sold to reach it.
    next_threshold: Decimal | None
    next_rate_percent: Decimal | None
    to_next: Decimal | None
    accrued_amount: Decimal | None
    accrual_journal_id: UUID | None
    accrued_at: datetime | None
    #: What approved rebate settlements have taken off the customer's
    #: account, and what is still to come.
    settled: Decimal
    to_settle: Decimal


class CustomerRebateAccrue(RebateSchema):
    """Book the rebate; the period must be over."""

    accrual_date: date | None = None


class RebateTurnoverRow(RebateSchema):
    """One customer's part of an agreement's turnover, by kind of document."""

    customer_id: UUID
    customer_name: str | None
    #: Approved bills at taxable value.
    invoiced: Decimal
    #: Completed sales returns at taxable value: off the turnover.
    returned: Decimal
    #: Approved credit notes at taxable value: off the turnover.
    credit_notes: Decimal
    #: Approved customer debit notes at taxable value: on to the turnover.
    debit_notes: Decimal
    turnover: Decimal


class RebateSettlementRow(RebateSchema):
    """One rebate settlement naming the agreement."""

    id: UUID
    adjustment_number: str
    adjustment_date: date
    customer_id: UUID | None
    customer_name: str | None
    amount: Decimal
    status: str


class CustomerRebateStatement(RebateSchema):
    """Where one agreement stands, and what it was built from."""

    agreement: CustomerRebateResponse
    #: The turnover as counted today, by customer -- one row for a customer's
    #: own agreement, one per member who traded for a group's. Live even
    #: after accrual, so a bill booked late into the period shows.
    customers: list[RebateTurnoverRow]
    invoiced: Decimal
    returned: Decimal
    credit_notes: Decimal
    debit_notes: Decimal
    #: The same four figures netted: what the period comes to today. It is
    #: `agreement.turnover` until accrual, which keeps what was booked.
    turnover_today: Decimal
    #: Approved and cancelled settlements, newest first.
    settlements: list[RebateSettlementRow]
    #: What the firm's CA needs to know before raising a GST credit note.
    gst_note: str


class CustomerRebateStatementRow(RebateSchema):
    """One agreement on the report of accrued and settled rebates."""

    id: UUID
    code: str
    name: str
    #: The customer's name, or the group's.
    party_name: str | None
    is_group: bool
    period_from: date
    period_to: date
    status: str
    agreed_before_sale: bool
    #: The same, in words a report column can show.
    agreed_label: str
    turnover: Decimal
    rate_percent: Decimal
    earned: Decimal
    accrued: Decimal
    settled: Decimal
    balance: Decimal


__all__ = [
    "CustomerRebateAccrue",
    "CustomerRebateCreate",
    "CustomerRebateResponse",
    "CustomerRebateStatement",
    "CustomerRebateStatementRow",
    "CustomerRebateUpdate",
    "RebateSettlementRow",
    "RebateSlabResponse",
    "RebateSlabWrite",
    "RebateTurnoverRow",
]
