"""Global search must read platform tables on the platform store.

`users`, `roles`, `permissions` and `firms` exist only in the platform schema.
A request carrying `X-Firm-ID` runs on a tenant session whose `search_path` is
that firm's schema and nothing else, so reading them there raised
``relation "wholesale_hub.users" does not exist`` -- and because one failing
definition aborts the whole search, **every** global search from inside a firm
answered 503. Ctrl+K was broken for every firm user.

Fourth occurrence of the shape CLAUDE.md records: firm-owned routers before
2026-08-09, the business-profile assignment endpoints, territory search, and
this.

The real proof is `tests/integration/test_search_platform_tables.py`, which
needs two schemas to express it. What can be checked here is the *decision*:
that the flag naming a platform-owned table agrees with `_PLATFORM_TABLES`, the
list provisioning drops from every firm store. Marking one wrongly is how this
returns.
"""

# ruff: noqa: D103

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.tenancy.lifecycle import _PLATFORM_TABLES
from app.identity.models import Role
from app.search.services import search_service as module
from app.search.services.search_service import _DEFINITIONS, SearchService


def _table_of(model: type) -> str:
    return str(model.__tablename__)


def test_every_platform_owned_entity_is_marked() -> None:
    missing = {
        definition.entity_type
        for definition in _DEFINITIONS
        if _table_of(definition.model) in _PLATFORM_TABLES
        and not definition.platform_store
    }
    assert not missing, (
        "these tables exist only in the platform schema, so searching them on "
        f"a tenant session raises UndefinedTable: {missing}"
    )


def test_nothing_else_is_marked() -> None:
    """A firm-owned table read on the platform store returns another firm's rows.

    That failure is silent, which makes it worse than the 503 this fixes.
    """
    wrong = {
        definition.entity_type: _table_of(definition.model)
        for definition in _DEFINITIONS
        if definition.platform_store
        and _table_of(definition.model) not in _PLATFORM_TABLES
    }
    assert not wrong, f"these live in every firm store, not the platform: {wrong}"


def test_the_four_that_broke_it_are_covered() -> None:
    marked = {
        definition.entity_type
        for definition in _DEFINITIONS
        if definition.platform_store
    }
    assert marked == {"users", "roles", "permissions", "firms"}


def test_geography_is_not_platform_owned() -> None:
    """The distinction the flag exists for.

    `geo_countries` and its siblings have no firm column either, which is why
    "has no firm id" cannot be used to decide where a table lives.
    """
    geography = [
        definition
        for definition in _DEFINITIONS
        if _table_of(definition.model).startswith("geo_")
    ]
    assert geography, "the geography definitions moved or were renamed"
    for definition in geography:
        assert definition.firm_column is None
        assert not definition.platform_store


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal(permissions: set[str], firm_id: object | None) -> Principal:
    subject = uuid4()
    return Principal(
        subject=subject,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(subject), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
        firm_id=firm_id,
    )


def test_a_search_with_no_firm_does_not_open_a_second_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no `X-Firm-ID` the session in hand is already the platform store.

    Reaching for `platform_reader()` there opens a real PostgreSQL connection
    to read a table the caller can see anyway -- which broke the whole unit
    suite on a machine with no database, CI included. The rule is not "is this
    entity platform-owned" but "is this session unable to see it".
    """
    session = _session()
    actor = uuid4()
    session.add(
        Role(code="OPS_ADMIN", name="Ops Admin", created_by=actor, updated_by=actor)
    )
    session.commit()

    def _refuse() -> None:
        raise AssertionError("opened the platform store for a platform request")

    monkeypatch.setattr(module, "platform_reader", _refuse)

    page = SearchService(session).search(
        query="Ops",
        principal=_principal({"ROLE_VIEW"}, firm_id=None),
        category="organization",
        page=1,
        page_size=20,
    )

    assert [item.entity_type for item in page.results] == ["roles"]


def test_a_firm_scoped_search_of_firm_owned_data_stays_on_one_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No platform entity in scope means no platform connection."""
    session = _session()

    def _refuse() -> None:
        raise AssertionError("opened the platform store with nothing to read there")

    monkeypatch.setattr(module, "platform_reader", _refuse)

    page = SearchService(session).search(
        query="anything",
        principal=_principal({"CUSTOMER_VIEW"}, firm_id=uuid4()),
        category="masters",
        page=1,
        page_size=20,
    )

    assert page.total == 0
