"""Boxes and pieces on the printed page (L5 step 8, box-and-piece design s4).

A line of a document saved in the boxes and pieces layout prints its
quantity the way the customer's own bill does: full boxes before the slash,
loose pieces after it, and what a box holds in brackets -- the worked
example's 41 pieces of a box of 12 read "3/5 (x12)", its 2 free "0/2". One
formatter does it for every paper; the layouts do no arithmetic. An item
with no pack, and any document not in the layout, print as before.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    TemplateSettings,
    in_packs,
    packed_cell,
)
from app.sales_order.services.order_print_service import SalesOrderPrintService
from app.uom.services.packs import printed_pack
from tests.unit.test_box_and_piece_note_and_bill import _ordered
from tests.unit.test_invoice_print import _HALF, _document, _is, _page_sizes
from tests.unit.test_invoice_print import _text_of as _raw_text_of
from tests.unit.test_selling_unit_default import _sold_by_the_box

D = Decimal


def _text_of(pdf: bytes) -> str:
    """Return the words a PDF prints, with its escaped brackets read back."""
    return _raw_text_of(pdf).replace("\\(", "(").replace("\\)", ")")


def _says(printed: str, pair: str, label: str) -> bool:
    """Say whether the pair prints with its pack, on one row or on two."""
    return f"{pair} {label}" in printed or f"{pair} | {label}" in printed


def _worked_example_line() -> InvoiceLineBlock:
    """Return the worked example's sale: 41 at 10.00 a piece, 2 free, 12 a box."""
    return InvoiceLineBlock(
        number=1,
        description="Soap 75 g",
        hsn="340111",
        quantity=D("41"),
        free_quantity=D("2"),
        uom="PCS",
        rate=D("10.00"),
        discount=D("0"),
        taxable=D("410.00"),
        total=D("459.20"),
        taxes=(("CGST", D("6"), D("24.60")), ("SGST", D("6"), D("24.60"))),
        pack_size=D("12"),
    )


def _bill(*lines: InvoiceLineBlock) -> InvoiceDocument:
    """Return a bill of ``lines`` that adds its quantities up, as a bill does."""
    return replace(
        _document(),
        lines=lines or (_worked_example_line(),),
        taxable_total=D("410.00"),
        tax_total=D("49.20"),
        grand_total=D("459.20"),
        show_total_quantity=True,
    )


# ---------------------------------------------------------------------------
# The one formatter


def test_a_total_is_written_as_full_boxes_and_the_pieces_over() -> None:
    """41 of 12 is 3/5; a whole number of boxes is 3/0; a bag keeps decimals."""
    assert in_packs(D("41"), D("12")) == "3/5"
    assert in_packs(D("36"), D("12")) == "3/0"
    assert in_packs(D("2"), D("12")) == "0/2"
    assert in_packs(D("53.5"), D("25")) == "2/3.5"

    line = _worked_example_line()
    assert (line.packed_quantity, line.packed_free, line.pack_label) == (
        "3/5",
        "0/2",
        "(x12)",
    )
    plain = replace(line, pack_size=None)
    assert (plain.packed_quantity, plain.packed_free, plain.pack_label) == (
        None,
        None,
        None,
    )


def test_a_pair_too_wide_for_its_cell_takes_a_second_row_for_the_pack() -> None:
    """The Qty column is narrow on every paper; nothing prints over the next."""
    assert packed_cell("3/5", "(x12)", 200, size=7) == "3/5 (x12)"
    assert packed_cell("120/11", "(x144)", 20, size=7) == "120/11\n(x144)"


def test_the_total_adds_the_boxes_and_puts_unpacked_items_with_the_pieces() -> None:
    """3/5 of a packed item and 4 of one with no pack add up to 3/9."""
    loose = replace(
        _worked_example_line(),
        number=2,
        description="Torch",
        quantity=D("4"),
        free_quantity=D("0"),
        pack_size=None,
    )
    document = _bill(_worked_example_line(), loose)
    assert document.total_in_packs == "3/9"
    assert document.total_free_in_packs == "0/2"

    # A document with no packed line adds up as it always did.
    plain = _bill(replace(_worked_example_line(), pack_size=None))
    assert (plain.total_in_packs, plain.total_free_in_packs) == (None, None)


# ---------------------------------------------------------------------------
# Every paper


def test_the_full_page_prints_the_worked_example_as_the_customers_bill() -> None:
    """Qty 3/5 (x12), Free 0/2, Rate 10.00, Amount 410.00."""
    printed = _text_of(InvoicePdfRenderer(TemplateSettings()).render(_bill()))
    assert _says(printed, "3/5", "(x12)"), printed
    assert "Free 0/2" in printed
    assert "10.00" in printed and "410.00" in printed
    after = printed[printed.index("Total quantity") :]
    assert "0/2 free" in after and "3/5" in after


def test_the_half_page_prints_the_pair_in_the_columns_it_has() -> None:
    """Qty "3/5 (x12)", Free "0/2", and the bill still fits half a page."""
    pdf = InvoicePdfRenderer(TemplateSettings(page_size="HALF")).render(
        _bill(*(replace(_worked_example_line(), number=n) for n in range(1, 7)))
    )
    sizes = _page_sizes(pdf)
    assert len(sizes) == 1 and _is(sizes[0], _HALF), sizes
    printed = _text_of(pdf)
    assert _says(printed, "3/5", "(x12)"), printed
    assert " | 0/2 | " in printed
    # Six lines of 3/5 and 0/2: 18 boxes and 30 pieces, 2 boxes and 12 free.
    after = printed[printed.index("Total quantity") :]
    assert "18/30" in after and "0/12" in after


def test_the_trade_layout_prints_the_pair_in_its_qty_and_free_columns() -> None:
    """The trade's full page: QTY "3/5 (x12)" and Free "0/2"."""
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(bill_layout="TRADE")).render(_bill())
    )
    assert _says(printed, "3/5", "(x12)"), printed
    assert " | 0/2 | " in printed


def test_the_roll_prints_the_pair_on_the_items_second_row() -> None:
    """80 mm: "3/5 (x12) Free 0/2 x 10.00"."""
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(page_size="THERMAL80")).render(_bill())
    )
    assert "3/5 (x12) Free 0/2 x 10.00" in printed, printed


def test_a_mixed_document_prints_an_item_with_no_pack_as_before() -> None:
    """The torch has no pack: it prints 4, beside the soap's 3/5 (x12)."""
    loose = replace(
        _worked_example_line(),
        number=2,
        description="Torch",
        quantity=D("4"),
        free_quantity=D("0"),
        pack_size=None,
    )
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings()).render(
            _bill(_worked_example_line(), loose)
        )
    )
    assert _says(printed, "3/5", "(x12)")
    assert "340111 | 4 | PCS" in printed
    assert "3/9" in printed[printed.index("Total quantity") :]


def test_a_line_with_no_pack_prints_its_plain_quantity_on_every_paper() -> None:
    """Off the layout nothing changes: 41, and 2 free, as today."""
    plain = _bill(replace(_worked_example_line(), pack_size=None))
    for template in (
        TemplateSettings(),
        TemplateSettings(page_size="HALF"),
        TemplateSettings(bill_layout="TRADE"),
        TemplateSettings(page_size="THERMAL80"),
    ):
        printed = _text_of(InvoicePdfRenderer(template).render(plain))
        assert "3/5" not in printed and "(x12)" not in printed
        assert "41" in printed


# ---------------------------------------------------------------------------
# Which lines print so


def test_only_a_line_in_the_stock_unit_of_a_document_in_the_layout_packs() -> None:
    """Off the layout, no pack, or a line counted in BOX: the plain figure."""
    shop = _sold_by_the_box()
    product = shop.setup.product
    assert printed_pack(
        in_boxes=True, pack_size=D("12"), unit_id=shop.piece, product=product
    ) == D("12")
    # A line naming no unit is in the stock unit.
    assert printed_pack(
        in_boxes=True, pack_size=D("12"), unit_id=None, product=product
    ) == D("12")
    assert (
        printed_pack(
            in_boxes=False, pack_size=D("12"), unit_id=shop.piece, product=product
        )
        is None
    )
    assert (
        printed_pack(in_boxes=True, pack_size=None, unit_id=shop.piece, product=product)
        is None
    )
    # "2 BOX" keeps its pack (decision 4) but is not a count of pieces.
    assert (
        printed_pack(
            in_boxes=True, pack_size=D("12"), unit_id=shop.box, product=product
        )
        is None
    )


def test_an_order_in_the_layout_prints_its_line_in_boxes_and_pieces() -> None:
    """The order confirmation of the worked example reads 3/5 (x12)."""
    shop = _sold_by_the_box()
    order = _ordered(shop)
    pdf, _ = SalesOrderPrintService(shop.session).render(
        order.id, firm_scope=shop.firm_id
    )
    printed = _text_of(pdf)
    assert _says(printed, "3/5", "(x12)"), printed
    assert "Free 0/2" in printed


def test_an_order_not_in_the_layout_prints_as_before() -> None:
    """The same order saved without the layout prints 41 and 2 free."""
    shop = _sold_by_the_box()
    order = _ordered(shop, boxes=False)
    pdf, _ = SalesOrderPrintService(shop.session).render(
        order.id, firm_scope=shop.firm_id
    )
    printed = _text_of(pdf)
    assert "3/5" not in printed and "(x12)" not in printed
    assert "+2 free" in printed
