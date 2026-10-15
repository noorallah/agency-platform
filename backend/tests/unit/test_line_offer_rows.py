"""What priced each sales line, named on the line (L7 step 2).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md``, section 3.9 and step 2 of
section 6. The engine answers what each offer gave each line; the order and
the quotation write a row per source; reads carry them. A line's APPLIED rows
add up to its ``discount_amount`` and its offers' free goods, and no price
moves.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customers.models import CustomerGroup
from app.pricing.models import PriceList, PriceListItem
from app.promotions.schemas import PromotionActionType
from app.quotation.models import SalesQuotationLine, SalesQuotationOffer
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_order.models import SalesOrder, SalesOrderOffer
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_promotions import (
    _line_cap,
    _promotion,
    _session_factory,
    _Shop,
)

ON = date(2026, 8, 4)


def _order(
    shop: _Shop,
    *,
    quantity: str = "4",
    discount_percent: str | None = None,
    order_id: UUID | None = None,
) -> SalesOrder:
    """Raise, or replace, one order of the shop's product at 250."""
    data = SalesOrderCreate(
        customer_id=shop.customer.id,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        order_date=ON,
        lines=[
            SalesOrderLineWrite(
                line_number=1,
                product_id=shop.product.id,
                quantity=Decimal(quantity),
                unit_price=Decimal("250"),
                discount_percent=(
                    None if discount_percent is None else Decimal(discount_percent)
                ),
            )
        ],
    )
    service = SalesOrderService(shop.session)
    if order_id is None:
        return service.create_order(data, firm_id=shop.firm.id, actor_id=uuid4())
    return service.update_order(
        order_id, data, firm_scope=shop.firm.id, actor_id=uuid4()
    )


def _rows(session: Session, order: SalesOrder) -> list[SalesOrderOffer]:
    """Return the order's rows, line by line in sequence."""
    return list(
        session.scalars(
            select(SalesOrderOffer)
            .where(SalesOrderOffer.sales_order_id == order.id)
            .order_by(SalesOrderOffer.sequence)
        )
    )


def _percent(shop: _Shop, code: str, percent: str, priority: int = 100) -> UUID:
    """Run one percentage offer and return its lasting identity."""
    row = _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code=code,
        priority=priority,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": percent})],
    )
    return row.version_group_id


def test_one_offer_is_one_row_worth_the_line_s_discount() -> None:
    """A 10% offer on 1000 names itself on the line for exactly 100."""
    session = _session_factory()()
    shop = _Shop(session, code="LO01")
    group_id = _percent(shop, "TEA-5", "10")

    order = _order(shop)
    line = shop.line_of(order)
    rows = _rows(session, order)

    assert len(rows) == 1
    (row,) = rows
    assert row.sales_order_line_id == line.id
    assert (row.source, row.code, row.state) == ("promotion", "TEA-5", "APPLIED")
    assert row.name == "Promotion TEA-5"
    assert row.promotion_group_id == group_id
    assert row.discount_amount == line.discount_amount == Decimal("100.0000")
    assert row.free_quantity == Decimal("0")
    assert row.chosen is False and row.part_share is False


def test_two_stacking_offers_add_up_in_the_order_applied() -> None:
    """10% then 15% of what is left: 100 and 135, which is the line's 235."""
    session = _session_factory()()
    shop = _Shop(session, code="LO02")
    _percent(shop, "TEN", "10", priority=10)
    _percent(shop, "FIFTEEN", "15", priority=20)

    order = _order(shop)
    line = shop.line_of(order)
    rows = _rows(session, order)

    assert [(row.sequence, row.code) for row in rows] == [(1, "TEN"), (2, "FIFTEEN")]
    assert [row.discount_amount for row in rows] == [
        Decimal("100.0000"),
        Decimal("135.0000"),
    ]
    assert sum(row.discount_amount for row in rows) == line.discount_amount


def test_a_line_cap_trims_the_rows_as_it_trims_the_line() -> None:
    """A 20% cap holds 235 at 200, taking the 35 off the last offer."""
    session = _session_factory()()
    shop = _Shop(session, code="LO03")
    _percent(shop, "TEN", "10", priority=10)
    _percent(shop, "FIFTEEN", "15", priority=20)
    _line_cap(session, shop.firm.id, "20")

    order = _order(shop)
    line = shop.line_of(order)
    rows = _rows(session, order)

    assert line.discount_amount == Decimal("200.0000")
    assert [row.discount_amount for row in rows] == [
        Decimal("100.0000"),
        Decimal("100.0000"),
    ]
    assert sum(row.discount_amount for row in rows) == line.discount_amount


def test_buy_n_get_m_free_names_the_offer_beside_its_free_goods() -> None:
    """Buy 2 get 1: four bought earn two free, and the row says whose."""
    session = _session_factory()()
    shop = _Shop(session, code="LO04")
    _promotion(
        session,
        firm_id=shop.firm.id,
        code="B2G1",
        actions=[
            (
                PromotionActionType.FREE_QUANTITY,
                {"buy_quantity": "2", "free_quantity": "1"},
            )
        ],
    )

    order = _order(shop)
    line = shop.line_of(order)
    (row,) = _rows(session, order)

    assert line.free_quantity == Decimal("2.0000")
    assert row.code == "B2G1"
    assert row.free_quantity == line.free_quantity
    assert row.discount_amount == line.discount_amount == Decimal("0")


def test_a_price_list_and_a_standing_rate_each_name_themselves() -> None:
    """The list that answered by its id and code; a shop's own rate as such."""
    session = _session_factory()()
    shop = _Shop(session, code="LO05")
    price_list = PriceList(
        firm_id=shop.firm.id,
        code="TRADE",
        name="Trade rates",
        effective_from=date(2026, 1, 1),
        status="ACTIVE",
    )
    session.add(price_list)
    session.flush()
    session.add(
        PriceListItem(
            price_list_id=price_list.id,
            firm_id=shop.firm.id,
            product_id=shop.product.id,
            min_quantity=Decimal("0"),
            discount_percent=Decimal("5"),
        )
    )
    session.commit()

    order = _order(shop)
    (row,) = _rows(session, order)
    assert (row.source, row.code, row.price_list_id) == (
        "price_list",
        "TRADE",
        price_list.id,
    )
    assert row.discount_amount == shop.line_of(order).discount_amount

    # Without the list, the shop's own standing rate answers.
    price_list.is_deleted = True
    shop.customer.default_discount_percent = Decimal("12")
    session.commit()
    order = _order(shop)
    (row,) = _rows(session, order)
    assert (row.source, row.code, row.name) == ("customer", "CUSTOMER", "Standing rate")
    assert row.discount_amount == Decimal("120.0000")


def test_a_segment_rate_names_the_segment() -> None:
    """The group's own code and name, read once for the document."""
    session = _session_factory()()
    shop = _Shop(session, code="LO05G")
    group = CustomerGroup(
        firm_id=shop.firm.id,
        code="WHOLESALE",
        name="Wholesalers",
        default_discount_percent=Decimal("5"),
    )
    session.add(group)
    session.commit()
    shop.customer.customer_group_id = group.id
    session.commit()

    (row,) = _rows(session, _order(shop))

    assert (row.source, row.code, row.name) == (
        "customer_group",
        "WHOLESALE",
        "Wholesalers",
    )
    assert row.discount_amount == Decimal("50.0000")


def test_a_typed_discount_names_no_arrangement() -> None:
    """A person deciding is not an arrangement, and beats the offer."""
    session = _session_factory()()
    shop = _Shop(session, code="LO06")
    _percent(shop, "TEN", "10")
    shop.customer.default_discount_percent = Decimal("12")
    session.commit()

    order = _order(shop, discount_percent="3")

    assert shop.line_of(order).discount_amount == Decimal("30.0000")
    assert _rows(session, order) == []


def test_saving_again_rewrites_the_rows_rather_than_adding_to_them() -> None:
    """A line's rows are rewritten each time it is priced."""
    session = _session_factory()()
    shop = _Shop(session, code="LO07")
    _percent(shop, "TEN", "10")

    order = _order(shop)
    order = _order(shop, quantity="8", order_id=order.id)
    rows = _rows(session, order)

    assert len(rows) == 1
    assert rows[0].discount_amount == Decimal("200.0000")


def test_the_quotation_writes_the_same_rows() -> None:
    """Two stacked offers on a quotation line, adding up as on the order."""
    session = _session_factory()()
    shop = _Shop(session, code="LO08")
    _percent(shop, "TEN", "10", priority=10)
    _percent(shop, "FIFTEEN", "15", priority=20)

    quotation = QuotationService(session).create_quotation(
        QuotationCreate(
            customer_id=shop.customer.id,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            quotation_date=ON,
            valid_until=date(2026, 9, 3),
            lines=[
                QuotationLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    line = session.scalar(
        select(SalesQuotationLine).where(
            SalesQuotationLine.sales_quotation_id == quotation.id
        )
    )
    assert line is not None
    rows = list(
        session.scalars(
            select(SalesQuotationOffer)
            .where(SalesQuotationOffer.sales_quotation_id == quotation.id)
            .order_by(SalesQuotationOffer.sequence)
        )
    )

    assert [row.code for row in rows] == ["TEN", "FIFTEEN"]
    assert {row.sales_quotation_line_id for row in rows} == {line.id}
    assert sum(row.discount_amount for row in rows) == line.discount_amount
    assert line.discount_amount == Decimal("235.0000")

    response = QuotationService(session).quotation_response(quotation)
    assert [offer.code for offer in response.lines[0].offers] == ["TEN", "FIFTEEN"]
    assert response.bill_offers == []


def test_the_order_s_response_carries_its_offers() -> None:
    """Read back on the line, by name, with what each took off."""
    session = _session_factory()()
    shop = _Shop(session, code="LO09")
    _percent(shop, "TEA-5", "10")

    order = _order(shop)
    response = SalesOrderService(session).order_response(order)

    (offer,) = response.lines[0].offers
    assert (offer.source, offer.code, offer.state) == (
        "promotion",
        "TEA-5",
        "APPLIED",
    )
    assert offer.discount_amount == Decimal("100.0000")
    assert offer.free_quantity == Decimal("0")
    assert response.bill_offers == []


def test_an_offer_on_the_whole_bill_is_a_row_with_no_line() -> None:
    """A bill discount is named on the document, not on a line."""
    session = _session_factory()()
    shop = _Shop(session, code="LO10")
    _promotion(
        session,
        firm_id=shop.firm.id,
        code="BILL5",
        actions=[(PromotionActionType.BILL_DISCOUNT_PERCENT, {"percent": "5"})],
    )

    order = _order(shop)
    (row,) = _rows(session, order)

    assert row.sales_order_line_id is None
    assert row.code == "BILL5"
    assert row.discount_amount == order.bill_discount_amount == Decimal("50.0000")
    response = SalesOrderService(session).order_response(order)
    assert [offer.code for offer in response.bill_offers] == ["BILL5"]
    assert response.lines[0].offers == []
