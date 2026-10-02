"""Every column the trigram migration indexes exists (PLT-3).

The migration skips a table or column it cannot find, so a misspelt name
would silently leave that search unindexed -- `quotations` for
`sales_quotations` did, while it was written.
"""

import importlib.util
from pathlib import Path

import tests.conftest  # noqa: F401
from app.core.database.base import Base

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261003_0250_trigram_search.py"
)


def test_every_indexed_column_is_a_real_text_column() -> None:
    """Each named table and column exists in the ORM schema."""
    spec = importlib.util.spec_from_file_location("trigram_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for table, columns in module.SEARCHED.items():
        assert table in Base.metadata.tables, table
        for column in columns:
            assert column in Base.metadata.tables[table].columns, (table, column)
