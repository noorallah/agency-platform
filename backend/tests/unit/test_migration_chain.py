"""The migration chain is whole: every parent exists, and there is one head.

On 2026-10-02 migration 20261002_0211 was written, never committed, and 0212
named it as its parent. ``main`` then had a chain alembic could not walk --
``alembic heads`` raised ``KeyError: '20261002_0211'`` -- and nothing in the
unit suite noticed, because it builds its schema from the models, never from
the migrations. Every store's next ``migrate-all`` would have failed.
"""

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND = Path(__file__).resolve().parents[2]


def _scripts() -> ScriptDirectory:
    """Return the migration scripts as alembic reads them."""
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


def test_every_parent_revision_exists_and_there_is_one_head() -> None:
    """A missing parent or a second head fails here, not on a customer."""
    scripts = _scripts()
    revisions = {script.revision: script for script in scripts.walk_revisions()}
    for script in revisions.values():
        parents = script.down_revision
        for parent in (parents,) if isinstance(parents, str) else parents or ():
            assert parent in revisions, (
                f"{script.revision} names {parent} as its parent, and no "
                "migration has that revision: was a file left uncommitted?"
            )
    assert len(scripts.get_heads()) == 1, scripts.get_heads()


def test_an_in_process_migration_leaves_the_servers_logging_alone() -> None:
    """D-RPT-21: `fileConfig` silenced the server after its first provision."""
    tree = ast.parse((_BACKEND / "alembic" / "env.py").read_text(encoding="utf-8"))
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and "attributes" in ast.unparse(node.test)
    ]
    inside = {
        id(call)
        for node in guarded
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }
    calls = [
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and ast.unparse(call.func) == "fileConfig"
    ]

    assert calls
    assert all(id(call) in inside for call in calls)


def test_no_migration_walks_every_schema_in_the_database() -> None:
    """D-MIG-2: provisioning one firm altered every other firm's tables.

    A store is migrated on its own, so a revision that looks schemas up may
    only find the one it is running in.
    """
    walkers = [
        path.name
        for path in sorted((_BACKEND / "alembic" / "versions").glob("*.py"))
        if "DISTINCT table_schema" in (source := path.read_text(encoding="utf-8"))
        and "table_schema = current_schema()" not in source
    ]

    assert walkers == []
