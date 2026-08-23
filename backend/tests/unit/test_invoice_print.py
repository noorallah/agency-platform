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
from decimal import Decimal

import pytest

from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
    amount_in_words,
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

    assert "10 + 1 free" in printed


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
