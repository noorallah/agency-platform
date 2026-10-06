"""A redemption can be undone, and a bill paid partly in points can be cancelled.

D-PRC-6, driven 2026-10-06: a bill of 118.00 with 10 points spent on it
answered 422 to its cancellation -- "...cannot be cancelled while it has
loyalty points spent on it. Reverse or cancel those first." -- and no route
reversed a redemption, so nobody could ever cancel it.

Cancelling the bill now puts the points back in the same transaction, and
`POST /loyalty/redemptions/{id}/reverse` undoes one redemption on a bill that
stays. Every case runs with the session shaped as a request's is: autoflush
off.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.models import AuditLog
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.finance.models import JournalEntry, JournalLine, JournalStatus
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.loyalty.api.router import router as loyalty_router
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.schemas import LoyaltySettingsWrite
from app.loyalty.services import LoyaltyService
from app.loyalty.services.redemption_reversal import RedemptionReversalService
from app.sales_invoice.models import SalesInvoice
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services.settlement_service import ReceiptService
from tests.unit.test_sales_invoice_module import (
    _firm,
    _invoice_from_sales_order,
    _session_factory,
)


class _Till:
    """A firm with a scheme, one approved bill of 400 and 50 points held."""

    def __init__(self) -> None:
        """Approve the bill, then credit a batch the customer can spend."""
        self.session: Session = _session_factory()()
        self.session.autoflush = False
        self.firm_id: UUID = _firm(self.session).id
        self.actor_id = uuid4()
        self.bills, self.bill_id = _invoice_from_sales_order(
            self.session, firm_id=self.firm_id
        )
        seed_finance_setup(
            self.session,
            firm_id=self.firm_id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.loyalty = LoyaltyService(self.session)
        self.loyalty.write_settings(
            self.firm_id,
            LoyaltySettingsWrite(
                is_enabled=True,
                # Nothing earned on the bill itself, so the arithmetic below
                # is about the batch alone.
                points_per_amount=Decimal("0"),
                amount_per_point=Decimal("1"),
            ),
            actor_id=self.actor_id,
        )
        self.bill = self.bills.approve_invoice(
            self.bill_id, firm_scope=self.firm_id, actor_id=self.actor_id
        )
        self.session.commit()
        self.customer_id: UUID = self.bill.customer_id
        self.today = firm_today(self.session, self.firm_id)
        self.batch = self.credit("50", expires_on=self.today + timedelta(days=90))

    def credit(self, points: str, *, expires_on: date | None) -> LoyaltyEntry:
        """Credit a batch of points at one rupee each."""
        row = LoyaltyEntry(
            firm_id=self.firm_id,
            customer_id=self.customer_id,
            kind=LoyaltyEntryKind.EARNED.value,
            points=Decimal(points),
            amount=Decimal(points),
            earned_on=date(2026, 8, 1),
            expires_on=expires_on,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def redeem(self, points: str, *, on: UUID | None = None) -> LoyaltyEntry:
        """Spend points on the bill, as the route does."""
        return self.loyalty.redeem(
            firm_scope=self.firm_id,
            invoice_id=on or self.bill_id,
            points=Decimal(points),
            actor_id=self.actor_id,
        )

    def cancel(self) -> SalesInvoice:
        """Cancel the bill, as the route does, and commit."""
        row = self.bills.cancel_invoice(
            self.bill_id, firm_scope=self.firm_id, actor_id=self.actor_id
        )
        self.session.commit()
        return row

    def reverse(self, entry: LoyaltyEntry, reason: str = "Wrong bill.") -> LoyaltyEntry:
        """Undo one redemption through the service the route calls."""
        return RedemptionReversalService(self.session).reverse(
            entry.id, firm_scope=self.firm_id, reason=reason, actor_id=self.actor_id
        )

    def points(self) -> Decimal:
        """Return what the customer holds."""
        self.session.expire_all()
        return self.loyalty.balance(self.customer_id, firm_scope=self.firm_id).points

    def owed_on_bill(self) -> Decimal:
        """Return what the bill still owes, as a redemption reads it."""
        self.session.expire_all()
        bill = self.session.get(SalesInvoice, self.bill_id)
        assert bill is not None
        return self.loyalty._outstanding_of(bill, firm_scope=self.firm_id)

    def outstanding(self) -> Decimal:
        """Return the customer's own balance."""
        self.session.expire_all()
        customer = self.session.get(Customer, self.customer_id)
        assert customer is not None
        return Decimal(str(customer.current_outstanding))

    def left(self) -> dict[UUID, Decimal]:
        """Return what each batch still holds."""
        self.session.expire_all()
        return {
            batch.id: remaining
            for batch, remaining in self.loyalty.unspent_batches(
                self.customer_id, firm_scope=self.firm_id
            )
        }

    def account_balance(self, purpose: ControlAccountPurpose) -> Decimal:
        """Return debits less credits on one control account, posted or not."""
        account = ControlAccountService(self.session).resolve(self.firm_id, purpose)
        legs = self.session.scalars(
            select(JournalLine).where(JournalLine.ledger_account_id == account)
        ).all()
        return sum(
            (
                Decimal(str(leg.debit_amount)) - Decimal(str(leg.credit_amount))
                for leg in legs
            ),
            Decimal("0"),
        )


def test_a_bill_with_points_spent_on_it_can_be_cancelled() -> None:
    """The cancellation puts the points back itself, in its own transaction."""
    till = _Till()
    spent = till.redeem("30")
    assert till.points() == Decimal("20.0000")
    assert till.outstanding() == Decimal("370.0000")

    cancelled = till.cancel()

    assert cancelled.status == "CANCELLED"
    assert till.points() == Decimal("50.0000")
    assert till.outstanding() == Decimal("0.0000")
    undone = till.session.scalars(
        select(LoyaltyEntry).where(LoyaltyEntry.reverses_id == spent.id)
    ).one()
    assert (undone.kind, undone.points, undone.amount) == (
        "REDEEMED",
        Decimal("30.0000"),
        Decimal("-30.0000"),
    )
    assert undone.sales_invoice_id == till.bill_id


def test_the_points_go_back_to_their_batch_on_its_own_date() -> None:
    """Fifty again, on the expiry date the batch always carried."""
    till = _Till()
    expires_on = till.batch.expires_on
    till.redeem("30")
    assert till.left() == {till.batch.id: Decimal("20.0000")}

    till.cancel()

    assert till.left() == {till.batch.id: Decimal("50.0000")}
    batch = till.session.get(LoyaltyEntry, till.batch.id)
    assert batch is not None and batch.expires_on == expires_on
    assert (
        till.session.scalars(
            select(LoyaltyEntry).where(LoyaltyEntry.kind == "EXPIRED")
        ).all()
        == []
    )


def test_the_redemption_journal_is_mirrored_under_its_own_reference() -> None:
    """`Dr Receivable / Cr Loyalty Payable`, and the liability is whole again."""
    till = _Till()
    payable_before = till.account_balance(ControlAccountPurpose.LOYALTY_PAYABLE)
    first, second = till.redeem("10"), till.redeem("5")
    number = till.bill.invoice_number

    till.cancel()

    references = {}
    for entry in (first, second):
        journal = till.session.get(JournalEntry, entry.journal_entry_id)
        assert journal is not None and journal.status == JournalStatus.REVERSED.value
        references[journal.reference_number] = till.session.scalars(
            select(JournalEntry.reference_number).where(
                JournalEntry.reversal_of_id == journal.id
            )
        ).one()
    assert references == {
        f"LOY-RED-{number}": f"LOY-RED-{number}-REV",
        f"LOY-RED-{number}-2": f"LOY-RED-{number}-2-REV",
    }
    assert till.account_balance(ControlAccountPurpose.LOYALTY_PAYABLE) == payable_before


def test_a_receipt_on_the_bill_is_still_reversed_by_a_person_first() -> None:
    """Money that changed hands keeps its rule; the points are not touched."""
    till = _Till()
    till.redeem("30")
    ReceiptService(till.session).create(
        SettlementCreate(
            party_id=till.customer_id,
            settlement_date=till.bill.invoice_date,
            amount=Decimal("100"),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=till.bill_id, amount=Decimal("100")
                )
            ],
        ),
        firm_id=till.firm_id,
        actor_id=uuid4(),
    )
    till.session.commit()

    with pytest.raises(ValidationError) as refused:
        till.cancel()
    till.session.rollback()

    assert "money applied from" in refused.value.message
    assert "loyalty points" not in refused.value.message
    assert till.points() == Decimal("20.0000")
    bill = till.session.get(SalesInvoice, till.bill_id)
    assert bill is not None and bill.status == "APPROVED"


def test_one_redemption_is_reversed_on_a_bill_that_stays() -> None:
    """Keyed against the wrong bill: the bill owes in full again and stands."""
    till = _Till()
    spent = till.redeem("30")
    assert till.owed_on_bill() == Decimal("370.00")

    undone = till.reverse(spent, "Keyed against the wrong bill.")

    assert till.owed_on_bill() == Decimal("400.00")
    assert till.outstanding() == Decimal("400.0000")
    assert till.points() == Decimal("50.0000")
    assert undone.remarks == (
        f"30.0000 points put back from {till.bill.invoice_number}: "
        "Keyed against the wrong bill."
    )
    bill = till.session.get(SalesInvoice, till.bill_id)
    assert bill is not None and bill.status == "APPROVED"
    trail = till.session.scalars(
        select(AuditLog).where(AuditLog.action == "loyalty.redemption_reversed")
    ).one()
    assert trail.entity_id == undone.id
    assert trail.after_data["reason"] == "Keyed against the wrong bill."


def test_the_points_can_be_spent_again_and_the_bill_then_cancelled() -> None:
    """A second redemption takes its own reference; both are told apart."""
    till = _Till()
    till.reverse(till.redeem("30"))

    again = till.redeem("40")
    till.cancel()

    assert till.points() == Decimal("50.0000")
    journal = till.session.get(JournalEntry, again.journal_entry_id)
    assert journal is not None
    assert journal.reference_number == f"LOY-RED-{till.bill.invoice_number}-2"
    assert journal.status == JournalStatus.REVERSED.value
    assert till.outstanding() == Decimal("0.0000")


def test_a_redemption_is_put_back_once() -> None:
    """The second attempt is told when the first was made."""
    till = _Till()
    spent = till.redeem("30")
    undone = till.reverse(spent)

    with pytest.raises(ValidationError) as refused:
        till.reverse(spent)
    till.session.rollback()

    assert refused.value.message == (
        f"Those points were already put back, on {undone.earned_on.isoformat()}."
    )
    assert till.points() == Decimal("50.0000")


def test_the_ledger_says_which_redemption_was_put_back_and_by_what() -> None:
    """A screen offers "put points back" once, without guessing from its rows.

    The desktop read the last hundred entries and inferred a reversal from a
    row of the same bill with opposite points. The ledger now says it: the
    redemption reads reversed, and the row that undid it names it.
    """
    from app.loyalty.services.loyalty_service import LoyaltyService

    till = _Till()
    spent = till.redeem("30")
    kept = till.redeem("5")
    undone = till.reverse(spent)

    rows = {
        row.id: row
        for row in LoyaltyService(till.session).describe([spent, kept, undone])
    }

    assert (rows[spent.id].is_reversed, rows[spent.id].reverses_id) == (True, None)
    assert (rows[kept.id].is_reversed, rows[kept.id].reverses_id) == (False, None)
    assert (rows[undone.id].is_reversed, rows[undone.id].reverses_id) == (
        False,
        spent.id,
    )


def test_the_row_that_puts_points_back_is_not_itself_reversed() -> None:
    """There is one way to spend points again: redeem them."""
    till = _Till()
    undone = till.reverse(till.redeem("30"))

    with pytest.raises(ValidationError) as refused:
        till.reverse(undone)
    till.session.rollback()

    assert refused.value.message == (
        "That entry is points being put back, not points spent; it cannot "
        "be reversed."
    )


def test_a_reason_is_required_and_another_firms_entry_is_not_found() -> None:
    """Blank is refused; an id from elsewhere reads as not found."""
    till = _Till()
    spent = till.redeem("30")

    with pytest.raises(ValidationError, match="Say why"):
        till.reverse(spent, "   ")
    with pytest.raises(ResourceNotFoundError, match="Redemption not found"):
        RedemptionReversalService(till.session).reverse(
            spent.id, firm_scope=uuid4(), reason="x", actor_id=till.actor_id
        )
    with pytest.raises(ResourceNotFoundError):
        till.reverse(till.batch)
    till.session.rollback()
    assert till.points() == Decimal("20.0000")


def test_a_batch_that_has_since_lapsed_stays_lapsed() -> None:
    """Points returned to a batch past its date are written off there and then.

    Thirty of fifty were spent while the batch was in date. Its date passes;
    the redemption is undone. The thirty come back to the batch they left,
    which has lapsed, so they lapse with it -- and only they: the twenty that
    were never spent are the sweep's, as before.
    """
    till = _Till()
    payable_before = till.account_balance(ControlAccountPurpose.LOYALTY_PAYABLE)
    spent = till.redeem("30")
    batch = till.session.get(LoyaltyEntry, till.batch.id)
    assert batch is not None
    batch.expires_on = till.today - timedelta(days=1)
    till.session.commit()

    till.reverse(spent)

    lapsed = till.session.scalars(
        select(LoyaltyEntry).where(LoyaltyEntry.kind == "EXPIRED")
    ).one()
    assert (lapsed.points, lapsed.reverses_id) == (Decimal("-30.0000"), batch.id)
    release = till.session.get(JournalEntry, lapsed.journal_entry_id)
    assert release is not None and release.status == JournalStatus.POSTED.value
    # The twenty never spent are still on the batch for the sweep to take,
    # and out of the balance already: a lapsed point is not held (D-PRC-3).
    assert till.points() == Decimal("0.0000")
    assert till.left() == {batch.id: Decimal("20.0000")}
    # Redeemed 30 (Dr), put back 30 (Cr), lapsed 30 (Dr): thirty less is owed
    # in points than before, which is the thirty nobody can claim.
    assert till.account_balance(
        ControlAccountPurpose.LOYALTY_PAYABLE
    ) - payable_before == Decimal("30.00")


def test_a_newer_batch_keeps_everything_when_an_old_one_is_restored() -> None:
    """Oldest first: the redemption came out of the old batch, and returns to it."""
    till = _Till()
    fresh = LoyaltyEntry(
        firm_id=till.firm_id,
        customer_id=till.customer_id,
        kind=LoyaltyEntryKind.EARNED.value,
        points=Decimal("40"),
        amount=Decimal("80"),
        earned_on=date(2026, 9, 1),
        expires_on=None,
        created_by=till.actor_id,
        updated_by=till.actor_id,
    )
    till.session.add(fresh)
    till.session.commit()
    spent = till.redeem("30")
    assert spent.amount == Decimal("30.0000"), "the old batch, at 1.00 a point"

    till.reverse(spent)

    assert till.left() == {
        till.batch.id: Decimal("50.0000"),
        fresh.id: Decimal("40.0000"),
    }


def test_the_route_takes_the_code_a_redemption_takes() -> None:
    """`LOYALTY_MANAGE`, declared with a reason in the body."""
    routes = {
        route.path: route
        for route in loyalty_router.routes
        if isinstance(route, APIRoute)
    }
    route = routes["/api/v1/loyalty/redemptions/{entry_id}/reverse"]
    assert route.methods == {"POST"}
    redeem = routes["/api/v1/loyalty/redeem"]

    def scope_of(found: APIRoute) -> object:
        """Return the scope dependency a route declares."""
        return next(
            dependency.call
            for dependency in found.dependant.dependencies
            if dependency.name == "scope"
        )

    assert scope_of(route) is scope_of(redeem)
