"""Firm-scoped REST endpoints for the firm's own salesman list.

**Reading is gated on membership alone**, like ``GET /api/v1/firm-members``:
whoever makes a bill must be able to fill its salesman box, and a firm's list
of its own salesmen is not a privilege. Changing the list needs
``SALESMAN_MANAGE``.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.scope import RequiredFirmScope, ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.imports.services import columns_for_kind, mapped_content, parse_mapping
from app.salesmen.schemas import (
    SalesmanCreate,
    SalesmanResponse,
    SalesmanStartingChoice,
    SalesmanUpdate,
)
from app.salesmen.services import SalesmanService
from app.salesmen.services.salesman_import import (
    SalesmanFileImporter,
    template_csv,
    template_workbook,
)
from app.salesmen.services.salesman_service import SalesmanSort
from app.salesmen.services.starting_choice import starting_choice

router = APIRouter(
    prefix="/api/v1/salesmen",
    tags=["Salesmen"],
    responses=STANDARD_ERROR_RESPONSES,
)

SalesmanManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALESMAN_MANAGE")
]


@router.get("", response_model=PaginatedResponse[SalesmanResponse])
def list_salesmen(
    scope: RequiredFirmScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str, Query()] = "",
    sort_by: SalesmanSort = "name",
    sort_direction: Literal["asc", "desc"] = "asc",
    active: Annotated[bool | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SalesmanResponse]:
    """List the firm's salesmen, by name unless asked otherwise."""
    rows, total = SalesmanService(db).list_salesmen(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        active=active,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[SalesmanResponse.model_validate(row) for row in rows],
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post(
    "",
    response_model=ApiResponse[SalesmanResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_salesman(
    data: SalesmanCreate,
    scope: SalesmanManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesmanResponse]:
    """Add one salesman to the list."""
    row = SalesmanService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=SalesmanResponse.model_validate(row))


# Declared above "/{salesman_id}": FastAPI matches in declaration order.
@router.get("/import-template")
def salesman_import_template(
    scope: SalesmanManageScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the salesman import template (Swathi G3).

    The workbook carries the sheet to fill, a notes sheet naming every column,
    and a lists sheet with this firm's salesmen.
    """
    if format == "csv":
        return StreamingResponse(
            iter([template_csv()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="salesman-template.csv"'
            },
        )
    return StreamingResponse(
        iter([template_workbook(db, scope.firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="salesman-template.xlsx"'
        },
    )


@router.post("/import-file", response_model=ApiResponse[ImportReportResponse])
async def import_salesman_file(
    scope: SalesmanManageScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    existing: Annotated[Literal["refuse", "update"], Form()] = "refuse",
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX salesman file, and with ``apply`` import it whole.

    Every row is checked and every problem returned with its row number. An
    apply that finds any problem writes nothing and says so with
    ``imported: false``. The list is kept under ``SALESMAN_MANAGE``, so the
    file is too, and updating existing salesmen needs nothing more.
    """
    file_format = file_format_of(file.filename)
    # A file mapped on the import screen is read as mapped (decision B3).
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "salesmen"),
    )
    report = SalesmanFileImporter(db, SalesmanService(db)).run(
        content,
        file_format=file_format,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        existing=existing,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


# Declared before "/{salesman_id}", which would read "starting-choice" as an id.
@router.get("/starting-choice", response_model=ApiResponse[SalesmanStartingChoice])
def get_starting_choice(
    scope: RequiredFirmScope,
    customer_id: Annotated[UUID | None, Query()] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesmanStartingChoice]:
    """Say what a new document's Salesman box starts on, and why.

    The signed-in user's own entry, else the customer's account manager,
    else the primary salesman of the customer's round, else nobody (P2,
    salesman list design section 5). Gated on membership, like the list.
    """
    return ApiResponse(
        data=starting_choice(
            db,
            firm_id=scope.firm_id,
            user_id=scope.actor_id,
            customer_id=customer_id,
        )
    )


@router.get("/{salesman_id}", response_model=ApiResponse[SalesmanResponse])
def get_salesman(
    salesman_id: UUID,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesmanResponse]:
    """Return one salesman."""
    row = SalesmanService(db).get(salesman_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=SalesmanResponse.model_validate(row))


@router.put("/{salesman_id}", response_model=ApiResponse[SalesmanResponse])
def update_salesman(
    salesman_id: UUID,
    data: SalesmanUpdate,
    scope: SalesmanManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesmanResponse]:
    """Change one salesman; a field left out is left alone."""
    service = SalesmanService(db)
    assert_version(
        service.get(salesman_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update(
        salesman_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=SalesmanResponse.model_validate(row))


@router.delete("/{salesman_id}", response_model=ApiResponse[dict[str, str]])
def delete_salesman(
    salesman_id: UUID,
    scope: SalesmanManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Delete a salesman nothing names; one in use is made inactive instead."""
    SalesmanService(db).delete(
        salesman_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"status": "deleted"})


@router.post("/{salesman_id}/restore", response_model=ApiResponse[SalesmanResponse])
def restore_salesman(
    salesman_id: UUID,
    scope: SalesmanManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SalesmanResponse]:
    """Bring back a deleted salesman."""
    row = SalesmanService(db).restore(
        salesman_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=SalesmanResponse.model_validate(row))
