"""Bring a firm's stock on hand at cutover in from one spreadsheet.

Backlog 36 and 46. A firm moving from Tally or Excel counts its shelves on the
cutover day and brings the count as one file, the way its products and
customers came in: download a template, fill it, check it -- every problem by
row and column, nothing written -- then import all of it or none of it. The
reading and the report are ``app.common.file_import``'s. What is particular to
opening stock:

* **One file, many warehouses.** Rows are grouped by warehouse into one
  opening-stock document each, numbered ``OS-IMPORT-<date>-<warehouse>``, all
  on the posting date chosen on the screen, and every one is **created and
  posted** in one transaction -- the same ``stage_*`` methods the form's
  create and post run, committed once.
* **Opening stock is posted once per warehouse.** A warehouse that already has
  posted opening stock is refused by name; a correction is a stock adjustment.
* **Tracking is the product's, not the file's.** A batch-tracked product needs
  a batch and a plain one may not have one; an expiry-tracked product needs an
  expiry unless its batch is already dated; serial-numbered stock is refused,
  because an opening-stock line carries no serial numbers.
* **The same stock twice is refused on the second row**, naming the first:
  one product, one warehouse, one batch.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.branches.models import Warehouse
from app.common import file_import
from app.common.file_import import (
    Column,
    FileFormat,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    read_rows,
)
from app.core.exceptions import ApplicationError
from app.inventory.models import OpeningStockBatch
from app.inventory.schemas import OpeningStockBatchCreate, OpeningStockLineCreate
from app.inventory.services.inventory_service import InventoryService
from app.products.models import Product
from app.uom.models import Uom

__all__ = [
    "COLUMNS",
    "LIST_PRODUCT_CAP",
    "OpeningStockFileImporter",
    "parse_date",
    "template_csv",
    "template_workbook",
]

#: The Lists sheet names at most this many products. Every code the firm has
#: is accepted whether it is listed or not; the list is a convenience.
LIST_PRODUCT_CAP = 2000

COLUMNS: tuple[Column, ...] = (
    Column(
        "ProductCode",
        ("code", "itemcode", "sku", "productcode", "stockitemcode", "partno"),
        True,
        "The product's code, as on its screen (see the Lists sheet).",
        "SKU-001",
    ),
    Column(
        "Warehouse",
        ("warehousecode", "warehousename", "godown", "location", "store"),
        False,
        "The warehouse's code or name. Required unless the firm has exactly "
        "one warehouse; blank then means that one.",
        "MAIN",
    ),
    Column(
        "Quantity",
        ("qty", "closingqty", "closingquantity", "stock", "openingqty"),
        True,
        "How much is on the shelf on the cutover day; more than 0.",
        "10",
    ),
    Column(
        "UnitCost",
        ("rate", "cost", "costprice", "purchaserate", "valuationrate"),
        False,
        "What one unit was worth on the cutover day. Blank is allowed, but "
        "stock without a cost is worth nothing in the valuation and the ledger.",
        "120.00",
    ),
    Column(
        "Batch",
        ("batchno", "batchnumber", "lot", "lotno"),
        False,
        "Required for a batch-tracked product; refused for one that is not.",
        "",
    ),
    Column(
        "Expiry",
        ("expirydate", "expdate", "exp", "bestbefore"),
        False,
        "Required for an expiry-tracked product whose batch is not already "
        "dated. dd-mm-yyyy, dd/mm/yyyy, yyyy-mm-dd or an Excel date.",
        "",
    ),
    Column(
        "Unit",
        ("uom", "units", "unitofmeasure"),
        False,
        "The unit the quantity is counted in, if not the product's own; it "
        "needs a conversion to the product's unit.",
        "",
    ),
    Column(
        "Remarks",
        ("narration", "notes", "remark"),
        False,
        "Free text, kept on the line.",
        "",
    ),
)

_EXCEL_EPOCH = date(1899, 12, 30)
_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def parse_date(raw: str) -> date | None:
    """Read a day the ways a spreadsheet writes one; None if it is not one.

    dd-mm-yyyy and dd/mm/yyyy are read day first, as India writes them;
    yyyy-mm-dd is what an Excel date cell reads as, with or without a time;
    a bare number between 20000 and 80000 is an Excel serial day.
    """
    text = raw.strip()
    try:
        if matched := _DMY.match(text):
            day, month, year = (int(part) for part in matched.groups())
            return date(year, month, day)
        if matched := _YMD.match(text):
            year, month, day = (int(part) for part in matched.groups())
            return date(year, month, day)
        if text.isdigit() and 20000 <= int(text) <= 80000:
            return _EXCEL_EPOCH + timedelta(days=int(text))
    except ValueError:
        return None
    return None


def _is_batch_tracked(product: Product) -> bool:
    """Say whether the product's stock is kept in batches.

    An expiry-tracked product counts: its expiry date is kept on the batch, so
    without one there is nowhere to record it.
    """
    return bool(
        product.track_batch
        or product.track_lot
        or product.require_batch_on_receipt
        or product.track_expiry
    )


def _is_serial_tracked(product: Product) -> bool:
    """Say whether the product's stock is kept by serial number."""
    return bool(product.track_serial or product.require_serial_on_receipt)


@dataclass
class _Line:
    """One checked row, ready to become an opening-stock line."""

    row: int
    product: Product
    line: OpeningStockLineCreate


@dataclass
class _Reference:
    """The firm's stock references, read once per file."""

    products: dict[str, Product]
    warehouses: list[Warehouse]
    units: dict[str, Uom]
    opened: dict[UUID, str]
    batches: dict[tuple[UUID, str], date | None]


def _read_references(session: Session, firm_id: UUID) -> _Reference:
    """Read the products, warehouses, units and opened warehouses once."""
    products = {
        product.code.strip().upper(): product
        for product in session.scalars(
            select(Product).where(
                Product.firm_id == firm_id, Product.is_deleted.is_(False)
            )
        ).all()
    }
    warehouses = list(
        session.scalars(
            select(Warehouse)
            .where(Warehouse.firm_id == firm_id, Warehouse.is_deleted.is_(False))
            .order_by(Warehouse.code)
        ).all()
    )
    units: dict[str, Uom] = {}
    stored_units = session.scalars(
        select(Uom).where(Uom.is_deleted.is_(False), Uom.status == "ACTIVE")
    ).all()
    # Codes win over names and symbols: filled last so they overwrite.
    for unit in stored_units:
        if unit.symbol:
            units.setdefault(unit.symbol.strip().lower(), unit)
    for unit in stored_units:
        units[unit.name.strip().lower()] = unit
    for unit in stored_units:
        units[unit.code.strip().lower()] = unit
    opened = {
        warehouse_id: reference
        for warehouse_id, reference in session.execute(
            select(OpeningStockBatch.warehouse_id, OpeningStockBatch.reference_number)
            .where(
                OpeningStockBatch.firm_id == firm_id,
                OpeningStockBatch.status == "POSTED",
                OpeningStockBatch.is_deleted.is_(False),
            )
            .order_by(OpeningStockBatch.posting_date)
        ).all()
    }
    batches = {
        (product_id, number): expiry
        for product_id, number, expiry in session.execute(
            select(
                BatchRecord.product_id,
                BatchRecord.batch_number,
                BatchRecord.expiry_date,
            ).where(BatchRecord.firm_id == firm_id, BatchRecord.is_deleted.is_(False))
        ).all()
    }
    return _Reference(products, warehouses, units, opened, batches)


def _find_warehouse(warehouses: Sequence[Warehouse], value: str) -> Warehouse | None:
    """Find a warehouse by code, then by name, ignoring case."""
    wanted = value.strip().lower()
    for warehouse in warehouses:
        if warehouse.code.strip().lower() == wanted:
            return warehouse
    for warehouse in warehouses:
        if warehouse.name.strip().lower() == wanted:
            return warehouse
    return None


class OpeningStockFileImporter:
    """Check an opening-stock file row by row, and import it whole or not at all."""

    NOUN = "opening stock"

    def __init__(self, session: Session) -> None:
        """Work on one request's session."""
        self._session = session
        self._service = InventoryService(session)

    def run(
        self,
        content: bytes,
        *,
        file_format: FileFormat,
        firm_id: UUID,
        actor_id: UUID,
        posting_date: date,
        apply: bool,
    ) -> ImportReport[OpeningStockBatch]:
        """Check every row; with ``apply``, create and post the file whole.

        A clean check still stages and posts every document before rolling
        back, so a firm with no chart of accounts or a closed period is told
        on the check rather than on the import. Nothing is written unless
        ``apply`` is set and nothing at all went wrong.
        """
        rows, used, ignored = read_rows(content, file_format, COLUMNS)
        report: ImportReport[OpeningStockBatch] = ImportReport(
            columns_used=used, columns_ignored=ignored
        )
        missing = [
            column.heading
            for column in COLUMNS
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
        reference = _read_references(self._session, firm_id)
        groups: dict[UUID, list[_Line]] = {}
        seen: dict[tuple[UUID, UUID, str], int] = {}
        for row in rows:
            if not any(row.cells.values()):
                report.skipped_blank += 1
                continue
            report.rows += 1
            checked = self._check_row(
                row, reference, firm_id, posting_date, seen, report
            )
            if checked is not None:
                warehouse, line = checked
                groups.setdefault(warehouse.id, []).append(line)
        if report.rows == 0 and not report.issues:
            report.issues.append(
                ImportIssue(1, None, None, "The file has no opening stock rows.")
            )
        if report.issues:
            return report
        try:
            self._stage(groups, reference, firm_id, actor_id, posting_date, report)
        except Exception:
            self._session.rollback()
            raise
        if not apply or report.issues:
            self._session.rollback()
            report.records = []
            return report
        self._service._commit()
        for record in report.records:
            self._session.refresh(record)
        report.imported = True
        return report

    def _check_row(
        self,
        row: ImportRow,
        reference: _Reference,
        firm_id: UUID,
        posting_date: date,
        seen: dict[tuple[UUID, UUID, str], int],
        report: ImportReport[OpeningStockBatch],
    ) -> tuple[Warehouse, _Line] | None:
        """Check one row against the firm's records; nothing is written."""
        code = row.cells.get("ProductCode", "").strip().upper()
        issues: list[ImportIssue] = []
        reader = RowReader(row, code, issues)
        product = reference.products.get(code) if code else None
        if not code:
            reader.fail("ProductCode", "is required.")
        elif product is None:
            reader.fail("ProductCode", f"'{code}' is not one of the firm's products.")
        elif product.product_type == "SERVICE":
            reader.fail("ProductCode", f"{code} is a service and holds no stock.")
            product = None
        elif _is_serial_tracked(product):
            reader.fail(
                "ProductCode",
                f"{code} is serial-numbered. Serial-numbered stock is entered on "
                "screen, one serial at a time.",
            )
            product = None
        warehouse = self._warehouse(reader, reference)
        if warehouse is not None and warehouse.id in reference.opened:
            reader.fail(
                "Warehouse",
                f"{warehouse.code} already has posted opening stock "
                f"({reference.opened[warehouse.id]}). Opening stock is posted "
                "once; correct it with a stock adjustment.",
            )
            warehouse = None
        quantity = reader.number("Quantity")
        if quantity is None and not reader.text("Quantity"):
            reader.fail("Quantity", "is required.")
        elif quantity is not None and quantity <= 0:
            reader.fail("Quantity", "must be more than 0.")
            quantity = None
        unit_cost = reader.number("UnitCost")
        if unit_cost is not None and unit_cost < 0:
            reader.fail("UnitCost", "cannot be negative.")
            unit_cost = None
        batch = reader.text("Batch")
        expiry = self._expiry(reader)
        if product is not None:
            self._check_tracking(reader, reference, product, batch, expiry)
        unit_id = self._unit(reader, reference)
        if product is not None and quantity is not None and not issues:
            try:
                self._service._resolve_base_quantity(
                    firm_scope=firm_id,
                    product_id=product.id,
                    quantity=quantity,
                    entered_uom_id=unit_id,
                    conversion_version=None,
                    on_date=posting_date,
                )
            except ApplicationError as error:
                reader.fail("Unit" if unit_id else "Quantity", error.message)
        if product is not None and warehouse is not None and not issues:
            key = (product.id, warehouse.id, batch)
            if key in seen:
                reader.fail(
                    "Batch" if batch else "ProductCode",
                    f"appears again for {warehouse.code}; row {seen[key]} "
                    "already has this product"
                    + (f" in batch {batch}." if batch else "."),
                )
            else:
                seen[key] = row.number
        if issues:
            report.issues.extend(issues)
            return None
        if product is None or warehouse is None or quantity is None:
            return None
        report.to_create += 1
        return warehouse, _Line(
            row=row.number,
            product=product,
            line=OpeningStockLineCreate(
                product_id=product.id,
                quantity=quantity,
                unit_cost=unit_cost,
                entered_quantity=quantity if unit_id else None,
                entered_uom_id=unit_id,
                batch_number=batch or None,
                expiry_date=expiry,
                remarks=reader.text("Remarks") or None,
            ),
        )

    @staticmethod
    def _warehouse(reader: RowReader, reference: _Reference) -> Warehouse | None:
        """Resolve the row's warehouse; blank means the only one there is."""
        value = reader.text("Warehouse")
        if not value:
            if len(reference.warehouses) == 1:
                return reference.warehouses[0]
            if not reference.warehouses:
                reader.fail("Warehouse", "the firm has no warehouse yet.")
            else:
                reader.fail(
                    "Warehouse",
                    f"is required; the firm has {len(reference.warehouses)} "
                    "warehouses.",
                )
            return None
        warehouse = _find_warehouse(reference.warehouses, value)
        if warehouse is None:
            reader.fail("Warehouse", f"'{value}' is not one of the firm's.")
        return warehouse

    @staticmethod
    def _expiry(reader: RowReader) -> date | None:
        """Read the expiry cell, naming it when it is not a date."""
        raw = reader.text("Expiry")
        if not raw:
            return None
        parsed = parse_date(raw)
        if parsed is None:
            reader.fail(
                "Expiry",
                f"'{raw}' is not a date. Write it as dd-mm-yyyy, dd/mm/yyyy "
                "or yyyy-mm-dd.",
            )
        return parsed

    @staticmethod
    def _check_tracking(
        reader: RowReader,
        reference: _Reference,
        product: Product,
        batch: str,
        expiry: date | None,
    ) -> None:
        """Hold the row to the product's batch and expiry tracking."""
        tracked = _is_batch_tracked(product)
        if tracked and not batch:
            reader.fail(
                "Batch",
                f"is required: {product.code} is "
                + (
                    "expiry-tracked, and an expiry is kept on a batch."
                    if product.track_expiry and not product.track_batch
                    else "batch-tracked."
                ),
            )
        elif batch and not tracked:
            reader.fail(
                "Batch",
                f"{product.code} is not batch-tracked; leave the batch blank.",
            )
        if expiry is not None and not tracked:
            reader.fail(
                "Expiry",
                f"{product.code} is not expiry-tracked; leave the expiry blank.",
            )
            return
        if not batch or not tracked:
            return
        known = (product.id, batch) in reference.batches
        dated = reference.batches.get((product.id, batch))
        if product.track_expiry and expiry is None and dated is None:
            reader.fail("Expiry", f"is required: {product.code} is expiry-tracked.")
        elif known and dated is not None and expiry is not None and expiry != dated:
            reader.fail(
                "Expiry",
                f"batch {batch} of {product.code} is already registered expiring "
                f"{dated:%d-%m-%Y}.",
            )

    @staticmethod
    def _unit(reader: RowReader, reference: _Reference) -> UUID | None:
        """Resolve the unit the quantity was counted in, if the row names one."""
        value = reader.text("Unit")
        if not value:
            return None
        unit = reference.units.get(value.strip().lower())
        if unit is None:
            reader.fail("Unit", f"'{value}' is not a unit on this system.")
            return None
        return unit.id

    def _stage(
        self,
        groups: dict[UUID, list[_Line]],
        reference: _Reference,
        firm_id: UUID,
        actor_id: UUID,
        posting_date: date,
        report: ImportReport[OpeningStockBatch],
    ) -> None:
        """Create and post one document per warehouse, without committing.

        The first failure stops the staging: the session may hold half a
        document by then, and it is rolled back whatever else is found.
        """
        warehouses = {warehouse.id: warehouse for warehouse in reference.warehouses}
        taken = set(
            self._session.scalars(
                select(OpeningStockBatch.reference_number).where(
                    OpeningStockBatch.firm_id == firm_id
                )
            ).all()
        )
        for warehouse_id, lines in groups.items():
            warehouse = warehouses[warehouse_id]
            number = _reference_number(posting_date, warehouse.code, taken)
            taken.add(number)
            try:
                batch = self._service.stage_opening_stock_batch(
                    OpeningStockBatchCreate(
                        branch_id=warehouse.branch_id,
                        warehouse_id=warehouse.id,
                        reference_number=number,
                        posting_date=posting_date,
                        remarks="Imported from a file.",
                        lines=[item.line for item in lines],
                    ),
                    firm_id=firm_id,
                    actor_id=actor_id,
                    source_format="FILE",
                )
                self._service.stage_post_opening_stock_batch(
                    batch, firm_scope=firm_id, actor_id=actor_id
                )
            except ApplicationError as error:
                report.issues.append(
                    ImportIssue(
                        lines[0].row,
                        lines[0].product.code,
                        "Warehouse",
                        f"{warehouse.code} could not be posted: {error.message}",
                    )
                )
                return
            report.records.append(batch)


def _reference_number(posting_date: date, warehouse_code: str, taken: set[str]) -> str:
    """Name a document ``OS-IMPORT-<yyyymmdd>-<warehouse>``, unique in the firm.

    Checked against every reference the firm has ever used, deleted ones
    included, because the database's uniqueness covers them too.
    """
    code = re.sub(r"[^A-Z0-9-]", "", warehouse_code.upper())[:40] or "WH"
    base = f"OS-IMPORT-{posting_date:%Y%m%d}-{code}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _examples(session: Session, firm_id: UUID) -> tuple[Column, ...]:
    """Fill the example row from the firm's own records, so it imports as is.

    The first product that is neither batch-, serial- nor expiry-tracked and
    the first warehouse; a firm with neither keeps the illustrative example.
    """
    product = session.scalar(
        select(Product)
        .where(
            Product.firm_id == firm_id,
            Product.is_deleted.is_(False),
            Product.product_type != "SERVICE",
            Product.track_batch.is_(False),
            Product.track_lot.is_(False),
            Product.track_serial.is_(False),
            Product.track_expiry.is_(False),
            Product.require_batch_on_receipt.is_(False),
            Product.require_serial_on_receipt.is_(False),
        )
        .order_by(Product.code)
        .limit(1)
    )
    warehouse = session.scalar(
        select(Warehouse)
        .where(Warehouse.firm_id == firm_id, Warehouse.is_deleted.is_(False))
        .order_by(Warehouse.code)
        .limit(1)
    )
    examples: dict[str, str] = {}
    if product is not None:
        examples["ProductCode"] = product.code
    if warehouse is not None:
        examples["Warehouse"] = warehouse.code
    return tuple(
        (
            replace(column, example=examples[column.heading])
            if column.heading in examples
            else column
        )
        for column in COLUMNS
    )


def template_workbook(session: Session, firm_id: UUID) -> bytes:
    """Build the XLSX template: the sheet to fill, the notes, and the lists."""
    reference = _read_references(session, firm_id)
    products = sorted(reference.products.values(), key=lambda item: item.code)
    stocked = [
        item
        for item in products
        if item.product_type != "SERVICE" and not _is_serial_tracked(item)
    ]
    listed = stocked[:LIST_PRODUCT_CAP]
    notes = [
        "One row is the stock of one product in one warehouse (and one batch, "
        "for a batch-tracked product). Rows are grouped into one opening stock "
        "document per warehouse, all on the posting date chosen on screen, and "
        "every document is posted as it is imported.",
        "A warehouse that already has posted opening stock is refused; correct "
        "its stock with a stock adjustment instead.",
        "Stock with no UnitCost is recorded at zero value: it adds nothing to "
        "the stock valuation or the ledger.",
        "Serial-numbered products are not imported from a file; enter their "
        "stock on screen, one serial at a time.",
        "Minimum, maximum and reorder levels are not part of this file; set "
        "them on the stock screen.",
        "Posting needs the firm's chart of accounts and an open period on the "
        "posting date when any row has a cost.",
    ]
    if len(stocked) > LIST_PRODUCT_CAP:
        notes.append(
            f"The Lists sheet shows the first {LIST_PRODUCT_CAP:,} of "
            f"{len(stocked):,} products; every product code the firm has is "
            "accepted."
        )
    return file_import.template_workbook(
        sheet_title="Opening stock",
        columns=_examples(session, firm_id),
        notes=notes,
        lists_header=[
            "Warehouse code",
            "Warehouse name",
            "",
            "Product code",
            "Product name",
            "Batch",
            "Expiry",
        ],
        lists=[
            [item.code for item in reference.warehouses],
            [item.name for item in reference.warehouses],
            [],
            [item.code for item in listed],
            [item.name for item in listed],
            ["Required" if _is_batch_tracked(item) else "" for item in listed],
            ["Required" if item.track_expiry else "" for item in listed],
        ],
    )


def template_csv(session: Session, firm_id: UUID) -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(_examples(session, firm_id))
