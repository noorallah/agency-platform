"""Draw a sales invoice in the trade's own boxed layout (backlog 143).

The second full-page layout a firm may choose in *Print settings*, beside the
standard one. It is drawn after the customer's own bill (`long bill.pdf` in
his papers, row P2): the firm's name, its licences, who took the order and the
market down the left; the bill's number and date in the middle; the buyer
under *Sold To* on the right. Then one ruled table of lines with the trade's
columns -- MRP, the dealer price with GST, the quantity, the free goods, the
price to the retailer, the discount, the GST rate and the net value, then the
batch, when it was made and when it expires. Under the lines the summary by
HSN and rate, the totals the trade reads (gross, discount, each GST head,
round off, net payable), the amount in words, and the terms as a list.

What it keeps from the standard layout is everything statutory: the title,
both GSTINs, the HSN of every line, the GST rate of every line, each head's
amount in the totals, the summary by HSN, the place of supply and the total in
words. The buyer's licences print under his details, not at the foot as the
sample has them (the owner, 2026-10-14).

Only the arrangement is new. The figures are the record's, as the standard
layout prints them; nothing is recomputed except what the trade's columns
derive from them (the dealer price is the rate with its GST added).
"""

from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.sales_invoice.services.invoice_pdf import (
    TOTAL_QUANTITY,
    ZERO,
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    amount_in_words,
    packed_cell,
)

#: The columns of the trade's bill, in its order, with the share of the line
#: each takes. Product Details takes what is left.
_COLUMNS: tuple[tuple[str, float], ...] = (
    ("SL", 0.030),
    ("Product Details", 0.0),
    ("HSN", 0.062),
    ("M.R.P", 0.058),
    ("D.Price", 0.066),
    ("QTY", 0.056),
    ("Free", 0.038),
    ("P.T.R.", 0.066),
    ("Disc.", 0.058),
    ("GST%", 0.046),
    ("Net Value", 0.074),
    ("Batch", 0.066),
    ("MfgDt", 0.046),
    ("ExpDt", 0.056),
)

_SIZE = 7.0
_HUNDRED = Decimal("100")


def _money(value: Decimal) -> str:
    """Format an amount as the trade's bill does: two decimals, grouped."""
    return f"{value:,.2f}"


def _price(value: Decimal) -> str:
    """Format a price per unit: three decimals below a thousand, as printed.

    The trade's bill carries the third decimal where it matters -- 73.278 --
    and drops it on a price large enough that a paisa is noise.
    """
    return f"{value:,.3f}" if abs(value) < 1000 else f"{value:,.2f}"


def _quantity(value: Decimal) -> str:
    """Format a quantity with two decimals, as the trade's bill does."""
    return f"{value:,.2f}"


def _rate_of(line: InvoiceLineBlock) -> Decimal:
    """Return the GST rate charged on a line, all its heads together."""
    return sum((rate for _, rate, _ in line.taxes), ZERO)


def _dealer_price(line: InvoiceLineBlock) -> Decimal:
    """Return the price per unit with its GST: what the trade calls D.Price.

    The rate as typed where the bill was typed with GST included; otherwise
    the taxable rate with the line's GST added to it.
    """
    if line.entered_rate is not None:
        return line.entered_rate
    return line.rate * (1 + _rate_of(line) / _HUNDRED)


class TradeInvoiceRenderer(InvoicePdfRenderer):
    """Draw one invoice in the trade's boxed layout.

    Built on the standard renderer so the paper, the copies, the styles, the
    e-invoice block and the pay-by-UPI block are the same ones.
    """

    def _is_trade(self) -> bool:
        """Say that this renderer draws the trade's layout itself."""
        return True

    def _one_copy(
        self, document: InvoiceDocument, width: float, copy_label: str
    ) -> list[object]:
        """Build the flowables for a single copy of the bill."""
        story: list[object] = []
        if document.not_final:
            story.extend([self._title_bar(width, "", document.not_final), Spacer(1, 2)])
        story.append(self._head(document, width, copy_label))
        if document.einvoice is not None:
            story.append(self._einvoice_block(document.einvoice, width))
        story.append(self._trade_lines(document, width))
        if document.place_of_supply and document.show_supply_terms:
            story.append(
                Paragraph(
                    f"Place of supply: {escape(document.place_of_supply)}",
                    self._centred(),
                )
            )
        story.append(self._hsn_summary(document, width))
        story.append(
            KeepTogether(
                [self._trade_totals(document, width), self._trade_foot(document, width)]
            )
        )
        if self._template.footer_note:
            story.append(Spacer(1, 3))
            story.append(Paragraph(self._template.footer_note, self._centred()))
        return story

    # ------------------------------------------------------------------
    def _cell(self, text: str, bold: bool = False) -> Paragraph:
        """Return one line of the head, set small."""
        style = ParagraphStyle(
            "trade-cell",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=_SIZE + 0.4,
            leading=_SIZE + 2.6,
        )
        return Paragraph(text, style)

    def _centred(self) -> ParagraphStyle:
        """Return the small centred style of a line between the blocks."""
        return ParagraphStyle("trade-centred", parent=self._small, alignment=TA_CENTER)

    def _seller_cells(self, seller: PartyBlock) -> list[Paragraph]:
        """Return the firm: its address, its phone and GSTIN, then its licences."""
        cells = [
            self._cell(escape(line)) for line in seller.address_lines if line.strip()
        ]
        reach = " ".join(
            part
            for part in (
                escape(seller.contact or ""),
                f"GSTIN.{escape(seller.gstin)}" if seller.gstin else "",
            )
            if part
        )
        if reach:
            cells.append(self._cell(reach, bold=True))
        licences = [
            f"{escape(kind)} : {escape(number)}" for kind, number in seller.licences
        ]
        # Two to a line, as the trade's bill sets its drug licences.
        for start in range(0, len(licences), 2):
            cells.append(self._cell("  ".join(licences[start : start + 2])))
        return cells

    def _buyer_cells(self, buyer: PartyBlock) -> list[Paragraph]:
        """Return the buyer, his GSTIN, and his licences under his details."""
        cells = [self._cell(f"Sold To :{escape(buyer.name)}", bold=True)]
        cells += [
            self._cell(escape(line)) for line in buyer.address_lines if line.strip()
        ]
        if buyer.gstin:
            cells.append(self._cell(f"GSTIN.{escape(buyer.gstin)}", bold=True))
        if buyer.contact:
            cells.append(self._cell(escape(buyer.contact)))
        for kind, number in buyer.licences:
            cells.append(self._cell(f"{escape(kind)} : {escape(number)}"))
        return cells

    def _head(self, document: InvoiceDocument, width: float, copy_label: str) -> Table:
        """Draw the firm, the bill's particulars and the buyer, in one box."""
        name = Paragraph(
            escape(document.seller.name),
            ParagraphStyle(
                "trade-name", fontName="Helvetica-Bold", fontSize=12, leading=14
            ),
        )
        banner = Paragraph(
            escape(self._template.title_text),
            ParagraphStyle(
                "trade-title",
                fontName="Helvetica-Bold",
                fontSize=10,
                leading=12,
                alignment=TA_RIGHT,
            ),
        )
        copy = self._cell(escape(copy_label), bold=True) if copy_label else ""

        market = [value for label, value in document.references if label == "Market"]
        others = [
            (label, value) for label, value in document.references if label != "Market"
        ]
        left: list[Paragraph] = []
        if document.order_by:
            left.append(self._cell(f"Order By : {escape(document.order_by)}"))
        for value in market:
            left.append(self._cell(f"Market : {escape(value)}"))

        middle = [
            self._cell(f"Inv No.{escape(document.number)}", bold=True),
            self._cell(f"Inv Dt.{escape(document.date)}", bold=True),
        ]
        if document.due_date:
            middle.append(self._cell(f"Due Dt.{escape(document.due_date)}"))
        for label, value in others:
            middle.append(self._cell(f"{escape(label)} : {escape(value)}"))
        if document.show_supply_terms:
            middle.append(
                self._cell(
                    f"Reverse charge : {'Yes' if document.reverse_charge else 'No'}"
                )
            )

        if document.ship_to is None:
            shipped: list[Paragraph] = [
                self._cell("Shipped to Sold Address", bold=True)
            ]
        else:
            shipped = [self._cell(f"Shipped to : {escape(document.ship_to.name)}")]
            shipped += [
                self._cell(escape(line))
                for line in document.ship_to.address_lines
                if line.strip()
            ]
            if document.ship_to.gstin:
                shipped.append(self._cell(f"GSTIN.{escape(document.ship_to.gstin)}"))

        widths = [width * 0.34, width * 0.22, width * 0.44]
        rows: list[list[object]] = [
            [name, copy, banner],
            [
                self._seller_cells(document.seller),
                "",
                self._buyer_cells(document.buyer),
            ],
            [left or "", middle, shipped],
        ]
        table = Table(rows, colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                    ("SPAN", (0, 1), (1, 1)),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.black),
                    ("LINEAFTER", (0, 0), (0, 0), 0.6, colors.black),
                    ("LINEAFTER", (1, 0), (1, -1), 0.6, colors.black),
                    ("LINEAFTER", (0, 2), (0, 2), 0.6, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]
            )
        )
        return table

    @staticmethod
    def _quantities(line: InvoiceLineBlock, room: float) -> tuple[str, str]:
        """Return the QTY and Free cells: "3/5 (x12)" and "0/2" in boxes (L5)."""
        packed = line.packed_quantity
        if packed is not None and line.pack_label is not None:
            return (
                packed_cell(packed, line.pack_label, room, size=_SIZE),
                line.packed_free or "",
            )
        free = _quantity(line.free_quantity) if line.free_quantity else ""
        return _quantity(line.quantity), free

    # ------------------------------------------------------------------
    def _trade_lines(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the lines in the trade's columns, each figure from the record."""
        header = [column for column, _ in _COLUMNS]
        weights = [share for _, share in _COLUMNS]
        described = 1.0 - sum(weights)
        widths = [width * (described if share == 0.0 else share) for share in weights]
        wrapped = ParagraphStyle(
            "trade-wrap", parent=self._body, fontSize=_SIZE, leading=_SIZE + 1.4
        )
        rows: list[list[object]] = [
            [Paragraph(f"<b>{column}</b>", self._small) for column in header]
        ]
        room = widths[header.index("QTY")] - 4
        for line in document.lines:
            rows.append(
                [
                    # Zero marks a continuation row: the same line from
                    # another batch (backlog 79).
                    str(line.number) if line.number else "",
                    Paragraph(escape(line.description), wrapped),
                    line.hsn or "",
                    "" if line.mrp is None else _money(line.mrp),
                    _price(_dealer_price(line)),
                    *self._quantities(line, room),
                    _price(line.rate),
                    _money(line.discount) if line.discount else "",
                    f"{_rate_of(line):.2f}",
                    _money(line.total),
                    # A batch longer than its column wraps in its own cell
                    # (D-SELL-98) rather than printing over the next.
                    Paragraph(escape(line.batch or ""), wrapped),
                    line.manufactured or "",
                    line.expiry or "",
                ]
            )
        totalled = document.show_total_quantity and bool(document.lines)
        if totalled:
            free = document.total_free_quantity
            total_row: list[object] = ["" for _ in header]
            total_row[1] = Paragraph(f"<b>{TOTAL_QUANTITY}</b>", wrapped)
            total_row[5] = document.total_in_packs or _quantity(document.total_quantity)
            total_row[6] = (
                (document.total_free_in_packs or _quantity(free)) if free else ""
            )
            rows.append(total_row)

        table = Table(rows, colWidths=widths, repeatRows=1)
        style = TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                ("INNERGRID", (0, 0), (-1, 0), 0.4, colors.black),
                ("FONTSIZE", (0, 1), (-1, -1), _SIZE),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]
        )
        if totalled:
            style.add("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)
            style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        table.setStyle(style)
        return table

    def _hsn_summary(self, document: InvoiceDocument, width: float) -> Table | Spacer:
        """Draw the summary by HSN and rate a tax invoice has to carry."""
        if not document.show_tax_summary:
            return Spacer(1, 0)
        grouped: dict[tuple[str, Decimal], list[Decimal]] = {}
        for line in document.lines:
            bucket = grouped.setdefault((line.hsn or "-", _rate_of(line)), [ZERO] * 3)
            bucket[0] += line.quantity
            bucket[1] += line.taxable
            bucket[2] += sum((tax for _, _, tax in line.taxes), ZERO)
        for charge in document.taxed_charges:
            rate = sum((rate for _, rate, _ in charge.taxes), ZERO)
            bucket = grouped.setdefault((charge.hsn or "-", rate), [ZERO] * 3)
            bucket[1] += charge.amount
            bucket[2] += sum((tax for _, _, tax in charge.taxes), ZERO)
        if not grouped:
            return Spacer(1, 0)
        rows: list[list[object]] = [
            [
                Paragraph(f"<b>{column}</b>", self._small)
                for column in ("HSN", "GST%", "QTY", "Taxable Val", "GST AMT")
            ]
        ]
        for (hsn, rate), (quantity, taxable, tax) in grouped.items():
            rows.append(
                [
                    hsn,
                    f"{rate:.2f}",
                    _quantity(quantity) if quantity else "",
                    _money(taxable),
                    _money(tax),
                ]
            )
        table = Table(rows, colWidths=[width * 0.12] * 5, hAlign="CENTER")
        table.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                    ("FONTSIZE", (0, 1), (-1, -1), _SIZE),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return table

    def _trade_totals(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the GST by rate on the left and the bill's arithmetic on the right.

        Gross is what the lines came to before any discount, so that gross less
        the discount is the taxable value the GST was charged on, and the rows
        add down to the net payable as printed.
        """
        by_rate: dict[Decimal, list[Decimal]] = {}
        heads: dict[str, Decimal] = {}
        for line in document.lines:
            bucket = by_rate.setdefault(_rate_of(line), [ZERO, ZERO])
            bucket[0] += line.taxable
            for code, _, amount in line.taxes:
                bucket[1] += amount
                heads[code] = heads.get(code, ZERO) + amount
        for charge in document.taxed_charges:
            for code, _, amount in charge.taxes:
                heads[code] = heads.get(code, ZERO) + amount

        rate_rows: list[list[str]] = [["", "Value", "GST Amt"]]
        for rate, (taxable, tax) in sorted(by_rate.items()):
            rate_rows.append([f"{rate.normalize():f}%", _money(taxable), _money(tax)])
        rates = Table(rate_rows, colWidths=[width * 0.07, width * 0.13, width * 0.13])
        rates.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), _SIZE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
                ]
            )
        )

        discount = sum((line.discount for line in document.lines), ZERO)
        discount += document.bill_discount
        figures: list[list[str]] = [
            ["Gross", _money(document.taxable_total + discount)],
        ]
        if discount:
            figures.append(["Less discount", f"-{_money(discount)}"])
        figures.append(["Taxable value", _money(document.taxable_total)])
        for charge in document.taxed_charges:
            figures.append([charge.name[:24], _money(charge.amount)])
        for code, amount in heads.items():
            figures.append([code, _money(amount)])
        if not heads and document.tax_total:
            figures.append(["GST", _money(document.tax_total)])
        if document.charges:
            figures.append(["Other charges", _money(document.charges)])
        if document.round_off:
            figures.append(["(+/-)", _money(document.round_off)])
        figures.append(["Net Payable:", _money(document.grand_total)])
        right = Table(figures, colWidths=[width * 0.20, width * 0.17])
        right.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -2), _SIZE + 0.6),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
                    ("BOX", (0, -1), (-1, -1), 0.8, colors.black),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, -1), (-1, -1), 10),
                    ("TOPPADDING", (0, -1), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 3),
                ]
            )
        )
        table = Table([[rates, right]], colWidths=[width * 0.60, width * 0.40])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def _terms(self, document: InvoiceDocument) -> list[str]:
        """Return the terms as the trade lists them, one point a line."""
        points: list[str] = []
        if self._template.jurisdiction:
            points.append(f"Subject to {self._template.jurisdiction} Jurisdiction.")
        if self._template.show_bank_details and self._template.bank_details:
            bank = " ".join(
                line.strip()
                for line in self._template.bank_details.splitlines()
                if line.strip()
            )
            points.append(f"Our Bank : {bank}")
        for line in (self._template.terms or "").splitlines():
            text = line.strip().lstrip("*").strip()
            if text:
                points.append(text)
        if self._template.declaration:
            points.append(self._template.declaration)
        return points

    def _trade_foot(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the amount in words, the signatures and the terms."""
        words = self._cell(escape(amount_in_words(document.grand_total)), bold=True)
        firm = Paragraph(
            escape(self._template.signatory_text or f"For {document.seller.name}"),
            ParagraphStyle(
                "trade-for",
                fontName="Helvetica-Bold",
                fontSize=_SIZE + 1.5,
                leading=_SIZE + 3.5,
                alignment=TA_RIGHT,
            ),
        )
        terms: list[object] = [self._cell("Terms &amp; Conditions :", bold=True)]
        terms += [self._cell(f"* {escape(point)}") for point in self._terms(document)]
        signature: list[object] = []
        if document.upi is not None:
            signature.append(self._upi_block(document.upi, document, width * 0.36))
            signature.append(Spacer(1, 4))
        else:
            signature.append(Spacer(1, 26))
        signature.append(
            Paragraph(
                "Authorised Signatory",
                ParagraphStyle("trade-sign", parent=self._small, alignment=TA_RIGHT),
            )
        )
        rows: list[list[object]] = [
            [words, self._cell("E&amp;O.E.,"), self._cell("Customer Sign.,"), firm],
            [terms, "", "", signature],
        ]
        table = Table(
            rows, colWidths=[width * 0.44, width * 0.10, width * 0.14, width * 0.32]
        )
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                    ("SPAN", (0, 1), (2, 1)),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("VALIGN", (-1, 1), (-1, 1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table
