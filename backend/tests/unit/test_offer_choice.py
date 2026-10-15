"""The bill maker's choice on the order and the quotation (L7 step 5).

``docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md`` sections 1, 3.3 to 3.5 and
3.8, step 5 of section 6. A line may send ``offer_choice``: the arrangement
its discount comes from and the offers it takes, by key. The server prices
it, refuses what the line cannot take by name, treats a choice equal to the
start as no choice, asks for ``SALES_OFFER_CHOOSE`` and writes each real
choice to the audit trail. The test shop has no tax rule, so each line's
tax is nothing and its taxable value is what the worked example says.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models.audit_log import AuditLog
from app.core.exceptions import AuthorizationError, ValidationError
from app.pricing.models import PriceList
from app.promotions.models import Promotion
from app.promotions.schemas import (
    OfferChoice,
    PromotionActionType,
    PromotionConditionOperator,
    PromotionField,
)
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService
from app.sales_order.models import SalesOrderLine, SalesOrderOffer
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_offer_candidates import ON, _by_code, _shop
from tests.unit.test_promotions import _best_offer_only, _promotion, _Shop


def _key(shop: _Shop, code: str) -> str:
    """Return the key an offer or a price list is chosen by."""
    offer = shop.session.scalar(select(Promotion).where(Promotion.code == code))
    if offer is not None:
        return str(offer.version_group_id)
    listed = shop.session.scalar(select(PriceList).where(PriceList.code == code))
    assert listed is not None, code
    return str(listed.id)


def _line(
    number: int,
    shop: _Shop,
    quantity: str,
    choice: OfferChoice | None = None,
    *,
    discount_percent: str | None = None,
) -> SalesOrderLineWrite:
    """Describe one line of the shop's product at 100 a piece."""
    fields: dict[str, object] = {
        "line_number": number,
        "product_id": shop.product.id,
        "quantity": Decimal(quantity),
        "unit_price": Decimal("100"),
    }
    if discount_percent is not None:
        fields["discount_percent"] = Decimal(discount_percent)
    if choice is not None:
        fields["offer_choice"] = choice
    return SalesOrderLineWrite.model_validate(fields)


def _order(shop: _Shop, *lines: SalesOrderLineWrite) -> SalesOrderCreate:
    """Describe an order of the given lines."""
    return SalesOrderCreate(
        customer_id=shop.customer.id,
        branch_id=shop.branch.id,
        warehouse_id=shop.warehouse.id,
        order_date=ON,
        lines=list(lines),
    )


def _city_not_tea5(shop: _Shop) -> OfferChoice:
    """Step 3: untick TEA-5, take CITY for the discount, keep TEA-11."""
    return OfferChoice(discount_from=_key(shop, "CITY"), offers=[_key(shop, "TEA-11")])


def _save(
    shop: _Shop, data: SalesOrderCreate, *, may_choose: bool = True
) -> SalesOrderLine:
    """Save the order and return its first line."""
    row = SalesOrderService(shop.session).create_order(
        data, firm_id=shop.firm.id, actor_id=uuid4(), may_choose=may_choose
    )
    line = shop.session.scalar(
        select(SalesOrderLine)
        .where(SalesOrderLine.sales_order_id == row.id)
        .order_by(SalesOrderLine.line_number)
    )
    assert line is not None
    return line


def _rows(shop: _Shop, line: SalesOrderLine) -> dict[str, SalesOrderOffer]:
    """Return a saved line's rows by code."""
    return {
        row.code: row
        for row in shop.session.scalars(
            select(SalesOrderOffer).where(
                SalesOrderOffer.sales_order_line_id == line.id
            )
        )
    }


def test_step_3_takes_city_in_place_of_tea_5_to_the_paisa() -> None:
    """11 pieces, CITY chosen: 44.00 off, taxable 1,056.00, one free."""
    shop = _shop("CH01")
    data = _order(shop, _line(1, shop, "11", _city_not_tea5(shop)))

    preview = SalesOrderService(shop.session).preview_order(
        data, firm_id=shop.firm.id, actor_id=uuid4(), may_choose=True
    )
    shown = preview.order.lines[0]
    assert shown.discount_amount == Decimal("44.0000")
    assert shown.gross_amount - shown.discount_amount == Decimal("1056.0000")
    assert shown.free_quantity == Decimal("1.0000")
    assert shown.discount_source == "price_list"
    found = _by_code(preview.lines[0].candidates)
    assert (found["CITY"].applied, found["CITY"].chosen) == (True, True)
    assert (found["TEA-11"].applied, found["TEA-11"].chosen) == (True, True)
    assert (found["TEA-5"].applied, found["TEA-5"].chosen) == (False, False)
    assert found["TEA-5"].reason == "Not chosen on this line."
    assert preview.lines[0].choice_refused is None

    line = _save(shop, data)
    assert line.discount_amount == Decimal("44.0000")
    assert line.discount_percent == Decimal("4.0000")
    assert line.gross_amount - line.discount_amount == Decimal("1056.0000")
    assert line.tax_amount == Decimal("0.0000"), "the test shop charges no tax"
    assert line.offer_choice_made is True
    rows = _rows(shop, line)
    assert set(rows) == {"CITY", "TEA-11"}
    assert rows["CITY"].chosen and rows["TEA-11"].chosen
    assert rows["CITY"].discount_amount == Decimal("44.0000")


def test_a_real_choice_is_written_to_the_audit_trail() -> None:
    """The line, the start, what was taken and by whom."""
    shop = _shop("CH02")
    actor = uuid4()
    SalesOrderService(shop.session).create_order(
        _order(shop, _line(1, shop, "11", _city_not_tea5(shop))),
        firm_id=shop.firm.id,
        actor_id=actor,
        may_choose=True,
    )

    (event,) = shop.session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_order.offer_chosen")
    ).all()
    assert event.actor_id == actor
    after = event.after_data or {}
    assert after["line_number"] == 1
    assert after["start"] == ["TEA-5", "TEA-11"]
    assert after["taken"] == ["TEA-11", "CITY"]


def test_a_stale_key_is_refused_on_save_and_reported_on_preview() -> None:
    """9 pieces: TEA-11 is no candidate of the line once it is unrestricted."""
    shop = _shop("CH03")
    stale = str(uuid4())
    _promotion(
        shop.session,
        firm_id=shop.firm.id,
        code="TEA-9",
        priority=30,
        actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "1"})],
        conditions=[
            (
                PromotionField.LINE_QUANTITY,
                PromotionConditionOperator.GREATER_OR_EQUAL,
                {"value_number": Decimal("50")},
            )
        ],
    )
    choice = OfferChoice(offers=[_key(shop, "TEA-9")])
    data = _order(shop, _line(1, shop, "2"), _line(2, shop, "9", choice))

    with pytest.raises(ValidationError) as refused:
        _save(shop, data)
    assert refused.value.message == (
        "Line 2: offer TEA-9 does not apply to this line any more. Choose again."
    )
    shop.session.rollback()

    preview = SalesOrderService(shop.session).preview_order(
        data, firm_id=shop.firm.id, actor_id=uuid4(), may_choose=True
    )
    assert preview.lines[1].choice_refused == refused.value.message
    # Priced from the start: TEA-5's 5% of 900.
    assert preview.order.lines[1].discount_amount == Decimal("45.0000")
    assert preview.lines[0].choice_refused is None

    unknown = _order(shop, _line(1, shop, "9", OfferChoice(offers=[stale])))
    with pytest.raises(ValidationError, match="does not apply to this line"):
        _save(shop, unknown)


def test_a_second_offer_is_refused_under_best_one_only() -> None:
    """BEST_OFFER: one offer a line; two ticked is refused by name."""
    shop = _shop("CH04")
    _best_offer_only(shop.session, shop.firm.id)
    both = OfferChoice(offers=[_key(shop, "TEA-5"), _key(shop, "TEA-11")])

    with pytest.raises(ValidationError) as refused:
        _save(shop, _order(shop, _line(1, shop, "11", both)))
    assert "best one offer a line" in refused.value.message
    assert "TEA-5, TEA-11" in refused.value.message
    shop.session.rollback()

    # One in place of the start's: TEA-5 instead of TEA-11 (and its free piece).
    line = _save(
        shop,
        _order(shop, _line(1, shop, "11", OfferChoice(offers=[_key(shop, "TEA-5")]))),
    )
    assert line.discount_amount == Decimal("55.0000")
    assert line.free_quantity == Decimal("0.0000")
    assert line.offer_choice_made is True


def test_two_offers_ticked_under_ask_combine() -> None:
    """ASK starts at the best one; tick both and they combine on the line."""
    shop = _shop("CH05")
    _best_offer_only(shop.session, shop.firm.id, "ASK")

    start = _save(shop, _order(shop, _line(1, shop, "11")))
    assert start.free_quantity == Decimal("1.0000")
    assert start.discount_amount == Decimal("44.0000"), "TEA-11 alone, then CITY"

    both = OfferChoice(offers=[_key(shop, "TEA-5"), _key(shop, "TEA-11")])
    line = _save(shop, _order(shop, _line(1, shop, "11", both)))
    assert line.discount_amount == Decimal("55.0000")
    assert line.free_quantity == Decimal("1.0000")
    assert line.discount_source == "promotion"
    assert line.offer_choice_made is True
    rows = _rows(shop, line)
    assert rows["TEA-5"].chosen and rows["TEA-11"].chosen


def test_a_choice_equal_to_the_start_is_not_a_choice() -> None:
    """Sending back the offers the line took stores it as the server's."""
    shop = _shop("CH06")
    echo = OfferChoice(offers=[_key(shop, "TEA-5"), _key(shop, "TEA-11")])

    # Without the permission: an editor echoing the start is harmless.
    line = _save(shop, _order(shop, _line(1, shop, "11", echo)), may_choose=False)

    assert line.offer_choice_made is False
    assert line.discount_amount == Decimal("55.0000")
    assert not any(row.chosen for row in _rows(shop, line).values())
    assert (
        shop.session.scalar(
            select(AuditLog).where(AuditLog.action == "sales_order.offer_chosen")
        )
        is None
    )


def test_a_typed_figure_beside_a_choice_is_two_answers() -> None:
    """A discount typed, zero included, and a choice sent: refused."""
    shop = _shop("CH07")

    for typed in ("0", "3"):
        with pytest.raises(ValidationError, match="two answers on one line"):
            _save(
                shop,
                _order(
                    shop,
                    _line(1, shop, "11", _city_not_tea5(shop), discount_percent=typed),
                ),
            )
        shop.session.rollback()


def test_a_choice_without_the_permission_is_refused() -> None:
    """A real choice needs SALES_OFFER_CHOOSE, named in the refusal."""
    shop = _shop("CH08")

    with pytest.raises(AuthorizationError, match="SALES_OFFER_CHOOSE"):
        _save(
            shop,
            _order(shop, _line(1, shop, "11", _city_not_tea5(shop))),
            may_choose=False,
        )
    shop.session.rollback()

    preview = SalesOrderService(shop.session).preview_order(
        _order(shop, _line(1, shop, "11", _city_not_tea5(shop))),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    assert "SALES_OFFER_CHOOSE" in (preview.lines[0].choice_refused or "")
    assert preview.order.lines[0].discount_amount == Decimal("55.0000")


def test_an_offer_the_engine_does_not_reach_is_refused() -> None:
    """TEA-5 does not stack: ticked with TEA-11, TEA-11 is refused by name."""
    shop = _shop("CH09")
    tea5 = shop.session.scalar(select(Promotion).where(Promotion.code == "TEA-5"))
    assert tea5 is not None
    tea5.allow_stacking = False
    shop.session.commit()
    both = OfferChoice(offers=[_key(shop, "TEA-5"), _key(shop, "TEA-11")])

    with pytest.raises(ValidationError) as refused:
        _save(shop, _order(shop, _line(1, shop, "11", both)))
    assert refused.value.message == "Line 1: TEA-11 does not combine with TEA-5."
    shop.session.rollback()

    # Unticking TEA-5 lets TEA-11 through, with the price list's discount.
    line = _save(
        shop,
        _order(shop, _line(1, shop, "11", OfferChoice(offers=[_key(shop, "TEA-11")]))),
    )
    assert line.free_quantity == Decimal("1.0000")
    assert line.discount_amount == Decimal("44.0000")


def test_an_edit_that_leaves_the_choice_out_keeps_it_and_null_clears_it() -> None:
    """Absent on a line edit keeps the stored choice; null clears it."""
    shop = _shop("CH10")
    service = SalesOrderService(shop.session)
    row = service.create_order(
        _order(shop, _line(1, shop, "11", _city_not_tea5(shop))),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    kept = service.update_order(
        row.id,
        _order(shop, _line(1, shop, "11")),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    line = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == kept.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("44.0000")
    assert line.offer_choice_made is True

    cleared_line = _line(1, shop, "11")
    cleared_line = SalesOrderLineWrite.model_validate(
        {**cleared_line.model_dump(exclude_unset=True), "offer_choice": None}
    )
    service.update_order(
        row.id,
        _order(shop, cleared_line),
        firm_scope=shop.firm.id,
        actor_id=uuid4(),
    )
    shop.session.refresh(line)
    assert line.discount_amount == Decimal("55.0000")
    assert line.offer_choice_made is False


def test_best_one_only_is_judged_per_line() -> None:
    """Two lines, each takes the offer worth most on it (decision 2)."""
    shop = _shop("CH11")
    _best_offer_only(shop.session, shop.firm.id)

    preview = SalesOrderService(shop.session).preview_order(
        _order(shop, _line(1, shop, "11"), _line(2, shop, "9")),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )
    first, second = preview.order.lines[0], preview.order.lines[1]
    # Line 1: TEA-11's free piece (100.00) beats TEA-5 (55.00); CITY's 4%.
    assert (first.free_quantity, first.discount_amount) == (
        Decimal("1.0000"),
        Decimal("44.0000"),
    )
    # Line 2: TEA-11 gives nothing on 9, so TEA-5 is its best: 45.00.
    assert (second.free_quantity, second.discount_amount) == (
        Decimal("0.0000"),
        Decimal("45.0000"),
    )


def test_the_quotation_takes_the_choice_as_the_order_does() -> None:
    """Step 3 on a quotation: 44.00 off, chosen rows, an audit row."""
    shop = _shop("CH12")
    service = QuotationService(shop.session)

    row = service.create_quotation(
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
                    quantity=Decimal("11"),
                    unit_price=Decimal("100"),
                    offer_choice=_city_not_tea5(shop),
                )
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
        may_choose=True,
    )

    response = service.quotation_response(row)
    line = response.lines[0]
    assert line.discount_amount == Decimal("44.0000")
    assert line.gross_amount - line.discount_amount == Decimal("1056.0000")
    assert line.free_quantity == Decimal("1.0000")
    chosen = {item.code: item.chosen for item in line.offers}
    assert chosen == {"TEA-11": True, "CITY": True}
    assert shop.session.scalar(
        select(AuditLog).where(AuditLog.action == "quotation.offer_chosen")
    )

    with pytest.raises(AuthorizationError):
        service.create_quotation(
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
                        quantity=Decimal("11"),
                        unit_price=Decimal("100"),
                        offer_choice=_city_not_tea5(shop),
                    )
                ],
            ),
            firm_id=shop.firm.id,
            actor_id=uuid4(),
        )


def test_an_unknown_field_in_the_choice_is_refused() -> None:
    """Keys only: an amount sent in the choice fails the schema."""
    from pydantic import ValidationError as SchemaError

    with pytest.raises(SchemaError):
        OfferChoice.model_validate({"offers": [], "discount_amount": "10"})
