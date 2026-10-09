"""Several bills, or several challans, printed as one PDF.

A morning's dispatches are forty challans and forty bills, and printing them
one at a time is forty trips to the printer. A run prints the chosen documents
as one file: each exactly as it would print alone -- its copies, its columns --
and in the order chosen.
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.delivery_note.api.router import ChallanPrintRunRequest
from app.delivery_note.services.challan_print_service import (
    DeliveryChallanPrintService,
)
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
