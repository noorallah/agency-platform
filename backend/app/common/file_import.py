"""Bring master records in from a CSV or XLSX file, with a template to fill in.

Backlog 46. A firm moving from Tally, Excel or another ERP brings its masters as
files -- products, customers, vendors -- and every one of them keeps the same
rules, which live here so each module states only its columns and its rows:

* **Every row is checked before anything is written**, and every problem is
  reported with its row number and column -- not only the first, because a
  3,000-row file that fails one row at a time is re-run 3,000 times.
* **All or nothing.** Each row goes through the module's ``stage_*`` methods --
  the same guards and audit writes as the form -- and the file commits once,
  or not at all.
* **Headings are matched ignoring case, spaces and punctuation**, with the
  names other software commonly exports, so an export needs little editing.
* **Update by code is an option.** With ``existing="update"`` a row whose code
  is already a record updates it, and a blank cell leaves that field alone --
  so a migration can be corrected and re-run.
"""

# ruff: noqa: D102, D107

import csv
import io
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError

ExistingRows = Literal["refuse", "update"]
FileFormat = Literal["csv", "xlsx"]

_YES = {"yes", "y", "true", "1", "t"}
_NO = {"no", "n", "false", "0", "f"}


@dataclass(frozen=True)
class Column:
    """One template column: its heading, the names it also answers to, and help."""

    heading: str
    aliases: tuple[str, ...]
    required: bool
    takes: str
    example: str


@dataclass
class ImportIssue:
    """One problem with one row: where, and what."""

    row: int
    code: str | None
    column: str | None
    message: str

    def describe(self) -> str:
        """Render it the way every import error reads."""
        where = f"Row {self.row}" + (f" ({self.code})" if self.code else "")
        column = f"{self.column}: " if self.column else ""
        return f"{where}: {column}{self.message}"


@dataclass
class ImportReport[RecordT]:
    """What a file would do, or did."""

    rows: int = 0
    to_create: int = 0
    to_update: int = 0
    skipped_blank: int = 0
    columns_used: list[str] = field(default_factory=list)
    columns_ignored: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    imported: bool = False
    records: list[RecordT] = field(default_factory=list)


@dataclass
class ImportRow:
    """One data row read off the file, by canonical heading."""

    number: int
    cells: dict[str, str]


class ImportIssueResponse(BaseModel):
    """One problem with one row of an imported file."""

    row: int
    code: str | None
    column: str | None
    message: str
    #: The whole line as the desktop lists it, "Row 3 (RICE): Unit: ...".
    text: str


class ImportReportResponse(BaseModel):
    """What checking, or importing, a file found."""

    rows: int
    to_create: int
    to_update: int
    skipped_blank: int
    columns_used: list[str]
    columns_ignored: list[str]
    issues: list[ImportIssueResponse]
    #: True only when the file was applied and committed.
    imported: bool


def report_response[RecordT](report: ImportReport[RecordT]) -> ImportReportResponse:
    """Shape an importer's report for the wire."""
    return ImportReportResponse(
        rows=report.rows,
        to_create=report.to_create,
        to_update=report.to_update,
        skipped_blank=report.skipped_blank,
        columns_used=report.columns_used,
        columns_ignored=report.columns_ignored,
        issues=[
            ImportIssueResponse(
                row=issue.row,
                code=issue.code,
                column=issue.column,
                message=issue.message,
                text=issue.describe(),
            )
            for issue in report.issues
        ],
        imported=report.imported,
    )


def file_format_of(filename: str | None) -> FileFormat:
    """Name a file's format from its extension, refusing anything else."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return "csv"
    if name.endswith((".xlsx", ".xlsm")):
        return "xlsx"
    raise ValidationError("Choose a .csv or .xlsx file.")


def normalise_heading(value: object) -> str:
    """Reduce a heading to letters and digits, lower case."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def read_rows(
    content: bytes, file_format: FileFormat, columns: Sequence[Column]
) -> tuple[list[ImportRow], list[str], list[str]]:
    """Read a file into rows keyed by canonical heading.

    Returns the rows, the headings used and the headings ignored. The header
    is row 1, as a spreadsheet shows it, so data starts at row 2.
    """
    lookup: dict[str, str] = {}
    for column in columns:
        lookup[normalise_heading(column.heading)] = column.heading
        for alias in column.aliases:
            lookup[alias] = column.heading
    grid = _read_csv(content) if file_format == "csv" else _read_xlsx(content)
    try:
        header = next(grid)
    except StopIteration:
        return [], [], []
    positions: dict[str, int] = {}
    ignored: list[str] = []
    for position, raw in enumerate(header):
        heading = lookup.get(normalise_heading(raw))
        if heading is None or heading in positions:
            if str(raw or "").strip():
                ignored.append(str(raw).strip())
            continue
        positions[heading] = position
    rows: list[ImportRow] = []
    for number, values in enumerate(grid, start=2):
        cells = {
            heading: _cell_text(values[position]) if position < len(values) else ""
            for heading, position in positions.items()
        }
        rows.append(ImportRow(number=number, cells=cells))
    used = [column.heading for column in columns if column.heading in positions]
    return rows, used, ignored


def _read_csv(content: bytes) -> Iterator[list[object]]:
    """Yield CSV rows, taking the byte-order mark Excel writes."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows saves "CSV" in the ANSI code page.
        text = content.decode("cp1252")
    yield from csv.reader(io.StringIO(text))


def _read_xlsx(content: bytes) -> Iterator[list[object]]:
    """Yield the rows of the workbook's first sheet."""
    try:
        from openpyxl import load_workbook  # type: ignore[import-untyped]
    except ImportError as error:
        raise ValidationError(
            "XLSX import dependency is unavailable. Install openpyxl."
        ) from error
    try:
        workbook = load_workbook(filename=BytesIO(content), read_only=True)
    except Exception as error:  # noqa: BLE001 -- any unreadable file
        raise ValidationError("The file is not a readable XLSX workbook.") from error
    sheet = workbook.worksheets[0]
    for values in sheet.iter_rows(values_only=True):
        yield list(values)


def _cell_text(value: object) -> str:
    """Read a cell as trimmed text; a whole float loses its ``.0``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


class RowReader:
    """Read typed values off one row, recording each cell that will not parse."""

    def __init__(self, row: ImportRow, code: str, issues: list[ImportIssue]) -> None:
        self.row = row
        self.cells = row.cells
        self._code = code
        self._issues = issues

    def fail(self, column: str, message: str) -> None:
        """Record one problem with this row."""
        self._issues.append(ImportIssue(self.row.number, self._code, column, message))

    def text(self, heading: str) -> str:
        """Return a cell as text, blank when the file has no such column."""
        return self.cells.get(heading, "")

    def number(self, heading: str) -> Decimal | None:
        """Read a number; commas are ignored and a blank cell is None."""
        raw = self.text(heading)
        if not raw:
            return None
        try:
            return Decimal(raw.replace(",", "").strip())
        except InvalidOperation:
            self.fail(heading, f"'{raw}' is not a number.")
            return None

    def whole(self, heading: str) -> int | None:
        """Read a whole number; a blank cell is None."""
        value = self.number(heading)
        if value is None:
            return None
        if value != value.to_integral_value():
            self.fail(heading, f"'{self.text(heading)}' is not a whole number.")
            return None
        return int(value)

    def flag(self, heading: str) -> bool | None:
        """Read Yes or No; a blank cell is None."""
        raw = self.text(heading).lower()
        if not raw:
            return None
        if raw in _YES:
            return True
        if raw in _NO:
            return False
        self.fail(heading, f"'{self.text(heading)}' should be Yes or No.")
        return None


class FileImporter[RecordT](ABC):
    """Check a file row by row, and import it whole or not at all.

    A module states its ``COLUMNS``, the noun a row is, how to read the records
    already stored, and how to stage one row; the checking, the counting and
    the all-or-nothing commit are the same for every master.
    """

    COLUMNS: ClassVar[tuple[Column, ...]]
    #: What one row is, for the messages: "product", "customer".
    NOUN: ClassVar[str]

    def __init__(self, session: Session) -> None:
        self._session = session

    def run(
        self,
        content: bytes,
        *,
        file_format: FileFormat,
        firm_id: UUID,
        actor_id: UUID,
        existing: ExistingRows = "refuse",
        apply: bool,
    ) -> ImportReport[RecordT]:
        """Check every row; with ``apply``, commit the file if nothing failed.

        Nothing is written by a check, and nothing is written by an apply
        that found a problem: the staged rows are rolled back either way.
        """
        rows, used, ignored = read_rows(content, file_format, self.COLUMNS)
        report: ImportReport[RecordT] = ImportReport(
            columns_used=used, columns_ignored=ignored
        )
        missing = [
            column.heading
            for column in self.COLUMNS
            if column.required and column.heading not in used
        ]
        if missing:
            report.issues.append(
                ImportIssue(
                    row=1,
                    code=None,
                    column=None,
                    message="The heading row has no "
                    + " or ".join(missing)
                    + " column. Download the template to see the headings.",
                )
            )
            return report
        self._prepare(firm_id)
        stored = self._stored(firm_id)
        seen: dict[str, int] = {}
        try:
            for row in rows:
                if not any(row.cells.values()):
                    report.skipped_blank += 1
                    continue
                report.rows += 1
                code = row.cells.get("Code", "").strip().upper()
                if not code:
                    report.issues.append(
                        ImportIssue(row.number, None, "Code", "is required.")
                    )
                    continue
                if code in seen:
                    report.issues.append(
                        ImportIssue(
                            row.number,
                            code,
                            "Code",
                            f"appears again; row {seen[code]} already has it.",
                        )
                    )
                    continue
                seen[code] = row.number
                current = stored.get(code)
                if current is not None and existing == "refuse":
                    report.issues.append(
                        ImportIssue(
                            row.number,
                            code,
                            "Code",
                            f"is already a {self.NOUN}. Choose to update "
                            f"existing {self.NOUN}s to change it from this file.",
                        )
                    )
                    continue
                self._stage(row, code, current, firm_id, actor_id, report)
        except Exception:
            self._session.rollback()
            raise
        if report.rows == 0 and not report.issues:
            report.issues.append(
                ImportIssue(1, None, None, f"The file has no {self.NOUN} rows.")
            )
        if not apply or report.issues:
            self._session.rollback()
            report.records = []
            return report
        self._commit()
        for record in report.records:
            self._session.refresh(record)
        report.imported = True
        return report

    def _prepare(self, firm_id: UUID) -> None:  # noqa: B027 -- optional hook
        """Read whatever reference data the rows name, once per file."""

    @abstractmethod
    def _stored(self, firm_id: UUID) -> dict[str, RecordT]:
        """Return the firm's live records by code."""

    @abstractmethod
    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: RecordT | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[RecordT],
    ) -> None:
        """Build, validate and stage one row; record what went wrong if not."""

    @abstractmethod
    def _commit(self) -> None:
        """Commit the staged file the way the module's own writes commit."""


def schema_issues(
    error: PydanticValidationError,
    row: ImportRow,
    code: str,
    field_headings: Mapping[str, str],
) -> list[ImportIssue]:
    """Turn a write-schema refusal into issues naming the file's columns."""
    issues: list[ImportIssue] = []
    for detail in error.errors():
        # A nested field is named by its path without the list positions,
        # "addresses.city", and falls back to the list it sits in.
        path = [str(part) for part in detail["loc"] if not isinstance(part, int)]
        heading = field_headings.get(".".join(path)) or (
            field_headings.get(path[0]) if path else None
        )
        message = str(detail["msg"]).removeprefix("Value error, ")
        issues.append(ImportIssue(row.number, code, heading, message + "."))
    return issues


def template_workbook(
    *,
    sheet_title: str,
    columns: Sequence[Column],
    notes: Sequence[str],
    lists_header: Sequence[str],
    lists: Sequence[Sequence[object]],
) -> bytes:
    """Build an XLSX template: the sheet to fill, the notes, and the lists.

    ``lists`` are the columns of the Lists sheet -- the codes a row may name
    -- each laid out top to bottom under its heading in ``lists_header``.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font  # type: ignore[import-untyped]
    except ImportError as error:
        raise ValidationError(
            "XLSX export dependency is unavailable. Install openpyxl."
        ) from error
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append([column.heading for column in columns])
    sheet.append([column.example for column in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for index, column in enumerate(columns, start=1):
        letter = sheet.cell(row=1, column=index).column_letter
        sheet.column_dimensions[letter].width = max(12, len(column.heading) + 4)
    sheet.freeze_panes = "A2"

    notes_sheet = workbook.create_sheet("Notes")
    notes_sheet.append(["Column", "Required", "What it takes", "Also read from"])
    for column in columns:
        notes_sheet.append(
            [
                column.heading,
                "Yes" if column.required else "No",
                column.takes,
                ", ".join(column.aliases),
            ]
        )
    notes_sheet.append([])
    for line in (
        f"Replace the example row with your own; only the {sheet_title} sheet "
        "is read.",
        "Headings are matched ignoring case and spaces, and the names in "
        "'Also read from' are accepted too; other columns are ignored.",
        "Nothing is saved until every row passes the check.",
        "When updating existing records, a blank cell leaves that field as it is.",
        *notes,
    ):
        notes_sheet.append([line])
    for cell in notes_sheet[1]:
        cell.font = Font(bold=True)
    notes_sheet.column_dimensions["A"].width = 20
    notes_sheet.column_dimensions["C"].width = 70
    notes_sheet.column_dimensions["D"].width = 50

    lists_sheet = workbook.create_sheet("Lists")
    lists_sheet.append(list(lists_header))
    for index in range(max((len(values) for values in lists), default=0)):
        lists_sheet.append(
            [values[index] if index < len(values) else None for values in lists]
        )
    for cell in lists_sheet[1]:
        cell.font = Font(bold=True)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def template_csv(columns: Sequence[Column]) -> str:
    """Build a CSV template: the headings and one example row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([column.heading for column in columns])
    writer.writerow([column.example for column in columns])
    return buffer.getvalue()
