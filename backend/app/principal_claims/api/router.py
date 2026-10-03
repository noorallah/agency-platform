"""Firm-scoped REST endpoints for claims on principals (SEL-11)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import set_etag
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.principal_claims.services import (
    PrincipalClaimCancel,
    PrincipalClaimPreview,
    PrincipalClaimReceiptWrite,
    PrincipalClaimResponse,
    PrincipalClaimService,
    PrincipalClaimWrite,
)

router = APIRouter(
    prefix="/api/v1/principal-claims",
    tags=["Principal Claims"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: A claim is money a supplier-side party owes, so it is read and managed
#: under the purchasing codes, as supplier rebates are (BUY-13).
ClaimViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PURCHASE_VIEW")]
ClaimManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PURCHASE_APPROVE")
]


@router.get("", response_model=ApiResponse[list[PrincipalClaimResponse]])
def list_claims(
    scope: ClaimViewScope,
    db: Session = Depends(get_db),
    principal_id: Annotated[UUID | None, Query()] = None,
) -> ApiResponse[list[PrincipalClaimResponse]]:
    """Return the firm's claims, newest first."""
    service = PrincipalClaimService(db)
    return ApiResponse(
        data=service.responses(
            service.list_rows(scope.firm_id, principal_id=principal_id)
        )
    )


@router.post("/preview", response_model=ApiResponse[PrincipalClaimPreview])
def preview_claim(
    data: PrincipalClaimWrite,
    scope: ClaimViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimPreview]:
    """Return what a claim for the period would hold, writing nothing."""
    return ApiResponse(
        data=PrincipalClaimService(db).preview(data, firm_id=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[PrincipalClaimResponse],
    status_code=status.HTTP_201_CREATED,
)
def raise_claim(
    data: PrincipalClaimWrite,
    scope: ClaimManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimResponse]:
    """Raise and post a claim for one principal and period."""
    service = PrincipalClaimService(db)
    row = service.raise_claim(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0], message="Claim raised.")


@router.get("/{claim_id}", response_model=ApiResponse[PrincipalClaimResponse])
def get_claim(
    claim_id: UUID,
    scope: ClaimViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimResponse]:
    """Return one claim with its lines and payments."""
    service = PrincipalClaimService(db)
    row = service.get(claim_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.post("/{claim_id}/cancel", response_model=ApiResponse[PrincipalClaimResponse])
def cancel_claim(
    claim_id: UUID,
    data: PrincipalClaimCancel,
    scope: ClaimManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimResponse]:
    """Withdraw a claim nothing has settled."""
    service = PrincipalClaimService(db)
    row = service.cancel(
        claim_id, data.reason, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Claim cancelled.")


@router.post(
    "/{claim_id}/receipts",
    response_model=ApiResponse[PrincipalClaimResponse],
    status_code=status.HTTP_201_CREATED,
)
def receive_claim_payment(
    claim_id: UUID,
    data: PrincipalClaimReceiptWrite,
    scope: ClaimManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimResponse]:
    """Record money the principal paid against a claim."""
    service = PrincipalClaimService(db)
    service.record_receipt(
        claim_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    row = service.get(claim_id, firm_id=scope.firm_id)
    return ApiResponse(data=service.responses([row])[0], message="Payment recorded.")


@router.post(
    "/{claim_id}/receipts/{receipt_id}/reverse",
    response_model=ApiResponse[PrincipalClaimResponse],
)
def reverse_claim_payment(
    claim_id: UUID,
    receipt_id: UUID,
    scope: ClaimManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalClaimResponse]:
    """Take a payment back off the books, as for a bounced cheque."""
    service = PrincipalClaimService(db)
    row = service.reverse_receipt(
        claim_id, receipt_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses([row])[0], message="Payment reversed.")


@router.get("/{claim_id}/print", response_class=StreamingResponse)
def print_claim(
    claim_id: UUID,
    scope: ClaimViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Render the claim statement sent to the principal."""
    pdf, filename = PrincipalClaimService(db).render_statement(
        claim_id, firm_id=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
