"""Transactional service for enterprise batch, lot, serial, and expiry management."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Table, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models.batch_serial import (
    BatchRecord,
    DocumentLineSerial,
    LotRecord,
    SerialNumber,
)
from app.batch_serial.schemas.batch_serial import (
    BatchAvailability,
    BatchCreate,
    BatchListFilters,
    BatchResponse,
    BatchStatus,
    BatchSummary,
    BatchUpdate,
    ExpiryDashboard,
    LotCreate,
    LotListFilters,
    LotUpdate,
    SerialCreate,
    SerialListFilters,
    SerialUpdate,
)
from app.batch_serial.services.product_tracking import (
    FIELD_SWITCHES,
    assert_date_order,
    assert_product_fields,
    assert_product_keeps,
    tracked_product,
)
from app.branches.models import Branch, Warehouse
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.concurrency import assert_version
from app.core.database.base import Base
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.inventory.schemas import BatchStockTotals
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales_order.models import SalesOrder, SalesOrderLine

ZERO = Decimal("0")

#: What an audit row records of each record, named like the rest of the
#: platform's ``module.action`` rows rather than bare ``CREATE`` (D-STK-10).
_AUDITED_FIELDS: dict[str, tuple[str, ...]] = {
    "batch": (
        "batch_number",
        "product_id",
        "status",
        "manufacturing_date",
        "expiry_date",
        "best_before_date",
        "supplier_batch",
        "internal_batch",
        "shelf_life_days",
        "mrp",
        "ptr",
        "pts",
    ),
    "lot": (
        "lot_number",
        "product_id",
        "lot_type",
        "status",
        "quantity",
        "production_date",
        "expiry_date",
    ),
    "serial_number": (
        "serial_number",
        "product_id",
        "batch_id",
        "status",
        "warranty_start",
        "warranty_end",
        "current_owner",
    ),
}


#: The dates of a batch that are judged against one another.
_BATCH_DATES = frozenset({"manufacturing_date", "expiry_date", "best_before_date"})


#: The tables that are the stock itself. A record they name has moved, which
#: reads differently to a person than a document that merely names it.
_STOCK_TABLES = frozenset(
    {"inventories", "inventory_transactions", "stock_ledger_entries"}
)


def batch_holds_stock() -> ColumnElement[bool]:
    """Return the condition that a batch still holds stock somewhere.

    On the shelf, in quarantine, damaged or blocked. This is the one test of
    "is there anything left to act on" for the expiry cards: the dashboard
    had it and the summary card did not, so the two disagreed about an
    emptied batch (D-STK-8, D-STK-18).
    """
    return (
        select(InventoryRecord.id)
        .where(
            InventoryRecord.batch_id == BatchRecord.id,
            InventoryRecord.is_deleted.is_(False),
            (
                InventoryRecord.current_quantity
                + InventoryRecord.quarantine_quantity
                + InventoryRecord.damaged_quantity
                + InventoryRecord.blocked_quantity
            )
            > 0,
        )
        .exists()
    )


def required_number(value: object, *, label: str) -> str:
    """Return a batch, lot or serial number trimmed, refusing a blank one.

    The schema asks for one character and a space is one, so a batch numbered
    "   " was saved and could never be found or typed again (F17).

    Raises:
        ValidationError: If nothing but spaces was given.

    """
    number = value.strip() if isinstance(value, str) else ""
    if not number:
        raise ValidationError(
            f"{label} is required: it cannot be blank or only spaces."
        )
    return number


def _changed(record: object, values: Mapping[str, object]) -> dict[str, object]:
    """Return the submitted values that differ from what the record holds."""
    return {
        name: value
        for name, value in values.items()
        if getattr(record, name, None) != value
    }


def _snapshot(entity_type: str, record: object) -> dict[str, object]:
    """Return the audited fields of a record, stringified for the trail."""
    values: dict[str, object] = {}
    for name in _AUDITED_FIELDS[entity_type]:
        value = getattr(record, name, None)
        values[name] = None if value is None else str(value)
    return values


def assert_warranty_order(start: date | None, end: date | None) -> None:
    """Refuse a warranty that ends before it starts (inventory round 1, S6).

    Nothing to judge where either date is blank.
    """
    if start is not None and end is not None and end < start:
        raise ValidationError(
            f"The warranty end {end.isoformat()} is before the warranty start "
            f"{start.isoformat()}. Check the two dates."
        )


def assert_trade_rates_within_mrp(
    *,
    mrp: Decimal | None,
    ptr: Decimal | None,
    pts: Decimal | None,
    selling_price: Decimal | None = None,
) -> None:
    """Refuse a price to retailer or stockist above the batch's MRP (PG-14).

    Both are trade rates before tax and the MRP is the most anyone may charge
    with tax, so a trade rate above it is a typing mistake, not a price.
    Nothing to judge where either side is blank.

    The two rates are held in order as well: **PTS at or below PTR** (D-PRC-18).
    A stockist sells on to the retailer, so a price to stockist above the
    price to retailer is the two boxes filled the wrong way round -- and it
    bills the firm's largest buyers more than its smallest. Judged whether or
    not the batch has an MRP, on every path that writes a rate: all of them
    come through here.

    ``selling_price`` is the batch's own selling price, where the caller is
    writing the batch itself: 90 against an MRP of 50 saved without a word
    while PTR and PTS were held under it (D-STK-49).

    Raises:
        ValidationError: When a rate exceeds the MRP, or PTS exceeds PTR.

    """
    if mrp is not None:
        for label, rate in (
            ("PTR", ptr),
            ("PTS", pts),
            ("Selling price", selling_price),
        ):
            if rate is not None and rate > mrp:
                raise ValidationError(
                    f"{label} {rate:.2f} cannot exceed the MRP {mrp:.2f}."
                )
    if ptr is not None and pts is not None and pts > ptr:
        raise ValidationError(
            f"PTS {pts:.2f} cannot exceed the PTR {ptr:.2f}: a stockist buys at "
            "or below the price to a retailer."
        )


def expiry_from_shelf_life(
    manufactured: date | None, shelf_life_days: int | None
) -> date | None:
    """Return the expiry a manufacturing date and a shelf life make (STK-18).

    None where either is missing: an expiry is filled, never guessed.
    """
    if manufactured is None or not shelf_life_days:
        return None
    return manufactured + timedelta(days=shelf_life_days)


class BatchSerialService:
    """Coordinate batch, lot, serial number, and expiry lifecycle operations."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    # ── Batch ────────────────────────────────────────────────────────────────

    def list_batches(
        self,
        *,
        firm_scope: UUID,
        filters: BatchListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[BatchRecord], int]:
        """Return a page of batches for the firm in scope."""
        columns = {
            "created_at": BatchRecord.created_at,
            "updated_at": BatchRecord.updated_at,
            "batch_number": BatchRecord.batch_number,
            "expiry_date": BatchRecord.expiry_date,
            "status": BatchRecord.status,
        }
        stmt = select(BatchRecord).where(
            BatchRecord.firm_id == firm_scope, BatchRecord.is_deleted.is_(False)
        )
        count_stmt = (
            select(func.count())
            .select_from(BatchRecord)
            .where(BatchRecord.firm_id == firm_scope, BatchRecord.is_deleted.is_(False))
        )
        if filters.product_id:
            stmt = stmt.where(BatchRecord.product_id == filters.product_id)
            count_stmt = count_stmt.where(BatchRecord.product_id == filters.product_id)
        if filters.warehouse_id:
            stmt = stmt.where(BatchRecord.warehouse_id == filters.warehouse_id)
            count_stmt = count_stmt.where(
                BatchRecord.warehouse_id == filters.warehouse_id
            )
        if filters.branch_id:
            stmt = stmt.where(BatchRecord.branch_id == filters.branch_id)
            count_stmt = count_stmt.where(BatchRecord.branch_id == filters.branch_id)
        if filters.status:
            stmt = stmt.where(BatchRecord.status == filters.status)
            count_stmt = count_stmt.where(BatchRecord.status == filters.status)
        if filters.expiry_before:
            stmt = stmt.where(BatchRecord.expiry_date <= filters.expiry_before)
            count_stmt = count_stmt.where(
                BatchRecord.expiry_date <= filters.expiry_before
            )
        if filters.expiry_after:
            stmt = stmt.where(BatchRecord.expiry_date >= filters.expiry_after)
            count_stmt = count_stmt.where(
                BatchRecord.expiry_date >= filters.expiry_after
            )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(BatchRecord.batch_number.ilike(term))
            count_stmt = count_stmt.where(BatchRecord.batch_number.ilike(term))
        col = columns.get(sort_by, BatchRecord.created_at)
        stmt = stmt.order_by(col.desc() if descending else col.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = list(self._session.scalars(stmt).all())
        total = int(self._session.scalar(count_stmt) or 0)
        return rows, total

    def batch_responses(
        self, records: Sequence[BatchRecord], *, firm_scope: UUID
    ) -> list[BatchResponse]:
        """Render batches with the stock each one is actually holding.

        The six quantities are read from `inventories`, not from the batch. A
        batch is a register entry -- number, expiry, vendor, status -- and how
        much of it is on the shelf is a consequence of the movements that put
        it there. It used to be both, and the two answers drifted the moment
        anything moved stock without going through the batch API.

        The product, warehouse and branch a batch belongs to are named here
        too. The response has declared those six fields since it was written
        and nothing ever filled them, so the desktop's batch grid rendered a
        product column reading " - " and a warehouse column reading "—" for
        every row -- the batch register was unreadable without knowing UUIDs.

        Four queries serve the whole page, however many batches are on it: one
        for the stock and one for each kind of name. Looking a name up per row
        is the shape that makes a twenty-row page eighty queries.
        """
        totals = InventoryService(self._session).stock_by_batch(
            firm_scope=firm_scope, batch_ids=[record.id for record in records]
        )
        products = self._names(Product, {record.product_id for record in records})
        warehouses = self._names(Warehouse, {record.warehouse_id for record in records})
        branches = self._names(Branch, {record.branch_id for record in records})
        empty = BatchStockTotals()
        responses = []
        for record in records:
            held = totals.get(record.id, empty)
            product_code, product_name = self._named(products, record.product_id)
            warehouse_code, warehouse_name = self._named(
                warehouses, record.warehouse_id
            )
            branch_code, branch_name = self._named(branches, record.branch_id)
            responses.append(
                BatchResponse.model_validate(record).model_copy(
                    update={
                        "quantity": held.current_quantity,
                        "available_quantity": held.available_quantity,
                        "reserved_quantity": held.reserved_quantity,
                        "blocked_quantity": held.blocked_quantity,
                        "damaged_quantity": held.damaged_quantity,
                        "quarantine_quantity": held.quarantine_quantity,
                        "product_code": product_code,
                        "product_name": product_name,
                        "warehouse_code": warehouse_code,
                        "warehouse_name": warehouse_name,
                        "branch_code": branch_code,
                        "branch_name": branch_name,
                    }
                )
            )
        return responses

    def _named(
        self, lookup: dict[UUID, tuple[str, str]], record_id: UUID | None
    ) -> tuple[str | None, str | None]:
        """Read one code and name out of a bulk lookup, or nulls.

        A batch's warehouse and branch are optional, and a record can be
        missing -- a soft-deleted product still has batches. Neither is worth
        failing a list over; the id is still in the response.
        """
        if record_id is None:
            return None, None
        found = lookup.get(record_id)
        return found if found is not None else (None, None)

    def _names(
        self,
        model: type[Branch] | type[Product] | type[Warehouse],
        ids: set[UUID | None],
    ) -> dict[UUID, tuple[str, str]]:
        """Return the code and name of each of these records, in one query.

        A batch's warehouse and branch are optional, so the ids arrive with
        NULLs mixed in; they are dropped rather than queried for.
        """
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        rows = self._session.execute(
            select(model.id, model.code, model.name).where(model.id.in_(wanted))
        ).all()
        return {row[0]: (row[1], row[2]) for row in rows}

    def batch_response(self, record: BatchRecord, *, firm_scope: UUID) -> BatchResponse:
        """Render one batch with the stock it is actually holding."""
        return self.batch_responses([record], firm_scope=firm_scope)[0]

    def get_batch(self, *, firm_scope: UUID, batch_id: UUID) -> BatchRecord:
        """Return one batch the firm owns."""
        row = self._session.scalar(
            select(BatchRecord).where(
                BatchRecord.id == batch_id,
                BatchRecord.firm_id == firm_scope,
                BatchRecord.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError(f"Batch {batch_id} not found.")
        return row

    def _is_named(
        self,
        column: InstrumentedAttribute[UUID | None],
        firm_scope: UUID,
        record_id: UUID,
    ) -> bool:
        """Return whether any row of the firm names this record in ``column``."""
        found = self._session.scalar(
            select(column)
            .where(column == record_id, column.class_.firm_id == firm_scope)
            .limit(1)
        )
        return found is not None

    def _named_by(self, target: str, record_id: UUID) -> list[str]:
        """Return the tables holding a live row that names this record.

        Asked of the schema rather than of a list: every table with a foreign
        key onto ``target`` is read, so a module that starts naming batches
        next year is covered the day it does. ``RESTRICT`` on those keys
        guards nothing here, because a soft delete never reaches the
        database's own check. Rows that are themselves soft-deleted do not
        count -- a pick taken back off a draft holds nothing.
        """
        found: list[str] = []
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if not any(
                    key.column.table.name == target and key.column.name == "id"
                    for key in column.foreign_keys
                ):
                    continue
                if self._has_live_row(table, column.name, record_id):
                    found.append(table.name)
                    break
        return sorted(found)

    def _has_live_row(self, table: Table, column: str, record_id: UUID) -> bool:
        """Return whether a live row of ``table`` holds this id in ``column``."""
        statement = select(table.c[column]).where(table.c[column] == record_id)
        if "is_deleted" in table.c:
            statement = statement.where(table.c["is_deleted"].is_(False))
        return self._session.execute(statement.limit(1)).first() is not None

    def _assert_unused(
        self, target: str, record_id: UUID, *, label: str, instead: str
    ) -> None:
        """Refuse to delete a record that stock or a document still names.

        Args:
            target: The table of the record, as the foreign keys name it.
            record_id: The record somebody asked to delete.
            label: The record as a person names it, "Batch B-1".
            instead: What to do in place of deleting it.

        Raises:
            ValidationError: Naming the record and what holds it.

        """
        holders = self._named_by(target, record_id)
        if not holders:
            return
        if _STOCK_TABLES.intersection(holders):
            raise ValidationError(
                f"{label} has stock movements recorded against it, so it "
                f"cannot be deleted. {instead}"
            )
        named = ", ".join(holder.replace("_", " ") for holder in holders)
        raise ValidationError(
            f"{label} is named on other records ({named}), so it cannot be "
            f"deleted. {instead}"
        )

    def _assert_batch_empty(self, record: BatchRecord) -> None:
        """Refuse to delete a batch that still holds stock in any bucket.

        Raises:
            ValidationError: If any stock row of the batch is not at zero.

        """
        held = self._session.scalar(
            select(InventoryRecord.id)
            .where(
                InventoryRecord.batch_id == record.id,
                InventoryRecord.is_deleted.is_(False),
                or_(
                    InventoryRecord.current_quantity != 0,
                    InventoryRecord.reserved_quantity != 0,
                    InventoryRecord.quarantine_quantity != 0,
                    InventoryRecord.in_transit_quantity != 0,
                    InventoryRecord.damaged_quantity != 0,
                    InventoryRecord.blocked_quantity != 0,
                ),
            )
            .limit(1)
        )
        if held is not None:
            raise ValidationError(
                f"Batch {record.batch_number} still holds stock, so it cannot "
                "be deleted. Sell, return or write off what is left; the batch "
                "stays in the register as the record of that stock."
            )

    def _assert_serial_not_in_stock(self, record: SerialNumber) -> None:
        """Refuse to delete a unit that a stock row still counts.

        A unit made by hand and never placed in stock has no stock row and is
        not judged here.

        Raises:
            ValidationError: If the unit is on hand in the row it points at.

        """
        if record.inventory_id is None or record.status not in {
            "AVAILABLE",
            "RESERVED",
        }:
            return
        stock = self._session.get(InventoryRecord, record.inventory_id)
        if stock is None or stock.is_deleted or stock.current_quantity <= 0:
            return
        raise ValidationError(
            f"Serial number {record.serial_number} is counted in stock, so it "
            "cannot be deleted. Sell, return or write off the unit instead."
        )

    def _batch_has_moved(self, firm_scope: UUID, batch_id: UUID) -> bool:
        """Return whether stock, a movement or a serial stands on the batch."""
        if self._is_named(
            InventoryRecord.batch_id, firm_scope, batch_id
        ) or self._is_named(InventoryTransaction.batch_id, firm_scope, batch_id):
            return True
        serial = self._session.scalar(
            select(SerialNumber.id)
            .where(
                SerialNumber.firm_id == firm_scope,
                SerialNumber.batch_id == batch_id,
                SerialNumber.is_deleted.is_(False),
            )
            .limit(1)
        )
        return serial is not None

    def _product_after(
        self,
        firm_scope: UUID,
        record: BatchRecord | LotRecord | SerialNumber,
        update_data: Mapping[str, object],
        *,
        kind: str,
        name: str,
        moved: Callable[[], bool],
    ) -> tuple[Product, dict[str, object]]:
        """Return the product a save leaves the record on, and what to judge.

        A save that keeps the product is judged on what it changes. One that
        names another product used to be judged against the **old** one, so a
        batch could be moved onto a product that tracks none, or onto one
        the firm does not own (D-STK-22). It is judged now as a new record of
        that product would be -- the product must be the firm's, must keep
        such a record, and must allow every dated field the record will
        hold -- and it is refused outright once stock has moved under the
        record, because those movements are the old product's. ``moved`` is
        asked only then, so an ordinary save costs no extra read.

        Raises:
            ResourceNotFoundError: If the product named is not the firm's.
            ValidationError: If the product is cleared, the record has moved
                stock, or the new product does not track such a record.

        """
        if "product_id" not in update_data:
            product = tracked_product(self._session, firm_scope, record.product_id)
            return product, _changed(record, update_data)
        product_id = update_data["product_id"]
        if not isinstance(product_id, UUID):
            raise ValidationError(f"A {kind} must belong to a product.")
        if product_id == record.product_id:
            product = tracked_product(self._session, firm_scope, product_id)
            return product, _changed(record, update_data)
        if moved():
            raise ValidationError(
                f"{kind.capitalize()} {name} has stock or movements recorded "
                "against it, so it cannot be moved to another product. Add a "
                f"new {kind} for that product instead."
            )
        product = tracked_product(self._session, firm_scope, product_id)
        assert_product_keeps(product, kind)
        held: dict[str, object] = {
            field: getattr(record, field)
            for _, _, fields in FIELD_SWITCHES
            for field in fields
            if hasattr(record, field)
        }
        return product, held | _changed(record, update_data)

    def _assert_serial_batch(
        self, firm_scope: UUID, product: Product, batch_id: UUID | None
    ) -> None:
        """Refuse a serial number filed under another product's batch.

        Raises:
            ResourceNotFoundError: If the batch is not the firm's.
            ValidationError: If the batch belongs to another product.

        """
        if batch_id is None:
            return
        batch = self.get_batch(firm_scope=firm_scope, batch_id=batch_id)
        if batch.product_id != product.id:
            raise ValidationError(
                f"Batch {batch.batch_number} belongs to another product, so a "
                f"serial number of {product.code} cannot be filed under it."
            )

    def _assert_batch_fields(
        self, firm_scope: UUID, product: Product, values: Mapping[str, object]
    ) -> None:
        """Check a batch's optional fields against what its product tracks.

        The dates are the product's own question (backlog 89): a paint that
        tracks no expiry is refused an expiry date in a firm that also sells
        medicines, and a medicine is allowed one whatever the firm's profile
        says. The trade rates stay a feature of the firm, since which prices a
        distributor keeps per batch is about its trade and not about one
        product.
        """
        assert_product_fields(product, values)
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="BATCH_PTR_PTS",
            values={name: values.get(name) for name in ("ptr", "pts")},
        )

    def create_batch(
        self, *, firm_scope: UUID, actor_id: UUID, data: BatchCreate
    ) -> BatchRecord:
        """Record a batch of a product that is tracked by batch."""
        batch_number = required_number(data.batch_number, label="Batch number")
        product = tracked_product(self._session, firm_scope, data.product_id)
        assert_product_keeps(product, "batch")
        self._assert_batch_fields(firm_scope, product, data.model_dump())
        assert_date_order(
            manufacturing_date=data.manufacturing_date,
            expiry_date=data.expiry_date,
            best_before_date=data.best_before_date,
        )
        assert_trade_rates_within_mrp(
            mrp=data.mrp,
            ptr=data.ptr,
            pts=data.pts,
            selling_price=data.selling_price,
        )
        record = BatchRecord(
            firm_id=firm_scope,
            product_id=data.product_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            vendor_id=data.vendor_id,
            storage_node_id=data.storage_node_id,
            batch_number=batch_number,
            supplier_batch=data.supplier_batch,
            internal_batch=data.internal_batch,
            manufacturing_date=data.manufacturing_date,
            expiry_date=data.expiry_date,
            best_before_date=data.best_before_date,
            status=data.status,
            shelf_life_days=data.shelf_life_days,
            mrp=data.mrp,
            selling_price=data.selling_price,
            ptr=data.ptr,
            pts=data.pts,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "A batch with this batch number already exists for the product."
            ) from exc
        record_audit(
            self._session,
            action="batch.created",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("batch", record),
        )
        self._session.commit()
        return record

    def resolve_for_receipt(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        product_id: UUID,
        batch_number: str,
        branch_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        vendor_id: UUID | None = None,
        expiry_date: date | None = None,
        mrp: Decimal | None = None,
        selling_price: Decimal | None = None,
        manufacturing_date: date | None = None,
        shelf_life_days: int | None = None,
        ptr: Decimal | None = None,
        pts: Decimal | None = None,
    ) -> BatchRecord:
        """Return the batch a receipt named, creating it if it is new.

        A goods receipt records a batch number typed off the carton. It was
        stored as free text and matched nothing, so the batch register and the
        goods on the shelf were two unrelated records of the same delivery.

        The batch is created rather than refused when the number is unknown.
        Goods that have physically arrived have to be receivable: refusing
        would stop a warehouse over a batch nobody had registered yet, while a
        mistyped number is recoverable afterwards. ``batches`` is unique on
        (firm, batch_number, product), so the same number on a later delivery
        of the same product resolves to the batch already there.

        Only the fields the receipt actually knows are set on creation. An
        expiry date is recorded when the receipt carries one and is left alone
        on an existing batch, which is the manufacturer's fact and not this
        delivery's to change. The MRP and selling price printed on the
        delivery (backlog 79 row 7) are set when the batch is new, and filled
        on an existing batch only where it has none -- a later delivery of the
        same batch carries the same print.

        The trade rates, price to retailer and price to stockist (PG-14), are
        the distributor's own and do change between deliveries, so the batch
        keeps its own unless a receipt states a different one: then the
        receipt's stands and the change is audited (``batch.rates_updated``).
        Either is refused above the MRP the batch will carry.
        """
        number = batch_number.strip()
        if not number:
            raise ValidationError("A batch number is required to receive stock.")
        existing = self._session.scalar(
            select(BatchRecord).where(
                BatchRecord.firm_id == firm_scope,
                BatchRecord.product_id == product_id,
                BatchRecord.batch_number == number,
                BatchRecord.is_deleted.is_(False),
            )
        )
        if existing is not None:
            if existing.mrp is None and mrp is not None:
                existing.mrp = mrp
            if existing.selling_price is None and selling_price is not None:
                existing.selling_price = selling_price
            self._restate_trade_rates(
                existing, ptr=ptr, pts=pts, actor_id=actor_id, firm_scope=firm_scope
            )
            return existing
        assert_trade_rates_within_mrp(mrp=mrp, ptr=ptr, pts=pts)
        product = tracked_product(self._session, firm_scope, product_id)
        # Not asked whether the product is tracked by batch: goods that have
        # arrived have to be receivable. Whether the batch may be dated is
        # the product's own switch.
        self._assert_batch_fields(firm_scope, product, {"expiry_date": expiry_date})
        # Every path that makes a batch from a delivery -- a receipt, opening
        # stock -- is held to the order the batch master asks for (F10).
        assert_date_order(
            manufacturing_date=(
                manufacturing_date if product.track_manufacturing_date else None
            ),
            expiry_date=expiry_date,
            best_before_date=None,
        )
        record = BatchRecord(
            firm_id=firm_scope,
            product_id=product_id,
            warehouse_id=warehouse_id,
            branch_id=branch_id,
            vendor_id=vendor_id,
            batch_number=number,
            expiry_date=expiry_date,
            # As typed off the carton, with the product's shelf life that
            # filled the expiry where only this date was given (STK-18) --
            # each kept only where the product tracks it, since a receipt
            # never refused them and must not start to.
            manufacturing_date=(
                manufacturing_date if product.track_manufacturing_date else None
            ),
            shelf_life_days=shelf_life_days if product.track_expiry else None,
            mrp=mrp,
            selling_price=selling_price,
            ptr=ptr,
            pts=pts,
            status=BatchStatus.AVAILABLE.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "A batch with this batch number already exists for the product."
            ) from exc
        record_audit(
            self._session,
            action="batch.created",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("batch", record),
        )
        return record

    def _restate_trade_rates(
        self,
        batch: BatchRecord,
        *,
        ptr: Decimal | None,
        pts: Decimal | None,
        actor_id: UUID,
        firm_scope: UUID,
    ) -> None:
        """Take a receipt's PTR / PTS onto an existing batch, audited (PG-14).

        Blank keeps the batch's own; only a rate the receipt states and the
        batch does not already hold changes anything.
        """
        changed = {
            name: value
            for name, value in (("ptr", ptr), ("pts", pts))
            if value is not None and getattr(batch, name) != value
        }
        if not changed:
            return
        assert_trade_rates_within_mrp(
            mrp=batch.mrp,
            ptr=changed.get("ptr", batch.ptr),
            pts=changed.get("pts", batch.pts),
        )
        before: dict[str, object] = {
            name: None if getattr(batch, name) is None else str(getattr(batch, name))
            for name in ("ptr", "pts")
        }
        for name, value in changed.items():
            setattr(batch, name, value)
        batch.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="batch.rates_updated",
            entity_type="batch",
            entity_id=batch.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=_snapshot("batch", batch),
        )

    def resolve_for_issue(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        batch_number: str,
    ) -> BatchRecord:
        """Return the registered batch a document is taking stock out of.

        The counterpart of ``resolve_for_receipt``, and deliberately the
        opposite of it in one respect: goods leaving never create a batch.

        Receiving creates an unknown batch because the goods are physically on
        the dock and refusing would stop a warehouse over paperwork. Issuing is
        the other way round -- a number nobody ever received names stock that
        was never taken in, so creating it would write a delivery that did not
        happen and leave the batch holding a negative quantity. The number is
        refused instead, which is a typo the storeman can fix.

        Raises:
            ValidationError: If the number is blank or names no batch of this
                product.

        """
        number = batch_number.strip()
        if not number:
            raise ValidationError("A batch number is required to issue this stock.")
        batch = self._session.scalar(
            select(BatchRecord).where(
                BatchRecord.firm_id == firm_scope,
                BatchRecord.product_id == product_id,
                BatchRecord.batch_number == number,
                BatchRecord.is_deleted.is_(False),
            )
        )
        if batch is None:
            raise ValidationError(
                f"Batch {number} was never received for this product, "
                "so no stock can be taken out of it."
            )
        return batch

    def update_batch(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        batch_id: UUID,
        data: BatchUpdate,
        expected_version: int | None = None,
    ) -> BatchRecord:
        """Change a batch."""
        record = self.get_batch(firm_scope=firm_scope, batch_id=batch_id)
        assert_version(record.version, expected_version)
        before: dict[str, object] = {
            "status": record.status,
            "batch_number": record.batch_number,
        }
        update_data = data.model_dump(exclude_unset=True)
        if "batch_number" in update_data:
            update_data["batch_number"] = required_number(
                update_data["batch_number"], label="Batch number"
            )
        # Only what this save changes is judged, so a batch dated before its
        # product stopped tracking expiry can still be held or recalled. A
        # batch moved to another product is judged whole, as a new one is.
        product, judged = self._product_after(
            firm_scope,
            record,
            update_data,
            kind="batch",
            name=record.batch_number,
            moved=lambda: self._batch_has_moved(firm_scope, record.id),
        )
        self._assert_batch_fields(firm_scope, product, judged)
        if judged.keys() & _BATCH_DATES:
            assert_date_order(
                manufacturing_date=update_data.get(
                    "manufacturing_date", record.manufacturing_date
                ),
                expiry_date=update_data.get("expiry_date", record.expiry_date),
                best_before_date=update_data.get(
                    "best_before_date", record.best_before_date
                ),
            )
        # Judged on what the batch will hold, so lowering the MRP under a
        # standing PTR is refused as surely as raising the PTR over it.
        assert_trade_rates_within_mrp(
            mrp=update_data.get("mrp", record.mrp),
            ptr=update_data.get("ptr", record.ptr),
            pts=update_data.get("pts", record.pts),
            selling_price=update_data.get("selling_price", record.selling_price),
        )
        for field, value in update_data.items():
            setattr(record, field, value)
        record.updated_by = actor_id
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "A batch with this batch number already exists for the product."
            ) from exc
        record_audit(
            self._session,
            action="batch.updated",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("batch", record),
            before_data=before,
        )
        self._session.commit()
        return record

    def delete_batch(self, *, firm_scope: UUID, actor_id: UUID, batch_id: UUID) -> None:
        """Soft delete a batch nothing has ever used.

        A batch that holds stock, has ever moved, or is named by a serial
        number or a document is history: deleting it left the stock row
        behind under a batch no screen listed, and the next order was refused
        "not one of this product's batches" (F2). One typed by mistake and
        never used can still go.

        Raises:
            ValidationError: If the batch holds stock or anything names it.

        """
        record = self.get_batch(firm_scope=firm_scope, batch_id=batch_id)
        self._assert_batch_empty(record)
        self._assert_unused(
            "batches",
            record.id,
            label=f"Batch {record.batch_number}",
            instead=(
                "Change its status instead (for example to Blocked or Destroyed)."
            ),
        )
        record.is_deleted = True
        record.deleted_at = utc_now()
        record.deleted_by = actor_id
        record.updated_by = actor_id
        record_audit(
            self._session,
            action="batch.deleted",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("batch", record) | {"is_deleted": True},
        )
        self._session.commit()

    def batch_summary(self, *, firm_scope: UUID) -> BatchSummary:
        """Return batch counts, including those past their expiry date.

        Near expiry and expired count only batches that still hold stock,
        the test the expiry dashboard applies (``batch_holds_stock``): an
        emptied batch read 1 on this card and 0 on that one (D-STK-18). The
        total and the quarantine count are of the register itself.
        """
        today = firm_today(self._session, firm_scope)
        near_expiry_cutoff = today + timedelta(days=30)
        total = int(
            self._session.scalar(
                select(func.count())
                .select_from(BatchRecord)
                .where(
                    BatchRecord.firm_id == firm_scope,
                    BatchRecord.is_deleted.is_(False),
                )
            )
            or 0
        )
        near_expiry = int(
            self._session.scalar(
                select(func.count())
                .select_from(BatchRecord)
                .where(
                    BatchRecord.firm_id == firm_scope,
                    BatchRecord.is_deleted.is_(False),
                    batch_holds_stock(),
                    BatchRecord.expiry_date.isnot(None),
                    BatchRecord.expiry_date > today,
                    BatchRecord.expiry_date <= near_expiry_cutoff,
                )
            )
            or 0
        )
        expired = int(
            self._session.scalar(
                select(func.count())
                .select_from(BatchRecord)
                .where(
                    BatchRecord.firm_id == firm_scope,
                    BatchRecord.is_deleted.is_(False),
                    batch_holds_stock(),
                    BatchRecord.expired_condition(today),
                )
            )
            or 0
        )
        quarantine = int(
            self._session.scalar(
                select(func.count())
                .select_from(BatchRecord)
                .where(
                    BatchRecord.firm_id == firm_scope,
                    BatchRecord.is_deleted.is_(False),
                    BatchRecord.status == "QUARANTINE",
                )
            )
            or 0
        )

        return BatchSummary(
            total_batches=total,
            near_expiry=near_expiry,
            expired=expired,
            quarantine=quarantine,
        )

    def expiry_dashboard(self, *, firm_scope: UUID) -> ExpiryDashboard:
        """Return expiry counts across the reporting windows.

        Every card counts batches that still hold stock somewhere -- on the
        shelf, in quarantine, damaged or blocked. A batch sold out months ago
        is history, not something to act on, and counting it put empty
        batches on every card (D-STK-8). "Expired today" is the batches whose
        expiry date is today; "total expired" is every batch past it.
        """
        today = firm_today(self._session, firm_scope)
        in_7 = today + timedelta(days=7)
        in_30 = today + timedelta(days=30)
        holds_stock = batch_holds_stock()

        def _count(where_clauses: list[ColumnElement[bool]]) -> int:
            """Count stock-holding batches matching the extra conditions."""
            return int(
                self._session.scalar(
                    select(func.count())
                    .select_from(BatchRecord)
                    .where(
                        BatchRecord.firm_id == firm_scope,
                        BatchRecord.is_deleted.is_(False),
                        holds_stock,
                        *where_clauses,
                    )
                )
                or 0
            )

        expired_today = _count(
            [
                BatchRecord.status != "DESTROYED",
                BatchRecord.expiry_date == today,
            ]
        )
        expire_in_7 = _count(
            [
                BatchRecord.expiry_date.isnot(None),
                BatchRecord.expiry_date > today,
                BatchRecord.expiry_date <= in_7,
            ]
        )
        expire_in_30 = _count(
            [
                BatchRecord.expiry_date.isnot(None),
                BatchRecord.expiry_date > today,
                BatchRecord.expiry_date <= in_30,
            ]
        )
        total_expired = _count([BatchRecord.expired_condition(today)])
        quarantine = _count([BatchRecord.status == "QUARANTINE"])
        recalled = _count([BatchRecord.status == "RECALLED"])

        return ExpiryDashboard(
            expired_today=expired_today,
            expire_in_7_days=expire_in_7,
            expire_in_30_days=expire_in_30,
            total_expired=total_expired,
            quarantine=quarantine,
            recalled=recalled,
        )

    def batch_availability(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        warehouse_id: UUID,
        as_of: date,
        storage_node_id: UUID | None = None,
        quantity: Decimal = Decimal("0"),
        sales_order_line_id: UUID | None = None,
        near_expiry_days: int = 30,
        keep_until: date | None = None,
    ) -> list[BatchAvailability]:
        """List a product's batches in one warehouse for a batch picker (79).

        Every batch with stock on the shelf, nearest expiry first and a batch
        with no expiry last, expired ones included so the picker can show them
        greyed out rather than leave somebody hunting for stock the stock
        screen says is there. Untracked stock (no batch) is not listed: a pick
        names a batch.

        ``sales_order_line_id`` is the order line a delivery is drawn against.
        Its own hold is let go before dispatch draws, preferring the batches
        chosen, so up to that much of each batch's reserved stock is the
        line's to take -- ``available_to_line``. ``quantity`` asks for the
        earliest-expiry split dispatch would make with nobody choosing, which
        the picker fills in so that Enter keeps today's behaviour.
        ``keep_until`` is the customer's minimum shelf life as a date: a batch
        expiring before it is flagged and never pre-filled, as dispatch passes
        it over.
        """
        rows = self._session.execute(
            select(InventoryRecord, BatchRecord)
            .join(BatchRecord, BatchRecord.id == InventoryRecord.batch_id)
            .where(
                InventoryRecord.firm_id == firm_scope,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.product_id == product_id,
                InventoryRecord.is_deleted.is_(False),
                InventoryRecord.current_quantity > 0,
                BatchRecord.is_deleted.is_(False),
                *(
                    [InventoryRecord.storage_node_id == storage_node_id]
                    if storage_node_id is not None
                    else []
                ),
            )
            .order_by(
                case((BatchRecord.expiry_date.is_(None), 1), else_=0).asc(),
                BatchRecord.expiry_date.asc(),
                BatchRecord.id.asc(),
            )
        ).all()
        totals: dict[UUID, list[Decimal]] = {}
        batches: dict[UUID, BatchRecord] = {}
        for stock, batch in rows:
            sums = totals.setdefault(batch.id, [ZERO, ZERO, ZERO])
            sums[0] += Decimal(str(stock.current_quantity))
            sums[1] += Decimal(str(stock.reserved_quantity))
            sums[2] += Decimal(str(stock.available_quantity))
            batches[batch.id] = batch
        own_hold = self._own_hold(
            sales_order_line_id, firm_scope=firm_scope, warehouse_id=warehouse_id
        )
        expired = {
            batch_id
            for batch_id in self._session.scalars(
                select(BatchRecord.id).where(
                    BatchRecord.id.in_(list(batches)),
                    BatchRecord.expired_condition(as_of),
                )
            )
        }
        # Where the line's order holds that stock, batch by batch: dispatch
        # lets go of its own holds first, so that is what is the line's to
        # take. Without it the earliest batch read as the line's although
        # another order held it, and the pre-fill offered 2 of the batch the
        # line had 8 reserved on (D-SELL-58).
        own_by_batch = self._own_hold_by_batch(
            sales_order_line_id, firm_scope=firm_scope, warehouse_id=warehouse_id
        )
        result: list[BatchAvailability] = []
        hold_left = own_hold
        wanted = Decimal(str(quantity))
        near_line = as_of + timedelta(days=near_expiry_days)
        for batch_id, (on_hand, reserved, available) in totals.items():
            batch = batches[batch_id]
            # Dispatch frees the line's hold earliest expiry first unless a
            # batch is chosen, so any one batch can be freed up to the whole
            # hold; the pre-fill below spends it in the order dispatch would.
            freeable = min(reserved, own_hold)
            freed = min(reserved, hold_left)
            if own_by_batch:
                freeable = freed = min(
                    reserved, own_hold, own_by_batch.get(batch_id, ZERO)
                )
            hold_left -= freed
            is_expired = batch_id in expired
            short = (
                keep_until is not None
                and batch.expiry_date is not None
                and batch.expiry_date < keep_until
            )
            fefo = ZERO
            if not is_expired and not short and wanted > ZERO:
                fefo = min(wanted, available + freed)
                wanted -= fefo
            result.append(
                BatchAvailability(
                    batch_id=batch_id,
                    batch_number=batch.batch_number,
                    manufacturing_date=batch.manufacturing_date,
                    expiry_date=batch.expiry_date,
                    days_to_expiry=(
                        (batch.expiry_date - as_of).days
                        if batch.expiry_date is not None
                        else None
                    ),
                    on_hand=on_hand,
                    reserved=reserved,
                    available=available,
                    available_to_line=ZERO if is_expired else available + freeable,
                    expired=is_expired,
                    near_expiry=(
                        not is_expired
                        and batch.expiry_date is not None
                        and batch.expiry_date <= near_line
                    ),
                    fefo=fefo,
                    short_for_customer=short,
                    mrp=batch.mrp,
                    selling_price=batch.selling_price,
                    ptr=batch.ptr,
                    pts=batch.pts,
                )
            )
        return result

    def _own_hold_by_batch(
        self,
        sales_order_line_id: UUID | None,
        *,
        firm_scope: UUID,
        warehouse_id: UUID,
    ) -> dict[UUID | None, Decimal]:
        """Return what an order line's order holds here, batch by batch.

        Read off the stock ledger (``InventoryService.held_by_reference``);
        empty where the line holds nothing in this warehouse.
        """
        if (
            self._own_hold(
                sales_order_line_id, firm_scope=firm_scope, warehouse_id=warehouse_id
            )
            <= ZERO
            or sales_order_line_id is None
        ):
            return {}
        line = self._session.get(SalesOrderLine, sales_order_line_id)
        order = (
            None if line is None else self._session.get(SalesOrder, line.sales_order_id)
        )
        if line is None or order is None:
            return {}
        return InventoryService(self._session).held_by_reference(
            firm_scope=firm_scope,
            reference_number=order.order_number,
            product_id=line.product_id,
            warehouse_id=warehouse_id,
        )

    def _own_hold(
        self,
        sales_order_line_id: UUID | None,
        *,
        firm_scope: UUID,
        warehouse_id: UUID,
    ) -> Decimal:
        """Return what an order line holds in this warehouse, in stock units.

        A hold made in another warehouse frees nothing here, so it counts as
        none -- the same location ``DeliveryNoteService._reservation_location``
        releases from: the line's warehouse, or else its order's.
        """
        if sales_order_line_id is None:
            return ZERO
        line = self._session.get(SalesOrderLine, sales_order_line_id)
        if line is None or line.is_deleted:
            return ZERO
        order = self._session.get(SalesOrder, line.sales_order_id)
        if order is None or order.firm_id != firm_scope:
            return ZERO
        if (line.warehouse_id or order.warehouse_id) != warehouse_id:
            return ZERO
        return Decimal(str(line.reserved_quantity or ZERO))

    # ── Lot ──────────────────────────────────────────────────────────────────

    def list_lots(
        self,
        *,
        firm_scope: UUID,
        filters: LotListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[LotRecord], int]:
        """Return a page of production lots."""
        columns = {
            "created_at": LotRecord.created_at,
            "updated_at": LotRecord.updated_at,
            "lot_number": LotRecord.lot_number,
            "status": LotRecord.status,
        }
        stmt = select(LotRecord).where(
            LotRecord.firm_id == firm_scope, LotRecord.is_deleted.is_(False)
        )
        count_stmt = (
            select(func.count())
            .select_from(LotRecord)
            .where(LotRecord.firm_id == firm_scope, LotRecord.is_deleted.is_(False))
        )
        if filters.product_id:
            stmt = stmt.where(LotRecord.product_id == filters.product_id)
            count_stmt = count_stmt.where(LotRecord.product_id == filters.product_id)
        if filters.warehouse_id:
            stmt = stmt.where(LotRecord.warehouse_id == filters.warehouse_id)
            count_stmt = count_stmt.where(
                LotRecord.warehouse_id == filters.warehouse_id
            )
        if filters.branch_id:
            stmt = stmt.where(LotRecord.branch_id == filters.branch_id)
            count_stmt = count_stmt.where(LotRecord.branch_id == filters.branch_id)
        if filters.status:
            stmt = stmt.where(LotRecord.status == filters.status)
            count_stmt = count_stmt.where(LotRecord.status == filters.status)
        if filters.lot_type:
            stmt = stmt.where(LotRecord.lot_type == filters.lot_type)
            count_stmt = count_stmt.where(LotRecord.lot_type == filters.lot_type)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(LotRecord.lot_number.ilike(term))
            count_stmt = count_stmt.where(LotRecord.lot_number.ilike(term))
        col = columns.get(sort_by, LotRecord.created_at)
        stmt = stmt.order_by(col.desc() if descending else col.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = list(self._session.scalars(stmt).all())
        total = int(self._session.scalar(count_stmt) or 0)
        return rows, total

    def get_lot(self, *, firm_scope: UUID, lot_id: UUID) -> LotRecord:
        """Return one lot the firm owns."""
        row = self._session.scalar(
            select(LotRecord).where(
                LotRecord.id == lot_id,
                LotRecord.firm_id == firm_scope,
                LotRecord.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError(f"Lot {lot_id} not found.")
        return row

    def create_lot(
        self, *, firm_scope: UUID, actor_id: UUID, data: LotCreate
    ) -> LotRecord:
        """Record a production lot of a product tracked by lot or by batch."""
        lot_number = required_number(data.lot_number, label="Lot number")
        product = tracked_product(self._session, firm_scope, data.product_id)
        assert_product_keeps(product, "lot")
        assert_product_fields(product, {"expiry_date": data.expiry_date})
        record = LotRecord(
            firm_id=firm_scope,
            product_id=data.product_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            parent_lot_id=data.parent_lot_id,
            lot_number=lot_number,
            lot_type=data.lot_type,
            status=data.status,
            quantity=data.quantity,
            available_quantity=data.quantity,
            production_date=data.production_date,
            expiry_date=data.expiry_date,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "A lot with this lot number already exists for the product."
            ) from exc
        record_audit(
            self._session,
            action="lot.created",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("lot", record),
        )
        self._session.commit()
        return record

    def update_lot(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        lot_id: UUID,
        data: LotUpdate,
        expected_version: int | None = None,
    ) -> LotRecord:
        """Change a lot."""
        record = self.get_lot(firm_scope=firm_scope, lot_id=lot_id)
        assert_version(record.version, expected_version)
        update_data = data.model_dump(exclude_unset=True)
        if "lot_number" in update_data:
            update_data["lot_number"] = required_number(
                update_data["lot_number"], label="Lot number"
            )
        product, judged = self._product_after(
            firm_scope,
            record,
            update_data,
            kind="lot",
            name=record.lot_number,
            moved=lambda: self._is_named(
                InventoryTransaction.lot_id, firm_scope, record.id
            ),
        )
        assert_product_fields(product, judged)
        for field, value in update_data.items():
            setattr(record, field, value)
        record.updated_by = actor_id
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "A lot with this lot number already exists for the product."
            ) from exc
        record_audit(
            self._session,
            action="lot.updated",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("lot", record),
        )
        self._session.commit()
        return record

    def delete_lot(self, *, firm_scope: UUID, actor_id: UUID, lot_id: UUID) -> None:
        """Soft delete a lot nothing has ever used.

        Raises:
            ValidationError: If a movement or another lot names it.

        """
        record = self.get_lot(firm_scope=firm_scope, lot_id=lot_id)
        self._assert_unused(
            "lots",
            record.id,
            label=f"Lot {record.lot_number}",
            instead="Change its status to Closed or Cancelled instead.",
        )
        record.is_deleted = True
        record.deleted_at = utc_now()
        record.deleted_by = actor_id
        record.updated_by = actor_id
        record_audit(
            self._session,
            action="lot.deleted",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("lot", record) | {"is_deleted": True},
        )
        self._session.commit()

    # ── Serial ────────────────────────────────────────────────────────────────

    def list_serials(
        self,
        *,
        firm_scope: UUID,
        filters: SerialListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SerialNumber], int]:
        """Return a page of serial numbers."""
        columns = {
            "created_at": SerialNumber.created_at,
            "updated_at": SerialNumber.updated_at,
            "serial_number": SerialNumber.serial_number,
            "status": SerialNumber.status,
        }
        stmt = select(SerialNumber).where(
            SerialNumber.firm_id == firm_scope, SerialNumber.is_deleted.is_(False)
        )
        count_stmt = (
            select(func.count())
            .select_from(SerialNumber)
            .where(
                SerialNumber.firm_id == firm_scope, SerialNumber.is_deleted.is_(False)
            )
        )
        if filters.product_id:
            stmt = stmt.where(SerialNumber.product_id == filters.product_id)
            count_stmt = count_stmt.where(SerialNumber.product_id == filters.product_id)
        if filters.warehouse_id:
            stmt = stmt.where(SerialNumber.warehouse_id == filters.warehouse_id)
            count_stmt = count_stmt.where(
                SerialNumber.warehouse_id == filters.warehouse_id
            )
        if filters.branch_id:
            stmt = stmt.where(SerialNumber.branch_id == filters.branch_id)
            count_stmt = count_stmt.where(SerialNumber.branch_id == filters.branch_id)
        if filters.batch_id:
            stmt = stmt.where(SerialNumber.batch_id == filters.batch_id)
            count_stmt = count_stmt.where(SerialNumber.batch_id == filters.batch_id)
        if filters.status:
            stmt = stmt.where(SerialNumber.status == filters.status)
            count_stmt = count_stmt.where(SerialNumber.status == filters.status)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(SerialNumber.serial_number.ilike(term))
            count_stmt = count_stmt.where(SerialNumber.serial_number.ilike(term))
        col = columns.get(sort_by, SerialNumber.created_at)
        stmt = stmt.order_by(col.desc() if descending else col.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = list(self._session.scalars(stmt).all())
        total = int(self._session.scalar(count_stmt) or 0)
        return rows, total

    def get_serial(self, *, firm_scope: UUID, serial_id: UUID) -> SerialNumber:
        """Return one serial number the firm owns."""
        row = self._session.scalar(
            select(SerialNumber).where(
                SerialNumber.id == serial_id,
                SerialNumber.firm_id == firm_scope,
                SerialNumber.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError(f"Serial number {serial_id} not found.")
        return row

    def create_serial(
        self, *, firm_scope: UUID, actor_id: UUID, data: SerialCreate
    ) -> SerialNumber:
        """Record a serial number of a product tracked by serial."""
        serial_number = required_number(data.serial_number, label="Serial number")
        assert_warranty_order(data.warranty_start, data.warranty_end)
        product = tracked_product(self._session, firm_scope, data.product_id)
        assert_product_keeps(product, "serial number")
        assert_product_fields(
            product,
            {
                "warranty_start": data.warranty_start,
                "warranty_end": data.warranty_end,
            },
        )
        self._assert_serial_batch(firm_scope, product, data.batch_id)
        record = SerialNumber(
            firm_id=firm_scope,
            product_id=data.product_id,
            inventory_id=data.inventory_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            batch_id=data.batch_id,
            serial_number=serial_number,
            status=data.status,
            manufactured_date=data.manufactured_date,
            warranty_start=data.warranty_start,
            warranty_end=data.warranty_end,
            current_owner=data.current_owner,
            asset_reference=data.asset_reference,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "This serial number already belongs to a unit in this firm."
            ) from exc
        record_audit(
            self._session,
            action="serial_number.created",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("serial_number", record),
        )
        self._session.commit()
        return record

    def update_serial(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        serial_id: UUID,
        data: SerialUpdate,
        expected_version: int | None = None,
    ) -> SerialNumber:
        """Change a serial number."""
        record = self.get_serial(firm_scope=firm_scope, serial_id=serial_id)
        assert_version(record.version, expected_version)
        update_data = data.model_dump(exclude_unset=True)
        if "serial_number" in update_data:
            update_data["serial_number"] = required_number(
                update_data["serial_number"], label="Serial number"
            )
        product, judged = self._product_after(
            firm_scope,
            record,
            update_data,
            kind="serial number",
            name=record.serial_number,
            moved=lambda: (
                self._is_named(InventoryTransaction.serial_id, firm_scope, record.id)
                or self._is_named(DocumentLineSerial.serial_id, firm_scope, record.id)
            ),
        )
        assert_product_fields(product, judged)
        batch_id = update_data.get("batch_id", record.batch_id)
        if product.id != record.product_id or batch_id != record.batch_id:
            self._assert_serial_batch(firm_scope, product, batch_id)
        # Judged on what the serial will hold: an edit may send one date only.
        assert_warranty_order(
            update_data.get("warranty_start", record.warranty_start),
            update_data.get("warranty_end", record.warranty_end),
        )
        for field, value in update_data.items():
            setattr(record, field, value)
        record.updated_by = actor_id
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "This serial number already belongs to a unit in this firm."
            ) from exc
        record_audit(
            self._session,
            action="serial_number.updated",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("serial_number", record),
        )
        self._session.commit()
        return record

    def delete_serial(
        self, *, firm_scope: UUID, actor_id: UUID, serial_id: UUID
    ) -> None:
        """Soft delete a serial number no document has ever carried.

        A unit a receipt brought in is counted in the stock quantity, so
        deleting it left the quantity and the serial count apart and a serial
        dispatch could not be completed (F2). One typed by mistake on the
        register, which no document names, can still go.

        Raises:
            ValidationError: If the unit is in stock or a document names it.

        """
        record = self.get_serial(firm_scope=firm_scope, serial_id=serial_id)
        self._assert_serial_not_in_stock(record)
        if self._named_by("serial_numbers", record.id):
            raise ValidationError(
                f"Serial number {record.serial_number} has been received or "
                "moved on a document, so it cannot be deleted. Its trail is "
                "the record of that unit; change its status instead (for "
                "example to Scrapped or Lost)."
            )
        record.is_deleted = True
        record.deleted_at = utc_now()
        record.deleted_by = actor_id
        record.updated_by = actor_id
        record_audit(
            self._session,
            action="serial_number.deleted",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=_snapshot("serial_number", record) | {"is_deleted": True},
        )
        self._session.commit()
