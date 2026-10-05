"""Firm-scoped REST endpoints for the enterprise inventory foundation."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.firm_metadata import firm_today
from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.pagination.reports import ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.imports.services import columns_for_kind, mapped_content, parse_mapping
from app.inventory.models import InventoryTransaction, PhysicalCount
from app.inventory.schemas import (
    MAX_STOCK_ATTACHMENTS,
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryListFilters,
    InventoryTransactionListFilters,
    OpeningStockBatchCreate,
    OpeningStockBatchListFilters,
    OpeningStockImportRequest,
    OpeningStockUpdate,
    PhysicalCountCreate,
    PhysicalCountLineResponse,
    PhysicalCountResponse,
    PhysicalCountUpdate,
    StockAttachmentResponse,
    StockAttachmentWrite,
    StockLedgerListFilters,
    StockQuarantineCreate,
    StockTransferCreate,
    StockWriteOffCreate,
)
from app.inventory.schemas.inventory import (
    InventoryLocationSummary,
    InventoryResponse,
    InventorySummary,
    InventoryTransactionResponse,
    InventoryUpdate,
    OpeningStockBatchResponse,
    StockLedgerResponse,
)
from app.inventory.services import InventoryService, PhysicalCountService
from app.inventory.services.adjustment_approval import (
    StockAdjustmentApprovalService,
    StockAdjustmentLimitItem,
    StockAdjustmentLimitsWrite,
    StockAdjustmentRejectWrite,
    StockAdjustmentRequestResponse,
    StockAdjustmentRequestWrite,
)
from app.inventory.services.adjustment_reasons import (
    AdjustmentReasonResponse,
    AdjustmentReasonService,
    AdjustmentReasonWrite,
)
from app.inventory.services.count_planning import (
    CountPlanResponse,
    CountPlanService,
    CountPlanWrite,
    abc_classes,
)
from app.inventory.services.free_goods import FreeGoodsRecord, free_goods_report
from app.inventory.services.opening_stock_import import OpeningStockFileImporter
from app.inventory.services.opening_stock_import import (
    template_csv as opening_stock_template_csv,
)
from app.inventory.services.opening_stock_import import (
    template_workbook as opening_stock_template_workbook,
)
from app.inventory.services.repacking import (
    RepackCancel,
    RepackResponse,
    RepackService,
    RepackWrite,
)
from app.inventory.services.stock_ageing import StockAgeingService
from app.inventory.services.stock_alerts import stock_alerts
from app.inventory.services.stock_evidence import StockEvidenceService
from app.inventory.services.stock_transfers import (
    StockTransferCancel,
    StockTransferDispatch,
    StockTransferReceive,
    StockTransferResponse,
    StockTransferService,
    StockTransferWrite,
)
from app.inventory.services.stock_valuation import (
    StockStatementService,
    StockValuationService,
)

router = APIRouter(
    prefix="/api/v1/inventory",
    tags=["Inventory"],
    responses=STANDARD_ERROR_RESPONSES,
)


InventoryViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_VIEW")
]
OpeningStockCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("OPENING_STOCK_CREATE")
]
OpeningStockUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("OPENING_STOCK_UPDATE")
]
InventoryLedgerViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_LEDGER_VIEW")
]
InventoryExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_EXPORT")
]
InventoryImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_IMPORT")
]
InventoryTransactionViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_TRANSACTION_VIEW")
]
InventoryAdjustScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_ADJUST")
]
#: The value limits on stock adjustments (STK-8).
InventorySettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_MANAGE_SETTINGS")
]
#: The reasons list and each reason's account (STK-7).
InventoryReasonsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_MANAGE_REASONS")
]
InventoryReasonsViewScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope(
        "INVENTORY_VIEW", "INVENTORY_ADJUST", "INVENTORY_MANAGE_REASONS"
    ),
]


@router.get("", response_model=PaginatedResponse[InventoryResponse])
def list_inventory(
    scope: InventoryViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "updated_at",
        "current_quantity",
        "available_quantity",
        "status",
        "product_code",
    ] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: str | None = Query(default=None, alias="status"),
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    low_stock_only: bool = False,
    out_of_stock_only: bool = False,
    negative_only: bool = False,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[InventoryResponse]:
    """List stock projections for the firm in scope."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = InventoryListFilters.model_validate(
        {
            "status": status_value,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "business_profile_id": business_profile_id,
            "low_stock_only": low_stock_only,
            "out_of_stock_only": out_of_stock_only,
            "negative_only": negative_only,
            "include_deleted": include_deleted,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_inventory(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=service.inventory_responses(rows),
        pagination=params.metadata(total),
    )


class StockValuationRecord(BaseModel):
    """One line of the stock valuation: an item, or a closing total."""

    model_config = ConfigDict(from_attributes=True)

    #: ITEM, or TOTAL / BOOKS / DIFFERENCE for the three closing rows.
    row_type: str
    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal | None
    rate: Decimal | None
    value: Decimal


StockValuationScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("INVENTORY_VIEW", "REPORT_VIEW")
]


@router.get(
    "/reports/free-goods",
    response_model=PaginatedResponse[FreeGoodsRecord],
)
def free_goods(
    scope: StockValuationScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[FreeGoodsRecord]:
    """Free goods received per supplier and scheme, given away, and held (BUY-1)."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(free_goods_report(db, firm_id=scope.firm_id, window=window))


class StockAlertRowRecord(BaseModel):
    """One stock alert row (STK-14)."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    product_code: str
    product_name: str
    quantity: Decimal
    level: Decimal | None = None
    detail: str = ""


class StockAlertsRecord(BaseModel):
    """What needs attention in the firm's stock (STK-14)."""

    model_config = ConfigDict(from_attributes=True)

    low: int
    out: int
    over_maximum: int
    near_expiry: int
    in_transit: int
    open_counts: int
    rows: list[StockAlertRowRecord]


@router.get("/alerts", response_model=ApiResponse[StockAlertsRecord])
def inventory_alerts(
    scope: StockValuationScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockAlertsRecord]:
    """Return the stock alerts for Home's to-do list (STK-14).

    Low, out, over maximum, near expiry, in transit, open counts -- each
    counted, with the first rows of each kind.
    """
    alerts = stock_alerts(db, scope.firm_id, on=firm_today(db, scope.firm_id))
    return ApiResponse(data=StockAlertsRecord.model_validate(alerts))


@router.get(
    "/reports/stock-valuation",
    response_model=PaginatedResponse[StockValuationRecord],
)
def stock_valuation(
    scope: StockValuationScope,
    to_date: date | None = None,
    from_date: date | None = None,
    warehouse_id: UUID | None = None,
    include_zero: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StockValuationRecord]:
    """Value the stock as on ``to_date`` (today when left out).

    Tally's Stock Summary (D-GOLIVE-3): each item's quantity, its moving
    average cost and value, then the grand total, the Inventory account's
    balance on the same day and the difference. ``from_date`` is accepted and
    ignored -- a valuation is as on a day, not over a period -- so the dated
    report screen can call it like its siblings.
    """
    del from_date
    today = firm_today(db, scope.firm_id)
    on = min(to_date or today, today)
    rows = StockValuationService(db).valuation(
        scope.firm_id, on=on, warehouse_id=warehouse_id, include_zero=include_zero
    )
    window = ReportWindow(None, None, page, page_size)
    return window.respond(
        [StockValuationRecord.model_validate(row, from_attributes=True) for row in rows]
    )


class StockStatementRecord(BaseModel):
    """One item's opening, in, out and closing over a period, or the total."""

    model_config = ConfigDict(from_attributes=True)

    #: ITEM, or TOTAL for the last row.
    row_type: str
    product_code: str
    product_name: str
    category: str
    unit: str
    opening_quantity: Decimal
    opening_value: Decimal
    inward_quantity: Decimal
    inward_value: Decimal
    outward_quantity: Decimal
    outward_value: Decimal
    closing_quantity: Decimal
    closing_value: Decimal


@router.get(
    "/reports/stock-statement",
    response_model=PaginatedResponse[StockStatementRecord],
)
def stock_statement(
    scope: StockValuationScope,
    from_date: date,
    to_date: date,
    warehouse_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StockStatementRecord]:
    """Return the bank stock statement: opening, in, out, closing, value.

    Backlog 70 row 6. Opening and closing agree with *Stock valuation* as on
    the day before ``from_date`` and on ``to_date``; what went out is valued
    as opening + in - closing, so the columns add up exactly.
    """
    if to_date < from_date:
        raise ValidationError("The period ends before it starts.")
    rows = StockStatementService(db).statement(
        scope.firm_id,
        from_date=from_date,
        to_date=min(to_date, firm_today(db, scope.firm_id)),
        warehouse_id=warehouse_id,
    )
    window = ReportWindow(None, None, page, page_size)
    return window.respond(
        [StockStatementRecord.model_validate(row, from_attributes=True) for row in rows]
    )


class StockAgeingRecord(BaseModel):
    """One item on hand, valued, split by how old it is (55 S7)."""

    model_config = ConfigDict(from_attributes=True)

    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal
    rate: Decimal
    value: Decimal
    days_0_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_91_180: Decimal
    days_over_180: Decimal
    last_receipt_date: date | None
    issued_last_year: Decimal = Decimal("0")
    #: Times a year what is on hand turns over (STK-14).
    turnover: Decimal | None = None


class SlowStockRecord(BaseModel):
    """One item on hand that is selling slowly or not at all (55 S7)."""

    model_config = ConfigDict(from_attributes=True)

    product_code: str
    product_name: str
    category: str
    unit: str
    quantity: Decimal
    value: Decimal
    issued_quantity: Decimal
    days_of_cover: Decimal | None
    last_issue_date: date | None
    days_since_issue: int | None
    last_receipt_date: date | None


@router.get(
    "/reports/stock-ageing",
    response_model=PaginatedResponse[StockAgeingRecord],
)
def stock_ageing(
    scope: StockValuationScope,
    to_date: date | None = None,
    from_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StockAgeingRecord]:
    """Age the stock on hand as on ``to_date`` (today when left out).

    What is on hand is taken to be the most recently received, as FIFO would
    leave it (``app/inventory/services/stock_ageing.py`` says how).
    ``from_date`` is accepted and ignored, as the valuation's is.
    """
    del from_date
    today = firm_today(db, scope.firm_id)
    on = min(to_date or today, today)
    rows = StockAgeingService(db).ageing(scope.firm_id, on=on)
    window = ReportWindow(None, None, page, page_size)
    return window.respond(
        [StockAgeingRecord.model_validate(row, from_attributes=True) for row in rows]
    )


def _slow_stock(
    firm_id: UUID,
    db: Session,
    *,
    to_date: date | None,
    days: int,
    dead_only: bool,
    window: ReportWindow,
) -> PaginatedResponse[SlowStockRecord]:
    """Answer the slow-moving or the dead stock, one page."""
    today = firm_today(db, firm_id)
    on = min(to_date or today, today)
    rows = StockAgeingService(db).slow_moving(
        firm_id, on=on, days=days, dead_only=dead_only
    )
    return window.respond(
        [SlowStockRecord.model_validate(row, from_attributes=True) for row in rows]
    )


@router.get(
    "/reports/slow-moving",
    response_model=PaginatedResponse[SlowStockRecord],
)
def slow_moving_stock(
    scope: StockValuationScope,
    days: Annotated[int, Query(ge=1, le=3660)] = 90,
    to_date: date | None = None,
    from_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SlowStockRecord]:
    """Stock on hand that the last ``days`` days' sales would not clear in as many.

    Days of cover is the quantity on hand over the daily rate it was issued
    at; no issue at all is the slowest. As on ``to_date`` (today when left
    out); ``from_date`` is accepted and ignored.
    """
    del from_date
    window = ReportWindow(None, None, page, page_size)
    return _slow_stock(
        scope.firm_id, db, to_date=to_date, days=days, dead_only=False, window=window
    )


@router.get(
    "/reports/dead-stock",
    response_model=PaginatedResponse[SlowStockRecord],
)
def dead_stock(
    scope: StockValuationScope,
    days: Annotated[int, Query(ge=1, le=3660)] = 180,
    to_date: date | None = None,
    from_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SlowStockRecord]:
    """Stock on hand with no issue to a customer in the last ``days`` days.

    As on ``to_date`` (today when left out); ``from_date`` is accepted and
    ignored.
    """
    del from_date
    window = ReportWindow(None, None, page, page_size)
    return _slow_stock(
        scope.firm_id, db, to_date=to_date, days=days, dead_only=True, window=window
    )


@router.get("/summary", response_model=ApiResponse[InventorySummary])
def inventory_summary(
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[InventorySummary]:
    """Return stock counts and value totals."""
    summary = InventoryService(db).inventory_summary(
        firm_scope=scope.firm_id,
        filters=InventoryListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.get(
    "/summary/by-firm", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_firm(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    """Return stock totals rolled up to the firm."""
    return ApiResponse(
        data=InventoryService(db).stock_by_firm(firm_scope=scope.firm_id)
    )


@router.get(
    "/summary/by-branch", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_branch(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    """Return stock totals per branch."""
    return ApiResponse(
        data=InventoryService(db).stock_by_branch(firm_scope=scope.firm_id)
    )


@router.get(
    "/summary/by-warehouse", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_warehouse(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    """Return stock totals per warehouse."""
    return ApiResponse(
        data=InventoryService(db).stock_by_warehouse(firm_scope=scope.firm_id)
    )


@router.get(
    "/summary/by-product", response_model=ApiResponse[list[InventoryLocationSummary]]
)
def stock_by_product(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryLocationSummary]]:
    """Return stock totals per product, summed across its batches."""
    return ApiResponse(
        data=InventoryService(db).stock_by_product(firm_scope=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[InventoryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_inventory(
    data: InventoryCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryResponse]:
    """Create a stock projection for a product location."""
    service = InventoryService(db)
    row = service.create_inventory_record(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.inventory_response(row))


@router.get(
    "/transactions", response_model=PaginatedResponse[InventoryTransactionResponse]
)
def list_transactions(
    scope: InventoryTransactionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "transaction_date",
        "transaction_type",
        "reference_number",
        "quantity",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    transaction_type: str | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    reference_number: str | None = None,
    reference_type: str | None = None,
    transaction_from: str | None = None,
    transaction_to: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[InventoryTransactionResponse]:
    """List inventory movements."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = InventoryTransactionListFilters.model_validate(
        {
            "transaction_type": transaction_type,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "reference_number": reference_number,
            "reference_type": reference_type,
            "transaction_from": transaction_from,
            "transaction_to": transaction_to,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_transactions(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=service.transaction_responses(rows),
        pagination=params.metadata(total),
    )


@router.get("/ledger", response_model=PaginatedResponse[StockLedgerResponse])
def list_ledger(
    scope: InventoryLedgerViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at",
        "transaction_date",
        "transaction_type",
        "reference_number",
        "quantity",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    transaction_type: str | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    storage_node_id: UUID | None = None,
    product_id: UUID | None = None,
    reference_number: str | None = None,
    reference_type: str | None = None,
    transaction_from: str | None = None,
    transaction_to: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StockLedgerResponse]:
    """List immutable stock ledger rows."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = StockLedgerListFilters.model_validate(
        {
            "transaction_type": transaction_type,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "storage_node_id": storage_node_id,
            "product_id": product_id,
            "reference_number": reference_number,
            "reference_type": reference_type,
            "transaction_from": transaction_from,
            "transaction_to": transaction_to,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_ledger(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=service.ledger_responses(rows),
        pagination=params.metadata(total),
    )


@router.post(
    "/opening-stock",
    response_model=ApiResponse[OpeningStockBatchResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_opening_stock(
    data: OpeningStockBatchCreate,
    scope: OpeningStockCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    """Create a draft opening-stock batch."""
    service = InventoryService(db)
    row = service.create_opening_stock_batch(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.get(
    "/opening-stock", response_model=PaginatedResponse[OpeningStockBatchResponse]
)
def list_opening_stock(
    scope: InventoryViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at", "posting_date", "reference_number", "status"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: str | None = Query(default=None, alias="status"),
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    posting_from: str | None = None,
    posting_to: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[OpeningStockBatchResponse]:
    """List opening-stock batches."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = OpeningStockBatchListFilters.model_validate(
        {
            "status": status_value,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "posting_from": posting_from,
            "posting_to": posting_to,
            "include_deleted": include_deleted,
        }
    )
    service = InventoryService(db)
    rows, total = service.list_opening_stock_batches(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=service.opening_stock_batch_responses(rows),
        pagination=params.metadata(total),
    )


@router.get("/opening-stock/import-template")
def opening_stock_import_template(
    scope: InventoryImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the opening-stock import template (backlog 36, 46).

    The workbook carries the sheet to fill, a notes sheet naming every column,
    and a lists sheet with this firm's warehouses and products, each product
    marked where it needs a batch or an expiry. The example row names the
    firm's own product and warehouse, so the template imports as it comes.
    """
    if format == "csv":
        return StreamingResponse(
            iter([opening_stock_template_csv(db, scope.firm_id)]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="opening-stock-template.csv"'
                )
            },
        )
    return StreamingResponse(
        iter([opening_stock_template_workbook(db, scope.firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="opening-stock-template.xlsx"'
        },
    )


@router.post(
    "/opening-stock/import-file", response_model=ApiResponse[ImportReportResponse]
)
async def import_opening_stock_file(
    scope: InventoryImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    posting_date: Annotated[str | None, Form()] = None,
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX stock count, and with ``apply`` create and post it.

    Rows are grouped into one opening-stock document per warehouse, all on
    ``posting_date`` (today when left out). Every problem is returned with its
    row and column; an apply that finds any writes nothing and says so with
    ``imported: false``.
    """
    file_format = file_format_of(file.filename)
    # A file mapped on the import screen is read as mapped (decision B3).
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "opening-stock"),
    )
    if posting_date:
        try:
            on = date.fromisoformat(posting_date)
        except ValueError as error:
            raise ValidationError("posting_date must be a date, yyyy-mm-dd.") from error
    else:
        on = firm_today(db, scope.firm_id)
    report = OpeningStockFileImporter(db).run(
        content,
        file_format=file_format,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        posting_date=on,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


@router.get(
    "/opening-stock/{batch_id}", response_model=ApiResponse[OpeningStockBatchResponse]
)
def get_opening_stock(
    batch_id: UUID,
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    """Return one opening-stock batch."""
    service = InventoryService(db)
    row = service.get_opening_stock_batch(
        batch_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.put(
    "/opening-stock/{batch_id}", response_model=ApiResponse[OpeningStockBatchResponse]
)
def update_opening_stock(
    batch_id: UUID,
    data: OpeningStockUpdate,
    scope: OpeningStockUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[OpeningStockBatchResponse]:
    """Change a draft opening-stock batch."""
    service = InventoryService(db)
    row = service.update_opening_stock_batch(
        batch_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/opening-stock/{batch_id}/post",
    response_model=ApiResponse[OpeningStockBatchResponse],
)
def post_opening_stock(
    batch_id: UUID,
    scope: OpeningStockCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[OpeningStockBatchResponse]:
    """Post an opening-stock batch into the ledger."""
    service = InventoryService(db)
    row = service.post_opening_stock_batch(
        batch_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/opening-stock/import",
    response_model=ApiResponse[OpeningStockBatchResponse],
    status_code=status.HTTP_201_CREATED,
)
async def import_opening_stock(
    scope: InventoryImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json", "csv", "xlsx"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    reference_number: Annotated[str | None, Form()] = None,
    posting_date: Annotated[str | None, Form()] = None,
    branch_id: Annotated[UUID | None, Form()] = None,
    warehouse_id: Annotated[UUID | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    auto_post: Annotated[bool, Form()] = True,
) -> ApiResponse[OpeningStockBatchResponse]:
    """Create an opening-stock batch from an upload or JSON body."""
    service = InventoryService(db)
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        row = service.import_opening_stock_json(
            OpeningStockImportRequest.model_validate_json(payload),
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
        return ApiResponse(data=service.opening_stock_batch_response(row))
    if (
        file is None
        or reference_number is None
        or posting_date is None
        or branch_id is None
        or warehouse_id is None
    ):
        raise ValidationError(
            "file, reference_number, posting_date, branch_id, and warehouse_id "
            "are required for CSV/XLSX import."
        )
    try:
        parsed_posting_date = date.fromisoformat(posting_date)
    except ValueError as error:
        raise ValidationError("posting_date must be a valid ISO date.") from error
    content = await file.read()
    if format == "csv":
        row = service.import_opening_stock_csv(
            content.decode("utf-8"),
            reference_number=reference_number,
            posting_date=parsed_posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
    else:
        row = service.import_opening_stock_xlsx(
            content,
            reference_number=reference_number,
            posting_date=parsed_posting_date,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            remarks=remarks,
            auto_post=auto_post,
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
    return ApiResponse(data=service.opening_stock_batch_response(row))


@router.post(
    "/adjustments",
    response_model=ApiResponse[InventoryTransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_adjustment(
    data: InventoryAdjustmentCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryTransactionResponse]:
    """Post a stock adjustment."""
    service = InventoryService(db)
    row = service.create_adjustment(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.transaction_response(row))


@router.post(
    "/transfers",
    response_model=ApiResponse[list[InventoryTransactionResponse]],
    status_code=status.HTTP_201_CREATED,
)
def transfer_stock(
    data: StockTransferCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[InventoryTransactionResponse]]:
    """Move stock between warehouses.

    Returns both movements, out and in: a transfer is two sides of one thing,
    and returning only one of them would leave the caller to guess the other.
    """
    service = InventoryService(db)
    outbound, inbound = service.transfer_stock(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=[
            service.transaction_response(outbound),
            service.transaction_response(inbound),
        ],
        message="Stock transferred.",
    )


@router.post(
    "/write-offs",
    response_model=ApiResponse[InventoryTransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
def write_off_stock(
    data: StockWriteOffCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryTransactionResponse]:
    """Take stock off the books, and say why.

    A generic adjustment reached damage, expiry and loss alike, so a firm could
    answer how much stock it lost and not to what.
    """
    service = InventoryService(db)
    row = service.write_off_stock(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=service.transaction_response(row), message="Stock written off."
    )


@router.get(
    "/adjustment-limits", response_model=ApiResponse[list[StockAdjustmentLimitItem]]
)
def list_adjustment_limits(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAdjustmentLimitItem]]:
    """Return the largest adjustment each role may post (STK-8)."""
    return ApiResponse(
        data=[
            StockAdjustmentLimitItem(role_code=row.role_code, max_value=row.max_value)
            for row in StockAdjustmentApprovalService(db).limits(scope.firm_id)
        ]
    )


@router.put(
    "/adjustment-limits", response_model=ApiResponse[list[StockAdjustmentLimitItem]]
)
def replace_adjustment_limits(
    data: StockAdjustmentLimitsWrite,
    scope: InventorySettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAdjustmentLimitItem]]:
    """Replace the whole list; a role left out has no limit (STK-8)."""
    rows = StockAdjustmentApprovalService(db).replace_limits(
        data.limits, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=[
            StockAdjustmentLimitItem(role_code=row.role_code, max_value=row.max_value)
            for row in rows
        ]
    )


@router.get(
    "/adjustment-requests",
    response_model=ApiResponse[list[StockAdjustmentRequestResponse]],
)
def list_adjustment_requests(
    scope: InventoryAdjustScope,
    status_filter: Annotated[
        Literal["PENDING", "APPROVED", "REJECTED"], Query(alias="status")
    ] = "PENDING",
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAdjustmentRequestResponse]]:
    """Return adjustments waiting for, or decided by, an approval (STK-8)."""
    return ApiResponse(
        data=StockAdjustmentApprovalService(db).list_requests(
            scope.firm_id, status=status_filter
        )
    )


@router.post(
    "/adjustment-requests",
    response_model=ApiResponse[StockAdjustmentRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
def submit_adjustment_request(
    data: StockAdjustmentRequestWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockAdjustmentRequestResponse]:
    """Submit an adjustment or write-off above your limit for approval."""
    return ApiResponse(
        data=StockAdjustmentApprovalService(db).submit(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Submitted for approval.",
    )


@router.post(
    "/adjustment-requests/bulk-approve",
    response_model=ApiResponse[BulkActionResult],
)
def bulk_approve_adjustment_requests(
    data: BulkApproveRequest,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked requests, each on its own (STK-8)."""
    service = StockAdjustmentApprovalService(db)
    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda request_id: service.get(request_id, firm_id=scope.firm_id),
            act=lambda request_id: service.approve(
                request_id, firm_id=scope.firm_id, actor_id=scope.actor_id
            ),
            number=lambda row: f"{row.kind} {row.quantity.normalize():f}",
        )
    )


@router.post(
    "/adjustment-requests/{request_id}/approve",
    response_model=ApiResponse[StockAdjustmentRequestResponse],
)
def approve_adjustment_request(
    request_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockAdjustmentRequestResponse]:
    """Post a pending request, if your limit covers it (STK-8)."""
    return ApiResponse(
        data=StockAdjustmentApprovalService(db).approve(
            request_id, firm_id=scope.firm_id, actor_id=scope.actor_id
        ),
        message="Approved and posted.",
    )


@router.post(
    "/adjustment-requests/{request_id}/reject",
    response_model=ApiResponse[StockAdjustmentRequestResponse],
)
def reject_adjustment_request(
    request_id: UUID,
    data: StockAdjustmentRejectWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockAdjustmentRequestResponse]:
    """Turn a pending request down, keeping why (STK-8)."""
    return ApiResponse(
        data=StockAdjustmentApprovalService(db).reject(
            request_id,
            data.reason,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
        )
    )


@router.get(
    "/adjustment-reasons",
    response_model=ApiResponse[list[AdjustmentReasonResponse]],
)
def list_adjustment_reasons(
    scope: InventoryReasonsViewScope,
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AdjustmentReasonResponse]]:
    """Return the firm's adjustment and write-off reasons (STK-7)."""
    return ApiResponse(
        data=AdjustmentReasonService(db).list_reasons(
            scope.firm_id, include_inactive=not active_only
        )
    )


@router.post(
    "/adjustment-reasons",
    response_model=ApiResponse[AdjustmentReasonResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_adjustment_reason(
    data: AdjustmentReasonWrite,
    scope: InventoryReasonsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AdjustmentReasonResponse]:
    """Add a reason of the firm's own (STK-7)."""
    return ApiResponse(
        data=AdjustmentReasonService(db).create(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.put(
    "/adjustment-reasons/{reason_id}",
    response_model=ApiResponse[AdjustmentReasonResponse],
)
def update_adjustment_reason(
    reason_id: UUID,
    data: AdjustmentReasonWrite,
    scope: InventoryReasonsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AdjustmentReasonResponse]:
    """Rename, retarget or deactivate a reason (STK-7)."""
    return ApiResponse(
        data=AdjustmentReasonService(db).update(
            reason_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.delete("/adjustment-reasons/{reason_id}", response_model=ApiResponse[None])
def delete_adjustment_reason(
    reason_id: UUID,
    scope: InventoryReasonsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a reason of the firm's own; a system one is refused (STK-7)."""
    AdjustmentReasonService(db).delete(
        reason_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Reason deleted.")


@router.get("/repacks", response_model=ApiResponse[list[RepackResponse]])
def list_repacks(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[RepackResponse]]:
    """Return the firm's repacks, newest first (STK-4)."""
    service = RepackService(db)
    return ApiResponse(data=service.responses(service.list_rows(scope.firm_id)))


@router.post(
    "/repacks",
    response_model=ApiResponse[RepackResponse],
    status_code=status.HTTP_201_CREATED,
)
def post_repack(
    data: RepackWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RepackResponse]:
    """Break or repack goods: consume, produce, write off wastage (STK-4)."""
    service = RepackService(db)
    row = service.post(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.responses([row])[0], message="Repack posted.")


@router.post("/repacks/{repack_id}/cancel", response_model=ApiResponse[RepackResponse])
def cancel_repack(
    repack_id: UUID,
    data: RepackCancel,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RepackResponse]:
    """Reverse a repack's movements and wastage (STK-4)."""
    service = RepackService(db)
    row = service.cancel(
        repack_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0])


@router.get("/stock-transfers", response_model=ApiResponse[list[StockTransferResponse]])
def list_stock_transfers(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
    status_filter: Annotated[str | None, Query(alias="status", max_length=20)] = None,
) -> ApiResponse[list[StockTransferResponse]]:
    """Return the firm's transfer documents, newest first (STK-1)."""
    service = StockTransferService(db)
    return ApiResponse(
        data=service.responses(service.list_rows(scope.firm_id, status=status_filter))
    )


@router.post(
    "/stock-transfers",
    response_model=ApiResponse[StockTransferResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_stock_transfer(
    data: StockTransferWrite,
    scope: InventoryAdjustScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[StockTransferResponse]:
    """Save a draft transfer (STK-1)."""
    service = StockTransferService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Transfer saved.")


@router.get(
    "/stock-transfers/{transfer_id}",
    response_model=ApiResponse[StockTransferResponse],
)
def get_stock_transfer(
    transfer_id: UUID,
    scope: InventoryViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[StockTransferResponse]:
    """Return one transfer document and its lines (STK-1)."""
    service = StockTransferService(db)
    row = service.get(transfer_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put(
    "/stock-transfers/{transfer_id}",
    response_model=ApiResponse[StockTransferResponse],
)
def update_stock_transfer(
    transfer_id: UUID,
    data: StockTransferWrite,
    scope: InventoryAdjustScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[StockTransferResponse]:
    """Rewrite a draft transfer (STK-1)."""
    service = StockTransferService(db)
    row = service.update(
        transfer_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Transfer saved.")


@router.post(
    "/stock-transfers/{transfer_id}/dispatch",
    response_model=ApiResponse[StockTransferResponse],
)
def dispatch_stock_transfer(
    transfer_id: UUID,
    data: StockTransferDispatch,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockTransferResponse]:
    """Send the goods: off the source and in transit (STK-1)."""
    service = StockTransferService(db)
    row = service.dispatch(
        transfer_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Dispatched.")


@router.post(
    "/stock-transfers/{transfer_id}/receive",
    response_model=ApiResponse[StockTransferResponse],
)
def receive_stock_transfer(
    transfer_id: UUID,
    data: StockTransferReceive,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockTransferResponse]:
    """Take the goods in, with damage and shortage (STK-1)."""
    service = StockTransferService(db)
    row = service.receive(
        transfer_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Received.")


@router.post(
    "/stock-transfers/{transfer_id}/cancel",
    response_model=ApiResponse[StockTransferResponse],
)
def cancel_stock_transfer(
    transfer_id: UUID,
    data: StockTransferCancel,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StockTransferResponse]:
    """Withdraw a draft, or bring dispatched goods back (STK-1)."""
    service = StockTransferService(db)
    row = service.cancel(
        transfer_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Cancelled.")


@router.get("/stock-transfers/{transfer_id}/challan", response_class=StreamingResponse)
def print_stock_transfer_challan(
    transfer_id: UUID,
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Render the delivery challan that travels with the goods (STK-1)."""
    pdf, filename = StockTransferService(db).render_challan(
        transfer_id, firm_id=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post(
    "/quarantine",
    response_model=ApiResponse[InventoryTransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
def quarantine_stock(
    data: StockQuarantineCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryTransactionResponse]:
    """Hold stock back from sale, or release it again.

    Quarantined stock is still owned and still worth what it was, so nothing
    posts. Condemning it is a separate decision and goes through the write-off.
    """
    service = InventoryService(db)
    row = service.quarantine_stock(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.transaction_response(row))


def _count_response(
    service: PhysicalCountService, row: PhysicalCount
) -> PhysicalCountResponse:
    """Build the response for one count sheet, with its lines."""
    return PhysicalCountResponse(
        id=row.id,
        branch_id=row.branch_id,
        warehouse_id=row.warehouse_id,
        warehouse_name=service.warehouse_name(row.warehouse_id),
        count_number=row.count_number,
        count_date=row.count_date,
        status=row.status,
        remarks=row.remarks,
        posted_at=row.posted_at,
        is_blind=row.is_blind,
        count_plan_id=row.count_plan_id,
        lines=_count_lines(service, row),
        version=row.version,
    )


def _count_lines(
    service: PhysicalCountService, row: PhysicalCount
) -> list[PhysicalCountLineResponse]:
    """Return the sheet's lines with each product and location named."""
    lines = service.lines_for(row.id)
    labels = service.product_labels(
        firm_id=row.firm_id, product_ids=[line.product_id for line in lines]
    )
    places = service.storage_labels(line.storage_node_id for line in lines)
    responses: list[PhysicalCountLineResponse] = []
    for line in lines:
        code, name = labels.get(line.product_id, ("", ""))
        place = (
            places.get(line.storage_node_id)
            if line.storage_node_id is not None
            else None
        )
        hidden = row.is_blind and row.status == "DRAFT"
        responses.append(
            PhysicalCountLineResponse.model_validate(line).model_copy(
                update={
                    "product_code": code,
                    "product_name": name,
                    "storage_node_code": place[0] if place else None,
                    "storage_node_name": place[1] if place else None,
                    # A blind sheet shows what the system holds only once
                    # posted (STK-6).
                    **({"expected_quantity": None} if hidden else {}),
                }
            )
        )
    return responses


@router.get("/abc-classes", response_model=ApiResponse[dict[str, str]])
def inventory_abc_classes(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Return each dispatched product's ABC class, by product id (STK-6).

    A product not listed is C.
    """
    classes = abc_classes(db, scope.firm_id, on=firm_today(db, scope.firm_id))
    return ApiResponse(data={str(key): value for key, value in classes.items()})


@router.get("/count-plans", response_model=ApiResponse[list[CountPlanResponse]])
def list_count_plans(
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CountPlanResponse]]:
    """Return the firm's count plans, the due ones first (STK-6)."""
    return ApiResponse(
        data=CountPlanService(db).list_plans(
            scope.firm_id, on=firm_today(db, scope.firm_id)
        )
    )


@router.post(
    "/count-plans",
    response_model=ApiResponse[CountPlanResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_count_plan(
    data: CountPlanWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CountPlanResponse]:
    """Add a count plan (STK-6)."""
    return ApiResponse(
        data=CountPlanService(db).create(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.put("/count-plans/{plan_id}", response_model=ApiResponse[CountPlanResponse])
def update_count_plan(
    plan_id: UUID,
    data: CountPlanWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CountPlanResponse]:
    """Change a count plan (STK-6)."""
    return ApiResponse(
        data=CountPlanService(db).update(
            plan_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.delete("/count-plans/{plan_id}", response_model=ApiResponse[None])
def delete_count_plan(
    plan_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a count plan; its sheets stay (STK-6)."""
    CountPlanService(db).delete(plan_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=None, message="Count plan deleted.")


@router.post(
    "/count-plans/{plan_id}/sheet",
    response_model=ApiResponse[PhysicalCountResponse],
    status_code=status.HTTP_201_CREATED,
)
def draw_count_plan_sheet(
    plan_id: UUID,
    scope: InventoryAdjustScope,
    count_date: date | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Open the sheet a count plan covers (STK-6)."""
    sheet = CountPlanService(db).draw_sheet(
        plan_id,
        count_date=count_date or firm_today(db, scope.firm_id),
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=_count_response(PhysicalCountService(db), sheet))


@router.post(
    "/counts",
    response_model=ApiResponse[PhysicalCountResponse],
    status_code=status.HTTP_201_CREATED,
)
def open_physical_count(
    data: PhysicalCountCreate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Open a count sheet, drawn up from what the warehouse currently holds."""
    service = PhysicalCountService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_count_response(service, row))


@router.get("/counts", response_model=PaginatedResponse[PhysicalCountResponse])
def list_physical_counts(
    scope: InventoryViewScope,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=""),
    count_from: date | None = None,
    count_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PhysicalCountResponse]:
    """List count sheets, newest first."""
    service = PhysicalCountService(db)
    rows, total = service.list_counts(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        count_from=count_from,
        count_to=count_to,
    )
    return PaginatedResponse(
        data=[_count_response(service, row) for row in rows],
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/counts/{count_id}", response_model=ApiResponse[PhysicalCountResponse])
def get_physical_count(
    count_id: UUID,
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Return one count sheet."""
    service = PhysicalCountService(db)
    return ApiResponse(
        data=_count_response(service, service.get(count_id, firm_id=scope.firm_id))
    )


@router.put("/counts/{count_id}", response_model=ApiResponse[PhysicalCountResponse])
def record_physical_count(
    count_id: UUID,
    data: PhysicalCountUpdate,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Record what was found, on a sheet nobody has posted yet."""
    service = PhysicalCountService(db)
    row = service.update(count_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_count_response(service, row))


@router.post(
    "/counts/{count_id}/post", response_model=ApiResponse[PhysicalCountResponse]
)
def post_physical_count(
    count_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Turn every difference into a stock adjustment.

    The variance is measured against what the system holds now, not against the
    snapshot the sheet was drawn up from: stock moves while a warehouse is
    counted, and posting a stale figure would undo the movements made in
    between.
    """
    service = PhysicalCountService(db)
    row = service.post(count_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=_count_response(service, row), message="Physical count posted."
    )


@router.post(
    "/counts/{count_id}/cancel", response_model=ApiResponse[PhysicalCountResponse]
)
def cancel_physical_count(
    count_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PhysicalCountResponse]:
    """Abandon a sheet that will not be posted."""
    service = PhysicalCountService(db)
    row = service.cancel(count_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_count_response(service, row))


class StockAttachmentsWrite(BaseModel):
    """The files a request keeps with a movement or a count sheet (STK-9)."""

    model_config = ConfigDict(extra="forbid")

    attachments: list[StockAttachmentWrite] = Field(
        min_length=1, max_length=MAX_STOCK_ATTACHMENTS
    )


@router.get(
    "/transactions/{transaction_id}/attachments",
    response_model=ApiResponse[list[StockAttachmentResponse]],
)
def list_movement_attachments(
    transaction_id: UUID,
    scope: InventoryTransactionViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAttachmentResponse]]:
    """List the photos and documents backing a movement.

    A transfer's two legs show the same files, whichever is asked about.
    """
    service = StockEvidenceService(db)
    rows = service.for_movement(transaction_id, firm_id=scope.firm_id)
    return ApiResponse(data=[service.response(row) for row in rows])


@router.post(
    "/transactions/{transaction_id}/attachments",
    response_model=ApiResponse[list[StockAttachmentResponse]],
    status_code=status.HTTP_201_CREATED,
)
def attach_to_movement(
    transaction_id: UUID,
    data: StockAttachmentsWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAttachmentResponse]]:
    """Keep photos or documents with a movement already posted."""
    service = StockEvidenceService(db)
    rows = service.attach_to_movement(
        transaction_id,
        data.attachments,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=[service.response(row) for row in rows], message="Files attached."
    )


@router.get(
    "/counts/{count_id}/attachments",
    response_model=ApiResponse[list[StockAttachmentResponse]],
)
def list_count_attachments(
    count_id: UUID,
    scope: InventoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAttachmentResponse]]:
    """List the photos and documents kept with a count sheet."""
    service = StockEvidenceService(db)
    rows = service.for_count(count_id, firm_id=scope.firm_id)
    return ApiResponse(data=[service.response(row) for row in rows])


@router.post(
    "/counts/{count_id}/attachments",
    response_model=ApiResponse[list[StockAttachmentResponse]],
    status_code=status.HTTP_201_CREATED,
)
def attach_to_count(
    count_id: UUID,
    data: StockAttachmentsWrite,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[StockAttachmentResponse]]:
    """Keep photos or documents with a count sheet, draft or posted."""
    service = StockEvidenceService(db)
    rows = service.attach_to_count(
        count_id, data.attachments, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=[service.response(row) for row in rows], message="Files attached."
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_stock_attachment(
    attachment_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> Response:
    """Take a file off its movement or count sheet; the trail keeps that it was."""
    StockEvidenceService(db).remove(
        attachment_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export")
def export_inventory(
    scope: InventoryExportScope,
    dataset: Literal["inventory", "ledger"] = "inventory",
    format: Literal["csv", "xlsx"] = "csv",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream stock or ledger rows as CSV or XLSX."""
    service = InventoryService(db)
    if dataset == "ledger":
        if format == "xlsx":
            content = service.export_ledger_xlsx(
                firm_scope=scope.firm_id, search=search
            )
            return StreamingResponse(
                iter([content]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": 'attachment; filename="stock-ledger.xlsx"'
                },
            )
        text = service.export_ledger_csv(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([text]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="stock-ledger.csv"'},
        )
    if format == "xlsx":
        content = service.export_inventory_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="inventory.xlsx"'},
        )
    text = service.export_inventory_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inventory.csv"'},
    )


@router.get("/{inventory_id}", response_model=ApiResponse[InventoryResponse])
def get_inventory(
    inventory_id: UUID,
    scope: InventoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[InventoryResponse]:
    """Return one stock projection."""
    service = InventoryService(db)
    row = service.get_inventory_record(
        inventory_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=service.inventory_response(row))


@router.put("/{inventory_id}", response_model=ApiResponse[InventoryResponse])
def update_inventory(
    inventory_id: UUID,
    data: InventoryUpdate,
    scope: InventoryAdjustScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[InventoryResponse]:
    """Change a stock projection's thresholds and status."""
    service = InventoryService(db)
    row = service.update_inventory_record(
        inventory_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=service.inventory_response(row))


@router.delete("/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory(
    inventory_id: UUID,
    scope: InventoryAdjustScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete a stock projection."""
    row = InventoryService(db).get_inventory_record(
        inventory_id, firm_scope=scope.firm_id
    )
    if any(
        value != 0
        for value in (
            row.current_quantity,
            row.reserved_quantity,
            row.available_quantity,
            row.blocked_quantity,
            row.damaged_quantity,
            row.quarantine_quantity,
            row.in_transit_quantity,
        )
    ):
        raise ValidationError("Inventory with stock balances cannot be deleted.")
    # Asked as a yes/no, not by loading the row's whole history.
    if db.scalar(
        select(InventoryTransaction.id)
        .where(InventoryTransaction.inventory_id == row.id)
        .limit(1)
    ):
        raise ValidationError("Inventory with transaction history cannot be deleted.")
    row.is_deleted = True
    row.deleted_at = utc_now()
    row.deleted_by = scope.actor_id
    row.updated_by = scope.actor_id
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
