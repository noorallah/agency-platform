"""Firm-scoped REST endpoints for batch, lot, serial and expiry management."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

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
from app.business.gating import require_feature
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1/batch-serial",
    tags=["Batch & Serial"],
    responses=STANDARD_ERROR_RESPONSES,
)


BatchViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("BATCH_VIEW")]
BatchCreateScope = Annotated[ResolvedFirmScope, firm_permission_scope("BATCH_CREATE")]
BatchUpdateScope = Annotated[ResolvedFirmScope, firm_permission_scope("BATCH_UPDATE")]
BatchDeleteScope = Annotated[ResolvedFirmScope, firm_permission_scope("BATCH_DELETE")]
SerialViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SERIAL_VIEW")]
SerialCreateScope = Annotated[ResolvedFirmScope, firm_permission_scope("SERIAL_CREATE")]
SerialUpdateScope = Annotated[ResolvedFirmScope, firm_permission_scope("SERIAL_UPDATE")]
SerialDeleteScope = Annotated[ResolvedFirmScope, firm_permission_scope("SERIAL_DELETE")]


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
    """Return a page of batches for the firm in scope."""
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
    """Return batch counts, including those past their expiry date."""
    summary = BatchSerialService(db).batch_summary(firm_scope=scope.firm_id)
    return ApiResponse(data=summary)


@router.get("/batches/expiry-dashboard", response_model=ApiResponse[ExpiryDashboard])
def expiry_dashboard(
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpiryDashboard]:
    """Return expiry counts across the reporting windows."""
    dashboard = BatchSerialService(db).expiry_dashboard(firm_scope=scope.firm_id)
    return ApiResponse(data=dashboard)


@router.get("/batches/{batch_id}", response_model=ApiResponse[BatchResponse])
def get_batch(
    batch_id: UUID,
    scope: BatchViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BatchResponse]:
    """Return one batch the firm owns."""
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
    """Record a batch of a product."""
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
    """Change a batch."""
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
    """Soft delete a batch."""
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
    """Return a page of production lots."""
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
    """Record a production lot."""
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
    """Return one lot the firm owns."""
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
    """Change a lot."""
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
    """Soft delete a lot."""
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
    """Return a page of serial numbers."""
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
    """Record a serial number."""
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
    """Return one serial number the firm owns."""
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
    """Change a serial number."""
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
    """Soft delete a serial number."""
    BatchSerialService(db).delete_serial(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, serial_id=serial_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
