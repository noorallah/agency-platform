"""Contracts for the supplier gifts register (BUY-2, decision A112)."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupplierGiftWrite(BaseModel):
    """Record one gift; saving posts its journal."""

    model_config = ConfigDict(extra="forbid")

    gift_date: date
    vendor_id: UUID
    item: str = Field(min_length=1, max_length=200)
    value: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    kept_by: Literal["ASSET", "EXPENSE", "OWNER"]
    #: The asset or expense account; not sent for the owner.
    debit_account_id: UUID | None = None
    goods_receipt_id: UUID | None = None
    scheme_name: str | None = Field(default=None, max_length=120)
    tds_194r_amount: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=2
    )
    remarks: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _account_by_keeper(self) -> "SupplierGiftWrite":
        """Require an account for an asset or expense, and none for the owner."""
        if self.kept_by == "OWNER" and self.debit_account_id is not None:
            raise ValueError(
                "A gift taken by the owner goes to drawings; send no account."
            )
        if self.kept_by != "OWNER" and self.debit_account_id is None:
            raise ValueError("Name the asset or expense account the gift is booked to.")
        return self


class SupplierGiftResponse(BaseModel):
    """One register row."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    gift_number: str
    gift_date: date
    vendor_id: UUID
    vendor_name: str
    item: str
    value: Decimal
    kept_by: str
    debit_account_id: UUID | None
    goods_receipt_id: UUID | None
    scheme_name: str | None
    tds_194r_amount: Decimal
    status: str
    journal_entry_id: UUID | None
    remarks: str | None
    cancel_reason: str | None
    version: int


class SupplierGiftCancel(BaseModel):
    """Why a gift entry is taken back."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class SupplierGift194RRecord(BaseModel):
    """One supplier's benefits in a financial year against the 194R limit."""

    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID
    vendor_name: str
    gifts: int
    total_value: Decimal
    tds_deducted: Decimal
    #: The year's total passed 20,000, so the supplier should have deducted.
    over_threshold: bool
    year_from: date
    year_to: date
