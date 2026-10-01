"""The migration chain is whole: every parent exists, and there is one head.

On 2026-10-02 migration 20261002_0211 was written, never committed, and 0212
named it as its parent. ``main`` then had a chain alembic could not walk --
``alembic heads`` raised ``KeyError: '20261002_0211'`` -- and nothing in the
unit suite noticed, because it builds its schema from the models, never from
the migrations. Every store's next ``migrate-all`` would have failed.
"""

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
