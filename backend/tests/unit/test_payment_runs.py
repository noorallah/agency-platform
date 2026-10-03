"""Payment runs and the bank file (BUY-11, decision A110).

Two bills from one supplier fall due. A run proposes both, refuses to pay
one more than it owes, and on approval records one bank payment for the
supplier that clears both. The bank file names the supplier's account; a
supplier with no account is refused by name.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.settlements.schemas.payment_run import PaymentRunWrite
from app.settlements.services.payment_runs import PaymentRunService
from app.vendors.models import VendorBankAccount
from tests.unit.test_purchase_chain_synthesis import _Firm

D = Decimal


@pytest.fixture
def firm() -> _Firm:
    """Build a firm owing its supplier two approved bills."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code="PAYRN")
    built.stages(order=False, receipt=False)
    bills = built.bills()
    for number, quantity in (("S-1", "2"), ("S-2", "3")):
        bill = bills.create_invoice(
            built.product_bill(quantity, "100", number=number),
            firm_id=built.firm.id,
            actor_id=built.actor_id,
        )
        bills.approve_invoice(
            bill.id, firm_scope=built.firm.id, actor_id=built.actor_id
        )
    return built


def _bank(firm: _Firm) -> None:
    firm.session.add(
        VendorBankAccount(
            vendor_id=firm.vendor.id,
            bank_name="State Bank",
            account_name="Supplier Ltd",
            account_number="123456789012",
            ifsc="SBIN0000001",
            is_primary=True,
        )
    )
    firm.session.commit()


def test_a_run_pays_each_supplier_once(firm: _Firm) -> None:
    service = PaymentRunService(firm.session)
    proposal = service.propose(firm.firm.id, date(2027, 12, 31))
    assert len(proposal) == 2
    owed = {record.invoice_id: record.outstanding_amount for record in proposal}

    with pytest.raises(ValidationError, match="owes"):
        service.create(
            PaymentRunWrite(
                payment_date=date(2026, 8, 20),
                lines=[
                    {"invoice_id": invoice, "amount": amount + 1}
                    for invoice, amount in owed.items()
                ],
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()
    run = service.create(
        PaymentRunWrite(
            payment_date=date(2026, 8, 20),
            lines=[{"invoice_id": invoice} for invoice in owed],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    (response,) = service.responses([run])
    assert response.total == sum(owed.values())

    approved = service.approve(run.id, firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert approved.status == "APPROVED"
    settlements = {line.settlement_id for line in service.lines(run.id)}
    assert len(settlements) == 1 and None not in settlements
    assert service.propose(firm.firm.id, date(2027, 12, 31)) == []


def test_the_bank_file_needs_an_account(firm: _Firm) -> None:
    service = PaymentRunService(firm.session)
    run = service.create(
        PaymentRunWrite(
            payment_date=date(2026, 8, 20),
            lines=[
                {"invoice_id": record.invoice_id}
                for record in service.propose(firm.firm.id, date(2027, 12, 31))
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    with pytest.raises(ValidationError, match="no bank account"):
        service.bank_file(run.id, firm_id=firm.firm.id)
    _bank(firm)
    content, name = service.bank_file(run.id, firm_id=firm.firm.id)
    rows = content.strip().split("\n")
    assert rows[0].startswith("Beneficiary Code,Beneficiary Name,Account Number")
    assert "123456789012" in rows[1] and "SBIN0000001" in rows[1]
    assert name.endswith("-neft.csv")
