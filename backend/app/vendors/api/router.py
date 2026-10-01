"""Firm-scoped REST endpoints for vendor management."""

import csv
import io
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.business.schemas import AttributeValueResponse
from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.vendors.models import Vendor
from app.vendors.schemas import (
    VendorCategoryResponse,
    VendorCategoryWrite,
    VendorCreate,
    VendorImportRequest,
    VendorListFilters,
    VendorResponse,
    VendorStatus,
    VendorSummary,
    VendorTypeResponse,
    VendorTypeWrite,
    VendorUpdate,
)
from app.vendors.schemas.opening_bill import (
    VendorOpeningBillCancel,
    VendorOpeningBillImportRequest,
    VendorOpeningBillResponse,
    VendorOpeningBillWrite,
)
from app.vendors.services import VendorService
from app.vendors.services.opening_bill_import import VendorOpeningBillFileImporter
from app.vendors.services.opening_bill_service import VendorOpeningBillService
from app.vendors.services.vendor_import import VendorFileImporter
from app.vendors.services.vendor_import import template_csv as vendor_template_csv
from app.vendors.services.vendor_import import (
    template_workbook as vendor_template_workbook,
)

router = APIRouter(
    prefix="/api/v1/vendors",
    tags=["Vendors"],
    responses=STANDARD_ERROR_RESPONSES,
)


class BulkIdsRequest(BaseModel):
    """Bulk operation payload containing vendor IDs."""

    ids: list[UUID] = Field(min_length=1, max_length=5000)


class BulkStatusRequest(BulkIdsRequest):
    """Bulk status change payload."""

    status: VendorStatus


class BulkCategoryRequest(BulkIdsRequest):
    """Bulk category assignment payload."""

    category_id: UUID | None = None


class BulkBusinessProfileRequest(BulkIdsRequest):
    """Bulk business profile assignment payload."""

    business_profile_id: UUID | None = None


VendorViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_VIEW")]
VendorCreateScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_CREATE")]
VendorUpdateScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_UPDATE")]
VendorDeleteScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_DELETE")]
VendorRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("VENDOR_RESTORE")
]
VendorExportScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_EXPORT")]
VendorImportScope = Annotated[ResolvedFirmScope, firm_permission_scope("VENDOR_IMPORT")]
VendorBankManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("VENDOR_MANAGE_BANK_DETAILS")
]
VendorCategoryManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("VENDOR_MANAGE_CATEGORIES")
]


def _filters(
    *,
    status_value: VendorStatus | None,
    category_id: UUID | None,
    type_id: UUID | None,
    business_profile_id: UUID | None,
    city_id: UUID | None,
    state_id: UUID | None,
    country_id: UUID | None,
    firm_id: UUID | None,
    created_from: date | None,
    created_to: date | None,
    include_deleted: bool,
) -> VendorListFilters:
    """Collect the vendor list filters from the query string."""
    try:
        return VendorListFilters(
            status=status_value,
            category_id=category_id,
            type_id=type_id,
            business_profile_id=business_profile_id,
            city_id=city_id,
            state_id=state_id,
            country_id=country_id,
            firm_id=firm_id,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        )
    except ValueError as error:
        raise ValidationError(str(error)) from error


def _may_manage_bank(scope: ResolvedFirmScope) -> bool:
    """Say whether the caller may change where a supplier is paid."""
    return scope.principal.has_permission("VENDOR_MANAGE_BANK_DETAILS")


def _may_view_bank(scope: ResolvedFirmScope) -> bool:
    """Say whether the caller may read a supplier's bank accounts."""
    return scope.principal.has_permission("VENDOR_VIEW_FINANCIAL_DETAILS")


def _response(
    row: Vendor,
    db: Session,
    scope: ResolvedFirmScope,
    *,
    attributes: list[AttributeValueResponse] | None = None,
) -> VendorResponse:
    """Build one vendor response with its custom fields attached.

    The values live in their own table and `VendorResponse` cannot reach them
    through the row, so every site goes through here.

    It is also where the bank accounts are withheld. They were served to
    anybody holding `VENDOR_VIEW` -- the seeded read-only `VIEWER` included --
    while `VENDOR_VIEW_FINANCIAL_DETAILS` sat seeded and enforced nowhere
    (D-MST-10). One projection rather than a second scope, the way the product
    router withholds a cost price.
    """
    payload = VendorResponse.model_validate(row).model_dump(mode="python")
    payload["attributes"] = (
        VendorService(db).attribute_responses(row) if attributes is None else attributes
    )
    if not _may_view_bank(scope):
        payload["bank_accounts"] = []
    return VendorResponse.model_validate(payload)


def _responses(
    rows: list[Vendor], db: Session, scope: ResolvedFirmScope
) -> list[VendorResponse]:
    """Build a page of responses, reading every row's custom fields at once."""
    attributes = VendorService(db).attribute_responses_for_many(rows)
    return [
        _response(row, db, scope, attributes=attributes.get(row.id, [])) for row in rows
    ]


@router.get("", response_model=PaginatedResponse[VendorResponse])
def list_vendors(
    scope: VendorViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "status", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: Annotated[VendorStatus | None, Query(alias="status")] = None,
    category_id: UUID | None = None,
    type_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    city_id: UUID | None = None,
    state_id: UUID | None = None,
    country_id: UUID | None = None,
    firm_id: UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[VendorResponse]:
    """Return a page of vendors for the firm in scope."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = _filters(
        status_value=status_value,
        category_id=category_id,
        type_id=type_id,
        business_profile_id=business_profile_id,
        city_id=city_id,
        state_id=state_id,
        country_id=country_id,
        firm_id=firm_id if scope.firm_id is None else None,
        created_from=created_from,
        created_to=created_to,
        include_deleted=include_deleted,
    )
    rows, total = VendorService(db).list_vendors(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=_responses(rows, db, scope),
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[VendorSummary])
def vendor_summary(
    scope: VendorViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorSummary]:
    """Return summary."""
    summary = VendorService(db).summary(
        firm_scope=scope.firm_id,
        filters=VendorListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.get("/export")
def export_vendors(
    scope: VendorExportScope,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Export vendors."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Code", "Name", "GSTIN", "PAN", "Email", "Phone", "Status"])
    page = 1
    service = VendorService(db)
    while True:
        rows, _ = service.list_vendors(
            firm_scope=scope.firm_id,
            filters=VendorListFilters(),
            page=page,
            page_size=1000,
            search=search,
            sort_by="code",
            descending=False,
        )
        for vendor in rows:
            writer.writerow(
                [
                    vendor.code,
                    vendor.name,
                    vendor.gstin or "",
                    vendor.pan or "",
                    vendor.email or "",
                    vendor.phone or "",
                    vendor.status,
                ]
            )
        if len(rows) < 1000:
            break
        page += 1
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vendors.csv"'},
    )


@router.post(
    "", response_model=ApiResponse[VendorResponse], status_code=status.HTTP_201_CREATED
)
def create_vendor(
    data: VendorCreate,
    scope: VendorCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorResponse]:
    """Create vendor."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when creating a vendor.")
    vendor = VendorService(db).create(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        may_manage_bank_details=_may_manage_bank(scope),
    )
    return ApiResponse(data=_response(vendor, db, scope))


@router.post(
    "/import",
    response_model=ApiResponse[list[VendorResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_vendors(
    data: VendorImportRequest,
    scope: VendorImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[VendorResponse]]:
    """Create several vendors from an uploaded batch."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing vendors.")
    vendors = VendorService(db).import_vendors(
        data.records,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        may_manage_bank_details=_may_manage_bank(scope),
    )
    return ApiResponse(data=_responses(vendors, db, scope))


def _firm(scope: ResolvedFirmScope) -> UUID:
    """Return the firm a supplier's opening bills belong to, or refuse."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for a supplier's opening bills.")
    return scope.firm_id


# Opening bills: what the firm owed each supplier on its first day here. The
# literal paths come before `/{vendor_id}`, for the reason given below.
@router.post(
    "/opening-bills/import",
    response_model=ApiResponse[list[VendorOpeningBillResponse]],
    status_code=status.HTTP_201_CREATED,
)
def import_vendor_opening_bills(
    data: VendorOpeningBillImportRequest,
    scope: VendorImportScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[VendorOpeningBillResponse]]:
    """Record a file of opening bills, naming suppliers by code; all or none."""
    firm_id = _firm(scope)
    service = VendorOpeningBillService(db)
    rows = service.import_bills(data.records, firm_id=firm_id, actor_id=scope.actor_id)
    return ApiResponse(
        data=[service.response_for(row, firm_id=firm_id) for row in rows]
    )


@router.get("/opening-bills/import-template")
def vendor_opening_bill_import_template(
    scope: VendorImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the suppliers' opening-bill template (D-GOLIVE-1).

    The workbook carries the sheet to fill, a notes sheet naming every column,
    and a lists sheet with this firm's suppliers; the example row names one of
    them, so the template imports as it comes.
    """
    importer = VendorOpeningBillFileImporter(db)
    firm_id = _firm(scope)
    if format == "csv":
        return StreamingResponse(
            iter([importer.template_csv(firm_id)]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="supplier-opening-bills-template.csv"'
                )
            },
        )
    return StreamingResponse(
        iter([importer.template_workbook(firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                'attachment; filename="supplier-opening-bills-template.xlsx"'
            )
        },
    )


@router.post(
    "/opening-bills/import-file", response_model=ApiResponse[ImportReportResponse]
)
async def import_vendor_opening_bill_file(
    scope: VendorImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    posting_date: Annotated[str | None, Form()] = None,
    apply: Annotated[bool, Form()] = False,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX file of opening bills, and with ``apply`` post it.

    Every bill is posted on ``posting_date`` (today when left out). Every
    problem is returned with its row and column; an apply that finds any
    writes nothing and says so with ``imported: false``.
    """
    firm_id = _firm(scope)
    file_format = file_format_of(file.filename)
    if posting_date:
        try:
            on = date.fromisoformat(posting_date)
        except ValueError as error:
            raise ValidationError("posting_date must be a date, yyyy-mm-dd.") from error
    else:
        on = utc_now().date()
    report = VendorOpeningBillFileImporter(db).run(
        await file.read(),
        file_format=file_format,
        firm_id=firm_id,
        actor_id=scope.actor_id,
        posting_date=on,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


@router.post(
    "/opening-bills/{bill_id}/cancel",
    response_model=ApiResponse[VendorOpeningBillResponse],
)
def cancel_vendor_opening_bill(
    bill_id: UUID,
    data: VendorOpeningBillCancel,
    scope: VendorUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorOpeningBillResponse]:
    """Take back an opening bill entered in error; refused once it is paid."""
    firm_id = _firm(scope)
    service = VendorOpeningBillService(db)
    row = service.cancel(
        bill_id, reason=data.reason, firm_id=firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.response_for(row, firm_id=firm_id))


@router.get(
    "/{vendor_id}/opening-bills",
    response_model=ApiResponse[list[VendorOpeningBillResponse]],
)
def list_vendor_opening_bills(
    vendor_id: UUID,
    scope: VendorViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[VendorOpeningBillResponse]]:
    """List one supplier's opening bills with what is paid and owed on each."""
    return ApiResponse(
        data=VendorOpeningBillService(db).list_for_vendor(
            vendor_id, firm_id=_firm(scope)
        )
    )


@router.post(
    "/{vendor_id}/opening-bills",
    response_model=ApiResponse[VendorOpeningBillResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_opening_bill(
    vendor_id: UUID,
    data: VendorOpeningBillWrite,
    scope: VendorUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorOpeningBillResponse]:
    """Record one bill the supplier was owed at cutover, and post it."""
    firm_id = _firm(scope)
    service = VendorOpeningBillService(db)
    row = service.create(vendor_id, data, firm_id=firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=service.response_for(row, firm_id=firm_id))


@router.get("/import-template")
def vendor_import_template(
    scope: VendorImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the supplier import template (backlog 46).

    The workbook carries the sheet to fill, a notes sheet naming every column
    and what it takes, and a lists sheet with this firm's supplier categories
    and types.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing vendors.")
    if format == "csv":
        return StreamingResponse(
            iter([vendor_template_csv()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="supplier-template.csv"'
            },
        )
    return StreamingResponse(
        iter([vendor_template_workbook(db, scope.firm_id)]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="supplier-template.xlsx"'
        },
    )


@router.post("/import-file", response_model=ApiResponse[ImportReportResponse])
async def import_vendor_file(
    scope: VendorImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    existing: Annotated[Literal["refuse", "update"], Form()] = "refuse",
    apply: Annotated[bool, Form()] = False,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX supplier file, and with ``apply`` import it whole.

    Every row is checked and every problem returned with its row number. An
    apply that finds any problem writes nothing and says so with
    ``imported: false``.
    """
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required when importing vendors.")
    file_format = file_format_of(file.filename)
    if existing == "update" and not scope.principal.has_permission("VENDOR_UPDATE"):
        raise AuthorizationError(
            "Updating existing suppliers from a file needs the right to edit "
            "suppliers."
        )
    report = VendorFileImporter(
        db,
        VendorService(db),
        may_manage_bank_details=_may_manage_bank(scope),
    ).run(
        await file.read(),
        file_format=file_format,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        existing=existing,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


# The two masters come first on purpose. FastAPI matches in declaration
# order, so `/{vendor_id}` below would read "categories" as a vendor id and
# answer 422 -- which is exactly what it did until 2026-08-22, making both
# lists unreachable from the day they were written. Same trap as
# `sales_territories`, whose /{territory_id} hid four literal paths.
@router.get("/categories", response_model=PaginatedResponse[VendorCategoryResponse])
def list_vendor_categories(
    scope: VendorViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[VendorCategoryResponse]:
    """List vendor categories."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor categories.")
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = VendorService(db).list_categories(
        firm_id=scope.firm_id,
        include_deleted=include_deleted,
        page=params.page,
        page_size=params.page_size,
        search=search,
    )
    return PaginatedResponse(
        data=[VendorCategoryResponse.model_validate(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/categories",
    response_model=ApiResponse[VendorCategoryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_category(
    data: VendorCategoryWrite,
    scope: VendorCategoryManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorCategoryResponse]:
    """Create vendor category."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor categories.")
    row = VendorService(db).create_category(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    set_etag(response, row)
    return ApiResponse(data=VendorCategoryResponse.model_validate(row))


@router.put(
    "/categories/{category_id}", response_model=ApiResponse[VendorCategoryResponse]
)
def update_vendor_category(
    category_id: UUID,
    data: VendorCategoryWrite,
    scope: VendorCategoryManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorCategoryResponse]:
    """Change vendor category."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor categories.")
    row = VendorService(db).update_category(
        category_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=VendorCategoryResponse.model_validate(row))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_category(
    category_id: UUID,
    scope: VendorCategoryManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete vendor category."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor categories.")
    VendorService(db).delete_category(
        category_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/types", response_model=PaginatedResponse[VendorTypeResponse])
def list_vendor_types(
    scope: VendorViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[VendorTypeResponse]:
    """List vendor types."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor types.")
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = VendorService(db).list_types(
        firm_id=scope.firm_id,
        include_deleted=include_deleted,
        page=params.page,
        page_size=params.page_size,
        search=search,
    )
    return PaginatedResponse(
        data=[VendorTypeResponse.model_validate(item) for item in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/types",
    response_model=ApiResponse[VendorTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_type(
    data: VendorTypeWrite,
    scope: VendorCategoryManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorTypeResponse]:
    """Create vendor type."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor types.")
    row = VendorService(db).create_type(
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    set_etag(response, row)
    return ApiResponse(data=VendorTypeResponse.model_validate(row))


@router.put("/types/{type_id}", response_model=ApiResponse[VendorTypeResponse])
def update_vendor_type(
    type_id: UUID,
    data: VendorTypeWrite,
    scope: VendorCategoryManageScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorTypeResponse]:
    """Change vendor type."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor types.")
    row = VendorService(db).update_type(
        type_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=VendorTypeResponse.model_validate(row))


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_type(
    type_id: UUID,
    scope: VendorCategoryManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete vendor type."""
    if scope.firm_id is None:
        raise ValidationError("X-Firm-ID is required for vendor types.")
    VendorService(db).delete_type(
        type_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{vendor_id}", response_model=ApiResponse[VendorResponse])
def get_vendor(
    vendor_id: UUID,
    scope: VendorViewScope,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorResponse]:
    """Return vendor."""
    vendor = VendorService(db).get(
        vendor_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    set_etag(response, vendor)
    return ApiResponse(data=_response(vendor, db, scope))


@router.put("/{vendor_id}", response_model=ApiResponse[VendorResponse])
def update_vendor(
    vendor_id: UUID,
    data: VendorUpdate,
    scope: VendorUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[VendorResponse]:
    """Change vendor.

    An update replaces six child collections -- contacts, addresses, banking,
    tax registrations, attachments and notes -- so the loser of a concurrent
    edit does not merge badly, they lose every row they entered. This is the
    worst case of that shape in the codebase.
    """
    service = VendorService(db)
    assert_version(
        service.get(vendor_id, firm_scope=scope.firm_id).version, expected_version
    )
    vendor = service.update(
        vendor_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        # Where a supplier is paid is its own duty, and somebody who is not
        # shown the accounts cannot be taken to be instructing about them.
        may_manage_bank_details=_may_manage_bank(scope),
        may_view_bank_details=_may_view_bank(scope),
    )
    set_etag(response, vendor)
    return ApiResponse(data=_response(vendor, db, scope))


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor(
    vendor_id: UUID,
    scope: VendorDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete vendor."""
    VendorService(db).delete(
        vendor_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{vendor_id}/restore", response_model=ApiResponse[VendorResponse])
def restore_vendor(
    vendor_id: UUID,
    scope: VendorRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorResponse]:
    """Restore vendor."""
    vendor = VendorService(db).restore(
        vendor_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_response(vendor, db, scope))


@router.post("/{vendor_id}/duplicate", response_model=ApiResponse[VendorResponse])
def duplicate_vendor(
    vendor_id: UUID,
    scope: VendorCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VendorResponse]:
    """Duplicate vendor."""
    vendor = VendorService(db).duplicate(
        vendor_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=_response(vendor, db, scope))


@router.post("/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_vendors(
    data: BulkIdsRequest,
    scope: VendorDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Apply in bulk: delete vendors."""
    affected = VendorService(db).bulk_delete(
        ids=data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_vendors(
    data: BulkIdsRequest,
    scope: VendorRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Apply in bulk: restore vendors."""
    affected = VendorService(db).bulk_restore(
        ids=data.ids,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/bulk-status", response_model=ApiResponse[dict[str, int]])
def bulk_status_vendors(
    data: BulkStatusRequest,
    scope: VendorUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Apply in bulk: status vendors."""
    affected = VendorService(db).bulk_status(
        ids=data.ids,
        status=data.status.value,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/bulk-category", response_model=ApiResponse[dict[str, int]])
def bulk_category_vendors(
    data: BulkCategoryRequest,
    scope: VendorUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Apply in bulk: category vendors."""
    affected = VendorService(db).bulk_category(
        ids=data.ids,
        category_id=data.category_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})


@router.post("/bulk-profile", response_model=ApiResponse[dict[str, int]])
def bulk_profile_vendors(
    data: BulkBusinessProfileRequest,
    scope: VendorUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    """Apply in bulk: profile vendors."""
    affected = VendorService(db).bulk_profile(
        ids=data.ids,
        business_profile_id=data.business_profile_id,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data={"affected": affected})
