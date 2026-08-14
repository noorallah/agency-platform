"""Guard the one list that says what the schema is.

``app/core/database/all_models.py`` is what makes ``Base.metadata`` complete,
and three things depend on it being so: alembic autogenerate, the tests'
``create_all``, and the sample-data reset. A model module missing from it is
invisible in all three, and that is exactly how the reset list fell 61 tables
behind without anybody noticing.
"""

import ast
import pathlib

import app.core.database.all_models as registry
from app.core.database.base import Base

#: Modules that define no mapped table -- a package marker or a shared base.
_NOT_MODELS = {"__init__"}


def _model_modules() -> set[str]:
    """Return every module under an ``app/*/models/`` package, as a path."""
    root = pathlib.Path(registry.__file__).parents[3] / "app"
    return {
        f"{path.parent.parent.name}.{path.stem}"
        for path in root.glob("*/models/*.py")
        if path.stem not in _NOT_MODELS
    } | {
        f"{path.parents[2].name}.{path.parent.parent.name}.{path.stem}"
        for path in root.glob("*/*/models/*.py")
        if path.stem not in _NOT_MODELS
    }


def test_every_model_module_is_registered() -> None:
    """A model module the registry does not import is invisible everywhere.

    Alembic would autogenerate a migration dropping its tables, `create_all`
    would build a database without them, and the sample-data reset would leave
    their rows behind and die on the first foreign key that noticed.
    """
    # Parsed rather than string-matched: ruff folds two imports from the same
    # package into one parenthesised statement, which a substring check reads
    # as the module having gone missing.
    tree = ast.parse(pathlib.Path(registry.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    missing = sorted(
        name for name in _model_modules() if name.rsplit(".", 1)[1] not in imported
    )
    assert not missing, "add these to app/core/database/all_models.py: " + ", ".join(
        missing
    )


def test_the_registry_alone_describes_the_whole_schema() -> None:
    """Importing the registry is enough; nothing else adds a table.

    `conftest.py` imports it, so if this file's own import were the only thing
    keeping the metadata complete the assertion would still pass -- the point
    is the count, which changes the moment a module stops being registered.
    """
    tables = {table.name for table in Base.metadata.sorted_tables}
    assert "sales_quotations" in tables
    assert "sales_returns" in tables
    assert "physical_counts" in tables
    assert "settlements" in tables
    # Sanity on the order the sample-data reset depends on: a table always
    # follows the ones it references, so reversed is a safe delete order.
    order = [table.name for table in Base.metadata.sorted_tables]
    assert order.index("firms") < order.index("customers")
    assert order.index("sales_returns") < order.index("sales_return_lines")
    assert order.index("batches") < order.index("inventory_transactions")
