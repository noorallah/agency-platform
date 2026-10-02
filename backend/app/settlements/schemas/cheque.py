"""Contracts for a bank account's cheque layout (ACC-12)."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChequeLayoutUpdate(BaseModel):
    """How far the firm's printer is off the CTS-2010 positions."""

    model_config = ConfigDict(extra="forbid")

    offset_x_mm: Decimal = Field(default=Decimal("0"), ge=-30, le=30, decimal_places=1)
    offset_y_mm: Decimal = Field(default=Decimal("0"), ge=-30, le=30, decimal_places=1)
    print_ac_payee: bool = True


class ChequeLayoutResponse(BaseModel):
    """One bank account's layout; an account never saved reads as zero."""

    model_config = ConfigDict(from_attributes=True)

    ledger_account_id: UUID
    offset_x_mm: Decimal
    offset_y_mm: Decimal
    print_ac_payee: bool
    version: int | None = None
