"""Stock alerts and stock turnover (STK-14, decision A116).

A product with 2 free against a reorder level of 5 is low; another with
none against 4 is out; one held over its maximum is flagged. A batch inside
the near-expiry window is listed. The ageing report gives each item its
turnover: eight dispatched in the year over what is left.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

from app.inventory.services.stock_ageing import StockAgeingService
from app.inventory.services.stock_alerts import ROWS_PER_KIND, stock_alerts
from app.products.models import Product
from tests.unit.test_batch_picker import _Shop as _BatchShop
from tests.unit.test_reorder_suggestions import _Shop

D = Decimal


def test_low_out_and_over_maximum_are_counted_and_listed() -> None:
    shop = _Shop()
    shop.stock(shop.product, available="2", reorder="5", maximum="20")
    other = shop.other_product()
    shop.stock(other, available="0", reorder="4", locator="B-1")
    alerts = stock_alerts(shop.session, shop.firm.id, on=date(2026, 9, 1))
    assert (alerts.low, alerts.out) == (1, 1)
    kinds = {row.kind: row for row in alerts.rows}
    assert kinds["LOW"].level == D("5")
    assert kinds["OUT"].product_code == other.code


def test_the_rows_listed_are_the_worst_of_their_kind() -> None:
    # Twelve products are low and ten are listed: the two left out are the
    # two that are short by least, whatever order they were written in
    # (D-STK-55).
    shop = _Shop()
    shop.stock(shop.product, available="4", reorder="5")
    for short in (1, 12, 3, 10, 5, 8, 7, 6, 9, 4, 11):
        product = Product(
            firm_id=shop.firm.id,
            code=f"LOW-{short:02d}",
            name=f"Short by {short}",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        shop.session.add(product)
        shop.session.commit()
        shop.stock(product, available="1", reorder=str(short + 1))
    alerts = stock_alerts(shop.session, shop.firm.id, on=date(2026, 9, 1))
    assert alerts.low == 12
    low = [row for row in alerts.rows if row.kind == "LOW"]
    assert len(low) == ROWS_PER_KIND
    shortfalls = [row.level - row.quantity for row in low if row.level is not None]
    assert shortfalls == [D(n) for n in range(12, 2, -1)]
    assert low[0].product_code == "LOW-12"
    # Two short by one: neither is listed, and the count still has both.
    assert {shop.product.code, "LOW-01"}.isdisjoint(row.product_code for row in low)


def test_near_expiry_batches_and_turnover() -> None:
    shop = _BatchShop()
    alerts = stock_alerts(shop.session, shop.firm_id, on=date(2027, 3, 15))
    assert alerts.near_expiry == 1
    near = next(row for row in alerts.rows if row.kind == "NEAR_EXPIRY")
    assert "MARCH" in near.detail

    shop.dispatch(shop.note(None))
    (row,) = StockAgeingService(shop.session).ageing(shop.firm_id, on=date(2026, 9, 30))
    assert row.issued_last_year == D("8")
    assert row.turnover == (D("8") / row.quantity).quantize(D("0.01"))
