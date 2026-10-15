"""A half-page layout for any printed document (backlog 118).

A distributor's bill is mostly one to eight lines, and the trade prints it on
half an A4 sheet: 210 mm wide and 148.5 mm tall. The full-page layout cannot
be squeezed into that -- its banner, two address boxes and HSN summary alone
are taller than the paper -- so this one is drawn for the height it has: the
seller and the buyer side by side, one strip for the document's particulars,
a line table carrying MRP, quantity, free goods, rate, discount, GST, batch
and expiry, a GST summary by rate, and the totals beside it.

The same `InvoiceDocument` the full-page renderer takes is drawn here, so a
bill reads the same facts on either paper. A copy that does not fit on its
half page is not split across two of them: `render` answers ``None`` and the
caller prints the document on a full page instead.
"""

from __future__ import annotations

from decimal import Decimal
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

from app.sales_invoice.services.invoice_pdf import (
    INCLUSIVE_RATE,
    TOTAL_QUANTITY,
    InvoiceDocument,
    InvoiceLineBlock,
    PartyBlock,
    TemplateSettings,
    amount_in_words,
    packed_cell,
    qr_drawing,
)

#: The paper value a firm chooses in Print settings.
HALF_PAGE = "HALF"

#: Half of an A4 sheet, cut across: as wide as A4 and half as tall.
HALF_PAGE_SIZE = (A4[0], A4[1] / 2)

#: The widest margin the half page keeps. A firm's 12 mm suits a full page
#: and would take a sixth of this one's height.
_MAX_MARGIN_MM = Decimal("8")

ZERO = Decimal("0")


def half_page_margin(template: TemplateSettings) -> float:
    """Return the margin a half page is drawn with, in points."""
    return float(min(template.margin_mm, _MAX_MARGIN_MM)) * float(mm)


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


class HalfPageRenderer:
    """Draw a document on half an A4 sheet, one page per copy."""

    def __init__(self, template: TemplateSettings | None = None) -> None:
        """Bind the firm's template; its title, copies and notes are used."""
        self._template = template or TemplateSettings()
        self._rule = colors.HexColor("#8E949E")
        base = ParagraphStyle("base", fontName="Helvetica", fontSize=7.4, leading=9)
        self._text = base
        self._cell = ParagraphStyle("cell", parent=base, fontSize=7.2, leading=8.4)
        self._small = ParagraphStyle("small", parent=base, fontSize=6.4, leading=7.8)
        self._right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
        self._centre = ParagraphStyle("centre", parent=self._small, alignment=TA_CENTER)
        self._bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")
        self._firm = ParagraphStyle(
            "firm", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=13
        )
        self._title = ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=11.5,
            alignment=TA_RIGHT,
        )
        self._bold_right = ParagraphStyle(
            "bold_right", parent=self._bold, alignment=TA_RIGHT
        )

    # ------------------------------------------------------------------
    def render(self, document: InvoiceDocument) -> bytes | None:
        """Return the document as PDF bytes, or ``None`` where it does not fit.

        Every copy has to sit on one half page. A bill that runs past it is
        the caller's to print on a full page: half a page of lines followed by
        a second half page holding the totals is neither.
        """
        buffer = BytesIO()
        margin = half_page_margin(self._template)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=HALF_PAGE_SIZE,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title=f"{self._template.title_text} {document.number}",
            author=document.seller.name,
        )
        doc.build(self.story(document, doc.width))
        if doc.page > len(self._template.copy_labels or ("",)):
            return None
        return buffer.getvalue()

    def story(self, document: InvoiceDocument, width: float) -> list[object]:
        """Build every copy of one document, each starting its own page."""
        story: list[object] = []
        for index, label in enumerate(self._template.copy_labels or ("",)):
            if index:
                story.append(PageBreak())
            story.extend(self._one_copy(document, width, label))
        return story

    # ------------------------------------------------------------------
    def _one_copy(
        self, document: InvoiceDocument, width: float, copy_label: str
    ) -> list[object]:
        """Build one copy: head, particulars, lines, summary and signatures."""
        story: list[object] = [self._head(document, width, copy_label)]
        if document.einvoice is not None:
            story.append(self._einvoice(document, width))
        story += [
            self._particulars(document, width),
            self._lines(document, width),
            self._summary(document, width),
            self._signatures(document, width),
        ]
        if self._template.footer_note:
            story.append(Spacer(1, 2))
            story.append(Paragraph(escape(self._template.footer_note), self._centre))
        return story

    def _party(self, party: PartyBlock, *, name_style: ParagraphStyle) -> list[object]:
        """Name, address and identifiers, as tightly as they will read."""
        blocks: list[object] = [Paragraph(escape(party.name), name_style)]
        address = ", ".join(line for line in party.address_lines if line)
        if address:
            blocks.append(Paragraph(escape(address), self._text))
        facts: list[str] = []
        if party.gstin:
            facts.append(f"<b>GSTIN</b> {escape(party.gstin)}")
        if party.pan:
            facts.append(f"<b>PAN</b> {escape(party.pan)}")
        if party.state:
            facts.append(f"<b>State</b> {escape(party.state)}")
        if party.contact:
            facts.append(escape(party.contact))
        if facts:
            blocks.append(Paragraph(" &nbsp; ".join(facts), self._text))
        if party.licences:
            # The firm's drug and food licences, under its address as the
            # trade prints them (backlog 54, 116).
            blocks.append(
                Paragraph(
                    " &nbsp; ".join(
                        f"<b>{escape(kind)}</b> {escape(number)}"
                        for kind, number in party.licences
                    ),
                    self._small,
                )
            )
        return blocks

    def _head(self, document: InvoiceDocument, width: float, copy_label: str) -> Table:
        """Draw the seller on the left; the title and the buyer on the right."""
        right: list[object] = []
        if document.not_final:
            right.append(Paragraph(escape(document.not_final), self._title))
        title = escape(self._template.title_text)
        if copy_label:
            title = f"<font size=6.4>{escape(copy_label)}</font> &nbsp; {title}"
        right.append(Paragraph(title, self._title))
        right.append(Paragraph(escape(document.party_labels[0]), self._small))
        right.extend(self._party(document.buyer, name_style=self._bold))
        ship = document.ship_to
        if ship is not None and ship != document.buyer:
            where = ", ".join(
                [ship.name, *[line for line in ship.address_lines if line]]
            )
            right.append(
                Paragraph(
                    f"<b>{escape(document.party_labels[1])}</b> {escape(where)}",
                    self._small,
                )
            )
        table = Table(
            [[self._party(document.seller, name_style=self._firm), right]],
            colWidths=[width * 0.52, width * 0.48],
        )
        style = self._boxed()
        style.add("LINEAFTER", (0, 0), (0, -1), 0.4, self._rule)
        table.setStyle(style)
        return table

    def _einvoice(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the IRN and acknowledgement beside the signed QR (77 row 11)."""
        stamp = document.einvoice
        assert stamp is not None
        facts = [f"<b>IRN</b> {escape(stamp.irn)}"]
        if stamp.acknowledgement_number:
            facts.append(f"<b>Ack No.</b> {escape(stamp.acknowledgement_number)}")
        if stamp.acknowledged_on:
            facts.append(f"<b>Ack Date</b> {escape(stamp.acknowledged_on)}")
        side = 20 * mm
        code: object = ""
        if stamp.signed_qr:
            code = qr_drawing(stamp.signed_qr, side)
        table = Table(
            [[Paragraph("<br/>".join(facts), self._small), code]],
            colWidths=[width - side - 8, side + 8],
        )
        style = self._boxed()
        style.add("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        table.setStyle(style)
        return table

    def _particulars(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the number, the date and the references in one strip."""
        facts: list[tuple[str, str]] = [
            (document.number_label, document.number),
            (document.date_label, document.date),
        ]
        if document.due_date:
            facts.append(("Due date", document.due_date))
        facts.extend(document.references)
        if document.show_supply_terms:
            if document.place_of_supply:
                facts.append(("Place of supply", document.place_of_supply))
            if document.reverse_charge:
                facts.append(("Reverse charge", "Yes"))
        strip = " &nbsp;&nbsp; ".join(
            f"<b>{escape(label)}</b> {escape(value)}" for label, value in facts
        )
        table = Table([[Paragraph(strip, self._text)]], colWidths=[width])
        table.setStyle(self._boxed())
        return table

    #: What each column needs, as a share of the table; the product's name
    #: takes what is left.
    _WEIGHTS = {
        "SL": 0.030,
        "HSN": 0.068,
        "MRP": 0.068,
        "Qty": 0.078,
        "Free": 0.042,
        INCLUSIVE_RATE: 0.070,
        "Rate": 0.072,
        "Disc.": 0.058,
        "GST %": 0.046,
        "GST": 0.070,
        "Net Amount": 0.088,
        "Batch": 0.078,
        # A whole date, which is ten characters and ran past the edge at 0.060.
        "Exp. Dt": 0.076,
    }

    def _lines(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the goods in the columns the trade's half-page bill carries."""
        inclusive = any(line.entered_rate is not None for line in document.lines)
        header = ["SL", "Product Details", "HSN", "MRP", "Qty", "Free"]
        if inclusive:
            header.append(INCLUSIVE_RATE)
        header += ["Rate", "Disc.", "GST %", "GST", "Net Amount", "Batch", "Exp. Dt"]

        rows: list[list[object]] = [
            [Paragraph(f"<b>{column}</b>", self._small) for column in header]
        ]
        # What the Qty cell holds once its padding is off (design L5 s4).
        room = width * self._WEIGHTS["Qty"] - 4
        for line in document.lines:
            rows.append(self._line_cells(line, inclusive=inclusive, room=room))
        totalled = document.show_total_quantity and bool(document.lines)
        if totalled:
            # The quantities added up under the lines (row P2); the free
            # goods in their own column, as the lines state them.
            total: list[object] = ["" for _ in header]
            total[header.index("Product Details")] = Paragraph(
                f"<b>{TOTAL_QUANTITY}</b>", self._text
            )
            total[header.index("Qty")] = document.total_in_packs or _quantity(
                document.total_quantity
            )
            if document.total_free_quantity:
                total[header.index("Free")] = document.total_free_in_packs or (
                    _quantity(document.total_free_quantity)
                )
            rows.append(total)

        weights = [self._WEIGHTS.get(column, 0.0) for column in header]
        described = 1.0 - sum(weights)
        table = Table(
            rows,
            colWidths=[
                width * (described if column == "Product Details" else weight)
                for column, weight in zip(header, weights, strict=True)
            ],
            repeatRows=1,
        )
        style = self._boxed()
        style.add("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black)
        style.add("LINEAFTER", (0, 0), (-2, -1), 0.3, self._rule)
        style.add("FONTSIZE", (0, 1), (-1, -1), 7.2)
        style.add("ALIGN", (2, 1), (-3, -1), "RIGHT")
        style.add("ALIGN", (0, 0), (0, -1), "CENTER")
        style.add("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        style.add("LEFTPADDING", (0, 0), (-1, -1), 2)
        style.add("RIGHTPADDING", (0, 0), (-1, -1), 2)
        style.add("TOPPADDING", (0, 1), (-1, -1), 1.5)
        style.add("BOTTOMPADDING", (0, 1), (-1, -1), 1.5)
        if totalled:
            style.add("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)
            style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        table.setStyle(style)
        return table

    def _line_cells(
        self, line: InvoiceLineBlock, *, inclusive: bool, room: float
    ) -> list[object]:
        """Return one printed line, its tax stated as a rate and an amount.

        A line in the boxes and pieces layout reads "3/5 (x12)" in Qty and
        "0/2" in Free, in the columns the page already has.
        """
        percent = sum((rate for _, rate, _ in line.taxes), ZERO)
        tax = sum((amount for _, _, amount in line.taxes), ZERO)
        quantity = _quantity(line.quantity)
        free = _quantity(line.free_quantity) if line.free_quantity else ""
        packed = line.packed_quantity
        if packed is not None and line.pack_label is not None:
            quantity = packed_cell(packed, line.pack_label, room, size=7.2)
            free = line.packed_free or ""
        elif line.uom:
            quantity = f"{quantity} {line.uom}"
        cells: list[object] = [
            # Zero marks a continuation row: the same line from another batch
            # (backlog 79).
            str(line.number) if line.number else "",
            Paragraph(line.description, self._text),
            line.hsn or "",
            "" if line.mrp is None else _money(line.mrp),
            quantity,
            free,
        ]
        if inclusive:
            cells.append("" if line.entered_rate is None else _money(line.entered_rate))
        cells += [
            _money(line.rate),
            _money(line.discount) if line.discount else "",
            _rate(percent) if line.taxes else "",
            _money(tax) if line.taxes else "",
            _money(line.total),
            # Wrapped in its cell rather than printed over the expiry.
            Paragraph(escape(line.batch or ""), self._cell),
            line.expiry or "",
        ]
        return cells

    def _by_rate(self, document: InvoiceDocument, width: float) -> Table | Spacer:
        """Draw the GST summary by rate: what was taxed at each, and the tax."""
        if not document.show_tax_summary:
            return Spacer(1, 0)
        grouped: dict[Decimal, dict[str, Decimal]] = {}
        codes: list[str] = []

        def add(
            taxable: Decimal, taxes: tuple[tuple[str, Decimal, Decimal], ...]
        ) -> None:
            """Put one line or charge under the total rate it was taxed at."""
            percent = sum((rate for _, rate, _ in taxes), ZERO)
            bucket = grouped.setdefault(percent, {"taxable": ZERO})
            bucket["taxable"] += taxable
            for code, _, amount in taxes:
                bucket[code] = bucket.get(code, ZERO) + amount
                if code not in codes:
                    codes.append(code)

        for line in document.lines:
            add(line.taxable, line.taxes)
        # A charge taxed at its own rate joins the rate it was taxed at.
        for charge in document.taxed_charges:
            add(charge.amount, charge.taxes)
        if not grouped:
            return Spacer(1, 0)

        header = ["GST %", "Taxable value", *codes, "GST"]
        rows: list[list[object]] = [
            [Paragraph(f"<b>{column}</b>", self._small) for column in header]
        ]
        for percent in sorted(grouped):
            bucket = grouped[percent]
            tax = sum((bucket.get(code, ZERO) for code in codes), ZERO)
            rows.append(
                [
                    f"{_rate(percent)}%",
                    _money(bucket["taxable"]),
                    *[_money(bucket.get(code, ZERO)) for code in codes],
                    _money(tax),
                ]
            )
        table = Table(rows, colWidths=[width / len(header)] * len(header))
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, self._rule),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return table

    def _figures(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the totals: taxable value, discount, tax, round-off, payable."""
        rows: list[list[str]] = []
        if document.bill_discount:
            rows.append(["Lines", _money(document.gross_before_bill_discount)])
            rows.append(["Discount on bill", f"-{_money(document.bill_discount)}"])
        rows.append(["Taxable value", _money(document.taxable_total)])
        line_discount = sum((line.discount for line in document.lines), ZERO)
        if line_discount:
            rows.append(["Total discount", _money(line_discount)])
        totals_by_code: dict[str, Decimal] = {}
        for line in document.lines:
            for code, _, amount in line.taxes:
                totals_by_code[code] = totals_by_code.get(code, ZERO) + amount
        for charge in document.taxed_charges:
            rows.append([charge.name[:28], _money(charge.amount)])
            for code, _, amount in charge.taxes:
                totals_by_code[code] = totals_by_code.get(code, ZERO) + amount
        for code, amount in totals_by_code.items():
            rows.append([code, _money(amount)])
        if not totals_by_code and document.tax_total:
            rows.append(["Tax", _money(document.tax_total)])
        if document.charges:
            rows.append(["Other charges", _money(document.charges)])
        if document.round_off:
            rows.append(["Round off", _money(document.round_off)])
        rows.append(
            [f"Net payable {document.currency_symbol}", _money(document.grand_total)]
        )
        table = Table(rows, colWidths=[width * 0.56, width * 0.44])
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, -1), (-1, -1), 8.6),
                ]
            )
        )
        return table

    def _summary(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the GST summary, the words and the bank beside the totals."""
        left_width = width * 0.62
        right_width = width - left_width
        left: list[object] = [self._by_rate(document, left_width - 8), Spacer(1, 2)]
        left.append(
            Paragraph(
                f"<b>{escape(amount_in_words(document.grand_total))}</b>", self._text
            )
        )
        if self._template.show_bank_details and self._template.bank_details:
            bank = ", ".join(
                line.strip()
                for line in self._template.bank_details.splitlines()
                if line.strip()
            )
            left.append(Paragraph(f"<b>Our bank</b> {escape(bank)}", self._small))
        if self._template.terms:
            terms = " ".join(
                line.strip()
                for line in self._template.terms.splitlines()
                if line.strip()
            )
            left.append(Paragraph(escape(terms), self._small))
        table = Table(
            [[left, self._figures(document, right_width - 8)]],
            colWidths=[left_width, right_width],
        )
        style = self._boxed()
        style.add("LINEAFTER", (0, 0), (0, -1), 0.4, self._rule)
        table.setStyle(style)
        return table

    def _signatures(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the customer's signature, the pay-by-UPI code and the firm's."""
        left: list[object] = [Paragraph("E. &amp; O.E.", self._small)]
        if self._template.jurisdiction:
            left.append(
                Paragraph(
                    f"Subject to {escape(self._template.jurisdiction)} jurisdiction.",
                    self._small,
                )
            )
        left += [Spacer(1, 14), Paragraph("Customer signature", self._text)]

        middle: list[object] = []
        if document.upi is not None:
            side = 15 * mm
            pay = Table(
                [
                    [
                        qr_drawing(document.upi.uri, side),
                        [
                            Paragraph("<b>Scan to pay by UPI</b>", self._small),
                            Paragraph(
                                f"{document.currency_symbol} "
                                f"{_money(document.upi.amount)}",
                                self._text,
                            ),
                            Paragraph(f"to {escape(document.upi.upi_id)}", self._small),
                        ],
                    ]
                ],
                colWidths=[side + 4, max(width * 0.34 - side - 12, 40)],
            )
            pay.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
            middle.append(pay)
        elif self._template.declaration:
            middle.append(Paragraph(escape(self._template.declaration), self._small))

        right: list[object] = [
            Paragraph(
                escape(self._template.signatory_text or f"For {document.seller.name}"),
                self._bold_right,
            ),
            Spacer(1, 16),
            Paragraph("Authorised signatory", self._right),
        ]
        table = Table(
            [[left, middle or "", right]],
            colWidths=[width * 0.28, width * 0.34, width * 0.38],
        )
        table.setStyle(self._boxed())
        return table

    def _boxed(self) -> TableStyle:
        """Return the ruled box every block of the bill sits inside."""
        return TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, self._rule),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
