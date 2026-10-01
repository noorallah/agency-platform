"""A business profile written at runtime lands in each store under one id.

Backlog 17. Each firm store keeps its own profile catalogue, so a profile
created in one store must be written to the others with the **same id**, or an
id read in one store names nothing in the next. SQLite builds one database per
unit test store and cannot show that two real schemas -- each with its own
`business_profiles` and its own append-only `audit_logs` -- take the row
independently, each commit on its own.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.business.models import BusinessProfile, FirmBusinessProfile
from app.business.schemas import BusinessProfileCreate
from app.business.services import BusinessProfileFrameworkService
from app.business.services.profile_replication import (
    ProfileStore,
    replicate_profile,
)
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.firms.models import Firm

#: `firms` only because the ORM declares `firm_business_profiles.firm_id` a key
#: to it; deployed firm stores carry no such key (it is cross-store).
_TABLES = [
    Firm.__table__,
    BusinessProfile.__table__,
    FirmBusinessProfile.__table__,
    AuditLog.__table__,
]


@pytest.fixture
def profile_stores(engine: Engine) -> Iterator[tuple[Engine, tuple[str, ...]]]:
    """Create three disposable schemas holding the profile tables only."""
    own = create_engine(engine.url)
    names = tuple(f"it_{uuid4().hex[:12]}" for _ in range(3))
    try:
        for name in names:
            with own.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{name}"'))
            Base.metadata.create_all(
                own.execution_options(schema_translate_map={None: name}),
                tables=_TABLES,  # type: ignore[arg-type]
            )
        yield own, names
    finally:
        for name in names:
            with own.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        own.dispose()


def _opener(own: Engine, schema: str) -> ProfileStore:
    """Describe one schema as a store a profile must reach."""

    @contextmanager
    def open_store() -> Iterator[Session]:
        """Open, and always close, one session on the schema."""
        session = sessionmaker(
            bind=own.execution_options(schema_translate_map={None: schema}),
            expire_on_commit=False,
        )()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    return ProfileStore(label=schema, opener=open_store)


def test_each_schema_takes_the_profile_under_the_same_id(
    profile_stores: tuple[Engine, tuple[str, ...]],
) -> None:
    """Created in the first schema, copied to the other two, audited in each."""
    own, (first, second, third) = profile_stores
    actor = uuid4()
    with _opener(own, first).opener() as session:  # type: ignore[misc]
        profile = BusinessProfileFrameworkService(session).create_profile(
            BusinessProfileCreate(code="BAKERY", name="Bakery", industry_type="FOOD"),
            actor,
        )
        outcomes = replicate_profile(
            profile, [_opener(own, second), _opener(own, third)], actor
        )

    assert [item.status for item in outcomes] == ["WRITTEN", "WRITTEN"]
    for schema in (second, third):
        with _opener(own, schema).opener() as session:  # type: ignore[misc]
            copy = session.get(BusinessProfile, profile.id)
            assert copy is not None and copy.code == "BAKERY"
            assert session.scalar(
                select(AuditLog.action).where(AuditLog.entity_id == profile.id)
            ) == ("business_profile.created")
