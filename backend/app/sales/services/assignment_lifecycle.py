"""Take somebody off their rounds when they stop working for the firm.

#575 fixed the **read**: `_derived_salesman` and `_inherited_salesman` skip an
assignee who is no longer an active member, so an order is no longer created in
the name of somebody who has left and then refused at the delivery note, which
does check (D-TER-11). It did not fix the rows. `territory_salesman_assignments`
still named them, so the round's Salespeople tab went on listing a departed
person and the coverage report went on counting them (D-TER-17).

Retiring the rows is a **cross-store write from a platform screen**, which is
why the read-side fix did not need it: `user_firms` lives only in the platform
schema, and the assignments live in every firm's own store. The caller opens
that store -- `firm_store_session` in `app/core/database/dependencies.py` -- and
hands the session here, so this module stays a plain function over one session
and never decides where that session points.

Soft, like every other retirement here: the row is the record that the person
covered the round while they were here, and a payout or a report reading back
over last quarter still has to find it.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.utils.dates import utc_now
from app.sales.models import SalesTerritoryNode, TerritorySalesmanAssignment


def retire_salesman_assignments(
    session: Session, *, firm_id: UUID, user_id: UUID, actor_id: UUID
) -> int:
    """Retire one person's live round assignments in one firm's store.

    Scoped to the firm's **own** nodes rather than to the assignment rows
    alone: `territory_salesman_assignments` carries no `firm_id` of its own,
    and in the shared store one query would otherwise reach another firm's
    rounds for the same person -- somebody who works for two firms and has
    left one of them.

    One audit row per round, in that firm's store, because "who came off this
    round and when" is a question asked of the round rather than of the
    person.

    Args:
        session: A session on **that firm's** store.
        firm_id: The firm the person has left.
        user_id: The person.
        actor_id: Who ended the membership.

    Returns:
        How many assignments were retired.

    """
    rows = list(
        session.scalars(
            select(TerritorySalesmanAssignment)
            .join(
                SalesTerritoryNode,
                SalesTerritoryNode.id == TerritorySalesmanAssignment.territory_id,
            )
            .where(
                TerritorySalesmanAssignment.user_id == user_id,
                TerritorySalesmanAssignment.is_deleted.is_(False),
                SalesTerritoryNode.firm_id == firm_id,
            )
        )
    )
    if not rows:
        return 0
    now = utc_now()
    for row in rows:
        row.is_deleted = True
        row.deleted_at = now
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            session,
            action="sales_territory.salesman_retired",
            entity_type="sales_territory",
            entity_id=row.territory_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={
                "user_id": str(user_id),
                "include_children": row.include_children,
                "is_primary": row.is_primary,
            },
            after_data={"user_id": str(user_id), "is_deleted": True},
        )
    session.commit()
    return len(rows)
