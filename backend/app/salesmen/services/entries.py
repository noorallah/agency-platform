"""Give a user an entry of the firm's salesman list, the way the migration does.

The seeders make their salespeople as users and then name them on rounds,
documents, targets and commission rules. Every `salesman_id` is an entry of
`salesmen` now, and nothing makes one silently any more, so a seeder asks for
the entry here first. The rules are the migration's (`20261014_0380`): the
entry takes the user's own id where no entry holds it, and his name, settled
against the firm's live names with `free_name`.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.salesmen.models import Salesman
from app.salesmen.naming import free_name, placeholder_name


def ensure_salesman_entry(
    session: Session,
    firm_id: UUID,
    user_id: UUID,
    *,
    name: str | None = None,
    actor_id: UUID | None = None,
) -> UUID:
    """Return this firm's live entry for the user, making one if he has none.

    Args:
        session: A session on the firm's own store; flushed, not committed.
        firm_id: The firm whose list the entry is on.
        user_id: The user the entry is tied to.
        name: The name to give a new entry; read from the platform's members
            (and failing that a placeholder) when not given.
        actor_id: Who is seeding, for the audit row.

    Returns:
        The entry's id -- the user's own id unless another entry held it.

    Raises:
        ValueError: When neither the name nor its suffixed form is free.

    """
    found = session.scalar(
        select(Salesman.id).where(
            Salesman.firm_id == firm_id,
            Salesman.user_id == user_id,
            Salesman.is_deleted.is_(False),
        )
    )
    if found is not None:
        return found
    if name is None:
        name = (
            FirmMetadataReader(session)
            .active_member_names(firm_id, [user_id])
            .get(user_id)
        )
    taken = {
        str(value).lower()
        for value in session.scalars(
            select(Salesman.name).where(
                Salesman.firm_id == firm_id, Salesman.is_deleted.is_(False)
            )
        )
    }
    settled = free_name(name or placeholder_name(user_id), user_id, taken)
    if settled is None:
        raise ValueError(f"No free salesman name for user {user_id}.")
    row = Salesman(
        id=uuid4() if session.get(Salesman, user_id) is not None else user_id,
        firm_id=firm_id,
        name=settled,
        user_id=user_id,
        earns_commission=True,
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(row)
    session.flush()
    record_audit(
        session,
        action="salesman.created",
        entity_type="salesman",
        entity_id=row.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={
            "name": row.name,
            "user_id": str(user_id),
            "earns_commission": True,
            "is_active": True,
            "source": "seeded for a user named as a salesman",
        },
    )
    return row.id
