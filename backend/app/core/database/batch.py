"""Read a page's child rows in one query per table, grouped by parent.

A list endpoint that builds each row's full response one row at a time
reads every child table once per row: a 50-row page of invoices was about
500 statements (backlog 56 C, step 3, ``docs/PERFORMANCE_AT_VOLUME.md``).
``children_by_parent`` reads one child table for every parent on the page
and groups the rows by parent id in Python, so the statement count of a page
no longer grows with its length.

The ids are sent in chunks (:func:`app.core.utils.chunks.chunks`), so a
caller passing every line of a large page cannot reach the driver's
bind-parameter ceiling.
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.database.base import Base
from app.core.utils.chunks import chunks

__all__ = ["children_by_parent"]


def children_by_parent[EntityT: Base](
    session: Session,
    entity: type[EntityT],
    parent: InstrumentedAttribute[Any],
    parent_ids: Iterable[UUID | None],
    *order_by: ColumnElement[Any],
    live_only: bool = True,
) -> defaultdict[UUID, list[EntityT]]:
    """Return ``entity`` rows keyed by the value of ``parent``.

    Args:
        session: The session to read on.
        entity: The child model.
        parent: The child's column naming its parent.
        parent_ids: The parents to read for; ``None`` is ignored.
        order_by: The same ordering the single-parent read used, applied
            within each parent (a stable grouping keeps the scan order).
        live_only: Skip soft-deleted children, as every list read does.

    Returns:
        A ``defaultdict(list)``, so a parent with no children reads as ``[]``.

    """
    found: defaultdict[UUID, list[EntityT]] = defaultdict(list)
    wanted = [value for value in parent_ids if value is not None]
    if not wanted:
        return found
    key = parent.key
    for chunk in chunks(wanted):
        statement = select(entity).where(parent.in_(chunk))
        if live_only:
            live = entity.is_deleted.is_(False)  # type: ignore[attr-defined]
            statement = statement.where(live)
        if order_by:
            statement = statement.order_by(*order_by)
        for row in session.scalars(statement):
            found[getattr(row, key)].append(row)
    return found
