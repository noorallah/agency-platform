"""The bill a customer is sent, and what a firm may change about it.

Printing was the last thing the platform could not do for a sale: a Print
control existed on two purchase screens and showed a toast saying print was
"reserved for the next transactional phase", while the document framework
carried `allows_print`, `printed_by` and `allows_export_pdf` columns that
nothing read.

These cover the two halves of it. The renderer states what a tax invoice must
state, from the record rather than recomputed. The template decides only what
sits around that -- a firm that could switch off the tax summary could
configure itself out of compliance.
"""

# ruff: noqa: D103

import re
import zlib
from base64 import a85decode
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.document_framework.models import DocumentPrintTemplate
from app.finance.models.bank_details import BankAccountDetails
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
    amount_in_words,
    render_together,
)
from app.sales_invoice.services.invoice_print_service import (
    NOT_FINAL,
    SalesInvoicePrintService,
)


def _text_of(pdf: bytes) -> str:
    """Return the words a PDF prints, in order.

    reportlab writes ASCII85 over deflate, so the streams are decoded rather
    than searched for -- looking for a string in the raw bytes would pass on a
    document that never draws it.
    """
    runs: list[str] = []
    for match in re.finditer(rb"stream", pdf):
        start = match.end()
        body = pdf[start : pdf.find(b"endstream", start)].strip(b"\r\n")
        for decode in (
            lambda raw: zlib.decompress(a85decode(raw, adobe=True)),
            zlib.decompress,
            lambda raw: raw,
        ):
            try:
                content = decode(body)
                break
            except Exception:  # noqa: BLE001 - any codec may reject a stream
                continue
        else:
            continue
        runs += [
            item.decode("latin-1") for item in re.findall(rb"\((.*?)\)\s*Tj", content)
        ]
    return " | ".join(runs)


def _document() -> InvoiceDocument:
    """One invoice, with the tax the customer was actually charged."""
    return InvoiceDocument(
        number="SI-2026-2027-000012",
        date="22 Aug 2026",
        due_date="12 Sep 2026",
        place_of_supply="Maharashtra",
        reverse_charge=False,
        seller=PartyBlock(
            name="ElectroLink Appliances Distribution Private Limited",
            address_lines=["Main Road", "Pune, Maharashtra, 411001"],
            gstin="27ELEC01A1Z5",
            state="Maharashtra",
        ),
        buyer=PartyBlock(
            name="QuickTech Retail",
            address_lines=["23 Market Road", "Pune, Maharashtra, 411001"],
            gstin="29ELEC01C0304Z5",
            pan="ABCDE0903F",
            state="Maharashtra",
        ),
        ship_to=None,
        lines=(
            InvoiceLineBlock(
                number=1,
                description="Extension Board 5 Meter",
                hsn="854442",
                quantity=Decimal("4"),
                uom="NOS",
                rate=Decimal("250.00"),
                discount=Decimal("0"),
                taxable=Decimal("1000.00"),
                total=Decimal("1180.00"),
                taxes=(
                    ("CGST", Decimal("9"), Decimal("90.00")),
                    ("SGST", Decimal("9"), Decimal("90.00")),
                ),
            ),
        ),
        taxable_total=Decimal("1000.00"),
        tax_total=Decimal("180.00"),
        charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("1180.00"),
    )


def test_the_bill_states_everything_a_tax_invoice_must() -> None:
    """The statutory spine, none of which a firm may switch off."""
    printed = _text_of(InvoicePdfRenderer().render(_document()))

    for required in (
        "TAX INVOICE",
        "ElectroLink Appliances Distribution Private Limited",
        "27ELEC01A1Z5",
        "QuickTech Retail",
        "29ELEC01C0304Z5",
        "SI-2026-2027-000012",
        "22 Aug 2026",
        "Maharashtra",
        "854442",
        "1,000.00",
        "1,180.00",
        "One Thousand One Hundred Eighty Rupees Only",
        "HSN / SAC",
    ):
        assert required in printed, f"the bill does not state {required!r}"


def test_the_bill_states_each_tax_component_and_its_rate() -> None:
    """The reason `sales_invoice_line_taxes` exists.

    "180.00 of tax" is not a tax invoice. The buyer claims input credit against
    the components, so each has to appear with the rate it was charged at.
    """
    printed = _text_of(InvoicePdfRenderer().render(_document()))

    assert "CGST" in printed
    assert "SGST" in printed
    assert (
        printed.count("90.00") >= 4
    ), "each component appears on its line and again in both summaries"
    assert "9.00" in printed, "the rate is stated, not only the amount"


def test_a_firm_changes_the_matter_around_the_spine() -> None:
    """Letterhead, bank block, terms and jurisdiction are the firm's."""
    template = TemplateSettings(
        title_text="BILL OF SUPPLY",
        bank_details="State Bank of India\nA/c 3021 5566 7788",
        terms="Payment due within 21 days.",
        jurisdiction="Pune",
        signatory_text="For ElectroLink Pvt Ltd",
        footer_note="This is a computer generated invoice.",
    )
    printed = _text_of(InvoicePdfRenderer(template).render(_document()))

    assert "BILL OF SUPPLY" in printed
    assert "State Bank of India" in printed
    assert "Payment due within 21 days." in printed
    assert "Subject to Pune jurisdiction." in printed
    assert "For ElectroLink Pvt Ltd" in printed
    assert "This is a computer generated invoice." in printed
    # ...and the spine is still there.
    assert "854442" in printed
    assert "CGST" in printed


def test_a_firm_that_has_configured_nothing_still_gets_a_correct_bill() -> None:
    """The platform default is a complete tax invoice, not a blank one."""
    printed = _text_of(InvoicePdfRenderer().render(_document()))

    assert "TAX INVOICE" in printed
    assert "Certified that the particulars given above are true" in printed
    assert "Authorised signatory" in printed


def test_a_firm_that_has_saved_no_print_settings_gets_the_statutory_copies() -> None:
    """Three labelled copies by default, not one unlabelled page.

    `copy_labels` was empty until the firm saved Print settings, so a first
    print carried one copy with no banner (BL-31.14). The challan already
    defaulted its three; the invoice defaults the set rule 48 names for
    goods. A saved template still says what it says, even one copy.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    DocumentPrintTemplate.__table__.create(engine)
    # The template reads the firm's printed bank account too (ACC-4).
    BankAccountDetails.__table__.create(engine)
    session = Session(engine)
    firm_id = uuid4()

    assert SalesInvoicePrintService(session)._template(firm_id).copy_labels == (
        "ORIGINAL FOR RECIPIENT",
        "DUPLICATE FOR TRANSPORTER",
        "TRIPLICATE FOR SUPPLIER",
    )

    session.add(
        DocumentPrintTemplate(
            firm_id=firm_id,
            document_type="SALES_INVOICE",
            copy_labels=["ORIGINAL FOR RECIPIENT"],
            created_by=firm_id,
            updated_by=firm_id,
        )
    )
    session.commit()
    assert SalesInvoicePrintService(session)._template(firm_id).copy_labels == (
        "ORIGINAL FOR RECIPIENT",
    )


def test_a_draft_bill_says_on_every_copy_that_it_is_not_a_tax_invoice() -> None:
    """A draft printed for checking must not pass for the bill.

    The phase 2 invoice screen prints on save, and a draft has been neither
    approved nor posted: a copy that read "TAX INVOICE" and nothing else
    could be handed to a customer, who would then hold a bill the books do
    not. Approved bills carry no such line; a cancelled one does.
    """
    template = TemplateSettings(copy_labels=("ORIGINAL", "DUPLICATE"))
    printed = _text_of(
        InvoicePdfRenderer(template).render(
            replace(_document(), not_final=NOT_FINAL["DRAFT"])
        )
    )
    assert printed.count("DRAFT - NOT A TAX INVOICE") == 2
    assert "NOT A TAX INVOICE" not in _text_of(
        InvoicePdfRenderer(template).render(_document())
    )
    assert "APPROVED" not in NOT_FINAL
    assert "CANCELLED" in NOT_FINAL


def test_each_copy_is_labelled_and_printed_once() -> None:
    """A firm printing three copies gets three, each saying which it is."""
    template = TemplateSettings(
        copy_labels=("ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER")
    )
    printed = _text_of(InvoicePdfRenderer(template).render(_document()))

    assert "ORIGINAL FOR RECIPIENT" in printed
    assert "DUPLICATE FOR TRANSPORTER" in printed
    assert printed.count("SI-2026-2027-000012") == 2


def test_the_optional_columns_are_the_firms_choice() -> None:
    """Discount, batch and expiry appear only where a firm asks for them."""
    without = _text_of(
        InvoicePdfRenderer(TemplateSettings(show_discount_column=False)).render(
            _document()
        )
    )
    assert "Disc." not in without

    with_batch = _text_of(
        InvoicePdfRenderer(
            TemplateSettings(show_batch_column=True, show_expiry_column=True)
        ).render(_document())
    )
    assert "Batch" in with_batch
    assert "Expiry" in with_batch


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        (Decimal("1180.00"), "One Thousand One Hundred Eighty Rupees Only"),
        (Decimal("0"), "Zero Rupees Only"),
        (Decimal("100"), "One Hundred Rupees Only"),
        (Decimal("125000"), "One Lakh Twenty Five Thousand Rupees Only"),
        (Decimal("10000000"), "One Crore Rupees Only"),
        (Decimal("99.50"), "Ninety Nine Rupees and Fifty Paise Only"),
        (
            Decimal("1500.75"),
            "One Thousand Five Hundred Rupees and Seventy Five Paise Only",
        ),
    ],
)
def test_the_amount_in_words_is_read_in_lakh_and_crore(
    amount: Decimal, words: str
) -> None:
    """Statutory on an Indian invoice, and grouped the Indian way.

    1,25,000 is *One Lakh Twenty Five Thousand*, not *One Hundred Twenty Five
    Thousand* -- a Western grouping on an Indian bill is wrong twice over: the
    words disagree with the figures beside them, and the figures themselves are
    printed with Indian separators.
    """
    assert amount_in_words(amount) == words


def test_a_template_colour_that_is_not_a_colour_still_prints() -> None:
    """A firm cannot break its own billing by saving nonsense."""
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(accent_color="not-a-colour")).render(
            _document()
        )
    )
    assert "TAX INVOICE" in printed


def test_an_order_does_not_call_itself_an_invoice() -> None:
    """The same renderer draws a purchase order, and it says so.

    The Print control on the purchase workspace showed a toast saying print was
    "reserved for the next transactional phase" from the day it was drawn. It
    prints now -- through this renderer, given an order's shape: placed with a
    supplier, delivered to a warehouse, and stating no place of supply and no
    HSN summary, because an order charges nobody.
    """
    order = _document()
    order = InvoiceDocument(
        **{
            **{
                field: getattr(order, field)
                for field in order.__dataclass_fields__
                if field
                not in {
                    "party_labels",
                    "show_tax_summary",
                    "show_supply_terms",
                    "number_label",
                    "date_label",
                    "words_label",
                }
            },
            "party_labels": ("SUPPLIER", "DELIVER TO"),
            "show_tax_summary": False,
            "show_supply_terms": False,
            "number_label": "Order no.",
            "date_label": "Order date",
            "words_label": "ORDER VALUE, IN WORDS",
        }
    )
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(title_text="PURCHASE ORDER")).render(order)
    )

    assert "PURCHASE ORDER" in printed
    assert "SUPPLIER" in printed
    assert "DELIVER TO" in printed
    assert "Order no." in printed
    assert "ORDER VALUE, IN WORDS" in printed
    assert "Invoice no." not in printed
    assert "BILLED TO" not in printed
    assert "Place of supply" not in printed
    assert "Reverse charge" not in printed
    assert "HSN / SAC" not in printed, "the statutory summary belongs to a bill"
    # The goods and the money are still stated.
    assert "854442" in printed
    assert "1,180.00" in printed


def _challan() -> InvoiceDocument:
    """One delivery challan: goods moving, on a named vehicle, charging nobody."""
    return InvoiceDocument(
        number="DN-ELEC01-ELC_HO-2026-2027-000006",
        date="22 Aug 2026",
        due_date=None,
        place_of_supply=None,
        reverse_charge=False,
        seller=PartyBlock(
            name="ElectroLink Appliances Distribution Private Limited",
            address_lines=["Main Road", "Pune, Maharashtra, 411001"],
            gstin="27ELEC01A1Z5",
            state="Maharashtra",
        ),
        buyer=PartyBlock(
            name="City Digital World",
            address_lines=["23 Market Road", "Pune, Maharashtra, 411001"],
            gstin="29ELEC01C0304Z5",
            state="Maharashtra",
        ),
        ship_to=None,
        lines=(
            InvoiceLineBlock(
                number=1,
                description="Extension Board 5 Meter",
                hsn="854442",
                quantity=Decimal("10"),
                free_quantity=Decimal("1"),
                uom="NOS",
                rate=Decimal("158.75"),
                discount=Decimal("0"),
                taxable=Decimal("1587.50"),
                total=Decimal("1873.25"),
            ),
        ),
        taxable_total=Decimal("1587.50"),
        tax_total=Decimal("285.75"),
        charges=Decimal("0"),
        round_off=Decimal("0"),
        grand_total=Decimal("1873.25"),
        references=(
            ("Against order", "SO-2026-2027-000006"),
            ("Vehicle", "MH12 AB 1234"),
            ("Driver", "R. Kulkarni"),
        ),
        party_labels=("CONSIGNEE", "SHIP TO"),
        show_tax_summary=False,
        show_supply_terms=False,
        number_label="Challan no.",
        date_label="Challan date",
        words_label="VALUE OF GOODS, IN WORDS",
    )


def test_a_challan_names_the_vehicle_and_the_driver() -> None:
    """The two things a driver is stopped and asked about.

    Until 2026-08-23 the platform could print a tax invoice and a purchase
    order and nothing else, so a firm could dispatch stock and had nothing to
    send with it.
    """
    printed = _text_of(
        InvoicePdfRenderer(
            TemplateSettings(title_text="DELIVERY CHALLAN", show_bank_details=False)
        ).render(_challan())
    )

    assert "DELIVERY CHALLAN" in printed
    assert "MH12 AB 1234" in printed
    assert "R. Kulkarni" in printed
    assert "SO-2026-2027-000006" in printed


def test_a_challan_states_the_free_goods_travelling() -> None:
    """The storekeeper at the other end counts eleven."""
    printed = _text_of(InvoicePdfRenderer(TemplateSettings()).render(_challan()))

    # Under the quantity, on a line of its own in the cell.
    assert "10 | +1 free" in printed


def test_a_challan_is_not_a_tax_invoice() -> None:
    """It carries the value of what is moving and asks for nothing.

    No HSN-wise summary and no supply terms: those belong to the bill that
    follows, and a challan that stated them would be claiming to be one.
    """
    printed = _text_of(
        InvoicePdfRenderer(
            TemplateSettings(title_text="DELIVERY CHALLAN", show_bank_details=False)
        ).render(_challan())
    )

    assert "Challan no." in printed
    assert "VALUE OF GOODS, IN WORDS" in printed
    assert "CONSIGNEE" in printed
    # The parts a tax invoice must state and a challan must not claim.
    assert "Reverse charge" not in printed
    assert "HSN / SAC" not in printed


def test_a_challan_still_carries_the_value_of_what_is_moving() -> None:
    """Which is what makes it usable behind an e-way bill."""
    printed = _text_of(InvoicePdfRenderer(TemplateSettings()).render(_challan()))

    assert "1,587.50" in printed
    assert "1,873.25" in printed


def test_a_quotation_says_how_long_the_prices_stand() -> None:
    """The one field a quotation has that no other document does.

    An offer without it is one the firm is still bound by next year -- and
    until 2026-08-23 an offer could not be sent as a document at all.
    """
    document = _challan()
    offer = replace(
        document,
        number="QT-2026-2027-000007",
        references=(("Prices stand until", "21 Sep 2026"),),
        party_labels=("OFFERED TO", "SHIP TO"),
        number_label="Quotation no.",
        date_label="Quotation date",
        words_label="QUOTED VALUE, IN WORDS",
    )
    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(title_text="QUOTATION")).render(offer)
    )

    assert "QUOTATION" in printed
    assert "Prices stand until" in printed
    assert "21 Sep 2026" in printed
    assert "OFFERED TO" in printed
    assert "QUOTED VALUE, IN WORDS" in printed


def test_a_credit_note_states_the_tax_it_gives_back() -> None:
    """The mirror of a bill, not a lesser document.

    The tax on a return is credited, so the components are stated the way an
    invoice states them; only the supply terms go, because nothing is being
    supplied.
    """
    note = replace(
        _document(),
        number="SR-2026-2027-000003",
        due_date=None,
        party_labels=("CREDITED TO", "RETURNED FROM"),
        show_supply_terms=False,
        number_label="Credit note no.",
        date_label="Credit note date",
        words_label="CREDIT, IN WORDS",
        references=(("Reason", "DAMAGED"),),
    )
    printed = _text_of(
        InvoicePdfRenderer(
            TemplateSettings(title_text="CREDIT NOTE", show_bank_details=False)
        ).render(note)
    )

    assert "CREDIT NOTE" in printed
    assert "Credit note no." in printed
    assert "CREDITED TO" in printed
    assert "CREDIT, IN WORDS" in printed
    assert "DAMAGED" in printed
    # The tax it gives back is stated. Component by component only where the
    # document carries a stored breakup -- a sales return has none, so the
    # real service asks for no summary; this document has one and proves the
    # renderer would print it the day the breakup is stored.
    assert "CGST" in printed
    assert "SGST" in printed
    # And what it must not: nothing is being supplied, so no supply terms.
    assert "Reverse charge" not in printed


def _page_sizes(pdf: bytes) -> list[tuple[float, float]]:
    """Return each page's width and height, in points, off its MediaBox."""
    return [
        (float(match[2]) - float(match[0]), float(match[3]) - float(match[1]))
        for match in re.findall(
            rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", pdf
        )
    ]


def test_a_counter_roll_is_80_mm_wide_and_as_long_as_the_bill() -> None:
    """A thermal printer feeds whatever height the page has.

    So the roll layout is one column 80 mm wide and exactly as tall as what
    is on it -- a fixed tall page would waste paper after every bill -- and
    it states the same facts the A4 bill does.
    """
    template = TemplateSettings(page_size="THERMAL80")
    pdf = InvoicePdfRenderer(template).render(_document())
    sizes = _page_sizes(pdf)
    assert len(sizes) == 1
    width, height = sizes[0]
    assert abs(width - 80 * 72 / 25.4) < 1
    assert height < 400, "a one-line bill needs well under an A4's height"

    printed = _text_of(pdf)
    for fact in (
        "SI-2026-2027-000012",
        "27ELEC01A1Z5",
        "QuickTech Retail",
        "Extension Board 5 Meter",
        "CGST 9%",
        "1,180.00",
    ):
        assert fact in printed, fact


def test_each_copy_on_a_roll_is_a_page_of_its_own() -> None:
    """Original and duplicate tear off separately, each saying which it is."""
    template = TemplateSettings(
        page_size="THERMAL80", copy_labels=("ORIGINAL", "DUPLICATE")
    )
    pdf = InvoicePdfRenderer(template).render(
        replace(_document(), not_final="DRAFT - NOT A TAX INVOICE")
    )
    assert len(_page_sizes(pdf)) == 2
    printed = _text_of(pdf)
    assert "ORIGINAL" in printed and "DUPLICATE" in printed
    assert printed.count("DRAFT - NOT A TAX INVOICE") == 2


def test_both_sides_licence_numbers_print_under_their_names() -> None:
    """A pharma bill carries the seller's and the buyer's drug licence (54)."""
    document = _document()
    printed = _text_of(
        InvoicePdfRenderer().render(
            replace(
                document,
                seller=replace(
                    document.seller,
                    licences=(("Drug licence, wholesale", "KA-B20-1234"),),
                ),
                buyer=replace(
                    document.buyer,
                    licences=(("Drug licence, retail", "KA-R20-9876"),),
                ),
            )
        )
    )
    assert "KA-B20-1234" in printed
    assert "KA-R20-9876" in printed
    assert "Drug licence, wholesale" in printed


_HALF = (595.28, 420.94)
_FULL = (595.28, 841.89)


def _is(size: tuple[float, float], paper: tuple[float, float]) -> bool:
    """Say whether a page is this paper, to the point."""
    return abs(size[0] - paper[0]) < 1 and abs(size[1] - paper[1]) < 1


def _trade_bill(lines: int = 1) -> InvoiceDocument:
    """Build a distributor's bill: MRP, free goods, a batch, a licence."""
    document = _document()
    line = replace(
        document.lines[0],
        free_quantity=Decimal("1"),
        discount=Decimal("25.00"),
        batch="B2407",
        expiry="Mar 2028",
        mrp=Decimal("320.00"),
    )
    return replace(
        document,
        seller=replace(
            document.seller,
            licences=(("DGL No.1", "AP/10/02/2019-4916"), ("FSSAI", "10114010000243")),
        ),
        lines=tuple(replace(line, number=index + 1) for index in range(lines)),
        round_off=Decimal("0.29"),
    )


def test_a_short_bill_prints_on_half_a_page_in_the_trades_columns() -> None:
    """Half an A4 sheet, one page, carrying what the trade's bill carries.

    The columns are the customer's sample's (backlog 118): MRP, quantity,
    free goods, rate, discount, GST as a rate and an amount, batch and
    expiry; then a GST summary by rate rather than by HSN, and the round-off.
    """
    pdf = InvoicePdfRenderer(TemplateSettings(page_size="HALF")).render(_trade_bill())
    sizes = _page_sizes(pdf)
    assert len(sizes) == 1 and _is(sizes[0], _HALF), sizes

    printed = _text_of(pdf)
    for fact in (
        "MRP",
        "Free",
        "Disc.",
        "GST %",
        "Net Amount",
        "Batch",
        "Exp. Dt",
        "SI-2026-2027-000012",
        "27ELEC01A1Z5",
        "QuickTech Retail",
        "Extension Board 5 Meter",
        "854442",
        "320.00",
        "B2407",
        "Mar 2028",
        "AP/10/02/2019-4916",
        "10114010000243",
        # The summary by rate: 9 + 9 is one row at 18%.
        "18%",
        "Round off",
        "0.29",
        "1,180.00",
        "Customer signature",
    ):
        assert fact in printed, fact
    # By rate, not by HSN: the full page's summary is not drawn here.
    assert "HSN / SAC" not in printed


def test_each_copy_on_half_page_paper_is_a_half_page_of_its_own() -> None:
    """Original and duplicate are two half pages, each saying which it is."""
    template = TemplateSettings(page_size="HALF", copy_labels=("ORIGINAL", "DUPLICATE"))
    pdf = InvoicePdfRenderer(template).render(_trade_bill())
    sizes = _page_sizes(pdf)
    assert len(sizes) == 2 and all(_is(size, _HALF) for size in sizes), sizes
    printed = _text_of(pdf)
    assert "ORIGINAL" in printed and "DUPLICATE" in printed


def test_a_bill_too_long_for_half_a_page_prints_on_a_full_page_by_itself() -> None:
    """Nobody chooses the paper per bill: the long one switches on its own.

    And it prints as a full-page bill, in the full page's layout, rather than
    as half a page of lines with the totals alone on a second half page.
    """
    template = TemplateSettings(page_size="HALF")
    pdf = InvoicePdfRenderer(template).render(_trade_bill(lines=40))
    sizes = _page_sizes(pdf)
    assert sizes and all(_is(size, _FULL) for size in sizes), sizes
    printed = _text_of(pdf)
    assert "HSN / SAC" in printed
    assert "AMOUNT CHARGEABLE, IN WORDS" in printed

    # A handful of lines still fits: the switch is not at the second line.
    few = _page_sizes(InvoicePdfRenderer(template).render(_trade_bill(lines=6)))
    assert len(few) == 1 and _is(few[0], _HALF), few


def test_a_run_gives_each_bill_the_paper_it_prints_on_alone() -> None:
    """Half pages and full pages share one file, each bill on its own paper."""
    half = TemplateSettings(page_size="HALF")
    full = TemplateSettings(page_size="A4")
    pdf = render_together(
        [
            (half, _trade_bill()),
            # Too long for half: a full page, by itself.
            (half, _trade_bill(lines=40)),
            (half, replace(_trade_bill(), number="SI-LAST")),
            # A customer whose bills print on a full page.
            (full, replace(_trade_bill(), number="SI-FULL")),
        ],
        title="Sales invoices",
    )
    sizes = _page_sizes(pdf)
    assert _is(sizes[0], _HALF), sizes
    assert _is(sizes[1], _FULL), sizes
    # The long bill may take more than one full page; the two after it are
    # the last two pages, on their own papers again.
    assert _is(sizes[-2], _HALF), sizes
    assert _is(sizes[-1], _FULL), sizes
    assert all(_is(size, _FULL) for size in sizes[1:-2]), sizes
    printed = _text_of(pdf)
    assert printed.index("SI-LAST") < printed.index("SI-FULL")


def _lot_bill() -> InvoiceDocument:
    """Two lines from two lots: one records when it was made, one does not."""
    line = _trade_bill().lines[0]
    return replace(
        _trade_bill(),
        show_total_quantity=True,
        lines=(
            replace(line, quantity=Decimal("4"), manufactured="01/26"),
            replace(
                line,
                number=2,
                quantity=Decimal("6.5"),
                free_quantity=Decimal("2"),
                batch="B2408",
            ),
        ),
    )


def test_the_full_page_prints_when_a_lot_was_made_and_leaves_the_rest_blank() -> None:
    """A column of its own, only on a bill with a lot that records the date.

    The customer's full-page sample carries the manufacture date beside the
    batch (row P2). The line whose lot records none prints the cell empty,
    and a bill with no such lot does not carry the column at all.
    """
    template = TemplateSettings(
        show_batch_column=True,
        show_expiry_column=True,
        show_manufactured_column=True,
    )
    printed = _text_of(InvoicePdfRenderer(template).render(_lot_bill()))
    assert " | Mfg | " in printed
    assert printed.count("01/26") == 1
    # Between the batch and the expiry, as the sample has it.
    assert printed.index("Batch") < printed.index(" | Mfg | ") < printed.index("Expiry")

    without = _text_of(
        InvoicePdfRenderer(replace(template, show_manufactured_column=False)).render(
            _lot_bill()
        )
    )
    assert " | Mfg | " not in without and "01/26" not in without


@pytest.mark.parametrize("paper", ["A4", "HALF"])
def test_the_quantities_are_added_up_under_the_lines(paper: str) -> None:
    """The total is the sum of the lines; free goods are counted beside it."""
    document = _lot_bill()
    assert document.total_quantity == Decimal("10.5")
    assert document.total_free_quantity == Decimal("3")

    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(page_size=paper)).render(document)
    )
    assert "Total quantity" in printed
    after = printed[printed.index("Total quantity") :]
    assert "10.5" in after and "3" in after

    # Only a document that asks: an order or a challan is not changed.
    plain = replace(document, show_total_quantity=False)
    assert "Total quantity" not in _text_of(
        InvoicePdfRenderer(TemplateSettings(page_size=paper)).render(plain)
    )


@pytest.mark.parametrize("paper", ["A4", "HALF"])
def test_the_firms_terms_print_on_both_sizes(paper: str) -> None:
    """Typed once under Print settings, at the foot of either paper."""
    template = TemplateSettings(
        page_size=paper, terms="Goods once sold are not taken back."
    )
    pdf = InvoicePdfRenderer(template).render(_trade_bill())
    assert _is(_page_sizes(pdf)[0], _HALF if paper == "HALF" else (595.28, 841.89))
    assert "Goods once sold are not taken back." in _text_of(pdf)


def test_a_whole_expiry_date_fits_its_cell_on_the_most_crowded_bill() -> None:
    """Sixteen columns on A4, and no figure runs over the cell beside it.

    Batch, manufacture date, expiry, MRP, discount and two tax components
    were sixteen columns: scaled down together, a whole date printed over the
    batch beside it and the free goods over the HSN. Such a bill now states
    GST as one rate and one amount a line, and every column has the room
    its widest figure needs.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from app.sales_invoice.services import invoice_pdf

    renderer = InvoicePdfRenderer(
        TemplateSettings(
            show_batch_column=True,
            show_manufactured_column=True,
            show_expiry_column=True,
            show_mrp_column=True,
        )
    )
    split = ["CGST %", "CGST amt", "SGST %", "SGST amt", "Amount"]
    assert renderer._is_crowded([*renderer._line_columns(), *split])
    # So the lines state GST as one rate and one amount.
    header = [*renderer._line_columns(), "GST %", "GST", "Amount"]
    width = 595.28 - 2 * 12 * 2.8346
    room = dict(zip(header, renderer._line_widths(width, header), strict=True))
    for column, widest in (
        ("Expiry", "2028-03-31"),
        ("Mfg", "01/26"),
        ("Qty", "+12 free"),
        ("HSN", "30049086"),
        ("Batch", "SXH1183B"),
        ("Rate", "2,462.00"),
        ("MRP", "4,750.00"),
        ("Disc.", "1,196.96"),
        ("Taxable", "12,345.00"),
        ("GST %", "18.00"),
        ("GST", "1,234.00"),
        ("Amount", "112,345.00"),
    ):
        needed = stringWidth(widest, "Helvetica", invoice_pdf._CROWDED_FONT)
        assert needed <= room[column] - 2 * invoice_pdf._LINE_PADDING, column


def test_a_bill_with_its_batches_states_gst_as_one_rate_and_one_amount() -> None:
    """The halves stay by name under the lines; a plain bill is unchanged."""
    template = TemplateSettings(
        show_batch_column=True, show_expiry_column=True, show_mrp_column=True
    )
    printed = _text_of(InvoicePdfRenderer(template).render(_lot_bill()))
    lines = printed[printed.index("Description") : printed.index("Total quantity")]
    assert "GST | %" in lines or "GST %" in lines
    assert "18.00" in lines and "180.00" in lines
    assert "CGST" not in lines and "SGST" not in lines
    after = printed[printed.index("Total quantity") :]
    assert "CGST" in after and "SGST" in after and "HSN / SAC" in after

    # A heading wraps in its cell, so the runs are joined back up.
    plain = _text_of(InvoicePdfRenderer(TemplateSettings()).render(_document()))
    plain = plain.replace(" | ", " ")
    assert "CGST %" in plain and "SGST amt" in plain
