"""Transactional service for configurable sales territory management."""

# ruff: noqa: D102, D107

from collections import defaultdict
from datetime import timedelta
from io import BytesIO
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.models import BusinessProfile, FirmBusinessProfile
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.identity.models import User
from app.sales.models import (
    AddressMaster,
    BeatPlan,
    BeatPlanStop,
    GeoCity,
    GeoCountry,
    GeoDistrict,
    GeoLocality,
    GeoPostalCode,
    GeoState,
    RouteTypeMaster,
    SalesHierarchyConfig,
    SalesHierarchyLevel,
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
    TerritorySalesmanAssignment,
    TerritoryWorkingDay,
)
from app.sales.schemas import (
    AddressMasterResponse,
    AddressMasterWrite,
    BeatPlanCreate,
    BeatPlanResponse,
    BeatPlanStopInput,
    BeatPlanUpdate,
    BulkOperationResult,
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
    HierarchyLevelInput,
    HierarchyLevelResponse,
    HierarchyResponse,
    HierarchyUpdateRequest,
    RouteProfileInput,
    RouteProfileResponse,
    RouteTypeResponse,
    RouteTypeWrite,
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryBulkCustomerAssignment,
    TerritoryBulkMoveRequest,
    TerritoryBulkSalesmanAssignment,
    TerritoryBulkStatusRequest,
    TerritoryCopyRequest,
    TerritoryCreate,
    TerritoryDashboardStats,
    TerritoryDetailResponse,
    TerritoryListFilters,
    TerritoryResponse,
    TerritorySalesmanCoverage,
    TerritoryTreeNodeResponse,
    TerritoryUpdate,
)


class SalesTerritoryService:
    """Coordinate hierarchy configuration, territory tree, and assignments."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_hierarchy(self, *, firm_scope: UUID, actor_id: UUID) -> HierarchyResponse:
        config = self._ensure_hierarchy_config(firm_scope, actor_id)
        levels = self._levels(config.id)
        return HierarchyResponse(
            config_id=config.id,
            firm_id=config.firm_id,
            business_profile_id=config.business_profile_id,
            max_levels=config.max_levels,
            allow_multi_route_per_salesman=config.allow_multi_route_per_salesman,
            allow_multi_salesman_per_route=config.allow_multi_salesman_per_route,
            enforce_customer_leaf_assignment=config.enforce_customer_leaf_assignment,
            levels=[self._level_response(item) for item in levels],
        )

    def update_hierarchy(
        self,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        payload: HierarchyUpdateRequest,
    ) -> HierarchyResponse:
        config = self._ensure_hierarchy_config(firm_scope, actor_id)
        config.max_levels = payload.max_levels
        config.allow_multi_route_per_salesman = payload.allow_multi_route_per_salesman
        config.allow_multi_salesman_per_route = payload.allow_multi_salesman_per_route
        config.enforce_customer_leaf_assignment = (
            payload.enforce_customer_leaf_assignment
        )
        config.updated_by = actor_id
        self._replace_levels(config.id, payload.levels, actor_id)
        record_audit(
            self._session,
            action="sales_territory.hierarchy.updated",
            entity_type="sales_hierarchy_config",
            entity_id=config.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()
        return self.get_hierarchy(firm_scope=firm_scope, actor_id=actor_id)

    def list_route_types(self, *, firm_scope: UUID) -> list[RouteTypeResponse]:
        return [
            RouteTypeResponse(
                id=row.id,
                code=row.code,
                name=row.name,
                description=row.description,
                is_active=row.is_active,
            )
            for row in self._session.scalars(
                select(RouteTypeMaster)
                .where(
                    RouteTypeMaster.firm_id == firm_scope,
                    RouteTypeMaster.is_deleted.is_(False),
                )
                .order_by(RouteTypeMaster.name.asc())
            )
        ]

    def create_route_type(
        self, payload: RouteTypeWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> RouteTypeResponse:
        row = RouteTypeMaster(
            firm_id=firm_scope,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return RouteTypeResponse(
            id=row.id,
            code=row.code,
            name=row.name,
            description=row.description,
            is_active=row.is_active,
        )

    def list_countries(self) -> list[GeoCountryResponse]:
        return [
            GeoCountryResponse(
                id=row.id,
                code=row.code,
                name=row.name,
                iso2=row.iso2,
                iso3=row.iso3,
                phone_code=row.phone_code,
                is_active=row.is_active,
            )
            for row in self._session.scalars(
                select(GeoCountry)
                .where(GeoCountry.is_deleted.is_(False))
                .order_by(GeoCountry.name.asc())
            )
        ]

    def create_country(
        self, payload: GeoCountryWrite, *, actor_id: UUID
    ) -> GeoCountryResponse:
        row = GeoCountry(
            code=payload.code,
            name=payload.name,
            iso2=payload.iso2,
            iso3=payload.iso3,
            phone_code=payload.phone_code,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoCountryResponse(
            id=row.id,
            code=row.code,
            name=row.name,
            iso2=row.iso2,
            iso3=row.iso3,
            phone_code=row.phone_code,
            is_active=row.is_active,
        )

    def list_states(self, *, country_id: UUID | None = None) -> list[GeoStateResponse]:
        statement = select(GeoState).where(GeoState.is_deleted.is_(False))
        if country_id is not None:
            statement = statement.where(GeoState.country_id == country_id)
        return [
            GeoStateResponse(
                id=row.id,
                country_id=row.country_id,
                code=row.code,
                name=row.name,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement.order_by(GeoState.name.asc()))
        ]

    def create_state(
        self, payload: GeoStateWrite, *, actor_id: UUID
    ) -> GeoStateResponse:
        row = GeoState(
            country_id=payload.country_id,
            code=payload.code,
            name=payload.name,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoStateResponse(
            id=row.id,
            country_id=row.country_id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
        )

    def list_districts(
        self, *, state_id: UUID | None = None
    ) -> list[GeoDistrictResponse]:
        statement = select(GeoDistrict).where(GeoDistrict.is_deleted.is_(False))
        if state_id is not None:
            statement = statement.where(GeoDistrict.state_id == state_id)
        return [
            GeoDistrictResponse(
                id=row.id,
                state_id=row.state_id,
                code=row.code,
                name=row.name,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement.order_by(GeoDistrict.name.asc()))
        ]

    def create_district(
        self, payload: GeoDistrictWrite, *, actor_id: UUID
    ) -> GeoDistrictResponse:
        row = GeoDistrict(
            state_id=payload.state_id,
            code=payload.code,
            name=payload.name,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoDistrictResponse(
            id=row.id,
            state_id=row.state_id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
        )

    def list_cities(self, *, district_id: UUID | None = None) -> list[GeoCityResponse]:
        statement = select(GeoCity).where(GeoCity.is_deleted.is_(False))
        if district_id is not None:
            statement = statement.where(GeoCity.district_id == district_id)
        return [
            GeoCityResponse(
                id=row.id,
                district_id=row.district_id,
                code=row.code,
                name=row.name,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement.order_by(GeoCity.name.asc()))
        ]

    def create_city(self, payload: GeoCityWrite, *, actor_id: UUID) -> GeoCityResponse:
        row = GeoCity(
            district_id=payload.district_id,
            code=payload.code,
            name=payload.name,
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoCityResponse(
            id=row.id,
            district_id=row.district_id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
        )

    def list_postal_codes(
        self, *, city_id: UUID | None = None
    ) -> list[GeoPostalCodeResponse]:
        statement = select(GeoPostalCode).where(GeoPostalCode.is_deleted.is_(False))
        if city_id is not None:
            statement = statement.where(GeoPostalCode.city_id == city_id)
        return [
            GeoPostalCodeResponse(
                id=row.id,
                city_id=row.city_id,
                postal_code=row.postal_code,
                is_active=row.is_active,
            )
            for row in self._session.scalars(
                statement.order_by(GeoPostalCode.postal_code.asc())
            )
        ]

    def create_postal_code(
        self, payload: GeoPostalCodeWrite, *, actor_id: UUID
    ) -> GeoPostalCodeResponse:
        row = GeoPostalCode(
            city_id=payload.city_id,
            postal_code=payload.postal_code.strip(),
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoPostalCodeResponse(
            id=row.id,
            city_id=row.city_id,
            postal_code=row.postal_code,
            is_active=row.is_active,
        )

    def list_localities(
        self, *, postal_code_id: UUID | None = None
    ) -> list[GeoLocalityResponse]:
        statement = select(GeoLocality).where(GeoLocality.is_deleted.is_(False))
        if postal_code_id is not None:
            statement = statement.where(GeoLocality.postal_code_id == postal_code_id)
        return [
            GeoLocalityResponse(
                id=row.id,
                postal_code_id=row.postal_code_id,
                name=row.name,
                is_active=row.is_active,
            )
            for row in self._session.scalars(statement.order_by(GeoLocality.name.asc()))
        ]

    def create_locality(
        self, payload: GeoLocalityWrite, *, actor_id: UUID
    ) -> GeoLocalityResponse:
        row = GeoLocality(
            postal_code_id=payload.postal_code_id,
            name=payload.name.strip(),
            is_active=payload.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._commit()
        return GeoLocalityResponse(
            id=row.id,
            postal_code_id=row.postal_code_id,
            name=row.name,
            is_active=row.is_active,
        )

    def upsert_addresses(
        self,
        *,
        firm_scope: UUID,
        owner_type: str,
        owner_id: UUID,
        payload: list[AddressMasterWrite],
        actor_id: UUID,
    ) -> list[AddressMasterResponse]:
        owner_type_code = owner_type.strip().upper()
        existing = list(
            self._session.scalars(
                select(AddressMaster).where(
                    AddressMaster.firm_id == firm_scope,
                    AddressMaster.owner_type == owner_type_code,
                    AddressMaster.owner_id == owner_id,
                )
            )
        )
        for row in existing:
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
        for item in payload:
            self._session.add(
                AddressMaster(
                    firm_id=firm_scope,
                    owner_type=owner_type_code,
                    owner_id=owner_id,
                    address_type=item.address_type,
                    line1=item.line1,
                    line2=item.line2,
                    landmark=item.landmark,
                    country_id=item.country_id,
                    state_id=item.state_id,
                    district_id=item.district_id,
                    city_id=item.city_id,
                    postal_code_id=item.postal_code_id,
                    locality_id=item.locality_id,
                    is_primary=item.is_primary,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._commit()
        return self.addresses(
            firm_scope=firm_scope,
            owner_type=owner_type_code,
            owner_id=owner_id,
        )

    def addresses(
        self, *, firm_scope: UUID, owner_type: str, owner_id: UUID
    ) -> list[AddressMasterResponse]:
        return [
            AddressMasterResponse(
                id=row.id,
                owner_type=row.owner_type,
                owner_id=row.owner_id,
                address_type=row.address_type,
                line1=row.line1,
                line2=row.line2,
                landmark=row.landmark,
                country_id=row.country_id,
                state_id=row.state_id,
                district_id=row.district_id,
                city_id=row.city_id,
                postal_code_id=row.postal_code_id,
                locality_id=row.locality_id,
                is_primary=row.is_primary,
            )
            for row in self._session.scalars(
                select(AddressMaster).where(
                    AddressMaster.firm_id == firm_scope,
                    AddressMaster.owner_type == owner_type.strip().upper(),
                    AddressMaster.owner_id == owner_id,
                    AddressMaster.is_deleted.is_(False),
                )
            )
        ]

    def search_territories(
        self,
        *,
        firm_scope: UUID,
        query: str,
        limit: int = 100,
    ) -> list[TerritoryResponse]:
        term = f"%{query.strip()}%"
        statement = (
            select(SalesTerritoryNode)
            .where(
                SalesTerritoryNode.firm_id == firm_scope,
                SalesTerritoryNode.is_deleted.is_(False),
                or_(
                    SalesTerritoryNode.code.ilike(term),
                    SalesTerritoryNode.name.ilike(term),
                    SalesTerritoryNode.path.ilike(term),
                    select(Customer.id)
                    .join(
                        TerritoryCustomerAssignment,
                        TerritoryCustomerAssignment.customer_id == Customer.id,
                    )
                    .where(
                        TerritoryCustomerAssignment.territory_id
                        == SalesTerritoryNode.id,
                        TerritoryCustomerAssignment.is_deleted.is_(False),
                        Customer.name.ilike(term),
                    )
                    .exists(),
                    select(User.id)
                    .join(
                        TerritorySalesmanAssignment,
                        TerritorySalesmanAssignment.user_id == User.id,
                    )
                    .where(
                        TerritorySalesmanAssignment.territory_id
                        == SalesTerritoryNode.id,
                        TerritorySalesmanAssignment.is_deleted.is_(False),
                        User.full_name.ilike(term),
                    )
                    .exists(),
                    select(TerritoryRouteProfile.id)
                    .join(
                        GeoCity,
                        GeoCity.id == TerritoryRouteProfile.city_id,
                        isouter=True,
                    )
                    .join(
                        GeoLocality,
                        GeoLocality.id == TerritoryRouteProfile.locality_id,
                        isouter=True,
                    )
                    .join(
                        RouteTypeMaster,
                        RouteTypeMaster.id == TerritoryRouteProfile.route_type_id,
                        isouter=True,
                    )
                    .where(
                        TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                        TerritoryRouteProfile.is_deleted.is_(False),
                        or_(
                            GeoCity.name.ilike(term),
                            GeoLocality.name.ilike(term),
                            RouteTypeMaster.name.ilike(term),
                            TerritoryRouteProfile.visit_frequency.ilike(term),
                        ),
                    )
                    .exists(),
                    select(BusinessProfile.id)
                    .where(
                        BusinessProfile.id == SalesTerritoryNode.business_profile_id,
                        BusinessProfile.name.ilike(term),
                    )
                    .exists(),
                ),
            )
            .order_by(SalesTerritoryNode.path.asc())
            .limit(limit)
        )
        return self._territory_responses(list(self._session.scalars(statement)))

    def list_territories(
        self,
        *,
        firm_scope: UUID,
        filters: TerritoryListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[TerritoryResponse], int]:
        columns = {
            "code": SalesTerritoryNode.code,
            "name": SalesTerritoryNode.name,
            "status": SalesTerritoryNode.status,
            "created_at": SalesTerritoryNode.created_at,
        }
        statement = select(SalesTerritoryNode).where(
            SalesTerritoryNode.firm_id == firm_scope
        )
        count = (
            select(func.count())
            .select_from(SalesTerritoryNode)
            .where(SalesTerritoryNode.firm_id == firm_scope)
        )
        statement, count = self._apply_filters(statement, count, filters)
        if search:
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    SalesTerritoryNode.code.ilike(term),
                    SalesTerritoryNode.name.ilike(term),
                    SalesTerritoryNode.path.ilike(term),
                )
            )
            count = count.where(
                or_(
                    SalesTerritoryNode.code.ilike(term),
                    SalesTerritoryNode.name.ilike(term),
                    SalesTerritoryNode.path.ilike(term),
                )
            )
        ordering = columns[sort_by].desc() if descending else columns[sort_by].asc()
        rows = list(
            self._session.scalars(
                statement.order_by(ordering)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return self._territory_responses(rows), int(self._session.scalar(count) or 0)

    def tree(
        self, *, firm_scope: UUID, include_deleted: bool = False
    ) -> list[TerritoryTreeNodeResponse]:
        nodes = list(
            self._session.scalars(
                select(SalesTerritoryNode)
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(include_deleted),
                )
                .order_by(
                    SalesTerritoryNode.path.asc(), SalesTerritoryNode.sort_order.asc()
                )
            )
        )
        if not include_deleted:
            nodes = [item for item in nodes if not item.is_deleted]
        level_map = self._level_name_map_by_id(
            {item.hierarchy_level_id for item in nodes}
        )
        node_by_id = {item.id: item for item in nodes}
        children: dict[UUID | None, list[SalesTerritoryNode]] = defaultdict(list)
        for node in nodes:
            if node.parent_id is not None and node.parent_id not in node_by_id:
                continue
            children[node.parent_id].append(node)

        def convert(node: SalesTerritoryNode) -> TerritoryTreeNodeResponse:
            return TerritoryTreeNodeResponse(
                id=node.id,
                parent_id=node.parent_id,
                hierarchy_level_id=node.hierarchy_level_id,
                hierarchy_level_name=level_map.get(node.hierarchy_level_id, ""),
                code=node.code,
                name=node.name,
                status=node.status,
                path=node.path,
                children=[convert(child) for child in children.get(node.id, [])],
            )

        return [convert(item) for item in children.get(None, [])]

    def create_territory(
        self, data: TerritoryCreate, *, firm_scope: UUID, actor_id: UUID
    ) -> TerritoryResponse:
        self._assert_unique_code(firm_scope, data.code)
        self._assert_unique_name_under_parent(
            firm_scope=firm_scope,
            parent_id=data.parent_id,
            name=data.name,
        )
        profile_id = self._profile_id(firm_scope)
        level = self._level(data.hierarchy_level_id)
        parent = self._parent(firm_scope, data.parent_id)
        self._validate_level_parent(level, parent)
        path = data.code if parent is None else f"{parent.path}/{data.code}"
        row = SalesTerritoryNode(
            firm_id=firm_scope,
            business_profile_id=profile_id,
            hierarchy_level_id=data.hierarchy_level_id,
            parent_id=data.parent_id,
            code=data.code,
            name=data.name.strip(),
            description=data.description,
            status=data.status.value,
            path=path,
            sort_order=data.sort_order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._upsert_route_profile(
            territory_id=row.id,
            data=data.route_profile,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_territory.created",
            entity_type="sales_territory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"code": row.code, "name": row.name},
        )
        self._commit()
        return self.get_territory(row.id, firm_scope=firm_scope)

    def get_territory(
        self, territory_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TerritoryResponse:
        node = self._territory(
            territory_id, firm_scope, include_deleted=include_deleted
        )
        return self._territory_responses([node])[0]

    def territory_details(
        self, territory_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TerritoryDetailResponse:
        node = self._territory(
            territory_id, firm_scope, include_deleted=include_deleted
        )
        base = self._territory_responses([node])[0]
        customer_ids = list(
            self._session.scalars(
                select(TerritoryCustomerAssignment.customer_id).where(
                    TerritoryCustomerAssignment.territory_id == node.id,
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            )
        )
        salesman_ids = list(
            self._session.scalars(
                select(TerritorySalesmanAssignment.user_id).where(
                    TerritorySalesmanAssignment.territory_id == node.id,
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
        )
        child_ids = list(
            self._session.scalars(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.parent_id == node.id,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
        )
        return TerritoryDetailResponse(
            **base.model_dump(),
            customer_ids=customer_ids,
            salesman_ids=salesman_ids,
            child_ids=child_ids,
        )

    def update_territory(
        self,
        territory_id: UUID,
        data: TerritoryUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TerritoryResponse:
        row = self._territory(territory_id, firm_scope, include_deleted=True)
        self._assert_unique_code(firm_scope, data.code, current_id=row.id)
        self._assert_unique_name_under_parent(
            firm_scope=firm_scope,
            parent_id=data.parent_id,
            name=data.name,
            current_id=row.id,
        )
        level = self._level(data.hierarchy_level_id)
        parent = self._parent(firm_scope, data.parent_id)
        if parent is not None and parent.id == row.id:
            raise ValidationError("A territory cannot be its own parent.")
        if parent is not None:
            self._assert_not_descendant(parent.id, row.path)
        self._validate_level_parent(level, parent)
        before_path = row.path
        row.hierarchy_level_id = data.hierarchy_level_id
        row.parent_id = data.parent_id
        row.code = data.code
        row.name = data.name.strip()
        row.description = data.description
        row.status = data.status.value
        row.sort_order = data.sort_order
        row.updated_by = actor_id
        row.path = data.code if parent is None else f"{parent.path}/{data.code}"
        if row.path != before_path:
            self._repath_descendants(row.id, before_path, row.path, actor_id)
        self._upsert_route_profile(
            territory_id=row.id,
            data=data.route_profile,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_territory.updated",
            entity_type="sales_territory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code, "path": before_path},
            after_data={"code": data.code, "path": row.path},
        )
        self._commit()
        return self.get_territory(row.id, firm_scope=firm_scope, include_deleted=True)

    def delete_territory(
        self, territory_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self._territory(territory_id, firm_scope)
        has_children = self._session.scalar(
            select(SalesTerritoryNode.id).where(
                SalesTerritoryNode.parent_id == row.id,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        )
        if has_children is not None:
            raise ValidationError("Cannot delete a territory that has active children.")
        has_customers = self._session.scalar(
            select(TerritoryCustomerAssignment.id).where(
                TerritoryCustomerAssignment.territory_id == row.id,
                TerritoryCustomerAssignment.is_deleted.is_(False),
            )
        )
        if has_customers is not None:
            raise ValidationError(
                "Cannot delete a territory that has assigned customers."
            )
        has_salesmen = self._session.scalar(
            select(TerritorySalesmanAssignment.id).where(
                TerritorySalesmanAssignment.territory_id == row.id,
                TerritorySalesmanAssignment.is_deleted.is_(False),
            )
        )
        if has_salesmen is not None:
            raise ValidationError(
                "Cannot delete a territory that has assigned salesmen."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_territory.deleted",
            entity_type="sales_territory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()

    def restore_territory(
        self, territory_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> TerritoryResponse:
        row = self._territory(territory_id, firm_scope, include_deleted=True)
        if not row.is_deleted:
            return self.get_territory(row.id, firm_scope=firm_scope)
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_territory.restored",
            entity_type="sales_territory",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()
        return self.get_territory(row.id, firm_scope=firm_scope)

    def set_customers(
        self,
        territory_id: UUID,
        payload: TerritoryAssignCustomersRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> list[UUID]:
        territory = self._territory(territory_id, firm_scope)
        entries = payload.entries
        customer_ids = (
            [item.customer_id for item in entries] if entries else payload.customer_ids
        )
        if customer_ids:
            count = self._session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(
                    Customer.id.in_(customer_ids),
                    Customer.firm_id == firm_scope,
                    Customer.is_deleted.is_(False),
                )
            )
            if int(count or 0) != len(set(customer_ids)):
                raise ValidationError(
                    "One or more customers do not belong to the active firm."
                )
        for assignment in self._session.scalars(
            select(TerritoryCustomerAssignment).where(
                TerritoryCustomerAssignment.customer_id.in_(customer_ids),
                TerritoryCustomerAssignment.is_deleted.is_(False),
            )
        ):
            assignment.is_deleted = True
            assignment.deleted_at = utc_now()
            assignment.deleted_by = actor_id
            assignment.updated_by = actor_id
        existing = {
            row.customer_id: row
            for row in self._session.scalars(
                select(TerritoryCustomerAssignment).where(
                    TerritoryCustomerAssignment.territory_id == territory.id
                )
            )
        }
        requested = set(customer_ids)
        entry_by_customer = {item.customer_id: item for item in entries}
        for customer_id in requested:
            row = existing.get(customer_id)
            entry = entry_by_customer.get(customer_id)
            if row is None:
                self._session.add(
                    TerritoryCustomerAssignment(
                        territory_id=territory.id,
                        customer_id=customer_id,
                        is_primary=True,
                        visit_sequence=(
                            entry.visit_sequence if entry is not None else None
                        ),
                        is_potential=entry.is_potential if entry is not None else False,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            elif row.is_deleted:
                row.is_deleted = False
                row.deleted_at = None
                row.deleted_by = None
                row.updated_by = actor_id
            if row is not None and entry is not None:
                row.visit_sequence = entry.visit_sequence
                row.is_potential = entry.is_potential
        for customer_id, row in existing.items():
            if customer_id not in requested and not row.is_deleted:
                row.is_deleted = True
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
                row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_territory.customers_set",
            entity_type="sales_territory",
            entity_id=territory.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"customer_count": len(customer_ids)},
        )
        self._commit()
        return self.customers(territory_id, firm_scope=firm_scope)

    def customers(self, territory_id: UUID, *, firm_scope: UUID) -> list[UUID]:
        territory = self._territory(territory_id, firm_scope)
        return list(
            self._session.scalars(
                select(TerritoryCustomerAssignment.customer_id).where(
                    TerritoryCustomerAssignment.territory_id == territory.id,
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            )
        )

    def set_salesmen(
        self,
        territory_id: UUID,
        payload: TerritoryAssignSalesmenRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> list[dict[str, object]]:
        territory = self._territory(territory_id, firm_scope)
        requested_user_ids = [item.user_id for item in payload.assignments]
        if requested_user_ids:
            # user_firms and users are platform tables; counting them on the
            # request session fails for any firm outside the platform store.
            members = FirmMetadataReader(self._session).active_member_count(
                firm_scope, requested_user_ids
            )
            if members != len(set(requested_user_ids)):
                raise ValidationError(
                    "One or more salesmen are not active firm members."
                )
        existing = {
            row.user_id: row
            for row in self._session.scalars(
                select(TerritorySalesmanAssignment).where(
                    TerritorySalesmanAssignment.territory_id == territory.id
                )
            )
        }
        requested = {item.user_id: item for item in payload.assignments}
        for user_id, item in requested.items():
            row = existing.get(user_id)
            if row is None:
                self._session.add(
                    TerritorySalesmanAssignment(
                        territory_id=territory.id,
                        user_id=user_id,
                        include_children=item.include_children,
                        is_primary=item.is_primary,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            else:
                row.include_children = item.include_children
                row.is_primary = item.is_primary
                if row.is_deleted:
                    row.is_deleted = False
                    row.deleted_at = None
                    row.deleted_by = None
                row.updated_by = actor_id
        for user_id, row in existing.items():
            if user_id not in requested and not row.is_deleted:
                row.is_deleted = True
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
                row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_territory.salesmen_set",
            entity_type="sales_territory",
            entity_id=territory.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"salesman_count": len(requested_user_ids)},
        )
        self._commit()
        return self.salesmen(territory_id, firm_scope=firm_scope)

    def salesmen(
        self, territory_id: UUID, *, firm_scope: UUID
    ) -> list[dict[str, object]]:
        territory = self._territory(territory_id, firm_scope)
        rows = list(
            self._session.scalars(
                select(TerritorySalesmanAssignment).where(
                    TerritorySalesmanAssignment.territory_id == territory.id,
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
        )
        return [
            {
                "user_id": item.user_id,
                "include_children": item.include_children,
                "is_primary": item.is_primary,
            }
            for item in rows
        ]

    def create_beat_plan(
        self, data: BeatPlanCreate, *, firm_scope: UUID, actor_id: UUID
    ) -> BeatPlanResponse:
        self._assert_unique_beat_code(firm_scope, data.code)
        territory = self._territory(data.territory_id, firm_scope)
        row = BeatPlan(
            firm_id=firm_scope,
            business_profile_id=territory.business_profile_id,
            territory_id=territory.id,
            code=data.code,
            name=data.name,
            plan_type=data.plan_type.value,
            weekday=data.weekday,
            week_of_month=data.week_of_month,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            is_active=data.is_active,
            notes=data.notes,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_beat_stops(row.id, data.stops, firm_scope, actor_id)
        record_audit(
            self._session,
            action="sales_territory.beat_plan.created",
            entity_type="sales_beat_plan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()
        return self.get_beat_plan(row.id, firm_scope=firm_scope)

    def get_beat_plan(
        self, beat_plan_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> BeatPlanResponse:
        row = self._beat_plan(beat_plan_id, firm_scope, include_deleted=include_deleted)
        return self._beat_plan_response(row)

    def list_beat_plans(
        self,
        *,
        firm_scope: UUID,
        include_deleted: bool = False,
        search: str | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[BeatPlanResponse], int]:
        statement = select(BeatPlan).where(BeatPlan.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(BeatPlan)
            .where(BeatPlan.firm_id == firm_scope)
        )
        if not include_deleted:
            statement = statement.where(BeatPlan.is_deleted.is_(False))
            count = count.where(BeatPlan.is_deleted.is_(False))
        if search:
            term = f"%{search.strip()}%"
            statement = statement.where(
                or_(BeatPlan.code.ilike(term), BeatPlan.name.ilike(term))
            )
            count = count.where(
                or_(BeatPlan.code.ilike(term), BeatPlan.name.ilike(term))
            )
        rows = list(
            self._session.scalars(
                statement.order_by(BeatPlan.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return [self._beat_plan_response(item) for item in rows], int(
            self._session.scalar(count) or 0
        )

    def update_beat_plan(
        self,
        beat_plan_id: UUID,
        data: BeatPlanUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> BeatPlanResponse:
        row = self._beat_plan(beat_plan_id, firm_scope, include_deleted=True)
        self._assert_unique_beat_code(firm_scope, data.code, current_id=row.id)
        self._territory(data.territory_id, firm_scope)
        row.territory_id = data.territory_id
        row.code = data.code
        row.name = data.name
        row.plan_type = data.plan_type.value
        row.weekday = data.weekday
        row.week_of_month = data.week_of_month
        row.starts_on = data.starts_on
        row.ends_on = data.ends_on
        row.is_active = data.is_active
        row.notes = data.notes
        row.updated_by = actor_id
        self._replace_beat_stops(row.id, data.stops, firm_scope, actor_id)
        record_audit(
            self._session,
            action="sales_territory.beat_plan.updated",
            entity_type="sales_beat_plan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()
        return self.get_beat_plan(row.id, firm_scope=firm_scope, include_deleted=True)

    def delete_beat_plan(
        self, beat_plan_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        row = self._beat_plan(beat_plan_id, firm_scope)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_territory.beat_plan.deleted",
            entity_type="sales_beat_plan",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._commit()

    def export_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        rows, _ = self.list_territories(
            firm_scope=firm_scope,
            filters=TerritoryListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="code",
            descending=False,
        )
        output = ["Code,Name,Level,ParentCode,Status,Path"]
        id_to_code = {
            item.id: item.code
            for item in self._session.scalars(
                select(SalesTerritoryNode).where(
                    SalesTerritoryNode.firm_id == firm_scope
                )
            )
        }
        for row in rows:
            parent_code = id_to_code.get(row.parent_id, "") if row.parent_id else ""
            output.append(
                ",".join(
                    [
                        row.code,
                        row.name,
                        row.hierarchy_level_name,
                        parent_code,
                        row.status,
                        row.path,
                    ]
                )
            )
        return "\n".join(output)

    def export_customer_assignments_csv(self, *, firm_scope: UUID) -> str:
        output = ["TerritoryCode,TerritoryName,CustomerId,VisitSequence,Potential"]
        rows = self._session.execute(
            select(
                SalesTerritoryNode.code,
                SalesTerritoryNode.name,
                TerritoryCustomerAssignment.customer_id,
                TerritoryCustomerAssignment.visit_sequence,
                TerritoryCustomerAssignment.is_potential,
            )
            .join(
                TerritoryCustomerAssignment,
                TerritoryCustomerAssignment.territory_id == SalesTerritoryNode.id,
            )
            .where(
                SalesTerritoryNode.firm_id == firm_scope,
                SalesTerritoryNode.is_deleted.is_(False),
                TerritoryCustomerAssignment.is_deleted.is_(False),
            )
            .order_by(SalesTerritoryNode.path.asc())
        )
        for row in rows:
            output.append(
                ",".join(
                    [
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3] or ""),
                        "true" if bool(row[4]) else "false",
                    ]
                )
            )
        return "\n".join(output)

    def export_salesman_assignments_csv(self, *, firm_scope: UUID) -> str:
        output = [
            "TerritoryCode,TerritoryName,UserId,IncludeChildren,IsPrimary",
        ]
        rows = self._session.execute(
            select(
                SalesTerritoryNode.code,
                SalesTerritoryNode.name,
                TerritorySalesmanAssignment.user_id,
                TerritorySalesmanAssignment.include_children,
                TerritorySalesmanAssignment.is_primary,
            )
            .join(
                TerritorySalesmanAssignment,
                TerritorySalesmanAssignment.territory_id == SalesTerritoryNode.id,
            )
            .where(
                SalesTerritoryNode.firm_id == firm_scope,
                SalesTerritoryNode.is_deleted.is_(False),
                TerritorySalesmanAssignment.is_deleted.is_(False),
            )
            .order_by(SalesTerritoryNode.path.asc())
        )
        for row in rows:
            output.append(
                ",".join(
                    [
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        "true" if bool(row[3]) else "false",
                        "true" if bool(row[4]) else "false",
                    ]
                )
            )
        return "\n".join(output)

    def export_xlsx(self, *, firm_scope: UUID, search: str | None = None) -> bytes:
        try:
            from openpyxl import Workbook  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValidationError(
                "XLSX export dependency is unavailable. Install openpyxl."
            ) from error
        rows, _ = self.list_territories(
            firm_scope=firm_scope,
            filters=TerritoryListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="code",
            descending=False,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Territories"
        sheet.append(["Code", "Name", "Level", "Status", "Path"])
        for row in rows:
            sheet.append(
                [row.code, row.name, row.hierarchy_level_name, row.status, row.path]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def import_csv(
        self, csv_content: str, *, firm_scope: UUID, actor_id: UUID
    ) -> list[TerritoryResponse]:
        import csv
        import io

        reader = csv.DictReader(io.StringIO(csv_content))
        hierarchy = self.get_hierarchy(firm_scope=firm_scope, actor_id=actor_id)
        level_by_name = {
            item.display_name.upper(): item.id for item in hierarchy.levels
        }
        territory_by_code = {
            item.code: item
            for item in self._session.scalars(
                select(SalesTerritoryNode).where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
        }
        created: list[TerritoryResponse] = []
        for row in reader:
            code = str(row.get("Code") or "").strip().upper()
            name = str(row.get("Name") or "").strip()
            level_name = str(row.get("Level") or "").strip().upper()
            parent_code = str(row.get("ParentCode") or "").strip().upper()
            status = str(row.get("Status") or "ACTIVE").strip().upper()
            customer_codes = [
                code.strip().upper()
                for code in str(row.get("CustomerCodes") or "").split(",")
                if code.strip()
            ]
            if not code or not name or not level_name:
                continue
            level_id = level_by_name.get(level_name)
            if level_id is None:
                raise ValidationError(
                    f"Unknown hierarchy level in import row: {level_name}"
                )
            parent_id = (
                territory_by_code[parent_code].id
                if parent_code in territory_by_code
                else None
            )
            created_row = self.create_territory(
                TerritoryCreate(
                    code=code,
                    name=name,
                    hierarchy_level_id=level_id,
                    parent_id=parent_id,
                    status=status,
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
            )
            territory_by_code[created_row.code] = self._territory(
                created_row.id, firm_scope
            )
            if customer_codes:
                customer_ids = list(
                    self._session.scalars(
                        select(Customer.id).where(
                            Customer.firm_id == firm_scope,
                            Customer.code.in_(customer_codes),
                            Customer.is_deleted.is_(False),
                        )
                    )
                )
                self.set_customers(
                    created_row.id,
                    TerritoryAssignCustomersRequest(customer_ids=customer_ids),
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                )
            created.append(created_row)
        return created

    def copy_hierarchy(
        self,
        territory_id: UUID,
        payload: TerritoryCopyRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TerritoryResponse:
        source = self._territory(territory_id, firm_scope)
        target_parent = self._parent(firm_scope, payload.target_parent_id)
        source_nodes = list(
            self._session.scalars(
                select(SalesTerritoryNode)
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.path.ilike(f"{source.path}%"),
                    SalesTerritoryNode.is_deleted.is_(False),
                )
                .order_by(SalesTerritoryNode.path.asc())
            )
        )
        id_map: dict[UUID, UUID] = {}
        created_root_id: UUID | None = None
        route_profiles = self._route_profile_map({item.id for item in source_nodes})
        for node in source_nodes:
            parent_id: UUID | None
            if node.id == source.id and target_parent is not None:
                parent_id = target_parent.id
            elif node.parent_id is not None:
                parent_id = id_map.get(node.parent_id)
            else:
                parent_id = None
            base_code = payload.new_root_code if node.id == source.id else node.code
            base_name = payload.new_root_name if node.id == source.id else node.name
            code = self._next_available_code(firm_scope, base_code)
            name = self._next_available_name(firm_scope, parent_id, base_name)
            source_profile = route_profiles.get(node.id)
            route_profile_payload = (
                None
                if source_profile is None
                else {
                    "route_type_id": source_profile.route_type_id,
                    "visit_frequency": source_profile.visit_frequency,
                    "effective_from": source_profile.effective_from,
                    "effective_to": source_profile.effective_to,
                    "city_id": source_profile.city_id,
                    "postal_code_id": source_profile.postal_code_id,
                    "locality_id": source_profile.locality_id,
                    "working_days": source_profile.working_days,
                }
            )
            created = self.create_territory(
                TerritoryCreate(
                    code=code,
                    name=name,
                    hierarchy_level_id=node.hierarchy_level_id,
                    parent_id=parent_id,
                    description=node.description,
                    status=node.status,
                    sort_order=node.sort_order,
                    route_profile=route_profile_payload,
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
            )
            id_map[node.id] = created.id
            if created_root_id is None:
                created_root_id = created.id
            if payload.include_assignments:
                customers = [
                    row
                    for row in self._session.scalars(
                        select(TerritoryCustomerAssignment).where(
                            TerritoryCustomerAssignment.territory_id == node.id,
                            TerritoryCustomerAssignment.is_deleted.is_(False),
                        )
                    )
                ]
                self.set_customers(
                    created.id,
                    TerritoryAssignCustomersRequest(
                        entries=[
                            {
                                "customer_id": item.customer_id,
                                "visit_sequence": item.visit_sequence,
                                "is_potential": item.is_potential,
                            }
                            for item in customers
                        ]
                    ),
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                )
                salesmen = self.salesmen(node.id, firm_scope=firm_scope)
                self.set_salesmen(
                    created.id,
                    TerritoryAssignSalesmenRequest(assignments=salesmen),
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                )
        if created_root_id is None:
            raise ValidationError("No hierarchy nodes were copied.")
        return self.get_territory(created_root_id, firm_scope=firm_scope)

    def bulk_set_customers(
        self,
        items: list[TerritoryBulkCustomerAssignment],
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> BulkOperationResult:
        affected = 0
        for item in items:
            self.set_customers(
                item.territory_id,
                TerritoryAssignCustomersRequest(customer_ids=item.customer_ids),
                firm_scope=firm_scope,
                actor_id=actor_id,
            )
            affected += 1
        return BulkOperationResult(affected=affected, failed=0)

    def bulk_set_salesmen(
        self,
        items: list[TerritoryBulkSalesmanAssignment],
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> BulkOperationResult:
        affected = 0
        for item in items:
            self.set_salesmen(
                item.territory_id,
                TerritoryAssignSalesmenRequest(assignments=item.assignments),
                firm_scope=firm_scope,
                actor_id=actor_id,
            )
            affected += 1
        return BulkOperationResult(affected=affected, failed=0)

    def bulk_status_change(
        self,
        payload: TerritoryBulkStatusRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> BulkOperationResult:
        affected = 0
        for territory_id in payload.territory_ids:
            row = self._territory(territory_id, firm_scope, include_deleted=True)
            before = row.status
            row.status = payload.status.value
            row.updated_by = actor_id
            # One row per territory: a single summary entry keyed on the first
            # id recorded that N territories changed without saying which.
            record_audit(
                self._session,
                action="sales_territory.status_changed",
                entity_type="sales_territory",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_scope,
                before_data={"status": before},
                after_data={"status": row.status},
            )
            affected += 1
        self._commit()
        return BulkOperationResult(affected=affected, failed=0)

    def bulk_move(
        self,
        payload: TerritoryBulkMoveRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> BulkOperationResult:
        new_parent = self._parent(firm_scope, payload.new_parent_id)
        affected = 0
        for territory_id in payload.territory_ids:
            row = self._territory(territory_id, firm_scope, include_deleted=True)
            if new_parent is not None and new_parent.id == row.id:
                raise ValidationError("A territory cannot be moved under itself.")
            if new_parent is not None:
                self._assert_not_descendant(new_parent.id, row.path)
            level = self._level(row.hierarchy_level_id)
            self._validate_level_parent(level, new_parent)
            self._assert_unique_name_under_parent(
                firm_scope=firm_scope,
                parent_id=new_parent.id if new_parent else None,
                name=row.name,
                current_id=row.id,
            )
            before_path = row.path
            row.parent_id = new_parent.id if new_parent else None
            row.path = (
                row.code if new_parent is None else f"{new_parent.path}/{row.code}"
            )
            row.updated_by = actor_id
            self._repath_descendants(row.id, before_path, row.path, actor_id)
            record_audit(
                self._session,
                action="sales_territory.moved",
                entity_type="sales_territory",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_scope,
                before_data={"path": before_path},
                after_data={"path": row.path},
            )
            affected += 1
        self._commit()
        return BulkOperationResult(affected=affected, failed=0)

    def dashboard_stats(self, *, firm_scope: UUID) -> TerritoryDashboardStats:
        total_territories = int(
            self._session.scalar(
                select(func.count())
                .select_from(SalesTerritoryNode)
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            or 0
        )
        total_routes = int(
            self._session.scalar(
                select(func.count())
                .select_from(TerritoryRouteProfile)
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritoryRouteProfile.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
            or 0
        )
        assigned_customers = int(
            self._session.scalar(
                select(func.count())
                .select_from(TerritoryCustomerAssignment)
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritoryCustomerAssignment.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            )
            or 0
        )
        assigned_salesmen = int(
            self._session.scalar(
                select(func.count())
                .select_from(TerritorySalesmanAssignment)
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritorySalesmanAssignment.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
            or 0
        )
        total_customers = int(
            self._session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.firm_id == firm_scope, Customer.is_deleted.is_(False))
            )
            or 0
        )
        route_customer_ids = set(
            self._session.scalars(
                select(TerritoryCustomerAssignment.customer_id)
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritoryCustomerAssignment.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
            )
        )
        route_ids = set(
            self._session.scalars(
                select(TerritoryRouteProfile.territory_id)
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritoryRouteProfile.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
        )
        route_ids_with_salesman = set(
            self._session.scalars(
                select(TerritorySalesmanAssignment.territory_id).where(
                    TerritorySalesmanAssignment.territory_id.in_(route_ids),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
            )
        )
        return TerritoryDashboardStats(
            total_territories=total_territories,
            total_routes=total_routes,
            assigned_customers=assigned_customers,
            assigned_salesmen=assigned_salesmen,
            customers_without_route=max(0, total_customers - len(route_customer_ids)),
            routes_without_salesman=max(
                0, len(route_ids) - len(route_ids_with_salesman)
            ),
        )

    def salesman_coverage(self, *, firm_scope: UUID) -> list[TerritorySalesmanCoverage]:
        assigned_totals = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritorySalesmanAssignment.user_id,
                    func.count(TerritorySalesmanAssignment.id),
                )
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritorySalesmanAssignment.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
                .group_by(TerritorySalesmanAssignment.user_id)
            )
        }
        route_totals = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritorySalesmanAssignment.user_id,
                    func.count(TerritorySalesmanAssignment.id),
                )
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritorySalesmanAssignment.territory_id,
                )
                .join(
                    TerritoryRouteProfile,
                    TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
                .group_by(TerritorySalesmanAssignment.user_id)
            )
        }
        customer_totals = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritorySalesmanAssignment.user_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .join(
                    SalesTerritoryNode,
                    SalesTerritoryNode.id == TerritorySalesmanAssignment.territory_id,
                )
                .join(
                    TerritoryCustomerAssignment,
                    TerritoryCustomerAssignment.territory_id
                    == TerritorySalesmanAssignment.territory_id,
                )
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
                .group_by(TerritorySalesmanAssignment.user_id)
            )
        }
        total_territories = int(
            self._session.scalar(
                select(func.count())
                .select_from(SalesTerritoryNode)
                .where(
                    SalesTerritoryNode.firm_id == firm_scope,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            or 0
        )
        users = sorted(set(assigned_totals) | set(route_totals) | set(customer_totals))
        result: list[TerritorySalesmanCoverage] = []
        for user_id in users:
            assigned = assigned_totals.get(user_id, 0)
            coverage = (
                (assigned / total_territories * 100) if total_territories else 0.0
            )
            result.append(
                TerritorySalesmanCoverage(
                    user_id=user_id,
                    assigned_territories=assigned,
                    assigned_routes=route_totals.get(user_id, 0),
                    customer_count=customer_totals.get(user_id, 0),
                    coverage_percent=round(coverage, 2),
                )
            )
        return result

    def _ensure_hierarchy_config(
        self, firm_id: UUID, actor_id: UUID
    ) -> SalesHierarchyConfig:
        config = self._session.scalar(
            select(SalesHierarchyConfig).where(
                SalesHierarchyConfig.firm_id == firm_id,
                SalesHierarchyConfig.is_deleted.is_(False),
            )
        )
        if config is not None:
            return config
        config = SalesHierarchyConfig(
            firm_id=firm_id,
            business_profile_id=self._profile_id(firm_id),
            max_levels=6,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(config)
        self._session.flush()
        defaults = [
            ("REGION", "Region", 1),
            ("TERRITORY", "Territory", 2),
            ("ROUTE", "Route", 3),
        ]
        for code, name, order in defaults:
            self._session.add(
                SalesHierarchyLevel(
                    config_id=config.id,
                    level_order=order,
                    level_code=code,
                    display_name=name,
                    is_mandatory=order <= 2,
                    is_enabled=True,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()
        return config

    def _replace_levels(
        self, config_id: UUID, levels: list[HierarchyLevelInput], actor_id: UUID
    ) -> None:
        existing = list(
            self._session.scalars(
                select(SalesHierarchyLevel).where(
                    SalesHierarchyLevel.config_id == config_id
                )
            )
        )
        existing_by_order = {
            row.level_order: row for row in existing if row.is_deleted is False
        }
        requested_orders = {item.level_order for item in levels}
        for row in existing:
            if row.level_order in requested_orders:
                continue
            in_use = self._session.scalar(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.hierarchy_level_id == row.id,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if in_use is not None:
                raise ValidationError(
                    "Cannot remove hierarchy levels that are already used by "
                    "territories."
                )
            self._session.delete(row)
        for item in levels:
            existing_row = existing_by_order.get(item.level_order)
            if existing_row is not None:
                existing_row.level_code = item.level_code
                existing_row.display_name = item.display_name
                existing_row.description = item.description
                existing_row.is_mandatory = item.is_mandatory
                existing_row.is_enabled = item.is_enabled
                existing_row.max_nodes_per_parent = item.max_nodes_per_parent
                existing_row.is_deleted = False
                existing_row.deleted_at = None
                existing_row.deleted_by = None
                existing_row.updated_by = actor_id
                continue
            self._session.add(
                SalesHierarchyLevel(
                    config_id=config_id,
                    level_order=item.level_order,
                    level_code=item.level_code,
                    display_name=item.display_name,
                    description=item.description,
                    is_mandatory=item.is_mandatory,
                    is_enabled=item.is_enabled,
                    max_nodes_per_parent=item.max_nodes_per_parent,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def _levels(self, config_id: UUID) -> list[SalesHierarchyLevel]:
        return list(
            self._session.scalars(
                select(SalesHierarchyLevel)
                .where(
                    SalesHierarchyLevel.config_id == config_id,
                    SalesHierarchyLevel.is_deleted.is_(False),
                )
                .order_by(SalesHierarchyLevel.level_order.asc())
            )
        )

    @staticmethod
    def _level_response(row: SalesHierarchyLevel) -> HierarchyLevelResponse:
        return HierarchyLevelResponse(
            id=row.id,
            level_order=row.level_order,
            level_code=row.level_code,
            display_name=row.display_name,
            description=row.description,
            is_mandatory=row.is_mandatory,
            is_enabled=row.is_enabled,
            max_nodes_per_parent=row.max_nodes_per_parent,
        )

    def _apply_filters(
        self,
        statement: Select[tuple[SalesTerritoryNode]],
        count: Select[tuple[int]],
        filters: TerritoryListFilters,
    ) -> tuple[Select[tuple[SalesTerritoryNode]], Select[tuple[int]]]:
        if not filters.include_deleted:
            statement = statement.where(SalesTerritoryNode.is_deleted.is_(False))
            count = count.where(SalesTerritoryNode.is_deleted.is_(False))
        if filters.hierarchy_level_id is not None:
            statement = statement.where(
                SalesTerritoryNode.hierarchy_level_id == filters.hierarchy_level_id
            )
            count = count.where(
                SalesTerritoryNode.hierarchy_level_id == filters.hierarchy_level_id
            )
        if filters.parent_id is not None:
            statement = statement.where(
                SalesTerritoryNode.parent_id == filters.parent_id
            )
            count = count.where(SalesTerritoryNode.parent_id == filters.parent_id)
        if filters.status is not None:
            statement = statement.where(
                SalesTerritoryNode.status == filters.status.value
            )
            count = count.where(SalesTerritoryNode.status == filters.status.value)
        if filters.salesman_id is not None:
            assignment_exists = select(TerritorySalesmanAssignment.id).where(
                TerritorySalesmanAssignment.territory_id == SalesTerritoryNode.id,
                TerritorySalesmanAssignment.user_id == filters.salesman_id,
                TerritorySalesmanAssignment.is_deleted.is_(False),
            )
            statement = statement.where(assignment_exists.exists())
            count = count.where(assignment_exists.exists())
        if filters.route_type_id is not None:
            route_type_exists = select(TerritoryRouteProfile.id).where(
                TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                TerritoryRouteProfile.route_type_id == filters.route_type_id,
                TerritoryRouteProfile.is_deleted.is_(False),
            )
            statement = statement.where(route_type_exists.exists())
            count = count.where(route_type_exists.exists())
        if filters.city_id is not None:
            city_exists = select(TerritoryRouteProfile.id).where(
                TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                TerritoryRouteProfile.city_id == filters.city_id,
                TerritoryRouteProfile.is_deleted.is_(False),
            )
            statement = statement.where(city_exists.exists())
            count = count.where(city_exists.exists())
        if filters.locality_id is not None:
            locality_exists = select(TerritoryRouteProfile.id).where(
                TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                TerritoryRouteProfile.locality_id == filters.locality_id,
                TerritoryRouteProfile.is_deleted.is_(False),
            )
            statement = statement.where(locality_exists.exists())
            count = count.where(locality_exists.exists())
        if filters.business_profile_id is not None:
            statement = statement.where(
                SalesTerritoryNode.business_profile_id == filters.business_profile_id
            )
            count = count.where(
                SalesTerritoryNode.business_profile_id == filters.business_profile_id
            )
        return statement, count

    def _territory_responses(
        self, rows: list[SalesTerritoryNode]
    ) -> list[TerritoryResponse]:
        ids = [item.id for item in rows]
        level_map = self._level_name_map_by_id(
            {item.hierarchy_level_id for item in rows}
        )
        customer_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritoryCustomerAssignment.territory_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .where(
                    TerritoryCustomerAssignment.territory_id.in_(ids),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                )
                .group_by(TerritoryCustomerAssignment.territory_id)
            )
        }
        active_customer_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritoryCustomerAssignment.territory_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .join(Customer, Customer.id == TerritoryCustomerAssignment.customer_id)
                .where(
                    TerritoryCustomerAssignment.territory_id.in_(ids),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                    Customer.is_deleted.is_(False),
                    Customer.status == "ACTIVE",
                )
                .group_by(TerritoryCustomerAssignment.territory_id)
            )
        }
        inactive_customer_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritoryCustomerAssignment.territory_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .join(Customer, Customer.id == TerritoryCustomerAssignment.customer_id)
                .where(
                    TerritoryCustomerAssignment.territory_id.in_(ids),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                    Customer.is_deleted.is_(False),
                    Customer.status != "ACTIVE",
                )
                .group_by(TerritoryCustomerAssignment.territory_id)
            )
        }
        new_customer_cutoff = utc_now() - timedelta(days=30)
        new_customer_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritoryCustomerAssignment.territory_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .join(Customer, Customer.id == TerritoryCustomerAssignment.customer_id)
                .where(
                    TerritoryCustomerAssignment.territory_id.in_(ids),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                    Customer.is_deleted.is_(False),
                    Customer.created_at >= new_customer_cutoff,
                )
                .group_by(TerritoryCustomerAssignment.territory_id)
            )
        }
        potential_customer_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritoryCustomerAssignment.territory_id,
                    func.count(TerritoryCustomerAssignment.id),
                )
                .where(
                    TerritoryCustomerAssignment.territory_id.in_(ids),
                    TerritoryCustomerAssignment.is_deleted.is_(False),
                    TerritoryCustomerAssignment.is_potential.is_(True),
                )
                .group_by(TerritoryCustomerAssignment.territory_id)
            )
        }
        salesman_counts = {
            row[0]: int(row[1] or 0)
            for row in self._session.execute(
                select(
                    TerritorySalesmanAssignment.territory_id,
                    func.count(TerritorySalesmanAssignment.id),
                )
                .where(
                    TerritorySalesmanAssignment.territory_id.in_(ids),
                    TerritorySalesmanAssignment.is_deleted.is_(False),
                )
                .group_by(TerritorySalesmanAssignment.territory_id)
            )
        }
        route_profiles = self._route_profile_map(set(ids))
        return [
            TerritoryResponse(
                id=item.id,
                firm_id=item.firm_id,
                business_profile_id=item.business_profile_id,
                hierarchy_level_id=item.hierarchy_level_id,
                hierarchy_level_name=level_map.get(item.hierarchy_level_id, ""),
                parent_id=item.parent_id,
                code=item.code,
                name=item.name,
                description=item.description,
                status=item.status,
                path=item.path,
                sort_order=item.sort_order,
                customer_count=customer_counts.get(item.id, 0),
                active_customer_count=active_customer_counts.get(item.id, 0),
                inactive_customer_count=inactive_customer_counts.get(item.id, 0),
                new_customer_count=new_customer_counts.get(item.id, 0),
                potential_customer_count=potential_customer_counts.get(item.id, 0),
                salesman_count=salesman_counts.get(item.id, 0),
                route_profile=route_profiles.get(item.id),
                created_at=item.created_at,
                updated_at=item.updated_at,
                is_deleted=item.is_deleted,
                deleted_at=item.deleted_at,
            )
            for item in rows
        ]

    def _level_name_map_by_id(self, level_ids: set[UUID]) -> dict[UUID, str]:
        if not level_ids:
            return {}
        return {
            row.id: row.display_name
            for row in self._session.scalars(
                select(SalesHierarchyLevel).where(SalesHierarchyLevel.id.in_(level_ids))
            )
        }

    def _route_profile_map(
        self, territory_ids: set[UUID]
    ) -> dict[UUID, RouteProfileResponse]:
        if not territory_ids:
            return {}
        profiles = list(
            self._session.scalars(
                select(TerritoryRouteProfile).where(
                    TerritoryRouteProfile.territory_id.in_(territory_ids),
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
        )
        if not profiles:
            return {}
        route_type_ids = {item.route_type_id for item in profiles if item.route_type_id}
        route_type_names = {
            row.id: row.name
            for row in self._session.scalars(
                select(RouteTypeMaster).where(
                    RouteTypeMaster.id.in_(route_type_ids),
                    RouteTypeMaster.is_deleted.is_(False),
                )
            )
        }
        working_days = defaultdict(list)
        for day in self._session.scalars(
            select(TerritoryWorkingDay).where(
                TerritoryWorkingDay.route_profile_id.in_(
                    {item.id for item in profiles}
                ),
                TerritoryWorkingDay.is_deleted.is_(False),
            )
        ):
            working_days[day.route_profile_id].append(day.weekday)
        return {
            profile.territory_id: RouteProfileResponse(
                route_type_id=profile.route_type_id,
                route_type_name=(
                    route_type_names.get(profile.route_type_id)
                    if profile.route_type_id is not None
                    else None
                ),
                visit_frequency=profile.visit_frequency,
                effective_from=profile.effective_from,
                effective_to=profile.effective_to,
                city_id=profile.city_id,
                postal_code_id=profile.postal_code_id,
                locality_id=profile.locality_id,
                working_days=sorted(working_days.get(profile.id, [])),
            )
            for profile in profiles
        }

    def _territory(
        self, territory_id: UUID, firm_id: UUID, *, include_deleted: bool = False
    ) -> SalesTerritoryNode:
        statement = select(SalesTerritoryNode).where(
            SalesTerritoryNode.id == territory_id,
            SalesTerritoryNode.firm_id == firm_id,
        )
        if not include_deleted:
            statement = statement.where(SalesTerritoryNode.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Territory not found.")
        return row

    def _level(self, level_id: UUID) -> SalesHierarchyLevel:
        row = self._session.scalar(
            select(SalesHierarchyLevel).where(
                SalesHierarchyLevel.id == level_id,
                SalesHierarchyLevel.is_deleted.is_(False),
                SalesHierarchyLevel.is_enabled.is_(True),
            )
        )
        if row is None:
            raise ValidationError("Configured hierarchy level is not active.")
        return row

    def _parent(
        self, firm_id: UUID, parent_id: UUID | None
    ) -> SalesTerritoryNode | None:
        if parent_id is None:
            return None
        return self._territory(parent_id, firm_id)

    def _validate_level_parent(
        self, level: SalesHierarchyLevel, parent: SalesTerritoryNode | None
    ) -> None:
        if parent is None:
            if level.level_order != 1:
                raise ValidationError(
                    "Only top hierarchy level can be created without a parent."
                )
            return
        parent_level = self._level(parent.hierarchy_level_id)
        if level.level_order != parent_level.level_order + 1:
            raise ValidationError(
                "Territory level must be exactly one level below its parent."
            )

    def _assert_unique_code(
        self, firm_id: UUID, code: str, current_id: UUID | None = None
    ) -> None:
        statement = select(SalesTerritoryNode.id).where(
            SalesTerritoryNode.firm_id == firm_id,
            SalesTerritoryNode.code == code,
            SalesTerritoryNode.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(SalesTerritoryNode.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("A territory with this code already exists.")

    def _next_available_code(self, firm_id: UUID, base_code: str) -> str:
        candidate = base_code.strip().upper()
        counter = 1
        while True:
            exists = self._session.scalar(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.code == candidate,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if exists is None:
                return candidate
            counter += 1
            candidate = f"{base_code.strip().upper()}_{counter}"

    def _next_available_name(
        self, firm_id: UUID, parent_id: UUID | None, base_name: str
    ) -> str:
        candidate = base_name.strip()
        counter = 1
        while True:
            exists = self._session.scalar(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.parent_id == parent_id,
                    SalesTerritoryNode.name.ilike(candidate),
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if exists is None:
                return candidate
            counter += 1
            candidate = f"{base_name.strip()} ({counter})"

    def _assert_unique_name_under_parent(
        self,
        *,
        firm_scope: UUID,
        parent_id: UUID | None,
        name: str,
        current_id: UUID | None = None,
    ) -> None:
        statement = select(SalesTerritoryNode.id).where(
            SalesTerritoryNode.firm_id == firm_scope,
            SalesTerritoryNode.parent_id == parent_id,
            SalesTerritoryNode.name.ilike(name.strip()),
            SalesTerritoryNode.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(SalesTerritoryNode.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError(
                "A territory with this name already exists under parent."
            )

    def _assert_not_descendant(self, parent_id: UUID, path_prefix: str) -> None:
        parent = self._session.scalar(
            select(SalesTerritoryNode).where(SalesTerritoryNode.id == parent_id)
        )
        if parent is None:
            return
        if parent.path.startswith(f"{path_prefix}/"):
            raise ValidationError("Circular hierarchy is not allowed.")

    def _upsert_route_profile(
        self,
        *,
        territory_id: UUID,
        data: RouteProfileInput | None,
        actor_id: UUID,
    ) -> None:
        profile = self._session.scalar(
            select(TerritoryRouteProfile).where(
                TerritoryRouteProfile.territory_id == territory_id
            )
        )
        if data is None:
            if profile is not None and not profile.is_deleted:
                profile.is_deleted = True
                profile.deleted_at = utc_now()
                profile.deleted_by = actor_id
                profile.updated_by = actor_id
            return
        if profile is None:
            profile = TerritoryRouteProfile(
                territory_id=territory_id,
                route_type_id=data.route_type_id,
                visit_frequency=data.visit_frequency.value,
                effective_from=data.effective_from,
                effective_to=data.effective_to,
                city_id=data.city_id,
                postal_code_id=data.postal_code_id,
                locality_id=data.locality_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(profile)
            self._session.flush()
        else:
            profile.route_type_id = data.route_type_id
            profile.visit_frequency = data.visit_frequency.value
            profile.effective_from = data.effective_from
            profile.effective_to = data.effective_to
            profile.city_id = data.city_id
            profile.postal_code_id = data.postal_code_id
            profile.locality_id = data.locality_id
            profile.updated_by = actor_id
            if profile.is_deleted:
                profile.is_deleted = False
                profile.deleted_at = None
                profile.deleted_by = None
        existing_days = {
            row.weekday: row
            for row in self._session.scalars(
                select(TerritoryWorkingDay).where(
                    TerritoryWorkingDay.route_profile_id == profile.id
                )
            )
        }
        requested = set(data.working_days)
        for weekday in requested:
            row = existing_days.get(weekday)
            if row is None:
                self._session.add(
                    TerritoryWorkingDay(
                        route_profile_id=profile.id,
                        weekday=weekday,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            elif row.is_deleted:
                row.is_deleted = False
                row.deleted_at = None
                row.deleted_by = None
                row.updated_by = actor_id
        for weekday, row in existing_days.items():
            if weekday not in requested and not row.is_deleted:
                row.is_deleted = True
                row.deleted_at = utc_now()
                row.deleted_by = actor_id
                row.updated_by = actor_id

    def _assert_unique_beat_code(
        self, firm_id: UUID, code: str, current_id: UUID | None = None
    ) -> None:
        statement = select(BeatPlan.id).where(
            BeatPlan.firm_id == firm_id,
            BeatPlan.code == code,
            BeatPlan.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(BeatPlan.id != current_id)
        if self._session.scalar(statement) is not None:
            raise ConflictError("A beat plan with this code already exists.")

    def _repath_descendants(
        self, node_id: UUID, old_prefix: str, new_prefix: str, actor_id: UUID
    ) -> None:
        for child in self._session.scalars(
            select(SalesTerritoryNode).where(
                SalesTerritoryNode.path.ilike(f"{old_prefix}/%"),
                SalesTerritoryNode.id != node_id,
                SalesTerritoryNode.is_deleted.is_(False),
            )
        ):
            child.path = child.path.replace(old_prefix, new_prefix, 1)
            child.updated_by = actor_id

    def _beat_plan(
        self, beat_plan_id: UUID, firm_id: UUID, *, include_deleted: bool = False
    ) -> BeatPlan:
        statement = select(BeatPlan).where(
            BeatPlan.id == beat_plan_id, BeatPlan.firm_id == firm_id
        )
        if not include_deleted:
            statement = statement.where(BeatPlan.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Beat plan not found.")
        return row

    def _replace_beat_stops(
        self,
        beat_plan_id: UUID,
        stops: list[BeatPlanStopInput],
        firm_scope: UUID,
        actor_id: UUID,
    ) -> None:
        for row in self._session.scalars(
            select(BeatPlanStop).where(BeatPlanStop.beat_plan_id == beat_plan_id)
        ):
            row.is_deleted = True
            row.deleted_at = utc_now()
            row.deleted_by = actor_id
            row.updated_by = actor_id
        for item in stops:
            territory_id = item.territory_id
            self._territory(territory_id, firm_scope)
            self._session.add(
                BeatPlanStop(
                    beat_plan_id=beat_plan_id,
                    territory_id=territory_id,
                    stop_order=item.stop_order,
                    planned_duration_minutes=item.planned_duration_minutes,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _beat_plan_response(self, row: BeatPlan) -> BeatPlanResponse:
        stops = list(
            self._session.scalars(
                select(BeatPlanStop)
                .where(
                    BeatPlanStop.beat_plan_id == row.id,
                    BeatPlanStop.is_deleted.is_(False),
                )
                .order_by(BeatPlanStop.stop_order.asc())
            )
        )
        return BeatPlanResponse(
            id=row.id,
            firm_id=row.firm_id,
            business_profile_id=row.business_profile_id,
            territory_id=row.territory_id,
            code=row.code,
            name=row.name,
            plan_type=row.plan_type,
            weekday=row.weekday,
            week_of_month=row.week_of_month,
            starts_on=row.starts_on,
            ends_on=row.ends_on,
            is_active=row.is_active,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
            stops=[
                {
                    "id": item.id,
                    "territory_id": item.territory_id,
                    "stop_order": item.stop_order,
                    "planned_duration_minutes": item.planned_duration_minutes,
                }
                for item in stops
            ],
        )

    def _profile_id(self, firm_id: UUID) -> UUID | None:
        assignment = self._session.scalar(
            select(FirmBusinessProfile).where(
                FirmBusinessProfile.firm_id == firm_id,
                FirmBusinessProfile.is_deleted.is_(False),
                FirmBusinessProfile.is_active.is_(True),
            )
        )
        if assignment is None:
            return None
        profile = self._session.scalar(
            select(BusinessProfile).where(
                BusinessProfile.id == assignment.business_profile_id,
                BusinessProfile.is_deleted.is_(False),
                BusinessProfile.status == "ACTIVE",
            )
        )
        return profile.id if profile is not None else None

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(
                "The operation violates uniqueness constraints."
            ) from error
