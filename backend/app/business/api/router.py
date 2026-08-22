"""FastAPI routes for business profile and industry framework administration."""

# ruff: noqa: D103

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.business.models import BusinessProfile
from app.business.schemas import (
    ActiveFeatureResponse,
    ActiveModuleResponse,
    AttributeDefinitionCreate,
    AttributeDefinitionResponse,
    AttributeDefinitionUpdate,
    BusinessFeatureCreate,
    BusinessFeatureResponse,
    BusinessFeatureUpdate,
    BusinessModuleCreate,
    BusinessModuleResponse,
    BusinessModuleUpdate,
    BusinessProfileConfigurationResponse,
    BusinessProfileCreate,
    BusinessProfileResponse,
    BusinessProfileUpdate,
    CategoryAttributeRuleCreate,
    CategoryAttributeRuleResponse,
    CategoryAttributeRuleUpdate,
    FirmBusinessProfileAssign,
    FirmBusinessProfileResponse,
    FirmProfileAssignmentRow,
    IdentifierList,
)
from app.business.services import BusinessProfileFrameworkService
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
    response_model=ApiResponse[BusinessProfileResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    data: BusinessProfileCreate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessProfileResponse]:
    row = _service(db).create_profile(data, _actor_id(principal))
    return ApiResponse(data=BusinessProfileResponse.model_validate(row))


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
    "/profiles/{profile_id}", response_model=ApiResponse[BusinessProfileResponse]
)
def update_profile(
    profile_id: UUID,
    data: BusinessProfileUpdate,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessProfileResponse]:
    row = _service(db).update_profile(
        profile_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    return ApiResponse(data=BusinessProfileResponse.model_validate(row))


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_profile(profile_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    response_model=ApiResponse[BusinessFeatureResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_feature(
    data: BusinessFeatureCreate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessFeatureResponse]:
    row = _service(db).create_feature(data, _actor_id(principal))
    return ApiResponse(data=BusinessFeatureResponse.model_validate(row))


@router.put(
    "/features/{feature_id}", response_model=ApiResponse[BusinessFeatureResponse]
)
def update_feature(
    feature_id: UUID,
    data: BusinessFeatureUpdate,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessFeatureResponse]:
    row = _service(db).update_feature(
        feature_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    return ApiResponse(data=BusinessFeatureResponse.model_validate(row))


@router.delete("/features/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature(
    feature_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_feature(feature_id, _actor_id(principal))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    response_model=ApiResponse[BusinessModuleResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_module(
    data: BusinessModuleCreate,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[BusinessModuleResponse]:
    row = _service(db).create_module(data, _actor_id(principal))
    return ApiResponse(data=BusinessModuleResponse.model_validate(row))


@router.put("/modules/{module_id}", response_model=ApiResponse[BusinessModuleResponse])
def update_module(
    module_id: UUID,
    data: BusinessModuleUpdate,
    principal: PlatformPrincipal,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BusinessModuleResponse]:
    row = _service(db).update_module(
        module_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    return ApiResponse(data=BusinessModuleResponse.model_validate(row))


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(
    module_id: UUID,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_module(module_id, _actor_id(principal))
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
    row = _service(db).create_attribute(data, _actor_id(principal))
    return ApiResponse(data=AttributeDefinitionResponse.model_validate(row))


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
    row = _service(db).update_attribute(
        attribute_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    return ApiResponse(data=AttributeDefinitionResponse.model_validate(row))


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


@router.get(
    "/category-attribute-rules",
    response_model=ApiResponse[list[CategoryAttributeRuleResponse]],
)
def list_category_rules(
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CategoryAttributeRuleResponse]]:
    rows = _service(db).list_category_rules()
    return ApiResponse(
        data=[CategoryAttributeRuleResponse.model_validate(row) for row in rows]
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
    row = _service(db).create_category_rule(data, _actor_id(principal))
    return ApiResponse(data=CategoryAttributeRuleResponse.model_validate(row))


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
    row = _service(db).update_category_rule(
        rule_id, data, _actor_id(principal), expected_version
    )
    set_etag(response, row)
    return ApiResponse(data=CategoryAttributeRuleResponse.model_validate(row))


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
    response_model=ApiResponse[None],
)
def set_profile_features(
    profile_id: UUID,
    data: IdentifierList,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    _service(db).set_profile_features(profile_id, data.ids, _actor_id(principal))
    return ApiResponse(data=None)


@router.put(
    "/profiles/{profile_id}/modules",
    response_model=ApiResponse[None],
)
def set_profile_modules(
    profile_id: UUID,
    data: IdentifierList,
    principal: PlatformPrincipal,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    _service(db).set_profile_modules(profile_id, data.ids, _actor_id(principal))
    return ApiResponse(data=None)


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
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
    firm_id: Annotated[UUID | None, Query()] = None,
) -> ApiResponse[list[ActiveFeatureResponse]]:
    resolved_firm = _resolve_firm_scope(principal, platform_db, x_firm_id, firm_id)
    rows = _service(db).active_features(resolved_firm)
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
    db: Session = Depends(get_db),
    platform_db: Session = Depends(get_platform_db),
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
    firm_id: Annotated[UUID | None, Query()] = None,
) -> ApiResponse[list[ActiveModuleResponse]]:
    resolved_firm = _resolve_firm_scope(principal, platform_db, x_firm_id, firm_id)
    rows = _service(db).active_modules(resolved_firm)
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
