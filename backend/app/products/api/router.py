"""Firm-scoped REST endpoints for enterprise product master management."""

# ruff: noqa: D103

from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
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
from app.products.models import Product
from app.products.schemas import (
    BulkProductRequest,
    ProductCategoryCreate,
    ProductCategoryFilter,
    ProductCategoryResponse,
    ProductCategoryUpdate,
    ProductCreate,
    ProductImportRequest,
    ProductListFilters,
    ProductMetadataResponse,
    ProductResponse,
    ProductSummary,
    ProductUpdate,
)
from app.products.services import ProductService


def _can_view_cost(scope: ResolvedFirmScope) -> bool:
    """Return whether the caller may see cost prices.

    This was a field on a bespoke product scope class; it is only a projection
    of a permission, so it does not justify a private scope resolver.
    """
    return scope.principal.has_permission("PRODUCT_VIEW_COST_PRICE")


router = APIRouter(
    prefix="/api/v1/products",
    tags=["Products"],
    responses=STANDARD_ERROR_RESPONSES,
)


ProductViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("PRODUCT_VIEW")]
ProductCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_CREATE")
]
ProductUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_UPDATE")
]
ProductDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_DELETE")
]
ProductRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_RESTORE")
]
ProductImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_IMPORT")
]
ProductExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PRODUCT_EXPORT")
]


@router.get("", response_model=PaginatedResponse[ProductResponse])
def list_products(
    scope: ProductViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal[
        "code", "name", "status", "selling_price", "created_at"
    ] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    status_value: Annotated[str | None, Query(alias="status")] = None,
    product_type: str | None = None,
    category_id: UUID | None = None,
    sub_category_id: UUID | None = None,
    tax_profile_group_code: str | None = None,
    brand: str | None = None,
    hsn_sac: str | None = None,
    attribute_query: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = ProductListFilters.model_validate(
        {
            "status": status_value,
            "product_type": product_type,
            "category_id": category_id,
            "sub_category_id": sub_category_id,
            "tax_profile_group_code": tax_profile_group_code,
            "brand": brand,
            "hsn_sac": hsn_sac,
            "attribute_query": attribute_query,
            "include_deleted": include_deleted,
        }
    )
    rows, total = ProductService(db).list_products(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[
            _response(row, can_view_cost=_can_view_cost(scope), db=db) for row in rows
        ],
        pagination=params.metadata(total),
    )


@router.get("/summary", response_model=ApiResponse[ProductSummary])
def product_summary(
    scope: ProductViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductSummary]:
    summary = ProductService(db).summary(
        firm_scope=scope.firm_id,
        filters=ProductListFilters(include_deleted=include_deleted),
    )
    return ApiResponse(data=summary)


@router.get("/metadata", response_model=ApiResponse[ProductMetadataResponse])
def product_metadata(
    scope: ProductViewScope,
    category_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductMetadataResponse]:
    data = ProductService(db).metadata(
        firm_scope=scope.firm_id, category_id=category_id
    )
    return ApiResponse(data=data)


@router.post(
    "", response_model=ApiResponse[ProductResponse], status_code=status.HTTP_201_CREATED
)
def create_product(
    data: ProductCreate,
    scope: ProductCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).create_product(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_response(row, can_view_cost=_can_view_cost(scope), db=db))


@router.post(
    "/import",
    response_model=ApiResponse[list[ProductResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_products(
    scope: ProductImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["json", "csv", "xlsx"], Form()] = "json",
    payload: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[ProductResponse]]:
    service = ProductService(db)
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        records = ProductImportRequest.model_validate_json(payload).records
        rows = service.import_products_json(
            records, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        return ApiResponse(
            data=[
                _response(row, can_view_cost=_can_view_cost(scope), db=db)
                for row in rows
            ]
        )
    if file is None:
        raise ValidationError("file is required for CSV/XLSX import.")
    content = await file.read()
    if format == "csv":
        rows = service.import_products_csv(
            content.decode("utf-8"), firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
    else:
        rows = service.import_products_xlsx(
            content, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
    return ApiResponse(
        data=[
            _response(row, can_view_cost=_can_view_cost(scope), db=db) for row in rows
        ]
    )


@router.get("/export")
def export_products(
    scope: ProductExportScope,
    format: Literal["csv", "xlsx"] = "csv",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = ProductService(db)
    if format == "xlsx":
        content = service.export_products_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="products.xlsx"'},
        )
    text = service.export_products_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="products.csv"'},
    )


@router.get("/categories", response_model=ApiResponse[list[ProductCategoryResponse]])
def list_categories(
    scope: ProductViewScope,
    parent_id: UUID | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[ProductCategoryResponse]]:
    rows = ProductService(db).list_categories(
        firm_scope=scope.firm_id,
        filters=ProductCategoryFilter(
            parent_id=parent_id, include_inactive=include_inactive
        ),
    )
    return ApiResponse(
        data=[ProductCategoryResponse.model_validate(item) for item in rows]
    )


@router.post(
    "/categories",
    response_model=ApiResponse[ProductCategoryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: ProductCategoryCreate,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductCategoryResponse]:
    row = ProductService(db).create_category(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=ProductCategoryResponse.model_validate(row))


@router.put(
    "/categories/{category_id}", response_model=ApiResponse[ProductCategoryResponse]
)
def update_category(
    category_id: UUID,
    data: ProductCategoryUpdate,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductCategoryResponse]:
    row = ProductService(db).update_category(
        category_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=ProductCategoryResponse.model_validate(row))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: UUID,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> Response:
    ProductService(db).delete_category(
        category_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{product_id}", response_model=ApiResponse[ProductResponse])
def get_product(
    product_id: UUID,
    scope: ProductViewScope,
    response: Response,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).get_product(
        product_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    set_etag(response, row)
    return ApiResponse(data=_response(row, can_view_cost=_can_view_cost(scope), db=db))


@router.put("/{product_id}", response_model=ApiResponse[ProductResponse])
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    scope: ProductUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[ProductResponse]:
    service = ProductService(db)
    assert_version(
        service.get_product(product_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_product(
        product_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=_response(row, can_view_cost=_can_view_cost(scope), db=db))


@router.post(
    "/{product_id}/duplicate",
    response_model=ApiResponse[ProductResponse],
    status_code=status.HTTP_201_CREATED,
)
def duplicate_product(
    product_id: UUID,
    scope: ProductCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).duplicate_product(
        product_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_response(row, can_view_cost=_can_view_cost(scope), db=db))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: UUID,
    scope: ProductDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    ProductService(db).delete_product(
        product_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/restore", response_model=ApiResponse[ProductResponse])
def restore_product(
    product_id: UUID,
    scope: ProductRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).restore_product(
        product_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_response(row, can_view_cost=_can_view_cost(scope), db=db))


@router.post("/bulk-delete", response_model=ApiResponse[dict[str, int]])
def bulk_delete_products(
    data: BulkProductRequest,
    scope: ProductDeleteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    count = ProductService(db).bulk_delete(
        data.ids, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"affected": count})


@router.post("/bulk-restore", response_model=ApiResponse[dict[str, int]])
def bulk_restore_products(
    data: BulkProductRequest,
    scope: ProductRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    count = ProductService(db).bulk_restore(
        data.ids, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data={"affected": count})


def _response(row: Product, *, can_view_cost: bool, db: Session) -> ProductResponse:
    """Build one product response with its configurable attributes."""
    payload = ProductResponse.model_validate(row).model_dump(mode="python")
    payload["attributes"] = ProductService(db).attribute_responses(row)
    if not can_view_cost:
        payload["purchase_price"] = None
    return ProductResponse.model_validate(payload)
