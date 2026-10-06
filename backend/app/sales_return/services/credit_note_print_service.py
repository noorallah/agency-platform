"""Turn a sales return into the credit note the customer files.

A credit note is the customer's evidence that the money came back, and their
accountant needs it as much as they needed the invoice. The platform could
reverse the stock, reverse the ledger and move the customer's balance, and had
no way to tell the customer any of it had happened.

It does not ask for money -- no due date and no bank block, because nothing is
being collected -- but it does state what was credited, including the tax.

It states the tax **component by component**, which a GST credit note must,
read from `sales_return_line_taxes` -- what was actually credited. Re-asking
the rule engine at print time is what that storage exists to prevent: rules are
effective-dated, so the engine can answer differently from what the customer
got back.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
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
    EInvoiceStamp,
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_return.billing import (
    CreditedBill,
    bills_credited,
    returns_crediting_bills,
)
from app.sales_return.models import (
    SalesReturn,
    SalesReturnLine,
    SalesReturnLineTax,
)
from app.uom.models import Uom
from app.uom.services import stated_line

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_RETURN"
DEFAULT_TITLE = "CREDIT NOTE"


#: What a credit note that does not stand says across its top, by status.
NOT_FINAL: dict[str, str] = {
    "DRAFT": "DRAFT - NO CREDIT GIVEN YET",
    "CANCELLED": "CANCELLED - NO CREDIT GIVEN",
}

#: A return's statuses once its credit note is issued (GSTR-1 reads the same).
_ISSUED = ("COMPLETED", "CLOSED")


def _stamp(session: Session, firm_scope: UUID, return_id: UUID) -> EInvoiceStamp | None:
    """Return the return's live IRN, as its print carries it (D-TAX-2)."""
    from app.sales_invoice.services.invoice_print_service import einvoice_stamp

    return einvoice_stamp(session, firm_scope=firm_scope, sales_return_id=return_id)


class CreditNotePrintService:
    """Render one sales return as the credit note the customer is sent."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the return lives on."""
        self._session = session

    def render(
        self, return_id: UUID, *, firm_scope: UUID, reference_copy: bool = False
    ) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under.

        A completed return against a B2B invoice the firm must e-invoice is
        a credit note the IRP registers, so it prints only once it has its
        IRN (77 row 6, D-TAX-2), or as a reference copy marked not valid.

        Raises:
            ResourceNotFoundError: When the firm has no such return.
            BusinessRuleError: When it needs an IRN it does not have and no
                reference copy was asked for.

        """
        from app.einvoice.services.issue_gate import (
            REFERENCE_COPY_BANNER,
            missing_irn,
            refuse_without_irn,
        )

        row = self._session.scalar(
            select(SalesReturn).where(
                SalesReturn.id == return_id,
                SalesReturn.firm_id == firm_scope,
                SalesReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales return not found.")
        no_irn = (
            missing_irn(
                self._session,
                firm_scope=firm_scope,
                number=row.return_number,
                on=row.return_date,
                customer_id=row.customer_id,
                status="APPROVED",
                sales_return_id=row.id,
            )
            if row.status in _ISSUED and self._credits_an_invoice(row.id)
            else None
        )
        if not reference_copy:
            refuse_without_irn(no_irn)

        document = self._document(row, firm_scope=firm_scope)
        if no_irn is not None:
            document = replace(document, not_final=REFERENCE_COPY_BANNER)
        pdf = InvoicePdfRenderer(self._template(firm_scope)).render(document)
        safe = row.return_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

    def _credits_an_invoice(self, return_id: UUID) -> bool:
        """Whether the return gives back goods an invoice billed.

        By either route: on a bill's own line, or off a delivery note and
        set against the bills that charged it (D-PRC-89). The same answer
        the print's "Against invoice" rows, GSTR-1 and the registration
        give, because all of them read ``bills_credited``.
        """
        return bool(returns_crediting_bills(self._session, [return_id]))

    # ------------------------------------------------------------------
    def _template(self, firm_scope: UUID) -> TemplateSettings:
        """Return the firm's credit note template, or a sensible default."""
        return load_template(
            self._session,
            firm_scope=firm_scope,
            document_type=DOCUMENT_TYPE,
            # Nothing is being collected, so no bank block.
            fallback=TemplateSettings(
                title_text=DEFAULT_TITLE,
                show_bank_details=False,
            ),
        )

    def _document(self, row: SalesReturn, *, firm_scope: UUID) -> InvoiceDocument:
        """Gather the parties, the goods coming back and the tax credited."""
        lines = list(
            self._session.scalars(
                select(SalesReturnLine)
                .where(
                    SalesReturnLine.sales_return_id == row.id,
                    SalesReturnLine.is_deleted.is_(False),
                )
                .order_by(SalesReturnLine.line_number.asc())
            ).all()
        )
        products = self._products(line.product_id for line in lines)
        # Each line as it is stated: quantity, unit and rate that belong
        # together -- as typed where the line kept what was typed, else in
        # the unit its quantity is in, the source line's (D-PRC-40).
        stated = {
            line.id: stated_line(
                quantity=line.current_return_quantity,
                free_quantity=line.free_quantity,
                unit_price=line.unit_price,
                source_uom_id=line.sales_uom_id,
                typed_uom_id=line.return_uom_id,
                entered_quantity=line.entered_quantity,
                conversion_factor=line.conversion_factor,
            )
            for line in lines
        }
        units = self._units(item.uom_id for item in stated.values())
        taxes = self._taxes(line.id for line in lines)

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
                quantity=stated[line.id].quantity,
                uom=(
                    units[unit_id].code
                    if (unit_id := stated[line.id].uom_id) in units
                    else None
                ),
                rate=stated[line.id].rate,
                discount=line.discount_amount,
                taxable=line.gross_amount
                - line.discount_amount
                - line.bill_discount_amount,
                total=line.net_amount,
                batch=line.batch_number,
                taxes=tuple(
                    (item.component_code, item.percentage, item.amount)
                    for item in taxes.get(line.id, [])
                ),
            )
            for line in lines
        ]

        references = self._originals(row, lines)
        if row.return_reason:
            # Why the goods came back is the first thing anybody reading a
            # credit note wants to know.
            references.append(("Reason", row.return_reason))

        return InvoiceDocument(
            # A draft credits nobody yet, and a cancelled one never will.
            not_final=NOT_FINAL.get(row.status),
            einvoice=_stamp(self._session, firm_scope, row.id),
            number=row.return_number,
            date=row.return_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=seller_party(self._session, firm_scope, row.branch_id),
            buyer=customer_party(self._session, row.customer_id, "BILLING")
            or PartyBlock(name="", address_lines=[]),
            ship_to=None,
            lines=tuple(printed),
            taxable_total=row.subtotal,
            tax_total=row.tax_total,
            charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            references=tuple(references),
            party_labels=("CREDITED TO", "RETURNED FROM"),
            # The tax it gives back, component by component, read from what
            # was credited rather than re-derived: rules are effective-dated,
            # so asking the engine again at print time can answer differently
            # from what the customer actually got back.
            show_tax_summary=True,
            # Nothing is being supplied, so no place of supply and no
            # reverse-charge declaration.
            show_supply_terms=False,
            number_label="Credit note no.",
            date_label="Credit note date",
            words_label="CREDIT, IN WORDS",
        )

    def _originals(
        self, row: SalesReturn, lines: list[SalesReturnLine]
    ) -> list[tuple[str, str]]:
        """Name the invoices this credit note corrects, and the notes it is off.

        A GST credit note is issued against a tax invoice and states the
        number and date of each one it corrects; this print carried neither,
        by either route, so a customer's accountant could not match it to a
        bill (D-PRC-84). A line raised on a bill's own line names that bill;
        a line off a delivery note names every bill its units were set
        against when the return completed -- several, where the note was
        billed in parts -- which is what GSTR-1 names too (`bills_credited`).
        One row a bill, earliest first, then the delivery notes the goods
        came back off.

        A return off a note that has not completed has been set against no
        bill yet, and names its note alone.
        """
        credited = bills_credited(self._session, lines, completed=row.status in _ISSUED)
        bills: dict[UUID, CreditedBill] = {}
        for line in lines:
            for bill in credited.get(line.id, []):
                bills.setdefault(bill.invoice_id, bill)
        references = [
            (
                "Against invoice",
                f"{bill.invoice_number} dated {bill.invoice_date.strftime('%d %b %Y')}",
            )
            for bill in sorted(
                bills.values(),
                key=lambda item: (item.invoice_date, item.invoice_number),
            )
        ]
        notes = list(
            dict.fromkeys(
                line.source_document_number
                for line in lines
                if line.source_document_type == "DELIVERY_NOTE"
                and line.source_document_number
            )
        )
        if notes:
            references.append(("Delivery note", ", ".join(notes)))
        return references

    def _taxes(self, ids: Iterable[UUID]) -> dict[UUID, list[SalesReturnLineTax]]:
        """Read the stored breakup for every line, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        found: dict[UUID, list[SalesReturnLineTax]] = {}
        for item in self._session.scalars(
            select(SalesReturnLineTax)
            .where(
                SalesReturnLineTax.sales_return_line_id.in_(wanted),
                SalesReturnLineTax.is_deleted.is_(False),
            )
            .order_by(SalesReturnLineTax.sequence.asc())
        ).all():
            found.setdefault(item.sales_return_line_id, []).append(item)
        return found

    def _products(self, ids: Iterable[UUID | None]) -> dict[UUID, Product]:
        """Read the products the lines name, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            item.id: item
            for item in self._session.scalars(
                select(Product).where(Product.id.in_(wanted))
            ).all()
        }

    def _units(self, ids: Iterable[UUID | None]) -> dict[UUID, Uom]:
        """Read the units the lines name, in one query."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            item.id: item
            for item in self._session.scalars(
                select(Uom).where(Uom.id.in_(wanted))
            ).all()
        }
