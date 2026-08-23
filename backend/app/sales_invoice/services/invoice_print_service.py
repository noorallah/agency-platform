"""Turn a stored sales invoice into the bill a customer is sent.

Everything here is read from the record. The tax components come from
`sales_invoice_line_taxes` rather than the rule engine, because rules are
effective-dated and asking again can answer differently from what the customer
was billed; the place of supply and the due date come from the invoice for the
same reason.
"""

from __future__ import annotations

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
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_INVOICE"


class SalesInvoicePrintService:
    """Render one invoice, with the firm's template around it."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the invoice lives on."""
        self._session = session

    # ------------------------------------------------------------------
    def render(self, invoice_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")

        template = self._template(firm_scope)
        document = self._document(invoice, firm_scope=firm_scope)
        pdf = InvoicePdfRenderer(template).render(document)
        safe = invoice.invoice_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's template, or the platform default."""
        return load_template(
            self._session, firm_scope=firm_scope, document_type=DOCUMENT_TYPE
        )

    def _document(self, invoice: SalesInvoice, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather every party, line and figure the bill states."""
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == invoice.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            ).all()
        )
        taxes: dict[UUID, list[SalesInvoiceLineTax]] = {}
        if lines:
            for component in self._session.scalars(
                select(SalesInvoiceLineTax)
                .where(
                    SalesInvoiceLineTax.sales_invoice_line_id.in_(
                        [line.id for line in lines]
                    ),
                    SalesInvoiceLineTax.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLineTax.sequence.asc())
            ):
                taxes.setdefault(component.sales_invoice_line_id, []).append(component)

        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            )
        }
        units = {
            unit.id: unit
            for unit in self._session.scalars(
                select(Uom).where(
                    Uom.id.in_(
                        [line.invoice_uom_id for line in lines if line.invoice_uom_id]
                        or [None]
                    )
                )
            )
        }

        printed: list[InvoiceLineBlock] = []
        for line in lines:
            product = products.get(line.product_id)
            unit = units.get(line.invoice_uom_id) if line.invoice_uom_id else None
            printed.append(
                InvoiceLineBlock(
                    number=line.line_number,
                    description=line.description
                    or (product.name if product else "")
                    or "",
                    hsn=product.hsn_sac if product else None,
                    quantity=line.current_invoice_quantity,
                    free_quantity=line.free_quantity,
                    uom=(unit.code if unit else None),
                    rate=line.unit_price,
                    discount=line.discount_amount,
                    # The line's share of any bill discount is in the taxable
                    # figure but not in the discount column: that column is
                    # what was agreed on this line, and the deduction from the
                    # whole document is stated once, in the totals.
                    taxable=line.gross_amount
                    - line.discount_amount
                    - line.bill_discount_amount,
                    total=line.net_amount,
                    batch=line.batch_number,
                    expiry=line.expiry_date.isoformat() if line.expiry_date else None,
                    taxes=tuple(
                        (item.component_code, item.percentage, item.amount)
                        for item in taxes.get(line.id, [])
                    ),
                )
            )

        return InvoiceDocument(
            number=invoice.invoice_number,
            date=invoice.invoice_date.strftime("%d %b %Y"),
            due_date=(
                invoice.due_date.strftime("%d %b %Y") if invoice.due_date else None
            ),
            place_of_supply=invoice.place_of_supply,
            reverse_charge=False,
            seller=self._seller(firm_scope),
            buyer=self._customer_block(invoice.customer_id, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            ship_to=self._customer_block(invoice.customer_id, "SHIPPING"),
            lines=tuple(printed),
            bill_discount=invoice.bill_discount_amount,
            gross_before_bill_discount=invoice.subtotal + invoice.bill_discount_amount,
            taxable_total=invoice.subtotal,
            tax_total=invoice.tax_total,
            charges=invoice.additional_charges,
            round_off=invoice.round_off,
            grand_total=invoice.grand_total,
            references=tuple(
                ("Reference", invoice.reference_number)
                for _ in (1,)
                if invoice.reference_number
            ),
        )

    def _seller(self, firm_scope: UUID) -> PartyBlock:
        """Describe the selling firm."""
        return firm_party(firm_scope)

    def _customer_block(self, customer_id: UUID, kind: str) -> PartyBlock | None:
        """Return the customer as one side of the bill."""
        return customer_party(self._session, customer_id, kind)
