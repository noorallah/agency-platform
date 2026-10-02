"""Discount given and collections (backlog 67 rows 8 and 9).

Discount given splits what somebody typed from what an arrangement or an
offer applied, by the stored ``discount_source`` -- looking through an
inherited line to the order line where it was decided. Collections count a
receipt on its date and its reversal on the reversal's, by day, by the
salesman of the bill it cleared (or *On account*) and by mode.
"""

# ruff: noqa: D103

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import event

from app.core.pagination.reports import ReportWindow
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNoteLine
from app.finance.models import JournalEntry
from app.identity.models import User, UserFirm
from app.products.models import Product
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_invoice.api.router import (
    get_discount_by_customer,
    get_discount_by_product,
    get_discount_by_promotion,
    get_discount_by_salesman,
)
from app.sales_invoice.api.router import router as invoice_router
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrderLine
from app.settlements.api.router import (
    collections_by_day,
    collections_by_mode,
    collections_by_salesman,
    receipts_router,
)
from app.settlements.models import Settlement, SettlementAllocation
from tests.unit.report_windows import assert_page_size_is_bounded, report_scope
from tests.unit.test_document_summaries_in_sql import _add, _session

MAY = ReportWindow(date(2026, 5, 1), date(2026, 5, 31))


class _Firm:
    """A firm with two customers, two products and one salesman."""

    def __init__(self) -> None:
        self.session = _session()
        self.id = uuid.uuid4()
        self.customers = [uuid.uuid4(), uuid.uuid4()]
        for number, customer in enumerate(self.customers):
            _add(
                self.session,
                Customer,
                id=customer,
                firm_id=self.id,
                code=f"C{number}",
                name=f"Customer {number} Ltd",
                display_name=f"Customer {number}",
            )
        self.products = [uuid.uuid4(), uuid.uuid4()]
        for number, product in enumerate(self.products):
            _add(
                self.session,
                Product,
                id=product,
                firm_id=self.id,
                code=f"P{number}",
                name=f"Product {number}",
                track_serial=False,
            )
        self.salesman = uuid.uuid4()
        _add(
            self.session,
            User,
            id=self.salesman,
            email="ravi@example.com",
            full_name="Ravi",
            is_active=True,
        )
        _add(
            self.session,
            UserFirm,
            user_id=self.salesman,
            firm_id=self.id,
            is_active=True,
        )

    def invoice(
        self,
        *,
        on: date,
        customer: int = 0,
        salesman: bool = True,
        status: str = "APPROVED",
        total: str = "0",
    ) -> UUID:
        invoice = uuid.uuid4()
        _add(
            self.session,
            SalesInvoice,
            id=invoice,
            firm_id=self.id,
            customer_id=self.customers[customer],
            salesman_id=self.salesman if salesman else None,
            invoice_date=on,
            status=status,
            grand_total=Decimal(total),
        )
        return invoice

    def line(
        self,
        invoice: UUID,
        *,
        source: str | None,
        discount: str,
        gross: str = "100",
        bill: str = "0",
        product: int = 0,
        source_type: str = "MANUAL",
        source_line: UUID | None = None,
    ) -> None:
        _add(
            self.session,
            SalesInvoiceLine,
            sales_invoice_id=invoice,
            firm_id=self.id,
            line_number=uuid.uuid4().int % 10_000,
            product_id=self.products[product],
            source_document_type=source_type,
            source_document_line_id=source_line or uuid.uuid4(),
            gross_amount=Decimal(gross),
            discount_amount=Decimal(discount),
            bill_discount_amount=Decimal(bill),
            discount_source=source,
        )

    def order_line(self, source: str) -> UUID:
        line = uuid.uuid4()
        _add(
            self.session,
            SalesOrderLine,
            id=line,
            firm_id=self.id,
            discount_source=source,
        )
        return line

    def note_line(self, order_line: UUID) -> UUID:
        line = uuid.uuid4()
        _add(
            self.session,
            DeliveryNoteLine,
            id=line,
            firm_id=self.id,
            sales_order_line_id=order_line,
        )
        return line

    def receipt(
        self,
        *,
        on: date,
        amount: str,
        method: str = "CASH",
        mode: str | None = None,
        reversed_on: date | None = None,
        allocations: tuple[tuple[UUID, str], ...] = (),
    ) -> UUID:
        reversal: UUID | None = None
        if reversed_on is not None:
            reversal = uuid.uuid4()
            _add(
                self.session,
                JournalEntry,
                id=reversal,
                firm_id=self.id,
                journal_date=reversed_on,
                status="POSTED",
            )
        receipt = uuid.uuid4()
        _add(
            self.session,
            Settlement,
            id=receipt,
            firm_id=self.id,
            direction="RECEIPT",
            customer_id=self.customers[0],
            settlement_date=on,
            amount=Decimal(amount),
            method=method,
            payment_mode=mode,
            status="REVERSED" if reversal else "POSTED",
            reversal_journal_entry_id=reversal,
        )
        for invoice, share in allocations:
            _add(
                self.session,
                SettlementAllocation,
                firm_id=self.id,
                settlement_id=receipt,
                sales_invoice_id=invoice,
                amount=Decimal(share),
            )
        return receipt

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


# ----------------------------------------------------------------------
# Discount given (67 row 8)
# ----------------------------------------------------------------------


def test_discount_by_customer_splits_typed_from_arranged() -> None:
    firm = _Firm()
    bill = firm.invoice(on=date(2026, 5, 3))
    firm.line(bill, source="percent", discount="10")
    firm.line(bill, source="amount", discount="5")
    firm.line(bill, source="price_list", discount="7")
    firm.line(bill, source="customer_group", discount="3")
    firm.line(bill, source="promotion", discount="4")
    firm.line(bill, source=None, discount="2")  # before the source was kept
    firm.line(bill, source="none", discount="0", bill="6")
    # Neither a draft nor a bill outside the month counts.
    firm.line(
        firm.invoice(on=date(2026, 5, 4), status="DRAFT"),
        source="amount",
        discount="99",
    )
    firm.line(firm.invoice(on=date(2026, 6, 1)), source="amount", discount="99")

    page = get_discount_by_customer(
        report_scope(firm.id), firm.session, date(2026, 5, 1), date(2026, 5, 31)
    )

    [row] = page.data
    assert row.name == "Customer 0" and row.code == "C0"
    assert row.typed_discount == Decimal("17.00")
    assert row.arranged_discount == Decimal("10.00")
    assert row.promotion_discount == Decimal("4.00")
    assert row.bill_discount == Decimal("6.00")
    assert row.total_discount == Decimal("37.00")
    assert row.gross_amount == Decimal("700.00")
    assert row.discount_percent == Decimal("5.29")


def test_an_inherited_discount_is_judged_where_it_was_decided() -> None:
    firm = _Firm()
    bill = firm.invoice(on=date(2026, 5, 3))
    # From an order line directly: the order's offer.
    firm.line(
        bill,
        source="inherited",
        discount="8",
        source_type="SALES_ORDER",
        source_line=firm.order_line("promotion"),
    )
    # Through a delivery note's line to an order line somebody typed.
    firm.line(
        bill,
        source="inherited",
        discount="5",
        source_type="DELIVERY_NOTE",
        source_line=firm.note_line(firm.order_line("percent")),
    )
    # Through a note to a price list.
    firm.line(
        bill,
        source="inherited",
        discount="3",
        source_type="DELIVERY_NOTE",
        source_line=firm.note_line(firm.order_line("price_list")),
    )

    [row] = get_discount_by_customer(
        report_scope(firm.id), firm.session, date(2026, 5, 1), date(2026, 5, 31)
    ).data

    assert row.promotion_discount == Decimal("8.00")
    assert row.typed_discount == Decimal("5.00")
    assert row.arranged_discount == Decimal("3.00")


def test_discount_by_salesman_and_by_product() -> None:
    firm = _Firm()
    firm.line(firm.invoice(on=date(2026, 5, 3)), source="amount", discount="10")
    firm.line(
        firm.invoice(on=date(2026, 5, 4), salesman=False),
        source="amount",
        discount="4",
        product=1,
    )

    by_salesman = get_discount_by_salesman(
        report_scope(firm.id), firm.session, date(2026, 5, 1), date(2026, 5, 31)
    ).data
    assert [(row.name, row.total_discount) for row in by_salesman] == [
        ("Ravi", Decimal("10.00")),
        ("No salesman", Decimal("4.00")),
    ]
    by_product = get_discount_by_product(
        report_scope(firm.id), firm.session, date(2026, 5, 1), date(2026, 5, 31)
    ).data
    assert [(row.code, row.total_discount) for row in by_product] == [
        ("P0", Decimal("10.00")),
        ("P1", Decimal("4.00")),
    ]


def test_a_discount_page_costs_the_same_statements_at_any_length() -> None:
    firm = _Firm()

    def count() -> int:
        with firm.statements() as seen:
            get_discount_by_product(
                report_scope(firm.id),
                firm.session,
                date(2026, 5, 1),
                date(2026, 5, 31),
            )
        return len(seen)

    firm.line(firm.invoice(on=date(2026, 5, 3)), source="amount", discount="1")
    few = count()
    for _ in range(12):
        product = uuid.uuid4()
        _add(firm.session, Product, id=product, firm_id=firm.id, track_serial=False)
        firm.products.append(product)
        firm.line(
            firm.invoice(on=date(2026, 5, 3)),
            source="amount",
            discount="1",
            product=len(firm.products) - 1,
        )
    assert count() == few


def test_discount_by_promotion_counts_claims_in_the_dates() -> None:
    firm = _Firm()
    group = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()
    for version, number, name in ((first, 1, "Diwali"), (second, 2, "Diwali 2")):
        _add(
            firm.session,
            Promotion,
            id=version,
            firm_id=firm.id,
            code="DIWALI",
            name=name,
            version_group_id=group,
            version_number=number,
        )
    for version, on, status, benefit in (
        (first, date(2026, 5, 2), "CLAIMED", "30"),
        (second, date(2026, 5, 9), "CLAIMED", "20"),
        (second, date(2026, 5, 10), "REVERSED", "50"),
        (second, date(2026, 6, 1), "CLAIMED", "70"),
    ):
        _add(
            firm.session,
            PromotionRedemption,
            firm_id=firm.id,
            promotion_id=version,
            customer_id=firm.customers[0],
            redeemed_on=on,
            status=status,
            benefit_amount=Decimal(benefit),
        )
    [row] = get_discount_by_promotion(
        report_scope(firm.id), firm.session, date(2026, 5, 1), date(2026, 5, 31)
    ).data
    assert (row.name, row.claims, row.customers, row.benefit_amount) == (
        "Diwali 2",
        2,
        1,
        Decimal("50.00"),
    )


# ----------------------------------------------------------------------
# Collections (67 row 9)
# ----------------------------------------------------------------------


def test_collections_by_day_net_a_reversal_on_its_own_day() -> None:
    firm = _Firm()
    firm.receipt(on=date(2026, 5, 3), amount="500", reversed_on=date(2026, 5, 9))
    firm.receipt(on=date(2026, 5, 3), amount="200")
    firm.receipt(on=date(2026, 4, 30), amount="80", reversed_on=date(2026, 5, 2))
    firm.receipt(on=date(2026, 6, 1), amount="999")

    rows = collections_by_day(
        report_scope(firm.id), date(2026, 5, 1), date(2026, 5, 31), db=firm.session
    ).data

    assert [
        (row.label, row.collected, row.reversed, row.net_collected) for row in rows
    ] == [
        ("2026-05-02", Decimal("0.00"), Decimal("80.00"), Decimal("-80.00")),
        ("2026-05-03", Decimal("700.00"), Decimal("0.00"), Decimal("700.00")),
        ("2026-05-09", Decimal("0.00"), Decimal("500.00"), Decimal("-500.00")),
    ]
    assert rows[1].receipts == 2


def test_collections_by_mode() -> None:
    firm = _Firm()
    firm.receipt(on=date(2026, 5, 3), amount="100", method="CASH")
    firm.receipt(on=date(2026, 5, 4), amount="250", method="BANK")
    firm.receipt(
        on=date(2026, 5, 5), amount="40", method="BANK", reversed_on=date(2026, 5, 6)
    )
    rows = collections_by_mode(
        report_scope(firm.id), date(2026, 5, 1), date(2026, 5, 31), db=firm.session
    ).data
    # Recorded before the mode was asked for: a bank receipt says so rather
    # than being guessed into one (ACC-3).
    assert [(row.label, row.net_collected) for row in rows] == [
        ("Bank (mode not recorded)", Decimal("250.00")),
        ("Cash", Decimal("100.00")),
    ]


def test_collections_by_mode_name_how_the_bank_money_came() -> None:
    """A cheque, a UPI and a transfer each count under their own mode (ACC-3)."""
    firm = _Firm()
    firm.receipt(on=date(2026, 5, 3), amount="100", method="CASH", mode="CASH")
    firm.receipt(on=date(2026, 5, 4), amount="250", method="BANK", mode="CHEQUE")
    firm.receipt(on=date(2026, 5, 4), amount="70", method="BANK", mode="UPI")
    firm.receipt(on=date(2026, 5, 5), amount="30", method="BANK", mode="UPI")
    rows = collections_by_mode(
        report_scope(firm.id), date(2026, 5, 1), date(2026, 5, 31), db=firm.session
    ).data
    assert [(row.label, row.receipts, row.net_collected) for row in rows] == [
        ("Cash", 1, Decimal("100.00")),
        ("Cheque", 1, Decimal("250.00")),
        ("UPI", 2, Decimal("100.00")),
    ]


def test_collections_by_salesman_follow_the_bill_and_keep_the_rest_on_account() -> None:
    firm = _Firm()
    his = firm.invoice(on=date(2026, 4, 20), total="300")
    nobody = firm.invoice(on=date(2026, 4, 21), salesman=False, total="100")
    firm.receipt(
        on=date(2026, 5, 3), amount="500", allocations=((his, "300"), (nobody, "100"))
    )
    firm.receipt(
        on=date(2026, 5, 4),
        amount="60",
        allocations=((his, "60"),),
        reversed_on=date(2026, 5, 20),
    )

    rows = collections_by_salesman(
        report_scope(firm.id), date(2026, 5, 1), date(2026, 5, 31), db=firm.session
    ).data

    assert [(row.label, row.collected, row.reversed) for row in rows] == [
        ("Ravi", Decimal("360.00"), Decimal("60.00")),
        ("No salesman", Decimal("100.00"), Decimal("0.00")),
        ("On account", Decimal("100.00"), Decimal("0.00")),
    ]
    assert rows[0].net_collected == Decimal("300.00")
    assert rows[-1].receipts == 1


def test_the_new_report_routes_bound_their_page() -> None:
    assert_page_size_is_bounded(
        invoice_router,
        "/api/v1/sales-invoices/reports/discount-by-customer",
        "/api/v1/sales-invoices/reports/discount-by-salesman",
        "/api/v1/sales-invoices/reports/discount-by-product",
        "/api/v1/sales-invoices/reports/discount-by-promotion",
    )
    assert_page_size_is_bounded(
        receipts_router,
        "/api/v1/receipts/reports/collections-by-day",
        "/api/v1/receipts/reports/collections-by-salesman",
        "/api/v1/receipts/reports/collections-by-mode",
    )
