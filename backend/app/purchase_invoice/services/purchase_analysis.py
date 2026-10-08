"""Purchase analysis: billed purchases by any one or two dimensions (66).

The §62 pivot for buying: rows by one dimension, optional columns by another
-- product by month, supplier by product, category by quarter -- with
quantity, taxable value, input tax, total billed, bill count and average rate
per unit, and totals both ways.

**Billed purchases**: approved and closed supplier bills dated in the period.
**Net of returns** (the default) takes off the completed purchase returns
dated in the same period. Grouped in SQL, with the same time buckets as the
sales analysis.

Two more bases (RPT-2, decision A122): **received** reads completed goods
receipts -- what arrived, billed or not -- and **ordered** reads purchase
orders approved or further on, never a draft, one awaiting approval or a
cancelled one. Nothing is netted off either. The **rate trend** lists one
product's billed rate bill by bill, so a buyer sees a supplier's price creep.

Every value is in **rupees** (D-BUY-35): a bill, an order or a return in
another currency (PG-12) counts at its own rate, and a receipt at its order's,
which is the rate its stock was valued at. Quantities are never converted.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, String, cast, func, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.branches.models import Branch
from app.core.exceptions import ValidationError
from app.finance.currency import rupee_rate_sql
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.products.models import Product, ProductCategory
from app.products.models.goods_type import GENERAL_GOODS, GoodsType
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
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

ENTITY_DIMENSIONS = (
    "product",
    "category",
    "goods_type",
    "supplier",
    "supplier_category",
    "branch",
)
DIMENSIONS = TIME_DIMENSIONS + ENTITY_DIMENSIONS
BILLED = ("APPROVED", "CLOSED")
RETURNED = ("COMPLETED", "CLOSED")
RECEIVED = ("COMPLETED", "CLOSED")
#: An order is placed once approved; before that it is a request.
UNPLACED = ("DRAFT", "SUBMITTED", "CANCELLED")
BASES = ("billed", "received", "ordered")
#: The document each basis counts, and the kinds it sums.
_KINDS = {"billed": "bill", "received": "receipt", "ordered": "order"}


@dataclass(frozen=True)
class RatePoint:
    """One billed line of a product: when, from whom, how many, at what rate."""

    bill_id: UUID
    bill_number: str
    bill_date: date
    supplier_id: UUID
    supplier_name: str
    quantity: Decimal
    #: Taxable value per unit -- net of discounts, before tax.
    rate: Decimal


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
        basis: str = "billed",
    ) -> SalesAnalysis:
        """Return the pivot for the period; the shape the sales one has.

        Raises:
            ValidationError: For an unknown dimension or basis, the same
                dimension on both axes, or a period that runs backwards.

        """
        if basis not in BASES:
            raise ValidationError(
                f"{basis} is not a basis. Use one of " + ", ".join(BASES) + "."
            )
        counted = _KINDS[basis]
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
        kinds: tuple[str, ...] = (
            (("bill", "return") if net_of_returns else ("bill",))
            if basis == "billed"
            else (counted,)
        )
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
            firm_id, rows, None, from_date, to_date, chosen, counted
        ):
            row_totals.setdefault(row_key, Cell()).invoices = count
        for _, column_key, count in self._bill_counts(
            firm_id, None, columns, from_date, to_date, chosen, counted
        ):
            column_totals.setdefault(column_key, Cell()).invoices = count
        for _, _, count in self._bill_counts(
            firm_id, None, None, from_date, to_date, chosen, counted
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
            select(
                PurchaseInvoice,
                func.sum(PurchaseInvoiceLine.net_amount * self._rupees("bill")),
            )
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

    def rate_trend(
        self,
        firm_id: UUID,
        *,
        product_id: UUID,
        from_date: date,
        to_date: date,
        supplier_id: UUID | None = None,
    ) -> list[RatePoint]:
        """List one product's billed rate, bill by bill, oldest first (RPT-2).

        A bill carrying the product on two lines contributes their weighted
        rate, so the trend shows what each purchase cost rather than how
        the lines were typed. Free goods (no quantity) are left out.

        Raises:
            ValidationError: If the period runs backwards.

        """
        if from_date > to_date:
            raise ValidationError("The period must not run backwards.")
        quantity = func.sum(PurchaseInvoiceLine.current_invoice_quantity)
        taxable = func.sum(
            (PurchaseInvoiceLine.net_amount - PurchaseInvoiceLine.tax_amount)
            * self._rupees("bill")
        )
        query = (
            select(
                PurchaseInvoice.id,
                PurchaseInvoice.invoice_number,
                PurchaseInvoice.invoice_date,
                Vendor.id,
                Vendor.name,
                quantity,
                taxable,
            )
            .select_from(PurchaseInvoice)
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            )
            .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
            .where(
                *self._bill_scope(firm_id, from_date, to_date),
                PurchaseInvoiceLine.product_id == product_id,
                *(
                    []
                    if supplier_id is None
                    else [PurchaseInvoice.vendor_id == supplier_id]
                ),
            )
            .group_by(
                PurchaseInvoice.id,
                PurchaseInvoice.invoice_number,
                PurchaseInvoice.invoice_date,
                Vendor.id,
                Vendor.name,
            )
            .having(quantity > 0)
            .order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.invoice_number)
        )
        points: list[RatePoint] = []
        for bill_id, number, on, vendor_id, name, units, value in self._session.execute(
            query
        ).all():
            units_d = Decimal(str(units))
            points.append(
                RatePoint(
                    bill_id=bill_id,
                    bill_number=number,
                    bill_date=on,
                    supplier_id=vendor_id,
                    supplier_name=name,
                    quantity=units_d,
                    rate=(Decimal(str(value or 0)) / units_d).quantize(
                        Decimal("0.0001")
                    ),
                )
            )
        return points

    # ------------------------------------------------------------------

    def _order_scope(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> list[ColumnElement[bool]]:
        return [
            PurchaseOrder.firm_id == firm_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status.not_in(UNPLACED),
            PurchaseOrder.purchase_date >= from_date,
            PurchaseOrder.purchase_date <= to_date,
            PurchaseOrderLine.is_deleted.is_(False),
        ]

    def _receipt_scope(
        self, firm_id: UUID, from_date: date, to_date: date
    ) -> list[ColumnElement[bool]]:
        return [
            GoodsReceipt.firm_id == firm_id,
            GoodsReceipt.is_deleted.is_(False),
            GoodsReceipt.status.in_(RECEIVED),
            GoodsReceipt.receipt_date >= from_date,
            GoodsReceipt.receipt_date <= to_date,
            GoodsReceiptLine.is_deleted.is_(False),
        ]

    def _from(
        self,
        kind: str,
        query: Select[Any],
        firm_id: UUID,
        from_date: date,
        to_date: date,
    ) -> tuple[Select[Any], list[ColumnElement[bool]]]:
        """Join the query to the kind's header and lines; return it and its scope."""
        if kind == "bill":
            return query.select_from(PurchaseInvoice).join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.purchase_invoice_id == PurchaseInvoice.id,
            ), self._bill_scope(firm_id, from_date, to_date)
        if kind == "order":
            return query.select_from(PurchaseOrder).join(
                PurchaseOrderLine,
                PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
            ), self._order_scope(firm_id, from_date, to_date)
        if kind == "receipt":
            return query.select_from(GoodsReceipt).join(
                GoodsReceiptLine,
                GoodsReceiptLine.goods_receipt_id == GoodsReceipt.id,
            ), self._receipt_scope(firm_id, from_date, to_date)
        return query.select_from(PurchaseReturn).join(
            PurchaseReturnLine,
            PurchaseReturnLine.purchase_return_id == PurchaseReturn.id,
        ), [
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.is_deleted.is_(False),
            PurchaseReturn.status.in_(RETURNED),
            PurchaseReturn.return_date >= from_date,
            PurchaseReturn.return_date <= to_date,
            PurchaseReturnLine.is_deleted.is_(False),
        ]

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

    @staticmethod
    def _rupees(kind: str) -> ColumnElement[Any]:
        """Return the rupees one unit of a document of this kind is worth."""
        if kind == "bill":
            return rupee_rate_sql(
                PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
            )
        if kind == "order":
            return rupee_rate_sql(
                PurchaseOrder.currency_code, PurchaseOrder.exchange_rate
            )
        if kind == "receipt":
            # A receipt carries no currency of its own: its order's.
            ordered = PurchaseOrder.__table__.alias("receipt_order")
            return func.coalesce(
                select(rupee_rate_sql(ordered.c.currency_code, ordered.c.exchange_rate))
                .where(ordered.c.id == GoodsReceipt.purchase_order_id)
                .scalar_subquery(),
                1,
            )
        return rupee_rate_sql(
            PurchaseReturn.currency_code, PurchaseReturn.exchange_rate
        )

    def _sources(self, kind: str) -> dict[str, Any]:
        """Return the columns each kind contributes, under one set of names.

        The three values are in rupees; the quantity is as entered.
        """
        source = self._columns(kind)
        rupees = self._rupees(kind)
        return {
            **source,
            **{name: source[name] * rupees for name in ("taxable", "tax", "net")},
        }

    def _columns(self, kind: str) -> dict[str, Any]:
        """Return each kind's columns as its documents hold them."""
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
        if kind == "order":
            return {
                "date": PurchaseOrder.purchase_date,
                "product": PurchaseOrderLine.product_id,
                "supplier": PurchaseOrder.vendor_id,
                "branch": PurchaseOrder.branch_id,
                "document": PurchaseOrder.id,
                "quantity": PurchaseOrderLine.ordered_quantity,
                "taxable": PurchaseOrderLine.net_amount - PurchaseOrderLine.tax_amount,
                "tax": PurchaseOrderLine.tax_amount,
                "net": PurchaseOrderLine.net_amount,
            }
        if kind == "receipt":
            return {
                "date": GoodsReceipt.receipt_date,
                "product": GoodsReceiptLine.product_id,
                "supplier": GoodsReceipt.vendor_id,
                "branch": GoodsReceipt.branch_id,
                "document": GoodsReceipt.id,
                "quantity": GoodsReceiptLine.current_receipt_quantity,
                "taxable": GoodsReceiptLine.net_amount - GoodsReceiptLine.tax_amount,
                "tax": GoodsReceiptLine.tax_amount,
                "net": GoodsReceiptLine.net_amount,
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
        if dimension == "goods_type":
            return cast(Product.goods_type_id, String)
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
        if "goods_type_id" in filters:
            clauses.append(Product.goods_type_id == filters["goods_type_id"])
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
        query, scope = self._from(kind, query, firm_id, from_date, to_date)
        query = (
            query.join(Product, Product.id == source["product"])
            .join(Vendor, Vendor.id == source["supplier"])
            .where(*scope, *self._filter_clauses(kind, filters))
            .group_by(row_expr, column_expr)
        )
        sign = Decimal("-1") if kind == "return" else Decimal("1")
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
                invoices=int(count or 0) if kind != "return" else 0,
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
        kind: str = "bill",
    ) -> list[tuple[str, str, int]]:
        """Count distinct documents of the basis per row, per column or overall."""
        source = self._sources(kind)
        row_expr = self._dimension(kind, rows).label("row_key")
        column_expr = self._dimension(kind, columns).label("column_key")
        query, scope = self._from(
            kind,
            select(
                row_expr, column_expr, func.count(func.distinct(source["document"]))
            ),
            firm_id,
            from_date,
            to_date,
        )
        query = (
            query.join(Product, Product.id == source["product"])
            .join(Vendor, Vendor.id == source["supplier"])
            .where(*scope, *self._filter_clauses(kind, filters))
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
        # A product with no goods type is General, not unfiled (backlog 89).
        unfiled = GENERAL_GOODS if dimension == "goods_type" else "(none)"
        result = [
            AnalysisKey(key, labels.get(key, "") or (key if key else unfiled))
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
            "goods_type": (GoodsType, GoodsType.name),
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
