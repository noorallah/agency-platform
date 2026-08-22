"""Firm-scoped REST endpoints for configurable sales territory management."""

# ruff: noqa: D102, D103, D107

from datetime import date
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

from app.common.scope import (
    RequiredFirmScope,
    ResolvedFirmScope,
    firm_permission_scope,
)
from app.core.concurrency import ExpectedVersion, publish_version
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.exceptions import ValidationError
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.security.authorization import (
    Principal,
    require_platform_admin,
)
from app.core.utils.dates import utc_now
from app.sales.schemas import (
    AddressMasterResponse,
    AddressMasterWrite,
    AssignableCustomer,
    AssignableCustomerFilters,
    BeatPlanCreate,
    BeatPlanResponse,
    BeatPlanUpdate,
    BulkOperationResult,
    CallListResponse,
    CustomerRoute,
    GeoCityResponse,
    GeoCityWrite,
    GeoCountryResponse,
    GeoCountryWrite,
    GeoDistrictResponse,
    GeoDistrictWrite,
    GeoLocalityResponse,
    GeoLocalityWrite,
    GeoPostalCodeResponse,
    GeoPostalCodeWrite,
    GeoStateResponse,
    GeoStateWrite,
    HierarchyResponse,
    HierarchyUpdateRequest,
    RouteTypeResponse,
    RouteTypeWrite,
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryBulkCustomerRequest,
    TerritoryBulkMoveRequest,
    TerritoryBulkSalesmanRequest,
    TerritoryBulkStatusRequest,
    TerritoryCopyRequest,
    TerritoryCreate,
    TerritoryCustomerAssignmentResponse,
    TerritoryDashboardStats,
    TerritoryDetailResponse,
    TerritoryListFilters,
    TerritoryResponse,
    TerritorySalesmanCandidate,
    TerritorySalesmanCoverage,
    TerritoryTreeNodeResponse,
    TerritoryUpdate,
)
from app.sales.services import SalesTerritoryService

router = APIRouter(
    prefix="/api/v1/sales-territories",
    tags=["Sales Territories"],
    responses=STANDARD_ERROR_RESPONSES,
)


TerritoryViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_VIEW")
]
TerritoryCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_CREATE")
]
TerritoryUpdateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_UPDATE")
]
TerritoryDeleteScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_DELETE")
]
TerritoryRestoreScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_RESTORE")
]
TerritoryAssignCustomersScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_ASSIGN_CUSTOMERS")
]
TerritoryAssignSalesmenScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_ASSIGN_SALESMEN")
]
TerritoryImportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_IMPORT")
]
TerritoryExportScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TERRITORY_EXPORT")
]
PlatformPrincipal = Annotated[Principal, Depends(require_platform_admin())]


def _service(db: Session) -> SalesTerritoryService:
    return SalesTerritoryService(db)


@router.get("/hierarchy-levels", response_model=ApiResponse[HierarchyResponse])
def get_hierarchy(
    scope: TerritoryViewScope, db: Session = Depends(get_db)
) -> ApiResponse[HierarchyResponse]:
    data = _service(db).get_hierarchy(firm_scope=scope.firm_id, actor_id=scope.actor_id)
    return ApiResponse(data=data)


@router.put("/hierarchy-levels", response_model=ApiResponse[HierarchyResponse])
def update_hierarchy(
    payload: HierarchyUpdateRequest,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[HierarchyResponse]:
    data = _service(db).update_hierarchy(
        firm_scope=scope.firm_id, actor_id=scope.actor_id, payload=payload
    )
    return ApiResponse(data=data)


@router.get("/route-types", response_model=ApiResponse[list[RouteTypeResponse]])
def list_route_types(
    scope: TerritoryViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[RouteTypeResponse]]:
    return ApiResponse(data=_service(db).list_route_types(firm_scope=scope.firm_id))


@router.post(
    "/route-types",
    response_model=ApiResponse[RouteTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_route_type(
    payload: RouteTypeWrite,
    scope: TerritoryCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[RouteTypeResponse]:
    data = _service(db).create_route_type(
        payload, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=data)


@router.put(
    "/route-types/{route_type_id}",
    response_model=ApiResponse[RouteTypeResponse],
)
def update_route_type(
    route_type_id: UUID,
    payload: RouteTypeWrite,
    scope: TerritoryUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[RouteTypeResponse]:
    """Rename a route type, or retire it by clearing its active flag."""
    data = _service(db).update_route_type(
        route_type_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, data.version)
    return ApiResponse(data=data)


@router.delete("/route-types/{route_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route_type(
    route_type_id: UUID,
    scope: TerritoryDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    """Soft delete a route type no route is still classified by."""
    _service(db).delete_route_type(
        route_type_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/geo/countries", response_model=ApiResponse[list[GeoCountryResponse]])
def list_geo_countries(
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoCountryResponse]]:
    return ApiResponse(data=_service(db).list_countries())


@router.post(
    "/geo/countries",
    response_model=ApiResponse[GeoCountryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_country(
    payload: GeoCountryWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoCountryResponse]:
    return ApiResponse(
        data=_service(db).create_country(payload, actor_id=scope.actor_id)
    )


@router.get("/geo/states", response_model=ApiResponse[list[GeoStateResponse]])
def list_geo_states(
    scope: TerritoryViewScope,
    country_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoStateResponse]]:
    return ApiResponse(data=_service(db).list_states(country_id=country_id))


@router.post(
    "/geo/states",
    response_model=ApiResponse[GeoStateResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_state(
    payload: GeoStateWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoStateResponse]:
    return ApiResponse(data=_service(db).create_state(payload, actor_id=scope.actor_id))


@router.get("/geo/districts", response_model=ApiResponse[list[GeoDistrictResponse]])
def list_geo_districts(
    scope: TerritoryViewScope,
    state_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoDistrictResponse]]:
    return ApiResponse(data=_service(db).list_districts(state_id=state_id))


@router.post(
    "/geo/districts",
    response_model=ApiResponse[GeoDistrictResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_district(
    payload: GeoDistrictWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoDistrictResponse]:
    return ApiResponse(
        data=_service(db).create_district(payload, actor_id=scope.actor_id)
    )


@router.get("/geo/cities", response_model=ApiResponse[list[GeoCityResponse]])
def list_geo_cities(
    scope: TerritoryViewScope,
    district_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoCityResponse]]:
    return ApiResponse(data=_service(db).list_cities(district_id=district_id))


@router.post(
    "/geo/cities",
    response_model=ApiResponse[GeoCityResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_city(
    payload: GeoCityWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoCityResponse]:
    return ApiResponse(data=_service(db).create_city(payload, actor_id=scope.actor_id))


@router.get(
    "/geo/postal-codes", response_model=ApiResponse[list[GeoPostalCodeResponse]]
)
def list_geo_postal_codes(
    scope: TerritoryViewScope,
    city_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoPostalCodeResponse]]:
    return ApiResponse(data=_service(db).list_postal_codes(city_id=city_id))


@router.post(
    "/geo/postal-codes",
    response_model=ApiResponse[GeoPostalCodeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_postal_code(
    payload: GeoPostalCodeWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoPostalCodeResponse]:
    return ApiResponse(
        data=_service(db).create_postal_code(payload, actor_id=scope.actor_id)
    )


@router.get("/geo/localities", response_model=ApiResponse[list[GeoLocalityResponse]])
def list_geo_localities(
    scope: TerritoryViewScope,
    postal_code_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[GeoLocalityResponse]]:
    return ApiResponse(data=_service(db).list_localities(postal_code_id=postal_code_id))


@router.post(
    "/geo/localities",
    response_model=ApiResponse[GeoLocalityResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_geo_locality(
    payload: GeoLocalityWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeoLocalityResponse]:
    return ApiResponse(
        data=_service(db).create_locality(payload, actor_id=scope.actor_id)
    )


@router.get(
    "/addresses/{owner_type}/{owner_id}",
    response_model=ApiResponse[list[AddressMasterResponse]],
)
def list_addresses(
    owner_type: str,
    owner_id: UUID,
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AddressMasterResponse]]:
    data = _service(db).addresses(
        firm_scope=scope.firm_id,
        owner_type=owner_type,
        owner_id=owner_id,
    )
    return ApiResponse(data=data)


@router.put(
    "/addresses/{owner_type}/{owner_id}",
    response_model=ApiResponse[list[AddressMasterResponse]],
)
def upsert_addresses(
    owner_type: str,
    owner_id: UUID,
    payload: list[AddressMasterWrite],
    scope: TerritoryUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AddressMasterResponse]]:
    data = _service(db).upsert_addresses(
        firm_scope=scope.firm_id,
        owner_type=owner_type,
        owner_id=owner_id,
        payload=payload,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.put(
    "/geo/countries/{country_id}",
    response_model=ApiResponse[GeoCountryResponse],
)
def update_geo_country(
    country_id: UUID,
    payload: GeoCountryWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoCountryResponse]:
    """Replace one country's editable fields."""
    row = _service(db).update_country(
        country_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/geo/countries/{country_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_country(
    country_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one country nothing still refers to."""
    _service(db).delete_country(country_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/geo/states/{state_id}",
    response_model=ApiResponse[GeoStateResponse],
)
def update_geo_state(
    state_id: UUID,
    payload: GeoStateWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoStateResponse]:
    """Replace one state's editable fields."""
    row = _service(db).update_state(
        state_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/geo/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_state(
    state_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one state nothing still refers to."""
    _service(db).delete_state(state_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/geo/districts/{district_id}",
    response_model=ApiResponse[GeoDistrictResponse],
)
def update_geo_district(
    district_id: UUID,
    payload: GeoDistrictWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoDistrictResponse]:
    """Replace one district's editable fields."""
    row = _service(db).update_district(
        district_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/geo/districts/{district_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_district(
    district_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one district nothing still refers to."""
    _service(db).delete_district(district_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/geo/cities/{city_id}",
    response_model=ApiResponse[GeoCityResponse],
)
def update_geo_city(
    city_id: UUID,
    payload: GeoCityWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoCityResponse]:
    """Replace one city's editable fields."""
    row = _service(db).update_city(
        city_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/geo/cities/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_city(
    city_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one city nothing still refers to."""
    _service(db).delete_city(city_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/geo/postal-codes/{postal_code_id}",
    response_model=ApiResponse[GeoPostalCodeResponse],
)
def update_geo_postal_code(
    postal_code_id: UUID,
    payload: GeoPostalCodeWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoPostalCodeResponse]:
    """Replace one postal code's editable fields."""
    row = _service(db).update_postal_code(
        postal_code_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete(
    "/geo/postal-codes/{postal_code_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_geo_postal_code(
    postal_code_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one postal code nothing still refers to."""
    _service(db).delete_postal_code(postal_code_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/geo/localities/{locality_id}",
    response_model=ApiResponse[GeoLocalityResponse],
)
def update_geo_locality(
    locality_id: UUID,
    payload: GeoLocalityWrite,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[GeoLocalityResponse]:
    """Replace one locality's editable fields."""
    row = _service(db).update_locality(
        locality_id,
        payload,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/geo/localities/{locality_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geo_locality(
    locality_id: UUID,
    _: PlatformPrincipal,
    scope: RequiredFirmScope,
    db: Session = Depends(get_db),
) -> Response:
    """Retire one locality nothing still refers to."""
    _service(db).delete_locality(locality_id, actor_id=scope.actor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=PaginatedResponse[TerritoryResponse])
def list_territories(
    scope: TerritoryViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    sort_by: Literal["code", "name", "status", "created_at"] = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    hierarchy_level_id: UUID | None = None,
    parent_id: UUID | None = None,
    status_value: Annotated[str | None, Query(alias="status")] = None,
    salesman_id: UUID | None = None,
    city_id: UUID | None = None,
    locality_id: UUID | None = None,
    route_type_id: UUID | None = None,
    business_profile_id: UUID | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[TerritoryResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    filters = TerritoryListFilters.model_validate(
        {
            "hierarchy_level_id": hierarchy_level_id,
            "parent_id": parent_id,
            "status": status_value,
            "salesman_id": salesman_id,
            "city_id": city_id,
            "locality_id": locality_id,
            "route_type_id": route_type_id,
            "business_profile_id": business_profile_id,
            "include_deleted": include_deleted,
        }
    )
    rows, total = _service(db).list_territories(
        firm_scope=scope.firm_id,
        filters=filters,
        page=params.page,
        page_size=params.page_size,
        search=search,
        sort_by=sort_by,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(data=rows, pagination=params.metadata(total))


@router.get("/tree", response_model=ApiResponse[list[TerritoryTreeNodeResponse]])
def territory_tree(
    scope: TerritoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritoryTreeNodeResponse]]:
    data = _service(db).tree(firm_scope=scope.firm_id, include_deleted=include_deleted)
    return ApiResponse(data=data)


@router.post(
    "",
    response_model=ApiResponse[TerritoryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_territory(
    payload: TerritoryCreate,
    scope: TerritoryCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TerritoryResponse]:
    row = _service(db).create_territory(
        payload, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=row)


@router.put("/{territory_id}", response_model=ApiResponse[TerritoryResponse])
def update_territory(
    territory_id: UUID,
    payload: TerritoryUpdate,
    scope: TerritoryUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[TerritoryResponse]:
    row = _service(db).update_territory(
        territory_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/{territory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_territory(
    territory_id: UUID,
    scope: TerritoryDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_territory(
        territory_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{territory_id}/restore", response_model=ApiResponse[TerritoryResponse])
def restore_territory(
    territory_id: UUID,
    scope: TerritoryRestoreScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TerritoryResponse]:
    row = _service(db).restore_territory(
        territory_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=row)


@router.post("/{territory_id}/copy", response_model=ApiResponse[TerritoryResponse])
def copy_territory_hierarchy(
    territory_id: UUID,
    payload: TerritoryCopyRequest,
    scope: TerritoryCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TerritoryResponse]:
    data = _service(db).copy_hierarchy(
        territory_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.get("/dashboard", response_model=ApiResponse[TerritoryDashboardStats])
def territory_dashboard(
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TerritoryDashboardStats]:
    return ApiResponse(data=_service(db).dashboard_stats(firm_scope=scope.firm_id))


@router.get(
    "/coverage/salesmen", response_model=ApiResponse[list[TerritorySalesmanCoverage]]
)
def territory_salesman_coverage(
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritorySalesmanCoverage]]:
    return ApiResponse(data=_service(db).salesman_coverage(firm_scope=scope.firm_id))


@router.get(
    "/salesman-candidates",
    response_model=ApiResponse[list[TerritorySalesmanCandidate]],
)
def territory_salesman_candidates(
    scope: TerritoryAssignSalesmenScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritorySalesmanCandidate]]:
    """List the people this firm can put on a route.

    Guarded by the assign permission rather than by `USER_VIEW`: the whole
    point is that somebody who may assign a route is usually not a platform
    administrator, and `/api/v1/users` refuses them.
    """
    return ApiResponse(data=_service(db).salesman_candidates(firm_scope=scope.firm_id))


@router.get("/search", response_model=ApiResponse[list[TerritoryResponse]])
def territory_global_search(
    q: str,
    scope: TerritoryViewScope,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritoryResponse]]:
    return ApiResponse(
        data=_service(db).search_territories(
            firm_scope=scope.firm_id,
            query=q,
            limit=min(max(limit, 1), 500),
        )
    )


@router.get(
    "/{territory_id}/customers",
    response_model=ApiResponse[list[TerritoryCustomerAssignmentResponse]],
)
def territory_customers(
    territory_id: UUID,
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritoryCustomerAssignmentResponse]]:
    """List the customers on a territory, in the order the round calls them."""
    data = _service(db).customers(territory_id, firm_scope=scope.firm_id)
    return ApiResponse(data=data)


@router.put(
    "/{territory_id}/customers",
    response_model=ApiResponse[list[TerritoryCustomerAssignmentResponse]],
)
def set_territory_customers(
    territory_id: UUID,
    payload: TerritoryAssignCustomersRequest,
    scope: TerritoryAssignCustomersScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[TerritoryCustomerAssignmentResponse]]:
    data = _service(db).set_customers(
        territory_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.get(
    "/{territory_id}/salesmen", response_model=ApiResponse[list[dict[str, object]]]
)
def territory_salesmen(
    territory_id: UUID,
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[dict[str, object]]]:
    data = _service(db).salesmen(territory_id, firm_scope=scope.firm_id)
    return ApiResponse(data=data)


@router.put(
    "/{territory_id}/salesmen", response_model=ApiResponse[list[dict[str, object]]]
)
def set_territory_salesmen(
    territory_id: UUID,
    payload: TerritoryAssignSalesmenRequest,
    scope: TerritoryAssignSalesmenScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[dict[str, object]]]:
    data = _service(db).set_salesmen(
        territory_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.post("/bulk/customers", response_model=ApiResponse[BulkOperationResult])
def bulk_set_customers(
    payload: TerritoryBulkCustomerRequest,
    scope: TerritoryAssignCustomersScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkOperationResult]:
    data = _service(db).bulk_set_customers(
        payload.items,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.post("/bulk/salesmen", response_model=ApiResponse[BulkOperationResult])
def bulk_set_salesmen(
    payload: TerritoryBulkSalesmanRequest,
    scope: TerritoryAssignSalesmenScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkOperationResult]:
    data = _service(db).bulk_set_salesmen(
        payload.items,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.post("/bulk/status", response_model=ApiResponse[BulkOperationResult])
def bulk_status_change(
    payload: TerritoryBulkStatusRequest,
    scope: TerritoryUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkOperationResult]:
    data = _service(db).bulk_status_change(
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.post("/bulk/move", response_model=ApiResponse[BulkOperationResult])
def bulk_move(
    payload: TerritoryBulkMoveRequest,
    scope: TerritoryUpdateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BulkOperationResult]:
    data = _service(db).bulk_move(
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=data)


@router.get("/beat-plans", response_model=PaginatedResponse[BeatPlanResponse])
def list_beat_plans(
    scope: TerritoryViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BeatPlanResponse]:
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).list_beat_plans(
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
        search=search,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(data=rows, pagination=params.metadata(total))


@router.post(
    "/beat-plans",
    response_model=ApiResponse[BeatPlanResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_beat_plan(
    payload: BeatPlanCreate,
    scope: TerritoryCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BeatPlanResponse]:
    row = _service(db).create_beat_plan(
        payload, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=row)


@router.get("/beat-plans/{beat_plan_id}", response_model=ApiResponse[BeatPlanResponse])
def get_beat_plan(
    beat_plan_id: UUID,
    scope: TerritoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[BeatPlanResponse]:
    row = _service(db).get_beat_plan(
        beat_plan_id, firm_scope=scope.firm_id, include_deleted=include_deleted
    )
    return ApiResponse(data=row)


@router.put("/beat-plans/{beat_plan_id}", response_model=ApiResponse[BeatPlanResponse])
def update_beat_plan(
    beat_plan_id: UUID,
    payload: BeatPlanUpdate,
    scope: TerritoryUpdateScope,
    response: Response,
    db: Session = Depends(get_db),
    expected_version: ExpectedVersion = None,
) -> ApiResponse[BeatPlanResponse]:
    row = _service(db).update_beat_plan(
        beat_plan_id,
        payload,
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
        expected_version=expected_version,
    )
    publish_version(response, row.version)
    return ApiResponse(data=row)


@router.delete("/beat-plans/{beat_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beat_plan(
    beat_plan_id: UUID,
    scope: TerritoryDeleteScope,
    db: Session = Depends(get_db),
) -> Response:
    _service(db).delete_beat_plan(
        beat_plan_id, firm_scope=scope.firm_id, actor_id=scope.actor_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/beat-plans/{beat_plan_id}/call-list")
def beat_plan_call_list(
    beat_plan_id: UUID,
    scope: TerritoryViewScope,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CallListResponse]:
    """Answer who one plan calls on a date, defaulting to today."""
    return ApiResponse(
        data=_service(db).call_list(
            firm_scope=scope.firm_id,
            # `utc_now()`, never `date.today()`: everything persisted here is
            # UTC, so the server's local clock is a different day for part of
            # every day on any non-UTC deployment.
            on_date=on_date or utc_now().date(),
            beat_plan_id=beat_plan_id,
        )
    )


# Literal path, so it must be declared above the trailing `GET /{territory_id}`.
# FastAPI matches in declaration order and that route is deliberately last;
# four paths on this router have already been read as a territory id once.
@router.get("/call-lists")
def call_lists(
    scope: TerritoryViewScope,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    salesman_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[CallListResponse]:
    """Answer who is called on a date across every active plan."""
    return ApiResponse(
        data=_service(db).call_list(
            firm_scope=scope.firm_id,
            on_date=on_date or utc_now().date(),
            salesman_id=salesman_id,
        )
    )


@router.get(
    "/customers/{customer_id}/routes",
    response_model=ApiResponse[list[CustomerRoute]],
)
def customer_routes(
    customer_id: UUID,
    scope: TerritoryViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[CustomerRoute]]:
    """List the rounds that call one shop.

    A literal path, so it is declared above the trailing `GET /{territory_id}`.
    """
    return ApiResponse(
        data=_service(db).customer_routes(customer_id, firm_scope=scope.firm_id)
    )


@router.get(
    "/assignable-customers",
    response_model=PaginatedResponse[AssignableCustomer],
)
def assignable_customers(
    scope: TerritoryViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    territory_id: UUID | None = None,
    search: str | None = None,
    postal_code: str | None = None,
    area: str | None = None,
    city: str | None = None,
    unassigned_only: bool = False,
    db: Session = Depends(get_db),
) -> PaginatedResponse[AssignableCustomer]:
    """Find outlets for a round by pin code, street or town.

    A literal path, so it is declared above the trailing `GET /{territory_id}`
    that FastAPI would otherwise match it against.
    """
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = _service(db).assignable_customers(
        firm_scope=scope.firm_id,
        territory_id=territory_id,
        filters=AssignableCustomerFilters(
            postal_code=postal_code,
            area=area,
            city=city,
            unassigned_only=unassigned_only,
        ),
        search=search,
        page=params.page,
        page_size=params.page_size,
    )
    return PaginatedResponse(data=rows, pagination=params.metadata(total))


@router.get("/export")
def export_territories(
    scope: TerritoryExportScope,
    format: Literal["csv", "xlsx"] = "csv",
    dataset: Literal["hierarchy", "customers", "salesmen"] = "hierarchy",
    search: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = _service(db)
    if dataset == "customers":
        csv_content = service.export_customer_assignments_csv(firm_scope=scope.firm_id)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="territory-customers.csv"'
            },
        )
    if dataset == "salesmen":
        csv_content = service.export_salesman_assignments_csv(firm_scope=scope.firm_id)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="territory-salesmen.csv"'
            },
        )
    if format == "xlsx":
        data = service.export_xlsx(firm_scope=scope.firm_id, search=search)
        return StreamingResponse(
            iter([data]),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": 'attachment; filename="territories.xlsx"'},
        )
    csv_content = service.export_csv(firm_scope=scope.firm_id, search=search)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="territories.csv"'},
    )


@router.post(
    "/import",
    response_model=ApiResponse[list[TerritoryResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def import_territories(
    scope: TerritoryImportScope,
    db: Session = Depends(get_db),
    format: Annotated[Literal["csv"], Form()] = "csv",
    file: Annotated[UploadFile | None, File()] = None,
) -> ApiResponse[list[TerritoryResponse]]:
    if format != "csv":
        raise ValidationError("Only CSV import is currently supported.")
    if file is None:
        raise ValidationError("file is required for import.")
    content = await file.read()
    rows = _service(db).import_csv(
        content.decode("utf-8"),
        firm_scope=scope.firm_id,
        actor_id=scope.actor_id,
    )
    return ApiResponse(data=rows)


# Declared after every literal path above, deliberately. FastAPI matches in
# declaration order, so while this sat higher in the file it swallowed
# `/dashboard`, `/search`, `/beat-plans` and `/export` — each was read as a
# territory id and answered 422 "Input should be a valid UUID". All four were
# unreachable, which is why the Geography dashboard line had never shown a
# number and beat plans could not be listed at all.
@router.get("/{territory_id}", response_model=ApiResponse[TerritoryDetailResponse])
def get_territory(
    territory_id: UUID,
    scope: TerritoryViewScope,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[TerritoryDetailResponse]:
    data = _service(db).territory_details(
        territory_id,
        firm_scope=scope.firm_id,
        include_deleted=include_deleted,
    )
    return ApiResponse(data=data)
