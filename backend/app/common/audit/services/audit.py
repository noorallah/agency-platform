"""Small generic service for recording mutation audit events."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.core.context import STORE_FIRM_SESSION_KEY, get_request_context


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
    by_support: bool = False,
) -> None:
    """Stage one immutable audit event in the current transaction.

    A write that names no firm is attributed to the firm whose store the
    session was opened on, when there is one. A firm's trail filters on
    ``firm_id``, so a row left null in a firm's own store -- the business
    framework catalogue, geography -- was on no screen at all (D-CFG-13). The
    platform store carries no such key, so platform rows are unchanged.

    A row is marked ``by_support`` when the request was authenticated as the
    support account (backlog 29s), which `get_current_principal` records on
    the request context -- so no module has to remember to pass it. The
    argument exists for the one write made before anybody is signed in: the
    sign-in itself.
    """
    if firm_id is None:
        firm_id = session.info.get(STORE_FIRM_SESSION_KEY)
    context = get_request_context()
    if context is not None and context.actor.by_support:
        by_support = True
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
            by_support=by_support,
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
