"""The 30-day limit and the list of what is still to be registered (77 row 7)."""

from datetime import date, timedelta

import pytest

from app.core.exceptions import ValidationError
from app.core.utils.dates import business_today
from app.einvoice.services.offline import OfflineEInvoiceService
from app.einvoice.services.reporting_window import (
    DUE_SOON,
    LATE,
    OPEN,
    REPORTING_DAYS,
    last_day,
    pending,
)
from tests.unit.test_einvoice import _Books, _note, _session_factory


def _settings(
    books: _Books, *, einvoice_from: date | None, thirty_from: date | None
) -> None:
    """Set the firm's GST document dates."""
    from app.tax.schemas.gst_compliance import GstComplianceSettingsWrite
    from app.tax.services.gst_compliance import GstComplianceService

    GstComplianceService(books.session).update_settings(
        GstComplianceSettingsWrite(
            einvoice_applicable_from=einvoice_from,
            thirty_day_rule_from=thirty_from,
            dispatch_without_invoice="WARN",
            route_sale_needs_invoice=False,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def _dated(books: _Books, days_ago: int) -> date:
    """Date the invoice ``days_ago`` days before today."""
    on = business_today("IN") - timedelta(days=days_ago)
    books.invoice.invoice_date = on
    books.session.commit()
    return on


def _bound(days_ago: int) -> _Books:
    """Return a firm bound by the limit, its invoice ``days_ago`` days old."""
    books = _Books(_session_factory()())
    _settings(books, einvoice_from=date(2020, 1, 1), thirty_from=date(2020, 1, 1))
    _dated(books, days_ago)
    return books


def test_a_document_on_its_last_day_is_still_registered() -> None:
    """Day 30 is inside the window; the portal counts from the document date."""
    books = _bound(REPORTING_DAYS)
    row = books.register()
    assert row.status == "REGISTERED"  # type: ignore[attr-defined]


def test_a_document_past_its_last_day_is_refused_naming_the_day() -> None:
    """Day 31 is refused before the portal is asked, with the way forward."""
    books = _bound(REPORTING_DAYS + 1)
    deadline = books.invoice.invoice_date + timedelta(days=REPORTING_DAYS)
    with pytest.raises(ValidationError, match=f"{deadline:%d %b %Y}") as refused:
        books.register()
    assert "raise it again" in refused.value.message
    assert (
        books.service().registration_for(books.invoice.id, firm_scope=books.firm.id)
        is None
    ), "nothing was sent, so nothing is recorded"


def test_the_limit_binds_only_from_the_firms_date() -> None:
    """No date, or a date still to come: an old document registers as before."""
    books = _Books(_session_factory()())
    _settings(
        books,
        einvoice_from=date(2020, 1, 1),
        thirty_from=business_today("IN") + timedelta(days=1),
    )
    _dated(books, 90)
    assert books.register().status == "REGISTERED"  # type: ignore[attr-defined]


def test_an_offline_export_of_a_late_document_is_refused() -> None:
    """The bulk upload would be refused by the portal too, so it is not built."""
    books = _bound(REPORTING_DAYS + 5)
    with pytest.raises(ValidationError, match="last day to register"):
        OfflineEInvoiceService(books.session).export(
            [books.invoice.id], firm_scope=books.firm.id, actor_id=books.actor_id
        )


@pytest.mark.parametrize("kind", ["CREDIT_NOTE", "DEBIT_NOTE"])
def test_a_late_note_is_refused_too(kind: str) -> None:
    """The advisory covers every document an IRN is issued for."""
    from app.einvoice.services.note_registration import NoteRegistrationService

    books = _bound(1)
    books.register()
    note = _note(books, kind)
    old = business_today("IN") - timedelta(days=REPORTING_DAYS + 2)
    if kind == "CREDIT_NOTE":
        note.credit_note_date = old  # type: ignore[attr-defined]
    else:
        note.debit_note_date = old  # type: ignore[attr-defined]
    books.session.commit()
    with pytest.raises(ValidationError, match="last day to register"):
        NoteRegistrationService(books.session, base=books.service()).register(
            kind, note.id, firm_scope=books.firm.id, actor_id=books.actor_id  # type: ignore[attr-defined]
        )


def test_the_list_shows_days_left_and_flags_what_is_close_or_late() -> None:
    """Oldest first; open, due soon and late by the days left."""
    books = _bound(2)
    today = business_today("IN")

    [item] = pending(books.session, books.firm.id)
    assert (item.number, item.state) == ("SI-1", OPEN)
    assert item.last_day == books.invoice.invoice_date + timedelta(days=30)
    assert item.days_left == REPORTING_DAYS - 2

    for days_ago, state in ((27, DUE_SOON), (31, LATE)):
        _dated(books, days_ago)
        [item] = pending(books.session, books.firm.id, today=today)
        assert item.state == state, days_ago


def test_a_registered_document_leaves_the_list_and_a_note_joins_it() -> None:
    """What has an IRN is done; a note against it is a document of its own."""
    books = _bound(1)
    books.register()
    assert pending(books.session, books.firm.id) == []

    _note(books, "CREDIT_NOTE")
    [item] = pending(books.session, books.firm.id)
    assert (item.document_type, item.number) == ("CREDIT_NOTE", "CN-1")


def test_the_list_holds_only_what_the_firm_must_register() -> None:
    """A consumer's bill, or a firm that does not e-invoice: nothing listed."""
    consumer = _Books(_session_factory()(), buyer_gstin=None)
    _settings(consumer, einvoice_from=date(2020, 1, 1), thirty_from=None)
    assert pending(consumer.session, consumer.firm.id) == []

    exempt = _Books(_session_factory()())
    assert pending(exempt.session, exempt.firm.id) == []


def test_without_the_limit_the_list_has_no_deadline() -> None:
    """A firm e-invoicing below 10 crore sees what is pending, with no clock."""
    books = _Books(_session_factory()())
    _settings(books, einvoice_from=date(2020, 1, 1), thirty_from=None)
    [item] = pending(books.session, books.firm.id)
    assert (item.last_day, item.days_left, item.state) == (None, None, OPEN)
    assert last_day(books.session, firm_scope=books.firm.id, on=item.on) is None


def test_a_refused_attempt_is_listed_with_the_portals_reason() -> None:
    """The person correcting it reads why beside it."""
    books = _bound(1)
    from app.einvoice.models import EInvoiceRegistration

    books.session.add(
        EInvoiceRegistration(
            firm_id=books.firm.id,
            sales_invoice_id=books.invoice.id,
            mode="SANDBOX",
            status="FAILED",
            error_message="Buyer GSTIN is not active",
        )
    )
    books.session.commit()
    [item] = pending(books.session, books.firm.id)
    assert item.registration_status == "FAILED"
    assert item.registration_error == "Buyer GSTIN is not active"


def test_the_route_answers_the_list() -> None:
    """The endpoint carries the flag, the warning days and the items."""
    from types import SimpleNamespace
    from typing import Any, cast

    from app.common.scope import ResolvedFirmScope
    from app.einvoice.api.router import pending_registrations

    books = _bound(28)
    scope = ResolvedFirmScope(
        principal=cast(Any, SimpleNamespace(subject=books.actor_id)),
        firm_id=books.firm.id,
    )
    answer = pending_registrations(scope, books.session).data
    assert answer is not None and answer.thirty_day_rule_applies
    assert answer.due_soon_days == 5
    [item] = answer.items
    assert (item.state, item.days_left, item.customer_name) == (
        "DUE_SOON",
        2,
        "Kumar Stores",
    )
