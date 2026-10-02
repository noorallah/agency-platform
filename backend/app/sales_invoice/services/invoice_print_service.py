"""Turn a stored sales invoice into the bill a customer is sent.

Everything here is read from the record. The tax components come from
`sales_invoice_line_taxes` rather than the rule engine, because rules are
effective-dated and asking again can answer differently from what the customer
was billed; the place of supply and the due date come from the invoice for the
same reason.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.delivery_note.models import DeliveryNote
from app.document_framework.services.print_support import (
    customer_party,
    firm_party,
    load_template,
)
from app.products.models import Product
from app.promotions.models import Promotion, PromotionRedemption
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
    SalesInvoiceSource,
)
from app.sales_invoice.services.invoice_pdf import (
    EInvoiceStamp,
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_order.models import SalesOrder
from app.trade_licences.services import TradeLicenceService
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_INVOICE"
#: What the copies of a tax invoice for goods are called (CGST rule 48: the
#: original for the recipient, the duplicate for the transporter, the
#: triplicate for the supplier). A firm may rename or cut them, but a firm
#: that has saved no Print settings used to get one unlabelled copy
#: (BL-31.14).
DEFAULT_COPIES: tuple[str, ...] = (
    "ORIGINAL FOR RECIPIENT",
    "DUPLICATE FOR TRANSPORTER",
    "TRIPLICATE FOR SUPPLIER",
)


#: What a bill that does not stand says across its top, by status.
NOT_FINAL: dict[str, str] = {
    "DRAFT": "DRAFT - NOT A TAX INVOICE - NOT YET APPROVED",
    "CANCELLED": "CANCELLED - NOT A TAX INVOICE",
}

#: How many delivery notes (or orders) the bill's header lists one by one.
#: Beyond it the header says "Several -- see lines" and every line names its
#: own note, which is how Tally prints a bill made of many dispatches.
MAX_LISTED_SOURCES = 3
SEVERAL = "Several - see lines"


def einvoice_stamp(
    session: Session,
    *,
    firm_scope: UUID,
    sales_invoice_id: UUID | None = None,
    credit_note_id: UUID | None = None,
    customer_debit_note_id: UUID | None = None,
    sales_return_id: UUID | None = None,
) -> EInvoiceStamp | None:
    """Return the live registration of one document, as its print carries it.

    Only a REGISTERED row prints: a refused or withdrawn one gave the
    document no IRN it may claim (77 row 11).
    """
    from app.einvoice.models import EInvoiceRegistration

    column, value = next(
        (column, value)
        for column, value in (
            (EInvoiceRegistration.sales_invoice_id, sales_invoice_id),
            (EInvoiceRegistration.credit_note_id, credit_note_id),
            (EInvoiceRegistration.customer_debit_note_id, customer_debit_note_id),
            (EInvoiceRegistration.sales_return_id, sales_return_id),
        )
        if value is not None
    )
    row = session.scalar(
        select(EInvoiceRegistration).where(
            EInvoiceRegistration.firm_id == firm_scope,
            column == value,
            EInvoiceRegistration.status == "REGISTERED",
            EInvoiceRegistration.is_deleted.is_(False),
        )
    )
    if row is None or not row.irn:
        return None
    return EInvoiceStamp(
        irn=row.irn,
        acknowledgement_number=row.acknowledgement_number,
        acknowledged_on=(
            f"{row.acknowledged_at:%d %b %Y %H:%M}" if row.acknowledged_at else None
        ),
        signed_qr=row.signed_qr_code,
    )


def _dated(number: str, on: object) -> str:
    """Render a document number with its date, as the GST bill heads do."""
    return f"{number} dt. {on:%d %b %Y}" if on is not None else number


class SalesInvoicePrintService:
    """Render one invoice, with the firm's template around it."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the invoice lives on."""
        self._session = session

    # ------------------------------------------------------------------
    def render(
        self, invoice_id: UUID, *, firm_scope: UUID, reference_copy: bool = False
    ) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under.

        A B2B invoice the firm must e-invoice prints only once it has its IRN
        (77 row 6); before then only as a reference copy, under a banner
        saying it is not a valid tax invoice.

        Raises:
            ResourceNotFoundError: When the firm has no such invoice.
            BusinessRuleError: When the invoice needs an IRN it does not have
                and no reference copy was asked for.

        """
        from app.einvoice.services.issue_gate import (
            REFERENCE_COPY_BANNER,
            missing_irn,
            refuse_without_irn,
        )

        invoice = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        no_irn = missing_irn(
            self._session,
            firm_scope=firm_scope,
            number=invoice.invoice_number,
            on=invoice.invoice_date,
            customer_id=invoice.customer_id,
            status=invoice.status,
            sales_invoice_id=invoice.id,
        )
        if not reference_copy:
            refuse_without_irn(no_irn)

        template = self._template(firm_scope)
        document = self._document(invoice, firm_scope=firm_scope)
        if no_irn is not None:
            document = replace(document, not_final=REFERENCE_COPY_BANNER)
        if any(line.batch for line in document.lines):
            # The batches the goods left in, with their expiry and printed
            # MRP, as the challan carries them (backlog 79 row 7).
            template = replace(
                template,
                show_batch_column=True,
                show_expiry_column=True,
                show_mrp_column=any(line.mrp is not None for line in document.lines),
            )
        pdf = InvoicePdfRenderer(template).render(document)
        safe = invoice.invoice_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's template, or the platform default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            fallback=TemplateSettings(copy_labels=DEFAULT_COPIES),
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

        references, source_of_line = self._sources(invoice, lines)

        # Imported here: the delivery note's print imports this module.
        from app.delivery_note.services.challan_print_service import (
            drawn_batches,
            per_batch,
        )

        drawn = drawn_batches(
            self._session,
            [
                line.source_document_line_id
                for line in lines
                if line.source_document_type == "DELIVERY_NOTE"
            ],
        )
        printed: list[InvoiceLineBlock] = []
        for line in lines:
            product = products.get(line.product_id)
            unit = units.get(line.invoice_uom_id) if line.invoice_uom_id else None
            batches = (
                drawn.get(line.source_document_line_id, [])
                if line.source_document_type == "DELIVERY_NOTE"
                else []
            )
            whole = InvoiceLineBlock(
                number=line.line_number,
                description=(
                    line.description or (product.name if product else "") or ""
                )
                + source_of_line.get(line.id, ""),
                # As billed (D-CMP-22); an old line with none stamped
                # falls back to the product.
                hsn=line.hsn_sac or (product.hsn_sac if product else None),
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
                # Both rates print where the bill typed them with GST in
                # (backlog 64 row 4).
                entered_rate=(line.entered_rate if invoice.rate_includes_tax else None),
            )
            printed.extend(
                per_batch(whole, batches, sum((qty for _, qty in batches), ZERO))
            )

        # The licences valid on the bill's own date: a drug or FSSAI number
        # that had lapsed by then is not one the bill may claim (54).
        licences = TradeLicenceService(self._session)
        return InvoiceDocument(
            # A draft has not been approved or posted, and a cancelled bill
            # charges nobody: neither may pass for a tax invoice on paper.
            not_final=NOT_FINAL.get(invoice.status),
            einvoice=einvoice_stamp(
                self._session, firm_scope=firm_scope, sales_invoice_id=invoice.id
            ),
            number=invoice.invoice_number,
            date=invoice.invoice_date.strftime("%d %b %Y"),
            due_date=(
                invoice.due_date.strftime("%d %b %Y") if invoice.due_date else None
            ),
            place_of_supply=invoice.place_of_supply,
            reverse_charge=False,
            seller=replace(
                self._seller(firm_scope),
                licences=tuple(
                    licences.valid_numbers(
                        firm_id=firm_scope,
                        on=invoice.invoice_date,
                        branch_id=invoice.branch_id,
                    )
                ),
            ),
            buyer=replace(
                self._customer_block(invoice.customer_id, "BILLING")
                or PartyBlock(name="", address_lines=[]),
                licences=tuple(
                    licences.valid_numbers(
                        firm_id=firm_scope,
                        on=invoice.invoice_date,
                        customer_id=invoice.customer_id,
                    )
                ),
            ),
            # The address the bill names (backlog 67 row 3).
            ship_to=customer_party(
                self._session,
                invoice.customer_id,
                "SHIPPING",
                address_id=invoice.shipping_address_id,
            ),
            lines=tuple(printed),
            bill_discount=invoice.bill_discount_amount,
            gross_before_bill_discount=invoice.subtotal + invoice.bill_discount_amount,
            taxable_total=invoice.subtotal,
            tax_total=invoice.tax_total,
            charges=invoice.additional_charges,
            round_off=invoice.round_off,
            grand_total=invoice.grand_total,
            references=(
                *references,
                *(
                    ("Reference", invoice.reference_number)
                    for _ in (1,)
                    if invoice.reference_number
                ),
            ),
        )

    def _sources(
        self, invoice: SalesInvoice, lines: list[SalesInvoiceLine]
    ) -> tuple[list[tuple[str, str]], dict[UUID, str]]:
        """Name every delivery note and order the bill covers (D-SELL-39, 58.7).

        A tax invoice made of dispatches says which: Tally prints "Delivery
        Note No." and "Buyer's Order No." in its head, and a bill of three
        dispatches has to say all three, or the buyer cannot match it to the
        goods received. Up to ``MAX_LISTED_SOURCES`` are listed in the head,
        each with its date; past that the head says "Several - see lines".
        Whenever there is more than one note, every line also names the note
        it came from, so a part-returned dispatch can be found on the bill.

        Returns the head's rows and, per line id, the text to add to its
        description.
        """
        sources = list(
            self._session.scalars(
                select(SalesInvoiceSource)
                .where(
                    SalesInvoiceSource.sales_invoice_id == invoice.id,
                    SalesInvoiceSource.is_deleted.is_(False),
                )
                .order_by(
                    SalesInvoiceSource.source_document_date.asc(),
                    SalesInvoiceSource.source_document_number.asc(),
                )
            ).all()
        )
        notes = [s for s in sources if s.source_document_type == "DELIVERY_NOTE"]
        order_ids = {
            s.source_document_id
            for s in sources
            if s.source_document_type == "SALES_ORDER"
        }
        if notes:
            order_ids |= set(
                self._session.scalars(
                    select(DeliveryNote.sales_order_id).where(
                        DeliveryNote.id.in_([s.source_document_id for s in notes])
                    )
                ).all()
            )
        orders = (
            list(
                self._session.scalars(
                    select(SalesOrder)
                    .where(SalesOrder.id.in_(order_ids))
                    .order_by(SalesOrder.order_date.asc(), SalesOrder.order_number)
                ).all()
            )
            if order_ids
            else []
        )

        rows: list[tuple[str, str]] = []

        def listed(label: str, values: list[str]) -> None:
            if not values:
                return
            if len(values) > MAX_LISTED_SOURCES:
                rows.append((f"{label}s", SEVERAL))
                return
            for value in values:
                rows.append((label, value))

        listed(
            "Delivery note",
            [_dated(n.source_document_number, n.source_document_date) for n in notes],
        )
        listed(
            "Sales order",
            [_dated(o.order_number, o.order_date) for o in orders],
        )
        listed(
            "Buyer's order no.",
            sorted({o.customer_reference for o in orders if o.customer_reference}),
        )
        # The offers the customer was given (backlog 60 item 12): claimed on
        # the orders this bill continues, so a festival offer is named on the
        # bill that delivers it, with what the bill took off in all.
        if orders:
            codes = sorted(
                set(
                    self._session.scalars(
                        select(Promotion.code)
                        .join(
                            PromotionRedemption,
                            PromotionRedemption.promotion_id == Promotion.id,
                        )
                        .where(
                            PromotionRedemption.document_id.in_([o.id for o in orders]),
                            PromotionRedemption.status == "CLAIMED",
                            PromotionRedemption.is_deleted.is_(False),
                        )
                    ).all()
                )
            )
            if codes:
                rows.append(("Offers", ", ".join(codes)))
        saved = invoice.line_discount_total + invoice.bill_discount_amount
        if saved > 0:
            rows.append(("You saved", f"{saved:.2f}"))

        per_line: dict[UUID, str] = {}
        if len(notes) > 1:
            for line in lines:
                if line.source_document_type == "DELIVERY_NOTE":
                    per_line[line.id] = f" (note {line.source_document_number})"
        return rows, per_line

    def _seller(self, firm_scope: UUID) -> PartyBlock:
        """Describe the selling firm."""
        return firm_party(firm_scope)

    def _customer_block(self, customer_id: UUID, kind: str) -> PartyBlock | None:
        """Return the customer as one side of the bill."""
        return customer_party(self._session, customer_id, kind)
