"""Firm-scoped REST endpoints for enterprise UOM and packaging framework."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.uom.schemas import (
    BusinessProfileUomDefaultResponse,
    BusinessProfileUomDefaultUpsert,
    ConversionRequest,
    ConversionResponse,
    ConversionRuleCreate,
    ConversionRuleListFilters,
    ConversionRuleResponse,
    ConversionRuleUpdate,
    IndustryTemplateCreate,
    IndustryTemplateResponse,
    IndustryTemplateUpdate,
    PackagingLevelCreate,
    PackagingLevelResponse,
    PackagingLevelUpdate,
    PackagingTypeCreate,
    PackagingTypeResponse,
    PackagingTypeUpdate,
    ProductUomConfigResponse,
    ProductUomConfigUpsert,
    UomCreate,
    UomGroupCreate,
    UomGroupResponse,
    UomGroupUpdate,
    UomResponse,
    UomUpdate,
)
from app.uom.services import UomService

router = APIRouter(
    prefix="/api/v1/uom-framework",
    tags=["UOM & Packaging"],
    responses=STANDARD_ERROR_RESPONSES,
)


UomViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("UOM_VIEW")]
UomManageScope = Annotated[ResolvedFirmScope, firm_permission_scope("UOM_MANAGE")]
PackagingManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PACKAGING_MANAGE")
]
ConversionManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CONVERSION_RULE_MANAGE")
]


@router.get("/uoms", response_model=ApiResponse[list[UomResponse]])
def list_uoms(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[UomResponse]]:
    """List the unit catalogue."""
    rows = UomService(db).list_uoms(include_inactive=include_inactive)
    return ApiResponse(data=[UomResponse.model_validate(row) for row in rows])


@router.post(
    "/uoms",
    response_model=ApiResponse[UomResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_uom(
    data: UomCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomResponse]:
    """Add a unit to the catalogue."""
    row = UomService(db).create_uom(data, actor_id=scope.actor_id)
    return ApiResponse(data=UomResponse.model_validate(row))


@router.put("/uoms/{uom_id}", response_model=ApiResponse[UomResponse])
def update_uom(
    uom_id: UUID,
    data: UomUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomResponse]:
    """Change a unit in the catalogue."""
    row = UomService(db).update_uom(uom_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=UomResponse.model_validate(row))


@router.delete("/uoms/{uom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom(
    uom_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a unit that nothing references."""
    UomService(db).delete_uom(uom_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/uom-groups", response_model=ApiResponse[list[UomGroupResponse]])
def list_uom_groups(
    scope: UomViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[UomGroupResponse]]:
    """List the unit groups."""
    rows = UomService(db).list_uom_groups()
    return ApiResponse(data=[UomGroupResponse.model_validate(row) for row in rows])


@router.post(
    "/uom-groups",
    response_model=ApiResponse[UomGroupResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_uom_group(
    data: UomGroupCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomGroupResponse]:
    """Add a unit group."""
    row = UomService(db).create_uom_group(data, actor_id=scope.actor_id)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.put("/uom-groups/{group_id}", response_model=ApiResponse[UomGroupResponse])
def update_uom_group(
    group_id: UUID,
    data: UomGroupUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomGroupResponse]:
    """Change a unit group."""
    row = UomService(db).update_uom_group(group_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.delete("/uom-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom_group(
    group_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a unit group that holds no units."""
    UomService(db).delete_uom_group(group_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/packaging-types", response_model=ApiResponse[list[PackagingTypeResponse]])
def list_packaging_types(
    scope: UomViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[PackagingTypeResponse]]:
    """List the packaging types."""
    rows = UomService(db).list_packaging_types()
    return ApiResponse(data=[PackagingTypeResponse.model_validate(row) for row in rows])


@router.post(
    "/packaging-types",
    response_model=ApiResponse[PackagingTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_packaging_type(
    data: PackagingTypeCreate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingTypeResponse]:
    """Add a packaging type."""
    row = UomService(db).create_packaging_type(data, actor_id=scope.actor_id)
    return ApiResponse(data=PackagingTypeResponse.model_validate(row))


@router.put(
    "/packaging-types/{packaging_type_id}",
    response_model=ApiResponse[PackagingTypeResponse],
)
def update_packaging_type(
    packaging_type_id: UUID,
    data: PackagingTypeUpdate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingTypeResponse]:
    """Change a packaging type."""
    row = UomService(db).update_packaging_type(
        packaging_type_id, data, actor_id=scope.actor_id
    )
    return ApiResponse(data=PackagingTypeResponse.model_validate(row))


@router.delete(
    "/packaging-types/{packaging_type_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_packaging_type(
    packaging_type_id: UUID,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a packaging type no packaging level uses."""
    UomService(db).delete_packaging_type(packaging_type_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/conversion-rules", response_model=PaginatedResponse[ConversionRuleResponse]
)
def list_conversion_rules(
    scope: UomViewScope,
    page: int = 1,
    page_size: int = 20,
    product_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    from_uom_id: UUID | None = None,
    to_uom_id: UUID | None = None,
    status_value: str | None = None,
    effective_on: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ConversionRuleResponse]:
    """List this firm's conversion rules."""
    params = PaginationParams(page=page, page_size=page_size)
    filters = ConversionRuleListFilters(
        product_id=product_id,
        business_profile_id=business_profile_id,
        from_uom_id=from_uom_id,
        to_uom_id=to_uom_id,
        status=status_value,
        effective_on=effective_on,
    )
    rows, total = UomService(db).list_conversion_rules(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(
        data=[ConversionRuleResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/conversion-rules",
    response_model=ApiResponse[ConversionRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_conversion_rule(
    data: ConversionRuleCreate,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionRuleResponse]:
    """Publish a conversion rule version for a unit pair."""
    row = UomService(db).create_conversion_rule(
        data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=ConversionRuleResponse.model_validate(row))


@router.put(
    "/conversion-rules/{rule_id}", response_model=ApiResponse[ConversionRuleResponse]
)
def update_conversion_rule(
    rule_id: UUID,
    data: ConversionRuleUpdate,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionRuleResponse]:
    """Change a conversion rule."""
    row = UomService(db).update_conversion_rule(
        rule_id, data, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=ConversionRuleResponse.model_validate(row))


@router.delete("/conversion-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversion_rule(
    rule_id: UUID,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire a conversion rule."""
    UomService(db).delete_conversion_rule(
        rule_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/convert", response_model=ApiResponse[ConversionResponse])
def convert(
    request: ConversionRequest,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionResponse]:
    """Convert a quantity using the rule in force on the given date."""
    response = UomService(db).convert_quantity(request, firm_scope=scope.firm_id)
    return ApiResponse(data=response)


@router.get(
    "/profiles/{profile_id}/defaults",
    response_model=ApiResponse[BusinessProfileUomDefaultResponse | None],
)
def get_profile_defaults(
    profile_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileUomDefaultResponse | None]:
    """Read a business profile's default unit behaviour."""
    row = UomService(db).get_profile_default(
        firm_scope=scope.firm_id, profile_id=profile_id
    )
    return ApiResponse(
        data=BusinessProfileUomDefaultResponse.model_validate(row) if row else None
    )


@router.put(
    "/profiles/{profile_id}/defaults",
    response_model=ApiResponse[BusinessProfileUomDefaultResponse],
)
def upsert_profile_defaults(
    profile_id: UUID,
    data: BusinessProfileUomDefaultUpsert,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileUomDefaultResponse]:
    """Store a business profile's default unit behaviour."""
    row = UomService(db).upsert_profile_default(
        firm_scope=scope.firm_id,
        profile_id=profile_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=BusinessProfileUomDefaultResponse.model_validate(row))


@router.get(
    "/products/{product_id}/config",
    response_model=ApiResponse[ProductUomConfigResponse | None],
)
def get_product_config(
    product_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductUomConfigResponse | None]:
    """Read one product's unit configuration."""
    row = UomService(db).get_product_config(
        firm_scope=scope.firm_id, product_id=product_id
    )
    return ApiResponse(
        data=ProductUomConfigResponse.model_validate(row) if row else None
    )


@router.put(
    "/products/{product_id}/config",
    response_model=ApiResponse[ProductUomConfigResponse],
)
def upsert_product_config(
    product_id: UUID,
    data: ProductUomConfigUpsert,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductUomConfigResponse]:
    """Store one product's unit configuration."""
    row = UomService(db).upsert_product_config(
        firm_scope=scope.firm_id,
        product_id=product_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=ProductUomConfigResponse.model_validate(row))


@router.get(
    "/products/{product_id}/packaging-levels",
    response_model=ApiResponse[list[PackagingLevelResponse]],
)
def list_packaging_levels(
    product_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PackagingLevelResponse]]:
    """List a product's packaging hierarchy."""
    rows = UomService(db).list_packaging_levels(
        firm_scope=scope.firm_id, product_id=product_id
    )
    return ApiResponse(
        data=[PackagingLevelResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/products/{product_id}/packaging-levels",
    response_model=ApiResponse[PackagingLevelResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_packaging_level(
    product_id: UUID,
    data: PackagingLevelCreate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingLevelResponse]:
    """Add a level to a product's packaging hierarchy."""
    row = UomService(db).create_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=PackagingLevelResponse.model_validate(row))


@router.put(
    "/products/{product_id}/packaging-levels/{level_id}",
    response_model=ApiResponse[PackagingLevelResponse],
)
def update_packaging_level(
    product_id: UUID,
    level_id: UUID,
    data: PackagingLevelUpdate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingLevelResponse]:
    """Change a packaging level."""
    row = UomService(db).update_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        level_id=level_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=PackagingLevelResponse.model_validate(row))


@router.delete(
    "/products/{product_id}/packaging-levels/{level_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_packaging_level(
    product_id: UUID,
    level_id: UUID,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a packaging level."""
    UomService(db).delete_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        level_id=level_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/industry-templates", response_model=ApiResponse[list[IndustryTemplateResponse]]
)
def list_industry_templates(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[IndustryTemplateResponse]]:
    """List the industry UOM templates."""
    rows = UomService(db).list_industry_templates(include_inactive=include_inactive)
    return ApiResponse(
        data=[IndustryTemplateResponse.model_validate(row) for row in rows]
    )


@router.post(
    "/industry-templates",
    response_model=ApiResponse[IndustryTemplateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_industry_template(
    data: IndustryTemplateCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[IndustryTemplateResponse]:
    """Add an industry UOM template."""
    row = UomService(db).create_industry_template(data, actor_id=scope.actor_id)
    return ApiResponse(data=IndustryTemplateResponse.model_validate(row))


@router.put(
    "/industry-templates/{template_id}",
    response_model=ApiResponse[IndustryTemplateResponse],
)
def update_industry_template(
    template_id: UUID,
    data: IndustryTemplateUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[IndustryTemplateResponse]:
    """Change an industry UOM template."""
    row = UomService(db).update_industry_template(
        template_id, data, actor_id=scope.actor_id
    )
    return ApiResponse(data=IndustryTemplateResponse.model_validate(row))


@router.delete(
    "/industry-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_industry_template(
    template_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove an industry UOM template."""
    UomService(db).delete_industry_template(template_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
