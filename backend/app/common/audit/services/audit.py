"""Small generic service for recording mutation audit events."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.context import get_request_context


def record_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None,
    firm_id: UUID | None = None,
    before_data: dict[str, object] | None = None,
    after_data: dict[str, object] | None = None,
    application_version: str | None = None,
) -> None:
    """Stage one immutable audit event in the current transaction."""
    context = get_request_context()
    before_payload = _with_context_metadata(before_data, context)
    after_payload = _with_context_metadata(after_data, context)
    session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before_payload,
            after_data=after_payload,
            ip_address=context.client_ip if context is not None else None,
            application_version=application_version,
        )
    )


def _with_context_metadata(
    payload: dict[str, object] | None,
    context: object,
) -> dict[str, object] | None:
    if context is None:
        return payload
    metadata: dict[str, object] = {
        "correlation_id": getattr(context, "correlation_id", ""),
        "request_id": getattr(context, "request_id", ""),
        "requested_at": _timestamp_value(getattr(context, "requested_at", None)),
    }
    data = dict(payload) if payload is not None else {}
    data["_meta"] = metadata
    return data


def _timestamp_value(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
