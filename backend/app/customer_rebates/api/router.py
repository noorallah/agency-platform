"""Firm-scoped REST endpoints for customer turnover rebates (SG-9)."""

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
from app.core.concurrency import ExpectedVersion, publish_version
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import ReportWindow
from app.core.pagination.reports import mapped_like
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.customer_rebates.models import CustomerRebateStatus
from app.customer_rebates.schemas import (
    CustomerRebateAccrue,
    CustomerRebateCreate,
    CustomerRebateResponse,
    CustomerRebateStatement,
    CustomerRebateStatementRow,
    CustomerRebateUpdate,
)
from app.customer_rebates.services import CustomerRebateService

router = APIRouter(
    prefix="/api/v1/customer-rebates",
    tags=["Customer Rebates"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Reading a rebate is reading sales; agreeing and accruing one is the sales
#: manager's call, as approving an order is -- the codes the supplier's rebate
#: takes on the buying side. Settling one moves the customer's account and is
#: a party adjustment, which that role does not hold.
RebateViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]
RebateManageScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")]
#: A report opens to whoever may read the module or holds `REPORT_VIEW`
#: (D-RPT-4).
RebateReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW")
]


def _one(
    db: Session, row_id: UUID, firm_id: UUID, response: Response
) -> CustomerRebateResponse:
    """Build one agreement's response and publish its version."""
    service = CustomerRebateService(db)
    view = service.responses([service.get(row_id, firm_id=firm_id)])[0]
    publish_version(response, view.version)
    return view


@router.get("", response_model=PaginatedResponse[CustomerRebateResponse])
def list_customer_rebates(
    scope: RebateViewScope,
    customer_id: UUID | None = None,
    customer_group_id: UUID | None = None,
    status_value: Annotated[CustomerRebateStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerRebateResponse]:
    """Return a page of the firm's rebate agreements with each one's progress."""
    service = CustomerRebateService(db)
    window = ReportWindow(page=page, page_size=page_size)
    rows = service.list_agreements(
        firm_id=scope.firm_id,
        customer_id=customer_id,
        customer_group_id=customer_group_id,
        status=None if status_value is None else status_value.value,
        search=search,
        window=window,
    )
    return window.respond(mapped_like(rows, service.responses(rows)))


@router.post(
    "",
    response_model=ApiResponse[CustomerRebateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_customer_rebate(
    data: CustomerRebateCreate,
    scope: RebateManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Agree a turnover rebate with a customer or a customer group."""
    row = CustomerRebateService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_one(db, row.id, scope.firm_id, response))


@router.get(
    "/reports/statement",
    response_model=PaginatedResponse[CustomerRebateStatementRow],
)
def customer_rebate_statement_report(
    scope: RebateReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[CustomerRebateStatementRow]:
    """Return accrued and settled per agreement whose period is in the window."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        CustomerRebateService(db).statement_report(scope.firm_id, window)
    )


@router.get("/{agreement_id}", response_model=ApiResponse[CustomerRebateResponse])
def get_customer_rebate(
    agreement_id: UUID,
    scope: RebateViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Return one agreement with its turnover, slab reached and settlements."""
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id, response))


@router.put("/{agreement_id}", response_model=ApiResponse[CustomerRebateResponse])
def update_customer_rebate(
    agreement_id: UUID,
    data: CustomerRebateUpdate,
    scope: RebateManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Change an agreement that is still counting."""
    CustomerRebateService(db).update(
        agreement_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id, response))


@router.get(
    "/{agreement_id}/statement",
    response_model=ApiResponse[CustomerRebateStatement],
)
def get_customer_rebate_statement(
    agreement_id: UUID,
    scope: RebateViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateStatement]:
    """Return what an agreement's turnover is made of and what settled it."""
    return ApiResponse(
        data=CustomerRebateService(db).statement(agreement_id, firm_id=scope.firm_id)
    )


@router.post(
    "/{agreement_id}/cancel", response_model=ApiResponse[CustomerRebateResponse]
)
def cancel_customer_rebate(
    agreement_id: UUID,
    scope: RebateManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Withdraw an agreement nothing was accrued on."""
    CustomerRebateService(db).cancel(
        agreement_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id, response))


@router.post(
    "/{agreement_id}/accrue", response_model=ApiResponse[CustomerRebateResponse]
)
def accrue_customer_rebate(
    agreement_id: UUID,
    data: CustomerRebateAccrue,
    scope: RebateManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Book what the period earned, once it is over."""
    CustomerRebateService(db).accrue(
        agreement_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        accrual_date=data.accrual_date,
        expected_version=expected_version,
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id, response))


@router.post(
    "/{agreement_id}/reverse-accrual",
    response_model=ApiResponse[CustomerRebateResponse],
)
def reverse_customer_rebate_accrual(
    agreement_id: UUID,
    scope: RebateManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CustomerRebateResponse]:
    """Take an accrual back off the books while nothing is settled."""
    CustomerRebateService(db).reverse_accrual(
        agreement_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    return ApiResponse(data=_one(db, agreement_id, scope.firm_id, response))
