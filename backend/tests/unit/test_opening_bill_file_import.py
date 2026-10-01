"""Opening bills from a file, both sides of the books (D-GOLIVE-1).

Until 2026-10-01 a firm's opening bills went in one at a time on each party's
form, or as JSON no screen sent. These pin the file import: every problem by
row and column with nothing written, the form's own posting when it is clean,
and all or nothing.
"""

# ruff: noqa: D103

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.common.file_import import ImportReport
from app.customers.models import CustomerOpeningBill
from app.customers.services.opening_bill_import import (
    CustomerOpeningBillFileImporter,
)
from app.vendors.models import VendorOpeningBill
from app.vendors.services.opening_bill_import import VendorOpeningBillFileImporter
from tests.unit.test_customer_opening_bills import CUTOVER
from tests.unit.test_customer_opening_bills import _Books as _CustomerBooks
from tests.unit.test_vendor_opening_bills import _Books as _VendorBooks

pytestmark = pytest.mark.typed_document_numbers

_HEADINGS = ["PartyCode", "BillNumber", "BillDate", "DueDate", "Amount", "Narration"]


def _csv(*rows: list[str], headings: list[str] = _HEADINGS) -> bytes:
    """Write a CSV file with the given rows under the headings."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headings)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _customer_import(
    books: _CustomerBooks, content: bytes, *, apply: bool
) -> ImportReport[CustomerOpeningBill]:
    """Run the customer importer on a CSV at the cutover day."""
    return CustomerOpeningBillFileImporter(books.session).run(
        content,
        file_format="csv",
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        posting_date=CUTOVER,
        apply=apply,
    )


def _count(books: _CustomerBooks) -> int:
    """Count the customer opening bills in the store."""
    return int(
        books.session.scalar(select(func.count()).select_from(CustomerOpeningBill)) or 0
    )


def test_a_clean_file_posts_every_bill_the_way_the_form_does() -> None:
    books = _CustomerBooks()
    content = _csv(
        ["c1", "SI-101", "15-02-2026", "", "1,500.00", "old bill"],
        ["C2", "SI-7", "2026-03-31", "30/04/2026", "250", ""],
    )

    report = _customer_import(books, content, apply=True)

    assert report.issues == []
    assert report.imported is True
    bills = books.session.scalars(
        select(CustomerOpeningBill).order_by(CustomerOpeningBill.amount)
    ).all()
    assert [(bill.amount, bill.reference_number) for bill in bills] == [
        (Decimal("250.00"), "SI-7"),
        (Decimal("1500.00"), "SI-101"),
    ]
    assert all(bill.posting_date == CUTOVER for bill in bills)
    # No due date given: the bill date plus the customer's 30-day terms,
    # exactly as the form decides it.
    assert bills[1].due_date == date(2026, 3, 17)
    assert bills[0].due_date == date(2026, 4, 30)
    # Posted, so the customer's balance moved.
    assert books.balance() == Decimal("1500.00")


def test_a_check_reports_every_problem_by_row_and_writes_nothing() -> None:
    books = _CustomerBooks()
    content = _csv(
        ["NOPE", "A-1", "01-03-2026", "", "100", ""],
        ["C1", "A-2", "02-04-2026", "", "100", ""],
        ["C1", "A-3", "01-03-2026", "01-02-2026", "-5", ""],
        ["C1", "A-4", "not a day", "", "abc", ""],
        ["C2", "A-5", "01-03-2026", "", "100", ""],
        ["C2", "a-5", "01-03-2026", "", "100", ""],
    )

    report = _customer_import(books, content, apply=True)

    found = {(issue.row, issue.column) for issue in report.issues}
    assert (2, "PartyCode") in found  # unknown customer
    assert (3, "BillDate") in found  # after the cutover
    assert (4, "DueDate") in found and (4, "Amount") in found
    assert (5, "BillDate") in found and (5, "Amount") in found
    assert (7, "BillNumber") in found  # the same bill twice, ignoring case
    assert (6, "BillNumber") not in found
    assert report.imported is False
    assert _count(books) == 0


def test_a_clean_check_writes_nothing_either() -> None:
    books = _CustomerBooks()
    report = _customer_import(
        books, _csv(["C1", "B-1", "01-03-2026", "", "100", ""]), apply=False
    )
    assert report.issues == []
    assert report.imported is False
    assert report.to_create == 1
    assert _count(books) == 0


def test_a_customer_with_a_single_figure_is_refused_by_name() -> None:
    books = _CustomerBooks()
    books.customer.opening_balance = Decimal("900")
    books.session.commit()
    report = _customer_import(
        books, _csv(["C1", "B-1", "01-03-2026", "", "100", ""]), apply=True
    )
    [issue] = report.issues
    assert issue.column == "PartyCode"
    assert "opening balance of 900.00" in issue.message
    assert _count(books) == 0


def test_a_bill_already_recorded_refuses_the_whole_file() -> None:
    books = _CustomerBooks()
    books.opening_bill("400", reference="SI-9")
    before = _count(books)
    content = _csv(
        ["C2", "X-1", "01-03-2026", "", "100", ""],
        ["C1", "SI-9", "01-03-2026", "", "100", ""],
    )
    report = _customer_import(books, content, apply=True)
    assert [issue.row for issue in report.issues] == [3]
    assert "already recorded" in report.issues[0].message
    # All or nothing: row 2 was clean and is not left behind.
    assert _count(books) == before


def test_a_file_without_the_required_headings_is_refused() -> None:
    books = _CustomerBooks()
    report = _customer_import(
        books, _csv(["C1", "100"], headings=["PartyCode", "Amount"]), apply=True
    )
    [issue] = report.issues
    assert "BillDate" in issue.message


def test_common_export_headings_are_understood() -> None:
    books = _CustomerBooks()
    content = _csv(
        ["C1", "INV-1", "01-03-2026", "100"],
        headings=["Customer Code", "Invoice No", "Invoice Date", "Pending Amount"],
    )
    report = _customer_import(books, content, apply=True)
    assert report.issues == []
    assert report.imported is True


def test_the_template_names_the_firms_own_customer() -> None:
    books = _CustomerBooks()
    importer = CustomerOpeningBillFileImporter(books.session)
    lines = importer.template_csv(books.firm.id).splitlines()
    assert lines[0].split(",")[:3] == ["PartyCode", "BillNumber", "BillDate"]
    assert lines[1].startswith("C1,")
    assert importer.template_workbook(books.firm.id)[:2] == b"PK"


def test_supplier_bills_come_in_the_same_way() -> None:
    books = _VendorBooks()
    content = _csv(
        ["V1", "PB-1", "01-03-2026", "", "700", ""],
        ["V2", "PB-2", "15-03-2026", "", "300", ""],
        headings=["Supplier Code", "BillNumber", "BillDate", "DueDate", "Amount", "x"],
    )
    report = VendorOpeningBillFileImporter(books.session).run(
        content,
        file_format="csv",
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        posting_date=CUTOVER,
        apply=True,
    )
    assert report.issues == []
    assert report.imported is True
    amounts = sorted(books.session.scalars(select(VendorOpeningBill.amount)).all())
    assert amounts == [Decimal("300.00"), Decimal("700.00")]
