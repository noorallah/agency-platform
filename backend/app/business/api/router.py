"""FastAPI routes for business profile and industry framework administration."""

# ruff: noqa: D103

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.business.models import (
    AttributeDefinition,
    AttributeEntityType,
    BusinessFeature,
    BusinessModule,
    BusinessProfile,
    CategoryAttributeRule,
)
from app.business.schemas import (
    ActiveFeatureResponse,
    ActiveModuleResponse,
    ApplicableAttributesResponse,
    AttributeDefinitionCreate,
    AttributeDefinitionResponse,
    AttributeDefinitionUpdate,
    BusinessFeatureCreate,
    BusinessFeatureResponse,
    BusinessFeatureUpdate,
    BusinessFeatureWriteResponse,
    BusinessModuleCreate,
    BusinessModuleResponse,
    BusinessModuleUpdate,
    BusinessModuleWriteResponse,
    BusinessProfileConfigurationResponse,
    BusinessProfileCreate,
    BusinessProfileResponse,
    BusinessProfileUpdate,
    BusinessProfileWriteResponse,
    CategoryAttributeRuleCreate,
    CategoryAttributeRuleResponse,
    CategoryAttributeRuleUpdate,
    FirmBusinessProfileAssign,
    FirmBusinessProfileResponse,
    FirmProfileAssignmentRow,
    IdentifierList,
    ProfileStoreOutcome,
)
from app.business.services import AttributeService, BusinessProfileFrameworkService
from app.business.services.firm_custom_fields import FirmCustomFieldService
from app.business.services.profile_replication import (
    other_profile_stores,
    replicate,
    replicate_feature,
    replicate_module,
    replicate_profile,
)
from app.business.services.profile_replication import (
    summary as replication_summary,
)
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import (
    firm_store_session,
    get_db,
    get_platform_db,
)
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ResourceNotFoundError,
)
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    require_authenticated,
    require_platform_admin,
)
from app.firms.models import Firm
from app.identity.models import UserFirm

router = APIRouter(
    prefix="/api/v1/business-framework",
    tags=["Business framework"],
    responses=STANDARD_ERROR_RESPONSES,
)
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _service(db: Session) -> BusinessProfileFrameworkService:
    return BusinessProfileFrameworkService(db)


def _actor_id(principal: Principal) -> UUID:
    if not isinstance(principal.subject, UUID):
        raise RuntimeError(
            "Business framework administration requires a user principal."
        )
    return principal.subject


@router.get("/profiles", response_model=PaginatedResponse[BusinessProfileResponse])
def list_profiles(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[BusinessProfileResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_profiles(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[BusinessProfileResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/profiles",
    response_model=ApiResponse[BusinessProfileWriteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    data: BusinessProfileCreate,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[BusinessProfileWriteResponse]:
    """Create a profile here, then in every other store under the same id.

    Backlog 17: each store keeps its own catalogue, so a profile that reached
    only the caller's store could be offered and then refused for a firm
    elsewhere. The response says what happened in each other store.
    """
    actor_id = _actor_id(principal)
    row = _service(db).create_profile(data, actor_id)
    return _replicated(row, request, platform_db, actor_id)


def _replicated(
    row: BusinessProfile, request: Request, platform_db: Session, actor_id: UUID
) -> ApiResponse[BusinessProfileWriteResponse]:
    """Carry a saved profile to every other store and report each (backlog 17)."""
    outcomes = replicate_profile(
        row, other_profile_stores(request, platform_db), actor_id
    )
    body = BusinessProfileResponse.model_validate(row).model_dump()
    message = replication_summary(outcomes)
    failed = any(item.status == "FAILED" for item in outcomes)
    return ApiResponse(
        data=BusinessProfileWriteResponse(
            **body, stores=outcomes, warning=message if failed else None
        ),
        message=message,
    )


@router.get(
    "/profiles/{profile_id}", response_model=ApiResponse[BusinessProfileResponse]
)
def get_profile(
    profile_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileResponse]:
    return ApiResponse(
        data=BusinessProfileResponse.model_validate(
            _service(db).get_profile(profile_id)
        )
    )


@router.put(
    "/profiles/{profile_id}",
    response_model=ApiResponse[BusinessProfileWriteResponse],
)
def update_profile(
    profile_id: UUID,
    data: BusinessProfileUpdate,
    principal: PlatformPrincipal,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessProfileWriteResponse]:
    """Change a profile here, then in every other store (backlog 17)."""
    actor_id = _actor_id(principal)
    row = _service(db).update_profile(profile_id, data, actor_id, expected_version)
    set_etag(response, row)
    return _replicated(row, request, platform_db, actor_id)


@router.delete(
    "/profiles/{profile_id}", response_model=ApiResponse[list[ProfileStoreOutcome]]
)
def delete_profile(
    profile_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[ProfileStoreOutcome]]:
    """Delete a profile here, then in every other store (backlog 17).

    A store where a firm is assigned the profile refuses, as this store would,
    and is reported by name rather than skipped.
    """
    actor_id = _actor_id(principal)
    _service(db).delete_profile(profile_id, actor_id)
    row = db.get(BusinessProfile, profile_id)
    outcomes = (
        []
        if row is None
        else replicate_profile(
            row, other_profile_stores(request, platform_db), actor_id
        )
    )
    return ApiResponse(data=outcomes, message=replication_summary(outcomes))


@router.get("/features", response_model=PaginatedResponse[BusinessFeatureResponse])
def list_features(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[BusinessFeatureResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_features(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[BusinessFeatureResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/features",
    response_model=ApiResponse[BusinessFeatureWriteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_feature(
    data: BusinessFeatureCreate,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[BusinessFeatureWriteResponse]:
    """Create a feature here, then in every other store under the same id (MST-7)."""
    actor_id = _actor_id(principal)
    row = _service(db).create_feature(data, actor_id)
    return _replicated_feature(row, request, platform_db, actor_id)


@router.put(
    "/features/{feature_id}", response_model=ApiResponse[BusinessFeatureResponse]
)
def update_feature(
    feature_id: UUID,
    data: BusinessFeatureUpdate,
    principal: PlatformPrincipal,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessFeatureWriteResponse]:
    """Change a feature here, then in every other store (MST-7)."""
    actor_id = _actor_id(principal)
    row = _service(db).update_feature(feature_id, data, actor_id, expected_version)
    set_etag(response, row)
    return _replicated_feature(row, request, platform_db, actor_id)


def _replicated_feature(
    row: BusinessFeature, request: Request, platform_db: Session, actor_id: UUID
) -> ApiResponse[BusinessFeatureWriteResponse]:
    """Carry a saved feature to every other store and report each (MST-7)."""
    outcomes = replicate_feature(
        row, other_profile_stores(request, platform_db), actor_id
    )
    body = BusinessFeatureResponse.model_validate(row).model_dump()
    message = replication_summary(outcomes)
    failed = any(item.status == "FAILED" for item in outcomes)
    return ApiResponse(
        data=BusinessFeatureWriteResponse(
            **body, stores=outcomes, warning=message if failed else None
        ),
        message=message,
    )


@router.delete(
    "/features/{feature_id}", response_model=ApiResponse[list[ProfileStoreOutcome]]
)
def delete_feature(
    feature_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[ProfileStoreOutcome]]:
    """Delete a feature here, then in every other store (MST-7).

    A store where a profile still enables it refuses, as this store would,
    and is reported by name rather than skipped.
    """
    actor_id = _actor_id(principal)
    _service(db).delete_feature(feature_id, actor_id)
    row = db.get(BusinessFeature, feature_id)
    outcomes = (
        []
        if row is None
        else replicate_feature(
            row, other_profile_stores(request, platform_db), actor_id
        )
    )
    return ApiResponse(data=outcomes, message=replication_summary(outcomes))


@router.get("/modules", response_model=PaginatedResponse[BusinessModuleResponse])
def list_modules(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[BusinessModuleResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_modules(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[BusinessModuleResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/modules",
    response_model=ApiResponse[BusinessModuleWriteResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_module(
    data: BusinessModuleCreate,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[BusinessModuleWriteResponse]:
    """Create a module here, then in every other store under the same id (MST-7)."""
    actor_id = _actor_id(principal)
    row = _service(db).create_module(data, actor_id)
    return _replicated_module(row, request, platform_db, actor_id)


@router.put("/modules/{module_id}", response_model=ApiResponse[BusinessModuleResponse])
def update_module(
    module_id: UUID,
    data: BusinessModuleUpdate,
    principal: PlatformPrincipal,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessModuleWriteResponse]:
    """Change a module here, then in every other store (MST-7)."""
    actor_id = _actor_id(principal)
    row = _service(db).update_module(module_id, data, actor_id, expected_version)
    set_etag(response, row)
    return _replicated_module(row, request, platform_db, actor_id)


def _replicated_module(
    row: BusinessModule, request: Request, platform_db: Session, actor_id: UUID
) -> ApiResponse[BusinessModuleWriteResponse]:
    """Carry a saved module to every other store and report each (MST-7)."""
    outcomes = replicate_module(
        row, other_profile_stores(request, platform_db), actor_id
    )
    body = BusinessModuleResponse.model_validate(row).model_dump()
    message = replication_summary(outcomes)
    failed = any(item.status == "FAILED" for item in outcomes)
    return ApiResponse(
        data=BusinessModuleWriteResponse(
            **body, stores=outcomes, warning=message if failed else None
        ),
        message=message,
    )


@router.delete(
    "/modules/{module_id}", response_model=ApiResponse[list[ProfileStoreOutcome]]
)
def delete_module(
    module_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[ProfileStoreOutcome]]:
    """Delete a module here, then in every other store (MST-7)."""
    actor_id = _actor_id(principal)
    _service(db).delete_module(module_id, actor_id)
    row = db.get(BusinessModule, module_id)
    outcomes = (
        []
        if row is None
        else replicate_module(row, other_profile_stores(request, platform_db), actor_id)
    )
    return ApiResponse(data=outcomes, message=replication_summary(outcomes))


#: A firm's own custom fields (MST-8).
CustomFieldViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOM_FIELD_VIEW")
]
CustomFieldManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("CUSTOM_FIELD_MANAGE")
]


@router.get(
    "/firm-custom-fields",
    response_model=ApiResponse[list[AttributeDefinitionResponse]],
)
def list_firm_custom_fields(
    scope: CustomFieldViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AttributeDefinitionResponse]]:
    """Return the firm's own fields and the shared ones (MST-8).

    A row with ``firm_id`` is the firm's own and its to change; one without
    is the shared catalogue, read-only here.
    """
    return ApiResponse(
        data=[
            AttributeDefinitionResponse.model_validate(row)
            for row in FirmCustomFieldService(db).list_fields(scope.firm_id)
        ]
    )


@router.post(
    "/firm-custom-fields",
    response_model=ApiResponse[AttributeDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_firm_custom_field(
    data: AttributeDefinitionCreate,
    scope: CustomFieldManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AttributeDefinitionResponse]:
    """Add a custom field of the firm's own (MST-8)."""
    row = FirmCustomFieldService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=AttributeDefinitionResponse.model_validate(row))


@router.put(
    "/firm-custom-fields/{field_id}",
    response_model=ApiResponse[AttributeDefinitionResponse],
)
def update_firm_custom_field(
    field_id: UUID,
    data: AttributeDefinitionUpdate,
    scope: CustomFieldManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AttributeDefinitionResponse]:
    """Change a field of the firm's own; a held type cannot change (MST-8)."""
    row = FirmCustomFieldService(db).update(
        field_id, data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=AttributeDefinitionResponse.model_validate(row))


@router.delete("/firm-custom-fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_firm_custom_field(
    field_id: UUID,
    scope: CustomFieldManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a field of the firm's own that holds no values (MST-8)."""
    FirmCustomFieldService(db).delete(
        field_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/firm-custom-field-rules",
    response_model=ApiResponse[list[CategoryAttributeRuleResponse]],
)
def list_firm_custom_field_rules(
    scope: CustomFieldViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CategoryAttributeRuleResponse]]:
    """Return the firm's own category rules (MST-8)."""
    service = _service(db)
    rows = FirmCustomFieldService(db).list_rules(scope.firm_id)
    described = service.describe_category_rules(rows)
    return ApiResponse(data=[_rule_response(row, service, described) for row in rows])


@router.post(
    "/firm-custom-field-rules",
    response_model=ApiResponse[CategoryAttributeRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_firm_custom_field_rule(
    data: CategoryAttributeRuleCreate,
    scope: CustomFieldManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CategoryAttributeRuleResponse]:
    """Require a field in one category, for this firm alone (MST-8)."""
    row = FirmCustomFieldService(db).create_rule(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=_rule_response(row, _service(db)))


@router.delete(
    "/firm-custom-field-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_firm_custom_field_rule(
    rule_id: UUID,
    scope: CustomFieldManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove one of the firm's own category rules (MST-8)."""
    FirmCustomFieldService(db).delete_rule(
        rule_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/attribute-definitions",
    response_model=PaginatedResponse[AttributeDefinitionResponse],
)
def list_attribute_definitions(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[AttributeDefinitionResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_attributes(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[AttributeDefinitionResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get(
    "/attribute-definitions/applicable",
    response_model=ApiResponse[ApplicableAttributesResponse],
)
def applicable_attribute_definitions(
    entity_type: AttributeEntityType,
    principal: Annotated[Principal, Depends(require_authenticated())],
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> ApiResponse[ApplicableAttributesResponse]:
    """Answer which custom fields a form should offer for one entity type.

    `GET /attribute-definitions` is the platform's catalogue, every
    definition for every profile, and the product form already had a
    firm-resolved answer in `/products/metadata`. Customers and vendors
    needed the same question answered without a product in it. Membership
    of the firm is the whole gate: what fields a record carries is not a
    privilege, filling them in is, and that is checked on the save.
    """
    firm_id = _resolve_firm_scope(principal, platform_db, x_firm_id, None)
    if firm_id is None:
        raise AuthorizationError("Select a firm to read its custom fields.")
    attributes = AttributeService(db)
    rows = attributes.definitions_for(entity_type.value, firm_id=firm_id)
    mandatory = attributes.mandatory_ids(entity_type.value, firm_id=firm_id)
    return ApiResponse(
        data=ApplicableAttributesResponse(
            entity_type=entity_type,
            definitions=[AttributeDefinitionResponse.model_validate(r) for r in rows],
            mandatory_ids=sorted(mandatory, key=str),
        )
    )


@router.post(
    "/attribute-definitions",
    response_model=ApiResponse[AttributeDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_attribute_definition(
    data: AttributeDefinitionCreate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[AttributeDefinitionResponse]:
    service = _service(db)
    row = service.create_attribute(data, _actor_id(principal))
    return _attribute_response(
        row, service.mandatory_warning(row) if row.mandatory else None
    )


def _attribute_response(
    row: AttributeDefinition, warning: str | None
) -> ApiResponse[AttributeDefinitionResponse]:
    """Answer an attribute save, with any mandatory warning (backlog 16)."""
    body = AttributeDefinitionResponse.model_validate(row)
    return ApiResponse(
        data=body.model_copy(update={"warning": warning}), message=warning
    )


@router.put(
    "/attribute-definitions/{attribute_id}",
    response_model=ApiResponse[AttributeDefinitionResponse],
)
def update_attribute_definition(
    attribute_id: UUID,
    data: AttributeDefinitionUpdate,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[AttributeDefinitionResponse]:
    service = _service(db)
    was_mandatory = service.get_attribute(attribute_id).mandatory
    row = service.update_attribute(
        attribute_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    newly = row.mandatory and not was_mandatory
    return _attribute_response(row, service.mandatory_warning(row) if newly else None)


@router.delete(
    "/attribute-definitions/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_attribute_definition(
    attribute_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_attribute(attribute_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _rule_response(
    row: CategoryAttributeRule,
    service: BusinessProfileFrameworkService,
    described: dict[UUID, tuple[str | None, str | None, str | None]] | None = None,
) -> CategoryAttributeRuleResponse:
    """Build one rule response, names included."""
    lookup = (
        described if described is not None else service.describe_category_rules([row])
    )
    attribute_code, attribute_name, profile_code = lookup.get(
        row.id, (None, None, None)
    )
    response = CategoryAttributeRuleResponse.model_validate(row)
    return response.model_copy(
        update={
            "attribute_code": attribute_code,
            "attribute_name": attribute_name,
            "business_profile_code": profile_code,
        }
    )


@router.get(
    "/category-attribute-rules",
    response_model=PaginatedResponse[CategoryAttributeRuleResponse],
)
def list_category_rules(
    principal: PlatformPrincipal,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["category_code", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
) -> PaginatedResponse[CategoryAttributeRuleResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    service = _service(db)
    rows, total = service.list_category_rules(
        params.page, params.page_size, search, sort_by, sort_direction == "desc"
    )
    return PaginatedResponse(
        data=[_rule_response(row, service) for row in rows],
        pagination=params.metadata(total),
    )


@router.post(
    "/category-attribute-rules",
    response_model=ApiResponse[CategoryAttributeRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_category_rule(
    data: CategoryAttributeRuleCreate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[CategoryAttributeRuleResponse]:
    service = _service(db)
    row = service.create_category_rule(data, _actor_id(principal))
    warning = (
        service.mandatory_warning(service.get_attribute(row.attribute_definition_id))
        if row.is_mandatory
        else None
    )
    body = _rule_response(row, service).model_copy(update={"warning": warning})
    return ApiResponse(data=body, message=warning)


@router.put(
    "/category-attribute-rules/{rule_id}",
    response_model=ApiResponse[CategoryAttributeRuleResponse],
)
def update_category_rule(
    rule_id: UUID,
    data: CategoryAttributeRuleUpdate,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[CategoryAttributeRuleResponse]:
    service = _service(db)
    was_mandatory = service.get_category_rule(rule_id).is_mandatory
    row = service.update_category_rule(
        rule_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    warning = (
        service.mandatory_warning(service.get_attribute(row.attribute_definition_id))
        if row.is_mandatory and not was_mandatory
        else None
    )
    body = _rule_response(row, service).model_copy(update={"warning": warning})
    return ApiResponse(data=body, message=warning)


@router.delete(
    "/category-attribute-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_category_rule(
    rule_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_category_rule(rule_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/profiles/{profile_id}/configuration",
    response_model=ApiResponse[BusinessProfileConfigurationResponse],
)
def get_profile_configuration(
    profile_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileConfigurationResponse]:
    feature_ids, module_ids = _service(db).profile_configuration(profile_id)
    return ApiResponse(
        data=BusinessProfileConfigurationResponse(
            feature_ids=feature_ids, module_ids=module_ids
        )
    )


@router.put(
    "/profiles/{profile_id}/features",
    response_model=ApiResponse[list[ProfileStoreOutcome]],
)
def set_profile_features(
    profile_id: UUID,
    data: IdentifierList,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[ProfileStoreOutcome]]:
    """Set the profile's features here, then in every other store (backlog 17)."""
    actor_id = _actor_id(principal)
    _service(db).set_profile_features(profile_id, data.ids, actor_id)

    def apply(service: BusinessProfileFrameworkService) -> str:
        """Set the same features in one other store."""
        service.set_profile_features(profile_id, data.ids, actor_id)
        return "updated"

    outcomes = replicate(other_profile_stores(request, platform_db), apply)
    return ApiResponse(data=outcomes, message=replication_summary(outcomes))


@router.put(
    "/profiles/{profile_id}/modules",
    response_model=ApiResponse[list[ProfileStoreOutcome]],
)
def set_profile_modules(
    profile_id: UUID,
    data: IdentifierList,
    principal: PlatformPrincipal,
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[ProfileStoreOutcome]]:
    """Set the profile's modules here, then in every other store (backlog 17)."""
    actor_id = _actor_id(principal)
    _service(db).set_profile_modules(profile_id, data.ids, actor_id)

    def apply(service: BusinessProfileFrameworkService) -> str:
        """Set the same modules in one other store."""
        service.set_profile_modules(profile_id, data.ids, actor_id)
        return "updated"

    outcomes = replicate(other_profile_stores(request, platform_db), apply)
    return ApiResponse(data=outcomes, message=replication_summary(outcomes))


@router.put(
    "/firms/{firm_id}/profile-assignment",
    response_model=ApiResponse[FirmBusinessProfileResponse],
)
def assign_profile_to_firm(
    firm_id: UUID,
    data: FirmBusinessProfileAssign,
    principal: PlatformPrincipal,
    request: Request,
) -> ApiResponse[FirmBusinessProfileResponse]:
    """Assign one business profile to a firm, in **that firm's** store.

    Deliberately not `get_db`. This is a platform screen administering a
    firm-owned record, so routing by the caller's `X-Firm-ID` wrote the
    assignment into whichever firm the administrator happened to have
    selected -- and returned success. The firm named in the URL kept its old
    profile, and a row claiming otherwise sat in a store that firm never
    reads. Proven against the seeded demo: assigning to ELEC01 while WHOLE01
    was selected left ELEC01 untouched and put the row in `wholesale_hub`.
    """
    with firm_store_session(request, firm_id) as db:
        row = _service(db).assign_profile_to_firm(firm_id, data, _actor_id(principal))
        return ApiResponse(data=FirmBusinessProfileResponse.model_validate(row))


@router.get(
    "/firms/{firm_id}/profiles",
    response_model=ApiResponse[list[BusinessProfileResponse]],
)
def list_firm_profile_catalogue(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
) -> ApiResponse[list[BusinessProfileResponse]]:
    """List the profiles one firm may be assigned, from **that firm's** store.

    `GET /profiles` reads the caller's own store, which in platform mode is
    none at all -- so the Firms setup panel, which assigns a profile to a firm
    the administrator is not inside, had nothing to offer. The catalogue is
    per store, so a dedicated firm's list is its own.
    """
    with firm_store_session(request, firm_id) as db:
        rows, _ = _service(db).list_profiles(1, MAX_PAGE_SIZE, None, "code", False)
        return ApiResponse(
            data=[BusinessProfileResponse.model_validate(row) for row in rows]
        )


@router.get(
    "/firms/{firm_id}/profile-assignment",
    response_model=ApiResponse[FirmBusinessProfileResponse | None],
)
def get_firm_profile_assignment(
    firm_id: UUID,
    principal: PlatformPrincipal,
    request: Request,
) -> ApiResponse[FirmBusinessProfileResponse | None]:
    """Return one firm's assignment, read from that firm's own store."""
    with firm_store_session(request, firm_id) as db:
        row = _service(db).get_firm_assignment(firm_id)
        return ApiResponse(
            data=(
                FirmBusinessProfileResponse.model_validate(row)
                if row is not None
                else None
            )
        )


@router.get(
    "/firm-profile-assignments",
    response_model=ApiResponse[list[FirmProfileAssignmentRow]],
)
def list_firm_profile_assignments(
    principal: PlatformPrincipal,
    request: Request,
    platform_db: Session = Depends(get_platform_db),
) -> ApiResponse[list[FirmProfileAssignmentRow]]:
    """List every firm with the profile it is assigned.

    There is no single query for this. Assignments live in each firm's own
    store, and the firms are spread across the shared schema, dedicated
    schemas and dedicated databases -- so this iterates, the same way
    `scripts/migrate_all_stores.py` does, and for the same reason.

    A firm whose store cannot be read is reported with `unavailable_reason`
    rather than dropped or blanked: an unprovisioned firm and a firm with no
    profile are different facts, and a grid that renders them identically
    invites the administrator to "fix" the wrong one.
    """
    firms = list(
        platform_db.scalars(
            select(Firm).where(Firm.is_deleted.is_(False)).order_by(Firm.code.asc())
        ).all()
    )
    rows: list[FirmProfileAssignmentRow] = []
    for firm in firms:
        base = {
            "firm_id": firm.id,
            "firm_code": firm.code,
            "firm_name": firm.name,
        }
        try:
            with firm_store_session(request, firm.id) as firm_db:
                assignment = _service(firm_db).get_firm_assignment(firm.id)
                if assignment is None:
                    rows.append(FirmProfileAssignmentRow(**base))
                    continue
                # Named from the same session that answered the assignment.
                # The profile catalogue lives in every firm store too, so a
                # lookup against the platform store would resolve some ids and
                # not others depending on which firms were seeded there.
                profile = firm_db.get(BusinessProfile, assignment.business_profile_id)
                rows.append(
                    FirmProfileAssignmentRow(
                        **base,
                        business_profile_id=assignment.business_profile_id,
                        business_profile_code=None if profile is None else profile.code,
                        business_profile_name=None if profile is None else profile.name,
                        is_active=assignment.is_active,
                        notes=assignment.notes,
                    )
                )
        except (BusinessRuleError, ResourceNotFoundError, SQLAlchemyError) as error:
            rows.append(FirmProfileAssignmentRow(**base, unavailable_reason=str(error)))
    return ApiResponse(data=rows)


@router.get("/active-features", response_model=ApiResponse[list[ActiveFeatureResponse]])
def get_active_features(
    principal: Annotated[Principal, Depends(require_authenticated())],
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
    firm_id: Annotated[UUID | None, Query()] = None,
) -> ApiResponse[list[ActiveFeatureResponse]]:
    resolved_firm = _resolve_firm_scope(principal, platform_db, x_firm_id, firm_id)
    rows = _read_in_firm_store(
        request,
        db,
        x_firm_id,
        resolved_firm,
        lambda service: service.active_features(resolved_firm),
    )
    return ApiResponse(
        data=[
            ActiveFeatureResponse(
                id=feature.id,
                code=feature.code,
                name=feature.name,
                category=feature.category,
                configuration=configuration,
            )
            for feature, configuration in rows
        ]
    )


@router.get("/active-modules", response_model=ApiResponse[list[ActiveModuleResponse]])
def get_active_modules(
    principal: Annotated[Principal, Depends(require_authenticated())],
    request: Request,
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
    firm_id: Annotated[UUID | None, Query()] = None,
) -> ApiResponse[list[ActiveModuleResponse]]:
    resolved_firm = _resolve_firm_scope(principal, platform_db, x_firm_id, firm_id)
    rows = _read_in_firm_store(
        request,
        db,
        x_firm_id,
        resolved_firm,
        lambda service: service.active_modules(resolved_firm),
    )
    return ApiResponse(
        data=[
            ActiveModuleResponse(
                id=module.id,
                code=module.code,
                name=module.name,
                ui_route=module.ui_route,
                display_order=display_order,
            )
            for module, display_order in rows
        ]
    )


def _read_in_firm_store[T](
    request: Request,
    db: Session,
    x_firm_id: UUID | None,
    firm_id: UUID | None,
    read: Callable[[BusinessProfileFrameworkService], T],
) -> T:
    """Answer from the store of the firm asked about, not the caller's.

    ``?firm_id=`` may name a firm other than the one ``X-Firm-ID`` selected,
    and the assignment lives in the named firm's store. Reading it through
    ``get_db`` answered from whichever store the header opened -- another
    firm's profile, or the platform default (D-CFG-19).
    """
    if firm_id is None or firm_id == x_firm_id:
        return read(_service(db))
    with firm_store_session(request, firm_id) as firm_db:
        return read(_service(firm_db))


def _resolve_firm_scope(
    principal: Principal,
    db: Session,
    x_firm_id: UUID | None,
    firm_id: UUID | None,
) -> UUID | None:
    selected = firm_id or x_firm_id or principal.firm_id
    if selected is None:
        return None
    if principal.is_platform_admin:
        valid = db.scalar(
            select(Firm.id).where(Firm.id == selected, Firm.is_deleted.is_(False))
        )
        if valid is None:
            raise AuthorizationError("The selected firm is unavailable.")
        return selected
    if not isinstance(principal.subject, UUID):
        raise AuthorizationError("A user principal is required.")
    membership = db.scalar(
        select(UserFirm.id)
        .join(Firm, Firm.id == UserFirm.firm_id)
        .where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == selected,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return selected
