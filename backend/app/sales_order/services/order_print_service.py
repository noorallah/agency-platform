"""Turn a sales order into the order confirmation a customer is sent (MSG-4).

The quotation's layout (``quotation_print_service``), because an order
confirmation is the same kind of paper: it asks nobody for money yet and
certifies no tax, so it carries no bank block and no tax summary. What it
states is what was ordered, at what price, and when it is to be delivered.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.document_framework.services.print_support import (
    customer_party,
    load_template,
    seller_party,
)
from app.products.models import Product
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_ORDER"
DEFAULT_TITLE = "ORDER CONFIRMATION"


class SalesOrderPrintService:
    """Render one sales order as the confirmation the customer reads."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the order lives on."""
        self._session = session

    def render(self, order_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        row = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == order_id,
                SalesOrder.firm_id == firm_scope,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales order not found.")

        pdf = InvoicePdfRenderer(self._template(firm_scope)).render(
            self._document(row, firm_scope=firm_scope)
        )
        safe = row.order_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's order template, or a sensible default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            # An order confirmation collects nothing and certifies nothing.
            fallback=TemplateSettings(
                title_text=DEFAULT_TITLE,
                declaration=None,
                show_bank_details=False,
            ),
        )

    def _document(self, row: SalesOrder, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, the goods ordered and when they are due."""
        lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == row.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        products = self._products(line.product_id for line in lines)
        units = self._units(line.sales_uom_id for line in lines)

        printed = [
            InvoiceLineBlock(
                number=line.line_number,
                description=line.description
                or (
                    products[line.product_id].name
                    if line.product_id in products
                    else ""
                )
                or "",
                hsn=(
                    products[line.product_id].hsn_sac
                    if line.product_id in products
                    else None
                ),
                quantity=line.quantity,
                free_quantity=line.free_quantity,
                uom=(
                    units[line.sales_uom_id].code
                    if line.sales_uom_id in units
                    else None
                ),
                rate=line.unit_price,
                discount=line.discount_amount,
                taxable=line.gross_amount
                - line.discount_amount
                - line.bill_discount_amount,
                total=line.net_amount,
                # An order typed at shelf prices prints them beside the
                # taxable rate, as the bill does (backlog 64 row 4).
                entered_rate=line.entered_rate if row.rate_includes_tax else None,
            )
            for line in lines
        ]

        references: list[tuple[str, str]] = []
        if row.delivery_date:
            references.append(("Delivery by", row.delivery_date.strftime("%d %b %Y")))
        if row.customer_reference:
            references.append(("Your order", row.customer_reference))
        if row.payment_terms:
            references.append(("Payment terms", row.payment_terms))

        return InvoiceDocument(
            number=row.order_number,
            date=row.order_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=seller_party(self._session, firm_scope, row.branch_id),
            buyer=customer_party(self._session, row.customer_id, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            ship_to=None,
            lines=tuple(printed),
            bill_discount=row.bill_discount_amount,
            gross_before_bill_discount=row.subtotal + row.bill_discount_amount,
            taxable_total=row.subtotal,
            tax_total=row.tax_total,
            charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            references=tuple(references),
            party_labels=("ORDERED BY", "SHIP TO"),
            # An order states what it will cost, not what tax was charged.
            show_tax_summary=False,
            show_supply_terms=False,
            number_label="Order no.",
            date_label="Order date",
            words_label="ORDER VALUE, IN WORDS",
        )

    def _products(self, ids: Iterable[UUID | None]) -> dict[UUID, Product]:
        """Read the products the lines name, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(wanted))
            ).all()
        }

    def _units(self, ids: Iterable[UUID | None]) -> dict[UUID, Uom]:
        """Read the units the lines name, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Uom).where(Uom.id.in_(wanted))
            ).all()
        }
