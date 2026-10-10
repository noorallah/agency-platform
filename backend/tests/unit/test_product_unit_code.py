"""A product says which unit it is sold in by name, not only by id.

D-UI-98 (2026-10-10): a sales line names a unit only when it was typed in a
unit other than the product's own, so the screens showing an ordinary line
have only the product to ask -- and a product carried its units as ids. The
Unit column of a quotation, a sales order and a bill read blank, and the
opened documents printed '-'. The product response now carries
``unit_code``, read for a whole page at once.
"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.products.api.router import _response, _responses
from app.products.models import Product
from app.products.services import ProductService
from app.uom.models import Uom
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session


def _unit(session: Session, code: str) -> Uom:
    """Add one unit of count."""
    unit = Uom(code=code, name=code.title(), dimension="COUNT", status="ACTIVE")
    session.add(unit)
    session.flush()
    return unit


def _product(setup: _Firm, code: str, **units: object) -> Product:
    """Add a product of the firm naming the given units."""
    product = Product(
        firm_id=setup.firm.id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        **units,
    )
    setup.session.add(product)
    setup.session.flush()
    return product


def test_the_selling_unit_is_named_then_the_stock_unit_then_the_base() -> None:
    """Each product answers with the first of the three it names."""
    setup = _Firm(_request_session())
    strip, box, piece = (_unit(setup.session, c) for c in ("STRIP", "BOX", "PIECE"))
    sold = _product(
        setup,
        "U-SOLD",
        sales_uom_id=strip.id,
        inventory_uom_id=box.id,
        base_uom_id=piece.id,
    )
    kept = _product(setup, "U-KEPT", inventory_uom_id=box.id, base_uom_id=piece.id)
    based = _product(setup, "U-BASE", base_uom_id=piece.id)
    setup.session.commit()

    codes = ProductService(setup.session).unit_codes_for_many(
        [sold, kept, based, setup.product]
    )

    assert codes == {sold.id: "STRIP", kept.id: "BOX", based.id: "PIECE"}
    # The firm's own product names no unit at all: absent, not blank.
    assert setup.product.id not in codes


def test_a_unit_id_nothing_answers_to_is_left_out() -> None:
    """A product pointing at a unit that is not there names nothing."""
    setup = _Firm(_request_session())
    lost = _product(setup, "U-LOST", sales_uom_id=uuid4())
    setup.session.commit()

    assert ProductService(setup.session).unit_codes_for_many([lost]) == {}


def test_the_response_carries_the_code_alone_and_on_a_page() -> None:
    """One product built alone reads as it does on a list page."""
    setup = _Firm(_request_session())
    strip = _unit(setup.session, "STRIP")
    sold = _product(setup, "U-SOLD", sales_uom_id=strip.id)
    setup.session.commit()

    alone = _response(sold, can_view_cost=True, db=setup.session)
    page = _responses([sold, setup.product], can_view_cost=True, db=setup.session)

    assert alone.unit_code == "STRIP"
    assert [row.unit_code for row in page] == ["STRIP", None]
    # The words typed on the product are a separate thing and stay as they are.
    assert alone.unit is None
