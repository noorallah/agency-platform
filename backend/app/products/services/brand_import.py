"""Bring a firm's brands in from a spreadsheet, with a template to fill in.

Swathi gap G3. The rules every master import keeps -- check every row, write
all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to brands:

* **A brand has no code; its name is its key.** Rows are matched on the name,
  ignoring case, so a file re-run after a correction updates the brands it
  made rather than making them twice. A rename is done on the brand's screen.
* **A brand belongs to a company** (backlog 138), so a new brand names an
  existing principal by code or name. The file does not make companies: the
  company a brand is under is a choice, and a guessed one is wrong silently.
* **Every row goes through** ``BrandService.stage_save_brand`` -- the same
  name clash, company check and audit row as the form -- and the file commits
  once.
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
from app.products.models.brand import Brand, Principal
from app.products.services.brands import BrandService, BrandWrite

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Name",
        ("brandname", "brand", "make", "brandtitle"),
        True,
        "The brand's name; unique among the firm's brands, ignoring case.",
        "Sunrise",
    ),
    Column(
        "Company",
        (
            "principal",
            "principalcode",
            "principalname",
            "companycode",
            "companyname",
            "manufacturer",
            "mfr",
        ),
        False,
        "The company the brand is under, by code or name (see the Lists sheet). "
        "Needed for a new brand.",
        "GENERAL",
    ),
    Column(
        "Active",
        ("isactive", "enabled", "inuse"),
        False,
        "Yes or No. Blank means Yes for a new brand.",
        "Yes",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "name": "Name",
    "principal_id": "Company",
    "is_active": "Active",
}


class BrandFileImporter(FileImporter[Brand]):
    """Check a brand file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "brand"
    KEY_HEADING = "Name"

    def __init__(self, session: Session, service: BrandService) -> None:
        super().__init__(session)
        self._service = service
        self._companies: list[Principal] = []

    def _prepare(self, firm_id: UUID) -> None:
        self._companies = firm_companies(self._session, firm_id)

    def _stored(self, firm_id: UUID) -> dict[str, Brand]:
        # Newest first, so where two brands differ only in case the oldest
        # is the one matched, as ``BrandService.brand_named`` matches it.
        return {
            brand.name.strip().upper(): brand
            for brand in self._session.scalars(
                select(Brand)
                .where(Brand.firm_id == firm_id, Brand.is_deleted.is_(False))
                .order_by(Brand.created_at.desc(), Brand.id.desc())
            ).all()
        }

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Brand | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Brand],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = BrandWrite.model_validate(values)
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            brand = self._service.stage_save_brand(
                data,
                firm_id=firm_id,
                actor_id=actor_id,
                brand_id=None if current is None else current.id,
            )
        except ApplicationError as error:
            # Every guard runs before the row is written, so the session is
            # still sound and the rest of the file can be checked.
            report.issues.append(service_issue(error, row, code, _FIELD_HEADINGS))
            return
        if current is None:
            report.to_create += 1
        else:
            report.to_update += 1
        report.records.append(brand)

    def _values(self, reader: RowReader, current: Brand | None) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        On an update a blank cell, or a column the file does not have, keeps
        what the brand already holds.
        """
        values: dict[str, object] = {"name": reader.text("Name")}
        company = reader.text("Company")
        if company:
            found = find_company(self._companies, company)
            if found is None:
                reader.fail(
                    "Company",
                    f"'{company}' is not one of the firm's companies; add the "
                    "company first, or name one on the Lists sheet.",
                )
            else:
                values["principal_id"] = found.id
        elif current is not None:
            values["principal_id"] = current.principal_id
        else:
            reader.fail("Company", "is needed for a new brand.")
        active = reader.flag("Active")
        if active is not None:
            values["is_active"] = active
        elif current is not None:
            values["is_active"] = current.is_active
        return values


def firm_companies(session: Session, firm_id: UUID) -> list[Principal]:
    """Return the firm's live principals by code."""
    return list(
        session.scalars(
            select(Principal)
            .where(Principal.firm_id == firm_id, Principal.is_deleted.is_(False))
            .order_by(Principal.code)
        ).all()
    )


def find_company(pool: list[Principal], value: str) -> Principal | None:
    """Find a principal by code, then by name, ignoring case."""
    wanted = value.strip().lower()
    for item in pool:
        if item.code.lower() == wanted:
            return item
    for item in pool:
        if item.name.strip().lower() == wanted:
            return item
    return None


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    companies = firm_companies(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Brands",
        columns=COLUMNS,
        notes=[
            "One row is one brand. Its name is its key: a row whose name is "
            "already a brand updates it when you choose to update.",
            "The company must already exist; the file does not make companies.",
        ],
        lists_header=["Company code", "Company name"],
        lists=[
            [item.code for item in companies],
            [item.name for item in companies],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
