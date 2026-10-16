"""Bring a firm's salesmen in from a spreadsheet.

Swathi gap G3. The rules every master import keeps -- check every row, write
all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to salesmen:

* **A salesman's code is his key.** The list allows an entry with no code,
  but a file has nothing else to match a row on, so the file needs one. A row
  whose code is already a salesman updates him when the caller asks to update,
  and is refused otherwise.
* **The file does not tie a salesman to a sign-in.** Which account a person
  signs in with is a platform fact, and a guessed one is wrong silently; it
  is set on the salesman form.
* **Every row goes through** ``SalesmanService.stage_create`` or
  ``stage_update`` -- the same name, code and audit rules as the form -- and
  the file commits once.
"""

# ruff: noqa: D102, D107

from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import file_import
from app.common.file_import import (
    Column,
    FileImporter,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    schema_issues,
    service_issue,
)
from app.core.exceptions import ApplicationError
from app.salesmen.models import Salesman
from app.salesmen.schemas import SalesmanCreate, SalesmanUpdate
from app.salesmen.services.salesman_service import SalesmanService

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("salesmancode", "salesmanid", "smcode", "repcode"),
        True,
        "The salesman's code; unique among the firm's salesmen.",
        "S01",
    ),
    Column(
        "Name",
        ("salesmanname", "salesman", "smname", "repname", "salesrep"),
        False,
        "The name that prints. Needed for a new salesman; unique on the list.",
        "Ravi Kumar",
    ),
    Column(
        "Phone",
        ("mobile", "mobileno", "phoneno", "contactno", "contact"),
        False,
        "A phone number, up to 20 characters. May be blank.",
        "9876543210",
    ),
    Column(
        "Commission",
        ("earnscommission", "commissionable", "oncommission"),
        False,
        "Yes or No: whether he is paid commission. Blank means Yes for a new "
        "salesman; No suits a phone order or company staff entry.",
        "Yes",
    ),
    Column(
        "Active",
        ("isactive", "enabled", "inuse"),
        False,
        "Yes or No. Blank means Yes for a new salesman.",
        "Yes",
    ),
    Column(
        "Notes",
        ("remarks", "note", "comment", "comments"),
        False,
        "Anything worth keeping about him. May be blank.",
        "",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "phone": "Phone",
    "earns_commission": "Commission",
    "is_active": "Active",
    "notes": "Notes",
}


class SalesmanFileImporter(FileImporter[Salesman]):
    """Check a salesman file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "salesman"

    def __init__(self, session: Session, service: SalesmanService) -> None:
        super().__init__(session)
        self._service = service

    def _stored(self, firm_id: UUID) -> dict[str, Salesman]:
        return {
            item.code.strip().upper(): item
            for item in firm_salesmen(self._session, firm_id)
            if item.code
        }

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Salesman | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Salesman],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            if current is None:
                salesman = self._service.stage_create(
                    SalesmanCreate.model_validate(values),
                    firm_id=firm_id,
                    actor_id=actor_id,
                )
            else:
                salesman = self._service.stage_update(
                    current.id,
                    SalesmanUpdate.model_validate(values),
                    firm_id=firm_id,
                    actor_id=actor_id,
                )
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        except ApplicationError as error:
            # Every guard runs before the row is written, so the session is
            # still sound and the rest of the file can be checked.
            report.issues.append(service_issue(error, row, code, _FIELD_HEADINGS))
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(salesman)

    def _values(
        self, reader: RowReader, code: str, current: Salesman | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        An update changes only what it is sent, so on an update a blank cell,
        or a column the file does not have, is left out and keeps what the
        salesman held.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name").strip()
        if name:
            values["name"] = name
        elif current is None:
            reader.fail("Name", "is needed for a new salesman.")
        for heading, field in (("Phone", "phone"), ("Notes", "notes")):
            text = reader.text(heading).strip()
            if text:
                values[field] = text
        for heading, field in (
            ("Commission", "earns_commission"),
            ("Active", "is_active"),
        ):
            flag = reader.flag(heading)
            if flag is not None:
                values[field] = flag
        return values


def firm_salesmen(session: Session, firm_id: UUID) -> list[Salesman]:
    """Return the firm's live salesmen by code, then name."""
    return list(
        session.scalars(
            select(Salesman)
            .where(Salesman.firm_id == firm_id, Salesman.is_deleted.is_(False))
            .order_by(Salesman.code, Salesman.name)
        ).all()
    )


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    salesmen = firm_salesmen(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Salesmen",
        columns=COLUMNS,
        notes=[
            "One row is one salesman. His code is his key: a row whose code is "
            "already a salesman updates him when you choose to update.",
            "Names are unique on the list, whatever their case.",
            "The sign-in a salesman uses is chosen on the salesman form; the "
            "file does not set it.",
        ],
        lists_header=["Salesman code", "Salesman name"],
        lists=[
            [item.code or "" for item in salesmen],
            [item.name for item in salesmen],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
