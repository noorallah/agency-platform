"""Whatever settles a claim locks the claim before it reads what is owed.

D-PRC-41, from the third pricing check: two receipts of 1.00 on one claim,
sent at the same instant from two connections. Both fitted what the claim
was owed; one posted and the other was refused with 409, "A journal entry
with reference CLAIM-...-PAY-5 already exists." Since D-PRC-33 a payment is
numbered by counting the claim's payments, and nothing was held while they
were counted -- nor while what is owed, a sum, was read, so two payments
that each fitted could together have settled more than the claim.

`record_receipt`, `reverse_receipt`, `cancel` and `to_settle` now take the
claim's row ``FOR UPDATE`` first.

**What these cases prove, and what they cannot.** The unit suite runs on
SQLite, which has no row locks and one connection, so the race itself is
not reproduced here. They prove that the lock is *asked for* -- the
statement carries FOR UPDATE, compiles to it on PostgreSQL, and is the first
thing each method sends, ahead of the sum and the count -- and that payments
made one after the other are numbered in order and cannot over-settle.
Every case runs on a request-shaped session.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import ORMExecuteState

from app.core.exceptions import ValidationError
from app.principal_claims.models import PrincipalClaim, PrincipalClaimReceipt
from tests.unit.test_principal_claim_receipts import _Owed

D = Decimal


@contextmanager
def _statements(owed: _Owed) -> Iterator[list[tuple[bool, str]]]:
    """Record each statement the session sends: (locks a claim, its SQL)."""
    seen: list[tuple[bool, str]] = []

    def record(state: ORMExecuteState) -> None:
        """Note one statement as PostgreSQL would be sent it."""
        statement = state.statement
        sql = str(statement.compile(dialect=postgresql.dialect()))
        locks = (
            state.is_select
            and getattr(statement, "_for_update_arg", None) is not None
            and "FROM principal_claims" in sql
        )
        seen.append((locks, sql))

    event.listen(owed.agency.session, "do_orm_execute", record)
    try:
        yield seen
    finally:
        event.remove(owed.agency.session, "do_orm_execute", record)


def _assert_locked_first(seen: list[tuple[bool, str]]) -> None:
    """Assert the claim was locked before anything was summed or counted."""
    assert seen, "nothing was sent"
    locks, sql = seen[0]
    assert locks, f"the first statement does not lock the claim: {sql}"
    assert sql.rstrip().endswith("FOR UPDATE")
    reads = [
        index
        for index, (_, text) in enumerate(seen)
        if "principal_claim_receipts" in text or "party_adjustments" in text
    ]
    assert reads and min(reads) > 0, "what is owed was read before the lock"


def test_a_payment_locks_the_claim_before_it_reads_what_is_owed() -> None:
    """The lock is the first statement; the sum and the count come after."""
    owed = _Owed()

    with _statements(owed) as seen:
        owed.pay("1.00")

    _assert_locked_first(seen)
    # One lock for the request, not one per read.
    assert sum(1 for locks, _ in seen if locks) == 1


def test_two_payments_in_turn_take_consecutive_numbers_under_the_lock() -> None:
    """The check's pair of 1.00: -PAY-1 and -PAY-2, each behind its own lock."""
    owed = _Owed()

    with _statements(owed) as seen:
        first = owed.pay("1.00")
        second = owed.pay("1.00")

    number = owed.claim.claim_number
    assert (owed.reference(first), owed.reference(second)) == (
        f"CLAIM-{number}-PAY-1",
        f"CLAIM-{number}-PAY-2",
    )
    assert sum(1 for locks, _ in seen if locks) == 2


def test_two_payments_cannot_together_settle_more_than_the_claim() -> None:
    """60.00 owed: 40.00 is taken, a second 40.00 is refused for the 20.00 left."""
    owed = _Owed()
    owed.pay("40.00")

    with pytest.raises(ValidationError, match="has 20.00 still to settle, so 40.00"):
        owed.pay("40.00")
    owed.agency.session.rollback()

    taken = owed.pay("20.00")
    assert owed.reference(taken) == f"CLAIM-{owed.claim.claim_number}-PAY-2"
    assert owed.service.outstanding(owed.claim) == D("0.00")
    with pytest.raises(ValidationError, match="has 0.00 still to settle"):
        owed.pay("0.01")


def test_the_locked_read_sees_what_was_committed_since_the_row_was_loaded() -> None:
    """A copy the session already holds does not hide a cancellation."""
    owed = _Owed()
    # Another request cancels the claim behind this session's back.
    owed.agency.session.execute(
        PrincipalClaim.__table__.update()
        .where(PrincipalClaim.id == owed.claim.id)
        .values(status="CANCELLED")
    )
    owed.agency.session.commit()
    assert owed.claim.status != "CANCELLED", "the held copy is stale"

    with pytest.raises(ValidationError, match="A cancelled claim takes no payment"):
        owed.pay("1.00")


def _reverse(owed: _Owed, receipt: PrincipalClaimReceipt) -> None:
    """Reverse a payment."""
    owed.service.reverse_receipt(
        owed.claim.id,
        receipt.id,
        firm_id=owed.agency.firm_id,
        actor_id=owed.agency.actor,
    )


def _cancel(owed: _Owed, _receipt: PrincipalClaimReceipt) -> None:
    """Try to cancel the claim; a part-settled one is refused after the lock."""
    with pytest.raises(ValidationError, match="Part of this claim is settled"):
        owed.service.cancel(
            owed.claim.id,
            "Raised twice",
            firm_id=owed.agency.firm_id,
            actor_id=owed.agency.actor,
        )


def _to_settle(owed: _Owed, _receipt: PrincipalClaimReceipt) -> None:
    """Ask what a credit note may still settle."""
    with pytest.raises(ValidationError, match="not on this supplier"):
        owed.service.to_settle(
            owed.claim.id,
            firm_id=owed.agency.firm_id,
            vendor_id=owed.agency.setup.customer.id,
        )


@pytest.mark.parametrize("act", [_reverse, _cancel, _to_settle])
def test_everything_else_that_settles_or_withdraws_a_claim_locks_it_first(
    act: Callable[[_Owed, PrincipalClaimReceipt], None],
) -> None:
    """A reversal, a cancellation and a credit note queue on the same row."""
    owed = _Owed()
    receipt = owed.pay("1.00")
    assert receipt.received_on == date(2026, 9, 10)

    with _statements(owed) as seen:
        act(owed, receipt)

    locks, sql = seen[0]
    assert locks, f"the first statement does not lock the claim: {sql}"
