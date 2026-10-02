"""Print a credit note or a debit note to a customer (backlog 77 row 11).

A note is a tax document in its own right (CGST section 34, rule 53): it names
the invoice it corrects, the parties, the place of supply, and the tax it
reverses or adds -- at the rate the invoice charged, which only the invoice
line knows. Where the note is registered on the portal it carries its IRN,
acknowledgement and signed QR the way the invoice does.

The layout is the invoice's, so a firm's template and its customers' habits
carry over: Tally and Zoho print a credit note on the invoice's own format with
the title changed and "Against invoice" in the head.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.document_framework.services.print_support import load_template
from app.products.models import Product
from app.sales_invoice.models import SalesInvoiceLine, SalesInvoiceLineTax
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
    einvoice_stamp,
)

ZERO = Decimal("0")
CREDIT_NOTE = "CREDIT_NOTE"
DEBIT_NOTE = "DEBIT_NOTE"

#: Rule 53 asks for no particular copies; the recipient's and the supplier's
#: are what Tally prints by default for a note.
NOTE_COPIES: tuple[str, ...] = ("ORIGINAL FOR RECIPIENT", "DUPLICATE FOR SUPPLIER")

#: Title, number label, date label and words label, by kind of note.
_WORDING = {
    CREDIT_NOTE: (
        "CREDIT NOTE",
        "Credit note no.",
        "Credit note date",
        "AMOUNT CREDITED, IN WORDS",
    ),
    DEBIT_NOTE: (
        "DEBIT NOTE",
        "Debit note no.",
        "Debit note date",
        "AMOUNT DEBITED, IN WORDS",
    ),
}

#: The template a firm saves for each kind; none saved takes the default.
_TEMPLATE_TYPE = {CREDIT_NOTE: "CREDIT_NOTE", DEBIT_NOTE: "CUSTOMER_DEBIT_NOTE"}

_NOT_FINAL = {
    "DRAFT": "DRAFT - NOT YET APPROVED",
    "CANCELLED": "CANCELLED",
}


class NotePrintService:
    """Render a credit or debit note to a customer as a PDF."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the note lives on."""
        self._session = session

    def render(
        self, kind: str, note_id: UUID, *, firm_scope: UUID
    ) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under.

        Raises:
            ResourceNotFoundError: When the firm has no such note.

        """
        from app.einvoice.services.note_registration import read_note

        note = read_note(self._session, kind, note_id, firm_scope=firm_scope)
        title, number_label, date_label, words_label = _WORDING[kind]
        template = replace(
            load_template(
                self._session,
                firm_scope=firm_scope,
                document_type=_TEMPLATE_TYPE[kind],
                fallback=TemplateSettings(copy_labels=NOTE_COPIES),
            ),
            title_text=title,
        )
        header = self._header(kind, note_id)
        invoice = note.invoice
        party = SalesInvoicePrintService(self._session)
        lines = self._lines(list(note.lines))
        taxable = sum((line.taxable for line in lines), ZERO)
        tax = sum((Decimal(str(line.tax_amount)) for line in note.lines), ZERO)
        document = InvoiceDocument(
            not_final=_NOT_FINAL.get(note.status),
            einvoice=einvoice_stamp(
                self._session,
                firm_scope=firm_scope,
                **{
                    (
                        "credit_note_id"
                        if kind == CREDIT_NOTE
                        else "customer_debit_note_id"
                    ): note_id
                },
            ),
            number=note.number,
            date=f"{header['date']:%d %b %Y}",
            due_date=None,
            place_of_supply=invoice.place_of_supply,
            reverse_charge=False,
            seller=party._seller(firm_scope),
            buyer=party._customer_block(invoice.customer_id, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            ship_to=None,
            lines=tuple(lines),
            taxable_total=taxable,
            tax_total=tax,
            charges=ZERO,
            round_off=ZERO,
            grand_total=taxable + tax,
            references=(
                (
                    "Against invoice",
                    f"{invoice.invoice_number} dt. {invoice.invoice_date:%d %b %Y}",
                ),
                *((("Reason", str(header["reason"])),) if header["reason"] else ()),
            ),
            number_label=number_label,
            date_label=date_label,
            words_label=words_label,
        )
        pdf = InvoicePdfRenderer(template).render(document)
        safe = note.number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    def _header(self, kind: str, note_id: UUID) -> dict[str, object]:
        """Return the note's date and reason, which the shared reader omits."""
        if kind == CREDIT_NOTE:
            from app.credit_note.models import CreditNote

            credit = self._session.get(CreditNote, note_id)
            if credit is None:
                raise ResourceNotFoundError("Credit note not found.")
            return {
                "date": credit.credit_note_date,
                "reason": _readable(credit.reason),
            }
        from app.customer_debit_note.models import CustomerDebitNote

        debit = self._session.get(CustomerDebitNote, note_id)
        if debit is None:
            raise ResourceNotFoundError("Debit note not found.")
        return {"date": debit.debit_note_date, "reason": _readable(debit.reason)}

    def _lines(self, lines: list[Any]) -> list[InvoiceLineBlock]:
        """Print each note line with its tax split as the invoice line was.

        The note records one tax figure per line; the invoice line records the
        heads it was charged in. The note's figure is shared across those heads
        in the same proportion -- the rate the supply was charged at, which is
        the rate a credit must reverse.
        """
        invoice_line_ids = [line.sales_invoice_line_id for line in lines]
        invoice_lines = {
            row.id: row
            for row in self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.id.in_(invoice_line_ids or [None])
                )
            )
        }
        components: dict[UUID, list[SalesInvoiceLineTax]] = {}
        for item in self._session.scalars(
            select(SalesInvoiceLineTax)
            .where(
                SalesInvoiceLineTax.sales_invoice_line_id.in_(
                    invoice_line_ids or [None]
                ),
                SalesInvoiceLineTax.is_deleted.is_(False),
            )
            .order_by(SalesInvoiceLineTax.sequence.asc())
        ):
            components.setdefault(item.sales_invoice_line_id, []).append(item)
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line in lines] or [None])
                )
            )
        }
        printed: list[InvoiceLineBlock] = []
        for line in lines:
            source = invoice_lines.get(line.sales_invoice_line_id)
            product = products.get(line.product_id)
            quantity = Decimal(str(line.quantity or 0))
            taxable = Decimal(str(line.taxable_amount))
            tax = Decimal(str(line.tax_amount))
            heads = components.get(line.sales_invoice_line_id, [])
            whole = sum((Decimal(str(item.amount)) for item in heads), ZERO)
            printed.append(
                InvoiceLineBlock(
                    number=line.line_number,
                    description=(
                        line.description or (product.name if product else "") or ""
                    ),
                    hsn=(source.hsn_sac if source else None)
                    or (product.hsn_sac if product else None),
                    quantity=quantity,
                    uom=None,
                    rate=(taxable / quantity if quantity > ZERO else taxable),
                    discount=ZERO,
                    taxable=taxable,
                    total=Decimal(str(line.total_amount)),
                    taxes=tuple(
                        (
                            item.component_code,
                            item.percentage,
                            (
                                tax * Decimal(str(item.amount)) / whole
                                if whole > ZERO
                                else ZERO
                            ).quantize(Decimal("0.01")),
                        )
                        for item in heads
                    ),
                )
            )
        return printed


def _readable(code: str | None) -> str | None:
    """Return a stored reason code as words: SALES_RETURN -> Sales return."""
    if not code:
        return None
    return code.replace("_", " ").capitalize()
