"""Check that a master id written onto a record names a row the firm may use.

The four master services wrote `customer_group_id`, `category_id`, `type_id`,
`business_profile_id`, `branch_type_id` and `warehouse_type_id` straight
through (D-MST-3). In the shared store every firm's rows sit in one table, so
one firm's customer could be put in another firm's segment -- and the order
resolver then applied that segment's 50% -- and a segment retired a second
earlier was accepted the same way.

The rule is the one a foreign key cannot express here: the row must be
**live**, and where its table carries a `firm_id` it must be **this firm's**.
A table with no firm column -- a business profile -- is shared by every firm
in the store, so only liveness is asked of it. A row that fails is reported as
not found, which is all another firm's row should ever look like.

On an update only a reference that is **changing** is checked: a record
already holding a since-retired id can still be saved around it, and can
always be pointed somewhere else or cleared.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.entity import BaseEntity
from app.core.exceptions import ResourceNotFoundError

#: ``{field on the record: (master model, what to call it in a refusal)}``.
MasterReferences = Mapping[str, tuple[type[BaseEntity], str]]


def assert_master_reference(
    session: Session,
    model: type[BaseEntity],
    row_id: UUID | None,
    *,
    firm_id: UUID | None,
    label: str,
) -> None:
    """Refuse an id that is not a live row of ``model`` this firm may use."""
    if row_id is None:
        return
    clauses = [model.id == row_id, model.is_deleted.is_(False)]
    firm_column = getattr(model, "firm_id", None)
    if firm_column is not None:
        clauses.append(firm_column == firm_id)
    if session.scalar(select(model.id).where(*clauses)) is None:
        raise ResourceNotFoundError(f"{label} not found.")


def assert_master_references(
    session: Session,
    values: Mapping[str, object],
    references: MasterReferences,
    *,
    firm_id: UUID | None,
    current: object | None = None,
) -> None:
    """Check every reference in ``values`` that is set and, on update, moving.

    ``values`` is the dumped write model, so on a partial update a field the
    caller never mentioned is simply absent and is not looked at. ``current``
    is the row being updated; leave it out on create.
    """
    for field, (model, label) in references.items():
        if field not in values:
            continue
        row_id = values[field]
        if row_id is None:
            continue
        if current is not None and getattr(current, field) == row_id:
            continue
        assert_master_reference(
            session,
            model,
            UUID(str(row_id)),
            firm_id=firm_id,
            label=label,
        )
