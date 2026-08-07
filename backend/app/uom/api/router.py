"""Firm-scoped REST endpoints for enterprise UOM and packaging framework."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db, get_platform_db
from app.core.exceptions import AuthorizationError
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


class UomScope:
    """Carry principal and resolved firm scope for UOM endpoints."""

    def __init__(self, principal: Principal, firm_id: UUID) -> None:
        self.principal = principal
        self.firm_id = firm_id

    @property
    def actor_id(self) -> UUID:
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("UOM operations require a user principal.")
        return self.principal.subject


def uom_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_platform_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> UomScope:
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
        return UomScope(principal, x_firm_id)
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
    return UomScope(principal, x_firm_id)


def _permission(code: str) -> object:
    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[UomScope, Depends(uom_scope)],
    ) -> UomScope:
        return scope

    return Depends(dependency)


UomViewScope = Annotated[UomScope, _permission("UOM_VIEW")]
UomManageScope = Annotated[UomScope, _permission("UOM_MANAGE")]
PackagingManageScope = Annotated[UomScope, _permission("PACKAGING_MANAGE")]
ConversionManageScope = Annotated[UomScope, _permission("CONVERSION_RULE_MANAGE")]


@router.get("/uoms", response_model=ApiResponse[list[UomResponse]])
def list_uoms(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[UomResponse]]:
    rows = UomService(db).list_uoms(include_inactive=include_inactive)
    return ApiResponse(data=[UomResponse.model_validate(row) for row in rows])


@router.post("/uoms", response_model=ApiResponse[UomResponse], status_code=status.HTTP_201_CREATED)
def create_uom(
    data: UomCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomResponse]:
    row = UomService(db).create_uom(data, actor_id=scope.actor_id)
    return ApiResponse(data=UomResponse.model_validate(row))


@router.put("/uoms/{uom_id}", response_model=ApiResponse[UomResponse])
def update_uom(
    uom_id: UUID,
    data: UomUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomResponse]:
    row = UomService(db).update_uom(uom_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=UomResponse.model_validate(row))


@router.delete("/uoms/{uom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom(
    uom_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    UomService(db).delete_uom(uom_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/uom-groups", response_model=ApiResponse[list[UomGroupResponse]])
def list_uom_groups(scope: UomViewScope, db: Session = Depends(get_db)) -> ApiResponse[list[UomGroupResponse]]:
    rows = UomService(db).list_uom_groups()
    return ApiResponse(data=[UomGroupResponse.model_validate(row) for row in rows])


@router.post("/uom-groups", response_model=ApiResponse[UomGroupResponse], status_code=status.HTTP_201_CREATED)
def create_uom_group(
    data: UomGroupCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomGroupResponse]:
    row = UomService(db).create_uom_group(data, actor_id=scope.actor_id)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.put("/uom-groups/{group_id}", response_model=ApiResponse[UomGroupResponse])
def update_uom_group(
    group_id: UUID,
    data: UomGroupUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomGroupResponse]:
    row = UomService(db).update_uom_group(group_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.delete("/uom-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom_group(
    group_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    UomService(db).delete_uom_group(group_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/packaging-types", response_model=ApiResponse[list[PackagingTypeResponse]])
def list_packaging_types(scope: UomViewScope, db: Session = Depends(get_db)) -> ApiResponse[list[PackagingTypeResponse]]:
    rows = UomService(db).list_packaging_types()
    return ApiResponse(data=[PackagingTypeResponse.model_validate(row) for row in rows])


@router.post("/packaging-types", response_model=ApiResponse[PackagingTypeResponse], status_code=status.HTTP_201_CREATED)
def create_packaging_type(
    data: PackagingTypeCreate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingTypeResponse]:
    row = UomService(db).create_packaging_type(data, actor_id=scope.actor_id)
    return ApiResponse(data=PackagingTypeResponse.model_validate(row))


@router.put("/packaging-types/{packaging_type_id}", response_model=ApiResponse[PackagingTypeResponse])
def update_packaging_type(
    packaging_type_id: UUID,
    data: PackagingTypeUpdate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingTypeResponse]:
    row = UomService(db).update_packaging_type(packaging_type_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=PackagingTypeResponse.model_validate(row))


@router.delete("/packaging-types/{packaging_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packaging_type(
    packaging_type_id: UUID,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> Response:
    UomService(db).delete_packaging_type(packaging_type_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversion-rules", response_model=PaginatedResponse[ConversionRuleResponse])
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
        firm_scope=scope.firm_id, filters=filters, page=params.page, page_size=params.page_size
    )
    return PaginatedResponse(
        data=[ConversionRuleResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post("/conversion-rules", response_model=ApiResponse[ConversionRuleResponse], status_code=status.HTTP_201_CREATED)
def create_conversion_rule(
    data: ConversionRuleCreate,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionRuleResponse]:
    row = UomService(db).create_conversion_rule(data, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=ConversionRuleResponse.model_validate(row))


@router.put("/conversion-rules/{rule_id}", response_model=ApiResponse[ConversionRuleResponse])
def update_conversion_rule(
    rule_id: UUID,
    data: ConversionRuleUpdate,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionRuleResponse]:
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
    UomService(db).delete_conversion_rule(rule_id, firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/convert", response_model=ApiResponse[ConversionResponse])
def convert(
    request: ConversionRequest,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ConversionResponse]:
    response = UomService(db).convert_quantity(request, firm_scope=scope.firm_id)
    return ApiResponse(data=response)


@router.get("/profiles/{profile_id}/defaults", response_model=ApiResponse[BusinessProfileUomDefaultResponse | None])
def get_profile_defaults(
    profile_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileUomDefaultResponse | None]:
    row = UomService(db).get_profile_default(firm_scope=scope.firm_id, profile_id=profile_id)
    return ApiResponse(
        data=BusinessProfileUomDefaultResponse.model_validate(row) if row else None
    )


@router.put("/profiles/{profile_id}/defaults", response_model=ApiResponse[BusinessProfileUomDefaultResponse])
def upsert_profile_defaults(
    profile_id: UUID,
    data: BusinessProfileUomDefaultUpsert,
    scope: ConversionManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileUomDefaultResponse]:
    row = UomService(db).upsert_profile_default(
        firm_scope=scope.firm_id,
        profile_id=profile_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=BusinessProfileUomDefaultResponse.model_validate(row))


@router.get("/products/{product_id}/config", response_model=ApiResponse[ProductUomConfigResponse | None])
def get_product_config(
    product_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductUomConfigResponse | None]:
    row = UomService(db).get_product_config(firm_scope=scope.firm_id, product_id=product_id)
    return ApiResponse(data=ProductUomConfigResponse.model_validate(row) if row else None)


@router.put("/products/{product_id}/config", response_model=ApiResponse[ProductUomConfigResponse])
def upsert_product_config(
    product_id: UUID,
    data: ProductUomConfigUpsert,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProductUomConfigResponse]:
    row = UomService(db).upsert_product_config(
        firm_scope=scope.firm_id, product_id=product_id, data=data, actor_id=scope.actor_id
    )
    return ApiResponse(data=ProductUomConfigResponse.model_validate(row))


@router.get("/products/{product_id}/packaging-levels", response_model=ApiResponse[list[PackagingLevelResponse]])
def list_packaging_levels(
    product_id: UUID,
    scope: UomViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[PackagingLevelResponse]]:
    rows = UomService(db).list_packaging_levels(firm_scope=scope.firm_id, product_id=product_id)
    return ApiResponse(data=[PackagingLevelResponse.model_validate(row) for row in rows])


@router.post("/products/{product_id}/packaging-levels", response_model=ApiResponse[PackagingLevelResponse], status_code=status.HTTP_201_CREATED)
def create_packaging_level(
    product_id: UUID,
    data: PackagingLevelCreate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingLevelResponse]:
    row = UomService(db).create_packaging_level(
        firm_scope=scope.firm_id, product_id=product_id, data=data, actor_id=scope.actor_id
    )
    return ApiResponse(data=PackagingLevelResponse.model_validate(row))


@router.put("/products/{product_id}/packaging-levels/{level_id}", response_model=ApiResponse[PackagingLevelResponse])
def update_packaging_level(
    product_id: UUID,
    level_id: UUID,
    data: PackagingLevelUpdate,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[PackagingLevelResponse]:
    row = UomService(db).update_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        level_id=level_id,
        data=data,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=PackagingLevelResponse.model_validate(row))


@router.delete("/products/{product_id}/packaging-levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packaging_level(
    product_id: UUID,
    level_id: UUID,
    scope: PackagingManageScope,
    db: Session = Depends(get_db),
) -> Response:
    UomService(db).delete_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        level_id=level_id,
        actor_id=scope.actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/industry-templates", response_model=ApiResponse[list[IndustryTemplateResponse]])
def list_industry_templates(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[IndustryTemplateResponse]]:
    rows = UomService(db).list_industry_templates(include_inactive=include_inactive)
    return ApiResponse(data=[IndustryTemplateResponse.model_validate(row) for row in rows])


@router.post("/industry-templates", response_model=ApiResponse[IndustryTemplateResponse], status_code=status.HTTP_201_CREATED)
def create_industry_template(
    data: IndustryTemplateCreate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[IndustryTemplateResponse]:
    row = UomService(db).create_industry_template(data, actor_id=scope.actor_id)
    return ApiResponse(data=IndustryTemplateResponse.model_validate(row))


@router.put("/industry-templates/{template_id}", response_model=ApiResponse[IndustryTemplateResponse])
def update_industry_template(
    template_id: UUID,
    data: IndustryTemplateUpdate,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[IndustryTemplateResponse]:
    row = UomService(db).update_industry_template(template_id, data, actor_id=scope.actor_id)
    return ApiResponse(data=IndustryTemplateResponse.model_validate(row))


@router.delete("/industry-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_industry_template(
    template_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    UomService(db).delete_industry_template(template_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
