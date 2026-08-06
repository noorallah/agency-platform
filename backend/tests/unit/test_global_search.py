"""Enterprise global search service tests."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import BusinessProfile
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import Permission, Role, User
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import product as _product_models  # noqa: F401
from app.sales.models import territory as _sales_models  # noqa: F401
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
