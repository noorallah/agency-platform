"""Collection follow-up: promises, the collector and the sheet (SG-8).

A promise to pay is a note beside a bill. What became of it is read from the
receipts every time it is asked: kept when they cover it by the day promised,
broken when that day passes without them. These tests record real bills and
real receipts through their own services, and pass the day in rather than
patching the clock.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.collections.models import PaymentPromise
from app.collections.schemas import (
    PaymentPromiseCreate,
    PaymentPromiseResponse,
    PromiseStatus,
)
from app.collections.services import CollectionSheetService, PromiseService
from app.common.audit.models import AuditLog
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.customers.schemas.customer import CustomerUpdate
from app.customers.services.customer_service import CustomerService
from app.identity.models import User, UserFirm
from app.sales.models.territory import (
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

#: The day the promises below are taken, and the day they are for.
TAKEN = date(2026, 8, 10)
PROMISED = date(2026, 8, 15)
AFTER = date(2026, 8, 16)


def _world() -> _Firm:
    """Build a counter firm that bills straight from the invoice."""
    setup = _Firm(_session_factory()())
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    return setup


def _member(setup: _Firm, name: str) -> UUID:
    """Add an active member of the firm and return their user id."""
    user = User(
        email=f"{name.lower().replace(' ', '.')}@collect.example.com",
        full_name=name,
        password_hash="x",
        is_active=True,
    )
    setup.session.add(user)
    setup.session.flush()
    setup.session.add(UserFirm(user_id=user.id, firm_id=setup.firm.id, is_active=True))
    setup.session.commit()
    return user.id


def _customer(setup: _Firm, code: str, **fields: object) -> Customer:
    """Add another customer of the firm."""
    customer = Customer(
        firm_id=setup.firm.id,
        code=code,
        customer_type="RETAIL",
        name=f"Customer {code}",
        display_name=f"Customer {code}",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("50000"),
        opening_balance=Decimal("0"),
        **fields,
    )
    setup.session.add(customer)
    setup.session.commit()
    return customer


def _bill(
    setup: _Firm,
    customer: Customer | None = None,
    *,
    due: date | None = date(2026, 8, 9),
) -> SalesInvoice:
    """Raise and approve one bill of 4 at 100."""
    service = SalesInvoiceService(setup.session)
    draft = service.create_invoice(
        setup.bare_bill().model_copy(
            update={
                "customer_id": (customer or setup.customer).id,
                "due_date": due,
            }
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    return service.approve_invoice(draft.id, firm_scope=setup.firm.id, actor_id=uuid4())


def _pay(
    setup: _Firm,
    bill: SalesInvoice,
    amount: Decimal,
    on: date,
    *,
    allocate: bool = True,
) -> Settlement:
    """Record a receipt from the bill's customer, allocated to the bill."""
    row = ReceiptService(setup.session).create(
        SettlementCreate(
            party_id=bill.customer_id,
            settlement_date=on,
            amount=amount,
            method=SettlementMethodEnum.CASH,
            allocations=(
                [SettlementAllocationWrite(invoice_id=bill.id, amount=amount)]
                if allocate
                else []
            ),
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    setup.session.commit()
    return row


def _total(bill: SalesInvoice) -> Decimal:
    """Return what the bill is for, to the paisa."""
    return Decimal(str(bill.grand_total)).quantize(Decimal("0.01"))


def _promise(
    setup: _Firm,
    bill: SalesInvoice | None,
    amount: Decimal,
    *,
    customer: Customer | None = None,
    promised_on: date = PROMISED,
    today: date = TAKEN,
    collector_id: UUID | None = None,
) -> PaymentPromiseResponse:
    """Record one promise on the bill, or on the customer's account."""
    return PromiseService(setup.session).record(
        PaymentPromiseCreate(
            customer_id=(
                bill.customer_id
                if bill is not None
                else (customer or setup.customer).id
            ),
            sales_invoice_id=None if bill is None else bill.id,
            promised_on=promised_on,
            amount=amount,
            note="Said he would send it with the driver.",
            collector_id=collector_id,
        ),
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
        today=today,
    )


def _actor(setup: _Firm) -> UUID:
    """Return the one member who writes the promises down, made once."""
    found = setup.session.scalar(
        select(User.id).where(User.email == "desk@collect.example.com")
    )
    return found or _member(setup, "Desk")


def _status(setup: _Firm, promise_id: UUID, today: date) -> PaymentPromiseResponse:
    """Read one promise as it stands on ``today``."""
    return PromiseService(setup.session).get(
        promise_id, firm_id=setup.firm.id, today=today
    )


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


# ---- what became of a promise ---------------------------------------------


def test_a_promise_is_pending_then_due_then_broken_when_nothing_arrives() -> None:
    """The same row reads differently as the days pass; nothing is stored."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, bill, _total(bill))

    assert promise.status is PromiseStatus.PENDING
    assert promise.invoice_number == bill.invoice_number
    assert promise.customer_name == setup.customer.name
    assert promise.recorded_on == TAKEN
    assert promise.recorded_by_name == "Desk"
    assert _status(setup, promise.id, PROMISED).status is PromiseStatus.DUE_TODAY
    broken = _status(setup, promise.id, AFTER)
    assert broken.status is PromiseStatus.BROKEN
    assert broken.received_amount == Decimal("0.00")


def test_a_promise_is_kept_when_the_bill_is_paid_in_time() -> None:
    """A receipt on the promised day itself keeps it, and it stays kept."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, bill, _total(bill))

    _pay(setup, bill, _total(bill), PROMISED)

    kept = _status(setup, promise.id, AFTER)
    assert kept.status is PromiseStatus.KEPT
    assert kept.received_amount == _total(bill)


def test_part_of_the_money_does_not_keep_a_promise() -> None:
    """Half of what was promised by the day is a broken promise."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, bill, _total(bill))

    _pay(setup, bill, Decimal("100.00"), date(2026, 8, 12))

    part = _status(setup, promise.id, AFTER)
    assert part.status is PromiseStatus.BROKEN
    assert part.received_amount == Decimal("100.00")


def test_money_that_arrives_late_or_came_before_does_not_keep_it() -> None:
    """Only receipts dated inside the promise's own window count."""
    setup = _world()
    bill = _bill(setup)
    _pay(setup, bill, Decimal("50.00"), date(2026, 8, 9))
    promise = _promise(setup, bill, Decimal("200.00"))

    _pay(setup, bill, Decimal("200.00"), AFTER)

    late = _status(setup, promise.id, date(2026, 8, 20))
    assert late.status is PromiseStatus.BROKEN
    assert late.received_amount == Decimal("0.00")


def test_a_reversed_receipt_does_not_keep_a_promise() -> None:
    """Taking the receipt back takes the kept promise back with it."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, bill, _total(bill))
    receipt = _pay(setup, bill, _total(bill), date(2026, 8, 12))
    assert _status(setup, promise.id, AFTER).status is PromiseStatus.KEPT

    ReceiptService(setup.session).reverse(
        receipt.id, firm_id=setup.firm.id, actor_id=uuid4(), reason="Wrong customer"
    )
    setup.session.commit()

    assert _status(setup, promise.id, AFTER).status is PromiseStatus.BROKEN


def test_a_promise_on_the_account_is_kept_by_any_receipt_from_the_customer() -> None:
    """With no bill named, what the customer paid in the window is what counts."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, None, Decimal("150.00"))
    assert promise.sales_invoice_id is None
    assert promise.invoice_number is None

    _pay(setup, bill, Decimal("150.00"), date(2026, 8, 14), allocate=False)

    assert _status(setup, promise.id, AFTER).status is PromiseStatus.KEPT


def test_a_withdrawn_promise_keeps_its_history() -> None:
    """Withdrawing stamps the row and the trail; it cannot be done twice."""
    setup = _world()
    bill = _bill(setup)
    promise = _promise(setup, bill, Decimal("100.00"))
    service = PromiseService(setup.session)

    withdrawn = service.withdraw(
        promise.id,
        "Customer asked for another week",
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
        today=AFTER,
    )

    assert withdrawn.status is PromiseStatus.WITHDRAWN
    assert withdrawn.cancel_reason == "Customer asked for another week"
    assert withdrawn.cancelled_at is not None
    assert setup.session.scalar(select(PaymentPromise.id)) == promise.id
    actions = setup.session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == promise.id)
    ).all()
    assert sorted(actions) == ["payment_promise.recorded", "payment_promise.withdrawn"]
    with pytest.raises(ConflictError, match="already withdrawn"):
        service.withdraw(
            promise.id, "Again", firm_id=setup.firm.id, actor_id=_actor(setup)
        )


# ---- what may be promised --------------------------------------------------


def test_a_promise_for_more_than_the_bill_owes_is_refused() -> None:
    """What the bill owes is net of what it has already been paid."""
    setup = _world()
    bill = _bill(setup)
    _pay(setup, bill, Decimal("100.00"), date(2026, 8, 9))

    with pytest.raises(ValidationError, match="cannot be for more"):
        _promise(setup, bill, _total(bill))

    assert _promise(setup, bill, _total(bill) - Decimal("100.00")).amount == (
        _total(bill) - Decimal("100.00")
    )


def test_a_promise_on_a_paid_bill_is_refused() -> None:
    """A bill that owes nothing has nothing to promise."""
    setup = _world()
    bill = _bill(setup)
    _pay(setup, bill, _total(bill), date(2026, 8, 9))

    with pytest.raises(ValidationError, match="owes nothing"):
        _promise(setup, bill, Decimal("10.00"))


def test_another_customers_bill_is_refused() -> None:
    """A promise names the customer who made it and a bill of theirs."""
    setup = _world()
    bill = _bill(setup)
    other = _customer(setup, "CUS-002")

    with pytest.raises(ValidationError, match="another customer"):
        PromiseService(setup.session).record(
            PaymentPromiseCreate(
                customer_id=other.id,
                sales_invoice_id=bill.id,
                promised_on=PROMISED,
                amount=Decimal("10.00"),
            ),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
            today=TAKEN,
        )


def test_a_draft_bill_and_a_day_gone_by_are_refused() -> None:
    """Nothing is owed on a draft, and nobody promises for yesterday."""
    setup = _world()
    draft = SalesInvoiceService(setup.session).create_invoice(
        setup.bare_bill(), firm_id=setup.firm.id, actor_id=uuid4()
    )
    with pytest.raises(ValidationError, match="not approved"):
        _promise(setup, draft, Decimal("10.00"))
    bill = _bill(setup)
    with pytest.raises(ValidationError, match="today or a later day"):
        _promise(setup, bill, Decimal("10.00"), promised_on=date(2026, 8, 9))


def test_the_collector_must_be_a_member_of_the_firm() -> None:
    """On the promise and on the customer alike; a stranger is refused."""
    setup = _world()
    bill = _bill(setup)
    asha = _member(setup, "Asha Rao")

    with pytest.raises(ValidationError, match="collector must be an active member"):
        _promise(setup, bill, Decimal("10.00"), collector_id=uuid4())
    named = _promise(setup, bill, Decimal("10.00"), collector_id=asha)
    assert named.collector_name == "Asha Rao"

    customers = CustomerService(setup.session)

    def save(**sent: object) -> None:
        """Save the customer's form with ``sent`` added to it."""
        customers.stage_update(
            setup.customer,
            CustomerUpdate.model_validate(
                {
                    "code": setup.customer.code,
                    "customer_type": "INDIVIDUAL",
                    "name": setup.customer.name,
                    "currency_code": "INR",
                    **sent,
                }
            ),
            actor_id=uuid4(),
        )
        setup.session.commit()

    with pytest.raises(ValidationError, match="collector must be an active member"):
        save(collector_id=str(uuid4()))
    setup.session.rollback()
    save(collector_id=str(asha))
    assert setup.customer.collector_id == asha
    # Absent on an update leaves it alone; an explicit null clears it.
    save()
    assert setup.customer.collector_id == asha
    save(collector_id=None)
    assert setup.customer.collector_id is None


def test_a_promise_takes_the_customers_collector_when_none_is_named() -> None:
    """Who took it defaults to who collects from the customer that day."""
    setup = _world()
    asha = _member(setup, "Asha Rao")
    setup.customer.salesman_id = asha
    setup.session.commit()
    bill = _bill(setup)

    assert _promise(setup, bill, Decimal("10.00")).collector_id == asha


# ---- the lists -------------------------------------------------------------


def test_the_list_filters_on_the_derived_status_and_pages() -> None:
    """Status is a filter the database answers, so the count is of the filter."""
    setup = _world()
    paid, unpaid, later = _bill(setup), _bill(setup), _bill(setup)
    kept = _promise(setup, paid, _total(paid))
    broken = _promise(setup, unpaid, Decimal("50.00"))
    pending = _promise(setup, later, Decimal("50.00"), promised_on=date(2026, 8, 30))
    _pay(setup, paid, _total(paid), date(2026, 8, 11))
    service = PromiseService(setup.session)

    def ids(**filters: Any) -> tuple[list[UUID], int]:  # noqa: ANN401
        """List with the filters on the day after the promised day."""
        rows, total = service.list_promises(
            setup.firm.id, page=1, page_size=10, today=AFTER, **filters
        )
        return [row.id for row in rows], total

    assert ids(status=PromiseStatus.KEPT) == ([kept.id], 1)
    assert ids(status=PromiseStatus.BROKEN) == ([broken.id], 1)
    assert ids(status=PromiseStatus.PENDING) == ([pending.id], 1)
    assert ids(status=PromiseStatus.WITHDRAWN) == ([], 0)
    assert ids(sales_invoice_id=unpaid.id) == ([broken.id], 1)
    assert ids(due_from=date(2026, 8, 20)) == ([pending.id], 1)
    assert ids(due_to=PROMISED)[1] == 2
    assert ids(customer_id=uuid4()) == ([], 0)
    everything, total = service.list_promises(
        setup.firm.id, page=2, page_size=2, today=AFTER
    )
    assert total == 3
    assert len(everything) == 1


def test_the_chase_list_is_todays_promises_and_the_broken_ones_not_renewed() -> None:
    """A broken promise leaves the list once a newer one is taken on the bill."""
    setup = _world()
    today_bill, old_bill, renewed_bill, paid_late = (
        _bill(setup),
        _bill(setup),
        _bill(setup),
        _bill(setup),
    )
    due_today = _promise(setup, today_bill, Decimal("50.00"), promised_on=AFTER)
    broken = _promise(setup, old_bill, Decimal("50.00"))
    _promise(setup, renewed_bill, Decimal("50.00"))
    renewal = _promise(
        setup,
        renewed_bill,
        Decimal("50.00"),
        promised_on=date(2026, 8, 25),
        today=PROMISED,
    )
    # Broken, then paid in full a day late: nothing left to chase.
    _promise(setup, paid_late, _total(paid_late))
    _pay(setup, paid_late, _total(paid_late), AFTER)
    service = PromiseService(setup.session)

    rows, total = service.chase_list(setup.firm.id, page=1, page_size=10, today=AFTER)

    assert [(row.id, row.status) for row in rows] == [
        (broken.id, PromiseStatus.BROKEN),
        (due_today.id, PromiseStatus.DUE_TODAY),
    ]
    assert total == 2
    assert renewal.status is PromiseStatus.PENDING
    paged, total = service.chase_list(setup.firm.id, page=2, page_size=1, today=AFTER)
    assert ([row.id for row in paged], total) == ([due_today.id], 2)


# ---- the sheet -------------------------------------------------------------


def test_the_sheet_is_by_collector_falling_back_to_the_account_manager() -> None:
    """Each open bill, net of what it was paid, under whose job it is."""
    setup = _world()
    asha = _member(setup, "Asha Rao")
    binod = _member(setup, "Binod Das")
    # The seeded customer: an account manager and no collector of its own.
    setup.customer.salesman_id = binod
    setup.session.commit()
    collected = _customer(setup, "CUS-002", collector_id=asha, salesman_id=binod)
    nobody = _customer(setup, "CUS-003")
    first = _bill(setup, due=date(2026, 8, 5))
    second = _bill(setup, collected, due=date(2026, 8, 20))
    third = _bill(setup, nobody, due=None)
    _pay(setup, first, Decimal("150.00"), date(2026, 8, 9))
    promise = _promise(setup, first, Decimal("100.00"))
    sheet = CollectionSheetService(setup.session)

    rows = sheet.rows(setup.firm.id, as_of=AFTER)

    assert [
        (row.collector_name, row.customer_code, row.invoice_number) for row in rows
    ] == [
        ("Asha Rao", "CUS-002", second.invoice_number),
        ("Binod Das", "CUS-001", first.invoice_number),
        (None, "CUS-003", third.invoice_number),
    ]
    mine = rows[1]
    assert mine.collector_id == binod
    assert mine.outstanding == _total(first) - Decimal("150.00")
    assert mine.invoice_total == _total(first)
    assert mine.days_overdue == 11
    assert (mine.promise_id, mine.promised_on, mine.promised_amount) == (
        promise.id,
        PROMISED,
        Decimal("100.00"),
    )
    assert mine.promise_status is PromiseStatus.BROKEN
    assert mine.promise_is_for_account is False
    assert rows[0].days_overdue == 0
    assert rows[0].promise_id is None
    assert rows[2].due_date is None

    assert [
        row.customer_code for row in sheet.rows(setup.firm.id, collector_id=binod)
    ] == ["CUS-001"]
    assert [
        row.customer_code
        for row in sheet.rows(setup.firm.id, as_of=AFTER, overdue_only=True)
    ] == ["CUS-001"]
    page, total = sheet.page(setup.firm.id, page=2, page_size=2, as_of=AFTER)
    assert total == 3
    assert [row.customer_code for row in page] == ["CUS-003"]
    # A bill paid in full leaves the sheet.
    _pay(setup, second, _total(second), AFTER)
    assert second.invoice_number not in [
        row.invoice_number for row in sheet.rows(setup.firm.id, as_of=AFTER)
    ]


def test_the_sheet_shows_an_account_promise_on_a_bill_with_none_of_its_own() -> None:
    """A promise for the account stands behind every bill of the customer."""
    setup = _world()
    _bill(setup)
    promise = _promise(setup, None, Decimal("75.00"))

    [row] = CollectionSheetService(setup.session).rows(setup.firm.id, as_of=TAKEN)

    assert row.promise_id == promise.id
    assert row.promise_is_for_account is True
    assert row.promise_status is PromiseStatus.PENDING


def test_the_sheet_by_route_lists_the_customers_on_that_round() -> None:
    """A route is named by its profile, or by the territory it profiles."""
    setup = _world()
    off_route = _customer(setup, "CUS-002")
    _bill(setup)
    _bill(setup, off_route)
    territory = SalesTerritoryNode(
        firm_id=setup.firm.id,
        hierarchy_level_id=uuid4(),
        code="R-01",
        name="Route 1",
        path="R-01",
    )
    setup.session.add(territory)
    setup.session.flush()
    route = TerritoryRouteProfile(territory_id=territory.id, visit_frequency="WEEKLY")
    setup.session.add_all(
        [
            route,
            TerritoryCustomerAssignment(
                territory_id=territory.id, customer_id=setup.customer.id
            ),
        ]
    )
    setup.session.commit()
    sheet = CollectionSheetService(setup.session)

    for named in (route.id, territory.id):
        assert [
            row.customer_code for row in sheet.rows(setup.firm.id, route_id=named)
        ] == ["CUS-001"]
    assert sheet.rows(setup.firm.id, route_id=uuid4()) == []


def test_the_sheet_prints_as_a_pdf() -> None:
    """The paper is a PDF whether or not there is anything on it."""
    setup = _world()
    sheet = CollectionSheetService(setup.session)
    assert sheet.pdf(setup.firm.id, as_of=AFTER).startswith(b"%PDF")
    bill = _bill(setup)
    _promise(setup, bill, Decimal("100.00"))
    assert sheet.pdf(setup.firm.id, as_of=AFTER).startswith(b"%PDF")


# ---- cost and bounds -------------------------------------------------------


def _seeded(bills: int) -> _Firm:
    """Build a firm with ``bills`` open bills, each carrying a promise."""
    setup = _world()
    _actor(setup)
    for _ in range(bills):
        _promise(setup, _bill(setup), Decimal("10.00"))
    setup.session.expire_all()
    return setup


def test_the_list_and_the_sheet_cost_the_same_at_any_length() -> None:
    """Six rows cost no more statements than two."""
    counts: dict[str, list[int]] = {"list": [], "chase": [], "sheet": []}
    for bills in (2, 6):
        setup = _seeded(bills)
        with _counting(setup.session) as seen:
            rows, total = PromiseService(setup.session).list_promises(
                setup.firm.id, page=1, page_size=50, today=AFTER
            )
        assert total == len(rows) == bills
        counts["list"].append(len(seen))
        with _counting(setup.session) as seen:
            chase, _ = PromiseService(setup.session).chase_list(
                setup.firm.id, page=1, page_size=50, today=AFTER
            )
        assert len(chase) == bills
        counts["chase"].append(len(seen))
        with _counting(setup.session) as seen:
            sheet = CollectionSheetService(setup.session).rows(
                setup.firm.id, as_of=AFTER
            )
        assert len(sheet) == bills
        counts["sheet"].append(len(seen))
    for name, (small, large) in counts.items():
        assert large == small, f"{name}: {small} statements at 2 rows, {large} at 6"


def test_a_listed_row_is_the_promise_read_alone() -> None:
    """The page builder and the single read answer the same."""
    setup = _seeded(3)
    service = PromiseService(setup.session)
    rows, _ = service.list_promises(setup.firm.id, page=1, page_size=50, today=AFTER)
    for row in rows:
        assert row == service.get(row.id, firm_id=setup.firm.id, today=AFTER)


def test_the_routes_are_served_and_bound_their_pages() -> None:
    """An over-cap page is a 422 naming the limit, never a 500."""
    from app.main import create_app

    application = create_app()
    paths = application.openapi()["paths"]
    for path in (
        "/api/v1/collections/promises",
        "/api/v1/collections/promises/due-today",
        "/api/v1/collections/sheet",
    ):
        bounds = {
            parameter["name"]: parameter["schema"]
            for parameter in paths[path]["get"]["parameters"]
        }
        assert bounds["page"]["minimum"] == 1
        assert bounds["page_size"]["minimum"] == 1
        assert bounds["page_size"]["maximum"] == MAX_PAGE_SIZE
    assert "post" in paths["/api/v1/collections/promises"]
    assert "post" in paths["/api/v1/collections/promises/{promise_id}/withdraw"]
    assert "get" in paths["/api/v1/collections/sheet/pdf"]
