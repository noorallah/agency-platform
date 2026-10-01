"""Firm-scoped REST endpoints for enterprise purchase orders."""

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
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.document_framework.schemas.bulk_actions import (
    BulkActionResult,
    BulkApproveRequest,
    BulkCancelRequest,
)
from app.document_framework.services.bulk_actions import run_each
from app.purchase.models import RolePurchaseApprovalLimit
from app.purchase.schemas import (
    PurchaseOrderByBuyerRecord,
    PurchaseOrderByProductRecord,
    PurchaseOrderByVendorRecord,
    PurchaseOrderCreate,
    PurchaseOrderHistoryResponse,
    PurchaseOrderImportRequest,
    PurchaseOrderListFilters,
    PurchaseOrderOverdueRecord,
    PurchaseOrderPendingRecord,
    PurchaseOrderPreview,
    PurchaseOrderRegisterRecord,
    PurchaseOrderResponse,
    PurchaseOrderSentRequest,
    PurchaseOrderStatus,
    PurchaseOrderUpdate,
    PurchaseSummary,
    PurchaseType,
    PurchaseWorkflowSettingsResponse,
    PurchaseWorkflowSettingsWrite,
    RolePurchaseApprovalLimitItem,
    RolePurchaseApprovalLimitsResponse,
    RolePurchaseApprovalLimitsWrite,
)
from app.purchase.services import PurchaseService
from app.purchase.services.approval_limit import PurchaseApprovalLimitService
from app.purchase.services.purchase_print_service import (
    PurchaseOrderPrintService,
)
from app.purchase.services.reorder import ReorderPick, ReorderService
from app.purchase.services.workflow_settings_service import PurchaseWorkflowService

router = APIRouter(
    prefix="/api/v1/purchases",
    tags=["Purchases"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Optional reason payload for cancellation/closure actions."""

    reason: str | None = Field(default=None, max_length=500)


PurchaseViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
PurchaseReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("PURCHASE_VIEW", "REPORT_VIEW")
]
PurchaseCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CREATE")
]
PurchaseUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_UPDATE")
]
PurchaseDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_DELETE")
]
PurchaseRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_RESTORE")
]
PurchaseImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_IMPORT")
]
PurchaseExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_EXPORT")
]
PurchaseApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]
PurchaseCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_CANCEL")
]
PurchaseWorkflowSettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_MANAGE_SETTINGS")
]


def _filters(
    *,
    vendor_id: UUID | None,
    status_value: PurchaseOrderStatus | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    buyer_id: UUID | None,
    purchase_type: PurchaseType | None,
    created_from: date | None,
    created_to: date | None,
    include_deleted: bool,
    sent: bool | None = None,
) -> PurchaseOrderListFilters:
    """Collect the purchase order list filters from the query string."""
    try:
        return PurchaseOrderListFilters.model_validate(
            {
                "vendor_id": vendor_id,
                "status": status_value,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "buyer_id": buyer_id,
                "purchase_type": purchase_type,
                "created_from": created_from,
                "created_to": created_to,
                "include_deleted": include_deleted,
                "sent": sent,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[PurchaseOrderResponse])
def list_purchase_orders(
    scope: PurchaseViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "po_number", "purchase_date", "status", "grand_total", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    vendor_id: UUID | None = None,
    status_value: Annotated[PurchaseOrderStatus | None, Query(alias="status")] = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    buyer_id: UUID | None = None,
    purchase_type: PurchaseType | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    include_deleted: bool = False,
    sent: bool | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderResponse]:
    """List purchase orders; ``sent=false`` finds approved ones never sent."""
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = PurchaseService(db).list_orders(
        firm_scope=scope.firm_id,
        filters=_filters(
            vendor_id=vendor_id,
            status_value=status_value,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            buyer_id=buyer_id,
            purchase_type=purchase_type,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
            sent=sent,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    service = PurchaseService(db)
    return PaginatedResponse(
        data=service.order_responses(rows),
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[PurchaseSummary])
def purchase_summary(
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseSummary]:
    """Purchase summary."""
    return ApiResponse(data=PurchaseService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[PurchaseOrderResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    data: PurchaseOrderCreate,
    scope: PurchaseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Create purchase order."""
    service = PurchaseService(db)
    row = service.create_order(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.order_response(row))


@router.post("/preview", response_model=ApiResponse[PurchaseOrderPreview])
def preview_purchase_order(
    data: PurchaseOrderCreate,
    scope: PurchaseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderPreview]:
    """Price a purchase order as saving it would, and save nothing.

    What the order screen calls as its lines are typed, so the discounts,
    tax and totals it shows are the ones the save will store.
    """
    return ApiResponse(
        data=PurchaseService(db).preview_order(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[PurchaseOrderResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_purchase_orders(
    scope: PurchaseImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json", "csv", "xlsx"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[PurchaseOrderResponse]]:
    """Create several purchase orders from an upload or JSON body."""
    service = PurchaseService(db)
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        rows = service.import_orders(
            PurchaseOrderImportRequest.model_validate_json(payload),
            firm_scope=scope.firm_id,
            actor_id=scope.actor_id,
        )
        return ApiResponse(data=service.order_responses(rows))
    if file is None:
        raise ValidationError("file is required for CSV/XLSX import.")
    content = await file.read()
    rows = (
        service.import_orders_csv(
            content.decode("utf-8"), firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        if format == "csv"
        else service.import_orders_xlsx(
            content, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
    )
    return ApiResponse(data=service.order_responses(rows))


@router.get("/export")
def export_purchase_orders(
    scope: PurchaseExportScope,
    format: Literal["csv", "xlsx"] = "csv",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export purchase orders."""
    service = PurchaseService(db)
    if format == "xlsx":
        content = service.export_orders_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="purchase_orders.xlsx"'
            },
        )
    text = service.export_orders_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="purchase_orders.csv"'},
    )


@router.get(
    "/{order_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_purchase_order(
    order_id: UUID,
    scope: PurchaseViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render one purchase order as the PDF a supplier is sent.

    The same renderer the sales invoice uses, given an order's shape -- an
    order is placed with a supplier and delivered to a warehouse, and states no
    place of supply and no tax summary because it charges nobody.
    """
    pdf, filename = PurchaseOrderPrintService(db).render(
        order_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[PurchaseOrderRegisterRecord],
)
def purchase_order_register(
    scope: PurchaseReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderRegisterRecord]:
    """Return the purchase order register for the visible firm scope."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseService(db).register_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/pending",
    response_model=ApiResponse[list[PurchaseOrderPendingRecord]],
)
def pending_purchase_orders(
    scope: PurchaseReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderPendingRecord]]:
    """Return orders the vendor still owes goods against."""
    return ApiResponse(
        data=PurchaseService(db).pending_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/overdue",
    response_model=ApiResponse[list[PurchaseOrderOverdueRecord]],
)
def overdue_purchase_orders(
    scope: PurchaseReportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderOverdueRecord]]:
    """Return orders whose goods were expected and have not all arrived."""
    return ApiResponse(
        data=PurchaseService(db).overdue_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-vendor",
    response_model=PaginatedResponse[PurchaseOrderByVendorRecord],
)
def purchase_orders_by_vendor(
    scope: PurchaseReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderByVendorRecord]:
    """Return ordered value and count per vendor."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseService(db).by_vendor_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/by-buyer",
    response_model=PaginatedResponse[PurchaseOrderByBuyerRecord],
)
def purchase_orders_by_buyer(
    scope: PurchaseReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderByBuyerRecord]:
    """Return ordered value and count per buyer."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseService(db).by_buyer_report(firm_scope=scope.firm_id, window=window)
    )


@router.get(
    "/reports/by-product",
    response_model=PaginatedResponse[PurchaseOrderByProductRecord],
)
def purchase_orders_by_product(
    scope: PurchaseReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PurchaseOrderByProductRecord]:
    """Return what the firm is buying, by quantity and by value."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PurchaseService(db).by_product_report(firm_scope=scope.firm_id, window=window)
    )


# Both declared above `/{order_id}`: FastAPI matches in declaration order, and
# below it "workflow-settings" is read as an order id and answered 422.
@router.get(
    "/workflow-settings",
    response_model=ApiResponse[PurchaseWorkflowSettingsResponse],
)
def get_purchase_workflow_settings(
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseWorkflowSettingsResponse]:
    """Report which buying stages this firm fills in by hand."""
    return ApiResponse(
        data=PurchaseWorkflowService(db).settings_response(scope.firm_id)
    )


@router.put(
    "/workflow-settings",
    response_model=ApiResponse[PurchaseWorkflowSettingsResponse],
)
def update_purchase_workflow_settings(
    data: PurchaseWorkflowSettingsWrite,
    scope: PurchaseWorkflowSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseWorkflowSettingsResponse]:
    """Replace which buying stages this firm fills in by hand."""
    settings = PurchaseWorkflowService(db).update_settings(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=settings)


# Declared above `/{order_id}` for the same reason as the settings above.
@router.get(
    "/approval-limits",
    response_model=ApiResponse[RolePurchaseApprovalLimitsResponse],
)
def get_purchase_approval_limits(
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RolePurchaseApprovalLimitsResponse]:
    """List the largest order each role may approve (backlog 68 row 4)."""
    rows = PurchaseApprovalLimitService(db).limits(scope.firm_id)
    return ApiResponse(data=_approval_limits_response(rows))


@router.put(
    "/approval-limits",
    response_model=ApiResponse[RolePurchaseApprovalLimitsResponse],
)
def replace_purchase_approval_limits(
    data: RolePurchaseApprovalLimitsWrite,
    scope: PurchaseWorkflowSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RolePurchaseApprovalLimitsResponse]:
    """Replace the whole list; a role left out has no limit afterwards.

    Under `PURCHASE_MANAGE_SETTINGS`, like the buying stages: whoever an
    approval limit constrains is not the one who should be able to lift it.
    """
    rows = PurchaseApprovalLimitService(db).replace_limits(
        [(item.role_code, item.max_order_amount) for item in data.limits],
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=_approval_limits_response(rows))


def _approval_limits_response(
    rows: list[RolePurchaseApprovalLimit],
) -> RolePurchaseApprovalLimitsResponse:
    """Describe the firm's approval limits."""
    return RolePurchaseApprovalLimitsResponse(
        limits=[
            RolePurchaseApprovalLimitItem(
                role_code=row.role_code, max_order_amount=row.max_order_amount
            )
            for row in rows
        ]
    )


class BelowReorderRecord(BaseModel):
    """One product in one warehouse at or below its reorder level (42.9)."""

    model_config = ConfigDict(from_attributes=True)

    branch_id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_code: str
    product_name: str
    available_quantity: Decimal
    reorder_level: Decimal
    maximum_level: Decimal | None
    on_order_quantity: Decimal
    suggested_quantity: Decimal
    supplier_id: UUID | None
    supplier_name: str | None
    unit_price: Decimal


class ReorderPickWrite(BaseModel):
    """One row to order; quantity and supplier default to the suggestion."""

    model_config = ConfigDict(extra="forbid")

    warehouse_id: UUID
    product_id: UUID
    quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )
    supplier_id: UUID | None = None


class ReorderDraftsRequest(BaseModel):
    """The rows a buyer ticked on Below reorder level."""

    model_config = ConfigDict(extra="forbid")

    items: list[ReorderPickWrite] = Field(min_length=1, max_length=1000)


@router.get(
    "/reports/below-reorder",
    response_model=PaginatedResponse[BelowReorderRecord],
)
def below_reorder_level(
    scope: PurchaseReportScope,
    warehouse_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BelowReorderRecord]:
    """List stock at or below its reorder level, with what to order (42.9)."""
    window = ReportWindow(None, None, page, page_size)
    rows = ReorderService(db).below_reorder(scope.firm_id, warehouse_id=warehouse_id)
    return window.respond([BelowReorderRecord.model_validate(row) for row in rows])


@router.post(
    "/reorder-drafts",
    response_model=ApiResponse[list[PurchaseOrderResponse]],
    status_code=status.HTTP_201_CREATED,
)
def raise_reorder_drafts(
    data: ReorderDraftsRequest,
    scope: PurchaseCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderResponse]]:
    """Raise one DRAFT order per supplier per warehouse for the ticked rows."""
    service = ReorderService(db)
    orders = service.raise_drafts(
        scope.firm_id,
        [
            ReorderPick(
                warehouse_id=item.warehouse_id,
                product_id=item.product_id,
                quantity=item.quantity,
                supplier_id=item.supplier_id,
            )
            for item in data.items
        ],
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=PurchaseService(db).order_responses(orders),
        message=f"{len(orders)} draft purchase order(s) raised.",
    )


@router.post("/bulk-approve", response_model=ApiResponse[BulkActionResult])
def bulk_approve_purchase_orders(
    data: BulkApproveRequest,
    scope: PurchaseApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Approve the ticked submitted orders, each on its own (backlog 56 A).

    Each goes through `approve_order` exactly as a single approval does, under
    the same `PURCHASE_APPROVE`; a draft not yet submitted is refused with the
    service's reason and the rest are approved.
    """
    service = PurchaseService(db)
    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda order_id: service.get_order(order_id, firm_scope=scope.firm_id),
            act=lambda order_id: service.approve_order(
                order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
            ),
            number=lambda row: row.po_number,
        )
    )


@router.post("/bulk-cancel", response_model=ApiResponse[BulkActionResult])
def bulk_cancel_purchase_orders(
    data: BulkCancelRequest,
    scope: PurchaseCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkActionResult]:
    """Cancel the ticked orders with one reason, each on its own (backlog 56 A)."""
    service = PurchaseService(db)
    return ApiResponse(
        data=run_each(
            db,
            data.items,
            load=lambda order_id: service.get_order(order_id, firm_scope=scope.firm_id),
            act=lambda order_id: service.cancel_order(
                order_id,
                firm_scope=scope.firm_id,
                actor_id=scope.actor_id,
                reason=data.reason,
            ),
            number=lambda row: row.po_number,
        )
    )


@router.get("/{order_id}", response_model=ApiResponse[PurchaseOrderResponse])
def get_purchase_order(
    order_id: UUID,
    scope: PurchaseViewScope,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Return purchase order."""
    service = PurchaseService(db)
    row = service.get_order(
        order_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.put("/{order_id}", response_model=ApiResponse[PurchaseOrderResponse])
def update_purchase_order(
    order_id: UUID,
    data: PurchaseOrderUpdate,
    scope: PurchaseUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PurchaseOrderResponse]:
    """Change purchase order."""
    service = PurchaseService(db)
    assert_version(
        service.get_order(order_id, firm_scope=scope.firm_id).version, expected_version
    )
    row = service.update_order(
        order_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    order_id: UUID,
    scope: PurchaseDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete purchase order."""
    PurchaseService(db).delete_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{order_id}/restore", response_model=ApiResponse[PurchaseOrderResponse])
def restore_purchase_order(
    order_id: UUID,
    scope: PurchaseRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Restore purchase order."""
    service = PurchaseService(db)
    row = service.restore_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/submit", response_model=ApiResponse[PurchaseOrderResponse])
def submit_purchase_order(
    order_id: UUID,
    scope: PurchaseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Send a draft purchase order for approval."""
    service = PurchaseService(db)
    row = service.submit_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/approve", response_model=ApiResponse[PurchaseOrderResponse])
def approve_purchase_order(
    order_id: UUID,
    scope: PurchaseApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Approve a submitted purchase order.

    Takes `PURCHASE_APPROVE`, deliberately a different code from the
    `PURCHASE_UPDATE` that submitting needs: the point of the two steps is
    that the person who raises an order need not be the person who commits
    the firm to it.
    """
    service = PurchaseService(db)
    row = service.approve_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/mark-sent", response_model=ApiResponse[PurchaseOrderResponse])
def mark_purchase_order_sent(
    order_id: UUID,
    request: PurchaseOrderSentRequest,
    scope: PurchaseUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Record that an approved order was sent to the supplier, and how."""
    service = PurchaseService(db)
    row = service.mark_sent(
        order_id, via=request.via, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/cancel", response_model=ApiResponse[PurchaseOrderResponse])
def cancel_purchase_order(
    order_id: UUID,
    request: ActionReasonRequest,
    scope: PurchaseCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Cancel purchase order."""
    service = PurchaseService(db)
    row = service.cancel_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=request.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/close", response_model=ApiResponse[PurchaseOrderResponse])
def close_purchase_order(
    order_id: UUID,
    request: ActionReasonRequest,
    scope: PurchaseApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PurchaseOrderResponse]:
    """Close purchase order."""
    service = PurchaseService(db)
    row = service.close_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=request.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.get(
    "/{order_id}/history",
    response_model=ApiResponse[list[PurchaseOrderHistoryResponse]],
)
def purchase_order_history(
    order_id: UUID,
    scope: PurchaseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PurchaseOrderHistoryResponse]]:
    """Purchase order history."""
    rows = PurchaseService(db).order_history(
        order_id=order_id, firm_scope=scope.firm_id
    )
    return ApiResponse(
        data=[PurchaseOrderHistoryResponse.model_validate(item) for item in rows]
    )
