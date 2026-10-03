"""Contracts for TDS on the purchase of goods, section 194Q (ACC-8)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Tds194QSettingsWrite(BaseModel):
    """The firm's 194Q switch, threshold and rates."""

    model_config = ConfigDict(extra="forbid")

    #: On only where the firm's turnover passed ten crore last year.
    is_enabled: bool
    threshold_amount: Decimal = Field(
        default=Decimal("5000000"), ge=0, max_digits=18, decimal_places=2
    )
    rate_percent: Decimal = Field(
        default=Decimal("0.1"), gt=0, le=20, max_digits=6, decimal_places=3
    )
    rate_without_pan_percent: Decimal = Field(
        default=Decimal("5"), gt=0, le=20, max_digits=6, decimal_places=3
    )


class Tds194QSettingsResponse(BaseModel):
    """The firm's settings; the defaults, switched off, where never saved."""

    model_config = ConfigDict(from_attributes=True)

    is_enabled: bool
    threshold_amount: Decimal
    rate_percent: Decimal
    rate_without_pan_percent: Decimal


class Supplier194QRecord(BaseModel):
    """One supplier's 194Q position for the Income-tax year."""

    model_config = ConfigDict(from_attributes=True)

    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    pan: str | None
    year_from: date
    year_to: date
    #: Approved bills in the year, without GST.
    purchases: Decimal
    threshold: Decimal
    excess: Decimal
    rate_percent: Decimal
    due: Decimal
    #: From the supplier's posted payments carrying a 194Q deduction.
    deducted: Decimal
    #: What the next payment should deduct.
    to_deduct: Decimal
    applies: bool
