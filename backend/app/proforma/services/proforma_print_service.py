"""Turn a proforma into the document a customer is handed (D-UI-71).

A proforma exists to be put in front of the customer -- for an advance, a
letter of credit, a purchase approval -- and it could be raised, issued and
withdrawn here and never printed or sent.

It states what a particular order will be charged and is **not a tax
invoice**: it says so across the top of every copy, carries no reverse-charge
declaration and no HSN summary, and names the order it states.
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
from app.proforma.models import ProformaInvoice, ProformaInvoiceLine, ProformaStatus
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_order.models import SalesOrder
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "PROFORMA_INVOICE"
DEFAULT_TITLE = "PROFORMA INVOICE"
#: Said across every copy: a proforma asks for nothing the books know of.
NOT_A_TAX_INVOICE = "This is not a tax invoice."
#: What a copy says when the proforma does not stand as issued.
NOT_FINAL = {
    ProformaStatus.DRAFT.value: "DRAFT - not issued. This is not a tax invoice.",
    ProformaStatus.CANCELLED.value: "WITHDRAWN. This is not a tax invoice.",
}


class ProformaPrintService:
    """Render one proforma as the document the customer reads."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the proforma lives on."""
        self._session = session

    def render(self, proforma_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        row = self._session.scalar(
            select(ProformaInvoice).where(
                ProformaInvoice.id == proforma_id,
                ProformaInvoice.firm_id == firm_scope,
                ProformaInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Proforma invoice not found.")

        pdf = InvoicePdfRenderer(self._template(firm_scope)).render(
            self.document(row, firm_scope=firm_scope)
        )
        safe = row.proforma_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's proforma template, or a sensible default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            # The bank block stays: a proforma is what an advance is paid on.
            fallback=TemplateSettings(title_text=DEFAULT_TITLE, declaration=None),
        )

    def document(self, row: ProformaInvoice, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, the goods stated and the order they belong to."""
        lines = list(
            self._session.scalars(
                select(ProformaInvoiceLine)
                .where(
                    ProformaInvoiceLine.proforma_invoice_id == row.id,
                    ProformaInvoiceLine.is_deleted.is_(False),
                )
                .order_by(ProformaInvoiceLine.line_number.asc())
            ).all()
        )
        products = self._products(line.product_id for line in lines)
        units = self._units(_unit_of(product) for product in products.values())

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
                uom=self._unit_code(products.get(line.product_id), units),
                rate=line.unit_price,
                discount=line.discount_amount,
                taxable=line.gross_amount
                - line.discount_amount
                - line.bill_discount_amount,
                total=line.net_amount,
            )
            for line in lines
        ]

        order = self._session.get(SalesOrder, row.sales_order_id)
        references: list[tuple[str, str]] = []
        if order is not None:
            references.append(("Against order", order.order_number))
        if row.valid_until is not None:
            references.append(
                ("Prices stand until", row.valid_until.strftime("%d %b %Y"))
            )
        if row.customer_reference:
            references.append(("Your reference", row.customer_reference))
        if row.payment_terms:
            references.append(("Payment terms", row.payment_terms))
        if row.delivery_terms:
            references.append(("Delivery terms", row.delivery_terms))

        return InvoiceDocument(
            number=row.proforma_number,
            date=row.proforma_date.strftime("%d %b %Y"),
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
            # The order's charges and round-off: what the total holds beyond
            # the taxable value and the tax, as the screen states them.
            charges=row.grand_total - row.subtotal - row.tax_total,
            round_off=ZERO,
            grand_total=row.grand_total,
            references=tuple(references),
            party_labels=("PROFORMA TO", "SHIP TO"),
            # A proforma states what will be charged, not tax that was.
            show_tax_summary=False,
            show_supply_terms=False,
            number_label="Proforma no.",
            date_label="Proforma date",
            words_label="PROFORMA VALUE, IN WORDS",
            not_final=NOT_FINAL.get(row.status, NOT_A_TAX_INVOICE),
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
        """Read the units the products are counted in, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Uom).where(Uom.id.in_(wanted))
            ).all()
        }

    @staticmethod
    def _unit_code(product: Product | None, units: dict[UUID, Uom]) -> str | None:
        """Return the code of the unit a product is counted in, if known."""
        unit_id = None if product is None else _unit_of(product)
        return units[unit_id].code if unit_id in units else None


def _unit_of(product: Product) -> UUID | None:
    """Return the unit a product is sold in, else the one it is stocked in."""
    return product.sales_uom_id or product.inventory_uom_id
