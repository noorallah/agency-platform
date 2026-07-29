"""Typed sorting contracts for future repository query builders."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SortDirection(StrEnum):
    """Supported sort directions."""

    ASCENDING = "asc"
    DESCENDING = "desc"


class SortField(BaseModel):
    """Describe one whitelisted-by-caller sort instruction."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    direction: SortDirection = SortDirection.ASCENDING
