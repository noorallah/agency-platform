"""Who may be named as a salesman: an entry of the firm's own list (P2 step 2).

Until step 2 a salesman was any active member of the firm, asked of the
platform store. Now the list is the authority, read in the firm's own store:
a document, a customer, a round, a rule, a payout or a target names a live,
active entry of this firm, and a rule, payout or target refuses an entry that
earns no commission (*Phone order*, *Company staff*).

**The bridge.** The desktop's pickers still offer the firm's members, by user
id, until step 4 moves them onto the list. A member who has no entry yet is
given one as he is named -- of his own id where that id is free, as the
migration does -- so a save from today's screens keeps working. Step 4 removes
it; every piece of it is marked so a grep finds it.

The functions answer the id to **store**. In the shared store the entry of a
user's id may belong to another firm (the migration's "one id, two firms"),
and this firm's entry for him is then of another id: a caller sending the
user's id is answered with that entry's id.
"""

from collections.abc import Iterable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.salesmen.models import Salesman
from app.salesmen.naming import free_name, placeholder_name


def _entry(session: Session, firm_id: UUID, salesman_id: UUID) -> Salesman | None:
    """Return this firm's live entry of that id, or the one tied to that user."""
    row = session.scalar(
        select(Salesman).where(
            Salesman.id == salesman_id,
            Salesman.firm_id == firm_id,
            Salesman.is_deleted.is_(False),
        )
    )
    if row is not None:
        return row
    # P2 step 4 removes this bridge: a picker still sends a user's id.
    return session.scalar(
        select(Salesman).where(
            Salesman.user_id == salesman_id,
            Salesman.firm_id == firm_id,
            Salesman.is_deleted.is_(False),
        )
    )


def _bridge(
    session: Session, firm_id: UUID, user_id: UUID, actor_id: UUID | None
) -> Salesman | None:
    """Make an entry for an active member named before the pickers moved.

    P2 step 4 removes this bridge. The entry takes the user's id where no
    entry holds it, as the migration does, so the document keeps the id it
    was sent; the name is the user's, settled against the firm's live names
    the way the migration settles it.
    """
    names = FirmMetadataReader(session).active_member_names(firm_id, [user_id])
    if user_id not in names:
        return None
    taken = {
        str(name).lower()
        for name in session.scalars(
            select(Salesman.name).where(
                Salesman.firm_id == firm_id, Salesman.is_deleted.is_(False)
            )
        )
    }
    name = free_name(names[user_id] or placeholder_name(user_id), user_id, taken)
    if name is None:
        return None
    held = session.get(Salesman, user_id) is not None
    row = Salesman(
        id=uuid4() if held else user_id,
        firm_id=firm_id,
        name=name,
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
            "source": "named as a member before the salesman pickers moved",
        },
    )
    return row


def nameable_salesman(
    session: Session,
    firm_id: UUID,
    salesman_id: UUID,
    *,
    for_commission: bool = False,
    actor_id: UUID | None = None,
) -> UUID:
    """Return the entry id to store for a salesman a caller named, or refuse.

    Args:
        session: A session on the firm's own store; nothing is committed.
        firm_id: The firm the salesman must be on the list of.
        salesman_id: What the caller sent: an entry id, or (until step 4) a
            member's user id.
        for_commission: True for a commission rule, a payout or a target,
            which refuse an entry that earns no commission.
        actor_id: Who is saving, for the audit row of a bridged entry.

    Returns:
        The id of the firm's entry.

    Raises:
        ValidationError: No live, active entry of this firm, or one that earns
            no commission where commission is asked.

    """
    row = _entry(session, firm_id, salesman_id)
    if row is None:
        row = _bridge(session, firm_id, salesman_id, actor_id)
    if row is None:
        raise ValidationError(
            "That salesman is not on this firm's list of salesmen. "
            "Add him under Salesmen first."
        )
    if not row.is_active:
        raise ValidationError(
            f"{row.name} is an inactive salesman and cannot be named on "
            "anything new. Make him active again under Salesmen first."
        )
    if for_commission and not row.earns_commission:
        raise ValidationError(
            f"{row.name} earns no commission, so he cannot be given a "
            "commission rule, a payout or a target."
        )
    return row.id


def active_salesman(
    session: Session,
    firm_id: UUID,
    salesman_id: UUID,
    *,
    actor_id: UUID | None = None,
) -> UUID | None:
    """Return the entry id a derived salesman stores, or None to name nobody.

    The quiet twin of `nameable_salesman`, for a salesman the server fills in
    rather than one a caller typed: an account manager, a round's salesman.
    One who would be refused is skipped instead. An entry tied to a user who
    is no longer an active member is skipped too, as a departed assignee
    always was (D-TER-11).
    """
    try:
        entry_id = nameable_salesman(session, firm_id, salesman_id, actor_id=actor_id)
    except ValidationError:
        return None
    return entry_id if usable_salesmen(session, firm_id, [entry_id]) else None


def usable_salesmen(
    session: Session, firm_id: UUID, salesman_ids: Iterable[UUID]
) -> set[UUID]:
    """Return those ids that are live, active entries a derivation may name.

    An entry tied to a user counts only while that user is an active member
    of the firm: ending a membership touches no firm store, and an order was
    once created in the name of somebody who had left (D-TER-11). An entry
    tied to nobody -- *Phone order* -- needs no membership.
    """
    wanted = {value for value in salesman_ids if value is not None}
    if not wanted:
        return set()
    rows = list(
        session.execute(
            select(Salesman.id, Salesman.user_id).where(
                Salesman.id.in_(wanted),
                Salesman.firm_id == firm_id,
                Salesman.is_deleted.is_(False),
                Salesman.is_active.is_(True),
            )
        )
    )
    tied = [user_id for _, user_id in rows if user_id is not None]
    members = (
        set(FirmMetadataReader(session).active_member_names(firm_id, tied))
        if tied
        else set()
    )
    return {
        entry_id for entry_id, user_id in rows if user_id is None or user_id in members
    }
