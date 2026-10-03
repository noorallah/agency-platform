"""Firm-scoped REST endpoints for landed cost vouchers (BUY-16)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import set_etag
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.landed_costs.services import (
    LandedCostCancel,
    LandedCostResponse,
    LandedCostService,
    LandedCostWrite,
)

router = APIRouter(
    prefix="/api/v1/landed-costs",
    tags=["Landed Costs"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: A landed cost changes what purchases cost, so it is read and posted under
#: the purchasing codes, as supplier rebates are.
LandedCostViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")
]
LandedCostManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]


@router.get("", response_model=ApiResponse[list[LandedCostResponse]])
def list_landed_costs(
    scope: LandedCostViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LandedCostResponse]]:
    """Return the firm's landed cost vouchers, newest first."""
    service = LandedCostService(db)
    return ApiResponse(data=service.responses(service.list_rows(scope.firm_id)))


@router.post(
    "",
    response_model=ApiResponse[LandedCostResponse],
    status_code=status.HTTP_201_CREATED,
)
def post_landed_cost(
    data: LandedCostWrite,
    scope: LandedCostManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[LandedCostResponse]:
    """Spread a charge over completed receipts and post it."""
    service = LandedCostService(db)
    row = service.post(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Landed cost posted.")


@router.get("/{voucher_id}", response_model=ApiResponse[LandedCostResponse])
def get_landed_cost(
    voucher_id: UUID,
    scope: LandedCostViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[LandedCostResponse]:
    """Return one voucher with its charges and spread."""
    service = LandedCostService(db)
    row = service.get(voucher_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{voucher_id}/cancel", response_model=ApiResponse[LandedCostResponse])
def cancel_landed_cost(
    voucher_id: UUID,
    data: LandedCostCancel,
    scope: LandedCostManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LandedCostResponse]:
    """Reverse a voucher's journal and take its added value back off."""
    service = LandedCostService(db)
    row = service.cancel(
        voucher_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Cancelled.")
