"""HTTP routes for payment runs (BUY-11, decision A110).

Proposing and reading take the payment view; keeping a draft takes
PAYMENT_CREATE; approving -- which books the money -- takes
PAYMENT_RUN_APPROVE; the bank file carries full account numbers, so it also
takes VENDOR_VIEW_FINANCIAL_DETAILS.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.settlements.schemas import OutstandingInvoiceRecord
from app.settlements.schemas.payment_run import (
    PaymentRunCancel,
    PaymentRunResponse,
    PaymentRunWrite,
)
from app.settlements.services.payment_runs import PaymentRunService

payment_runs_router = APIRouter(
    prefix="/api/v1/payment-runs",
    tags=["Payment runs"],
    responses=STANDARD_ERROR_RESPONSES,
)

RunViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_VIEW")]
RunWriteScope = Annotated[ResolvedFirmScope, firm_permission_scope("PAYMENT_CREATE")]
RunApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PAYMENT_RUN_APPROVE")
]


@payment_runs_router.get(
    "/proposal", response_model=ApiResponse[list[OutstandingInvoiceRecord]]
)
def propose_payment_run(
    due_by: date,
    scope: RunViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[OutstandingInvoiceRecord]]:
    """Return every supplier bill still owing that falls due by ``due_by``."""
    return ApiResponse(data=PaymentRunService(db).propose(scope.firm_id, due_by))


@payment_runs_router.get("", response_model=ApiResponse[list[PaymentRunResponse]])
def list_payment_runs(
    scope: RunViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PaymentRunResponse]]:
    """Return the firm's payment runs, newest first."""
    service = PaymentRunService(db)
    return ApiResponse(data=service.responses(service.list_rows(scope.firm_id)))


@payment_runs_router.post(
    "",
    response_model=ApiResponse[PaymentRunResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_payment_run(
    data: PaymentRunWrite,
    scope: RunWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentRunResponse]:
    """Keep a draft run of the chosen bills."""
    service = PaymentRunService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.responses([row])[0])


@payment_runs_router.get("/{run_id}", response_model=ApiResponse[PaymentRunResponse])
def get_payment_run(
    run_id: UUID,
    scope: RunViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentRunResponse]:
    """Return one run."""
    service = PaymentRunService(db)
    return ApiResponse(
        data=service.responses([service.get(run_id, firm_id=scope.firm_id)])[0]
    )


@payment_runs_router.put("/{run_id}", response_model=ApiResponse[PaymentRunResponse])
def update_payment_run(
    run_id: UUID,
    data: PaymentRunWrite,
    scope: RunWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentRunResponse]:
    """Change a draft run's date and bills."""
    service = PaymentRunService(db)
    row = service.update(run_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.responses([row])[0])


@payment_runs_router.post(
    "/{run_id}/approve", response_model=ApiResponse[PaymentRunResponse]
)
def approve_payment_run(
    run_id: UUID,
    scope: RunApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentRunResponse]:
    """Record one payment per supplier, all or none."""
    service = PaymentRunService(db)
    row = service.approve(run_id, firm_id=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.responses([row])[0], message="Payments recorded.")


@payment_runs_router.post(
    "/{run_id}/cancel", response_model=ApiResponse[PaymentRunResponse]
)
def cancel_payment_run(
    run_id: UUID,
    data: PaymentRunCancel,
    scope: RunWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PaymentRunResponse]:
    """Call off a draft run."""
    service = PaymentRunService(db)
    row = service.cancel(
        run_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0])


@payment_runs_router.get("/{run_id}/bank-file", response_class=StreamingResponse)
def payment_run_bank_file(
    run_id: UUID,
    scope: RunWriteScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the run's NEFT bulk-upload file (generic layout)."""
    if not scope.principal.has_permission("VENDOR_VIEW_FINANCIAL_DETAILS"):
        raise AuthorizationError(
            "The bank file carries full account numbers, so it needs the right "
            "to see suppliers' bank details."
        )
    content, name = PaymentRunService(db).bank_file(run_id, firm_id=scope.firm_id)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
