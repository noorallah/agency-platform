"""Reusable pagination request and response helpers."""

from math import ceil

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants.core import (
    DEFAULT_PAGE_NUMBER,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from app.core.responses.models import PaginationMetadata


class PaginationParams(BaseModel):
    """Validate page-based collection request parameters."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=DEFAULT_PAGE_NUMBER, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        """Return the zero-based offset suitable for a repository query."""
        return (self.page - 1) * self.page_size

    def metadata(self, total_records: int) -> PaginationMetadata:
        """Create response metadata for a repository result count."""
        return PaginationMetadata(
            page=self.page,
            page_size=self.page_size,
            total_records=total_records,
            total_pages=ceil(total_records / self.page_size) if total_records else 0,
        )
