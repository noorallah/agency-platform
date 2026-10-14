"""Which pack an item is typed in, and a total split into boxes and pieces.

L5 step 2 (`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.1 and 3.2): one
answer, `pack_of`, for the pack an item uses on the buying or the selling
side on a date, read from its dated conversion rule; a value object that
splits a total into full packs and loose and adds two cells up; and the item
rows the screens read answering the pack size, for a page at once.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.products.api.router import _response, _responses
from app.products.models import Product
from app.products.services import ProductService
from app.uom.models import ConversionRule, Uom
from app.uom.services import BoxesAndPieces, pack_of, packs_of_many
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

_LONG_AGO = date(2020, 1, 1)


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


def _rule(
    setup: _Firm,
    product: Product | None,
    from_unit: Uom,
    to_unit: Uom,
    factor: str,
    *,
    effective_from: date = _LONG_AGO,
    effective_to: date | None = None,
    version_number: int = 1,
) -> ConversionRule:
    """Add one active conversion rule, the item's own or the firm's."""
    rule = ConversionRule(
        firm_id=setup.firm.id,
        product_id=None if product is None else product.id,
        from_uom_id=from_unit.id,
        to_uom_id=to_unit.id,
        conversion_factor=Decimal(factor),
        effective_from=effective_from,
        effective_to=effective_to,
        version_number=version_number,
        status="ACTIVE",
    )
    setup.session.add(rule)
    setup.session.flush()
    return rule


class _Units:
    """A firm with a piece, a box, a case and a strip."""

    def __init__(self) -> None:
        """Build the firm and its four units."""
        self.setup = _Firm(_request_session())
        session = self.setup.session
        self.pcs, self.box, self.case, self.strip = (
            _unit(session, code) for code in ("PCS", "BOX", "CASE", "STRIP")
        )


def test_each_side_reads_its_own_unit_first() -> None:
    """Bought by the case of 24 and sold by the box of 12: two packs."""
    units = _Units()
    item = _product(
        units.setup,
        "P-TWO",
        inventory_uom_id=units.pcs.id,
        purchase_uom_id=units.case.id,
        sales_uom_id=units.box.id,
    )
    _rule(units.setup, item, units.box, units.pcs, "12")
    _rule(units.setup, item, units.case, units.pcs, "24")
    session = units.setup.session

    selling = pack_of(session, item, side="SELL", on_date=date(2026, 10, 15))
    buying = pack_of(session, item, side="BUY", on_date=date(2026, 10, 15))

    assert selling is not None and buying is not None
    assert (selling.unit_code, selling.size) == ("BOX", Decimal("12"))
    assert (buying.unit_code, buying.size) == ("CASE", Decimal("24"))


def test_a_side_with_no_unit_of_its_own_takes_the_other() -> None:
    """Sold by the box and bought in pieces: the box is the pack both ways."""
    units = _Units()
    item = _product(
        units.setup,
        "P-ONE",
        inventory_uom_id=units.pcs.id,
        purchase_uom_id=units.pcs.id,
        sales_uom_id=units.box.id,
    )
    # The firm-wide rule serves an item with none of its own.
    _rule(units.setup, None, units.box, units.pcs, "12")

    buying = pack_of(units.setup.session, item, side="BUY", on_date=date(2026, 10, 15))

    assert buying is not None and buying.size == Decimal("12")


def test_an_item_with_no_pack_has_none() -> None:
    """Pieces only, a fraction, a factor of one and no rule all answer None."""
    units = _Units()
    plain = _product(units.setup, "P-PLAIN", inventory_uom_id=units.pcs.id)
    half = _product(
        units.setup, "P-HALF", inventory_uom_id=units.pcs.id, sales_uom_id=units.box.id
    )
    _rule(units.setup, half, units.box, units.pcs, "12.5")
    single = _product(
        units.setup,
        "P-ONE-TO-ONE",
        inventory_uom_id=units.pcs.id,
        sales_uom_id=units.strip.id,
    )
    _rule(units.setup, single, units.strip, units.pcs, "1")
    unruled = _product(
        units.setup,
        "P-NORULE",
        inventory_uom_id=units.pcs.id,
        sales_uom_id=units.case.id,
    )

    found = packs_of_many(
        units.setup.session,
        [plain, half, single, unruled],
        side="SELL",
        on_date=date(2026, 10, 15),
    )

    assert found == {}
    assert pack_of(units.setup.session, None, side="SELL", on_date=_LONG_AGO) is None


def test_the_pack_is_the_one_in_force_on_the_date() -> None:
    """12 to a box until September, 10 after: each date reads its own."""
    units = _Units()
    item = _product(
        units.setup, "P-DATED", inventory_uom_id=units.pcs.id, sales_uom_id=units.box.id
    )
    _rule(
        units.setup,
        item,
        units.box,
        units.pcs,
        "12",
        effective_to=date(2026, 8, 31),
    )
    _rule(
        units.setup,
        item,
        units.box,
        units.pcs,
        "10",
        effective_from=date(2026, 9, 1),
        version_number=2,
    )
    # A firm-wide rule loses to the item's own whatever its version.
    _rule(units.setup, None, units.box, units.pcs, "6", version_number=9)
    session = units.setup.session

    before = pack_of(session, item, side="SELL", on_date=date(2026, 8, 31))
    after = pack_of(session, item, side="SELL", on_date=date(2026, 9, 1))

    assert before is not None and before.size == Decimal("12")
    assert after is not None and after.size == Decimal("10")


def test_a_total_splits_into_full_boxes_and_pieces() -> None:
    """41 of a box of 12 is 3 and 5; a decimal unit keeps its loose decimals."""
    split = BoxesAndPieces.split(Decimal("41"), Decimal("12"))
    bags = BoxesAndPieces.split(Decimal("53.5"), Decimal("25"))
    back = BoxesAndPieces.split(Decimal("-41"), Decimal("12"))

    assert (split.packs, split.loose, split.total) == (3, 5, 41)
    assert (bags.packs, bags.loose) == (2, Decimal("3.5"))
    assert (back.packs, back.loose, back.total) == (-3, -5, -41)


def test_two_cells_add_up_to_full_boxes() -> None:
    """2 boxes + 17 pieces is 3 + 5; a part box or a negative is refused."""
    typed = BoxesAndPieces.added_up(Decimal("2"), Decimal("17"), Decimal("12"))

    assert (typed.packs, typed.loose, typed.total) == (3, 5, 41)
    with pytest.raises(ValidationError, match="whole boxes"):
        BoxesAndPieces.added_up(Decimal("1.5"), Decimal("0"), Decimal("12"))
    with pytest.raises(ValidationError, match="negative"):
        BoxesAndPieces.added_up(Decimal("1"), Decimal("-1"), Decimal("12"))
    with pytest.raises(ValidationError, match="whole number"):
        BoxesAndPieces.split(Decimal("41"), Decimal("1"))


def test_the_item_row_answers_both_packs_alone_and_on_a_page() -> None:
    """The response carries each side's pack, the same built alone or listed."""
    units = _Units()
    item = _product(
        units.setup,
        "P-ROW",
        inventory_uom_id=units.pcs.id,
        purchase_uom_id=units.case.id,
        sales_uom_id=units.box.id,
    )
    _rule(units.setup, item, units.box, units.pcs, "12")
    _rule(units.setup, item, units.case, units.pcs, "24")
    session = units.setup.session
    session.commit()

    alone = _response(item, can_view_cost=True, db=session)
    page = _responses([item, units.setup.product], can_view_cost=True, db=session)

    assert (alone.pack_size, alone.pack_unit_code) == (Decimal("12"), "BOX")
    assert (alone.buying_pack_size, alone.buying_pack_unit_code) == (
        Decimal("24"),
        "CASE",
    )
    assert page[0] == alone
    assert (page[1].pack_size, page[1].buying_pack_size) == (None, None)


@contextmanager
def _statements(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []
    engine = session.get_bind()

    def record(*args: object) -> None:
        """Keep the statement text."""
        seen.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_the_packs_of_a_page_cost_the_same_at_two_rows_as_at_eight() -> None:
    """The packs are read once for a page, not once per item.

    The pack read alone: the page as a whole still loads each item's media
    and licence requirements row by row, which is older than the packs.
    """
    units = _Units()
    items = []
    for number in range(8):
        item = _product(
            units.setup,
            f"P-PAGE-{number}",
            inventory_uom_id=units.pcs.id,
            sales_uom_id=units.box.id,
        )
        _rule(units.setup, item, units.box, units.pcs, str(6 + number))
        items.append(item)
    session = units.setup.session
    session.commit()

    def count(rows: list[Product]) -> int:
        """Return the statements the packs of one page of ``rows`` cost."""
        with _statements(session) as seen:
            ProductService(session).packs_for_many(rows)
        return len(seen)

    assert count(items[:2]) == count(items)
    assert [
        row.pack_size for row in _responses(items, can_view_cost=True, db=session)
    ] == [Decimal(6 + number) for number in range(8)]
