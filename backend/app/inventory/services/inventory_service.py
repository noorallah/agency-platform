"""Transactional service for the enterprise inventory foundation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import Select

from app.batch_serial.models import BatchRecord
from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.gating import resolve_profile_id
from app.business.models import BusinessProfile
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.concurrency import assert_version
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.chunks import chunks
from app.core.utils.csv_text import csv_text, sheet_text
from app.core.utils.money import quantize_money
from app.core.validation.payloads import parse_payload
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.document_posting import (
    DocumentPostingService,
    assert_stock_date_in_open_period,
    assert_stock_date_not_ahead,
)
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    OpeningStockBatch,
    OpeningStockLine,
    ProductValuation,
    StockLedgerEntry,
)
from app.inventory.schemas import (
    REVERSAL_SUFFIX,
    BatchStockTotals,
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryListFilters,
    InventoryLocationSummary,
    InventoryResponse,
    InventorySummary,
    InventoryTransactionListFilters,
    InventoryTransactionResponse,
    InventoryTransactionType,
    InventoryUpdate,
    OpeningStockBatchCreate,
    OpeningStockBatchListFilters,
    OpeningStockBatchResponse,
    OpeningStockImportRequest,
    OpeningStockLineCreate,
    OpeningStockLineResponse,
    OpeningStockUpdate,
    QuarantineAction,
    StockLedgerListFilters,
    StockLedgerResponse,
    StockQuarantineCreate,
    StockTransferCreate,
    StockWriteOffCreate,
)
from app.inventory.services import pipeline
from app.inventory.services.movement_numbering import MovementNumbering
from app.inventory.services.stock_evidence import StockEvidenceService
from app.products.models import Product
from app.uom.models import ConversionRule
from app.uom.services.uom_service import (
    assert_quantity_fits_unit,
    missing_conversion_message,
    quantize_by_rule,
    round_by_rule,
)

if TYPE_CHECKING:
    from app.inventory.services.opening_serials import OpeningSerials

ZERO = Decimal("0")
#: How many rows an export reads at a time; it reads until there are no more.
EXPORT_PAGE_SIZE = 5000

#: Stock issued rather than lost, and the expense each is booked to (STK-3).
#: Damage, expiry and loss stay on the inventory adjustment account.
ISSUE_PURPOSES: dict[str, ControlAccountPurpose] = {
    "INTERNAL_USE": ControlAccountPurpose.INTERNAL_USE,
    "STAFF": ControlAccountPurpose.STAFF_WELFARE,
    "DISPLAY": ControlAccountPurpose.SAMPLES_AND_DISPLAY,
    # Free goods passed on to a customer and samples (BUY-1).
    "FREE_TO_CUSTOMER": ControlAccountPurpose.PROMOTIONAL_EXPENSE,
    "SAMPLE": ControlAccountPurpose.PROMOTIONAL_EXPENSE,
}

#: The reasons that must name the customer the stock went to (BUY-1).
CUSTOMER_REASONS = frozenset({"FREE_TO_CUSTOMER"})


@dataclass(frozen=True, slots=True)
class LineConversion:
    """The conversion a document line was written with.

    A line carries the factor it was priced and counted at, the way every
    ERP document line does, and its stock moves at that factor -- never at
    whatever the rule says by the time the document is completed. Re-reading
    the rule by version let an edit to it move a draft receipt's stock, value
    and GRNI journal away from its own line (D-CFG-1).

    ``to_uom_id`` is the unit the factor converts *into*. The stored factor is
    only used when that is the unit stock is counted in; a line whose factor
    converts into some other unit (a return's factor is into the source line's
    unit) still has its stock quantity resolved from the rule.
    """

    factor: Decimal
    to_uom_id: UUID | None


@dataclass(slots=True)
class _Movement:
    transaction_type: str
    reference_number: str
    reference_type: str
    transaction_date: date
    quantity: Decimal
    current_delta: Decimal = ZERO
    reserved_delta: Decimal = ZERO
    blocked_delta: Decimal = ZERO
    damaged_delta: Decimal = ZERO
    quarantine_delta: Decimal = ZERO
    in_transit_delta: Decimal = ZERO
    entered_quantity: Decimal | None = None
    entered_uom_id: UUID | None = None
    conversion_version: int | None = None
    remarks: str | None = None
    unit_cost: Decimal | None = None
    #: The batch that moved, mirrored onto the transaction and the ledger so
    #: "where did batch B-2405 go" is answerable from the history rather than
    #: only from the current balance.
    batch_id: UUID | None = None
    #: The one serialised unit this movement carried, when it carried exactly
    #: one. A movement of several units cannot name them in one column; the
    #: ``document_line_serials`` rows of the line that moved them do.
    serial_id: UUID | None = None
    #: How much the firm stopped owning, when that is not ``current_delta``.
    #:
    #: The valuation follows ``current_delta``, which is right for almost
    #: everything: stock arrives into the sellable bucket and leaves from it.
    #: Condemning quarantined stock does not touch that bucket at all -- it was
    #: moved out of it when it was held -- so the write-off left the value on
    #: the books while the goods went in the skip.
    owned_delta: Decimal | None = None
    #: Whether this movement changes what the firm owns.
    #:
    #: Almost every movement does, and the moving average is rolled forward
    #: from ``current_delta``. A quarantine hold does not: the goods are still
    #: owned and still worth what they were, they have only stopped being
    #: sellable. Rolling the average on one consumed the value as though the
    #: stock had left -- a hold of 4 units at 30.00 wrote 120.00 off a firm
    #: that had lost nothing.
    revalues: bool = True


@dataclass(frozen=True, slots=True)
class ReservationPlan:
    """What a sales order line holds, and what it could not hold and why.

    ``batches`` is the split to stage one movement per pair, any uncovered
    remainder last under ``None``. ``expired_note`` names the batches that
    were on the shelf but out of date when there is such a remainder, and is
    empty otherwise -- a back order beside a screen showing twenty on hand
    needs the explanation written where the hold is.
    """

    batches: list[tuple[UUID | None, Decimal]]
    expired_note: str = ""


@dataclass(frozen=True, slots=True)
class _TypedSerials:
    """The serials a page of opening stock lines typed, read once."""

    by_line: Mapping[UUID, Sequence[str]]
    tracked: frozenset[UUID] | set[UUID]


@dataclass(frozen=True, slots=True)
class _Labels:
    """The codes and names a page of stock rows shows, read once per table.

    Each accessor answers exactly what the matching ``_lookup_*`` on the
    service answers for one id, so a row built from a page's labels is the
    row built alone (backlog 56 C, step 3).
    """

    branches: dict[UUID, tuple[str | None, str | None]]
    warehouses: dict[UUID, tuple[str | None, str | None]]
    storage: dict[UUID, tuple[str | None, str | None]]
    products: dict[UUID, tuple[str | None, str | None]]
    batches: dict[UUID, tuple[str | None, date | None]]
    profiles: dict[UUID, str | None]

    def branch_code(self, branch_id: UUID) -> str:
        """Return the branch code, or an empty string."""
        return str(self.branches.get(branch_id, (None, None))[0] or "")

    def branch_name(self, branch_id: UUID) -> str:
        """Return the branch name, or an empty string."""
        return str(self.branches.get(branch_id, (None, None))[1] or "")

    def warehouse_code(self, warehouse_id: UUID) -> str:
        """Return the warehouse code, or an empty string."""
        return str(self.warehouses.get(warehouse_id, (None, None))[0] or "")

    def warehouse_name(self, warehouse_id: UUID) -> str:
        """Return the warehouse name, or an empty string."""
        return str(self.warehouses.get(warehouse_id, (None, None))[1] or "")

    def storage_code(self, storage_node_id: UUID | None) -> str | None:
        """Return the storage node code, or None."""
        if storage_node_id is None:
            return None
        value = self.storage.get(storage_node_id, (None, None))[0]
        return str(value) if value is not None else None

    def storage_name(self, storage_node_id: UUID | None) -> str | None:
        """Return the storage node name, or None."""
        if storage_node_id is None:
            return None
        value = self.storage.get(storage_node_id, (None, None))[1]
        return str(value) if value is not None else None

    def product_code(self, product_id: UUID) -> str:
        """Return the product code, or an empty string."""
        return str(self.products.get(product_id, (None, None))[0] or "")

    def product_name(self, product_id: UUID) -> str:
        """Return the product name, or an empty string."""
        return str(self.products.get(product_id, (None, None))[1] or "")

    def batch(self, batch_id: UUID | None) -> tuple[str | None, date | None]:
        """Return the batch number and expiry, or a pair of None."""
        if batch_id is None:
            return None, None
        return self.batches.get(batch_id, (None, None))

    def profile_code(self, profile_id: UUID | None) -> str | None:
        """Return the business profile code, or None."""
        if profile_id is None:
            return None
        value = self.profiles.get(profile_id)
        return str(value) if value is not None else None


def _four_places(value: Decimal) -> Decimal:
    """Return a quantity to the four places stock is kept to."""
    return Decimal(str(value)).quantize(Decimal("0.0001"))


def _plain(value: Decimal) -> str:
    """Return a quantity as a person writes it: 5, not 5.0000."""
    return format(Decimal(str(value)).normalize(), "f")


def _pairs(
    session: Session,
    key: InstrumentedAttribute[Any],
    columns: tuple[InstrumentedAttribute[Any], ...],
    ids: Iterable[UUID | None],
) -> dict[UUID, Any]:
    """Read ``columns`` for every id in ``ids``, in chunks, keyed by id."""
    wanted = [value for value in ids if value is not None]
    found: dict[UUID, Any] = {}
    for chunk in chunks(wanted):
        for row in session.execute(select(key, *columns).where(key.in_(chunk))):
            found[row[0]] = tuple(row[1:]) if len(columns) > 1 else row[1]
    return found


def opening_stock_key(
    product_id: UUID, warehouse_id: UUID, batch_number: str | None
) -> tuple[UUID, UUID, str]:
    """Name one item's opening stock: product, warehouse and batch."""
    return product_id, warehouse_id, (batch_number or "").strip().upper()


class InventoryService:
    """Coordinate inventory projections, immutable movements, and opening stock."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_inventory(
        self,
        *,
        firm_scope: UUID,
        filters: InventoryListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[InventoryRecord], int]:
        """Return a page of stock projections and the total."""
        columns = {
            "created_at": InventoryRecord.created_at,
            "updated_at": InventoryRecord.updated_at,
            "current_quantity": InventoryRecord.current_quantity,
            "available_quantity": InventoryRecord.available_quantity,
            "status": InventoryRecord.status,
            "product_code": Product.code,
        }
        statement = (
            select(InventoryRecord)
            .join(Product, Product.id == InventoryRecord.product_id)
            .join(Branch, Branch.id == InventoryRecord.branch_id)
            .join(Warehouse, Warehouse.id == InventoryRecord.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == InventoryRecord.storage_node_id,
            )
            .where(InventoryRecord.firm_id == firm_scope)
        )
        count = (
            select(func.count())
            .select_from(InventoryRecord)
            .join(Product, Product.id == InventoryRecord.product_id)
            .join(Branch, Branch.id == InventoryRecord.branch_id)
            .join(Warehouse, Warehouse.id == InventoryRecord.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == InventoryRecord.storage_node_id,
            )
            .where(InventoryRecord.firm_id == firm_scope)
        )
        statement, count = self._apply_inventory_filters(statement, count, filters)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                Product.code.ilike(term),
                Product.name.ilike(term),
                Branch.code.ilike(term),
                Branch.name.ilike(term),
                Warehouse.code.ilike(term),
                Warehouse.name.ilike(term),
                WarehouseStorageNode.code.ilike(term),
                WarehouseStorageNode.name.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns.get(sort_by, InventoryRecord.created_at)
        rows = self._session.scalars(
            statement.order_by(
                ordering.desc() if descending else ordering.asc(),
                # Tiebreaker: see list_ledger for why every paged query needs one.
                InventoryRecord.id.desc() if descending else InventoryRecord.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def inventory_summary(
        self, *, firm_scope: UUID, filters: InventoryListFilters
    ) -> InventorySummary:
        """Return stock counts, value and exception totals."""
        statement = (
            select(
                func.count(InventoryRecord.id),
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.in_transit_quantity), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryRecord.current_quantity
                                <= func.coalesce(
                                    InventoryRecord.reorder_level,
                                    InventoryRecord.minimum_level,
                                    ZERO,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(case((InventoryRecord.current_quantity <= 0, 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((InventoryRecord.available_quantity < 0, 1), else_=0)
                    ),
                    0,
                ),
            )
            .select_from(InventoryRecord)
            .where(InventoryRecord.firm_id == firm_scope)
        )
        statement, _ = self._apply_inventory_filters(statement, statement, filters)
        (
            total,
            current_quantity,
            reserved_quantity,
            available_quantity,
            blocked_quantity,
            damaged_quantity,
            quarantine_quantity,
            in_transit_quantity,
            low_stock_count,
            out_of_stock_count,
            negative_stock_count,
        ) = self._session.execute(statement).one()
        return InventorySummary(
            total_records=int(total or 0),
            current_quantity=Decimal(current_quantity or 0),
            reserved_quantity=Decimal(reserved_quantity or 0),
            available_quantity=Decimal(available_quantity or 0),
            blocked_quantity=Decimal(blocked_quantity or 0),
            damaged_quantity=Decimal(damaged_quantity or 0),
            quarantine_quantity=Decimal(quarantine_quantity or 0),
            in_transit_quantity=Decimal(in_transit_quantity or 0),
            low_stock_count=int(low_stock_count or 0),
            out_of_stock_count=int(out_of_stock_count or 0),
            negative_stock_count=int(negative_stock_count or 0),
        )

    def stock_by_firm(self, *, firm_scope: UUID) -> list[InventoryLocationSummary]:
        """Return stock totals rolled up to the firm."""
        row = self._session.execute(
            select(
                func.count(InventoryRecord.id),
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.in_transit_quantity), 0),
            ).where(
                InventoryRecord.firm_id == firm_scope,
                InventoryRecord.is_deleted.is_(False),
            )
        ).first()
        if row is None or int(row[0] or 0) == 0:
            return []
        # The firm's and each branch's row carry what is coming and going
        # like the warehouse's and the product's: they read 0, and a
        # projected figure of 0 beside real stock (inventory round 1, F6).
        coming = pipeline.incoming(self._session, firm_id=firm_scope)
        going = pipeline.outgoing(self._session, firm_id=firm_scope)
        return [
            self._with_pipeline(
                InventoryLocationSummary(
                    scope_id=firm_scope,
                    scope_code="FIRM",
                    scope_name="Selected Firm",
                    current_quantity=Decimal(row[1] or 0),
                    reserved_quantity=Decimal(row[2] or 0),
                    available_quantity=Decimal(row[3] or 0),
                    blocked_quantity=Decimal(row[4] or 0),
                    damaged_quantity=Decimal(row[5] or 0),
                    quarantine_quantity=Decimal(row[6] or 0),
                    in_transit_quantity=Decimal(row[7] or 0),
                ),
                {firm_scope: sum(coming.values(), ZERO)},
                {firm_scope: sum(going.values(), ZERO)},
            )
        ]

    def stock_by_branch(self, *, firm_scope: UUID) -> list[InventoryLocationSummary]:
        """Return stock totals per branch."""
        rows = self._session.execute(
            select(
                Branch.id,
                Branch.code,
                Branch.name,
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.in_transit_quantity), 0),
            )
            .join(InventoryRecord, InventoryRecord.branch_id == Branch.id)
            .where(
                Branch.firm_id == firm_scope,
                Branch.is_deleted.is_(False),
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(Branch.id, Branch.code, Branch.name)
            .order_by(Branch.code.asc())
        ).all()
        branch_of: dict[UUID, UUID] = {
            warehouse_id: branch_id
            for warehouse_id, branch_id in self._session.execute(
                select(Warehouse.id, Warehouse.branch_id).where(
                    Warehouse.firm_id == firm_scope
                )
            ).all()
        }
        coming = self._by_branch(
            pipeline.incoming(self._session, firm_id=firm_scope), branch_of
        )
        going = self._by_branch(
            pipeline.outgoing(self._session, firm_id=firm_scope), branch_of
        )
        return [
            self._with_pipeline(
                InventoryLocationSummary(
                    scope_id=row[0],
                    scope_code=row[1],
                    scope_name=row[2],
                    current_quantity=Decimal(row[3] or 0),
                    reserved_quantity=Decimal(row[4] or 0),
                    available_quantity=Decimal(row[5] or 0),
                    blocked_quantity=Decimal(row[6] or 0),
                    damaged_quantity=Decimal(row[7] or 0),
                    quarantine_quantity=Decimal(row[8] or 0),
                    in_transit_quantity=Decimal(row[9] or 0),
                ),
                coming,
                going,
            )
            for row in rows
        ]

    @staticmethod
    def _by_branch(
        keyed: pipeline.Keyed, branch_of: Mapping[UUID, UUID]
    ) -> dict[UUID, Decimal]:
        """Add a per-warehouse figure up to one per branch."""
        totals: dict[UUID, Decimal] = {}
        for warehouse_id, quantity in pipeline.by_warehouse(keyed).items():
            branch_id = branch_of.get(warehouse_id)
            if branch_id is not None:
                totals[branch_id] = totals.get(branch_id, ZERO) + quantity
        return totals

    def stock_by_batch(
        self, *, firm_scope: UUID, batch_ids: Sequence[UUID]
    ) -> dict[UUID, BatchStockTotals]:
        """Return what each of these batches is holding, in one query.

        A batch is held per location, so its total is a sum across however many
        stock rows carry it. ``batches`` used to keep its own copy of these six
        numbers, written by the batch API and reconciled against the projection
        by nothing -- so a batch could claim ten on the shelf while no stock row
        anywhere held any of it.

        Callers rendering a page of batches pass every id on the page. Asking
        per row would be a query per batch, which is the mistake
        ``values_for_many`` exists to avoid elsewhere.

        Returns:
            The totals for each batch that holds stock. A batch with no stock
            rows is absent -- ``BatchStockTotals()`` is its answer, and the
            caller supplies it rather than this running a query per empty
            batch.

        """
        if not batch_ids:
            return {}
        rows = self._session.execute(
            select(
                InventoryRecord.batch_id,
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
            )
            .where(
                InventoryRecord.firm_id == firm_scope,
                InventoryRecord.batch_id.in_(batch_ids),
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(InventoryRecord.batch_id)
        ).all()
        return {
            row[0]: BatchStockTotals(
                current_quantity=Decimal(row[1] or 0),
                available_quantity=Decimal(row[2] or 0),
                reserved_quantity=Decimal(row[3] or 0),
                blocked_quantity=Decimal(row[4] or 0),
                damaged_quantity=Decimal(row[5] or 0),
                quarantine_quantity=Decimal(row[6] or 0),
            )
            for row in rows
            if row[0] is not None
        }

    def stock_by_product(self, *, firm_scope: UUID) -> list[InventoryLocationSummary]:
        """Return stock totals per product, across batches and locations.

        A batch-tracked product is several stock rows -- one per batch per
        place -- so "how much amoxicillin do I have" stopped being a row and
        became a sum. The list endpoint deliberately still returns the
        individual rows, because which batch stock is in is the reason the
        grain changed; this is where the total lives.
        """
        rows = self._session.execute(
            select(
                Product.id,
                Product.code,
                Product.name,
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.in_transit_quantity), 0),
            )
            .join(InventoryRecord, InventoryRecord.product_id == Product.id)
            .where(
                InventoryRecord.firm_id == firm_scope,
                Product.is_deleted.is_(False),
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(Product.id, Product.code, Product.name)
            .order_by(Product.code.asc())
        ).all()
        coming = pipeline.by_product(
            pipeline.incoming(self._session, firm_id=firm_scope)
        )
        going = pipeline.by_product(
            pipeline.outgoing(self._session, firm_id=firm_scope)
        )
        summaries = [
            self._with_pipeline(
                InventoryLocationSummary(
                    scope_id=row[0],
                    scope_code=row[1],
                    scope_name=row[2],
                    current_quantity=Decimal(row[3] or 0),
                    reserved_quantity=Decimal(row[4] or 0),
                    available_quantity=Decimal(row[5] or 0),
                    blocked_quantity=Decimal(row[6] or 0),
                    damaged_quantity=Decimal(row[7] or 0),
                    quarantine_quantity=Decimal(row[8] or 0),
                    in_transit_quantity=Decimal(row[9] or 0),
                ),
                coming,
                going,
            )
            for row in rows
        ]
        # A product with nothing on the shelf yet but on order, or promised,
        # still belongs in the list: that is exactly when the figures matter.
        stocked = {summary.scope_id for summary in summaries}
        unstocked = (set(coming) | set(going)) - stocked
        if unstocked:
            for product_id, code, name in self._session.execute(
                select(Product.id, Product.code, Product.name).where(
                    Product.id.in_(list(unstocked)),
                    Product.firm_id == firm_scope,
                    Product.is_deleted.is_(False),
                )
            ).all():
                summaries.append(
                    self._with_pipeline(
                        InventoryLocationSummary(
                            scope_id=product_id,
                            scope_code=code,
                            scope_name=name,
                            current_quantity=ZERO,
                            reserved_quantity=ZERO,
                            available_quantity=ZERO,
                            blocked_quantity=ZERO,
                            damaged_quantity=ZERO,
                            quarantine_quantity=ZERO,
                            in_transit_quantity=ZERO,
                        ),
                        coming,
                        going,
                    )
                )
            summaries.sort(key=lambda summary: summary.scope_code)
        return summaries

    @staticmethod
    def _with_pipeline(
        summary: InventoryLocationSummary,
        coming: dict[UUID, Decimal],
        going: dict[UUID, Decimal],
    ) -> InventoryLocationSummary:
        """Add what is coming in and going out for the summary's scope."""
        # To the four places every other quantity carries: a sum of
        # converted order lines came back as 10.00000000000000.
        incoming = _four_places(coming.get(summary.scope_id, ZERO))
        outgoing = _four_places(going.get(summary.scope_id, ZERO))
        summary.incoming_quantity = incoming
        summary.outgoing_quantity = outgoing
        summary.projected_quantity = summary.available_quantity + incoming - outgoing
        return summary

    def stock_by_warehouse(self, *, firm_scope: UUID) -> list[InventoryLocationSummary]:
        """Return stock totals per warehouse."""
        rows = self._session.execute(
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                func.coalesce(func.sum(InventoryRecord.current_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.blocked_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.damaged_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.quarantine_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.in_transit_quantity), 0),
            )
            .join(InventoryRecord, InventoryRecord.warehouse_id == Warehouse.id)
            .where(
                Warehouse.firm_id == firm_scope,
                Warehouse.is_deleted.is_(False),
                InventoryRecord.is_deleted.is_(False),
            )
            .group_by(Warehouse.id, Warehouse.code, Warehouse.name)
            .order_by(Warehouse.code.asc())
        ).all()
        coming = pipeline.by_warehouse(
            pipeline.incoming(self._session, firm_id=firm_scope)
        )
        going = pipeline.by_warehouse(
            pipeline.outgoing(self._session, firm_id=firm_scope)
        )
        return [
            self._with_pipeline(
                InventoryLocationSummary(
                    scope_id=row[0],
                    scope_code=row[1],
                    scope_name=row[2],
                    current_quantity=Decimal(row[3] or 0),
                    reserved_quantity=Decimal(row[4] or 0),
                    available_quantity=Decimal(row[5] or 0),
                    blocked_quantity=Decimal(row[6] or 0),
                    damaged_quantity=Decimal(row[7] or 0),
                    quarantine_quantity=Decimal(row[8] or 0),
                    in_transit_quantity=Decimal(row[9] or 0),
                ),
                coming,
                going,
            )
            for row in rows
        ]

    def create_inventory_record(
        self, data: InventoryCreate, *, firm_id: UUID, actor_id: UUID
    ) -> InventoryRecord:
        """Create a stock projection for a product location."""
        branch, warehouse, storage_node, product, profile_id = (
            self._validate_references(
                firm_id=firm_id,
                branch_id=data.branch_id,
                warehouse_id=data.warehouse_id,
                storage_node_id=data.storage_node_id,
                product_id=data.product_id,
            )
        )
        locator = self._storage_locator(storage_node.id if storage_node else None)
        if (
            self._find_inventory_row(
                firm_id=firm_id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                storage_locator=locator,
                product_id=product.id,
                # Creating a stock row by hand creates the untracked one; a
                # batch's row is created by the movement that receives it.
                batch_id=None,
            )
            is not None
        ):
            raise ConflictError("An inventory record already exists for this location.")
        row = InventoryRecord(
            firm_id=firm_id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=storage_node.id if storage_node else None,
            storage_locator=locator,
            product_id=product.id,
            business_profile_id=profile_id,
            minimum_level=data.minimum_level,
            maximum_level=data.maximum_level,
            reorder_level=data.reorder_level,
            safety_stock=data.safety_stock,
            status=data.status.value,
            current_quantity=ZERO,
            reserved_quantity=ZERO,
            available_quantity=ZERO,
            blocked_quantity=ZERO,
            damaged_quantity=ZERO,
            quarantine_quantity=ZERO,
            in_transit_quantity=ZERO,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="inventory.created",
            entity_type="inventory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "product_id": str(product.id),
                "warehouse_id": str(warehouse.id),
            },
        )
        self._commit()
        self._session.refresh(row)
        return row

    def get_inventory_record(
        self, inventory_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> InventoryRecord:
        """Return one stock projection the firm owns."""
        statement = select(InventoryRecord).where(
            InventoryRecord.id == inventory_id, InventoryRecord.firm_id == firm_scope
        )
        if not include_deleted:
            statement = statement.where(InventoryRecord.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Inventory record not found.")
        return row

    def update_inventory_record(
        self,
        inventory_id: UUID,
        data: InventoryUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> InventoryRecord:
        """Change a projection's thresholds and status."""
        row = self.get_inventory_record(
            inventory_id, firm_scope=firm_scope, include_deleted=True
        )
        assert_version(row.version, expected_version)
        # The row is where the goods are and what they are. Rewriting either
        # here moved ten of one product into another, or into another
        # warehouse, with no movement, no ledger row and no cost (inventory
        # round 1, F1): goods move by a transfer, and this edits the levels.
        if (
            data.branch_id != row.branch_id
            or data.warehouse_id != row.warehouse_id
            or data.storage_node_id != row.storage_node_id
            or data.product_id != row.product_id
        ):
            raise ValidationError(
                "A stock row's product, branch, warehouse and storage location "
                "cannot be changed here. Move the goods with a transfer; this "
                "changes the stock levels and the status."
            )
        before: dict[str, object] = {
            "minimum_level": str(row.minimum_level or ""),
            "maximum_level": str(row.maximum_level or ""),
            "reorder_level": str(row.reorder_level or ""),
            "safety_stock": str(row.safety_stock or ""),
            "status": row.status,
        }
        row.minimum_level = data.minimum_level
        row.maximum_level = data.maximum_level
        row.reorder_level = data.reorder_level
        row.safety_stock = data.safety_stock
        row.status = data.status.value
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="inventory.updated",
            entity_type="inventory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={"status": row.status},
        )
        self._commit()
        self._session.refresh(row)
        return row

    def list_transactions(
        self,
        *,
        firm_scope: UUID,
        filters: InventoryTransactionListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[InventoryTransaction], int]:
        """Return a page of inventory movements."""
        columns = {
            "created_at": InventoryTransaction.created_at,
            "transaction_date": InventoryTransaction.transaction_date,
            "transaction_type": InventoryTransaction.transaction_type,
            "reference_number": InventoryTransaction.reference_number,
            "quantity": InventoryTransaction.quantity,
        }
        statement = (
            select(InventoryTransaction)
            .join(Product, Product.id == InventoryTransaction.product_id)
            .join(Branch, Branch.id == InventoryTransaction.branch_id)
            .join(Warehouse, Warehouse.id == InventoryTransaction.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == InventoryTransaction.storage_node_id,
            )
            .where(InventoryTransaction.firm_id == firm_scope)
        )
        count = (
            select(func.count())
            .select_from(InventoryTransaction)
            .join(Product, Product.id == InventoryTransaction.product_id)
            .join(Branch, Branch.id == InventoryTransaction.branch_id)
            .join(Warehouse, Warehouse.id == InventoryTransaction.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == InventoryTransaction.storage_node_id,
            )
            .where(InventoryTransaction.firm_id == firm_scope)
        )
        statement, count = self._apply_transaction_filters(statement, count, filters)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                Product.code.ilike(term),
                Product.name.ilike(term),
                InventoryTransaction.reference_number.ilike(term),
                InventoryTransaction.reference_type.ilike(term),
                Warehouse.code.ilike(term),
                Warehouse.name.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns.get(sort_by, InventoryTransaction.created_at)
        rows = self._session.scalars(
            statement.order_by(
                ordering.desc() if descending else ordering.asc(),
                # Tiebreaker: see list_ledger for why every paged query needs one.
                (
                    InventoryTransaction.id.desc()
                    if descending
                    else InventoryTransaction.id.asc()
                ),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_ledger(
        self,
        *,
        firm_scope: UUID,
        filters: StockLedgerListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[StockLedgerEntry], int]:
        """Return a page of immutable ledger rows."""
        columns = {
            "created_at": StockLedgerEntry.created_at,
            "transaction_date": StockLedgerEntry.transaction_date,
            "transaction_type": StockLedgerEntry.transaction_type,
            "reference_number": StockLedgerEntry.reference_number,
            "quantity": StockLedgerEntry.quantity,
        }
        statement = (
            select(StockLedgerEntry)
            .join(Product, Product.id == StockLedgerEntry.product_id)
            .join(Branch, Branch.id == StockLedgerEntry.branch_id)
            .join(Warehouse, Warehouse.id == StockLedgerEntry.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == StockLedgerEntry.storage_node_id,
            )
            .where(StockLedgerEntry.firm_id == firm_scope)
        )
        count = (
            select(func.count())
            .select_from(StockLedgerEntry)
            .join(Product, Product.id == StockLedgerEntry.product_id)
            .join(Branch, Branch.id == StockLedgerEntry.branch_id)
            .join(Warehouse, Warehouse.id == StockLedgerEntry.warehouse_id)
            .outerjoin(
                WarehouseStorageNode,
                WarehouseStorageNode.id == StockLedgerEntry.storage_node_id,
            )
            .where(StockLedgerEntry.firm_id == firm_scope)
        )
        statement, count = self._apply_ledger_filters(statement, count, filters)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                Product.code.ilike(term),
                Product.name.ilike(term),
                StockLedgerEntry.reference_number.ilike(term),
                StockLedgerEntry.reference_type.ilike(term),
                Warehouse.code.ilike(term),
                Warehouse.name.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns.get(sort_by, StockLedgerEntry.created_at)
        rows = self._session.scalars(
            statement.order_by(
                ordering.desc() if descending else ordering.asc(),
                # A sort column alone is not a total order. `created_at` is not
                # unique -- a dispatch writes its DISPATCH and UNRESERVE rows in
                # one flush, so they share a timestamp to the microsecond -- and
                # OFFSET/LIMIT over a tie is free to hand the same row to two
                # pages and never show another. Paging the seeded ledger showed
                # one row twice and hid one entirely until this tiebreaker.
                StockLedgerEntry.id.desc() if descending else StockLedgerEntry.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_opening_stock_batches(
        self,
        *,
        firm_scope: UUID,
        filters: OpeningStockBatchListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[OpeningStockBatch], int]:
        """Return a page of opening-stock batches."""
        columns = {
            "created_at": OpeningStockBatch.created_at,
            "posting_date": OpeningStockBatch.posting_date,
            "reference_number": OpeningStockBatch.reference_number,
            "status": OpeningStockBatch.status,
        }
        statement = (
            select(OpeningStockBatch)
            .join(Branch, Branch.id == OpeningStockBatch.branch_id)
            .join(Warehouse, Warehouse.id == OpeningStockBatch.warehouse_id)
            .where(OpeningStockBatch.firm_id == firm_scope)
            .options(selectinload(OpeningStockBatch.lines))
        )
        count = (
            select(func.count())
            .select_from(OpeningStockBatch)
            .join(Branch, Branch.id == OpeningStockBatch.branch_id)
            .join(Warehouse, Warehouse.id == OpeningStockBatch.warehouse_id)
            .where(OpeningStockBatch.firm_id == firm_scope)
        )
        statement, count = self._apply_opening_stock_filters(statement, count, filters)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                OpeningStockBatch.reference_number.ilike(term),
                Branch.code.ilike(term),
                Branch.name.ilike(term),
                Warehouse.code.ilike(term),
                Warehouse.name.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        ordering = columns.get(sort_by, OpeningStockBatch.created_at)
        rows = self._session.scalars(
            statement.order_by(
                ordering.desc() if descending else ordering.asc(),
                # Tiebreaker: see list_ledger for why every paged query needs one.
                (
                    OpeningStockBatch.id.desc()
                    if descending
                    else OpeningStockBatch.id.asc()
                ),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def get_opening_stock_batch(
        self, batch_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> OpeningStockBatch:
        """Return one opening-stock batch."""
        statement = (
            select(OpeningStockBatch)
            .where(
                OpeningStockBatch.id == batch_id,
                OpeningStockBatch.firm_id == firm_scope,
            )
            .options(selectinload(OpeningStockBatch.lines))
        )
        if not include_deleted:
            statement = statement.where(OpeningStockBatch.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Opening stock batch not found.")
        return row

    def create_opening_stock_batch(
        self,
        data: OpeningStockBatchCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source_format: str = "MANUAL",
    ) -> OpeningStockBatch:
        """Create a draft opening-stock batch."""
        batch = self.stage_opening_stock_batch(
            data, firm_id=firm_id, actor_id=actor_id, source_format=source_format
        )
        self._commit()
        self._session.refresh(batch)
        return batch

    def stage_opening_stock_batch(
        self,
        data: OpeningStockBatchCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        source_format: str = "MANUAL",
    ) -> OpeningStockBatch:
        """Build and flush a draft opening-stock batch without committing.

        The file import stages one batch per warehouse and commits the file
        once, so a problem in the last warehouse leaves the first unwritten.
        """
        self._validate_branch_warehouse_scope(
            firm_id=firm_id, branch_id=data.branch_id, warehouse_id=data.warehouse_id
        )
        assert_stock_date_not_ahead(
            self._session, firm_id, data.posting_date, what="Opening stock"
        )
        self._assert_unique_opening_reference(firm_id, data.reference_number)
        batch = OpeningStockBatch(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            reference_number=data.reference_number.strip().upper(),
            posting_date=data.posting_date,
            remarks=data.remarks,
            source_format=source_format.upper(),
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        batch.lines = self._build_opening_stock_lines(
            firm_id=firm_id,
            warehouse_id=data.warehouse_id,
            lines=data.lines,
            actor_id=actor_id,
        )
        self._session.add(batch)
        self._session.flush()
        self._write_opening_serials(batch, data.lines, actor_id=actor_id)
        record_audit(
            self._session,
            action="opening_stock.created",
            entity_type="opening_stock_batch",
            entity_id=batch.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "reference_number": batch.reference_number,
                "line_count": len(batch.lines),
            },
        )
        return batch

    def update_opening_stock_batch(
        self,
        batch_id: UUID,
        data: OpeningStockUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> OpeningStockBatch:
        """Change a draft opening-stock batch."""
        batch = self.get_opening_stock_batch(
            batch_id, firm_scope=firm_scope, include_deleted=True
        )
        assert_version(batch.version, expected_version)
        if batch.status != "DRAFT":
            raise ValidationError("Only draft opening stock batches can be edited.")
        self._validate_branch_warehouse_scope(
            firm_id=firm_scope, branch_id=data.branch_id, warehouse_id=data.warehouse_id
        )
        assert_stock_date_not_ahead(
            self._session, firm_scope, data.posting_date, what="Opening stock"
        )
        self._assert_unique_opening_reference(
            firm_scope, data.reference_number, excluding_id=batch.id
        )
        before: dict[str, object] = {
            "reference_number": batch.reference_number,
            "status": batch.status,
        }
        batch.branch_id = data.branch_id
        batch.warehouse_id = data.warehouse_id
        batch.reference_number = data.reference_number.strip().upper()
        batch.posting_date = data.posting_date
        batch.remarks = data.remarks
        batch.updated_by = actor_id
        self._opening_serials().clear_batch(batch.id)
        for existing in list(batch.lines):
            self._session.delete(existing)
        # Written before the new lines are staged: the unit of work inserts
        # before it deletes, so a line kept at its number met its old self
        # and no draft could be edited at all (inventory round 1, F7).
        self._session.flush()
        batch.lines = self._build_opening_stock_lines(
            firm_id=firm_scope,
            warehouse_id=data.warehouse_id,
            lines=data.lines,
            actor_id=actor_id,
        )
        self._session.flush()
        self._write_opening_serials(batch, data.lines, actor_id=actor_id)
        record_audit(
            self._session,
            action="opening_stock.updated",
            entity_type="opening_stock_batch",
            entity_id=batch.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={
                "reference_number": batch.reference_number,
                "line_count": len(batch.lines),
            },
        )
        self._commit()
        self._session.refresh(batch)
        return batch

    def _opening_serials(self) -> OpeningSerials:
        """Return the keeper of what opening stock lines typed.

        Imported here for the reason `BatchSerialService` is, below: the
        serial trail's package reads stock totals from this module.
        """
        from app.inventory.services.opening_serials import OpeningSerials

        return OpeningSerials(self._session)

    def _write_opening_serials(
        self,
        batch: OpeningStockBatch,
        lines: Sequence[OpeningStockLineCreate],
        *,
        actor_id: UUID,
    ) -> None:
        """Keep the serials each freshly written line typed (D-STK-40).

        The lines were built from ``lines`` in order, so the two pair up by
        position. Nothing is created yet: posting makes the units.
        """
        serials = self._opening_serials()
        written = sorted(batch.lines, key=lambda line: line.line_number)
        for line, stated in zip(written, lines, strict=True):
            if stated.serial_numbers:
                serials.replace(batch, line, stated.serial_numbers, actor_id=actor_id)
        serials.refuse_repeats(batch, written)

    def _opening_stock_batch_id(
        self,
        line: OpeningStockLine,
        batch: OpeningStockBatch,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> UUID | None:
        """Resolve the batch one opening-stock line puts its goods in.

        Opening stock is stock arriving, so it behaves like a goods receipt:
        an unknown number registers the batch rather than being refused, and a
        product whose profile requires a batch on receipt is refused without
        one. Enforcing it here as well as on receipts is what makes the rule
        mean something -- otherwise a firm could take in untraceable stock on
        day one and never be able to say where it came from.

        Returns:
            The batch id, or None where the line names none and the product
            does not require one.

        """
        number = (line.batch_number or "").strip()
        product = self._session.get(Product, line.product_id)
        if not number:
            if product is not None and product.require_batch_on_receipt:
                raise ValidationError(
                    f"{product.code} must be taken in with a batch number, "
                    "including as opening stock."
                )
            return None
        if product is not None and not product.track_batch:
            # As on a goods receipt: a number typed for a product that keeps
            # no batches registers none (D-STK-43).
            return None
        # Imported here rather than at the top: `batch_serial` reads stock
        # totals from this service, so the two modules would import each other
        # at load. The dependency is real in both directions -- a batch is
        # identity and stock is quantity, and each needs the other's answer.
        from app.batch_serial.services import BatchSerialService

        resolved = BatchSerialService(self._session).resolve_for_receipt(
            firm_scope=firm_scope,
            actor_id=actor_id,
            product_id=line.product_id,
            batch_number=number,
            branch_id=batch.branch_id,
            warehouse_id=batch.warehouse_id,
            expiry_date=line.expiry_date,
        )
        line.batch_id = resolved.id
        return resolved.id

    def post_opening_stock_batch(
        self, batch_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> OpeningStockBatch:
        """Post an opening-stock batch into the ledger."""
        batch = self.get_opening_stock_batch(batch_id, firm_scope=firm_scope)
        self.stage_post_opening_stock_batch(
            batch, firm_scope=firm_scope, actor_id=actor_id
        )
        self._commit()
        self._session.refresh(batch)
        return batch

    def posted_opening_stock(
        self, firm_scope: UUID, *, excluding: UUID | None = None
    ) -> dict[tuple[UUID, UUID, str], str]:
        """Return every item with posted opening stock, and the document's number.

        Keyed by ``opening_stock_key``: product, warehouse and batch.
        """
        statement = (
            select(
                OpeningStockLine.product_id,
                OpeningStockBatch.warehouse_id,
                OpeningStockLine.batch_number,
                OpeningStockBatch.reference_number,
            )
            .join(
                OpeningStockBatch,
                OpeningStockBatch.id == OpeningStockLine.opening_stock_batch_id,
            )
            .where(
                OpeningStockBatch.firm_id == firm_scope,
                OpeningStockBatch.status == "POSTED",
                OpeningStockBatch.is_deleted.is_(False),
                OpeningStockLine.is_deleted.is_(False),
            )
            .order_by(OpeningStockBatch.posting_date.desc())
        )
        if excluding is not None:
            statement = statement.where(OpeningStockBatch.id != excluding)
        return {
            opening_stock_key(product_id, warehouse_id, batch_number): reference
            for product_id, warehouse_id, batch_number, reference in (
                self._session.execute(statement).all()
            )
        }

    def stage_post_opening_stock_batch(
        self, batch: OpeningStockBatch, *, firm_scope: UUID, actor_id: UUID
    ) -> OpeningStockBatch:
        """Post a batch's movements and journal, flushed but not committed."""
        if batch.status == "POSTED":
            raise ConflictError("Opening stock batch has already been posted.")
        if not batch.lines:
            raise ValidationError("Opening stock batch must contain at least one line.")
        # One rule for the form and the file import: an item's opening stock
        # in one warehouse (and batch) is posted once. A second document for
        # a warehouse is fine -- the items forgotten the first time -- but the
        # same item again is the same stock counted twice; a correction is a
        # stock adjustment.
        posted = self.posted_opening_stock(firm_scope, excluding=batch.id)
        for line in batch.lines:
            if line.is_deleted:
                continue
            earlier = posted.get(
                opening_stock_key(
                    line.product_id, batch.warehouse_id, line.batch_number
                )
            )
            if earlier is not None:
                raise ValidationError(
                    f"Line {line.line_number} already has posted opening stock in "
                    f"this warehouse ({earlier}). Opening stock is posted once per "
                    "item; correct it with a stock adjustment."
                )
        movement_ids: list[UUID] = []
        for line in batch.lines:
            (
                base_quantity,
                entered_quantity,
                entered_uom_id,
                conversion_version,
            ) = self._resolve_base_quantity(
                firm_scope=firm_scope,
                product_id=line.product_id,
                quantity=line.entered_quantity or line.quantity,
                entered_uom_id=line.entered_uom_id,
                conversion_version=line.conversion_version,
                on_date=batch.posting_date,
            )
            # Day-one stock arrives in a batch like any other stock. It was
            # the last way stock could enter with no batch behind it, so a
            # pharmacy's opening shelf was one untraceable heap while every
            # later delivery was traced -- and a product that requires a batch
            # on issue could never ship what it started with.
            line_batch_id = self._opening_stock_batch_id(
                line, batch, firm_scope=firm_scope, actor_id=actor_id
            )
            inventory = self._ensure_inventory_projection(
                firm_id=firm_scope,
                branch_id=batch.branch_id,
                warehouse_id=batch.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                actor_id=actor_id,
                batch_id=line_batch_id,
            )
            self._apply_thresholds(
                inventory,
                minimum_level=line.minimum_level,
                maximum_level=line.maximum_level,
                reorder_level=line.reorder_level,
                safety_stock=line.safety_stock,
                actor_id=actor_id,
            )
            transaction = self._stage_movement(
                inventory,
                actor_id=actor_id,
                movement=_Movement(
                    transaction_type=InventoryTransactionType.OPENING_STOCK.value,
                    batch_id=line_batch_id,
                    reference_number=batch.reference_number,
                    reference_type="OPENING_STOCK",
                    transaction_date=batch.posting_date,
                    quantity=base_quantity,
                    current_delta=base_quantity,
                    unit_cost=line.unit_cost,
                    entered_quantity=entered_quantity,
                    entered_uom_id=entered_uom_id,
                    conversion_version=conversion_version,
                    remarks=line.remarks or batch.remarks,
                ),
            )
            line.transaction_id = transaction.id
            line.updated_by = actor_id
            movement_ids.append(transaction.id)
            # The units the line named arrive with its stock (D-STK-40).
            self._opening_serials().receive(
                batch,
                line,
                transaction,
                units=base_quantity,
                batch_id=line_batch_id,
                actor_id=actor_id,
            )
        # Day-one stock arrived from nowhere the ledger can see, so it is
        # debited to inventory against opening balance equity. The flush is
        # required for the same reason it is on adjustments: request sessions
        # do not autoflush, so the rows staged above are invisible to a query
        # until they are written.
        self._session.flush()
        opening_value = self._session.scalar(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                StockLedgerEntry.transaction_id.in_(movement_ids)
            )
        )
        DocumentPostingService(self._session).post_opening_stock(
            firm_id=firm_scope,
            batch_id=batch.id,
            reference_number=batch.reference_number,
            posting_date=batch.posting_date,
            stock_value=Decimal(str(opening_value or ZERO)),
            actor_id=actor_id,
        )
        batch.status = "POSTED"
        batch.posted_at = batch.posting_date
        batch.updated_by = actor_id
        record_audit(
            self._session,
            action="opening_stock.posted",
            entity_type="opening_stock_batch",
            entity_id=batch.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reference_number": batch.reference_number,
                "line_count": len(batch.lines),
            },
        )
        self._session.flush()
        return batch

    def import_opening_stock_json(
        self,
        payload: OpeningStockImportRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> OpeningStockBatch:
        """Build opening-stock lines from a JSON payload.

        The draft and its posting are staged and committed once (D-STK-56):
        saved and then posted in two commits, a posting that was refused left
        the draft behind holding the reference number, so the corrected
        payload was refused for a number already used.
        """
        try:
            batch = self.stage_opening_stock_batch(
                OpeningStockBatchCreate(
                    branch_id=payload.branch_id,
                    warehouse_id=payload.warehouse_id,
                    reference_number=payload.reference_number,
                    posting_date=payload.posting_date,
                    remarks=payload.remarks,
                    lines=payload.lines,
                ),
                firm_id=firm_scope,
                actor_id=actor_id,
                source_format="JSON",
            )
            if payload.auto_post:
                self.stage_post_opening_stock_batch(
                    batch, firm_scope=firm_scope, actor_id=actor_id
                )
        except Exception:
            self._session.rollback()
            raise
        self._commit()
        self._session.refresh(batch)
        return batch

    #: The columns an opening-stock CSV or XLSX may carry, by the line's field.
    _OPENING_FILE_COLUMNS = (
        ("ProductId", "product_id"),
        ("Quantity", "quantity"),
        ("StorageNodeId", "storage_node_id"),
        ("MinimumLevel", "minimum_level"),
        ("MaximumLevel", "maximum_level"),
        ("ReorderLevel", "reorder_level"),
        ("SafetyStock", "safety_stock"),
        ("Remarks", "remarks"),
    )

    def _import_opening_stock_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        reference_number: str,
        posting_date: date,
        branch_id: UUID,
        warehouse_id: UUID,
        remarks: str | None,
        auto_post: bool,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> OpeningStockBatch:
        """Import a file's rows, refusing a cell that cannot be read by line.

        The cells go through the request model as text, the way a JSON import
        does, so "lots" for a quantity is a 422 naming ``lines[2].quantity``.
        Building the line models by hand raised ``ValueError`` and pydantic's
        own error past every handler, and the route answered 500 (D-STK-58).

        Raises:
            ValidationError: If no row names a product and a quantity, or a
                cell cannot be read.

        """
        lines: list[dict[str, str]] = []
        for row in rows:
            cells = {
                field: str(row.get(column) if row.get(column) is not None else "")
                for column, field in self._OPENING_FILE_COLUMNS
            }
            cells = {field: text.strip() for field, text in cells.items()}
            if not cells["product_id"] or not cells["quantity"]:
                continue
            lines.append({field: text for field, text in cells.items() if text})
        if not lines:
            raise ValidationError(
                "The file has no row with a ProductId and a Quantity, so "
                "nothing was imported."
            )
        return self.import_opening_stock_json(
            parse_payload(
                OpeningStockImportRequest,
                json.dumps(
                    {
                        "reference_number": reference_number,
                        "posting_date": posting_date.isoformat(),
                        "branch_id": str(branch_id),
                        "warehouse_id": str(warehouse_id),
                        "remarks": remarks,
                        "auto_post": auto_post,
                        "lines": lines,
                    }
                ),
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def import_opening_stock_csv(
        self,
        csv_content: str,
        *,
        reference_number: str,
        posting_date: date,
        branch_id: UUID,
        warehouse_id: UUID,
        remarks: str | None,
        auto_post: bool,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> OpeningStockBatch:
        """Build opening-stock lines from a CSV upload."""
        import csv
        import io

        return self._import_opening_stock_rows(
            list(csv.DictReader(io.StringIO(csv_content))),
            reference_number=reference_number,
            posting_date=posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def import_opening_stock_xlsx(
        self,
        workbook_bytes: bytes,
        *,
        reference_number: str,
        posting_date: date,
        branch_id: UUID,
        warehouse_id: UUID,
        remarks: str | None,
        auto_post: bool,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> OpeningStockBatch:
        """Build opening-stock lines from an XLSX upload."""
        try:
            from openpyxl import load_workbook  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValidationError(
                "XLSX import dependency is unavailable. Install openpyxl."
            ) from error
        try:
            workbook = load_workbook(filename=BytesIO(workbook_bytes), read_only=True)
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True))
        except Exception as error:  # openpyxl raises many kinds
            raise ValidationError(
                "The file could not be opened as an XLSX workbook, so nothing "
                "was imported."
            ) from error
        if not rows:
            raise ValidationError("The XLSX import file is empty.")
        header = [str(value or "").strip() for value in rows[0]]
        return self._import_opening_stock_rows(
            [dict(zip(header, values, strict=False)) for values in rows[1:]],
            reference_number=reference_number,
            posting_date=posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def moved_base_quantity(
        self,
        data: InventoryAdjustmentCreate | StockWriteOffCreate,
        *,
        firm_scope: UUID,
    ) -> Decimal:
        """Return what an adjustment or write-off moves, in the stock unit.

        The limit on a post is a limit on value, and value is pieces at cost.
        Judging the number typed let three boxes of twelve through as three
        pieces (D-STK-57), so the limit and a request's stated worth both
        read the quantity from here. It keeps the sign of what was typed.
        """
        base_quantity, _, _, _ = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=data.product_id,
            quantity=(
                data.entered_quantity
                if data.entered_quantity is not None
                else data.quantity
            ),
            entered_uom_id=data.entered_uom_id,
            conversion_version=None,
            on_date=data.transaction_date,
        )
        sign = Decimal("-1") if data.quantity < 0 else Decimal("1")
        return abs(base_quantity) * sign

    def assert_postable(
        self,
        data: InventoryAdjustmentCreate | StockWriteOffCreate,
        *,
        firm_scope: UUID,
    ) -> None:
        """Refuse what names a record the firm does not keep, writing nothing.

        A request for approval is posted later, by somebody else. One naming
        an unknown product, warehouse, batch or reason was accepted and could
        then never be approved, or was refused as a conflict by the database
        rather than by name (D-STK-60).

        Raises:
            ValidationError: Naming the record that is not the firm's.

        """
        assert_stock_date_not_ahead(
            self._session,
            firm_scope,
            data.transaction_date,
            what=(
                "A write-off"
                if isinstance(data, StockWriteOffCreate)
                else "A stock adjustment"
            ),
        )
        self._validate_references(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            storage_node_id=data.storage_node_id,
            product_id=data.product_id,
        )
        if data.batch_id is not None:
            self._require_batch_of(
                data.batch_id, firm_id=firm_scope, product_id=data.product_id
            )
        code = (
            data.reason if isinstance(data, StockWriteOffCreate) else data.reason_code
        )
        if code:
            from app.inventory.services.adjustment_reasons import (
                AdjustmentReasonService,
            )

            AdjustmentReasonService(self._session).resolve(firm_scope, code)

    def write_off_stock(
        self,
        data: StockWriteOffCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        enforce_limit: bool = True,
    ) -> InventoryTransaction:
        """Take stock off the books, and record why.

        A generic adjustment reached damage, expiry and loss alike, so a firm
        could answer "how much stock did we lose" and not "to what". The reason
        rides on the movement and into the journal narration, which is where
        somebody reading the ledger asks the question.

        The value leaves through the same inventory adjustment account an
        adjustment uses. Splitting damage and expiry into separate accounts is
        a chart decision a firm can make by remapping the purpose; putting
        three accounts into the seeded chart would be deciding it for them.

        Args:
            data: What is being written off, and why.
            firm_scope: The owning firm.
            actor_id: The user writing it off.
            enforce_limit: False only where an approved request is posted
                (STK-8): the approval already judged the value.

        Returns:
            The movement written.

        Raises:
            ValidationError: If the location does not hold that much.

        """
        assert_stock_date_not_ahead(
            self._session, firm_scope, data.transaction_date, what="A write-off"
        )
        if enforce_limit:
            from app.inventory.services.adjustment_approval import (
                StockAdjustmentApprovalService,
            )

            StockAdjustmentApprovalService(self._session).assert_within_limit(
                firm_scope,
                actor_id,
                product_id=data.product_id,
                quantity=self.moved_base_quantity(data, firm_scope=firm_scope),
            )
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=data.product_id,
            quantity=(
                data.entered_quantity
                if data.entered_quantity is not None
                else data.quantity
            ),
            entered_uom_id=data.entered_uom_id,
            conversion_version=None,
            on_date=data.transaction_date,
        )
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            storage_node_id=data.storage_node_id,
            product_id=data.product_id,
            actor_id=actor_id,
            batch_id=data.batch_id,
        )
        # What a customer sent back damaged or as scrap is held off the
        # shelf, in the damaged bucket alone, and nothing could take it out
        # again (D-STK-46). Goods given to a customer are never drawn from it.
        set_aside = (
            ZERO
            if data.reason.strip().upper() in CUSTOMER_REASONS
            else self._damaged_off_the_shelf(inventory)
        )
        held = inventory.current_quantity + inventory.quarantine_quantity + set_aside
        if base_quantity > held:
            raise ValidationError(
                f"This location holds {held}, so {base_quantity} cannot be "
                "written off from it."
            )
        # What is already condemned goes first, then what is doubted: it is
        # in quarantine because somebody already doubted it, so it is the
        # likeliest thing going.
        from_damaged = min(base_quantity, set_aside)
        from_quarantine = min(
            base_quantity - from_damaged, inventory.quarantine_quantity
        )
        from_current = base_quantity - from_damaged - from_quarantine
        reference = self._movement_reference(
            data, "WRITE_OFF", firm_id=firm_scope, actor_id=actor_id
        )
        # The journal is keyed on the reference and would refuse the second
        # one in its own words, about a journal entry nobody here typed
        # (D-STK-44).
        if self._session.scalar(
            select(InventoryTransaction.id)
            .where(
                InventoryTransaction.firm_id == firm_scope,
                InventoryTransaction.reference_number == reference,
                InventoryTransaction.transaction_type
                == InventoryTransactionType.WRITE_OFF.value,
                InventoryTransaction.is_deleted.is_(False),
            )
            .limit(1)
        ):
            raise ConflictError(
                f"A write-off with the reference {reference} already exists: "
                "give this one a reference of its own, or leave the box "
                "empty to have it numbered."
            )
        from app.inventory.services.adjustment_reasons import (
            AdjustmentReasonService,
        )

        listed = AdjustmentReasonService(self._session).resolve(firm_scope, data.reason)
        reason = listed.code
        if reason in CUSTOMER_REASONS and data.customer_id is None:
            raise ValidationError(
                f"{listed.name} names the customer the goods went to."
            )
        if data.customer_id is not None:
            from app.customers.models import Customer

            customer = self._session.get(Customer, data.customer_id)
            if (
                customer is None
                or customer.firm_id != firm_scope
                or customer.is_deleted
            ):
                raise ValidationError("That customer is not one of this firm's.")
        narration = (
            f"{listed.name}: {data.remarks}"
            if data.remarks
            else f"Stock written off as {listed.name.lower()}"
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.WRITE_OFF.value,
                batch_id=data.batch_id,
                reference_number=reference,
                reference_type=reason,
                transaction_date=data.transaction_date,
                quantity=base_quantity,
                current_delta=-from_current,
                damaged_delta=-from_damaged,
                quarantine_delta=-from_quarantine,
                # The whole amount leaves the firm, whichever bucket held it.
                owned_delta=-base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=narration,
            ),
        )
        transaction.customer_id = data.customer_id
        # The flush is required: request sessions do not autoflush, so the row
        # staged above is invisible to this query until it is written.
        self._session.flush()
        entry = self._session.scalar(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == transaction.id
            )
        )
        value = Decimal(str(entry.total_cost or ZERO)) if entry else ZERO
        DocumentPostingService(self._session).post_stock_adjustment(
            firm_id=firm_scope,
            transaction_id=transaction.id,
            reference_number=reference,
            transaction_date=data.transaction_date,
            value_delta=-value,
            actor_id=actor_id,
            remarks=narration,
            expense_purpose=ISSUE_PURPOSES.get(
                reason, ControlAccountPurpose.INVENTORY_ADJUSTMENT
            ),
            expense_account_id=listed.ledger_account_id,
        )
        StockEvidenceService(self._session).stage_for_movement(
            transaction, data.attachments, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="inventory.stock_written_off",
            entity_type="inventory_transaction",
            entity_id=transaction.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reference_number": reference,
                "reason": reason,
                "quantity": str(base_quantity),
            },
        )
        self._commit()
        self._session.refresh(transaction)
        return transaction

    def quarantine_stock(
        self,
        data: StockQuarantineCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> InventoryTransaction:
        """Hold stock back from sale, or release it again.

        Quarantined stock is still owned and still worth what it was, so this
        moves quantity between buckets and posts nothing. Condemning it is a
        separate decision taken once somebody has looked at the goods, and it
        goes through `write_off_stock`.

        Args:
            data: What is being held or released.
            firm_scope: The owning firm.
            actor_id: The user doing it.

        Returns:
            The movement written.

        Raises:
            ValidationError: If there is not that much to hold or release.

        """
        assert_stock_date_in_open_period(
            self._session,
            firm_scope,
            data.transaction_date,
            what="A quarantine hold or release",
        )
        transaction = self.stage_quarantine(
            data, firm_scope=firm_scope, actor_id=actor_id
        )
        self._commit()
        self._session.refresh(transaction)
        return transaction

    def stage_quarantine(
        self,
        data: StockQuarantineCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> InventoryTransaction:
        """Hold or release stock without committing, for a composing caller.

        A goods receipt holds what needs inspection in the same transaction
        that brought it in (BUY-9).
        """
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            storage_node_id=data.storage_node_id,
            product_id=data.product_id,
            actor_id=actor_id,
            batch_id=data.batch_id,
        )
        holding = data.action == QuarantineAction.HOLD
        available = (
            inventory.current_quantity - inventory.reserved_quantity
            if holding
            else inventory.quarantine_quantity
        )
        verb = "hold" if holding else "release"
        if data.quantity > available:
            raise ValidationError(
                f"There is {available} to {verb}, so {data.quantity} cannot be."
            )
        sign = Decimal("-1") if holding else Decimal("1")
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=(
                    InventoryTransactionType.QUARANTINE_HOLD.value
                    if holding
                    else InventoryTransactionType.QUARANTINE_RELEASE.value
                ),
                batch_id=data.batch_id,
                reference_number=self._movement_reference(
                    data, "QUARANTINE", firm_id=firm_scope, actor_id=actor_id
                ),
                reference_type="QUARANTINE",
                transaction_date=data.transaction_date,
                quantity=data.quantity,
                current_delta=sign * data.quantity,
                quarantine_delta=-sign * data.quantity,
                remarks=data.remarks,
                revalues=False,
            ),
        )
        # A named row, so the trail says a hold was placed rather than only
        # that a movement was written (D-STK-6).
        record_audit(
            self._session,
            action=(
                "inventory.quarantine.held"
                if holding
                else "inventory.quarantine.released"
            ),
            entity_type="inventory_transaction",
            entity_id=transaction.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reference_number": transaction.reference_number,
                "product_id": str(data.product_id),
                "batch_id": str(data.batch_id) if data.batch_id else None,
                "quantity": str(data.quantity),
            },
        )
        self._session.flush()
        return transaction

    def transfer_stock(
        self,
        data: StockTransferCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> tuple[InventoryTransaction, InventoryTransaction]:
        """Move stock from one warehouse to another.

        Two movements, one out and one in, and **no journal**. The firm still
        owns the same goods at the same value afterwards; there is a single
        inventory control account, so debiting and crediting it for the same
        amount would put noise in the ledger rather than information. A firm
        that wanted stock by warehouse in the accounts would need an account
        per warehouse, which is a different feature and a much larger one.

        The value is held still deliberately. Stock leaves at the moving
        average and arrives at the same figure, so a transfer cannot quietly
        revalue a product -- which it would if the inbound leg were left to
        value itself at nothing.

        Args:
            data: What is moving, from where, to where.
            firm_scope: The owning firm.
            actor_id: The user moving it.

        Returns:
            The outbound and inbound movements, in that order.

        Raises:
            ValidationError: If the source does not hold enough to send.

        """
        assert_stock_date_in_open_period(
            self._session, firm_scope, data.transaction_date, what="A transfer"
        )
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=data.product_id,
            quantity=(
                data.entered_quantity
                if data.entered_quantity is not None
                else data.quantity
            ),
            entered_uom_id=data.entered_uom_id,
            conversion_version=None,
            on_date=data.transaction_date,
        )
        source = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.from_warehouse_id,
            storage_node_id=data.from_storage_node_id,
            product_id=data.product_id,
            actor_id=actor_id,
            batch_id=data.batch_id,
        )
        # Unlike a dispatch, which may run stock negative because the goods
        # have physically gone, a transfer of stock the source does not hold is
        # a keying error: nothing left the building.
        available = source.current_quantity - source.reserved_quantity
        if base_quantity > available:
            raise ValidationError(
                f"The source holds {available} available, so {base_quantity} "
                "cannot be transferred out of it."
            )
        held_average = self.valuation_for(
            firm_scope=firm_scope, product_id=data.product_id
        ).average_cost
        reference = self._movement_reference(
            data, "TRANSFER", firm_id=firm_scope, actor_id=actor_id
        )
        outbound = self._stage_movement(
            source,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.TRANSFER_OUT.value,
                batch_id=data.batch_id,
                reference_number=reference,
                reference_type="TRANSFER",
                transaction_date=data.transaction_date,
                quantity=base_quantity,
                current_delta=-base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=data.remarks,
            ),
        )
        # The destination sits under its own branch, which need not be the
        # source's: moving goods between branches is the ordinary reason to
        # transfer at all. Until 2026-09-12 the inbound leg was keyed on the
        # request's branch, so any warehouse outside it was refused as
        # "Warehouse does not belong to the selected branch" (plan item 8.3).
        to_branch_id = self._session.scalar(
            select(Warehouse.branch_id).where(
                Warehouse.id == data.to_warehouse_id,
                Warehouse.firm_id == firm_scope,
                Warehouse.is_deleted.is_(False),
            )
        )
        if to_branch_id is None:
            raise ValidationError(
                "The destination warehouse does not belong to the active firm."
            )
        from app.branches.services.registration import BranchRegistration

        registration = BranchRegistration(self._session)
        sent_under = registration.gstin_for(firm_scope, data.branch_id)
        received_under = registration.gstin_for(firm_scope, to_branch_id)
        if sent_under and received_under and sent_under != received_under:
            # Between two GSTINs a move of goods is a supply (STK-2).
            raise ValidationError(
                f"The goods would leave GSTIN {sent_under} for {received_under}; "
                "between two registrations that is a supply, so raise a sales "
                "invoice to the other branch instead of a transfer."
            )
        destination = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=to_branch_id,
            warehouse_id=data.to_warehouse_id,
            storage_node_id=data.to_storage_node_id,
            product_id=data.product_id,
            actor_id=actor_id,
            batch_id=data.batch_id,
        )
        inbound = self._stage_movement(
            destination,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.TRANSFER_IN.value,
                batch_id=data.batch_id,
                reference_number=reference,
                reference_type="TRANSFER",
                transaction_date=data.transaction_date,
                quantity=base_quantity,
                current_delta=base_quantity,
                # Arrives at what it left at, so the move is value-neutral.
                unit_cost=held_average,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=data.remarks,
            ),
        )
        # Imported here for the reason `BatchSerialService` is, further up:
        # the serial trail's package reads stock totals from this module.
        from app.inventory.services.transfer_serials import TransferSerials

        # The units go where the goods went (D-STK-40), or a dispatch from
        # the destination refuses them as not being in that warehouse.
        TransferSerials(self._session).move(
            serial_ids=data.serial_ids,
            quantity=base_quantity,
            outbound=outbound,
            inbound=inbound,
            actor_id=actor_id,
        )
        StockEvidenceService(self._session).stage_for_movement(
            outbound, data.attachments, actor_id=actor_id
        )
        record_audit(
            self._session,
            action="inventory.stock_transferred",
            entity_type="inventory_transaction",
            entity_id=outbound.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reference_number": reference,
                "quantity": str(base_quantity),
                "from_warehouse_id": str(data.from_warehouse_id),
                "to_branch_id": str(to_branch_id),
                "to_warehouse_id": str(data.to_warehouse_id),
            },
        )
        self._commit()
        self._session.refresh(outbound)
        self._session.refresh(inbound)
        return outbound, inbound

    def create_adjustment(
        self,
        data: InventoryAdjustmentCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        enforce_limit: bool = True,
    ) -> InventoryTransaction:
        """Post a stock adjustment movement, and commit it on its own.

        ``enforce_limit`` is False only where an approved request is posted
        (STK-8): the approval already judged the value.
        """
        if enforce_limit:
            from app.inventory.services.adjustment_approval import (
                StockAdjustmentApprovalService,
            )

            StockAdjustmentApprovalService(self._session).assert_within_limit(
                firm_scope,
                actor_id,
                product_id=data.product_id,
                quantity=self.moved_base_quantity(data, firm_scope=firm_scope),
            )
        transaction = self.stage_adjustment(
            data, firm_scope=firm_scope, actor_id=actor_id
        )
        self._commit()
        self._session.refresh(transaction)
        return transaction

    def stage_adjustment(
        self,
        data: InventoryAdjustmentCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> InventoryTransaction:
        """Write a stock adjustment and its journal, flushed but not committed.

        A caller making several adjustments as one decision -- a count sheet
        is one -- composes this and commits once, so a line that fails leaves
        none of the others behind. Committing per adjustment left a sheet
        still DRAFT beside stock and journals it had already moved (D-STK-3).
        """
        assert_stock_date_not_ahead(
            self._session,
            firm_scope,
            data.transaction_date,
            what="A stock adjustment",
        )
        # Filled once here, so the movement and its journal carry the same
        # number rather than each drawing one.
        data = data.model_copy(
            update={
                "reference_number": self._movement_reference(
                    data, "ADJUSTMENT", firm_id=firm_scope, actor_id=actor_id
                )
            }
        )
        listed = None
        if data.reason_code:
            from app.inventory.services.adjustment_reasons import (
                AdjustmentReasonService,
            )

            listed = AdjustmentReasonService(self._session).resolve(
                firm_scope, data.reason_code
            )
            update: dict[str, object] = {"reason_code": listed.code}
            if data.reference_type == "ADJUSTMENT":
                update["reference_type"] = listed.code
            if not data.remarks:
                update["remarks"] = listed.name
            data = data.model_copy(update=update)
        transaction, value_delta = self.stage_adjustment_movement(
            data, firm_scope=firm_scope, actor_id=actor_id
        )
        DocumentPostingService(self._session).post_stock_adjustment(
            firm_id=firm_scope,
            transaction_id=transaction.id,
            reference_number=self._movement_reference(
                data, "ADJUSTMENT", firm_id=firm_scope, actor_id=actor_id
            ),
            transaction_date=data.transaction_date,
            value_delta=value_delta,
            actor_id=actor_id,
            remarks=data.remarks,
            expense_purpose=(
                ISSUE_PURPOSES.get(
                    listed.code, ControlAccountPurpose.INVENTORY_ADJUSTMENT
                )
                if listed is not None
                else ControlAccountPurpose.INVENTORY_ADJUSTMENT
            ),
            expense_account_id=None if listed is None else listed.ledger_account_id,
        )
        StockEvidenceService(self._session).stage_for_movement(
            transaction, data.attachments, actor_id=actor_id
        )
        self._session.flush()
        return transaction

    def stage_adjustment_movement(
        self,
        data: InventoryAdjustmentCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> tuple[InventoryTransaction, Decimal]:
        """Write the stock side of an adjustment, and return what it moved.

        No journal: the caller posts one. A single adjustment posts its own
        (`stage_adjustment`); a count sheet posts one journal for all of its
        differences, because each line posting under the count's number broke
        the reference's uniqueness on the second line (D-STK-11).

        Returns:
            The movement, and the change in stock value it made -- positive
            when stock rose -- taken from the stock ledger row it wrote.

        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=data.product_id,
            quantity=(
                data.entered_quantity
                if data.entered_quantity is not None
                else data.quantity
            ),
            entered_uom_id=data.entered_uom_id,
            conversion_version=None,
            on_date=data.transaction_date,
        )
        delta_sign = Decimal("1") if data.quantity >= 0 else Decimal("-1")
        delta = abs(base_quantity) * delta_sign
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            storage_node_id=data.storage_node_id,
            product_id=data.product_id,
            actor_id=actor_id,
            batch_id=data.batch_id,
        )
        if delta < ZERO:
            # Against what is there, not what is free: a count that finds
            # fewer than are promised to orders still has to be posted.
            self._refuse_below_zero(
                inventory,
                -delta,
                "taken off by an adjustment",
                held=inventory.current_quantity,
            )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.ADJUSTMENT.value,
                batch_id=data.batch_id,
                reference_number=self._movement_reference(
                    data, "ADJUSTMENT", firm_id=firm_scope, actor_id=actor_id
                ),
                reference_type=data.reference_type.strip().upper(),
                transaction_date=data.transaction_date,
                quantity=abs(base_quantity),
                current_delta=delta,
                entered_quantity=abs(entered_quantity),
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=data.remarks,
            ),
        )
        # An adjustment is the movement with no paperwork behind it, so nothing
        # on screen would ever hint that the ledger had stopped agreeing with
        # the stock it controls. The value is taken from the stock ledger row
        # the movement just wrote, signed by the direction stock went.
        #
        # The flush is required, not defensive: request sessions are built with
        # `autoflush=False`, so the row staged above is invisible to a query
        # until it is written. Without it the value read as nothing and the
        # adjustment posted no journal at all -- which unit tests could not
        # catch, because their session factory autoflushes by default.
        self._session.flush()
        entry = self._session.scalar(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == transaction.id
            )
        )
        movement_value = Decimal(str(entry.total_cost or ZERO)) if entry else ZERO
        return transaction, movement_value if delta >= ZERO else -movement_value

    def _refuse_below_zero(
        self,
        inventory: InventoryRecord,
        quantity: Decimal,
        done: str,
        *,
        held: Decimal | None = None,
    ) -> None:
        """Refuse to take out more than a location has free to give.

        A repack of 999 against 40 left the bulk at -959 and made a pack at
        the cost of all 999, and an adjustment of -999 against 10 posted its
        journal (inventory round 1, F3 and F4). Like a transfer and a return
        to the supplier: goods that are not here cannot be taken, unless the
        product is one the firm lets run below zero.
        """
        available = (
            held
            if held is not None
            else inventory.current_quantity - inventory.reserved_quantity
        )
        if quantity <= available:
            return
        product = self._session.get(Product, inventory.product_id)
        if product is not None and product.allow_negative_stock:
            return
        label = f"{product.code} - {product.name}" if product else "This product"
        what = "holds" if held is not None else "has free"
        raise ValidationError(
            f"{label}: this location {what} {_plain(available)}, so "
            f"{_plain(quantity)} cannot be {done}."
        )

    def stage_repack_movement(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        batch_id: UUID | None,
        quantity: Decimal,
        unit_cost: Decimal | None,
        reference_number: str,
        transaction_date: date,
        remarks: str,
        actor_id: UUID,
    ) -> tuple[InventoryTransaction, Decimal]:
        """Move one repack line, unposted; return it and the value it moved.

        STK-4. ``quantity`` is signed in the stock unit: negative consumes at
        the moving average, positive produces at ``unit_cost``. No journal --
        the repack posts its wastage alone.
        """
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        if quantity < ZERO:
            self._refuse_below_zero(inventory, -quantity, "repacked")
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.ADJUSTMENT.value,
                batch_id=batch_id,
                reference_number=reference_number,
                reference_type="REPACK",
                transaction_date=transaction_date,
                quantity=abs(quantity),
                current_delta=quantity,
                unit_cost=unit_cost,
                remarks=remarks,
            ),
        )
        self._session.flush()
        entry = self._session.scalar(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == transaction.id
            )
        )
        value = Decimal(str(entry.total_cost or ZERO)) if entry else ZERO
        return transaction, value

    def allocate_for_repack(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product: Product,
        quantity: Decimal,
        as_of: date,
    ) -> list[tuple[UUID | None, Decimal]]:
        """Choose the batches a repack consumes, as a dispatch would.

        Earliest expiry first among batches in date and outside the
        product's stop-selling window: what may not be sold as itself is not
        made into something else to be sold. The shortage is named by
        product, because a kit has several parts and "short by 5" does not
        say of which.

        Raises:
            ValidationError: If the batches free here do not cover it.

        """
        try:
            return self.allocate_for_dispatch(
                firm_scope=firm_scope,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                storage_node_id=None,
                product_id=product.id,
                quantity=quantity,
                as_of=as_of,
            )
        except ValidationError as error:
            raise ValidationError(
                f"{product.code} - {product.name}: {quantity} cannot be "
                f"repacked from its batches here. {error.message}"
            ) from error

    def stage_transfer_leg(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        batch_id: UUID | None,
        transaction_type: InventoryTransactionType,
        quantity: Decimal,
        reference_number: str,
        transaction_date: date,
        remarks: str,
        actor_id: UUID,
        current_delta: Decimal = ZERO,
        in_transit_delta: Decimal = ZERO,
        damaged_delta: Decimal = ZERO,
        owned_delta: Decimal | None = None,
        unit_cost: Decimal | None = None,
        require_available: bool = False,
    ) -> tuple[InventoryTransaction, Decimal]:
        """Move one leg of a transfer document, unposted (STK-1).

        The firm owns goods in transit. The source leg leaves at the moving
        average; the in-transit leg at the destination owns them again at
        that same figure (``owned_delta``, ``unit_cost``), so the pair is
        value-neutral firm-wide and the destination's valuation shows what is
        on its way. The receiving leg takes them out of transit onto the shelf
        and gives up ownership only of what never arrived, at the average.
        Damaged goods arrive blocked from sale, as on a goods receipt.
        Returns the movement and the value it moved.

        Raises:
            ValidationError: If ``require_available`` and the location does
                not hold that much free stock.

        """
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        if require_available:
            available = inventory.current_quantity - inventory.reserved_quantity
            if quantity > available:
                raise ValidationError(
                    f"The source holds {available} available, so {quantity} "
                    "cannot be sent from it."
                )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=transaction_type.value,
                batch_id=batch_id,
                reference_number=reference_number,
                reference_type="STOCK_TRANSFER",
                transaction_date=transaction_date,
                quantity=quantity,
                current_delta=current_delta,
                in_transit_delta=in_transit_delta,
                blocked_delta=damaged_delta,
                damaged_delta=damaged_delta,
                owned_delta=owned_delta,
                unit_cost=unit_cost,
                remarks=remarks,
            ),
        )
        self._session.flush()
        entry = self._session.scalar(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == transaction.id
            )
        )
        value = Decimal(str(entry.total_cost or ZERO)) if entry else ZERO
        return transaction, value

    def stage_revaluation(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        batch_id: UUID | None,
        amount: Decimal,
        reference_number: str,
        transaction_date: date,
        remarks: str,
        actor_id: UUID,
    ) -> InventoryTransaction:
        """Add value to stock already held, moving no quantity (BUY-16).

        A landed cost lands after the goods: the quantity on hand is what it
        is, and only its value -- and so its moving average -- changes. The
        movement carries no quantity in any bucket; its ledger entry carries
        the value added and the average after it, which is what the
        valuation and the stock statement read. ``amount`` is negative when a
        cancelled voucher takes the value back off.

        Raises:
            ValidationError: If value is added to a product with nothing on
                hand to carry it.

        """
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.LANDED_COST.value,
                batch_id=batch_id,
                reference_number=reference_number,
                reference_type="LANDED_COST",
                transaction_date=transaction_date,
                quantity=ZERO,
                revalues=False,
                remarks=remarks,
            ),
        )
        valuation = self.valuation_for(firm_scope=firm_scope, product_id=product_id)
        on_hand = Decimal(str(valuation.quantity_on_hand))
        if on_hand <= ZERO and amount != ZERO:
            raise ValidationError(
                "Nothing of this product is on hand to carry the added cost."
            )
        new_value = quantize_money(Decimal(str(valuation.total_value)) + amount)
        valuation.total_value = new_value
        valuation.average_cost = new_value / on_hand if on_hand > ZERO else ZERO
        valuation.updated_by = actor_id
        self._session.flush()
        entry = self._session.scalar(
            select(StockLedgerEntry).where(
                StockLedgerEntry.transaction_id == transaction.id
            )
        )
        if entry is not None:
            entry.total_cost = quantize_money(amount)
            entry.average_cost_after = valuation.average_cost
        return transaction

    def record_goods_receipt(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        total_quantity: Decimal,
        blocked_quantity: Decimal = Decimal("0"),
        damaged_quantity: Decimal = Decimal("0"),
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        line_conversion: LineConversion | None = None,
        remarks: str | None = None,
        unit_cost: Decimal | None = None,
        batch_id: UUID | None = None,
        entered_unit_cost: Decimal | None = None,
    ) -> InventoryTransaction:
        """Post the stock a goods receipt brought in.

        ``batch_id`` puts the goods in that batch's row rather than the
        product's single row, which is what makes two deliveries of one
        medicine countable apart.

        ``unit_cost`` is the cost of one **stock** unit. A document that
        knows only what one of *its* units cost -- a box, on a line received
        by the box -- passes ``entered_unit_cost`` instead, and it is divided
        by the factor the quantity moved at, so the movement is worth what
        the line is: the receipt passed a box's cost as ``unit_cost`` and 24
        pieces came in at 720.00 each.
        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else total_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            line_conversion=line_conversion,
            on_date=transaction_date,
        )
        conversion_factor = (
            base_quantity / entered_quantity
            if entered_quantity not in {None, ZERO}
            else Decimal("1")
        )
        blocked_base = Decimal(str(blocked_quantity)) * conversion_factor
        damaged_base = Decimal(str(damaged_quantity)) * conversion_factor
        if entered_unit_cost is not None:
            unit_cost = (
                entered_unit_cost / conversion_factor
                if conversion_factor > ZERO
                else entered_unit_cost
            )
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.GOODS_RECEIPT.value,
                batch_id=batch_id,
                unit_cost=unit_cost,
                reference_number=reference_number.strip().upper(),
                reference_type="GOODS_RECEIPT",
                transaction_date=transaction_date,
                quantity=base_quantity,
                current_delta=base_quantity,
                blocked_delta=blocked_base + damaged_base,
                damaged_delta=damaged_base,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks,
            ),
        )
        self._session.flush()
        return transaction

    def valuation_for(self, *, firm_scope: UUID, product_id: UUID) -> ProductValuation:
        """Return a product's running valuation, creating it on first use.

        Args:
            firm_scope: The owning firm.
            product_id: The product being valued.

        Returns:
            The valuation state row.

        """
        row = self._session.scalar(
            select(ProductValuation).where(
                ProductValuation.firm_id == firm_scope,
                ProductValuation.product_id == product_id,
                ProductValuation.is_deleted.is_(False),
            )
        )
        if row is None:
            row = ProductValuation(firm_id=firm_scope, product_id=product_id)
            self._session.add(row)
            self._session.flush()
        return row

    def _held_average(self, inventory: InventoryRecord, movement: _Movement) -> Decimal:
        """Return the average a value-neutral movement leaves untouched."""
        return self.valuation_for(
            firm_scope=inventory.firm_id, product_id=inventory.product_id
        ).average_cost

    def _apply_valuation(
        self, inventory: InventoryRecord, movement: _Movement, actor_id: UUID
    ) -> tuple[Decimal | None, Decimal | None, Decimal]:
        """Roll the moving weighted average forward for one movement.

        Receipts move the average toward the price paid; issues leave it alone
        and consume at it, which is what makes the value released equal the cost
        of goods sold. A receipt with no stated cost is valued at the current
        average rather than at zero, so an unpriced movement cannot silently
        destroy the average.

        Args:
            inventory: The projection the movement applies to.
            movement: The staged movement.
            actor_id: The user responsible.

        Returns:
            The unit cost applied, the total cost of the movement, and the
            average cost after it.

        """
        valuation = self.valuation_for(
            firm_scope=inventory.firm_id, product_id=inventory.product_id
        )
        delta = (
            movement.current_delta
            if movement.owned_delta is None
            else movement.owned_delta
        )
        average = Decimal(str(valuation.average_cost))
        on_hand = Decimal(str(valuation.quantity_on_hand))

        if delta == ZERO:
            # Reservations and status moves shift no goods and no value.
            return None, None, average

        if delta > ZERO:
            unit_cost = average if movement.unit_cost is None else movement.unit_cost
            new_quantity = on_hand + delta
            new_value = Decimal(str(valuation.total_value)) + (delta * unit_cost)
            average = (new_value / new_quantity) if new_quantity != ZERO else ZERO
        else:
            unit_cost = average
            new_quantity = on_hand + delta
            new_value = Decimal(str(valuation.total_value)) + (delta * average)
            if new_quantity <= ZERO:
                # Stock fully issued: hold no residual value on nothing.
                new_quantity = new_quantity if new_quantity < ZERO else ZERO
                new_value = ZERO if new_quantity == ZERO else new_value

        valuation.quantity_on_hand = new_quantity
        valuation.total_value = quantize_money(new_value)
        valuation.average_cost = average
        valuation.updated_by = actor_id
        return unit_cost, quantize_money(abs(delta) * unit_cost), average

    def reverse_transaction(
        self,
        transaction_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> InventoryTransaction:
        """Post the exact inverse of an existing movement.

        Cancelling a document that already moved stock must put the stock back,
        otherwise a cancelled goods receipt or purchase return leaves phantom
        quantities behind. The reversal is itself an immutable movement linked to
        the original, so the ledger keeps both halves and cannot be replayed.

        Args:
            transaction_id: The movement to reverse.
            firm_scope: The firm that owns the movement.
            actor_id: The user performing the reversal.
            reason: Optional narration stored on the reversing movement.

        Returns:
            The reversing inventory transaction.

        Raises:
            ResourceNotFoundError: If the movement or its projection is missing.
            ValidationError: If the movement was already reversed.

        """
        original = self._session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.id == transaction_id,
                InventoryTransaction.firm_id == firm_scope,
                InventoryTransaction.is_deleted.is_(False),
            )
        )
        if original is None:
            raise ResourceNotFoundError("Inventory transaction not found.")
        already_reversed = self._session.scalar(
            select(InventoryTransaction.id).where(
                InventoryTransaction.reversal_of_transaction_id == original.id,
                InventoryTransaction.is_deleted.is_(False),
            )
        )
        if already_reversed is not None:
            raise ValidationError("This inventory movement was already reversed.")
        inventory = self._session.get(InventoryRecord, original.inventory_id)
        if inventory is None:
            raise ResourceNotFoundError("Inventory record not found.")
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=f"{original.transaction_type}{REVERSAL_SUFFIX}"[:40],
                # The unit that came in goes back out, so the reversal names
                # it wherever the original did.
                serial_id=original.serial_id,
                reference_number=original.reference_number,
                reference_type=original.reference_type,
                # Dated when the goods moved back, not when they first moved:
                # the original's date showed stock leaving the day it arrived
                # and ran `last_transaction_at` backwards (D-STK-9). Never
                # before the original, which may itself be dated ahead.
                transaction_date=max(
                    original.transaction_date, firm_today(self._session, firm_scope)
                ),
                quantity=-original.quantity,
                current_delta=-original.current_quantity_delta,
                reserved_delta=-original.reserved_quantity_delta,
                blocked_delta=-original.blocked_quantity_delta,
                damaged_delta=-original.damaged_quantity_delta,
                quarantine_delta=-original.quarantine_quantity_delta,
                in_transit_delta=-original.in_transit_quantity_delta,
                # Undo the valuation the original applied, not the one
                # its sellable bucket implies. A return that brought
                # back a damaged unit owned two and shelved one;
                # reversing only the shelf left the value behind.
                owned_delta=(
                    None
                    if original.owned_quantity_delta is None
                    else -original.owned_quantity_delta
                ),
                entered_quantity=(
                    -original.entered_quantity
                    if original.entered_quantity is not None
                    else None
                ),
                entered_uom_id=original.entered_uom_id,
                conversion_version=original.conversion_version,
                remarks=reason,
            ),
        )
        transaction.reversal_of_transaction_id = original.id
        self._session.flush()
        return transaction

    def record_purchase_return(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        return_quantity: Decimal,
        sellable_quantity: Decimal,
        damaged_quantity: Decimal = Decimal("0"),
        scrap_quantity: Decimal = Decimal("0"),
        quarantine_quantity: Decimal = Decimal("0"),
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        remarks: str | None = None,
        batch_id: UUID | None = None,
        rejects_held: Decimal = Decimal("0"),
    ) -> InventoryTransaction:
        """Post the stock a purchase return sent back, from one batch.

        ``batch_id`` takes the goods out of that batch's row rather than the
        product's untracked one. Without it a batch could be received, sold
        from, and then returned to the supplier off stock that was never in it.

        ``quarantine_quantity`` is the part of the return the line says is
        standing in quarantine; it leaves that bucket and the rest leaves
        sellable stock. ``rejects_held`` is how much of the receipt line was
        rejected at inspection and kept for a return and has not gone back
        yet, in the stock unit: the return takes those first, as far as the
        location still holds them in quarantine, whether or not the line
        says so.

        Raises:
            ValidationError: If more is returned from quarantine than the
                location holds there, or more from sellable stock than is
                available there and the product may not go negative.

        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else return_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            on_date=transaction_date,
        )
        conversion_factor = (
            base_quantity / entered_quantity
            if entered_quantity not in {None, ZERO}
            else Decimal("1")
        )
        sellable_base = Decimal(str(sellable_quantity)) * conversion_factor
        damaged_base = Decimal(str(damaged_quantity)) * conversion_factor
        scrap_base = Decimal(str(scrap_quantity)) * conversion_factor
        quarantine_base = Decimal(str(quarantine_quantity)) * conversion_factor
        if quarantine_base > base_quantity:
            raise ValidationError(
                "Quarantined return quantity cannot exceed return quantity."
            )
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        # Goods rejected at inspection and kept for a return are in the
        # quarantine bucket, not the sellable one: they were moved out of it
        # when they were held. Taking them from sellable stock left the
        # rejects held for ever and removed good units instead (D-BUY-44).
        if quarantine_base > inventory.quarantine_quantity:
            raise ValidationError(
                f"This location holds {inventory.quarantine_quantity} in "
                f"quarantine, so {quarantine_base} cannot be returned from it."
            )
        quarantine_base = max(
            quarantine_base,
            min(base_quantity, rejects_held, inventory.quarantine_quantity),
        )
        # Like a transfer and unlike a dispatch: goods that are not here
        # cannot be crated up for the supplier, so a return of them is a
        # keying error -- usually goods already sold (D-BUY-45). What comes
        # out of quarantine was checked against quarantine above.
        from_sellable = base_quantity - quarantine_base
        available = inventory.current_quantity - inventory.reserved_quantity
        if from_sellable > ZERO and from_sellable > available:
            product = self._session.get(Product, product_id)
            if product is None or not product.allow_negative_stock:
                hint = (
                    " Name the batch the goods are leaving."
                    if batch_id is None
                    and self._held_in_batches(inventory, product_id=product_id)
                    else ""
                )
                raise ValidationError(
                    f"This location holds {available} available, so "
                    f"{from_sellable} cannot be returned to the supplier "
                    f"from it.{hint}"
                )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.RETURN.value,
                batch_id=batch_id,
                reference_number=reference_number.strip().upper(),
                reference_type="PURCHASE_RETURN",
                transaction_date=transaction_date,
                quantity=base_quantity,
                current_delta=-from_sellable,
                blocked_delta=ZERO,
                damaged_delta=ZERO,
                quarantine_delta=-quarantine_base,
                # The whole amount leaves the firm, whichever bucket held it.
                owned_delta=-base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks
                or (
                    f"purchase_return buckets sellable={sellable_base} "
                    f"damaged={damaged_base} scrap={scrap_base} "
                    f"quarantine={quarantine_base}"
                ),
            ),
        )
        if sellable_base > base_quantity:
            raise ValidationError(
                "Sellable return quantity cannot exceed return quantity."
            )
        self._session.flush()
        return transaction

    @staticmethod
    def _damaged_off_the_shelf(inventory: InventoryRecord) -> Decimal:
        """Say how much of the damaged bucket stands outside current stock.

        Two things fill the bucket. Goods that arrive damaged on a receipt or
        a transfer stay in current stock and are blocked from sale as well,
        so a write-off already reaches them. Goods a customer sent back
        damaged or as scrap are in the damaged bucket only. The row does not
        say which is which, so what is blocked is taken to be the first kind:
        the answer can fall short where stock is blocked for another reason,
        and never runs over.
        """
        return max(inventory.damaged_quantity - inventory.blocked_quantity, ZERO)

    def _held_in_batches(self, inventory: InventoryRecord, *, product_id: UUID) -> bool:
        """Say whether this warehouse holds the product in a batch's own row."""
        return (
            self._session.scalar(
                select(InventoryRecord.id)
                .where(
                    InventoryRecord.firm_id == inventory.firm_id,
                    InventoryRecord.warehouse_id == inventory.warehouse_id,
                    InventoryRecord.product_id == product_id,
                    InventoryRecord.batch_id.is_not(None),
                    InventoryRecord.is_deleted.is_(False),
                    InventoryRecord.current_quantity > ZERO,
                )
                .limit(1)
            )
            is not None
        )

    def record_sales_return(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        return_quantity: Decimal,
        restock_quantity: Decimal,
        damaged_quantity: Decimal = Decimal("0"),
        scrap_quantity: Decimal = Decimal("0"),
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        remarks: str | None = None,
        batch_id: UUID | None = None,
        serial_id: UUID | None = None,
        hold_for_check: bool = False,
    ) -> InventoryTransaction:
        """Take back into stock the goods a customer sent back.

        The mirror of ``record_purchase_return``, in the other direction. Only
        ``restock_quantity`` returns to the sellable bucket: goods that came
        back broken are still the firm's and still worth what they cost, but
        they cannot be sold, so they arrive in the damaged bucket instead, and
        scrap arrives there with them: a write-off takes both out. The
        firm gains ownership of all of it either way, which is why the
        valuation follows the whole return rather than the sellable part --
        without that, damaged goods would come back onto the shelf at no cost
        and the inventory account would understate what the firm holds.

        The unit cost is left unset so the goods return at the moving average
        the product is carried at. Bringing them back at the selling price
        would revalue stock at a number no purchase ever paid.

        ``hold_for_check`` (the firm's *hold customer returns until checked*,
        STK-13) puts the sellable part in quarantine instead of on the shelf;
        releasing it is the ordinary quarantine release.
        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else return_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            on_date=transaction_date,
        )
        conversion_factor = (
            base_quantity / entered_quantity
            if entered_quantity not in {None, ZERO}
            else Decimal("1")
        )
        restock_base = Decimal(str(restock_quantity)) * conversion_factor
        damaged_base = Decimal(str(damaged_quantity)) * conversion_factor
        scrap_base = Decimal(str(scrap_quantity)) * conversion_factor
        if restock_base + damaged_base + scrap_base > base_quantity:
            raise ValidationError(
                "Restock, damaged and scrap quantities cannot exceed the "
                "returned quantity."
            )
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.SALES_RETURN.value,
                batch_id=batch_id,
                serial_id=serial_id,
                reference_number=reference_number.strip().upper(),
                reference_type="SALES_RETURN",
                transaction_date=transaction_date,
                quantity=base_quantity,
                current_delta=ZERO if hold_for_check else restock_base,
                # Scrapped goods arrive with the damaged ones. They landed in
                # no bucket at all while the valuation went on carrying them,
                # so nothing on screen could write them off (D-STK-46).
                damaged_delta=damaged_base + scrap_base,
                blocked_delta=ZERO,
                quarantine_delta=restock_base if hold_for_check else ZERO,
                # Everything that came back is owned, sellable or not, so the
                # value follows the whole return rather than the shelf-ready
                # part of it.
                owned_delta=base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks
                or (
                    f"sales_return buckets restock={restock_base} "
                    f"damaged={damaged_base} scrap={scrap_base}"
                ),
            ),
        )
        self._session.flush()
        return transaction

    def record_sales_order_reservation(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        reserve_quantity: Decimal,
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        line_conversion: LineConversion | None = None,
        remarks: str | None = None,
        batch_id: UUID | None = None,
        share_of_line: bool = False,
    ) -> InventoryTransaction:
        """Reserve stock for a sales order line, against one batch.

        ``batch_id`` holds that batch's stock rather than the product's
        untracked row. Callers split the line with
        ``allocate_for_reservation`` and call this once per batch; the part of
        a reservation no batch can cover is passed with no batch, because there
        is no batch behind it.

        ``share_of_line`` says the entered quantity is one batch's share of a
        line split across batches, not a figure anybody typed: a box of
        twelve drawn ten from one batch and two from the next is 0.8333 and
        0.1667 of a box. The whole-number rule of the unit is the line's to
        pass, not each share's, and the stock that moves is the allocation
        itself -- ten pieces, not 0.8333 of twelve (D-PRC-38).
        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else reserve_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            line_conversion=line_conversion,
            on_date=transaction_date,
            enforce_whole_units=not share_of_line,
        )
        if share_of_line:
            base_quantity = Decimal(str(reserve_quantity))
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.RESERVE.value,
                batch_id=batch_id,
                reference_number=reference_number.strip().upper(),
                reference_type="SALES_ORDER",
                transaction_date=transaction_date,
                quantity=base_quantity,
                reserved_delta=base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks or "sales_order reservation",
            ),
        )
        self._session.flush()
        return transaction

    def release_sales_order_reservation(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        release_quantity: Decimal,
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        line_conversion: LineConversion | None = None,
        remarks: str | None = None,
        batch_id: UUID | None = None,
        share_of_line: bool = False,
    ) -> InventoryTransaction:
        """Release a sales order's reservation.

        ``share_of_line`` is one batch's share of a line held across
        batches: what is let go is that batch's hold itself, in stock units,
        as it was reserved.
        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else release_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            line_conversion=line_conversion,
            on_date=transaction_date,
            enforce_whole_units=False,
        )
        if share_of_line:
            base_quantity = Decimal(str(release_quantity))
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.UNRESERVE.value,
                batch_id=batch_id,
                reference_number=reference_number.strip().upper(),
                reference_type="SALES_ORDER",
                transaction_date=transaction_date,
                quantity=base_quantity,
                reserved_delta=-base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks or "sales_order reservation release",
            ),
        )
        self._session.flush()
        return transaction

    def allocate_for_reservation(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        quantity: Decimal,
        as_of: date | None = None,
        only_batch: UUID | None = None,
        keep_until: date | None = None,
    ) -> ReservationPlan:
        """Choose which batches a sales order holds, earliest expiry first.

        ``only_batch`` is a batch the customer asked for (backlog 79 row 4):
        only it is held, and what it cannot cover is the back order.

        ``keep_until`` is the date the customer's minimum shelf life asks the
        goods to last to, as ``allocate_for_dispatch`` takes it: a batch
        expiring before it is passed over here as it will be there, so the
        hold lands on stock the order can actually ship (D-SELL-58).

        Committing stock at approval is what stops two salespeople promising
        the same box, and until now it committed the *product*: the movement
        went to the untracked row whatever the goods were held in. A firm whose
        stock is all in batches then had reservations on a row with nothing in
        it, driving its available negative while the batch rows sat untouched
        and apparently free.

        Reserving in the same order the goods will ship in keeps the two
        halves of the sales flow talking about the same stock -- dispatch
        releases a batch's reservation and immediately draws from it, because
        both rank by expiry. **And the same stock is a candidate for both.**
        Dispatch stopped drawing expired batches on 2026-09-16 (D-8-1) while
        this went on holding them: a pharmacy approving an order for five held
        the batch that expired in August -- earliest expiry, read literally --
        and the note then shipped from the in-date batch, which had stayed
        free for anybody else to promise. The hold protected nothing. Expired
        stock is dropped here exactly as ``allocate_for_dispatch`` drops it,
        judged on the order's own date (``as_of``) rather than today.

        **Short stock does not fail here.** An order may be taken for more than
        is on the shelf; that is a back order, and the reports count on it. The
        batches cover what they can and the remainder is returned as a single
        pair with no batch, which is the truth: there is no batch behind it.
        When stock that has gone out of date stands behind that remainder, the
        plan says so by batch name, in the words dispatch refuses with -- the
        screen still shows that stock as on hand, and a back order beside
        twenty on the shelf explains nothing.

        Returns:
            The batches to hold, in the order to hold them, any uncovered
            remainder last under ``None``, and the note naming the expired
            stock behind that remainder (empty when there is none).

        """
        rows = self._expiry_ranked_rows(
            firm_scope=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            column=InventoryRecord.available_quantity,
        )
        if only_batch is not None:
            rows = [row for row in rows if row.batch_id == only_batch]
        rows, expired, held_expired = self._without_expired(
            rows, firm_scope=firm_scope, as_of=as_of
        )
        short: dict[UUID, tuple[str, date]] = {}
        if only_batch is None:
            # The batches dispatch will pass over for this customer are not
            # held for them either (D-SELL-58): the hold went on the earliest
            # batch, the next order took the only one that suited, and the
            # first order's dispatch was refused with stock on the shelf. A
            # batch the customer asked for by name is theirs to ask for, and
            # is judged when it ships.
            rows, short = self._without_short_dated(
                rows,
                firm_scope=firm_scope,
                product_id=product_id,
                as_of=as_of,
                keep_until=keep_until,
            )
        outstanding = Decimal(str(quantity))
        allocation: list[tuple[UUID | None, Decimal]] = []
        for row in rows:
            if outstanding <= ZERO:
                break
            take = min(outstanding, Decimal(str(row.available_quantity)))
            if take <= ZERO:
                continue
            allocation.append((row.batch_id, take))
            outstanding -= take
        note = ""
        if outstanding > ZERO:
            allocation.append((None, outstanding))
            note = self._expired_note(
                expired, held_expired, verb="reserved"
            ) + self._short_dated_note(short)
        return ReservationPlan(batches=allocation, expired_note=note)

    def _without_short_dated(
        self,
        rows: list[InventoryRecord],
        *,
        firm_scope: UUID,
        product_id: UUID,
        as_of: date | None,
        keep_until: date | None,
    ) -> tuple[list[InventoryRecord], dict[UUID, tuple[str, date]]]:
        """Drop the rows whose batch will not last as long as it must.

        One step for reservation and dispatch alike, as ``_without_expired``
        is, and for the same reason: the hold has to be on the stock that
        will ship. ``keep_until`` is the date a customer's minimum shelf life
        asks the goods to last to; the product's own stop-selling window
        (STK-5) is a date its goods must outlast in the same way, and the
        later of the two rules.

        Returns:
            The rows that last long enough, and the batches passed over by
            id (number and expiry date, for naming them).

        """
        from app.batch_serial.services.expiry_rules import expiry_rules

        rule = expiry_rules(self._session, firm_scope, {product_id}).get(product_id)
        stop_at = (
            rule.sell_until(as_of or firm_today(self._session, firm_scope))
            if rule
            else None
        )
        if stop_at is not None and (keep_until is None or stop_at > keep_until):
            keep_until = stop_at
        if keep_until is None:
            return rows, {}
        # Good on the day itself is long enough: the customer's shelf life
        # and the stop-selling rule both name the last day that will do.
        short = self._batches_dated_before(
            {row.batch_id for row in rows if row.batch_id is not None},
            keep_until,
        )
        return [row for row in rows if row.batch_id not in short], short

    @staticmethod
    def _short_dated_note(short: dict[UUID, tuple[str, date]]) -> str:
        """Name the batches passed over for a customer's minimum shelf life."""
        if not short:
            return ""
        return (
            " Too short-dated for this customer's minimum shelf life: "
            + ", ".join(
                f"{number} (expires {expiry.isoformat()})"
                for number, expiry in short.values()
            )
            + "."
        )

    def allocate_for_release(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        quantity: Decimal,
        prefer: Sequence[UUID] = (),
        own: Mapping[UUID | None, Decimal] | None = None,
    ) -> list[tuple[UUID | None, Decimal]]:
        """Choose which reservations to let go, earliest expiry first.

        ``own`` is what the order letting go holds on each batch
        (``held_by_reference``). **Its own holds go first**, each up to what
        it holds there. A stock row's reserved quantity belongs to every
        order holding that batch, so releasing by expiry alone let go of
        another order's hold on the earlier batch and kept this order's on
        the later one -- and its dispatch was then refused for stock it had
        itself reserved (D-SELL-58).

        ``prefer`` puts those batches first, in the order given: the batches a
        person chose for a delivery line (backlog 79), so the order's own hold
        on them is let go before the line draws from them.

        The mirror of ``allocate_for_reservation``, and it has to walk the rows
        that actually hold a reservation rather than the ones holding stock:
        releasing a batch that was never held would drive its reserved
        quantity negative.

        Earliest expiry first again, so a dispatch that releases and then
        allocates frees exactly the batch it is about to draw from. Anything
        left over comes off the untracked row, which is where a reservation
        goes that no batch could cover.

        Returns:
            The reservations to release, in the order to release them.

        """
        rows = self._expiry_ranked_rows(
            firm_scope=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            column=InventoryRecord.reserved_quantity,
        )
        if prefer:
            rank: dict[UUID | None, int] = {
                batch_id: index for index, batch_id in enumerate(prefer)
            }
            rows.sort(key=lambda row: rank.get(row.batch_id, len(rank)))
        outstanding = Decimal(str(quantity))
        taken: dict[UUID | None, Decimal] = {}
        order: list[UUID | None] = []

        def take_from(row: InventoryRecord, limit: Decimal) -> None:
            """Let go of up to ``limit`` of one row's reservation."""
            nonlocal outstanding
            left = Decimal(str(row.reserved_quantity)) - taken.get(row.batch_id, ZERO)
            take = min(outstanding, left, limit)
            if take <= ZERO:
                return
            if row.batch_id not in taken:
                order.append(row.batch_id)
            taken[row.batch_id] = taken.get(row.batch_id, ZERO) + take
            outstanding -= take

        for row in rows:
            held = (own or {}).get(row.batch_id, ZERO)
            if held > ZERO:
                take_from(row, held)
        for row in rows:
            if outstanding <= ZERO:
                break
            take_from(row, outstanding)
        allocation: list[tuple[UUID | None, Decimal]] = [
            (batch_id, taken[batch_id]) for batch_id in order
        ]
        if outstanding > ZERO:
            if allocation and allocation[-1][0] is None:
                allocation[-1] = (None, allocation[-1][1] + outstanding)
            else:
                allocation.append((None, outstanding))
        return allocation

    def held_by_reference(
        self,
        *,
        firm_scope: UUID,
        reference_number: str,
        product_id: UUID,
        warehouse_id: UUID,
    ) -> dict[UUID | None, Decimal]:
        """Return what one sales order still holds of a product, by batch.

        A stock row's ``reserved_quantity`` is the sum of every order's hold
        on it and does not say whose. The stock ledger does: every hold and
        every release an order makes carries its number, so what it has put
        on a batch less what it has let go is what it still holds there. A
        batch it holds nothing on is left out; ``None`` is the back order
        no batch covered.
        """
        held: dict[UUID | None, Decimal] = {}
        for batch_id, total in self._session.execute(
            select(
                InventoryTransaction.batch_id,
                func.coalesce(
                    func.sum(InventoryTransaction.reserved_quantity_delta), 0
                ),
            )
            .where(
                InventoryTransaction.firm_id == firm_scope,
                InventoryTransaction.reference_number == reference_number,
                InventoryTransaction.product_id == product_id,
                InventoryTransaction.warehouse_id == warehouse_id,
                InventoryTransaction.reserved_quantity_delta != 0,
                InventoryTransaction.is_deleted.is_(False),
            )
            .group_by(InventoryTransaction.batch_id)
        ).all():
            quantity = Decimal(str(total))
            if quantity > ZERO:
                held[batch_id] = quantity
        return held

    def shippable_past_back_orders(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
    ) -> tuple[Decimal, dict[UUID, Decimal]]:
        """Return what one order may ship where holds exceed the stock.

        An order holds its whole quantity, and the part no stock covers is a
        back order sitting on the stock row as a hold like any other. Read
        as a plain sum, that hold stopped the goods that *were* there from
        leaving: four held and one order for ten could not ship the four, and
        an order for three could not ship beside a later one for four, with
        four on the shelf (D-STK-39).

        A hold with no stock behind it stops nobody. On a row holding less
        than is reserved on it, the holds are read in the order they were
        made: the stock stands behind the earliest first, and what is left
        over when it runs out is the back order. This order may draw what
        the row holds less what stands behind the holds made *before* its
        own, and less what still stands behind later ones once its own hold
        is counted. Its own hold never stands in its own way.

        A row that covers its holds is unchanged: what is available on it
        plus this order's own hold there.

        Returns:
            What the order may ship from this place in all, and for each row
            that holds less than is reserved on it, what may be drawn from
            it, by row id -- ``allocate_for_dispatch`` takes that.

        """
        rows = list(
            self._session.scalars(
                select(InventoryRecord).where(
                    InventoryRecord.firm_id == firm_scope,
                    InventoryRecord.branch_id == branch_id,
                    InventoryRecord.warehouse_id == warehouse_id,
                    InventoryRecord.storage_node_id == storage_node_id,
                    InventoryRecord.product_id == product_id,
                    InventoryRecord.is_deleted.is_(False),
                )
            ).all()
        )
        over = {row.id for row in rows if Decimal(str(row.available_quantity)) < ZERO}
        if not over:
            # Nothing here is short of its holds: the plain sum stands.
            return ZERO, {}
        holds: dict[UUID, list[tuple[str | None, Decimal, Any]]] = {}
        if rows:
            for row_id, reference, total, first in self._session.execute(
                select(
                    InventoryTransaction.inventory_id,
                    InventoryTransaction.reference_number,
                    func.coalesce(
                        func.sum(InventoryTransaction.reserved_quantity_delta), 0
                    ),
                    func.min(InventoryTransaction.created_at),
                )
                .where(
                    InventoryTransaction.firm_id == firm_scope,
                    InventoryTransaction.inventory_id.in_([row.id for row in rows]),
                    InventoryTransaction.reserved_quantity_delta != 0,
                    InventoryTransaction.is_deleted.is_(False),
                    # Every hold on a row short of its holds, and this
                    # order's own on the rest.
                    or_(
                        InventoryTransaction.inventory_id.in_(over),
                        InventoryTransaction.reference_number == reference_number,
                    ),
                )
                .group_by(
                    InventoryTransaction.inventory_id,
                    InventoryTransaction.reference_number,
                )
            ).all():
                quantity = Decimal(str(total))
                if quantity > ZERO:
                    holds.setdefault(row_id, []).append((reference, quantity, first))
        shippable = ZERO
        past: dict[UUID, Decimal] = {}
        for row in rows:
            held = holds.get(row.id, [])
            own = sum((qty for ref, qty, _ in held if ref == reference_number), ZERO)
            if row.id not in over:
                shippable += max(Decimal(str(row.available_quantity)) + own, ZERO)
                continue
            stock = max(
                Decimal(str(row.current_quantity)) - Decimal(str(row.blocked_quantity)),
                ZERO,
            )
            mine = next(
                (first for ref, _, first in held if ref == reference_number), None
            )
            # A hold the ledger cannot name, and every hold where this order
            # has none, comes before it: nothing is looked past on a guess.
            earlier = max(
                Decimal(str(row.reserved_quantity))
                - sum((qty for _, qty, _ in held), ZERO),
                ZERO,
            )
            later = ZERO
            for ref, qty, first in held:
                if ref == reference_number:
                    continue
                before = (
                    mine is None
                    or ref is None
                    or (first, ref) < (mine, reference_number)
                )
                if before:
                    earlier += qty
                else:
                    later += qty
            behind_later = min(max(stock - earlier - own, ZERO), later)
            drawable = max(stock - min(stock, earlier) - behind_later, ZERO)
            past[row.id] = drawable
            shippable += drawable
        return shippable, past

    def _expiry_ranked_rows(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        column: InstrumentedAttribute[Decimal],
    ) -> list[InventoryRecord]:
        """Return this product's stock rows in the order its goods leave.

        The product's issue rule decides (STK-11): earliest expiry first by
        default, or first received first for FIFO. A PICK product ranks by
        expiry too -- a hold is not a choice of batch, and dispatch refuses
        to choose for it (``allocate_for_dispatch``). Reservation, release and
        dispatch all rank here, so the three agree on the same batch.

        Expiry is ranked explicitly rather than left to the backend's NULL
        ordering -- PostgreSQL sorts NULLs first in ASC and SQLite last, so a
        batch with no expiry date would be picked first on one and last on the
        other. A batch without an expiry is not urgent, so it goes last, and
        ties break on the batch id to keep two runs of the same allocation
        identical. Under FIFO the untracked row goes last for the same reason.
        """
        if self.issue_rule(product_id) == "FIFO":
            ranking: tuple[Any, ...] = (
                case((InventoryRecord.batch_id.is_(None), 1), else_=0).asc(),
                BatchRecord.created_at.asc(),
                InventoryRecord.batch_id.asc(),
            )
        else:
            ranking = (
                case((BatchRecord.expiry_date.is_(None), 1), else_=0).asc(),
                BatchRecord.expiry_date.asc(),
                InventoryRecord.batch_id.asc(),
            )
        return list(
            self._session.scalars(
                select(InventoryRecord)
                .outerjoin(BatchRecord, BatchRecord.id == InventoryRecord.batch_id)
                .where(
                    InventoryRecord.firm_id == firm_scope,
                    InventoryRecord.branch_id == branch_id,
                    InventoryRecord.warehouse_id == warehouse_id,
                    InventoryRecord.product_id == product_id,
                    InventoryRecord.is_deleted.is_(False),
                    column > ZERO,
                )
                .order_by(*ranking)
            ).all()
        )

    def issue_rule(self, product_id: UUID) -> str:
        """Return the product's issue rule: FEFO unless it names another."""
        rule = self._session.scalar(
            select(Product.issue_rule).where(Product.id == product_id)
        )
        return rule or "FEFO"

    def _expired_batches(
        self, batch_ids: set[UUID], *, as_of: date
    ) -> dict[UUID, tuple[str, date]]:
        """Return the batches among these that had expired by ``as_of``.

        Keyed by batch id, carrying the number and the date, because a refusal
        that cannot name the batch leaves whoever reads it looking for stock
        the screen says is there.

        **A batch is out of date on its expiry date**, the rule
        `BatchRecord.expired_condition` states and every place a person
        names a batch already applied: the picker, a pinned order, a batch
        picked on a note, a counter bill. This one read "before the date",
        so on that day the batch nobody would let you choose was the one
        first-expiry-first chose for you and shipped (D-STK-17).
        """
        return self._batches_dated_before(batch_ids, as_of + timedelta(days=1))

    def _batches_dated_before(
        self, batch_ids: set[UUID], day: date
    ) -> dict[UUID, tuple[str, date]]:
        """Return the batches among these whose expiry date is before ``day``.

        The one read behind "expired" (before the day after) and "too
        short-dated for this customer" (before the day the goods must still
        be good on), which are different questions about the same column.
        """
        if not batch_ids:
            return {}
        rows = self._session.scalars(
            select(BatchRecord).where(
                BatchRecord.id.in_(batch_ids),
                BatchRecord.expiry_date.is_not(None),
                BatchRecord.expiry_date < day,
            )
        ).all()
        return {
            row.id: (row.batch_number, row.expiry_date)
            for row in rows
            if row.expiry_date is not None
        }

    def allocate_for_dispatch(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        quantity: Decimal,
        as_of: date | None = None,
        keep_until: date | None = None,
        past_back_orders: Mapping[UUID, Decimal] | None = None,
    ) -> list[tuple[UUID | None, Decimal]]:
        """Choose which batches a dispatch consumes, earliest expiry first.

        ``past_back_orders`` is what the order shipping may draw from each
        row that holds less than is reserved on it, by row id
        (``shippable_past_back_orders``): a hold with no stock behind it
        leaves the row showing nothing available while the goods stand
        there, and this order's place among the holds says how much of them
        is its to take (D-STK-39). A row not named is drawn by what it has
        available, as before.

        ``keep_until`` is the date a customer's minimum shelf life asks the
        goods to last to (backlog 79 row 6): a batch expiring before it is
        passed over as an expired one is, and named if the rest fall short.

        A product held in one bay can now be several stock rows, one per batch,
        so a single document line may have to come out of more than one of
        them: sixty strips from the batch expiring in March and forty from
        June. This returns the split as (batch_id, quantity) pairs, and the
        caller stages one movement per pair.

        First expiry, first out -- **among batches that have not expired**.
        Read literally, "earliest expiry first" hands the customer the batch
        that went out of date last month, which is what it did until
        2026-09-16: a pharmacy firm holding a batch expired on the 17th of
        August and two in date shipped the expired one. Stock past its date is
        dropped from the candidates and the dispatch is refused **by name**
        rather than coming up short for no visible reason, because the screen
        still shows that stock as on hand. Judged on the document's own date
        (``as_of``), not on today: a note dated when the batch was still good
        must post the same way when the history is rebuilt a year later.

        Expiry is ranked explicitly rather than left to the backend's NULL
        ordering -- PostgreSQL sorts NULLs first in ASC and SQLite last, so a
        batch with no expiry date would be picked first on one and last on the
        other. A batch without an expiry is not urgent,
        so it goes last, and ties break on the batch id to keep two runs of the
        same dispatch identical.

        Untracked stock -- the row whose ``batch_id`` is NULL -- is returned as
        a single pair, so a product nobody tracks behaves exactly as it did.

        Returns:
            The batches to draw from, in the order to draw from them. Raises if
            the available stock across all of them is short.

        """
        return [
            (batch_id, taken)
            for _, batch_id, taken in self._draw_for_dispatch(
                firm_scope=firm_scope,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=quantity,
                as_of=as_of,
                keep_until=keep_until,
                past_back_orders=past_back_orders,
            )
        ]

    def allocate_across_bins(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        quantity: Decimal,
        as_of: date | None = None,
        keep_until: date | None = None,
        past_back_orders: Mapping[UUID, Decimal] | None = None,
    ) -> list[tuple[UUID | None, UUID | None, Decimal]]:
        """Choose the places and batches a line naming no bin leaves from.

        A line that names no bin asks the warehouse, and goods standing in a
        bin of it are in the warehouse: four in a bin and a note for four was
        refused for want of stock (D-STK-54). What stands on the warehouse's
        own row goes first -- that is where the order's hold is -- and then
        the bins, by the product's issue rule across them, so the earliest
        expiry leaves whichever bin it is in. The same refusals as
        ``allocate_for_dispatch``: expired, short-dated, pick-only.

        Returns:
            (storage node, batch, quantity) in the order to draw; the node is
            None for the warehouse's own row. Raises if all of it is short.

        """
        return self._draw_for_dispatch(
            firm_scope=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=quantity,
            as_of=as_of,
            keep_until=keep_until,
            past_back_orders=past_back_orders,
            warehouse_row_first=True,
        )

    def free_in_bins(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
    ) -> list[tuple[str, Decimal]]:
        """Return what each bin of a warehouse holds free of a product.

        By bin code, with the quantity no hold or block stands on, summed
        over its batches. The warehouse's own row is not a bin and is left
        out. For the dispatch gate, and for a refusal that says where the
        goods stand rather than that there are none.
        """
        rows = self._session.execute(
            select(
                WarehouseStorageNode.code,
                func.sum(InventoryRecord.available_quantity),
            )
            .join(
                WarehouseStorageNode,
                WarehouseStorageNode.id == InventoryRecord.storage_node_id,
            )
            .where(
                InventoryRecord.firm_id == firm_scope,
                InventoryRecord.branch_id == branch_id,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.product_id == product_id,
                InventoryRecord.is_deleted.is_(False),
                InventoryRecord.available_quantity > ZERO,
            )
            .group_by(WarehouseStorageNode.code)
            .order_by(WarehouseStorageNode.code.asc())
        ).all()
        return [(code, Decimal(str(free))) for code, free in rows]

    def _draw_for_dispatch(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        quantity: Decimal,
        as_of: date | None,
        keep_until: date | None,
        past_back_orders: Mapping[UUID, Decimal] | None,
        warehouse_row_first: bool = False,
    ) -> list[tuple[UUID | None, UUID | None, Decimal]]:
        """Draw a dispatch from a product's stock rows, naming each row's place.

        The one body behind ``allocate_for_dispatch`` and
        ``allocate_across_bins``. ``warehouse_row_first`` puts the rows that
        stand in no bin ahead of the rest, each group keeping the order its
        goods leave in.
        """
        rows = self._expiry_ranked_rows(
            firm_scope=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            column=(
                InventoryRecord.current_quantity
                if past_back_orders
                else InventoryRecord.available_quantity
            ),
        )
        if warehouse_row_first:
            # A stable sort: the ranking above holds within each group.
            rows.sort(key=lambda row: row.storage_node_id is not None)
        drawable = {
            row.id: max(
                Decimal(str(row.available_quantity)),
                min(
                    (past_back_orders or {}).get(row.id, ZERO),
                    Decimal(str(row.current_quantity))
                    - Decimal(str(row.blocked_quantity)),
                ),
            )
            for row in rows
        }
        rows = [row for row in rows if drawable[row.id] > ZERO]
        # `require_batch_on_issue` is the product saying its goods cannot leave
        # unidentified. Untracked stock -- the row whose batch is NULL -- is
        # exactly what that forbids, so it is dropped from the candidates and
        # the dispatch is short rather than silently shipping stock nobody can
        # trace.
        product = self._session.get(Product, product_id)
        if product is not None and product.require_batch_on_issue:
            rows = [row for row in rows if row.batch_id is not None]
        # A product whose batch a person chooses is never drawn silently
        # (STK-11): where it is held in batches, the line has to name them.
        if (
            product is not None
            and product.issue_rule == "PICK"
            and any(row.batch_id is not None for row in rows)
        ):
            raise ValidationError(
                f"{product.code} ({product.name}) is issued by choosing the "
                "batch: pick the batches on the line before dispatching it."
            )
        rows, expired, held_expired = self._without_expired(
            rows, firm_scope=firm_scope, as_of=as_of
        )
        # The product's own stop-selling window (STK-5) is a date its goods
        # must outlast, like a customer's minimum shelf life.
        rows, short = self._without_short_dated(
            rows,
            firm_scope=firm_scope,
            product_id=product_id,
            as_of=as_of,
            keep_until=keep_until,
        )
        outstanding = Decimal(str(quantity))
        allocation: list[tuple[UUID | None, UUID | None, Decimal]] = []
        for row in rows:
            if outstanding <= ZERO:
                break
            take = min(outstanding, drawable[row.id])
            if take <= ZERO:
                continue
            allocation.append((row.storage_node_id, row.batch_id, take))
            outstanding -= take
        if outstanding > ZERO:
            raise ValidationError(
                "Insufficient available stock to dispatch: short by "
                f"{outstanding}."
                + (
                    " This product may only be issued from a batch."
                    if product is not None and product.require_batch_on_issue
                    else ""
                )
                + self._expired_note(expired, held_expired, verb="dispatched")
                + self._short_dated_note(short)
            )
        return allocation

    def _without_expired(
        self, rows: list[InventoryRecord], *, firm_scope: UUID, as_of: date | None
    ) -> tuple[list[InventoryRecord], dict[UUID, tuple[str, date]], Decimal]:
        """Drop the rows whose batch had expired by ``as_of``.

        One step for reservation and dispatch alike, because the two drifted
        apart the moment it lived in only one of them: dispatch stopped drawing
        expired stock and reservation went on holding it (D-STK-2). Judged on
        the document's own date rather than today, so a history rebuilt a year
        later posts what it posted at the time.

        Returns:
            The rows still in date, the expired batches by id (number and
            expiry date, for naming them), and how much available stock those
            expired rows were holding.

        """
        expired = self._expired_batches(
            {row.batch_id for row in rows if row.batch_id is not None},
            as_of=as_of or firm_today(self._session, firm_scope),
        )
        held_expired = sum(
            (
                Decimal(str(row.available_quantity))
                for row in rows
                if row.batch_id in expired
            ),
            ZERO,
        )
        return (
            [row for row in rows if row.batch_id not in expired],
            expired,
            held_expired,
        )

    @staticmethod
    def _expired_note(
        expired: dict[UUID, tuple[str, date]], held: Decimal, *, verb: str
    ) -> str:
        """Say how much of the shortfall is stock that has gone out of date.

        Without this the refusal reads "short by 5" beside a screen showing
        fifteen on hand, and the difference is invisible. ``verb`` is what the
        stock could not be -- "dispatched" or "reserved" -- so the same note
        reads right on a refused note and on a back-ordered hold.
        """
        if not expired or held <= ZERO:
            return ""
        names = ", ".join(
            f"{number} expired {on.isoformat()}"
            for number, on in sorted(expired.values(), key=lambda item: item[1])
        )
        return (
            f" {held} of this product's stock is past its expiry date "
            f"({names}) and cannot be {verb}: write it off or quarantine "
            "it."
        )

    def record_delivery_note_dispatch(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        reference_number: str,
        transaction_date: date,
        dispatch_quantity: Decimal,
        entered_quantity: Decimal | None = None,
        entered_uom_id: UUID | None = None,
        conversion_version: int | None = None,
        line_conversion: LineConversion | None = None,
        remarks: str | None = None,
        batch_id: UUID | None = None,
        serial_id: UUID | None = None,
        share_of_line: bool = False,
    ) -> InventoryTransaction:
        """Post the stock a delivery note dispatched, from one batch.

        Callers holding a line that spans batches call
        ``allocate_for_dispatch`` first and then this once per allocated batch.

        ``share_of_line`` says the entered quantity is one batch's share of a
        line split across batches, not a figure anybody typed: a box of
        twelve drawn ten from one batch and two from the next is 0.8333 and
        0.1667 of a box. The whole-number rule of the unit is the line's to
        pass, not each share's, and the stock that moves is the allocation
        itself -- ten pieces, not 0.8333 of twelve (D-PRC-38).
        """
        (
            base_quantity,
            entered_quantity,
            entered_uom_id,
            conversion_version,
        ) = self._resolve_base_quantity(
            firm_scope=firm_scope,
            product_id=product_id,
            quantity=(
                entered_quantity if entered_quantity is not None else dispatch_quantity
            ),
            entered_uom_id=entered_uom_id,
            conversion_version=conversion_version,
            line_conversion=line_conversion,
            on_date=transaction_date,
            enforce_whole_units=not share_of_line,
        )
        if share_of_line:
            base_quantity = Decimal(str(dispatch_quantity))
        inventory = self._ensure_inventory_projection(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        transaction = self._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type=InventoryTransactionType.DISPATCH.value,
                batch_id=batch_id,
                serial_id=serial_id,
                reference_number=reference_number.strip().upper(),
                reference_type="DELIVERY_NOTE",
                transaction_date=transaction_date,
                quantity=base_quantity,
                current_delta=-base_quantity,
                entered_quantity=entered_quantity,
                entered_uom_id=entered_uom_id,
                conversion_version=conversion_version,
                remarks=remarks or "delivery_note dispatch",
            ),
        )
        self._session.flush()
        return transaction

    def available_at(
        self,
        *,
        firm_scope: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        batch_id: UUID | None,
    ) -> Decimal:
        """Return what one stock row can still give: on hand less held and blocked.

        For a caller that names the batch itself rather than asking
        ``allocate_for_dispatch`` to choose, and so has to make the allocator's
        refusal for itself (D-SELL-50). A place holding no row holds nothing.
        """
        row = self._find_inventory_row(
            firm_id=firm_scope,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_locator=self._storage_locator(storage_node_id),
            product_id=product_id,
            batch_id=batch_id,
        )
        return ZERO if row is None else Decimal(str(row.available_quantity))

    def _every_inventory_row(
        self, *, firm_scope: UUID, search: str | None
    ) -> list[InventoryRecord]:
        """Return every stock row an export covers, however many there are.

        An export read one page of 5,000 and stopped without saying so
        (inventory round 1, F12); a file that is quietly short is worse than
        none. Read page after page, in the list's own stable order.
        """
        rows: list[InventoryRecord] = []
        page = 1
        while True:
            chunk, total = self.list_inventory(
                firm_scope=firm_scope,
                filters=InventoryListFilters(include_deleted=False),
                page=page,
                page_size=EXPORT_PAGE_SIZE,
                search=search,
                sort_by="product_code",
                descending=False,
            )
            rows.extend(chunk)
            if not chunk or len(rows) >= total:
                return rows
            page += 1

    def _every_ledger_row(
        self, *, firm_scope: UUID, search: str | None
    ) -> list[StockLedgerEntry]:
        """Return every ledger row an export covers, page after page."""
        rows: list[StockLedgerEntry] = []
        page = 1
        while True:
            chunk, total = self.list_ledger(
                firm_scope=firm_scope,
                filters=StockLedgerListFilters(),
                page=page,
                page_size=EXPORT_PAGE_SIZE,
                search=search,
                sort_by="transaction_date",
                descending=False,
            )
            rows.extend(chunk)
            if not chunk or len(rows) >= total:
                return rows
            page += 1

    def export_inventory_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        """Render the filtered projections as CSV."""
        rows = self._every_inventory_row(firm_scope=firm_scope, search=search)
        output = [
            "ProductCode,ProductName,BranchCode,WarehouseCode,StorageNodeCode,Current,Available,Reserved,Blocked,Damaged,Quarantine,InTransit,ReorderLevel,Status"
        ]
        # One response per row, built for the whole export at once -- it used
        # to be rebuilt for every column, eleven look-ups each time.
        for item, response in zip(rows, self.inventory_responses(rows), strict=True):
            output.append(
                ",".join(
                    [
                        self._csv(response, "product_code"),
                        self._csv(response, "product_name"),
                        self._csv(response, "branch_code"),
                        self._csv(response, "warehouse_code"),
                        self._csv(response, "storage_node_code"),
                        str(item.current_quantity),
                        str(item.available_quantity),
                        str(item.reserved_quantity),
                        str(item.blocked_quantity),
                        str(item.damaged_quantity),
                        str(item.quarantine_quantity),
                        str(item.in_transit_quantity),
                        str(item.reorder_level or ""),
                        item.status,
                    ]
                )
            )
        return "\n".join(output)

    def export_inventory_xlsx(self, *, firm_scope: UUID, search: str | None) -> bytes:
        """Render the filtered projections as XLSX."""
        try:
            from openpyxl import Workbook
        except ImportError as error:
            raise ValidationError(
                "XLSX export dependency is unavailable. Install openpyxl."
            ) from error
        rows = self._every_inventory_row(firm_scope=firm_scope, search=search)
        labels = self.labels_for(rows)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Inventory"
        sheet.append(
            [
                "ProductCode",
                "ProductName",
                "BranchCode",
                "WarehouseCode",
                "StorageNodeCode",
                "Current",
                "Available",
                "Reserved",
                "Blocked",
                "Damaged",
                "Quarantine",
                "InTransit",
                "ReorderLevel",
                "Status",
            ]
        )
        for item in rows:
            sheet.append(
                [
                    sheet_text(labels.product_code(item.product_id)),
                    sheet_text(labels.product_name(item.product_id)),
                    sheet_text(labels.branch_code(item.branch_id)),
                    sheet_text(labels.warehouse_code(item.warehouse_id)),
                    sheet_text(labels.storage_code(item.storage_node_id)),
                    item.current_quantity,
                    item.available_quantity,
                    item.reserved_quantity,
                    item.blocked_quantity,
                    item.damaged_quantity,
                    item.quarantine_quantity,
                    item.in_transit_quantity,
                    item.reorder_level or 0,
                    item.status,
                ]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def export_ledger_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        """Render the filtered ledger rows as CSV."""
        rows = self._every_ledger_row(firm_scope=firm_scope, search=search)
        labels = self.labels_for(rows)
        output = [
            "TransactionDate,TransactionType,ReferenceNumber,ProductCode,WarehouseCode,Quantity,CurrentDelta,ReservedDelta,BlockedDelta,DamagedDelta,QuarantineDelta,InTransitDelta,NewCurrent,NewAvailable"
        ]
        for item in rows:
            output.append(
                ",".join(
                    [
                        item.transaction_date.isoformat(),
                        item.transaction_type,
                        csv_text(item.reference_number),
                        csv_text(labels.product_code(item.product_id)),
                        csv_text(labels.warehouse_code(item.warehouse_id)),
                        str(item.quantity),
                        str(item.current_quantity_delta),
                        str(item.reserved_quantity_delta),
                        str(item.blocked_quantity_delta),
                        str(item.damaged_quantity_delta),
                        str(item.quarantine_quantity_delta),
                        str(item.in_transit_quantity_delta),
                        str(item.new_current_quantity),
                        str(item.new_available_quantity),
                    ]
                )
            )
        return "\n".join(output)

    def export_ledger_xlsx(self, *, firm_scope: UUID, search: str | None) -> bytes:
        """Render the filtered ledger rows as XLSX."""
        try:
            from openpyxl import Workbook
        except ImportError as error:
            raise ValidationError(
                "XLSX export dependency is unavailable. Install openpyxl."
            ) from error
        rows = self._every_ledger_row(firm_scope=firm_scope, search=search)
        labels = self.labels_for(rows)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "StockLedger"
        sheet.append(
            [
                "TransactionDate",
                "TransactionType",
                "ReferenceNumber",
                "ProductCode",
                "WarehouseCode",
                "Quantity",
                "CurrentDelta",
                "ReservedDelta",
                "BlockedDelta",
                "DamagedDelta",
                "QuarantineDelta",
                "InTransitDelta",
                "NewCurrent",
                "NewAvailable",
            ]
        )
        for item in rows:
            sheet.append(
                [
                    item.transaction_date.isoformat(),
                    item.transaction_type,
                    sheet_text(item.reference_number),
                    sheet_text(labels.product_code(item.product_id)),
                    sheet_text(labels.warehouse_code(item.warehouse_id)),
                    item.quantity,
                    item.current_quantity_delta,
                    item.reserved_quantity_delta,
                    item.blocked_quantity_delta,
                    item.damaged_quantity_delta,
                    item.quarantine_quantity_delta,
                    item.in_transit_quantity_delta,
                    item.new_current_quantity,
                    item.new_available_quantity,
                ]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def labels_for(
        self, rows: Sequence[InventoryRecord | InventoryTransaction | StockLedgerEntry]
    ) -> _Labels:
        """Read every code and name a page of stock rows shows, once per table."""
        return _Labels(
            branches=_pairs(
                self._session,
                Branch.id,
                (Branch.code, Branch.name),
                (row.branch_id for row in rows),
            ),
            warehouses=_pairs(
                self._session,
                Warehouse.id,
                (Warehouse.code, Warehouse.name),
                (row.warehouse_id for row in rows),
            ),
            storage=_pairs(
                self._session,
                WarehouseStorageNode.id,
                (WarehouseStorageNode.code, WarehouseStorageNode.name),
                (row.storage_node_id for row in rows),
            ),
            products=_pairs(
                self._session,
                Product.id,
                (Product.code, Product.name),
                (row.product_id for row in rows),
            ),
            batches=_pairs(
                self._session,
                BatchRecord.id,
                (BatchRecord.batch_number, BatchRecord.expiry_date),
                (row.batch_id for row in rows),
            ),
            profiles=_pairs(
                self._session,
                BusinessProfile.id,
                (BusinessProfile.code,),
                (row.business_profile_id for row in rows),
            ),
        )

    def inventory_response(self, row: InventoryRecord) -> InventoryResponse:
        """Expose one stock projection."""
        return self.inventory_responses([row])[0]

    def inventory_responses(
        self, rows: Sequence[InventoryRecord]
    ) -> list[InventoryResponse]:
        """Expose a page of stock projections, naming them once per table.

        About eleven look-ups per row became six reads per page (backlog 56 C,
        step 3). The single-row builder is this with a list of one.
        """
        if not rows:
            return []
        labels = self.labels_for(rows)
        return [self._inventory_response(row, labels) for row in rows]

    def _inventory_response(
        self, row: InventoryRecord, labels: _Labels
    ) -> InventoryResponse:
        """Build one projection's response from a page's labels."""
        batch_number, batch_expiry = labels.batch(row.batch_id)
        return InventoryResponse.model_validate(
            {
                "batch_id": row.batch_id,
                "batch_number": batch_number,
                "batch_expiry_date": batch_expiry,
                "id": row.id,
                "version": row.version,
                "firm_id": row.firm_id,
                "branch_id": row.branch_id,
                "branch_code": labels.branch_code(row.branch_id),
                "branch_name": labels.branch_name(row.branch_id),
                "warehouse_id": row.warehouse_id,
                "warehouse_code": labels.warehouse_code(row.warehouse_id),
                "warehouse_name": labels.warehouse_name(row.warehouse_id),
                "storage_node_id": row.storage_node_id,
                "storage_node_code": labels.storage_code(row.storage_node_id),
                "storage_node_name": labels.storage_name(row.storage_node_id),
                "product_id": row.product_id,
                "product_code": labels.product_code(row.product_id),
                "product_name": labels.product_name(row.product_id),
                "business_profile_id": row.business_profile_id,
                "business_profile_code": labels.profile_code(row.business_profile_id),
                "current_quantity": row.current_quantity,
                "reserved_quantity": row.reserved_quantity,
                "available_quantity": row.available_quantity,
                "blocked_quantity": row.blocked_quantity,
                "damaged_quantity": row.damaged_quantity,
                "quarantine_quantity": row.quarantine_quantity,
                "in_transit_quantity": row.in_transit_quantity,
                "display_quantity": row.display_quantity,
                "display_uom_id": row.display_uom_id,
                "minimum_level": row.minimum_level,
                "maximum_level": row.maximum_level,
                "reorder_level": row.reorder_level,
                "safety_stock": row.safety_stock,
                "last_transaction_at": row.last_transaction_at,
                "status": row.status,
                "is_deleted": row.is_deleted,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    def transaction_response(
        self, row: InventoryTransaction
    ) -> InventoryTransactionResponse:
        """Expose one inventory movement."""
        return self.transaction_responses([row])[0]

    def transaction_responses(
        self, rows: Sequence[InventoryTransaction]
    ) -> list[InventoryTransactionResponse]:
        """Expose a page of inventory movements, naming them once per table."""
        if not rows:
            return []
        labels = self.labels_for(rows)
        responses: list[InventoryTransactionResponse] = []
        for row in rows:
            payload = self._movement_payload(row, labels)
            payload["entered_quantity"] = row.entered_quantity
            payload["entered_uom_id"] = row.entered_uom_id
            payload["conversion_version"] = row.conversion_version
            responses.append(InventoryTransactionResponse.model_validate(payload))
        return responses

    def _movement_payload(
        self, row: InventoryTransaction | StockLedgerEntry, labels: _Labels
    ) -> dict[str, object]:
        """Build the fields a transaction and its ledger row have in common.

        The ledger row is not an ``InventoryTransaction``: it records the
        as-entered quantity under ``original_quantity``/``original_uom_id`` and
        has no ``conversion_version``. Reusing the transaction builder for it
        raised AttributeError, so ``GET /inventory/ledger`` failed for every
        firm that had ever moved stock.
        """
        return {
            "id": row.id,
            "inventory_id": row.inventory_id,
            "firm_id": row.firm_id,
            "branch_id": row.branch_id,
            "branch_code": labels.branch_code(row.branch_id),
            "branch_name": labels.branch_name(row.branch_id),
            "warehouse_id": row.warehouse_id,
            "warehouse_code": labels.warehouse_code(row.warehouse_id),
            "warehouse_name": labels.warehouse_name(row.warehouse_id),
            "storage_node_id": row.storage_node_id,
            "storage_node_code": labels.storage_code(row.storage_node_id),
            "storage_node_name": labels.storage_name(row.storage_node_id),
            "product_id": row.product_id,
            "product_code": labels.product_code(row.product_id),
            "product_name": labels.product_name(row.product_id),
            "batch_id": row.batch_id,
            "batch_number": labels.batch(row.batch_id)[0],
            "business_profile_id": row.business_profile_id,
            "transaction_type": row.transaction_type,
            "reference_number": row.reference_number,
            "reference_type": row.reference_type,
            "transaction_date": row.transaction_date,
            "quantity": row.quantity,
            "current_quantity_delta": row.current_quantity_delta,
            "reserved_quantity_delta": row.reserved_quantity_delta,
            "blocked_quantity_delta": row.blocked_quantity_delta,
            "damaged_quantity_delta": row.damaged_quantity_delta,
            "quarantine_quantity_delta": row.quarantine_quantity_delta,
            "in_transit_quantity_delta": row.in_transit_quantity_delta,
            "previous_current_quantity": row.previous_current_quantity,
            "new_current_quantity": row.new_current_quantity,
            "previous_reserved_quantity": row.previous_reserved_quantity,
            "new_reserved_quantity": row.new_reserved_quantity,
            "previous_available_quantity": row.previous_available_quantity,
            "new_available_quantity": row.new_available_quantity,
            "previous_blocked_quantity": row.previous_blocked_quantity,
            "new_blocked_quantity": row.new_blocked_quantity,
            "previous_damaged_quantity": row.previous_damaged_quantity,
            "new_damaged_quantity": row.new_damaged_quantity,
            "previous_quarantine_quantity": row.previous_quarantine_quantity,
            "new_quarantine_quantity": row.new_quarantine_quantity,
            "previous_in_transit_quantity": row.previous_in_transit_quantity,
            "new_in_transit_quantity": row.new_in_transit_quantity,
            "remarks": row.remarks,
            "created_at": row.created_at,
        }

    def ledger_response(self, row: StockLedgerEntry) -> StockLedgerResponse:
        """Expose one immutable ledger row."""
        return self.ledger_responses([row])[0]

    def ledger_responses(
        self, rows: Sequence[StockLedgerEntry]
    ) -> list[StockLedgerResponse]:
        """Expose a page of ledger rows, naming them once per table."""
        if not rows:
            return []
        labels = self.labels_for(rows)
        responses: list[StockLedgerResponse] = []
        for row in rows:
            payload = self._movement_payload(row, labels)
            payload["transaction_id"] = row.transaction_id
            payload["entered_quantity"] = row.original_quantity
            payload["entered_uom_id"] = row.original_uom_id
            responses.append(StockLedgerResponse.model_validate(payload))
        return responses

    def opening_stock_batch_response(
        self, row: OpeningStockBatch
    ) -> OpeningStockBatchResponse:
        """Expose one opening-stock batch."""
        return self.opening_stock_batch_responses([row])[0]

    def opening_stock_batch_responses(
        self, rows: Sequence[OpeningStockBatch]
    ) -> list[OpeningStockBatchResponse]:
        """Expose a page of opening-stock batches, naming them once per table.

        A batch carries every line of a firm's opening count, so four look-ups
        per line made three batches of fifteen thousand lines take 54 s on the
        volume firm (backlog 56 C, step 4). The single-batch builder is this
        with a list of one.
        """
        if not rows:
            return []
        lines = [line for row in rows for line in row.lines if not line.is_deleted]
        labels = _Labels(
            branches=_pairs(
                self._session,
                Branch.id,
                (Branch.code, Branch.name),
                (row.branch_id for row in rows),
            ),
            warehouses=_pairs(
                self._session,
                Warehouse.id,
                (Warehouse.code, Warehouse.name),
                (row.warehouse_id for row in rows),
            ),
            storage=_pairs(
                self._session,
                WarehouseStorageNode.id,
                (WarehouseStorageNode.code, WarehouseStorageNode.name),
                (line.storage_node_id for line in lines),
            ),
            products=_pairs(
                self._session,
                Product.id,
                (Product.code, Product.name),
                (line.product_id for line in lines),
            ),
            batches={},
            profiles={},
        )
        serials = self._opening_serials()
        typed = _TypedSerials(
            by_line=serials.typed(line.id for line in lines),
            tracked=serials.tracked(line.product_id for line in lines),
        )
        return [self._opening_stock_batch_response(row, labels, typed) for row in rows]

    def _opening_stock_batch_response(
        self, row: OpeningStockBatch, labels: _Labels, typed: _TypedSerials
    ) -> OpeningStockBatchResponse:
        """Build one opening-stock batch's response from a page's labels."""
        return OpeningStockBatchResponse.model_validate(
            {
                "id": row.id,
                "version": row.version,
                "firm_id": row.firm_id,
                "branch_id": row.branch_id,
                "branch_code": labels.branch_code(row.branch_id),
                "branch_name": labels.branch_name(row.branch_id),
                "warehouse_id": row.warehouse_id,
                "warehouse_code": labels.warehouse_code(row.warehouse_id),
                "warehouse_name": labels.warehouse_name(row.warehouse_id),
                "reference_number": row.reference_number,
                "posting_date": row.posting_date,
                "source_format": row.source_format,
                "status": row.status,
                "remarks": row.remarks,
                "posted_at": row.posted_at,
                "lines": [
                    self._opening_stock_line_response(line, labels, typed)
                    for line in row.lines
                    if not line.is_deleted
                ],
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    def _opening_stock_line_response(
        self, row: OpeningStockLine, labels: _Labels, typed: _TypedSerials
    ) -> OpeningStockLineResponse:
        return OpeningStockLineResponse.model_validate(
            {
                "id": row.id,
                "line_number": row.line_number,
                "product_id": row.product_id,
                "product_code": labels.product_code(row.product_id),
                "product_name": labels.product_name(row.product_id),
                "storage_node_id": row.storage_node_id,
                "storage_node_code": labels.storage_code(row.storage_node_id),
                "storage_node_name": labels.storage_name(row.storage_node_id),
                "business_profile_id": row.business_profile_id,
                "quantity": row.quantity,
                "unit_cost": row.unit_cost,
                "entered_quantity": row.entered_quantity,
                "entered_uom_id": row.entered_uom_id,
                "conversion_version": row.conversion_version,
                "batch_number": row.batch_number,
                "batch_id": row.batch_id,
                "expiry_date": row.expiry_date,
                "minimum_level": row.minimum_level,
                "maximum_level": row.maximum_level,
                "reorder_level": row.reorder_level,
                "safety_stock": row.safety_stock,
                "remarks": row.remarks,
                "transaction_id": row.transaction_id,
                "serial_tracked": row.product_id in typed.tracked,
                "serial_numbers": list(typed.by_line.get(row.id, [])),
            }
        )

    def _apply_inventory_filters(
        self,
        statement: Select[Any],
        count: Select[Any],
        filters: InventoryListFilters,
    ) -> tuple[Select[Any], Select[Any]]:
        if not filters.include_deleted:
            statement = statement.where(InventoryRecord.is_deleted.is_(False))
            count = count.where(InventoryRecord.is_deleted.is_(False))
        if filters.status is not None:
            statement = statement.where(InventoryRecord.status == filters.status.value)
            count = count.where(InventoryRecord.status == filters.status.value)
        for field, value in {
            InventoryRecord.branch_id: filters.branch_id,
            InventoryRecord.warehouse_id: filters.warehouse_id,
            InventoryRecord.storage_node_id: filters.storage_node_id,
            InventoryRecord.product_id: filters.product_id,
            InventoryRecord.business_profile_id: filters.business_profile_id,
        }.items():
            if value is not None:
                statement = statement.where(field == value)
                count = count.where(field == value)
        if filters.low_stock_only:
            condition = InventoryRecord.current_quantity <= func.coalesce(
                InventoryRecord.reorder_level, InventoryRecord.minimum_level, ZERO
            )
            statement = statement.where(condition)
            count = count.where(condition)
        if filters.out_of_stock_only:
            statement = statement.where(InventoryRecord.current_quantity <= 0)
            count = count.where(InventoryRecord.current_quantity <= 0)
        if filters.negative_only:
            condition = or_(
                InventoryRecord.current_quantity < 0,
                InventoryRecord.available_quantity < 0,
            )
            statement = statement.where(condition)
            count = count.where(condition)
        return statement, count

    def _apply_transaction_filters(
        self,
        statement: Select[Any],
        count: Select[Any],
        filters: InventoryTransactionListFilters,
    ) -> tuple[Select[Any], Select[Any]]:
        if filters.transaction_type is not None:
            statement = statement.where(
                InventoryTransaction.transaction_type == filters.transaction_type
            )
            count = count.where(
                InventoryTransaction.transaction_type == filters.transaction_type
            )
        for field, value in {
            InventoryTransaction.branch_id: filters.branch_id,
            InventoryTransaction.warehouse_id: filters.warehouse_id,
            InventoryTransaction.storage_node_id: filters.storage_node_id,
            InventoryTransaction.product_id: filters.product_id,
        }.items():
            if value is not None:
                statement = statement.where(field == value)
                count = count.where(field == value)
        if filters.reference_number:
            statement = statement.where(
                InventoryTransaction.reference_number.ilike(
                    f"%{filters.reference_number.strip()}%"
                )
            )
            count = count.where(
                InventoryTransaction.reference_number.ilike(
                    f"%{filters.reference_number.strip()}%"
                )
            )
        if filters.reference_type:
            statement = statement.where(
                InventoryTransaction.reference_type
                == filters.reference_type.strip().upper()
            )
            count = count.where(
                InventoryTransaction.reference_type
                == filters.reference_type.strip().upper()
            )
        if filters.transaction_from is not None:
            statement = statement.where(
                InventoryTransaction.transaction_date >= filters.transaction_from
            )
            count = count.where(
                InventoryTransaction.transaction_date >= filters.transaction_from
            )
        if filters.transaction_to is not None:
            statement = statement.where(
                InventoryTransaction.transaction_date <= filters.transaction_to
            )
            count = count.where(
                InventoryTransaction.transaction_date <= filters.transaction_to
            )
        return statement, count

    def _apply_ledger_filters(
        self,
        statement: Select[Any],
        count: Select[Any],
        filters: StockLedgerListFilters,
    ) -> tuple[Select[Any], Select[Any]]:
        if filters.transaction_type is not None:
            statement = statement.where(
                StockLedgerEntry.transaction_type == filters.transaction_type
            )
            count = count.where(
                StockLedgerEntry.transaction_type == filters.transaction_type
            )
        for field, value in {
            StockLedgerEntry.branch_id: filters.branch_id,
            StockLedgerEntry.warehouse_id: filters.warehouse_id,
            StockLedgerEntry.storage_node_id: filters.storage_node_id,
            StockLedgerEntry.product_id: filters.product_id,
        }.items():
            if value is not None:
                statement = statement.where(field == value)
                count = count.where(field == value)
        if filters.reference_number:
            statement = statement.where(
                StockLedgerEntry.reference_number.ilike(
                    f"%{filters.reference_number.strip()}%"
                )
            )
            count = count.where(
                StockLedgerEntry.reference_number.ilike(
                    f"%{filters.reference_number.strip()}%"
                )
            )
        if filters.reference_type:
            statement = statement.where(
                StockLedgerEntry.reference_type
                == filters.reference_type.strip().upper()
            )
            count = count.where(
                StockLedgerEntry.reference_type
                == filters.reference_type.strip().upper()
            )
        if filters.transaction_from is not None:
            statement = statement.where(
                StockLedgerEntry.transaction_date >= filters.transaction_from
            )
            count = count.where(
                StockLedgerEntry.transaction_date >= filters.transaction_from
            )
        if filters.transaction_to is not None:
            statement = statement.where(
                StockLedgerEntry.transaction_date <= filters.transaction_to
            )
            count = count.where(
                StockLedgerEntry.transaction_date <= filters.transaction_to
            )
        return statement, count

    def _apply_opening_stock_filters(
        self,
        statement: Select[Any],
        count: Select[Any],
        filters: OpeningStockBatchListFilters,
    ) -> tuple[Select[Any], Select[Any]]:
        if not filters.include_deleted:
            statement = statement.where(OpeningStockBatch.is_deleted.is_(False))
            count = count.where(OpeningStockBatch.is_deleted.is_(False))
        if filters.status is not None:
            statement = statement.where(
                OpeningStockBatch.status == filters.status.value
            )
            count = count.where(OpeningStockBatch.status == filters.status.value)
        if filters.branch_id is not None:
            statement = statement.where(
                OpeningStockBatch.branch_id == filters.branch_id
            )
            count = count.where(OpeningStockBatch.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                OpeningStockBatch.warehouse_id == filters.warehouse_id
            )
            count = count.where(OpeningStockBatch.warehouse_id == filters.warehouse_id)
        if filters.posting_from is not None:
            statement = statement.where(
                OpeningStockBatch.posting_date >= filters.posting_from
            )
            count = count.where(OpeningStockBatch.posting_date >= filters.posting_from)
        if filters.posting_to is not None:
            statement = statement.where(
                OpeningStockBatch.posting_date <= filters.posting_to
            )
            count = count.where(OpeningStockBatch.posting_date <= filters.posting_to)
        return statement, count

    def _ensure_inventory_projection(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
        actor_id: UUID,
        batch_id: UUID | None = None,
    ) -> InventoryRecord:
        _, _, storage_node, _, profile_id = self._validate_references(
            firm_id=firm_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node_id,
            product_id=product_id,
        )
        if batch_id is not None:
            self._require_batch_of(batch_id, firm_id=firm_id, product_id=product_id)
        locator = self._storage_locator(storage_node.id if storage_node else None)
        row = self._find_inventory_row(
            firm_id=firm_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_locator=locator,
            product_id=product_id,
            batch_id=batch_id,
        )
        if row is not None:
            return row
        row = InventoryRecord(
            firm_id=firm_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=storage_node.id if storage_node else None,
            storage_locator=locator,
            product_id=product_id,
            batch_id=batch_id,
            business_profile_id=profile_id,
            current_quantity=ZERO,
            reserved_quantity=ZERO,
            available_quantity=ZERO,
            blocked_quantity=ZERO,
            damaged_quantity=ZERO,
            quarantine_quantity=ZERO,
            in_transit_quantity=ZERO,
            display_quantity=ZERO,
            display_uom_id=self._default_display_uom_id(product_id),
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _require_batch_of(
        self, batch_id: UUID, *, firm_id: UUID, product_id: UUID
    ) -> None:
        """Refuse a batch that is not this product's, in this firm.

        Every stock row a movement lands on is found or made here, so this is
        the one place a batch named on an adjustment, a write-off, a hold, a
        transfer or a count line is checked. None of them checked: an
        adjustment for one product naming another product's batch made a
        stock row for the first under the second's batch (D-STK-14, driven on
        2026-09-19 in fx_t09194k75_p).
        """
        batch = self._session.get(BatchRecord, batch_id)
        if (
            batch is None
            or batch.is_deleted
            or batch.firm_id != firm_id
            or batch.product_id != product_id
        ):
            raise ValidationError(
                "The batch named is not one of this product's batches in this firm."
            )

    def _stage_movement(
        self, inventory: InventoryRecord, *, actor_id: UUID, movement: _Movement
    ) -> InventoryTransaction:
        previous_current = inventory.current_quantity
        previous_reserved = inventory.reserved_quantity
        previous_blocked = inventory.blocked_quantity
        previous_damaged = inventory.damaged_quantity
        previous_quarantine = inventory.quarantine_quantity
        previous_in_transit = inventory.in_transit_quantity
        previous_available = inventory.available_quantity

        new_current = previous_current + movement.current_delta
        new_reserved = previous_reserved + movement.reserved_delta
        new_blocked = previous_blocked + movement.blocked_delta
        new_damaged = previous_damaged + movement.damaged_delta
        new_quarantine = previous_quarantine + movement.quarantine_delta
        new_in_transit = previous_in_transit + movement.in_transit_delta
        new_available = self._available_quantity(
            current_quantity=new_current,
            reserved_quantity=new_reserved,
            blocked_quantity=new_blocked,
        )

        self._validate_non_negative_bucket("Reserved", new_reserved)
        self._validate_non_negative_bucket("Blocked", new_blocked)
        self._validate_non_negative_bucket("Damaged", new_damaged)
        self._validate_non_negative_bucket("Quarantine", new_quarantine)
        self._validate_non_negative_bucket("In transit", new_in_transit)

        inventory.current_quantity = new_current
        inventory.reserved_quantity = new_reserved
        inventory.available_quantity = new_available
        inventory.blocked_quantity = new_blocked
        inventory.damaged_quantity = new_damaged
        inventory.quarantine_quantity = new_quarantine
        inventory.in_transit_quantity = new_in_transit
        inventory.display_quantity = new_current
        if movement.entered_uom_id is not None:
            inventory.display_uom_id = movement.entered_uom_id
        elif inventory.display_uom_id is None:
            inventory.display_uom_id = self._default_display_uom_id(
                inventory.product_id
            )
        inventory.last_transaction_at = movement.transaction_date
        inventory.updated_by = actor_id

        unit_cost, total_cost, average_after = (
            self._apply_valuation(inventory, movement, actor_id)
            if movement.revalues
            else (None, None, self._held_average(inventory, movement))
        )
        transaction = InventoryTransaction(
            inventory_id=inventory.id,
            firm_id=inventory.firm_id,
            branch_id=inventory.branch_id,
            warehouse_id=inventory.warehouse_id,
            storage_node_id=inventory.storage_node_id,
            product_id=inventory.product_id,
            batch_id=movement.batch_id or inventory.batch_id,
            serial_id=movement.serial_id,
            business_profile_id=inventory.business_profile_id,
            transaction_type=movement.transaction_type,
            reference_number=movement.reference_number,
            reference_type=movement.reference_type,
            transaction_date=movement.transaction_date,
            quantity=movement.quantity,
            current_quantity_delta=movement.current_delta,
            reserved_quantity_delta=movement.reserved_delta,
            blocked_quantity_delta=movement.blocked_delta,
            damaged_quantity_delta=movement.damaged_delta,
            quarantine_quantity_delta=movement.quarantine_delta,
            in_transit_quantity_delta=movement.in_transit_delta,
            owned_quantity_delta=movement.owned_delta,
            previous_current_quantity=previous_current,
            new_current_quantity=new_current,
            previous_reserved_quantity=previous_reserved,
            new_reserved_quantity=new_reserved,
            previous_available_quantity=previous_available,
            new_available_quantity=new_available,
            previous_blocked_quantity=previous_blocked,
            new_blocked_quantity=new_blocked,
            previous_damaged_quantity=previous_damaged,
            new_damaged_quantity=new_damaged,
            previous_quarantine_quantity=previous_quarantine,
            new_quarantine_quantity=new_quarantine,
            previous_in_transit_quantity=previous_in_transit,
            new_in_transit_quantity=new_in_transit,
            remarks=movement.remarks,
            entered_quantity=movement.entered_quantity or movement.quantity,
            entered_uom_id=movement.entered_uom_id,
            conversion_version=movement.conversion_version,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(transaction)
        self._session.flush()
        self._session.add(
            StockLedgerEntry(
                transaction_id=transaction.id,
                inventory_id=inventory.id,
                firm_id=inventory.firm_id,
                branch_id=inventory.branch_id,
                warehouse_id=inventory.warehouse_id,
                storage_node_id=inventory.storage_node_id,
                product_id=inventory.product_id,
                batch_id=transaction.batch_id,
                business_profile_id=inventory.business_profile_id,
                transaction_type=transaction.transaction_type,
                reference_number=transaction.reference_number,
                reference_type=transaction.reference_type,
                transaction_date=transaction.transaction_date,
                quantity=transaction.quantity,
                current_quantity_delta=transaction.current_quantity_delta,
                reserved_quantity_delta=transaction.reserved_quantity_delta,
                blocked_quantity_delta=transaction.blocked_quantity_delta,
                damaged_quantity_delta=transaction.damaged_quantity_delta,
                quarantine_quantity_delta=transaction.quarantine_quantity_delta,
                in_transit_quantity_delta=transaction.in_transit_quantity_delta,
                previous_current_quantity=transaction.previous_current_quantity,
                new_current_quantity=transaction.new_current_quantity,
                previous_reserved_quantity=transaction.previous_reserved_quantity,
                new_reserved_quantity=transaction.new_reserved_quantity,
                previous_available_quantity=transaction.previous_available_quantity,
                new_available_quantity=transaction.new_available_quantity,
                previous_blocked_quantity=transaction.previous_blocked_quantity,
                new_blocked_quantity=transaction.new_blocked_quantity,
                previous_damaged_quantity=transaction.previous_damaged_quantity,
                new_damaged_quantity=transaction.new_damaged_quantity,
                previous_quarantine_quantity=transaction.previous_quarantine_quantity,
                new_quarantine_quantity=transaction.new_quarantine_quantity,
                previous_in_transit_quantity=transaction.previous_in_transit_quantity,
                new_in_transit_quantity=transaction.new_in_transit_quantity,
                remarks=transaction.remarks,
                unit_cost=unit_cost,
                total_cost=total_cost,
                average_cost_after=average_after,
                original_quantity=transaction.entered_quantity or transaction.quantity,
                original_uom_id=transaction.entered_uom_id,
                base_quantity=transaction.quantity,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        record_audit(
            self._session,
            action="inventory.transaction.created",
            entity_type="inventory_transaction",
            entity_id=transaction.id,
            actor_id=actor_id,
            firm_id=inventory.firm_id,
            after_data={
                "inventory_id": str(inventory.id),
                "transaction_type": transaction.transaction_type,
                "reference_number": transaction.reference_number,
                "new_current_quantity": str(new_current),
                "new_available_quantity": str(new_available),
            },
        )
        return transaction

    def _build_opening_stock_lines(
        self,
        *,
        firm_id: UUID,
        warehouse_id: UUID,
        lines: Iterable[OpeningStockLineCreate],
        actor_id: UUID,
    ) -> list[OpeningStockLine]:
        items: list[OpeningStockLine] = []
        seen: set[tuple[UUID, str, str]] = set()
        profile_id = self._resolved_profile_id(firm_id)
        for index, line in enumerate(lines, start=1):
            product = self._session.scalar(
                select(Product).where(
                    Product.id == line.product_id,
                    Product.firm_id == firm_id,
                    Product.is_deleted.is_(False),
                )
            )
            if product is None:
                raise ValidationError(
                    "Opening stock line references an unknown product."
                )
            storage_node = None
            if line.storage_node_id is not None:
                storage_node = self._session.scalar(
                    select(WarehouseStorageNode).where(
                        WarehouseStorageNode.id == line.storage_node_id,
                        WarehouseStorageNode.warehouse_id == warehouse_id,
                        WarehouseStorageNode.is_deleted.is_(False),
                    )
                )
                if storage_node is None:
                    raise ValidationError(
                        "Opening stock line storage node does not belong to "
                        "the selected warehouse."
                    )
            locator = self._storage_locator(storage_node.id if storage_node else None)
            # The batch is part of the key, so one count of one shelf can
            # record two deliveries of a product expiring months apart.
            unique_key = (line.product_id, locator, (line.batch_number or "").strip())
            if unique_key in seen:
                raise ValidationError(
                    "Duplicate opening stock lines for the same product, "
                    "storage location and batch are not allowed."
                )
            seen.add(unique_key)
            items.append(
                OpeningStockLine(
                    line_number=index,
                    product_id=product.id,
                    storage_node_id=storage_node.id if storage_node else None,
                    storage_locator=locator,
                    business_profile_id=profile_id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    entered_quantity=line.entered_quantity,
                    entered_uom_id=line.entered_uom_id,
                    conversion_version=line.conversion_version,
                    batch_number=(line.batch_number or "").strip() or None,
                    expiry_date=line.expiry_date,
                    minimum_level=line.minimum_level,
                    maximum_level=line.maximum_level,
                    reorder_level=line.reorder_level,
                    safety_stock=line.safety_stock,
                    remarks=line.remarks,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        return items

    def _find_inventory_row(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_locator: str,
        product_id: UUID,
        batch_id: UUID | None,
    ) -> InventoryRecord | None:
        return self._session.scalar(
            select(InventoryRecord).where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.branch_id == branch_id,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.storage_locator == storage_locator,
                InventoryRecord.product_id == product_id,
                # `== None` renders IS NULL, which is what selects the single
                # row an untracked product keeps. Comparing a nullable column
                # with `==` to a None variable is the intent here, not a
                # mistake -- batch-tracked stock and untracked stock are
                # different rows and must not collapse into one.
                InventoryRecord.batch_id == batch_id,
                InventoryRecord.is_deleted.is_(False),
            )
        )

    def _validate_references(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
    ) -> tuple[Branch, Warehouse, WarehouseStorageNode | None, Product, UUID | None]:
        branch = self._session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.firm_id == firm_id,
                Branch.is_deleted.is_(False),
            )
        )
        if branch is None:
            raise ValidationError("Branch does not belong to the active firm.")
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.branch_id == branch.id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Warehouse does not belong to the selected branch.")
        storage_node = None
        if storage_node_id is not None:
            storage_node = self._session.scalar(
                select(WarehouseStorageNode).where(
                    WarehouseStorageNode.id == storage_node_id,
                    WarehouseStorageNode.warehouse_id == warehouse.id,
                    WarehouseStorageNode.is_deleted.is_(False),
                )
            )
            if storage_node is None:
                raise ValidationError(
                    "Storage node does not belong to the selected warehouse."
                )
        product = self._session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.firm_id == firm_id,
                Product.is_deleted.is_(False),
            )
        )
        if product is None:
            raise ValidationError("Product does not belong to the active firm.")
        return (
            branch,
            warehouse,
            storage_node,
            product,
            self._resolved_profile_id(firm_id),
        )

    def _validate_branch_warehouse_scope(
        self, *, firm_id: UUID, branch_id: UUID, warehouse_id: UUID
    ) -> None:
        branch = self._session.scalar(
            select(Branch.id).where(
                Branch.id == branch_id,
                Branch.firm_id == firm_id,
                Branch.is_deleted.is_(False),
            )
        )
        if branch is None:
            raise ValidationError("Branch does not belong to the active firm.")
        warehouse = self._session.scalar(
            select(Warehouse.id).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.branch_id == branch_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Warehouse does not belong to the selected branch.")

    def _movement_reference(
        self,
        data: (
            StockWriteOffCreate
            | StockQuarantineCreate
            | StockTransferCreate
            | InventoryAdjustmentCreate
        ),
        kind: str,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> str:
        """Return the typed reference, or the next number of ``kind``'s series.

        Returns what was typed whenever something was, so calling it again on a
        movement already numbered hands back the same number (D-QA-16).
        """
        return MovementNumbering(self._session, kind).reference(
            data.reference_number,
            firm_id=firm_id,
            on=data.transaction_date,
            actor_id=actor_id,
        )

    def _assert_unique_opening_reference(
        self, firm_id: UUID, reference_number: str, excluding_id: UUID | None = None
    ) -> None:
        statement = select(OpeningStockBatch.id).where(
            OpeningStockBatch.firm_id == firm_id,
            OpeningStockBatch.reference_number == reference_number.strip().upper(),
            OpeningStockBatch.is_deleted.is_(False),
        )
        if excluding_id is not None:
            statement = statement.where(OpeningStockBatch.id != excluding_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("Opening stock reference number already exists.")

    def _resolved_profile_id(self, firm_id: UUID) -> UUID | None:
        """Return the profile a stock row is filed under, default included.

        Delegated to ``resolve_profile_id``: a private copy answers a different
        profile from the gate the moment either changes, and this one is
        stamped onto rows that outlive the request. Nothing here needs the
        profile object -- only its id -- so the id form is what it takes.
        """
        return resolve_profile_id(self._session, firm_id)

    def _storage_locator(self, storage_node_id: UUID | None) -> str:
        return str(storage_node_id) if storage_node_id is not None else "ROOT"

    def _default_display_uom_id(self, product_id: UUID) -> UUID | None:
        product = self._session.scalar(
            select(Product).where(
                Product.id == product_id, Product.is_deleted.is_(False)
            )
        )
        if product is None:
            return None
        return product.inventory_uom_id or product.base_uom_id

    def _resolve_base_quantity(
        self,
        *,
        firm_scope: UUID,
        product_id: UUID,
        quantity: Decimal,
        entered_uom_id: UUID | None,
        conversion_version: int | None,
        on_date: date,
        line_conversion: LineConversion | None = None,
        enforce_whole_units: bool = True,
    ) -> tuple[Decimal, Decimal, UUID | None, int | None]:
        entered = Decimal(str(quantity))
        # Every movement that brings a quantity in: a release only gives back
        # what was reserved, and refusing it would strand the reservation.
        if enforce_whole_units:
            assert_quantity_fits_unit(
                self._session,
                quantity=entered,
                uom_id=entered_uom_id,
                product_id=product_id,
                firm_id=firm_scope,
            )
        if entered_uom_id is None:
            return entered, entered, None, conversion_version
        product = self._session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.firm_id == firm_scope,
                Product.is_deleted.is_(False),
            )
        )
        if product is None:
            raise ValidationError("Transaction product is unavailable for conversion.")
        target_uom_id = product.base_uom_id or product.inventory_uom_id
        if target_uom_id is None or target_uom_id == entered_uom_id:
            return entered, entered, entered_uom_id, conversion_version
        if (
            line_conversion is not None
            and line_conversion.to_uom_id == target_uom_id
            and line_conversion.factor > ZERO
        ):
            # The line's own factor, as written. Editing the rule since --
            # its factor, or its version number -- changes nothing already on
            # a document (D-CFG-1).
            base_quantity = entered * Decimal(str(line_conversion.factor))
            recorded = (
                None
                if conversion_version is None
                else self._session.scalars(
                    select(ConversionRule)
                    .where(
                        ConversionRule.firm_id == firm_scope,
                        ConversionRule.from_uom_id == entered_uom_id,
                        ConversionRule.to_uom_id == target_uom_id,
                        ConversionRule.version_number == conversion_version,
                        or_(
                            ConversionRule.product_id == product_id,
                            ConversionRule.product_id.is_(None),
                        ),
                    )
                    .order_by(
                        case((ConversionRule.product_id.is_(None), 1), else_=0).asc(),
                        ConversionRule.is_deleted.asc(),
                    )
                ).first()
            )
            if recorded is not None:
                # Rounded the way the line was, so the shelf holds the 0.33
                # the line says rather than 0.3333 (D-CFG-11). The factor is
                # still the line's own; only the rule's rounding is read.
                base_quantity = quantize_by_rule(base_quantity, recorded)
            return base_quantity, entered, entered_uom_id, conversion_version
        statement = select(ConversionRule).where(
            ConversionRule.firm_id == firm_scope,
            ConversionRule.is_deleted.is_(False),
            ConversionRule.status == "ACTIVE",
            ConversionRule.from_uom_id == entered_uom_id,
            ConversionRule.to_uom_id == target_uom_id,
            ConversionRule.effective_from <= on_date,
            or_(
                ConversionRule.effective_to.is_(None),
                ConversionRule.effective_to >= on_date,
            ),
            or_(
                ConversionRule.product_id == product_id,
                ConversionRule.product_id.is_(None),
            ),
        )
        if conversion_version is not None:
            # version_number, not version. A line records the rule's published
            # revision -- which is what `convert_quantity` returns and what the
            # seven transactional modules store -- while `version` is the
            # optimistic-concurrency counter every ORM update bumps. The two
            # agree only until somebody edits a rule, after which this matched
            # nothing and the movement was refused for a rule that exists.
            statement = statement.where(
                ConversionRule.version_number == conversion_version
            )
        rule = self._session.scalars(
            statement.order_by(
                # Specificity ranked explicitly, the way
                # `UomService._resolve_conversion_rule` does it. Ordering by
                # product_id DESC relies on where the backend sorts NULLs:
                # PostgreSQL puts them first, so the firm-wide fallback beat
                # the product's own rule. SQLite sorts them last, which is why
                # no unit test could see it -- it was fixed once in `uom` and
                # this second copy kept the defect.
                case((ConversionRule.product_id.is_(None), 1), else_=0).asc(),
                ConversionRule.version_number.desc(),
                ConversionRule.created_at.desc(),
            )
        ).first()
        if rule is None:
            raise ValidationError(
                missing_conversion_message(
                    self._session,
                    product_id=product_id,
                    from_uom_id=entered_uom_id,
                    to_uom_id=target_uom_id,
                )
            )
        # The rule's own rounding, which the line was stored with.
        base_quantity = round_by_rule(entered, rule)
        return base_quantity, entered, entered_uom_id, rule.version_number

    def _available_quantity(
        self,
        *,
        current_quantity: Decimal,
        reserved_quantity: Decimal,
        blocked_quantity: Decimal,
    ) -> Decimal:
        return current_quantity - reserved_quantity - blocked_quantity

    def _validate_non_negative_bucket(self, label: str, value: Decimal) -> None:
        if value < 0:
            raise ValidationError(f"{label} quantity cannot become negative.")

    def _apply_thresholds(
        self,
        inventory: InventoryRecord,
        *,
        minimum_level: Decimal | None,
        maximum_level: Decimal | None,
        reorder_level: Decimal | None,
        safety_stock: Decimal | None,
        actor_id: UUID,
    ) -> None:
        if minimum_level is not None:
            inventory.minimum_level = minimum_level
        if maximum_level is not None:
            inventory.maximum_level = maximum_level
        if reorder_level is not None:
            inventory.reorder_level = reorder_level
        if safety_stock is not None:
            inventory.safety_stock = safety_stock
        inventory.updated_by = actor_id

    def _lookup_branch_code(self, branch_id: UUID) -> str:
        return str(
            self._session.scalar(select(Branch.code).where(Branch.id == branch_id))
            or ""
        )

    def _lookup_branch_name(self, branch_id: UUID) -> str:
        return str(
            self._session.scalar(select(Branch.name).where(Branch.id == branch_id))
            or ""
        )

    def _lookup_warehouse_code(self, warehouse_id: UUID) -> str:
        return str(
            self._session.scalar(
                select(Warehouse.code).where(Warehouse.id == warehouse_id)
            )
            or ""
        )

    def _lookup_warehouse_name(self, warehouse_id: UUID) -> str:
        return str(
            self._session.scalar(
                select(Warehouse.name).where(Warehouse.id == warehouse_id)
            )
            or ""
        )

    def _lookup_storage_code(self, storage_node_id: UUID | None) -> str | None:
        if storage_node_id is None:
            return None
        value = self._session.scalar(
            select(WarehouseStorageNode.code).where(
                WarehouseStorageNode.id == storage_node_id
            )
        )
        return str(value) if value is not None else None

    def _lookup_storage_name(self, storage_node_id: UUID | None) -> str | None:
        if storage_node_id is None:
            return None
        value = self._session.scalar(
            select(WarehouseStorageNode.name).where(
                WarehouseStorageNode.id == storage_node_id
            )
        )
        return str(value) if value is not None else None

    def _lookup_product_code(self, product_id: UUID) -> str:
        return str(
            self._session.scalar(select(Product.code).where(Product.id == product_id))
            or ""
        )

    def _lookup_product_name(self, product_id: UUID) -> str:
        return str(
            self._session.scalar(select(Product.name).where(Product.id == product_id))
            or ""
        )

    def _lookup_batch(self, batch_id: UUID | None) -> tuple[str | None, date | None]:
        """Return a batch's number and expiry, in one query rather than two."""
        if batch_id is None:
            return None, None
        row = self._session.execute(
            select(BatchRecord.batch_number, BatchRecord.expiry_date).where(
                BatchRecord.id == batch_id
            )
        ).first()
        if row is None:
            return None, None
        return row[0], row[1]

    def _lookup_profile_code(self, profile_id: UUID | None) -> str | None:
        if profile_id is None:
            return None
        value = self._session.scalar(
            select(BusinessProfile.code).where(BusinessProfile.id == profile_id)
        )
        return str(value) if value is not None else None

    def _csv(self, response: InventoryResponse, attribute: str) -> str:
        return csv_text(getattr(response, attribute, None))

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(
                "The operation violates inventory uniqueness constraints."
            ) from error
