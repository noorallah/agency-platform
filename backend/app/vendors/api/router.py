"""Firm-scoped REST endpoints for vendor management."""

import csv
import io
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
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
from app.vendors.services import VendorService

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
        data=[VendorResponse.model_validate(row) for row in rows],
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
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=VendorResponse.model_validate(vendor))


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
    )
    return ApiResponse(data=[VendorResponse.model_validate(item) for item in vendors])


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
    return ApiResponse(data=VendorCategoryResponse.model_validate(row))


@router.put(
    "/categories/{category_id}", response_model=ApiResponse[VendorCategoryResponse]
)
def update_vendor_category(
    category_id: UUID,
    data: VendorCategoryWrite,
    scope: VendorCategoryManageScope,
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
    )
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
    return ApiResponse(data=VendorTypeResponse.model_validate(row))


@router.put("/types/{type_id}", response_model=ApiResponse[VendorTypeResponse])
def update_vendor_type(
    type_id: UUID,
    data: VendorTypeWrite,
    scope: VendorCategoryManageScope,
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
    )
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
    return ApiResponse(data=VendorResponse.model_validate(vendor))


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
    )
    set_etag(response, vendor)
    return ApiResponse(data=VendorResponse.model_validate(vendor))


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
    return ApiResponse(data=VendorResponse.model_validate(vendor))


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
    return ApiResponse(data=VendorResponse.model_validate(vendor))


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
