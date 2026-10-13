"""Sales analysis: billed sales by any one or two dimensions (backlog 62).

Billed sales are approved and closed invoices; net of returns takes off the
approved credit notes and completed returns dated in the same period. Totals
both ways add up, and the invoices behind a cell are exactly those summed.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.products.models import Product
from app.products.models.brand import Brand, Principal
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services.sales_analysis import (
    BILLED,
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


@pytest.mark.parametrize(
    ("on", "label"),
    [
        (date(2026, 6, 30), "Q1 2026-27"),
        (date(2026, 7, 1), "Q2 2026-27"),
        (date(2026, 12, 15), "Q3 2026-27"),
        (date(2027, 1, 5), "Q4 2026-27"),
        (date(2027, 3, 31), "Q4 2026-27"),
    ],
)
def test_every_month_lands_in_its_quarter(on: date, label: str) -> None:
    """June was rounded into Q2 by true division (found on WHOLE01)."""
    books = _Books(_session_factory()())
    _second_invoice(books, on, books.product, "118")
    result = SalesAnalysisService(books.session).analyse(
        books.firm.id, rows="quarter", columns=None, from_date=on, to_date=on
    )
    assert [row.label for row in result.rows] == [label]


class _Varied:
    """Books whose invoices differ on every dimension the list can be cut by."""

    def __init__(self) -> None:
        """Add a second product, customer and branch, and more invoices."""
        self.books = _Books(_session_factory()())
        session, firm_id = self.books.session, self.books.firm.id
        self.principal = Principal(firm_id=firm_id, code="PR-1", name="Principal One")
        session.add(self.principal)
        session.flush()
        self.brand = Brand(
            firm_id=firm_id, name="Brand One", principal_id=self.principal.id
        )
        self.loose_brand = Brand(firm_id=firm_id, name="Brand Loose")
        session.add_all([self.brand, self.loose_brand])
        session.flush()
        self.category_id, self.goods_type_id, self.group_id = (
            uuid4(),
            uuid4(),
            uuid4(),
        )
        self.salesman_id, self.territory_id, self.route_id, self.branch_id = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        self.filed = Product(
            firm_id=firm_id,
            code="SKU-2",
            name="Product Two",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            category_id=self.category_id,
            goods_type_id=self.goods_type_id,
            brand_id=self.brand.id,
        )
        self.loose = Product(
            firm_id=firm_id,
            code="SKU-3",
            name="Product Three",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            brand_id=self.loose_brand.id,
        )
        self.grouped = Customer(
            firm_id=firm_id,
            code="C2",
            customer_type="BUSINESS",
            name="Customer Two",
            display_name="Customer Two",
            currency_code="INR",
            status="ACTIVE",
            customer_group_id=self.group_id,
        )
        session.add_all([self.filed, self.loose, self.grouped])
        session.commit()
        plain = self.books.product
        # Two lines, of two products: a product filter takes one of them.
        self.bill("SI-A", date(2026, 5, 4), [(plain, "118"), (self.filed, "59.50")])
        self.bill(
            "SI-B",
            date(2026, 5, 4),
            [(self.filed, "236.25")],
            customer_id=self.grouped.id,
            salesman_id=self.salesman_id,
            territory_id=self.territory_id,
            route_id=self.route_id,
        )
        self.bill(
            "SI-C", date(2026, 5, 2), [(self.loose, "70")], branch_id=self.branch_id
        )
        self.bill("SI-D", date(2026, 5, 9), [(self.filed, "11")], status="CLOSED")
        # Not billed, and outside the month: neither is behind any cell.
        self.bill("SI-E", date(2026, 5, 5), [(self.filed, "500")], status="DRAFT")
        self.bill("SI-F", date(2026, 6, 1), [(self.filed, "900")])
        # A line taken off an invoice no longer counts towards it.
        removed = self.bill("SI-G", date(2026, 5, 6), [(plain, "40"), (plain, "7")])
        last = session.scalars(
            select(SalesInvoiceLine)
            .where(SalesInvoiceLine.sales_invoice_id == removed)
            .order_by(SalesInvoiceLine.line_number.desc())
        ).first()
        assert last is not None
        last.is_deleted = True
        session.commit()

    def bill(
        self,
        number: str,
        on: date,
        lines: list[tuple[Product, str]],
        *,
        status: str = "APPROVED",
        customer_id: UUID | None = None,
        branch_id: UUID | None = None,
        salesman_id: UUID | None = None,
        territory_id: UUID | None = None,
        route_id: UUID | None = None,
    ) -> UUID:
        """Add one invoice of the given lines and return its id."""
        books = self.books
        invoice = SalesInvoice(
            firm_id=books.firm.id,
            customer_id=customer_id or books.customer.id,
            branch_id=branch_id or books.branch.id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
            invoice_number=number,
            invoice_date=on,
            status=status,
            grand_total=sum((Decimal(net) for _, net in lines), Decimal("0")),
        )
        books.session.add(invoice)
        books.session.flush()
        for position, (product, net) in enumerate(lines, start=1):
            value = Decimal(net)
            books.session.add(
                SalesInvoiceLine(
                    sales_invoice_id=invoice.id,
                    firm_id=books.firm.id,
                    line_number=position,
                    source_document_type="SALES_ORDER",
                    source_document_id=uuid4(),
                    source_document_number="SO-X",
                    source_document_line_id=uuid4(),
                    source_document_line_number=position,
                    product_id=product.id,
                    delivered_quantity=Decimal("1"),
                    current_invoice_quantity=Decimal("1"),
                    unit_price=value,
                    gross_amount=value,
                    tax_amount=Decimal("0"),
                    net_amount=value,
                )
            )
        books.session.commit()
        return UUID(str(invoice.id))

    def as_it_was_read(
        self, filters: AnalysisFilters
    ) -> list[tuple[UUID, str, date, UUID, Decimal]]:
        """Answer with the statement the list ran before D-PERF-5.

        The whole invoice, with the product, its brand and the customer
        joined to every line: the reference the narrower read must equal.
        """
        service = SalesAnalysisService(self.books.session)
        query = (
            select(SalesInvoice, func.sum(SalesInvoiceLine.net_amount))
            .join(
                SalesInvoiceLine, SalesInvoiceLine.sales_invoice_id == SalesInvoice.id
            )
            .join(Product, Product.id == SalesInvoiceLine.product_id)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(
                SalesInvoice.firm_id == self.books.firm.id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status.in_(BILLED),
                SalesInvoice.invoice_date >= date(2026, 5, 1),
                SalesInvoice.invoice_date <= date(2026, 5, 31),
                SalesInvoiceLine.is_deleted.is_(False),
                *service._filter_clauses("invoice", filters),
            )
            .group_by(SalesInvoice.id)
            .order_by(SalesInvoice.invoice_date, SalesInvoice.invoice_number)
        )
        return [
            (
                invoice.id,
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.customer_id,
                Decimal(str(net or 0)),
            )
            for invoice, net in self.books.session.execute(query).all()
        ]

    def read(
        self, filters: AnalysisFilters | None
    ) -> list[tuple[UUID, str, date, UUID, Decimal]]:
        """Answer with the service, flattened to what the route returns."""
        return [
            (
                invoice.id,
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.customer_id,
                net,
            )
            for invoice, net in SalesAnalysisService(self.books.session).invoices(
                self.books.firm.id,
                from_date=date(2026, 5, 1),
                to_date=date(2026, 5, 31),
                filters=filters,
            )
        ]


#: Every filter the route takes, by the attribute of ``_Varied`` holding a
#: value some invoice matches.
_FILTERS = {
    "product_id": "filed",
    "category_id": "category_id",
    "goods_type_id": "goods_type_id",
    "brand_id": "brand",
    "principal_id": "principal",
    "customer_id": "grouped",
    "customer_group_id": "group_id",
    "salesman_id": "salesman_id",
    "territory_id": "territory_id",
    "route_id": "route_id",
    "branch_id": "branch_id",
}


def _value(varied: _Varied, attribute: str) -> UUID:
    """Read a filter's value: an id held directly, or a row's id."""
    held = getattr(varied, attribute)
    return held if isinstance(held, UUID) else UUID(str(held.id))


def test_the_filters_tested_are_every_filter_the_route_takes() -> None:
    """A filter added to the analysis joins the comparison below."""
    assert set(_FILTERS) == set(AnalysisFilters.__dataclass_fields__)


def test_the_invoices_behind_a_cell_are_listed_in_order_with_their_share() -> None:
    """Unfiltered: billed invoices of the month, by date then number."""
    varied = _Varied()
    assert WHEN.month != 5, "the fixture's own invoice must fall outside the month"

    listed = varied.read(None)

    assert [(number, net) for _, number, _, _, net in listed] == [
        ("SI-C", Decimal("70")),
        ("SI-A", Decimal("177.5")),
        ("SI-B", Decimal("236.25")),
        ("SI-G", Decimal("40")),
        ("SI-D", Decimal("11")),
    ]
    assert listed == varied.as_it_was_read(AnalysisFilters())


@pytest.mark.parametrize("name", sorted(_FILTERS))
def test_each_filter_lists_what_it_listed_before(name: str) -> None:
    """Narrower columns and fewer joins, the same invoices and the same sums."""
    varied = _Varied()
    filters = AnalysisFilters(**{name: _value(varied, _FILTERS[name])})

    listed = varied.read(filters)

    assert listed, f"{name} matched nothing, so the comparison proves nothing"
    assert len(listed) < 5, f"{name} narrowed nothing"
    assert listed == varied.as_it_was_read(filters)
    # A value no invoice carries lists nothing, as before.
    nobody = AnalysisFilters(**{name: uuid4()})
    assert varied.read(nobody) == varied.as_it_was_read(nobody) == []


def test_filters_together_list_what_they_listed_before() -> None:
    """A product filter with a master's: one line of a two-line invoice."""
    varied = _Varied()
    filters = AnalysisFilters(
        product_id=UUID(str(varied.filed.id)),
        principal_id=UUID(str(varied.principal.id)),
        customer_group_id=varied.group_id,
        category_id=varied.category_id,
    )

    assert [(number, net) for _, number, _, _, net in varied.read(filters)] == [
        ("SI-B", Decimal("236.25"))
    ]
    assert varied.read(filters) == varied.as_it_was_read(filters)
    only_filed = AnalysisFilters(product_id=UUID(str(varied.filed.id)))
    assert ("SI-A", Decimal("59.5")) in [
        (number, net) for _, number, _, _, net in varied.read(only_filed)
    ]


def test_the_list_is_one_narrow_statement_however_many_invoices() -> None:
    """Four columns and a sum, once; no master joined that no filter reads."""
    varied = _Varied()
    statements: list[str] = []

    def _record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001 - SQLAlchemy's own signature
    ) -> None:
        """Keep every statement the engine is handed."""
        statements.append(statement)

    engine = varied.books.session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    few = varied.read(None)
    counted_few = len(statements)
    event.remove(engine, "before_cursor_execute", _record)
    for index in range(12):
        varied.bill(f"SI-M{index:02d}", date(2026, 5, 20), [(varied.filed, "10")])
    event.listen(engine, "before_cursor_execute", _record)
    many = varied.read(None)
    by_group = varied.read(AnalysisFilters(customer_group_id=varied.group_id))
    event.remove(engine, "before_cursor_execute", _record)

    assert len(many) == len(few) + 12
    assert counted_few == 1
    assert len(statements) == 3
    plain, grouped = statements[1], statements[2]
    assert "grand_total" not in plain, "the whole invoice row is selected again"
    for master in ("products", "brands", "customers"):
        assert f"JOIN {master}" not in plain
    assert "JOIN customers" in grouped
    assert "JOIN products" not in grouped
    assert [number for _, number, _, _, _ in by_group] == ["SI-B"]
