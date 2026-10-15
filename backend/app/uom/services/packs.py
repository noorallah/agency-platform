"""Which pack an item is typed in, and a total split into packs and loose.

L5, box and piece on one line (`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`,
3.1 and 3.2). A line typed as boxes and pieces is a line in the stock unit:
its quantity is the total in pieces and beside it the line keeps the pack
size it was written at. The boxes are the whole packs in that total and the
pieces what is over, worked out wherever they are shown and never stored,
so they cannot disagree with the quantity.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.products.models import Product
from app.uom.models import ConversionRule, Uom
from app.uom.services.uom_service import stock_unit_of

#: The side of the trade a document is on: a buying document reads the
#: item's purchase unit first, a selling one its sales unit.
PackSide = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Pack:
    """An item's pack on one side: its unit, its code and the stock units in it."""

    uom_id: UUID
    unit_code: str | None
    size: Decimal


@dataclass(frozen=True)
class PackedLine:
    """A line as `line_packs` reads it, where the written line cannot say.

    A line continuing another -- a delivery note's of its order line, a
    bill's of its note line -- names no product and may name no unit: both
    are its source's. The caller states them here, the unit as the line is
    counted in, so a line typed as boxes and pieces against a source in
    another unit is refused as any other is.
    """

    line_number: int
    product_id: UUID | None
    pack_size: Decimal | None
    sales_uom_id: UUID | None


@dataclass(frozen=True)
class BoxesAndPieces:
    """A total in stock units, as the whole packs in it and what is over.

    Boxes are always full boxes: 2 boxes + 17 of a box of 12 is 3 + 5, since
    only the total is kept (design 3.4, rule 3). The loose figure keeps the
    stock unit's own decimals -- 2 bags of 25 kg + 3.5 -- and is always less
    than one pack. A negative total splits with its sign on both figures.
    """

    packs: Decimal
    loose: Decimal
    pack_size: Decimal

    @classmethod
    def split(cls, total: Decimal, pack_size: Decimal) -> BoxesAndPieces:
        """Split ``total`` into the whole packs of ``pack_size`` and the rest."""
        _assert_pack_size(pack_size)
        packs = total // pack_size
        return cls(packs, total - packs * pack_size, pack_size)

    @classmethod
    def added_up(
        cls, packs: Decimal, loose: Decimal, pack_size: Decimal
    ) -> BoxesAndPieces:
        """Add two typed cells up and split the sum again into full packs.

        Raises:
            ValidationError: A cell is negative, or the packs are not a whole
                number.

        """
        _assert_pack_size(pack_size)
        if packs < 0 or loose < 0:
            raise ValidationError("Boxes and pieces cannot be negative.")
        if packs != packs.to_integral_value():
            raise ValidationError(f"Boxes are whole boxes, not {packs.normalize()}.")
        return cls.split(packs * pack_size + loose, pack_size)

    @property
    def total(self) -> Decimal:
        """Return the quantity in stock units the two figures hold."""
        return self.packs * self.pack_size + self.loose


def _assert_pack_size(pack_size: Decimal) -> None:
    """Refuse a pack size that is not a whole number above one."""
    if pack_size <= 1 or pack_size != pack_size.to_integral_value():
        raise ValidationError(
            f"A pack holds a whole number of units above one, not {pack_size}."
        )


def pack_unit_of(product: Product | None, side: PackSide) -> UUID | None:
    """Return the unit an item's pack is on one side, before its size is read.

    Buying reads the purchase unit where it is not the stock unit, else the
    sales unit; selling the other way about (design 3.2). None where neither
    differs from the stock unit.
    """
    if product is None:
        return None
    stock = stock_unit_of(product)
    first, second = (
        (product.purchase_uom_id, product.sales_uom_id)
        if side == "BUY"
        else (product.sales_uom_id, product.purchase_uom_id)
    )
    for unit in (first, second):
        if unit is not None and unit != stock:
            return unit
    return None


def packs_of_many(
    session: Session,
    products: Iterable[Product],
    *,
    side: PackSide,
    on_date: date,
) -> dict[UUID, Pack]:
    """Return each item's pack on one side on a date, read for a page at once.

    The pack size is the factor of the item's conversion rule from the pack's
    unit to its stock unit in force on ``on_date``, resolved as
    `UomService._resolve_conversion_rule` resolves it -- the item's own rule
    before the firm-wide one, then the latest version -- in one read of the
    rules and one of the unit codes. An item whose factor is not a whole
    number above one, or which no rule converts, has no pack and is absent:
    its lines show pieces only.
    """
    wanted: dict[UUID, tuple[Product, UUID, UUID]] = {}
    for product in products:
        unit = pack_unit_of(product, side)
        stock = stock_unit_of(product)
        if unit is not None and stock is not None:
            wanted[product.id] = (product, unit, stock)
    if not wanted:
        return {}
    rules = _rules_in_force(session, list(wanted.values()), on_date=on_date)
    sizes: dict[UUID, tuple[UUID, Decimal]] = {}
    for product_id, (product, unit, stock) in wanted.items():
        candidates = [
            rule
            for rule in rules
            if rule.firm_id == product.firm_id
            and rule.from_uom_id == unit
            and rule.to_uom_id == stock
            and rule.product_id in (product_id, None)
        ]
        if not candidates:
            continue
        chosen = min(
            candidates,
            key=lambda rule: (
                rule.product_id is None,
                -rule.version_number,
                -rule.created_at.timestamp(),
            ),
        )
        factor = Decimal(chosen.conversion_factor)
        if factor > 1 and factor == factor.to_integral_value():
            sizes[product_id] = (unit, Decimal(int(factor)))
    if not sizes:
        return {}
    codes = dict(
        session.execute(
            select(Uom.id, Uom.code).where(
                Uom.id.in_({unit for unit, _ in sizes.values()})
            )
        )
        .tuples()
        .all()
    )
    return {
        product_id: Pack(unit, codes.get(unit), size)
        for product_id, (unit, size) in sizes.items()
    }


def pack_of(
    session: Session, product: Product | None, *, side: PackSide, on_date: date
) -> Pack | None:
    """Return one item's pack on one side on a date, or None where it has none.

    The one answer for a single line; `packs_of_many` answers a page.
    """
    if product is None:
        return None
    return packs_of_many(session, [product], side=side, on_date=on_date).get(product.id)


def _rules_in_force(
    session: Session,
    wanted: Sequence[tuple[Product, UUID, UUID]],
    *,
    on_date: date,
) -> list[ConversionRule]:
    """Return every active rule that could convert a wanted pack, in one read."""
    firms = {product.firm_id for product, _, _ in wanted}
    return list(
        session.scalars(
            select(ConversionRule).where(
                ConversionRule.firm_id.in_(firms),
                ConversionRule.is_deleted.is_(False),
                ConversionRule.status == "ACTIVE",
                ConversionRule.from_uom_id.in_({unit for _, unit, _ in wanted}),
                ConversionRule.to_uom_id.in_({stock for _, _, stock in wanted}),
                ConversionRule.effective_from <= on_date,
                or_(
                    ConversionRule.effective_to.is_(None),
                    ConversionRule.effective_to >= on_date,
                ),
                or_(
                    ConversionRule.product_id.in_(
                        {product.id for product, _, _ in wanted}
                    ),
                    ConversionRule.product_id.is_(None),
                ),
            )
        )
    )


def line_packs(
    session: Session,
    lines: Sequence[BaseModel | PackedLine],
    *,
    side: PackSide,
    on_date: date,
    kept: Mapping[int, tuple[UUID, Pack]] | None = None,
) -> dict[int, Pack]:
    """Return the pack each typed line is written at, by line number.

    Design 3.3 and 3.4. ``kept`` is the pack a line already holds, by line
    number with the product it was held for: a saved draft line, or the
    source line a line continues. A line sent again for that product keeps
    it, so a draft saved at 12 to a box still reads 12 after the item moved
    to 10; any other line takes the item's pack on ``on_date``. A line of an
    item with no pack is absent.

    A line sending ``pack_size`` was typed as boxes and pieces. The server
    never takes the figure: it is refused where it differs from the pack the
    line is written at -- the item row the screen read went stale -- or
    where the line names a unit other than the stock unit, since such a line
    is counted in pieces.

    Raises:
        ValidationError: A sent ``pack_size`` is not the line's pack, or a
            line typed as boxes and pieces names another unit.

    """
    held = kept or {}
    product_ids = {getattr(line, "product_id", None) for line in lines} - {None}
    products = {
        product.id: product
        for product in session.scalars(
            select(Product).where(Product.id.in_(product_ids))
        )
    }
    fresh = packs_of_many(session, products.values(), side=side, on_date=on_date)
    packs: dict[int, Pack] = {}
    for line in lines:
        number = int(getattr(line, "line_number", 0))
        product_id: UUID | None = getattr(line, "product_id", None)
        product = None if product_id is None else products.get(product_id)
        saved = held.get(number)
        pack = (
            saved[1]
            if saved is not None and saved[0] == product_id
            else None if product is None else fresh.get(product.id)
        )
        sent: Decimal | None = getattr(line, "pack_size", None)
        if sent is not None:
            _assert_typed_at(
                number,
                sent=sent,
                pack=pack,
                unit=getattr(line, "sales_uom_id", None),
                stock=stock_unit_of(product),
            )
        if pack is not None:
            packs[number] = pack
    return packs


def _assert_typed_at(
    number: int,
    *,
    sent: Decimal,
    pack: Pack | None,
    unit: UUID | None,
    stock: UUID | None,
) -> None:
    """Refuse a line typed as boxes and pieces that the server reads otherwise."""
    if pack is None:
        raise ValidationError(
            f"Line {number}: this item has no box to type it in. "
            "Type the quantity in pieces."
        )
    if sent != pack.size:
        raise ValidationError(
            f"Line {number}: a box of this item holds {pack.size.normalize():f}, "
            f"not {sent.normalize():f}. Open the line again."
        )
    if unit is not None and unit != stock:
        raise ValidationError(
            f"Line {number} is typed in boxes and pieces, so it is counted in "
            "the item's stock unit, not in another unit."
        )


class _HeldLine(Protocol):
    """A saved or source line row, as `held_packs` reads it."""

    @property
    def line_number(self) -> int:
        """Return the line's number on its document."""

    @property
    def product_id(self) -> UUID:
        """Return the item on the line."""

    @property
    def pack_uom_id(self) -> UUID | None:
        """Return the pack's unit the line holds, if any."""

    @property
    def pack_size(self) -> Decimal | None:
        """Return the pack size the line holds, if any."""


def held_packs(rows: Iterable[_HeldLine]) -> dict[int, tuple[UUID, Pack]]:
    """Return the pack each saved or source line holds, keyed for `line_packs`.

    A row holding no pack is left out.
    """
    return {
        row.line_number: (row.product_id, Pack(row.pack_uom_id, None, row.pack_size))
        for row in rows
        if row.pack_uom_id is not None and row.pack_size is not None
    }


def printed_pack(
    *,
    in_boxes: bool,
    pack_size: Decimal | None,
    unit_id: UUID | None,
    product: Product | None,
) -> Decimal | None:
    """Return the pack a printed line states its quantity in, else None.

    A line prints as boxes and pieces only on a document saved in that layout
    (design section 4), only where it holds a pack, and only where its
    quantity is a count of the item's stock unit: a line typed in BOX keeps
    its pack too (decision 4), and "2 BOX" split by twelve would print
    nonsense. Any other line prints its plain quantity, as today.
    """
    if not in_boxes or pack_size is None or pack_size <= 1:
        return None
    stock = stock_unit_of(product)
    if unit_id is not None and stock is not None and unit_id != stock:
        return None
    return pack_size
