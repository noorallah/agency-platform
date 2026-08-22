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

from app.common.firm_metadata import platform_reader
from app.core.exceptions import ResourceNotFoundError
from app.customers.models import Customer, CustomerAddress
from app.document_framework.models import DocumentPrintTemplate
from app.firms.models import Firm
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
        row = self._session.scalar(
            select(DocumentPrintTemplate).where(
                DocumentPrintTemplate.firm_id == firm_scope,
                DocumentPrintTemplate.document_type == DOCUMENT_TYPE,
                DocumentPrintTemplate.is_deleted.is_(False),
            )
        )
        if row is None:
            # A firm that has configured nothing still prints a correct bill.
            return TemplateSettings()
        return TemplateSettings(
            title_text=row.title_text,
            accent_color=row.accent_color,
            header_note=row.header_note,
            show_bank_details=row.show_bank_details,
            bank_details=row.bank_details,
            terms=row.terms,
            declaration=row.declaration or TemplateSettings().declaration,
            jurisdiction=row.jurisdiction,
            footer_note=row.footer_note,
            signatory_text=row.signatory_text,
            show_discount_column=row.show_discount_column,
            show_batch_column=row.show_batch_column,
            show_expiry_column=row.show_expiry_column,
            copy_labels=tuple(row.copy_labels or ()),
            page_size=row.page_size,
            margin_mm=row.margin_mm,
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
                    uom=(unit.code if unit else None),
                    rate=line.unit_price,
                    discount=line.discount_amount,
                    taxable=line.gross_amount - line.discount_amount,
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
        """Return the selling firm, read from the platform store.

        `firms` exists only in the platform schema, so a tenant session cannot
        see it -- the fourth occurrence of that trap is documented in
        CLAUDE.md, and `platform_reader` is the answer to it.
        """
        with platform_reader() as platform:
            firm = platform.get(Firm, firm_scope)
            if firm is None:
                return PartyBlock(name="", address_lines=[])
            address = [
                firm.address_line1,
                ", ".join(
                    part for part in (firm.city, firm.state, firm.postal_code) if part
                ),
                firm.country,
            ]
            contact = " · ".join(
                part for part in (firm.contact_phone, firm.contact_email) if part
            )
            return PartyBlock(
                name=firm.name,
                address_lines=[line for line in address if line],
                gstin=firm.gst_number,
                pan=firm.pan_number,
                state=firm.state,
                contact=contact or None,
            )

    def _customer_block(self, customer_id: UUID, kind: str) -> PartyBlock | None:
        """Return the customer as one side of the bill."""
        customer = self._session.get(Customer, customer_id)
        if customer is None:
            return None
        address = self._session.scalar(
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.address_type == kind,
                CustomerAddress.is_deleted.is_(False),
            )
            .limit(1)
        )
        lines: list[str] = []
        state: str | None = None
        if address is not None:
            lines = [
                part
                for part in (
                    address.address_line1,
                    address.address_line2,
                    ", ".join(
                        piece
                        for piece in (address.city, address.state, address.postal_code)
                        if piece
                    ),
                )
                if part
            ]
            state = address.state
        return PartyBlock(
            name=customer.display_name or customer.name,
            address_lines=lines,
            gstin=customer.gst_number,
            pan=customer.pan_number,
            state=state,
            contact=customer.phone,
        )
