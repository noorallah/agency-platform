"""Map a file from any software onto an import's template (decision B3).

The owner, 2026-10-02: "one common import with field mapping, so a file from
any software (Tally, Marg, Busy, Excel) is mapped onto our templates rather
than a reader per product". The shape is Zoho's and ERPNext's import wizard:

1. **Preview** -- the file's headings, the template's columns, a suggestion
   of which is which (by the names each import already accepts) and a few
   rows to judge it by.
2. The person adjusts the mapping -- a template column per heading, or
   *not imported* -- and may **save** it under a name for the next export
   from the same source.
3. **Check and apply** as every import does today, with the mapping sent
   along: the file's heading row is relabelled (``remap_headings``) and the
   import's own checks, staging and all-or-nothing commit run unchanged.

Six imports take a mapping: products, customers, vendors, both sides' opening
bills and opening stock.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.file_import import (
    Column,
    FileFormat,
    read_grid,
    remap_headings,
    suggest_mapping,
)
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.imports.models import ImportMapping
from app.imports.schemas import (
    ImportColumnInfo,
    ImportMappingResponse,
    ImportMappingWrite,
    ImportPreview,
)


@dataclass(frozen=True)
class ImportKind:
    """One import a mapping can be made for."""

    label: str
    #: The code its own import endpoint is guarded by.
    permission: str
    columns: Callable[[Session], tuple[Column, ...]]


def _products(_: Session) -> tuple[Column, ...]:
    """Return the product import's columns."""
    from app.products.services.product_import import ProductFileImporter

    return ProductFileImporter.COLUMNS


def _customers(_: Session) -> tuple[Column, ...]:
    """Return the customer import's columns."""
    from app.customers.services.customer_import import CustomerFileImporter

    return CustomerFileImporter.COLUMNS


def _vendors(_: Session) -> tuple[Column, ...]:
    """Return the supplier import's columns."""
    from app.vendors.services.vendor_import import VendorFileImporter

    return VendorFileImporter.COLUMNS


def _customer_bills(session: Session) -> tuple[Column, ...]:
    """Return the customer opening-bill import's columns."""
    from app.customers.services.opening_bill_import import (
        CustomerOpeningBillFileImporter,
    )

    return CustomerOpeningBillFileImporter(session).columns


def _vendor_bills(session: Session) -> tuple[Column, ...]:
    """Return the supplier opening-bill import's columns."""
    from app.vendors.services.opening_bill_import import VendorOpeningBillFileImporter

    return VendorOpeningBillFileImporter(session).columns


def _supplier_catalogue(_: Session) -> tuple[Column, ...]:
    """Return the supplier catalogue import's columns (BUY-4)."""
    from app.vendors.services.supplier_catalogue import COLUMNS

    return COLUMNS


def _opening_stock(_: Session) -> tuple[Column, ...]:
    """Return the opening-stock import's columns."""
    from app.inventory.services.opening_stock_import import COLUMNS

    return COLUMNS


def _bank_statement(_: Session) -> tuple[Column, ...]:
    """Return the bank statement import's columns (ACC-1)."""
    from app.bank_reconciliation.services.statement_import import COLUMNS

    return COLUMNS


IMPORT_KINDS: dict[str, ImportKind] = {
    "products": ImportKind("Products", "PRODUCT_IMPORT", _products),
    "customers": ImportKind("Customers", "CUSTOMER_IMPORT", _customers),
    "vendors": ImportKind("Suppliers", "VENDOR_IMPORT", _vendors),
    "customer-opening-bills": ImportKind(
        "Customer opening bills", "CUSTOMER_IMPORT", _customer_bills
    ),
    "vendor-opening-bills": ImportKind(
        "Supplier opening bills", "VENDOR_IMPORT", _vendor_bills
    ),
    "opening-stock": ImportKind("Opening stock", "INVENTORY_IMPORT", _opening_stock),
    "supplier-catalogue": ImportKind(
        "Supplier catalogue", "VENDOR_IMPORT", _supplier_catalogue
    ),
    "bank-statement": ImportKind("Bank statement", "JOURNAL_POST", _bank_statement),
}

#: Rows shown on the mapping screen.
SAMPLE_ROWS = 5


def kind_of(kind: str) -> ImportKind:
    """Return a known import kind, or refuse it by name."""
    found = IMPORT_KINDS.get(kind)
    if found is None:
        raise ResourceNotFoundError(
            f"There is no {kind} import; choose one of {', '.join(IMPORT_KINDS)}."
        )
    return found


def columns_for_kind(session: Session, kind: str) -> tuple[Column, ...]:
    """Return the template columns of one import."""
    return kind_of(kind).columns(session)


def mapped_content(
    content: bytes,
    file_format: FileFormat,
    mapping: Mapping[str, str | None] | None,
    columns: tuple[Column, ...],
) -> tuple[bytes, FileFormat]:
    """Apply a mapping to an uploaded file, or hand it back as it came.

    The import endpoints call this before their own check, so a file mapped
    on the screen is read exactly as mapped and an unmapped one as before.
    """
    if not mapping:
        return content, file_format
    return remap_headings(content, file_format, mapping, columns), "csv"


def parse_mapping(raw: str | None) -> dict[str, str | None] | None:
    """Read the ``mapping`` form field an import endpoint is sent (B3).

    JSON: an object from file heading to template column, or null to leave
    the heading out. Absent or empty means the file is read as it comes.

    Raises:
        ValidationError: When it is not such an object.

    """
    if raw is None or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("The column mapping is not valid JSON.") from exc
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and (target is None or isinstance(target, str))
        for key, target in value.items()
    ):
        raise ValidationError(
            "The column mapping must name, for each file heading, a template "
            "column or null."
        )
    return {key: target for key, target in value.items()}


class ImportMappingService:
    """Preview a file, and keep a firm's saved mappings."""

    def __init__(self, session: Session) -> None:
        """Hold the firm's session."""
        self._session = session

    def preview(
        self, kind: str, content: bytes, file_format: FileFormat
    ) -> ImportPreview:
        """Read a file's headings and first rows, and suggest a mapping.

        Raises:
            ValidationError: When the file has no heading row.

        """
        columns = columns_for_kind(self._session, kind)
        headings, rows = read_grid(content, file_format, limit=SAMPLE_ROWS)
        if not any(heading.strip() for heading in headings):
            raise ValidationError(
                "The file has no heading row; its first row must name the " "columns."
            )
        return ImportPreview(
            file_headings=headings,
            columns=[
                ImportColumnInfo(
                    heading=column.heading,
                    required=column.required,
                    takes=column.takes,
                    example=column.example,
                )
                for column in columns
            ],
            suggested=suggest_mapping(headings, columns),
            sample_rows=rows,
        )

    def list_mappings(self, firm_id: UUID, kind: str) -> list[ImportMappingResponse]:
        """Return the firm's saved mappings for one import, by name."""
        kind_of(kind)
        return [
            ImportMappingResponse.model_validate(row)
            for row in self._session.scalars(
                select(ImportMapping)
                .where(
                    ImportMapping.firm_id == firm_id,
                    ImportMapping.kind == kind,
                    ImportMapping.is_deleted.is_(False),
                )
                .order_by(ImportMapping.name.asc())
            )
        ]

    def save_mapping(
        self,
        firm_id: UUID,
        kind: str,
        data: ImportMappingWrite,
        *,
        actor_id: UUID,
    ) -> ImportMappingResponse:
        """Save a mapping under its name, replacing one already called that.

        Raises:
            ValidationError: When it names a column the import does not have.

        """
        columns = columns_for_kind(self._session, kind)
        known = {column.heading for column in columns}
        unknown = sorted(
            {
                target
                for target in data.mapping.values()
                if target and target not in known
            }
        )
        if unknown:
            raise ValidationError(
                "The mapping names columns this import does not have: "
                + ", ".join(unknown)
                + "."
            )
        name = data.name.strip()
        row = self._session.scalar(
            select(ImportMapping).where(
                ImportMapping.firm_id == firm_id,
                ImportMapping.kind == kind,
                ImportMapping.name == name,
                ImportMapping.is_deleted.is_(False),
            )
        )
        before = None if row is None else dict(row.mapping)
        if row is None:
            row = ImportMapping(
                firm_id=firm_id,
                kind=kind,
                name=name,
                mapping=dict(data.mapping),
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
        else:
            row.mapping = dict(data.mapping)
            row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="import_mapping.saved",
            entity_type="import_mapping",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=None if before is None else {"mapping": before},
            after_data={"kind": kind, "name": name, "mapping": dict(data.mapping)},
        )
        self._session.commit()
        self._session.refresh(row)
        return ImportMappingResponse.model_validate(row)

    def get_mapping(self, firm_id: UUID, mapping_id: UUID) -> ImportMapping:
        """Return one of the firm's live mappings.

        Raises:
            ResourceNotFoundError: When the firm has no such mapping.

        """
        row = self._session.get(ImportMapping, mapping_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("Import mapping not found.")
        return row

    def delete_mapping(self, row: ImportMapping, *, actor_id: UUID) -> None:
        """Delete a saved mapping."""
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="import_mapping.deleted",
            entity_type="import_mapping",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data={"kind": row.kind, "name": row.name},
        )
        self._session.commit()
