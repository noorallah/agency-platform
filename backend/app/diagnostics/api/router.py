"""REST access to error and crash reports.

Reports live in the **platform** schema, unlike the audit trail: they are
operational telemetry for whoever maintains the product, and a fault split
across firm stores cannot be counted or triaged. ``/api/v1/diagnostics`` is
therefore registered as a platform path in
``app/core/database/dependencies.py``, so ``get_db`` resolves the platform
session regardless of any ``X-Firm-ID`` the client happens to send.

Ingest is **authenticated**. A public write endpoint would need its own abuse
protection, and the desktop already queues reports on disk until it can sign in,
so nothing is lost by requiring a caller we can name.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    require_authenticated,
    require_permission,
)
from app.diagnostics.schemas import (
    ClientErrorReportBatch,
    ErrorReportGroupResponse,
    ErrorReportResponse,
)
from app.diagnostics.services import ErrorReportService

router = APIRouter(
    prefix="/api/v1/diagnostics",
    tags=["Diagnostics"],
    responses=STANDARD_ERROR_RESPONSES,
)

AuthenticatedPrincipal = Annotated[Principal, Depends(require_authenticated())]
DiagnosticsViewPrincipal = Annotated[
    Principal, Depends(require_permission("DIAGNOSTICS_VIEW"))
]


@router.post("/client-errors", response_model=ApiResponse[None])
def report_client_errors(
    data: ClientErrorReportBatch,
    principal: AuthenticatedPrincipal,
    db: Session = Depends(get_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> ApiResponse[None]:
    """Accept a batch of reports queued by a desktop client.

    Any authenticated user may report: a crash is not a privileged act, and a
    client that could not report its own failures would be reporting nothing at
    all. Firm and user are taken from the caller rather than the payload, so a
    report cannot claim to come from somewhere it did not.
    """
    service = ErrorReportService(db)
    user_id = principal.subject if isinstance(principal.subject, UUID) else None
    for report in data.reports:
        service.record_client_report(report, firm_id=x_firm_id, user_id=user_id)
    return ApiResponse(
        data=None,
        message=f"Recorded {len(data.reports)} report(s).",
    )


@router.get("/errors", response_model=PaginatedResponse[ErrorReportGroupResponse])
def list_error_groups(
    principal: DiagnosticsViewPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    # Bounded on the parameter, not by constructing PaginationParams in the
    # body: the model enforces the same ceiling, but a violation raised after
    # routing surfaces as a 500 rather than a 422 naming the limit.
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    source: Literal["CLIENT", "SERVER"] | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ErrorReportGroupResponse]:
    """List faults collapsed by fingerprint, most recently seen first."""
    params = PaginationParams(page=page, page_size=page_size)
    groups, total = ErrorReportService(db).list_groups(
        params.page, params.page_size, search, source
    )
    return PaginatedResponse(
        data=[ErrorReportGroupResponse.model_validate(group) for group in groups],
        pagination=params.metadata(total),
    )


@router.get(
    "/errors/{fingerprint}",
    response_model=ApiResponse[list[ErrorReportResponse]],
)
def list_error_occurrences(
    fingerprint: str,
    principal: DiagnosticsViewPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ErrorReportResponse]]:
    """Return individual occurrences of one fault, newest first."""
    return ApiResponse(
        data=[
            ErrorReportResponse.model_validate(row)
            for row in ErrorReportService(db).list_occurrences(fingerprint)
        ]
    )
