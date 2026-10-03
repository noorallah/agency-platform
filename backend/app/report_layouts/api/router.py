"""Firm-scoped REST endpoints for a person's saved report layouts (RPT-1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_any_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.report_layouts.schemas import ReportLayoutResponse, ReportLayoutWrite
from app.report_layouts.services import ReportLayoutService

router = APIRouter(
    prefix="/api/v1/report-layouts",
    tags=["Report Layouts"],
    responses=STANDARD_ERROR_RESPONSES,
)

#: Whoever may open either analysis may keep layouts of it; a layout is the
#: person's own and shows nothing the report itself would not.
LayoutScope = Annotated[
    ResolvedFirmScope,
    firm_any_permission_scope("SALES_VIEW", "PURCHASE_VIEW", "REPORT_VIEW"),
]


@router.get("", response_model=ApiResponse[list[ReportLayoutResponse]])
def list_report_layouts(
    scope: LayoutScope,
    report_code: Annotated[str, Query(pattern=r"^(sales_analysis|purchase_analysis)$")],
    db: Session = Depends(get_db),
) -> ApiResponse[list[ReportLayoutResponse]]:
    """Return the caller's saved layouts of one report."""
    rows = ReportLayoutService(db).list_layouts(
        firm_id=scope.firm_id, user_id=scope.actor_id, report_code=report_code
    )
    return ApiResponse(data=[ReportLayoutResponse.model_validate(r) for r in rows])


@router.post("", response_model=ApiResponse[ReportLayoutResponse])
def save_report_layout(
    data: ReportLayoutWrite,
    scope: LayoutScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ReportLayoutResponse]:
    """Save a layout under its name; the same name again replaces it."""
    row = ReportLayoutService(db).save(
        data, firm_id=scope.firm_id, user_id=scope.actor_id
    )
    return ApiResponse(data=ReportLayoutResponse.model_validate(row))


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_layout(
    layout_id: UUID,
    scope: LayoutScope,
    db: Session = Depends(get_db),
) -> Response:
    """Delete one of the caller's own layouts."""
    ReportLayoutService(db).delete(
        layout_id, firm_id=scope.firm_id, user_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
