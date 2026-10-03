"""Post-dated cheque request and response schemas (backlog 42.3, ACC-2)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.settlements.schemas import SettlementAllocationWrite, SettlementSchema


class PostDatedChequeStatusEnum(StrEnum):
    """Where a post-dated cheque has got to."""

    HELD = "HELD"
    DEPOSITED = "DEPOSITED"
    CLEARED = "CLEARED"
    BOUNCED = "BOUNCED"
    CANCELLED = "CANCELLED"


class PostDatedChequeCreate(SettlementSchema):
    """Record a cheque dated ahead. Nothing is posted until it is banked."""

    party_id: UUID
    cheque_number: str = Field(min_length=1, max_length=30)
    cheque_date: date
    drawn_on_bank: str | None = Field(default=None, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    #: The day the cheque was taken in, or handed over.
    received_on: date
    narration: str | None = Field(default=None, max_length=2000)


class PostDatedChequeDeposit(SettlementSchema):
    """Bank a held cheque, which records it as a receipt or payment."""

    #: The day it was paid in (or presented); not before the cheque's date.
    deposited_on: date
    #: The bills the money clears. Blank leaves it on account, to be applied
    #: later like any advance.
    allocations: list[SettlementAllocationWrite] = Field(default_factory=list)


class PostDatedChequeClear(SettlementSchema):
    """Record that the bank honoured a deposited cheque."""

    cleared_on: date


class PostDatedChequeBounce(SettlementSchema):
    """Record that the bank returned a deposited cheque."""

    bounced_on: date
    reason: str = Field(min_length=1, max_length=500)
    #: What the firm's own bank charged for the return. Blank or 0 is none.
    bank_charges_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: What the firm charges the customer for it; a customer's cheque only.
    customer_charge_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )


class PostDatedChequeCancel(SettlementSchema):
    """Cancel a held cheque: handed back, or replaced by another."""

    reason: str = Field(min_length=1, max_length=500)


class PostDatedChequeResponse(SettlementSchema):
    """One post-dated cheque and where it has got to."""

    id: UUID
    firm_id: UUID
    direction: str
    party_id: UUID
    party_code: str
    party_name: str
    cheque_number: str
    cheque_date: date
    drawn_on_bank: str | None
    amount: Decimal
    received_on: date
    narration: str | None
    status: PostDatedChequeStatusEnum
    #: Held, and its date has come: it can be banked today.
    is_due: bool
    settlement_id: UUID | None
    settlement_number: str | None
    deposited_on: date | None
    cleared_on: date | None
    bounced_on: date | None
    bounce_reason: str | None
    bank_charges_amount: Decimal
    customer_charge_amount: Decimal
    charges_journal_entry_id: UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime
