"""Contracts for payment runs (BUY-11, decision A110)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentRunLineWrite(BaseModel):
    """One bill to pay; blank amount pays what it still owes."""

    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)


class PaymentRunWrite(BaseModel):
    """Keep or change a draft run: the whole list of bills."""

    model_config = ConfigDict(extra="forbid")

    payment_date: date
    due_by: date | None = None
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[PaymentRunLineWrite] = Field(min_length=1, max_length=2000)


class PaymentRunLineResponse(BaseModel):
    """One bill in a run."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    vendor_id: UUID
    vendor_name: str
    invoice_id: UUID
    invoice_number: str
    is_opening_bill: bool
    amount: Decimal
    settlement_id: UUID | None


class PaymentRunResponse(BaseModel):
    """One run and its bills."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    run_number: str
    payment_date: date
    due_by: date | None
    status: str
    remarks: str | None
    approved_by: UUID | None
    approved_at: datetime | None
    cancel_reason: str | None
    total: Decimal
    version: int
    lines: list[PaymentRunLineResponse]


class PaymentRunCancel(BaseModel):
    """Why a draft run is called off."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
