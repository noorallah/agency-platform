"""Recognise a record a previous import run already brought in (gap G2).

``docs/SWATHI_IMPORT_PLAN.md``: a conversion is "safe to run again" -- a
record already brought in is recognised by its old number and skipped, never
duplicated. A converter asks :func:`lookup` for every key in the file before
it writes, skips the ones answered, and calls :func:`stage_record` beside each
record it creates, inside the same transaction, so the key and the record are
committed together or not at all. Neither function commits.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ValidationError
from app.imports.models import ImportSourceKey
from app.imports.repositories import live_key, records_for_keys


def _code(value: str, label: str) -> str:
    """Return ``value`` as a stored code: trimmed and upper case."""
    code = value.strip().upper()
    if not code:
        raise ValidationError(f"An import source key needs a {label}.")
    return code


def _key(value: str) -> str:
    """Return ``value`` as a stored key: trimmed, otherwise as written."""
    key = value.strip()
    if not key:
        raise ValidationError("An import source key needs the old number.")
    return key


def lookup(
    session: Session,
    firm_id: UUID,
    source_system: str,
    subject: str,
    keys: Iterable[str],
) -> dict[str, UUID]:
    """Return our record id for each old number already brought in.

    Keys are matched as trimmed; the answer is keyed by the trimmed key. A key
    never brought in is absent, so ``key in answer`` means "skip it".
    """
    system = _code(source_system, "source system")
    kind = _code(subject, "subject")
    wanted = [key.strip() for key in keys if key.strip()]
    if not wanted:
        return {}
    return records_for_keys(session, firm_id, system, kind, wanted)


def stage_record(
    session: Session,
    *,
    firm_id: UUID,
    source_system: str,
    subject: str,
    source_key: str,
    record_id: UUID,
    actor_id: UUID | None,
) -> ImportSourceKey:
    """Keep ``source_key`` against ``record_id``; flush, never commit.

    Raises:
        ConflictError: When the old number is already held by a live entry --
            the converter should have skipped that record.
        ValidationError: When a code or the key is blank.

    """
    system = _code(source_system, "source system")
    kind = _code(subject, "subject")
    key = _key(source_key)
    existing = live_key(session, firm_id, system, kind, key)
    if existing is not None:
        raise ConflictError(
            f"{system} {kind.lower()} {key} was already imported.",
            details={"record_id": str(existing.record_id)},
        )
    row = ImportSourceKey(
        firm_id=firm_id,
        source_system=system,
        subject=kind,
        source_key=key,
        record_id=record_id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(row)
    session.flush()
    record_audit(
        session,
        action="import_source_key.recorded",
        entity_type="import_source_key",
        entity_id=row.id,
        actor_id=actor_id,
        firm_id=firm_id,
        after_data={
            "source_system": system,
            "subject": kind,
            "source_key": key,
            "record_id": str(record_id),
        },
    )
    return row
