"""Several bills, or several challans, printed as one PDF.

A morning's dispatches are forty challans and forty bills, and printing them
one at a time is forty trips to the printer. A run prints the chosen documents
as one file: each exactly as it would print alone -- its copies, its columns --
and in the order chosen.
"""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.customers.models import Customer
from app.delivery_note.api.router import ChallanPrintRunRequest
from app.delivery_note.services.challan_print_service import (
    DeliveryChallanPrintService,
)
from app.document_framework.models import DocumentPrintTemplate
from app.sales_invoice.api.router import InvoicePrintRunRequest
from app.sales_invoice.services.invoice_pdf import (
    MAX_PRINT_RUN,
    InvoicePdfRenderer,
    TemplateSettings,
    render_together,
)
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
)
from tests.unit.test_invoice_print import _document, _page_sizes, _text_of
from tests.unit.test_sales_chain_synthesis import (
    _Firm,
    _persons_note,
    _session_factory,
)
from tests.unit.test_walk_in_cash_sale import _counter, _draft, _walk_in_bill


def test_a_run_prints_every_copy_of_every_document_in_order() -> None:
    """Two bills of two copies are four pages, the first bill's first."""
    template = TemplateSettings(copy_labels=("ORIGINAL", "DUPLICATE"))
    first = replace(_document(), number="SI-000001")
    second = replace(_document(), number="SI-000002")

    pdf = render_together([(template, first), (template, second)], title="Bills")

    assert len(_page_sizes(pdf)) == 4
    printed = _text_of(pdf)
    assert printed.count("SI-000001") == printed.count("SI-000002") > 0
    assert printed.index("SI-000001") < printed.index("SI-000002")
    assert printed.count("ORIGINAL") == printed.count("DUPLICATE") == 2


def test_a_document_in_a_run_prints_as_it_would_alone() -> None:
    """One bill in a run draws the same words as that bill printed singly."""
    template = TemplateSettings(copy_labels=("ORIGINAL", "DUPLICATE"))

    alone = InvoicePdfRenderer(template).render(_document())
    together = render_together([(template, _document())], title="Bills")

    assert _text_of(together) == _text_of(alone)
    assert _page_sizes(together) == _page_sizes(alone)


def test_each_document_in_a_run_keeps_its_own_template() -> None:
    """A bill with batches shows its batch column; its neighbour does not."""
    plain = TemplateSettings(copy_labels=("ONLY",))
    three = TemplateSettings(copy_labels=("A-COPY", "B-COPY", "C-COPY"))

    pdf = render_together([(plain, _document()), (three, _document())], title="Bills")

    assert len(_page_sizes(pdf)) == 4
    printed = _text_of(pdf)
    assert printed.count("ONLY") == 1
    assert "B-COPY" in printed


def test_a_roll_is_refused_for_a_run() -> None:
    """Every bill on a roll is a page of its own length, so a run cannot be."""
    roll = TemplateSettings(page_size="THERMAL80")

    with pytest.raises(BusinessRuleError, match="one at a time"):
        render_together([(roll, _document()), (roll, _document())], title="Bills")


def test_a_run_of_invoices_is_one_file_in_the_order_asked_for() -> None:
    """The service prints the firm's own bills, last asked for last."""
    session, setup, cash = _counter()
    one = _draft(session, setup, _walk_in_bill(setup, cash))
    two = _draft(session, setup, _walk_in_bill(setup, cash))

    pdf, filename = SalesInvoicePrintService(session).render_many(
        [two.id, one.id, two.id], firm_scope=setup.firm.id
    )

    printed = _text_of(pdf)
    assert filename == "sales-invoices.pdf"
    assert printed.index(two.invoice_number) < printed.index(one.invoice_number)
    # An id asked for twice prints once.
    single, _ = SalesInvoicePrintService(session).render(
        two.id, firm_scope=setup.firm.id
    )
    assert printed.count(two.invoice_number) == _text_of(single).count(
        two.invoice_number
    )


def test_a_run_naming_a_bill_that_is_not_the_firms_prints_nothing() -> None:
    """One bad id refuses the whole run rather than printing a short one."""
    session, setup, cash = _counter()
    one = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)

    with pytest.raises(ResourceNotFoundError):
        printer.render_many([one.id, uuid4()], firm_scope=setup.firm.id)
    with pytest.raises(ResourceNotFoundError):
        printer.render_many([one.id], firm_scope=uuid4())


def test_a_run_of_challans_is_one_file() -> None:
    """Two delivery notes print as one PDF holding both challans."""
    session = _session_factory()()
    setup = _Firm(session)
    one = _persons_note(setup)
    two = _persons_note(setup)
    printer = DeliveryChallanPrintService(session)

    pdf, filename = printer.render_many([one.id, two.id], firm_scope=setup.firm.id)

    printed = _text_of(pdf)
    assert filename == "delivery-challans.pdf"
    assert one.delivery_note_number in printed
    assert two.delivery_note_number in printed
    alone, _ = printer.render(one.id, firm_scope=setup.firm.id)
    assert len(_page_sizes(pdf)) == 2 * len(_page_sizes(alone))
    with pytest.raises(ResourceNotFoundError):
        printer.render_many([one.id, uuid4()], firm_scope=setup.firm.id)


def test_a_run_is_capped() -> None:
    """A run is one file held in memory, so it is bounded at the request."""
    too_many = [uuid4() for _ in range(MAX_PRINT_RUN + 1)]

    with pytest.raises(ValueError, match="at most"):
        InvoicePrintRunRequest(invoice_ids=too_many)
    with pytest.raises(ValueError, match="at most"):
        ChallanPrintRunRequest(note_ids=too_many)
    with pytest.raises(ValueError, match="at least"):
        InvoicePrintRunRequest(invoice_ids=[])


HALF_SHEET = (595, 421)
FULL_SHEET = (595, 842)


def _papers(
    printer: SalesInvoicePrintService,
    bill_id: UUID,
    firm_id: UUID,
    *,
    paper: str | None = None,
) -> set[tuple[int, int]]:
    """Return the page sizes one bill prints on, in whole points."""
    pdf, _ = printer.render(
        bill_id, firm_scope=firm_id, reference_copy=True, paper=paper
    )
    return {(round(width), round(height)) for width, height in _page_sizes(pdf)}


def _on_half_pages(session: Session, firm_id: UUID) -> None:
    """Set the firm's sales bills to print on half pages."""
    session.add(
        DocumentPrintTemplate(
            firm_id=firm_id,
            document_type="SALES_INVOICE",
            page_size="HALF",
            created_by=firm_id,
            updated_by=firm_id,
        )
    )
    session.commit()


def test_a_full_page_firm_does_not_read_the_customers_paper() -> None:
    """Every bill of a full-page firm is a full page, whoever it is for.

    The firm's paper is what is in the printer's tray (the owner,
    2026-10-13): a customer set to half a page before the firm changed its
    mind does not send a half-page bill to a tray of full sheets.
    """
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)
    customer = session.get(Customer, bill.customer_id)
    assert customer is not None

    assert _papers(printer, bill.id, setup.firm.id) == {FULL_SHEET}

    customer.bill_page_size = "HALF"
    session.commit()
    assert _papers(printer, bill.id, setup.firm.id) == {FULL_SHEET}

    said = printer.paper_for(bill.id, firm_scope=setup.firm.id)
    assert (said.firm_paper, said.paper, said.customer_paper) == ("A4", "A4", None)
    assert not said.may_choose
    assert not said.fits_half_page


def test_a_half_page_firm_prints_full_for_the_customer_set_so() -> None:
    """On a half-page firm one buyer's bills print on a full page."""
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)
    _on_half_pages(session, setup.firm.id)
    customer = session.get(Customer, bill.customer_id)
    assert customer is not None

    assert _papers(printer, bill.id, setup.firm.id) == {HALF_SHEET}
    said = printer.paper_for(bill.id, firm_scope=setup.firm.id)
    assert (said.firm_paper, said.paper, said.customer_paper) == ("HALF", "HALF", None)
    assert said.may_choose
    assert said.fits_half_page

    customer.bill_page_size = "A4"
    session.commit()
    assert _papers(printer, bill.id, setup.firm.id) == {FULL_SHEET}
    said = printer.paper_for(bill.id, firm_scope=setup.firm.id)
    assert (said.paper, said.customer_paper) == ("A4", "A4")
    # The bill would fit on half a page, so the person printing may ask.
    assert said.may_choose


def test_the_person_printing_switches_one_print_either_way() -> None:
    """The choice made at printing outranks the customer's paper, once."""
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)
    _on_half_pages(session, setup.firm.id)
    customer = session.get(Customer, bill.customer_id)
    assert customer is not None

    assert _papers(printer, bill.id, setup.firm.id, paper="A4") == {FULL_SHEET}
    assert _papers(printer, bill.id, setup.firm.id, paper="HALF") == {HALF_SHEET}

    customer.bill_page_size = "A4"
    session.commit()
    assert _papers(printer, bill.id, setup.firm.id, paper="HALF") == {HALF_SHEET}
    # Nothing was stored: the next print is the customer's paper again.
    assert _papers(printer, bill.id, setup.firm.id) == {FULL_SHEET}


def test_a_long_bill_goes_to_a_full_page_whatever_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bill that does not fit on half a page is a full page, and says so."""
    from app.sales_invoice.services.half_page_pdf import HalfPageRenderer

    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)
    _on_half_pages(session, setup.firm.id)
    # What the half-page layout answers for a document too long for it.
    monkeypatch.setattr(HalfPageRenderer, "render", lambda self, document: None)

    assert _papers(printer, bill.id, setup.firm.id) == {FULL_SHEET}
    assert _papers(printer, bill.id, setup.firm.id, paper="HALF") == {FULL_SHEET}
    said = printer.paper_for(bill.id, firm_scope=setup.firm.id)
    assert (said.firm_paper, said.paper) == ("HALF", "A4")
    assert not said.fits_half_page
    assert not said.may_choose


def test_a_paper_is_not_chosen_where_the_firm_has_one() -> None:
    """Half a page asked of a full-page firm is refused, by name."""
    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)

    with pytest.raises(BusinessRuleError, match="half pages"):
        printer.render(
            bill.id, firm_scope=setup.firm.id, reference_copy=True, paper="HALF"
        )
    # Asking for the paper the firm prints on anyway is not a choice.
    assert _papers(printer, bill.id, setup.firm.id, paper="A4") == {FULL_SHEET}


def test_a_run_keeps_each_bills_own_paper_on_a_half_page_firm() -> None:
    """Print selected asks nobody: the full-page customer's bill is full."""
    session, setup, cash = _counter()
    first = _draft(session, setup, _walk_in_bill(setup, cash))
    printer = SalesInvoicePrintService(session)
    _on_half_pages(session, setup.firm.id)
    customer = session.get(Customer, first.customer_id)
    assert customer is not None
    customer.bill_page_size = "A4"
    session.commit()

    pdf, _ = printer.render_many([first.id], firm_scope=setup.firm.id)
    sizes = {(round(width), round(height)) for width, height in _page_sizes(pdf)}
    assert sizes == {FULL_SHEET}


def test_the_paper_route_answers_what_the_service_says() -> None:
    """The screen reads the paper from the route before it prints."""
    from app.sales_invoice.api.router import sales_invoice_paper

    session, setup, cash = _counter()
    bill = _draft(session, setup, _walk_in_bill(setup, cash))
    _on_half_pages(session, setup.firm.id)
    scope = SimpleNamespace(firm_id=setup.firm.id)

    answer = sales_invoice_paper(bill.id, scope, session).data  # type: ignore[arg-type]

    assert answer is not None
    assert (answer.firm_paper, answer.paper) == ("HALF", "HALF")
    assert answer.may_choose
