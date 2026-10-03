"""What a period's documents would trip on, listed before filing (GST-5, A82).

Each check against a document built to trip it, and a clean period listing
nothing: the GSTIN's check character and state code, HSN missing or short for
the firm's turnover, IGST to a buyer with nowhere to place it, a document that
needed an IRN and has none, and a credit note past section 34(2) or against a
cancelled bill.
"""

# ruff: noqa: D103

from datetime import date
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.core.validation.common import gstin_check_character, gstin_problem
from app.gst_returns.api.router import filing_checks
from app.gst_returns.services.filing_checks import (
    GstFilingChecks,
    credit_note_deadline,
)
from app.sales_invoice.models import SalesInvoiceLine
from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
from app.tax.services.gst_compliance import GstComplianceService
from tests.unit.test_gst_returns import APRIL, _Books, _session_factory

SELLER = "29AABCU9603R1ZJ"
BUYER = "29AAACR5055K1Z3"


def _books() -> _Books:
    books = _Books(_session_factory()(), seller=SELLER)
    books.registered.gst_number = BUYER
    books.session.commit()
    return books


def _checks(books: _Books) -> list[tuple[str, str, str]]:
    rows = GstFilingChecks(books.session).rows(
        books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    return [(row.check, row.document_type, row.document_number) for row in rows]


def _einvoice_from(books: _Books, since: date) -> None:
    GstComplianceService(books.session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=since,
            thirty_day_rule_from=None,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
        ),
        firm_id=books.firm.id,
        actor_id=uuid4(),
    )


@pytest.mark.parametrize(
    ("gstin", "check"),
    [("27AAPFU0939F1ZV", "V"), ("29AAGCB7383J1Z4", "4"), (SELLER, "J")],
)
def test_the_check_character_is_gstns_mod_36(gstin: str, check: str) -> None:
    assert gstin_check_character(gstin) == check
    assert gstin_problem(gstin) is None


def test_a_gstin_with_a_wrong_check_or_state_is_named() -> None:
    assert "should end in V" in (gstin_problem("27AAPFU0939F1ZX") or "")
    assert "no state's code" in (gstin_problem("45AAPFU0939F1ZV") or "")
    assert "15 characters" in (gstin_problem("27AAPFU0939") or "")
    assert gstin_problem(None) is None


def test_a_clean_period_lists_nothing() -> None:
    books = _books()
    books.invoice("INV-1")
    books.invoice("INV-2", customer=books.walk_in)
    assert _checks(books) == []


def test_a_mistyped_gstin_is_listed_on_the_firm_and_each_bill() -> None:
    books = _books()
    books.firm.gst_number = "29AABCU9603R1ZM"
    books.registered.gst_number = "29AAACR5055K1Z5"
    books.session.commit()
    books.invoice("INV-1")
    assert _checks(books) == [
        ("GSTIN_INVALID", "FIRM", ""),
        ("GSTIN_INVALID", "SALES_INVOICE", "INV-1"),
    ]


def test_hsn_needs_four_digits_below_five_crore_and_six_above() -> None:
    books = _books()
    books.product.hsn_sac = "3306"
    books.session.commit()
    books.invoice("INV-1")
    assert _checks(books) == []

    _einvoice_from(books, date(2026, 4, 1))
    found = GstFilingChecks(books.session).rows(
        books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    assert [row.check for row in found] == ["HSN_SHORT", "IRN_MISSING"]
    assert "fewer than 6 digits" in found[0].message


def test_a_line_with_no_code_is_listed() -> None:
    books = _books()
    invoice = books.invoice("INV-1")
    line = (
        books.session.query(SalesInvoiceLine)
        .filter_by(sales_invoice_id=invoice.id)
        .one()
    )
    line.hsn_sac = None
    books.product.hsn_sac = None
    books.session.commit()
    found = GstFilingChecks(books.session).rows(
        books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    assert [(row.check, row.message) for row in found] == [
        ("HSN_MISSING", "Line 1: no HSN or SAC code.")
    ]


def test_igst_to_a_buyer_with_nowhere_to_place_it_is_listed() -> None:
    books = _books()
    books.invoice("INV-1", customer=books.walk_in, interstate=True)
    assert _checks(books) == [("PLACE_OF_SUPPLY_MISSING", "SALES_INVOICE", "INV-1")]


def test_a_bill_that_needed_an_irn_and_has_none_is_listed() -> None:
    books = _books()
    _einvoice_from(books, date(2026, 4, 5))
    books.invoice("INV-OLD", on=date(2026, 4, 2))
    books.invoice("INV-NEW", on=date(2026, 4, 10))
    books.invoice("INV-B2C", customer=books.walk_in, on=date(2026, 4, 10))
    assert [c for c in _checks(books) if c[0] == "IRN_MISSING"] == [
        ("IRN_MISSING", "SALES_INVOICE", "INV-NEW")
    ]


@pytest.mark.parametrize(
    ("supply", "deadline"),
    [
        (date(2025, 4, 1), date(2026, 11, 30)),
        (date(2026, 3, 31), date(2026, 11, 30)),
        (date(2026, 4, 1), date(2027, 11, 30)),
    ],
)
def test_section_34_2_runs_to_november_after_the_year(
    supply: date, deadline: date
) -> None:
    assert credit_note_deadline(supply) == deadline


def test_a_late_credit_note_and_one_on_a_cancelled_bill_are_listed() -> None:
    books = _books()
    old = books.invoice("INV-OLD", on=date(2025, 3, 10))
    books.credit("CN-LATE", old, on=date(2026, 4, 20))
    cancelled = books.invoice("INV-X", on=date(2026, 4, 2))
    books.credit("CN-X", cancelled)
    cancelled.status = "CANCELLED"
    books.session.commit()

    found = [c for c in _checks(books) if c[1] == "CREDIT_NOTE"]
    assert found == [
        ("CREDIT_NOTE_LATE", "CREDIT_NOTE", "CN-LATE"),
        ("CREDIT_NOTE_ON_CANCELLED_INVOICE", "CREDIT_NOTE", "CN-X"),
    ]


def test_the_route_counts_by_check_and_names_the_hsn_digits() -> None:
    books = _books()
    books.invoice("INV-1", customer=books.walk_in, interstate=True)
    scope = type("Scope", (), {"firm_id": books.firm.id})()
    response = filing_checks(scope, APRIL[0], APRIL[1], books.session)  # type: ignore[arg-type]
    assert response.data is not None
    assert response.data.counts == {"PLACE_OF_SUPPLY_MISSING": 1}
    assert response.data.required_hsn_digits == 4


def test_a_window_longer_than_a_quarter_is_refused() -> None:
    books = _books()
    with pytest.raises(ValidationError):
        GstFilingChecks(books.session).rows(
            books.firm.id, from_date=date(2026, 4, 1), to_date=date(2026, 8, 31)
        )
