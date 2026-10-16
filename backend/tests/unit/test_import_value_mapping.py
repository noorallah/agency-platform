"""A saved import mapping translates values too (Swathi plan, G6 part 2).

A migrating firm's old program names its account heads its own way --
Tally's "Sundry Creditors", Swathi's "codes" heads. The chart-of-accounts
import reads its *Group* column as one of our groups, so a saved mapping
keeps, per firm, kind and name, how each source head reads as ours. It is
applied after the headings are remapped, only to columns the kind declares,
and a value it does not name passes through for the import's own check.
"""

from uuid import uuid4

import pytest

from app.common.file_import import read_rows
from app.core.exceptions import ValidationError
from app.finance.services.ledger_account_import import COLUMNS
from app.imports.schemas import ImportMappingWrite
from app.imports.services import (
    ImportMappingService,
    mapped_content,
    parse_value_mapping,
    value_columns_for_kind,
)
from tests.unit.test_ledger_account_import import (
    _account,
    _codes,
    _csv,
    _factory,
    _firm,
    _run,
)

#: A Tally-style chart: its own heading for the group, and its own head names.
TALLY = _csv(
    "Ledger Code,Ledger Name,Parent Head",
    "4100,Sales - Local,Sales A/c",
    "1100,Petty Cash,cash in hand ",
)

HEADINGS = {"Parent Head": "Group"}
VALUES = {"Group": {"Sales A/c": "SALES", "Cash in Hand": "CASH"}}
GROUP_ONLY = value_columns_for_kind("ledger-accounts")


def test_the_chart_declares_group_as_its_mappable_column() -> None:
    """Only Group is mappable on the chart; other kinds declare nothing yet."""
    assert GROUP_ONLY == ("Group",)
    assert value_columns_for_kind("customers") == ()


def test_mapped_head_names_import_as_our_groups() -> None:
    """Headings are remapped first, then each head name is read as ours."""
    factory = _factory()
    with factory() as session:
        firm = _firm(session)
        content, file_format = mapped_content(
            TALLY, "csv", HEADINGS, COLUMNS, VALUES, value_columns=GROUP_ONLY
        )
        assert file_format == "csv"

        report = _run(session, firm.id, content, apply=True)

    assert report.issues == []
    assert report.imported is True
    assert _codes(factory) == ["1000", "1100", "4100"]
    assert _account(factory, "1100").account_type == "ASSET"


def test_an_unmapped_value_passes_through_unchanged() -> None:
    """A head nobody mapped is read as it is, and the import's check refuses it."""
    content, _ = mapped_content(
        _csv("Code,Name,Group", "4100,Sales,Sales A/c", "4200,Misc,SALES"),
        "csv",
        None,
        COLUMNS,
        {"Group": {"Something Else": "CASH"}},
        value_columns=GROUP_ONLY,
    )
    rows, _, _ = read_rows(content, "csv", COLUMNS)

    assert [row.cells["Group"] for row in rows] == ["Sales A/c", "SALES"]
    # Name is never translated, even when a value there matches a key.
    named, _, _ = read_rows(
        mapped_content(
            _csv("Code,Name,Group", "1,Sales A/c,Sales A/c"),
            "csv",
            None,
            COLUMNS,
            VALUES,
            value_columns=GROUP_ONLY,
        )[0],
        "csv",
        COLUMNS,
    )
    assert named[0].cells == {"Code": "1", "Name": "Sales A/c", "Group": "SALES"}


def test_a_column_the_kind_does_not_declare_is_refused() -> None:
    """A value mapping for Name, or on a kind with none, is refused by name."""
    with pytest.raises(ValidationError, match="cannot be mapped for Name"):
        mapped_content(
            TALLY,
            "csv",
            HEADINGS,
            COLUMNS,
            {"Name": {"a": "b"}},
            value_columns=GROUP_ONLY,
        )
    session = _factory()()
    firm = _firm(session)
    with pytest.raises(ValidationError, match="cannot be mapped for Name"):
        ImportMappingService(session).save_mapping(
            firm.id,
            "ledger-accounts",
            ImportMappingWrite(
                name="Bad", mapping=HEADINGS, value_mapping={"Name": {"a": "b"}}
            ),
            actor_id=uuid4(),
        )


def test_a_saved_value_mapping_round_trips_and_omission_leaves_it_alone() -> None:
    """Saved, listed, kept when left out of a later save, cleared by null."""
    session = _factory()()
    firm = _firm(session)
    service = ImportMappingService(session)
    actor = uuid4()

    saved = service.save_mapping(
        firm.id,
        "ledger-accounts",
        ImportMappingWrite(name="Tally heads", mapping=HEADINGS, value_mapping=VALUES),
        actor_id=actor,
    )
    assert saved.value_mapping == VALUES
    [listed] = service.list_mappings(firm.id, "ledger-accounts")
    assert listed.value_mapping == VALUES

    # The heading mapping changes; the value mapping is not mentioned.
    service.save_mapping(
        firm.id,
        "ledger-accounts",
        ImportMappingWrite(name="Tally heads", mapping={"Parent Head": "Group"}),
        actor_id=actor,
    )
    [kept] = service.list_mappings(firm.id, "ledger-accounts")
    assert kept.value_mapping == VALUES

    service.save_mapping(
        firm.id,
        "ledger-accounts",
        ImportMappingWrite(name="Tally heads", mapping=HEADINGS, value_mapping=None),
        actor_id=actor,
    )
    [cleared] = service.list_mappings(firm.id, "ledger-accounts")
    assert cleared.value_mapping is None


def test_the_preview_lists_the_files_values_for_each_mappable_column() -> None:
    """The screen is shown the distinct heads the file holds, to map each."""
    session = _factory()()
    preview = ImportMappingService(session).preview(
        "ledger-accounts",
        _csv(
            "Ledger Code,Ledger Name,Under",
            "1,A,Sales A/c",
            "2,B,Cash in hand",
            "3,C,Sales A/c",
        ),
        "csv",
    )

    assert preview.value_columns == ["Group"]
    assert preview.file_values == {"Group": ["Sales A/c", "Cash in hand"]}


def test_the_form_field_is_json_or_nothing() -> None:
    """Absent is no translation; anything but column-to-object is refused."""
    assert parse_value_mapping(None) is None
    assert parse_value_mapping(" ") is None
    assert parse_value_mapping('{"Group": {"Sales A/c": "SALES"}}') == {
        "Group": {"Sales A/c": "SALES"}
    }
    with pytest.raises(ValidationError, match="not valid JSON"):
        parse_value_mapping("{")
    with pytest.raises(ValidationError, match="from the file's value to ours"):
        parse_value_mapping('{"Group": "SALES"}')
