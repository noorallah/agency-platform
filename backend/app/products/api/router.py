"""Firm-scoped REST endpoints for enterprise product master management."""

# ruff: noqa: D103

from decimal import Decimal
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

from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.file_import import template_csv as columns_template_csv
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.imports.services import columns_for_kind, mapped_content, parse_mapping
from app.inventory.services.repacking import RepackResponse, RepackService
from app.products.models import Product
from app.products.schemas import (
    BulkProductRequest,
    ProductAttributeResponse,
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
from app.products.schemas.labels import ProductLabelRequest
from app.products.services import ProductService
from app.products.services.barcode_labels import (
    BarcodeLabelService,
    LabelRequestItem,
)
from app.products.services.brands import (
    BrandResponse,
    BrandService,
    BrandWrite,
    PrincipalResponse,
    PrincipalWrite,
)
from app.products.services.kits import (
    KitAssemblyWrite,
    KitComponentResponse,
    KitComponentsWrite,
    KitService,
)
from app.products.services.price_revisions import COLUMNS as REVISION_COLUMNS
from app.products.services.price_revisions import (
    PriceRevisionFileImporter,
    PriceRevisionResponse,
    PriceRevisionService,
    PriceRevisionWrite,
)
from app.products.services.product_import import template_csv, template_workbook
from app.products.services.product_service import PRODUCT_DUTIES


def _can_view_cost(scope: ResolvedFirmScope) -> bool:
    """Return whether the caller may see cost prices.

    This was a field on a bespoke product scope class; it is only a projection
    of a permission, so it does not justify a private scope resolver.
    """
    return scope.principal.has_permission("PRODUCT_VIEW_COST_PRICE")


def _withheld_duties(scope: ResolvedFirmScope) -> frozenset[str]:
    """Return the product duties the caller does not hold.

    ``PRODUCT_PRICING_MANAGE``, ``PRODUCT_TAX_MANAGE`` and
    ``PRODUCT_ATTRIBUTE_MANAGE`` were seeded and read by no route, so a price,
    a tax group and the custom fields all rode on ``PRODUCT_UPDATE``
    (D-MST-10). A projection of the principal, like the cost price above,
    because the duty is over *fields* of a resource every product editor
    writes, not over an endpoint.
    """
    return frozenset(
        code for code in PRODUCT_DUTIES if not scope.principal.has_permission(code)
    )


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
    low_stock: bool = False,
    no_price: bool = False,
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
            "low_stock": low_stock,
            "no_price": no_price,
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
        data=_responses(rows, can_view_cost=_can_view_cost(scope), db=db),
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
    row = ProductService(db, withheld_duties=_withheld_duties(scope)).create_product(
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
    service = ProductService(db, withheld_duties=_withheld_duties(scope))
    if format == "json":
        if payload is None:
            raise ValidationError("payload is required for JSON import.")
        records = ProductImportRequest.model_validate_json(payload).records
        rows = service.import_products_json(
            records, firm_scope=scope.firm_id, actor_id=scope.actor_id
        )
        return ApiResponse(
            data=_responses(rows, can_view_cost=_can_view_cost(scope), db=db)
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
        data=_responses(rows, can_view_cost=_can_view_cost(scope), db=db)
    )


@router.get("/import-template")
def product_import_template(
    scope: ProductImportScope,
    format: Literal["csv", "xlsx"] = "xlsx",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the product import template (backlog 46).

    The workbook carries the sheet to fill, a notes sheet naming every column
    and what it takes, and a lists sheet with this firm's categories, units
    and tax groups -- the codes a row may name.
    """
    if format == "csv":
        return StreamingResponse(
            iter([template_csv()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="product-template.csv"'
            },
        )
    content = template_workbook(db, scope.firm_id)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="product-template.xlsx"'},
    )


@router.post("/import-file", response_model=ApiResponse[ImportReportResponse])
async def import_product_file(
    scope: ProductImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    existing: Annotated[Literal["refuse", "update"], Form()] = "refuse",
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX product file, and with ``apply`` import it whole.

    Every row is checked and every problem returned with its row number. An
    apply that finds any problem writes nothing and says so with
    ``imported: false``; the report is the answer either way, so the screen
    can list the problems for the file to be fixed and sent again.
    """
    file_format = file_format_of(file.filename)
    # A file mapped on the import screen is read as mapped (decision B3).
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "products"),
    )
    if existing == "update" and not scope.principal.has_permission("PRODUCT_UPDATE"):
        raise AuthorizationError(
            "Updating existing products from a file needs the right to edit "
            "products."
        )
    report = ProductService(
        db, withheld_duties=_withheld_duties(scope)
    ).check_product_file(
        content,
        file_format,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        existing=existing,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


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


@router.post("/labels", response_class=StreamingResponse)
def print_product_labels(
    payload: ProductLabelRequest,
    scope: ProductViewScope,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Draw price and barcode labels for the products picked (STK-16).

    A4 label sheets or a 50 x 25 mm thermal roll; the barcode is the
    product's own, else its code. Nothing is written.
    """
    pdf = BarcodeLabelService(db).product_labels(
        [LabelRequestItem(item.product_id, item.copies) for item in payload.items],
        firm_id=scope.firm_id,
        layout=payload.layout,
        skip=payload.skip,
        show_price=payload.show_price,
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="labels.pdf"'},
    )


@router.get("/principals", response_model=ApiResponse[list[PrincipalResponse]])
def list_principals(
    scope: ProductViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PrincipalResponse]]:
    """Return the firm's principals (MST-1)."""
    return ApiResponse(data=BrandService(db).principals(scope.firm_id))


@router.post(
    "/principals",
    response_model=ApiResponse[PrincipalResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_principal(
    data: PrincipalWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalResponse]:
    """Add a principal (MST-1)."""
    return ApiResponse(
        data=BrandService(db).save_principal(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.put("/principals/{principal_id}", response_model=ApiResponse[PrincipalResponse])
def update_principal(
    principal_id: UUID,
    data: PrincipalWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PrincipalResponse]:
    """Change a principal (MST-1)."""
    return ApiResponse(
        data=BrandService(db).save_principal(
            data,
            firm_id=scope.firm_id,
            actor_id=scope.actor_id,
            principal_id=principal_id,
        )
    )


@router.delete("/principals/{principal_id}", response_model=ApiResponse[None])
def delete_principal(
    principal_id: UUID,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a principal no brand names (MST-1)."""
    BrandService(db).delete_principal(
        principal_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Principal deleted.")


@router.get("/brands", response_model=ApiResponse[list[BrandResponse]])
def list_brands(
    scope: ProductViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[BrandResponse]]:
    """Return the firm's brands (MST-1)."""
    return ApiResponse(data=BrandService(db).brands(scope.firm_id))


@router.post(
    "/brands",
    response_model=ApiResponse[BrandResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_brand(
    data: BrandWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BrandResponse]:
    """Add a brand (MST-1)."""
    return ApiResponse(
        data=BrandService(db).save_brand(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.put("/brands/{brand_id}", response_model=ApiResponse[BrandResponse])
def update_brand(
    brand_id: UUID,
    data: BrandWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BrandResponse]:
    """Rename or re-file a brand; its products' brand text follows (MST-1)."""
    return ApiResponse(
        data=BrandService(db).save_brand(
            data, firm_id=scope.firm_id, actor_id=scope.actor_id, brand_id=brand_id
        )
    )


@router.delete("/brands/{brand_id}", response_model=ApiResponse[None])
def delete_brand(
    brand_id: UUID,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a brand no product carries (MST-1)."""
    BrandService(db).delete_brand(
        brand_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Brand deleted.")


@router.get("/price-revisions/import-template")
def price_revision_import_template(scope: ProductImportScope) -> StreamingResponse:
    """Download the price revision template, as CSV (MST-2)."""
    return StreamingResponse(
        iter([columns_template_csv(REVISION_COLUMNS)]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="price-revisions-template.csv"'
        },
    )


@router.post(
    "/price-revisions/import-file", response_model=ApiResponse[ImportReportResponse]
)
async def import_price_revisions(
    scope: ProductImportScope,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    apply: Annotated[bool, Form()] = False,
) -> ApiResponse[ImportReportResponse]:
    """Check a file of new rates, and with ``apply`` import it whole (MST-2)."""
    report = PriceRevisionFileImporter(db).run(
        await file.read(),
        file_format=file_format_of(file.filename),
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


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
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductCategoryResponse]:
    row = ProductService(db).create_category(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    set_etag(response, row)
    return ApiResponse(data=ProductCategoryResponse.model_validate(row))


@router.put(
    "/categories/{category_id}", response_model=ApiResponse[ProductCategoryResponse]
)
def update_category(
    category_id: UUID,
    data: ProductCategoryUpdate,
    scope: ProductUpdateScope,
    response: Response,
    expected_version: ExpectedVersion = None,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductCategoryResponse]:
    row = ProductService(db).update_category(
        category_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
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


@router.get(
    "/{product_id}/price-revisions",
    response_model=ApiResponse[list[PriceRevisionResponse]],
)
def list_price_revisions(
    product_id: UUID,
    scope: ProductViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PriceRevisionResponse]]:
    """Return a product's dated price revisions, newest first (MST-2)."""
    return ApiResponse(
        data=PriceRevisionService(db).list_for(product_id, firm_id=scope.firm_id)
    )


@router.post(
    "/{product_id}/price-revisions",
    response_model=ApiResponse[PriceRevisionResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_price_revision(
    product_id: UUID,
    data: PriceRevisionWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PriceRevisionResponse]:
    """Record new rates from a date (MST-2)."""
    return ApiResponse(
        data=PriceRevisionService(db).add(
            product_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
        )
    )


@router.delete(
    "/{product_id}/price-revisions/{revision_id}", response_model=ApiResponse[None]
)
def delete_price_revision(
    product_id: UUID,
    revision_id: UUID,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Remove a revision typed in error (MST-2)."""
    PriceRevisionService(db).delete(
        product_id, revision_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Revision deleted.")


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
    service = ProductService(db, withheld_duties=_withheld_duties(scope))
    assert_version(
        service.get_product(product_id, firm_scope=scope.firm_id).version,
        expected_version,
    )
    row = service.update_product(
        product_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        # Somebody who cannot see the cost is served null and sends it back;
        # their save must not clear what they were never shown (D-MST-5).
        may_write_cost_price=_can_view_cost(scope),
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


def _response(
    row: Product,
    *,
    can_view_cost: bool,
    db: Session,
    attributes: list[ProductAttributeResponse] | None = None,
    stock: dict[UUID, tuple[Decimal, bool]] | None = None,
) -> ProductResponse:
    """Build one product response with its attributes and its stock."""
    payload = ProductResponse.model_validate(row).model_dump(mode="python")
    payload["attributes"] = (
        ProductService(db).attribute_responses(row)
        if attributes is None
        else attributes
    )
    held = (ProductService(db).stock_for_many([row]) if stock is None else stock).get(
        row.id
    )
    if held is not None:
        payload["stock_on_hand"], payload["low_stock"] = held
    if not can_view_cost:
        payload["purchase_price"] = None
    return ProductResponse.model_validate(payload)


def _responses(
    rows: list[Product], *, can_view_cost: bool, db: Session
) -> list[ProductResponse]:
    """Build a page of responses, reading every row's attributes at once."""
    service = ProductService(db)
    attributes = service.attribute_responses_for_many(rows)
    stock = service.stock_for_many(rows)
    return [
        _response(
            row,
            can_view_cost=can_view_cost,
            db=db,
            attributes=attributes.get(row.id, []),
            stock=stock,
        )
        for row in rows
    ]


#: Assembling kits moves stock, so it needs the stock adjustment code, as a
#: repack does (STK-15).
KitAssembleScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("INVENTORY_ADJUST")
]


@router.get(
    "/{product_id}/components",
    response_model=ApiResponse[list[KitComponentResponse]],
)
def list_kit_components(
    product_id: UUID,
    scope: ProductViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[KitComponentResponse]]:
    """Return what goes into one of a kit (STK-15)."""
    service = KitService(db)
    return ApiResponse(
        data=service.responses(service.components(product_id, firm_id=scope.firm_id))
    )


@router.put(
    "/{product_id}/components",
    response_model=ApiResponse[list[KitComponentResponse]],
)
def replace_kit_components(
    product_id: UUID,
    data: KitComponentsWrite,
    scope: ProductUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[KitComponentResponse]]:
    """Replace a kit's component list (STK-15)."""
    service = KitService(db)
    rows = service.replace(
        product_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=service.responses(rows), message="Components saved.")


@router.post("/{product_id}/assemble", response_model=ApiResponse[RepackResponse])
def assemble_kits(
    product_id: UUID,
    data: KitAssemblyWrite,
    scope: KitAssembleScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RepackResponse]:
    """Make kits from their components by a repack (STK-15)."""
    repack = KitService(db).assemble(
        product_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(
        data=RepackService(db).responses([repack])[0],  # type: ignore[list-item]
        message="Kits assembled.",
    )


@router.post("/{product_id}/disassemble", response_model=ApiResponse[RepackResponse])
def disassemble_kits(
    product_id: UUID,
    data: KitAssemblyWrite,
    scope: KitAssembleScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RepackResponse]:
    """Break kits back into their components by a repack (STK-15)."""
    repack = KitService(db).assemble(
        product_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        disassemble=True,
    )
    return ApiResponse(
        data=RepackService(db).responses([repack])[0],  # type: ignore[list-item]
        message="Kits broken into components.",
    )
