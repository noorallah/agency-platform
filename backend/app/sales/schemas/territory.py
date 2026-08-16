"""Validated request and response contracts for sales territory management."""

# ruff: noqa: D101, D102

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TerritorySchema(BaseModel):
    """Apply strict API schema behavior for territory endpoints."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class TerritoryStatus(StrEnum):
    """Supported territory node status values."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class VisitFrequency(StrEnum):
    """Supported route visit frequencies."""

    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ON_DEMAND = "ON_DEMAND"


class BeatPlanType(StrEnum):
    """Supported beat-plan recurrence patterns."""

    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    CUSTOM = "CUSTOM"


class GeoMasterWrite(TerritorySchema):
    """Shared writable fields for geographical masters."""

    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class GeoCountryWrite(GeoMasterWrite):
    iso2: str | None = Field(default=None, min_length=2, max_length=2)
    iso3: str | None = Field(default=None, min_length=3, max_length=3)
    phone_code: str | None = Field(default=None, min_length=1, max_length=10)


class GeoCountryResponse(TerritorySchema):
    id: UUID
    code: str
    name: str
    iso2: str | None
    iso3: str | None
    phone_code: str | None
    is_active: bool


class GeoStateWrite(GeoMasterWrite):
    country_id: UUID


class GeoStateResponse(TerritorySchema):
    id: UUID
    country_id: UUID
    code: str
    name: str
    is_active: bool


class GeoDistrictWrite(GeoMasterWrite):
    state_id: UUID


class GeoDistrictResponse(TerritorySchema):
    id: UUID
    state_id: UUID
    code: str
    name: str
    is_active: bool


class GeoCityWrite(GeoMasterWrite):
    district_id: UUID


class GeoCityResponse(TerritorySchema):
    id: UUID
    district_id: UUID
    code: str
    name: str
    is_active: bool


class GeoPostalCodeWrite(TerritorySchema):
    city_id: UUID
    postal_code: str = Field(min_length=1, max_length=20)
    is_active: bool = True


class GeoPostalCodeResponse(TerritorySchema):
    id: UUID
    city_id: UUID
    postal_code: str
    is_active: bool


class GeoLocalityWrite(TerritorySchema):
    postal_code_id: UUID
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True


class GeoLocalityResponse(TerritorySchema):
    id: UUID
    postal_code_id: UUID
    name: str
    is_active: bool


class AddressMasterWrite(TerritorySchema):
    owner_type: str = Field(min_length=1, max_length=40)
    owner_id: UUID
    address_type: str = Field(min_length=1, max_length=40)
    line1: str = Field(min_length=1, max_length=300)
    line2: str | None = Field(default=None, max_length=300)
    landmark: str | None = Field(default=None, max_length=200)
    country_id: UUID
    state_id: UUID | None = None
    district_id: UUID | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    is_primary: bool = False

    @field_validator("owner_type", "address_type", mode="before")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return value.strip().upper()


class AddressMasterResponse(AddressMasterWrite):
    id: UUID


class RouteTypeWrite(TerritorySchema):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class RouteTypeResponse(TerritorySchema):
    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool


class HierarchyLevelInput(TerritorySchema):
    """One configurable territory hierarchy level definition."""

    level_order: int = Field(ge=1, le=20)
    level_code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_mandatory: bool = True
    is_enabled: bool = True
    max_nodes_per_parent: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("level_code", mode="before")
    @classmethod
    def normalize_level_code(cls, value: str) -> str:
        """Normalize level codes for deterministic matching."""
        return value.strip().upper()


class HierarchyLevelResponse(TerritorySchema):
    """Persisted hierarchy level configuration details."""

    id: UUID
    level_order: int
    level_code: str
    display_name: str
    description: str | None
    is_mandatory: bool
    is_enabled: bool
    max_nodes_per_parent: int | None


class HierarchyResponse(TerritorySchema):
    """Firm hierarchy configuration with configurable level collection."""

    config_id: UUID
    firm_id: UUID
    business_profile_id: UUID | None
    max_levels: int
    allow_multi_route_per_salesman: bool
    allow_multi_salesman_per_route: bool
    enforce_customer_leaf_assignment: bool
    levels: list[HierarchyLevelResponse]


class HierarchyUpdateRequest(TerritorySchema):
    """Replace hierarchy configuration and configured levels for one firm."""

    max_levels: int = Field(ge=1, le=20)
    allow_multi_route_per_salesman: bool = True
    allow_multi_salesman_per_route: bool = True
    enforce_customer_leaf_assignment: bool = False
    levels: list[HierarchyLevelInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_level_order(self) -> "HierarchyUpdateRequest":
        """Require unique and contiguous level ordering."""
        ordered = sorted(item.level_order for item in self.levels if item.is_enabled)
        if len(ordered) != len(set(ordered)):
            raise ValueError("Hierarchy levels must not repeat level_order values.")
        if ordered and ordered != list(range(1, len(ordered) + 1)):
            raise ValueError(
                "Enabled hierarchy levels must use contiguous order from 1."
            )
        if len(self.levels) > self.max_levels:
            raise ValueError("Configured levels exceed max_levels.")
        return self


class RouteProfileInput(TerritorySchema):
    """Route profile extension fields for territory nodes."""

    route_type_id: UUID | None = None
    visit_frequency: VisitFrequency = VisitFrequency.ON_DEMAND
    effective_from: date | None = None
    effective_to: date | None = None
    city_id: UUID | None = None
    postal_code_id: UUID | None = None
    locality_id: UUID | None = None
    working_days: list[int] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def validate_dates_days(self) -> "RouteProfileInput":
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("effective_from must not be after effective_to.")
        if any(day < 1 or day > 7 for day in self.working_days):
            raise ValueError("working_days must use weekday values 1-7.")
        return self


class TerritoryCreate(TerritorySchema):
    """Create payload for one territory node."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    hierarchy_level_id: UUID
    parent_id: UUID | None = None
    description: str | None = None
    status: TerritoryStatus = TerritoryStatus.ACTIVE
    sort_order: int = Field(default=0, ge=0, le=999999)
    route_profile: RouteProfileInput | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize territory code for deterministic uniqueness."""
        return value.strip().upper()


class TerritoryUpdate(TerritoryCreate):
    """Replace editable territory node fields."""


class RouteProfileResponse(TerritorySchema):
    route_type_id: UUID | None
    route_type_name: str | None
    visit_frequency: str
    effective_from: date | None
    effective_to: date | None
    city_id: UUID | None
    postal_code_id: UUID | None
    locality_id: UUID | None
    working_days: list[int]


class TerritoryResponse(TerritorySchema):
    """Response contract for one territory node."""

    id: UUID
    firm_id: UUID
    business_profile_id: UUID | None
    hierarchy_level_id: UUID
    hierarchy_level_name: str
    parent_id: UUID | None
    code: str
    name: str
    description: str | None
    status: str
    path: str
    sort_order: int
    customer_count: int
    active_customer_count: int
    inactive_customer_count: int
    new_customer_count: int
    potential_customer_count: int
    salesman_count: int
    route_profile: RouteProfileResponse | None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None


class TerritoryTreeNodeResponse(TerritorySchema):
    """Recursive tree response contract for hierarchy visualization."""

    id: UUID
    parent_id: UUID | None
    hierarchy_level_id: UUID
    hierarchy_level_name: str
    code: str
    name: str
    status: str
    path: str
    children: list["TerritoryTreeNodeResponse"] = Field(default_factory=list)


class TerritoryDetailResponse(TerritoryResponse):
    """Extended territory details including linked assignment identifiers."""

    customer_ids: list[UUID]
    salesman_ids: list[UUID]
    child_ids: list[UUID]


class TerritoryDashboardStats(TerritorySchema):
    total_territories: int
    total_routes: int
    assigned_customers: int
    assigned_salesmen: int
    customers_without_route: int
    routes_without_salesman: int


class TerritorySalesmanCoverage(TerritorySchema):
    user_id: UUID
    assigned_territories: int
    assigned_routes: int
    customer_count: int
    coverage_percent: float


class TerritorySalesmanCandidate(TerritorySchema):
    """One person a route can be handed to.

    Assigning a salesperson needs the firm's people by name, and ``users``
    lives only in the platform schema behind ``USER_VIEW`` -- a platform-admin
    permission the roles that run territories do not hold. Without this the
    desktop had to ask for a raw user id, which is not something anybody knows.
    """

    user_id: UUID
    full_name: str
    email: str


class TerritoryListFilters(TerritorySchema):
    """Validated filters for territory list endpoints."""

    hierarchy_level_id: UUID | None = None
    parent_id: UUID | None = None
    status: TerritoryStatus | None = None
    salesman_id: UUID | None = None
    city_id: UUID | None = None
    locality_id: UUID | None = None
    route_type_id: UUID | None = None
    business_profile_id: UUID | None = None
    include_deleted: bool = False


class TerritoryCustomerAssignmentInput(TerritorySchema):
    customer_id: UUID
    visit_sequence: int | None = Field(default=None, ge=1, le=100000)
    #: A shop the round calls on but does not yet sell to.
    #:
    #: `None` means "leave it alone", for the same reason `is_primary` does:
    #: every client used to send a hardcoded `False` on every save, so the flag
    #: was wiped by the next round save and `potential_customer_count` -- shown
    #: on the grid and the coverage line -- could only ever read zero.
    is_potential: bool | None = None
    #: Which round a document for this customer belongs to. Every assignment
    #: was written `is_primary = True` with no way for a caller to say
    #: otherwise, so once a shop could be on two rounds the flag could not
    #: settle which one a sale counts against.
    #:
    #: `None` means "leave it alone" rather than `False`: a new assignment
    #: still defaults to primary, matching what every existing caller wrote,
    #: and re-saving a round from the customer picker -- which sends no flag --
    #: cannot silently demote the round someone chose. The salesman list was
    #: demoted exactly that way once already.
    is_primary: bool | None = None


class TerritoryCustomerAssignmentResponse(TerritorySchema):
    """One customer's place on a round.

    The `GET`/`PUT` pair for territory customers used to move a bare list of
    ids, which meant `visit_sequence` -- the order the round is walked in --
    could be written and never read back. A round with no readable order is a
    set, not a route.
    """

    customer_id: UUID
    is_primary: bool
    visit_sequence: int | None
    is_potential: bool


class TerritoryAssignCustomersRequest(TerritorySchema):
    """Replace customer assignments for one territory node."""

    customer_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    entries: list[TerritoryCustomerAssignmentInput] = Field(
        default_factory=list, max_length=5000
    )

    @model_validator(mode="after")
    def validate_call_order(self) -> "TerritoryAssignCustomersRequest":
        """Refuse two shops at the same stop number.

        The database refuses it too, but as a rollback reading "the operation
        violates uniqueness constraints", which names neither the round nor the
        number. This call replaces the whole list for one territory, so every
        sequence in play arrives in this payload and the clash can be named
        here instead.
        """
        placed = [
            item.visit_sequence
            for item in self.entries
            if item.visit_sequence is not None
        ]
        duplicates = sorted({value for value in placed if placed.count(value) > 1})
        if duplicates:
            raise ValueError(
                "Two customers cannot share a stop number on one route: "
                + ", ".join(str(value) for value in duplicates)
            )
        return self


class SalesmanAssignmentInput(TerritorySchema):
    """One salesperson assignment entry for a territory node."""

    user_id: UUID
    include_children: bool = False
    is_primary: bool = False


class TerritoryAssignSalesmenRequest(TerritorySchema):
    """Replace salesperson assignments for one territory node."""

    assignments: list[SalesmanAssignmentInput] = Field(
        default_factory=list, max_length=5000
    )

    @model_validator(mode="after")
    def validate_primary(self) -> "TerritoryAssignSalesmenRequest":
        """Limit each territory to one primary salesperson assignment."""
        if sum(item.is_primary for item in self.assignments) > 1:
            raise ValueError("Only one primary salesman assignment is allowed.")
        return self


class TerritoryCopyRequest(TerritorySchema):
    """Copy one hierarchy subtree under a target parent."""

    new_root_code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    new_root_name: str = Field(min_length=1, max_length=200)
    target_parent_id: UUID | None = None
    include_assignments: bool = False

    @field_validator("new_root_code", mode="before")
    @classmethod
    def normalize_root_code(cls, value: str) -> str:
        return value.strip().upper()


class CustomerRoute(TerritorySchema):
    """One round that calls a given shop, and where in it.

    The relationship was one-directional everywhere: from a territory you could
    list its customers, and from a customer you could see nothing at all.
    """

    territory_id: UUID
    code: str
    name: str
    path: str
    is_route: bool
    is_primary: bool
    visit_sequence: int | None


class AssignableCustomer(TerritorySchema):
    """One shop a round could call, with enough address to find it by.

    Built for the question a supervisor actually asks -- "which outlets on this
    pin code are not on a round yet" -- which the customer list could not
    answer: it filters on city and state and nothing finer, and it knows
    nothing about territory assignment at all.
    """

    customer_id: UUID
    code: str
    name: str
    address_line: str
    area: str | None
    city: str
    postal_code: str
    #: Already on the route being built, and where in its order.
    on_this_route: bool
    visit_sequence: int | None
    #: A prospect on this round rather than a buyer. Carried so the screen that
    #: offers the toggle knows the current state before it saves.
    is_potential: bool = False
    #: Other rounds that already call this shop, by code. A distributor calling
    #: the same outlet on a sales beat and a collection round is ordinary, so
    #: this is information rather than a warning.
    other_routes: list[str] = Field(default_factory=list)


class AssignableCustomerFilters(TerritorySchema):
    """How to narrow the outlets offered to a round."""

    postal_code: str | None = Field(default=None, max_length=24)
    area: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    #: Only shops no live route assignment names. The default is False, because
    #: hiding a shop already on another round would make it impossible to put
    #: one outlet on both.
    unassigned_only: bool = False


class TerritoryBulkCustomerAssignment(TerritorySchema):
    """One territory's customer list, for a batch that applies several at once."""

    territory_id: UUID
    customer_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    #: Carried so a bulk assignment can set the call order and the primary
    #: flag. The bulk path used to forward only `customer_ids`, which made it a
    #: strictly weaker version of the single-row endpoint for no reason.
    entries: list[TerritoryCustomerAssignmentInput] = Field(
        default_factory=list, max_length=5000
    )


class TerritoryBulkSalesmanAssignment(TerritorySchema):
    territory_id: UUID
    assignments: list[SalesmanAssignmentInput] = Field(
        default_factory=list, max_length=5000
    )


class TerritoryBulkCustomerRequest(TerritorySchema):
    """A batch of per-territory customer lists.

    Wrapped in an object rather than posted as a bare JSON array so that all
    four bulk endpoints take the same shape -- the status and move endpoints
    always did, and a bare array cannot be sent by the desktop client, whose
    request body is a map.
    """

    items: list[TerritoryBulkCustomerAssignment] = Field(min_length=1, max_length=5000)


class TerritoryBulkSalesmanRequest(TerritorySchema):
    """A batch of per-territory salesperson lists."""

    items: list[TerritoryBulkSalesmanAssignment] = Field(min_length=1, max_length=5000)


class TerritoryBulkStatusRequest(TerritorySchema):
    territory_ids: list[UUID] = Field(min_length=1, max_length=5000)
    status: TerritoryStatus


class TerritoryBulkMoveRequest(TerritorySchema):
    territory_ids: list[UUID] = Field(min_length=1, max_length=5000)
    new_parent_id: UUID | None = None


class BulkOperationResult(TerritorySchema):
    affected: int
    failed: int = 0


class BeatPlanCustomerStopInput(TerritorySchema):
    """One ordered outlet on a beat plan.

    Optional: a plan that lists none calls every customer on its territory, in
    `visit_sequence` order. These rows exist for a route that splits into
    several day-beats calling different shops.
    """

    customer_id: UUID
    stop_order: int = Field(ge=1, le=1000)
    planned_duration_minutes: int | None = Field(default=None, ge=1, le=1440)


class BeatPlanWrite(TerritorySchema):
    """Shared writable beat-plan fields for create and update operations."""

    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    territory_id: UUID
    plan_type: BeatPlanType
    weekday: int | None = Field(default=None, ge=1, le=7)
    week_of_month: int | None = Field(default=None, ge=1, le=5)
    starts_on: date | None = None
    ends_on: date | None = None
    is_active: bool = True
    notes: str | None = None
    customer_stops: list[BeatPlanCustomerStopInput] = Field(
        default_factory=list, max_length=1000
    )

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize beat-plan code for deterministic uniqueness."""
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self) -> "BeatPlanWrite":
        """Reject inverted date ranges."""
        if (
            self.starts_on is not None
            and self.ends_on is not None
            and self.starts_on > self.ends_on
        ):
            raise ValueError("starts_on must not be after ends_on.")
        return self


class BeatPlanCreate(BeatPlanWrite):
    """Create payload for one beat-plan template."""


class BeatPlanUpdate(BeatPlanWrite):
    """Replace payload for one beat-plan template."""


class BeatPlanCustomerStopResponse(TerritorySchema):
    """Persisted outlet stop representation."""

    id: UUID
    customer_id: UUID
    stop_order: int
    planned_duration_minutes: int | None


class CallListStop(TerritorySchema):
    """One outlet to be called, in the order the round walks it."""

    customer_id: UUID
    customer_code: str
    customer_name: str
    stop_order: int
    planned_duration_minutes: int | None


class CallListEntry(TerritorySchema):
    """What one beat plan asks for on one date.

    `occurs` is answered even when it is false, and `reason` says why, because
    "this plan does not run today" and "this plan cannot be computed" are
    different answers and a screen that shows an empty list for both is lying
    about one of them.
    """

    beat_plan_id: UUID
    beat_plan_code: str
    beat_plan_name: str
    territory_id: UUID
    territory_code: str
    territory_name: str
    salesman_id: UUID | None
    occurs: bool
    reason: str | None
    stops: list[CallListStop] = Field(default_factory=list)


class CallListResponse(TerritorySchema):
    """Every plan's call list for one date."""

    on_date: date
    entries: list[CallListEntry] = Field(default_factory=list)


class BeatPlanResponse(TerritorySchema):
    """Persisted beat-plan response envelope."""

    id: UUID
    firm_id: UUID
    business_profile_id: UUID | None
    territory_id: UUID
    code: str
    name: str
    plan_type: str
    weekday: int | None
    week_of_month: int | None
    starts_on: date | None
    ends_on: date | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    customer_stops: list[BeatPlanCustomerStopResponse] = Field(default_factory=list)
