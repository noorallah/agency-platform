"""Enquiries and leads before the quotation (SEL-10, decision A133).

A prospect asks for four of a product. The enquiry is followed up, appears
on the follow-ups due, and converts: the prospect becomes a customer and a
quotation is raised from its lines in one commit. When that quotation
becomes an order the enquiry is won. Another is lost on price, which the
lost report counts.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError

from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.enquiry.api.router import follow_ups_due, list_enquiries
from app.enquiry.api.router import router as enquiry_router
from app.enquiry.services import (
    EnquiryConvertWrite,
    EnquiryFollowUpWrite,
    EnquiryLostWrite,
    EnquiryService,
    EnquiryWrite,
)
from app.quotation.models import SalesQuotation
from tests.unit.report_windows import assert_page_size_is_bounded, report_scope
from tests.unit.test_quotation_module import _session_factory, _Setup

TODAY = utc_now().date()


def _enquiry(setup: _Setup, **extra: object) -> EnquiryWrite:
    return EnquiryWrite.model_validate(
        {
            "enquiry_date": TODAY,
            "branch_id": setup.branch.id,
            "prospect_name": "Anand",
            "prospect_company": "Anand Traders",
            "prospect_phone": "+919876543210",
            "source": "WALK_IN",
            "expected_value": "400",
            "next_follow_up_on": TODAY,
            "lines": [
                {
                    "product_id": setup.product.id,
                    "quantity": "4",
                    "expected_price": "100",
                }
            ],
            **extra,
        }
    )


def test_an_enquiry_is_followed_up_and_converted_to_a_quotation() -> None:
    setup = _Setup(_session_factory()())
    service = EnquiryService(setup.session)
    row = service.create(
        _enquiry(setup), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    assert row.enquiry_number.startswith("ENQ")
    due = service.list_rows(setup.firm.id, due_on=TODAY)
    assert [item.id for item in due] == [row.id]

    service.follow_up(
        row.id,
        EnquiryFollowUpWrite(
            followed_on=TODAY,
            note="Wants a price for 4",
            next_follow_up_on=TODAY + timedelta(days=3),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert service.list_rows(setup.firm.id, due_on=TODAY) == []

    service.convert(
        row.id,
        EnquiryConvertWrite(
            warehouse_id=setup.warehouse.id,
            quotation_date=TODAY,
            valid_until=TODAY + timedelta(days=30),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert row.status == "QUOTED"
    customer = setup.session.get(Customer, row.customer_id)
    assert customer is not None and customer.name == "Anand Traders"
    quotation = setup.session.get(SalesQuotation, row.quotation_id)
    assert quotation is not None and quotation.customer_id == customer.id
    assert quotation.customer_reference == row.enquiry_number
    (view,) = service.responses([row])
    assert view.follow_ups[0].note == "Wants a price for 4"

    quotes = setup.service
    quotes.send_quotation(
        quotation.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    quotes.accept_quotation(
        quotation.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    quotes.convert_quotation(
        quotation.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    setup.session.refresh(row)
    assert row.status == "WON"


def test_a_lost_enquiry_is_counted_by_its_reason() -> None:
    setup = _Setup(_session_factory()())
    service = EnquiryService(setup.session)
    row = service.create(
        _enquiry(setup), firm_id=setup.firm.id, actor_id=setup.actor_id
    )
    service.mark_lost(
        row.id,
        EnquiryLostWrite(reason="PRICE", remarks="Competitor 8% cheaper"),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    (report,) = service.lost_reasons(setup.firm.id, from_date=TODAY, to_date=TODAY)
    assert (report.reason, report.count, report.expected_value) == (
        "PRICE",
        1,
        Decimal("400.00"),
    )
    with pytest.raises(ValidationError, match="already closed"):
        service.mark_lost(
            row.id,
            EnquiryLostWrite(reason="OTHER"),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_line_without_a_product_must_be_matched_before_quoting() -> None:
    setup = _Setup(_session_factory()())
    service = EnquiryService(setup.session)
    row = service.create(
        _enquiry(
            setup,
            lines=[{"description": "Blue paint, 20 litres", "quantity": "2"}],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    with pytest.raises(ValidationError, match="Match line 1"):
        service.convert(
            row.id,
            EnquiryConvertWrite(
                warehouse_id=setup.warehouse.id,
                quotation_date=TODAY,
                valid_until=TODAY + timedelta(days=30),
            ),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_someone_has_to_have_asked() -> None:
    with pytest.raises(SchemaError, match="Name the customer or the prospect"):
        EnquiryWrite.model_validate(
            {
                "enquiry_date": date(2026, 10, 1),
                "branch_id": "00000000-0000-0000-0000-000000000001",
            }
        )


def test_the_enquiry_list_is_paged() -> None:
    """D-SELL-63: ``page`` and ``page_size`` were ignored; every row came back."""
    setup = _Setup(_session_factory()())
    service = EnquiryService(setup.session)
    made = [
        service.create(
            _enquiry(setup, prospect_name=f"Prospect {index}"),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
        for index in range(3)
    ]
    scope = report_scope(setup.firm.id)

    first = list_enquiries(scope=scope, db=setup.session, page=1, page_size=2)
    second = list_enquiries(scope=scope, db=setup.session, page=2, page_size=2)

    assert first.pagination.total_records == 3
    assert first.pagination.total_pages == 2
    assert len(first.data) == 2 and len(second.data) == 1
    assert {row.id for row in first.data} | {row.id for row in second.data} == {
        row.id for row in made
    }
    past = list_enquiries(scope=scope, db=setup.session, page=99, page_size=2)
    assert past.data == [] and past.pagination.total_records == 3
    assert_page_size_is_bounded(enquiry_router, "/api/v1/enquiries")


def test_the_follow_ups_due_are_paged_too() -> None:
    """D-SELL-63, the half left: ``page_size=1000`` answered every row."""
    setup = _Setup(_session_factory()())
    service = EnquiryService(setup.session)
    for index in range(3):
        service.create(
            _enquiry(setup, prospect_name=f"Prospect {index}"),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    scope = report_scope(setup.firm.id)

    first = follow_ups_due(scope=scope, db=setup.session, page=1, page_size=2)
    second = follow_ups_due(scope=scope, db=setup.session, page=2, page_size=2)

    assert first.pagination.total_records == 3
    assert (len(first.data), len(second.data)) == (2, 1)
    assert not {row.id for row in first.data} & {row.id for row in second.data}
    assert_page_size_is_bounded(enquiry_router, "/api/v1/enquiries/follow-ups-due")
