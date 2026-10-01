"""Bring a firm's opening bills in from a spreadsheet, either side of the books.

Backlog 36, D-GOLIVE-1. What each customer owed the firm, and what the firm
owed each supplier, on the day its books here start is a list of bills -- often
hundreds -- and until 2026-10-01 the only way in was one bill at a time on each
party's form. This brings the list as one file, the way products, customers and
opening stock come in: download a template, fill it, check it -- every problem
by row and column, nothing written -- then import all of it or none of it.

The reading and the report are ``app.common.file_import``'s; the posting is
the opening-bill service's own ``_stage``, the same one the form runs, so the
journal, the balance and every refusal are the form's. What is particular here:

* **The posting date is the screen's**, one cutover day for the whole file, as
  it is for opening stock. A bill dated after it is refused.
* **A party is named by code** and must already exist; parties come first in
  the order a firm brings its data over.
* **A party carrying a single opening-balance figure is refused**, by name,
  because a balance entered both as one figure and bill by bill counts twice.
* **The same bill twice is refused on the second row**, naming the first: one
  party, one old bill number.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import file_import
from app.common.file_import import (
    Column,
    FileFormat,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    parse_date,
    read_rows,
    schema_issues,
)
from app.core.database.entity import BaseEntity
from app.core.exceptions import ApplicationError

PartyT = TypeVar("PartyT", bound=BaseEntity)
BillT = TypeVar("BillT")
WriteT = TypeVar("WriteT", bound=BaseModel)

#: The write model's fields, by the file column each one is read from, so a
#: schema refusal names the column the firm has to correct.
_FIELD_HEADINGS: dict[str, str] = {
    "reference_number": "BillNumber",
    "bill_date": "BillDate",
    "due_date": "DueDate",
    "amount": "Amount",
    "narration": "Narration",
}


@dataclass(frozen=True)
class _Bill(Generic[WriteT]):  # noqa: UP046
    """One checked row, ready to stage."""

    row: int
    party_code: str
    write: WriteT


def columns_for(party: str, aliases: tuple[str, ...]) -> tuple[Column, ...]:
    """Return the template's columns, worded for ``party`` ("customer")."""
    return (
        Column(
            "PartyCode",
            ("code", "partycode", "ledgercode", "accountcode", *aliases),
            True,
            f"The {party}'s code, as on its screen (see the Lists sheet).",
            "",
        ),
        Column(
            "BillNumber",
            ("billno", "invoiceno", "invoicenumber", "refno", "reference", "voucherno"),
            False,
            "The bill's number in the old books. Kept as its reference; the "
            "same number twice for one party is refused.",
            "INV-1042",
        ),
        Column(
            "BillDate",
            ("date", "invoicedate", "billdt", "voucherdate"),
            True,
            "The day the bill was raised; on or before the posting date. "
            "dd-mm-yyyy, dd/mm/yyyy, yyyy-mm-dd or an Excel date.",
            "15-02-2026",
        ),
        Column(
            "DueDate",
            ("duedt", "due", "paymentdue"),
            False,
            f"When it falls due. Blank: the bill date plus the {party}'s "
            "payment terms.",
            "",
        ),
        Column(
            "Amount",
            ("pending", "pendingamount", "balance", "outstanding", "amountdue"),
            True,
            "What was still owed on the bill on the posting date; more than 0.",
            "1500.00",
        ),
        Column(
            "Narration",
            ("remarks", "notes", "remark", "description"),
            False,
            "Free text, kept on the bill.",
            "",
        ),
    )


class OpeningBillFileImporter(ABC, Generic[PartyT, WriteT, BillT]):  # noqa: UP046
    """Check an opening-bill file row by row, and import it whole or not at all.

    A side states its party noun, its parties, how to build its write model
    and how to stage one bill; the checking and the all-or-nothing commit are
    shared.
    """

    #: "customer" or "supplier", for the messages and the template.
    PARTY: ClassVar[str]
    #: Other headings the party's code is exported under.
    CODE_ALIASES: ClassVar[tuple[str, ...]]
    #: Anything particular to this side, for the template's notes sheet.
    NOTES: ClassVar[tuple[str, ...]] = ()

    def __init__(self, session: Session) -> None:
        """Work on one request's session."""
        self._session = session

    @property
    def columns(self) -> tuple[Column, ...]:
        """The columns this side's file is read with."""
        return columns_for(self.PARTY, self.CODE_ALIASES)

    def run(
        self,
        content: bytes,
        *,
        file_format: FileFormat,
        firm_id: UUID,
        actor_id: UUID,
        posting_date: date,
        apply: bool,
    ) -> ImportReport[BillT]:
        """Check every row; with ``apply``, post the file whole.

        A clean check still stages and posts every bill before rolling back,
        so a firm with no chart of accounts or a closed period is told on the
        check rather than on the import.
        """
        rows, used, ignored = read_rows(content, file_format, self.columns)
        report: ImportReport[BillT] = ImportReport(
            columns_used=used, columns_ignored=ignored
        )
        missing = [
            column.heading
            for column in self.columns
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
        parties = self._parties(firm_id)
        bills: list[_Bill[WriteT]] = []
        seen: dict[tuple[str, str], int] = {}
        for row in rows:
            if not any(row.cells.values()):
                report.skipped_blank += 1
                continue
            report.rows += 1
            bill = self._check_row(row, parties, posting_date, seen, report)
            if bill is not None:
                bills.append(bill)
                report.to_create += 1
        if report.rows == 0 and not report.issues:
            report.issues.append(
                ImportIssue(1, None, None, "The file has no opening bill rows.")
            )
        if report.issues:
            return report
        try:
            self._stage_all(bills, parties, firm_id, actor_id, report)
        except Exception:
            self._session.rollback()
            raise
        if not apply or report.issues:
            self._session.rollback()
            report.records = []
            return report
        self._session.commit()
        for record in report.records:
            self._session.refresh(record)
        report.imported = True
        return report

    def _check_row(
        self,
        row: ImportRow,
        parties: dict[str, PartyT],
        posting_date: date,
        seen: dict[tuple[str, str], int],
        report: ImportReport[BillT],
    ) -> _Bill[WriteT] | None:
        """Read one row; record every problem with it, and return it if clean."""
        code = row.cells.get("PartyCode", "").strip().upper()
        reader = RowReader(row, code or "", report.issues)
        before = len(report.issues)
        party = parties.get(code)
        if not code:
            reader.fail("PartyCode", "is required.")
        elif party is None:
            reader.fail("PartyCode", f"is not a {self.PARTY} of this firm.")
        elif (conflict := self._refusal(party)) is not None:
            reader.fail("PartyCode", conflict)
        bill_date = self._date(reader, "BillDate", required=True)
        due_date = self._date(reader, "DueDate", required=False)
        if bill_date is not None and bill_date > posting_date:
            reader.fail(
                "BillDate",
                f"is after the posting date {posting_date:%d-%m-%Y}; an opening "
                "bill is one raised before the books here start.",
            )
        if bill_date is not None and due_date is not None and due_date < bill_date:
            reader.fail("DueDate", "is before the bill date.")
        amount = reader.number("Amount")
        if amount is None and not reader.text("Amount"):
            reader.fail("Amount", "is required.")
        elif amount is not None and amount <= 0:
            reader.fail("Amount", "must be more than 0.")
        number = reader.text("BillNumber")
        if code and number:
            key = (code, number.upper())
            if key in seen:
                reader.fail(
                    "BillNumber",
                    f"appears again for {code}; row {seen[key]} already has it.",
                )
            else:
                seen[key] = row.number
        if len(report.issues) > before:
            return None
        try:
            write = self._write_model(
                {
                    "reference_number": number or None,
                    "bill_date": bill_date,
                    "due_date": due_date,
                    "posting_date": posting_date,
                    "amount": amount,
                    "narration": reader.text("Narration") or None,
                }
            )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return None
        return _Bill(row=row.number, party_code=code, write=write)

    @staticmethod
    def _date(reader: RowReader, heading: str, *, required: bool) -> date | None:
        raw = reader.text(heading)
        if not raw:
            if required:
                reader.fail(heading, "is required.")
            return None
        parsed = parse_date(raw)
        if parsed is None:
            reader.fail(heading, f"'{raw}' is not a date.")
        return parsed

    def _stage_all(
        self,
        bills: Sequence[_Bill[WriteT]],
        parties: dict[str, PartyT],
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[BillT],
    ) -> None:
        """Post every bill without committing; the first refusal stops it.

        The session may hold half a posting by then, and it is rolled back
        whatever else is found.
        """
        for bill in bills:
            try:
                staged = self._stage(
                    parties[bill.party_code], bill.write, firm_id, actor_id
                )
            except ApplicationError as error:
                report.issues.append(
                    ImportIssue(bill.row, bill.party_code, None, error.message)
                )
                return
            report.records.append(staged)

    @abstractmethod
    def _parties(self, firm_id: UUID) -> dict[str, PartyT]:
        """Return the firm's live parties by upper-cased code."""

    def _refusal(self, party: PartyT) -> str | None:
        """Say why this party can take no opening bills, or None if it can."""
        return None

    @abstractmethod
    def _write_model(self, values: dict[str, Any]) -> WriteT:
        """Build the side's write model, which applies the form's own rules."""

    @abstractmethod
    def _stage(
        self,
        party: PartyT,
        write: WriteT,
        firm_id: UUID,
        actor_id: UUID,
    ) -> BillT:
        """Validate and post one bill through the side's own service."""

    def template_columns(self, firm_id: UUID) -> tuple[Column, ...]:
        """Return the columns, the example naming one of the firm's own parties."""
        first = next(iter(sorted(self._parties(firm_id).values(), key=_code)), None)
        return tuple(
            (
                replace(column, example=_code(first))
                if column.heading == "PartyCode" and first is not None
                else column
            )
            for column in self.columns
        )

    def template_workbook(self, firm_id: UUID) -> bytes:
        """Build the XLSX template: the sheet to fill, the notes, and the lists."""
        parties = sorted(self._parties(firm_id).values(), key=_code)
        listed = [party for party in parties if self._refusal(party) is None]
        notes = [
            f"One row is one bill a {self.PARTY} still had open on the day the "
            "books here start. Every bill is posted on the posting date chosen "
            "on screen; bill dates must be on or before it.",
            "Enter what was still owed on each bill. A part-paid bill is "
            "entered at what was left.",
            *self.NOTES,
            "Posting needs the firm's chart of accounts and an open period on "
            "the posting date.",
            "The file is imported whole or not at all. A bill entered in error "
            f"is cancelled on the {self.PARTY}'s screen.",
        ]
        return file_import.template_workbook(
            sheet_title="Opening bills",
            columns=self.template_columns(firm_id),
            notes=notes,
            lists_header=[f"{self.PARTY.title()} code", "Name"],
            lists=[
                [_code(party) for party in listed],
                [_name(party) for party in listed],
            ],
        )

    def template_csv(self, firm_id: UUID) -> str:
        """Build the CSV template: the headings and one example row."""
        return file_import.template_csv(self.template_columns(firm_id))


def _code(party: BaseEntity) -> str:
    """Read a customer's or a supplier's code; both name the column alike."""
    return str(getattr(party, "code"))  # noqa: B009


def _name(party: BaseEntity) -> str:
    return str(getattr(party, "name"))  # noqa: B009


def parties_by_code(  # noqa: UP047 -- see RecordT in file_import (D-SETUP-6)
    session: Session, model: type[PartyT], firm_id: UUID
) -> dict[str, PartyT]:
    """Read a firm's live parties of one kind, keyed by upper-cased code."""
    rows = session.scalars(
        select(model).where(
            model.firm_id == firm_id,  # type: ignore[attr-defined]
            model.is_deleted.is_(False),
        )
    ).all()
    return {_code(row).strip().upper(): row for row in rows}


__all__ = [
    "OpeningBillFileImporter",
    "columns_for",
    "parties_by_code",
]
