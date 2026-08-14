"""Reconcile what is on the shelf with what the system thinks.

A count is a document rather than an action. The sheet is drawn up from what
the warehouse currently holds, walked over hours by people with a clipboard,
and posted once at the end -- so it has to survive somebody closing a laptop,
which is what makes it tables rather than an endpoint.

Posting turns each difference into a stock adjustment, and adjustments reach
the general ledger, so a count that finds twenty missing cartons puts their
value in the profit and loss without anybody keying a journal.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.inventory.models import (
    InventoryRecord,
    PhysicalCount,
    PhysicalCountLine,
    PhysicalCountStatus,
)
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    PhysicalCountCreate,
    PhysicalCountLineWrite,
    PhysicalCountUpdate,
)
from app.inventory.services.inventory_service import InventoryService

ZERO = Decimal("0")


class PhysicalCountService(TransactionalDocumentService):
    """Open, fill in and post a count sheet."""

    DOCUMENT = DocumentTypeSpec(
        code="PHYSICAL_COUNT",
        name="Physical Count",
        description="Stock count sheet for one warehouse",
        category="INVENTORY",
        module="inventory",
        prefix="PC",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("POSTED", "Posted", 2, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 3, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus the inventory service it posts through."""
        super().__init__(session)
        self._inventory = InventoryService(session)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_counts(
        self, *, firm_id: UUID, page: int, page_size: int, search: str = ""
    ) -> tuple[list[PhysicalCount], int]:
        """Return one page of count sheets, newest first."""
        statement = self._scoped(select(PhysicalCount), firm_id)
        if search.strip():
            statement = statement.where(
                PhysicalCount.count_number.ilike(f"%{search.strip()}%")
            )
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                PhysicalCount.count_date.desc(), PhysicalCount.count_number.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def get(self, count_id: UUID, *, firm_id: UUID) -> PhysicalCount:
        """Return one count sheet or raise when it is unavailable."""
        row = self._session.scalar(
            self._scoped(select(PhysicalCount), firm_id).where(
                PhysicalCount.id == count_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Physical count not found.")
        return row

    def lines_for(self, count_id: UUID) -> list[PhysicalCountLine]:
        """Return the lines of one sheet, in the order they are walked."""
        return list(
            self._session.scalars(
                select(PhysicalCountLine)
                .where(
                    PhysicalCountLine.physical_count_id == count_id,
                    PhysicalCountLine.is_deleted.is_(False),
                )
                .order_by(PhysicalCountLine.line_number.asc())
            ).all()
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(
        self, data: PhysicalCountCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PhysicalCount:
        """Open a sheet, drawn up from what the warehouse currently holds.

        Naming no lines takes everything in the warehouse, which is what a
        counter walks out with. Naming them counts part of one.
        """
        _, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        number = (
            data.reference_number.strip().upper()
            if data.reference_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.count_date, firm_id
                ),
                company_code=self._company_code(firm_id),
                document_date=data.count_date,
                actor_id=actor_id,
            )
        )
        row = PhysicalCount(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            count_number=number,
            count_date=data.count_date,
            status=PhysicalCountStatus.DRAFT.value,
            remarks=data.remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()

        wanted: list[tuple[UUID, UUID | None, PhysicalCountLineWrite | None]] = [
            (line.product_id, line.batch_id, line) for line in data.lines
        ]
        if not wanted:
            wanted = [
                (stock.product_id, stock.batch_id, None)
                for stock in self._stock_in(
                    firm_id=firm_id, warehouse_id=data.warehouse_id
                )
            ]
        for index, (product_id, batch_id, written) in enumerate(wanted, start=1):
            self._session.add(
                PhysicalCountLine(
                    firm_id=firm_id,
                    physical_count_id=row.id,
                    line_number=index,
                    product_id=product_id,
                    batch_id=batch_id,
                    expected_quantity=self._on_hand(
                        firm_id=firm_id,
                        warehouse_id=data.warehouse_id,
                        product_id=product_id,
                        batch_id=batch_id,
                    ),
                    counted_quantity=(
                        written.counted_quantity if written is not None else None
                    ),
                    remarks=written.remarks if written is not None else None,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        record_audit(
            self._session,
            action="inventory.physical_count.opened",
            entity_type="physical_count",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"count_number": number, "line_count": len(wanted)},
        )
        self._session.flush()
        return row

    def update(
        self,
        count_id: UUID,
        data: PhysicalCountUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> PhysicalCount:
        """Record what was found, on a sheet nobody has posted yet."""
        row = self.get(count_id, firm_id=firm_id)
        self._require_draft(row)
        counted = {(line.product_id, line.batch_id): line for line in data.lines}
        for line in self.lines_for(row.id):
            written = counted.get((line.product_id, line.batch_id))
            if written is None:
                continue
            line.counted_quantity = written.counted_quantity
            if written.remarks is not None:
                line.remarks = written.remarks
            line.updated_by = actor_id
        if data.remarks is not None:
            row.remarks = data.remarks
        row.updated_by = actor_id
        self._session.flush()
        return row

    def post(self, count_id: UUID, *, firm_id: UUID, actor_id: UUID) -> PhysicalCount:
        """Turn every difference into a stock adjustment.

        The variance is measured against what the system holds **now**, not
        against the snapshot taken when the sheet was drawn up. Stock moves
        while a warehouse is being counted, and posting against a stale figure
        would silently undo every dispatch made in between -- the count would
        put back goods that had left the building.

        Lines nobody walked are skipped. An uncounted line is not a line that
        found nothing, and treating it as zero would write off the stock that
        was simply not reached before the sheet was posted.
        """
        row = self.get(count_id, firm_id=firm_id)
        self._require_draft(row)
        adjusted = 0
        for line in self.lines_for(row.id):
            if line.counted_quantity is None:
                continue
            on_hand = self._on_hand(
                firm_id=firm_id,
                warehouse_id=row.warehouse_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
            )
            variance = Decimal(str(line.counted_quantity)) - on_hand
            line.variance_quantity = variance
            line.updated_by = actor_id
            if variance == ZERO:
                continue
            transaction = self._inventory.create_adjustment(
                InventoryAdjustmentCreate(
                    branch_id=row.branch_id,
                    warehouse_id=row.warehouse_id,
                    product_id=line.product_id,
                    quantity=variance,
                    reference_number=row.count_number,
                    reference_type="PHYSICAL_COUNT",
                    transaction_date=row.count_date,
                    remarks=(
                        f"Physical count {row.count_number}: counted "
                        f"{line.counted_quantity} against {on_hand}"
                    ),
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
            )
            line.transaction_id = transaction.id
            adjusted += 1

        row.status = PhysicalCountStatus.POSTED.value
        row.posted_at = utc_now()
        row.posted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="inventory.physical_count.posted",
            entity_type="physical_count",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": PhysicalCountStatus.DRAFT.value},
            after_data={
                "status": row.status,
                "adjusted_lines": str(adjusted),
            },
        )
        self._session.flush()
        return row

    def cancel(self, count_id: UUID, *, firm_id: UUID, actor_id: UUID) -> PhysicalCount:
        """Abandon a sheet that will not be posted."""
        row = self.get(count_id, firm_id=firm_id)
        self._require_draft(row)
        row.status = PhysicalCountStatus.CANCELLED.value
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="inventory.physical_count.cancelled",
            entity_type="physical_count",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": PhysicalCountStatus.DRAFT.value},
            after_data={"status": row.status},
        )
        self._session.flush()
        return row

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[PhysicalCount]], firm_id: UUID
    ) -> Select[tuple[PhysicalCount]]:
        """Restrict a query to this firm and live rows."""
        return statement.where(
            PhysicalCount.firm_id == firm_id,
            PhysicalCount.is_deleted.is_(False),
        )

    def _require_draft(self, row: PhysicalCount) -> None:
        """Refuse to change a sheet that has been posted or abandoned."""
        if row.status != PhysicalCountStatus.DRAFT.value:
            raise ConflictError(
                f"{row.count_number} is {row.status.lower()}, so it cannot be "
                "changed."
            )

    def _stock_in(self, *, firm_id: UUID, warehouse_id: UUID) -> list[InventoryRecord]:
        """Return every stock row in one warehouse."""
        return list(
            self._session.scalars(
                select(InventoryRecord)
                .where(
                    InventoryRecord.firm_id == firm_id,
                    InventoryRecord.warehouse_id == warehouse_id,
                    InventoryRecord.is_deleted.is_(False),
                )
                .order_by(InventoryRecord.created_at.asc())
            ).all()
        )

    def _on_hand(
        self,
        *,
        firm_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        batch_id: UUID | None,
    ) -> Decimal:
        """Return what the system holds for one product in one place."""
        statement = select(
            func.coalesce(func.sum(InventoryRecord.current_quantity), 0)
        ).where(
            InventoryRecord.firm_id == firm_id,
            InventoryRecord.warehouse_id == warehouse_id,
            InventoryRecord.product_id == product_id,
            InventoryRecord.is_deleted.is_(False),
        )
        statement = statement.where(
            InventoryRecord.batch_id == batch_id
            if batch_id is not None
            else InventoryRecord.batch_id.is_(None)
        )
        return Decimal(str(self._session.scalar(statement) or 0))

    def count_date_for(self, row: PhysicalCount) -> date:
        """Return the date a sheet was counted on."""
        return row.count_date
