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

    def list_events_with(
        self,
        platform_reader: "AuditLogReader",
        *,
        firm_scope: UUID,
        filters: AuditLogFilters,
        page: int,
        page_size: int,
        descending: bool = True,
    ) -> tuple[list[AuditLog], int]:
        """Return one page of a firm's trail, including its platform rows.

        A firm's history is written to its own store, except for the part that
        is not: `users`, `roles` and `user_firms` live only in the platform
        schema, so administering a firm's people runs on the platform session
        and `record_audit` writes there. The rows carry the firm on
        `firm_id` -- they were simply in a store the firm cannot read, so a
        firm administrator could not see their own hiring, role edits or
        promotions.

        This merges on the read rather than moving the write, and the reason
        is atomicity. A DATABASE-mode firm is a separate database, possibly on
        a separate server, so writing the audit row there would be a second
        transaction: the promotion could commit and its record fail, or the
        reverse. Today they commit together, and that is worth more than the
        row's physical location.

        The merge is exact, not approximate: `page * page_size` rows are taken
        from each store, combined, ordered, and the requested slice returned.
        Deep paging therefore costs more on both stores -- acceptable while
        `MAX_PAGE_SIZE` is 100, and the reason this is not simply a union.

        Args:
            platform_reader: A reader bound to the platform store.
            firm_scope: The firm whose trail is wanted.
            filters: The caller's filters, applied to both stores.
            page: 1-based page number.
            page_size: Rows per page.
            descending: Newest first when true.

        Returns:
            The page, and the total across both stores.

        """
        if platform_reader._session is self._session:
            # One store, read twice. It happens wherever the platform schema
            # *is* the caller's store -- the unit suite builds a single SQLite
            # schema holding every table, and a platform administrator reading
            # a firm they are exempt into resolves both dependencies to the
            # same session. Merging a store with itself doubles every row and
            # doubles the total, which looks like history nobody wrote.
            return self.list_events(
                firm_scope=firm_scope,
                filters=filters,
                page=page,
                page_size=page_size,
                descending=descending,
            )
        depth = page * page_size
        own, own_total = self.list_events(
            firm_scope=firm_scope,
            filters=filters,
            page=1,
            page_size=depth,
            descending=descending,
        )
        # The platform store holds rows for every firm, so it is filtered on
        # `firm_id` exactly as the firm's own store is -- one firm never sees
        # another's, and the platform's own unscoped rows (`firm_id IS NULL`)
        # stay out because they are nobody's firm history.
        shared, shared_total = platform_reader.list_events(
            firm_scope=firm_scope,
            filters=filters,
            page=1,
            page_size=depth,
            descending=descending,
        )
        combined = sorted(
            own + shared,
            key=lambda row: (row.created_at, str(row.id)),
            reverse=descending,
        )
        start = (page - 1) * page_size
        return combined[start : start + page_size], own_total + shared_total

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
