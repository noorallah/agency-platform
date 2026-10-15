"""Offers a person's choice passed over, kept as REFUSED rows (L7 step 9).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` sections 3.9 and 5. Where a
real choice drops an arrangement the start applied, the line keeps a REFUSED
row of it, holding what it would have given. Only the APPLIED rows add up to
the line; a line with no choice keeps none; the choice read back is the same.
"""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.promotions.schemas import OfferChoice
from app.promotions.services.line_offers import OfferRow
from app.promotions.services.offer_choice import SettledChoice
from app.sales_order.models import SalesOrderLine, SalesOrderOffer
from app.sales_order.services import SalesOrderService
from tests.unit.test_offer_candidates import _shop
from tests.unit.test_offer_choice import (
    _city_not_tea5,
    _key,
    _line,
    _order,
    _save,
)
from tests.unit.test_promotions import _Shop


def _states(shop: _Shop, line: SalesOrderLine) -> list[tuple[str, str]]:
    """Return a saved line's rows as (code, state), in sequence."""
    return [
        (row.code, row.state)
        for row in shop.session.scalars(
            select(SalesOrderOffer)
            .where(SalesOrderOffer.sales_order_line_id == line.id)
            .order_by(SalesOrderOffer.sequence)
        )
    ]


def _refused(shop: _Shop, line: SalesOrderLine) -> list[SalesOrderOffer]:
    """Return a saved line's REFUSED rows."""
    return list(
        shop.session.scalars(
            select(SalesOrderOffer).where(
                SalesOrderOffer.sales_order_line_id == line.id,
                SalesOrderOffer.state == "REFUSED",
            )
        )
    )


def test_a_choice_that_drops_the_starts_offer_keeps_it_as_refused() -> None:
    """CITY in place of TEA-5: TEA-5 stays as REFUSED, worth its 55.00."""
    shop = _shop("PO01")
    line = _save(shop, _order(shop, _line(1, shop, "11", _city_not_tea5(shop))))

    assert _states(shop, line) == [
        ("TEA-11", "APPLIED"),
        ("CITY", "APPLIED"),
        ("TEA-5", "REFUSED"),
    ]
    (passed,) = _refused(shop, line)
    assert passed.discount_amount == Decimal("55.0000")
    assert passed.free_quantity == Decimal("0")
    assert passed.chosen is False
    assert passed.part_share is False
    applied = [
        row
        for row in shop.session.scalars(
            select(SalesOrderOffer).where(
                SalesOrderOffer.sales_order_line_id == line.id,
                SalesOrderOffer.state == "APPLIED",
            )
        )
    ]
    # The invariant: the APPLIED rows add up to the line.
    assert sum((row.discount_amount for row in applied), Decimal("0")) == (
        line.discount_amount
    )


def test_a_passed_over_offer_keeps_the_free_goods_it_would_have_given() -> None:
    """TEA-5 alone: TEA-11's one free piece is kept on a REFUSED row."""
    shop = _shop("PO02")
    choice = OfferChoice(offers=[_key(shop, "TEA-5")])
    line = _save(shop, _order(shop, _line(1, shop, "11", choice)))

    assert line.offer_choice_made is True
    (passed,) = _refused(shop, line)
    assert passed.code == "TEA-11"
    assert passed.free_quantity == Decimal("1.0000")
    assert passed.discount_amount == Decimal("0")


def test_a_line_with_no_choice_keeps_no_refused_row() -> None:
    """The start alone: every row is APPLIED."""
    shop = _shop("PO03")
    line = _save(shop, _order(shop, _line(1, shop, "11")))

    assert line.offer_choice_made is False
    assert _refused(shop, line) == []
    assert {state for _, state in _states(shop, line)} == {"APPLIED"}


def test_an_edit_that_omits_the_choice_reads_back_the_same_choice() -> None:
    """The REFUSED row is not read as part of the stored choice."""
    shop = _shop("PO04")
    service = SalesOrderService(shop.session)
    row = service.create_order(
        _order(shop, _line(1, shop, "11", _city_not_tea5(shop))),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == row.id)
    )
    assert line is not None
    held = service.choices_of_lines([line])[line.id]
    assert held.discount_from == _key(shop, "CITY")
    assert held.offers == [_key(shop, "TEA-11")]

    service.update_order(
        row.id,
        _order(shop, _line(1, shop, "11")),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == row.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("44.0000")
    assert service.choices_of_lines([line])[line.id] == held
    assert [(code, state) for code, state in _states(shop, line)][-1] == (
        "TEA-5",
        "REFUSED",
    )


def test_a_passed_over_rows_free_goods_are_in_stock_units() -> None:
    """On a box of twelve, one free box is kept as twelve stock units."""
    settled = SettledChoice(
        discount_from=None,
        offers=frozenset(),
        start=("TEA-11",),
        taken=(),
        passed_over=(
            OfferRow(
                source="promotion",
                code="TEA-11",
                name="Eleven plus one",
                free_quantity=Decimal("1"),
                promotion_group_id=uuid4(),
            ),
        ),
    )

    (row,) = settled.mark_rows([], stock_factor=Decimal("12"))

    assert row.state == "REFUSED"
    assert row.free_quantity == Decimal("12.0000")
    assert row.chosen is False
