"""A sales invoice carries a UPI QR for what it still owes (MSG-2, A55).

The firm keeps its UPI ID on the invoice's print template, beside the bank
details. The QR is a ``upi://pay`` link for the amount still owed, carrying
the bill's number as the note so the money can be matched to the bill. No
UPI ID, nothing owed, or a bill that does not stand: no QR.
"""

# ruff: noqa: D103

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.document_framework.models import DocumentPrintTemplate
from app.document_framework.schemas import DocumentPrintTemplateWrite
from app.sales_invoice.services import invoice_print_service
from app.sales_invoice.services.invoice_pdf import (
    InvoicePdfRenderer,
    PartyBlock,
    TemplateSettings,
)
from app.sales_invoice.services.invoice_print_service import SalesInvoicePrintService
from app.sales_invoice.services.upi_qr import UpiPayment, upi_payment
from tests.unit.test_invoice_print import _document, _text_of
from tests.unit.test_invoice_print_sources import _bill
from tests.unit.test_sales_invoice_module import (
    _Billing,
    _dispatched_note,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers


@pytest.fixture(autouse=True)
def _no_platform_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the seller without opening the platform store."""
    monkeypatch.setattr(
        SalesInvoicePrintService,
        "_seller",
        lambda self, firm_scope, branch_id=None: PartyBlock(
            name="Sri Ram & Sons", address_lines=[]
        ),
    )


# ---------------------------------------------------------------------------
# The link


def test_the_link_names_the_payee_the_amount_and_the_bill() -> None:
    payment = upi_payment(
        upi_id="sriram@okaxis",
        payee="Sri Ram & Sons",
        amount=Decimal("1234.5"),
        note="SI-26-27-000042",
    )

    assert payment is not None
    assert payment.amount == Decimal("1234.50")
    assert payment.uri == (
        "upi://pay?pa=sriram@okaxis&pn=Sri%20Ram%20%26%20Sons&am=1234.50"
        "&cu=INR&tn=SI-26-27-000042"
    )


@pytest.mark.parametrize(
    ("upi_id", "amount"),
    [(None, Decimal("10")), ("  ", Decimal("10")), ("a@b", Decimal("0"))],
)
def test_no_upi_id_or_nothing_owed_asks_for_nothing(
    upi_id: str | None, amount: Decimal
) -> None:
    assert upi_payment(upi_id=upi_id, payee="Shop", amount=amount, note="SI-1") is None


# ---------------------------------------------------------------------------
# On paper


def _with_upi(amount: str = "1180.00") -> UpiPayment | None:
    return upi_payment(
        upi_id="sriram@okaxis",
        payee="Seller",
        amount=Decimal(amount),
        note="SI-1",
    )


def test_the_a4_bill_says_scan_to_pay_with_the_amount_and_the_id() -> None:
    document = replace(_document(), upi=_with_upi())

    printed = _text_of(InvoicePdfRenderer().render(document))

    assert "SCAN TO PAY BY UPI" in printed
    assert "1,180.00" in printed
    assert "to sriram@okaxis" in printed


def test_the_counter_roll_carries_the_qr_under_the_total() -> None:
    document = replace(_document(), upi=_with_upi())

    printed = _text_of(
        InvoicePdfRenderer(TemplateSettings(page_size="THERMAL80")).render(document)
    )

    assert "Scan to pay by UPI" in printed
    assert printed.index("TOTAL") < printed.index("Scan to pay by UPI")
    assert "to sriram@okaxis" in printed


def test_a_bill_with_no_upi_asks_for_nothing_on_paper() -> None:
    printed = _text_of(InvoicePdfRenderer().render(_document()))

    assert "UPI" not in printed


# ---------------------------------------------------------------------------
# From the record


def _template(setup: _Billing, upi_id: str | None) -> None:
    setup.session.add(
        DocumentPrintTemplate(
            firm_id=setup.firm.id,
            document_type="SALES_INVOICE",
            upi_id=upi_id,
            created_by=setup.firm.id,
            updated_by=setup.firm.id,
        )
    )
    setup.session.flush()


def _printed(setup: _Billing, invoice_id: object) -> str:
    pdf, _ = SalesInvoicePrintService(setup.session).render(
        invoice_id,  # type: ignore[arg-type]
        firm_scope=setup.firm.id,
    )
    return _text_of(pdf).replace(" | ", "")


def test_a_draft_bill_asks_for_no_payment() -> None:
    setup = _Billing(_session_factory()())
    _template(setup, "sriram@okaxis")
    invoice = _bill(setup, [_dispatched_note(setup, quantity=Decimal("2"))])

    assert "UPI" not in _printed(setup, invoice.id)


def test_a_bill_that_stands_asks_for_what_it_still_owes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _Billing(_session_factory()())
    _template(setup, "sriram@okaxis")
    invoice = _bill(setup, [_dispatched_note(setup, quantity=Decimal("2"))])
    invoice.status = "APPROVED"
    setup.session.flush()

    whole = _printed(setup, invoice.id)
    assert "SCAN TO PAY BY UPI" in whole
    assert f"{invoice.grand_total:,.2f}" in whole.split("SCAN TO PAY BY UPI")[1]

    # Part-paid: the QR asks only for the rest.
    from app.settlements.services import settlement_service

    monkeypatch.setattr(
        settlement_service,
        "settled_against",
        lambda session, *, firm_id, invoice_ids: {invoice.id: Decimal("100")},
    )
    rest = invoice.grand_total - Decimal("100")
    part = _printed(setup, invoice.id)
    assert f"{rest:,.2f}" in part.split("SCAN TO PAY BY UPI")[1]

    # Paid in full at the counter: nothing to scan.
    monkeypatch.setattr(
        settlement_service,
        "settled_against",
        lambda session, *, firm_id, invoice_ids: {invoice.id: invoice.grand_total},
    )
    assert "UPI" not in _printed(setup, invoice.id)


def test_a_firm_with_no_upi_id_prints_no_qr() -> None:
    setup = _Billing(_session_factory()())
    _template(setup, None)
    invoice = _bill(setup, [_dispatched_note(setup, quantity=Decimal("2"))])
    invoice.status = "APPROVED"
    setup.session.flush()

    assert "UPI" not in _printed(setup, invoice.id)
    assert invoice_print_service.DOCUMENT_TYPE == "SALES_INVOICE"


# ---------------------------------------------------------------------------
# Saving it


def test_a_upi_id_is_kept_and_a_blank_one_is_none() -> None:
    assert (
        DocumentPrintTemplateWrite(upi_id=" sriram.store@okaxis ").upi_id
        == "sriram.store@okaxis"
    )
    assert DocumentPrintTemplateWrite(upi_id="  ").upi_id is None


@pytest.mark.parametrize("bad", ["sriram", "sriram@", "@okaxis", "sri ram@okaxis"])
def test_a_upi_id_no_app_could_pay_is_refused(bad: str) -> None:
    with pytest.raises(ValidationError, match="UPI ID"):
        DocumentPrintTemplateWrite(upi_id=bad)


def test_the_saved_upi_id_reaches_the_print() -> None:
    from app.document_framework.services.print_template_service import (
        DocumentPrintTemplateService,
    )

    setup = _Billing(_session_factory()())
    service = DocumentPrintTemplateService(setup.session)
    saved = service.set(
        "SALES_INVOICE",
        DocumentPrintTemplateWrite(upi_id="sriram@okaxis"),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )

    assert saved.upi_id == "sriram@okaxis"
    template = SalesInvoicePrintService(setup.session)._template(setup.firm.id)
    assert template.upi_id == "sriram@okaxis"
