"""A one-page printed document on the firm's letterhead.

The invoice renderer (`app/sales_invoice/services/invoice_pdf.py`) draws a
grid of lines and taxes; a contra voucher and a balance confirmation letter
have neither. They need the firm's name and address across the top in the
firm's accent colour, a title, a few labelled facts, some paragraphs and a
signature -- the same reportlab platypus pieces, the same `PartyBlock` from
`print_support.firm_party`, and the accent from the firm's saved invoice
template so every page the firm prints looks like one firm's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from app.sales_invoice.services.invoice_pdf import PartyBlock

DEFAULT_ACCENT = "#0B3D6B"


@dataclass(frozen=True, slots=True)
class LetterPage:
    """What one printed page says."""

    firm: PartyBlock
    title: str
    #: Labelled facts in a two-column block under the title: number, date,
    #: account, amount.
    facts: list[tuple[str, str]] = field(default_factory=list)
    #: Who the letter is to, printed above the paragraphs. None for a voucher.
    addressee: PartyBlock | None = None
    #: The body, one string per paragraph. Plain text; escaped here.
    paragraphs: list[str] = field(default_factory=list)
    #: The signature line's caption, under the firm's name.
    signatory: str = "Authorised Signatory"
    #: A second signature box on the left (the voucher's "Received by").
    counter_signatory: str | None = None


class LetterPdfRenderer:
    """Turn one or more `LetterPage`s into PDF bytes."""

    def __init__(self, accent_color: str | None = None) -> None:
        """Pick the accent, falling back to the platform's for a bad value."""
        try:
            self._accent = colors.HexColor(accent_color or DEFAULT_ACCENT)
        except ValueError:
            self._accent = colors.HexColor(DEFAULT_ACCENT)
        grey = colors.HexColor("#4A4F58")
        self._name = ParagraphStyle(
            "name",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=self._accent,
        )
        self._small = ParagraphStyle(
            "small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=grey
        )
        self._title = ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            alignment=TA_CENTER,
            textColor=self._accent,
        )
        self._label = ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=grey
        )
        self._body = ParagraphStyle(
            "body", fontName="Helvetica", fontSize=10, leading=14
        )
        self._strong = ParagraphStyle(
            "strong", fontName="Helvetica-Bold", fontSize=10, leading=14
        )
        self._right = ParagraphStyle(
            "right", fontName="Helvetica", fontSize=9, leading=12, alignment=TA_RIGHT
        )

    def render(self, pages: list[LetterPage]) -> bytes:
        """Return every page, one after another, as one PDF."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )
        story: list[Flowable] = []
        for index, page in enumerate(pages):
            if index:
                story.append(PageBreak())
            story.extend(self._page(page, doc.width))
        doc.build(story)
        return buffer.getvalue()

    def _page(self, page: LetterPage, width: float) -> list[Flowable]:
        """Lay out one page."""
        story: list[Flowable] = [*self._letterhead(page.firm, width)]
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(escape(page.title), self._title))
        story.append(Spacer(1, 5 * mm))
        if page.facts:
            rows = [
                [
                    Paragraph(escape(label), self._label),
                    Paragraph(escape(value), self._body),
                ]
                for label, value in page.facts
            ]
            table = Table(rows, colWidths=[width * 0.3, width * 0.7])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        (
                            "LINEBELOW",
                            (0, 0),
                            (-1, -1),
                            0.25,
                            colors.HexColor("#D5D8DD"),
                        ),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 6 * mm))
        if page.addressee is not None:
            story.append(Paragraph("To,", self._body))
            story.append(Paragraph(escape(page.addressee.name), self._strong))
            for line in page.addressee.address_lines:
                story.append(Paragraph(escape(line), self._body))
            if page.addressee.gstin:
                story.append(
                    Paragraph(f"GSTIN: {escape(page.addressee.gstin)}", self._body)
                )
            story.append(Spacer(1, 5 * mm))
        for paragraph in page.paragraphs:
            story.append(Paragraph(escape(paragraph), self._body))
            story.append(Spacer(1, 3 * mm))
        story.append(Spacer(1, 14 * mm))
        story.append(self._signatures(page, width))
        return story

    def _letterhead(self, firm: PartyBlock, width: float) -> list[Flowable]:
        """Draw the firm's name, address and registrations, ruled off."""
        parts: list[Flowable] = [Paragraph(escape(firm.name), self._name)]
        for line in firm.address_lines:
            parts.append(Paragraph(escape(line), self._small))
        ids = " · ".join(
            text
            for text in (
                f"GSTIN {firm.gstin}" if firm.gstin else "",
                f"PAN {firm.pan}" if firm.pan else "",
                firm.contact or "",
            )
            if text
        )
        if ids:
            parts.append(Paragraph(escape(ids), self._small))
        rule = Table([[""]], colWidths=[width], rowHeights=[1.5])
        rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, self._accent)]))
        return [*parts, rule]

    def _signatures(self, page: LetterPage, width: float) -> Flowable:
        """Draw the signature line, and the counter-signature where asked."""
        right = [
            Paragraph(f"For {escape(page.firm.name)}", self._right),
            Spacer(1, 12 * mm),
            Paragraph(escape(page.signatory), self._right),
        ]
        left: list[Flowable] = []
        if page.counter_signatory:
            left = [
                Spacer(1, 16 * mm),
                Paragraph(escape(page.counter_signatory), self._body),
            ]
        table = Table([[left, right]], colWidths=[width * 0.5, width * 0.5])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        return table


__all__ = ["DEFAULT_ACCENT", "LetterPage", "LetterPdfRenderer"]
