"""Transactional service for enterprise batch, lot, serial, and expiry management."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models.batch_serial import BatchRecord, LotRecord, SerialNumber
from app.batch_serial.schemas.batch_serial import (
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
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.inventory.schemas import BatchStockTotals
from app.inventory.services import InventoryService
from app.products.models import Product


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
            action="CREATE",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
        delivery's to change.
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
            return existing
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
            action="CREATE",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        return record

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
            action="UPDATE",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
            action="DELETE",
            entity_type="batch",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()

    def batch_summary(self, *, firm_scope: UUID) -> BatchSummary:
        """Return batch counts, including those past their expiry date."""
        today = utc_now().date()
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
        """Return expiry counts across the reporting windows."""
        today = utc_now().date()
        in_7 = today + timedelta(days=7)
        in_30 = today + timedelta(days=30)

        def _count(where_clauses: list[ColumnElement[bool]]) -> int:
            """Count batches matching the extra conditions."""
            return int(
                self._session.scalar(
                    select(func.count())
                    .select_from(BatchRecord)
                    .where(
                        BatchRecord.firm_id == firm_scope,
                        BatchRecord.is_deleted.is_(False),
                        *where_clauses,
                    )
                )
                or 0
            )

        expired_today = _count([BatchRecord.expired_condition(today)])
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
            action="CREATE",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
            action="UPDATE",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
            action="DELETE",
            entity_type="lot",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
            serial_number=data.serial_number,
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
                "A serial number already exists for this product."
            ) from exc
        record_audit(
            self._session,
            action="CREATE",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
                "A serial number already exists for this product."
            ) from exc
        record_audit(
            self._session,
            action="UPDATE",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
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
            action="DELETE",
            entity_type="serial_number",
            entity_id=record.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
