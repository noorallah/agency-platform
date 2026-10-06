"""A sales return's credit note is e-invoiced like any other (D-TAX-2)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
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
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import (
    SalesReturn,
    SalesReturnBillPlacement,
    SalesReturnLine,
)
from app.uom.models import Uom
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


def test_a_return_typed_in_another_unit_is_registered_as_its_note_states_it() -> None:
    """D-PRC-50: 24 PIECE of 2 BOX go to the portal as 24 at 8.333.

    The row stores the line in its source line's unit -- 2 at 100.00 -- and
    that is what was sent, beside a printed credit note that says 24 pieces.
    """
    books = _Books(_session_factory()())
    sales_return = _return(books)
    piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
    books.session.add(piece)
    books.session.flush()
    line = books.session.scalars(
        select(SalesReturnLine).where(
            SalesReturnLine.sales_return_id == sales_return.id
        )
    ).one()
    line.return_uom_id = piece.id
    line.entered_quantity = Decimal("24")
    line.conversion_factor = Decimal("0.0833333333")
    books.session.commit()

    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )

    item = row.request_payload["ItemList"][0]  # type: ignore[index]
    assert (item["Qty"], item["UnitPrice"]) == (24.0, 8.333)
    assert (item["TotAmt"], item["AssAmt"]) == (200.0, 200.0)


# ---- a return raised off the delivery note (D-PRC-89) ----------------------


def _second_bill(books: _Books) -> SalesInvoiceLine:
    """Raise SI-2, a second bill of the same goods, a day after SI-1."""
    invoice = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        invoice_number="SI-2",
        invoice_date=WHEN + timedelta(days=1),
        status="APPROVED",
        grand_total=Decimal("1180.00"),
    )
    books.session.add(invoice)
    books.session.flush()
    line = SalesInvoiceLine(
        sales_invoice_id=invoice.id,
        firm_id=books.firm.id,
        line_number=1,
        source_document_type="DELIVERY_NOTE",
        source_document_id=uuid4(),
        source_document_number="DN-1",
        source_document_line_id=uuid4(),
        source_document_line_number=1,
        product_id=books.product.id,
        delivered_quantity=Decimal("10"),
        current_invoice_quantity=Decimal("10"),
        unit_price=Decimal("100"),
        gross_amount=Decimal("1000"),
        tax_amount=Decimal("180"),
        net_amount=Decimal("1180"),
    )
    books.session.add(line)
    books.session.commit()
    return line


def _return_off_the_note(
    books: _Books,
    *,
    placed_on: list[tuple[SalesInvoiceLine, str]],
    unbilled: str = "0",
    status: str = "COMPLETED",
) -> SalesReturn:
    """Record 2 back off DN-1 for 236, set against these bill lines.

    Each bill line takes the units given, at 100 a unit plus 18% -- what
    completing the return writes to ``sales_return_bill_placements``.
    """
    row = SalesReturn(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch.id,
        warehouse_id=uuid4(),
        return_number="SR-9",
        return_date=WHEN,
        status=status,
        subtotal=Decimal("200"),
        tax_total=Decimal("36"),
        grand_total=Decimal("236"),
    )
    books.session.add(row)
    books.session.flush()
    line = SalesReturnLine(
        sales_return_id=row.id,
        firm_id=books.firm.id,
        line_number=1,
        source_document_type="DELIVERY_NOTE",
        source_document_id=uuid4(),
        source_document_number="DN-1",
        source_document_line_id=uuid4(),
        source_document_line_number=1,
        product_id=books.product.id,
        current_return_quantity=Decimal("2"),
        unbilled_quantity=Decimal(unbilled),
        tax_amount=Decimal("36"),
        net_amount=Decimal("236"),
    )
    books.session.add(line)
    books.session.flush()
    for bill_line, units in placed_on:
        books.session.add(
            SalesReturnBillPlacement(
                sales_return_id=row.id,
                sales_return_line_id=line.id,
                firm_id=books.firm.id,
                sales_invoice_id=bill_line.sales_invoice_id,
                sales_invoice_line_id=bill_line.id,
                quantity=Decimal(units),
                taxable_amount=Decimal(units) * Decimal("100"),
                net_amount=Decimal(units) * Decimal("118"),
            )
        )
    books.session.commit()
    return row


def test_a_return_off_the_note_registers_naming_the_bill_it_credits() -> None:
    """Refused before as crediting no tax invoice, while its print named one."""
    books = _Books(_session_factory()())
    sales_return = _return_off_the_note(books, placed_on=[(books.line, "2")])
    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    assert row.status == "REGISTERED" and row.sales_return_id == sales_return.id
    payload: Any = row.request_payload
    assert payload["DocDtls"]["Typ"] == "CRN" and payload["DocDtls"]["No"] == "SR-9"
    assert [each["InvNo"] for each in payload["RefDtls"]["PrecDocDtls"]] == ["SI-1"]
    assert payload["ValDtls"]["AssVal"] == 200.0
    assert payload["ValDtls"]["CgstVal"] + payload["ValDtls"]["SgstVal"] == 36.0
    assert payload["ItemList"][0]["HsnCd"] == "34011190"


def test_a_return_off_the_note_names_every_bill_it_was_set_against() -> None:
    """Billed in parts: one credit note, both invoices, earliest first."""
    books = _Books(_session_factory()())
    second = _second_bill(books)
    sales_return = _return_off_the_note(
        books, placed_on=[(second, "1"), (books.line, "1")]
    )
    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    payload: Any = row.request_payload
    assert [each["InvNo"] for each in payload["RefDtls"]["PrecDocDtls"]] == [
        "SI-1",
        "SI-2",
    ]
    # One line, as the credit note prints it, for the whole of what it credits.
    assert len(payload["ItemList"]) == 1
    assert payload["ValDtls"]["AssVal"] == 200.0
    assert payload["ValDtls"]["TotInvVal"] == 236.0


def test_only_the_billed_part_of_a_return_off_the_note_is_registered() -> None:
    """One of the two came back before any bill charged it: it credits nothing."""
    books = _Books(_session_factory()())
    sales_return = _return_off_the_note(
        books, placed_on=[(books.line, "1")], unbilled="1"
    )
    row = _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    payload: Any = row.request_payload
    assert payload["ItemList"][0]["Qty"] == 1.0
    assert payload["ValDtls"]["AssVal"] == 100.0
    assert payload["ValDtls"]["TotInvVal"] == 118.0


def test_a_return_off_the_note_prints_only_with_its_irn() -> None:
    """The print gate cannot be passed by the route the return was raised by."""
    from app.sales_return.services.credit_note_print_service import (
        CreditNotePrintService,
    )
    from tests.unit.test_invoice_print import _text_of

    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return_off_the_note(books, placed_on=[(books.line, "2")])
    printer = CreditNotePrintService(books.session)

    with pytest.raises(BusinessRuleError, match="SR-9 has no IRN yet"):
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
    assert "SI-1" in text


def test_a_return_off_the_note_waits_in_the_list_until_registered() -> None:
    """Listed like the return raised on the bill's own line."""
    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return_off_the_note(books, placed_on=[(books.line, "2")])

    [item] = pending(books.session, books.firm.id)
    assert (item.document_type, item.number) == ("SALES_RETURN", "SR-9")

    _service(books).register(
        SALES_RETURN, sales_return.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert pending(books.session, books.firm.id) == []


def test_a_return_off_a_note_no_bill_charged_stays_outside_e_invoicing() -> None:
    """Nothing was credited: not listed, not registered, printed as before."""
    from app.sales_return.services.credit_note_print_service import (
        CreditNotePrintService,
    )

    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return_off_the_note(books, placed_on=[], unbilled="2")

    assert pending(books.session, books.firm.id) == []
    with pytest.raises(ValidationError, match="no invoice billed"):
        _service(books).register(
            SALES_RETURN,
            sales_return.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )
    pdf, _ = CreditNotePrintService(books.session).render(
        sales_return.id, firm_scope=books.firm.id
    )
    assert pdf


def test_a_return_off_the_note_still_open_says_it_is_not_completed() -> None:
    """It is set against its bills at completion, so it names none before."""
    books = _Books(_session_factory()())
    _einvoicing_since(books, date(2020, 1, 1))
    books.register()
    sales_return = _return_off_the_note(books, placed_on=[], status="APPROVED")
    assert pending(books.session, books.firm.id) == []
    with pytest.raises(ValidationError, match="SR-9 is not completed"):
        _service(books).register(
            SALES_RETURN,
            sales_return.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )
