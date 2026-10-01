"""Purchase analysis: billed purchases by any one or two dimensions (66).

The §62 pivot for buying: rows by one dimension, optional columns by another
-- product by month, supplier by product, category by quarter -- with
quantity, taxable value, input tax, total billed, bill count and average rate
per unit, and totals both ways.

**Billed purchases**: approved and closed supplier bills dated in the period.
**Net of returns** (the default) takes off the completed purchase returns
dated in the same period. Grouped in SQL, with the same time buckets as the
sales analysis.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, func, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.branches.models import Branch
from app.core.exceptions import ValidationError
from app.products.models import Product, ProductCategory
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.sales_invoice.services.sales_analysis import (
    TIME_DIMENSIONS,
    AnalysisKey,
    Cell,
    SalesAnalysis,
)
from app.sales_invoice.services.sales_analysis import _bucket as time_bucket
from app.sales_invoice.services.sales_analysis import _time_key as time_key
from app.vendors.models import Vendor, VendorCategory

ENTITY_DIMENSIONS = ("product", "category", "supplier", "supplier_category", "branch")
DIMENSIONS = TIME_DIMENSIONS + ENTITY_DIMENSIONS
BILLED = ("APPROVED", "CLOSED")
RETURNED = ("COMPLETED", "CLOSED")


class PurchaseAnalysisService:
    """Group billed purchases by one or two dimensions."""

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
        filters: dict[str, UUID] | None = None,
        net_of_returns: bool = True,
    ) -> SalesAnalysis:
        """Return the pivot for the period; the shape the sales one has.

        Raises:
            ValidationError: For an unknown dimension, the same dimension on
                both axes, or a period that runs backwards.

        """
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
        chosen = filters or {}

        cells: dict[tuple[str, str], Cell] = {}
        row_totals: dict[str, Cell] = {}
        column_totals: dict[str, Cell] = {}
        grand = Cell()
        kinds = ("bill", "return") if net_of_returns else ("bill",)
        for kind in kinds:
            for row_key, column_key, cell in self._grouped(
                kind, firm_id, rows, columns, from_date, to_date, chosen
            ):
                target = cells.setdefault((row_key, column_key), Cell())
                target.add(cell)
                target.invoices += cell.invoices
                row_totals.setdefault(row_key, Cell()).add(cell)
                column_totals.setdefault(column_key, Cell()).add(cell)
                grand.add(cell)
        for row_key, _, count in self._bill_counts(
            firm_id, rows, None, from_date, to_date, chosen
        ):
            row_totals.setdefault(row_key, Cell()).invoices = count
        for _, column_key, count in self._bill_counts(
            firm_id, None, columns, from_date, to_date, chosen
        ):
            column_totals.setdefault(column_key, Cell()).invoices = count
        for _, _, count in self._bill_counts(
            firm_id, None, None, from_date, to_date, chosen
        ):
            grand.invoices = count
        return SalesAnalysis(
            rows=self._keys(rows, list(row_totals)),
            columns=(
                self._keys(columns, list(column_totals))
                if columns is not None
                else [AnalysisKey("", "Total")]
            ),
            cells=cells,
            row_totals=row_totals,
            column_totals=column_totals,
            grand_total=grand,
        )

    def bills(
        self,
        firm_id: UUID,
        *,
        from_date: date,
        to_date: date,
        filters: dict[str, UUID] | None = None,
    ) -> list[tuple[PurchaseInvoice, Decimal]]:
        """List the bills behind a cell, with what their matching lines came to."""
        query = (
            select(PurchaseInvoice, func.sum(PurchaseInvoiceLine.net_amount))
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            )
            .join(Product, Product.id == PurchaseInvoiceLine.product_id)
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                *self._bill_scope(firm_id, from_date, to_date),
                *self._filter_clauses("bill", filters or {}),
            )
            .group_by(PurchaseInvoice.id)
            .order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.invoice_number)
        )
        return [
            (bill, Decimal(str(net or 0)))
            for bill, net in self._session.execute(query).all()
        ]

    # ------------------------------------------------------------------

    def _bill_scope(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> list[ColumnElement[bool]]:
        return [
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(BILLED),
            PurchaseInvoice.invoice_date >= from_date,
            PurchaseInvoice.invoice_date <= to_date,
            PurchaseInvoiceLine.is_deleted.is_(False),
        ]

    def _sources(self, kind: str) -> dict[str, Any]:
        """Return the columns each kind contributes, under one set of names."""
        if kind == "bill":
            return {
                "date": PurchaseInvoice.invoice_date,
                "product": PurchaseInvoiceLine.product_id,
                "supplier": PurchaseInvoice.vendor_id,
                "branch": PurchaseInvoice.branch_id,
                "document": PurchaseInvoice.id,
                "quantity": PurchaseInvoiceLine.current_invoice_quantity,
                "taxable": PurchaseInvoiceLine.net_amount
                - PurchaseInvoiceLine.tax_amount,
                "tax": PurchaseInvoiceLine.tax_amount,
                "net": PurchaseInvoiceLine.net_amount,
            }
        return {
            "date": PurchaseReturn.return_date,
            "product": PurchaseReturnLine.product_id,
            "supplier": PurchaseReturn.vendor_id,
            "branch": PurchaseReturn.branch_id,
            "document": PurchaseReturn.id,
            "quantity": PurchaseReturnLine.current_return_quantity,
            "taxable": PurchaseReturnLine.net_amount - PurchaseReturnLine.tax_amount,
            "tax": PurchaseReturnLine.tax_amount,
            "net": PurchaseReturnLine.net_amount,
        }

    def _dimension(self, kind: str, dimension: str | None) -> ColumnElement[Any]:
        if dimension is None:
            return literal("")
        source = self._sources(kind)
        if dimension in TIME_DIMENSIONS:
            return time_bucket(self._session, dimension, source["date"])
        if dimension == "category":
            return cast(Product.category_id, String)
        if dimension == "supplier_category":
            return cast(Vendor.category_id, String)
        return cast(source[dimension], String)

    def _filter_clauses(
        self, kind: str, filters: dict[str, UUID]
    ) -> list[ColumnElement[bool]]:
        source = self._sources(kind)
        clauses: list[ColumnElement[bool]] = []
        for name in ("product", "supplier", "branch"):
            if f"{name}_id" in filters:
                clauses.append(source[name] == filters[f"{name}_id"])
        if "category_id" in filters:
            clauses.append(Product.category_id == filters["category_id"])
        if "supplier_category_id" in filters:
            clauses.append(Vendor.category_id == filters["supplier_category_id"])
        return clauses

    def _grouped(
        self,
        kind: str,
        firm_id: UUID,
        rows: str,
        columns: str | None,
        from_date: date,
        to_date: date,
        filters: dict[str, UUID],
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
        )
        if kind == "bill":
            query = query.select_from(PurchaseInvoice).join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            )
            scope = self._bill_scope(firm_id, from_date, to_date)
        else:
            query = query.select_from(PurchaseReturn).join(
                PurchaseReturnLine,
                PurchaseReturnLine.purchase_return_id == PurchaseReturn.id,
            )
            scope = [
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status.in_(RETURNED),
                PurchaseReturn.return_date >= from_date,
                PurchaseReturn.return_date <= to_date,
                PurchaseReturnLine.is_deleted.is_(False),
            ]
        query = (
            query.join(Product, Product.id == source["product"])
            .join(Vendor, Vendor.id == source["supplier"])
            .where(*scope, *self._filter_clauses(kind, filters))
            .group_by(row_expr, column_expr)
        )
        sign = Decimal("1") if kind == "bill" else Decimal("-1")
        results: list[tuple[str, str, Cell]] = []
        for (
            row_key,
            column_key,
            quantity,
            taxable,
            tax,
            net,
            count,
        ) in self._session.execute(query).all():
            cell = Cell(
                quantity=sign * Decimal(str(quantity or 0)),
                taxable=sign * Decimal(str(taxable or 0)),
                tax=sign * Decimal(str(tax or 0)),
                net=sign * Decimal(str(net or 0)),
                invoices=int(count or 0) if kind == "bill" else 0,
            )
            results.append((str(row_key or ""), str(column_key or ""), cell))
        return results

    def _bill_counts(
        self,
        firm_id: UUID,
        rows: str | None,
        columns: str | None,
        from_date: date,
        to_date: date,
        filters: dict[str, UUID],
    ) -> list[tuple[str, str, int]]:
        """Count distinct bills per row, per column or overall."""
        row_expr = self._dimension("bill", rows).label("row_key")
        column_expr = self._dimension("bill", columns).label("column_key")
        query = (
            select(row_expr, column_expr, func.count(func.distinct(PurchaseInvoice.id)))
            .select_from(PurchaseInvoice)
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            )
            .join(Product, Product.id == PurchaseInvoiceLine.product_id)
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                *self._bill_scope(firm_id, from_date, to_date),
                *self._filter_clauses("bill", filters),
            )
            .group_by(row_expr, column_expr)
        )
        return [
            (str(row or ""), str(column or ""), int(count or 0))
            for row, column, count in self._session.execute(query).all()
        ]

    def _keys(self, dimension: str, keys: list[str]) -> list[AnalysisKey]:
        if dimension in TIME_DIMENSIONS:
            return sorted(
                (time_key(dimension, key) for key in keys), key=lambda k: k.key
            )
        labels = self._labels(dimension, [UUID(key) for key in keys if key])
        result = [
            AnalysisKey(key, labels.get(key, "") or (key if key else "(none)"))
            for key in keys
        ]
        return sorted(result, key=lambda item: item.label.lower())

    def _labels(self, dimension: str, ids: list[UUID]) -> dict[str, str]:
        if not ids:
            return {}
        if dimension == "product":
            return {
                str(i): f"{code} {name}"
                for i, code, name in self._session.execute(
                    select(Product.id, Product.code, Product.name).where(
                        Product.id.in_(ids)
                    )
                ).all()
            }
        model, column = {
            "category": (ProductCategory, ProductCategory.name),
            "supplier": (Vendor, Vendor.name),
            "supplier_category": (VendorCategory, VendorCategory.name),
            "branch": (Branch, Branch.name),
        }[dimension]
        return {
            str(i): name
            for i, name in self._session.execute(
                select(model.id, column).where(model.id.in_(ids))
            ).all()
        }
