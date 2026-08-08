"""Firm-scoped REST endpoints for enterprise product master management."""

# ruff: noqa: D103

from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db, get_platform_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.firms.models import Firm
from app.identity.models import UserFirm
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

router = APIRouter(
    prefix="/api/v1/products",
    tags=["Products"],
    responses=STANDARD_ERROR_RESPONSES,
)


class ProductScope:
    """Carry principal, firm scope, and permission projection for product APIs."""

    def __init__(
        self, principal: Principal, firm_id: UUID, can_view_cost: bool
    ) -> None:
        """Store resolved authorization scope for product handlers."""
        self.principal = principal
        self.firm_id = firm_id
        self.can_view_cost = can_view_cost

    @property
    def actor_id(self) -> UUID:
        """Return authenticated user identifier for auditing."""
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("Product management requires a user principal.")
        return self.principal.subject


def product_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_platform_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> ProductScope:
    if "platform_admin" in principal.roles:
        if x_firm_id is None:
            raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
        firm = db.scalar(
            select(Firm.id).where(
                Firm.id == x_firm_id,
                Firm.is_active.is_(True),
                Firm.is_deleted.is_(False),
            )
        )
        if firm is None:
            raise AuthorizationError("The selected firm is inactive or unavailable.")
        return ProductScope(
            principal=principal,
            firm_id=x_firm_id,
            can_view_cost=principal.has_permission("PRODUCT_VIEW_COST_PRICE"),
        )
    if not isinstance(principal.subject, UUID) or x_firm_id is None:
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return ProductScope(
        principal=principal,
        firm_id=x_firm_id,
        can_view_cost=principal.has_permission("PRODUCT_VIEW_COST_PRICE"),
    )


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[ProductScope, Depends(product_scope)],
    ) -> ProductScope:
        return scope

    return Depends(dependency)


ProductViewScope = Annotated[ProductScope, _permission("PRODUCT_VIEW")]
ProductCreateScope = Annotated[ProductScope, _permission("PRODUCT_CREATE")]
ProductUpdateScope = Annotated[ProductScope, _permission("PRODUCT_UPDATE")]
ProductDeleteScope = Annotated[ProductScope, _permission("PRODUCT_DELETE")]
ProductRestoreScope = Annotated[ProductScope, _permission("PRODUCT_RESTORE")]
ProductImportScope = Annotated[ProductScope, _permission("PRODUCT_IMPORT")]
ProductExportScope = Annotated[ProductScope, _permission("PRODUCT_EXPORT")]


@router.get("", response_model=PaginatedResponse[ProductResponse])
def list_products(
    scope: ProductViewScope,
    page: int = 1,
    page_size: int = 20,
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
        data=[_response(row, can_view_cost=scope.can_view_cost, db=db) for row in rows],
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
    return ApiResponse(data=_response(row, can_view_cost=scope.can_view_cost, db=db))


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
                _response(row, can_view_cost=scope.can_view_cost, db=db) for row in rows
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
        data=[_response(row, can_view_cost=scope.can_view_cost, db=db) for row in rows]
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
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).get_product(
        product_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=_response(row, can_view_cost=scope.can_view_cost, db=db))


@router.put("/{product_id}", response_model=ApiResponse[ProductResponse])
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductResponse]:
    row = ProductService(db).update_product(
        product_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_response(row, can_view_cost=scope.can_view_cost, db=db))


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
    return ApiResponse(data=_response(row, can_view_cost=scope.can_view_cost, db=db))


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
    return ApiResponse(data=_response(row, can_view_cost=scope.can_view_cost, db=db))


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
