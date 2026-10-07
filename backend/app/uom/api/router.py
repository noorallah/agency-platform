"""Firm-scoped REST endpoints for enterprise UOM and packaging framework."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import (
    RequiredFirmScope,
    ResolvedFirmScope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, publish_version, set_etag
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import (
    get_db,
)
from app.core.exceptions import AuthorizationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import Principal, require_platform_admin
from app.uom.models import Uom
from app.uom.schemas import (
    BarcodeLookupResponse,
    ConversionRequest,
    ConversionResponse,
    ConversionRuleCreate,
    ConversionRuleListFilters,
    ConversionRuleResponse,
    ConversionRuleUpdate,
    PackagingLevelCreate,
    PackagingLevelResponse,
    PackagingLevelUpdate,
    PackagingTypeCreate,
    PackagingTypeResponse,
    PackagingTypeUpdate,
    UnitSetCreate,
    UnitSetResponse,
    UnitSetUpdate,
    UomCreate,
    UomGroupCreate,
    UomGroupResponse,
    UomGroupUpdate,
    UomResponse,
    UomUpdate,
)
from app.uom.services import UnitSetService, UomService

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
#: The shared unit catalogue -- units, groups and packaging types. None of
#: them carries a firm, so in `firm_shared` one row serves
#: every firm there: a firm administrator renaming BOX, or making it
#: whole-number, did it for MEDI01 and FOOD01 as well (D-CFG-9). Reference
#: data like the geography masters, so the same designation writes it.
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _uom_response(service: UomService, row: Uom, firm_id: UUID) -> UomResponse:
    """Build one unit response with the calling firm's custom fields."""
    payload = UomResponse.model_validate(row).model_dump(mode="python")
    payload["attributes"] = service.attribute_responses(row, firm_id=firm_id)
    return UomResponse.model_validate(payload)


@router.get("/uoms", response_model=ApiResponse[list[UomResponse]])
def list_uoms(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[UomResponse]]:
    """List the unit catalogue."""
    service = UomService(db)
    rows = service.list_uoms(include_inactive=include_inactive)
    # One read for the whole catalogue rather than one per unit (D-CFG-20).
    attributes = service.attribute_responses_for_many(rows, firm_id=scope.firm_id)
    data = []
    for row in rows:
        payload = UomResponse.model_validate(row).model_dump(mode="python")
        payload["attributes"] = attributes.get(row.id, [])
        data.append(UomResponse.model_validate(payload))
    return ApiResponse(data=data)


@router.post(
    "/uoms",
    response_model=ApiResponse[UomResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_uom(
    data: UomCreate,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomResponse]:
    """Add a unit to the catalogue."""
    service = UomService(db)
    row = service.create_uom(data, actor_id=scope.actor_id, firm_id=scope.firm_id)
    return ApiResponse(data=_uom_response(service, row, scope.firm_id))


@router.put("/uoms/{uom_id}", response_model=ApiResponse[UomResponse])
def update_uom(
    uom_id: UUID,
    data: UomUpdate,
    scope: UomManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[UomResponse]:
    """Change a unit in the catalogue, or the calling firm's custom fields on it.

    The unit's own columns are shared by every firm in the store, so they need
    the platform designation, as creating or deleting a unit does. The custom
    fields are the calling firm's own values, so ``UOM_MANAGE`` is enough for
    a body carrying nothing else.
    """
    shared = data.model_dump(exclude_unset=True, exclude={"attributes"})
    if shared and not scope.principal.is_platform_admin:
        raise AuthorizationError(
            "A unit is shared by every firm in this store, so only a platform "
            "administrator can change it. Your firm's own custom fields on it "
            "can still be saved on their own."
        )
    service = UomService(db)
    row = service.update_uom(
        uom_id,
        data,
        actor_id=scope.actor_id,
        expected_version=expected_version,
        firm_id=scope.firm_id,
    )
    set_etag(response, row)
    return ApiResponse(data=_uom_response(service, row, scope.firm_id))


@router.delete("/uoms/{uom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom(
    uom_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
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
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[UomGroupResponse]:
    """Add a unit group."""
    row = UomService(db).create_uom_group(data, actor_id=scope.actor_id)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.put("/uom-groups/{group_id}", response_model=ApiResponse[UomGroupResponse])
def update_uom_group(
    group_id: UUID,
    data: UomGroupUpdate,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[UomGroupResponse]:
    """Change a unit group."""
    row = UomService(db).update_uom_group(
        group_id,
        data,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=UomGroupResponse.model_validate(row))


@router.delete("/uom-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_uom_group(
    group_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
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
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
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
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PackagingTypeResponse]:
    """Change a packaging type."""
    row = UomService(db).update_packaging_type(
        packaging_type_id,
        data,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
    return ApiResponse(data=PackagingTypeResponse.model_validate(row))


@router.delete(
    "/packaging-types/{packaging_type_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_packaging_type(
    packaging_type_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
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
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
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
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[ConversionRuleResponse]:
    """Change a conversion rule."""
    row = UomService(db).update_conversion_rule(
        rule_id,
        data,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
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
    "/barcode-lookup",
    response_model=ApiResponse[BarcodeLookupResponse],
)
def lookup_barcode(
    scope: UomViewScope,
    code: Annotated[str, Query(min_length=1, max_length=300)],
    db: Session = Depends(get_db),
) -> ApiResponse[BarcodeLookupResponse]:
    """Resolve a scanned code to a product and the stock one scan means.

    A literal path, and it is declared above `/products/{product_id}/...`
    deliberately: FastAPI matches in declaration order, and this repository has
    had four features made unreachable by a literal sitting below a parameter
    that swallowed it.
    """
    return ApiResponse(
        data=UomService(db).lookup_barcode(firm_scope=scope.firm_id, code=code)
    )


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
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[PackagingLevelResponse]:
    """Change a packaging level."""
    row = UomService(db).update_packaging_level(
        firm_scope=scope.firm_id,
        product_id=product_id,
        level_id=level_id,
        data=data,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    set_etag(response, row)
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


@router.get("/unit-sets", response_model=ApiResponse[list[UnitSetResponse]])
def list_unit_sets(
    scope: UomViewScope,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[UnitSetResponse]]:
    """Return the shared unit sets and the firm's own (backlog 89).

    A row with ``firm_id`` is the firm's own and its to change; one without
    is the shared catalogue, read-only here.
    """
    return ApiResponse(
        data=UnitSetService(db).list_sets(
            scope.firm_id, include_inactive=include_inactive
        )
    )


@router.post(
    "/unit-sets",
    response_model=ApiResponse[UnitSetResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_unit_set(
    data: UnitSetCreate,
    scope: UomManageScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[UnitSetResponse]:
    """Add a unit set of the firm's own (backlog 89)."""
    row = UnitSetService(db).create(
        data, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.put("/unit-sets/{unit_set_id}", response_model=ApiResponse[UnitSetResponse])
def update_unit_set(
    unit_set_id: UUID,
    data: UnitSetUpdate,
    scope: UomManageScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[UnitSetResponse]:
    """Change a unit set of the firm's own; products made from it keep theirs."""
    row = UnitSetService(db).update(
        unit_set_id,
        data,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/unit-sets/{unit_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit_set(
    unit_set_id: UUID,
    scope: UomManageScope,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a unit set of the firm's own."""
    UnitSetService(db).delete(
        unit_set_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
