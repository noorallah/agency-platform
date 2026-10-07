"""A shelf life on the product fills each batch's expiry (STK-18, decision A59).

A receipt typed with only the manufacturing date off the carton gets its
expiry from the product's shelf life, and the batch it creates keeps all
three. A typed expiry always stands, and a product with no shelf life fills
nothing.
"""

# ruff: noqa: D103

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.batch_serial.services.batch_serial_service import expiry_from_shelf_life
from app.goods_receipt.models import GoodsReceiptLine
from app.goods_receipt.services import GoodsReceiptService
from app.products.schemas.product import ProductCreate
from tests.unit.test_goods_receipt import _Fixture, _session_factory

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _receive(fixture: _Fixture, **line: object) -> object:
    payload = fixture.receipt_payload("4")
    data = payload.model_dump()
    data["lines"][0].update(line)
    return GoodsReceiptService(fixture.session).create_receipt(
        type(payload).model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _track(fixture: _Fixture, *switches: str) -> None:
    """Switch tracking on for the fixture's product.

    The product's own switches decide what its batch carries, never the
    firm's profile (backlog 89).
    """
    for switch in switches:
        setattr(fixture.product, switch, True)
    fixture.session.commit()


def _line(fixture: _Fixture, receipt: object) -> GoodsReceiptLine:
    line = fixture.session.scalar(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.goods_receipt_id == receipt.id  # type: ignore[attr-defined]
        )
    )
    assert line is not None
    return line


@pytest.mark.parametrize(
    ("made", "days", "expected"),
    [
        (date(2026, 8, 1), 180, date(2027, 1, 28)),
        (date(2026, 8, 1), None, None),
        (None, 180, None),
    ],
)
def test_the_expiry_is_the_manufacturing_date_plus_the_shelf_life(
    made: date | None, days: int | None, expected: date | None
) -> None:
    assert expiry_from_shelf_life(made, days) == expected


def test_a_receipt_with_only_a_manufacturing_date_gets_its_expiry() -> None:
    fixture = _Fixture(_session_factory()(), "SHL1")
    _track(fixture, "track_expiry", "track_manufacturing_date")
    fixture.product.shelf_life_days = 180
    fixture.session.commit()

    receipt = _receive(
        fixture, batch_number="B-801", manufacturing_date=date(2026, 8, 1)
    )

    line = _line(fixture, receipt)
    assert line.expiry_date == date(2027, 1, 28)

    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id,  # type: ignore[attr-defined]
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    batch = fixture.session.scalar(
        select(BatchRecord).where(BatchRecord.batch_number == "B-801")
    )
    assert batch is not None
    assert (batch.manufacturing_date, batch.expiry_date, batch.shelf_life_days) == (
        date(2026, 8, 1),
        date(2027, 1, 28),
        180,
    )


def test_a_typed_expiry_stands() -> None:
    fixture = _Fixture(_session_factory()(), "SHL2")
    _track(fixture, "track_expiry")
    fixture.product.shelf_life_days = 180
    fixture.session.commit()

    receipt = _receive(
        fixture,
        batch_number="B-802",
        manufacturing_date=date(2026, 8, 1),
        expiry_date=date(2026, 12, 31),
    )

    line = _line(fixture, receipt)
    assert line.expiry_date == date(2026, 12, 31)


def test_a_product_with_no_shelf_life_fills_nothing() -> None:
    fixture = _Fixture(_session_factory()(), "SHL3")
    _track(fixture, "track_expiry")

    receipt = _receive(
        fixture, batch_number="B-803", manufacturing_date=date(2026, 8, 1)
    )

    line = _line(fixture, receipt)
    assert line.expiry_date is None


def test_a_product_that_does_not_track_expiry_gets_none_filled() -> None:
    """Filling an expiry its batch would then be refused would stop the receipt."""
    fixture = _Fixture(_session_factory()(), "SHL4")
    fixture.product.shelf_life_days = 180
    fixture.session.commit()

    receipt = _receive(
        fixture, batch_number="B-804", manufacturing_date=date(2026, 8, 1)
    )
    assert _line(fixture, receipt).expiry_date is None

    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id,  # type: ignore[attr-defined]
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    batch = fixture.session.scalar(
        select(BatchRecord).where(BatchRecord.batch_number == "B-804")
    )
    assert batch is not None
    assert (batch.expiry_date, batch.manufacturing_date) == (None, None)


@pytest.mark.parametrize("days", [0, 3651])
def test_a_shelf_life_is_a_day_to_ten_years(days: int) -> None:
    with pytest.raises(ValidationError):
        ProductCreate(
            code="MILK-1",
            name="Milk",
            product_type="STOCK_ITEM",
            shelf_life_days=days,
        )
