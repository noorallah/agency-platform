"""Bring a firm's principals (companies) in from a spreadsheet.

Swathi gap G3. The rules every master import keeps -- check every row, write
all or nothing, match headings loosely, update on request -- live in
``app.common.file_import``. What is particular to principals:

* **A principal's code is its key.** A row whose code is already a principal
  updates it when the caller asks to update, and is refused otherwise.
* **The file does not make suppliers.** The supplier a company is bought from
  is a choice, and a guessed one is wrong silently, so a *Supplier* must
  already exist.
* **Every row goes through** ``BrandService.stage_save_principal`` -- the same
  code clash and audit row as the form -- and the file commits once.
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
from app.products.models.brand import Principal
from app.products.services.brand_import import firm_companies
from app.products.services.brands import BrandService, PrincipalWrite
from app.vendors.models import Vendor

#: The template, in the order it is laid out.
COLUMNS: tuple[Column, ...] = (
    Column(
        "Code",
        ("principalcode", "companycode", "mfrcode", "manufacturercode"),
        True,
        "The company's code; unique among the firm's principals.",
        "HUL",
    ),
    Column(
        "Name",
        (
            "principalname",
            "principal",
            "companyname",
            "company",
            "manufacturer",
            "manufacturername",
            "mfr",
        ),
        False,
        "The company's name. Needed for a new principal.",
        "Hindustan Unilever",
    ),
    Column(
        "Supplier",
        ("vendor", "vendorcode", "vendorname", "suppliercode", "suppliername"),
        False,
        "The supplier the firm buys this company's goods from, by code or name "
        "(see the Lists sheet). May be blank.",
        "",
    ),
    Column(
        "Active",
        ("isactive", "enabled", "inuse"),
        False,
        "Yes or No. Blank means Yes for a new principal.",
        "Yes",
    ),
)

#: The write-schema field each heading fills, for naming a schema refusal.
_FIELD_HEADINGS: dict[str, str] = {
    "code": "Code",
    "name": "Name",
    "vendor_id": "Supplier",
    "is_active": "Active",
}


class PrincipalFileImporter(FileImporter[Principal]):
    """Check a principal file row by row, and import it whole or not at all."""

    COLUMNS = COLUMNS
    NOUN = "principal"

    def __init__(self, session: Session, service: BrandService) -> None:
        super().__init__(session)
        self._service = service
        self._suppliers: list[Vendor] = []

    def _prepare(self, firm_id: UUID) -> None:
        self._suppliers = firm_suppliers(self._session, firm_id)

    def _stored(self, firm_id: UUID) -> dict[str, Principal]:
        return {
            item.code.strip().upper(): item
            for item in firm_companies(self._session, firm_id)
        }

    def _commit(self) -> None:
        self._session.commit()

    def _stage(
        self,
        row: ImportRow,
        code: str,
        current: Principal | None,
        firm_id: UUID,
        actor_id: UUID,
        report: ImportReport[Principal],
    ) -> None:
        issues: list[ImportIssue] = []
        values = self._values(RowReader(row, code, issues), code, current)
        if issues:
            report.issues.extend(issues)
            return
        try:
            data = PrincipalWrite.model_validate(values)
        except PydanticValidationError as error:
            report.issues.extend(schema_issues(error, row, code, _FIELD_HEADINGS))
            return
        try:
            principal = self._service.stage_save_principal(
                data,
                firm_id=firm_id,
                actor_id=actor_id,
                principal_id=None if current is None else current.id,
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
        report.records.append(principal)

    def _values(
        self, reader: RowReader, code: str, current: Principal | None
    ) -> dict[str, object]:
        """Turn one row's cells into write-schema values.

        The write replaces the whole principal, so on an update a blank cell,
        or a column the file does not have, is filled from what it holds.
        """
        values: dict[str, object] = {"code": code}
        name = reader.text("Name").strip()
        if name:
            values["name"] = name
        elif current is not None:
            values["name"] = current.name
        else:
            reader.fail("Name", "is needed for a new principal.")
        supplier = reader.text("Supplier").strip()
        if supplier:
            found = find_supplier(self._suppliers, supplier)
            if found is None:
                reader.fail(
                    "Supplier",
                    f"'{supplier}' is not one of the firm's suppliers; add the "
                    "supplier first, or name one on the Lists sheet.",
                )
            else:
                values["vendor_id"] = found.id
        elif current is not None:
            values["vendor_id"] = current.vendor_id
        active = reader.flag("Active")
        if active is not None:
            values["is_active"] = active
        elif current is not None:
            values["is_active"] = current.is_active
        return values


def firm_suppliers(session: Session, firm_id: UUID) -> list[Vendor]:
    """Return the firm's live suppliers by code."""
    return list(
        session.scalars(
            select(Vendor)
            .where(Vendor.firm_id == firm_id, Vendor.is_deleted.is_(False))
            .order_by(Vendor.code)
        ).all()
    )


def find_supplier(pool: list[Vendor], value: str) -> Vendor | None:
    """Find a supplier by code, then by name, ignoring case."""
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
    suppliers = firm_suppliers(session, firm_id)
    return file_import.template_workbook(
        sheet_title="Principals",
        columns=COLUMNS,
        notes=[
            "One row is one principal (the company whose agency the firm "
            "holds). Its code is its key: a row whose code is already a "
            "principal updates it when you choose to update.",
            "A supplier must already exist; the file does not make suppliers.",
        ],
        lists_header=[
            "Company code",
            "Company name",
            "Supplier code",
            "Supplier name",
        ],
        lists=[
            [item.code for item in companies],
            [item.name for item in companies],
            [item.code for item in suppliers],
            [item.name for item in suppliers],
        ],
    )


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)
