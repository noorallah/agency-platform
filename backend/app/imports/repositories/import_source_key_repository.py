"""Soft-delete-aware reads of the old-software keys (gap G2)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.chunks import over_chunks
from app.imports.models import ImportSourceKey


@over_chunks("keys")
def records_for_keys(
    session: Session,
    firm_id: UUID,
    source_system: str,
    subject: str,
    keys: Sequence[str],
) -> dict[str, UUID]:
    """Return our record id for each of ``keys`` already brought in.

    A key never brought in, or whose entry was deleted, is absent. Asked in
    chunks, because a conversion names every bill of two years at once.
    """
    if not keys:
        return {}
    rows = session.execute(
        select(ImportSourceKey.source_key, ImportSourceKey.record_id).where(
            ImportSourceKey.firm_id == firm_id,
            ImportSourceKey.source_system == source_system,
            ImportSourceKey.subject == subject,
            ImportSourceKey.source_key.in_(list(keys)),
            ImportSourceKey.is_deleted.is_(False),
        )
    )
    return {key: record_id for key, record_id in rows}


def live_key(
    session: Session,
    firm_id: UUID,
    source_system: str,
    subject: str,
    source_key: str,
) -> ImportSourceKey | None:
    """Return the live entry for one key, or None."""
    return session.scalars(
        select(ImportSourceKey).where(
            ImportSourceKey.firm_id == firm_id,
            ImportSourceKey.source_system == source_system,
            ImportSourceKey.subject == subject,
            ImportSourceKey.source_key == source_key,
            ImportSourceKey.is_deleted.is_(False),
        )
    ).first()
