"""Named price levels and special rates per customer (SEL-9, decision A89).

Detergent sells at 100. Dealers pay 90 and the Dealer group is on that level;
Anand, a dealer, has a list agreeing 80. A line with no price starts at the
most specific arrangement -- Anand's 80, another dealer's 90, a walk-in's 100
-- and a typed price beats all three.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.core.utils.pricing import resolve_unit_price
from app.customers.models import Customer, CustomerGroup
from app.pricing.api.price_levels_router import (
    create_price_level,
    delete_price_level,
    list_price_levels,
    update_price_level,
)
from app.pricing.models import PriceList, PriceListItem
from app.pricing.schemas.price_level import (
    PriceLevelWrite,
    ProductLevelRate,
    ProductLevelRatesWrite,
)
from app.pricing.services.price_levels import PriceLevelService
from app.pricing.services.unit_price import UnitPriceResolver
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.report_windows import report_scope
from tests.unit.test_sales_order_module import (
    _branch,
    _customer,
    _firm,
    _product,
    _session_factory,
    _warehouse,
)

D = Decimal
ON = date(2026, 8, 3)


def test_the_most_specific_arrangement_names_the_price() -> None:
    assert resolve_unit_price(
        product_price=D("100"), level_rate=D("90"), list_rate=D("80")
    ) == (resolve_unit_price(product_price=D("1"), list_rate=D("80")))
    assert resolve_unit_price(product_price=D("100"), level_rate=D("90")).source == (
        "PRICE_LEVEL"
    )
    found = resolve_unit_price(product_price=None)
    assert (found.price, found.source) == (D("0"), "PRODUCT")


def _priced_firm() -> tuple[Session, object, object, object, Customer, Customer]:
    """Build the firm of the module docstring."""
    session = _session_factory()()
    actor = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    product = _product(session, firm_id=firm.id)
    product.selling_price = D("100")
    levels = PriceLevelService(session)
    dealer = levels.create(
        PriceLevelWrite(code="dealer", name="Dealer"), firm_id=firm.id, actor_id=actor
    )
    levels.replace_product_rates(
        product.id,
        ProductLevelRatesWrite(
            rates=[ProductLevelRate(price_level_id=dealer.id, rate=D("90"))]
        ),
        firm_id=firm.id,
        actor_id=actor,
    )
    group = CustomerGroup(
        firm_id=firm.id, code="DEALERS", name="Dealers", price_level_id=dealer.id
    )
    session.add(group)
    session.flush()
    anand = _customer(session, firm_id=firm.id)
    anand.customer_group_id = group.id
    other = Customer(
        firm_id=firm.id,
        code="CUS-002",
        customer_type="RETAIL",
        name="Walk-in",
        display_name="Walk-in",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(other)
    price_list = PriceList(
        firm_id=firm.id,
        code="ANAND",
        name="Anand's rates",
        customer_id=anand.id,
        effective_from=date(2026, 4, 1),
    )
    session.add(price_list)
    session.flush()
    session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=firm.id,
            product_id=product.id,
            discount_percent=D("0"),
            rate=D("80"),
        )
    )
    session.commit()
    return session, firm, branch, warehouse, anand, other


def test_a_list_rate_beats_the_level_which_beats_the_product_price() -> None:
    session, firm, _, _, anand, walk_in = _priced_firm()
    item = session.scalar(select(PriceListItem))
    assert item is not None
    product = item.product_id

    def price_for(customer: Customer | None) -> tuple[Decimal, str]:
        found = UnitPriceResolver(
            session,
            firm_id=firm.id,  # type: ignore[attr-defined]
            customer_id=None if customer is None else customer.id,
            territory_id=None,
            on=ON,
        ).price(product)
        return found.price, found.source

    assert price_for(anand) == (D("80"), "PRICE_LIST")
    session.query(PriceListItem).update({"rate": None})
    session.commit()
    assert price_for(anand) == (D("90"), "PRICE_LEVEL"), "the group's level"
    assert price_for(walk_in) == (D("100"), "PRODUCT")


def test_an_order_line_with_no_price_takes_the_customers_and_a_typed_one_stands() -> (
    None
):
    session, firm, branch, warehouse, anand, _ = _priced_firm()
    item = session.scalar(select(PriceListItem))
    assert item is not None
    product = item.product_id
    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=anand.id,
            branch_id=branch.id,  # type: ignore[attr-defined]
            warehouse_id=warehouse.id,  # type: ignore[attr-defined]
            order_date=ON,
            lines=[
                SalesOrderLineWrite(line_number=1, product_id=product, quantity=D("2")),
                SalesOrderLineWrite(
                    line_number=2,
                    product_id=product,
                    quantity=D("1"),
                    unit_price=D("75"),
                ),
            ],
        ),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=uuid4(),
    )
    prices = sorted(
        (line.line_number, line.unit_price)
        for line in SalesOrderService(session).order_response(order).lines
    )
    assert prices == [(1, D("80.0000")), (2, D("75.0000"))]


def test_a_level_still_held_cannot_be_retired() -> None:
    session, firm, _, _, _, _ = _priced_firm()
    levels = PriceLevelService(session)
    [dealer] = levels.list_levels(firm.id)  # type: ignore[attr-defined]
    assert dealer.code == "DEALER"
    with pytest.raises(ConflictError, match="Move them to another level"):
        levels.delete(dealer.id, firm_id=firm.id, actor_id=uuid4())  # type: ignore[attr-defined]


def test_a_price_level_publishes_its_version_and_refuses_a_stale_one() -> None:
    """D-PRC-13: `If-Match: "99"` was answered 200, and no route gave an ETag.

    Driven through the route functions on a session that does not flush on a
    read, as a request's does not.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()
    scope = report_scope(uuid4())

    answer = Response()
    created = create_price_level(
        PriceLevelWrite(code="dealer", name="Dealer"),
        scope,
        response=answer,
        db=session,
    ).data
    assert created is not None
    assert answer.headers["ETag"] == f'"{created.version}"'

    with pytest.raises(ConflictError, match="changed since you loaded it"):
        update_price_level(
            created.id,
            PriceLevelWrite(code="DEALER", name="Dealers"),
            scope,
            response=Response(),
            expected_version=99,
            db=session,
        )

    answer = Response()
    updated = update_price_level(
        created.id,
        PriceLevelWrite(code="DEALER", name="Dealers"),
        scope,
        response=answer,
        expected_version=created.version,
        db=session,
    ).data
    assert updated is not None
    assert (updated.name, updated.version) == ("Dealers", created.version + 1)
    assert answer.headers["ETag"] == f'"{updated.version}"'
    [listed] = list_price_levels(scope, db=session).data or []
    assert listed.version == updated.version, "a list row carries what to send back"

    with pytest.raises(ConflictError, match="changed since you loaded it"):
        delete_price_level(
            created.id, scope, expected_version=created.version, db=session
        )
    # Sending nothing is still taken: the precondition is opt-in.
    delete_price_level(created.id, scope, expected_version=None, db=session)
    assert list_price_levels(scope, db=session).data == []
