"""Firm-scoped REST endpoints for commission rules and the commission report.

`/report` is declared before `/rules/{rule_id}` for the reason nine endpoints
in eight routers were unreachable until 2026-08-22: FastAPI matches in
declaration order, and a literal path underneath a parameterised one is read as
an id and answered 422.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.commission.schemas import (
    CommissionReport,
    CommissionRuleCreate,
    CommissionRuleResponse,
    CommissionRuleStatusEnum,
    CommissionRuleUpdate,
    CommissionSalesman,
)
from app.commission.services import CommissionService
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1/commission",
    tags=["Commission"],
    responses=STANDARD_ERROR_RESPONSES,
)

CommissionViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("COMMISSION_VIEW")
]
CommissionManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("COMMISSION_MANAGE")
]


@router.get("/report", response_model=ApiResponse[CommissionReport])
def commission_report(
    scope: CommissionViewScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    salesman_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CommissionReport]:
    """Report money collected in the period and the commission it earned.

    The period is read against the settlement date -- the day the money
    arrived -- because that is what earns the commission, not the day the
    invoice was raised.
    """
    report = CommissionService(db).report(
        firm_id=scope.firm_id,
        from_date=from_date,
        to_date=to_date,
        salesman_id=salesman_id,
    )
    return ApiResponse(data=report)


@router.get("/salesmen", response_model=ApiResponse[list[CommissionSalesman]])
def commission_salesmen(
    scope: CommissionViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CommissionSalesman]]:
    """List the people this firm can agree a rate with.

    Guarded by `COMMISSION_VIEW` rather than by `USER_VIEW`, and deliberately
    not shared with the territory module's twin, which is gated on
    `TERRITORY_ASSIGN_SALESMEN` -- a permission whoever sets commission need
    not hold. Without a list of its own the screen could only offer people who
    already had a rule, so a brand-new rate could never be agreed from it.
    """
    return ApiResponse(data=CommissionService(db).salesmen(firm_id=scope.firm_id))


@router.get("/rules", response_model=PaginatedResponse[CommissionRuleResponse])
def list_commission_rules(
    scope: CommissionViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    salesman_id: Annotated[UUID | None, Query()] = None,
    rule_status: Annotated[
        CommissionRuleStatusEnum | None, Query(alias="status")
    ] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CommissionRuleResponse]:
    """Return a page of commission rules."""
    service = CommissionService(db)
    rows, total = service.list_rules(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        salesman_id=salesman_id,
        status=rule_status,
    )
    names = service.names_for(scope.firm_id)
    return PaginatedResponse(
        data=[service.rule_response(row, names) for row in rows],
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "/rules",
    response_model=ApiResponse[CommissionRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_commission_rule(
    payload: CommissionRuleCreate,
    scope: CommissionManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CommissionRuleResponse]:
    """Declare a commission rate for one salesman, or for the whole firm."""
    service = CommissionService(db)
    row = service.create_rule(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.rule_response(row, service.names_for(scope.firm_id)),
        message="Commission rule recorded.",
    )


@router.get("/rules/{rule_id}", response_model=ApiResponse[CommissionRuleResponse])
def get_commission_rule(
    rule_id: UUID,
    scope: CommissionViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CommissionRuleResponse]:
    """Return one commission rule."""
    service = CommissionService(db)
    row = service.get_rule(rule_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(
        data=service.rule_response(row, service.names_for(scope.firm_id))
    )


@router.put("/rules/{rule_id}", response_model=ApiResponse[CommissionRuleResponse])
def update_commission_rule(
    rule_id: UUID,
    payload: CommissionRuleUpdate,
    scope: CommissionManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[CommissionRuleResponse]:
    """Change a commission rule."""
    service = CommissionService(db)
    row = service.update_rule(
        rule_id,
        payload,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.rule_response(row, service.names_for(scope.firm_id)),
        message="Commission rule updated.",
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commission_rule(
    rule_id: UUID,
    scope: CommissionManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire a commission rule."""
    CommissionService(db).delete_rule(
        rule_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
