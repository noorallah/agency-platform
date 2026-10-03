"""Rule 42: common credit given back for exempt supplies (GST-4, decision A84).

A firm sells half exempt in April 2026 and nothing exempt for the rest of the
year, claiming 1,000 of IGST credit every month. April gives back
1,000 x 50,000 / 100,000 = 500. Worked out on the whole year the exempt share
is far smaller, so the true-up claims most of it back. A posted reversal is
4(B)(1) in GSTR-3B; the true-up's reclaim is 4(A)(5).
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.finance.models import AccountingPeriod, FinancialYear, PeriodStatus
from app.gst_returns.services import gstr_service
from app.gst_returns.services.rule42 import Rule42Service, financial_year_bounds
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from tests.unit.test_gst_payment import _net
from tests.unit.test_settlements import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

D = Decimal


def _summary(
    self: object, *, firm_scope: UUID, from_date: date, to_date: date
) -> dict[str, object]:
    """Fake GSTR-3B, one month at a time: April half exempt, then none."""
    april = from_date.month == 4
    return {
        "outward_taxable_supplies": {
            "taxable_value": "50000" if april else "200000",
            "integrated_tax": "0",
        },
        "zero_rated_supplies": {"taxable_value": "0"},
        "nil_rated_and_exempt_supplies": {"taxable_value": "50000" if april else "0"},
        "non_gst_supplies": {"taxable_value": "0"},
        "eligible_itc": {"integrated_tax": "1000"},
        "itc_reverse_charge": {},
        "itc_reversed_blocked": {},
        "itc_reversed": {},
        "itc_reversed_rule37": {},
        "itc_reclaimed": {},
        "net_itc": {"integrated_tax": "1000"},
    }


def _books(monkeypatch: pytest.MonkeyPatch, mode: str = "POST") -> _Books:
    """Build a firm that chose rule 42 ``mode``, with the fake 3B."""
    books = _Books(_session_factory()())
    monkeypatch.setattr(gstr_service.GstReturnService, "gstr3b", _summary)
    GstComplianceService(books.session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=None,
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
            rule42_mode=mode,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    return books


def test_a_period_gives_back_the_exempt_share_of_common_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books(monkeypatch)
    figures = Rule42Service(books.session).period(books.firm.id, "2026-04")
    assert (figures.exempt_turnover, figures.total_turnover) == (
        D("50000.00"),
        D("100000.00"),
    )
    assert figures.share == D("0.5")
    assert figures.common["igst"] == D("1000.00")
    assert figures.reversal["igst"] == D("500.00")
    may = Rule42Service(books.session).period(books.firm.id, "2026-05")
    assert may.reversal["igst"] == D("0.00"), "no exempt sales, nothing back"


def test_posting_moves_the_credit_and_3b_reports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books(monkeypatch)
    service = Rule42Service(books.session)
    row = service.post_period(
        books.firm.id, "2026-04", posting_date=None, actor_id=books.actor_id
    )
    books.session.commit()
    assert row.movement_date == date(2026, 4, 30), "the period's last day"
    assert row.reversed_igst == D("500.00")
    assert _net(books, "1310") == D("-500.00"), "Input IGST credited"

    table4 = gstr_service.GstReturnService(books.session)._input_tax_credit(
        firm_scope=books.firm.id, from_date=date(2026, 4, 1), to_date=date(2026, 4, 30)
    )
    assert table4["itc_reversed_rule42"]["integrated_tax"] == 500.0  # type: ignore[index]
    assert table4["net_itc"]["integrated_tax"] == -500.0  # type: ignore[index]

    with pytest.raises(ValidationError, match="already posted"):
        service.post_period(
            books.firm.id, "2026-04", posting_date=None, actor_id=books.actor_id
        )
    with pytest.raises(ValidationError, match="gives nothing back"):
        service.post_period(
            books.firm.id, "2026-05", posting_date=None, actor_id=books.actor_id
        )
    with pytest.raises(ValidationError, match="inside the period"):
        service.post_period(
            books.firm.id,
            "2026-06",
            posting_date=date(2026, 7, 1),
            actor_id=books.actor_id,
        )


def test_the_year_end_true_up_claims_back_the_excess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _books(monkeypatch)
    service = Rule42Service(books.session)
    april = service.post_period(
        books.firm.id, "2026-04", posting_date=None, actor_id=books.actor_id
    )
    books.session.commit()

    year = service.annual(books.firm.id, "2026-27")
    # E 50,000; F 100,000 + 11 x 200,000; C2 12 x 1,000.
    assert year.figures.total_turnover == D("2300000.00")
    assert year.figures.reversal["igst"] == D("260.87")
    assert year.already["igst"] == D("500.00")
    assert year.difference["igst"] == D("-239.13")

    with pytest.raises(ValidationError, match="after the year ends"):
        service.post_annual(
            books.firm.id,
            "2026-27",
            posting_date=date(2027, 3, 31),
            actor_id=books.actor_id,
        )
    _open_next_year(books)
    true_up = service.post_annual(
        books.firm.id,
        "2026-27",
        posting_date=date(2027, 9, 30),
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert true_up.reversed_igst == D("-239.13")
    assert _net(books, "1310") == D("-260.87"), "what the year should give back"

    reported = gstr_service.GstReturnService(books.session)._input_tax_credit(
        firm_scope=books.firm.id, from_date=date(2027, 9, 1), to_date=date(2027, 9, 30)
    )
    assert reported["itc_reclaimed_rule42"]["integrated_tax"] == 239.13  # type: ignore[index]

    with pytest.raises(ValidationError, match="Take back the true-up first"):
        service.reverse(
            april.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="x"
        )
    service.reverse(
        true_up.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="redo"
    )
    service.reverse(
        april.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="redo"
    )
    books.session.commit()
    assert _net(books, "1310") == D("0.00")


def _open_next_year(books: _Books) -> None:
    """Open 2027-28 with one period covering it, for the true-up's date."""
    year = FinancialYear(
        firm_id=books.firm.id,
        code="FY2027",
        name="2027-28",
        starts_on=date(2027, 4, 1),
        ends_on=date(2028, 3, 31),
    )
    books.session.add(year)
    books.session.flush()
    books.session.add(
        AccountingPeriod(
            firm_id=books.firm.id,
            financial_year_id=year.id,
            period_number=1,
            code="Y2",
            name="2027-28",
            starts_on=date(2027, 4, 1),
            ends_on=date(2028, 3, 31),
            status=PeriodStatus.OPEN.value,
        )
    )
    books.session.commit()


def test_a_firm_that_reports_cannot_post(monkeypatch: pytest.MonkeyPatch) -> None:
    books = _books(monkeypatch, mode="REPORT")
    service = Rule42Service(books.session)
    assert service.period(books.firm.id, "2026-04").reversal["igst"] == D("500.00")
    with pytest.raises(ValidationError, match="reported, not posted"):
        service.post_period(
            books.firm.id, "2026-04", posting_date=None, actor_id=books.actor_id
        )


def test_a_financial_year_is_named_by_its_two_years() -> None:
    assert financial_year_bounds("2026-27") == (date(2026, 4, 1), date(2027, 3, 31))
    with pytest.raises(ValidationError, match="named like 2026-27"):
        financial_year_bounds("2026-28")
