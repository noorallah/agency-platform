"""Sales analysis: billed sales by any one or two dimensions (backlog 62).

Tally's item analysis, Zoho's sales by item / customer / salesperson: rows by
one dimension, optional columns by another -- product by month, customer by
product, salesman by quarter -- with quantity, taxable value, tax, net sales,
invoice count and average bill in every cell, and totals both ways.

**Billed sales**: approved and closed invoices dated in the period. **Net of
returns** (the default) takes off the approved credit notes and completed
sales returns dated in the same period, as GSTR-3B takes them off: a return
reduces the month it happened in, not the month of the sale it returns.

**Orders booked** (``basis="ordered"``, RPT-1) reads sales orders instead:
every order approved or further on, cancelled ones left out, dated in the
period -- what the field force booked, whether or not it has been billed.
Nothing is netted off an order.

**Margin** (RPT-1) is what billed lines fetched over what the goods cost, at
the cost the dispatch recorded on the line. A line with no recorded cost is
left out of the margin altogether -- NULL cost is not zero cost -- so the
margin is measured on ``costed``, the taxable value of the lines that carry
one. Returns and notes record no cost and do not move it.

Grouped in SQL, so a year of a large firm is one query per document kind;
time buckets are computed per dialect, and the financial-year quarter is the
Indian one (April-June is Q1).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, String, case, cast, func, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.branches.models import Branch
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ValidationError
from app.credit_note.models import CreditNote, CreditNoteLine
from app.customer_debit_note.models import CustomerDebitNote, CustomerDebitNoteLine
from app.customers.models import Customer, CustomerGroup
from app.products.models import Product, ProductCategory
from app.products.models.brand import Brand, Principal
from app.sales.models.territory import SalesTerritoryNode, TerritoryRouteProfile
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.billing import billed_part
from app.sales_return.models import SalesReturn, SalesReturnLine

ZERO = Decimal("0")
TIME_DIMENSIONS = ("day", "week", "month", "quarter", "year")
ENTITY_DIMENSIONS = (
    "product",
    "category",
    "brand",
    "principal",
    "customer",
    "customer_group",
    "salesman",
    "territory",
    "route",
    "branch",
)
DIMENSIONS = TIME_DIMENSIONS + ENTITY_DIMENSIONS
BILLED = ("APPROVED", "CLOSED")
BASES = ("billed", "ordered")
#: An order is booked once approved; a draft is not yet a booking and a
#: cancelled one never became one.
UNBOOKED = ("DRAFT", "CANCELLED")
RETURNED = ("COMPLETED", "CLOSED")


@dataclass
class Cell:
    """The figures for one cell, row total or column total."""

    quantity: Decimal = ZERO
    taxable: Decimal = ZERO
    tax: Decimal = ZERO
    net: Decimal = ZERO
    #: What the goods cost, from the lines that recorded a cost, and those
    #: lines' taxable value -- the margin is `costed - cost`.
    cost: Decimal = ZERO
    costed: Decimal = ZERO
    #: Distinct invoices. Never summed across cells -- one invoice of two
    #: products sits in two cells of a row -- so totals take theirs from a
    #: query of their own.
    invoices: int = 0

    def add(self, other: "Cell") -> None:
        """Fold another cell's money into this one (not its invoice count)."""
        self.quantity += other.quantity
        self.taxable += other.taxable
        self.tax += other.tax
        self.net += other.net
        self.cost += other.cost
        self.costed += other.costed


@dataclass
class AnalysisKey:
    """One row or column heading, with the dates it covers for a period."""

    key: str
    label: str
    from_date: date | None = None
    to_date: date | None = None


@dataclass
class SalesAnalysis:
    """The pivot: headings both ways, the cells, and the totals."""

    rows: list[AnalysisKey]
    columns: list[AnalysisKey]
    cells: dict[tuple[str, str], Cell]
    row_totals: dict[str, Cell]
    column_totals: dict[str, Cell]
    grand_total: Cell


@dataclass(frozen=True)
class AnalysisFilters:
    """Narrow the analysis to some values of any dimension."""

    product_id: UUID | None = None
    category_id: UUID | None = None
    #: The brand and the principal behind it (MST-1).
    brand_id: UUID | None = None
    principal_id: UUID | None = None
    customer_id: UUID | None = None
    customer_group_id: UUID | None = None
    salesman_id: UUID | None = None
    territory_id: UUID | None = None
    route_id: UUID | None = None
    branch_id: UUID | None = None


def _year_month(
    session: Session, column: ColumnElement[Any]
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    """Return integer year and month expressions for a date, per dialect."""
    if session.get_bind().dialect.name == "postgresql":
        return (
            cast(func.extract("year", column), Integer),
            cast(func.extract("month", column), Integer),
        )
    return (
        cast(func.strftime("%Y", column), Integer),
        cast(func.strftime("%m", column), Integer),
    )


def _bucket(
    session: Session, dimension: str, column: ColumnElement[Any]
) -> ColumnElement[Any]:
    """Return the SQL expression naming the time bucket a date falls in."""
    year, month = _year_month(session, column)
    fy_start = year - case((month < 4, 1), else_=0)
    postgres = session.get_bind().dialect.name == "postgresql"
    if dimension == "day":
        return cast(column, String)
    if dimension == "month":
        return (
            func.to_char(column, "YYYY-MM")
            if postgres
            else func.strftime("%Y-%m", column)
        )
    if dimension == "week":
        return (
            func.to_char(column, 'IYYY-"W"IW')
            if postgres
            else func.strftime("%Y-W%W", column)
        )
    # Floor division: in SQLAlchemy 2.0 `/` between integers is true
    # division, and June's 2/3 + 1 rounded to the second quarter.
    quarter = cast((month + 8) % 12 // 3 + 1, Integer)
    if dimension == "quarter":
        return (
            func.concat(
                literal("Q"),
                cast(quarter, String),
                literal(" "),
                cast(fy_start, String),
            )
            if postgres
            else (
                literal("Q")
                + cast(quarter, String)
                + literal(" ")
                + cast(fy_start, String)
            )
        )
    return cast(fy_start, String)  # "year": the financial year's starting year


def _time_key(dimension: str, key: str) -> AnalysisKey:
    """Label a time bucket and say which dates it covers."""
    if dimension == "day":
        day = date.fromisoformat(key)
        return AnalysisKey(key, f"{day:%d %b %Y}", day, day)
    if dimension == "month":
        year, month = (int(part) for part in key.split("-"))
        first = date(year, month, 1)
        following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return AnalysisKey(key, f"{first:%b %Y}", first, following - timedelta(days=1))
    if dimension == "year":
        start = int(key)
        return AnalysisKey(
            key,
            f"{start}-{(start + 1) % 100:02d}",
            date(start, 4, 1),
            date(start + 1, 3, 31),
        )
    if dimension == "quarter":
        number, start_text = key.lstrip("Q").split(" ")
        start, quarter = int(start_text), int(number)
        first_month = 4 + (quarter - 1) * 3
        year = start + (first_month - 1) // 12
        month = (first_month - 1) % 12 + 1
        first = date(year, month, 1)
        end_month = month + 2
        end_year = year + (end_month - 1) // 12
        end_month = (end_month - 1) % 12 + 1
        following = (
            date(end_year + 1, 1, 1)
            if end_month == 12
            else date(end_year, end_month + 1, 1)
        )
        return AnalysisKey(
            key,
            f"Q{quarter} {start}-{(start + 1) % 100:02d}",
            first,
            following - timedelta(days=1),
        )
    return AnalysisKey(key, key)  # week: labelled as the bucket reads


class SalesAnalysisService:
    """Group billed sales by one or two dimensions."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def analyse(
        self,
        firm_id: UUID,
        *,
        rows: str,
        columns: str | None,
        from_date: date,
        to_date: date,
        filters: AnalysisFilters | None = None,
        net_of_returns: bool = True,
        basis: str = "billed",
    ) -> SalesAnalysis:
        """Return the pivot for the period.

        Raises:
            ValidationError: For an unknown dimension or basis, the same
                dimension on both axes, or a period that runs backwards.

        """
        if basis not in BASES:
            raise ValidationError(
                f"{basis} is not a basis. Use one of " + ", ".join(BASES) + "."
            )
        for dimension in (rows, columns):
            if dimension is not None and dimension not in DIMENSIONS:
                raise ValidationError(
                    f"{dimension} is not a dimension. Use one of "
                    + ", ".join(DIMENSIONS)
                    + "."
                )
        if columns == rows:
            raise ValidationError("Choose a different dimension for the columns.")
        if from_date > to_date:
            raise ValidationError("The period must not run backwards.")
        filters = filters or AnalysisFilters()

        grouped: list[tuple[str, str, Cell]] = []
        # A debit note to a customer is more of a sale already made (backlog
        # 77 row 5), so it counts whether or not returns are netted off.
        counted = "order" if basis == "ordered" else "invoice"
        kinds: tuple[str, ...] = (
            ("order",)
            if basis == "ordered"
            else ("invoice", "debit_note", "credit_note", "sales_return")
        )
        for kind in kinds:
            if kind in ("credit_note", "sales_return") and not net_of_returns:
                continue
            grouped.extend(
                self._grouped(kind, firm_id, rows, columns, from_date, to_date, filters)
            )

        cells: dict[tuple[str, str], Cell] = {}
        row_totals: dict[str, Cell] = {}
        column_totals: dict[str, Cell] = {}
        grand = Cell()
        for row_key, column_key, cell in grouped:
            target = cells.setdefault((row_key, column_key), Cell())
            target.add(cell)
            target.invoices += cell.invoices
            row_totals.setdefault(row_key, Cell()).add(cell)
            column_totals.setdefault(column_key, Cell()).add(cell)
            grand.add(cell)
        # Distinct invoices for the totals, each from its own grouping.
        for row_key, _, count in self._invoice_counts(
            firm_id, rows, None, from_date, to_date, filters, counted
        ):
            row_totals.setdefault(row_key, Cell()).invoices = count
        for _, column_key, count in self._invoice_counts(
            firm_id, None, columns, from_date, to_date, filters, counted
        ):
            column_totals.setdefault(column_key, Cell()).invoices = count
        for _, _, count in self._invoice_counts(
            firm_id, None, None, from_date, to_date, filters, counted
        ):
            grand.invoices = count

        return SalesAnalysis(
            rows=self._keys(firm_id, rows, list(row_totals)),
            columns=(
                self._keys(firm_id, columns, list(column_totals))
                if columns is not None
                else [AnalysisKey("", "Total")]
            ),
            cells=cells,
            row_totals=row_totals,
            column_totals=column_totals,
            grand_total=grand,
        )

    def invoices(
        self,
        firm_id: UUID,
        *,
        from_date: date,
        to_date: date,
        filters: AnalysisFilters | None = None,
    ) -> list[tuple[SalesInvoice, Decimal]]:
        """List the invoices behind a cell, with what each contributed.

        The desktop narrows the filters and the dates to the cell clicked;
        the invoices are exactly the ones whose lines that cell summed.
        """
        filters = filters or AnalysisFilters()
        line_net = func.sum(SalesInvoiceLine.net_amount)
        query = (
            select(SalesInvoice, line_net)
            .join(
                SalesInvoiceLine, SalesInvoiceLine.sales_invoice_id == SalesInvoice.id
            )
            .join(Product, Product.id == SalesInvoiceLine.product_id)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(
                *self._invoice_scope(firm_id, from_date, to_date),
                *self._filter_clauses("invoice", filters),
            )
            .group_by(SalesInvoice.id)
            .order_by(SalesInvoice.invoice_date, SalesInvoice.invoice_number)
        )
        return [
            (invoice, Decimal(str(net or 0)))
            for invoice, net in self._session.execute(query).all()
        ]

    # ------------------------------------------------------------------

    def _invoice_scope(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> list[ColumnElement[bool]]:
        return [
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status.in_(BILLED),
            SalesInvoice.invoice_date >= from_date,
            SalesInvoice.invoice_date <= to_date,
            SalesInvoiceLine.is_deleted.is_(False),
        ]

    def _order_scope(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> list[ColumnElement[bool]]:
        return [
            SalesOrder.firm_id == firm_id,
            SalesOrder.is_deleted.is_(False),
            SalesOrder.status.not_in(UNBOOKED),
            SalesOrder.order_date >= from_date,
            SalesOrder.order_date <= to_date,
            SalesOrderLine.is_deleted.is_(False),
        ]

    def _sources(self, kind: str) -> dict[str, Any]:
        """Return the columns each document kind contributes, under one set of names."""
        if kind == "order":
            return {
                "date": SalesOrder.order_date,
                "product": SalesOrderLine.product_id,
                "customer": SalesOrder.customer_id,
                "salesman": SalesOrder.salesman_id,
                "territory": SalesOrder.territory_id,
                "route": SalesOrder.route_id,
                "branch": SalesOrder.branch_id,
                "document": SalesOrder.id,
                "quantity": SalesOrderLine.quantity,
                "taxable": SalesOrderLine.net_amount - SalesOrderLine.tax_amount,
                "tax": SalesOrderLine.tax_amount,
                "net": SalesOrderLine.net_amount,
            }
        if kind == "invoice":
            return {
                "date": SalesInvoice.invoice_date,
                "product": SalesInvoiceLine.product_id,
                "customer": SalesInvoice.customer_id,
                "salesman": SalesInvoice.salesman_id,
                "territory": SalesInvoice.territory_id,
                "route": SalesInvoice.route_id,
                "branch": SalesInvoice.branch_id,
                "document": SalesInvoice.id,
                "quantity": SalesInvoiceLine.current_invoice_quantity,
                "taxable": SalesInvoiceLine.net_amount - SalesInvoiceLine.tax_amount,
                "tax": SalesInvoiceLine.tax_amount,
                "net": SalesInvoiceLine.net_amount,
            }
        if kind == "debit_note":
            return {
                "date": CustomerDebitNote.debit_note_date,
                "product": CustomerDebitNoteLine.product_id,
                "customer": CustomerDebitNote.customer_id,
                "salesman": SalesInvoice.salesman_id,
                "territory": SalesInvoice.territory_id,
                "route": SalesInvoice.route_id,
                "branch": SalesInvoice.branch_id,
                "document": CustomerDebitNote.id,
                # Value, not units: the goods were counted on the invoice.
                "quantity": literal(0),
                "taxable": CustomerDebitNoteLine.taxable_amount,
                "tax": CustomerDebitNoteLine.tax_amount,
                "net": CustomerDebitNoteLine.total_amount,
            }
        if kind == "credit_note":
            return {
                "date": CreditNote.credit_note_date,
                "product": CreditNoteLine.product_id,
                "customer": CreditNote.customer_id,
                "salesman": SalesInvoice.salesman_id,
                "territory": SalesInvoice.territory_id,
                "route": SalesInvoice.route_id,
                "branch": SalesInvoice.branch_id,
                "document": CreditNote.id,
                "quantity": CreditNoteLine.quantity,
                "taxable": CreditNoteLine.taxable_amount,
                "tax": CreditNoteLine.tax_amount,
                "net": CreditNoteLine.total_amount,
            }
        return {
            "date": SalesReturn.return_date,
            "product": SalesReturnLine.product_id,
            "customer": SalesReturn.customer_id,
            "salesman": literal(None),
            "territory": literal(None),
            "route": literal(None),
            "branch": SalesReturn.branch_id,
            "document": SalesReturn.id,
            # The billed part only: goods that came back before billing were
            # never in billed sales to be taken out of them (D-SELL-55).
            "quantity": billed_part(SalesReturnLine.current_return_quantity),
            "taxable": billed_part(
                SalesReturnLine.net_amount - SalesReturnLine.tax_amount
            ),
            "tax": billed_part(SalesReturnLine.tax_amount),
            "net": billed_part(SalesReturnLine.net_amount),
        }

    def _dimension(self, kind: str, dimension: str | None) -> ColumnElement[Any]:
        if dimension is None:
            return literal("")
        source = self._sources(kind)
        if dimension in TIME_DIMENSIONS:
            return _bucket(self._session, dimension, source["date"])
        if dimension == "category":
            return cast(Product.category_id, String)
        if dimension == "brand":
            return cast(Product.brand_id, String)
        if dimension == "principal":
            return cast(Brand.principal_id, String)
        if dimension == "customer_group":
            return cast(Customer.customer_group_id, String)
        return cast(source[dimension], String)

    def _filter_clauses(
        self, kind: str, filters: AnalysisFilters
    ) -> list[ColumnElement[bool]]:
        source = self._sources(kind)
        clauses: list[ColumnElement[bool]] = []
        pairs = {
            "product": filters.product_id,
            "customer": filters.customer_id,
            "salesman": filters.salesman_id,
            "territory": filters.territory_id,
            "route": filters.route_id,
            "branch": filters.branch_id,
        }
        for name, value in pairs.items():
            if value is not None:
                clauses.append(source[name] == value)
        if filters.category_id is not None:
            clauses.append(Product.category_id == filters.category_id)
        if filters.brand_id is not None:
            clauses.append(Product.brand_id == filters.brand_id)
        if filters.principal_id is not None:
            clauses.append(Brand.principal_id == filters.principal_id)
        if filters.customer_group_id is not None:
            clauses.append(Customer.customer_group_id == filters.customer_group_id)
        return clauses

    def _grouped(
        self,
        kind: str,
        firm_id: UUID,
        rows: str,
        columns: str | None,
        from_date: date,
        to_date: date,
        filters: AnalysisFilters,
    ) -> list[tuple[str, str, Cell]]:
        source = self._sources(kind)
        row_expr = self._dimension(kind, rows).label("row_key")
        column_expr = self._dimension(kind, columns).label("column_key")
        query = select(
            row_expr,
            column_expr,
            func.sum(source["quantity"]),
            func.sum(source["taxable"]),
            func.sum(source["tax"]),
            func.sum(source["net"]),
            func.count(func.distinct(source["document"])),
            *self._cost_columns(kind),
        )
        if kind == "order":
            query = query.select_from(SalesOrder).join(
                SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id
            )
            scope = self._order_scope(firm_id, from_date, to_date)
        elif kind == "invoice":
            query = query.select_from(SalesInvoice).join(
                SalesInvoiceLine, SalesInvoiceLine.sales_invoice_id == SalesInvoice.id
            )
            scope = self._invoice_scope(firm_id, from_date, to_date)
        elif kind == "debit_note":
            query = (
                query.select_from(CustomerDebitNote)
                .join(
                    CustomerDebitNoteLine,
                    CustomerDebitNoteLine.debit_note_id == CustomerDebitNote.id,
                )
                .join(
                    SalesInvoice, SalesInvoice.id == CustomerDebitNote.sales_invoice_id
                )
            )
            scope = [
                CustomerDebitNote.firm_id == firm_id,
                CustomerDebitNote.is_deleted.is_(False),
                CustomerDebitNote.status == "APPROVED",
                CustomerDebitNote.debit_note_date >= from_date,
                CustomerDebitNote.debit_note_date <= to_date,
                CustomerDebitNoteLine.is_deleted.is_(False),
            ]
        elif kind == "credit_note":
            query = (
                query.select_from(CreditNote)
                .join(CreditNoteLine, CreditNoteLine.credit_note_id == CreditNote.id)
                .join(SalesInvoice, SalesInvoice.id == CreditNote.sales_invoice_id)
            )
            scope = [
                CreditNote.firm_id == firm_id,
                CreditNote.is_deleted.is_(False),
                CreditNote.status == "APPROVED",
                CreditNote.credit_note_date >= from_date,
                CreditNote.credit_note_date <= to_date,
                CreditNoteLine.is_deleted.is_(False),
            ]
        else:
            query = query.select_from(SalesReturn).join(
                SalesReturnLine, SalesReturnLine.sales_return_id == SalesReturn.id
            )
            scope = [
                SalesReturn.firm_id == firm_id,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(RETURNED),
                SalesReturn.return_date >= from_date,
                SalesReturn.return_date <= to_date,
                SalesReturnLine.is_deleted.is_(False),
            ]
        query = (
            query.join(Product, Product.id == source["product"])
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .join(Customer, Customer.id == source["customer"])
            .where(*scope, *self._filter_clauses(kind, filters))
            .group_by(row_expr, column_expr)
        )
        sign = (
            Decimal("1")
            if kind in ("order", "invoice", "debit_note")
            else Decimal("-1")
        )
        results: list[tuple[str, str, Cell]] = []
        for (
            row_key,
            column_key,
            quantity,
            taxable,
            tax,
            net,
            count,
            cost,
            costed,
        ) in self._session.execute(query).all():
            cell = Cell(
                quantity=sign * Decimal(str(quantity or 0)),
                taxable=sign * Decimal(str(taxable or 0)),
                tax=sign * Decimal(str(tax or 0)),
                net=sign * Decimal(str(net or 0)),
                cost=Decimal(str(cost or 0)),
                costed=Decimal(str(costed or 0)),
            )
            # Returns change the money but are not bills: the invoice count
            # and the average bill count invoices (or, booked, orders) only.
            if kind in ("invoice", "order"):
                cell.invoices = int(count or 0)
            results.append((str(row_key or ""), str(column_key or ""), cell))
        return results

    def _cost_columns(self, kind: str) -> list[ColumnElement[Any]]:
        """Return the summed cost and costed value; only invoice lines carry one."""
        if kind != "invoice":
            return [literal(0), literal(0)]
        recorded = SalesInvoiceLine.cost_amount.is_not(None)
        return [
            func.sum(case((recorded, SalesInvoiceLine.cost_amount), else_=0)),
            func.sum(
                case(
                    (
                        recorded,
                        SalesInvoiceLine.net_amount - SalesInvoiceLine.tax_amount,
                    ),
                    else_=0,
                )
            ),
        ]

    def _invoice_counts(
        self,
        firm_id: UUID,
        rows: str | None,
        columns: str | None,
        from_date: date,
        to_date: date,
        filters: AnalysisFilters,
        kind: str = "invoice",
    ) -> list[tuple[str, str, int]]:
        """Count distinct invoices (or orders) per row, per column or overall."""
        row_expr = self._dimension(kind, rows).label("row_key")
        column_expr = self._dimension(kind, columns).label("column_key")
        if kind == "order":
            order_query = (
                select(row_expr, column_expr, func.count(func.distinct(SalesOrder.id)))
                .select_from(SalesOrder)
                .join(SalesOrderLine, SalesOrderLine.sales_order_id == SalesOrder.id)
                .join(Product, Product.id == SalesOrderLine.product_id)
                .outerjoin(Brand, Brand.id == Product.brand_id)
                .join(Customer, Customer.id == SalesOrder.customer_id)
                .where(
                    *self._order_scope(firm_id, from_date, to_date),
                    *self._filter_clauses("order", filters),
                )
                .group_by(row_expr, column_expr)
            )
            return [
                (str(row or ""), str(column or ""), int(count or 0))
                for row, column, count in self._session.execute(order_query).all()
            ]
        query = (
            select(row_expr, column_expr, func.count(func.distinct(SalesInvoice.id)))
            .select_from(SalesInvoice)
            .join(
                SalesInvoiceLine, SalesInvoiceLine.sales_invoice_id == SalesInvoice.id
            )
            .join(Product, Product.id == SalesInvoiceLine.product_id)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(
                *self._invoice_scope(firm_id, from_date, to_date),
                *self._filter_clauses("invoice", filters),
            )
            .group_by(row_expr, column_expr)
        )
        return [
            (str(row or ""), str(column or ""), int(count or 0))
            for row, column, count in self._session.execute(query).all()
        ]

    def _keys(
        self, firm_id: UUID, dimension: str, keys: Sequence[str]
    ) -> list[AnalysisKey]:
        if dimension in TIME_DIMENSIONS:
            return sorted(
                (_time_key(dimension, key) for key in keys), key=lambda k: k.key
            )
        labels = self._labels(firm_id, dimension, [key for key in keys if key])
        result = [
            AnalysisKey(key, labels.get(key, "") or (key if key else "(none)"))
            for key in keys
        ]
        return sorted(result, key=lambda item: item.label.lower())

    def _labels(self, firm_id: UUID, dimension: str, keys: list[str]) -> dict[str, str]:
        ids = [UUID(key) for key in keys]
        if not ids:
            return {}
        if dimension == "product":
            rows = self._session.execute(
                select(Product.id, Product.code, Product.name).where(
                    Product.id.in_(ids)
                )
            ).all()
            return {str(i): f"{code} {name}" for i, code, name in rows}
        if dimension == "category":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(ProductCategory.id, ProductCategory.name).where(
                        ProductCategory.id.in_(ids)
                    )
                ).all()
            }
        if dimension == "brand":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(Brand.id, Brand.name).where(Brand.id.in_(ids))
                ).all()
            }
        if dimension == "principal":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(Principal.id, Principal.name).where(Principal.id.in_(ids))
                ).all()
            }
        if dimension == "customer":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(Customer.id, Customer.display_name).where(
                        Customer.id.in_(ids)
                    )
                ).all()
            }
        if dimension == "customer_group":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(CustomerGroup.id, CustomerGroup.name).where(
                        CustomerGroup.id.in_(ids)
                    )
                ).all()
            }
        if dimension == "territory":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(SalesTerritoryNode.id, SalesTerritoryNode.name).where(
                        SalesTerritoryNode.id.in_(ids)
                    )
                ).all()
            }
        if dimension == "route":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(TerritoryRouteProfile.id, SalesTerritoryNode.name)
                    .join(
                        SalesTerritoryNode,
                        SalesTerritoryNode.id == TerritoryRouteProfile.territory_id,
                    )
                    .where(TerritoryRouteProfile.id.in_(ids))
                ).all()
            }
        if dimension == "branch":
            return {
                str(i): name
                for i, name in self._session.execute(
                    select(Branch.id, Branch.name).where(Branch.id.in_(ids))
                ).all()
            }
        # salesman: a person, from the platform store's members list.
        members = FirmMetadataReader(self._session).active_members(firm_id)
        return {
            str(member.user_id): member.full_name or member.email for member in members
        }


def year_earlier(day: date) -> date:
    """Return the same date a year earlier; 29 February becomes the 28th."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def shift_key_a_year(dimension: str | None, key: str) -> str:
    """Move a time bucket's key one year on, so last year's lands beside this.

    Comparing with last year (RPT-1) runs the same analysis a year earlier and
    files each of its buckets under the one it compares with: May 2025 under
    May 2026. An entity key -- a product, a customer -- is the same both years.
    """
    if dimension not in TIME_DIMENSIONS or not key:
        return key
    if dimension == "quarter":
        number, start = key.split(" ")
        return f"{number} {int(start) + 1}"
    if dimension == "year":
        return str(int(key) + 1)
    if dimension == "day":
        day = date.fromisoformat(key)
        try:
            return day.replace(year=day.year + 1).isoformat()
        except ValueError:
            return day.replace(year=day.year + 1, day=28).isoformat()
    year, rest = key.split("-", 1)  # month "2025-05", week "2025-W18"
    return f"{int(year) + 1}-{rest}"


def shifted_a_year(
    result: SalesAnalysis, rows: str, columns: str | None
) -> SalesAnalysis:
    """File last year's pivot under this year's keys (RPT-1).

    Cells and totals move to the key they compare with; the headings are
    re-labelled so a bucket last year had and this year has not still reads
    as this year's bucket beside an empty one.
    """

    def heading(dimension: str | None, item: AnalysisKey) -> AnalysisKey:
        if dimension not in TIME_DIMENSIONS or dimension is None:
            return item
        return _time_key(dimension, shift_key_a_year(dimension, item.key))

    def column(key: str) -> str:
        return shift_key_a_year(columns, key)

    return SalesAnalysis(
        rows=[heading(rows, item) for item in result.rows],
        columns=[heading(columns, item) for item in result.columns],
        cells={
            (shift_key_a_year(rows, row), column(col)): cell
            for (row, col), cell in result.cells.items()
        },
        row_totals={
            shift_key_a_year(rows, key): cell for key, cell in result.row_totals.items()
        },
        column_totals={column(key): cell for key, cell in result.column_totals.items()},
        grand_total=result.grand_total,
    )
