"""The sample file an importer hands out must be a file the server reads.

Two of the desktop's importers send the file to the server as it is, so the
headings in their samples are the server's spelling and nothing on the
desktop can check them. The branch and warehouse importer builds JSON from
its columns, so its headings must be fields of the write schema. Either kind
of drift ships a sample the very first customer file is refused for, and a
suite on one side alone cannot see it -- the same gap
``test_desktop_preference_payloads_are_accepted.py`` closes for preferences.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.branches.api.router import BRANCH_EXPORT_COLUMNS, WAREHOUSE_EXPORT_COLUMNS
from app.branches.schemas.branch_warehouse import BranchCreate, WarehouseCreate

_ROOT = Path(__file__).resolve().parents[3]
_DESKTOP = _ROOT / "desktop" / "lib" / "ui"
_BACKEND = _ROOT / "backend" / "app"


def _dart_list(path: Path, name: str) -> list[str]:
    """Read the string literals of the ``name: [ ... ]`` list in a Dart file."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"{name}:\s*\[(.*?)\]", text, re.DOTALL)
    assert match, f"{path.name} has no `{name}:` list"
    return re.findall(r"'([^']*)'", match.group(1))


def _dart_columns(path: Path, name: str) -> list[str]:
    """Read the header of every ``_Column('header', ...)`` in a named list."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"{name} = \[(.*?)\];", text, re.DOTALL)
    assert match, f"{path.name} has no `{name}` list"
    return re.findall(r"_Column\(\s*'([^']+)'", match.group(1))


def _server_reads(path: Path, function: str) -> set[str]:
    """Collect the ``row.get("...")`` names inside one method body."""
    text = path.read_text(encoding="utf-8")
    start = text.index(f"def {function}(")
    end = text.find("\n    def ", start + 1)
    body = text[start : end if end > 0 else len(text)]
    return set(re.findall(r'row\.get\("([^"]+)"\)', body))


def test_the_territory_sample_names_exactly_the_columns_the_server_reads() -> None:
    """The territory sample and ``import_csv`` read one list of headings."""
    sample = _dart_list(_DESKTOP / "sales" / "territory_import_sample.dart", "columns")
    server = _server_reads(
        _BACKEND / "sales" / "services" / "territory_service.py", "import_csv"
    )
    assert set(sample) == server
    assert len(sample) == len(set(sample))


def test_the_purchase_sample_names_exactly_the_columns_the_server_reads() -> None:
    """The purchase sample and ``import_orders_csv`` read one list of headings."""
    sample = _dart_list(
        _DESKTOP / "purchases" / "purchase_import_sample.dart", "columns"
    )
    server = _server_reads(
        _BACKEND / "purchase" / "services" / "purchase_service.py",
        "import_orders_csv",
    )
    assert set(sample) == server
    assert len(sample) == len(set(sample))


def test_every_branch_and_warehouse_sample_column_is_a_write_field() -> None:
    """A heading the branch dialog offers is a field its write schema takes."""
    dialog = _DESKTOP / "branches" / "branch_warehouse_import_dialog.dart"
    for name, schema in (
        ("_branchColumns", BranchCreate),
        ("_warehouseColumns", WarehouseCreate),
    ):
        columns = _dart_columns(dialog, name)
        assert columns, name
        unknown = set(columns) - set(schema.model_fields)
        assert not unknown, f"{name} names fields {schema.__name__} lacks: {unknown}"


def test_the_branch_and_warehouse_exports_write_what_their_importer_reads() -> None:
    """An export is re-importable only if its columns are the importer's."""
    dialog = _DESKTOP / "branches" / "branch_warehouse_import_dialog.dart"
    assert tuple(_dart_columns(dialog, "_branchColumns")) == BRANCH_EXPORT_COLUMNS
    assert tuple(_dart_columns(dialog, "_warehouseColumns")) == WAREHOUSE_EXPORT_COLUMNS
