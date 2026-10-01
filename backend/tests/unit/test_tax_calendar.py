"""The tax calendar on Home: due, late and done, with amounts (backlog 63.4).

A firm whose first bill is dated 2 August, looked at on 2 October: August's
GSTR-1 (due 11 September) and GSTR-3B (due the 20th) are late, September's
are due. Saying GSTR-1 was filed, or recording the month's GST payment, closes
a return; a closed month drops off unless it is the latest one, and a filing
recorded in error can be withdrawn.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.finance.models import LedgerAccount
from app.gst_returns.models import GstReturnType
from app.gst_returns.services.gst_payment_service import GstPaymentService
from app.gst_returns.services.tax_calendar import CalendarItem, TaxCalendarService
from tests.unit.test_output_tax_by_head import _reverse_charge_bill

pytestmark = pytest.mark.typed_document_numbers

OCTOBER_2 = date(2026, 10, 2)


def _by_key(items: list[CalendarItem]) -> dict[tuple[str, str], CalendarItem]:
    """Index the calendar by (kind, month)."""
    return {(item.kind, item.return_period): item for item in items}


def _firm() -> tuple[TaxCalendarService, Session, UUID, UUID]:
    """Approve the reverse-charge bill of 2 August: 72 owed in cash."""
    session, service, firm_id, bill_id, actor_id = _reverse_charge_bill()
    service.approve_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()
    return TaxCalendarService(session), session, firm_id, actor_id


def test_last_months_returns_are_late_and_this_months_are_due() -> None:
    """August is past its due dates; September is not due yet."""
    calendar, _, firm_id, _ = _firm()
    items = _by_key(calendar.calendar(firm_id, today=OCTOBER_2))

    assert set(items) == {
        ("GSTR1", "2026-09"),
        ("GSTR3B", "2026-09"),
        ("GSTR1", "2026-08"),
        ("GSTR3B", "2026-08"),
    }, "nothing before the month the firm started trading"
    august_1 = items[("GSTR1", "2026-08")]
    assert (august_1.due_date, august_1.status, august_1.days_late) == (
        date(2026, 9, 11),
        "LATE",
        21,
    )
    august_3b = items[("GSTR3B", "2026-08")]
    assert (august_3b.status, august_3b.days_late) == ("LATE", 12)
    assert august_3b.amount == Decimal("72.00"), "reverse charge is paid in cash"
    september_3b = items[("GSTR3B", "2026-09")]
    assert (september_3b.due_date, september_3b.status) == (date(2026, 10, 20), "DUE")
    assert september_3b.amount == Decimal("0.00")


def test_filing_and_paying_close_a_month() -> None:
    """A filed GSTR-1 and a recorded payment close August; withdrawing reopens."""
    calendar, session, firm_id, actor_id = _firm()
    filed = calendar.mark_filed(
        firm_id,
        return_type=GstReturnType.GSTR1,
        return_period="2026-08",
        filed_on=date(2026, 9, 10),
        arn=" aa3308260012345 ",
        actor_id=actor_id,
    )
    session.commit()
    assert filed.arn == "AA3308260012345"
    bank = session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == firm_id, LedgerAccount.code == "1010"
        )
    )
    GstPaymentService(session).record(
        firm_id,
        "2026-08",
        payment_date=date(2026, 9, 25),
        money_account_id=bank,
        actor_id=actor_id,
        challan_cpin="26093300012345",
    )
    session.commit()

    items = _by_key(calendar.calendar(firm_id, today=OCTOBER_2))
    assert ("GSTR1", "2026-08") not in items, "a closed month that is not the latest"
    assert ("GSTR3B", "2026-08") not in items
    assert items[("GSTR1", "2026-09")].status == "DUE"

    september = calendar.mark_filed(
        firm_id,
        return_type=GstReturnType.GSTR1,
        return_period="2026-09",
        filed_on=date(2026, 10, 1),
        actor_id=actor_id,
    )
    session.commit()
    done = _by_key(calendar.calendar(firm_id, today=OCTOBER_2))[("GSTR1", "2026-09")]
    assert (done.status, done.done_on, done.filing_id) == (
        "DONE",
        date(2026, 10, 1),
        september.id,
    ), "the latest month's closed returns stay, ticked"

    calendar.withdraw(september.id, firm_id=firm_id, actor_id=actor_id)
    session.commit()
    again = _by_key(calendar.calendar(firm_id, today=OCTOBER_2))
    assert again[("GSTR1", "2026-09")].status == "DUE"


def test_a_filing_is_dated_after_its_month_and_recorded_once() -> None:
    """Filed before the month ended is refused, and so is a second filing."""
    calendar, session, firm_id, actor_id = _firm()
    with pytest.raises(ValidationError, match="after the month ends"):
        calendar.mark_filed(
            firm_id,
            return_type=GstReturnType.GSTR3B,
            return_period="2026-08",
            filed_on=date(2026, 8, 31),
            actor_id=actor_id,
        )
    calendar.mark_filed(
        firm_id,
        return_type=GstReturnType.GSTR3B,
        return_period="2026-08",
        filed_on=date(2026, 9, 1),
        actor_id=actor_id,
    )
    session.commit()
    with pytest.raises(ConflictError, match="already recorded"):
        calendar.mark_filed(
            firm_id,
            return_type=GstReturnType.GSTR3B,
            return_period="2026-08",
            filed_on=date(2026, 9, 2),
            actor_id=actor_id,
        )


def test_a_firm_that_has_not_traded_owes_nothing() -> None:
    """No sale and no bill: nothing to file."""
    calendar, _, _, _ = _firm()
    assert calendar.calendar(uuid4(), today=OCTOBER_2) == []
