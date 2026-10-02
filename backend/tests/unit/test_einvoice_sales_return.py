"""A sales return's credit note is e-invoiced like any other (D-TAX-2)."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import BusinessRuleError, ValidationError
from app.einvoice.services.note_registration import (
    SALES_RETURN,
    NoteRegistrationService,
)
from app.einvoice.services.offline import OfflineEInvoiceService
from app.einvoice.services.reporting_window import pending
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_return.models import SalesReturn, SalesReturnLine
from tests.unit.test_einvoice import WHEN, _Books, _einvoicing_since, _session_factory


def _return(
    books: _Books, *, status: str = "COMPLETED", billed: bool = True
) -> SalesReturn:
    """Record a return of 2 of SI-1's 10, crediting 200 plus 36 tax."""
    invoice_line = books.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.sales_invoice_id == books.invoice.id
        )
    )
    assert invoice_line is not None
    row = SalesReturn(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        warehouse_id=uuid4(),
        return_number="SR-1",
        return_date=WHEN,
        status=status,
        subtotal=Decimal("200"),
        tax_total=Decimal("36"),
        grand_total=Decimal("236"),
    )
    books.session.add(row)
    books.session.flush()
    books.session.add(
        SalesReturnLine(
            sales_return_id=row.id,
            firm_id=books.firm.id,
            line_number=1,
            source_document_type="SALES_INVOICE" if billed else "DELIVERY_NOTE",
            source_document_id=books.invoice.id if billed else uuid4(),
            source_document_number="SI-1" if billed else "DN-1",
            source_document_line_id=invoice_line.id if billed else uuid4(),
            source_document_line_number=1,
            product_id=books.product.id,
            current_return_quantity=Decimal("2"),
            tax_amount=Decimal("36"),
            net_amount=Decimal("236"),
        )
    )
    books.session.commit()
    return row


def _service(books: _Books) -> NoteRegistrationService:
    """Return the note registrar on the sandbox."""
    return NoteRegistrationService(books.session, base=books.service())


def test_a_return_registers_as_a_credit_note_naming_its_invoice() -> None:
    """CRN, its own number and values, the invoice it returns goods from."""
    books = _Books(_session_factory()())
    sales_return = _return(books)

    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    assert row.status == "REGISTERED" and row.sales_return_id == sales_return.id
    payload = row.request_payload
    assert payload["DocDtls"]["Typ"] == "CRN"  # type: ignore[index]
    assert payload["DocDtls"]["No"] == "SR-1"  # type: ignore[index]
    assert payload["RefDtls"]["PrecDocDtls"][0]["InvNo"] == "SI-1"  # type: ignore[index]
    assert payload["ValDtls"]["AssVal"] == 200.0  # type: ignore[index]
    assert payload["ValDtls"]["CgstVal"] + payload["ValDtls"]["SgstVal"] == 36.0  # type: ignore[index]


def test_a_return_still_open_is_not_registered() -> None:
    """Only a completed return has credited the customer."""
    books = _Books(_session_factory()())
    sales_return = _return(books, status="APPROVED")
    with pytest.raises(ValidationError, match="only an approved note"):
        _service(books).register(
            SALES_RETURN,
            sales_return.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_return_of_goods_never_invoiced_is_not_registered() -> None:
    """No tax invoice was issued, so there is nothing to credit."""
    books = _Books(_session_factory()())
    sales_return = _return(books, billed=False)
    with pytest.raises(ValidationError, match="no invoice billed"):
        _service(books).register(
            SALES_RETURN,
            sales_return.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_return_goes_in_the_offline_upload_and_comes_back_matched() -> None:
    """Exported as a CRN; the portal's CRN answer finds the return."""
    import json

    books = _Books(_session_factory()())
    sales_return = _return(books)
    offline = OfflineEInvoiceService(books.session)
    [payload] = offline.export(
        [],
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        sales_return_ids=[sales_return.id],
    )
    assert payload["DocDtls"]["Typ"] == "CRN"  # type: ignore[index]

    report = offline.import_result(
        json.dumps(
            [
                {
                    "DocDtls": {"No": "SR-1", "Typ": "CRN"},
                    "Irn": "b" * 64,
                    "AckNo": "112210000099999",
                    "AckDt": "2026-08-04 10:15:00",
                    "SignedQRCode": "eyJ.qr.sig",
                }
            ]
        ).encode(),
        file_format="json",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    assert report.registered == ["SR-1"]


def test_a_b2b_return_prints_only_with_its_irn() -> None:
    """The print gate covers it now that it can be registered."""
    from app.sales_return.services.credit_note_print_service import (
        CreditNotePrintService,
    )
    from tests.unit.test_invoice_print import _text_of

    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return(books)
    printer = CreditNotePrintService(books.session)

    with pytest.raises(BusinessRuleError, match="SR-1 has no IRN yet"):
        printer.render(sales_return.id, firm_scope=books.firm.id)
    pdf, _ = printer.render(
        sales_return.id, firm_scope=books.firm.id, reference_copy=True
    )
    assert "NOT A VALID TAX INVOICE" in _text_of(pdf)

    _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    pdf, _ = printer.render(sales_return.id, firm_scope=books.firm.id)
    text = _text_of(pdf)
    assert "NOT A VALID" not in text and "E-INVOICE" in text


def test_a_return_of_goods_never_invoiced_prints_as_before() -> None:
    """Nothing to register, so nothing is held."""
    from app.sales_return.services.credit_note_print_service import (
        CreditNotePrintService,
    )

    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    sales_return = _return(books, billed=False)
    pdf, _ = CreditNotePrintService(books.session).render(
        sales_return.id, firm_scope=books.firm.id
    )
    assert pdf


def test_a_completed_return_waits_in_the_list_until_registered() -> None:
    """Listed beside the invoices and notes; gone once it has an IRN."""
    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return(books)

    [item] = pending(books.session, books.firm.id)
    assert (item.document_type, item.number) == ("SALES_RETURN", "SR-1")

    _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert pending(books.session, books.firm.id) == []


def test_the_registration_list_names_the_return() -> None:
    """The register page says what each row is."""
    books = _Books(_session_factory()())
    sales_return = _return(books)
    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    labels = books.service().document_labels(firm_scope=books.firm.id, rows=[row])
    assert labels[row.id] == ("SALES_RETURN", "SR-1", "Kumar Stores")


def test_the_route_takes_sales_returns() -> None:
    """``/einvoice/sales-returns/{id}/register`` names the kind."""
    from app.einvoice.api.router import _note_kind

    assert _note_kind("sales-returns") == SALES_RETURN


def test_the_registration_answer_names_the_return() -> None:
    """The desktop acts on a row by the id the answer carries."""
    from app.einvoice.api.router import _labelled

    books = _Books(_session_factory()())
    sales_return = _return(books)
    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    answer = _labelled(books.session, row, firm_id=books.firm.id)
    assert answer.sales_return_id == sales_return.id
    assert answer.document_type == "SALES_RETURN"
