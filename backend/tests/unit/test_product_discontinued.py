"""Discontinued and not-for-sale products (STK-17, §75 row 5, decision A58).

A DISCONTINUED product is no longer bought but is sold until the stock is
gone: a purchase order refuses it and reorder planning leaves it out, while a
sales order takes it as it takes an ACTIVE one. A product marked *not for
sale* -- packing material, consumables -- is bought and stocked but never put
on a sales line, whatever its status.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.products.schemas.product import ProductCreate, ProductStatus
from app.purchase.services.purchase_service import PurchaseService
from app.purchase.services.reorder import ReorderService
from app.sales_order.models import SalesOrder
from app.sales_order.services import SalesOrderService
from tests.unit.test_reorder_suggestions import _Shop
from tests.unit.test_sales_order_module import (
    _branch,
    _customer,
    _firm,
    _order_for,
    _product,
    _session_factory,
    _warehouse,
)


def _setup(*, status: str = "ACTIVE", not_for_sale: bool = False) -> tuple:
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    product.status = status
    product.not_for_sale = not_for_sale
    session.commit()
    order = _order_for(
        customer_id=customer.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
    )
    return session, firm, product, order


def test_a_discontinued_product_is_still_sold() -> None:
    session, firm, _, order = _setup(status="DISCONTINUED")

    created = SalesOrderService(session).create_order(
        order, firm_id=firm.id, actor_id=uuid4()
    )

    assert created.id is not None


@pytest.mark.parametrize("status", ["ACTIVE", "DISCONTINUED"])
def test_a_product_not_for_sale_is_never_put_on_a_sales_line(status: str) -> None:
    session, firm, product, order = _setup(status=status, not_for_sale=True)

    with pytest.raises(ValidationError) as refused:
        SalesOrderService(session).create_order(
            order, firm_id=firm.id, actor_id=uuid4()
        )
    session.rollback()

    assert product.code in str(refused.value)
    assert "not for sale" in str(refused.value)
    assert session.scalar(select(SalesOrder.id)) is None


def test_a_discontinued_product_is_not_bought_again() -> None:
    session, firm, product, _ = _setup(status="DISCONTINUED")

    with pytest.raises(ValidationError, match="discontinued") as refused:
        PurchaseService(session)._active_product(firm.id, product.id)

    assert product.code in str(refused.value)


def test_a_product_not_for_sale_is_still_bought() -> None:
    session, firm, product, _ = _setup(not_for_sale=True)

    assert PurchaseService(session)._active_product(firm.id, product.id) is product


def test_reorder_planning_leaves_a_discontinued_product_out() -> None:
    shop = _Shop()
    shop.stock(shop.product, available="2", reorder="5", maximum="20")
    assert len(ReorderService(shop.session).below_reorder(shop.firm.id)) == 1

    shop.product.status = "DISCONTINUED"
    shop.session.commit()

    assert ReorderService(shop.session).below_reorder(shop.firm.id) == []


def test_the_product_form_takes_both() -> None:
    data = ProductCreate(
        code="BOX-10",
        name="Carton, 10 kg",
        product_type="STOCK_ITEM",
        status="DISCONTINUED",
        not_for_sale=True,
        selling_price=Decimal("0"),
    )

    assert data.status is ProductStatus.DISCONTINUED
    assert data.not_for_sale is True
