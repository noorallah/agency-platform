"""Transactional service for enterprise batch, lot, serial, and expiry management."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models.batch_serial import BatchRecord, LotRecord, SerialNumber
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
from app.branches.models import Branch, Warehouse
from app.business.gating import assert_feature_fields, feature_enabled
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.concurrency import assert_version
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.inventory.models import InventoryRecord
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


def _snapshot(entity_type: str, record: object) -> dict[str, object]:
    """Return the audited fields of a record, stringified for the trail."""
    values: dict[str, object] = {}
    for name in _AUDITED_FIELDS[entity_type]:
        value = getattr(record, name, None)
        values[name] = None if value is None else str(value)
    return values


def assert_trade_rates_within_mrp(
    *, mrp: Decimal | None, ptr: Decimal | None, pts: Decimal | None
) -> None:
    """Refuse a price to retailer or stockist above the batch's MRP (PG-14).

    Both are trade rates before tax and the MRP is the most anyone may charge
    with tax, so a trade rate above it is a typing mistake, not a price.
    Nothing to judge where either side is blank.

    Raises:
        ValidationError: When a rate exceeds the MRP.

    """
    if mrp is None:
        return
    for label, rate in (("PTR", ptr), ("PTS", pts)):
        if rate is not None and rate > mrp:
            raise ValidationError(
                f"{label} {rate:.2f} cannot exceed the MRP {mrp:.2f}."
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

    def _assert_batch_features(
        self, firm_scope: UUID, values: Mapping[str, object]
    ) -> None:
        """Check the optional batch fields against the firm's profile.

        A firm without EXPIRY_TRACKING can still record batches; it just
        cannot date them. Gating the endpoint would have stopped it recording
        batches at all, which is BATCH_TRACKING's job, not this one.
        """
        for feature, fields in (
            ("EXPIRY_TRACKING", ("expiry_date", "best_before_date")),
            ("MANUFACTURING_DATE", ("manufacturing_date",)),
            ("SHELF_LIFE", ("shelf_life_days",)),
            ("BATCH_PTR_PTS", ("ptr", "pts")),
        ):
            assert_feature_fields(
                self._session,
                firm_scope,
                feature=feature,
                values={name: values.get(name) for name in fields},
            )

    def create_batch(
        self, *, firm_scope: UUID, actor_id: UUID, data: BatchCreate
    ) -> BatchRecord:
        """Record a batch of a product."""
        self._assert_batch_features(firm_scope, data.model_dump())
        assert_trade_rates_within_mrp(mrp=data.mrp, ptr=data.ptr, pts=data.pts)
        record = BatchRecord(
            firm_id=firm_scope,
            product_id=data.product_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            vendor_id=data.vendor_id,
            storage_node_id=data.storage_node_id,
            batch_number=data.batch_number,
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
        self._assert_batch_features(
            firm_scope,
            {"expiry_date": expiry_date, "best_before_date": None},
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
            # each kept only where the firm's profile has the feature, since a
            # receipt never refused them and must not start to.
            manufacturing_date=(
                manufacturing_date
                if feature_enabled(self._session, firm_scope, "MANUFACTURING_DATE")
                else None
            ),
            shelf_life_days=(
                shelf_life_days
                if feature_enabled(self._session, firm_scope, "SHELF_LIFE")
                else None
            ),
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
        self._assert_batch_features(firm_scope, update_data)
        # Judged on what the batch will hold, so lowering the MRP under a
        # standing PTR is refused as surely as raising the PTR over it.
        assert_trade_rates_within_mrp(
            mrp=update_data.get("mrp", record.mrp),
            ptr=update_data.get("ptr", record.ptr),
            pts=update_data.get("pts", record.pts),
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
        """Soft delete a batch."""
        record = self.get_batch(firm_scope=firm_scope, batch_id=batch_id)
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
        """Return batch counts, including those past their expiry date."""
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
        holds_stock = (
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
        """Record a production lot."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="EXPIRY_TRACKING",
            values={"expiry_date": data.expiry_date},
        )
        record = LotRecord(
            firm_id=firm_scope,
            product_id=data.product_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            parent_lot_id=data.parent_lot_id,
            lot_number=data.lot_number,
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
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="EXPIRY_TRACKING",
            values={"expiry_date": update_data.get("expiry_date")},
        )
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
        """Soft delete a lot."""
        record = self.get_lot(firm_scope=firm_scope, lot_id=lot_id)
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
        """Record a serial number."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="WARRANTY",
            values={
                "warranty_start": data.warranty_start,
                "warranty_end": data.warranty_end,
            },
        )
        record = SerialNumber(
            firm_id=firm_scope,
            product_id=data.product_id,
            inventory_id=data.inventory_id,
            warehouse_id=data.warehouse_id,
            branch_id=data.branch_id,
            batch_id=data.batch_id,
            serial_number=data.serial_number.strip(),
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
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="WARRANTY",
            values={
                name: update_data.get(name)
                for name in ("warranty_start", "warranty_end")
            },
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
        """Soft delete a serial number."""
        record = self.get_serial(firm_scope=firm_scope, serial_id=serial_id)
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
