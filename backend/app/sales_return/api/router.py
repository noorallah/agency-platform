"""Firm-scoped REST endpoints for sales returns."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.sales_return.schemas import (
    SalesReturnByCustomerRecord,
    SalesReturnByProductRecord,
    SalesReturnCreate,
    SalesReturnImportRequest,
    SalesReturnListFilters,
    SalesReturnReconciliationRecord,
    SalesReturnRegisterRecord,
    SalesReturnResponse,
    SalesReturnStatus,
    SalesReturnSummary,
    SalesReturnUpdate,
)
from app.sales_return.services import SalesReturnService

router = APIRouter(
    prefix="/api/v1/sales-returns",
    tags=["Sales Returns"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ActionReasonRequest(BaseModel):
    """Carry the optional reason a lifecycle action was taken for."""

    reason: str | None = Field(default=None, max_length=500)


# `SALES_RETURN` has been a seeded permission code since the identity seed was
# written, held by SALES_MANAGER and never enforced anywhere: it was reserved
# for exactly this document. Raising a return is the act it names, so it gates
# creation while the ordinary sales codes gate the rest.
SalesReturnViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]
SalesReturnCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_RETURN")
]
SalesReturnUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")
]
SalesReturnApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")
]
SalesReturnCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CANCEL")
]
SalesReturnImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_IMPORT")
]
SalesReturnExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_EXPORT")
]


def _filters(
    *,
    customer_id: UUID | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    status_value: SalesReturnStatus | None,
    return_from: date | None,
    return_to: date | None,
    include_deleted: bool,
) -> SalesReturnListFilters:
    try:
        return SalesReturnListFilters.model_validate(
            {
                "customer_id": customer_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "status": status_value,
                "return_from": return_from,
                "return_to": return_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[SalesReturnResponse])
def list_sales_returns(
    scope: SalesReturnViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "return_number",
        "return_date",
        "warehouse_id",
        "grand_total",
        "status",
        "created_at",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    customer_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[SalesReturnStatus | None, Query(alias="status")] = None,
    return_from: date | None = None,
    return_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SalesReturnResponse]:
    """List sales returns for the visible firm scope."""
    params = PaginationParams(page=page, page_size=page_size)
    service = SalesReturnService(db)
    rows, total = service.list_returns(
        firm_scope=scope.firm_id,
        filters=_filters(
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            return_from=return_from,
            return_to=return_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.return_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[SalesReturnSummary])
def get_sales_return_summary(
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnSummary]:
    """Summarise sales returns for the visible firm scope."""
    return ApiResponse(data=SalesReturnService(db).summary(firm_scope=scope.firm_id))


@router.get(
    "/reports/register",
    response_model=ApiResponse[list[SalesReturnRegisterRecord]],
)
def sales_return_register(
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesReturnRegisterRecord]]:
    """Every sales return raised, with what it was worth."""
    return ApiResponse(
        data=SalesReturnService(db).register_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-customer",
    response_model=ApiResponse[list[SalesReturnByCustomerRecord]],
)
def sales_returns_by_customer(
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesReturnByCustomerRecord]]:
    """Total returned value and count per customer."""
    return ApiResponse(
        data=SalesReturnService(db).by_customer_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-product",
    response_model=ApiResponse[list[SalesReturnByProductRecord]],
)
def sales_returns_by_product(
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesReturnByProductRecord]]:
    """Total returned quantity and value per product."""
    return ApiResponse(
        data=SalesReturnService(db).by_product_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/reconciliation",
    response_model=ApiResponse[list[SalesReturnReconciliationRecord]],
)
def sales_return_reconciliation(
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesReturnReconciliationRecord]]:
    """Return lines set against the documents they were dispatched on."""
    return ApiResponse(
        data=SalesReturnService(db).reconciliation_report(firm_scope=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[SalesReturnResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_sales_return(
    payload: SalesReturnCreate,
    scope: SalesReturnCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Create one sales return in draft."""
    service = SalesReturnService(db)
    row = service.create_return(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.return_response(row))


@router.get("/export")
def export_sales_returns(
    scope: SalesReturnExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export matching sales returns as CSV."""
    csv_content = SalesReturnService(db).export_returns_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_returns.csv"},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[SalesReturnResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_sales_returns(
    scope: SalesReturnImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[SalesReturnResponse]]:
    """Import a validated batch of sales returns atomically.

    JSON only, as for purchase returns: a return line names the delivery-note
    or invoice line it came off, so a flat CSV row cannot express one without
    inventing a way to identify the source, and a source picked wrongly puts
    stock back against the wrong document.
    """
    if format != "json":
        raise ValidationError("Only JSON import is supported for sales returns.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = SalesReturnService(db)
    rows = service.import_returns(
        SalesReturnImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.return_response(item) for item in rows])


@router.get("/{return_id}", response_model=ApiResponse[SalesReturnResponse])
def get_sales_return(
    return_id: UUID,
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Return one sales return."""
    service = SalesReturnService(db)
    row = service.get_return(return_id, firm_scope=scope.firm_id)
    return ApiResponse(data=service.return_response(row))


@router.get(
    "/{return_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def get_sales_return_history(
    return_id: UUID,
    scope: SalesReturnViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Return the lifecycle history of one sales return."""
    events = SalesReturnService(db).timeline(return_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=[
            DocumentLifecycleEventResponse.model_validate(event, from_attributes=True)
            for event in events
        ]
    )


@router.put("/{return_id}", response_model=ApiResponse[SalesReturnResponse])
def update_sales_return(
    return_id: UUID,
    payload: SalesReturnUpdate,
    scope: SalesReturnUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Replace one draft sales return."""
    service = SalesReturnService(db)
    row = service.update_return(
        return_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/approve", response_model=ApiResponse[SalesReturnResponse])
def approve_sales_return(
    return_id: UUID,
    scope: SalesReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Approve one draft sales return."""
    service = SalesReturnService(db)
    row = service.approve_return(
        return_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/complete", response_model=ApiResponse[SalesReturnResponse])
def complete_sales_return(
    return_id: UUID,
    scope: SalesReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Take the goods back into stock and credit the customer."""
    service = SalesReturnService(db)
    row = service.complete_return(
        return_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/cancel", response_model=ApiResponse[SalesReturnResponse])
def cancel_sales_return(
    return_id: UUID,
    payload: ActionReasonRequest,
    scope: SalesReturnCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Cancel one sales return, undoing it if it had completed."""
    service = SalesReturnService(db)
    row = service.cancel_return(
        return_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    return ApiResponse(data=service.return_response(row))


@router.post("/{return_id}/close", response_model=ApiResponse[SalesReturnResponse])
def close_sales_return(
    return_id: UUID,
    payload: ActionReasonRequest,
    scope: SalesReturnApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesReturnResponse]:
    """Close one completed sales return."""
    service = SalesReturnService(db)
    row = service.close_return(
        return_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    return ApiResponse(data=service.return_response(row))


@router.delete("/{return_id}", response_model=ApiResponse[None])
def delete_sales_return(
    return_id: UUID,
    scope: SalesReturnCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Soft-delete one draft sales return."""
    SalesReturnService(db).delete_return(
        return_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Sales return deleted.")
