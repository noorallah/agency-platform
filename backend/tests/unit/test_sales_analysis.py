"""Sales analysis: billed sales by any one or two dimensions (backlog 62).

Billed sales are approved and closed invoices; net of returns takes off the
approved credit notes and completed returns dated in the same period. Totals
both ways add up, and the invoices behind a cell are exactly those summed.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services.sales_analysis import (
    AnalysisFilters,
    SalesAnalysisService,
)
from tests.unit.test_credit_note import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)


def _second_invoice(books: _Books, on: date, product: Product, net: str) -> None:
    """Add another approved invoice of one line, taxed at 18%."""
    invoice = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        invoice_number=f"SI-{uuid4().hex[:6]}",
        invoice_date=on,
        status="APPROVED",
        grand_total=Decimal(net),
    )
    books.session.add(invoice)
    books.session.flush()
    value = Decimal(net)
    books.session.add(
        SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=books.firm.id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=uuid4(),
            source_document_number="SO-X",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=product.id,
            delivered_quantity=Decimal("2"),
            current_invoice_quantity=Decimal("2"),
            unit_price=value / 2,
            gross_amount=value * 100 / 118,
            tax_amount=value * 18 / 118,
            net_amount=value,
        )
    )
    books.session.commit()


def test_one_dimension_with_totals() -> None:
    books = _Books(_session_factory()())
    result = SalesAnalysisService(books.session).analyse(
        books.firm.id, rows="product", columns=None, from_date=FROM, to_date=TO
    )
    [row] = result.rows
    assert row.label == "SKU-1 Product One"
    totals = result.row_totals[row.key]
    assert (totals.quantity, totals.taxable, totals.tax, totals.net) == (
        Decimal("10"),
        Decimal("1000"),
        Decimal("180"),
        Decimal("1180"),
    )
    assert result.grand_total.invoices == 1


def test_a_credit_note_in_the_period_reduces_net_sales() -> None:
    books = _Books(_session_factory()())
    books.approved("100")  # 100 + 18 tax credited
    service = SalesAnalysisService(books.session)

    net = service.analyse(
        books.firm.id, rows="month", columns=None, from_date=FROM, to_date=TO
    )
    gross = service.analyse(
        books.firm.id,
        rows="month",
        columns=None,
        from_date=FROM,
        to_date=TO,
        net_of_returns=False,
    )
    assert net.grand_total.net == Decimal("1062")
    assert gross.grand_total.net == Decimal("1180")
    # A return is not a bill: the invoice count is unchanged.
    assert net.grand_total.invoices == 1


def test_crossed_dimensions_add_up_both_ways() -> None:
    books = _Books(_session_factory()())
    other = Product(
        firm_id=books.firm.id,
        code="SKU-2",
        name="Product Two",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    books.session.add(other)
    books.session.commit()
    _second_invoice(books, date(2026, 5, 10), other, "236")
    _second_invoice(books, WHEN, other, "118")

    result = SalesAnalysisService(books.session).analyse(
        books.firm.id, rows="product", columns="month", from_date=FROM, to_date=TO
    )

    assert len(result.rows) == 2
    assert len(result.columns) == 2
    cell_sum = sum((cell.net for cell in result.cells.values()), Decimal(0))
    assert cell_sum == result.grand_total.net == Decimal("1534")
    for key, total in result.row_totals.items():
        assert total.net == sum(
            (cell.net for (row, _), cell in result.cells.items() if row == key),
            Decimal(0),
        )
    # One invoice per cell here, but three distinct invoices in all.
    assert result.grand_total.invoices == 3
    assert [column.label for column in result.columns] == ["Apr 2026", "May 2026"]


def test_a_filter_narrows_and_drill_down_lists_exactly_the_invoices() -> None:
    books = _Books(_session_factory()())
    _second_invoice(books, date(2026, 5, 10), books.product, "236")
    service = SalesAnalysisService(books.session)

    may = service.analyse(
        books.firm.id,
        rows="customer",
        columns=None,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        filters=AnalysisFilters(product_id=books.product.id),
    )
    assert may.grand_total.net == Decimal("236")

    behind = service.invoices(
        books.firm.id,
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        filters=AnalysisFilters(customer_id=books.customer.id),
    )
    assert [net for _, net in behind] == [Decimal("236")]


def test_the_quarter_is_the_financial_year_s() -> None:
    books = _Books(_session_factory()())
    result = SalesAnalysisService(books.session).analyse(
        books.firm.id, rows="quarter", columns=None, from_date=FROM, to_date=TO
    )
    [quarter] = result.rows
    # 20 April falls in April-June: the first quarter of 2026-27.
    assert quarter.label == "Q1 2026-27"
    assert (quarter.from_date, quarter.to_date) == (date(2026, 4, 1), date(2026, 6, 30))


def test_unknown_or_repeated_dimensions_are_refused() -> None:
    books = _Books(_session_factory()())
    service = SalesAnalysisService(books.session)
    with pytest.raises(ValidationError, match="is not a dimension"):
        service.analyse(
            books.firm.id, rows="colour", columns=None, from_date=FROM, to_date=TO
        )
    with pytest.raises(ValidationError, match="different dimension"):
        service.analyse(
            books.firm.id, rows="month", columns="month", from_date=FROM, to_date=TO
        )
