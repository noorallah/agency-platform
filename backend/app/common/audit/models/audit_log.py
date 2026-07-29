"""Generic immutable mutation-audit persistence model."""

from uuid import UUID

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class AuditLog(BaseEntity):
    """Record a mutation without coupling auditing to a business domain."""

    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(UUIDType())
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSON)
