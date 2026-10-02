"""Contracts for people's ratings of a supplier (BUY-15)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VendorRatingWrite(BaseModel):
    """One person's scores, 1 (poor) to 5 (excellent), and a remark."""

    model_config = ConfigDict(extra="forbid")

    quality: int = Field(ge=1, le=5)
    delivery: int = Field(ge=1, le=5)
    price: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    paperwork: int = Field(ge=1, le=5)
    remark: str | None = Field(default=None, max_length=1000)


class VendorRatingResponse(BaseModel):
    """One live rating."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rated_by: UUID
    rated_on: date
    quality: int
    delivery: int
    price: int
    communication: int
    paperwork: int
    remark: str | None
    created_at: datetime


class VendorRatingSummary(BaseModel):
    """Every live rating of a supplier, the averages and the reader's own."""

    count: int
    #: Each criterion's average to one decimal; None where nobody rated.
    averages: dict[str, Decimal | None]
    overall: Decimal | None
    ratings: list[VendorRatingResponse]
    mine: VendorRatingResponse | None = None
