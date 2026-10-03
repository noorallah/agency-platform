"""The post-dated cheque register (ACC-2, decision A80).

A cheque dated ahead is held and posts nothing; banking it records the receipt
or payment; clearing posts nothing more; a return reverses it on the day the
bank returned it and posts the bank's fee and the customer's charge; a held
cheque can be cancelled.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.finance.models import JournalEntry
from app.settlements.api.post_dated_cheques_router import list_received_cheques
from app.settlements.models import Settlement, SettlementDirection
from app.settlements.schemas.post_dated_cheque import (
    PostDatedChequeBounce,
    PostDatedChequeCreate,
    PostDatedChequeDeposit,
)
from app.settlements.services.post_dated_cheques import PostDatedChequeService
from app.vendors.models import Vendor
from tests.unit.report_windows import report_scope
from tests.unit.test_expenses import _Books

BANK, RECEIVABLE, BANK_CHARGES, RETURN_CHARGES = "1010", "1100", "6700", "4310"
TAKEN, DATED = date(2026, 4, 10), date(2026, 4, 30)


def _customer(books: _Books) -> Customer:
    customer = Customer(
        firm_id=books.firm.id,
        code="C1",
        customer_type="BUSINESS",
        name="Kumar Stores",
        display_name="Kumar Stores",
        currency_code="INR",
        status="ACTIVE",
    )
    books.session.add(customer)
    books.session.commit()
    return customer


def _vendor(books: _Books) -> Vendor:
    vendor = Vendor(
        firm_id=books.firm.id,
        code="V1",
        name="Vendor One",
        display_name="Vendor One",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(vendor)
    books.session.commit()
    return vendor


def _service(
    books: _Books, direction: SettlementDirection = SettlementDirection.RECEIPT
) -> PostDatedChequeService:
    return PostDatedChequeService(books.session, direction=direction)


def _hold(
    books: _Books,
    party_id: UUID,
    *,
    number: str = "000123",
    direction: SettlementDirection = SettlementDirection.RECEIPT,
) -> UUID:
    row = _service(books, direction).create(
        PostDatedChequeCreate(
            party_id=party_id,
            cheque_number=number,
            cheque_date=DATED,
            drawn_on_bank="State Bank of India",
            amount=Decimal("25000"),
            received_on=TAKEN,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row.id


def _journals(books: _Books) -> int:
    return int(books.session.scalar(select(func.count(JournalEntry.id))) or 0)


def test_a_held_cheque_posts_nothing_until_it_is_banked_on_its_date() -> None:
    books = _Books()
    customer = _customer(books)
    before = _journals(books)
    cheque_id = _hold(books, customer.id)
    service = _service(books)
    assert _journals(books) == before
    assert books.session.scalar(select(func.count(Settlement.id))) == 0

    with pytest.raises(ValidationError, match="will not take it"):
        service.deposit(
            cheque_id,
            PostDatedChequeDeposit(deposited_on=date(2026, 4, 29)),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()

    row = service.deposit(
        cheque_id,
        PostDatedChequeDeposit(deposited_on=DATED),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert row.status == "DEPOSITED"
    settlement = books.session.get(Settlement, row.settlement_id)
    assert settlement is not None
    assert settlement.settlement_date == DATED
    assert settlement.payment_mode == "CHEQUE"
    assert settlement.instrument_reference == "000123"
    assert settlement.instrument_date == DATED
    legs = books.postings(settlement.journal_entry_id)
    assert legs[BANK] == (Decimal("25000.00"), Decimal("0.00"))
    assert legs[RECEIVABLE] == (Decimal("0.00"), Decimal("25000.00"))

    cleared = service.clear(
        cheque_id,
        cleared_on=date(2026, 5, 2),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert cleared.status == "CLEARED"
    assert _journals(books) == before + 1
    [answer] = service.responses([cleared])
    assert answer.settlement_number == settlement.settlement_number
    assert answer.party_name == "Kumar Stores"


def test_a_returned_cheque_reverses_the_receipt_and_posts_its_charges() -> None:
    books = _Books()
    customer = _customer(books)
    cheque_id = _hold(books, customer.id)
    service = _service(books)
    service.deposit(
        cheque_id,
        PostDatedChequeDeposit(deposited_on=DATED),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    row = service.bounce(
        cheque_id,
        PostDatedChequeBounce(
            bounced_on=date(2026, 5, 3),
            reason="Funds insufficient",
            bank_charges_amount=Decimal("150"),
            customer_charge_amount=Decimal("500"),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert row.status == "BOUNCED"
    settlement = books.session.get(Settlement, row.settlement_id)
    assert settlement is not None
    assert settlement.status == "REVERSED"
    mirror = books.session.get(JournalEntry, settlement.reversal_journal_entry_id)
    assert mirror is not None and mirror.journal_date == date(2026, 5, 3)
    assert row.charges_journal_entry_id is not None
    legs = books.postings(row.charges_journal_entry_id)
    assert legs[BANK_CHARGES] == (Decimal("150.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("0.00"), Decimal("150.00"))
    assert legs[RECEIVABLE] == (Decimal("500.00"), Decimal("0.00"))
    assert legs[RETURN_CHARGES] == (Decimal("0.00"), Decimal("500.00"))
    # The money came and went; the bank is out by its fee and the customer
    # owes the charge, in the ledger and on their own account alike.
    assert books.net(BANK) == Decimal("-150.00")
    assert books.net(RECEIVABLE) == Decimal("500.00")
    books.session.refresh(customer)
    assert customer.current_outstanding == Decimal("500.00")
    assert customer.unapplied_advance_balance == Decimal("0.00")
    charge = books.session.get(
        CustomerReceivableTransaction, row.charge_receivable_transaction_id
    )
    assert charge is not None
    assert charge.transaction_type == "CHEQUE_RETURN_CHARGE"

    with pytest.raises(ValidationError, match="bounced, so it cannot be cleared"):
        service.clear(
            cheque_id,
            cleared_on=date(2026, 5, 4),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_return_without_charges_posts_only_the_reversal() -> None:
    books = _Books()
    customer = _customer(books)
    cheque_id = _hold(books, customer.id)
    service = _service(books)
    service.deposit(
        cheque_id,
        PostDatedChequeDeposit(deposited_on=DATED),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    row = service.bounce(
        cheque_id,
        PostDatedChequeBounce(bounced_on=DATED, reason="Signature differs"),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert row.charges_journal_entry_id is None
    assert books.net(BANK) == Decimal("0.00")
    assert books.net(RECEIVABLE) == Decimal("0.00")


def test_the_register_refuses_what_is_not_a_post_dated_cheque() -> None:
    books = _Books()
    customer = _customer(books)
    service = _service(books)
    with pytest.raises(ValidationError, match="not post-dated"):
        service.create(
            PostDatedChequeCreate(
                party_id=customer.id,
                cheque_number="1",
                cheque_date=date(2026, 4, 1),
                amount=Decimal("10"),
                received_on=TAKEN,
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    cheque_id = _hold(books, customer.id)
    with pytest.raises(ValidationError, match="already in the register"):
        _hold(books, customer.id)
    books.session.rollback()

    row = service.cancel(
        cheque_id, reason="Replaced", firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert row.status == "CANCELLED"
    # The number is free again once the cheque is out of the register.
    _hold(books, customer.id)
    with pytest.raises(ValidationError, match="cancelled, so it cannot be banked"):
        service.deposit(
            cheque_id,
            PostDatedChequeDeposit(deposited_on=DATED),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_the_firms_own_cheque_becomes_a_payment_and_charges_no_supplier() -> None:
    books = _Books()
    vendor = _vendor(books)
    direction = SettlementDirection.PAYMENT
    cheque_id = _hold(books, vendor.id, direction=direction)
    service = _service(books, direction)
    row = service.deposit(
        cheque_id,
        PostDatedChequeDeposit(deposited_on=DATED),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    settlement = books.session.get(Settlement, row.settlement_id)
    assert settlement is not None and settlement.direction == "PAYMENT"
    assert books.net(BANK) == Decimal("-25000.00")
    with pytest.raises(ValidationError, match="Only a customer's cheque"):
        service.bounce(
            cheque_id,
            PostDatedChequeBounce(
                bounced_on=DATED,
                reason="Stopped",
                customer_charge_amount=Decimal("100"),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    # A customer's register does not see the firm's own cheques.
    assert (
        _service(books).list_cheques(firm_id=books.firm.id, page=1, page_size=10)[1]
        == 0
    )


def test_the_deposit_today_list_is_what_is_held_and_due() -> None:
    books = _Books()
    customer = _customer(books)
    _hold(books, customer.id, number="1")
    later = _service(books).create(
        PostDatedChequeCreate(
            party_id=customer.id,
            cheque_number="2",
            cheque_date=date(2026, 5, 15),
            amount=Decimal("10"),
            received_on=TAKEN,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    scope = report_scope(books.firm.id)
    page = list_received_cheques(
        scope=scope,
        page=1,
        page_size=50,
        search="",
        status_filter=None,
        party_id=None,
        due_on=DATED,
        cheque_from=None,
        cheque_to=None,
        db=books.session,
    )
    assert [row.cheque_number for row in page.data] == ["1"]
    everything = list_received_cheques(
        scope=scope,
        page=1,
        page_size=50,
        search="",
        status_filter=None,
        party_id=None,
        due_on=None,
        cheque_from=None,
        cheque_to=None,
        db=books.session,
    )
    assert [row.cheque_number for row in everything.data] == ["1", "2"]
    assert everything.data[1].id == later.id


def test_a_step_aimed_at_an_old_version_is_refused() -> None:
    from fastapi import Response

    from app.core.exceptions import ConflictError
    from app.settlements.api.post_dated_cheques_router import (
        cancel_received_cheque,
    )
    from app.settlements.schemas.post_dated_cheque import PostDatedChequeCancel

    books = _Books()
    customer = _customer(books)
    cheque_id = _hold(books, customer.id)
    with pytest.raises(ConflictError):
        cancel_received_cheque(
            cheque_id=cheque_id,
            payload=PostDatedChequeCancel(reason="Replaced"),
            scope=report_scope(books.firm.id),
            response=Response(),
            expected_version=99,
            db=books.session,
        )
