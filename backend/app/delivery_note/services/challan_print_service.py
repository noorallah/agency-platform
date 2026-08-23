"""Turn a delivery note into the challan that travels with the goods.

The document a driver carries. Goods moving without paperwork is the problem
this exists to solve, and until 2026-08-23 the platform could print a tax
invoice and a purchase order and nothing else -- so a firm could dispatch stock
and had nothing to send with it.

A challan is not a bill. It states what left, for whom, and on whose vehicle;
it does not ask for money. So it carries no bank block, no due date, no
HSN-wise tax summary and no "amount payable" -- but it does carry the value of
what is moving, because that is what makes it usable as the document behind an
e-way bill.

Free goods are stated the way the invoice states them: the quantity column
reads "10 + 1 free", because the storekeeper at the other end counts eleven.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.document_framework.services.print_support import (
    customer_party,
    firm_party,
    load_template,
)
from app.products.models import Product
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "DELIVERY_NOTE"
#: A challan accompanies goods; it is not a tax invoice and does not say so.
DEFAULT_TITLE = "DELIVERY CHALLAN"
#: What the copies of a challan are conventionally called. A firm may rename
#: them, but nobody should have to type these to get the ordinary set.
DEFAULT_COPIES: tuple[str, ...] = (
    "ORIGINAL FOR CONSIGNEE",
    "DUPLICATE FOR TRANSPORTER",
    "TRIPLICATE FOR CONSIGNOR",
)


class DeliveryChallanPrintService:
    """Render one delivery note as the challan that goes with the lorry."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the note lives on."""
        self._session = session

    def render(self, note_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        note = self._session.scalar(
            select(DeliveryNote).where(
                DeliveryNote.id == note_id,
                DeliveryNote.firm_id == firm_scope,
                DeliveryNote.is_deleted.is_(False),
            )
        )
        if note is None:
            raise ResourceNotFoundError("Delivery note not found.")

        template = self._template(firm_scope)
        document = self._document(note, firm_scope=firm_scope)
        pdf = InvoicePdfRenderer(template).render(document)
        safe = note.delivery_note_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's challan template, or a sensible default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            # A challan collects nothing, so it carries no bank block and
            # certifies nothing about tax.
            fallback=TemplateSettings(
                title_text=DEFAULT_TITLE,
                declaration=None,
                show_bank_details=False,
                copy_labels=DEFAULT_COPIES,
            ),
        )

    def _document(self, note: DeliveryNote, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, the goods and the vehicle carrying them."""
        lines = list(
            self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
        )
        products = self._products(line.product_id for line in lines)
        units = self._units(line.sales_uom_id for line in lines)

        printed: list[InvoiceLineBlock] = []
        for line in lines:
            product = products.get(line.product_id)
            unit = units.get(line.sales_uom_id) if line.sales_uom_id else None
            printed.append(
                InvoiceLineBlock(
                    number=line.line_number,
                    description=line.description
                    or (product.name if product else "")
                    or "",
                    hsn=product.hsn_sac if product else None,
                    quantity=line.current_delivery_quantity,
                    free_quantity=line.free_quantity,
                    uom=(unit.code if unit else None),
                    rate=line.unit_price,
                    discount=line.discount_amount,
                    taxable=line.gross_amount
                    - line.discount_amount
                    - line.bill_discount_amount,
                    total=line.net_amount,
                    batch=line.batch_number,
                    expiry=line.expiry_date.isoformat() if line.expiry_date else None,
                )
            )

        references: list[tuple[str, str]] = []
        if note.sales_order_reference:
            references.append(("Against order", note.sales_order_reference))
        # The two the driver is stopped and asked about.
        if note.vehicle:
            references.append(("Vehicle", note.vehicle))
        if note.driver:
            references.append(("Driver", note.driver))

        return InvoiceDocument(
            number=note.delivery_note_number,
            date=note.delivery_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=self._firm(firm_scope),
            # A note whose customer has been removed still prints; the
            # goods left and the paperwork has to exist.
            buyer=self._customer(note, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            ship_to=self._customer(note, "SHIPPING"),
            lines=tuple(printed),
            bill_discount=note.bill_discount_amount,
            gross_before_bill_discount=note.subtotal + note.bill_discount_amount,
            taxable_total=note.subtotal,
            tax_total=note.tax_total,
            charges=note.additional_charges,
            round_off=note.round_off,
            grand_total=note.grand_total,
            references=tuple(references),
            party_labels=("CONSIGNEE", "SHIP TO"),
            # A challan is not a tax invoice: it states the value of what is
            # moving and leaves the tax breakup to the bill that follows.
            show_tax_summary=False,
            show_supply_terms=False,
            number_label="Challan no.",
            date_label="Challan date",
            words_label="VALUE OF GOODS, IN WORDS",
        )

    def _firm(self, firm_scope: UUID) -> PartyBlock:
        """Describe the dispatching firm."""
        return firm_party(firm_scope)

    def _customer(self, note: DeliveryNote, kind: str) -> PartyBlock | None:
        """Describe the customer, billing or shipping side."""
        return customer_party(self._session, note.customer_id, kind)

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
