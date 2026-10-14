"""A sample bill drawn with the settings on the screen (backlog 143).

*Print settings* offers a choice of layouts, and a choice nobody can see is a
guess. So the dialog sends what it holds, saved or not, and gets back a bill
that is plainly a sample: the firm's own name, address and licences at the
head, its bank account, terms and copies, and a few lines that use every
column the layouts print -- an MRP, free goods, a discount, a batch, when it
was made and when it expires.

Nothing is read from a real bill and nothing is written: the preview is a
picture of the settings, not of any customer's account.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.document_framework.schemas import DocumentPrintTemplateWrite
from app.document_framework.services.print_support import (
    firm_party,
    with_bank_account,
)
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)

#: Across the top of every copy, so a sample can never pass for a bill.
SAMPLE_BANNER = "SAMPLE - NOT A TAX INVOICE"


def _line(
    number: int,
    description: str,
    hsn: str,
    quantity: str,
    rate: str,
    *,
    gst: str,
    discount: str = "0",
    free: str = "0",
    mrp: str,
    batch: str,
    made: str | None,
    expiry: str,
) -> InvoiceLineBlock:
    """Return one sample line with its GST split into halves."""
    taxable = Decimal(quantity) * Decimal(rate) - Decimal(discount)
    half_rate = Decimal(gst) / 2
    half = (taxable * half_rate / 100).quantize(Decimal("0.01"))
    return InvoiceLineBlock(
        number=number,
        description=description,
        hsn=hsn,
        quantity=Decimal(quantity),
        uom="NOS",
        rate=Decimal(rate),
        discount=Decimal(discount),
        taxable=taxable,
        total=taxable + 2 * half,
        free_quantity=Decimal(free),
        batch=batch,
        manufactured=made,
        expiry=expiry,
        mrp=Decimal(mrp),
        taxes=(("CGST", half_rate, half), ("SGST", half_rate, half)),
    )


def sample_document(seller: PartyBlock) -> InvoiceDocument:
    """Return the sample bill: the firm's own head over illustrative lines."""
    lines = (
        _line(
            1,
            "Sample Syrup 100 ML",
            "30049099",
            "24",
            "52.50",
            gst="12",
            mrp="75.00",
            free="2",
            batch="SB2401",
            made="01/26",
            expiry="12/27",
        ),
        _line(
            2,
            "Sample Tablets 10 x 10",
            "30049069",
            "10",
            "118.00",
            gst="12",
            discount="59.00",
            mrp="165.00",
            batch="ST1187",
            made="03/26",
            expiry="02/28",
        ),
        _line(
            3,
            "Sample Cream 30 GM",
            "33049990",
            "12",
            "61.25",
            gst="18",
            mrp="95.00",
            batch="SC0302",
            made=None,
            expiry="06/27",
        ),
    )
    taxable = sum((line.taxable for line in lines), Decimal("0"))
    total = sum((line.total for line in lines), Decimal("0"))
    grand = total.quantize(Decimal("1"))
    return InvoiceDocument(
        number="SAMPLE-0001",
        date="01 Jan 2027",
        due_date="31 Jan 2027",
        place_of_supply=seller.state,
        reverse_charge=False,
        seller=seller,
        buyer=PartyBlock(
            name="Sample Medical Stores",
            address_lines=["12 Market Road", "Your City"],
            gstin="00AAAAA0000A1Z0",
            contact="Ph. 90000 00000",
            licences=(("DL No.1", "SAMPLE/20B/0001"), ("DL No.2", "SAMPLE/21B/0001")),
        ),
        ship_to=None,
        lines=lines,
        taxable_total=taxable,
        tax_total=total - taxable,
        charges=Decimal("0"),
        round_off=grand - total,
        grand_total=grand,
        references=(("Market", "Sample Market"),),
        show_total_quantity=True,
        order_by="Sample Salesman",
        not_final=SAMPLE_BANNER,
    )


def sample_bill_pdf(
    session: Session,
    *,
    firm_scope: UUID,
    document_type: str,
    settings: DocumentPrintTemplateWrite,
) -> bytes:
    """Return a sample bill drawn with ``settings``, which need not be saved.

    Raises:
        ValidationError: For a document other than a sales invoice, which
            has no layout to choose and is previewed by printing one.

    """
    if document_type.strip().upper() != "SALES_INVOICE":
        raise ValidationError(
            "A sample is drawn for a sales invoice. Print any other document "
            "to see how it looks."
        )
    template = TemplateSettings(
        title_text=settings.title_text,
        accent_color=settings.accent_color,
        header_note=settings.header_note,
        show_bank_details=settings.show_bank_details,
        bank_details=settings.bank_details,
        upi_id=None,
        terms=settings.terms,
        declaration=settings.declaration or TemplateSettings().declaration,
        jurisdiction=settings.jurisdiction,
        footer_note=settings.footer_note,
        signatory_text=settings.signatory_text,
        show_discount_column=settings.show_discount_column,
        show_batch_column=settings.show_batch_column,
        show_expiry_column=settings.show_expiry_column,
        show_manufactured_column=settings.show_batch_column,
        show_mrp_column=settings.show_batch_column,
        copy_labels=tuple(settings.copy_labels),
        page_size=settings.page_size,
        margin_mm=settings.margin_mm,
        bill_layout=settings.bill_layout,
    )
    template = with_bank_account(session, firm_scope=firm_scope, settings=template)
    return InvoicePdfRenderer(template).render(sample_document(firm_party(firm_scope)))
