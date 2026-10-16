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

A saved mapping may also translate **values** (Swathi G6, part 2): for a
column its kind declares in ``value_columns`` -- the chart of accounts'
*Group* -- the source program's own head names are read as ours. A value it
does not name passes through unchanged, so the import's own check still
refuses a group nobody mapped.
"""

import csv
import io
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
    heading_lookup,
    normalise_heading,
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
    #: Template columns whose values a saved mapping may translate (G6).
    value_columns: tuple[str, ...] = ()


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


def _brands(_: Session) -> tuple[Column, ...]:
    """Return the brand import's columns (Swathi G3)."""
    from app.products.services.brand_import import BrandFileImporter

    return BrandFileImporter.COLUMNS


def _principals(_: Session) -> tuple[Column, ...]:
    """Return the principal import's columns (Swathi G3)."""
    from app.products.services.principal_import import PrincipalFileImporter

    return PrincipalFileImporter.COLUMNS


def _salesmen(_: Session) -> tuple[Column, ...]:
    """Return the salesman import's columns (Swathi G3)."""
    from app.salesmen.services.salesman_import import SalesmanFileImporter

    return SalesmanFileImporter.COLUMNS


def _ledger_accounts(_: Session) -> tuple[Column, ...]:
    """Return the chart-of-accounts import's columns (Swathi G6)."""
    from app.finance.services.ledger_account_import import (
        LedgerAccountFileImporter,
    )

    return LedgerAccountFileImporter.COLUMNS


def _routes(_: Session) -> tuple[Column, ...]:
    """Return the route (beat) import's columns (Swathi G3)."""
    from app.sales.services.route_import import RouteFileImporter

    return RouteFileImporter.COLUMNS


def _segments(_: Session) -> tuple[Column, ...]:
    """Return the customer segment import's columns (Swathi G3)."""
    from app.customers.services.segment_import import SegmentFileImporter

    return SegmentFileImporter.COLUMNS


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
    # Brands are kept under PRODUCT_UPDATE, so their import is too.
    "brands": ImportKind("Brands", "PRODUCT_UPDATE", _brands),
    # A principal is kept under PRODUCT_UPDATE, as brands are.
    "principals": ImportKind("Principals", "PRODUCT_UPDATE", _principals),
    # The salesman list is kept under SALESMAN_MANAGE, so its import is too.
    "salesmen": ImportKind("Salesmen", "SALESMAN_MANAGE", _salesmen),
    # The chart of accounts is kept under ACCOUNT_MANAGE, so its import is too.
    # The old program's head names are read as our account groups (G6).
    "ledger-accounts": ImportKind(
        "Chart of accounts",
        "ACCOUNT_MANAGE",
        _ledger_accounts,
        value_columns=("Group",),
    ),
    # A route is made on the territory form, under TERRITORY_CREATE.
    "routes": ImportKind("Routes", "TERRITORY_CREATE", _routes),
    # A segment is kept under CUSTOMER_MANAGE_SETTINGS, so its import is too.
    "segments": ImportKind("Customer segments", "CUSTOMER_MANAGE_SETTINGS", _segments),
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


def value_columns_for_kind(kind: str) -> tuple[str, ...]:
    """Return the template columns whose values one import lets a firm map."""
    return kind_of(kind).value_columns


def mapped_content(
    content: bytes,
    file_format: FileFormat,
    mapping: Mapping[str, str | None] | None,
    columns: tuple[Column, ...],
    value_mapping: Mapping[str, Mapping[str, str]] | None = None,
    *,
    value_columns: tuple[str, ...] = (),
) -> tuple[bytes, FileFormat]:
    """Apply a mapping to an uploaded file, or hand it back as it came.

    The import endpoints call this before their own check, so a file mapped
    on the screen is read exactly as mapped and an unmapped one as before.
    Headings are remapped first; then, for a column in ``value_columns``,
    each cell ``value_mapping`` names is replaced by our value (Swathi G6).
    A value it does not name passes through unchanged.

    Raises:
        ValidationError: When ``value_mapping`` names a column this import
            does not let a firm map.

    """
    if mapping:
        content = remap_headings(content, file_format, mapping, columns)
        file_format = "csv"
    if not value_mapping or not any(value_mapping.values()):
        return content, file_format
    _refuse_unmappable(value_mapping, value_columns)
    return _remap_values(content, file_format, value_mapping, columns), "csv"


def _refuse_unmappable(
    value_mapping: Mapping[str, Mapping[str, str]], value_columns: tuple[str, ...]
) -> None:
    """Refuse a value mapping for a column the import does not declare."""
    unknown = sorted(set(value_mapping) - set(value_columns))
    if unknown:
        allowed = ", ".join(value_columns) if value_columns else "none"
        raise ValidationError(
            "Values cannot be mapped for "
            + ", ".join(unknown)
            + f" in this import; the columns that can be are: {allowed}."
        )


def _value_key(value: str) -> str:
    """Normalise a cell for matching a value mapping: trimmed, any case."""
    return value.strip().casefold()


def _column_positions(header: list[str], columns: tuple[Column, ...]) -> dict[str, int]:
    """Return where each template column is read from, as ``read_rows`` does."""
    lookup = heading_lookup(columns)
    positions: dict[str, int] = {}
    for position, heading in enumerate(header):
        target = lookup.get(normalise_heading(heading))
        if target is not None and target not in positions:
            positions[target] = position
    return positions


def _remap_values(
    content: bytes,
    file_format: FileFormat,
    value_mapping: Mapping[str, Mapping[str, str]],
    columns: tuple[Column, ...],
) -> bytes:
    """Rewrite the mapped columns' cells as our values, as CSV (G6)."""
    header, rows = read_grid(content, file_format)
    if not header:
        return b""
    positions = _column_positions(header, columns)
    plan = [
        (positions[column], {_value_key(k): v for k, v in values.items()})
        for column, values in value_mapping.items()
        if column in positions and values
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        cells = list(row)
        for position, translate in plan:
            if position < len(cells):
                ours = translate.get(_value_key(cells[position]))
                if ours is not None:
                    cells[position] = ours
        writer.writerow(cells)
    return out.getvalue().encode("utf-8")


def parse_value_mapping(raw: str | None) -> dict[str, dict[str, str]] | None:
    """Read the ``value_mapping`` form field an import endpoint is sent (G6).

    JSON: an object from template column to an object from the source
    program's value to ours. Absent or empty means no value is translated.

    Raises:
        ValidationError: When it is not such an object.

    """
    if raw is None or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("The value mapping is not valid JSON.") from exc
    if not isinstance(value, dict) or not all(
        isinstance(column, str)
        and isinstance(values, dict)
        and all(
            isinstance(source, str) and isinstance(ours, str)
            for source, ours in values.items()
        )
        for column, values in value.items()
    ):
        raise ValidationError(
            "The value mapping must name, for each template column, an object "
            "from the file's value to ours."
        )
    return {column: dict(values) for column, values in value.items()}


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


def _clean_value_mapping(
    value_mapping: Mapping[str, Mapping[str, str]] | None,
) -> dict[str, dict[str, str]] | None:
    """Drop blank source values and empty columns; nothing left is null."""
    if not value_mapping:
        return None
    cleaned = {
        column: {
            source.strip(): ours.strip()
            for source, ours in values.items()
            if source.strip() and ours.strip()
        }
        for column, values in value_mapping.items()
    }
    kept = {column: values for column, values in cleaned.items() if values}
    return kept or None


#: Distinct values shown per mappable column on the mapping screen.
MAX_FILE_VALUES = 500


def _file_values(
    content: bytes,
    file_format: FileFormat,
    suggested: Mapping[str, str | None],
    value_columns: tuple[str, ...],
) -> dict[str, list[str]]:
    """Return the distinct values the file holds for each mappable column."""
    if not value_columns:
        return {}
    header, rows = read_grid(content, file_format)
    found: dict[str, list[str]] = {}
    for column in value_columns:
        position = next(
            (
                index
                for index, heading in enumerate(header)
                if suggested.get(heading) == column
            ),
            None,
        )
        if position is None:
            continue
        seen: dict[str, None] = {}
        for row in rows:
            value = row[position].strip() if position < len(row) else ""
            if value and value not in seen:
                seen[value] = None
                if len(seen) >= MAX_FILE_VALUES:
                    break
        found[column] = list(seen)
    return found


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
        suggested = suggest_mapping(headings, columns)
        value_columns = value_columns_for_kind(kind)
        return ImportPreview(
            value_columns=list(value_columns),
            file_values=_file_values(content, file_format, suggested, value_columns),
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
            suggested=suggested,
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
        if data.value_mapping:
            _refuse_unmappable(data.value_mapping, value_columns_for_kind(kind))
        name = data.name.strip()
        row = self._session.scalar(
            select(ImportMapping).where(
                ImportMapping.firm_id == firm_id,
                ImportMapping.kind == kind,
                ImportMapping.name == name,
                ImportMapping.is_deleted.is_(False),
            )
        )
        before: dict[str, object] | None = (
            None
            if row is None
            else {"mapping": dict(row.mapping), "value_mapping": row.value_mapping}
        )
        # Left out keeps what is saved; an explicit null clears it.
        sent_values = "value_mapping" in data.model_fields_set
        new_values = _clean_value_mapping(data.value_mapping)
        if row is None:
            row = ImportMapping(
                firm_id=firm_id,
                kind=kind,
                name=name,
                mapping=dict(data.mapping),
                value_mapping=new_values,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
        else:
            row.mapping = dict(data.mapping)
            if sent_values:
                row.value_mapping = new_values
            row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="import_mapping.saved",
            entity_type="import_mapping",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={
                "kind": kind,
                "name": name,
                "mapping": dict(data.mapping),
                "value_mapping": row.value_mapping,
            },
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
