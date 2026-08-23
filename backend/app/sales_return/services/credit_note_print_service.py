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
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_return.models import (
    SalesReturn,
    SalesReturnLine,
    SalesReturnLineTax,
)
from app.uom.models import Uom

ZERO = Decimal("0")
DOCUMENT_TYPE = "SALES_RETURN"
DEFAULT_TITLE = "CREDIT NOTE"


class CreditNotePrintService:
    """Render one sales return as the credit note the customer is sent."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the return lives on."""
        self._session = session

    def render(self, return_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        row = self._session.scalar(
            select(SalesReturn).where(
                SalesReturn.id == return_id,
                SalesReturn.firm_id == firm_scope,
                SalesReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales return not found.")

        pdf = InvoicePdfRenderer(self._template(firm_scope)).render(
            self._document(row, firm_scope=firm_scope)
        )
        safe = row.return_number.replace("/", "-").replace(" ", "-")
        return pdf, f"{safe}.pdf"

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
        units = self._units(line.return_uom_id for line in lines)
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
                quantity=line.current_return_quantity,
                uom=(
                    units[line.return_uom_id].code
                    if line.return_uom_id in units
                    else None
                ),
                rate=line.unit_price,
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

        references: list[tuple[str, str]] = []
        if row.return_reason:
            # Why the goods came back is the first thing anybody reading a
            # credit note wants to know.
            references.append(("Reason", row.return_reason))

        return InvoiceDocument(
            number=row.return_number,
            date=row.return_date.strftime("%d %b %Y"),
            due_date=None,
            place_of_supply=None,
            reverse_charge=False,
            seller=firm_party(firm_scope),
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
