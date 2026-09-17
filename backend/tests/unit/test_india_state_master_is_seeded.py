"""The seeded India state master is complete, and fits where it is stored.

`20260917_0137` fills `geo_states` in every firm store, because geography is a
per-store master that shipped empty: on 2026-09-17 three of this project's
seven stores held no states at all, so the State rung of the place picker on
customers, vendors, branches and warehouses was blank until somebody typed one.

The list is the thing worth guarding. A missing state is not a crash -- it is
an address somebody cannot record, found months later by whoever tries, and
nothing else in this suite looks at the blueprint.

The migration's *behaviour* -- the `has_table` guard, skipping what a store
already has, leaving a soft-deleted state deleted -- was verified against the
seven live stores rather than here: a replay left the count at 36 and a
deliberately deleted Mizoram deleted. The unit suite builds one SQLite schema
and cannot express "a store that already has its own list".
"""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260917_0137_seed_the_india_state_master.py"
)

#: The constitutional counts. Both are facts about India rather than about this
#: codebase, which is why they are written as numbers here: 28 states and 8
#: union territories after the 2019-2020 reorganisations, which made Jammu and
#: Kashmir and Ladakh separate union territories and merged Dadra and Nagar
#: Haveli with Daman and Diu.
_STATE_COUNT = 28
_UNION_TERRITORY_COUNT = 8

#: The eight union territories, named so the split can be checked rather than
#: assumed from a total that happens to add up.
_UNION_TERRITORIES = {
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
}


def _migration() -> ModuleType:
    """Load the migration as a module, by path.

    Alembic loads its own scripts this way; the versions directory is not a
    package, so importing it normally is not available.
    """
    spec = importlib.util.spec_from_file_location("_seed_states", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_state_and_union_territory_is_present() -> None:
    """Thirty-six places, and the right split between the two kinds."""
    states = _migration()._INDIAN_STATES
    assert len(states) == _STATE_COUNT + _UNION_TERRITORY_COUNT

    names = {name for _, name in states}
    missing = _UNION_TERRITORIES - names
    assert not missing, f"union territories absent from the seed: {sorted(missing)}"
    assert len(names - _UNION_TERRITORIES) == _STATE_COUNT


def test_no_state_is_listed_twice() -> None:
    """Both unique indexes are on (country_id, code) and (country_id, name).

    A duplicate in the blueprint would not be caught by the skip logic -- it
    reads what the *store* already holds, not what this list repeats -- so the
    second insert would take the whole migration down mid-run.
    """
    states = _migration()._INDIAN_STATES
    codes = [code for code, _ in states]
    names = [name for _, name in states]
    assert len(set(codes)) == len(codes), "a code is repeated"
    assert len(set(names)) == len(names), "a name is repeated"


def test_every_code_and_name_fits_the_column_it_is_stored_in() -> None:
    """`geo_states.code` is String(20) and `name` is String(100).

    PostgreSQL refuses an over-long value; SQLite silently accepts it, so the
    unit suite would never see this and the migration would fail on the
    customer's machine instead.
    """
    for code, name in _migration()._INDIAN_STATES:
        assert code == code.upper(), f"{code} is not upper case"
        assert 1 <= len(code) <= 20, f"{code} does not fit code String(20)"
        assert 1 <= len(name) <= 100, f"{name} does not fit name String(100)"


def test_the_country_matches_the_one_the_tax_template_creates() -> None:
    """Two paths create India; they must agree, or a store gets two.

    `app/tax/services/gst_template.py` creates India where a store has none,
    and this migration does the same. The country's unique index is on `code`,
    so disagreeing on the code would mean the second one to run either fails
    or quietly adds a duplicate country under a different spelling.
    """
    india = _migration()._INDIA
    template = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "tax"
        / "services"
        / "gst_template.py"
    ).read_text(encoding="utf-8")
    assert f'code="{india["code"]}"' in template
    assert f'name="{india["name"]}"' in template
    assert f'iso3="{india["iso3"]}"' in template


def test_the_migration_refuses_a_store_that_has_no_geography() -> None:
    """The platform schema holds no firm-owned tables, geography included.

    Without the guard this migration fails there, and `migrate-all` reports a
    failed store on every installation. Checked as source because running it
    needs an Alembic context and a connection.
    """
    # Whitespace-collapsed before matching: black wraps this guard across
    # three lines, so the call and its argument are not adjacent in the file
    # and a plain substring check fails on correct code.
    source = " ".join(_MIGRATION.read_text(encoding="utf-8").split())
    for table in ("geo_countries", "geo_states"):
        assert re.search(rf'has_table\(\s*"{table}"', source), (
            f"the migration does not guard on {table} being present. The "
            "platform schema has no firm-owned tables: without it, every "
            "installation reports a failed store."
        )
