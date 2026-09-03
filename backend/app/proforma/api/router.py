"""Firm-scoped REST endpoints for proforma invoices."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.proforma.schemas import (
    ProformaCancel,
    ProformaCreate,
    ProformaResponse,
    ProformaUpdate,
)
from app.proforma.services import ProformaService

router = APIRouter(
    prefix="/api/v1/proforma-invoices",
    tags=["Proforma Invoices"],
    responses=STANDARD_ERROR_RESPONSES,
)

ProformaViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PROFORMA_VIEW")]
ProformaManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PROFORMA_MANAGE")
]


@router.get("", response_model=PaginatedResponse[ProformaResponse])
def list_proformas(
    scope: ProformaViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    document_status: str | None = None,
    customer_id: UUID | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProformaResponse]:
    """List this firm's proformas, newest first."""
    params = PaginationParams(page=page, page_size=page_size)
    service = ProformaService(db)
    rows, total = service.list_proformas(
        firm_scope=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        status=document_status,
        customer_id=customer_id,
        search=search,
    )
    return PaginatedResponse(
        data=[service.proforma_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[ProformaResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_proforma(
    payload: ProformaCreate,
    scope: ProformaManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ProformaResponse]:
    """Raise a proforma stating what one sales order will be charged.

    The lines are snapshotted from the order rather than sent: a caller that
    could name its own would be stating a price the order never agreed.
    """
    service = ProformaService(db)
    row = service.create_proforma(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(
        data=service.proforma_response(row),
        message=f"Proforma {row.proforma_number} raised.",
    )


@router.get("/{proforma_id}", response_model=ApiResponse[ProformaResponse])
def get_proforma(
    proforma_id: UUID,
    scope: ProformaViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ProformaResponse]:
    """Return one proforma, lines and all."""
    service = ProformaService(db)
    row = service.get_proforma(proforma_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.proforma_response(row))


@router.put("/{proforma_id}", response_model=ApiResponse[ProformaResponse])
def update_proforma(
    proforma_id: UUID,
    payload: ProformaUpdate,
    scope: ProformaManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[ProformaResponse]:
    """Amend a draft proforma's covering terms. An omitted field is left alone."""
    service = ProformaService(db)
    row = service.update_proforma(
        proforma_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=service.proforma_response(row), message="Proforma saved.")


@router.post("/{proforma_id}/issue", response_model=ApiResponse[ProformaResponse])
def issue_proforma(
    proforma_id: UUID,
    scope: ProformaManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ProformaResponse]:
    """Send the proforma to the customer, and freeze it.

    Nothing is posted: a proforma raises no revenue, no output tax and no
    receivable, and there is nowhere on the document to record that it did.
    """
    service = ProformaService(db)
    row = service.issue_proforma(
        proforma_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(
        data=service.proforma_response(row),
        message=f"Proforma {row.proforma_number} issued.",
    )


@router.post("/{proforma_id}/cancel", response_model=ApiResponse[ProformaResponse])
def cancel_proforma(
    proforma_id: UUID,
    payload: ProformaCancel,
    scope: ProformaManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ProformaResponse]:
    """Withdraw a proforma, saying why.

    Nothing is reversed because nothing was posted, and the row stays: the
    customer holds a copy, and a document that vanished leaves them with a
    number this system cannot explain.
    """
    service = ProformaService(db)
    row = service.cancel_proforma(
        proforma_id,
        reason=payload.reason,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    set_etag(response, row)
    return ApiResponse(
        data=service.proforma_response(row),
        message=f"Proforma {row.proforma_number} withdrawn.",
    )
