"""Expiry rules per product (STK-5, decision A113).

The shop holds MARCH (expires 2027-03-31) and JUNE (2027-06-30); the note is
dated 2026-09-16. With the product set to stop selling 250 days before
expiry, dispatch passes MARCH over and draws JUNE, and choosing MARCH is
refused naming the window. A product with no rule takes its category's; its
own wins. The return list names batches inside the return window.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest

from app.batch_serial.services.expiry_rules import expiry_rules, returns_due
from app.core.exceptions import ValidationError
from app.products.models import ProductCategory
from tests.unit.test_batch_picker import _Shop

D = Decimal


def _stop_selling(shop: _Shop, days: int) -> None:
    shop.product.expiry_stop_sale_days = days
    shop.session.commit()


def test_dispatch_passes_over_a_batch_inside_the_stop_window() -> None:
    shop = _Shop()
    _stop_selling(shop, 250)
    note = shop.note(None)
    shop.dispatch(note)
    assert shop.drawn(note) == {"JUNE": D("8.0000")}


def test_choosing_a_batch_inside_the_stop_window_is_refused() -> None:
    shop = _Shop()
    _stop_selling(shop, 250)
    note = shop.note(shop.picks(MARCH="8"))
    with pytest.raises(ValidationError, match="inside the 250 days"):
        shop.dispatch(note)


def test_a_product_takes_its_categorys_rule_and_its_own_wins() -> None:
    shop = _Shop()
    category = ProductCategory(
        firm_id=shop.firm_id,
        code="MEDS",
        name="Medicines",
        level=0,
        path="MEDS",
        expiry_stop_sale_days=30,
        expiry_alert_days=90,
        expiry_return_days=60,
    )
    shop.session.add(category)
    shop.session.flush()
    shop.product.category_id = category.id
    shop.session.commit()
    rule = expiry_rules(shop.session, shop.firm_id, {shop.product.id})[shop.product.id]
    assert (rule.stop_sale_days, rule.alert_days, rule.return_days) == (30, 90, 60)
    shop.product.expiry_alert_days = 45
    shop.session.commit()
    rule = expiry_rules(shop.session, shop.firm_id, {shop.product.id})[shop.product.id]
    assert rule.alert_days == 45


def test_the_return_list_names_batches_inside_the_window() -> None:
    shop = _Shop()
    assert returns_due(shop.session, shop.firm_id, on=date(2026, 10, 3)) == []
    shop.product.expiry_return_days = 200
    shop.session.commit()
    due = returns_due(shop.session, shop.firm_id, on=date(2026, 10, 3))
    assert [record.batch_number for record in due] == ["STALE", "MARCH"]
