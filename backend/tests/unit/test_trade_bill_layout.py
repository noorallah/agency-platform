"""A firm chooses the layout of its full-page bill (backlog 143).

Two layouts: the standard bill every firm printed until now, and the trade's
boxed bill, laid out after the customer's own sample (`long bill.pdf`). The
choice is the firm's, in *Print settings*, beside a sample it can look at
before saving. These pin that the trade layout states what a tax invoice must
and the trade's columns besides, that it reaches the bill and nothing that
borrows the bill's template, and that only a sales invoice may take it.
"""

# ruff: noqa: D103

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.document_framework.models import DocumentPrintTemplate
from app.document_framework.schemas import DocumentPrintTemplateWrite
from app.document_framework.services import DocumentPrintTemplateService
from app.document_framework.services.print_support import load_template
from app.sales_invoice.services import print_preview
from app.sales_invoice.services.invoice_pdf import (
    InvoiceDocument,
    InvoiceLineBlock,
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_invoice.services.invoice_print_service import SalesInvoicePrintService
from tests.unit.test_invoice_print import _document, _text_of

TRADE = TemplateSettings(bill_layout="TRADE")


def _session() -> Session:
    """Return a session over every table, as the request sees them."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _with_licences() -> InvoiceDocument:
    """Return the test bill with licences on both sides and who took it."""
    document = _document()
    return replace(
        document,
        seller=replace(document.seller, licences=(("FSSAI", "10114010000243"),)),
        buyer=replace(
            document.buyer,
            licences=(("DL NO.1", "1028/AP/TPT/R/2005"),),
            contact="Ph.9966913335",
        ),
        references=(("Market", "PK LAY OUT"),),
        order_by="COMP STAFF",
        show_total_quantity=True,
    )


# ---------------------------------------------------------------------------
# What the trade layout prints


def test_the_trade_bill_states_what_a_tax_invoice_must() -> None:
    printed = _text_of(InvoicePdfRenderer(TRADE).render(_document()))

    for required in (
        "TAX INVOICE",
        # A long name wraps in its box, so it is two runs of text.
        "ElectroLink Appliances",
        "Distribution Private Limited",
        "27ELEC01A1Z5",
        "QuickTech Retail",
        "29ELEC01C0304Z5",
        "SI-2026-2027-000012",
        "22 Aug 2026",
        "854442",
        "CGST",
        "SGST",
        "Place of supply: Maharashtra",
        "One Thousand One Hundred",
    ):
        assert required in printed, required


def test_the_trade_bill_has_the_trades_columns_and_figures() -> None:
    """D.Price is the rate with its GST; P.T.R. the rate the GST was charged on."""
    printed = _text_of(InvoicePdfRenderer(TRADE).render(_document()))

    for heading in (
        "Product Details",
        "M.R.P",
        "D.Price",
        "QTY",
        "Free",
        "P.T.R.",
        "Disc.",
        "GST%",
        "Net Value",
        "Batch",
        "MfgDt",
        "ExpDt",
        "Net Payable:",
    ):
        assert heading in printed, heading
    # 250.00 at 18%: the dealer's price is 295.000, the line comes to 1,180.00.
    assert "295.000" in printed
    assert "250.000" in printed
    assert "1,180.00" in printed
    assert "18.00" in printed


def test_the_buyers_licences_print_under_his_details() -> None:
    """Not at the foot, as the sample has them (the owner, 2026-10-14)."""
    printed = _text_of(InvoicePdfRenderer(TRADE).render(_with_licences()))

    assert "Sold To :QuickTech Retail" in printed
    licence = printed.index("DL NO.1 : 1028/AP/TPT/R/2005")
    assert printed.index("Sold To :QuickTech Retail") < licence
    assert licence < printed.index("Order By : COMP STAFF")
    assert "FSSAI : 10114010000243" in printed


def test_who_took_the_order_and_the_market_print_at_the_head() -> None:
    printed = _text_of(InvoicePdfRenderer(TRADE).render(_with_licences()))

    assert "Order By : COMP STAFF" in printed
    assert "Market : PK LAY OUT" in printed
    assert "Total quantity" in printed


def test_gross_less_the_discount_is_the_taxable_value() -> None:
    """The rows add down to what the bill charges, as printed."""
    document = _document()
    line = document.lines[0]
    discounted = replace(
        document,
        lines=(
            replace(
                line,
                discount=Decimal("100.00"),
                taxable=Decimal("900.00"),
                total=Decimal("1062.00"),
                taxes=(
                    ("CGST", Decimal("9"), Decimal("81.00")),
                    ("SGST", Decimal("9"), Decimal("81.00")),
                ),
            ),
        ),
        taxable_total=Decimal("900.00"),
        tax_total=Decimal("162.00"),
        grand_total=Decimal("1062.00"),
    )
    printed = _text_of(InvoicePdfRenderer(TRADE).render(discounted))

    assert "Gross | 1,000.00" in printed
    assert "Less discount | -100.00" in printed
    assert "Taxable value | 900.00" in printed
    assert "Net Payable: | 1,062.00" in printed


def test_free_goods_print_in_their_own_column_and_are_not_added_in() -> None:
    document = _document()
    with_free: InvoiceLineBlock = replace(document.lines[0], free_quantity=Decimal("1"))
    printed = _text_of(
        InvoicePdfRenderer(TRADE).render(
            replace(document, lines=(with_free,), show_total_quantity=True)
        )
    )

    assert "4.00 | 1.00" in printed


def test_every_copy_the_firm_prints_is_labelled() -> None:
    template = replace(TRADE, copy_labels=("Original", "Duplicate"))
    printed = _text_of(InvoicePdfRenderer(template).render(_document()))

    assert "Original" in printed
    assert "Duplicate" in printed


# ---------------------------------------------------------------------------
# Where the choice reaches


def test_the_standard_layout_is_unchanged() -> None:
    printed = _text_of(InvoicePdfRenderer(TemplateSettings()).render(_document()))

    assert "P.T.R." not in printed
    assert "Net Payable:" not in printed


def test_the_half_page_and_the_roll_keep_their_own_layouts() -> None:
    for paper in ("HALF", "THERMAL80"):
        template = replace(TRADE, page_size=paper)
        printed = _text_of(InvoicePdfRenderer(template).render(_document()))
        assert "P.T.R." not in printed, paper


def test_the_bill_reads_the_firms_layout_and_nothing_else_does() -> None:
    """A transfer or a voucher borrows the bill's template for its letterhead."""
    session = _session()
    firm_id = uuid4()
    session.add(
        DocumentPrintTemplate(
            firm_id=firm_id,
            document_type="SALES_INVOICE",
            bill_layout="TRADE",
            created_by=firm_id,
            updated_by=firm_id,
        )
    )
    session.commit()

    assert SalesInvoicePrintService(session)._template(firm_id).bill_layout == "TRADE"
    borrowed = load_template(session, firm_scope=firm_id, document_type="SALES_INVOICE")
    assert borrowed.bill_layout == "STANDARD"


# ---------------------------------------------------------------------------
# Saving the choice


def test_a_sales_invoice_saves_the_trade_layout_and_reads_it_back() -> None:
    session = _session()
    firm_id = uuid4()
    service = DocumentPrintTemplateService(session)

    saved = service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(bill_layout="TRADE"),
        firm_scope=firm_id,
        actor_id=firm_id,
    )
    session.commit()

    assert saved.bill_layout == "TRADE"
    assert service.get("SALES_INVOICE", firm_scope=firm_id).bill_layout == "TRADE"


def test_an_update_that_does_not_send_the_layout_keeps_it() -> None:
    """Absent leaves it alone: an older screen must not put a firm back."""
    session = _session()
    firm_id = uuid4()
    service = DocumentPrintTemplateService(session)
    service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(bill_layout="TRADE"),
        firm_scope=firm_id,
        actor_id=firm_id,
    )
    service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite.model_validate({"terms": "Goods once sold."}),
        firm_scope=firm_id,
        actor_id=firm_id,
    )
    session.commit()

    assert service.get("SALES_INVOICE", firm_scope=firm_id).bill_layout == "TRADE"


def test_only_a_sales_invoice_may_take_the_trade_layout() -> None:
    session = _session()
    firm_id = uuid4()

    with pytest.raises(ValidationError, match="trade layout is for a sales invoice"):
        DocumentPrintTemplateService(session).set(
            "PURCHASE_ORDER",
            DocumentPrintTemplateWrite(bill_layout="TRADE"),
            firm_scope=firm_id,
            actor_id=firm_id,
        )


def test_a_layout_nobody_draws_is_refused() -> None:
    with pytest.raises(SchemaError):
        DocumentPrintTemplateWrite.model_validate({"bill_layout": "FANCY"})


# ---------------------------------------------------------------------------
# The sample in Print settings


@pytest.fixture
def _firm_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the firm without opening the platform store."""
    monkeypatch.setattr(
        print_preview,
        "firm_party",
        lambda firm_scope: PartyBlock(
            name="Sri Vinayaka Marketing",
            address_lines=["Railway Colony", "Tirupati"],
            gstin="37BOYPS1721R1ZT",
            state="Andhra Pradesh",
        ),
    )


@pytest.mark.usefixtures("_firm_head")
def test_the_sample_is_drawn_with_the_settings_on_the_screen() -> None:
    """Unsaved settings, the firm's own head, and a banner saying it is a sample."""
    session = _session()
    pdf = print_preview.sample_bill_pdf(
        session,
        firm_scope=uuid4(),
        document_type="SALES_INVOICE",
        settings=DocumentPrintTemplateWrite(
            bill_layout="TRADE", terms="Goods once sold are not taken back."
        ),
    )
    printed = _text_of(pdf)

    assert print_preview.SAMPLE_BANNER in printed
    assert "Sri Vinayaka Marketing" in printed
    assert "P.T.R." in printed
    assert "Goods once sold are not taken back." in printed
    assert session.query(DocumentPrintTemplate).count() == 0


@pytest.mark.usefixtures("_firm_head")
def test_the_sample_follows_the_layout_chosen() -> None:
    session = _session()
    printed = _text_of(
        print_preview.sample_bill_pdf(
            session,
            firm_scope=uuid4(),
            document_type="SALES_INVOICE",
            settings=DocumentPrintTemplateWrite(bill_layout="STANDARD"),
        )
    )

    assert print_preview.SAMPLE_BANNER in printed
    assert "P.T.R." not in printed


def test_a_sample_is_drawn_for_a_sales_invoice_only() -> None:
    with pytest.raises(ValidationError, match="sample is drawn for a sales invoice"):
        print_preview.sample_bill_pdf(
            _session(),
            firm_scope=uuid4(),
            document_type="PURCHASE_ORDER",
            settings=DocumentPrintTemplateWrite(),
        )
