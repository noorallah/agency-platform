"""Firm-scoped REST endpoints for sales targets."""

from datetime import date
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
from app.sales_targets.schemas import (
    SalesTargetAchievement,
    SalesTargetResponse,
    SalesTargetWrite,
)
from app.sales_targets.services import SalesTargetService

router = APIRouter(
    prefix="/api/v1/sales-targets",
    tags=["Sales Targets"],
    responses=STANDARD_ERROR_RESPONSES,
)

TargetViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_TARGET_VIEW")
]
TargetManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_TARGET_MANAGE")
]


# Declared above `/{target_id}`: FastAPI matches in declaration order, and
# below it "achievement" is read as a target id and answered 422.
@router.get("/achievement", response_model=ApiResponse[list[SalesTargetAchievement]])
def target_achievement(
    scope: TargetViewScope,
    from_date: date,
    to_date: date,
    salesman_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[SalesTargetAchievement]]:
    """Report every target overlapping the window, against what it took.

    Each is measured over its own period and on its own basis. The window only
    chooses which targets are worth reporting.
    """
    return ApiResponse(
        data=SalesTargetService(db).achievement(
            firm_scope=scope.firm_id,
            from_date=from_date,
            to_date=to_date,
            salesman_id=salesman_id,
        )
    )


@router.get("", response_model=PaginatedResponse[SalesTargetResponse])
def list_sales_targets(
    scope: TargetViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    salesman_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SalesTargetResponse]:
    """List this firm's targets, newest period first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = SalesTargetService(db)
    rows, total = service.list_targets(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        salesman_id=salesman_id,
    )
    names = service._names_for(  # noqa: SLF001
        {row.salesman_id for row in rows if row.salesman_id}, scope.firm_id
    )
    return PaginatedResponse(
        data=[service.target_response(row, names) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[SalesTargetResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_sales_target(
    data: SalesTargetWrite,
    scope: TargetManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesTargetResponse]:
    """Set one target."""
    service = SalesTargetService(db)
    row = service.create_target(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.target_response(row))


@router.get("/{target_id}", response_model=ApiResponse[SalesTargetResponse])
def get_sales_target(
    target_id: UUID,
    scope: TargetViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesTargetResponse]:
    """Return one target."""
    service = SalesTargetService(db)
    row = service.get_target(target_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.target_response(row))


@router.put("/{target_id}", response_model=ApiResponse[SalesTargetResponse])
def update_sales_target(
    target_id: UUID,
    data: SalesTargetWrite,
    scope: TargetManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesTargetResponse]:
    """Replace one target's numbers."""
    service = SalesTargetService(db)
    current = service.get_target(target_id, firm_scope=scope.firm_id)
    assert_version(current.version, expected_version)
    row = service.update_target(
        target_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.target_response(row))


@router.delete("/{target_id}", response_model=ApiResponse[dict[str, str]])
def delete_sales_target(
    target_id: UUID,
    scope: TargetManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Withdraw one target."""
    SalesTargetService(db).delete_target(
        target_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})
