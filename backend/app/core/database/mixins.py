"""Reusable ORM entity mixins for identity, lifecycle, and audit fields."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.types import UTCDateTime, UUIDType


class UUIDMixin:
    """Provide a generated UUID primary key."""

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid4)


class TimestampMixin:
    """Track automatic creation and modification timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    """Preserve rows by recording logical deletion rather than deleting them."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditMixin:
    """Reserve actor identifiers for future authentication integration."""

    created_by: Mapped[UUID | None] = mapped_column(UUIDType(), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(UUIDType(), nullable=True)


class VersionMixin:
    """Track an entity version for optimistic concurrency support."""

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
