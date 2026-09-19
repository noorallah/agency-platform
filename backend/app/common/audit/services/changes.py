"""Say what a configuration write actually changed.

An audit row that names a record and not the change is a row nobody can use:
"the print template was updated" does not say that the bank account customers
pay into moved, and "a conversion rule was updated" does not say from which
factor to which. These helpers read a mapped row's columns into JSON-safe
values, before and after a write, and keep only the fields that differ -- so
the row carries the change and nothing else, and a write that changed nothing
can be recognised as one and left out of the trail.
"""

from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import cast
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapper, Session

from app.common.audit.services.audit import record_audit
from app.core.database.entity import BaseEntity

#: Columns every entity carries that say who touched a row and when, not what
#: the row holds. The audit row records the actor and the time on its own.
_BOOKKEEPING = frozenset(
    {
        "id",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "version",
        "deleted_at",
        "deleted_by",
    }
)


def audit_value(value: object) -> object:
    """Return ``value`` in a form a JSON audit column can hold and compare."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return audit_value(value.value)
    if isinstance(value, Decimal):
        # By value, not by scale: a column read back as 12.00 is the 12 that
        # was written, and must not look like a change.
        return format(value.normalize(), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): audit_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [audit_value(item) for item in value]
    return str(value)


def row_state(row: object, *, exclude: Iterable[str] = ()) -> dict[str, object]:
    """Read every content column of a mapped row, JSON-safe."""
    skip = _BOOKKEEPING | set(exclude)
    mapper = cast(Mapper[object], sa_inspect(type(row)))
    return {
        attribute.key: audit_value(getattr(row, attribute.key))
        for attribute in mapper.column_attrs
        if attribute.key not in skip
    }


def changed_fields(
    before: dict[str, object], after: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the before and after of only the fields that differ.

    Both sides empty means nothing changed, which a caller uses to skip the
    audit row altogether.
    """
    keys = sorted(
        key for key in {**before, **after} if before.get(key) != after.get(key)
    )
    return (
        {key: before.get(key) for key in keys},
        {key: after.get(key) for key in keys},
    )


def record_change(
    session: Session,
    *,
    action: str,
    entity_type: str,
    row: BaseEntity,
    actor_id: UUID | None,
    before: dict[str, object] | None = None,
    firm_id: UUID | None = None,
    exclude: Iterable[str] = (),
) -> bool:
    """Audit the create, update or soft delete of ``row`` with what changed.

    ``before`` is :func:`row_state` taken before the write, or ``None`` for a
    create -- whose after side is the whole new row -- and for a soft delete,
    which keeps the whole row on the before side so the trail still says what
    was removed. An update keeps only the fields that moved, and writes **no
    row at all** when none did: a re-save of the same values is not an event.
    Returns whether a row was written.
    """
    after = row_state(row, exclude=exclude)
    if before is None and after.get("is_deleted"):
        # A soft delete moves nothing but the flag, so the row as it stood is
        # the row now with the flag cleared; the caller need not snapshot it.
        before = {**after, "is_deleted": False}
    before_data: dict[str, object] | None
    if before is None:
        before_data, after_data = None, after
    elif after.get("is_deleted") and not before.get("is_deleted"):
        before_data, after_data = before, {"is_deleted": True}
    else:
        before_data, after_data = changed_fields(before, after)
        if not after_data:
            return False
    record_audit(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=row.id,
        actor_id=actor_id,
        firm_id=firm_id,
        before_data=before_data,
        after_data=after_data,
    )
    return True
