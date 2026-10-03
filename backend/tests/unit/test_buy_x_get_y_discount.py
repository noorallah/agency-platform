"""Offer: buy X, get Y at a discount (SEL-2, decision A94).

"Buy 1, get 1 at 50% off" on a line of 5 at 100 each: two complete pairs,
so two units at half price -- 100 off. A cap holds the offer to its limit
across the document, and the write refuses an offer missing its quantities.
"""

# ruff: noqa: D103

from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError

from app.promotions.schemas import PromotionActionType, PromotionActionWrite
from app.promotions.services import PromotionService
from tests.unit.test_promotions import (
    _firm,
    _product,
    _promotion,
    _request,
    _session_factory,
)

D = Decimal
HALF = {"buy_quantity": "1", "free_quantity": "1", "percent": "50"}


def test_every_complete_group_discounts_its_get_units() -> None:
    session = _session_factory()()
    firm = _firm(session)
    product = _product(session, firm_id=firm.id)
    _promotion(
        session,
        firm_id=firm.id,
        code="BOGOHALF",
        actions=[(PromotionActionType.BUY_X_GET_Y_DISCOUNT, HALF)],
    )
    service = PromotionService(session)
    five = service.evaluate(
        _request(lines=[(1, product.id, "5", "500")]), firm_scope=firm.id
    )
    assert five.lines[0].discount_amount == D("100.00"), "two pairs, a spare"
    one = service.evaluate(
        _request(lines=[(1, product.id, "1", "100")]), firm_scope=firm.id
    )
    assert one.lines[0].discount_amount == D("0"), "no complete pair"


def test_a_cap_holds_the_offer_across_the_document() -> None:
    session = _session_factory()()
    firm = _firm(session)
    first = _product(session, firm_id=firm.id)
    second = _product(session, firm_id=firm.id, code="SKU-002")
    _promotion(
        session,
        firm_id=firm.id,
        code="CAPPED",
        actions=[
            (PromotionActionType.BUY_X_GET_Y_DISCOUNT, {**HALF, "max_amount": "60"})
        ],
    )
    result = PromotionService(session).evaluate(
        _request(lines=[(1, first.id, "2", "200"), (2, second.id, "2", "200")]),
        firm_scope=firm.id,
    )
    assert sum(line.discount_amount for line in result.lines) == D("60.00")


def test_the_offer_needs_both_quantities_and_a_percent() -> None:
    with pytest.raises(SchemaError, match="buy 1, get 1 at 50%"):
        PromotionActionWrite(
            action_type=PromotionActionType.BUY_X_GET_Y_DISCOUNT, percent=D("50")
        )
    with pytest.raises(SchemaError, match="needs a percent"):
        PromotionActionWrite(
            action_type=PromotionActionType.BUY_X_GET_Y_DISCOUNT,
            buy_quantity=D("1"),
            free_quantity=D("1"),
        )
