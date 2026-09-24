"""Refuse a master code another live row of the same scope already holds.

Every master's code, and the other identifiers a firm types (a GSTIN, a PAN, a
category name), is unique **among live rows only** (D-MST-11). The keys were
plain unique indexes over every row, deleted ones included, so a retired code
was never released; and where a service asked only about live rows, the
database refused what the service allowed and the caller got the bare 409 "The
request conflicts with existing data. Please retry." The keys are now partial
over live rows, and this is the service half: one question asked the same way
by every master, which answers with a sentence naming what clashed.

It also guards a **restore**: bringing a row back puts its code back into the
live set, and a live row may have taken it since.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database.entity import BaseEntity
from app.core.exceptions import ConflictError


def assert_codes_free(
    session: Session,
    model: type[BaseEntity],
    *,
    scope: Mapping[str, object],
    values: Mapping[str, object],
    message: str,
    excluding_id: UUID | None = None,
) -> None:
    """Refuse when a live row in ``scope`` holds any of ``values``.

    Args:
        session: The session the write is on.
        model: The master's mapped class.
        scope: Columns that bound the namespace, such as ``{"firm_id": ...}``;
            a None value matches NULL.
        values: Each identifier to keep unique, ``{column: value}``. A blank
            value is skipped, since an empty GSTIN is not a claim on one.
        message: What the refusal says.
        excluding_id: The row being written, which may keep its own values.

    Raises:
        ConflictError: If a live row already holds one of the values.

    """
    wanted = [
        getattr(model, column) == value
        for column, value in values.items()
        if value is not None and value != ""
    ]
    if not wanted:
        return
    bounds = [
        (
            getattr(model, column).is_(None)
            if value is None
            else getattr(model, column) == value
        )
        for column, value in scope.items()
    ]
    statement = select(model.id).where(
        *bounds, model.is_deleted.is_(False), or_(*wanted)
    )
    if excluding_id is not None:
        statement = statement.where(model.id != excluding_id)
    if session.scalar(statement.limit(1)) is not None:
        raise ConflictError(message)
