"""Request and response contracts for error reporting."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiagnosticsSchema(BaseModel):
    """Base configuration for diagnostics API contracts."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ClientErrorReportCreate(DiagnosticsSchema):
    """One failure reported by a desktop client.

    Every field is length-capped. The client is the least trusted input the
    server takes -- a runaway stack trace or a breadcrumb list that grew without
    limit must be refused at the boundary, not stored.
    """

    fingerprint: str = Field(min_length=1, max_length=64)
    error_type: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    stack_trace: str | None = Field(default=None, max_length=20000)
    app_version: str | None = Field(default=None, max_length=50)
    build_number: str | None = Field(default=None, max_length=50)
    platform_info: str | None = Field(default=None, max_length=200)
    context_label: str | None = Field(default=None, max_length=200)
    request_id: str | None = Field(default=None, max_length=64)
    breadcrumbs: list[str] = Field(default_factory=list, max_length=300)
    occurred_at: datetime | None = None

    @field_validator("breadcrumbs")
    @classmethod
    def cap_breadcrumb_length(cls, value: list[str]) -> list[str]:
        """Keep one oversized line from carrying an unbounded payload."""
        return [line[:500] for line in value]


class ClientErrorReportBatch(DiagnosticsSchema):
    """A queued batch, flushed once the client can reach the server."""

    reports: list[ClientErrorReportCreate] = Field(min_length=1, max_length=50)


class ErrorReportResponse(DiagnosticsSchema):
    """One stored report."""

    id: UUID
    source: str
    fingerprint: str
    error_type: str
    message: str
    stack_trace: str | None
    app_version: str | None
    build_number: str | None
    platform_info: str | None
    firm_id: UUID | None
    user_id: UUID | None
    request_id: str | None
    context_label: str | None
    breadcrumbs: list[str] | None
    occurred_at: datetime | None
    received_at: datetime


class ErrorReportGroupResponse(DiagnosticsSchema):
    """Occurrences of one fault, collapsed.

    The list endpoint returns these rather than raw rows: a thousand copies of
    the same crash is one problem, and a screen that shows it as a thousand rows
    is unusable for triage.
    """

    fingerprint: str
    source: str
    error_type: str
    message: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    app_versions: list[str]
