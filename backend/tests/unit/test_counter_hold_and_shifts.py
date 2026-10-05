"""Hold and recall a counter bill; a cashier's shift counted at close (SG-7).

Two things a counter does all day that the firm had no record of:

* **A held bill** is a draft with a flag. It stays a draft, it can be edited,
  and it never posts -- not from its own screen and not from a ticked list --
  until it is recalled.
* **A shift** is a cashier's till. A bill paid at the counter is stamped with
  the shift its approver has open, and what the drawer should hold is summed
  from those bills' cash tenders on every read. Closing snapshots that figure
  and posts the difference from the count to *Cash short and over*.

Shifts are optional: somebody with none open bills exactly as before.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.common.audit.models.audit_log import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from app.counter_shifts.models import CounterShift, CounterShiftStatus
from app.counter_shifts.schemas import CounterShiftClose, CounterShiftOpen
from app.counter_shifts.services import CounterShiftService
from app.document_framework.schemas.bulk_actions import BulkApproveRequest, BulkRow
from app.finance.models import FirmControlAccount, JournalEntry, JournalLine
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.sales_invoice.api.router import (
    HoldRequest,
    bulk_approve_sales_invoices,
    hold_sales_invoice,
    recall_sales_invoice,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceListFilters,
    SalesInvoiceStatus,
    SalesInvoiceTenderWrite,
)
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.services import ReceiptService
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory
from tests.unit.test_sales_order_module import _principal

#: Inside the year the fixture's books are open for, the day its bills carry.
EVENING = datetime(2026, 8, 4, 18, 0, tzinfo=UTC)
PRICE = Decimal("100")


class _Counter:
    """A firm that bills at the counter, and one cashier at its till."""

    def __init__(self) -> None:
        """Build the firm with every stage off and name a cashier."""
        self.session: Session = _session_factory()()
        self.setup = _Firm(self.session)
        self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.firm_id: UUID = self.setup.firm.id
        self.cashier: UUID = uuid4()
        self.bills = SalesInvoiceService(self.session)
        self.shifts = CounterShiftService(self.session)

    def draft(
        self,
        tenders: list[SalesInvoiceTenderWrite] | None = None,
        *,
        actor: UUID | None = None,
    ) -> SalesInvoice:
        """Save a one-unit counter bill of 100, paid as the tenders say."""
        data = self.setup.bare_bill(Decimal("1"))
        if tenders is not None:
            data = data.model_copy(update={"received_now_tenders": tenders})
        return self.bills.create_invoice(
            data, firm_id=self.firm_id, actor_id=actor or self.cashier
        )

    def sell(
        self, cash: str = "0", upi: str = "0", *, actor: UUID | None = None
    ) -> SalesInvoice:
        """Approve a counter bill of 100 paid by the cash and UPI given."""
        tenders = [
            SalesInvoiceTenderWrite(mode=mode, amount=Decimal(amount))
            for mode, amount in (("CASH", cash), ("UPI", upi))
            if Decimal(amount) > 0
        ]
        bill = self.draft(tenders, actor=actor)
        return self.bills.approve_invoice(
            bill.id, firm_scope=self.firm_id, actor_id=actor or self.cashier
        )

    def open(self, float_: str = "500", *, actor: UUID | None = None) -> CounterShift:
        """Open a till with the float given."""
        return self.shifts.open(
            CounterShiftOpen(opening_float=Decimal(float_)),
            firm_id=self.firm_id,
            actor_id=actor or self.cashier,
            now=datetime(2026, 8, 4, 9, 0, tzinfo=UTC),
        )

    def close(self, shift: CounterShift, counted: str) -> CounterShift:
        """Close a till on the count given, that evening."""
        return self.shifts.close(
            shift.id,
            CounterShiftClose(counted_cash=Decimal(counted), note="End of day"),
            firm_id=self.firm_id,
            actor_id=self.cashier,
            now=EVENING,
        )

    def scope(self, *codes: str, user: UUID | None = None) -> ResolvedFirmScope:
        """Return a firm scope for somebody holding the codes given."""
        return ResolvedFirmScope(
            principal=_principal(user or self.cashier, set(codes)),
            firm_id=self.firm_id,
        )

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Return the account the firm maps a purpose to."""
        return ControlAccountService(self.session).resolve(self.firm_id, purpose)

    def audits(self, action: str) -> list[AuditLog]:
        """Return the audit rows written for one action."""
        return list(
            self.session.scalars(select(AuditLog).where(AuditLog.action == action))
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


# ---- hold and recall ------------------------------------------------------


def test_a_bill_is_held_and_recalled_and_both_are_audited() -> None:
    """Holding sets a flag and a note; the bill stays the draft it was."""
    counter = _Counter()
    bill = counter.draft()

    held = counter.bills.hold_invoice(
        bill.id,
        firm_scope=counter.firm_id,
        actor_id=counter.cashier,
        note="  lady in red, back in 5 min ",
    )
    assert held.is_held is True
    assert held.held_at is not None
    assert held.held_note == "lady in red, back in 5 min"
    assert held.status == SalesInvoiceStatus.DRAFT.value, "a flag, not a status"
    shown = counter.bills.invoice_response(held)
    assert (shown.is_held, shown.held_note) == (True, "lady in red, back in 5 min")
    assert shown.held_at is not None
    assert len(counter.audits("sales_invoice.held")) == 1

    recalled = counter.bills.recall_invoice(
        bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
    )
    assert (recalled.is_held, recalled.held_at, recalled.held_note) == (
        False,
        None,
        None,
    )
    assert recalled.status == SalesInvoiceStatus.DRAFT.value
    assert len(counter.audits("sales_invoice.recalled")) == 1
    with pytest.raises(ValidationError, match="is not held"):
        counter.bills.recall_invoice(
            bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )


def test_the_routes_hold_and_recall_for_whoever_raised_the_bill() -> None:
    """The cashier holds their own draft; a stranger needs the edit code."""
    counter = _Counter()
    bill = counter.draft()
    own = counter.scope("SALES_INVOICE_CREATE")

    held = hold_sales_invoice(
        own, counter.session, bill.id, HoldRequest(note="back soon"), Response()
    )
    assert held.data is not None
    assert held.data.is_held is True
    with pytest.raises(AuthorizationError):
        recall_sales_invoice(
            counter.scope("SALES_INVOICE_CREATE", user=uuid4()),
            counter.session,
            bill.id,
            Response(),
        )
    response = Response()
    recalled = recall_sales_invoice(
        counter.scope("SALES_UPDATE", user=uuid4()),
        counter.session,
        bill.id,
        response,
    )
    assert recalled.data is not None
    assert recalled.data.is_held is False
    assert response.headers["ETag"] == f'"{recalled.data.version}"'


def test_a_held_bill_is_refused_at_approval_and_approves_after_recall() -> None:
    """A held bill never posts, from its own screen or a ticked list."""
    counter = _Counter()
    bill = counter.draft()
    counter.bills.hold_invoice(
        bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
    )

    with pytest.raises(ValidationError, match="Recall it first"):
        counter.bills.approve_invoice(
            bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )
    bulk = bulk_approve_sales_invoices(
        BulkApproveRequest(items=[BulkRow(id=bill.id)]),
        counter.scope("SALES_APPROVE"),
        counter.session,
    )
    assert bulk.data is not None
    assert (bulk.data.done, bulk.data.refused) == (0, 1)
    assert "Recall it first" in (bulk.data.results[0].message or "")
    counter.session.refresh(bill)
    assert bill.status == SalesInvoiceStatus.DRAFT.value
    assert counter.session.scalars(select(JournalEntry)).all() == []

    counter.bills.recall_invoice(
        bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
    )
    approved = counter.bills.approve_invoice(
        bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
    )
    assert approved.status == SalesInvoiceStatus.APPROVED.value


def test_a_held_bill_can_still_be_edited() -> None:
    """Recall is not needed to change a parked bill, and it stays parked."""
    counter = _Counter()
    bill = counter.draft()
    counter.bills.hold_invoice(
        bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier, note="tea"
    )

    [line] = counter.bills.invoice_response(bill).lines
    edited = counter.bills.update_invoice(
        bill.id,
        SalesInvoiceCreate(
            customer_id=counter.setup.customer.id,
            invoice_date=bill.invoice_date,
            remarks="Wants a carry bag",
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=line.source_document_type,
                    source_document_id=line.source_document_id,
                    source_document_line_id=line.source_document_line_id,
                    line_number=1,
                    current_invoice_quantity=line.current_invoice_quantity,
                )
            ],
        ),
        firm_id=counter.firm_id,
        actor_id=counter.cashier,
    )
    assert edited.remarks == "Wants a carry bag"
    assert (edited.is_held, edited.held_note) == (True, "tea")


def test_only_a_draft_can_be_held() -> None:
    """An approved bill has posted; there is nothing left to park."""
    counter = _Counter()
    bill = counter.sell(cash="100")

    with pytest.raises(ValidationError, match="Only a draft bill can be held"):
        counter.bills.hold_invoice(
            bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )


def test_the_list_filters_on_held_without_a_statement_per_row() -> None:
    """The counter's parked bills are one filter, read in bulk."""
    counter = _Counter()
    parked = [counter.draft() for _ in range(3)]
    loose = counter.draft()
    for bill in parked:
        counter.bills.hold_invoice(
            bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )

    def listed(is_held: bool | None, page_size: int = 50) -> list[SalesInvoice]:
        """List the firm's bills through the held filter."""
        rows, _ = counter.bills.list_invoices(
            firm_scope=counter.firm_id,
            filters=SalesInvoiceListFilters(is_held=is_held),
            page=1,
            page_size=page_size,
            search=None,
            sort_by="created_at",
            descending=True,
        )
        return rows

    assert {row.id for row in listed(True)} == {bill.id for bill in parked}
    assert [row.id for row in listed(False)] == [loose.id]
    assert len(listed(None)) == 4
    with _counting(counter.session) as one:
        counter.bills.invoice_responses(listed(True, page_size=1))
    with _counting(counter.session) as three:
        counter.bills.invoice_responses(listed(True))
    assert len(three) == len(one), f"{len(one)} at one row, {len(three)} at three"


# ---- shifts ---------------------------------------------------------------


def test_a_cashier_has_one_open_shift_and_another_cashier_may_open() -> None:
    """The second open is refused by name; the till next door is its own."""
    counter = _Counter()
    first = counter.open()
    assert first.shift_number == "SHIFT-000001"
    assert first.cash_account_id == counter.account(ControlAccountPurpose.CASH)
    assert first.branch_id == counter.setup.branch.id
    assert len(counter.audits("counter_shift.opened")) == 1

    with pytest.raises(ConflictError, match="SHIFT-000001"):
        counter.open()
    other = counter.open(actor=uuid4())
    assert other.shift_number == "SHIFT-000002"

    current = counter.shifts.current(
        firm_id=counter.firm_id, cashier_id=counter.cashier
    )
    assert current is not None
    assert current.id == first.id
    assert counter.shifts.current(firm_id=counter.firm_id, cashier_id=uuid4()) is None

    # Closed, the cashier may open the next one.
    counter.close(first, "500")
    assert counter.open().shift_number == "SHIFT-000003"


def test_a_cash_account_that_is_not_an_asset_is_refused() -> None:
    """A till's cash cannot be booked to income."""
    counter = _Counter()
    with pytest.raises(ValidationError, match="cannot hold a till's cash"):
        counter.shifts.open(
            CounterShiftOpen(
                opening_float=Decimal("0"),
                cash_account_id=counter.account(ControlAccountPurpose.SALES_REVENUE),
            ),
            firm_id=counter.firm_id,
            actor_id=counter.cashier,
        )


def test_a_bill_paid_at_the_counter_is_stamped_and_summed_by_mode() -> None:
    """Expected cash is the float and the cash tenders, and nothing else."""
    counter = _Counter()
    shift = counter.open("500")
    split = counter.sell(cash="60", upi="40")
    cash = counter.sell(cash="100")
    credit = counter.bills.approve_invoice(
        counter.draft().id, firm_scope=counter.firm_id, actor_id=counter.cashier
    )

    assert split.counter_shift_id == shift.id
    assert cash.counter_shift_id == shift.id
    assert credit.counter_shift_id is None, "no money was taken at the counter"

    view = counter.shifts.response(shift)
    assert view.summary.bills == 2
    assert view.summary.total_billed == Decimal("200.00")
    assert view.summary.tenders == {
        "CASH": Decimal("160.00"),
        "UPI": Decimal("40.00"),
        "CARD": Decimal("0.00"),
        "BANK_TRANSFER": Decimal("0.00"),
    }
    assert view.opening_float == Decimal("500.00")
    assert view.expected_cash == Decimal("660.00")
    assert view.status is CounterShiftStatus.OPEN
    assert view.counted_cash is None


def test_a_bill_with_one_method_and_no_tenders_counts_by_that_method() -> None:
    """`received_now_amount` alone is cash unless it says bank."""
    counter = _Counter()
    shift = counter.open("0")
    for method in ("CASH", "BANK"):
        data = counter.setup.bare_bill(Decimal("1")).model_copy(
            update={
                "received_now_amount": Decimal("100"),
                "received_now_method": method,
            }
        )
        bill = counter.bills.create_invoice(
            data, firm_id=counter.firm_id, actor_id=counter.cashier
        )
        counter.bills.approve_invoice(
            bill.id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )

    view = counter.shifts.response(shift)
    assert view.summary.bills == 2
    assert view.summary.tenders["CASH"] == Decimal("100.00")
    assert view.summary.tenders["BANK_TRANSFER"] == Decimal("100.00")
    assert view.expected_cash == Decimal("100.00")


def test_somebody_with_no_shift_still_approves_a_counter_bill() -> None:
    """Shifts are optional: the bill posts and is stamped with none."""
    counter = _Counter()
    bill = counter.sell(cash="100")
    assert bill.status == SalesInvoiceStatus.APPROVED.value
    assert bill.counter_shift_id is None

    # And a bill approved by somebody else is not put in this cashier's till.
    shift = counter.open()
    other = counter.sell(cash="100", actor=uuid4())
    assert other.counter_shift_id is None
    assert counter.shifts.response(shift).summary.bills == 0


def _legs(counter: _Counter, entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return a journal's legs by account as (debit, credit)."""
    return {
        line.ledger_account_id: (
            Decimal(str(line.debit_amount)),
            Decimal(str(line.credit_amount)),
        )
        for line in counter.session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
        )
    }


def test_closing_short_debits_cash_short_and_over() -> None:
    """Ten rupees missing: Dr Cash short and over / Cr the till's cash."""
    counter = _Counter()
    shift = counter.open("500")
    counter.sell(cash="100")

    closed = counter.close(shift, "590")
    assert closed.status == CounterShiftStatus.CLOSED.value
    assert closed.expected_cash == Decimal("600.00")
    assert closed.counted_cash == Decimal("590.00")
    assert closed.difference == Decimal("-10.00")
    assert closed.closed_by == counter.cashier
    assert closed.closing_note == "End of day"
    assert closed.difference_journal_entry_id is not None

    entry = counter.session.get(JournalEntry, closed.difference_journal_entry_id)
    assert entry is not None
    assert entry.reference_number == "SHIFT-000001"
    assert (entry.source_module, entry.source_id) == ("counter_shift", shift.id)
    assert entry.status == "POSTED"
    assert _legs(counter, entry.id) == {
        counter.account(ControlAccountPurpose.CASH_SHORT_AND_OVER): (
            Decimal("10.00"),
            Decimal("0.00"),
        ),
        counter.account(ControlAccountPurpose.CASH): (
            Decimal("0.00"),
            Decimal("10.00"),
        ),
    }
    assert len(counter.audits("counter_shift.closed")) == 1
    with pytest.raises(ValidationError, match="already closed"):
        counter.close(shift, "590")


def test_closing_over_credits_it_and_each_shift_has_its_own_reference() -> None:
    """Five rupees extra: Dr cash / Cr Cash short and over, a second journal."""
    counter = _Counter()
    counter.close(counter.open("500"), "490")
    second = counter.open("500")
    counter.sell(cash="100")

    closed = counter.close(second, "605")
    assert closed.difference == Decimal("5.00")
    entry = counter.session.get(JournalEntry, closed.difference_journal_entry_id)
    assert entry is not None
    assert entry.reference_number == "SHIFT-000002"
    assert _legs(counter, entry.id) == {
        counter.account(ControlAccountPurpose.CASH): (
            Decimal("5.00"),
            Decimal("0.00"),
        ),
        counter.account(ControlAccountPurpose.CASH_SHORT_AND_OVER): (
            Decimal("0.00"),
            Decimal("5.00"),
        ),
    }
    references = counter.session.scalars(
        select(JournalEntry.reference_number).where(
            JournalEntry.source_module == "counter_shift"
        )
    ).all()
    assert sorted(references) == ["SHIFT-000001", "SHIFT-000002"]


def test_closing_exact_posts_nothing() -> None:
    """A drawer that agrees with the books needs no journal."""
    counter = _Counter()
    shift = counter.open("500")
    counter.sell(cash="100")

    closed = counter.close(shift, "600")
    assert closed.difference == Decimal("0.00")
    assert closed.difference_journal_entry_id is None
    assert (
        counter.session.scalars(
            select(JournalEntry).where(JournalEntry.source_module == "counter_shift")
        ).all()
        == []
    )
    view = counter.shifts.response(closed)
    assert view.expected_cash == Decimal("600.00")
    assert (view.counted_cash, view.difference) == (
        Decimal("600.00"),
        Decimal("0.00"),
    )


def test_a_difference_with_no_account_mapped_is_refused_and_nothing_closes() -> None:
    """The purpose is needed only when a difference is posted, and named."""
    counter = _Counter()
    shift = counter.open("500")
    mapping = counter.session.scalar(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == counter.firm_id,
            FirmControlAccount.purpose
            == ControlAccountPurpose.CASH_SHORT_AND_OVER.value,
        )
    )
    assert mapping is not None, "a new firm is seeded with the account"
    counter.session.delete(mapping)
    counter.session.commit()

    with pytest.raises(ValidationError, match="CASH_SHORT_AND_OVER"):
        counter.close(shift, "490")
    counter.session.rollback()
    counter.session.refresh(shift)
    assert shift.status == CounterShiftStatus.OPEN.value
    assert counter.close(shift, "500").status == CounterShiftStatus.CLOSED.value


def test_a_cancelled_bills_cash_drops_out_of_expected_cash() -> None:
    """The receipt is reversed, the bill cancelled, and the drawer owes less."""
    counter = _Counter()
    shift = counter.open("500")
    kept = counter.sell(cash="100")
    gone = counter.sell(cash="60", upi="40")
    assert counter.shifts.response(shift).expected_cash == Decimal("660.00")

    receipts = ReceiptService(counter.session)
    for tender in counter.bills.invoice_response(gone).received_now_tenders:
        assert tender.settlement_id is not None
        receipts.reverse(
            tender.settlement_id,
            firm_id=counter.firm_id,
            actor_id=counter.cashier,
            reason="Customer changed their mind",
        )
    counter.session.commit()
    # The money went back the moment the receipts were reversed.
    assert counter.shifts.response(shift).expected_cash == Decimal("600.00")

    counter.bills.cancel_invoice(
        gone.id, firm_scope=counter.firm_id, actor_id=counter.cashier, reason="Void"
    )
    view = counter.shifts.response(shift)
    assert view.summary.bills == 1
    assert view.summary.total_billed == Decimal("100.00")
    assert view.summary.tenders["CASH"] == Decimal("100.00")
    assert view.summary.tenders["UPI"] == Decimal("0.00")
    assert view.expected_cash == Decimal("600.00")
    assert kept.counter_shift_id == shift.id


def test_only_the_cashier_or_an_approver_closes_a_shift() -> None:
    """Somebody else's till needs the code that approves sales."""
    counter = _Counter()
    shift = counter.open("500")
    stranger = uuid4()

    with pytest.raises(AuthorizationError, match="approve sales"):
        counter.shifts.close(
            shift.id,
            CounterShiftClose(counted_cash=Decimal("500")),
            firm_id=counter.firm_id,
            actor_id=stranger,
            now=EVENING,
        )
    closed = counter.shifts.close(
        shift.id,
        CounterShiftClose(counted_cash=Decimal("500")),
        firm_id=counter.firm_id,
        actor_id=stranger,
        may_close_others=True,
        now=EVENING,
    )
    assert closed.closed_by == stranger


def test_bills_still_held_are_reported_at_the_close_and_do_not_block_it() -> None:
    """A parked bill took no money; the close warns and goes ahead."""
    counter = _Counter()
    shift = counter.open("500")
    for _ in range(2):
        counter.bills.hold_invoice(
            counter.draft().id, firm_scope=counter.firm_id, actor_id=counter.cashier
        )
    # Somebody else's parked bill is not this cashier's to answer for.
    other = uuid4()
    counter.bills.hold_invoice(
        counter.draft(actor=other).id, firm_scope=counter.firm_id, actor_id=other
    )

    assert counter.shifts.response(shift).summary.held_bills == 2
    # On the clock, like the holds: the count is exact, so nothing posts.
    closed = counter.shifts.close(
        shift.id,
        CounterShiftClose(counted_cash=Decimal("500")),
        firm_id=counter.firm_id,
        actor_id=counter.cashier,
    )
    assert closed.status == CounterShiftStatus.CLOSED.value
    assert counter.shifts.response(closed).summary.held_bills == 2


def test_the_summary_costs_the_same_however_many_bills_the_shift_took() -> None:
    """Six bills cost no more statements than two, alone or on a page."""
    counter = _Counter()
    shift = counter.open("0")
    other = counter.open("0", actor=uuid4())
    for _ in range(2):
        counter.sell(cash="60", upi="40")
    with _counting(counter.session) as small:
        counter.shifts.response(shift)
    for _ in range(4):
        counter.sell(cash="60", upi="40")
    with _counting(counter.session) as large:
        view = counter.shifts.response(shift)
    assert view.summary.bills == 6
    assert len(large) == len(small), f"{len(small)} at 2 bills, {len(large)} at 6"

    with _counting(counter.session) as page:
        rows = counter.shifts.responses([shift, other])
    assert len(page) == len(small), "a page of shifts costs what one does"
    assert rows[0] == view, "a listed shift is the shift read alone"
    assert rows[1].summary.bills == 0


def test_the_list_filters_by_status_cashier_and_day() -> None:
    """The latest opened first, narrowed by what the caller asks."""
    counter = _Counter()
    first = counter.open()
    counter.close(first, "500")
    second = counter.open()
    other = uuid4()
    third = counter.open(actor=other)

    def ids(**filters: Any) -> list[UUID]:  # noqa: ANN401
        """List the shift ids a filter leaves."""
        rows, _ = counter.shifts.list_shifts(
            counter.firm_id, page=1, page_size=10, **filters
        )
        return [row.id for row in rows]

    assert set(ids()) == {first.id, second.id, third.id}
    assert ids(status=CounterShiftStatus.CLOSED) == [first.id]
    assert set(ids(status=CounterShiftStatus.OPEN)) == {second.id, third.id}
    assert ids(cashier_id=other) == [third.id]
    day = EVENING.date()
    assert len(ids(from_date=day, to_date=day)) == 3
    assert ids(from_date=day.replace(day=5)) == []
    assert ids(to_date=day.replace(day=3)) == []
    rows, total = counter.shifts.list_shifts(counter.firm_id, page=2, page_size=2)
    assert (len(rows), total) == (1, 3)


def test_the_shift_report_prints_as_a_pdf() -> None:
    """Open or closed, the report is a real PDF."""
    counter = _Counter()
    shift = counter.open("500")
    counter.sell(cash="60", upi="40")
    assert counter.shifts.report_pdf(shift.id, firm_id=counter.firm_id).startswith(
        b"%PDF"
    )
    counter.close(shift, "555")
    assert counter.shifts.report_pdf(shift.id, firm_id=counter.firm_id).startswith(
        b"%PDF"
    )


def test_the_routes_are_served_and_the_list_bounds_its_page() -> None:
    """An over-cap page is a 422 naming the limit, never a 500."""
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    bounds = {
        parameter["name"]: parameter["schema"]
        for parameter in paths["/api/v1/counter-shifts"]["get"]["parameters"]
    }
    assert bounds["page"]["minimum"] == 1
    assert bounds["page_size"]["minimum"] == 1
    assert bounds["page_size"]["maximum"] == MAX_PAGE_SIZE
    assert {"status", "cashier_id", "from_date", "to_date"} <= set(bounds)
    assert "post" in paths["/api/v1/counter-shifts/open"]
    assert "get" in paths["/api/v1/counter-shifts/current"]
    assert "get" in paths["/api/v1/counter-shifts/{shift_id}"]
    assert "post" in paths["/api/v1/counter-shifts/{shift_id}/close"]
    assert "get" in paths["/api/v1/counter-shifts/{shift_id}/report"]
    assert "post" in paths["/api/v1/sales-invoices/{invoice_id}/hold"]
    assert "post" in paths["/api/v1/sales-invoices/{invoice_id}/recall"]
    held = {
        parameter["name"]
        for parameter in paths["/api/v1/sales-invoices"]["get"]["parameters"]
    }
    assert "is_held" in held


def test_a_bill_goes_to_the_shift_of_the_cashier_who_made_it() -> None:
    """D-SELL-51: the till that took the money is the maker's, not the approver's.

    Counter staff raise bills and hold no approve code, so a manager approves
    them. Stamping the approver's shift left the cashier's drawer at its float
    and put the cash in the manager's shift, or in none.
    """
    counter = _Counter()
    manager = uuid4()
    till = counter.open("500")
    tender = [SalesInvoiceTenderWrite(mode="CASH", amount=Decimal("100"))]

    by_manager = counter.bills.approve_invoice(
        counter.draft(tender).id, firm_scope=counter.firm_id, actor_id=manager
    )
    assert by_manager.counter_shift_id == till.id
    assert counter.shifts.response(till).expected_cash == Decimal("600.00")

    # A manager with a till of their own still does not take the cashier's bill.
    own = counter.open("0", actor=manager)
    again = counter.bills.approve_invoice(
        counter.draft(tender).id, firm_scope=counter.firm_id, actor_id=manager
    )
    assert again.counter_shift_id == till.id
    assert counter.shifts.response(own).expected_cash == Decimal("0.00")

    # A bill whose maker has no till open falls to the approver's.
    counter.close(till, "700")
    fallen = counter.bills.approve_invoice(
        counter.draft(tender).id, firm_scope=counter.firm_id, actor_id=manager
    )
    assert fallen.counter_shift_id == own.id
