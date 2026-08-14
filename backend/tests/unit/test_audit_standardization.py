"""Audit payload standardization tests."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.audit.services.audit import record_audit
from app.core.context import RequestContext, reset_request_context, set_request_context
from app.core.database.base import Base


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_record_audit_adds_correlation_metadata_to_payload() -> None:
    """An audit row carries the request that caused it.

    Without the correlation id, a trail says what changed and gives
    nobody a way to find the request it came from.
    """
    session = _session_factory()()
    actor_id = uuid4()
    entity_id = uuid4()
    context = RequestContext(
        request_id="req-100",
        correlation_id="corr-100",
        client_ip="127.0.0.1",
        requested_at=datetime(2026, 1, 1),
        user_id=actor_id,
        firm_id=uuid4(),
    )
    token = set_request_context(context)
    try:
        record_audit(
            session,
            action="customer.updated",
            entity_type="customer",
            entity_id=entity_id,
            actor_id=actor_id,
            before_data={"status": "ACTIVE"},
            after_data={"status": "INACTIVE"},
        )
        session.commit()
    finally:
        reset_request_context(token)
    row = session.scalar(select(AuditLog).where(AuditLog.entity_id == entity_id))
    assert row is not None
    assert row.after_data is not None
    assert row.before_data is not None
    after_meta = row.after_data.get("_meta")
    before_meta = row.before_data.get("_meta")
    assert isinstance(after_meta, dict)
    assert isinstance(before_meta, dict)
    assert after_meta["correlation_id"] == "corr-100"
    assert before_meta["request_id"] == "req-100"
