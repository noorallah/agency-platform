"""Supplier rebate request and response models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RebateSchema(BaseModel):
    """Strict input, ORM-friendly output."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class RebateSlabWrite(RebateSchema):
    """From this volume, this rate on all of it."""

    threshold: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    rate_percent: Decimal = Field(gt=0, le=100, max_digits=7, decimal_places=4)


def _slabs_rise(slabs: list[RebateSlabWrite] | None) -> None:
    """Refuse two slabs at one threshold."""
    if slabs is None:
        return
    thresholds = [slab.threshold for slab in slabs]
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("Two slabs cannot start at the same volume.")


class SupplierRebateCreate(RebateSchema):
    """Agree a rebate with a supplier for a period."""

    vendor_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    period_from: date
    period_to: date
    notes: str | None = Field(default=None, max_length=2000)
    slabs: list[RebateSlabWrite] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _shape(self) -> "SupplierRebateCreate":
        """Refuse a period that runs backwards and a repeated threshold."""
        if self.period_to < self.period_from:
            raise ValueError("The period must not end before it starts.")
        self.code = self.code.strip().upper()
        _slabs_rise(self.slabs)
        return self


class SupplierRebateUpdate(RebateSchema):
    """Change an agreement still counting. Absent fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    period_from: date | None = None
    period_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    slabs: list[RebateSlabWrite] | None = Field(
        default=None, min_length=1, max_length=20
    )

    @model_validator(mode="after")
    def _shape(self) -> "SupplierRebateUpdate":
        """Refuse a repeated threshold."""
        _slabs_rise(self.slabs)
        return self


class RebateSlabResponse(RebateSchema):
    """One slab."""

    id: UUID
    line_number: int
    threshold: Decimal
    rate_percent: Decimal


class SupplierRebateResponse(RebateSchema):
    """One agreement, with where it stands."""

    id: UUID
    version: int
    vendor_id: UUID
    vendor_name: str | None
    code: str
    name: str
    period_from: date
    period_to: date
    status: str
    notes: str | None
    slabs: list[RebateSlabResponse]
    #: Purchases counted so far, and what they earn at the slab reached.
    volume: Decimal
    rate_percent: Decimal
    earned: Decimal
    #: The next slab, and how much more must be bought to reach it.
    next_threshold: Decimal | None
    next_rate_percent: Decimal | None
    to_next: Decimal | None
    accrued_amount: Decimal | None
    accrual_journal_id: UUID | None
    accrued_at: datetime | None
    #: What approved rebate settlements have set against the supplier's
    #: bills, and what is still to come.
    settled: Decimal
    to_settle: Decimal


class SupplierRebateAccrue(RebateSchema):
    """Book the rebate; the period must be over."""

    accrual_date: date | None = None


__all__ = [
    "RebateSlabResponse",
    "RebateSlabWrite",
    "SupplierRebateAccrue",
    "SupplierRebateCreate",
    "SupplierRebateResponse",
    "SupplierRebateUpdate",
]
