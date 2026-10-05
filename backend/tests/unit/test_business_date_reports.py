"""Reports, as-of boundaries and "printed on" keep the firm's own day (D-CFG-25).

Three shapes of the same mistake, in the places the first two passes did not
reach:

* a report or list with no date defaulted to the UTC day;
* a boundary drawn round an as-of day **on a timestamp** -- "was it cancelled
  after the 5th" -- was drawn at UTC midnight, so a bill cancelled at 01:00 on
  the 6th in India (19:30 UTC on the 5th) read as cancelled *on* the 5th and
  dropped out of an ageing as on the 5th, when it was still owed that day;
* a document that says when it was made said yesterday.

Every case is for a firm whose country is ``IN``; where "now" matters the
clock is frozen at 19:30 UTC on the 5th, which is 01:00 on the 6th in India.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.common.firm_metadata import firm_day_after, firm_day_start
from app.core.utils import dates
from app.core.utils.dates import business_day_start
from app.counter_shifts.schemas import CounterShiftClose, CounterShiftOpen
from app.enquiry.api.router import follow_ups_due
from app.enquiry.services import EnquiryService, EnquiryWrite
from app.finance.models import JournalEntry
from app.firms.models import Firm
from app.firms.services.readiness import FirmReadinessService
from app.messaging.services.hand_documents import load_hand_document
from tests.unit.report_windows import report_scope
from tests.unit.test_counter_hold_and_shifts import _Counter
from tests.unit.test_customer_statement import _Books as _StatementBooks
from tests.unit.test_customer_statement import _session_factory as _statement_session
from tests.unit.test_firm_readiness import _ACTOR
from tests.unit.test_firm_readiness import _firm as _platform_firm
from tests.unit.test_firm_readiness import _session as _platform_session
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_messaging import _Shop as _MessagingShop
from tests.unit.test_quotation_module import _session_factory as _selling_session
from tests.unit.test_quotation_module import _Setup as _Selling

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: 19:30 UTC on the 5th: 01:00 on the 6th in India.
ONE_IN_THE_MORNING = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)
THE_5TH = date(2026, 10, 5)
THE_6TH = date(2026, 10, 6)


@pytest.fixture
def one_in_the_morning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the clock the business day is read from."""
    monkeypatch.setattr(dates, "utc_now", lambda: ONE_IN_THE_MORNING)


def test_a_firms_day_begins_at_its_own_midnight() -> None:
    """The 6th begins in India at 18:30 UTC on the 5th; elsewhere at 00:00 UTC."""
    assert business_day_start(THE_6TH, "IN") == datetime(
        2026, 10, 5, 18, 30, tzinfo=UTC
    )
    assert business_day_start(THE_6TH, None) == datetime(2026, 10, 6, tzinfo=UTC)
    assert business_day_start(THE_6TH, "ZZ") == datetime(2026, 10, 6, tzinfo=UTC)

    session = _statement_session()()
    india = Firm(
        name="Kolkata Traders",
        code="KOL",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(india)
    session.flush()
    assert firm_day_start(session, india.id, THE_6TH) == datetime(
        2026, 10, 5, 18, 30, tzinfo=UTC
    )
    # The first instant after the 5th is the instant the 6th begins.
    assert firm_day_after(session, india.id, THE_5TH) == firm_day_start(
        session, india.id, THE_6TH
    )
    assert firm_day_after(session, None, THE_5TH) == datetime(2026, 10, 6, tzinfo=UTC)


def test_a_bill_cancelled_after_midnight_was_still_owed_the_day_before() -> None:
    """Cancelled at 01:00 on the 6th: an ageing as on the 5th counts it.

    The boundary sat at UTC midnight, five and a half hours late, so the
    cancellation read as the 5th's and the bill left the 5th's ageing.
    """
    books = _StatementBooks(_statement_session()())
    bill = books.invoice("SI-1", "1000", on=date(2026, 10, 1), status="CANCELLED")
    bill.approved_at = datetime(2026, 10, 1, 9, tzinfo=UTC)
    bill.cancelled_at = ONE_IN_THE_MORNING
    books.session.commit()

    on_the_5th = books.ageing(as_of=THE_5TH)

    assert [
        (row.invoice_number, row.outstanding) for row in on_the_5th[0].invoices
    ] == [("SI-1", Decimal("1000.00"))]
    assert books.ageing(as_of=THE_6TH) == []


def test_shifts_are_listed_under_the_firms_day_they_opened_on() -> None:
    """Opened at 01:00 on the 6th: listed under the 6th, not the 5th."""
    counter = _Counter()
    shift = counter.shifts.open(
        CounterShiftOpen(opening_float=Decimal("500")),
        firm_id=counter.firm_id,
        actor_id=counter.cashier,
        now=ONE_IN_THE_MORNING,
    )

    def ids(day: date) -> list[UUID]:
        rows, _ = counter.shifts.list_shifts(
            counter.firm_id, page=1, page_size=10, from_date=day, to_date=day
        )
        return [row.id for row in rows]

    assert ids(THE_6TH) == [shift.id]
    assert ids(THE_5TH) == []


def test_a_shift_closed_after_midnight_books_its_difference_on_the_firms_day() -> None:
    """The cash short-and-over entry of a till closed at 01:00 is dated the 6th."""
    counter = _Counter()
    shift = counter.open("500")
    counter.sell(cash="100")
    closed = counter.shifts.close(
        shift.id,
        CounterShiftClose(counted_cash=Decimal("590"), note="Ten short"),
        firm_id=counter.firm_id,
        actor_id=counter.cashier,
        now=ONE_IN_THE_MORNING,
    )

    entry = counter.session.scalar(
        select(JournalEntry).where(
            JournalEntry.id == closed.difference_journal_entry_id
        )
    )
    assert entry is not None and entry.journal_date == THE_6TH


@pytest.mark.usefixtures("one_in_the_morning")
def test_the_shift_report_says_it_was_printed_on_the_firms_today() -> None:
    """Printed at 01:00 on the 6th, it said "printed 05-10-2026" (seen live)."""
    counter = _Counter()
    shift = counter.open("500")

    printed = _text_of(counter.shifts.report_pdf(shift.id, firm_id=counter.firm_id))

    assert "printed 06-10-2026" in printed


@pytest.mark.usefixtures("one_in_the_morning")
def test_follow_ups_due_with_no_date_are_the_firms_todays() -> None:
    """An enquiry to chase on the 6th is on the list at 01:00 on the 6th."""
    setup = _Selling(_selling_session()())
    row = EnquiryService(setup.session).create(
        EnquiryWrite.model_validate(
            {
                "enquiry_date": THE_5TH,
                "branch_id": setup.branch.id,
                "prospect_name": "Anand",
                "prospect_phone": "+919876543210",
                "source": "WALK_IN",
                "next_follow_up_on": THE_6TH,
                "lines": [
                    {
                        "product_id": setup.product.id,
                        "quantity": "4",
                        "expected_price": "100",
                    }
                ],
            }
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )

    listed = follow_ups_due(
        scope=report_scope(setup.firm.id), db=setup.session, page=1, page_size=10
    )

    assert [item.id for item in listed.data] == [row.id]


@pytest.mark.usefixtures("one_in_the_morning")
def test_a_statement_sent_by_hand_is_named_for_the_firms_today() -> None:
    """It is called Statement 06 Oct 2026, not the 5th."""
    shop = _MessagingShop()

    found = load_hand_document(
        shop.session,
        firm_id=shop.firm.id,
        document_type="CUSTOMER_STATEMENT",
        document_id=shop.customer.id,
    )

    assert found.document.document_number == "Statement 06 Oct 2026"


def test_books_opened_on_the_night_of_31_march_open_the_new_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """01:00 on 1 April in India: the year running now is the new one."""
    monkeypatch.setattr(
        dates, "utc_now", lambda: datetime(2027, 3, 31, 19, 30, tzinfo=UTC)
    )
    session = _platform_session()
    firm = _platform_firm(session, year_start=date(2019, 4, 1))

    _, starts_on = FirmReadinessService(session).open_books(firm, session, _ACTOR)

    assert starts_on == date(2027, 4, 1)
