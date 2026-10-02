"""Stock ageing, slow-moving and dead stock, and vendor ageing (55 S7).

Stock on hand is aged as FIFO would leave it -- the newest receipts are what
is left -- with what no receipt explains put in the oldest bucket. Slow and
dead stock are judged on dispatches to customers only. Vendor ageing mirrors
the customer ageing over what Record Payment says each bill owes.
"""

# ruff: noqa: D103

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import event

from app.core.utils.dates import utc_now
from app.finance.services.ageing_settings import AgeingSettingsService
from app.inventory.api.router import dead_stock, router, slow_moving_stock, stock_ageing
from app.inventory.models import InventoryTransaction
from app.inventory.services.stock_ageing import StockAgeingService
from app.products.models import Product
from app.purchase_invoice.api.router import vendor_ageing
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.models import Settlement, SettlementAllocation
from app.vendors.models import Vendor
from tests.unit.report_windows import assert_page_size_is_bounded, report_scope
from tests.unit.test_document_summaries_in_sql import _add, _session

ON = date(2026, 9, 30)


class _Stock:
    """A firm's products and the movements they had."""

    def __init__(self) -> None:
        self.session = _session()
        self.firm = uuid.uuid4()
        self.products: list[UUID] = []

    def product(self, code: str) -> UUID:
        product = uuid.uuid4()
        _add(
            self.session,
            Product,
            id=product,
            firm_id=self.firm,
            code=code,
            name=f"Item {code}",
            track_serial=False,
        )
        self.products.append(product)
        return product

    def move(self, product: UUID, kind: str, days_ago: int, quantity: str) -> None:
        _add(
            self.session,
            InventoryTransaction,
            firm_id=self.firm,
            product_id=product,
            transaction_type=kind,
            transaction_date=ON - timedelta(days=days_ago),
            current_quantity_delta=Decimal(quantity),
            quarantine_quantity_delta=Decimal("0"),
            owned_quantity_delta=None,
        )

    @contextmanager
    def statements(self) -> Iterator[list[Any]]:
        seen: list[Any] = []

        def record(*args: Any) -> None:  # noqa: ANN401
            seen.append(args[2])

        engine = self.session.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            yield seen
        finally:
            event.remove(engine, "before_cursor_execute", record)


def test_stock_on_hand_is_the_newest_receipts() -> None:
    stock = _Stock()
    item = stock.product("A")
    stock.move(item, "OPENING_STOCK", 400, "50")
    stock.move(item, "GOODS_RECEIPT", 100, "30")
    stock.move(item, "GOODS_RECEIPT", 45, "20")
    stock.move(item, "GOODS_RECEIPT", 10, "10")
    stock.move(item, "DISPATCH", 5, "-70")  # the oldest went first
    # A move between the firm's own warehouses changes nothing.
    stock.move(item, "TRANSFER_OUT", 2, "-5")
    stock.move(item, "TRANSFER_IN", 2, "5")

    [row] = StockAgeingService(stock.session).ageing(stock.firm, on=ON)

    assert row.quantity == Decimal("40")
    assert (
        row.days_0_30,
        row.days_31_60,
        row.days_61_90,
        row.days_91_180,
        row.days_over_180,
    ) == (Decimal("10"), Decimal("20"), Decimal("0"), Decimal("10"), Decimal("0"))
    assert row.last_receipt_date == ON - timedelta(days=10)


def test_stock_no_receipt_explains_is_put_in_the_oldest_bucket() -> None:
    stock = _Stock()
    item = stock.product("A")
    stock.move(item, "GOODS_RECEIPT", 3, "5")
    stock.move(item, "ADJUSTMENT", 1, "7")  # found at a count
    stock.move(item, "GOODS_RECEIPT", 20, "9")
    stock.move(item, "GOODS_RECEIPT_REVERSAL", 19, "-9")  # cancelled

    [row] = StockAgeingService(stock.session).ageing(stock.firm, on=ON)

    assert row.quantity == Decimal("12")
    assert row.days_0_30 == Decimal("5")
    assert row.days_over_180 == Decimal("7")


def test_the_ageing_route_reads_as_on_a_past_day() -> None:
    stock = _Stock()
    item = stock.product("A")
    stock.move(item, "GOODS_RECEIPT", 50, "4")
    stock.move(item, "GOODS_RECEIPT", 0, "6")  # after the day asked about
    page = stock_ageing(
        report_scope(stock.firm),
        to_date=ON - timedelta(days=1),
        db=stock.session,
    )
    [row] = page.data
    assert row.quantity == Decimal("4")
    assert row.days_31_60 == Decimal("4")


def test_an_ageing_page_costs_the_same_statements_at_any_length() -> None:
    stock = _Stock()

    def count() -> int:
        with stock.statements() as seen:
            StockAgeingService(stock.session).ageing(stock.firm, on=ON)
        return len(seen)

    stock.move(stock.product("A"), "GOODS_RECEIPT", 5, "1")
    few = count()
    for number in range(12):
        stock.move(stock.product(f"B{number}"), "GOODS_RECEIPT", 40, "2")
    assert count() == few


def test_slow_moving_is_stock_its_recent_sales_would_not_clear() -> None:
    stock = _Stock()
    brisk, slow, idle, gone = (stock.product(code) for code in "BSIG")
    for item in (brisk, slow, idle, gone):
        stock.move(item, "GOODS_RECEIPT", 200, "100")
    stock.move(brisk, "DISPATCH", 10, "-60")  # 40 left, 60 in 90 days
    stock.move(slow, "DISPATCH", 10, "-10")  # 90 left, 10 in 90 days
    stock.move(idle, "DISPATCH", 150, "-5")  # nothing in the last 90 days
    stock.move(idle, "WRITE_OFF", 3, "-5")  # not demand
    stock.move(gone, "DISPATCH", 5, "-100")  # none on hand

    rows = StockAgeingService(stock.session).slow_moving(stock.firm, on=ON, days=90)

    assert [row.product_code for row in rows] == ["I", "S"]
    idle_row, slow_row = rows
    assert idle_row.days_of_cover is None
    assert idle_row.days_since_issue == 150
    assert slow_row.days_of_cover == Decimal("810.0")
    assert slow_row.issued_quantity == Decimal("10")


def test_dead_stock_is_what_no_customer_took_in_the_days() -> None:
    stock = _Stock()
    sold, unsold = stock.product("S"), stock.product("U")
    stock.move(sold, "GOODS_RECEIPT", 300, "10")
    stock.move(unsold, "GOODS_RECEIPT", 300, "10")
    stock.move(sold, "DISPATCH", 100, "-1")
    stock.move(unsold, "DISPATCH", 200, "-1")
    stock.move(unsold, "DISPATCH", 100, "-1")
    stock.move(unsold, "DISPATCH_REVERSAL", 99, "1")  # taken back

    page = dead_stock(
        report_scope(stock.firm),
        days=180,
        to_date=ON,
        db=stock.session,
    )
    # U's one issue in the 180 days was taken back, so it sold nothing.
    assert [row.product_code for row in page.data] == ["U"]
    page = dead_stock(report_scope(stock.firm), days=90, to_date=ON, db=stock.session)
    assert {row.product_code for row in page.data} == {"S", "U"}
    page = slow_moving_stock(
        report_scope(stock.firm), days=90, to_date=ON, db=stock.session
    )
    assert {row.product_code for row in page.data} == {"S", "U"}


def test_the_stock_routes_bound_their_page_and_days() -> None:
    assert_page_size_is_bounded(
        router,
        "/api/v1/inventory/reports/stock-ageing",
        "/api/v1/inventory/reports/slow-moving",
        "/api/v1/inventory/reports/dead-stock",
    )


# ----------------------------------------------------------------------
# Vendor ageing
# ----------------------------------------------------------------------


def test_vendor_ageing_buckets_what_record_payment_says_is_owed() -> None:
    session = _session()
    firm = uuid.uuid4()
    today = utc_now().date()
    acme, bolt = uuid.uuid4(), uuid.uuid4()
    for vendor, code in ((acme, "V-ACME"), (bolt, "V-BOLT")):
        _add(
            session,
            Vendor,
            id=vendor,
            firm_id=firm,
            code=code,
            name=f"{code} Ltd",
            display_name=code.title(),
        )

    def bill(vendor: UUID, total: str, due_days_ago: int, status: str) -> UUID:
        invoice = uuid.uuid4()
        _add(
            session,
            PurchaseInvoice,
            id=invoice,
            firm_id=firm,
            vendor_id=vendor,
            invoice_date=today - timedelta(days=due_days_ago + 30),
            due_date=today - timedelta(days=due_days_ago),
            grand_total=Decimal(total),
            status=status,
        )
        return invoice

    bill(acme, "100", -5, "APPROVED")  # not yet due
    bill(acme, "200", 45, "APPROVED")
    paid = bill(acme, "300", 100, "APPROVED")
    bill(acme, "999", 100, "DRAFT")  # not a debt
    bill(bolt, "50", 95, "APPROVED")
    payment = uuid.uuid4()
    _add(
        session,
        Settlement,
        id=payment,
        firm_id=firm,
        direction="PAYMENT",
        vendor_id=acme,
        settlement_date=today,
        amount=Decimal("250"),
        status="POSTED",
    )
    _add(
        session,
        SettlementAllocation,
        firm_id=firm,
        settlement_id=payment,
        purchase_invoice_id=paid,
        amount=Decimal("250"),
    )

    rows = vendor_ageing(report_scope(firm), db=session).data

    assert [row.vendor_code for row in rows] == ["V-ACME", "V-BOLT"]
    acme_row, bolt_row = rows
    assert acme_row.total_outstanding == Decimal("350.00")
    assert [(band.label, band.amount) for band in acme_row.buckets] == [
        ("0-29", Decimal("100.00")),
        ("30-59", Decimal("200.00")),
        ("60-89", Decimal("0.00")),
        ("90+", Decimal("50.00")),
    ]
    assert acme_row.bills == 3
    assert acme_row.oldest_days == 100
    assert bolt_row.buckets[-1].amount == Decimal("50.00")

    # The firm's own bands (ACC-6): the same bills read in 0-14 / 15-59 / 60+.
    AgeingSettingsService(session).set_bucket_days(firm, [15, 60], actor_id=firm)
    acme_row = vendor_ageing(report_scope(firm), db=session).data[0]
    assert [(band.label, band.amount) for band in acme_row.buckets] == [
        ("0-14", Decimal("100.00")),
        ("15-59", Decimal("200.00")),
        ("60+", Decimal("50.00")),
    ]

    # Falling due (ACC-6): the bill five days ahead is in the week, not today.
    from app.purchase_invoice.api.router import purchase_invoices_falling_due

    week = purchase_invoices_falling_due(report_scope(firm), days=7, db=session)
    assert [(row.outstanding_amount, row.days_until_due) for row in week.data] == [
        (Decimal("100.00"), 5)
    ]
    today_only = purchase_invoices_falling_due(report_scope(firm), days=0, db=session)
    assert today_only.data == []
