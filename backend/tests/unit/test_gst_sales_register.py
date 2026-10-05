"""The GST sales register and the HSN summary of sales (§87 #1).

Both are GSTR-1's own figures laid out by document and by code, so the cases
that matter are the ones where a second reading could drift from the return:
a credit in minus on its own date, a debit note in plus, a bill cancelled
after its month was filed, and the totals against GSTR-1 for the same days.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.pagination.reports import ReportWindow
from app.customer_debit_note.models import CustomerDebitNote, CustomerDebitNoteLine
from app.gst_returns.services import GstReturnService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services.gst_sales_register import GstSalesRegisterService
from tests.unit.test_gst_returns import (
    APRIL,
    MAY,
    REGISTERED_BUYER,
    _Books,
    _cancel,
    _session_factory,
)

APRIL_WINDOW = ReportWindow(*APRIL)
MAY_WINDOW = ReportWindow(*MAY)


def _books() -> _Books:
    """Return a registered firm on a fresh in-memory store."""
    return _Books(_session_factory()())


def _debit(
    books: _Books,
    number: str,
    invoice: SalesInvoice,
    *,
    taxable: str = "50",
    tax: str = "9",
    on: date = date(2026, 4, 25),
) -> CustomerDebitNote:
    """Charge more against an invoice, approved."""
    line = books.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    ).first()
    assert line is not None
    note = CustomerDebitNote(
        firm_id=books.firm.id,
        customer_id=invoice.customer_id,
        branch_id=books.branch.id,
        sales_invoice_id=invoice.id,
        debit_note_number=number,
        debit_note_date=on,
        status="APPROVED",
        taxable_amount=Decimal(taxable),
        tax_amount=Decimal(tax),
        total_amount=Decimal(taxable) + Decimal(tax),
    )
    books.session.add(note)
    books.session.flush()
    books.session.add(
        CustomerDebitNoteLine(
            debit_note_id=note.id,
            firm_id=books.firm.id,
            line_number=1,
            sales_invoice_line_id=line.id,
            product_id=books.product.id,
            quantity=Decimal("0"),
            taxable_amount=Decimal(taxable),
            tax_rate_percent=Decimal("18"),
            tax_amount=Decimal(tax),
            total_amount=Decimal(taxable) + Decimal(tax),
        )
    )
    books.session.commit()
    return note


def _register(books: _Books, window: ReportWindow = APRIL_WINDOW) -> list[Any]:
    """Return the register for a window."""
    return GstSalesRegisterService(books.session).register(books.firm.id, window)


def test_a_bill_is_read_by_tax_head() -> None:
    """A bill within the state shows CGST and SGST; one across it, IGST."""
    books = _books()
    books.invoice("SI-1", gross="1000", tax="180", on=date(2026, 4, 10))
    books.invoice(
        "SI-2",
        customer=books.walk_in,
        gross="500",
        tax="90",
        interstate=True,
        on=date(2026, 4, 12),
    )

    across, within = _register(books)

    assert (within.document_number, within.document_type) == ("SI-1", "INVOICE")
    assert within.customer_gstin == REGISTERED_BUYER
    assert within.place_of_supply == "Karnataka (29)"
    assert (within.taxable_value, within.cgst, within.sgst, within.igst) == (
        Decimal("1000.00"),
        Decimal("90.00"),
        Decimal("90.00"),
        Decimal("0.00"),
    )
    assert (within.total_tax, within.document_total) == (
        Decimal("180.00"),
        Decimal("1180.00"),
    )
    assert across.customer_gstin is None
    assert (across.igst, across.cgst, across.total_tax) == (
        Decimal("90.00"),
        Decimal("0.00"),
        Decimal("90.00"),
    )


def test_a_draft_and_an_early_cancelled_bill_are_left_out() -> None:
    """A draft is not a supply; a bill cancelled before filing never was."""
    books = _books()
    books.invoice("SI-1")
    books.invoice("SI-2", status="DRAFT")
    cancelled = books.invoice("SI-3")
    _cancel(books, cancelled, on=date(2026, 4, 20))

    assert [row.document_number for row in _register(books)] == ["SI-1"]


def test_a_credit_note_and_a_return_are_in_minus_and_a_debit_note_in_plus() -> None:
    """Each is a row of its own, on its own date, naming its bill."""
    books = _books()
    invoice = books.invoice("SI-1", gross="1000", tax="180", on=date(2026, 4, 10))
    books.credit("CN-1", invoice, taxable="100", tax="18", on=date(2026, 4, 20))
    books.returned("SR-1", invoice, taxable="200", tax="36", on=date(2026, 4, 22))
    _debit(books, "DN-1", invoice, taxable="50", tax="9", on=date(2026, 4, 25))

    rows = {row.document_number: row for row in _register(books)}

    assert [row.document_number for row in _register(books)] == [
        "DN-1",
        "SR-1",
        "CN-1",
        "SI-1",
    ]
    assert (
        rows["CN-1"].document_type,
        rows["CN-1"].taxable_value,
        rows["CN-1"].cgst,
        rows["CN-1"].sgst,
        rows["CN-1"].document_total,
    ) == (
        "CREDIT_NOTE",
        Decimal("-100.00"),
        Decimal("-9.00"),
        Decimal("-9.00"),
        Decimal("-118.00"),
    )
    assert (rows["SR-1"].document_type, rows["SR-1"].taxable_value) == (
        "SALES_RETURN",
        Decimal("-200.00"),
    )
    assert rows["SR-1"].total_tax == Decimal("-36.00")
    assert (
        rows["DN-1"].document_type,
        rows["DN-1"].taxable_value,
        rows["DN-1"].total_tax,
        rows["DN-1"].document_total,
    ) == ("DEBIT_NOTE", Decimal("50.00"), Decimal("9.00"), Decimal("59.00"))
    assert {rows[number].against_invoice_number for number in ("CN-1", "SR-1")} == {
        "SI-1"
    }
    assert rows["DN-1"].against_invoice_number == "SI-1"


def test_only_an_approved_note_and_a_completed_return_count() -> None:
    """A draft note and a return not yet completed have given nothing back."""
    books = _books()
    invoice = books.invoice("SI-1")
    note = books.credit("CN-1", invoice)
    note.status = "DRAFT"
    books.returned("SR-1", invoice, status="APPROVED")
    books.session.commit()

    assert [row.document_number for row in _register(books)] == ["SI-1"]


def test_a_late_cancellation_stands_in_its_month_and_reverses_in_the_next() -> None:
    """April was due on 11 May; a cancellation on 20 May is May's (D-CMP-11)."""
    books = _books()
    invoice = books.invoice("SI-1", gross="1000", tax="180")
    _cancel(books, invoice, on=date(2026, 5, 20))

    april = _register(books)
    may = _register(books, MAY_WINDOW)
    both = _register(books, ReportWindow(APRIL[0], MAY[1]))

    assert [(row.document_type, row.taxable_value) for row in april] == [
        ("INVOICE", Decimal("1000.00"))
    ]
    assert [
        (row.document_type, row.document_date, row.taxable_value, row.total_tax)
        for row in may
    ] == [("CANCELLED_INVOICE", date(2026, 5, 20), Decimal("-1000.00"), -180)]
    assert may[0].against_invoice_number == "SI-1"
    assert [row.document_type for row in both] == ["CANCELLED_INVOICE", "INVOICE"]


def _seeded() -> _Books:
    """Return books holding a month of every kind of document."""
    books = _books()
    first = books.invoice("SI-1", gross="1000", tax="180", on=date(2026, 4, 5))
    second = books.invoice(
        "SI-2",
        customer=books.walk_in,
        gross="333.33",
        tax="60.01",
        interstate=True,
        on=date(2026, 4, 6),
    )
    books.invoice("SI-3", customer=books.walk_in, gross="250", tax="45", freight="20")
    books.credit("CN-1", first, taxable="33.33", tax="6.01")
    books.returned("SR-1", second, taxable="100", tax="18", interstate=True)
    _debit(books, "DN-1", first)
    march = books.invoice("SI-0", gross="400", tax="72", on=date(2026, 3, 10))
    _cancel(books, march, on=date(2026, 4, 28))
    return books


def test_the_totals_are_gstr1s_for_the_same_period() -> None:
    """The register and the HSN summary both add up to GSTR-1's Table 12."""
    books = _seeded()
    service = GstSalesRegisterService(books.session)
    gstr1 = GstReturnService(books.session).gstr1(
        firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    declared = gstr1["hsn"]
    assert isinstance(declared, list)
    fields = ("taxable_value", "integrated_tax", "central_tax", "state_tax")
    expected = [
        sum((Decimal(str(row[field])) for row in declared), Decimal("0"))
        for field in fields
    ]

    register = service.register(books.firm.id, APRIL_WINDOW)
    hsn = service.hsn_summary(books.firm.id, APRIL_WINDOW)

    for rows in (register, hsn):
        assert [
            sum((getattr(row, name) for row in rows), Decimal("0"))
            for name in ("taxable_value", "igst", "cgst", "sgst")
        ] == expected
    assert {row.document_type for row in register} == {
        "INVOICE",
        "CREDIT_NOTE",
        "DEBIT_NOTE",
        "SALES_RETURN",
        "CANCELLED_INVOICE",
    }
    assert [(row.hsn_code, row.rate) for row in hsn] == [
        (str(row["hsn"]), Decimal(str(row["rate"]))) for row in declared
    ]


def test_the_hsn_summary_is_net_of_credits() -> None:
    """Quantity and value come off the code the bill was folded under."""
    books = _books()
    invoice = books.invoice("SI-1", gross="1000", tax="180")
    books.returned("SR-1", invoice, taxable="100", tax="18")

    (row,) = GstSalesRegisterService(books.session).hsn_summary(
        books.firm.id, APRIL_WINDOW
    )

    assert (row.hsn_code, row.rate) == ("33061020", Decimal("18"))
    assert (row.quantity, row.taxable_value, row.total_tax) == (
        Decimal("9"),
        Decimal("900"),
        Decimal("162"),
    )


def test_every_kind_is_paged_together() -> None:
    """A page is a page of the register, counted across every kind."""
    books = _seeded()
    service = GstSalesRegisterService(books.session)
    whole = [row.document_number for row in service.register(books.firm.id)]

    pages = [
        service.register(books.firm.id, ReportWindow(page=page, page_size=3))
        for page in (1, 2, 3)
    ]

    assert {getattr(page, "total_records", None) for page in pages} == {len(whole)}
    assert [row.document_number for page in pages for row in page] == whole


def test_the_routes_take_a_window_and_a_page() -> None:
    """Both reports read the document's own date and count matches."""
    from app.sales_invoice.api.router import (
        gst_sales_register,
        hsn_sales_summary,
        router,
    )
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

    books = _books()
    days = [date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 4)]
    for index, day in enumerate(days):
        books.invoice(f"SI-{index}", on=day)
    scope = report_scope(books.firm.id)

    page = gst_sales_register(
        scope=scope,
        db=books.session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=1,
    )
    hsn = hsn_sales_summary(
        scope=scope,
        db=books.session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=50,
    )

    assert page.pagination.total_records == 2
    assert [row.document_date for row in page.data] == [days[2]]
    assert [row.document_type_label for row in page.data] == ["Invoice"]
    assert [row.taxable_value for row in hsn.data] == [Decimal("2000")]
    for path in ("gst-register", "hsn-summary"):
        assert_page_size_is_bounded(router, f"/api/v1/sales-invoices/reports/{path}")


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _statements(bills: int) -> tuple[int, int]:
    """Return the statements each report reads over ``bills`` bills."""
    books = _books()
    for index in range(bills):
        invoice = books.invoice(f"SI-{index:03d}")
        books.credit(f"CN-{index:03d}", invoice)
        books.returned(f"SR-{index:03d}", invoice)
        _debit(books, f"DN-{index:03d}", invoice)
    late = books.invoice("SI-LATE", on=date(2026, 3, 10))
    _cancel(books, late, on=date(2026, 4, 28))
    books.session.expire_all()
    service = GstSalesRegisterService(books.session)
    firm_id = books.firm.id
    with _counting(books.session) as register:
        service.register(firm_id, APRIL_WINDOW)
    with _counting(books.session) as hsn:
        service.hsn_summary(firm_id, APRIL_WINDOW)
    return len(register), len(hsn)


def test_the_statements_do_not_grow_with_the_documents() -> None:
    """Two bills with their notes and twelve cost the same statements."""
    assert _statements(2) == _statements(12)


def test_the_place_of_supply_reads_one_way_on_every_row() -> None:
    """D-SELL-61: "Tamil Nadu (33)" on the bill, "33" on its notes, blank.

    Driven 2026-10-05: the bill's row named the state with its code, the
    credit note, debit note and return of the same bill a bare code, and an
    unregistered buyer's bill nothing -- though GSTR-1 placed it in the
    seller's state by the CGST and SGST it charged. One form, on every row.
    """
    books = _books()
    invoice = books.invoice("SI-1", gross="1000", tax="180", on=date(2026, 4, 10))
    books.credit("CN-1", invoice, taxable="100", tax="18", on=date(2026, 4, 20))
    books.returned("SR-1", invoice, taxable="200", tax="36", on=date(2026, 4, 22))
    _debit(books, "DN-1", invoice, taxable="50", tax="9", on=date(2026, 4, 25))
    # A buyer with no GSTIN, taxed CGST + SGST: the seller's own state.
    books.invoice(
        "SI-2", customer=books.walk_in, gross="500", tax="90", on=date(2026, 4, 26)
    )

    rows = {row.document_number: row for row in _register(books)}

    assert {number: row.place_of_supply for number, row in rows.items()} == {
        "SI-1": "Karnataka (29)",
        "CN-1": "Karnataka (29)",
        "SR-1": "Karnataka (29)",
        "DN-1": "Karnataka (29)",
        "SI-2": "Karnataka (29)",
    }
