"""Firm-scoped REST endpoints for enterprise batch, lot, serial, and expiry management."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.gating import require_feature
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.batch_serial.schemas import (
    BatchCreate,
    BatchListFilters,
    BatchResponse,
    BatchStatus,
    BatchSummary,
    BatchUpdate,
    ExpiryDashboard,
    LotCreate,
    LotListFilters,
    LotResponse,
    LotStatus,
    LotType,
    LotUpdate,
    SerialCreate,
    SerialListFilters,
    SerialResponse,
    SerialStatus,
    SerialUpdate,
)
from app.batch_serial.services import BatchSerialService

router = APIRouter(
    prefix="/api/v1/batch-serial",
    tags=["Batch & Serial"],
    responses=STANDARD_ERROR_RESPONSES,
)


class BatchSerialScope:
    """Carry the authenticated principal and resolved firm scope."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Batch/serial operations require a user principal.")
        return self.principal.subject


def batch_serial_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> BatchSerialScope:
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
        return BatchSerialScope(principal, x_firm_id)
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
    return BatchSerialScope(principal, x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[BatchSerialScope, Depends(batch_serial_scope)],
    ) -> BatchSerialScope:
        return scope

    return Depends(dependency)


BatchViewScope = Annotated[BatchSerialScope, _permission("BATCH_VIEW")]
BatchCreateScope = Annotated[BatchSerialScope, _permission("BATCH_CREATE")]
BatchUpdateScope = Annotated[BatchSerialScope, _permission("BATCH_UPDATE")]
BatchDeleteScope = Annotated[BatchSerialScope, _permission("BATCH_DELETE")]
SerialViewScope = Annotated[BatchSerialScope, _permission("SERIAL_VIEW")]
SerialCreateScope = Annotated[BatchSerialScope, _permission("SERIAL_CREATE")]
SerialUpdateScope = Annotated[BatchSerialScope, _permission("SERIAL_UPDATE")]
SerialDeleteScope = Annotated[BatchSerialScope, _permission("SERIAL_DELETE")]


# ── Batch endpoints ──────────────────────────────────────────────────────────


@router.get("/batches", response_model=PaginatedResponse[BatchResponse])
def list_batches(
    scope: BatchViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at", "updated_at", "batch_number", "expiry_date", "status"
    ] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    product_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    branch_id: UUID | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    expiry_before: str | None = None,
    expiry_after: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BatchResponse]:
    from datetime import date as _date

    params = PaginationParams(page=page, page_size=page_size)
    filters = BatchListFilters(
        product_id=product_id,
        warehouse_id=warehouse_id,
        branch_id=branch_id,
        status=BatchStatus(status_value) if status_value else None,
        expiry_before=_date.fromisoformat(expiry_before) if expiry_before else None,
        expiry_after=_date.fromisoformat(expiry_after) if expiry_after else None,
    )
    service = BatchSerialService(db)
    rows, total = service.list_batches(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[BatchResponse.model_validate(r) for r in rows],
        pagination=params.metadata(total),
    )


@router.get("/batches/summary", response_model=ApiResponse[BatchSummary])
def batch_summary(
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchSummary]:
    summary = BatchSerialService(db).batch_summary(firm_scope=scope.firm_id)
    return ApiResponse(data=summary)


@router.get("/batches/expiry-dashboard", response_model=ApiResponse[ExpiryDashboard])
def expiry_dashboard(
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpiryDashboard]:
    dashboard = BatchSerialService(db).expiry_dashboard(firm_scope=scope.firm_id)
    return ApiResponse(data=dashboard)


@router.get("/batches/{batch_id}", response_model=ApiResponse[BatchResponse])
def get_batch(
    batch_id: UUID,
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchResponse]:
    record = BatchSerialService(db).get_batch(
        firm_scope=scope.firm_id, batch_id=batch_id
    )
    return ApiResponse(data=BatchResponse.model_validate(record))


@router.post(
    "/batches",
    response_model=ApiResponse[BatchResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("BATCH_TRACKING")],
)
def create_batch(
    data: BatchCreate,
    scope: BatchCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchResponse]:
    record = BatchSerialService(db).create_batch(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, data=data
    )
    return ApiResponse(data=BatchResponse.model_validate(record))


@router.put(
    "/batches/{batch_id}",
    response_model=ApiResponse[BatchResponse],
    dependencies=[require_feature("BATCH_TRACKING")],
)
def update_batch(
    batch_id: UUID,
    data: BatchUpdate,
    scope: BatchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchResponse]:
    record = BatchSerialService(db).update_batch(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, batch_id=batch_id, data=data
    )
    return ApiResponse(data=BatchResponse.model_validate(record))


@router.delete(
    "/batches/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_feature("BATCH_TRACKING")],
)
def delete_batch(
    batch_id: UUID,
    scope: BatchDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    BatchSerialService(db).delete_batch(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, batch_id=batch_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Lot endpoints ────────────────────────────────────────────────────────────


@router.get("/lots", response_model=PaginatedResponse[LotResponse])
def list_lots(
    scope: BatchViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal["created_at", "updated_at", "lot_number", "status"] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    product_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    branch_id: UUID | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    lot_type_value: str | None = Query(default=None, alias="lot_type"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[LotResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = LotListFilters(
        product_id=product_id,
        warehouse_id=warehouse_id,
        branch_id=branch_id,
        status=LotStatus(status_value) if status_value else None,
        lot_type=LotType(lot_type_value) if lot_type_value else None,
    )
    service = BatchSerialService(db)
    rows, total = service.list_lots(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[LotResponse.model_validate(r) for r in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/lots",
    response_model=ApiResponse[LotResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("BATCH_TRACKING")],
)
def create_lot(
    data: LotCreate,
    scope: BatchCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LotResponse]:
    record = BatchSerialService(db).create_lot(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, data=data
    )
    return ApiResponse(data=LotResponse.model_validate(record))


@router.get("/lots/{lot_id}", response_model=ApiResponse[LotResponse])
def get_lot(
    lot_id: UUID,
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LotResponse]:
    record = BatchSerialService(db).get_lot(firm_scope=scope.firm_id, lot_id=lot_id)
    return ApiResponse(data=LotResponse.model_validate(record))


@router.put(
    "/lots/{lot_id}",
    response_model=ApiResponse[LotResponse],
    dependencies=[require_feature("BATCH_TRACKING")],
)
def update_lot(
    lot_id: UUID,
    data: LotUpdate,
    scope: BatchUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LotResponse]:
    record = BatchSerialService(db).update_lot(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, lot_id=lot_id, data=data
    )
    return ApiResponse(data=LotResponse.model_validate(record))


@router.delete(
    "/lots/{lot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_feature("BATCH_TRACKING")],
)
def delete_lot(
    lot_id: UUID,
    scope: BatchDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    BatchSerialService(db).delete_lot(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, lot_id=lot_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Serial endpoints ──────────────────────────────────────────────────────────


@router.get("/serials", response_model=PaginatedResponse[SerialResponse])
def list_serials(
    scope: SerialViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_by: Literal[
        "created_at", "updated_at", "serial_number", "status"
    ] = "updated_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    product_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    branch_id: UUID | None = None,
    batch_id: UUID | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SerialResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = SerialListFilters(
        product_id=product_id,
        warehouse_id=warehouse_id,
        branch_id=branch_id,
        batch_id=batch_id,
        status=SerialStatus(status_value) if status_value else None,
    )
    service = BatchSerialService(db)
    rows, total = service.list_serials(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[SerialResponse.model_validate(r) for r in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/serials",
    response_model=ApiResponse[SerialResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("SERIAL_NUMBER")],
)
def create_serial(
    data: SerialCreate,
    scope: SerialCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SerialResponse]:
    record = BatchSerialService(db).create_serial(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, data=data
    )
    return ApiResponse(data=SerialResponse.model_validate(record))


@router.get("/serials/{serial_id}", response_model=ApiResponse[SerialResponse])
def get_serial(
    serial_id: UUID,
    scope: SerialViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SerialResponse]:
    record = BatchSerialService(db).get_serial(
        firm_scope=scope.firm_id, serial_id=serial_id
    )
    return ApiResponse(data=SerialResponse.model_validate(record))


@router.put(
    "/serials/{serial_id}",
    response_model=ApiResponse[SerialResponse],
    dependencies=[require_feature("SERIAL_NUMBER")],
)
def update_serial(
    serial_id: UUID,
    data: SerialUpdate,
    scope: SerialUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SerialResponse]:
    record = BatchSerialService(db).update_serial(
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        serial_id=serial_id,
        data=data,
    )
    return ApiResponse(data=SerialResponse.model_validate(record))


@router.delete(
    "/serials/{serial_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_feature("SERIAL_NUMBER")],
)
def delete_serial(
    serial_id: UUID,
    scope: SerialDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    BatchSerialService(db).delete_serial(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, serial_id=serial_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
