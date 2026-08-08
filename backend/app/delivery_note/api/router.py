"""Firm-scoped REST endpoints for enterprise delivery notes."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.delivery_note.schemas import (
    DeliveryNoteByDimensionRecord,
    DeliveryNoteCreate,
    DeliveryNoteImportRequest,
    DeliveryNoteListFilters,
    DeliveryNoteOrderProgressRecord,
    DeliveryNoteRegisterRecord,
    DeliveryNoteResponse,
    DeliveryNoteStatus,
    DeliveryNoteSummary,
    DeliveryNoteUpdate,
)
from app.delivery_note.services import DeliveryNoteService
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.firms.models import Firm
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/delivery-notes",
    tags=["Delivery Notes"],
    responses=STANDARD_ERROR_RESPONSES,
)


class DeliveryNoteScope:
    """Carry principal and firm scope for delivery note handlers."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Delivery note operations require a user principal.")
        return self.principal.subject


class ActionReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def delivery_note_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> DeliveryNoteScope:
    if "platform_admin" in principal.roles:
        if x_firm_id is None:
            raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
        firm = db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return DeliveryNoteScope(principal=principal, firm_id=x_firm_id)
    if not isinstance(principal.subject, UUID) or x_firm_id is None:
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return DeliveryNoteScope(principal=principal, firm_id=x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[DeliveryNoteScope, Depends(delivery_note_scope)],
    ) -> DeliveryNoteScope:
        return scope

    return Depends(dependency)


DeliveryNoteViewScope = Annotated[DeliveryNoteScope, _permission("SALES_VIEW")]
DeliveryNoteCreateScope = Annotated[DeliveryNoteScope, _permission("SALES_CREATE")]
DeliveryNoteUpdateScope = Annotated[DeliveryNoteScope, _permission("SALES_UPDATE")]
DeliveryNoteApproveScope = Annotated[DeliveryNoteScope, _permission("SALES_APPROVE")]
DeliveryNoteCancelScope = Annotated[DeliveryNoteScope, _permission("SALES_CANCEL")]
DeliveryNoteExportScope = Annotated[DeliveryNoteScope, _permission("SALES_EXPORT")]
DeliveryNoteImportScope = Annotated[DeliveryNoteScope, _permission("SALES_IMPORT")]


def _filters(
    *,
    sales_order_id: UUID | None,
    customer_id: UUID | None,
    branch_id: UUID | None,
    warehouse_id: UUID | None,
    status_value: DeliveryNoteStatus | None,
    delivery_from: date | None,
    delivery_to: date | None,
    include_deleted: bool,
) -> DeliveryNoteListFilters:
    try:
        return DeliveryNoteListFilters.model_validate(
            {
                "sales_order_id": sales_order_id,
                "customer_id": customer_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "status": status_value,
                "delivery_from": delivery_from,
                "delivery_to": delivery_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[DeliveryNoteResponse])
def list_delivery_notes(
    scope: DeliveryNoteViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "delivery_note_number", "delivery_date", "status", "grand_total", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    sales_order_id: UUID | None = None,
    customer_id: UUID | None = None,
    branch_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    status_value: Annotated[DeliveryNoteStatus | None, Query(alias="status")] = None,
    delivery_from: date | None = None,
    delivery_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[DeliveryNoteResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    service = DeliveryNoteService(db)
    rows, total = service.list_notes(
        firm_scope=scope.firm_id,
        filters=_filters(
            sales_order_id=sales_order_id,
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            status_value=status_value,
            delivery_from=delivery_from,
            delivery_to=delivery_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.note_response(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[DeliveryNoteSummary])
def delivery_note_summary(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteSummary]:
    return ApiResponse(data=DeliveryNoteService(db).summary(firm_scope=scope.firm_id))


@router.post(
    "",
    response_model=ApiResponse[DeliveryNoteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_delivery_note(
    data: DeliveryNoteCreate,
    scope: DeliveryNoteCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.create_note(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.note_response(row))


@router.put("/{note_id}", response_model=ApiResponse[DeliveryNoteResponse])
def update_delivery_note(
    note_id: UUID,
    data: DeliveryNoteUpdate,
    scope: DeliveryNoteUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.update_note(
        note_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/approve", response_model=ApiResponse[DeliveryNoteResponse])
def approve_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.approve_note(
        note_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/dispatch", response_model=ApiResponse[DeliveryNoteResponse])
def dispatch_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.dispatch_note(
        note_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/complete", response_model=ApiResponse[DeliveryNoteResponse])
def complete_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.complete_note(
        note_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/cancel", response_model=ApiResponse[DeliveryNoteResponse])
def cancel_delivery_note(
    note_id: UUID,
    data: ActionReasonRequest,
    scope: DeliveryNoteCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.cancel_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.note_response(row))


@router.post("/{note_id}/close", response_model=ApiResponse[DeliveryNoteResponse])
def close_delivery_note(
    note_id: UUID,
    data: ActionReasonRequest,
    scope: DeliveryNoteApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    row = service.close_note(
        note_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=data.reason,
    )
    return ApiResponse(data=service.note_response(row))


@router.get("/{note_id}", response_model=ApiResponse[DeliveryNoteResponse])
def get_delivery_note(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[DeliveryNoteResponse]:
    service = DeliveryNoteService(db)
    return ApiResponse(
        data=service.note_response(service.get_note(note_id, firm_scope=scope.firm_id))
    )


@router.get(
    "/{note_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def delivery_note_history(
    note_id: UUID,
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    rows = DeliveryNoteService(db).timeline(
        note_id=note_id, firm_scope=scope.firm_id, page=1, page_size=200
    )[0]
    return ApiResponse(
        data=[DocumentLifecycleEventResponse.model_validate(item) for item in rows]
    )


@router.get(
    "/reports/register", response_model=ApiResponse[list[DeliveryNoteRegisterRecord]]
)
def delivery_note_register(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteRegisterRecord]]:
    return ApiResponse(
        data=DeliveryNoteService(db).register_report(firm_scope=scope.firm_id)
    )


@router.get("/reports/pending", response_model=ApiResponse[list[DeliveryNoteResponse]])
def pending_delivery_notes(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteResponse]]:
    service = DeliveryNoteService(db)
    return ApiResponse(
        data=[
            service.note_response(item)
            for item in service.pending_notes(firm_scope=scope.firm_id)
        ]
    )


@router.get(
    "/reports/partial",
    response_model=ApiResponse[list[DeliveryNoteOrderProgressRecord]],
)
def partial_delivery_report(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteOrderProgressRecord]]:
    return ApiResponse(
        data=DeliveryNoteService(db).partially_delivered_orders(
            firm_scope=scope.firm_id
        )
    )


@router.get(
    "/reports/by-route", response_model=ApiResponse[list[DeliveryNoteByDimensionRecord]]
)
def delivery_by_route(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteByDimensionRecord]]:
    return ApiResponse(
        data=DeliveryNoteService(db).by_route_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-salesman",
    response_model=ApiResponse[list[DeliveryNoteByDimensionRecord]],
)
def delivery_by_salesman(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteByDimensionRecord]]:
    return ApiResponse(
        data=DeliveryNoteService(db).by_salesman_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/by-warehouse",
    response_model=ApiResponse[list[DeliveryNoteByDimensionRecord]],
)
def delivery_by_warehouse(
    scope: DeliveryNoteViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DeliveryNoteByDimensionRecord]]:
    return ApiResponse(
        data=DeliveryNoteService(db).by_warehouse_report(firm_scope=scope.firm_id)
    )


@router.get("/export")
def export_delivery_notes(
    scope: DeliveryNoteExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_content = DeliveryNoteService(db).export_notes_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=delivery_notes.csv"},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[DeliveryNoteResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_delivery_notes(
    scope: DeliveryNoteImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[DeliveryNoteResponse]]:
    if format != "json":
        raise ValidationError("Only JSON import is supported for delivery notes.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = DeliveryNoteService(db)
    rows = service.import_notes(
        DeliveryNoteImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.note_response(item) for item in rows])
