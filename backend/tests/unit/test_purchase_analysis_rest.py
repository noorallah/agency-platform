"""Purchase analysis, the rest (RPT-2): received and ordered, rate, last year.

Received reads completed goods receipts, ordered reads purchase orders that
were placed -- never a draft, one awaiting approval or a cancelled one. Every
figure carries its average rate per unit, and the rate trend lists one
product's billed rate bill by bill.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.api.router import purchase_analysis, purchase_rate_trend
from app.purchase_invoice.services.purchase_analysis import PurchaseAnalysisService
from tests.unit.test_purchase_analysis import _bill, _product
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)


def _scope(books: _Books) -> ResolvedFirmScope:
    actor = books.actor_id
    return ResolvedFirmScope(
        principal=Principal(
            subject=actor,
            roles=frozenset(),
            permissions=frozenset({"PURCHASE_VIEW"}),
            claims=TokenClaims(
                sub=str(actor),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                roles=[],
            ),
        ),
        firm_id=books.firm.id,
    )


def _order(books: _Books, product: Product, status: str, net: str) -> None:
    order = PurchaseOrder(
        firm_id=books.firm.id,
        branch_id=books.branch_id,
        warehouse_id=uuid4(),
        vendor_id=books.vendor.id,
        po_number=f"PO-{uuid4().hex[:6]}",
        purchase_date=WHEN,
        status=status,
    )
    books.session.add(order)
    books.session.flush()
    value = Decimal(net)
    books.session.add(
        PurchaseOrderLine(
            purchase_order_id=order.id,
            firm_id=books.firm.id,
            line_number=1,
            product_id=product.id,
            ordered_quantity=Decimal("10"),
            tax_amount=value * 18 / 118,
            net_amount=value,
        )
    )
    books.session.commit()


def _receipt(books: _Books, product: Product, status: str, net: str) -> None:
    receipt = GoodsReceipt(
        firm_id=books.firm.id,
        purchase_order_id=uuid4(),
        purchase_order_number="PO",
        vendor_id=books.vendor.id,
        branch_id=books.branch_id,
        warehouse_id=uuid4(),
        grn_number=f"GR-{uuid4().hex[:6]}",
        receipt_date=WHEN,
        status=status,
    )
    books.session.add(receipt)
    books.session.flush()
    value = Decimal(net)
    books.session.add(
        GoodsReceiptLine(
            goods_receipt_id=receipt.id,
            firm_id=books.firm.id,
            line_number=1,
            purchase_order_line_id=uuid4(),
            purchase_order_line_number=1,
            product_id=product.id,
            ordered_quantity=Decimal("4"),
            current_receipt_quantity=Decimal("4"),
            accepted_quantity=Decimal("4"),
            warehouse_id=receipt.warehouse_id,
            tax_amount=value * 18 / 118,
            net_amount=value,
        )
    )
    books.session.commit()


def _grand(books: _Books, basis: str) -> tuple[Decimal, Decimal, int]:
    result = PurchaseAnalysisService(books.session).analyse(
        books.firm.id,
        rows="product",
        columns=None,
        from_date=FROM,
        to_date=TO,
        basis=basis,
    )
    total = result.grand_total
    return total.quantity, total.net, total.invoices


def test_ordered_counts_placed_orders_only() -> None:
    books = _Books(_session_factory()())
    product = _product(books, "A")
    for status, net in (
        ("APPROVED", "118"),
        ("RECEIVED", "236"),
        ("DRAFT", "999"),
        ("SUBMITTED", "999"),
        ("CANCELLED", "999"),
    ):
        _order(books, product, status, net)

    assert _grand(books, "ordered") == (Decimal("20"), Decimal("354"), 2)


def test_received_counts_completed_receipts_only() -> None:
    books = _Books(_session_factory()())
    product = _product(books, "A")
    _receipt(books, product, "COMPLETED", "472")
    _receipt(books, product, "DRAFT", "999")
    _receipt(books, product, "CANCELLED", "999")

    assert _grand(books, "received") == (Decimal("4"), Decimal("472"), 1)


def test_an_unknown_basis_is_refused() -> None:
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError):
        _grand(books, "invoiced")


def test_every_figure_carries_its_average_rate() -> None:
    books = _Books(_session_factory()())
    product = _product(books, "A")
    _bill(books, "PI-1", product, "1180")  # 5 units, taxable 1000

    response = purchase_analysis(
        _scope(books),
        rows="product",
        from_date=FROM,
        to_date=TO,
        db=books.session,
    )

    assert response.data is not None
    assert response.data.grand_total.average_rate == Decimal("200.00")


def test_last_year_is_filed_under_this_years_keys() -> None:
    books = _Books(_session_factory()())
    product = _product(books, "A")
    _bill(books, "PI-1", product, "1180")

    response = purchase_analysis(
        _scope(books),
        rows="month",
        from_date=date(2027, 4, 1),
        to_date=date(2027, 4, 30),
        compare_previous_year=True,
        db=books.session,
    )

    assert response.data is not None
    assert response.data.grand_total.net == Decimal("0.00")
    previous = response.data.previous
    assert previous is not None
    assert previous.row_totals["2027-04"].net == Decimal("1180.00")


def test_the_rate_trend_lists_each_bill_oldest_first() -> None:
    books = _Books(_session_factory()())
    product, other = _product(books, "A"), _product(books, "B")
    _bill(books, "PI-1", product, "1180")  # 200 a unit
    _bill(books, "PI-2", product, "1298")  # 220 a unit
    _bill(books, "PI-3", other, "590")

    response = purchase_rate_trend(
        _scope(books),
        product_id=product.id,
        from_date=FROM,
        to_date=TO,
        db=books.session,
    )

    assert response.data is not None
    assert [(p.bill_number, p.rate) for p in response.data] == [
        ("PI-1", Decimal("200.0000")),
        ("PI-2", Decimal("220.0000")),
    ]
    assert {p.supplier_name for p in response.data} == {books.vendor.name}
