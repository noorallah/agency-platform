"""Contracts for TDS on contracts (194C) and fees (194J) (PG-5)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TdsSectionSettingsWrite(BaseModel):
    """Change one section's settings; a field left out keeps what is saved."""

    model_config = ConfigDict(extra="forbid")

    is_enabled: bool | None = None
    #: 194C only: one bill past which the tax applies. Null clears it (and is
    #: the only value 194J accepts).
    single_threshold_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    annual_threshold_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    #: 194C: anybody but an individual or HUF. 194J: professional fees.
    rate_percent: Decimal | None = Field(
        default=None, gt=0, le=30, max_digits=6, decimal_places=3
    )
    #: 194C: an individual or HUF. 194J: technical services.
    lower_rate_percent: Decimal | None = Field(
        default=None, gt=0, le=30, max_digits=6, decimal_places=3
    )
    #: Where the supplier gave no PAN (section 206AA).
    rate_without_pan_percent: Decimal | None = Field(
        default=None, gt=0, le=30, max_digits=6, decimal_places=3
    )


class TdsSectionSettingsResponse(BaseModel):
    """One section's settings; the defaults where never saved."""

    model_config = ConfigDict(from_attributes=True)

    section: str
    is_enabled: bool
    single_threshold_amount: Decimal | None
    annual_threshold_amount: Decimal
    rate_percent: Decimal
    lower_rate_percent: Decimal
    rate_without_pan_percent: Decimal


class TdsProposalRecord(BaseModel):
    """What the next bill or payment to one supplier should deduct, and why."""

    model_config = ConfigDict(from_attributes=True)

    vendor_id: UUID
    #: ``194C`` or ``194J``; null where the supplier is under neither.
    section: str | None
    pan: str | None
    rate_percent: Decimal
    #: ``NO_PAN``, ``INDIVIDUAL_HUF``, ``OTHER``, ``PROFESSIONAL`` or
    #: ``TECHNICAL``; blank under no section.
    rate_basis: str
    year_from: date
    year_to: date
    #: The year's other approved bills, before GST.
    billed: Decimal
    #: The bill (before GST) or the advance being proposed for.
    this_document: Decimal
    #: Money on account that the supplier's open bills do not cover.
    advances: Decimal
    base_total: Decimal
    #: ``SINGLE``, ``ANNUAL`` or blank.
    threshold_crossed: str
    due: Decimal
    deducted: Decimal
    #: What the document should deduct.
    proposed: Decimal
    applies: bool
