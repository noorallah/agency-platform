"""Payments against one claim are numbered, not timed.

D-PRC-33: a payment's journal reference was
``CLAIM-<number>-PAY-<the clock to the second>``, so a second payment recorded
0.15 s after the first was the same reference and was refused with a 409 "A
journal entry with reference ... already exists". A second later the same
body was taken. The reversal's reference was built the same way.

A claim's payments are numbered ``-PAY-1``, ``-PAY-2``, ... from the payments
it has already had, and a reversal is its payment's reference with ``-REV``.
Every case runs on a request-shaped session.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.finance.models import FirmControlAccount, JournalEntry
from app.finance.services.control_accounts import ControlAccountPurpose
from app.principal_claims.models import PrincipalClaim, PrincipalClaimReceipt
from app.principal_claims.services import (
    PrincipalClaimReceiptWrite,
    PrincipalClaimService,
)
from tests.unit.test_principal_claim_free_goods import _Agency

D = Decimal


class _Owed:
    """A claim of 60.00 raised on ACME, and the bank it is paid into."""

    def __init__(self) -> None:
        """Bill a typed free unit and raise August's claim."""
        self.agency = _Agency()
        self.agency.bill(free="1")
        self.service = PrincipalClaimService(self.agency.session)
        self.claim: PrincipalClaim = self.service.raise_claim(
            self.agency.write(),
            firm_id=self.agency.firm_id,
            actor_id=self.agency.actor,
        )
        bank = self.agency.session.scalar(
            select(FirmControlAccount.ledger_account_id).where(
                FirmControlAccount.firm_id == self.agency.firm_id,
                FirmControlAccount.purpose == ControlAccountPurpose.BANK.value,
            )
        )
        assert bank is not None
        self.bank: UUID = bank

    def pay(self, amount: str) -> PrincipalClaimReceipt:
        """Record one payment against the claim."""
        return self.service.record_receipt(
            self.claim.id,
            PrincipalClaimReceiptWrite(
                received_on=date(2026, 9, 10),
                amount=D(amount),
                money_account_id=self.bank,
            ),
            firm_id=self.agency.firm_id,
            actor_id=self.agency.actor,
        )

    def reference(self, receipt: PrincipalClaimReceipt) -> str:
        """Return the journal reference a payment was posted under."""
        entry = self.agency.session.get(JournalEntry, receipt.journal_entry_id)
        assert entry is not None
        return str(entry.reference_number)

    def reversal_of(self, receipt: PrincipalClaimReceipt) -> str:
        """Return the reference of the journal that reversed a payment."""
        entry = self.agency.session.scalars(
            select(JournalEntry).where(
                JournalEntry.reversal_of_id == receipt.journal_entry_id
            )
        ).one()
        return str(entry.reference_number)


def test_two_payments_one_after_the_other_are_both_taken() -> None:
    """The check's own steps: 1.00, and 1.00 again straight away."""
    owed = _Owed()

    first = owed.pay("1.00")
    second = owed.pay("1.00")

    number = owed.claim.claim_number
    assert (owed.reference(first), owed.reference(second)) == (
        f"CLAIM-{number}-PAY-1",
        f"CLAIM-{number}-PAY-2",
    )
    assert owed.service.outstanding(owed.claim) == D("58.00")


def test_a_reversal_takes_its_payments_reference_and_the_count_goes_on() -> None:
    """-PAY-1-REV; the next payment is -PAY-3, never a second -PAY-2."""
    owed = _Owed()
    first = owed.pay("1.00")
    owed.pay("2.00")

    owed.service.reverse_receipt(
        owed.claim.id,
        first.id,
        firm_id=owed.agency.firm_id,
        actor_id=owed.agency.actor,
    )
    third = owed.pay("3.00")

    number = owed.claim.claim_number
    assert owed.reversal_of(first) == f"CLAIM-{number}-PAY-1-REV"
    assert owed.reference(third) == f"CLAIM-{number}-PAY-3"
    assert owed.service.outstanding(owed.claim) == D("55.00")


def test_a_reference_written_under_the_old_rule_is_left_and_stepped_over() -> None:
    """An old payment keeps its timestamp; its reversal is that plus -REV."""
    owed = _Owed()
    old = owed.pay("1.00")
    entry = owed.agency.session.get(JournalEntry, old.journal_entry_id)
    assert entry is not None
    number = owed.claim.claim_number
    entry.reference_number = f"CLAIM-{number}-PAY-20261006011831"
    owed.agency.session.commit()

    new = owed.pay("1.00")
    owed.service.reverse_receipt(
        owed.claim.id, old.id, firm_id=owed.agency.firm_id, actor_id=owed.agency.actor
    )

    assert owed.reference(new) == f"CLAIM-{number}-PAY-2"
    assert owed.reversal_of(old) == f"CLAIM-{number}-PAY-20261006011831-REV"
    assert len(owed.reversal_of(old)) <= 50
