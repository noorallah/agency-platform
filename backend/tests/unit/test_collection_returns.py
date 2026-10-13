"""The collector's end-of-day line on a handed-out bill (backlog 124, M6).

One line per handed-out bill per day: collected, part, promised or not
collected. The line states; a receipt records. A day's sheet adds up when
every rupee stated is in a receipt.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import func, select

from app.collections.api.router import my_day_sheet, record_my_return
from app.collections.models import CollectionReturn, PaymentPromise
from app.collections.schemas import (
    CollectionDaySheet,
    CollectionReturnCreate,
    CollectionReturnResponse,
    ReturnOutcome,
    ReturnPaymentMode,
)
from app.collections.services import BillHandoverService, CollectionReturnService
from app.common.firm_metadata import firm_today
from app.common.scope import ResolvedFirmScope
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.customers.schemas import CreditControlSettingsWrite, CreditEnforcement
from app.customers.services.credit_control import CreditControlService
from app.finance.models import JournalEntry
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement
from app.settlements.services import ReceiptService
from tests.unit import test_sales_order_module as sales
from tests.unit.test_bill_handovers import TODAY, _give, _out, _take_back
from tests.unit.test_collection_follow_up import (
    _actor,
    _bill,
    _customer,
    _member,
    _total,
    _world,
)
from tests.unit.test_sales_chain_synthesis import _Firm


def _switch(setup: _Firm, on: bool) -> None:
    """Set the firm's switch: a collector's own line records the receipt."""
    CreditControlService(setup.session).update_settings(
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.WARN,
            warn_at_percent=Decimal("80"),
            block_at_percent=Decimal("100"),
            collector_records_receipt=on,
        ),
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
    )


def _line(
    setup: _Firm,
    bill: SalesInvoice,
    outcome: ReturnOutcome,
    *,
    by: UUID | None = None,
    amount: Decimal | None = None,
    promised_on: date | None = None,
    day: date | None = None,
    mode: ReturnPaymentMode | None = None,
    today: date = TODAY,
) -> CollectionReturnResponse:
    """Write the day's line on a handed-out bill.

    ``by`` is the collector writing his own; omitted, the office writes it.
    """
    return CollectionReturnService(setup.session).record(
        CollectionReturnCreate(
            handover_id=_out(setup)[bill.id].id,
            outcome=outcome,
            amount_collected=amount,
            promised_on=promised_on,
            return_date=day,
            payment_mode=mode,
        ),
        firm_id=setup.firm.id,
        actor_id=by or _actor(setup),
        own=by is not None,
        today=today,
    )


def _sheet(
    setup: _Firm, collector: UUID | None = None, day: date = TODAY
) -> CollectionDaySheet:
    """Read the day's sheet."""
    return CollectionReturnService(setup.session).day_sheet(
        setup.firm.id, day=day, collector_id=collector
    )


def _owes(setup: _Firm, bill: SalesInvoice) -> Decimal:
    """Return what the bill owes now, from Record Receipt's own list."""
    return next(
        (
            record.outstanding_amount
            for record in ReceiptService(setup.session).outstanding_invoices(
                firm_id=setup.firm.id, party_id=bill.customer_id
            )
            if record.invoice_id == bill.id
        ),
        Decimal("0.00"),
    )


def _count(setup: _Firm, model: type) -> int:
    """Count the rows of a table."""
    return int(setup.session.scalar(select(func.count()).select_from(model)) or 0)


# ---- the line and its receipt ----------------------------------------------


def test_the_offices_line_records_the_receipt_and_the_sheet_adds_up() -> None:
    """Collected in full, written in the office: one receipt, nothing owed."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)

    line = _line(setup, bill, ReturnOutcome.COLLECTED)

    assert line.outcome == ReturnOutcome.COLLECTED
    assert line.amount_collected == _total(bill)
    assert line.outstanding_before == _total(bill)
    assert line.payment_mode == ReturnPaymentMode.CASH
    assert line.settlement_number is not None
    assert line.receipt_amount == _total(bill)
    assert line.collector_name == "Ravi Collector"
    assert _owes(setup, bill) == Decimal("0.00")
    receipt = setup.session.get(Settlement, line.settlement_id)
    assert receipt is not None
    assert receipt.settlement_date == TODAY
    assert Decimal(str(receipt.amount)) == _total(bill)
    assert receipt.narration == "Collected by Ravi Collector"
    sheet = _sheet(setup, ravi)
    assert sheet.collected_bills == 1
    assert sheet.amount_stated == sheet.amount_receipted == _total(bill)
    assert sheet.amount_not_receipted == Decimal("0.00")
    assert sheet.adds_up is True


def test_a_collectors_own_line_states_and_the_office_records_the_receipt() -> None:
    """Switch off: his line moves nothing until the office records it."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    receipts, journals = _count(setup, Settlement), _count(setup, JournalEntry)

    line = _line(setup, bill, ReturnOutcome.COLLECTED, by=ravi)

    assert line.settlement_id is None
    assert line.receipt_amount == Decimal("0.00")
    assert _count(setup, Settlement) == receipts
    assert _count(setup, JournalEntry) == journals
    assert _owes(setup, bill) == _total(bill)
    sheet = _sheet(setup, ravi)
    assert sheet.collector_records_receipt is False
    assert sheet.amount_stated == _total(bill)
    assert sheet.amount_receipted == Decimal("0.00")
    assert sheet.amount_not_receipted == _total(bill)
    assert sheet.adds_up is False

    recorded = CollectionReturnService(setup.session).record_receipt(
        line.id, firm_id=setup.firm.id, actor_id=_actor(setup)
    )

    assert recorded.settlement_number is not None
    assert recorded.receipt_amount == _total(bill)
    assert _owes(setup, bill) == Decimal("0.00")
    assert _sheet(setup, ravi).adds_up is True
    with pytest.raises(ConflictError, match="already records"):
        CollectionReturnService(setup.session).record_receipt(
            line.id, firm_id=setup.firm.id, actor_id=_actor(setup)
        )


def test_the_firms_switch_lets_a_collectors_line_record_the_receipt() -> None:
    """Switch on: his own line is the receipt."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    _switch(setup, True)

    line = _line(
        setup,
        bill,
        ReturnOutcome.PART,
        by=ravi,
        amount=Decimal("100.00"),
        mode=ReturnPaymentMode.UPI,
    )

    assert line.settlement_id is not None
    assert line.receipt_amount == Decimal("100.00")
    assert line.payment_mode == ReturnPaymentMode.UPI
    assert _owes(setup, bill) == _total(bill) - Decimal("100.00")
    sheet = _sheet(setup, ravi)
    assert sheet.collector_records_receipt is True
    assert sheet.part_bills == 1
    assert sheet.adds_up is True


def test_the_switch_is_kept_when_the_settings_are_saved_without_it() -> None:
    """Absent means leave alone: the credit screen does not switch it off."""
    setup = _world()
    _switch(setup, True)
    service = CreditControlService(setup.session)

    answer = service.update_settings(
        CreditControlSettingsWrite(
            enforcement=CreditEnforcement.WARN,
            warn_at_percent=Decimal("70"),
            block_at_percent=Decimal("100"),
        ),
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
    )

    assert answer.collector_records_receipt is True
    assert answer.warn_at_percent == Decimal("70")


def test_a_firm_that_never_chose_does_not_let_collectors_record() -> None:
    """No settings row reads as off."""
    setup = _world()

    assert (
        CreditControlService(setup.session)
        .settings_response(setup.firm.id)
        .collector_records_receipt
        is False
    )
    assert (
        CollectionReturnService(setup.session).collector_records_receipt(setup.firm.id)
        is False
    )


# ---- part, promised, not collected -----------------------------------------


def test_part_collected_takes_less_than_the_bill_and_may_promise_the_rest() -> None:
    """A part line records its receipt and a promise for what is left."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    later = TODAY + timedelta(days=5)

    line = _line(
        setup,
        bill,
        ReturnOutcome.PART,
        amount=Decimal("150.00"),
        promised_on=later,
    )

    rest = _total(bill) - Decimal("150.00")
    assert line.receipt_amount == Decimal("150.00")
    assert line.promised_on == later
    assert line.promised_amount == rest
    assert _owes(setup, bill) == rest
    promise = setup.session.get(PaymentPromise, line.payment_promise_id)
    assert promise is not None
    assert promise.sales_invoice_id == bill.id
    assert promise.collector_id == ravi
    assert promise.recorded_on == TODAY


def test_the_amount_must_fit_the_outcome() -> None:
    """Part is less than the bill; in full is exactly the bill."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)

    with pytest.raises(ValidationError, match="Part collected is less"):
        _line(setup, bill, ReturnOutcome.PART, amount=_total(bill))
    with pytest.raises(ValidationError, match="Collected in full is exactly"):
        _line(setup, bill, ReturnOutcome.COLLECTED, amount=Decimal("1.00"))
    assert _count(setup, CollectionReturn) == 0
    assert _owes(setup, bill) == _total(bill)


def test_promised_writes_a_promise_and_no_money() -> None:
    """A promised line is the promise the Promises screen shows."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    receipts = _count(setup, Settlement)

    line = _line(
        setup,
        bill,
        ReturnOutcome.PROMISED,
        by=ravi,
        promised_on=TODAY + timedelta(days=2),
    )

    assert line.amount_collected == Decimal("0.00")
    assert line.payment_mode is None
    assert line.promised_amount == _total(bill)
    assert _count(setup, Settlement) == receipts
    assert _count(setup, PaymentPromise) == 1
    sheet = _sheet(setup, ravi)
    assert sheet.promised_bills == 1
    assert sheet.amount_stated == Decimal("0.00")
    assert sheet.adds_up is True


def test_not_collected_writes_the_line_and_nothing_else() -> None:
    """Nothing taken, nothing promised: a line and no more."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    receipts = _count(setup, Settlement)

    line = _line(setup, bill, ReturnOutcome.NOT_COLLECTED, by=ravi)

    assert line.amount_collected == Decimal("0.00")
    assert line.settlement_id is None
    assert line.payment_promise_id is None
    assert _count(setup, Settlement) == receipts
    assert _count(setup, PaymentPromise) == 0
    assert _sheet(setup, ravi).not_collected_bills == 1


def test_the_request_refuses_figures_its_outcome_does_not_carry() -> None:
    """A line's fields are checked against what it says happened."""
    handover = sales.uuid4()

    def build(**fields: object) -> CollectionReturnCreate:
        """Build a line on a made-up handover."""
        return CollectionReturnCreate(handover_id=handover, **fields)  # type: ignore[arg-type]

    with pytest.raises(SchemaError, match="how much was collected"):
        build(outcome="PART")
    with pytest.raises(SchemaError, match="Nothing was collected"):
        build(outcome="NOT_COLLECTED", amount_collected="10")
    with pytest.raises(SchemaError, match="Nothing was collected"):
        build(outcome="PROMISED", promised_on="2026-08-25", payment_mode="CASH")
    with pytest.raises(SchemaError, match="which day was promised"):
        build(outcome="PROMISED")
    with pytest.raises(SchemaError, match="promised day goes with"):
        build(outcome="COLLECTED", promised_on="2026-08-25")
    with pytest.raises(SchemaError):
        build(outcome="PART", amount_collected="0")
    with pytest.raises(SchemaError):
        build(outcome="LOST")
    assert build(outcome="COLLECTED").amount_collected is None


# ---- whose line, which day --------------------------------------------------


def test_a_collector_writes_only_his_own_bills_and_only_today() -> None:
    """Another bag reads as no bill; a past day is the office's."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill, handed_on=TODAY - timedelta(days=3))

    with pytest.raises(ResourceNotFoundError):
        _line(setup, bill, ReturnOutcome.NOT_COLLECTED, by=sita)
    with pytest.raises(ValidationError, match="writes today's line"):
        _line(
            setup,
            bill,
            ReturnOutcome.NOT_COLLECTED,
            by=ravi,
            day=TODAY - timedelta(days=1),
        )
    assert _count(setup, CollectionReturn) == 0

    office = _line(
        setup, bill, ReturnOutcome.NOT_COLLECTED, day=TODAY - timedelta(days=1)
    )

    assert office.return_date == TODAY - timedelta(days=1)


def test_a_line_is_for_a_day_the_bill_was_out() -> None:
    """Not tomorrow, not before it went out, and not once it is back."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill, handed_on=TODAY - timedelta(days=1))

    with pytest.raises(ValidationError, match="today or a past day"):
        _line(setup, bill, ReturnOutcome.NOT_COLLECTED, day=TODAY + timedelta(days=1))
    with pytest.raises(ValidationError, match="no line before then"):
        _line(setup, bill, ReturnOutcome.NOT_COLLECTED, day=TODAY - timedelta(days=2))
    handover = _out(setup)[bill.id].id
    _take_back(setup, bill)
    with pytest.raises(ConflictError, match="taken back"):
        CollectionReturnService(setup.session).record(
            CollectionReturnCreate(
                handover_id=handover, outcome=ReturnOutcome.NOT_COLLECTED
            ),
            firm_id=setup.firm.id,
            actor_id=_actor(setup),
            own=False,
            today=TODAY,
        )


def test_one_line_a_day_and_one_each_day() -> None:
    """A second line the same day is refused; the next day has its own."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill, handed_on=TODAY - timedelta(days=1))
    _line(setup, bill, ReturnOutcome.NOT_COLLECTED, day=TODAY - timedelta(days=1))

    with pytest.raises(ConflictError, match="already has a line"):
        _line(setup, bill, ReturnOutcome.NOT_COLLECTED, day=TODAY - timedelta(days=1))
    _line(setup, bill, ReturnOutcome.NOT_COLLECTED, by=ravi)

    assert _count(setup, CollectionReturn) == 2
    assert len(_sheet(setup, ravi).rows) == 1
    assert len(_sheet(setup, ravi, TODAY - timedelta(days=1)).rows) == 1


def test_a_bill_paid_meanwhile_takes_no_money_line() -> None:
    """A bill that owes nothing is not collected again."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill, handed_on=TODAY - timedelta(days=1))
    _line(setup, bill, ReturnOutcome.COLLECTED, day=TODAY - timedelta(days=1))

    with pytest.raises(ValidationError, match="owes nothing now"):
        _line(setup, bill, ReturnOutcome.COLLECTED, by=ravi)
    with pytest.raises(ValidationError, match="owes nothing now"):
        _line(
            setup,
            bill,
            ReturnOutcome.PROMISED,
            by=ravi,
            promised_on=TODAY + timedelta(days=1),
        )


# ---- withdrawing ------------------------------------------------------------


def test_a_line_is_withdrawn_with_its_promise_and_written_again() -> None:
    """Withdrawing keeps the row, takes the promise back, frees the day."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    line = _line(
        setup,
        bill,
        ReturnOutcome.PROMISED,
        by=ravi,
        promised_on=TODAY + timedelta(days=2),
    )
    service = CollectionReturnService(setup.session)

    with pytest.raises(ResourceNotFoundError):
        service.withdraw(
            line.id, "not mine", firm_id=setup.firm.id, actor_id=sita, own=True
        )
    gone = service.withdraw(
        line.id, "wrong bill", firm_id=setup.firm.id, actor_id=ravi, own=True
    )

    assert gone.cancelled_at is not None
    assert gone.cancel_reason == "wrong bill"
    promise = setup.session.get(PaymentPromise, line.payment_promise_id)
    assert promise is not None
    assert promise.cancelled_at is not None
    assert _sheet(setup, ravi).rows == []
    with pytest.raises(ConflictError, match="already withdrawn"):
        service.withdraw(
            line.id, "again", firm_id=setup.firm.id, actor_id=ravi, own=True
        )
    again = _line(setup, bill, ReturnOutcome.NOT_COLLECTED, by=ravi)
    assert again.id != line.id
    assert _count(setup, CollectionReturn) == 2


def test_a_line_with_a_live_receipt_is_not_withdrawn() -> None:
    """The receipt is reversed first; then the line goes, or is recorded anew."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    line = _line(setup, bill, ReturnOutcome.COLLECTED)
    service = CollectionReturnService(setup.session)

    with pytest.raises(ConflictError, match="Reverse the receipt first"):
        service.withdraw(
            line.id, "typo", firm_id=setup.firm.id, actor_id=_actor(setup), own=False
        )
    assert line.settlement_id is not None
    ReceiptService(setup.session).reverse(
        line.settlement_id,
        firm_id=setup.firm.id,
        actor_id=_actor(setup),
        reason="wrong customer",
        on=TODAY,
    )
    setup.session.commit()

    sheet = _sheet(setup, ravi)
    assert sheet.rows[0].receipt_reversed is True
    assert sheet.amount_receipted == Decimal("0.00")
    assert sheet.adds_up is False
    assert _owes(setup, bill) == _total(bill)

    again = service.record_receipt(
        line.id, firm_id=setup.firm.id, actor_id=_actor(setup)
    )
    assert again.settlement_id != line.settlement_id
    assert again.receipt_reversed is False
    assert _sheet(setup, ravi).adds_up is True


def test_the_receipt_is_not_recorded_for_a_line_that_took_no_money() -> None:
    """A promise or a nothing has no receipt to record."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    bill = _bill(setup)
    _give(setup, ravi, bill)
    line = _line(setup, bill, ReturnOutcome.NOT_COLLECTED, by=ravi)

    with pytest.raises(ValidationError, match="Nothing was collected"):
        CollectionReturnService(setup.session).record_receipt(
            line.id, firm_id=setup.firm.id, actor_id=_actor(setup)
        )
    with pytest.raises(ResourceNotFoundError):
        CollectionReturnService(setup.session).record_receipt(
            sales.uuid4(), firm_id=setup.firm.id, actor_id=_actor(setup)
        )


# ---- the sheet and the collector's list -------------------------------------


def test_the_days_sheet_counts_each_outcome_and_the_bills_with_no_line() -> None:
    """Four bills, three lines: the sheet says which and what is missing."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    second, third = _customer(setup, "C-RET-2"), _customer(setup, "C-RET-3")
    paid, part, silent = _bill(setup), _bill(setup, second), _bill(setup, third)
    sitas = _bill(setup, third)
    _give(setup, ravi, paid, part, silent)
    _give(setup, sita, sitas)
    _line(setup, paid, ReturnOutcome.COLLECTED)
    _line(setup, part, ReturnOutcome.PART, by=ravi, amount=Decimal("50.00"))
    _line(setup, sitas, ReturnOutcome.NOT_COLLECTED, by=sita)

    ravis, everyone = _sheet(setup, ravi), _sheet(setup)

    assert {row.invoice_id for row in ravis.rows} == {paid.id, part.id}
    assert ravis.collector_name == "Ravi Collector"
    assert (ravis.collected_bills, ravis.part_bills) == (1, 1)
    assert ravis.bills_without_a_line == 1
    assert ravis.amount_stated == _total(paid) + Decimal("50.00")
    assert ravis.amount_receipted == _total(paid)
    assert ravis.amount_not_receipted == Decimal("50.00")
    assert ravis.adds_up is False
    assert len(everyone.rows) == 3
    assert everyone.collector_id is None
    assert everyone.not_collected_bills == 1
    assert everyone.bills_without_a_line == 1
    assert _sheet(setup, ravi, TODAY - timedelta(days=1)).rows == []


def test_a_collectors_list_shows_todays_line_on_his_bill() -> None:
    """My Bills carries the line written today, and only on his own bills."""
    setup = _world()
    ravi = _member(setup, "Ravi Collector")
    carried, other = _bill(setup), _bill(setup)
    _give(setup, ravi, carried)
    line = _line(setup, carried, ReturnOutcome.PART, by=ravi, amount=Decimal("40.00"))

    rows = {
        row.invoice_id: row
        for row in BillHandoverService(setup.session).my_bills(
            setup.firm.id, collector_id=ravi, today=TODAY
        )
    }

    assert rows[carried.id].return_id == line.id
    assert rows[carried.id].return_outcome == ReturnOutcome.PART
    assert rows[carried.id].return_amount == Decimal("40.00")
    assert rows[other.id].return_id is None
    assert rows[other.id].return_outcome is None
    tomorrow = {
        row.invoice_id: row
        for row in BillHandoverService(setup.session).my_bills(
            setup.firm.id, collector_id=ravi, today=TODAY + timedelta(days=1)
        )
    }
    assert tomorrow[carried.id].return_id is None


# ---- the routes and the role -------------------------------------------------


def test_the_collectors_routes_take_him_from_the_token() -> None:
    """His own line and his own sheet: the caller, whatever else is out."""
    setup = _world()
    ravi, sita = _member(setup, "Ravi Collector"), _member(setup, "Sita Collector")
    second = _customer(setup, "C-RET-R")
    ravis, sitas = _bill(setup), _bill(setup, second)
    _give(setup, ravi, ravis)
    _give(setup, sita, sitas)
    today = firm_today(setup.session, setup.firm.id)

    def scope(actor: UUID) -> ResolvedFirmScope:
        """Build the collector's scope."""
        return ResolvedFirmScope(
            principal=sales._principal(
                actor, {"COLLECTION_OWN_VIEW", "COLLECTION_OWN_RECORD"}
            ),
            firm_id=setup.firm.id,
        )

    answer = record_my_return(
        data=CollectionReturnCreate(
            handover_id=_out(setup)[ravis.id].id,
            outcome=ReturnOutcome.NOT_COLLECTED,
            note="shop shut",
        ),
        scope=scope(ravi),
        db=setup.session,
    )
    with pytest.raises(ResourceNotFoundError):
        record_my_return(
            data=CollectionReturnCreate(
                handover_id=_out(setup)[sitas.id].id,
                outcome=ReturnOutcome.NOT_COLLECTED,
            ),
            scope=scope(ravi),
            db=setup.session,
        )

    assert answer.data.return_date == today
    assert answer.data.note == "shop shut"
    assert answer.data.recorded_by == ravi
    mine = my_day_sheet(scope=scope(ravi), day=None, db=setup.session).data
    hers = my_day_sheet(scope=scope(sita), day=None, db=setup.session).data
    assert [row.invoice_id for row in mine.rows] == [ravis.id]
    assert mine.collector_id == ravi
    assert hers.rows == []
    assert hers.bills_without_a_line == 1


def test_the_bill_collector_role_may_write_his_line_and_no_receipt() -> None:
    """The code is his; the receipt codes are not."""
    collector = ROLE_PERMISSION_CODES["BILL_COLLECTOR"]

    assert "COLLECTION_OWN_RECORD" in PERMISSION_GROUPS["accounting"]
    assert collector == {"COLLECTION_OWN_VIEW", "COLLECTION_OWN_RECORD"}
    assert "COLLECTION_OWN_RECORD" in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "COLLECTION_OWN_RECORD" in ROLE_PERMISSION_CODES["ACCOUNTANT"]
    assert "COLLECTION_OWN_RECORD" not in ROLE_PERMISSION_CODES["VIEWER"]
    assert "COLLECTION_OWN_RECORD" not in ROLE_PERMISSION_CODES["CASHIER"]
