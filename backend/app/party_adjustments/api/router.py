"""Firm-scoped REST endpoints for party adjustments (backlog 74 row 2).

Literal paths are declared **above** `/{adjustment_id}`, because FastAPI
matches in declaration order.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.party_adjustments.schemas import (
    PartyAdjustmentCancel,
    PartyAdjustmentCreate,
    PartyAdjustmentKindEnum,
    PartyAdjustmentOpenBills,
    PartyAdjustmentRegisterRecord,
    PartyAdjustmentResponse,
    PartyAdjustmentSettingsResponse,
    PartyAdjustmentSettingsWrite,
    PartyAdjustmentStatusEnum,
    PartyAdjustmentUpdate,
)
from app.party_adjustments.services import PartyAdjustmentService
from app.party_adjustments.services.settings import (
    AdjustmentLimits,
    adjustment_limits,
    stage_adjustment_limits,
)

router = APIRouter(
    prefix="/api/v1/party-adjustments",
    tags=["Party Adjustments"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: The authority above the firm's threshold: approving or cancelling a large
#: adjustment, and setting the threshold itself -- the role a limit
#: constrains must not be the one that moves it.
APPROVE_CODE = "PARTY_ADJUSTMENT_APPROVE"

PartyAdjustmentViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PARTY_ADJUSTMENT_VIEW")
]
PartyAdjustmentReportScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope("PARTY_ADJUSTMENT_VIEW", "REPORT_VIEW"),
]
PartyAdjustmentManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PARTY_ADJUSTMENT_MANAGE")
]
PartyAdjustmentApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope(APPROVE_CODE)
]


def _limits_response(limits: AdjustmentLimits) -> PartyAdjustmentSettingsResponse:
    """Shape the firm's limits for the response."""
    return PartyAdjustmentSettingsResponse(
        approval_threshold=limits.approval_threshold,
        rounding_limit=limits.rounding_limit,
        is_default=limits.is_default,
    )


@router.get("", response_model=PaginatedResponse[PartyAdjustmentResponse])
def list_party_adjustments(
    scope: PartyAdjustmentViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    kind: Annotated[PartyAdjustmentKindEnum | None, Query()] = None,
    adjustment_status: Annotated[
        PartyAdjustmentStatusEnum | None, Query(alias="status")
    ] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PartyAdjustmentResponse]:
    """Return a page of party adjustments, newest first."""
    service = PartyAdjustmentService(db)
    rows, total = service.list_adjustments(
        firm_scope=scope.firm_id,
        page=page,
        page_size=page_size,
        kind=kind,
        status=adjustment_status,
        customer_id=customer_id,
        vendor_id=vendor_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    return PaginatedResponse(
        data=service.responses(rows),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[PartyAdjustmentResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_party_adjustment(
    payload: PartyAdjustmentCreate,
    scope: PartyAdjustmentManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentResponse]:
    """Draft a write-off, write-back or set-off. Nothing posts until approval."""
    service = PartyAdjustmentService(db)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.response(row), message="Adjustment drafted.")


@router.get("/settings", response_model=ApiResponse[PartyAdjustmentSettingsResponse])
def get_party_adjustment_settings(
    scope: PartyAdjustmentViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentSettingsResponse]:
    """Return the approval threshold and the rounding limit, or the defaults."""
    return ApiResponse(data=_limits_response(adjustment_limits(db, scope.firm_id)))


@router.put("/settings", response_model=ApiResponse[PartyAdjustmentSettingsResponse])
def update_party_adjustment_settings(
    payload: PartyAdjustmentSettingsWrite,
    scope: PartyAdjustmentApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentSettingsResponse]:
    """Set the approval threshold and the rounding limit."""
    limits = stage_adjustment_limits(
        db,
        scope.firm_id,
        approval_threshold=payload.approval_threshold,
        rounding_limit=payload.rounding_limit,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(data=_limits_response(limits), message="Limits saved.")


@router.get("/open-bills", response_model=ApiResponse[PartyAdjustmentOpenBills])
def party_adjustment_open_bills(
    scope: PartyAdjustmentManageScope,
    customer_id: UUID | None = None,
    vendor_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentOpenBills]:
    """Return the open bills of the customer and the supplier named."""
    return ApiResponse(
        data=PartyAdjustmentService(db).open_bills(
            firm_id=scope.firm_id, customer_id=customer_id, vendor_id=vendor_id
        )
    )


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[PartyAdjustmentRegisterRecord],
)
def party_adjustment_register(
    scope: PartyAdjustmentReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[PartyAdjustmentRegisterRecord]:
    """Every write-off, write-back and set-off, with its reason and status."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        PartyAdjustmentService(db).register_report(
            firm_scope=scope.firm_id, window=window
        )
    )


@router.get("/{adjustment_id}", response_model=ApiResponse[PartyAdjustmentResponse])
def get_party_adjustment(
    adjustment_id: UUID,
    scope: PartyAdjustmentViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentResponse]:
    """Return one party adjustment."""
    service = PartyAdjustmentService(db)
    row = service.get(adjustment_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.response(row))


@router.put("/{adjustment_id}", response_model=ApiResponse[PartyAdjustmentResponse])
def update_party_adjustment(
    adjustment_id: UUID,
    payload: PartyAdjustmentUpdate,
    scope: PartyAdjustmentManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentResponse]:
    """Change a draft adjustment."""
    service = PartyAdjustmentService(db)
    row = service.update(
        adjustment_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.response(row), message="Adjustment updated.")


@router.post(
    "/{adjustment_id}/approve",
    response_model=ApiResponse[PartyAdjustmentResponse],
)
def approve_party_adjustment(
    adjustment_id: UUID,
    scope: PartyAdjustmentManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentResponse]:
    """Post the adjustment. Above the firm's threshold, a second person's."""
    service = PartyAdjustmentService(db)
    row = service.approve(
        adjustment_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        may_approve_above_threshold=scope.principal.has_permission(APPROVE_CODE),
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.response(row), message="Adjustment approved and posted."
    )


@router.post(
    "/{adjustment_id}/cancel",
    response_model=ApiResponse[PartyAdjustmentResponse],
)
def cancel_party_adjustment(
    adjustment_id: UUID,
    payload: PartyAdjustmentCancel,
    scope: PartyAdjustmentManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[PartyAdjustmentResponse]:
    """Withdraw an adjustment, reversing whatever it posted."""
    service = PartyAdjustmentService(db)
    row = service.cancel(
        adjustment_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        may_approve_above_threshold=scope.principal.has_permission(APPROVE_CODE),
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(data=service.response(row), message="Adjustment cancelled.")
