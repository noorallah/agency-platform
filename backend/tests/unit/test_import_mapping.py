"""Mapping a file from any software onto an import's template (decision B3).

A Tally or Marg export names its columns its own way. The mapping screen
previews the file, suggests a template column per heading, lets a person
change it, and sends the mapping with the check and the apply; the import's
own rules then run unchanged. Mappings can be saved per firm and import.
"""

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import Workbook

from app.common.file_import import read_rows, remap_headings, suggest_mapping
from app.core.exceptions import AuthorizationError, ValidationError
from app.customers.services.customer_import import CustomerFileImporter
from app.imports.api.router import _require_kind
from app.imports.schemas import ImportMappingWrite
from app.imports.services import ImportMappingService, mapped_content, parse_mapping
from tests.unit.test_customer_import_file import _codes, _csv, _factory, _firm, _run

COLUMNS = CustomerFileImporter.COLUMNS

#: A Tally-style export: two headings the import does not know as they are.
TALLY = _csv(
    "Account No,Ledger Name,GSTIN/UIN,Remarks",
    "C-001,Balaji Stores,33AAAPL1234C1Z5,old",
    "C-002,Sri Ram Traders,,",
)


def test_the_suggestion_is_what_the_import_would_read() -> None:
    """Known names map; unknown ones are left out until a person says."""
    suggested = suggest_mapping(
        ["Account No", "Ledger Name", "GSTIN/UIN", "Remarks"], COLUMNS
    )

    assert suggested["Ledger Name"] == "Name"
    assert suggested["GSTIN/UIN"] == "GSTIN"
    assert suggested["Account No"] is None


def test_a_mapped_file_imports_as_mapped() -> None:
    """Account No is the code; the remarks column is left out by choice."""
    factory = _factory()
    session = factory()
    firm = _firm(session)
    content, file_format = mapped_content(
        TALLY,
        "csv",
        {"Account No": "Code", "Remarks": None},
        COLUMNS,
    )
    assert file_format == "csv"

    report = _run(session, firm.id, content, apply=True)

    assert report.issues == []
    assert report.imported is True
    assert _codes(factory) == ["C-001", "C-002"]
    assert "(not imported) Remarks" in report.columns_ignored


def test_without_a_mapping_the_unknown_code_column_is_refused_as_before() -> None:
    """Nothing changes for a file sent without one."""
    session = _factory()()
    firm = _firm(session)

    report = _run(session, firm.id, TALLY, apply=False)

    assert report.issues and "no Code column" in report.issues[0].message


def test_a_heading_competing_with_a_mapped_one_is_left_out() -> None:
    """Mapped Party Name wins over a stray Name column the file also has."""
    content = remap_headings(
        _csv("Code,Party Name,Name", "C-1,Right,Wrong"),
        "csv",
        {"Party Name": "Name"},
        COLUMNS,
    )
    rows, used, ignored = read_rows(content, "csv", COLUMNS)

    assert rows[0].cells["Name"] == "Right"
    assert "(not imported) Name" in ignored


def test_a_mapping_must_name_real_columns_once_each() -> None:
    """An unknown column, or one column twice, is refused by name."""
    with pytest.raises(ValidationError, match="does not have: Colour"):
        remap_headings(TALLY, "csv", {"Remarks": "Colour"}, COLUMNS)
    with pytest.raises(ValidationError, match="mapped to Code"):
        remap_headings(
            TALLY, "csv", {"Account No": "Code", "Ledger Name": "Code"}, COLUMNS
        )


def test_an_xlsx_file_is_mapped_too() -> None:
    """A workbook comes back as CSV, read the way an import reads cells."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Account No", "Ledger Name"])
    sheet.append(["C-9", "Nine"])
    buffer = BytesIO()
    book.save(buffer)

    content, file_format = mapped_content(
        buffer.getvalue(), "xlsx", {"Account No": "Code"}, COLUMNS
    )
    rows, _, _ = read_rows(content, file_format, COLUMNS)

    assert file_format == "csv"
    assert rows[0].cells == {"Code": "C-9", "Name": "Nine"}


def test_the_form_field_is_json_or_nothing() -> None:
    """Absent is no mapping; anything but heading-to-column-or-null is refused."""
    assert parse_mapping(None) is None
    assert parse_mapping("  ") is None
    assert parse_mapping('{"A": "Code", "B": null}') == {"A": "Code", "B": None}
    with pytest.raises(ValidationError, match="not valid JSON"):
        parse_mapping("{")
    with pytest.raises(ValidationError, match="a template column or null"):
        parse_mapping('{"A": 3}')


def test_preview_and_saved_mappings() -> None:
    """Preview reads the file; a saved name is replaced, listed, deleted."""
    session = _factory()()
    firm = _firm(session)
    service = ImportMappingService(session)
    actor = uuid4()

    preview = service.preview("customers", TALLY, "csv")
    assert preview.file_headings == [
        "Account No",
        "Ledger Name",
        "GSTIN/UIN",
        "Remarks",
    ]
    assert preview.sample_rows[0][:2] == ["C-001", "Balaji Stores"]
    assert "Code" in [column.heading for column in preview.columns]

    service.save_mapping(
        firm.id,
        "customers",
        ImportMappingWrite(name="Tally ledgers", mapping={"Account No": "Code"}),
        actor_id=actor,
    )
    service.save_mapping(
        firm.id,
        "customers",
        ImportMappingWrite(
            name="Tally ledgers", mapping={"Account No": "Code", "Remarks": None}
        ),
        actor_id=actor,
    )
    [saved] = service.list_mappings(firm.id, "customers")
    assert saved.mapping == {"Account No": "Code", "Remarks": None}
    assert service.list_mappings(firm.id, "products") == []

    with pytest.raises(ValidationError, match="does not have: Colour"):
        service.save_mapping(
            firm.id,
            "customers",
            ImportMappingWrite(name="Bad", mapping={"X": "Colour"}),
            actor_id=actor,
        )

    service.delete_mapping(service.get_mapping(firm.id, saved.id), actor_id=actor)
    assert service.list_mappings(firm.id, "customers") == []


def test_mapping_a_file_needs_the_right_to_import_it() -> None:
    """A supplier importer may not map a customer file."""
    principal = SimpleNamespace(has_permission=lambda code: code == "VENDOR_IMPORT")
    scope = SimpleNamespace(principal=principal)

    _require_kind(scope, "vendors")  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError, match="CUSTOMER_IMPORT"):
        _require_kind(scope, "customers")  # type: ignore[arg-type]
