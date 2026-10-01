"""Purchase analysis: billed purchases by any one or two dimensions (66).

The sales pivot's twin for buying: approved and closed bills, net of the
completed purchase returns dated in the period, totals both ways, and the
bills behind a cell.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.products.models import Product
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.services.purchase_analysis import PurchaseAnalysisService
from tests.unit.test_settlements import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)


def _bill(books: _Books, number: str, product: Product, net: str) -> None:
    """Add an approved bill of one line at 18% tax."""
    invoice = books.purchase_invoice(number, net)
    value = Decimal(net)
    books.session.add(
        PurchaseInvoiceLine(
            purchase_invoice_id=invoice.id,
            firm_id=books.firm.id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=uuid4(),
            source_document_number="GR-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=product.id,
            received_quantity=Decimal("5"),
            current_invoice_quantity=Decimal("5"),
            unit_price=value / 5,
            gross_amount=value * 100 / 118,
            tax_amount=value * 18 / 118,
            net_amount=value,
        )
    )
    books.session.commit()


def _product(books: _Books, code: str) -> Product:
    product = Product(
        firm_id=books.firm.id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    books.session.add(product)
    books.session.commit()
    return product


def test_bills_by_product_with_totals() -> None:
    books = _Books(_session_factory()())
    one, two = _product(books, "A"), _product(books, "B")
    _bill(books, "PI-1", one, "1180")
    _bill(books, "PI-2", two, "590")

    result = PurchaseAnalysisService(books.session).analyse(
        books.firm.id, rows="product", columns=None, from_date=FROM, to_date=TO
    )

    assert [row.label for row in result.rows] == ["A Product A", "B Product B"]
    assert result.grand_total.net == Decimal("1770")
    assert result.grand_total.invoices == 2


def test_supplier_by_month_adds_up_both_ways() -> None:
    books = _Books(_session_factory()())
    one = _product(books, "A")
    _bill(books, "PI-1", one, "1180")
    _bill(books, "PI-2", one, "236")

    result = PurchaseAnalysisService(books.session).analyse(
        books.firm.id, rows="supplier", columns="month", from_date=FROM, to_date=TO
    )

    [row] = result.rows
    assert row.label == "Vendor One"
    assert sum((c.net for c in result.cells.values()), Decimal(0)) == Decimal("1416")
    assert result.row_totals[row.key].invoices == 2


def test_the_bills_behind_a_cell_are_exactly_those_summed() -> None:
    books = _Books(_session_factory()())
    one, two = _product(books, "A"), _product(books, "B")
    _bill(books, "PI-1", one, "1180")
    _bill(books, "PI-2", two, "590")

    behind = PurchaseAnalysisService(books.session).bills(
        books.firm.id, from_date=FROM, to_date=TO, filters={"product_id": two.id}
    )
    assert [(bill.invoice_number, net) for bill, net in behind] == [
        ("PI-2", Decimal("590"))
    ]


def test_unknown_dimensions_are_refused() -> None:
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError, match="is not a dimension"):
        PurchaseAnalysisService(books.session).analyse(
            books.firm.id, rows="salesman", columns=None, from_date=FROM, to_date=TO
        )
