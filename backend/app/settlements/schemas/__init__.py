"""Settlement request and response schemas."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettlementSchema(BaseModel):
    """Apply strict input and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SettlementDirectionEnum(StrEnum):
    """Which way the money went."""

    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"


class SettlementMethodEnum(StrEnum):
    """How the money moved."""

    CASH = "CASH"
    BANK = "BANK"


class SettlementAllocationWrite(SettlementSchema):
    """Allocate part of a settlement to one invoice."""

    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class SettlementReverseRequest(SettlementSchema):
    """Carry why a settlement was taken back."""

    reason: str | None = Field(default=None, max_length=500)


class SettlementCreate(SettlementSchema):
    """Record one receipt or payment that has already happened."""

    party_id: UUID
    settlement_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: SettlementMethodEnum
    instrument_reference: str | None = Field(default=None, max_length=120)
    narration: str | None = Field(default=None, max_length=2000)
    settlement_number: str | None = Field(default=None, max_length=60)
    allocations: list[SettlementAllocationWrite] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_row_per_invoice(self) -> "SettlementCreate":
        """Refuse the same invoice twice in one settlement.

        Two lines against one invoice are one allocation. Accepting both would
        make the invoice's outstanding depend on how somebody typed it, and the
        database refuses it anyway -- better to say so in the language of the
        request than as a constraint violation.
        """
        seen = {allocation.invoice_id for allocation in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("An invoice can appear only once in one settlement.")
        return self


class SettlementAllocationResponse(SettlementSchema):
    """Return one allocation with the invoice it cleared."""

    id: UUID
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    invoice_total: Decimal
    amount: Decimal


class SettlementResponse(SettlementSchema):
    """Return one settlement."""

    id: UUID
    direction: SettlementDirectionEnum
    party_id: UUID
    party_code: str
    party_name: str
    settlement_number: str
    settlement_date: date
    amount: Decimal
    allocated_amount: Decimal
    unallocated_amount: Decimal
    method: SettlementMethodEnum
    ledger_account_id: UUID
    ledger_account_name: str
    instrument_reference: str | None
    narration: str | None
    status: str
    journal_entry_id: UUID
    reversal_journal_entry_id: UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None
    allocations: list[SettlementAllocationResponse]
    version: int


class OutstandingInvoiceRecord(SettlementSchema):
    """Return one invoice with what is still owed on it.

    `outstanding_amount` is the invoice total less everything allocated to it,
    derived rather than stored. A stored paid-to-date column is a second copy
    of the allocations and drifts the first time one is written outside the
    service that maintains it.
    """

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    invoice_total: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal


__all__ = [
    "OutstandingInvoiceRecord",
    "SettlementAllocationResponse",
    "SettlementAllocationWrite",
    "SettlementCreate",
    "SettlementDirectionEnum",
    "SettlementMethodEnum",
    "SettlementResponse",
    "SettlementReverseRequest",
    "SettlementSchema",
]
