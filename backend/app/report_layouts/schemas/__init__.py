"""Saved report layout request and response models."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: The screens a layout may be saved for.
REPORT_CODES = ("sales_analysis", "purchase_analysis")


class ReportLayoutWrite(BaseModel):
    """Save a layout under a name; the same name again replaces it."""

    model_config = ConfigDict(extra="forbid")

    report_code: str = Field(pattern=r"^(sales_analysis|purchase_analysis)$")
    name: str = Field(min_length=1, max_length=100)
    #: The screen's own settings; the server does not read inside them.
    settings: dict[str, Any] = Field(max_length=100)


class ReportLayoutResponse(BaseModel):
    """One saved layout."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_code: str
    name: str
    settings: dict[str, Any]
    version: int


__all__ = ["REPORT_CODES", "ReportLayoutResponse", "ReportLayoutWrite"]
