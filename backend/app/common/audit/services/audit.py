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
    session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before_data,
            after_data=after_data,
            ip_address=context.client_ip if context is not None else None,
            application_version=application_version,
        )
    )
