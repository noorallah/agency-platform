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
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchRecord
from app.core.exceptions import ResourceNotFoundError
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteLine,
    DeliveryNoteLineBatch,
)
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
from app.tax.services.gst_compliance import CHALLAN_REASONS
from app.uom.models import Uom

ZERO = Decimal("0")
QTY = Decimal("0.0001")
MONEY = Decimal("0.01")
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


def _per_batch(
    whole: InvoiceLineBlock,
    batches: list[tuple[BatchRecord, Decimal]],
    stock_quantity: Decimal,
) -> list[InvoiceLineBlock]:
    """Print a line once per batch it takes, as a pharmacy challan does (79).

    Each row states its batch and expiry and its share of the quantity, the
    free goods and the value, in proportion to the stock units it takes; the
    last row takes what rounding left, so the rows add up to the line exactly.
    One batch, or none recorded, prints the line as it is.
    """
    if not batches:
        return [whole]
    if len(batches) == 1 or stock_quantity <= ZERO:
        batch = batches[0][0]
        return [
            replace(
                whole,
                batch=batch.batch_number,
                expiry=batch.expiry_date.isoformat() if batch.expiry_date else None,
                mrp=batch.mrp,
            )
        ]
    rows: list[InvoiceLineBlock] = []
    left = {
        "quantity": whole.quantity,
        "free_quantity": whole.free_quantity,
        "discount": whole.discount,
        "taxable": whole.taxable,
        "total": whole.total,
    }
    places = {
        "quantity": QTY,
        "free_quantity": QTY,
        "discount": MONEY,
        "taxable": MONEY,
        "total": MONEY,
    }
    for index, (batch, quantity) in enumerate(batches):
        last = index == len(batches) - 1
        share = quantity / stock_quantity
        values: dict[str, Decimal] = {}
        for name in left:
            part = (
                left[name]
                if last
                else (getattr(whole, name) * share).quantize(places[name])
            )
            values[name] = part
            left[name] -= part
        rows.append(
            replace(
                whole,
                # The line's number goes on its first row only, so the rows
                # read as one line taken from several batches.
                number=whole.number if index == 0 else 0,
                description=whole.description if index == 0 else "",
                batch=batch.batch_number,
                expiry=batch.expiry_date.isoformat() if batch.expiry_date else None,
                mrp=batch.mrp,
                quantity=values["quantity"],
                free_quantity=values["free_quantity"],
                discount=values["discount"],
                taxable=values["taxable"],
                total=values["total"],
            )
        )
    return rows


def drawn_batches(
    session: Session, line_ids: list[UUID]
) -> dict[UUID, list[tuple[BatchRecord, Decimal]]]:
    """Return each note line's batches -- chosen, or drawn at dispatch (79).

    Shared by the challan and the tax invoice, which prints the batches of the
    note line it bills (79 row 7).
    """
    if not line_ids:
        return {}
    found: dict[UUID, list[tuple[BatchRecord, Decimal]]] = {}
    for pick, batch in session.execute(
        select(DeliveryNoteLineBatch, BatchRecord)
        .join(BatchRecord, BatchRecord.id == DeliveryNoteLineBatch.batch_id)
        .where(
            DeliveryNoteLineBatch.delivery_note_line_id.in_(line_ids),
            DeliveryNoteLineBatch.is_deleted.is_(False),
        )
        .order_by(DeliveryNoteLineBatch.created_at.asc())
    ).all():
        found.setdefault(pick.delivery_note_line_id, []).append((batch, pick.quantity))
    return found


def per_batch(
    whole: InvoiceLineBlock,
    batches: list[tuple[BatchRecord, Decimal]],
    stock_quantity: Decimal,
) -> list[InvoiceLineBlock]:
    """Print a line once per batch it takes; see ``_per_batch``."""
    return _per_batch(whole, batches, stock_quantity)


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
        if any(line.batch for line in document.lines):
            # Goods that carry batches travel with their batch and expiry on
            # the paper (backlog 79), whatever the firm's template hides.
            template = replace(
                template,
                show_batch_column=True,
                show_expiry_column=True,
                # And the MRP each batch carries, where any does (79 row 7).
                show_mrp_column=any(line.mrp is not None for line in document.lines),
            )
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

        drawn = self._drawn([line.id for line in lines])
        printed: list[InvoiceLineBlock] = []
        for line in lines:
            product = products.get(line.product_id)
            unit = units.get(line.sales_uom_id) if line.sales_uom_id else None
            whole = InvoiceLineBlock(
                number=line.line_number,
                description=line.description or (product.name if product else "") or "",
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
            printed.extend(
                _per_batch(whole, drawn.get(line.id, []), line.delivered_quantity)
            )

        references: list[tuple[str, str]] = []
        # Why the goods travel ahead of the invoice, which a checkpost asks
        # first (backlog 77 row 3; CGST Rules r.55).
        reason = CHALLAN_REASONS.get(note.challan_reason or "SALE", "Sale")
        references.append(
            (
                "Reason",
                (
                    f"{reason}: {note.challan_reason_note}"
                    if note.challan_reason_note
                    else reason
                ),
            )
        )
        if note.sales_order_reference:
            references.append(("Against order", note.sales_order_reference))
        # The two the driver is stopped and asked about.
        if note.vehicle:
            references.append(("Vehicle", note.vehicle))
        if note.driver:
            references.append(("Driver", note.driver))
        # What the e-way bill's Part B and a checkpost ask for (67 row 5).
        if note.transporter_name:
            references.append(("Transporter", note.transporter_name))
        if note.transporter_gstin:
            references.append(("Transporter GSTIN", note.transporter_gstin))
        if note.transport_mode:
            references.append(("Mode", note.transport_mode.title()))
        if note.lr_number:
            references.append(
                (
                    "LR / docket",
                    note.lr_number
                    + (f" dt {note.lr_date:%d %b %Y}" if note.lr_date else ""),
                )
            )
        if note.distance_km:
            references.append(("Distance", f"{note.distance_km} km"))

        return InvoiceDocument(
            number=note.delivery_note_number,
            date=note.delivery_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=self._firm(firm_scope, note.branch_id),
            # A note whose customer has been removed still prints; the
            # goods left and the paperwork has to exist.
            buyer=self._customer(note, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            # The address this dispatch names (backlog 67 row 3).
            ship_to=customer_party(
                self._session,
                note.customer_id,
                "SHIPPING",
                address_id=note.shipping_address_id,
            ),
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

    def _drawn(
        self, line_ids: list[UUID]
    ) -> dict[UUID, list[tuple[BatchRecord, Decimal]]]:
        """Return each line's batches -- chosen, or drawn at dispatch (79)."""
        return drawn_batches(self._session, line_ids)

    def _firm(self, firm_scope: UUID, branch_id: UUID | None = None) -> PartyBlock:
        """Describe the dispatching firm, under its branch's GSTIN (STK-2)."""
        return seller_party(self._session, firm_scope, branch_id)

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
