"""Offer: a combo price for a set bought together (SEL-3, decision A96).

Shampoo at 100 and conditioner at 50 sell as a pair for 120. Two pairs and a
spare shampoo on the document: two complete sets, so 30 x 2 = 60 off, spread
over the lines by the value the sets used -- 40 off the shampoo line, 20 off
the conditioner -- so each keeps its own tax. A partial set saves nothing,
and a combo dearer than its parts saves nothing.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

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


def _combo(session: object, firm_id: object, a: object, b: object, price: str) -> None:
    _promotion(
        session,  # type: ignore[arg-type]
        firm_id=firm_id,  # type: ignore[arg-type]
        code="PAIR",
        actions=[
            (
                PromotionActionType.COMBO_PRICE,
                {
                    "price": price,
                    "items": [
                        {"product_id": str(a), "quantity": "1"},
                        {"product_id": str(b), "quantity": "1"},
                    ],
                },
            )
        ],
    )


def test_complete_sets_take_the_saving_spread_by_value() -> None:
    session = _session_factory()()
    firm = _firm(session)
    shampoo = _product(session, firm_id=firm.id)
    conditioner = _product(session, firm_id=firm.id, code="SKU-002")
    _combo(session, firm.id, shampoo.id, conditioner.id, "120")
    service = PromotionService(session)

    result = service.evaluate(
        _request(lines=[(1, shampoo.id, "3", "300"), (2, conditioner.id, "2", "100")]),
        firm_scope=firm.id,
    )
    off = {line.line_number: line.discount_amount for line in result.lines}
    assert off == {1: D("40.00"), 2: D("20.00")}

    partial = service.evaluate(
        _request(lines=[(1, shampoo.id, "3", "300")]), firm_scope=firm.id
    )
    assert partial.lines[0].discount_amount == D("0")


def test_a_combo_dearer_than_its_parts_saves_nothing() -> None:
    session = _session_factory()()
    firm = _firm(session)
    a = _product(session, firm_id=firm.id)
    b = _product(session, firm_id=firm.id, code="SKU-002")
    _combo(session, firm.id, a.id, b.id, "500")
    result = PromotionService(session).evaluate(
        _request(lines=[(1, a.id, "1", "100"), (2, b.id, "1", "50")]),
        firm_scope=firm.id,
    )
    assert all(line.discount_amount == D("0") for line in result.lines)


def test_a_combo_names_two_or_more_products_once_each() -> None:
    one = uuid4()
    with pytest.raises(SchemaError, match="two or more products"):
        PromotionActionWrite(
            action_type=PromotionActionType.COMBO_PRICE,
            amount=D("100"),
            combo_items=[{"product_id": one, "quantity": D("1")}],
        )
    with pytest.raises(SchemaError, match="each product of a combo once"):
        PromotionActionWrite(
            action_type=PromotionActionType.COMBO_PRICE,
            amount=D("100"),
            combo_items=[
                {"product_id": one, "quantity": D("1")},
                {"product_id": one, "quantity": D("2")},
            ],
        )
