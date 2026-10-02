"""Firm-scoped REST endpoints for contra vouchers (backlog 74 row 3).

The finance codes, not a namespace of its own: a contra is a journal with a
number, so reading one is `JOURNAL_VIEW`, recording one -- which writes and
posts its journal in the same act -- is `JOURNAL_POST`, and cancelling one is
`JOURNAL_REVERSE`, exactly as for a hand journal.

Literal paths are declared **above** `/{voucher_id}`, because FastAPI matches
in declaration order.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import (
    ResolvedFirmScope,
    firm_any_permission_scope,
    firm_permission_scope,
)
from app.contra.schemas import (
    ContraKindEnum,
    ContraRegisterRecord,
    ContraStatusEnum,
    ContraVoucherCancel,
    ContraVoucherCreate,
    ContraVoucherResponse,
    MoneyAccountRecord,
)
from app.contra.services import ContraVoucherService
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams, ReportWindow
from app.core.responses.models import ApiResponse, PaginatedResponse

router = APIRouter(
    prefix="/api/v1/contra-vouchers",
    tags=["Contra Vouchers"],
    responses=STANDARD_ERROR_RESPONSES,
)

ContraViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("JOURNAL_VIEW")]
ContraReportScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("JOURNAL_VIEW", "REPORT_VIEW")
]
#: The cash and bank accounts are also what a payment is made from and what
#: a cheque layout is kept for (ACC-12), so whoever pays may list them.
MoneyAccountsScope = Annotated[
    ResolvedFirmScope, firm_any_permission_scope("JOURNAL_VIEW", "PAYMENT_VIEW")
]
ContraPostScope = Annotated[ResolvedFirmScope, firm_permission_scope("JOURNAL_POST")]
ContraCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("JOURNAL_REVERSE")
]


def _message(done: str, warning: str | None) -> str:
    """Join what happened and the below-zero warning, if any."""
    return f"{done} Warning: {warning}" if warning else done


@router.get("", response_model=PaginatedResponse[ContraVoucherResponse])
def list_contra_vouchers(
    scope: ContraViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    kind: Annotated[ContraKindEnum | None, Query()] = None,
    voucher_status: Annotated[ContraStatusEnum | None, Query(alias="status")] = None,
    account_id: Annotated[UUID | None, Query()] = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ContraVoucherResponse]:
    """Return a page of contra vouchers, newest first."""
    service = ContraVoucherService(db)
    rows, total = service.list_vouchers(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        kind=kind,
        status=voucher_status,
        account_id=account_id,
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
    response_model=ApiResponse[ContraVoucherResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_contra_voucher(
    payload: ContraVoucherCreate,
    scope: ContraPostScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ContraVoucherResponse]:
    """Record money moved between two own accounts and post it: Dr to, Cr from.

    Saved even when the account the money left would stand below zero on the
    day; the message and `balance_warning` say so.
    """
    service = ContraVoucherService(db)
    row, warning = service.create(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.response(row, warning=warning),
        message=_message(f"{row.voucher_number} recorded and posted.", warning),
    )


@router.get("/money-accounts", response_model=ApiResponse[list[MoneyAccountRecord]])
def contra_money_accounts(
    scope: MoneyAccountsScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[MoneyAccountRecord]]:
    """Return the cash and bank accounts money can be moved between."""
    return ApiResponse(data=ContraVoucherService(db).money_accounts(scope.firm_id))


@router.get(
    "/reports/register",
    response_model=PaginatedResponse[ContraRegisterRecord],
)
def contra_register(
    scope: ContraReportScope,
    from_date: date | None = None,
    to_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ContraRegisterRecord]:
    """Every deposit, withdrawal and transfer in the period, with its status."""
    window = ReportWindow(from_date, to_date, page, page_size)
    return window.respond(
        ContraVoucherService(db).register_report(firm_id=scope.firm_id, window=window)
    )


@router.get("/{voucher_id}", response_model=ApiResponse[ContraVoucherResponse])
def get_contra_voucher(
    voucher_id: UUID,
    scope: ContraViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ContraVoucherResponse]:
    """Return one contra voucher."""
    service = ContraVoucherService(db)
    row = service.get(voucher_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.response(row))


@router.get(
    "/{voucher_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_contra_voucher(
    voucher_id: UUID,
    scope: ContraViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw one contra voucher as a PDF on the firm's letterhead."""
    pdf, filename = ContraVoucherService(db).render_pdf(
        voucher_id, firm_id=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post(
    "/{voucher_id}/cancel",
    response_model=ApiResponse[ContraVoucherResponse],
)
def cancel_contra_voucher(
    voucher_id: UUID,
    payload: ContraVoucherCancel,
    scope: ContraCancelScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[ContraVoucherResponse]:
    """Take a contra voucher back with a mirror journal; the original stays."""
    service = ContraVoucherService(db)
    assert_version(
        service.get(voucher_id, firm_id=scope.firm_id).version, expected_version
    )
    row, warning = service.cancel(
        voucher_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=service.response(row, warning=warning),
        message=_message(f"{row.voucher_number} cancelled.", warning),
    )
