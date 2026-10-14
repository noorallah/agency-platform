"""A lot's retail and wholesale prices on receiving (L3 step 2).

`docs/design/LOT_MARGINS_DESIGN.md`, sections 3.3 and 3.4: the receipt line's
net rate per stock unit before tax, marked up by the product's margins unless
the line changes them, a typed price winning over its margin, the result on
the line and on the lot to the paisa; a price above the MRP with tax warns;
the BATCH_PTR_PTS gate and the printed-batch rule held for a firm on Average
only; and the other places a lot is made priced the same way.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.services.lot_margins import (
    LotPrices,
    lot_prices,
    margin_from_price,
    mrp_warning,
    worked_price,
)
from app.inventory.services.lots import newest_valued_lot
from app.inventory.services.repacking import (
    RepackLineWrite,
    RepackService,
    RepackWrite,
)
from tests.unit.test_lot_receiving import _batches, _receive, _shop
from tests.unit.test_lot_stock_moves import ON, _Shop

pytestmark = pytest.mark.typed_document_numbers


def _line(receipt: GoodsReceipt, fixture: object) -> GoodsReceiptLine:
    """Return the receipt's one line."""
    session = fixture.session  # type: ignore[attr-defined]
    return session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()


def test_the_worked_example_of_the_design_note() -> None:
    """26.60 a piece at 12 % and 6 % is 29.79 and 28.20, to the paisa."""
    prices = lot_prices(
        cost=Decimal("26.60"),
        retail_margin_percent=Decimal("12"),
        wholesale_margin_percent=Decimal("6"),
    )
    assert (prices.ptr, prices.pts) == (Decimal("29.79"), Decimal("28.20"))
    assert worked_price(Decimal("26.60"), Decimal("20")) == Decimal("31.92")
    assert margin_from_price(Decimal("26.60"), Decimal("31.92")) == Decimal("20.00")
    assert margin_from_price(None, Decimal("31.92")) is None
    # Nothing to mark up: no price, the margin kept.
    free = lot_prices(
        cost=None, retail_margin_percent=Decimal("12"), wholesale_margin_percent=None
    )
    assert free == LotPrices(retail_margin_percent=Decimal("12"))


def test_a_price_above_the_mrp_with_tax_warns_and_names_the_price_at_it() -> None:
    """31.92 plus 18 % is 37.67, above an MRP of 35.00; 29.66 sits at it."""
    warning = mrp_warning(
        mrp=Decimal("35.00"),
        ptr=Decimal("31.92"),
        pts=Decimal("28.20"),
        tax_rate=Decimal("0.18"),
    )
    assert warning is not None
    assert "Retail price (PTR) 31.92 is 37.67 with tax" in warning
    assert "29.66 before tax sits at the MRP" in warning
    assert "Wholesale" not in warning
    assert (
        mrp_warning(
            mrp=Decimal("40"), ptr=Decimal("31.92"), pts=None, tax_rate=Decimal("0.18")
        )
        is None
    )


def test_a_lot_priced_by_nobody_drops_what_the_register_would_refuse() -> None:
    """Above the MRP before tax, or wholesale above retail, is left off."""
    prices = LotPrices(ptr=Decimal("50"), pts=Decimal("45"))
    assert prices.within(Decimal("40")) == LotPrices()
    assert LotPrices(ptr=Decimal("30"), pts=Decimal("35")).within(None) == LotPrices(
        ptr=Decimal("30")
    )


def test_the_lot_takes_the_products_margins_on_the_net_rate() -> None:
    """100.00 less 5 % is 95.00; 12 % and 6 % on it are 106.40 and 100.70."""
    fixture = _shop("LMP1", by_lot=True)
    fixture.product.retail_margin_percent = Decimal("12")
    fixture.product.wholesale_margin_percent = Decimal("6")
    fixture.session.commit()

    receipt = _receive(fixture, "4", batch_number="BN-1", discount_percent="5")

    line = _line(receipt, fixture)
    assert (line.ptr, line.pts) == (Decimal("106.40"), Decimal("100.70"))
    assert line.retail_margin_percent == Decimal("12")
    assert line.wholesale_margin_percent == Decimal("6")
    (lot,) = _batches(fixture.session)
    assert (lot.ptr, lot.pts) == (Decimal("106.40"), Decimal("100.70"))
    assert lot.retail_margin_percent == Decimal("12")
    assert lot.wholesale_margin_percent == Decimal("6")


def test_a_margin_or_a_price_on_the_line_is_for_this_lot_only() -> None:
    """A line margin replaces the product's; a typed price wins over its margin."""
    fixture = _shop("LMP2", by_lot=True)
    fixture.product.retail_margin_percent = Decimal("12")
    fixture.product.wholesale_margin_percent = Decimal("6")
    fixture.session.commit()

    receipt = _receive(
        fixture,
        "4",
        batch_number="BN-1",
        retail_margin_percent="20",
        pts="104.50",
    )

    line = _line(receipt, fixture)
    assert (line.ptr, line.retail_margin_percent) == (Decimal("120.00"), Decimal("20"))
    assert (line.pts, line.wholesale_margin_percent) == (
        Decimal("104.50"),
        Decimal("4.50"),
    )
    assert fixture.product.retail_margin_percent == Decimal("12")


def test_a_by_lot_firm_prices_a_lot_with_no_printed_batch_or_pharma_profile() -> None:
    """The gate and the printed-batch rule are for a firm on Average."""
    fixture = _shop("LMP3", by_lot=True, track_batch=False)

    receipt = _receive(fixture, "4", ptr="130.00", pts="120.00")

    line = _line(receipt, fixture)
    assert (line.ptr, line.pts) == (Decimal("130.00"), Decimal("120.00"))
    assert line.retail_margin_percent == Decimal("30.00")
    (lot,) = _batches(fixture.session)
    assert (lot.ptr, lot.pts) == (Decimal("130.00"), Decimal("120.00"))


def test_a_product_with_no_margins_gives_its_lot_no_price() -> None:
    """Nothing typed, nothing set: the sale falls through the ranking."""
    fixture = _shop("LMP4", by_lot=True)

    _receive(fixture, "4", batch_number="BN-1")

    (lot,) = _batches(fixture.session)
    assert (lot.ptr, lot.pts) == (None, None)


def test_a_worked_price_above_the_mrp_before_tax_is_refused_by_line() -> None:
    """No tax rate makes a price before tax above the MRP lawful."""
    fixture = _shop("LMP5", by_lot=True)
    fixture.product.retail_margin_percent = Decimal("50")
    fixture.session.commit()

    with pytest.raises(ValidationError, match=r"Line 1: PTR 150.00 cannot exceed"):
        _receive(fixture, "4", batch_number="BN-1", mrp="140.00")


def test_a_firm_on_average_may_not_send_margins() -> None:
    """Margins price lots, and an Average firm has none."""
    fixture = _shop("LMP6", by_lot=False)

    with pytest.raises(ValidationError, match="does not cost its stock by lot"):
        _receive(fixture, "4", batch_number="BN-1", retail_margin_percent="10")


def test_the_receipt_line_warns_above_the_mrp_with_its_own_tax() -> None:
    """The line's tax over its taxable value is the rate judged."""
    service = GoodsReceiptService.__new__(GoodsReceiptService)
    line = GoodsReceiptLine(
        gross_amount=Decimal("100"),
        discount_amount=Decimal("0"),
        bill_discount_amount=Decimal("0"),
        tax_amount=Decimal("18"),
        mrp=Decimal("35.00"),
        ptr=Decimal("31.92"),
        pts=None,
    )
    warning = service._mrp_warning(line)
    assert warning is not None and "37.67 with tax" in warning
    line.mrp = None
    assert service._mrp_warning(line) is None


def test_stock_found_takes_the_newest_lots_prices_or_works_its_own() -> None:
    """Copied with the newest lot's cost; worked from the pair on a typed cost."""
    shop = _Shop()
    newest = newest_valued_lot(shop.session, shop.firm.id, shop.drug.id)
    assert newest is not None
    late = newest[0]
    late.ptr, late.pts = Decimal("45.00"), Decimal("42.00")
    late.retail_margin_percent = Decimal("25")
    shop.drug.retail_margin_percent = Decimal("10")
    shop.drug.wholesale_margin_percent = Decimal("5")
    shop.session.commit()

    copied = shop.adjust("2")
    worked = shop.adjust("3", unit_cost="30")

    lot = shop.session.get(BatchRecord, copied.batch_id)
    assert lot is not None
    assert (lot.ptr, lot.pts) == (Decimal("45.00"), Decimal("42.00"))
    assert lot.retail_margin_percent == Decimal("25")
    lot = shop.session.get(BatchRecord, worked.batch_id)
    assert lot is not None
    assert (lot.ptr, lot.pts) == (Decimal("33.00"), Decimal("31.50"))


def test_a_repack_prices_its_lot_from_the_output_products_margins() -> None:
    """Four of EARLY (160) make two packs at 80 each; 10 % on it is 88.00."""
    shop = _Shop()
    shop.pack.retail_margin_percent = Decimal("10")
    shop.session.commit()

    repack = RepackService(shop.session).post(
        RepackWrite(
            repack_date=ON,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            lines=[
                RepackLineWrite(
                    kind="CONSUME", product_id=shop.drug.id, quantity=Decimal("4")
                ),
                RepackLineWrite(
                    kind="PRODUCE", product_id=shop.pack.id, quantity=Decimal("2")
                ),
            ],
        ),
        firm_id=shop.firm.id,
        actor_id=uuid4(),
    )

    _, produced = RepackService(shop.session).lines(repack.id)
    lot = shop.session.get(BatchRecord, produced.batch_id)
    assert lot is not None
    assert (lot.ptr, lot.pts, lot.retail_margin_percent) == (
        Decimal("88.00"),
        None,
        Decimal("10"),
    )
