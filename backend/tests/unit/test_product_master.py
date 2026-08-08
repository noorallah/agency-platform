"""Product master service and API authorization tests."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import (
    AttributeDefinition,
    BusinessFeature,
    BusinessProfile,
    CategoryAttributeRule,
    ProfileFeature,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.products.api.router import (
    create_product,
    delete_product,
    get_product,
    list_products,
    product_scope,
    restore_product,
)
from app.products.schemas import (
    ProductAttributeInput,
    ProductCategoryCreate,
    ProductCreate,
)
from app.products.services import ProductService


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database for product tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def _seed_profile(session: Session, *, with_barcode_feature: bool) -> None:
    profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        default_settings={},
        created_by=uuid4(),
        updated_by=uuid4(),
    )
    session.add(profile)
    session.flush()
    if with_barcode_feature:
        feature = BusinessFeature(
            code="BARCODE",
            name="Barcode",
            default_enabled=False,
            is_active=True,
            created_by=uuid4(),
            updated_by=uuid4(),
        )
        session.add(feature)
        session.flush()
        session.add(
            ProfileFeature(
                business_profile_id=profile.id,
                feature_id=feature.id,
                is_enabled=True,
                created_by=uuid4(),
                updated_by=uuid4(),
            )
        )
    session.commit()


def _base_payload(code: str = "PROD-001") -> ProductCreate:
    return ProductCreate.model_validate(
        {
            "code": code,
            "name": "Pain Relief Tablet",
            "product_type": "STOCK_ITEM",
            "status": "ACTIVE",
            "selling_price": "120.00",
            "purchase_price": "95.00",
            "mrp": "130.00",
            "attributes": [],
            "media": [],
        }
    )


def test_product_service_enforces_category_attribute_rules() -> None:
    """Require category attributes from profile-driven category rules."""
    session = _session_factory()()
    firm = _firm(session, "MED")
    _seed_profile(session, with_barcode_feature=True)
    actor_id = uuid4()
    service = ProductService(session)
    category = service.create_category(
        data=ProductCategoryCreate(
            code="MEDICINE",
            name="Medicine",
            is_active=True,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    definition = AttributeDefinition(
        code="EXPIRY_DATE",
        name="Expiry Date",
        data_type="DATE",
        mandatory=True,
        is_active=True,
        applicable_category="MEDICINE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    profile_id = session.scalar(select(BusinessProfile.id))
    assert profile_id is not None
    session.add(definition)
    session.flush()
    session.add(
        CategoryAttributeRule(
            business_profile_id=profile_id,
            category_code="MEDICINE",
            attribute_definition_id=definition.id,
            is_mandatory=True,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    session.commit()

    missing = _base_payload()
    missing.category_id = category.id
    with pytest.raises(ValidationError, match="Required category attributes"):
        service.create_product(missing, firm_id=firm.id, actor_id=actor_id)

    valid = _base_payload("PROD-002")
    valid.category_id = category.id
    valid.attributes = [
        ProductAttributeInput(
            attribute_definition_id=definition.id,
            value=datetime(2028, 12, 31).date(),
        )
    ]
    created = service.create_product(valid, firm_id=firm.id, actor_id=actor_id)
    assert created.code == "PROD-002"
    assert created.category_attribute_values[0]["value_type"] == "date"
    assert created.category_attribute_values[0]["value"] == "2028-12-31"


def test_product_service_enforces_feature_gated_fields() -> None:
    """Reject feature-gated payload fields when profile disables them."""
    session = _session_factory()()
    firm = _firm(session, "NOBC")
    _seed_profile(session, with_barcode_feature=False)
    service = ProductService(session)

    payload = _base_payload()
    payload.barcode = "890100001"
    with pytest.raises(ValidationError, match="Barcode is disabled"):
        service.create_product(payload, firm_id=firm.id, actor_id=uuid4())


def test_product_api_applies_permissions_and_soft_delete_restore() -> None:
    """Enforce permission checks and support delete/restore lifecycle endpoints."""
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "API")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    _seed_profile(setup, with_barcode_feature=True)
    setup.close()

    permissions = {
        "PRODUCT_VIEW",
        "PRODUCT_CREATE",
        "PRODUCT_UPDATE",
        "PRODUCT_DELETE",
        "PRODUCT_RESTORE",
    }
    principal = _principal(user_id, permissions)
    session = factory()
    scope = product_scope(principal, session, firm.id)
    created = create_product(_base_payload(), scope, session)
    product_id = created.data.id

    listed = list_products(
        scope=scope,
        page=1,
        page_size=20,
        search="Pain",
        sort_by="created_at",
        sort_direction="desc",
        status_value=None,
        product_type=None,
        category_id=None,
        sub_category_id=None,
        brand=None,
        hsn_sac=None,
        attribute_query=None,
        include_deleted=False,
        db=session,
    )
    assert listed.pagination.total_records == 1

    delete_product(product_id, scope, session)
    restored = restore_product(product_id, scope, session)
    assert restored.data.is_deleted is False

    view_only = _principal(user_id, {"PRODUCT_VIEW"})
    with pytest.raises(AuthorizationError):
        require_permission("PRODUCT_CREATE")(view_only)


def test_product_cost_price_is_hidden_without_permission() -> None:
    """Hide cost fields from API responses when permission is missing."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "COST")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    _seed_profile(session, with_barcode_feature=True)

    creator_scope = product_scope(
        _principal(
            user_id, {"PRODUCT_VIEW", "PRODUCT_CREATE", "PRODUCT_VIEW_COST_PRICE"}
        ),
        session,
        firm.id,
    )
    created = create_product(_base_payload("PROD-COST"), creator_scope, session)
    viewer_scope = product_scope(
        _principal(user_id, {"PRODUCT_VIEW"}), session, firm.id
    )
    fetched = get_product(created.data.id, viewer_scope, False, session)
    assert fetched.data.purchase_price is None
    assert fetched.data.selling_price == Decimal("120.00")
