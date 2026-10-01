"""Contra voucher request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContraSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ContraKindEnum(StrEnum):
    """Which way the money went."""

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH_TRANSFER = "CASH_TRANSFER"


class ContraStatusEnum(StrEnum):
    """Posted, or cancelled by a mirror."""

    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class MoneyAccountKindEnum(StrEnum):
    """Whether a money account holds cash or is a bank account."""

    CASH = "CASH"
    BANK = "BANK"


class ContraVoucherCreate(ContraSchema):
    """Record money moved between two of the firm's own accounts."""

    voucher_date: date
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference: str | None = Field(default=None, max_length=120)
    remarks: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _two_accounts(self) -> "ContraVoucherCreate":
        """Refuse money moved from an account to itself."""
        if self.from_account_id == self.to_account_id:
            raise ValueError("The money has to move between two different accounts.")
        return self


class ContraVoucherCancel(ContraSchema):
    """Carry why a contra voucher is taken back."""

    reason: str = Field(min_length=1, max_length=500)


class MoneyAccountRecord(ContraSchema):
    """One account money can be moved into or out of."""

    id: UUID
    code: str
    name: str
    kind: MoneyAccountKindEnum


class ContraVoucherResponse(ContraSchema):
    """Return one contra voucher."""

    id: UUID
    voucher_number: str
    voucher_date: date
    kind: ContraKindEnum
    status: ContraStatusEnum
    from_account_id: UUID
    from_account_code: str
    from_account_name: str
    to_account_id: UUID
    to_account_code: str
    to_account_name: str
    amount: Decimal
    reference: str | None
    remarks: str | None
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    created_by: UUID | None
    created_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str | None
    #: Set only on the response to a save or a cancel: the account the money
    #: left would stand below zero on the voucher's date. A warning, not a
    #: refusal -- the books may simply be behind (a receipt not yet keyed).
    balance_warning: str | None = None
    version: int


class ContraRegisterRecord(ContraSchema):
    """One row of the contra register."""

    voucher_id: UUID
    voucher_number: str
    voucher_date: date
    kind: ContraKindEnum
    status: ContraStatusEnum
    from_account_name: str
    to_account_name: str
    amount: Decimal
    reference: str | None
    remarks: str | None


__all__ = [
    "ContraKindEnum",
    "ContraRegisterRecord",
    "ContraSchema",
    "ContraStatusEnum",
    "ContraVoucherCancel",
    "ContraVoucherCreate",
    "ContraVoucherResponse",
    "MoneyAccountKindEnum",
    "MoneyAccountRecord",
]
