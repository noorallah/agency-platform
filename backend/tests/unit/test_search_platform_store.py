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

from app.core.tenancy.lifecycle import _PLATFORM_TABLES
from app.search.services.search_service import _DEFINITIONS


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
