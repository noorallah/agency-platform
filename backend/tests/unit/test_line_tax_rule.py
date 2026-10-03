"""The tax rule that decided a line is kept on the line (GST-8, decision A85).

The execution log that says which rule taxed a line is purged after 90 days;
a reprint years later still has to say it. A bill taxed by ``SALES_DEFAULT``
version 1 keeps that on its line, and the response carries it. Lines written
before stay null rather than carry a guess.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.tax.services.tax_rule_service import TaxRuleService
from tests.unit.test_sales_invoice_module import (
    _branch,
    _customer,
    _dispatched_line_for,
    _firm,
    _gst_profile,
    _product,
    _session_factory,
    _warehouse,
)

pytestmark = pytest.mark.typed_document_numbers


def _bill() -> tuple[SalesInvoiceService, SalesInvoice, Session]:
    """Raise a bill of four at 250 from a dispatched note, taxed at 18%."""
    session = _session_factory()()
    actor_id = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    profile = _gst_profile(session, firm=firm, actor_id=actor_id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                    tax_profile_id=profile.id,  # type: ignore[attr-defined]
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    return service, invoice, session


def test_the_line_keeps_the_rule_that_taxed_it() -> None:
    service, invoice, session = _bill()
    line = session.scalar(select(SalesInvoiceLine))
    assert line is not None
    assert (line.tax_rule_code, line.tax_rule_version) == ("SALES_DEFAULT", 1)
    response = service.invoice_response(invoice)
    assert (response.lines[0].tax_rule_code, response.lines[0].tax_rule_version) == (
        "SALES_DEFAULT",
        1,
    )


def test_the_simulation_names_the_rule_by_code_and_version() -> None:
    service, invoice, session = _bill()
    tax = TaxRuleService(session)
    assert tax.rule_for(invoice.id, 1) is None, "only lines simulated here"
    assert service._tax.rule_for(invoice.id, 1) == ("SALES_DEFAULT", 1)
