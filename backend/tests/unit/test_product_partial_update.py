"""A product update applies what the caller sent, and only that.

D-MST-5: ``_product_values`` dumped the whole write model and ``attributes``
and ``media`` were applied unconditionally, so a ``PUT`` naming a code, a name
and a type left a product with no category, no tax group, no units and no
price, and cleared its custom fields and images. A caller who cannot see the
cost price is served ``null`` and the form sends it back, which cleared that.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import AttributeDefinition, BusinessProfile
from app.common.scope import optional_firm_scope, required_firm_scope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.products.api.router import update_product
from app.products.models import Product
from app.products.schemas import ProductCategoryCreate, ProductCreate, ProductUpdate
from app.products.services import ProductService
from app.uom.models import Uom


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Add a firm and the default profile a product needs."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.add(
        BusinessProfile(
            code="GENERIC",
            name="Generic",
            industry_type="GENERIC",
            status="ACTIVE",
            is_default=True,
            default_settings={},
        )
    )
    session.commit()
    return firm


def _full_product(session: Session, firm: Firm) -> Product:
    """Create a product with every slot the defect cleared filled in."""
    service = ProductService(session)
    actor = uuid4()
    category = service.create_category(
        ProductCategoryCreate.model_validate({"code": "CAT", "name": "Category"}),
        firm_id=firm.id,
        actor_id=actor,
    )
    unit = Uom(code="PIECE", name="Piece", symbol="pc")
    definition = AttributeDefinition(
        code="SHELF", name="Shelf", entity_type="PRODUCT", data_type="TEXT"
    )
    session.add_all([unit, definition])
    session.commit()
    return service.create_product(
        ProductCreate.model_validate(
            {
                "code": "PPU-1",
                "name": "Whole product",
                "product_type": "STOCK_ITEM",
                "category_id": category.id,
                "base_uom_id": unit.id,
                "sales_uom_id": unit.id,
                "brand": "Acme",
                "hsn_sac": "1234",
                "purchase_price": "60",
                "selling_price": "100",
                "mrp": "120",
                "track_batch": True,
                "allow_decimal": False,
                "status": "INACTIVE",
                "attributes": [
                    {"attribute_definition_id": definition.id, "value": "A-12"}
                ],
                "media": [
                    {
                        "media_kind": "IMAGE",
                        "file_name": "front.png",
                        "mime_type": "image/png",
                        "storage_path": "products/front.png",
                        "is_primary": True,
                    }
                ],
            }
        ),
        firm_id=firm.id,
        actor_id=actor,
    )


def _three_fields(**more: object) -> ProductUpdate:
    """Build the smallest valid update, plus whatever the case names."""
    return ProductUpdate.model_validate(
        {"code": "PPU-1", "name": "Renamed", "product_type": "STOCK_ITEM", **more}
    )


def test_a_three_field_update_leaves_everything_else_alone() -> None:
    """Absent means leave alone, for the columns and both child collections."""
    session = _session()
    firm = _firm(session, "PPU1")
    product = _full_product(session, firm)
    service = ProductService(session)
    category_id, unit_id = product.category_id, product.base_uom_id
    assert category_id is not None and unit_id is not None

    updated = service.update_product(
        product.id, _three_fields(), firm_scope=firm.id, actor_id=uuid4()
    )

    assert updated.name == "Renamed"
    assert updated.category_id == category_id
    assert updated.base_uom_id == unit_id
    assert updated.sales_uom_id == unit_id
    assert updated.brand == "Acme"
    assert updated.hsn_sac == "1234"
    assert updated.purchase_price == Decimal("60")
    assert updated.selling_price == Decimal("100")
    assert updated.mrp == Decimal("120")
    assert updated.track_batch is True
    assert updated.allow_decimal is False
    assert updated.status == "INACTIVE"
    assert [row.value_text for row in service.attribute_responses(updated)] == ["A-12"]
    assert [row.file_name for row in updated.media if not row.is_deleted] == [
        "front.png"
    ]


def test_an_explicit_null_or_empty_list_still_clears() -> None:
    """Partial must not mean unclearable."""
    session = _session()
    firm = _firm(session, "PPU2")
    product = _full_product(session, firm)
    service = ProductService(session)

    updated = service.update_product(
        product.id,
        _three_fields(brand=None, category_id=None, attributes=[], media=[]),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert updated.brand is None
    assert updated.category_id is None
    assert updated.hsn_sac == "1234"
    assert service.attribute_responses(updated) == []
    assert [row for row in updated.media if not row.is_deleted] == []


def test_the_mrp_rule_holds_across_what_was_sent_and_what_is_stored() -> None:
    """A partial save of one price cannot cross the other on file."""
    session = _session()
    firm = _firm(session, "PPU3")
    product = _full_product(session, firm)
    service = ProductService(session)

    with pytest.raises(ValidationError, match="MRP"):
        service.update_product(
            product.id,
            _three_fields(selling_price="150"),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )
    session.rollback()
    with pytest.raises(ValidationError, match="MRP"):
        service.update_product(
            product.id, _three_fields(mrp="90"), firm_scope=firm.id, actor_id=uuid4()
        )
    session.rollback()
    raised = service.update_product(
        product.id,
        _three_fields(selling_price="110"),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert raised.selling_price == Decimal("110")


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    """Build a principal holding exactly these codes."""
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


def test_a_caller_who_cannot_see_the_cost_cannot_clear_it() -> None:
    """The form sends back the null it was served; the stored cost stays."""
    session = _session()
    firm = _firm(session, "PPU4")
    product = _full_product(session, firm)
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    def save(codes: set[str], **fields: object) -> Product:
        principal = _principal(user_id, codes)
        scope = required_firm_scope(
            optional_firm_scope(principal=principal, db=session, x_firm_id=firm.id)
        )
        update_product(
            product.id, _three_fields(**fields), scope, Response(), session, None
        )
        session.refresh(product)
        return product

    blind = {"PRODUCT_VIEW", "PRODUCT_UPDATE"}
    assert save(blind, purchase_price=None).purchase_price == Decimal("60")
    assert save(blind, purchase_price="1").purchase_price == Decimal("60")

    # Changing a price is also the pricing duty (D-MST-10).
    sighted = blind | {"PRODUCT_VIEW_COST_PRICE", "PRODUCT_PRICING_MANAGE"}
    assert save(sighted, purchase_price="75").purchase_price == Decimal("75")
    assert save(sighted, purchase_price=None).purchase_price is None
