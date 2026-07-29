"""Small generic service for recording mutation audit events."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog


def record_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None,
    before_data: dict[str, object] | None = None,
    after_data: dict[str, object] | None = None,
) -> None:
    """Stage one immutable audit event in the current transaction."""
    session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            before_data=before_data,
            after_data=after_data,
        )
    )
