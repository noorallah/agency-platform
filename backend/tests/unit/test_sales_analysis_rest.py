"""Sales analysis, the rest (RPT-1): orders booked, margin, last year, layouts.

Orders booked counts approved orders and anything further on, never a draft or
a cancelled one. Margin is measured only on the billed lines that recorded a
cost -- NULL cost is not zero cost -- and only a caller who may see cost is
shown it. Comparing with last year files the earlier year under this year's
keys. A saved layout is the person's own.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.report_layouts.api.router import (
    delete_report_layout,
    list_report_layouts,
    save_report_layout,
)
from app.report_layouts.schemas import ReportLayoutWrite
from app.sales_invoice.api.router import sales_analysis
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.services.sales_analysis import (
    SalesAnalysisService,
    shift_key_a_year,
    year_earlier,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from tests.unit.test_credit_note import _Books, _session_factory
from tests.unit.test_sales_analysis import _second_invoice

pytestmark = pytest.mark.typed_document_numbers

FROM, TO = date(2026, 4, 1), date(2027, 3, 31)
_ACTOR = UUID("00000000-0000-0000-0000-0000000000b1")


def _scope(firm_id: UUID, *codes: str, actor: UUID = _ACTOR) -> ResolvedFirmScope:
    return ResolvedFirmScope(
        principal=Principal(
            subject=actor,
            roles=frozenset(),
            permissions=frozenset({"SALES_VIEW", *codes}),
            claims=TokenClaims(
                sub=str(actor),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                roles=[],
            ),
        ),
        firm_id=firm_id,
    )


def _order(books: _Books, status: str, net: str, on: date = date(2026, 6, 1)) -> None:
    order = SalesOrder(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        warehouse_id=uuid4(),
        order_number=f"SO-{uuid4().hex[:6]}",
        order_date=on,
        status=status,
    )
    books.session.add(order)
    books.session.flush()
    value = Decimal(net)
    books.session.add(
        SalesOrderLine(
            sales_order_id=order.id,
            firm_id=books.firm.id,
            line_number=1,
            product_id=books.product.id,
            quantity=Decimal("3"),
            tax_amount=value * 18 / 118,
            net_amount=value,
        )
    )
    books.session.commit()


def test_orders_booked_count_approved_and_later_never_draft_or_cancelled() -> None:
    books = _Books(_session_factory()())
    _order(books, "APPROVED", "118")
    _order(books, "DELIVERED", "236")
    _order(books, "DRAFT", "1000")
    _order(books, "CANCELLED", "1000")

    result = SalesAnalysisService(books.session).analyse(
        books.firm.id,
        rows="product",
        columns=None,
        from_date=FROM,
        to_date=TO,
        basis="ordered",
    )

    assert result.grand_total.net == Decimal("354")
    assert result.grand_total.quantity == Decimal("6")
    assert result.grand_total.invoices == 2  # orders, counted as the documents


def test_an_unknown_basis_is_refused() -> None:
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError):
        SalesAnalysisService(books.session).analyse(
            books.firm.id,
            rows="product",
            columns=None,
            from_date=FROM,
            to_date=TO,
            basis="shipped",
        )


def test_margin_is_measured_only_on_lines_that_recorded_a_cost() -> None:
    books = _Books(_session_factory()())
    line = books.session.scalars(select(SalesInvoiceLine)).one()
    line.cost_amount = Decimal("700")  # taxable 1000
    books.session.commit()
    _second_invoice(books, date(2026, 5, 10), books.product, "236")  # no cost

    result = SalesAnalysisService(books.session).analyse(
        books.firm.id, rows="product", columns=None, from_date=FROM, to_date=TO
    )

    assert result.grand_total.cost == Decimal("700")
    assert result.grand_total.costed == Decimal("1000")
    assert result.grand_total.taxable == Decimal("1200")


def test_the_route_shows_margin_only_to_a_caller_who_may_see_cost() -> None:
    books = _Books(_session_factory()())
    line = books.session.scalars(select(SalesInvoiceLine)).one()
    line.cost_amount = Decimal("700")
    books.session.commit()

    def grand(*codes: str, basis: str = "billed") -> object:
        response = sales_analysis(
            _scope(books.firm.id, *codes),
            books.session,
            rows="product",
            from_date=FROM,
            to_date=TO,
            basis=basis,
        )
        assert response.data is not None
        return response.data.grand_total

    shown = grand("PRODUCT_VIEW_COST_PRICE")
    assert (shown.cost, shown.margin, shown.margin_percent) == (  # type: ignore[attr-defined]
        Decimal("700.00"),
        Decimal("300.00"),
        Decimal("30.00"),
    )
    hidden = grand()
    assert hidden.margin is None and hidden.cost is None  # type: ignore[attr-defined]
    # Orders carry no cost, so the margin is not offered on that basis.
    assert grand("PRODUCT_VIEW_COST_PRICE", basis="ordered").margin is None  # type: ignore[attr-defined]


def test_last_year_is_filed_under_this_years_months() -> None:
    books = _Books(_session_factory()())
    _second_invoice(books, date(2025, 5, 10), books.product, "236")

    response = sales_analysis(
        _scope(books.firm.id),
        books.session,
        rows="month",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 5, 31),
        compare_previous_year=True,
    )

    assert response.data is not None
    previous = response.data.previous
    assert previous is not None
    assert previous.row_totals["2026-05"].net == Decimal("236.00")
    assert [row.label for row in previous.rows] == ["May 2026"]
    assert previous.grand_total.net == Decimal("236.00")
    assert response.data.previous is not None and previous.previous is None


@pytest.mark.parametrize(
    ("dimension", "key", "shifted"),
    [
        ("month", "2025-05", "2026-05"),
        ("week", "2025-W18", "2026-W18"),
        ("quarter", "Q2 2025", "Q2 2026"),
        ("year", "2025", "2026"),
        ("day", "2024-02-29", "2025-02-28"),
        ("product", "abc", "abc"),
    ],
)
def test_keys_shift_a_year(dimension: str, key: str, shifted: str) -> None:
    assert shift_key_a_year(dimension, key) == shifted


def test_a_leap_day_a_year_earlier_is_the_28th() -> None:
    assert year_earlier(date(2028, 2, 29)) == date(2027, 2, 28)


def test_a_layout_is_saved_replaced_by_name_listed_and_deleted() -> None:
    books = _Books(_session_factory()())
    mine = _scope(books.firm.id)

    def save(name: str, rows: str) -> UUID:
        response = save_report_layout(
            ReportLayoutWrite(
                report_code="sales_analysis", name=name, settings={"rows": rows}
            ),
            mine,
            books.session,
        )
        assert response.data is not None
        return response.data.id

    first = save("By month", "month")
    again = save("By month", "customer")
    save("By product", "product")

    listed = list_report_layouts(mine, "sales_analysis", books.session).data or []
    assert first == again
    assert [(row.name, row.settings["rows"]) for row in listed] == [
        ("By month", "customer"),
        ("By product", "product"),
    ]
    assert list_report_layouts(mine, "purchase_analysis", books.session).data == []

    someone_else = _scope(books.firm.id, actor=uuid4())
    assert list_report_layouts(someone_else, "sales_analysis", books.session).data == []
    with pytest.raises(ResourceNotFoundError):
        delete_report_layout(first, someone_else, books.session)

    delete_report_layout(first, mine, books.session)
    assert [
        row.name
        for row in list_report_layouts(mine, "sales_analysis", books.session).data or []
    ] == ["By product"]
