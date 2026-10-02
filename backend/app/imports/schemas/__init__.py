"""Contracts for import mapping (decision B3)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportSchema(BaseModel):
    """Apply strict validation and ORM response behaviour."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ImportColumnInfo(ImportSchema):
    """One column of an import's template."""

    heading: str
    required: bool
    takes: str
    example: str


class ImportPreview(ImportSchema):
    """What a file holds, and how it would be read, before any check (B3)."""

    #: The file's own headings, in order.
    file_headings: list[str]
    #: The template the file is mapped onto.
    columns: list[ImportColumnInfo]
    #: File heading to template column as the import would read it today,
    #: or null where it would be left out.
    suggested: dict[str, str | None]
    #: Up to five data rows, as text, in the file's own column order.
    sample_rows: list[list[str]]


class ImportMappingWrite(ImportSchema):
    """Save a mapping under a name, replacing one of the same name."""

    name: str = Field(min_length=1, max_length=100)
    mapping: dict[str, str | None] = Field(max_length=500)


class ImportMappingResponse(ImportSchema):
    """One saved mapping."""

    id: UUID
    kind: str
    name: str
    mapping: dict[str, str | None]
    updated_at: datetime


__all__ = [
    "ImportColumnInfo",
    "ImportMappingResponse",
    "ImportMappingWrite",
    "ImportPreview",
    "ImportSchema",
]
