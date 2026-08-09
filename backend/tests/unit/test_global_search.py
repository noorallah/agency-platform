"""Enterprise global search service tests."""

import inspect
import re
from datetime import date
from pathlib import Path
from typing import get_args
from uuid import UUID, uuid4

import pytest
from fastapi import params
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
from app.sales.models import territory as _sales_models  # noqa: F401
from app.search.api.router import global_search
from app.search.services import SearchService
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
    }
    # KNOWN BUGS, not exemptions. Each of these resolves firms or memberships on
    # the request session, so the endpoints behind them fail with UndefinedTable
    # whenever the caller supplies X-Firm-ID for a firm outside the platform
    # schema — which the desktop client always does. Route each through
    # FirmMetadataReader or an explicit platform session, then delete its entry.
    known_bugs = {
        # GET/PUT /business-framework/firms/{id}/profile-assignment
        "app/business/services/framework_service.py",
        # Salesman assignment validates membership against user_firms.
        "app/sales/services/territory_service.py",
        # Product creation validates the owning firm exists.
        "app/products/services/product_service.py",
    }
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
