"""Supplier rates fill the purchase order line (BUY-3, decision A97).

A supplier takes 5% off everything; its price list fixes widgets at 80 and
gives 10% on them. A line with no price or discount of its own starts at the
list's 80 and 10%; a product the list does not name takes the product's
purchase price and the supplier's 5%; a typed zero discount refuses both. A
supplier's list never prices a sale.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.pricing.models import PriceList, PriceListItem
from app.pricing.services.price_list_service import PriceListResolver
from app.products.models import Product
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm on a fresh in-memory store."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="SUPRT")


def _second_product(firm: _Firm) -> Product:
    product = Product(
        firm_id=firm.firm.id,
        code="SKU-OTHER",
        name="Other",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        purchase_price=D("40"),
    )
    firm.session.add(product)
    firm.session.commit()
    return product


def _supplier_terms(firm: _Firm) -> None:
    firm.vendor.standing_discount_percent = D("5")
    price_list = PriceList(
        firm_id=firm.firm.id,
        code="SUP-LIST",
        name="Supplier list",
        vendor_id=firm.vendor.id,
        effective_from=date(2026, 4, 1),
    )
    firm.session.add(price_list)
    firm.session.flush()
    firm.session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=firm.firm.id,
            product_id=firm.product.id,
            discount_percent=D("10"),
            rate=D("80"),
        )
    )
    firm.session.commit()


def _lines(firm: _Firm, lines: list[dict[str, object]]) -> list[PurchaseOrderLine]:
    order = PurchaseService(firm.session).create_order(
        PurchaseOrderCreate.model_validate(
            {
                "branch_id": firm.branch.id,
                "warehouse_id": firm.warehouse.id,
                "vendor_id": firm.vendor.id,
                "purchase_date": "2026-08-02",
                "lines": lines,
            }
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    return list(
        firm.session.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.line_number)
        ).all()
    )


def test_blank_lines_take_the_suppliers_terms(firm: _Firm) -> None:
    _supplier_terms(firm)
    other = _second_product(firm)
    listed, unlisted = _lines(
        firm,
        [
            {"product_id": firm.product.id, "ordered_quantity": "10"},
            {"product_id": other.id, "ordered_quantity": "10"},
        ],
    )
    assert (listed.unit_price, listed.discount_percent) == (D("80"), D("10"))
    assert listed.discount_amount == D("80.00")
    assert (unlisted.unit_price, unlisted.discount_percent) == (D("40"), D("5"))


def test_typed_values_stand(firm: _Firm) -> None:
    _supplier_terms(firm)
    [line] = _lines(
        firm,
        [
            {
                "product_id": firm.product.id,
                "ordered_quantity": "10",
                "unit_price": "75",
                "discount_percent": "0",
            }
        ],
    )
    assert (line.unit_price, line.discount_percent) == (D("75"), D("0"))
    assert line.discount_amount == D("0")


def test_a_suppliers_list_never_prices_a_sale(firm: _Firm) -> None:
    _supplier_terms(firm)
    resolver = PriceListResolver(
        firm.session,
        firm_id=firm.firm.id,
        customer_id=None,
        territory_id=None,
        on=date(2026, 8, 2),
    )
    assert resolver.price_for(firm.product.id) is None
    assert resolver.rate_for(firm.product.id) is None
