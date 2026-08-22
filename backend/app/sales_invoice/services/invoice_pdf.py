"""Draw a sales invoice as a PDF a customer can be sent.

Rendered on the backend rather than in the desktop client for two reasons: the
layout then has to be right in exactly one place, and the same bytes are what
an email will attach when that arrives.

Everything statutory is read from the invoice itself, never recomputed. The tax
components are the reason `sales_invoice_line_taxes` exists -- asking the rule
engine again at print time can answer differently from what the customer was
billed, because rules are effective-dated. What a firm may change is the matter
around that spine, and it arrives here as a `DocumentPrintTemplate`.

Pure Python: `reportlab` has no system dependencies, which keeps the Windows
installer free of GTK and Pango.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ZERO = Decimal("0")

#: Indian numbering, because the amount in words on an Indian invoice is read
#: in lakh and crore rather than in millions.
_ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = (
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
)


def _under_hundred(value: int) -> str:
    """Spell a number below one hundred."""
    if value < 20:
        return _ONES[value]
    tens, ones = divmod(value, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _under_thousand(value: int) -> str:
    """Spell a number below one thousand."""
    hundreds, rest = divmod(value, 100)
    words = f"{_ONES[hundreds]} Hundred" if hundreds else ""
    if rest:
        words = f"{words} {_under_hundred(rest)}" if words else _under_hundred(rest)
    return words


def amount_in_words(amount: Decimal, currency: str = "Rupees") -> str:
    """Spell an amount the way an Indian invoice states it.

    Statutory on a tax invoice, and grouped in lakh and crore -- 1,25,000 reads
    as *One Lakh Twenty Five Thousand*, not *One Hundred Twenty Five Thousand*.
    """
    whole = int(amount)
    paise = int((amount - whole) * 100)
    if whole == 0 and paise == 0:
        return f"Zero {currency} Only"

    groups: list[tuple[int, str]] = []
    crore, whole = divmod(whole, 10_000_000)
    lakh, whole = divmod(whole, 100_000)
    thousand, hundreds = divmod(whole, 1_000)
    if crore:
        groups.append((crore, "Crore"))
    if lakh:
        groups.append((lakh, "Lakh"))
    if thousand:
        groups.append((thousand, "Thousand"))

    words = " ".join(
        f"{_under_thousand(count)} {label}" for count, label in groups if count
    )
    if hundreds:
        words = f"{words} {_under_thousand(hundreds)}".strip()
    words = f"{words} {currency}".strip()
    if paise:
        words = f"{words} and {_under_hundred(paise)} Paise"
    return f"{words} Only"


@dataclass(frozen=True, slots=True)
class PartyBlock:
    """One side of the bill: who is selling, or who is being billed."""

    name: str
    address_lines: list[str]
    gstin: str | None = None
    pan: str | None = None
    state: str | None = None
    contact: str | None = None


@dataclass(frozen=True, slots=True)
class InvoiceLineBlock:
    """One printed line, with the tax the customer was actually charged."""

    number: int
    description: str
    hsn: str | None
    quantity: Decimal
    uom: str | None
    rate: Decimal
    discount: Decimal
    taxable: Decimal
    total: Decimal
    #: Supplied free with this line, charged for at nothing. Printed beside
    #: the quantity rather than in a column of its own, which would be empty
    #: on almost every bill: "10 + 1 free" is what the storekeeper counted.
    free_quantity: Decimal = ZERO
    batch: str | None = None
    expiry: str | None = None
    #: (code, percentage, amount) as recorded on the line.
    taxes: tuple[tuple[str, Decimal, Decimal], ...] = ()


@dataclass(frozen=True, slots=True)
class InvoiceDocument:
    """Everything the renderer needs, already resolved."""

    number: str
    date: str
    due_date: str | None
    place_of_supply: str | None
    reverse_charge: bool
    seller: PartyBlock
    buyer: PartyBlock
    ship_to: PartyBlock | None
    lines: tuple[InvoiceLineBlock, ...]

    taxable_total: Decimal
    tax_total: Decimal
    charges: Decimal
    round_off: Decimal
    grand_total: Decimal
    currency_symbol: str = "Rs."
    #: What came off the whole document, above the line discounts. Stated on
    #: its own row rather than folded into the taxable value, because a
    #: customer who negotiated it looks for it by name.
    bill_discount: Decimal = ZERO

    #: What the lines came to before that deduction. Printed only where there
    #: is a deduction to explain.
    gross_before_bill_discount: Decimal = ZERO
    references: tuple[tuple[str, str], ...] = ()
    #: What the two address blocks are called. A bill is billed to and shipped
    #: to; an order is placed with a supplier and delivered to a warehouse.
    party_labels: tuple[str, str] = ("BILLED TO", "SHIPPED TO")
    #: The HSN-wise summary is statutory on a tax invoice and meaningless on a
    #: purchase order, which is a request rather than a charge.
    show_tax_summary: bool = True
    #: Place of supply and the reverse-charge flag likewise belong to a bill.
    show_supply_terms: bool = True
    #: What the document calls its own number, date and total in words. An
    #: order that labelled itself "Invoice no." would be lying on its face.
    number_label: str = "Invoice no."
    date_label: str = "Invoice date"
    words_label: str = "AMOUNT CHARGEABLE, IN WORDS"


@dataclass(frozen=True, slots=True)
class TemplateSettings:
    """The parts a firm owns. Defaults match the platform template."""

    title_text: str = "TAX INVOICE"
    accent_color: str = "#0B3D6B"
    header_note: str | None = None
    show_bank_details: bool = True
    bank_details: str | None = None
    terms: str | None = None
    declaration: str | None = (
        "Certified that the particulars given above are true, and that the "
        "amount charged is the price actually payable."
    )
    jurisdiction: str | None = None
    footer_note: str | None = None
    signatory_text: str | None = None
    show_discount_column: bool = True
    show_batch_column: bool = False
    show_expiry_column: bool = False
    copy_labels: tuple[str, ...] = ()
    page_size: str = "A4"
    margin_mm: Decimal = Decimal("12")


def _money(value: Decimal) -> str:
    """Format an amount with thousands separators and two decimals."""
    return f"{value:,.2f}"


def _quantity(value: Decimal) -> str:
    """Format a quantity without trailing zeros beyond three decimals."""
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


class InvoicePdfRenderer:
    """Turn one resolved invoice into PDF bytes."""

    def __init__(self, template: TemplateSettings | None = None) -> None:
        """Keep the firm's template, or fall back to the platform default."""
        self._template = template or TemplateSettings()
        accent = self._template.accent_color or "#0B3D6B"
        try:
            self._accent = colors.HexColor(accent)
        except ValueError:
            # A firm that saved something that is not a colour still gets a
            # bill; it just gets the default one.
            self._accent = colors.HexColor("#0B3D6B")
        self._tint = colors.Color(
            self._accent.red + (1 - self._accent.red) * 0.88,
            self._accent.green + (1 - self._accent.green) * 0.88,
            self._accent.blue + (1 - self._accent.blue) * 0.88,
        )
        self._rule = colors.HexColor("#8E949E")
        self._body = ParagraphStyle(
            "body", fontName="Helvetica", fontSize=8, leading=10.5
        )
        self._small = ParagraphStyle(
            "small",
            fontName="Helvetica",
            fontSize=6.8,
            leading=9,
            textColor=colors.HexColor("#4A4F58"),
        )
        self._label = ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=8.5,
            textColor=colors.HexColor("#4A4F58"),
        )
        self._strong = ParagraphStyle(
            "strong", fontName="Helvetica-Bold", fontSize=9.5, leading=12
        )
        self._title = ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            alignment=TA_CENTER,
            textColor=self._accent,
        )
        self._copy = ParagraphStyle(
            "copy",
            fontName="Helvetica",
            fontSize=6.5,
            leading=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4A4F58"),
        )
        self._right = ParagraphStyle(
            "right", fontName="Helvetica", fontSize=8, leading=10.5, alignment=TA_RIGHT
        )

    # ------------------------------------------------------------------
    def render(self, document: InvoiceDocument) -> bytes:
        """Return the invoice as PDF bytes, one page set per copy."""
        buffer = BytesIO()
        margin = float(self._template.margin_mm) * mm
        page = A5 if self._template.page_size.upper() == "A5" else A4
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title=f"{self._template.title_text} {document.number}",
            author=document.seller.name,
        )
        width = doc.width

        story: list[object] = []
        copies = self._template.copy_labels or ("",)
        for index, label in enumerate(copies):
            if index:
                story.append(PageBreak())
            story.extend(self._one_copy(document, width, label))
        doc.build(story)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    def _one_copy(
        self, document: InvoiceDocument, width: float, copy_label: str
    ) -> list[object]:
        """Build the flowables for a single copy of the bill."""
        story: list[object] = [
            self._title_bar(width, copy_label),
            Spacer(1, 4),
            self._parties(document, width),
            Spacer(1, 2),
            self._addresses(document, width),
            Spacer(1, 4),
            self._lines_table(document, width),
            self._totals(document, width),
            Spacer(1, 4),
            self._tax_summary(document, width),
            Spacer(1, 4),
        ]
        story.append(KeepTogether(self._footer(document, width)))
        return story

    def _title_bar(self, width: float, copy_label: str) -> Table:
        """Draw the banner, saying which copy this is where a firm prints several."""
        rows = [[Paragraph(self._template.title_text, self._title)]]
        if copy_label:
            rows.append([Paragraph(copy_label, self._copy)])
        table = Table(rows, colWidths=[width])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.1, colors.black),
                    ("BACKGROUND", (0, 0), (-1, -1), self._tint),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def _party_paragraphs(self, party: PartyBlock) -> list[Paragraph]:
        """Name, address and the identifiers a tax invoice must carry."""
        blocks = [Paragraph(party.name, self._strong)]
        for line in party.address_lines:
            if line:
                blocks.append(Paragraph(line, self._body))
        identifiers = []
        if party.gstin:
            identifiers.append(f"<b>GSTIN</b> {party.gstin}")
        if party.pan:
            identifiers.append(f"<b>PAN</b> {party.pan}")
        if party.state:
            identifiers.append(f"<b>State</b> {party.state}")
        if party.contact:
            identifiers.append(party.contact)
        for line in identifiers:
            blocks.append(Paragraph(line, self._small))
        return blocks

    def _parties(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the seller, and the document's own particulars beside it."""
        meta: list[tuple[str, str]] = [
            (document.number_label, document.number),
            (document.date_label, document.date),
        ]
        if document.due_date:
            meta.append(("Due date", document.due_date))
        meta.extend(document.references)
        if document.show_supply_terms:
            if document.place_of_supply:
                meta.append(("Place of supply", document.place_of_supply))
            meta.append(("Reverse charge", "Yes" if document.reverse_charge else "No"))

        meta_rows = [
            [Paragraph(key, self._label), Paragraph(value, self._body)]
            for key, value in meta
        ]
        meta_table = Table(meta_rows, colWidths=[width * 0.16, width * 0.24])
        meta_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        table = Table(
            [[self._party_paragraphs(document.seller), meta_table]],
            colWidths=[width * 0.58, width * 0.42],
        )
        table.setStyle(self._boxed())
        return table

    def _addresses(self, document: InvoiceDocument, width: float) -> Table:
        """Billed to on the left, shipped to on the right."""
        ship = document.ship_to or document.buyer
        table = Table(
            [
                [
                    Paragraph(document.party_labels[0], self._label),
                    Paragraph(document.party_labels[1], self._label),
                ],
                [self._party_paragraphs(document.buyer), self._party_paragraphs(ship)],
            ],
            colWidths=[width * 0.5, width * 0.5],
        )
        style = self._boxed()
        style.add("BOTTOMPADDING", (0, 0), (-1, 0), 1)
        table.setStyle(style)
        return table

    def _line_columns(self) -> list[str]:
        """Return the columns this firm prints, statutory ones always included."""
        columns = ["Sl", "Description", "HSN", "Qty", "UOM", "Rate"]
        if self._template.show_batch_column:
            columns.append("Batch")
        if self._template.show_expiry_column:
            columns.append("Expiry")
        if self._template.show_discount_column:
            columns.append("Disc.")
        columns.append("Taxable")
        return columns

    def _lines_table(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the goods, and the tax charged on each of them."""
        component_codes: list[str] = []
        for line in document.lines:
            for code, _, _ in line.taxes:
                if code not in component_codes:
                    component_codes.append(code)

        header = self._line_columns()
        for code in component_codes:
            header.extend([f"{code} %", f"{code} amt"])
        header.append("Amount")

        rows: list[list[object]] = [
            [Paragraph(f"<b>{column}</b>", self._small) for column in header]
        ]
        for line in document.lines:
            charged = {code: (percent, amount) for code, percent, amount in line.taxes}
            cells: list[object] = [
                str(line.number),
                Paragraph(line.description, self._body),
                line.hsn or "",
                (
                    f"{_quantity(line.quantity)} + "
                    f"{_quantity(line.free_quantity)} free"
                    if line.free_quantity
                    else _quantity(line.quantity)
                ),
                line.uom or "",
                _money(line.rate),
            ]
            if self._template.show_batch_column:
                cells.append(line.batch or "")
            if self._template.show_expiry_column:
                cells.append(line.expiry or "")
            if self._template.show_discount_column:
                cells.append(_money(line.discount))
            cells.append(_money(line.taxable))
            for code in component_codes:
                percent, amount = charged.get(code, (ZERO, ZERO))
                cells.extend([f"{percent:.2f}", _money(amount)])
            cells.append(_money(line.total))
            rows.append(cells)

        table = Table(rows, colWidths=self._line_widths(width, header), repeatRows=1)
        style = self._boxed()
        style.add("BACKGROUND", (0, 0), (-1, 0), self._tint)
        style.add("TEXTCOLOR", (0, 0), (-1, 0), self._accent)
        style.add("INNERGRID", (0, 0), (-1, -1), 0.4, self._rule)
        style.add("ALIGN", (2, 1), (-1, -1), "RIGHT")
        style.add("ALIGN", (0, 0), (0, -1), "CENTER")
        style.add("FONTSIZE", (0, 1), (-1, -1), 7.6)
        style.add("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        table.setStyle(style)
        return table

    #: What each column needs, as a share of the table. An even split made a
    #: bill with batch, expiry and two tax components wrap its own headings
    #: mid-word -- "Expir / y" -- because a heading is a paragraph and a
    #: paragraph in a narrow cell breaks wherever it must.
    _COLUMN_WEIGHTS = {
        "Sl": 0.030,
        "HSN": 0.060,
        "Qty": 0.050,
        "UOM": 0.052,
        "Rate": 0.070,
        "Batch": 0.064,
        "Expiry": 0.062,
        "Disc.": 0.060,
        "Taxable": 0.080,
        "Amount": 0.085,
    }
    #: Every tax column: a rate and an amount per component.
    _RATE_WEIGHT = 0.052
    _AMOUNT_WEIGHT = 0.068
    #: The description gives up its room first, but never all of it.
    _MIN_DESCRIPTION = 0.14

    def _line_widths(self, width: float, header: list[str]) -> list[float]:
        """Return each column's width, the description absorbing the slack."""
        weights: list[float] = []
        for column in header:
            if column == "Description":
                weights.append(0.0)
            elif column in self._COLUMN_WEIGHTS:
                weights.append(self._COLUMN_WEIGHTS[column])
            elif column.endswith("%"):
                weights.append(self._RATE_WEIGHT)
            else:
                weights.append(self._AMOUNT_WEIGHT)

        described = 1.0 - sum(weights)
        if described < self._MIN_DESCRIPTION:
            # More columns than the page can hold at full width: scale the
            # others down together rather than let one of them wrap.
            scale = (1.0 - self._MIN_DESCRIPTION) / max(sum(weights), 0.001)
            weights = [weight * scale for weight in weights]
            described = self._MIN_DESCRIPTION
        return [
            width * (described if column == "Description" else weight)
            for column, weight in zip(header, weights, strict=True)
        ]

    def _totals(self, document: InvoiceDocument, width: float) -> Table:
        """Draw the amount in words beside the figures it spells."""
        rows: list[list[str]] = []
        if document.bill_discount:
            # Three rows rather than one, so the arithmetic is followable: what
            # the lines came to, what was taken off, what is being taxed.
            rows.append(["Lines", _money(document.gross_before_bill_discount)])
            rows.append(["Discount on bill", f"-{_money(document.bill_discount)}"])
        rows.append(["Taxable value", _money(document.taxable_total)])
        totals_by_code: dict[str, Decimal] = {}
        for line in document.lines:
            for code, _, amount in line.taxes:
                totals_by_code[code] = totals_by_code.get(code, ZERO) + amount
        for code, amount in totals_by_code.items():
            rows.append([code, _money(amount)])
        if not totals_by_code and document.tax_total:
            rows.append(["Tax", _money(document.tax_total)])
        if document.charges:
            rows.append(["Other charges", _money(document.charges)])
        if document.round_off:
            rows.append(["Round off", _money(document.round_off)])
        rows.append([f"Total {document.currency_symbol}", _money(document.grand_total)])

        figures = Table(rows, colWidths=[width * 0.22, width * 0.16])
        figures.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.9, colors.black),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ]
            )
        )
        words = [
            Paragraph(document.words_label, self._label),
            Paragraph(
                amount_in_words(document.grand_total),
                ParagraphStyle("words", parent=self._body, fontName="Helvetica-Bold"),
            ),
        ]
        table = Table([[words, figures]], colWidths=[width * 0.62, width * 0.38])
        table.setStyle(self._boxed())
        return table

    def _tax_summary(self, document: InvoiceDocument, width: float) -> Table | Spacer:
        """Draw the HSN-wise summary a tax invoice has to carry."""
        if not document.show_tax_summary:
            return Spacer(1, 0)
        grouped: dict[str, dict[str, Decimal]] = {}
        codes: list[str] = []
        for line in document.lines:
            bucket = grouped.setdefault(line.hsn or "-", {"taxable": ZERO})
            bucket["taxable"] += line.taxable
            for code, _, amount in line.taxes:
                bucket[code] = bucket.get(code, ZERO) + amount
                if code not in codes:
                    codes.append(code)
        if not grouped:
            return Spacer(1, 0)

        header = ["HSN / SAC", "Taxable value", *codes, "Total tax"]
        rows: list[list[object]] = [
            [Paragraph(f"<b>{column}</b>", self._small) for column in header]
        ]
        for hsn, bucket in grouped.items():
            tax = sum(bucket.get(code, ZERO) for code in codes)
            rows.append(
                [
                    hsn,
                    _money(bucket["taxable"]),
                    *[_money(bucket.get(code, ZERO)) for code in codes],
                    _money(Decimal(tax)),
                ]
            )
        table = Table(rows, colWidths=[width / len(header)] * len(header))
        style = self._boxed()
        style.add("BACKGROUND", (0, 0), (-1, 0), self._tint)
        style.add("TEXTCOLOR", (0, 0), (-1, 0), self._accent)
        style.add("INNERGRID", (0, 0), (-1, -1), 0.4, self._rule)
        style.add("ALIGN", (1, 1), (-1, -1), "RIGHT")
        style.add("FONTSIZE", (0, 1), (-1, -1), 7.6)
        table.setStyle(style)
        return table

    def _footer(self, document: InvoiceDocument, width: float) -> list[object]:
        """Bank details and terms on the left, the signature on the right."""
        left: list[object] = []
        if self._template.show_bank_details and self._template.bank_details:
            left.append(Paragraph("BANK DETAILS", self._label))
            for line in self._template.bank_details.splitlines():
                left.append(Paragraph(line, self._body))
            left.append(Spacer(1, 3))
        if self._template.terms:
            left.append(Paragraph("TERMS", self._label))
            for line in self._template.terms.splitlines():
                left.append(Paragraph(line, self._small))
        if self._template.jurisdiction:
            left.append(Spacer(1, 2))
            left.append(
                Paragraph(
                    f"Subject to {self._template.jurisdiction} jurisdiction.",
                    self._small,
                )
            )

        right: list[object] = []
        if self._template.declaration:
            right.append(Paragraph("DECLARATION", self._label))
            right.append(Paragraph(self._template.declaration, self._small))
            right.append(Spacer(1, 10))
        right.append(
            Paragraph(
                self._template.signatory_text or f"For {document.seller.name}",
                ParagraphStyle("for", parent=self._right, fontName="Helvetica-Bold"),
            )
        )
        right.append(Spacer(1, 22))
        right.append(Paragraph("Authorised signatory", self._right))

        table = Table(
            [[left or Spacer(1, 0), right]], colWidths=[width * 0.58, width * 0.42]
        )
        table.setStyle(self._boxed())
        flowables: list[object] = [table]
        if self._template.footer_note:
            flowables.append(Spacer(1, 3))
            flowables.append(
                Paragraph(
                    self._template.footer_note,
                    ParagraphStyle("footer", parent=self._small, alignment=TA_CENTER),
                )
            )
        return flowables

    def _boxed(self) -> TableStyle:
        """Return the ruled box every block on a tax invoice sits inside."""
        return TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, self._rule),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
