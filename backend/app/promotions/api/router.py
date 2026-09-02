"""Firm-scoped REST endpoints for customer promotions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.promotions.schemas import (
    PromotionEvaluationRequest,
    PromotionEvaluationResponse,
    PromotionResponse,
    PromotionStatus,
    PromotionWrite,
)
from app.promotions.services import PromotionService
from app.promotions.services.promotion_crud import PromotionCrudService

router = APIRouter(
    prefix="/api/v1/promotions",
    tags=["Promotions"],
    responses=STANDARD_ERROR_RESPONSES,
)

PromotionViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PROMOTION_VIEW")
]
PromotionManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PROMOTION_MANAGE")
]


@router.get("", response_model=PaginatedResponse[PromotionResponse])
def list_promotions(
    scope: PromotionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    status_value: Annotated[PromotionStatus | None, Query(alias="status")] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PromotionResponse]:
    """List the firm's promotions in the order they would be applied."""
    params = PaginationParams(page=page, page_size=page_size)
    service = PromotionCrudService(db)
    rows, total = service.list_promotions(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        status=status_value,
    )
    return PaginatedResponse(
        data=[service.promotion_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[PromotionResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_promotion(
    data: PromotionWrite,
    scope: PromotionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PromotionResponse]:
    """Record one promotion."""
    service = PromotionCrudService(db)
    row = service.create_promotion(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.promotion_response(row))


# Declared above `/{promotion_id}` on purpose: FastAPI matches in declaration
# order, and below it "simulate" is read as an id and answered 422. Nine routes
# across eight routers shipped that way before the guard existed.
@router.post("/simulate", response_model=ApiResponse[PromotionEvaluationResponse])
def simulate_promotions(
    data: PromotionEvaluationRequest,
    scope: PromotionViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PromotionEvaluationResponse]:
    """Answer what a document would earn, without saving anything.

    This endpoint owns the commit. `PromotionService.evaluate` never commits,
    because every sales document calls it mid-write.
    """
    result = PromotionService(db).evaluate(data, firm_scope=scope.firm_id)
    db.commit()
    return ApiResponse(data=result)


@router.get("/{promotion_id}", response_model=ApiResponse[PromotionResponse])
def get_promotion(
    promotion_id: UUID,
    scope: PromotionViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PromotionResponse]:
    """Return one promotion."""
    service = PromotionCrudService(db)
    row = service.get_promotion(promotion_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.promotion_response(row))


@router.put("/{promotion_id}", response_model=ApiResponse[PromotionResponse])
def update_promotion(
    promotion_id: UUID,
    data: PromotionWrite,
    scope: PromotionManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PromotionResponse]:
    """Edit a draft, or supersede a published promotion with a new version."""
    service = PromotionCrudService(db)
    current = service.get_promotion(promotion_id, firm_scope=scope.firm_id)
    assert_version(current.version, expected_version)
    row = service.update_promotion(
        promotion_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.promotion_response(row))


@router.delete("/{promotion_id}", response_model=ApiResponse[dict[str, str]])
def delete_promotion(
    promotion_id: UUID,
    scope: PromotionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Retire one promotion."""
    PromotionCrudService(db).delete_promotion(
        promotion_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})
