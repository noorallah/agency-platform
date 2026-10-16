"""Append-only mutation-audit persistence model."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, String, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDMixin
from app.core.database.types import UUIDType
from app.core.exceptions import BusinessRuleError


class AuditLog(UUIDMixin, Base):
    """Record a mutation without coupling auditing to a business domain."""

    __tablename__ = "audit_logs"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(UUIDType())
    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    application_version: Mapped[str | None] = mapped_column(String(50))
    #: Written while the support account (backlog 29s) was the one signed in,
    #: so the customer can list everything the vendor's support person did.
    #: Set by `record_audit` from the request, never by the caller.
    by_support: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


def _reject_audit_mutation(*_: object) -> None:
    raise BusinessRuleError("Audit records are append-only.")


event.listen(AuditLog, "before_update", _reject_audit_mutation)
event.listen(AuditLog, "before_delete", _reject_audit_mutation)
