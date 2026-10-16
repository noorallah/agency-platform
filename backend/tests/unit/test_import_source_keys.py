"""An old software's number kept against our record (Swathi plan, gap G2).

A conversion is safe to run again: the converter asks which old numbers were
already brought in, skips them, and keeps the number of each record it
creates in the same transaction.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.utils.chunks as chunk_module
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.core.utils.dates import utc_now
from app.imports.models import ImportSourceKey
from app.imports.services.import_source_keys import lookup, stage_record


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Build an in-memory schema holding every table."""
    built = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(built)
    yield built
    built.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Open one session on the in-memory schema."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    opened = factory()
    yield opened
    opened.close()


def test_lookup_answers_only_what_was_brought_in(session: Session) -> None:
    """A staged key is found, trimmed and case-folded codes match, others not."""
    firm_id = uuid4()
    record_id = uuid4()
    stage_record(
        session,
        firm_id=firm_id,
        source_system="swathi",
        subject="customer",
        source_key=" 101 ",
        record_id=record_id,
        actor_id=None,
    )
    session.commit()

    answer = lookup(session, firm_id, "SWATHI", "CUSTOMER", ["101 ", "102", ""])

    assert answer == {"101": record_id}
    # Another subject, program or firm is a different key altogether.
    assert lookup(session, firm_id, "SWATHI", "PRODUCT", ["101"]) == {}
    assert lookup(session, firm_id, "TALLY", "CUSTOMER", ["101"]) == {}
    assert lookup(session, uuid4(), "SWATHI", "CUSTOMER", ["101"]) == {}
    assert lookup(session, firm_id, "SWATHI", "CUSTOMER", []) == {}


def test_stage_record_flushes_and_audits_without_committing(
    session: Session,
) -> None:
    """The key goes with the record's own transaction, so a rollback drops it."""
    firm_id = uuid4()
    row = stage_record(
        session,
        firm_id=firm_id,
        source_system="SWATHI",
        subject="PRODUCT",
        source_key="I-7",
        record_id=uuid4(),
        actor_id=uuid4(),
    )
    assert row.id is not None
    assert session.query(AuditLog).filter_by(entity_id=row.id).count() == 1

    session.rollback()

    assert lookup(session, firm_id, "SWATHI", "PRODUCT", ["I-7"]) == {}


def test_a_key_already_held_is_refused(session: Session) -> None:
    """The service names the clash; the index holds even without the service."""
    firm_id = uuid4()
    first = uuid4()
    stage_record(
        session,
        firm_id=firm_id,
        source_system="SWATHI",
        subject="VENDOR",
        source_key="S1",
        record_id=first,
        actor_id=None,
    )
    session.commit()

    with pytest.raises(ConflictError) as refused:
        stage_record(
            session,
            firm_id=firm_id,
            source_system="swathi",
            subject="vendor",
            source_key="S1",
            record_id=uuid4(),
            actor_id=None,
        )
    assert refused.value.details == {"record_id": str(first)}

    session.add(
        ImportSourceKey(
            firm_id=firm_id,
            source_system="SWATHI",
            subject="VENDOR",
            source_key="S1",
            record_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_a_deleted_key_can_be_kept_again(session: Session) -> None:
    """Deleting the entry releases the number for the record that replaces it."""
    firm_id = uuid4()
    row = stage_record(
        session,
        firm_id=firm_id,
        source_system="SWATHI",
        subject="CUSTOMER",
        source_key="9",
        record_id=uuid4(),
        actor_id=None,
    )
    row.is_deleted = True
    row.deleted_at = utc_now()
    session.commit()
    assert lookup(session, firm_id, "SWATHI", "CUSTOMER", ["9"]) == {}

    replacement = uuid4()
    stage_record(
        session,
        firm_id=firm_id,
        source_system="SWATHI",
        subject="CUSTOMER",
        source_key="9",
        record_id=replacement,
        actor_id=None,
    )
    session.commit()

    assert lookup(session, firm_id, "SWATHI", "CUSTOMER", ["9"]) == {"9": replacement}


def test_blank_codes_are_refused(session: Session) -> None:
    """A key with no program, subject or number would match nothing useful."""
    for system, subject, key in (("", "CUSTOMER", "1"), ("SWATHI", " ", "1")):
        with pytest.raises(ValidationError):
            stage_record(
                session,
                firm_id=uuid4(),
                source_system=system,
                subject=subject,
                source_key=key,
                record_id=uuid4(),
                actor_id=None,
            )
    with pytest.raises(ValidationError):
        stage_record(
            session,
            firm_id=uuid4(),
            source_system="SWATHI",
            subject="CUSTOMER",
            source_key="  ",
            record_id=uuid4(),
            actor_id=None,
        )


def test_lookup_asks_in_chunks(
    session: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More keys than a chunk are asked in several statements and merged."""
    firm_id = uuid4()
    expected = {}
    for number in range(5):
        record_id = uuid4()
        expected[str(number)] = record_id
        stage_record(
            session,
            firm_id=firm_id,
            source_system="SWATHI",
            subject="SALES_INVOICE",
            source_key=str(number),
            record_id=record_id,
            actor_id=None,
        )
    session.commit()
    monkeypatch.setattr(chunk_module, "CHUNK_SIZE", 2)
    statements: list[str] = []

    def count(*args: object) -> None:
        """Note each statement sent to the key table."""
        text = str(args[2])
        if "import_source_keys" in text:
            statements.append(text)

    event.listen(engine, "before_cursor_execute", count)
    try:
        answer = lookup(
            session,
            firm_id,
            "SWATHI",
            "SALES_INVOICE",
            [*expected, "missing"],
        )
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert answer == expected
    assert len(statements) == 3
