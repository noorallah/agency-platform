"""Firm-scoped REST endpoints for tax collected at source.

There is no endpoint that collects. A collection is raised by a receipt, and a
route that could raise one on its own would let the same money be charged twice
with nothing to say which figure the buyer was given. What is exposed is the
policy, the preview a salesman needs before taking the money, and the register
the quarterly return is prepared from.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.tcs.schemas import (
    TcsCollectionResponse,
    TcsPreview,
    TcsSettingsResponse,
    TcsSettingsWrite,
)
from app.tcs.services import TcsService

router = APIRouter(
    prefix="/api/v1/tcs",
    tags=["Tax Collected at Source"],
    responses=STANDARD_ERROR_RESPONSES,
)

TcsViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("TCS_VIEW")]

#: Writing the policy decides what every buyer is charged, so it is separate
#: from reading it -- and deliberately not granted to `SALES_MANAGER`, on the
#: same reasoning as the credit-control policy: the role the rule constrains
#: must not be able to switch it off.
TcsManageScope = Annotated[ResolvedFirmScope, firm_permission_scope("TCS_MANAGE")]


@router.get("/settings", response_model=ApiResponse[TcsSettingsResponse])
def read_settings(
    scope: TcsViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TcsSettingsResponse]:
    """Return this firm's policy, or the section's defaults where it has none."""
    return ApiResponse(data=TcsService(db).read_settings(scope.firm_id))


@router.put("/settings", response_model=ApiResponse[TcsSettingsResponse])
def write_settings(
    payload: TcsSettingsWrite,
    scope: TcsManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TcsSettingsResponse]:
    """Change this firm's policy. An omitted field is left alone."""
    return ApiResponse(
        data=TcsService(db).write_settings(
            scope.firm_id, payload, actor_id=scope.actor_id
        ),
        message="TCS settings saved.",
    )


@router.get("/preview", response_model=ApiResponse[TcsPreview])
def preview(
    scope: TcsViewScope,
    customer_id: UUID,
    amount: Decimal,
    on: date,
    db: Session = Depends(get_db),
) -> ApiResponse[TcsPreview]:
    """Say what a receipt of this size from this buyer would attract.

    Answered before the receipt exists, so the figure is known when the money
    is asked for rather than discovered after it has been taken.
    """
    return ApiResponse(
        data=TcsService(db).preview(
            firm_id=scope.firm_id, customer_id=customer_id, amount=amount, on=on
        )
    )


@router.get("/collections", response_model=PaginatedResponse[TcsCollectionResponse])
def list_collections(
    scope: TcsViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    customer_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TcsCollectionResponse]:
    """List what has been collected, newest first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = TcsService(db)
    rows, total = service.list_collections(
        firm_id=scope.firm_id,
        customer_id=customer_id,
        from_date=from_date,
        to_date=to_date,
        offset=(params.page - 1) * params.page_size,
        limit=params.page_size,
    )
    return PaginatedResponse(
        data=service.describe(rows),
        pagination=params.metadata(total),
    )
