"""Credit a return or credit note leaves on a paid bill, set against another.

A sales return off a bill that was already paid has nothing left on that bill
to come off, so the customer's account held the money as an advance that
belonged to no receipt: `allocate` could not reach it, and the customer owed
826.00 on one line and was owed 826.00 on another (D-PRC-75, PRCQ-74). These
drive the receivable twin of `test_supplier_credit.py`.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas.opening_bill import CustomerOpeningBillWrite
from app.customers.services import CustomerStatementService
from app.customers.services.opening_bill_service import CustomerOpeningBillService
from app.finance.models import GLPosting, JournalEntry
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services import SalesInvoiceService
from app.sales_return.models import SalesReturn
from app.sales_return.services import SalesReturnService
from app.settlements.api.router import (
    apply_customer_unapplied_credit,
    customer_unapplied_credits,
    reverse_customer_credit,
)
from app.settlements.models import CustomerCreditApplication, Settlement
from app.settlements.schemas import (
    CustomerCreditApplyRequest,
    CustomerCreditReverseRequest,
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService, RefundService
from app.settlements.services.customer_credits import (
    CustomerCredit,
    apply_customer_credit,
    customer_credits,
    reverse_customer_credit_application,
)
from app.settlements.services.net_sales import collected_net, sum_of
from app.settlements.services.settlement_service import settled_against
from tests.unit.test_sales_return_module import (
    _credit_note_on,
    _Dispatch,
    _on_the_line_of,
    _returned,
    _session_factory,
)

PAID_ON = date(2026, 8, 4)
APPLIED_ON = date(2026, 8, 6)


def _receipt(
    setup: _Dispatch, amount: str, *bills: tuple[UUID, str], on: date = PAID_ON
) -> Settlement:
    """Record a receipt from the customer, allocated as told."""
    row = ReceiptService(setup.session).create(
        SettlementCreate(
            party_id=setup.customer.id,
            settlement_date=on,
            amount=Decimal(amount),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(invoice_id=bill_id, amount=Decimal(value))
                for bill_id, value in bills
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.session.commit()
    return row


def _refund(
    setup: _Dispatch, amount: str, *, source_id: UUID | None = None
) -> Settlement:
    """Hand money back to the customer."""
    row = RefundService(setup.session).create(
        SettlementCreate(
            party_id=setup.customer.id,
            settlement_date=APPLIED_ON,
            amount=Decimal(amount),
            method=SettlementMethodEnum.CASH,
            credit_source_id=source_id,
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.session.commit()
    return row


def _second_bill(setup: _Dispatch) -> SalesInvoice:
    """Bill and approve the other two units of the note."""
    row = SalesInvoiceService(setup.session).approve_invoice(
        setup.bill(Decimal("2")).id,
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )
    setup.session.commit()
    return row


def _paid_then_returned(
    session: Session,
) -> tuple[_Dispatch, SalesReturn, SalesInvoice]:
    """Pay a bill of 200.00 in full, return one unit, then raise a second bill.

    The return's 100.00 finds nothing owed, so all of it is held on account;
    the second bill of 200.00 is raised afterwards.
    """
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    return setup, returned, _second_bill(setup)


def _balances(setup: _Dispatch) -> tuple[Decimal, Decimal]:
    """Return what the customer owes and what they hold on account."""
    setup.session.expire_all()
    customer = setup.session.get(Customer, setup.customer.id)
    assert customer is not None
    return (
        Decimal(str(customer.current_outstanding)),
        Decimal(str(customer.unapplied_advance_balance)),
    )


def _owes(setup: _Dispatch, bill_id: UUID) -> Decimal:
    """Return what Record Receipt offers a bill as still owing; 0 if not listed."""
    for record in ReceiptService(setup.session).outstanding_invoices(
        firm_id=setup.firm.id, party_id=setup.customer.id
    ):
        if record.invoice_id == bill_id:
            return record.outstanding_amount
    return Decimal("0")


def _credits(setup: _Dispatch) -> list[CustomerCredit]:
    """Return the customer's credits."""
    return customer_credits(
        setup.session, firm_id=setup.firm.id, customer_id=setup.customer.id
    )


def _apply(
    setup: _Dispatch,
    source_id: UUID,
    bill_id: UUID,
    amount: str,
    *,
    on: date | None = APPLIED_ON,
) -> CustomerCredit:
    """Set part of a credit against a bill and commit."""
    credit = apply_customer_credit(
        setup.session,
        firm_id=setup.firm.id,
        source_id=source_id,
        invoice_id=bill_id,
        amount=Decimal(amount),
        applied_on=on,
        actor_id=setup.actor_id,
    )
    setup.session.commit()
    return credit


def _trial_balance(session: Session) -> dict[UUID, Decimal]:
    """Return every account's debit less credit."""
    return {
        account_id: Decimal(str(total))
        for account_id, total in session.execute(
            select(
                GLPosting.ledger_account_id,
                func.sum(GLPosting.debit_amount - GLPosting.credit_amount),
            ).group_by(GLPosting.ledger_account_id)
        ).all()
    }


def _journals(session: Session) -> int:
    """Count the journal entries in the store."""
    return int(session.scalar(select(func.count()).select_from(JournalEntry)) or 0)


def _applications(session: Session) -> list[CustomerCreditApplication]:
    """Return every application row, oldest first."""
    return list(
        session.scalars(
            select(CustomerCreditApplication).order_by(
                CustomerCreditApplication.created_at.asc()
            )
        ).all()
    )


def test_credit_left_on_a_paid_bill_is_set_against_a_later_bill() -> None:
    """The orphan advance, end to end: listed, applied, and nothing posted."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)

    # The state PRCQ-74 found: owing on one line, owed on another.
    assert _balances(setup) == (Decimal("200.00"), Decimal("100.00"))
    [credit] = _credits(setup)
    assert credit.source_id == returned.id
    assert credit.source_type == "SALES_RETURN"
    assert credit.credit_amount == Decimal("100.00")
    assert credit.available_amount == Decimal("100.00")
    assert credit.held_amount == Decimal("100.00")

    journals, books = _journals(session), _trial_balance(session)
    after = _apply(setup, returned.id, second.id, "100")

    assert after.available_amount == Decimal("0.00")
    assert after.applied_to == [second.invoice_number]
    assert _owes(setup, second.id) == Decimal("100.00")
    assert _balances(setup) == (Decimal("100.00"), Decimal("0.00"))
    # One customer, one control account: no journal, the books unmoved.
    assert _journals(session) == journals
    assert _trial_balance(session) == books
    # One receivable row, named after the application, carries the deltas.
    [row] = _applications(session)
    written = session.get(CustomerReceivableTransaction, row.receivable_transaction_id)
    assert written is not None
    assert written.transaction_type == "ADVANCE_APPLY"
    assert written.reference_type == "customer_credit_application"
    assert written.reference_id == row.id
    assert Decimal(str(written.outstanding_delta)) == Decimal("-100.00")
    assert Decimal(str(written.advance_delta)) == Decimal("-100.00")
    assert session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "customer_credit.applied")
    )


def test_every_reader_of_what_a_bill_owes_counts_the_credit() -> None:
    """Record Receipt, ageing, the statement and the collected basis agree."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "100")

    settled = settled_against(
        session, firm_id=setup.firm.id, invoice_ids=[second.id, setup.invoice.id]
    )
    assert settled[second.id] == Decimal("100.00")
    # The first bill: 200.00 received and 100.00 returned, as before.
    assert settled[setup.invoice.id] == Decimal("300.00")
    # Before the day it was applied the second bill owed all of it.
    assert settled_against(
        session,
        firm_id=setup.firm.id,
        invoice_ids=[second.id],
        as_of=date(2026, 8, 5),
    ).get(second.id, Decimal("0")) == Decimal("0")
    statements = CustomerStatementService(session)
    [aged] = statements.ageing(firm_scope=setup.firm.id, customer_id=setup.customer.id)
    assert aged.total_outstanding == Decimal("100.00")
    statement = statements.statement(
        setup.customer.id,
        firm_scope=setup.firm.id,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )
    assert statement.closing_balance == Decimal("100.00")
    assert statement.unapplied_advance == Decimal("0.00")
    # Collected: the first bill's 200.00 is worth 100.00 once a unit came
    # back, and the other 100.00 met the second bill when it was applied.
    collected = collected_net(
        session,
        firm_id=setup.firm.id,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )
    assert sum_of(collected) == Decimal("200.00")
    assert {row.invoice_id: row.amount for row in collected} == {
        setup.invoice.id: Decimal("100.00"),
        second.id: Decimal("100.00"),
    }


def test_part_of_a_credit_is_applied_and_the_rest_stays() -> None:
    """40.00 of 100.00: 60.00 is left, on the account and on the credit."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)

    credit = _apply(setup, returned.id, second.id, "40")

    assert credit.applied_amount == Decimal("40.00")
    assert credit.available_amount == Decimal("60.00")
    assert credit.held_amount == Decimal("60.00")
    assert _owes(setup, second.id) == Decimal("160.00")
    assert _balances(setup) == (Decimal("160.00"), Decimal("60.00"))


def test_more_than_the_credit_has_left_is_refused() -> None:
    """A second application cannot spend what the first one did."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "70")

    with pytest.raises(ValidationError, match="has only 30.00 of credit left"):
        _apply(setup, returned.id, second.id, "40")
    session.rollback()

    assert _balances(setup) == (Decimal("130.00"), Decimal("30.00"))


def test_more_than_the_bill_owes_is_refused() -> None:
    """A bill paid down to 50.00 takes 50.00 of the credit and no more."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _receipt(setup, "150", (second.id, "150"), on=date(2026, 8, 5))

    with pytest.raises(ValidationError, match="owes only 50.00"):
        _apply(setup, returned.id, second.id, "100")
    session.rollback()

    _apply(setup, returned.id, second.id, "50")
    assert _owes(setup, second.id) == Decimal("0")


def test_another_customers_bill_is_refused() -> None:
    """A credit is set against a bill of the customer it belongs to."""
    session = _session_factory()()
    setup, returned, _second = _paid_then_returned(session)
    other = Customer(
        firm_id=setup.firm.id,
        code="CUS-002",
        customer_type="RETAIL",
        name="Customer CUS-002",
        display_name="Customer CUS-002",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("500000"),
        opening_balance=Decimal("0"),
    )
    session.add(other)
    session.commit()
    theirs = CustomerOpeningBillService(session).create(
        other.id,
        CustomerOpeningBillWrite(
            bill_date=date(2026, 3, 10),
            posting_date=date(2026, 4, 1),
            amount=Decimal("500"),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    session.commit()

    with pytest.raises(ValidationError, match="not this customer's"):
        _apply(setup, returned.id, theirs.id, "100")
    session.rollback()
    with pytest.raises(ValidationError, match="not this customer's"):
        _apply(setup, returned.id, uuid4(), "100")


def test_the_date_is_neither_in_the_future_nor_before_the_bill() -> None:
    """A credit meets a bill on or after both documents, and not tomorrow."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)

    with pytest.raises(ValidationError, match="future date"):
        _apply(setup, returned.id, second.id, "100", on=date(2099, 1, 1))
    session.rollback()
    with pytest.raises(ValidationError, match="on or after both"):
        _apply(setup, returned.id, second.id, "100", on=date(2026, 8, 4))
    session.rollback()

    # Left blank it is the later of the two documents' dates.
    _apply(setup, returned.id, second.id, "100", on=None)
    [row] = _applications(session)
    assert row.applied_on == date(2026, 8, 5)


def test_an_application_is_reversed_by_what_it_moved() -> None:
    """Taken back: the bill owes again, the advance is back, nothing posted."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "100")
    [row] = _applications(session)
    journals = _journals(session)

    reverse_customer_credit_application(
        session,
        firm_id=setup.firm.id,
        application_id=row.id,
        reason="wrong bill",
        actor_id=setup.actor_id,
    )
    session.commit()

    assert row.status == "REVERSED"
    assert row.is_deleted is False
    assert row.reversal_reason == "wrong bill"
    assert _owes(setup, second.id) == Decimal("200.00")
    assert _balances(setup) == (Decimal("200.00"), Decimal("100.00"))
    assert _journals(session) == journals
    [credit] = _credits(setup)
    assert credit.available_amount == Decimal("100.00")
    with pytest.raises(ValidationError, match="already been taken off"):
        reverse_customer_credit_application(
            session,
            firm_id=setup.firm.id,
            application_id=row.id,
            reason="again",
            actor_id=setup.actor_id,
        )


def test_cancelling_the_return_withdraws_what_its_credit_cleared() -> None:
    """The source gone: the bill owes all of it again and nothing is held."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "100")

    SalesReturnService(session).cancel_return(
        returned.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="undo"
    )
    session.commit()

    [row] = _applications(session)
    assert row.status == "REVERSED"
    assert _owes(setup, second.id) == Decimal("200.00")
    assert _balances(setup) == (Decimal("200.00"), Decimal("0.00"))
    assert _credits(setup) == []


def test_a_bill_with_credit_applied_is_not_cancelled_until_it_is_taken_off() -> None:
    """The target is held, as it is by a receipt, and freed by the reversal."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "100")
    invoices = SalesInvoiceService(session)

    with pytest.raises(ValidationError, match="credit applied from"):
        invoices.cancel_invoice(
            second.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
    session.rollback()

    [row] = _applications(session)
    reverse_customer_credit_application(
        session,
        firm_id=setup.firm.id,
        application_id=row.id,
        reason="bill raised in error",
        actor_id=setup.actor_id,
    )
    session.commit()
    invoices.cancel_invoice(
        second.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert _balances(setup) == (Decimal("0.00"), Decimal("100.00"))
    [credit] = _credits(setup)
    assert credit.available_amount == Decimal("100.00")


def test_a_refund_cannot_spend_credit_that_was_applied() -> None:
    """60.00 applied leaves 40.00 to pay back, and a refund takes it from the credit."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _apply(setup, returned.id, second.id, "60")

    with pytest.raises(ValidationError, match="exceeds unapplied advance"):
        _refund(setup, "100")
    session.rollback()
    with pytest.raises(ValidationError, match="has only 40.00 of credit left"):
        _refund(setup, "41", source_id=returned.id)
    session.rollback()

    refund = _refund(setup, "40")

    [credit] = _credits(setup)
    assert credit.refunded_amount == Decimal("40.00")
    assert credit.available_amount == Decimal("0.00")
    assert _balances(setup) == (Decimal("140.00"), Decimal("0.00"))
    # And what was paid back cannot be set against a bill as well.
    with pytest.raises(ValidationError, match="has only 0.00 of credit left"):
        _apply(setup, returned.id, second.id, "40")
    session.rollback()

    # Reversing the refund frees the credit again.
    RefundService(session).reverse(
        refund.id, firm_id=setup.firm.id, actor_id=setup.actor_id, reason="bounced"
    )
    session.commit()
    [credit] = _credits(setup)
    assert credit.available_amount == Decimal("40.00")
    assert _balances(setup) == (Decimal("140.00"), Decimal("40.00"))


def test_a_refund_made_before_credits_were_tracked_is_not_applied_again() -> None:
    """Money already handed back with no row to say so comes off the credit."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _refund(setup, "100")
    # As the store stood before this table existed.
    session.query(CustomerCreditApplication).delete()
    session.commit()

    [credit] = _credits(setup)
    assert credit.refunded_amount == Decimal("100.00")
    assert credit.available_amount == Decimal("0.00")
    with pytest.raises(ValidationError, match="has only 0.00 of credit left"):
        _apply(setup, returned.id, second.id, "100")


def test_only_a_refund_names_a_credit() -> None:
    """A receipt naming a return is refused rather than quietly ignoring it."""
    session = _session_factory()()
    setup, returned, _second = _paid_then_returned(session)

    with pytest.raises(ValidationError, match="Only a refund names"):
        ReceiptService(session).create(
            SettlementCreate(
                party_id=setup.customer.id,
                settlement_date=PAID_ON,
                amount=Decimal("10"),
                method=SettlementMethodEnum.CASH,
                credit_source_id=returned.id,
            ),
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )


def test_a_credit_note_on_a_paid_bill_gives_credit_too() -> None:
    """A credit note is a second source, applied and withdrawn the same way."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    note = _credit_note_on(setup, setup.invoice, "80")
    second = _second_bill(setup)

    [credit] = _credits(setup)
    assert credit.source_type == "CREDIT_NOTE"
    assert credit.source_id == note.id
    assert credit.available_amount == Decimal("80.00")
    assert _balances(setup) == (Decimal("200.00"), Decimal("80.00"))

    _apply(setup, note.id, second.id, "80")

    assert _owes(setup, second.id) == Decimal("120.00")
    assert _balances(setup) == (Decimal("120.00"), Decimal("0.00"))


def test_a_credit_that_already_came_off_the_balance_moves_nothing() -> None:
    """A return on a paid bill while another bill is owed nets on the account.

    The customer's balance fell when the return posted, so setting it
    against the second bill only says which bill it cleared.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    second = _second_bill(setup)
    _receipt(setup, "200", (setup.invoice.id, "200"))
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()

    assert _balances(setup) == (Decimal("100.00"), Decimal("0.00"))
    assert _owes(setup, second.id) == Decimal("200.00")
    [credit] = _credits(setup)
    assert credit.available_amount == Decimal("100.00")
    assert credit.held_amount == Decimal("0.00")

    _apply(setup, returned.id, second.id, "100")

    assert _owes(setup, second.id) == Decimal("100.00")
    assert _balances(setup) == (Decimal("100.00"), Decimal("0.00"))
    [row] = _applications(session)
    assert row.receivable_transaction_id is None
    assert Decimal(str(row.advance_amount)) == Decimal("0.00")


def test_a_return_on_an_unpaid_bill_gives_no_credit() -> None:
    """The bill absorbs it: there is nothing to set against another."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    second = _second_bill(setup)
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()

    assert _credits(setup) == []
    with pytest.raises(ValidationError, match="leaves no credit"):
        _apply(setup, returned.id, second.id, "100")


def test_a_return_off_a_note_billed_in_parts_gives_what_each_bill_could_not_take() -> (
    None
):
    """Three units back off a note billed as two paid bills: 300.00 of credit.

    Placed two on the first bill and one on the second, and both were paid,
    so all of it is credit -- set here against an opening bill, of which
    250.00 had already come off the balance when the return posted.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    second = _second_bill(setup)
    _receipt(setup, "400", (setup.invoice.id, "200"), (second.id, "200"))
    opening = CustomerOpeningBillService(session).create(
        setup.customer.id,
        CustomerOpeningBillWrite(
            bill_date=date(2026, 3, 10),
            posting_date=date(2026, 4, 1),
            amount=Decimal("250"),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    session.commit()
    returned = _returned(setup, setup.payload(quantity=Decimal("3")))
    session.commit()

    assert _balances(setup) == (Decimal("0.00"), Decimal("50.00"))
    [credit] = _credits(setup)
    assert credit.credit_amount == Decimal("300.00")
    assert credit.held_amount == Decimal("50.00")

    after = _apply(setup, returned.id, opening.id, "250")

    assert after.available_amount == Decimal("50.00")
    assert after.held_amount == Decimal("50.00")
    assert _owes(setup, opening.id) == Decimal("0")
    assert _balances(setup) == (Decimal("0.00"), Decimal("50.00"))
    [row] = _applications(session)
    assert row.target_type == "CUSTOMER_OPENING_BILL"
    # What is left is the customer's to be paid back.
    _refund(setup, "50", source_id=returned.id)
    [credit] = _credits(setup)
    assert credit.available_amount == Decimal("0.00")


def test_credit_used_goes_back_on_its_bill_when_the_receipt_is_reversed() -> None:
    """The first bill owes again, less only what its return still covers."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    receipt = _receipt(setup, "200", (setup.invoice.id, "200"))
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    second = _second_bill(setup)
    _apply(setup, returned.id, second.id, "100")

    ReceiptService(session).reverse(
        receipt.id, firm_id=setup.firm.id, actor_id=setup.actor_id, reason="bounced"
    )
    session.commit()

    # 400.00 billed less 100.00 returned: 300.00 owed, and the bills say so.
    assert _owes(setup, setup.invoice.id) == Decimal("200.00")
    assert _owes(setup, second.id) == Decimal("100.00")
    assert _balances(setup)[0] - _balances(setup)[1] == Decimal("300.00")


def _statements(setup: _Dispatch) -> int:
    """Count the statements one read of the customer's credits sends."""
    sent: list[str] = []

    def note(*args: object) -> None:
        """Record one statement."""
        sent.append(str(args[2]))

    engine = setup.session.get_bind()
    event.listen(engine, "before_cursor_execute", note)
    try:
        _credits(setup)
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return len(sent)


def test_the_list_is_read_in_bulk_however_many_credits_there_are() -> None:
    """Two credits cost the statements one does: nothing is read per row."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    one = _statements(setup)
    _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()

    assert len(_credits(setup)) == 2
    assert _statements(setup) == one


def _scope(setup: _Dispatch, *codes: str) -> ResolvedFirmScope:
    """Return a firm scope whose caller holds exactly ``codes``."""
    return ResolvedFirmScope(
        principal=Principal(
            subject=setup.actor_id,
            roles=frozenset(),
            permissions=frozenset(codes),
            claims=TokenClaims(
                sub=str(setup.actor_id),
                type=TokenType.ACCESS,
                iat=1,
                exp=4_102_444_800,
                permissions=sorted(codes),
            ),
        ),
        firm_id=setup.firm.id,
    )


def test_the_routes_list_apply_and_take_back() -> None:
    """The three routes, as the desktop calls them."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    view = _scope(setup, "RECEIPT_VIEW")
    create = _scope(setup, "RECEIPT_CREATE")

    listed = customer_unapplied_credits(
        party_id=setup.customer.id, scope=view, include_applied=False, db=session
    ).data
    assert listed is not None
    assert [(row.source_id, row.available_amount) for row in listed] == [
        (returned.id, Decimal("100.00"))
    ]

    applied = apply_customer_unapplied_credit(
        returned.id,
        CustomerCreditApplyRequest(
            invoice_id=second.id, amount=Decimal("100"), applied_on=APPLIED_ON
        ),
        scope=create,
        db=session,
    ).data
    assert applied is not None
    assert applied.available_amount == Decimal("0.00")
    [application] = applied.applications
    assert application.target_number == second.invoice_number

    # Used up, it leaves the list unless the used ones are asked for.
    assert (
        customer_unapplied_credits(
            party_id=setup.customer.id, scope=view, include_applied=False, db=session
        ).data
        == []
    )
    kept = customer_unapplied_credits(
        party_id=setup.customer.id, scope=view, include_applied=True, db=session
    ).data
    assert kept is not None and len(kept) == 1

    response = Response()
    taken_back = reverse_customer_credit(
        application.id,
        CustomerCreditReverseRequest(reason="wrong bill"),
        scope=create,
        response=response,
        db=session,
    ).data
    assert taken_back is not None
    assert response.headers["ETag"] == f'"{taken_back.version}"'
    assert _owes(setup, second.id) == Decimal("200.00")


# ---- the account goes on agreeing with the bills, in any order (D-PRC-88) ---


class _Scene:
    """A bill of 200.00 paid, one unit returned, and a second bill of 200.00.

    Each step is what a person does, committed, and after every one the
    customer's two figures are checked against the bills and the credits.
    """

    def __init__(self) -> None:
        """Pay the first bill, return one unit of it, raise the second."""
        self.session = _session_factory()()
        self.setup = _Dispatch(self.session, billed=Decimal("2"))
        self.first = self.setup.invoice
        self.receipt = _receipt(self.setup, "200", (self.first.id, "200"))
        self.returned = _returned(
            self.setup, _on_the_line_of(self.setup, self.first, "1")
        )
        self.session.commit()
        self.second = _second_bill(self.setup)
        self.refund: Settlement | None = None
        self.agree()

    def owed(self) -> dict[UUID, Decimal]:
        """Return what each bill still owes, as Record Receipt offers them."""
        return {
            record.invoice_id: record.outstanding_amount
            for record in ReceiptService(self.session).outstanding_invoices(
                firm_id=self.setup.firm.id, party_id=self.setup.customer.id
            )
        }

    def agree(self) -> None:
        """Check the account against the bills and the credits.

        The customer holds exactly what their credits hold as an advance,
        and owes what the bills owe less the credit that already came off
        the balance and names no bill yet.
        """
        outstanding, advance = _balances(self.setup)
        credits = _credits(self.setup)
        held = sum((credit.held_amount for credit in credits), Decimal("0"))
        loose = sum(
            (credit.available_amount - credit.held_amount for credit in credits),
            Decimal("0"),
        )
        assert advance == held
        assert outstanding == sum(self.owed().values(), Decimal("0")) - loose

    def apply(self) -> None:
        """Set the return's credit against the second bill."""
        _apply(self.setup, self.returned.id, self.second.id, "100")
        self.agree()

    def reverse_receipt(self) -> None:
        """Take back the receipt that paid the first bill."""
        ReceiptService(self.session).reverse(
            self.receipt.id,
            firm_id=self.setup.firm.id,
            actor_id=self.setup.actor_id,
            reason="bounced",
        )
        self.session.commit()
        self.agree()

    def reverse_application(self) -> None:
        """Take the credit off the second bill again."""
        [row] = [row for row in _applications(self.session) if row.status == "POSTED"]
        reverse_customer_credit_application(
            self.session,
            firm_id=self.setup.firm.id,
            application_id=row.id,
            reason="wrong bill",
            actor_id=self.setup.actor_id,
        )
        self.session.commit()
        self.agree()

    def pay_back(self) -> None:
        """Hand the credit back in cash."""
        self.refund = _refund(self.setup, "100", source_id=self.returned.id)
        self.agree()

    def reverse_refund(self) -> None:
        """Take the refund back."""
        assert self.refund is not None
        RefundService(self.session).reverse(
            self.refund.id,
            firm_id=self.setup.firm.id,
            actor_id=self.setup.actor_id,
            reason="not collected",
        )
        self.session.commit()
        self.agree()

    def cancel_return(self) -> None:
        """Cancel the return that gave the credit."""
        SalesReturnService(self.session).cancel_return(
            self.returned.id,
            firm_scope=self.setup.firm.id,
            actor_id=self.setup.actor_id,
            reason="undo",
        )
        self.session.commit()
        self.agree()

    def pay_what_the_bills_read(self) -> None:
        """Pay each bill exactly what it owes, then expect nothing either way."""
        for bill_id, amount in self.owed().items():
            _receipt(self.setup, str(amount), (bill_id, str(amount)))
        self.agree()
        assert self.owed() == {}
        assert _balances(self.setup) == (Decimal("0.00"), Decimal("0.00"))
        # Nothing is held, so nothing can be handed back a second time.
        with pytest.raises(ValidationError, match="exceeds unapplied advance"):
            _refund(self.setup, "100")
        self.session.rollback()


@pytest.mark.parametrize(
    "steps",
    [
        # Round 9's sequence: 4,248.00 owed and 826.00 held at 826.00 a unit.
        ("apply", "reverse_receipt", "reverse_application"),
        ("apply", "reverse_application", "reverse_receipt"),
        ("apply", "reverse_receipt"),
        ("reverse_receipt",),
        ("pay_back", "reverse_receipt", "reverse_refund"),
        ("pay_back", "reverse_refund", "reverse_receipt"),
        ("pay_back", "reverse_receipt"),
        ("apply", "reverse_application", "pay_back", "reverse_receipt"),
    ],
)
def test_the_account_agrees_with_the_bills_in_any_order(steps: tuple[str, ...]) -> None:
    """Apply, refund and reverse in every order: paid up, nothing owed or held."""
    scene = _Scene()
    for step in steps:
        getattr(scene, step)()
    scene.pay_what_the_bills_read()


def test_a_reversed_application_puts_back_no_advance_the_credit_lost() -> None:
    """The figures of the defect: the first bill's receipt goes, then the credit.

    The return's 100.00 is part of what the first bill does not owe once its
    receipt is reversed, so taking the application off the second bill moves
    100.00 between the bills and nothing on the account.
    """
    scene = _Scene()
    scene.apply()
    scene.reverse_receipt()
    assert _balances(scene.setup) == (Decimal("300.00"), Decimal("0.00"))
    assert scene.owed() == {
        scene.first.id: Decimal("200.00"),
        scene.second.id: Decimal("100.00"),
    }
    journals = _journals(scene.session)

    scene.reverse_application()

    assert _balances(scene.setup) == (Decimal("300.00"), Decimal("0.00"))
    assert scene.owed() == {
        scene.first.id: Decimal("100.00"),
        scene.second.id: Decimal("200.00"),
    }
    assert _credits(scene.setup) == []
    assert _journals(scene.session) == journals
    statement = CustomerStatementService(scene.session).statement(
        scene.setup.customer.id,
        firm_scope=scene.setup.firm.id,
        from_date=date(2026, 1, 1),
        to_date=date(2027, 1, 1),
    )
    assert statement.closing_balance == Decimal("300.00")


def test_a_reversed_receipt_takes_an_unused_credit_back_onto_its_bill() -> None:
    """Never applied: the bill owes less the return, and nothing is held."""
    scene = _Scene()

    scene.reverse_receipt()

    assert _balances(scene.setup) == (Decimal("300.00"), Decimal("0.00"))
    assert scene.owed() == {
        scene.first.id: Decimal("100.00"),
        scene.second.id: Decimal("200.00"),
    }
    [row] = scene.session.scalars(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.reference_type == "customer_credit_absorbed"
        )
    ).all()
    assert row.reference_id == scene.returned.id
    assert (row.outstanding_delta, row.advance_delta) == (
        Decimal("-100.00"),
        Decimal("-100.00"),
    )
    events = scene.session.scalars(
        select(AuditLog.action).where(AuditLog.action == "customer_credit.absorbed")
    ).all()
    assert len(events) == 1


def test_only_the_part_the_bill_owes_again_goes_back_onto_it() -> None:
    """Two receipts of 100.00 and one reversed after 60.00 was applied.

    The return's 100.00 is no longer past the bill's total, so the 40.00
    still held goes back on it and the 60.00 used elsewhere is drawn back.
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "100", (setup.invoice.id, "100"))
    late = _receipt(setup, "100", (setup.invoice.id, "100"))
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    second = _second_bill(setup)
    _apply(setup, returned.id, second.id, "60")
    assert _balances(setup) == (Decimal("140.00"), Decimal("40.00"))

    ReceiptService(session).reverse(
        late.id, firm_id=setup.firm.id, actor_id=setup.actor_id, reason="bounced"
    )
    session.commit()

    assert _balances(setup) == (Decimal("200.00"), Decimal("0.00"))
    assert _owes(setup, setup.invoice.id) == Decimal("60.00")
    assert _owes(setup, second.id) == Decimal("140.00")


@pytest.mark.parametrize("applied_first", [True, False])
def test_cancelling_the_return_undoes_what_went_back_onto_its_bill(
    applied_first: bool,
) -> None:
    """The source gone after its advance was absorbed: every bill owes in full."""
    scene = _Scene()
    if applied_first:
        scene.apply()
        scene.reverse_receipt()
        scene.reverse_application()
    else:
        scene.reverse_receipt()

    scene.cancel_return()

    assert _balances(scene.setup) == (Decimal("400.00"), Decimal("0.00"))
    assert scene.owed() == {
        scene.first.id: Decimal("200.00"),
        scene.second.id: Decimal("200.00"),
    }


# ---- a refund made before credits were tracked (D-PRC-91) -------------------


def _untracked(session: Session) -> None:
    """Leave the store as it stood before the table existed: no rows."""
    session.query(CustomerCreditApplication).delete()
    session.commit()


def test_money_received_since_does_not_bring_back_a_credit_paid_back() -> None:
    """500.00 on account after an untracked refund is the receipt's, not credit."""
    session = _session_factory()()
    setup, returned, second = _paid_then_returned(session)
    _refund(setup, "100")
    _untracked(session)

    receipt = _receipt(setup, "500")

    assert _balances(setup) == (Decimal("0.00"), Decimal("300.00"))
    [credit] = _credits(setup)
    assert credit.refunded_amount == Decimal("100.00")
    assert credit.available_amount == Decimal("0.00")
    assert credit.held_amount == Decimal("0.00")
    with pytest.raises(ValidationError, match="has only 0.00 of credit left"):
        _apply(setup, returned.id, second.id, "100")
    session.rollback()
    with pytest.raises(ValidationError, match="has only 0.00 of credit left"):
        _refund(setup, "100", source_id=returned.id)
    session.rollback()
    # And the receipt's money is still the receipt's to set against the bill.
    ReceiptService(session).allocate(
        receipt.id,
        invoice_id=second.id,
        amount=Decimal("200"),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    assert _owes(setup, second.id) == Decimal("0")
    assert _balances(setup) == (Decimal("0.00"), Decimal("300.00"))


def test_an_untracked_refund_takes_the_oldest_credit_and_leaves_the_next() -> None:
    """Two credits of 100.00, 100.00 handed back before rows were kept."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    first = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    _refund(setup, "100")
    _untracked(session)
    second = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    _receipt(setup, "500")

    credits = {credit.source_id: credit for credit in _credits(setup)}

    assert credits[first.id].refunded_amount == Decimal("100.00")
    assert credits[first.id].available_amount == Decimal("0.00")
    assert credits[second.id].refunded_amount == Decimal("0.00")
    assert credits[second.id].available_amount == Decimal("100.00")
    assert credits[second.id].held_amount == Decimal("100.00")


def test_a_refund_made_before_a_credit_existed_took_none_of_it() -> None:
    """Money on account handed back, and only then a return on a paid bill."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=Decimal("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    _receipt(setup, "50")
    _refund(setup, "50")
    # The unit suite's clock has one-second ticks: put the refund where it
    # was made, a day before the return.
    session.execute(
        update(CustomerReceivableTransaction).values(
            created_at=datetime(2026, 8, 1, 9, 0, 0)
        )
    )
    session.commit()
    returned = _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()

    [credit] = _credits(setup)

    assert credit.source_id == returned.id
    assert credit.refunded_amount == Decimal("0.00")
    assert credit.available_amount == Decimal("100.00")
    assert credit.held_amount == Decimal("100.00")


# ---- an opening bill a credit is set against (D-PRC-92) ---------------------


def test_cancelling_an_opening_bill_names_the_credit_set_against_it() -> None:
    """No receipt exists, so the refusal must not ask for one to be reversed."""
    session = _session_factory()()
    setup, returned, _second = _paid_then_returned(session)
    bills = CustomerOpeningBillService(session)
    opening = bills.create(
        setup.customer.id,
        CustomerOpeningBillWrite(
            bill_date=date(2026, 3, 10),
            posting_date=date(2026, 4, 1),
            amount=Decimal("250"),
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    session.commit()
    _apply(setup, returned.id, opening.id, "100")

    with pytest.raises(ValidationError) as refused:
        bills.cancel(
            opening.id,
            reason="entered twice",
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()
    message = str(refused.value)
    assert message == (
        f"{opening.bill_number} cannot be cancelled while it has 100.00 of "
        f"credit applied from {returned.return_number}. Reverse that "
        "application first."
    )
    assert "receipt" not in message

    # With a receipt beside the credit, both are named.
    _receipt(setup, "50", (opening.id, "50"))
    with pytest.raises(ValidationError, match="the receipts for the other 50.00"):
        bills.cancel(
            opening.id,
            reason="entered twice",
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
    session.rollback()

    # A bill only a receipt was taken against is refused as before.
    [row] = [row for row in _applications(session) if row.status == "POSTED"]
    reverse_customer_credit_application(
        session,
        firm_id=setup.firm.id,
        application_id=row.id,
        reason="wrong bill",
        actor_id=setup.actor_id,
    )
    session.commit()
    with pytest.raises(ValidationError, match="Reverse those receipts"):
        bills.cancel(
            opening.id,
            reason="entered twice",
            firm_id=setup.firm.id,
            actor_id=setup.actor_id,
        )
