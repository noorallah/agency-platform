"""Quarterly GST filing, QRMP (GST-7, decision A83).

A firm in Maharashtra joins QRMP from July 2026. June stays monthly. July and
August are paid on PMT-06 -- the fixed sum from June's cash, or self-assessed
-- and the quarter's GSTR-3B, settled as September, uses those deposits before
the bank. GSTR-1 for the quarter is due on 13 October and 3B on the 22nd (the
24th in Delhi); a month's B2B invoices furnished on a filed IFF are not
repeated in the quarter's GSTR-1.
"""

# ruff: noqa: D103

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError as SchemaError

from app.core.exceptions import ValidationError
from app.gst_returns.models import GstReturnType
from app.gst_returns.services import gstr_service
from app.gst_returns.services.filing_frequency import (
    FilingFrequencyService,
    FilingPlan,
    quarter_months,
)
from app.gst_returns.services.gst_cash_deposits import GstCashDepositService
from app.gst_returns.services.gst_payment_service import GstPaymentService
from app.gst_returns.services.qrmp import QrmpReturnService
from app.gst_returns.services.tax_calendar import CalendarItem, TaxCalendarService
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from tests.unit.test_gst_payment import _account, _net
from tests.unit.test_settlements import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
#: IGST owed each month, with no credit: the cash every month needs.
MONTHLY_IGST = D("1000")


def _plan(state: str = "27", quarterly_from: date | None = None) -> FilingPlan:
    return FilingPlan(
        frequency="QUARTERLY",
        quarterly_from=quarterly_from,
        payment_method="FIXED_SUM",
        state_code=state,
    )


def _per_month(
    self: object, *, firm_scope: UUID, from_date: date, to_date: date
) -> dict[str, object]:
    """Fake GSTR-3B: 1,000 of IGST for every month the period covers."""
    months = (to_date.year - from_date.year) * 12 + to_date.month - from_date.month + 1
    return {
        "outward_taxable_supplies": {"integrated_tax": str(MONTHLY_IGST * months)},
        "net_itc": {},
    }


def _quarterly_books(
    monkeypatch: pytest.MonkeyPatch, *, method: str = "FIXED_SUM"
) -> _Books:
    """Build a Maharashtra firm filing quarterly from July 2026."""
    books = _Books(_session_factory()())
    books.firm.gst_number = "27AAPFU0939F1ZV"
    books.session.commit()
    monkeypatch.setattr(gstr_service.GstReturnService, "gstr3b", _per_month)
    GstComplianceService(books.session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=None,
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
            filing_frequency="QUARTERLY",
            quarterly_from=date(2026, 7, 1),
            qrmp_payment_method=method,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    return books


def _settle(books: _Books, period: str, paid_on: date) -> None:
    GstPaymentService(books.session).record(
        books.firm.id,
        period,
        payment_date=paid_on,
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
    )
    books.session.commit()


def _deposit(books: _Books, period: str, paid_on: date, igst: str) -> UUID:
    row = GstCashDepositService(books.session).record(
        books.firm.id,
        period,
        deposit_date=paid_on,
        money_account_id=_account(books, "1010"),
        amounts={"igst": D(igst)},
        actor_id=books.actor_id,
        challan_cpin="26080000000001",
    )
    books.session.commit()
    return row.id


# --- the plan ------------------------------------------------------------


def test_quarterly_due_dates_follow_the_state() -> None:
    plan = _plan("27")
    assert plan.gstr1_due("2026-09") == date(2026, 10, 13)
    assert plan.gstr3b_due("2026-09") == date(2026, 10, 22), "Maharashtra: X"
    assert _plan("07").gstr3b_due("2026-09") == date(2026, 10, 24), "Delhi: Y"
    assert plan.iff_due("2026-07") == date(2026, 8, 13)
    assert plan.pmt06_due("2026-08") == date(2026, 9, 25)
    assert plan.gstr3b_due("2026-12") == date(2027, 1, 22)


def test_months_before_the_first_quarterly_quarter_stay_monthly() -> None:
    plan = _plan(quarterly_from=date(2026, 7, 1))
    assert not plan.is_quarterly("2026-06")
    assert plan.return_period("2026-06") == "2026-06"
    assert plan.gstr1_due("2026-06") == date(2026, 7, 11)
    assert plan.gstr3b_due("2026-06") == date(2026, 7, 20)
    assert plan.is_quarterly("2026-08")
    assert plan.return_period("2026-08") == "2026-09"
    assert plan.span("2026-09") == (date(2026, 7, 1), date(2026, 9, 30))
    assert quarter_months("2027-02") == ("2027-01", "2027-02", "2027-03")


def test_a_quarter_starts_on_a_quarter_day_and_needs_quarterly_filing() -> None:
    base = {
        "einvoice_applicable_from": None,
        "thirty_day_rule_from": None,
        "dispatch_without_invoice": "WARN",
        "route_sale_needs_invoice": False,
    }
    with pytest.raises(SchemaError, match="first day of a quarter"):
        GstComplianceSettingsWrite(
            **base, filing_frequency="QUARTERLY", quarterly_from=date(2026, 8, 1)
        )
    with pytest.raises(SchemaError, match="needs quarterly filing"):
        GstComplianceSettingsWrite(
            **base, filing_frequency="MONTHLY", quarterly_from=date(2026, 7, 1)
        )


def test_going_back_to_monthly_clears_the_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    settings = GstComplianceService(books.session)
    assert settings.settings_response(books.firm.id).quarterly_from == date(2026, 7, 1)
    settings.update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=None,
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
            filing_frequency="MONTHLY",
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    after = settings.settings_response(books.firm.id)
    assert (after.filing_frequency, after.quarterly_from) == ("MONTHLY", None)
    assert after.qrmp_payment_method == "FIXED_SUM", "absent keeps the firm's own"


# --- paying a quarter ----------------------------------------------------


def test_the_quarter_uses_its_deposits_before_the_bank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    _settle(books, "2026-06", date(2026, 7, 20))
    deposits = GstCashDepositService(books.session)

    july = deposits.suggestion(books.firm.id, "2026-07")
    assert july.amounts["igst"] == D("1000.00"), "June was monthly: all its cash"
    assert july.due_date == date(2026, 8, 25)
    _deposit(books, "2026-07", date(2026, 8, 20), "1000")
    _deposit(books, "2026-08", date(2026, 9, 20), "1000")
    assert deposits.balance(books.firm.id)["igst"] == D("2000.00")

    preview = GstPaymentService(books.session).preview(
        books.firm.id, "2026-09", payment_date=date(2026, 10, 22)
    )
    assert preview.period_from == date(2026, 7, 1)
    assert preview.due_date == date(2026, 10, 22)
    assert preview.cash_total == D("3000.00")
    assert preview.from_deposits["igst"] == D("2000.00")
    assert preview.bank_total == D("1000.00")

    bank_before = _net(books, "1010")
    _settle(books, "2026-09", date(2026, 10, 22))
    assert _net(books, "1010") - bank_before == D("-1000.00")
    assert _net(books, "1340") == D("0.00"), "the cash ledger is used up"
    assert deposits.balance(books.firm.id)["igst"] == D("0.00")

    october = deposits.suggestion(books.firm.id, "2026-10")
    assert october.amounts["igst"] == D("1050.00"), "35% of the quarter's 3,000"


def test_self_assessment_deposits_the_quarter_so_far_less_the_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch, method="SELF_ASSESSMENT")
    deposits = GstCashDepositService(books.session)
    july = deposits.suggestion(books.firm.id, "2026-07")
    assert (july.method, july.amounts["igst"]) == ("SELF_ASSESSMENT", D("1000.00"))
    _deposit(books, "2026-07", date(2026, 8, 20), "1000")
    august = deposits.suggestion(books.firm.id, "2026-08")
    assert august.amounts["igst"] == D("1000.00"), "2,000 so far less 1,000 held"
    fixed = deposits.suggestion(books.firm.id, "2026-08", method="FIXED_SUM")
    assert fixed.amounts["igst"] == D("0.00"), "no June settlement to take 35% of"
    assert "No settlement of 2026-06" in fixed.basis


def test_what_is_paid_when_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    payments = GstPaymentService(books.session)
    with pytest.raises(ValidationError, match="settled as 2026-09"):
        payments.preview(books.firm.id, "2026-08")
    deposits = GstCashDepositService(books.session)
    with pytest.raises(ValidationError, match="last month of Jul-Sep 2026"):
        deposits.suggestion(books.firm.id, "2026-09")
    with pytest.raises(ValidationError, match="filed monthly"):
        deposits.suggestion(books.firm.id, "2026-06")
    with pytest.raises(ValidationError, match="once the month has begun"):
        _deposit(books, "2026-08", date(2026, 7, 31), "10")

    deposit_id = _deposit(books, "2026-07", date(2026, 8, 20), "500")
    _settle(books, "2026-09", date(2026, 10, 20))
    with pytest.raises(ValidationError, match="already settled"):
        _deposit(books, "2026-08", date(2026, 9, 20), "10")
    with pytest.raises(ValidationError, match="may have used this deposit"):
        deposits.reverse(
            deposit_id, firm_id=books.firm.id, actor_id=books.actor_id, reason="x"
        )

    settlement = payments.list_payments(books.firm.id)[0]
    payments.reverse(
        settlement.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="redo"
    )
    deposits.reverse(
        deposit_id, firm_id=books.firm.id, actor_id=books.actor_id, reason="typo"
    )
    books.session.commit()
    assert _net(books, "1340") == D("0.00")
    assert deposits.balance(books.firm.id)["igst"] == D("0.00")


# --- the calendar and the filings ----------------------------------------


def _by_key(items: list[CalendarItem]) -> dict[tuple[str, str], CalendarItem]:
    return {(item.kind, item.return_period): item for item in items}


def test_the_calendar_shows_iff_and_pmt06_then_the_quarter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    calendar = TaxCalendarService(books.session)
    monkeypatch.setattr(
        QrmpReturnService, "b2b_value", lambda self, firm_id, month: D("0")
    )
    _deposit(books, "2026-07", date(2026, 8, 20), "1000")

    months: Callable[..., list[str]] = lambda self, firm_id, today: [  # noqa: E731
        "2026-08",
        "2026-07",
        "2026-06",
    ]
    monkeypatch.setattr(TaxCalendarService, "_months", months)
    items = _by_key(calendar.calendar(books.firm.id, today=date(2026, 9, 5)))
    assert items[("IFF", "2026-08")].status == "OPTIONAL"
    assert ("IFF", "2026-07") not in items, "past the 13th the IFF is gone"
    assert items[("PMT06", "2026-08")].due_date == date(2026, 9, 25)
    assert items[("PMT06", "2026-08")].status == "DUE"
    assert items[("GSTR3B", "2026-06")].due_date == date(2026, 7, 20)
    assert ("PMT06", "2026-07") not in items, "done, and not the latest month"

    monkeypatch.setattr(
        TaxCalendarService,
        "_months",
        lambda self, firm_id, today: ["2026-09", "2026-08", "2026-07"],
    )
    items = _by_key(calendar.calendar(books.firm.id, today=date(2026, 10, 3)))
    quarter_1 = items[("GSTR1", "2026-09")]
    assert (quarter_1.due_date, quarter_1.period_from) == (
        date(2026, 10, 13),
        date(2026, 7, 1),
    )
    quarter_3b = items[("GSTR3B", "2026-09")]
    assert quarter_3b.due_date == date(2026, 10, 22)
    assert quarter_3b.amount == D("2000.00"), "3,000 less July's deposit"
    assert items[("PMT06", "2026-08")].status == "LATE"


def test_quarterly_filings_name_the_quarter_and_the_iff_months(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    calendar = TaxCalendarService(books.session)
    with pytest.raises(ValidationError, match="filed as 2026-09"):
        calendar.mark_filed(
            books.firm.id,
            return_type=GstReturnType.GSTR1,
            return_period="2026-08",
            filed_on=date(2026, 9, 10),
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="first two months"):
        calendar.mark_filed(
            books.firm.id,
            return_type=GstReturnType.IFF,
            return_period="2026-09",
            filed_on=date(2026, 10, 10),
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="first two months"):
        calendar.mark_filed(
            books.firm.id,
            return_type=GstReturnType.IFF,
            return_period="2026-06",
            filed_on=date(2026, 7, 10),
            actor_id=books.actor_id,
        )


def _invoice(number: str, on: str, value: float) -> dict[str, object]:
    return {"invoice_number": number, "invoice_date": on, "invoice_value": value}


def _fake_gstr1(
    self: object, *, firm_scope: UUID, from_date: date, to_date: date
) -> dict[str, object]:
    """Fake GSTR-1: one B2B invoice and one registered note a month."""
    rows = [
        ("2026-07-10", "INV-7", 6_000_000.0),
        ("2026-08-10", "INV-8", 100.0),
        ("2026-09-10", "INV-9", 100.0),
    ]
    kept = [row for row in rows if from_date.isoformat() <= row[0] <= str(to_date)]
    return {
        "gstin": "27AAPFU0939F1ZV",
        "b2b": [
            {
                "gstin": "29AAGCB7383J1Z4",
                "name": "Buyer",
                "invoices": [_invoice(n, on, v) for on, n, v in kept],
            }
        ],
        "cdnr": [{"note_number": f"CN-{n}", "note_date": on} for on, n, _ in kept],
        "unplaced_invoices": [],
    }


def test_the_quarter_leaves_out_what_a_filed_iff_furnished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    monkeypatch.setattr(gstr_service.GstReturnService, "gstr1", _fake_gstr1)
    qrmp = QrmpReturnService(books.session)

    july = qrmp.iff(books.firm.id, "2026-07")
    assert july["over_limit"] is True, "60 lakh is past the IFF's 50"
    assert july["due_date"] == "2026-08-13"
    with pytest.raises(ValidationError, match="first two months"):
        qrmp.iff(books.firm.id, "2026-09")

    TaxCalendarService(books.session).mark_filed(
        books.firm.id,
        return_type=GstReturnType.IFF,
        return_period="2026-08",
        filed_on=date(2026, 9, 12),
        actor_id=books.actor_id,
    )
    books.session.commit()
    quarter = qrmp.gstr1_quarter(books.firm.id, "2026-08")
    assert quarter["return_period"] == "2026-09"
    assert quarter["furnished_in_iff"] == ["2026-08"]
    numbers = [
        invoice["invoice_number"]
        for party in quarter["b2b"]  # type: ignore[attr-defined]
        for invoice in party["invoices"]
    ]
    assert numbers == ["INV-7", "INV-9"], "August went on its IFF"
    assert [note["note_number"] for note in quarter["cdnr"]] == [  # type: ignore[attr-defined]
        "CN-INV-7",
        "CN-INV-9",
    ]
    with pytest.raises(ValidationError, match="filed monthly"):
        qrmp.gstr1_quarter(books.firm.id, "2026-06")


def test_the_plan_reads_the_firms_gstin_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _quarterly_books(monkeypatch)
    plan = FilingFrequencyService(books.session).plan(books.firm.id)
    assert (plan.frequency, plan.state_code) == ("QUARTERLY", "27")
