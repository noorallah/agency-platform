"""Persistence model for client and server error reports."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import UUIDMixin
from app.core.database.types import UUIDType


class ErrorReport(UUIDMixin, Base):
    """One failure, reported by a desktop client or raised by this server.

    Deliberately **not** a ``BaseEntity``. Soft delete, an optimistic-concurrency
    counter and created/updated actors are the vocabulary of a business record
    somebody edits; a report is written once and read. ``audit_logs`` is the
    precedent -- the same shape, for the same reason.

    Lives in the **platform** schema, unlike the audit trail. Audit records are
    per firm store so a dedicated-database firm keeps its own history for the
    isolation guarantees; error reports are operational telemetry for whoever
    maintains the product, and are useless scattered across stores. ``firm_id``
    is therefore recorded as data, not used as routing.
    """

    __tablename__ = "error_reports"
    __table_args__ = (
        # Grouping by fingerprint over a recent window is the read this table
        # exists for; ordering by arrival is the other.
        Index("IX_error_reports_fingerprint", "fingerprint"),
        Index("IX_error_reports_received_at", "received_at"),
        Index("IX_error_reports_request_id", "request_id"),
    )

    #: ``CLIENT`` for a desktop report, ``SERVER`` for an unhandled request.
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Stable identity for "the same bug", so one fault groups instead of
    #: arriving ten thousand times.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    error_type: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text)

    app_version: Mapped[str | None] = mapped_column(String(50))
    build_number: Mapped[str | None] = mapped_column(String(50))
    platform_info: Mapped[str | None] = mapped_column(String(200))

    firm_id: Mapped[UUID | None] = mapped_column(UUIDType(), index=True)
    user_id: Mapped[UUID | None] = mapped_column(UUIDType())

    #: Joins a client's report to this server's account of the same request --
    #: the value already returned to every caller as ``ApiResponse.requestId``.
    request_id: Mapped[str | None] = mapped_column(String(64))

    #: Screen or route the failure happened on.
    context_label: Mapped[str | None] = mapped_column(String(200))

    breadcrumbs: Mapped[list[str] | None] = mapped_column(JSON)

    #: When it happened on the reporting machine; may be well before arrival,
    #: because a client queues reports until it can reach the server.
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
