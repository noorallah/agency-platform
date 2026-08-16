"""Firm-scoped sales territory hierarchy and reusable geo persistence models."""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class SalesHierarchyConfig(BaseEntity):
    """Store configurable hierarchy behavior for one firm."""

    __tablename__ = "sales_hierarchy_configs"
    __table_args__ = (
        UniqueConstraint("firm_id", name="UQ_sales_hierarchy_configs_firm"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id")
    )
    max_levels: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default="6"
    )
    allow_multi_route_per_salesman: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    allow_multi_salesman_per_route: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    enforce_customer_leaf_assignment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class SalesHierarchyLevel(BaseEntity):
    """Store one configurable hierarchy level."""

    __tablename__ = "sales_hierarchy_levels"
    __table_args__ = (
        UniqueConstraint(
            "config_id", "level_order", name="UQ_sales_hierarchy_level_order"
        ),
        UniqueConstraint(
            "config_id", "level_code", name="UQ_sales_hierarchy_level_code"
        ),
        Index("IX_sales_hierarchy_levels_config_enabled", "config_id", "is_enabled"),
    )

    config_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_hierarchy_configs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    level_order: Mapped[int] = mapped_column(Integer, nullable=False)
    level_code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    max_nodes_per_parent: Mapped[int | None] = mapped_column(Integer)


class SalesTerritoryNode(BaseEntity):
    """Store one node in the configurable sales hierarchy tree."""

    __tablename__ = "sales_territories"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_sales_territories_firm_code"),
        Index("IX_sales_territories_firm_parent", "firm_id", "parent_id"),
        Index("IX_sales_territories_firm_level", "firm_id", "hierarchy_level_id"),
        Index("IX_sales_territories_firm_path", "firm_id", "path"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id")
    )
    hierarchy_level_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_hierarchy_levels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_territories.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    path: Mapped[str] = mapped_column(String(1200), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class TerritoryCustomerAssignment(BaseEntity):
    """Assign one customer to one territory node."""

    __tablename__ = "territory_customer_assignments"
    __table_args__ = (
        UniqueConstraint(
            "territory_id",
            "customer_id",
            name="UQ_territory_customer_assignments_territory_customer",
        ),
        Index("IX_territory_customer_assignments_customer", "customer_id"),
    )

    territory_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_territories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    visit_sequence: Mapped[int | None] = mapped_column(Integer)
    is_potential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class TerritorySalesmanAssignment(BaseEntity):
    """Assign one salesperson user to one territory node."""

    __tablename__ = "territory_salesman_assignments"
    __table_args__ = (
        UniqueConstraint(
            "territory_id",
            "user_id",
            name="UQ_territory_salesman_assignments_territory_user",
        ),
        Index("IX_territory_salesman_assignments_user", "user_id"),
    )

    territory_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_territories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    include_children: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class BeatPlan(BaseEntity):
    """Store beat-planning templates without visit execution data."""

    __tablename__ = "sales_beat_plans"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_sales_beat_plans_firm_code"),
        Index("IX_sales_beat_plans_firm_status", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    business_profile_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("business_profiles.id")
    )
    territory_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_territories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    weekday: Mapped[int | None] = mapped_column(Integer)
    week_of_month: Mapped[int | None] = mapped_column(Integer)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notes: Mapped[str | None] = mapped_column(Text)


class BeatPlanStop(BaseEntity):
    """Store one ordered territory stop belonging to a beat plan."""

    __tablename__ = "sales_beat_plan_stops"
    __table_args__ = (
        UniqueConstraint(
            "beat_plan_id", "stop_order", name="UQ_sales_beat_plan_stops_plan_order"
        ),
        UniqueConstraint(
            "beat_plan_id",
            "territory_id",
            name="UQ_sales_beat_plan_stops_plan_territory",
        ),
    )

    beat_plan_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_beat_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    territory_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_territories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_duration_minutes: Mapped[int | None] = mapped_column(Integer)


class BeatPlanCustomerStop(BaseEntity):
    """Store one ordered outlet belonging to a beat plan.

    `BeatPlanStop` names a *sub-territory*, which only works when the hierarchy
    has a level below the route to act as a day bucket. The demo firms run
    `Region > Territory > Route`, so a plan's territory is already the leaf and
    its territory stops have nothing to point at -- that table is unusable for
    them.

    This one names outlets directly, so a route that splits into several
    day-beats can say which shops belong to which. It is additive: a plan that
    lists none falls back to the customers on its territory, in
    `visit_sequence` order, which is the ordinary case and needs no rows here
    at all.
    """

    __tablename__ = "sales_beat_plan_customer_stops"
    __table_args__ = (
        UniqueConstraint(
            "beat_plan_id",
            "stop_order",
            name="UQ_sales_beat_plan_customer_stops_plan_order",
        ),
        UniqueConstraint(
            "beat_plan_id",
            "customer_id",
            name="UQ_sales_beat_plan_customer_stops_plan_customer",
        ),
    )

    beat_plan_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_beat_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_duration_minutes: Mapped[int | None] = mapped_column(Integer)


class GeoCountry(BaseEntity):
    """Reusable geographical master for countries."""

    __tablename__ = "geo_countries"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_countries_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_geo_countries_name_active",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    iso2: Mapped[str | None] = mapped_column(String(2))
    iso3: Mapped[str | None] = mapped_column(String(3))
    phone_code: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class GeoState(BaseEntity):
    """Reusable geographical master for states/provinces."""

    __tablename__ = "geo_states"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_states_country_code_active",
            "country_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_geo_states_country_name_active",
            "country_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_geo_states_country_active", "country_id", "is_active"),
    )

    country_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class GeoDistrict(BaseEntity):
    """Reusable geographical master for districts."""

    __tablename__ = "geo_districts"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_districts_state_code_active",
            "state_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_geo_districts_state_name_active",
            "state_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_geo_districts_state_active", "state_id", "is_active"),
    )

    state_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("geo_states.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class GeoCity(BaseEntity):
    """Reusable geographical master for cities."""

    __tablename__ = "geo_cities"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_cities_district_code_active",
            "district_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "UQ_geo_cities_district_name_active",
            "district_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_geo_cities_district_active", "district_id", "is_active"),
    )

    district_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("geo_districts.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class GeoPostalCode(BaseEntity):
    """Reusable geographical master for postal codes."""

    __tablename__ = "geo_postal_codes"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_postal_codes_city_code_active",
            "city_id",
            "postal_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_geo_postal_codes_city_active", "city_id", "is_active"),
    )

    city_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT"), nullable=False
    )
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class GeoLocality(BaseEntity):
    """Reusable geographical master for areas/localities."""

    __tablename__ = "geo_localities"
    __table_args__ = (
        # Scoped to live rows: these are soft-deleted, so a table-wide key
        # would let a retired place hold its code and name forever and
        # refuse the re-creation with nothing on screen to explain it.
        # Mirrors UQ_firms_code_active; MySQL ignores the predicate, so
        # SalesTerritoryService stays the authoritative check.
        Index(
            "UQ_geo_localities_postal_name_active",
            "postal_code_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("IX_geo_localities_postal_active", "postal_code_id", "is_active"),
    )

    postal_code_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("geo_postal_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class AddressMaster(BaseEntity):
    """Reusable multi-address storage for firm-owned entities."""

    __tablename__ = "address_masters"
    __table_args__ = (
        Index("IX_address_masters_owner", "firm_id", "owner_type", "owner_id"),
        Index("IX_address_masters_geo", "country_id", "state_id", "city_id"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    address_type: Mapped[str] = mapped_column(String(40), nullable=False)
    line1: Mapped[str] = mapped_column(String(300), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(300))
    landmark: Mapped[str | None] = mapped_column(String(200))
    country_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("geo_countries.id", ondelete="RESTRICT"), nullable=False
    )
    state_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_states.id", ondelete="RESTRICT")
    )
    district_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_districts.id", ondelete="RESTRICT")
    )
    city_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT")
    )
    postal_code_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_postal_codes.id", ondelete="RESTRICT")
    )
    locality_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_localities.id", ondelete="RESTRICT")
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class RouteTypeMaster(BaseEntity):
    """Reusable route-type master for territory route profiles."""

    __tablename__ = "sales_route_types"
    __table_args__ = (
        UniqueConstraint("firm_id", "code", name="UQ_sales_route_types_firm_code"),
        UniqueConstraint("firm_id", "name", name="UQ_sales_route_types_firm_name"),
        Index("IX_sales_route_types_firm_active", "firm_id", "is_active"),
    )

    firm_id: Mapped[UUID] = mapped_column(
        UUIDType(), ForeignKey("firms.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class TerritoryRouteProfile(BaseEntity):
    """Route-specific extension fields for territory nodes."""

    __tablename__ = "territory_route_profiles"
    __table_args__ = (
        UniqueConstraint("territory_id", name="UQ_territory_route_profiles_territory"),
        Index("IX_territory_route_profiles_route_type", "route_type_id"),
    )

    territory_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("sales_territories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    route_type_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("sales_route_types.id", ondelete="RESTRICT")
    )
    visit_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ON_DEMAND", server_default="ON_DEMAND"
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    city_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_cities.id", ondelete="RESTRICT")
    )
    postal_code_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_postal_codes.id", ondelete="RESTRICT")
    )
    locality_id: Mapped[UUID | None] = mapped_column(
        UUIDType(), ForeignKey("geo_localities.id", ondelete="RESTRICT")
    )


class TerritoryWorkingDay(BaseEntity):
    """Working weekdays assigned to one route profile."""

    __tablename__ = "territory_working_days"
    __table_args__ = (
        UniqueConstraint(
            "route_profile_id", "weekday", name="UQ_territory_working_days_profile_day"
        ),
        Index("IX_territory_working_days_profile", "route_profile_id"),
    )

    route_profile_id: Mapped[UUID] = mapped_column(
        UUIDType(),
        ForeignKey("territory_route_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
