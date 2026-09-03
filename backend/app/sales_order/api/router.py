"""Firm-scoped REST endpoints for enterprise sales orders."""

from datetime import date
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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.sales_order.schemas import (
    SalesOrderBackOrderRecord,
    SalesOrderByCustomerRecord,
    SalesOrderBySalesmanRecord,
    SalesOrderByTerritoryRecord,
    SalesOrderCreate,
    SalesOrderImportRequest,
    SalesOrderListFilters,
    SalesOrderPendingRecord,
    SalesOrderRegisterRecord,
    SalesOrderResponse,
    SalesOrderStatus,
    SalesOrderSummary,
    SalesWorkflowSettingsResponse,
    SalesWorkflowSettingsWrite,
)
from app.sales_order.services import SalesOrderService, SalesWorkflowService

router = APIRouter(
    prefix="/api/v1/sales-orders",
    tags=["Sales Orders"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Carry the optional reason a lifecycle action was taken for."""

    reason: str | None = Field(default=None, max_length=500)


SalesOrderViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]
SalesOrderCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CREATE")
]
SalesOrderUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")
]
SalesOrderApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")
]
SalesOrderCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CANCEL")
]
SalesOrderExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_EXPORT")
]
SalesOrderImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_IMPORT")
]
#: Reading the configuration is not a privilege -- somebody whose screens the
#: setting moves should be able to see the rule behind that. Changing it is.
SalesWorkflowSettingsScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_MANAGE_SETTINGS")
]


def _filters(
    *,
    customer_id: UUID | None,
    salesman_id: UUID | None,
    territory_id: UUID | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    status_value: SalesOrderStatus | None,
    order_from: date | None,
    order_to: date | None,
    include_deleted: bool,
) -> SalesOrderListFilters:
    try:
        return SalesOrderListFilters.model_validate(
            {
                "customer_id": customer_id,
                "salesman_id": salesman_id,
                "territory_id": territory_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "status": status_value,
                "order_from": order_from,
                "order_to": order_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[SalesOrderResponse])
def list_sales_orders(
    scope: SalesOrderViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "order_number",
        "order_date",
        "delivery_date",
        "grand_total",
        "status",
        "created_at",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    customer_id: UUID | None = None,
    salesman_id: UUID | None = None,
    territory_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[SalesOrderStatus | None, Query(alias="status")] = None,
    order_from: date | None = None,
    order_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SalesOrderResponse]:
    """List sales orders for the visible firm scope."""
    params = PaginationParams(page=page, page_size=page_size)
    service = SalesOrderService(db)
    rows, total = service.list_orders(
        firm_scope=scope.firm_id,
        filters=_filters(
            customer_id=customer_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            order_from=order_from,
            order_to=order_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.order_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[SalesOrderSummary])
def sales_order_summary(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderSummary]:
    """Return aggregate sales order values for the visible firm scope."""
    return ApiResponse(data=SalesOrderService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[SalesOrderResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_sales_order(
    data: SalesOrderCreate,
    scope: SalesOrderCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Create one sales order."""
    service = SalesOrderService(db)
    row = service.create_order(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.order_response(row))


# Declared above the `/{{id}}` route below on purpose: FastAPI matches in
# declaration order, so that route read "export" as an id and answered 422.
# Unreachable from the day it was written until 2026-08-22.
@router.get("/export")
def export_sales_orders(
    scope: SalesOrderExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export matching sales orders as CSV."""
    csv_content = SalesOrderService(db).export_orders_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_orders.csv"},
    )


# Both declared above `/{order_id}` for the same reason `/export` is: FastAPI
# matches in declaration order, and below it "workflow-settings" is read as an
# order id and answered 422. Nine routes across eight routers shipped that way.
@router.get(
    "/workflow-settings",
    response_model=ApiResponse[SalesWorkflowSettingsResponse],
)
def get_sales_workflow_settings(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesWorkflowSettingsResponse]:
    """Report which sales stages this firm fills in by hand."""
    return ApiResponse(data=SalesWorkflowService(db).settings_response(scope.firm_id))


@router.put(
    "/workflow-settings",
    response_model=ApiResponse[SalesWorkflowSettingsResponse],
)
def update_sales_workflow_settings(
    data: SalesWorkflowSettingsWrite,
    scope: SalesWorkflowSettingsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesWorkflowSettingsResponse]:
    """Replace which sales stages this firm fills in by hand."""
    settings = SalesWorkflowService(db).update_settings(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=settings)


@router.put("/{order_id}", response_model=ApiResponse[SalesOrderResponse])
def update_sales_order(
    order_id: UUID,
    data: SalesOrderCreate,
    scope: SalesOrderUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[SalesOrderResponse]:
    """Replace one sales order."""
    service = SalesOrderService(db)
    assert_version(
        service.get_order(order_id, firm_scope=scope.firm_id).version, expected_version
    )
    row = service.update_order(
        order_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/approve", response_model=ApiResponse[SalesOrderResponse])
def approve_sales_order(
    order_id: UUID,
    scope: SalesOrderApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Approve one sales order."""
    service = SalesOrderService(db)
    row = service.approve_order(
        order_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/cancel", response_model=ApiResponse[SalesOrderResponse])
def cancel_sales_order(
    order_id: UUID,
    data: ActionReasonRequest,
    scope: SalesOrderCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Cancel one sales order."""
    service = SalesOrderService(db)
    row = service.cancel_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.post("/{order_id}/hold", response_model=ApiResponse[SalesOrderResponse])
def hold_sales_order(
    order_id: UUID,
    data: ActionReasonRequest,
    scope: SalesOrderApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Stop an order progressing, without unwinding anything.

    The status is untouched, so releasing puts the order back exactly where it
    was rather than guessing. The stock stays reserved: holding says "not yet",
    not "never", and releasing the goods would let another order take them
    while this one waits.
    """
    service = SalesOrderService(db)
    row = service.hold_order(
        order_id,
        reason=data.reason or "",
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(
        data=service.order_response(row),
        message=f"{row.order_number} is on hold.",
    )


@router.post("/{order_id}/release", response_model=ApiResponse[SalesOrderResponse])
def release_sales_order(
    order_id: UUID,
    data: ActionReasonRequest,
    scope: SalesOrderApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Lift a hold, leaving the order exactly where it was."""
    service = SalesOrderService(db)
    row = service.release_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        remarks=data.reason,
    )
    return ApiResponse(
        data=service.order_response(row),
        message=f"{row.order_number} released.",
    )


@router.post("/{order_id}/close", response_model=ApiResponse[SalesOrderResponse])
def close_sales_order(
    order_id: UUID,
    data: ActionReasonRequest,
    scope: SalesOrderApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Close one sales order."""
    service = SalesOrderService(db)
    row = service.close_order(
        order_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.order_response(row))


@router.get("/{order_id}", response_model=ApiResponse[SalesOrderResponse])
def get_sales_order(
    order_id: UUID,
    scope: SalesOrderViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesOrderResponse]:
    """Return one sales order."""
    service = SalesOrderService(db)
    row = service.get_order(order_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.order_response(row))


@router.get(
    "/{order_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def sales_order_history(
    order_id: UUID,
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Return the lifecycle timeline for one sales order."""
    rows = SalesOrderService(db).timeline(
        order_id=order_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(
        data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/register", response_model=ApiResponse[list[SalesOrderRegisterRecord]]
)
def sales_order_register(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderRegisterRecord]]:
    """Return the sales order register report for the visible firm scope."""
    return ApiResponse(
        data=SalesOrderService(db).register_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/pending", response_model=ApiResponse[list[SalesOrderPendingRecord]]
)
def pending_sales_orders(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderPendingRecord]]:
    """List orders still open: draft or approved, not yet closed."""
    return ApiResponse(
        data=SalesOrderService(db).pending_orders(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/back-orders", response_model=ApiResponse[list[SalesOrderBackOrderRecord]]
)
def back_order_report(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderBackOrderRecord]]:
    """Return the back order report for the visible firm scope."""
    return ApiResponse(data=SalesOrderService(db).back_orders(firm_scope=scope.firm_id))


@router.get(
    "/reports/by-customer", response_model=ApiResponse[list[SalesOrderByCustomerRecord]]
)
def orders_by_customer(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderByCustomerRecord]]:
    """Total order value and count per customer, cancellations excluded."""
    return ApiResponse(
        data=SalesOrderService(db).orders_by_customer(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-salesman", response_model=ApiResponse[list[SalesOrderBySalesmanRecord]]
)
def orders_by_salesman(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderBySalesmanRecord]]:
    """Total order value and count per salesman, cancellations excluded."""
    return ApiResponse(
        data=SalesOrderService(db).orders_by_salesman(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-territory",
    response_model=ApiResponse[list[SalesOrderByTerritoryRecord]],
)
def orders_by_territory(
    scope: SalesOrderViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesOrderByTerritoryRecord]]:
    """Total order value and count per territory, cancellations excluded."""
    return ApiResponse(
        data=SalesOrderService(db).orders_by_territory(firm_scope=scope.firm_id)
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[SalesOrderResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_sales_orders(
    scope: SalesOrderImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[SalesOrderResponse]]:
    """Import a validated batch of sales orders atomically."""
    if format != "json":
        raise ValidationError("Only JSON import is supported for sales orders.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = SalesOrderService(db)
    rows = service.import_orders(
        SalesOrderImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.order_response(item) for item in rows])
