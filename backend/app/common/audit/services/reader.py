"""Read access to the audit trail.

The trail is stored per store rather than centrally: platform-level mutations
land in the platform schema and firm-level mutations in that firm's own schema.
A caller therefore reads whichever trail its session is already pointed at, and
the router decides that by firm context.
"""

from datetime import UTC, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.common.audit.schemas import AuditLogFilters


class AuditLogReader:
    """Query one audit store."""

    def __init__(self, session: Session) -> None:
        """Bind the reader to one request unit of work."""
        self._session = session

    def list_events(
        self,
        *,
        firm_scope: UUID | None,
        filters: AuditLogFilters,
        page: int,
        page_size: int,
        descending: bool = True,
    ) -> tuple[list[AuditLog], int]:
        """Return one page of audit events and the total matching count."""
        statement = self._apply(select(AuditLog), firm_scope, filters)
        count_statement = self._apply(
            select(func.count()).select_from(AuditLog), firm_scope, filters
        )
        total = self._session.scalar(count_statement) or 0
        order = AuditLog.created_at.desc() if descending else AuditLog.created_at.asc()
        rows = list(
            self._session.scalars(
                statement.order_by(order, AuditLog.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, total

    def _apply[RowT: tuple[Any, ...]](
        self,
        statement: Select[RowT],
        firm_scope: UUID | None,
        filters: AuditLogFilters,
    ) -> Select[RowT]:
        """Restrict a statement to the requested scope and filters."""
        if firm_scope is not None:
            statement = statement.where(AuditLog.firm_id == firm_scope)
        if filters.action is not None:
            statement = statement.where(AuditLog.action == filters.action)
        if filters.entity_type is not None:
            statement = statement.where(AuditLog.entity_type == filters.entity_type)
        if filters.entity_id is not None:
            statement = statement.where(AuditLog.entity_id == filters.entity_id)
        if filters.actor_id is not None:
            statement = statement.where(AuditLog.actor_id == filters.actor_id)
        # Bounds are inclusive UTC calendar days, matching the created_from /
        # created_to convention used by the customer and product list filters.
        if filters.date_from is not None:
            statement = statement.where(
                AuditLog.created_at
                >= datetime.combine(filters.date_from, time.min, UTC)
            )
        if filters.date_to is not None:
            statement = statement.where(
                AuditLog.created_at <= datetime.combine(filters.date_to, time.max, UTC)
            )
        return statement
