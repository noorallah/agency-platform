"""Put back the points a redemption spent (D-PRC-6).

A redemption could not be undone. Cancelling a bill with points spent on it
was refused -- "...cannot be cancelled while it has loyalty points spent on
it. Reverse or cancel those first." -- and no route reversed one, so such a
bill could never be cancelled by anybody.

**Cancelling the bill puts the points back itself.** Money received on a bill
is a receipt, and the person reverses it first, deliberately: cash changed
hands and somebody has to say what became of it. A redemption is not money
that changed hands and points have no receipt screen, so there is nothing for
a person to decide; the cancellation undoes it in the same transaction. A
redemption keyed against the wrong bill is undone by its own route,
`POST /api/v1/loyalty/redemptions/{entry_id}/reverse`, on the bill that
stays.

**A redemption undone is a second REDEEMED row with the signs turned**, naming
the first in `reverses_id`: the points positive, the amount negative. What a
bill still owes is everywhere a sum of its REDEEMED amounts, and a balance is
a sum of points, so both net out in every reader without any of them being
told -- and a statement as of a day between the two still reads the bill as
settled, which it was.

Three things are undone together, each by the record of what was done:

- the **journal** is mirrored (`Dr Accounts Receivable / Cr Loyalty Payable`)
  under the redemption's own reference with `-REV`, so two redemptions of one
  bill never share one;
- the **customer's balance** goes back by the deltas stored on the LOYALTY
  row the redemption wrote, as a settlement's does;
- the **points** return to the batches: the redemption leaves the spending
  that batches are allocated against, oldest first, so each batch holds again
  what it held, on its own expiry date and at its own value. **A batch that
  has since lapsed stays lapsed** -- the share returned to a batch already
  past its date is written off there and then, with its cost released, as the
  sweep would have done had the points never been spent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.money import ZERO
from app.customers.models import CustomerReceivableTransaction
from app.customers.schemas import CustomerReceivableTransactionType
from app.customers.services import CustomerService
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.journal_engine import JournalEntryEngine
from app.loyalty.models import LoyaltyEntry, LoyaltyEntryKind
from app.loyalty.services.loyalty_service import LoyaltyService
from app.sales_invoice.models import SalesInvoice


class RedemptionReversalService:
    """Undo redemptions: one by hand, or all of a bill being cancelled."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._loyalty = LoyaltyService(session)

    def reverse(
        self,
        entry_id: UUID,
        *,
        firm_scope: UUID,
        reason: str,
        actor_id: UUID,
    ) -> LoyaltyEntry:
        """Undo one redemption on a bill that stays, and commit.

        Args:
            entry_id: The REDEEMED entry to undo.
            firm_scope: The owning firm.
            reason: Why, kept on the new entry and in the trail.
            actor_id: The user undoing it.

        Returns:
            The entry written.

        Raises:
            ResourceNotFoundError: If the entry is not a redemption of this
                firm's.
            ValidationError: If no reason is given, or it was undone already.

        """
        why = reason.strip()
        if not why:
            raise ValidationError("Say why the redemption is being reversed.")
        entry = self._redemption(entry_id, firm_scope=firm_scope)
        written = self.stage(entry, firm_id=firm_scope, reason=why, actor_id=actor_id)
        self._session.commit()
        return written

    def stage_for_cancelled_bill(
        self, invoice: SalesInvoice, *, firm_id: UUID, actor_id: UUID
    ) -> list[LoyaltyEntry]:
        """Put back every live redemption of a bill being cancelled.

        Never commits: the cancellation owns the transaction, so the points,
        the customer's balance and the bill go together or not at all.

        Returns:
            The entries written, oldest redemption first; empty where no
            points were spent on the bill.

        """
        redemptions = self._session.scalars(
            select(LoyaltyEntry)
            .where(
                LoyaltyEntry.firm_id == firm_id,
                LoyaltyEntry.sales_invoice_id == invoice.id,
                LoyaltyEntry.kind == LoyaltyEntryKind.REDEEMED.value,
                LoyaltyEntry.points < 0,
                LoyaltyEntry.is_deleted.is_(False),
            )
            .order_by(LoyaltyEntry.earned_on, LoyaltyEntry.created_at, LoyaltyEntry.id)
        ).all()
        return [
            self.stage(
                entry,
                firm_id=firm_id,
                reason=f"{invoice.invoice_number} cancelled.",
                actor_id=actor_id,
            )
            for entry in redemptions
            if self._undone_by(entry) is None
        ]

    def stage(
        self,
        entry: LoyaltyEntry,
        *,
        firm_id: UUID,
        reason: str,
        actor_id: UUID,
    ) -> LoyaltyEntry:
        """Undo one redemption without committing.

        Raises:
            ValidationError: If it was undone already, or the customer's
                balance has since moved so that it cannot be put back.

        """
        # Held before anything is read, as a redemption holds it: what each
        # batch has left is a sum over this customer's ledger.
        self._loyalty._hold_customer(entry.customer_id, firm_scope=firm_id)
        already = self._undone_by(entry)
        if already is not None:
            raise ValidationError(
                "Those points were already put back, on "
                f"{already.earned_on.isoformat()}."
            )
        invoice = self._session.get(SalesInvoice, entry.sales_invoice_id)
        number = "the bill" if invoice is None else invoice.invoice_number
        points = -Decimal(str(entry.points))
        amount = Decimal(str(entry.amount))
        before = {
            batch.id: remaining
            for batch, remaining in self._loyalty.unspent_batches(
                entry.customer_id, firm_scope=firm_id
            )
        }

        journal = (
            None
            if entry.journal_entry_id is None
            else self._session.get(JournalEntry, entry.journal_entry_id)
        )
        mirror = None
        if journal is not None and journal.status == JournalStatus.POSTED.value:
            mirror = JournalEntryEngine(self._session).reverse_entry(
                journal.id,
                firm_id=firm_id,
                # The redemption's own reference, which is already unique
                # among the redemptions of one bill (`LOY-RED-<bill>`, `-2`).
                reference_number=f"{journal.reference_number}-REV",
                actor_id=actor_id,
            )
        on = (
            max(firm_today(self._session, firm_id), entry.earned_on)
            if mirror is None
            else mirror.journal_date
        )
        self._put_balance_back(
            entry, number=number, on=on, firm_id=firm_id, actor_id=actor_id
        )

        undone = LoyaltyEntry(
            firm_id=firm_id,
            customer_id=entry.customer_id,
            kind=LoyaltyEntryKind.REDEEMED.value,
            # The first row with its signs turned, so every sum nets.
            points=points,
            amount=-amount,
            sales_invoice_id=entry.sales_invoice_id,
            earned_on=on,
            reverses_id=entry.id,
            journal_entry_id=None if mirror is None else mirror.id,
            remarks=f"{points} points put back from {number}: {reason}",
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(undone)
        self._session.flush()
        self._keep_lapsed_batches_lapsed(
            entry.customer_id,
            before=before,
            firm_id=firm_id,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="loyalty.redemption_reversed",
            entity_type="loyalty_entry",
            entity_id=undone.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=self._loyalty._entry_snapshot(entry),
            after_data=self._loyalty._entry_snapshot(undone) | {"reason": reason},
        )
        self._session.flush()
        return undone

    def _redemption(self, entry_id: UUID, *, firm_scope: UUID) -> LoyaltyEntry:
        """Fetch one redemption of this firm's, as it was first written."""
        entry = self._session.scalar(
            select(LoyaltyEntry).where(
                LoyaltyEntry.id == entry_id,
                LoyaltyEntry.firm_id == firm_scope,
                LoyaltyEntry.kind == LoyaltyEntryKind.REDEEMED.value,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )
        if entry is None:
            raise ResourceNotFoundError("Redemption not found.")
        if Decimal(str(entry.points)) > ZERO:
            raise ValidationError(
                "That entry is points being put back, not points spent; it "
                "cannot be reversed."
            )
        return entry

    def _undone_by(self, entry: LoyaltyEntry) -> LoyaltyEntry | None:
        """Return the row that already put this redemption back, if any."""
        return self._session.scalar(
            select(LoyaltyEntry).where(
                LoyaltyEntry.firm_id == entry.firm_id,
                LoyaltyEntry.reverses_id == entry.id,
                LoyaltyEntry.kind == LoyaltyEntryKind.REDEEMED.value,
                LoyaltyEntry.is_deleted.is_(False),
            )
        )

    def _put_balance_back(
        self,
        entry: LoyaltyEntry,
        *,
        number: str,
        on: date,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Undo the LOYALTY row the redemption wrote on the customer's account.

        By the deltas stored on that row, never recomputed: the journal alone
        would move the control account while the customer's own balance
        stayed where it was.
        """
        loyalty = CustomerReceivableTransactionType.LOYALTY.value
        posted = self._session.scalar(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.customer_id == entry.customer_id,
                CustomerReceivableTransaction.transaction_type == loyalty,
                CustomerReceivableTransaction.reference_type == "LOYALTY_ENTRY",
                CustomerReceivableTransaction.reference_id == entry.id,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        )
        if posted is None:
            # A redemption that never reached the customer's account has
            # nothing there to put back.
            return
        CustomerService(self._session).reverse_receivable_transaction(
            posted.id,
            firm_scope=firm_id,
            actor_id=actor_id,
            reference_number=number,
            remarks=f"Points put back from {number}.",
            commit=False,
            on=on,
        )

    def _keep_lapsed_batches_lapsed(
        self,
        customer_id: UUID,
        *,
        before: dict[UUID, Decimal],
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Write off what came back to a batch already past its date.

        Only the share this reversal returned: what such a batch held before
        is the sweep's to take, as it always was.
        """
        today = firm_today(self._session, firm_id)
        for batch, remaining in self._loyalty.unspent_batches(
            customer_id, firm_scope=firm_id
        ):
            if batch.expires_on is None or batch.expires_on >= today:
                continue
            returned = remaining - before.get(batch.id, ZERO)
            if returned > ZERO:
                self._loyalty._lapse(
                    batch,
                    returned,
                    firm_scope=firm_id,
                    today=today,
                    actor_id=actor_id,
                )
