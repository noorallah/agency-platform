"""An 80 mm roll layout for any printed document, for counter billing.

A counter prints on a thermal roll, not on A4: 72 mm of printable width, one
column, and a page exactly as long as what is on it -- a roll printer feeds
whatever height the page has, so a fixed tall page would waste paper after
every bill. The same `InvoiceDocument` the A4 renderer takes is drawn here, so
a bill, a credit note or a challan reads the same facts on either paper.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    TemplateSettings,
    amount_in_words,
)

#: The paper value a firm chooses in Print settings.
THERMAL_80 = "THERMAL80"

_ROLL_WIDTH = 80 * mm
_MARGIN = 4 * mm


def _money(value: Decimal) -> str:
    """Format an amount with thousands separators and two decimals."""
    return f"{value:,.2f}"


def _quantity(value: Decimal) -> str:
    """Format a quantity without trailing zeros."""
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _rate(value: Decimal) -> str:
    """Format a tax rate without trailing zeros."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


class ThermalReceiptRenderer:
    """Draw a document on an 80 mm roll, one page per copy."""

    def __init__(self, template: TemplateSettings | None = None) -> None:
        """Bind the firm's template; its title, copies and notes are used."""
        self._template = template or TemplateSettings()
        base = ParagraphStyle("base", fontName="Helvetica", fontSize=8, leading=10)
        self._text = base
        self._small = ParagraphStyle("small", parent=base, fontSize=7, leading=8.5)
        self._centre = ParagraphStyle("centre", parent=base, alignment=TA_CENTER)
        self._right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
        self._firm = ParagraphStyle(
            "firm",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            alignment=TA_CENTER,
        )
        self._banner = ParagraphStyle(
            "banner",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
        )
        self._bold_right = ParagraphStyle(
            "bold_right",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_RIGHT,
        )

    def render(self, document: InvoiceDocument) -> bytes:
        """Return the document as a PDF roll, sized to its content."""
        # The frame keeps 6 pt of padding each side; tables drawn wider than
        # what is left would stand out past the text.
        width = _ROLL_WIDTH - 2 * _MARGIN - 12
        copies = self._template.copy_labels or ("",)
        stories = [self._one_copy(document, width, label) for label in copies]
        # One page per copy, each exactly as tall as its content.
        height = max(self._height(story, width) for story in stories)
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(_ROLL_WIDTH, height + 2 * _MARGIN),
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN,
            title=f"{self._template.title_text} {document.number}",
            author=document.seller.name,
        )
        flat: list[Flowable] = []
        for index, story in enumerate(stories):
            if index:
                flat.append(PageBreak())
            flat.extend(story)
        doc.build(flat)
        return buffer.getvalue()

    @staticmethod
    def _height(story: list[Flowable], width: float) -> float:
        """Return how tall the story lays out at this width, with slack."""
        total = 0.0
        for flowable in story:
            _, height = flowable.wrap(width, 10_000)
            total += float(height)
            total += float(flowable.getSpaceBefore() + flowable.getSpaceAfter())
        # A little slack: a paragraph measured here can wrap one line longer
        # in the frame, and a page one line short would spill the total onto
        # a second, mostly blank, page.
        return total + float(12 * mm)

    def _rule(self, width: float) -> Table:
        """Draw a thin line across the roll."""
        table = Table([[""]], colWidths=[width], rowHeights=[2])
        table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, "black")]))
        return table

    def _pair(
        self,
        width: float,
        left: str,
        right: str,
        *,
        bold: bool = False,
        split: float = 0.55,
    ) -> Table:
        """Set a label on the left and a figure on the right."""
        style = self._bold_right if bold else self._right
        table = Table(
            [[Paragraph(left, self._text), Paragraph(right, style)]],
            colWidths=[width * split, width * (1 - split)],
        )
        table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _one_copy(
        self, document: InvoiceDocument, width: float, copy_label: str
    ) -> list[Flowable]:
        """Build one copy: seller, title, party, lines, totals, footer."""
        seller = document.seller
        story: list[Flowable] = [Paragraph(seller.name, self._firm)]
        for address in seller.address_lines:
            if address:
                story.append(Paragraph(address, self._centre))
        if seller.gstin:
            story.append(Paragraph(f"GSTIN {seller.gstin}", self._centre))
        if seller.contact:
            story.append(Paragraph(seller.contact, self._centre))
        story += [Spacer(1, 3), self._rule(width)]
        if document.not_final:
            story.append(Paragraph(document.not_final, self._banner))
        story.append(Paragraph(self._template.title_text, self._banner))
        if copy_label:
            story.append(Paragraph(copy_label, self._centre))
        story.append(self._rule(width))
        story.append(Paragraph(document.number_label, self._small))
        story.append(self._pair(width, document.number, document.date, split=0.68))
        buyer = document.buyer
        if buyer.name:
            story.append(Paragraph(f"To: {buyer.name}", self._text))
            if buyer.gstin:
                story.append(Paragraph(f"GSTIN {buyer.gstin}", self._small))
        if document.show_supply_terms and document.place_of_supply:
            story.append(
                Paragraph(f"Place of supply: {document.place_of_supply}", self._small)
            )
        story.append(self._rule(width))

        taxes: dict[tuple[str, Decimal], Decimal] = defaultdict(Decimal)
        for line in document.lines:
            name = line.description
            if line.hsn:
                name = f"{name} <font size=6>HSN {line.hsn}</font>"
            story.append(Paragraph(name, self._text))
            quantity = f"{_quantity(line.quantity)} {line.uom or ''}".strip()
            if line.free_quantity:
                quantity += f" +{_quantity(line.free_quantity)} free"
            story.append(
                self._pair(
                    width, f"{quantity} x {_money(line.rate)}", _money(line.total)
                )
            )
            if line.discount:
                story.append(
                    Paragraph(f"less discount {_money(line.discount)}", self._small)
                )
            if line.batch:
                story.append(Paragraph(f"batch {line.batch}", self._small))
            for component, rate, amount in line.taxes:
                taxes[(component, rate)] += amount
        story.append(self._rule(width))

        if document.bill_discount:
            story.append(
                self._pair(width, "Bill discount", f"-{_money(document.bill_discount)}")
            )
        story.append(self._pair(width, "Taxable value", _money(document.taxable_total)))
        for (component, rate), amount in sorted(taxes.items()):
            story.append(
                self._pair(width, f"{component} {_rate(rate)}%", _money(amount))
            )
        if not taxes and document.tax_total:
            story.append(self._pair(width, "Tax", _money(document.tax_total)))
        if document.charges:
            story.append(self._pair(width, "Charges", _money(document.charges)))
        if document.round_off:
            story.append(self._pair(width, "Round off", _money(document.round_off)))
        story.append(
            self._pair(
                width,
                "TOTAL",
                f"{document.currency_symbol} {_money(document.grand_total)}",
                bold=True,
            )
        )
        story.append(Paragraph(amount_in_words(document.grand_total), self._small))
        story.append(self._rule(width))

        for note in (
            self._template.terms,
            self._template.footer_note,
            self._template.signatory_text,
        ):
            if note:
                story.append(Paragraph(note, self._small))
        story.append(Spacer(1, 2))
        story.append(Paragraph("Thank you", self._centre))
        return story
