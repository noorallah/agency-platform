"""Firm-scoped REST endpoints for GST returns.

Read-only. A return is a view of the documents, so there is nothing to write
and nothing to approve here -- filing happens on the authority's portal, and
what this answers is what a firm files from.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.gst_returns.services import GstReturnService

router = APIRouter(
    prefix="/api/v1/gst-returns",
    tags=["GST Returns"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Reading a return means reading every sale of the period, so it is gated on
#: the same authority as the sales register rather than on a new code nobody
#: would think to grant.
GstReturnScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]


@router.get("/gstr1", response_model=ApiResponse[dict[str, object]])
def gstr1(
    scope: GstReturnScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    """Return the outward supplies for a period, section by section."""
    return ApiResponse(
        data=GstReturnService(db).gstr1(
            firm_scope=scope.firm_id, from_date=from_date, to_date=to_date
        )
    )


@router.get("/gstr3b", response_model=ApiResponse[dict[str, object]])
def gstr3b(
    scope: GstReturnScope,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    """Return the outward half of the summary return for a period."""
    return ApiResponse(
        data=GstReturnService(db).gstr3b(
            firm_scope=scope.firm_id, from_date=from_date, to_date=to_date
        )
    )
