"""Transactional service for enterprise batch, lot, serial, and expiry management."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.batch_serial.models.batch_serial import BatchRecord, LotRecord, SerialNumber
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchListFilters,
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
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now


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

    def create_batch(
        self, *, firm_scope: UUID, actor_id: UUID, data: BatchCreate
    ) -> BatchRecord:
        """Record a batch of a product."""
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
            quantity=data.quantity,
            available_quantity=data.quantity,
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

    def update_batch(
        self, *, firm_scope: UUID, actor_id: UUID, batch_id: UUID, data: BatchUpdate
    ) -> BatchRecord:
        """Change a batch."""
        record = self.get_batch(firm_scope=firm_scope, batch_id=batch_id)
        before: dict[str, object] = {
            "status": record.status,
            "batch_number": record.batch_number,
        }
        update_data = data.model_dump(exclude_unset=True)
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
        self, *, firm_scope: UUID, actor_id: UUID, lot_id: UUID, data: LotUpdate
    ) -> LotRecord:
        """Change a lot."""
        record = self.get_lot(firm_scope=firm_scope, lot_id=lot_id)
        for field, value in data.model_dump(exclude_unset=True).items():
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
        self, *, firm_scope: UUID, actor_id: UUID, serial_id: UUID, data: SerialUpdate
    ) -> SerialNumber:
        """Change a serial number."""
        record = self.get_serial(firm_scope=firm_scope, serial_id=serial_id)
        for field, value in data.model_dump(exclude_unset=True).items():
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
