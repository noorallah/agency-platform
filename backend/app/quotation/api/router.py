"""Firm-scoped REST endpoints for sales quotations."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.document_framework.schemas import DocumentLifecycleEventResponse
from app.quotation.schemas import (
    QuotationConversionRecord,
    QuotationConvertRequest,
    QuotationCreate,
    QuotationDecision,
    QuotationImportRequest,
    QuotationListFilters,
    QuotationRegisterRecord,
    QuotationResponse,
    QuotationStatus,
    QuotationSummary,
    QuotationUpdate,
)
from app.quotation.services import QuotationService
from app.quotation.services.quotation_print_service import (
    QuotationPrintService,
)
from app.sales_order.schemas import SalesOrderResponse
from app.sales_order.services import SalesOrderService

router = APIRouter(
    prefix="/api/v1/quotations",
    tags=["Quotations"],
    responses=STANDARD_ERROR_RESPONSES,
)

# `SALES_QUOTATION_CREATE` has been a seeded permission code, held by
# SALES_MANAGER and SALES_EXECUTIVE, since the identity seed was written and
# enforced nowhere: it was reserved for exactly this document.
QuotationViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SALES_VIEW")]
QuotationCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_QUOTATION_CREATE")
]
QuotationUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_UPDATE")
]
QuotationApproveScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_APPROVE")
]
QuotationCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_CANCEL")
]
QuotationImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_IMPORT")
]
QuotationExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SALES_EXPORT")
]


class ConversionResult(ApiResponse[QuotationResponse]):
    """The quotation and the order it became, in one answer."""

    order: SalesOrderResponse | None = None


def _filters(
    *,
    customer_id: UUID | None,
    branch_id: UUID | None,
    salesman_id: UUID | None,
    status_value: QuotationStatus | None,
    quotation_from: date | None,
    quotation_to: date | None,
    include_deleted: bool,
) -> QuotationListFilters:
    try:
        return QuotationListFilters.model_validate(
            {
                "customer_id": customer_id,
                "branch_id": branch_id,
                "salesman_id": salesman_id,
                "status": status_value,
                "quotation_from": quotation_from,
                "quotation_to": quotation_to,
                "include_deleted": include_deleted,
            }
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


@router.get("", response_model=PaginatedResponse[QuotationResponse])
def list_quotations(
    scope: QuotationViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "quotation_number",
        "quotation_date",
        "valid_until",
        "grand_total",
        "status",
        "created_at",
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    customer_id: UUID | None = None,
    branch_id: UUID | None = None,
    salesman_id: UUID | None = None,
    status_value: Annotated[QuotationStatus | None, Query(alias="status")] = None,
    quotation_from: date | None = None,
    quotation_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[QuotationResponse]:
    """List quotations for the visible firm scope."""
    params = PaginationParams(page=page, page_size=page_size)
    service = QuotationService(db)
    rows, total = service.list_quotations(
        firm_scope=scope.firm_id,
        filters=_filters(
            customer_id=customer_id,
            branch_id=branch_id,
            salesman_id=salesman_id,
            status_value=status_value,
            quotation_from=quotation_from,
            quotation_to=quotation_to,
            include_deleted=include_deleted,
        ),
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[service.quotation_response(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[QuotationSummary])
def get_quotation_summary(
    scope: QuotationViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationSummary]:
    """Summarise quotations for the visible firm scope."""
    return ApiResponse(data=QuotationService(db).summary(firm_scope=scope.firm_id))


@router.get(
    "/reports/register",
    response_model=ApiResponse[list[QuotationRegisterRecord]],
)
def quotation_register(
    scope: QuotationViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[QuotationRegisterRecord]]:
    """Every quotation raised, with what became of it."""
    return ApiResponse(
        data=QuotationService(db).register_report(firm_scope=scope.firm_id)
    )


@router.get(
    "/reports/conversion",
    response_model=ApiResponse[list[QuotationConversionRecord]],
)
def quotation_conversion(
    scope: QuotationViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[QuotationConversionRecord]]:
    """How many quotations turned into orders, per customer."""
    return ApiResponse(
        data=QuotationService(db).conversion_report(firm_scope=scope.firm_id)
    )


@router.post(
    "",
    response_model=ApiResponse[QuotationResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_quotation(
    payload: QuotationCreate,
    scope: QuotationCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Create one quotation in draft."""
    service = QuotationService(db)
    row = service.create_quotation(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.quotation_response(row))


@router.get("/export")
def export_quotations(
    scope: QuotationExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export matching quotations as CSV."""
    csv_content = QuotationService(db).export_quotations_csv(
        firm_scope=scope.firm_id, search=search
    )
    return StreamingResponse(
        iter([csv_content.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quotations.csv"},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[QuotationResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_quotations(
    scope: QuotationImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[QuotationResponse]]:
    """Import a validated batch of quotations atomically.

    JSON only. A quotation carries its lines, and a CSV row is one line, so a
    flat upload would have to be regrouped into documents on some column the
    file has no reason to be sorted by.
    """
    if format != "json":
        raise ValidationError("Only JSON import is supported for quotations.")
    if payload is None:
        raise ValidationError("payload is required for JSON import.")
    service = QuotationService(db)
    rows = service.import_quotations(
        QuotationImportRequest.model_validate_json(payload),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=[service.quotation_response(item) for item in rows])


@router.get(
    "/{quotation_id}/print",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def print_quotation(
    quotation_id: UUID,
    scope: QuotationViewScope,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Render one quotation as the offer a customer is sent.

    Viewing is the permission: the document states what the screen already
    shows, and the person who sends it is not necessarily the one who may
    change it.
    """
    pdf, filename = QuotationPrintService(db).render(
        quotation_id, firm_scope=scope.firm_id
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            # `inline` so a viewer opens it rather than dropping a file the
            # user then has to find.
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{quotation_id}", response_model=ApiResponse[QuotationResponse])
def get_quotation(
    quotation_id: UUID,
    scope: QuotationViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Return one quotation."""
    service = QuotationService(db)
    row = service.get_quotation(quotation_id, firm_scope=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.quotation_response(row))


@router.get(
    "/{quotation_id}/history",
    response_model=ApiResponse[list[DocumentLifecycleEventResponse]],
)
def get_quotation_history(
    quotation_id: UUID,
    scope: QuotationViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[DocumentLifecycleEventResponse]]:
    """Return the lifecycle history of one quotation."""
    events = QuotationService(db).timeline(quotation_id, firm_scope=scope.firm_id)
    return ApiResponse(
        data=[
            DocumentLifecycleEventResponse.model_validate(event, from_attributes=True)
            for event in events
        ]
    )


@router.put("/{quotation_id}", response_model=ApiResponse[QuotationResponse])
def update_quotation(
    quotation_id: UUID,
    payload: QuotationUpdate,
    scope: QuotationUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[QuotationResponse]:
    """Replace one quotation that has not been decided on.

    The update replaces the whole line collection, and the desktop dialog now
    writes as many lines as the offer needs, so a lost race costs every line
    somebody typed rather than a single field.
    """
    service = QuotationService(db)
    assert_version(
        service.get_quotation(quotation_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_quotation(
        quotation_id, payload, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.quotation_response(row))


@router.post("/{quotation_id}/send", response_model=ApiResponse[QuotationResponse])
def send_quotation(
    quotation_id: UUID,
    scope: QuotationApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Mark a quotation as sent to the customer."""
    service = QuotationService(db)
    row = service.send_quotation(
        quotation_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.quotation_response(row))


@router.post("/{quotation_id}/accept", response_model=ApiResponse[QuotationResponse])
def accept_quotation(
    quotation_id: UUID,
    payload: QuotationDecision,
    scope: QuotationApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Record that the customer accepted the offer."""
    service = QuotationService(db)
    row = service.accept_quotation(
        quotation_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    return ApiResponse(data=service.quotation_response(row))


@router.post("/{quotation_id}/decline", response_model=ApiResponse[QuotationResponse])
def decline_quotation(
    quotation_id: UUID,
    payload: QuotationDecision,
    scope: QuotationApproveScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Record that the customer said no, and why."""
    service = QuotationService(db)
    row = service.decline_quotation(
        quotation_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    return ApiResponse(data=service.quotation_response(row))


@router.post("/{quotation_id}/cancel", response_model=ApiResponse[QuotationResponse])
def cancel_quotation(
    quotation_id: UUID,
    payload: QuotationDecision,
    scope: QuotationCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[QuotationResponse]:
    """Withdraw a quotation the firm no longer stands behind."""
    service = QuotationService(db)
    row = service.cancel_quotation(
        quotation_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    return ApiResponse(data=service.quotation_response(row))


@router.post(
    "/{quotation_id}/convert",
    response_model=ConversionResult,
    status_code=status.HTTP_201_CREATED,
)
def convert_quotation(
    quotation_id: UUID,
    payload: QuotationConvertRequest,
    scope: QuotationApproveScope,
    db: Session = Depends(get_db),
) -> ConversionResult:
    """Turn an accepted quotation into a sales order.

    Answers with both documents: the caller needs the order number, and a
    second round trip to find it would be a client guessing at a link the
    server already holds.
    """
    service = QuotationService(db)
    row, order = service.convert_quotation(
        quotation_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        order_date=payload.order_date,
        delivery_date=payload.delivery_date,
    )
    return ConversionResult(
        data=service.quotation_response(row),
        order=SalesOrderService(db).order_response(order),
        message=f"{row.quotation_number} became {order.order_number}.",
    )


@router.delete("/{quotation_id}", response_model=ApiResponse[None])
def delete_quotation(
    quotation_id: UUID,
    scope: QuotationCancelScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Soft-delete a quotation nobody has been sent."""
    QuotationService(db).delete_quotation(
        quotation_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Quotation deleted.")
