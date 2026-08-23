"""Turn a quotation into the offer a customer is sent.

An offer that could not be sent as a document was the odd gap: a firm could
compose a quotation, price it, tax it and show it on screen, and then had no
way to put it in front of the customer.

A quotation asks nobody for money and certifies nothing, so it carries no bank
block, no due date and no reverse-charge declaration. What it does carry, and
what no other document here has, is **how long the prices stand** — a quotation
without that is one the firm is still bound by next year.
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
    firm_party,
    load_template,
)
from app.products.models import Product
from app.quotation.models import SalesQuotation, SalesQuotationLine
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_QUOTATION"
DEFAULT_TITLE = "QUOTATION"


class QuotationPrintService:
    """Render one quotation as the document the customer reads."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the quotation lives on."""
        self._session = session

    def render(self, quotation_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        row = self._session.scalar(
            select(SalesQuotation).where(
                SalesQuotation.id == quotation_id,
                SalesQuotation.firm_id == firm_scope,
                SalesQuotation.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Quotation not found.")

        pdf = InvoicePdfRenderer(self._template(firm_scope)).render(
            self._document(row, firm_scope=firm_scope)
        )
        safe = row.quotation_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's quotation template, or a sensible default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            # An offer collects nothing and certifies nothing.
            fallback=TemplateSettings(
                title_text=DEFAULT_TITLE,
                declaration=None,
                show_bank_details=False,
            ),
        )

    def _document(self, row: SalesQuotation, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, the goods offered and how long the price holds."""
        lines = list(
            self._session.scalars(
                select(SalesQuotationLine)
                .where(
                    SalesQuotationLine.sales_quotation_id == row.id,
                    SalesQuotationLine.is_deleted.is_(False),
                )
                .order_by(SalesQuotationLine.line_number.asc())
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
            )
            for line in lines
        ]

        references: list[tuple[str, str]] = [
            # The one field a quotation has that no other document does.
            ("Prices stand until", row.valid_until.strftime("%d %b %Y")),
        ]
        if row.customer_reference:
            references.append(("Your reference", row.customer_reference))
        if row.payment_terms:
            references.append(("Payment terms", row.payment_terms))
        if row.delivery_terms:
            references.append(("Delivery terms", row.delivery_terms))

        return InvoiceDocument(
            number=row.quotation_number,
            date=row.quotation_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=firm_party(firm_scope),
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
            party_labels=("OFFERED TO", "SHIP TO"),
            # An offer states what it would cost, not what tax was charged.
            show_tax_summary=False,
            show_supply_terms=False,
            number_label="Quotation no.",
            date_label="Quotation date",
            words_label="QUOTED VALUE, IN WORDS",
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
