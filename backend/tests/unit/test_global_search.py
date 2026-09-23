"""Enterprise global search service tests."""

import inspect
import re
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from typing import get_args
from uuid import UUID, uuid4

import pytest
from fastapi import params
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Warehouse, WarehouseStorageNode
from app.business.models import BusinessProfile
from app.common.scope import FirmScope, OptionalFirmScope, optional_firm_scope
from app.core.database.base import Base
from app.core.database.dependencies import get_platform_db
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import Permission, Role, User, UserFirm
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import product as _product_models  # noqa: F401
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales.models import territory as _sales_models  # noqa: F401
from app.search.api.router import global_search
from app.search.services import SearchService
from app.search.services import search_service as search_service_module
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401
from app.vendors.models import vendor as _vendor_models  # noqa: F401


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _principal(
    user_id: UUID,
    *,
    permissions: set[str],
    firm_id: UUID | None = None,
    roles: set[str] | None = None,
) -> Principal:
    claim_roles = roles or set()
    return Principal(
        subject=user_id,
        roles=frozenset(claim_roles),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=sorted(claim_roles),
            permissions=sorted(permissions),
        ),
        firm_id=firm_id,
    )


def test_global_search_respects_firm_scope_and_permissions() -> None:
    """Search returns one firm's records to that firm, and no others.

    A search box that reaches across firms is a tenancy breach with a
    friendly interface.
    """
    session = _session_factory()()
    first_firm = Firm(
        name="First Firm",
        code="FIRST",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    second_firm = Firm(
        name="Second Firm",
        code="SECOND",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([first_firm, second_firm])
    session.flush()
    session.add_all(
        [
            Customer(
                firm_id=first_firm.id,
                code="CUST-001",
                customer_type="RETAIL",
                name="Acme Medical",
                display_name="Acme Medical",
                currency_code="INR",
                status="ACTIVE",
                created_by=uuid4(),
                updated_by=uuid4(),
            ),
            Customer(
                firm_id=second_firm.id,
                code="CUST-002",
                customer_type="RETAIL",
                name="Acme Retail",
                display_name="Acme Retail",
                currency_code="INR",
                status="ACTIVE",
                created_by=uuid4(),
                updated_by=uuid4(),
            ),
        ]
    )
    session.commit()

    permitted = _principal(
        uuid4(),
        permissions={"CUSTOMER_VIEW"},
        firm_id=first_firm.id,
    )
    result = SearchService(session).search(
        query="Acme",
        principal=permitted,
        category="masters",
        page=1,
        page_size=20,
    )
    assert result.total == 1
    assert result.results[0].entity_type == "customers"
    assert result.results[0].title == "Acme Medical"

    forbidden = _principal(uuid4(), permissions=set(), firm_id=first_firm.id)
    blocked = SearchService(session).search(
        query="Acme",
        principal=forbidden,
        category="masters",
        page=1,
        page_size=20,
    )
    assert blocked.total == 0


def test_global_search_returns_platform_entities_for_platform_admin() -> None:
    """Platform administration is searchable by platform authority only."""
    session = _session_factory()()
    actor = uuid4()
    session.add_all(
        [
            User(
                email="architect@example.com",
                full_name="Enterprise Architect",
                password_hash="hashed",
                created_by=actor,
                updated_by=actor,
            ),
            Role(
                code="OPS_ADMIN",
                name="Ops Admin",
                created_by=actor,
                updated_by=actor,
            ),
            Permission(
                code="PLATFORM_VIEW",
                name="Platform View",
                created_by=actor,
                updated_by=actor,
            ),
            BusinessProfile(
                code="GENERIC",
                name="Generic",
                industry_type="GENERIC",
                status="ACTIVE",
                is_default=True,
                default_settings={},
                created_by=actor,
                updated_by=actor,
            ),
        ]
    )
    session.commit()
    principal = _principal(
        actor,
        permissions={"PLATFORM_VIEW", "USER_VIEW", "ROLE_VIEW", "PERMISSION_VIEW"},
        roles={"platform_admin"},
    )
    result = SearchService(session).search(
        query="Admin",
        principal=principal,
        category="organization",
        page=1,
        page_size=20,
    )
    assert any(item.entity_type == "roles" for item in result.results)


def test_search_scope_rejects_a_firm_the_user_does_not_belong_to() -> None:
    """A supplied X-Firm-ID must be backed by an active membership.

    Global search had no scope dependency at all. Because every entity filter
    narrows *to* ``principal.firm_id``, and ``permissions`` carries globally
    assigned custom roles that ``has_permission`` accepts for any firm, a caller
    could read another firm's data purely by changing the header.
    """
    session = _session_factory()()
    home = Firm(
        name="Home Firm",
        code="HOME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    other = Firm(
        name="Other Firm",
        code="OTHER",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([home, other])
    session.flush()
    user = User(
        email="member@example.com",
        full_name="Member",
        password_hash="x",
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        UserFirm(user_id=user.id, firm_id=home.id, is_active=True, is_primary=True)
    )
    session.commit()

    principal = _principal(user.id, permissions={"CUSTOMER_VIEW"})

    scope = optional_firm_scope(principal=principal, db=session, x_firm_id=home.id)
    assert scope.firm_id == home.id

    with pytest.raises(AuthorizationError):
        optional_firm_scope(principal=principal, db=session, x_firm_id=other.id)

    unknown = optional_firm_scope(principal=principal, db=session, x_firm_id=None)
    assert unknown.firm_id is None


def test_search_scope_requires_the_firm_to_exist_and_be_active() -> None:
    """An unknown or inactive firm is refused rather than silently accepted."""
    session = _session_factory()()
    inactive = Firm(
        name="Closed Firm",
        code="CLOSED",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=False,
    )
    session.add(inactive)
    session.commit()

    principal = _principal(uuid4(), permissions={"CUSTOMER_VIEW"})
    with pytest.raises(AuthorizationError):
        optional_firm_scope(principal=principal, db=session, x_firm_id=inactive.id)
    with pytest.raises(AuthorizationError):
        optional_firm_scope(principal=principal, db=session, x_firm_id=uuid4())


def test_global_search_route_resolves_a_validated_firm_scope() -> None:
    """The route must take its principal from the validated scope.

    Testing ``optional_firm_scope`` alone would still pass if the search route
    went back to reading the raw principal, which is the defect this guards.
    """
    annotations = inspect.get_annotations(global_search, eval_str=False)
    assert "scope" in annotations, "global search must resolve a firm scope"
    assert (
        "principal" not in annotations
    ), "global search must not take an unvalidated principal directly"
    assert get_args(OptionalFirmScope)[0] is FirmScope


def test_firm_scope_is_resolved_against_the_platform_store() -> None:
    """Membership must be checked on a platform session, never the tenant one.

    ``firms`` and ``user_firms`` exist only in the platform schema. Every
    firm-owned router used to resolve them on the request's tenant session,
    whose search_path is the firm schema, so on PostgreSQL the check raised
    UndefinedTable for every firm whose data does not live in the platform
    schema. SQLite puts every table in one schema, which is why the unit suite
    never noticed.
    """
    annotation = inspect.get_annotations(optional_firm_scope)["db"]
    depends = next(
        arg for arg in get_args(annotation) if isinstance(arg, params.Depends)
    )
    assert depends.dependency is get_platform_db


def test_no_firm_owned_router_declares_its_own_scope_resolver() -> None:
    """Firm-owned routers must compose the shared scope, not re-implement it.

    A private copy is how the tenant-session defect spread to nineteen routers,
    and how global search ended up with no membership check at all.
    """
    allowed = {
        # Platform paths: these legitimately run on the platform session and
        # manage the membership records themselves.
        "app/identity/api/router.py",
        # Passes an explicit platform session to its own resolver.
        "app/business/api/router.py",
    }
    offenders = sorted(
        path.as_posix()
        for path in Path("app").glob("*/api/router.py")
        if "UserFirm" in path.read_text(encoding="utf-8")
        and path.as_posix() not in allowed
    )
    assert not offenders, f"routers with a private firm-scope resolver: {offenders}"


def test_no_service_resolves_firms_on_a_tenant_session() -> None:
    """Services must not query ``firms``/``user_firms`` on the request session.

    Those tables exist only in the platform schema, and a tenant session runs
    ``SET search_path TO "<firm schema>"`` with no fallback. This defect has
    shipped three times — in every firm-owned router, then in the shared
    document base, then in the business framework — and the unit suite cannot
    see any of it because SQLite puts every table in one schema.

    Use ``app.common.firm_metadata.FirmMetadataReader``, which resolves against
    the platform connection, or take a platform session explicitly.
    """
    owns_the_tables = {
        # Own the firm registry and membership; their routes are platform paths.
        "app/firms/services/firm_service.py",
        "app/identity/services/identity_service.py",
        # The reader and the scope dependency that resolve against platform.
        "app/common/firm_metadata.py",
        "app/common/scope.py",
        # Takes two sessions by name -- the platform one for the firm record
        # and its memberships, the firm's own store for everything else --
        # and its routes are platform paths under /api/v1/firms.
        "app/firms/services/readiness.py",
        # Reads `users` and `user_firms` for its people definition, and only
        # ever through `platform_reader()` or on a platform session --
        # `test_search_platform_store.py` compares its `platform_store` flags
        # with `_PLATFORM_TABLES`, and
        # `test_a_firm_caller_searches_only_the_firms_own_people` is the read.
        "app/search/services/search_service.py",
    }
    # Known offenders, kept empty. Five instances of this defect shipped before
    # the guard existed; all are fixed. Anything added here needs a fix, not a
    # permanent home — the assertions below fail both on a new violation and on
    # leaving a fixed entry behind.
    known_bugs: set[str] = set()
    offenders: set[str] = set()
    for path in Path("app").rglob("*.py"):
        key = path.as_posix()
        if "/services/" not in key and key not in owns_the_tables:
            continue
        if key in owns_the_tables:
            continue
        source = path.read_text(encoding="utf-8")
        # Word-bounded so FirmControlAccount, FirmMetadata and
        # FirmStorageMapping are not mistaken for the registry tables.
        if re.search("(?:^|[^A-Za-z_])(?:Firm|UserFirm)[.][A-Za-z_]", source):
            offenders.add(key)

    new_offenders = offenders - known_bugs
    assert not new_offenders, (
        "new services resolving firms on a tenant session: " f"{sorted(new_offenders)}"
    )
    fixed = known_bugs - offenders
    assert not fixed, (
        "these were fixed — remove them from known_bugs so the list stays "
        f"honest: {sorted(fixed)}"
    )


def test_global_search_never_crosses_firms_even_for_a_platform_admin() -> None:
    """A platform admin with no firm selected used to see every firm's rows.

    The firm filter was skipped entirely for platform admins. In a SHARED
    deployment one schema holds every firm's rows, so the exemption put two
    firms' customers in a single result list -- the exemption the rest of the
    platform explicitly refuses on firm-owned resources.
    """
    session = _session_factory()()
    actor = uuid4()
    firms = []
    for code in ("ALPHA", "BETA"):
        firm = Firm(
            name=f"{code} Firm",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(firm)
        session.flush()
        firms.append(firm)
        session.add(
            Customer(
                firm_id=firm.id,
                code=f"CUST-{code}",
                customer_type="BUSINESS",
                name=f"Shared Name {code}",
                display_name=f"Shared Name {code}",
                currency_code="INR",
                status="ACTIVE",
                created_by=actor,
                updated_by=actor,
            )
        )
    session.commit()

    service = SearchService(session)

    def _titles(firm_id: UUID | None) -> list[str]:
        principal = _principal(
            actor, permissions={"CUSTOMER_VIEW"}, roles={"platform_admin"}
        )
        page = service.search(
            query="Shared Name",
            principal=principal.__class__(
                subject=principal.subject,
                roles=principal.roles,
                permissions=principal.permissions,
                claims=principal.claims,
                firm_id=firm_id,
            ),
            category="all",
            page=1,
            page_size=20,
            entity_types={"customers"},
        )
        return sorted(item.title for item in page.results)

    assert _titles(None) == []
    assert _titles(firms[0].id) == ["Shared Name ALPHA"]
    assert _titles(firms[1].id) == ["Shared Name BETA"]


def _firm(session: Session, code: str) -> Firm:
    """Add one firm to search inside."""
    firm = Firm(
        name=f"Firm {code}",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _user(session: Session, email: str, name: str, *firms: Firm) -> User:
    """Add a user holding an active membership in each firm named."""
    actor = uuid4()
    user = User(
        email=email,
        full_name=name,
        password_hash="x",
        created_by=actor,
        updated_by=actor,
    )
    session.add(user)
    session.flush()
    for firm in firms:
        session.add(
            UserFirm(
                user_id=user.id,
                firm_id=firm.id,
                is_active=True,
                created_by=actor,
                updated_by=actor,
            )
        )
    session.commit()
    return user


def _search_titles(
    session: Session, principal: Principal, entity_type: str, query: str
) -> list[str]:
    page = SearchService(session).search(
        query=query,
        principal=principal,
        category="all",
        page=1,
        page_size=50,
        entity_types={entity_type},
    )
    return sorted(item.title for item in page.results)


def test_a_firm_caller_searches_only_the_firms_own_people(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl+K narrows people to the firm's members, as the users list does.

    The `users` definition had no firm column, so a firm administrator --
    every one holds `USER_VIEW` -- searched every user on the platform by name
    and email, where `GET /api/v1/users` narrows them to their own members
    (D-IDN-7). TEST01's administrator listed 37 people and searched 100
    (D-RPT-1).
    """
    session = _session_factory()()
    # A firm-scoped search reads `users` on the platform store; here that is
    # the one SQLite schema the test built.
    monkeypatch.setattr(
        search_service_module, "platform_reader", lambda: nullcontext(session)
    )
    ours, theirs = _firm(session, "OURS"), _firm(session, "THEIRS")
    _user(session, "asha@ours.example", "Asha Searchable", ours)
    _user(session, "bala@theirs.example", "Bala Searchable", theirs)
    _user(session, "chitra@both.example", "Chitra Searchable", ours, theirs)
    _user(session, "dev@platform.example", "Dev Searchable")
    left = _user(session, "esha@ours.example", "Esha Searchable", ours)
    session.execute(
        UserFirm.__table__.update()
        .where(UserFirm.user_id == left.id)
        .values(is_active=False)
    )
    session.commit()

    firm_admin = _principal(uuid4(), permissions={"USER_VIEW"}, firm_id=ours.id)
    assert _search_titles(session, firm_admin, "users", "Searchable") == [
        "Asha Searchable",
        "Chitra Searchable",
    ]

    # Without a firm in scope a firm caller is told nothing, as the users list
    # refuses them; naming a firm is what a person is entitled to ask about.
    unscoped = _principal(uuid4(), permissions={"USER_VIEW"})
    assert _search_titles(session, unscoped, "users", "Searchable") == []

    # A platform administrator acts platform-wide and still sees everyone.
    # The designation is its own claim, never a role name.
    admin_id = uuid4()
    platform = Principal(
        subject=admin_id,
        roles=frozenset(),
        permissions=frozenset({"USER_VIEW"}),
        claims=TokenClaims(
            sub=str(admin_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=[],
            permissions=["USER_VIEW"],
            platform_admin=True,
        ),
        firm_id=None,
    )
    assert len(_search_titles(session, platform, "users", "Searchable")) == 5


def test_storage_areas_are_searched_within_the_firm() -> None:
    """A shelf belongs to a warehouse, and the warehouse to a firm.

    `warehouse_storage_nodes` has no firm column and the definition declared
    none, so it was never narrowed: in the SHARED store MEDI01 searched
    FOOD01's three shelves beside its own, and the reverse (D-RPT-1).
    """
    session = _session_factory()()
    ours, theirs = _firm(session, "OURS"), _firm(session, "THEIRS")
    for firm in (ours, theirs):
        warehouse = Warehouse(
            firm_id=firm.id,
            branch_id=uuid4(),
            code="MAIN",
            name="Main",
            display_name="Main",
        )
        session.add(warehouse)
        session.flush()
        session.add(
            WarehouseStorageNode(
                warehouse_id=warehouse.id,
                node_type="BIN",
                code="A1",
                name=f"Bin A1 {firm.code}",
                path="A1",
            )
        )
    session.commit()

    ours_only = _principal(
        uuid4(), permissions={"STORAGE_AREA_MANAGE"}, firm_id=ours.id
    )
    assert _search_titles(session, ours_only, "storage_areas", "Bin A1") == [
        "Bin A1 OURS"
    ]
    nobody = _principal(uuid4(), permissions={"STORAGE_AREA_MANAGE"})
    assert _search_titles(session, nobody, "storage_areas", "Bin A1") == []


def test_a_territory_node_is_listed_once_under_the_label_it_earns() -> None:
    """A route is a node with a route profile; a territory is one without.

    `territories` and `routes` were two definitions over `SalesTerritoryNode`
    with the same filter, so every node was listed twice, once under each
    label -- WHOLE01's six nodes answered twelve hits (D-RPT-6).
    """
    session = _session_factory()()
    firm = _firm(session, "TERR")
    region = SalesTerritoryNode(
        firm_id=firm.id,
        hierarchy_level_id=uuid4(),
        code="N",
        name="North Zone",
        path="N",
    )
    route = SalesTerritoryNode(
        firm_id=firm.id,
        hierarchy_level_id=uuid4(),
        code="N-R1",
        name="North Beat",
        path="N/N-R1",
    )
    session.add_all([region, route])
    session.flush()
    session.add(TerritoryRouteProfile(territory_id=route.id))
    session.commit()

    principal = _principal(uuid4(), permissions={"TERRITORY_VIEW"}, firm_id=firm.id)
    hits = SearchService(session).search(
        query="North",
        principal=principal,
        category="organization",
        page=1,
        page_size=20,
        entity_types={"territories", "routes"},
    )
    assert sorted((item.entity_type, item.title) for item in hits.results) == [
        ("routes", "North Beat"),
        ("territories", "North Zone"),
    ]
