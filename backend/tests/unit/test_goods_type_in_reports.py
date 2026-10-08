"""Goods type as a dimension of the reports and a filter of the list (89).

The schema stores the goods type on the product so that "all Medicine stock"
and "sales by goods type" read one indexed column. These pin the reports that
group by it -- the sales and purchase analyses -- the stock reports that state
it per item, and the product list's filter. A product with no goods type is
General everywhere: General is the absence of a type, not a row.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.inventory.services.stock_ageing import StockAgeingService
from app.inventory.services.stock_valuation import StockValuationService
from app.products.models import Product
from app.products.models.goods_type import GoodsType
from app.products.schemas import ProductListFilters
from app.products.services import ProductService
from app.purchase_invoice.services.purchase_analysis import PurchaseAnalysisService
from app.sales_invoice.services.sales_analysis import (
    AnalysisFilters,
    SalesAnalysisService,
)
from tests.unit import test_credit_note as selling
from tests.unit import test_settlements as buying
from tests.unit.test_opening_stock_import_file import _ON
from tests.unit.test_purchase_analysis import _bill
from tests.unit.test_purchase_analysis import _product as _bought_product
from tests.unit.test_sales_analysis import _second_invoice
from tests.unit.test_stock_valuation import _stocked

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)


def _goods_type(session: Session, name: str) -> GoodsType:
    """Add one shared goods type."""
    row = GoodsType(code=name.upper(), name=name)
    session.add(row)
    session.flush()
    return row


def _typed(session: Session, firm_id: UUID, code: str, kind: GoodsType) -> Product:
    """Add one product filed under a goods type."""
    product = Product(
        firm_id=firm_id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        goods_type_id=kind.id,
    )
    session.add(product)
    session.commit()
    return product


def _file_rice_under(session: Session, firm_id: UUID, kind: GoodsType) -> None:
    """Give the stocked firm's rice a goods type and leave its oil General."""
    rice = session.scalar(
        select(Product).where(Product.firm_id == firm_id, Product.code == "RICE")
    )
    assert rice is not None
    rice.goods_type_id = kind.id
    session.commit()


def test_sales_are_grouped_by_goods_type_and_none_reads_general() -> None:
    books = selling._Books(selling._session_factory()())
    medicine = _goods_type(books.session, "Medicine")
    tablet = _typed(books.session, books.firm.id, "TAB-1", medicine)
    _second_invoice(books, date(2026, 5, 10), tablet, "236")
    service = SalesAnalysisService(books.session)

    result = service.analyse(
        books.firm.id, rows="goods_type", columns="month", from_date=FROM, to_date=TO
    )

    labels = {row.label: row.key for row in result.rows}
    assert set(labels) == {"General", "Medicine"}
    # The product the books came with has no type: General, keyed by nothing.
    assert labels["General"] == ""
    assert result.row_totals[str(medicine.id)].net == Decimal("236")
    assert result.row_totals[""].net == Decimal("1180")
    assert result.grand_total.net == Decimal("1416")
    assert result.row_totals[str(medicine.id)].invoices == 1

    narrowed = service.analyse(
        books.firm.id,
        rows="product",
        columns=None,
        from_date=FROM,
        to_date=TO,
        filters=AnalysisFilters(goods_type_id=medicine.id),
    )
    assert [row.label for row in narrowed.rows] == ["TAB-1 Product TAB-1"]
    behind = service.invoices(
        books.firm.id,
        from_date=FROM,
        to_date=TO,
        filters=AnalysisFilters(goods_type_id=medicine.id),
    )
    assert [net for _, net in behind] == [Decimal("236")]


def test_goods_type_cannot_sit_on_both_axes() -> None:
    books = selling._Books(selling._session_factory()())
    with pytest.raises(ValidationError):
        SalesAnalysisService(books.session).analyse(
            books.firm.id,
            rows="goods_type",
            columns="goods_type",
            from_date=FROM,
            to_date=TO,
        )


def test_purchases_are_grouped_by_goods_type_and_none_reads_general() -> None:
    books = buying._Books(buying._session_factory()())
    paint = _goods_type(books.session, "Paint")
    tin = _typed(books.session, books.firm.id, "TIN-1", paint)
    plain = _bought_product(books, "PLAIN")
    _bill(books, "PI-1", tin, "1180")
    _bill(books, "PI-2", plain, "590")
    service = PurchaseAnalysisService(books.session)

    result = service.analyse(
        books.firm.id, rows="goods_type", columns=None, from_date=FROM, to_date=TO
    )

    assert {row.label: result.row_totals[row.key].net for row in result.rows} == {
        "General": Decimal("590"),
        "Paint": Decimal("1180"),
    }
    narrowed = service.analyse(
        books.firm.id,
        rows="product",
        columns=None,
        from_date=FROM,
        to_date=TO,
        filters={"goods_type_id": paint.id},
    )
    assert [row.label for row in narrowed.rows] == ["TIN-1 Product TIN-1"]


def test_the_stock_reports_state_the_goods_type_of_each_item() -> None:
    session, firm = _stocked()
    _file_rice_under(session, firm.id, _goods_type(session, "Food"))
    expected = {"RICE": "Food", "OIL": "General"}

    valued = StockValuationService(session).valuation(firm.id, on=_ON)
    assert {
        row.product_code: row.goods_type for row in valued if row.row_type == "ITEM"
    } == expected
    # A total is not an item and belongs to no goods type.
    assert {row.goods_type for row in valued if row.row_type != "ITEM"} == {""}

    ageing = StockAgeingService(session)
    aged = ageing.ageing(firm.id, on=_ON)
    assert {row.product_code: row.goods_type for row in aged} == expected
    dead = ageing.slow_moving(firm.id, on=_ON, days=90, dead_only=True)
    assert {row.product_code: row.goods_type for row in dead} == expected


def test_the_product_list_filters_on_goods_type_and_on_general() -> None:
    session, firm = _stocked()
    food = _goods_type(session, "Food")
    other = _goods_type(session, "Paint")
    _file_rice_under(session, firm.id, food)

    def codes(filters: ProductListFilters) -> set[str]:
        """Return the codes one filter lists, checked against its count."""
        rows, total = ProductService(session).list_products(
            firm_scope=firm.id,
            filters=filters,
            page=1,
            page_size=50,
            search=None,
            sort_by="code",
            descending=False,
        )
        assert total == len(rows)
        return {row.code for row in rows}

    assert codes(ProductListFilters(goods_type_id=food.id)) == {"RICE"}
    assert codes(ProductListFilters(goods_type_id=other.id)) == set()
    # The firm also files a phone and a syrup it holds no stock of.
    everything = codes(ProductListFilters())
    assert {"RICE", "OIL"} <= everything
    assert codes(ProductListFilters(general_goods=True)) == everything - {"RICE"}
    # A type nobody holds lists nothing rather than everything.
    assert codes(ProductListFilters(goods_type_id=uuid4())) == set()
