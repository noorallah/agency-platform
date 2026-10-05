"""'Today' is the firm's calendar day, not the server's UTC one (D-CFG-25).

Driven 2026-10-06 between 00:09 and 00:50 India time, when the UTC day was
still the 5th: a supplier refund dated today was refused as future-dated and
one dated yesterday as before its return, an opening bill could not be dated
today, and the stock valuation read nothing for stock that came in that
night. The clock is still `utc_now()` and every timestamp is still UTC; what
changed is the day a **business date** is judged against.

Every case here freezes the clock at 19:30 UTC on the 5th, which is 01:00 on
the 6th in India.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.common.firm_metadata import firm_date_of, firm_today
from app.core.exceptions import ValidationError
from app.core.utils import dates
from app.core.utils.dates import business_date, business_today, business_zone
from app.customers.schemas.opening_bill import CustomerOpeningBillWrite
from app.firms.models import Firm
from app.inventory.api.router import stock_valuation
from app.inventory.services.opening_stock_import import OpeningStockFileImporter
from app.settlements.models import SettlementMethod
from app.settlements.services.supplier_credits import refund_supplier_credit
from app.vendors.schemas.opening_bill import VendorOpeningBillWrite
from tests.unit.test_customer_opening_bills import _Books as _CustomerBooks
from tests.unit.test_customer_opening_bills import _standing, _type_opening_balance
from tests.unit.test_opening_stock_import_file import _csv, _factory
from tests.unit.test_opening_stock_import_file import _firm as _stock_firm
from tests.unit.test_purchase_return_module import (
    _approved_return,
    _session_factory,
)
from tests.unit.test_purchase_return_module import _firm as _return_firm
from tests.unit.test_vendor_opening_bills import _Books as _VendorBooks

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: 19:30 UTC on the 5th: 01:00 on the 6th in India.
ONE_IN_THE_MORNING = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)
THE_5TH = date(2026, 10, 5)
THE_6TH = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def _one_in_the_morning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the clock the business day is read from."""
    monkeypatch.setattr(dates, "utc_now", lambda: ONE_IN_THE_MORNING)


def test_the_business_day_is_read_in_the_firms_zone() -> None:
    """India is on the 6th while UTC, and a country not listed, are on the 5th."""
    assert business_today("IN") == THE_6TH
    assert business_today("in ") == THE_6TH
    assert business_today(None) == THE_5TH
    assert business_today("ZZ") == THE_5TH
    # A stored instant, aware or read back naive from SQLite, lands the same.
    assert business_date(ONE_IN_THE_MORNING, "IN") == THE_6TH
    assert business_date(ONE_IN_THE_MORNING.replace(tzinfo=None), "IN") == THE_6TH
    # Half past five is where the two days meet again.
    assert business_date(datetime(2026, 10, 5, 18, 29, tzinfo=UTC), "IN") == THE_5TH
    assert business_date(datetime(2026, 10, 5, 18, 30, tzinfo=UTC), "IN") == THE_6TH


def test_a_machine_with_no_zone_database_still_knows_indias_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build without ``tzdata`` falls back on the fixed offset, not on UTC."""

    def missing(name: str) -> None:
        raise ZoneInfoNotFoundError(name)

    monkeypatch.setattr(dates, "ZoneInfo", missing)
    business_zone.cache_clear()
    try:
        zone = business_zone("IN")
        assert zone.utcoffset(None) == timedelta(hours=5, minutes=30)
        assert business_today("IN") == THE_6TH
    finally:
        business_zone.cache_clear()


def test_firm_today_follows_the_country_on_the_firm() -> None:
    """Read through the firm's metadata; no firm, or none known, is the UTC day."""
    session = _factory()()
    india = Firm(
        name="Kolkata Traders",
        code="KOL",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    elsewhere = Firm(
        name="Elsewhere",
        code="ELSE",
        country="ZZ",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add_all([india, elsewhere])
    session.flush()

    assert firm_today(session, india.id) == THE_6TH
    assert firm_today(session, elsewhere.id) == THE_5TH
    assert firm_today(session, uuid4()) == THE_5TH
    assert firm_today(session, None) == THE_5TH
    assert firm_date_of(session, india.id, ONE_IN_THE_MORNING) == THE_6TH
    assert firm_date_of(session, None, ONE_IN_THE_MORNING) == THE_5TH


def test_a_supplier_refund_dated_the_firms_today_is_not_future() -> None:
    """The refund the UTC day called future-dated; tomorrow still is."""
    session = _session_factory()()
    firm = _return_firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())
    row.outcome = "REFUND"
    session.commit()

    def refund(on: date) -> object:
        return refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("100"),
            refunded_on=on,
            method=SettlementMethod.BANK,
            actor_id=uuid4(),
        )

    with pytest.raises(ValidationError) as tomorrow:
        refund(THE_6TH + timedelta(days=1))
    assert tomorrow.value.message == "A refund cannot be received on a future date."
    session.rollback()

    assert refund(THE_6TH) is not None


def test_a_customers_opening_bill_can_be_dated_the_firms_today() -> None:
    """Dated today and posted today, where "today" had to be yesterday."""
    books = _CustomerBooks()

    row = books.bills.create(
        books.customer.id,
        CustomerOpeningBillWrite(bill_date=THE_6TH, amount=Decimal("100.00")),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    assert (row.bill_date, row.posting_date) == (THE_6TH, THE_6TH)
    with pytest.raises(ValidationError) as later:
        books.bills.create(
            books.customer.id,
            CustomerOpeningBillWrite(
                bill_date=THE_6TH + timedelta(days=1), amount=Decimal("100.00")
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    assert later.value.message == (
        "An opening bill is one raised before the books here start, so its "
        "date cannot be after 2026-10-06."
    )


def test_an_opening_balance_typed_after_midnight_is_dated_the_firms_today() -> None:
    """The figure's bill was dated, and fell due from, the day before."""
    books = _CustomerBooks()

    _type_opening_balance(books, "1500.00")

    [bill] = _standing(books)
    assert (bill.bill_date, bill.posting_date) == (THE_6TH, THE_6TH)
    assert bill.due_date == THE_6TH + timedelta(days=30)


def test_a_suppliers_opening_bill_can_be_dated_the_firms_today() -> None:
    """The payable twin."""
    books = _VendorBooks()

    row = books.bills.create(
        books.vendor.id,
        VendorOpeningBillWrite(bill_date=THE_6TH, amount=Decimal("100.00")),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    assert (row.bill_date, row.posting_date) == (THE_6TH, THE_6TH)


def test_the_stock_valuation_counts_what_came_in_since_midnight() -> None:
    """Asked with no date, and for today: it read 0.00 for stock on hand."""
    session = _factory()()
    firm = _stock_firm(session)
    report = OpeningStockFileImporter(session).run(
        _csv("ProductCode,Warehouse,Quantity,UnitCost", "RICE,MAIN,10,50"),
        file_format="csv",
        firm_id=firm.id,
        actor_id=uuid4(),
        posting_date=THE_6TH,
        apply=True,
    )
    assert report.imported, [issue.describe() for issue in report.issues]
    scope = SimpleNamespace(firm_id=firm.id)

    for asked in (None, THE_6TH, date(2099, 1, 1)):
        response = stock_valuation(
            scope=scope,  # type: ignore[arg-type]
            to_date=asked,
            from_date=None,
            warehouse_id=None,
            include_zero=False,
            page=1,
            page_size=100,
            db=session,
        )
        assert response.data[-3].product_name == "Grand total"
        assert response.data[-3].value == Decimal("500.00")
