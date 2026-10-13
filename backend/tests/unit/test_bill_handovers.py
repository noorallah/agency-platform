"""Bills handed to a collector, and taken back (backlog 122, row M4).

A handover is a note beside a bill: who carries it, since which day, and when
it came home. These tests raise real bills and real receipts through their
own services and ask the one thing the customer asked for: handing a bill out
and taking it back changes no balance, no journal and no report.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.collections.models import BillHandover
from app.collections.schemas import (
    HandedFilter,
    HandoverCreate,
    HandoverMatching,
    HandoverResult,
    HandoverState,
    HandoverTakeBack,
)
from app.collections.services import BillHandoverService, CollectionSheetService
from app.common.audit.models import AuditLog
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.customers.models import (
    Customer,
    CustomerAddress,
    CustomerReceivableTransaction,
)
from app.customers.services.statement_service import CustomerStatementService
from app.finance.models import JournalEntry
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement
from tests.unit.test_collection_follow_up import (
    _actor,
    _bill,
    _counting,
    _customer,
    _member,
    _pay,
    _total,
    _world,
)
from tests.unit.test_sales_chain_synthesis import _Firm

TODAY = date(2026, 8, 20)


def _give(
    setup: _Firm,
    collector: UUID,
    *bills: SalesInvoice,
    matching: HandoverMatching | None = None,
    handed_on: date | None = None,
) -> HandoverResult:
    """Hand the bills, or a matched bundle, to the collector."""
    return BillHandoverService(setup.session).hand_out(
        HandoverCreate(
            collector_id=collector,
            handed_on=handed_on,
            invoice_ids=[bill.id for bill in bills] if matching is None else None,
            matching=matching,
        ),
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
        today=TODAY,
    )


def _out(setup: _Firm) -> dict[UUID, BillHandover]:
    """Return the live handovers by the invoice each carries."""
    return {
        row.sales_invoice_id: row
        for row in setup.session.scalars(
            select(BillHandover).where(BillHandover.returned_at.is_(None))
        )
        if row.sales_invoice_id is not None
    }


def _take_back(setup: _Firm, *bills: SalesInvoice, note: str | None = None) -> int:
    """Take the bills back and return how many came."""
    live = _out(setup)
    return (
        BillHandoverService(setup.session)
        .take_back(
            HandoverTakeBack(
                handover_ids=[live[bill.id].id for bill in bills], note=note
            ),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
        )
        .bills
    )


def _lives_in(setup: _Firm, customer: Customer, area: str, city: str) -> None:
    """Give the customer a billing address in that area."""
    setup.session.add(
        CustomerAddress(
            customer_id=customer.id,
            address_type="BILLING",
            address_line1="1 Market Road",
            area=area,
            city=city,
            state="Telangana",
            country="IN",
            postal_code="500001",
            is_default_billing=True,
        )
    )
    setup.session.commit()


def _books(setup: _Firm) -> dict[str, object]:
    """Read everything that states money, to compare before and after."""
    session = setup.session
    firm_id = setup.firm.id
    statements = CustomerStatementService(session)
    return {
        "journals": session.scalar(select(func.count()).select_from(JournalEntry)),
        "settlements": session.scalar(select(func.count()).select_from(Settlement)),
        "receivables": [
            (str(row.customer_id), str(row.outstanding_after), str(row.advance_after))
            for row in session.scalars(
                select(CustomerReceivableTransaction).order_by(
                    CustomerReceivableTransaction.created_at,
                    CustomerReceivableTransaction.id,
                )
            )
        ],
        "ageing": [
            row.model_dump()
            for row in statements.ageing(firm_scope=firm_id, as_of=TODAY)
        ],
        "sheet": [
            row.model_dump()
            for row in CollectionSheetService(session).rows(firm_id, as_of=TODAY)
        ],
        "bills": [
            (row.invoice_number, row.outstanding)
            for row in BillHandoverService(session).bills(firm_id, today=TODAY)
        ],
    }


# ---- handing out ----------------------------------------------------------


def test_a_ticked_bill_goes_out_with_the_collector() -> None:
    """A handed-out bill names who carries it, since when, and what it owed."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill, other = _bill(setup), _bill(setup)

    result = _give(setup, ravi, bill)

    assert (result.bills, result.amount, result.already_out) == (1, _total(bill), 0)
    rows = {
        row.invoice_id: row
        for row in BillHandoverService(setup.session).bills(setup.firm.id, today=TODAY)
    }
    assert rows[bill.id].collector_id == ravi
    assert rows[bill.id].collector_name == "Ravi Collector"
    assert rows[bill.id].handed_on == TODAY
    assert rows[bill.id].days_overdue == (TODAY - date(2026, 8, 9)).days
    assert rows[other.id].handover_id is None
    stored = _out(setup)[bill.id]
    assert Decimal(str(stored.outstanding_at_handover)) == _total(bill)
    assert stored.handed_by == _actor(setup)
    audit = setup.session.scalars(
        select(AuditLog).where(AuditLog.action == "bill_handover.handed_out")
    ).all()
    assert [entry.entity_id for entry in audit] == [stored.id]


def test_handing_out_and_taking_back_change_no_balance_and_no_report() -> None:
    """The customer's Try: nothing that states money moves."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    second = _customer(setup, "C-HAND-2")
    paid_part, untouched = _bill(setup), _bill(setup, second)
    _pay(setup, paid_part, Decimal("100.00"), date(2026, 8, 12))
    before = _books(setup)

    _give(setup, ravi, paid_part, untouched)
    out = _books(setup)
    assert _take_back(setup, paid_part, untouched, note="Shop closed") == 2
    back = _books(setup)

    assert out == before
    assert back == before
    assert setup.session.scalar(select(func.count()).select_from(BillHandover)) == 2


def test_a_bill_already_out_is_refused_by_name_and_nothing_is_written() -> None:
    """Ticking a bill somebody carries hands out none of the ticked bills."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    held, free = _bill(setup), _bill(setup)
    _give(setup, ravi, held)

    with pytest.raises(ConflictError) as refusal:
        _give(setup, sita, free, held)

    assert held.invoice_number in str(refusal.value.message)
    assert set(_out(setup)) == {held.id}
    assert _out(setup)[held.id].collector_id == ravi


def test_a_bill_that_owes_nothing_or_is_not_the_firms_is_refused() -> None:
    """Only a bill still owing is handed out."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    paid = _bill(setup)
    _pay(setup, paid, _total(paid), date(2026, 8, 12))

    with pytest.raises(ValidationError):
        _give(setup, ravi, paid)
    with pytest.raises(ValidationError):
        BillHandoverService(setup.session).hand_out(
            HandoverCreate(collector_id=ravi, invoice_ids=[uuid4()]),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
            today=TODAY,
        )
    assert _out(setup) == {}


def test_the_collector_is_a_member_and_the_day_is_not_in_the_future() -> None:
    """A stranger carries nothing, and nothing goes out tomorrow."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)

    with pytest.raises(ValidationError):
        _give(setup, uuid4(), bill)
    with pytest.raises(ValidationError):
        _give(setup, ravi, bill, handed_on=TODAY + timedelta(days=1))
    _give(setup, ravi, bill, handed_on=TODAY - timedelta(days=2))
    assert _out(setup)[bill.id].handed_on == TODAY - timedelta(days=2)


def test_the_request_names_the_ticked_bills_or_a_bundle_never_both() -> None:
    """Neither, both, and a bundle naming nothing are refused by the schema."""
    collector = uuid4()
    with pytest.raises(SchemaError):
        HandoverCreate(collector_id=collector)
    with pytest.raises(SchemaError):
        HandoverCreate(
            collector_id=collector,
            invoice_ids=[uuid4()],
            matching=HandoverMatching(area="Abids"),
        )
    with pytest.raises(SchemaError):
        HandoverMatching()
    with pytest.raises(SchemaError):
        HandoverMatching(area="   ")
    with pytest.raises(SchemaError):
        HandoverMatching(date_from=date(2026, 8, 9), date_to=date(2026, 8, 8))


# ---- a bundle: by date, area, a run of numbers ----------------------------


def test_a_bundle_by_area_takes_that_areas_bills_and_leaves_those_out() -> None:
    """Bills of the area go out; one already out stays and is counted."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    abids, kothi = _customer(setup, "C-ABIDS"), _customer(setup, "C-KOTHI")
    _lives_in(setup, abids, "Abids", "Hyderabad")
    _lives_in(setup, kothi, "Kothi", "Hyderabad")
    first, second, elsewhere = (
        _bill(setup, abids),
        _bill(setup, abids),
        _bill(setup, kothi),
    )
    _give(setup, sita, first)

    result = _give(setup, ravi, matching=HandoverMatching(area="abids"))

    assert (result.bills, result.already_out) == (1, 1)
    assert result.amount == _total(second)
    live = _out(setup)
    assert live[first.id].collector_id == sita
    assert live[second.id].collector_id == ravi
    assert elsewhere.id not in live
    listed = BillHandoverService(setup.session).bills(
        setup.firm.id, matching=HandoverMatching(area="HYDERABAD"), today=TODAY
    )
    assert {row.invoice_id for row in listed} == {first.id, second.id, elsewhere.id}
    assert {row.customer_place for row in listed} == {
        "Abids, Hyderabad",
        "Kothi, Hyderabad",
    }


def test_a_bundle_by_a_run_of_bill_numbers_stays_inside_the_run() -> None:
    """From one number to another of the same series, both ends counted."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bills = [_bill(setup) for _ in range(4)]
    numbers = [bill.invoice_number for bill in bills]

    result = _give(
        setup,
        ravi,
        matching=HandoverMatching(number_from=numbers[1], number_to=numbers[2]),
    )

    assert result.bills == 2
    assert set(_out(setup)) == {bills[1].id, bills[2].id}
    service = BillHandoverService(setup.session)
    open_ended = service.bills(
        setup.firm.id, matching=HandoverMatching(number_from=numbers[2]), today=TODAY
    )
    assert [row.invoice_number for row in open_ended] == numbers[2:]
    with pytest.raises(ValidationError):
        service.bills(
            setup.firm.id,
            matching=HandoverMatching(number_from=numbers[2], number_to=numbers[0]),
        )
    with pytest.raises(ValidationError):
        service.bills(
            setup.firm.id,
            matching=HandoverMatching(number_from="OTHER-1", number_to=numbers[0]),
        )
    with pytest.raises(ValidationError):
        service.bills(setup.firm.id, matching=HandoverMatching(number_from="ABC"))


def test_a_bundle_by_date_and_by_customer() -> None:
    """A day's bills, and one customer's."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    second = _customer(setup, "C-HAND-3")
    mine, theirs = _bill(setup), _bill(setup, second)
    service = BillHandoverService(setup.session)

    on_the_day = service.bills(
        setup.firm.id,
        matching=HandoverMatching(
            date_from=mine.invoice_date, date_to=mine.invoice_date
        ),
        today=TODAY,
    )
    before = service.bills(
        setup.firm.id,
        matching=HandoverMatching(date_to=mine.invoice_date - timedelta(days=1)),
        today=TODAY,
    )
    result = _give(setup, ravi, matching=HandoverMatching(customer_id=second.id))

    assert {row.invoice_id for row in on_the_day} == {mine.id, theirs.id}
    assert before == []
    assert result.bills == 1
    assert set(_out(setup)) == {theirs.id}


# ---- the lists ------------------------------------------------------------


def test_the_list_is_narrowed_by_who_carries_the_bill() -> None:
    """In the office, out, and out with one person."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    with_ravi, with_sita, in_office = _bill(setup), _bill(setup), _bill(setup)
    _give(setup, ravi, with_ravi)
    _give(setup, sita, with_sita)
    service = BillHandoverService(setup.session)

    def ids(**asked: object) -> set[UUID]:
        """Return the bills one way of asking lists."""
        return {
            row.invoice_id
            for row in service.bills(setup.firm.id, today=TODAY, **asked)  # type: ignore[arg-type]
        }

    assert ids() == {with_ravi.id, with_sita.id, in_office.id}
    assert ids(handed=HandedFilter.OUT) == {with_ravi.id, with_sita.id}
    assert ids(handed=HandedFilter.NOT_OUT) == {in_office.id}
    assert ids(collector_id=ravi) == {with_ravi.id}
    page, total = service.bills_page(setup.firm.id, page=2, page_size=2)
    assert (len(page), total) == (1, 3)


def test_a_bill_paid_while_out_is_found_in_the_history_and_taken_back() -> None:
    """It leaves the unpaid bills, stays out, and still comes home."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    _pay(setup, bill, _total(bill), date(2026, 8, 19))
    service = BillHandoverService(setup.session)

    assert service.bills(setup.firm.id, today=TODAY) == []
    rows, total = service.list_handovers(
        setup.firm.id, page=1, page_size=20, state=HandoverState.OUT
    )
    assert total == 1
    assert rows[0].invoice_number == bill.invoice_number
    assert rows[0].outstanding_at_handover == _total(bill)
    assert rows[0].outstanding == Decimal("0.00")
    assert rows[0].collector_name == "Ravi Collector"
    assert rows[0].handed_by_name == "Desk"

    assert _take_back(setup, bill, note="Paid at the shop") == 1
    rows, total = service.list_handovers(setup.firm.id, page=1, page_size=20)
    assert (total, rows[0].state) == (1, HandoverState.RETURNED)
    assert rows[0].return_note == "Paid at the shop"
    assert rows[0].returned_by_name == "Desk"
    none_out, _ = service.list_handovers(
        setup.firm.id, page=1, page_size=20, state=HandoverState.OUT
    )
    assert none_out == []


def test_the_history_lists_bills_still_out_first() -> None:
    """Out before taken back, whatever the day."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    old, new = _bill(setup), _bill(setup)
    _give(setup, ravi, new, handed_on=TODAY)
    _take_back(setup, new)
    _give(setup, ravi, old, handed_on=TODAY - timedelta(days=5))

    rows, _ = BillHandoverService(setup.session).list_handovers(
        setup.firm.id, page=1, page_size=20, collector_id=ravi
    )

    assert [row.invoice_id for row in rows] == [old.id, new.id]
    assert [row.state for row in rows] == [HandoverState.OUT, HandoverState.RETURNED]
    narrowed, total = BillHandoverService(setup.session).list_handovers(
        setup.firm.id,
        page=1,
        page_size=20,
        handed_from=TODAY,
        handed_to=TODAY,
    )
    assert (total, narrowed[0].invoice_id) == (1, new.id)


# ---- taking back ----------------------------------------------------------


def test_a_bill_taken_back_can_go_out_again_and_keeps_its_history() -> None:
    """One live handover per bill; the earlier ones stay as rows."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    _take_back(setup, bill)
    _give(setup, sita, bill)

    assert _out(setup)[bill.id].collector_id == sita
    assert setup.session.scalar(select(func.count()).select_from(BillHandover)) == 2
    taken = setup.session.scalars(
        select(AuditLog).where(AuditLog.action == "bill_handover.taken_back")
    ).all()
    assert len(taken) == 1


def test_taking_back_is_all_or_nothing() -> None:
    """An unknown handover or one already back refuses the whole request."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    first, second = _bill(setup), _bill(setup)
    _give(setup, ravi, first, second)
    live = _out(setup)
    service = BillHandoverService(setup.session)

    with pytest.raises(ResourceNotFoundError):
        service.take_back(
            HandoverTakeBack(handover_ids=[live[first.id].id, uuid4()]),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
        )
    assert set(_out(setup)) == {first.id, second.id}

    _take_back(setup, first)
    with pytest.raises(ConflictError):
        service.take_back(
            HandoverTakeBack(handover_ids=[live[first.id].id, live[second.id].id]),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
        )
    setup.session.rollback()
    assert set(_out(setup)) == {second.id}


def test_the_index_holds_a_bill_to_one_live_handover() -> None:
    """Two rows out for one bill are refused by the store itself."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    first = _out(setup)[bill.id]

    setup.session.add(
        BillHandover(
            firm_id=setup.firm.id,
            customer_id=bill.customer_id,
            sales_invoice_id=bill.id,
            collector_id=ravi,
            handed_on=TODAY,
            handed_by=ravi,
            outstanding_at_handover=Decimal("1.00"),
        )
    )
    with pytest.raises(IntegrityError):
        setup.session.flush()
    setup.session.rollback()
    assert _out(setup)[bill.id].id == first.id


# ---- cost and access ------------------------------------------------------


def test_the_list_costs_the_same_however_many_bills_it_holds() -> None:
    """The unpaid bills and the history are built in bulk, not row by row."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    service = BillHandoverService(setup.session)

    def cost() -> tuple[int, int]:
        """Count the statements behind each list."""
        with _counting(setup.session) as bills:
            service.bills(setup.firm.id, today=TODAY)
        with _counting(setup.session) as history:
            service.list_handovers(setup.firm.id, page=1, page_size=50)
        return len(bills), len(history)

    _give(setup, ravi, _bill(setup))
    few = cost()
    _give(setup, ravi, *[_bill(setup) for _ in range(4)])

    assert cost() == few


def test_handing_out_has_its_own_permission_which_a_cashier_does_not_hold() -> None:
    """Whoever records the money does not decide which bills he carries."""
    assert "COLLECTION_ASSIGN" in PERMISSION_GROUPS["accounting"]
    assert "COLLECTION_ASSIGN" in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "COLLECTION_ASSIGN" in ROLE_PERMISSION_CODES["ACCOUNTANT"]
    assert "COLLECTION_ASSIGN" not in ROLE_PERMISSION_CODES["CASHIER"]
    assert "COLLECTION_ASSIGN" not in ROLE_PERMISSION_CODES["SALES_EXECUTIVE"]
