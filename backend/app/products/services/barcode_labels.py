"""Price and barcode labels for products and received batches (STK-16).

A shop sticks a label on each piece it puts on the shelf: the product's name,
a Code 128 barcode the counter scanner reads, the MRP and the firm's own price,
and for a batch-tracked product the batch and its expiry. Marg and Busy print
the same thing on two kinds of stock (decision A65):

* **A4 label sheets** -- the 65-up (38.1 x 21.2 mm) and 24-up (64 x 33.9 mm)
  sheets any stationer sells, printed on an ordinary office printer. A sheet
  partly used last time is fed again with ``skip`` naming how many positions
  are already gone, so nothing is wasted.
* **A 50 x 25 mm thermal roll** -- one label per page, which is what a label
  printer's Windows driver expects.

The barcode carries the product's own ``barcode`` and falls back to its code,
so a product nobody has given a barcode still gets a label the scanner finds
-- search and the counter look both up. Nothing here writes: a label is a view
of the product, or of what a goods receipt brought in.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from io import BytesIO
from uuid import UUID

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.goods_receipt.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.products.models.product import Product

#: The most labels one request draws -- about 77 sheets of 65. A receipt of
#: 10,000 strips is printed in parts rather than as one 150-page PDF.
MAX_LABELS = 5000


class LabelLayout(StrEnum):
    """The label stock a PDF is drawn for."""

    A4_65 = "A4_65"
    A4_24 = "A4_24"
    ROLL_50X25 = "ROLL_50X25"


@dataclass(frozen=True)
class _Stock:
    """Where the labels sit on one page of a given stock, in points."""

    page_width: float
    page_height: float
    label_width: float
    label_height: float
    columns: int
    rows: int
    left: float
    top: float
    pitch_x: float
    pitch_y: float

    @property
    def per_page(self) -> int:
        """Return how many labels one page holds."""
        return self.columns * self.rows


_A4_WIDTH = 210 * mm
_A4_HEIGHT = 297 * mm

_STOCKS: dict[LabelLayout, _Stock] = {
    LabelLayout.A4_65: _Stock(
        page_width=_A4_WIDTH,
        page_height=_A4_HEIGHT,
        label_width=38.1 * mm,
        label_height=21.2 * mm,
        columns=5,
        rows=13,
        left=4.65 * mm,
        top=10.7 * mm,
        pitch_x=40.6 * mm,
        pitch_y=21.2 * mm,
    ),
    LabelLayout.A4_24: _Stock(
        page_width=_A4_WIDTH,
        page_height=_A4_HEIGHT,
        label_width=64 * mm,
        label_height=33.9 * mm,
        columns=3,
        rows=8,
        left=6.5 * mm,
        top=12.9 * mm,
        pitch_x=66 * mm,
        pitch_y=33.9 * mm,
    ),
    LabelLayout.ROLL_50X25: _Stock(
        page_width=50 * mm,
        page_height=25 * mm,
        label_width=50 * mm,
        label_height=25 * mm,
        columns=1,
        rows=1,
        left=0,
        top=0,
        pitch_x=50 * mm,
        pitch_y=25 * mm,
    ),
}


@dataclass(frozen=True)
class LabelContent:
    """What one label says, and how many copies of it are wanted."""

    name: str
    barcode: str
    mrp: Decimal | None
    price: Decimal | None
    batch_number: str | None = None
    expiry_date: date | None = None
    copies: int = 1


@dataclass(frozen=True)
class LabelRequestItem:
    """One product and how many of its labels to print."""

    product_id: UUID
    copies: int


def barcode_value(product: Product) -> str:
    """Return what a product's barcode carries: its barcode, else its code.

    Code 128 encodes printable ASCII only, so a value outside it is refused
    with the product named rather than drawn as a barcode nothing can read.
    """
    value = (product.barcode or product.code or "").strip()
    if not value or not all(32 <= ord(char) < 127 for char in value):
        raise ValidationError(
            f"{product.name} has no barcode or code a label can print "
            "(letters, digits and plain punctuation only)."
        )
    return value


def _money(value: Decimal) -> str:
    """Return a price as a label prints it -- no paise when there are none."""
    rounded = value.quantize(Decimal("0.01"))
    if rounded == rounded.to_integral_value():
        return f"{int(rounded):,}"
    return f"{rounded:,.2f}"


def _fit(text: str, font: str, size: float, width: float) -> str:
    """Return ``text`` cut with an ellipsis so it fits ``width`` points."""
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "...", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "..."


class BarcodeLabelRenderer:
    """Draw labels onto a stock's pages and return the PDF."""

    def __init__(self, layout: LabelLayout) -> None:
        """Remember the stock the labels are drawn for."""
        self._layout = layout
        self._stock = _STOCKS[layout]

    def render(self, labels: Sequence[LabelContent], *, skip: int = 0) -> bytes:
        """Return the PDF of every copy of every label, after ``skip`` blanks.

        ``skip`` only means something on a sheet: it is how many positions of
        the first page were used last time, counted across then down.
        """
        stock = self._stock
        total = sum(label.copies for label in labels)
        if total < 1:
            raise ValidationError("There is nothing to print a label for.")
        if total > MAX_LABELS:
            raise ValidationError(
                f"{total} labels were asked for; print at most {MAX_LABELS} "
                "at a time."
            )
        if skip < 0 or (stock.per_page > 1 and skip >= stock.per_page):
            raise ValidationError(
                f"Skip between 0 and {stock.per_page - 1} labels on this sheet."
            )
        offset = skip if stock.per_page > 1 else 0
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(stock.page_width, stock.page_height))
        canvas.setTitle("Labels")
        position = offset
        for label in labels:
            for _ in range(label.copies):
                if position == stock.per_page:
                    canvas.showPage()
                    position = 0
                column = position % stock.columns
                row = position // stock.columns
                x = stock.left + column * stock.pitch_x
                y = stock.page_height - stock.top - (row + 1) * stock.pitch_y
                self._draw(canvas, label, x, y)
                position += 1
        canvas.showPage()
        canvas.save()
        return buffer.getvalue()

    def _draw(self, canvas: Canvas, label: LabelContent, x: float, y: float) -> None:
        """Draw one label with its bottom-left corner at ``(x, y)``."""
        stock = self._stock
        pad = 1.5 * mm
        width = stock.label_width - 2 * pad
        small = stock.label_height < 30 * mm
        name_size = 6.5 if small else 8.5
        text_size = 5.5 if small else 7.0
        top = y + stock.label_height - pad

        canvas.setFont("Helvetica-Bold", name_size)
        canvas.drawString(
            x + pad,
            top - name_size,
            _fit(label.name, "Helvetica-Bold", name_size, width),
        )

        lines: list[str] = []
        prices = []
        if label.mrp is not None:
            prices.append(f"MRP Rs.{_money(label.mrp)}")
        if label.price is not None and label.price != label.mrp:
            prices.append(f"Our price Rs.{_money(label.price)}")
        if prices:
            lines.append("  ".join(prices))
        tracked = []
        if label.batch_number:
            tracked.append(f"B: {label.batch_number}")
        if label.expiry_date is not None:
            tracked.append(f"Exp: {label.expiry_date:%m/%Y}")
        if tracked:
            lines.append("  ".join(tracked))

        bottom = y + pad
        canvas.setFont("Helvetica", text_size)
        for index, line in enumerate(reversed(lines)):
            canvas.drawString(
                x + pad,
                bottom + index * (text_size + 1),
                _fit(line, "Helvetica", text_size, width),
            )
        text_top = bottom + len(lines) * (text_size + 1)

        bar_bottom = text_top + 0.5 * mm
        bar_top = top - name_size - 1 * mm
        human = 5.0
        bar_height = max(bar_top - bar_bottom - human - 1, 4 * mm)
        symbol = Code128(
            label.barcode,
            barHeight=bar_height,
            barWidth=0.33 * mm,
            humanReadable=False,
            quiet=False,
        )
        if symbol.width > width:
            symbol = Code128(
                label.barcode,
                barHeight=bar_height,
                barWidth=0.33 * mm * width / symbol.width,
                humanReadable=False,
                quiet=False,
            )
        bar_x = x + pad + (width - symbol.width) / 2
        symbol.drawOn(canvas, bar_x, bar_bottom + human + 1)
        canvas.setFont("Helvetica", human)
        canvas.drawCentredString(
            x + stock.label_width / 2,
            bar_bottom,
            _fit(label.barcode, "Helvetica", human, width),
        )


class BarcodeLabelService:
    """Collect what each label says from the firm's own records."""

    def __init__(self, session: Session) -> None:
        """Keep the firm store's session."""
        self._session = session

    def product_labels(
        self,
        items: Sequence[LabelRequestItem],
        *,
        firm_id: UUID,
        layout: LabelLayout,
        skip: int = 0,
        show_price: bool = True,
    ) -> bytes:
        """Return labels for products picked from the list, in the order given.

        The price is the product's selling price; ``show_price`` leaves it off
        for a shop that prints only the MRP.
        """
        ids = {item.product_id for item in items}
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(
                    Product.firm_id == firm_id,
                    Product.id.in_(ids),
                    Product.is_deleted.is_(False),
                )
            )
        }
        missing = ids - products.keys()
        if missing:
            raise ResourceNotFoundError("Product not found.")
        labels = [
            LabelContent(
                name=products[item.product_id].name,
                barcode=barcode_value(products[item.product_id]),
                mrp=products[item.product_id].mrp,
                price=products[item.product_id].selling_price if show_price else None,
                copies=item.copies,
            )
            for item in items
        ]
        return BarcodeLabelRenderer(layout).render(labels, skip=skip)

    def receipt_labels(
        self,
        receipt_id: UUID,
        *,
        firm_id: UUID,
        layout: LabelLayout,
        skip: int = 0,
        show_price: bool = True,
    ) -> tuple[bytes, str]:
        """Return the PDF of :meth:`receipt_label_contents` and its file name."""
        labels, number = self.receipt_label_contents(
            receipt_id, firm_id=firm_id, show_price=show_price
        )
        pdf = BarcodeLabelRenderer(layout).render(labels, skip=skip)
        return pdf, f"labels-{number}.pdf"

    def receipt_label_contents(
        self, receipt_id: UUID, *, firm_id: UUID, show_price: bool = True
    ) -> tuple[list[LabelContent], str]:
        """Return a label for every piece a goods receipt put into stock.

        One label per stock unit accepted plus the free goods, rounded up, so
        a shop labels exactly what came off the van. The batch's own MRP and
        price -- what this delivery is marked at -- beat the product's, and
        the batch and expiry print where the line has them. A cancelled
        receipt stocked nothing, so it has nothing to label.
        """
        receipt = self._session.scalar(
            select(GoodsReceipt).where(
                GoodsReceipt.id == receipt_id,
                GoodsReceipt.firm_id == firm_id,
                GoodsReceipt.is_deleted.is_(False),
            )
        )
        if receipt is None:
            raise ResourceNotFoundError("Goods receipt not found.")
        if receipt.status == "CANCELLED":
            raise ValidationError("A cancelled receipt has nothing to label.")
        lines = list(
            self._session.scalars(
                select(GoodsReceiptLine)
                .where(
                    GoodsReceiptLine.goods_receipt_id == receipt.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
                .order_by(GoodsReceiptLine.line_number)
            )
        )
        products = {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(
                    Product.id.in_({line.product_id for line in lines})
                )
            )
        }
        labels: list[LabelContent] = []
        for line in lines:
            pieces = (line.accepted_quantity + line.free_quantity) * (
                line.conversion_factor or Decimal("1")
            )
            copies = math.ceil(pieces)
            if copies < 1:
                continue
            product = products[line.product_id]
            price = line.selling_price or product.selling_price
            labels.append(
                LabelContent(
                    name=product.name,
                    barcode=barcode_value(product),
                    mrp=line.mrp or product.mrp,
                    price=price if show_price else None,
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    copies=copies,
                )
            )
        if not labels:
            raise ValidationError("Nothing on this receipt was accepted into stock.")
        return labels, receipt.grn_number
