"""The money receipt a customer is given for a payment (MSG-4, decision A95).

What a firm hands over or emails when money comes in: who paid, how much in
figures and in words, how (cash, cheque and its number, UPI and its reference),
and which bills it settled. One A5 page, the way a receipt book reads; a
reversed receipt prints as such, so a copy of one can never pass for proof of
payment.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ResourceNotFoundError
from app.customers.models import Customer
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services.invoice_pdf import amount_in_words
from app.settlements.models.settlement import Settlement, SettlementAllocation

#: How each mode reads on the receipt.
_MODES = {
    "CASH": "Cash",
    "CHEQUE": "Cheque",
    "UPI": "UPI",
    "BANK_TRANSFER": "Bank transfer",
    "CARD": "Card",
    "DEMAND_DRAFT": "Demand draft",
    "OTHER": "Other",
}


class ReceiptPrintService:
    """Render one receipt as the voucher the customer keeps."""

    def __init__(self, session: Session) -> None:
        """Keep the tenant session the receipt lives on."""
        self._session = session

    def render(self, settlement_id: UUID, *, firm_scope: UUID) -> tuple[bytes, str]:
        """Return the PDF bytes and the filename to offer them under."""
        row = self._session.get(Settlement, settlement_id)
        if (
            row is None
            or row.firm_id != firm_scope
            or row.is_deleted
            or row.direction != "RECEIPT"
        ):
            raise ResourceNotFoundError("Receipt not found.")
        styles = getSampleStyleSheet()
        firm = FirmMetadataReader(self._session).get(firm_scope)
        customer = (
            self._session.get(Customer, row.customer_id) if row.customer_id else None
        )
        amount = Decimal(str(row.amount))
        mode = _MODES.get(row.payment_mode or row.method, row.method.title())
        if row.instrument_reference:
            mode = f"{mode} -- {row.instrument_reference}"
        parts: list[object] = [
            Paragraph(firm.name or "", styles["Title"]),
            Paragraph(
                "RECEIPT" + (" -- REVERSED" if row.status == "REVERSED" else ""),
                styles["Heading2"],
            ),
            Spacer(1, 3 * mm),
            self._table(
                [
                    ["Receipt no.", row.settlement_number],
                    ["Date", row.settlement_date.strftime("%d %b %Y")],
                    ["Received from", customer.name if customer else ""],
                    ["Amount", f"{amount:,.2f}"],
                    ["In words", Paragraph(amount_in_words(amount), styles["Normal"])],
                    ["Paid by", mode],
                ],
                [32 * mm, 88 * mm],
            ),
        ]
        settled = self._settled(row.id)
        if settled:
            parts += [
                Spacer(1, 4 * mm),
                Paragraph("Against", styles["Heading4"]),
                self._table(
                    [["Bill", "Amount"]]
                    + [[number, f"{value:,.2f}"] for number, value in settled],
                    [80 * mm, 40 * mm],
                    header=True,
                ),
            ]
        if row.narration:
            parts += [Spacer(1, 3 * mm), Paragraph(row.narration, styles["Normal"])]
        buffer = BytesIO()
        SimpleDocTemplate(
            buffer,
            pagesize=A5,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
            title=f"Receipt {row.settlement_number}",
        ).build(parts)
        safe = row.settlement_number.replace("/", "-").replace(" ", "-")
        return buffer.getvalue(), f"{safe}.pdf"

    def _settled(self, settlement_id: UUID) -> list[tuple[str, Decimal]]:
        """Return the bills the receipt was set against, by number."""
        rows = self._session.execute(
            select(SalesInvoice.invoice_number, SettlementAllocation.amount)
            .join(
                SalesInvoice, SalesInvoice.id == SettlementAllocation.sales_invoice_id
            )
            .where(
                SettlementAllocation.settlement_id == settlement_id,
                SettlementAllocation.is_deleted.is_(False),
            )
            .order_by(SalesInvoice.invoice_number.asc())
        ).all()
        return [(number, Decimal(str(value))) for number, value in rows]

    @staticmethod
    def _table(
        rows: Sequence[Sequence[object]], widths: list[float], *, header: bool = False
    ) -> Table:
        """Return a ruled two-column table."""
        table = Table(rows, colWidths=widths)
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        if header:
            style.append(("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"))
            style.append(("ALIGN", (1, 0), (1, -1), "RIGHT"))
        else:
            style.append(("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"))
        table.setStyle(TableStyle(style))
        return table


__all__ = ["ReceiptPrintService"]
