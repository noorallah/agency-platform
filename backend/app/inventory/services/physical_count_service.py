"""Reconcile what is on the shelf with what the system thinks.

A count is a document rather than an action. The sheet is drawn up from what
the warehouse currently holds, walked over hours by people with a clipboard,
and posted once at the end -- so it has to survive somebody closing a laptop,
which is what makes it tables rather than an endpoint.

Posting turns each difference into a stock adjustment, and adjustments reach
the general ledger, so a count that finds twenty missing cartons puts their
value in the profit and loss without anybody keying a journal.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.branches.models import WarehouseStorageNode
from app.common.audit.services import record_audit
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
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
from app.products.models import Product

ZERO = Decimal("0")

#: What a line counts: a product, a batch and a storage location -- exactly as
#: the stock is held. ``None`` for the batch is the untracked row, and ``None``
#: for the location is the warehouse's unlocated ROOT row (D-STK-13).
_LineKey = tuple[UUID, UUID | None, UUID | None]


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

    def product_labels(
        self, *, firm_id: UUID, product_ids: Iterable[UUID]
    ) -> dict[UUID, tuple[str, str]]:
        """Return code and name for each product a sheet names.

        A line stores the product's id; the person walking the shelf reads
        its code and name. One query for the whole sheet rather than one per
        line.
        """
        wanted = set(product_ids)
        if not wanted:
            return {}
        rows = self._session.execute(
            select(Product.id, Product.code, Product.name).where(
                Product.firm_id == firm_id,
                Product.id.in_(wanted),
            )
        ).all()
        return {product_id: (code or "", name or "") for product_id, code, name in rows}

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

        Either way a line is one stock row -- product, batch and storage
        location, as the stock is held. A line keyed on the product alone
        measured every bin summed and posted onto ROOT, so the total came out
        right and the rows wrong (D-STK-13).
        """
        wanted: list[tuple[_LineKey, PhysicalCountLineWrite | None]] = [
            (self._key(line), line) for line in data.lines
        ]
        # Checked before a number is reserved, so a refused sheet spends none.
        self._require_distinct([key for key, _ in wanted])
        self._require_locations_in(data.warehouse_id, {key[2] for key, _ in wanted})
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

        if not wanted:
            wanted = [
                ((stock.product_id, stock.batch_id, stock.storage_node_id), None)
                for stock in self._stock_in(
                    firm_id=firm_id, warehouse_id=data.warehouse_id
                )
            ]
        for index, (key, written) in enumerate(wanted, start=1):
            product_id, batch_id, storage_node_id = key
            self._session.add(
                PhysicalCountLine(
                    firm_id=firm_id,
                    physical_count_id=row.id,
                    line_number=index,
                    product_id=product_id,
                    batch_id=batch_id,
                    storage_node_id=storage_node_id,
                    expected_quantity=self._on_hand(
                        firm_id=firm_id,
                        warehouse_id=data.warehouse_id,
                        key=key,
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
        """Record what was found, on a sheet nobody has posted yet.

        A written line is matched to the sheet on product, batch and storage
        location. One that matches no line is refused rather than dropped: a
        count typed against a bin the sheet does not hold would otherwise
        vanish while the save reported success.
        """
        row = self.get(count_id, firm_id=firm_id)
        self._require_draft(row)
        self._require_distinct([self._key(line) for line in data.lines])
        counted = {self._key(line): line for line in data.lines}
        lines = self.lines_for(row.id)
        missing = set(counted) - {self._key(line) for line in lines}
        if missing:
            raise ValidationError(
                f"{len(missing)} counted line(s) are not on {row.count_number}; "
                "a line is its product, batch and storage location."
            )
        for line in lines:
            written = counted.get(self._key(line))
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

        Nothing here commits. Every adjustment is staged on the caller's
        session, so a line that fails takes the whole sheet with it: no stock
        moved, no journal, and the sheet still DRAFT to be corrected and posted
        again.
        """
        row = self.get(count_id, firm_id=firm_id)
        self._require_draft(row)
        adjusted = 0
        differences: list[tuple[str, Decimal]] = []
        for line in self.lines_for(row.id):
            if line.counted_quantity is None:
                continue
            on_hand = self._on_hand(
                firm_id=firm_id,
                warehouse_id=row.warehouse_id,
                key=self._key(line),
            )
            variance = Decimal(str(line.counted_quantity)) - on_hand
            line.variance_quantity = variance
            line.updated_by = actor_id
            if variance == ZERO:
                continue
            # Staged, not committed: the sheet is one decision, and the router
            # commits it once. A committing adjustment per line left a failing
            # sheet DRAFT beside the lines it had already moved (D-STK-3).
            # The stock side only: the sheet posts one journal below, since a
            # journal per line under the count's number broke on the second
            # line's reference (D-STK-11).
            remarks = (
                f"Physical count {row.count_number}: counted "
                f"{line.counted_quantity} against {on_hand}"
            )
            transaction, value_delta = self._inventory.stage_adjustment_movement(
                InventoryAdjustmentCreate(
                    branch_id=row.branch_id,
                    warehouse_id=row.warehouse_id,
                    product_id=line.product_id,
                    # The row the variance was measured against. Leaving it
                    # out corrected the product's untracked row instead, so a
                    # batch counted short stayed short on the books.
                    batch_id=line.batch_id,
                    # And the location it was measured in. Leaving it out
                    # took a bin's shortage off ROOT -- which could go
                    # negative -- while the bin kept its phantom stock
                    # (D-STK-13).
                    storage_node_id=line.storage_node_id,
                    quantity=variance,
                    reference_number=row.count_number,
                    reference_type="PHYSICAL_COUNT",
                    transaction_date=row.count_date,
                    remarks=remarks,
                ),
                firm_scope=firm_id,
                actor_id=actor_id,
            )
            line.transaction_id = transaction.id
            differences.append((remarks, value_delta))
            adjusted += 1

        DocumentPostingService(self._session).post_physical_count(
            firm_id=firm_id,
            count_id=row.id,
            count_number=row.count_number,
            count_date=row.count_date,
            differences=differences,
            actor_id=actor_id,
        )
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

    @staticmethod
    def _key(line: PhysicalCountLine | PhysicalCountLineWrite) -> _LineKey:
        """Return the stock row a line counts: product, batch and location."""
        return (line.product_id, line.batch_id, line.storage_node_id)

    @staticmethod
    def _require_distinct(keys: list[_LineKey]) -> None:
        """Refuse a request naming the same stock row twice.

        A line is found again by its product, batch and location, so two lines
        with the same three could never be told apart when counts are written.
        """
        if len(set(keys)) != len(keys):
            raise ValidationError(
                "The same product, batch and storage location is named twice."
            )

    def _require_locations_in(
        self, warehouse_id: UUID, storage_node_ids: set[UUID | None]
    ) -> None:
        """Refuse a storage location that is not a live node of the warehouse."""
        wanted = {node_id for node_id in storage_node_ids if node_id is not None}
        if not wanted:
            return
        found = set(
            self._session.scalars(
                select(WarehouseStorageNode.id).where(
                    WarehouseStorageNode.id.in_(wanted),
                    WarehouseStorageNode.warehouse_id == warehouse_id,
                    WarehouseStorageNode.is_deleted.is_(False),
                )
            ).all()
        )
        if wanted - found:
            raise ValidationError(
                "Storage node does not belong to the warehouse being counted."
            )

    def storage_labels(
        self, storage_node_ids: Iterable[UUID | None]
    ) -> dict[UUID, tuple[str, str]]:
        """Return code and name for each storage location a sheet names.

        One query for the whole sheet, as for the products. The ROOT row has
        no node and so no entry.
        """
        wanted = {node_id for node_id in storage_node_ids if node_id is not None}
        if not wanted:
            return {}
        rows = self._session.execute(
            select(
                WarehouseStorageNode.id,
                WarehouseStorageNode.code,
                WarehouseStorageNode.name,
            ).where(WarehouseStorageNode.id.in_(wanted))
        ).all()
        return {node_id: (code or "", name or "") for node_id, code, name in rows}

    def _on_hand(
        self,
        *,
        firm_id: UUID,
        warehouse_id: UUID,
        key: _LineKey,
    ) -> Decimal:
        """Return what the system holds in the one stock row a line counts.

        The row is the product, the batch and the storage location. Summing
        every location in the warehouse measured a bin's shortage against the
        whole warehouse and posted it onto ROOT (D-STK-13).
        """
        product_id, batch_id, storage_node_id = key
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
        statement = statement.where(
            InventoryRecord.storage_node_id == storage_node_id
            if storage_node_id is not None
            else InventoryRecord.storage_node_id.is_(None)
        )
        return Decimal(str(self._session.scalar(statement) or 0))

    def count_date_for(self, row: PhysicalCount) -> date:
        """Return the date a sheet was counted on."""
        return row.count_date
