"""Supplier performance (BUY-12, decision A107).

A supplier billed ten widgets at 100, received through the bill's own
receipt, three days after an order expected in two: one receipt, late, ten
received, nothing short of a finished order. Its price trend for August is
100. A supplier with nothing in the window does not appear.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.pagination import ReportWindow
from app.goods_receipt.models import GoodsReceipt
from app.purchase.models import PurchaseOrder
from app.purchase.services.supplier_performance import (
    supplier_performance,
    supplier_price_trend,
)
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm that has billed ten widgets from its supplier."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="PERFS")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    receipt = built.session.scalar(select(GoodsReceipt))
    assert receipt is not None
    order = built.session.get(PurchaseOrder, receipt.purchase_order_id)
    assert order is not None
    order.purchase_date = receipt.receipt_date - timedelta(days=3)
    order.expected_delivery_date = receipt.receipt_date - timedelta(days=1)
    built.session.commit()
    return built


def test_one_row_per_supplier(firm: _Firm) -> None:
    (row,) = supplier_performance(
        firm.session, firm_id=firm.firm.id, window=ReportWindow()
    )
    assert row.vendor_id == firm.vendor.id
    assert (row.receipts, row.on_time_receipts, row.receipts_with_expected_date) == (
        1,
        0,
        1,
    )
    assert row.on_time_percent == D("0.0")
    assert row.received_quantity == D("10")
    assert row.rejected_percent == D("0.0")
    assert row.short_quantity == D("0")


def test_a_window_with_nothing_in_it_is_empty(firm: _Firm) -> None:
    window = ReportWindow(date(2020, 1, 1), date(2020, 12, 31))
    assert supplier_performance(firm.session, firm_id=firm.firm.id, window=window) == []


def test_the_price_trend(firm: _Firm) -> None:
    (point,) = supplier_price_trend(
        firm.session,
        firm_id=firm.firm.id,
        vendor_id=firm.vendor.id,
        product_id=firm.product.id,
        window=ReportWindow(),
    )
    assert (point.month, point.quantity, point.average_rate) == (
        "2026-08",
        D("10"),
        D("100.00"),
    )
