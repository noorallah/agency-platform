"""Validated response contracts for reading the audit trail."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """Return one recorded mutation."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    created_at: datetime
    action: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None
    firm_id: UUID | None
    before_data: dict[str, object] | None
    after_data: dict[str, object] | None
    ip_address: str | None
    application_version: str | None


class AuditLogFilters(BaseModel):
    """Filter the audit trail."""

    model_config = ConfigDict(extra="forbid")

    action: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    actor_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


__all__ = ["AuditLogFilters", "AuditLogResponse"]
