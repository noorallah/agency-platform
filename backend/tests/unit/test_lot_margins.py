"""Retail and wholesale margins on the goods type and the product (L3 step 1).

A goods type gives a new product its starting pair, as it gives an HSN code;
the product's own pair is never written over afterwards. The receipt line,
the lot and the price level only gain their columns in this step
(``docs/design/LOT_MARGINS_DESIGN.md``, section 6).
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.batch_serial.models import BatchRecord
from app.core.utils.dates import utc_now
from app.goods_receipt.models import GoodsReceiptLine
from app.pricing.models.price_level import PriceLevel
from app.pricing.schemas.price_level import PriceLevelResponse
from app.products.schemas import ProductUpdate
from app.products.schemas.goods_type import (
    GoodsTypeCreate,
    GoodsTypeUpdate,
    GoodsTypeUse,
)
from app.products.services import ProductService
from app.products.services.goods_types import GoodsTypeService
from tests.unit.test_goods_types import _by_code, _category, _product, _store
from tests.unit.test_product_master import _firm


def _margins(session: object, firm_id: object, code: str) -> object:
    """Take a shared type into use with a retail and a wholesale margin."""
    return GoodsTypeService(session).set_use(  # type: ignore[arg-type]
        _by_code(session, firm_id, code).id,  # type: ignore[arg-type]
        GoodsTypeUse(
            in_use=True,
            retail_margin_percent=Decimal("12"),
            wholesale_margin_percent=Decimal("6"),
        ),
        firm_id=firm_id,  # type: ignore[arg-type]
        actor_id=uuid4(),
    )


def test_the_type_hands_a_new_product_its_pair_where_none_is_given() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    fmcg = _margins(session, firm.id, "MEDICINE")
    assert (fmcg.retail_margin_percent, fmcg.wholesale_margin_percent) == (  # type: ignore[attr-defined]
        Decimal("12"),
        Decimal("6"),
    )
    shelf = _category(session, firm.id, "SHELF", goods_type_id=fmcg.id)  # type: ignore[attr-defined]

    filled = _product(session, firm.id, "P-1", category_id=shelf)
    own = _product(
        session,
        firm.id,
        "P-2",
        category_id=shelf,
        retail_margin_percent=Decimal("20"),
    )
    general = _product(session, firm.id, "P-3")

    assert (filled.retail_margin_percent, filled.wholesale_margin_percent) == (
        Decimal("12"),
        Decimal("6"),
    )
    # A margin given is the product's; the one left out still follows the type.
    assert (own.retail_margin_percent, own.wholesale_margin_percent) == (
        Decimal("20"),
        Decimal("6"),
    )
    assert (general.retail_margin_percent, general.wholesale_margin_percent) == (
        None,
        None,
    )
    option = next(
        row
        for row in ProductService(session)
        .metadata(firm_scope=firm.id, category_id=shelf)  # type: ignore[arg-type]
        .goods_types
        if row.code == "MEDICINE"
    )
    assert (option.retail_margin_percent, option.wholesale_margin_percent) == (
        Decimal("12"),
        Decimal("6"),
    )


def test_a_change_to_the_type_never_reaches_a_product_already_made() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    fmcg = _margins(session, firm.id, "MEDICINE")
    shelf = _category(session, firm.id, "SHELF", goods_type_id=fmcg.id)  # type: ignore[attr-defined]
    made = _product(session, firm.id, "P-1", category_id=shelf)

    changed = GoodsTypeService(session).set_use(
        fmcg.id,  # type: ignore[attr-defined]
        GoodsTypeUse(in_use=True, retail_margin_percent=Decimal("15")),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    # Left out is left alone: the wholesale margin stands.
    assert (changed.retail_margin_percent, changed.wholesale_margin_percent) == (
        Decimal("15"),
        Decimal("6"),
    )
    session.refresh(made)
    assert made.retail_margin_percent == Decimal("12")


def test_a_firms_own_type_carries_the_pair_from_creation() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    service = GoodsTypeService(session)
    soap = service.create(
        GoodsTypeCreate(
            code="SOAP",
            name="Soap",
            retail_margin_percent=Decimal("12.5"),
            wholesale_margin_percent=Decimal("6.25"),
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    assert (soap.retail_margin_percent, soap.wholesale_margin_percent) == (
        Decimal("12.5"),
        Decimal("6.25"),
    )

    cleared = service.update(
        soap.id,
        GoodsTypeUpdate(wholesale_margin_percent=None),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    # An explicit null clears; the retail margin was not mentioned.
    assert (cleared.retail_margin_percent, cleared.wholesale_margin_percent) == (
        Decimal("12.5"),
        None,
    )


def test_a_product_update_leaves_the_pair_alone_unless_it_names_it() -> None:
    session = _store()
    firm = _firm(session, "ONE")
    product = _product(
        session,
        firm.id,
        "P-1",
        retail_margin_percent=Decimal("10"),
        wholesale_margin_percent=Decimal("5"),
    )
    service = ProductService(session)

    renamed = service.update_product(
        product.id,
        ProductUpdate.model_validate(
            {"code": "P-1", "name": "Renamed", "product_type": "STOCK_ITEM"}
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert (renamed.retail_margin_percent, renamed.wholesale_margin_percent) == (
        Decimal("10"),
        Decimal("5"),
    )

    changed = service.update_product(
        product.id,
        ProductUpdate.model_validate(
            {
                "code": "P-1",
                "name": "Renamed",
                "product_type": "STOCK_ITEM",
                "retail_margin_percent": "18.75",
                "wholesale_margin_percent": None,
            }
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert (changed.retail_margin_percent, changed.wholesale_margin_percent) == (
        Decimal("18.75"),
        None,
    )

    copied = service.duplicate_product(product.id, firm_scope=firm.id, actor_id=uuid4())
    assert copied.retail_margin_percent == Decimal("18.75")


@pytest.mark.parametrize("value", ["-1", "1000", "12.34567"])
def test_a_margin_out_of_range_is_refused(value: str) -> None:
    with pytest.raises(PydanticValidationError):
        GoodsTypeUse(in_use=True, retail_margin_percent=Decimal(value))
    with pytest.raises(PydanticValidationError):
        ProductUpdate.model_validate(
            {
                "code": "P-1",
                "name": "P",
                "product_type": "STOCK_ITEM",
                "wholesale_margin_percent": value,
            }
        )


def test_the_receipt_line_the_lot_and_the_level_hold_their_new_columns() -> None:
    """Step 1 gives them the columns; steps 2 and 3 write them."""
    for model in (GoodsReceiptLine, BatchRecord):
        columns = model.__table__.columns
        assert "retail_margin_percent" in columns
        assert "wholesale_margin_percent" in columns
    assert "trade_class" in PriceLevel.__table__.columns
    level = PriceLevel(
        id=uuid4(),
        firm_id=uuid4(),
        code="DEALER",
        name="Dealer",
        sort_order=0,
        is_active=True,
        version=1,
    )
    level.created_at = level.updated_at = utc_now()
    assert PriceLevelResponse.model_validate(level).trade_class is None
