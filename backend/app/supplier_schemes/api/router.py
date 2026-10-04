"""Supplier free-goods schemes on an item (PG-11)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.supplier_schemes.schemas import (
    SupplierSchemeCreate,
    SupplierSchemeResponse,
    SupplierSchemeUpdate,
)
from app.supplier_schemes.services import SupplierSchemeService

router = APIRouter(
    prefix="/api/v1/supplier-schemes",
    tags=["Supplier schemes"],
    responses=STANDARD_ERROR_RESPONSES,
)

ViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("SUPPLIER_SCHEME_VIEW")]
ManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("SUPPLIER_SCHEME_MANAGE")
]


@router.get("", response_model=PaginatedResponse[SupplierSchemeResponse])
def list_supplier_schemes(
    scope: ViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    vendor_id: UUID | None = None,
    product_id: UUID | None = None,
    all_suppliers: bool | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SupplierSchemeResponse]:
    """Return one page of the firm's schemes, latest start first.

    ``product_id`` matches the product bought or the product given free;
    ``all_suppliers`` true lists only schemes for every supplier, false only
    a supplier's own.
    """
    params = PaginationParams(page=page, page_size=page_size)
    service = SupplierSchemeService(db)
    rows, total = service.page(
        scope.firm_id,
        vendor_id=vendor_id,
        product_id=product_id,
        all_suppliers=all_suppliers,
        is_active=is_active,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=service.responses(rows), pagination=params.metadata(total)
    )


@router.post(
    "",
    response_model=ApiResponse[SupplierSchemeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_scheme(
    data: SupplierSchemeCreate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierSchemeResponse]:
    """Set a scheme up; refused if an active one for the same terms overlaps."""
    service = SupplierSchemeService(db)
    row = service.create(data, firm_id=scope.firm_id, actor_id=scope.actor_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.get("/{scheme_id}", response_model=ApiResponse[SupplierSchemeResponse])
def get_supplier_scheme(
    scheme_id: UUID,
    scope: ViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[SupplierSchemeResponse]:
    """Return one scheme."""
    service = SupplierSchemeService(db)
    row = service.get(scheme_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.put("/{scheme_id}", response_model=ApiResponse[SupplierSchemeResponse])
def update_supplier_scheme(
    scheme_id: UUID,
    data: SupplierSchemeUpdate,
    scope: ManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[SupplierSchemeResponse]:
    """Change a scheme; a field left out is left alone."""
    service = SupplierSchemeService(db)
    assert_version(
        service.get(scheme_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.update(
        scheme_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=service.responses([row])[0])


@router.delete("/{scheme_id}", response_model=ApiResponse[None])
def delete_supplier_scheme(
    scheme_id: UUID,
    scope: ManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a scheme; order lines that took it keep its label."""
    SupplierSchemeService(db).delete(
        scheme_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Supplier scheme deleted.")
