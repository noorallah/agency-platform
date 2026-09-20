"""Accruing, approving, paying and cancelling commission.

`CommissionService.report` answers what a period earned. This is what turns
that answer into a debt the books can see and money that leaves the firm.

The rule the whole module turns on: **the report is read once, at accrual, and
never again.** Everything downstream reads the stored row. The report walks
live documents, so asking it a second time in September answers a different
number than the one approved in April -- a settlement reversed, an invoice
cancelled, a rate corrected -- and a payout that changes after it was approved
is one nobody can reconcile against the journal it posted.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.commission.models import (
    CommissionClawback,
    CommissionPayout,
    CommissionPayoutStatus,
)
from app.commission.schemas.payout import (
    CommissionPaymentMethodEnum,
    CommissionPayoutAccrue,
    CommissionPayoutPay,
    CommissionPayoutResponse,
    CommissionPayoutStatusEnum,
    CommissionPayoutUpdate,
)
from app.commission.services.commission_service import (
    FORMER_MEMBER_LABEL,
    CommissionService,
)
from app.common.audit.services import record_audit
from app.core.concurrency import assert_version
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.journal_engine import quantize_money as quantize_ledger

#: Statuses that still hold a claim on a period. A CANCELLED payout does not,
#: which is what makes re-accruing a corrected period possible.
LIVE_STATUSES = (
    CommissionPayoutStatus.DRAFT.value,
    CommissionPayoutStatus.APPROVED.value,
    CommissionPayoutStatus.PAID.value,
)


class CommissionPayoutService:
    """Turn a period's earnings into an approved, posted and paid debt."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session
        self._commission = CommissionService(session)
        self._posting = DocumentPostingService(session)
        self._journals = JournalEntryEngine(session)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def _scoped(
        self, statement: Select[tuple[CommissionPayout]], firm_id: UUID
    ) -> Select[tuple[CommissionPayout]]:
        """Restrict a payout query to one firm's live rows."""
        return statement.where(
            CommissionPayout.firm_id == firm_id,
            CommissionPayout.is_deleted.is_(False),
        )

    def list_payouts(
        self,
        *,
        firm_id: UUID,
        page: int,
        page_size: int,
        salesman_id: UUID | None = None,
        status: CommissionPayoutStatusEnum | None = None,
    ) -> tuple[Sequence[CommissionPayout], int]:
        """Return one page of payouts, most recent period first.

        Args:
            firm_id: The owning firm.
            page: One-based page number.
            page_size: How many rows to return.
            salesman_id: Restrict to one person.
            status: Restrict to one state.

        Returns:
            The page of payouts and the total matching count.

        """
        statement = self._scoped(select(CommissionPayout), firm_id)
        if salesman_id is not None:
            statement = statement.where(CommissionPayout.salesman_id == salesman_id)
        if status is not None:
            statement = statement.where(CommissionPayout.status == status.value)
        total = self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = self._session.scalars(
            statement.order_by(
                CommissionPayout.period_start.desc(),
                CommissionPayout.created_at.desc(),
                CommissionPayout.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return rows, int(total or 0)

    def get_payout(self, payout_id: UUID, *, firm_id: UUID) -> CommissionPayout:
        """Return one payout.

        Args:
            payout_id: The payout to read.
            firm_id: The owning firm.

        Returns:
            The payout.

        Raises:
            ResourceNotFoundError: If the firm has no such live payout.

        """
        row = self._session.scalar(
            self._scoped(select(CommissionPayout), firm_id).where(
                CommissionPayout.id == payout_id
            )
        )
        if row is None:
            raise ResourceNotFoundError("Commission payout not found.")
        return row

    # ------------------------------------------------------------------
    # Accrual
    # ------------------------------------------------------------------

    def accrue(
        self, data: CommissionPayoutAccrue, *, firm_id: UUID, actor_id: UUID
    ) -> list[CommissionPayout]:
        """Turn what a period earned into draft payouts.

        Reads the report once and stores what it said. Everything after this
        reads the row, not the report -- see the module docstring.

        Nobody who earned nothing gets a row: a payout of zero is a piece of
        paperwork that has to be approved and paid like any other, and it says
        nothing the report does not.

        **What an earlier, paid period is now short by is taken off here.** A
        bill credited or returned after its period was paid makes that period
        worth less than was paid on it; the PAID row is never rewritten, so
        the shortfall is carried onto this accrual as a clawback, up to what
        this period earned, and the rest waits for the next (D-TER-3).

        **Only a period that has ended can be accrued (D-TER-6).** The payout
        holds the whole period against a second accrual and a paid one cannot
        be cancelled, so whatever is collected between an early accrual and
        the period's end belongs to no payout, ever. Judged against today in
        UTC, the only clock this repo reads. The booking date may not precede
        the period's end -- the cost belongs to the period -- nor fall in the
        future, which would date a journal for a day that has not happened.
        Any length of period is allowed: the overlap guard already refuses
        the same day being paid twice, and a firm that pays fortnightly is
        not wrong.

        Args:
            data: The period, optionally narrowed to one person.
            firm_id: The owning firm.
            actor_id: The user running the accrual.

        Returns:
            The payouts created, biggest first.

        Raises:
            ValidationError: If the period runs backwards, has not ended, or
                the booking date is outside the window it may fall in.
            ConflictError: If a live payout already covers part of the period
                for one of the people it would accrue for.

        """
        self._assert_period_has_ended(data)
        report = self._commission.report(
            firm_id=firm_id,
            from_date=data.period_start,
            to_date=data.period_end,
            salesman_id=data.salesman_id,
        )
        accrued_on = data.accrued_on or data.period_end
        created: list[CommissionPayout] = []
        for row in report.rows:
            # The Unassigned bucket belongs to nobody, so there is nobody to
            # pay; it stays in the report for the cash-book reconciliation and
            # never becomes a payout.
            if row.salesman_id is None or row.commission_amount <= ZERO:
                continue
            self._assert_period_is_free(
                firm_id=firm_id,
                salesman_id=row.salesman_id,
                period_start=data.period_start,
                period_end=data.period_end,
            )
            measured = (
                row.invoiced_amount if row.basis == "INVOICED" else row.collected_amount
            )
            recovered = self._recover(
                firm_id=firm_id,
                salesman_id=row.salesman_id,
                available=Decimal(str(row.commission_amount)),
            )
            clawback = sum((amount for _, amount in recovered), ZERO)
            payout = CommissionPayout(
                firm_id=firm_id,
                salesman_id=row.salesman_id,
                period_start=data.period_start,
                period_end=data.period_end,
                basis=row.basis,
                measured_amount=measured,
                earned_amount=row.commission_amount,
                adjustment_amount=ZERO,
                clawback_amount=clawback,
                payable_amount=quantize_ledger(
                    Decimal(str(row.commission_amount)) - clawback
                ),
                status=CommissionPayoutStatus.DRAFT.value,
                accrued_on=accrued_on,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(payout)
            try:
                self._session.flush()
            except IntegrityError as exc:
                # The partial unique index caught what the read above could
                # not: another request accrued this person's period between
                # the check and the write. Translated here so the loser is
                # refused by name rather than answered with a 500.
                self._session.rollback()
                raise ConflictError(
                    "A commission payout for that period was created while "
                    "this one was being worked out. Reload and check before "
                    "accruing again."
                ) from exc
            for source, amount in recovered:
                self._session.add(
                    CommissionClawback(
                        firm_id=firm_id,
                        payout_id=payout.id,
                        source_payout_id=source.id,
                        amount=amount,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            self._session.flush()
            record_audit(
                self._session,
                action="commission.payout.accrued",
                entity_type="commission_payout",
                entity_id=payout.id,
                actor_id=actor_id,
                firm_id=firm_id,
                after_data=self._snapshot(payout),
            )
            created.append(payout)
        return created

    def _recover(
        self, *, firm_id: UUID, salesman_id: UUID, available: Decimal
    ) -> list[tuple[CommissionPayout, Decimal]]:
        """Say what this accrual takes back from the person's paid periods.

        For each PAID payout of theirs, the period's report is read again and
        the difference between what was paid on it and what it is worth now
        -- less whatever a live later payout has already recovered -- is the
        shortfall. Only a shortfall is carried: a period now worth *more* is
        not paid again, because nothing about it was owed at the time.

        The re-read is the one place a paid period's report is consulted
        after accrual, and it changes nothing on the paid row. It exists so
        that a credit note or a return after payment reaches the person who
        was paid on the sale, which is what a firm means by commission on net
        sales.

        Applied oldest period first, each up to what is left of `available`,
        because a payout cannot take money back: what this period cannot
        cover waits for the next.

        Args:
            firm_id: The owning firm.
            salesman_id: The person being accrued for.
            available: What this period earned, which is the most that can be
                recovered now.

        Returns:
            The paid payouts recovered from, with the amount taken off each.

        """
        if available <= ZERO:
            return []
        paid = self._session.scalars(
            self._scoped(select(CommissionPayout), firm_id)
            .where(
                CommissionPayout.salesman_id == salesman_id,
                CommissionPayout.status == CommissionPayoutStatus.PAID.value,
            )
            .order_by(CommissionPayout.period_start.asc(), CommissionPayout.id.asc())
        ).all()
        recovered: list[tuple[CommissionPayout, Decimal]] = []
        for source in paid:
            if available <= ZERO:
                break
            shortfall = self._shortfall_of(source)
            if shortfall <= ZERO:
                continue
            taken = min(shortfall, available)
            recovered.append((source, taken))
            available -= taken
        return recovered

    def _shortfall_of(self, source: CommissionPayout) -> Decimal:
        """Return what a paid payout's period is now short by, net of recoveries."""
        report = self._commission.report(
            firm_id=source.firm_id,
            from_date=source.period_start,
            to_date=source.period_end,
            salesman_id=source.salesman_id,
        )
        worth_now = sum(
            (
                Decimal(str(row.commission_amount))
                for row in report.rows
                if row.salesman_id == source.salesman_id
            ),
            ZERO,
        )
        already = self._session.scalar(
            select(func.coalesce(func.sum(CommissionClawback.amount), 0))
            .join(CommissionPayout, CommissionPayout.id == CommissionClawback.payout_id)
            .where(
                CommissionClawback.source_payout_id == source.id,
                CommissionClawback.is_deleted.is_(False),
                CommissionPayout.is_deleted.is_(False),
                CommissionPayout.status != CommissionPayoutStatus.CANCELLED.value,
            )
        )
        return quantize_ledger(
            Decimal(str(source.earned_amount)) - worth_now - Decimal(str(already or 0))
        )

    def _assert_period_has_ended(self, data: CommissionPayoutAccrue) -> None:
        """Refuse a period still running, and a booking date outside its window.

        Args:
            data: The accrual being asked for.

        Raises:
            ValidationError: If the period runs backwards or has not ended,
                or `accrued_on` precedes the period's end or is in the future.

        """
        today = self.utc_today()
        if data.period_end < data.period_start:
            raise ValidationError("period_end cannot be before period_start.")
        if data.period_end >= today:
            first_free_day = data.period_end + timedelta(days=1)
            raise ValidationError(
                "That period has not ended. A payout accrued before its last "
                "day is over would leave whatever is collected afterwards "
                f"belonging to no payout; accrue it from {first_free_day:%Y-%m-%d}."
            )
        if data.accrued_on is not None:
            if data.accrued_on < data.period_end:
                raise ValidationError(
                    "The accrual cannot be booked before the period ends: "
                    "the cost belongs to the period it was earned in."
                )
            if data.accrued_on > today:
                raise ValidationError(
                    "The accrual cannot be booked on a day that has not "
                    "happened yet."
                )

    def _assert_period_is_free(
        self,
        *,
        firm_id: UUID,
        salesman_id: UUID,
        period_start: date,
        period_end: date,
    ) -> None:
        """Refuse a second live payout over one person's days.

        Two would pay the same collections twice and nothing downstream could
        say which was the real one. A CANCELLED payout holds no claim, so a
        period whose accrual was withdrawn can be run again.

        Args:
            firm_id: The owning firm.
            salesman_id: The person being accrued for.
            period_start: First day of the period.
            period_end: Last day of the period.

        Raises:
            ConflictError: If a live payout already covers part of it.

        """
        clash = self._session.scalar(
            self._scoped(select(CommissionPayout), firm_id).where(
                CommissionPayout.salesman_id == salesman_id,
                CommissionPayout.status.in_(LIVE_STATUSES),
                CommissionPayout.period_start <= period_end,
                CommissionPayout.period_end >= period_start,
            )
        )
        if clash is not None:
            raise ConflictError(
                "A commission payout already covers part of that period for "
                f"this salesman ({clash.period_start.isoformat()} to "
                f"{clash.period_end.isoformat()})."
            )

    # ------------------------------------------------------------------
    # Adjustment
    # ------------------------------------------------------------------

    def update_payout(
        self,
        payout_id: UUID,
        data: CommissionPayoutUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionPayout:
        """Adjust or annotate a payout nobody has approved.

        Only while DRAFT. Changing what was approved would leave the journal
        saying one number and the record saying another, and the way to
        correct an approved payout is to cancel it -- which reverses the
        journal -- and accrue again.

        Args:
            payout_id: The payout to change.
            data: The fields to change.
            firm_id: The owning firm.
            actor_id: The user making the change.
            expected_version: The version the caller last read, if any.

        Returns:
            The changed payout.

        Raises:
            ValidationError: If the payout has left DRAFT, or the adjustment
                would make it owe a negative amount.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != CommissionPayoutStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft payout can be adjusted. Cancel this one and "
                "accrue the period again."
            )
        before = self._snapshot(row)
        values = data.model_dump(exclude_unset=True)
        if values.get("adjustment_amount") is not None:
            row.adjustment_amount = values["adjustment_amount"]
        if "adjustment_reason" in values:
            row.adjustment_reason = values["adjustment_reason"]
        if "notes" in values:
            row.notes = values["notes"]
        payable = (
            Decimal(str(row.earned_amount))
            - Decimal(str(row.clawback_amount))
            + Decimal(str(row.adjustment_amount))
        )
        if payable < ZERO:
            raise ValidationError(
                "That adjustment would make the payout negative. A payout "
                "cannot take money back; record what is owed as zero and "
                "settle the difference separately."
            )
        # An adjustment with no reason is a number nobody can explain at the
        # year end, so it is refused rather than merely discouraged.
        if row.adjustment_amount != ZERO and not (row.adjustment_reason or "").strip():
            raise ValidationError("Say why the payout is being adjusted.")
        row.payable_amount = quantize_ledger(payable)
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.payout.updated",
            entity_type="commission_payout",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    # ------------------------------------------------------------------
    # Approval, payment, cancellation
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_not_own(row: CommissionPayout, actor_id: UUID, *, doing: str) -> None:
        """Refuse to let the person a payout pays approve or pay it.

        Judged on `salesman_id` against the actor, whatever roles the actor
        holds: a salesman who is also the accountant is still the payee.

        Args:
            row: The payout being acted on.
            actor_id: The user acting.
            doing: The verb for the message -- "approve" or "pay".

        Raises:
            AuthorizationError: If the actor is the payee.

        """
        if row.salesman_id == actor_id:
            raise AuthorizationError(
                f"You cannot {doing} your own commission payout. Ask somebody "
                "else to; a payout is agreed by a person it does not pay."
            )

    def approve(
        self,
        payout_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionPayout:
        """Recognise the debt and post the accrual journal.

        **The approver is a second person.** Not the one the payout pays, and
        not the one who accrued it: one person who could state a debt, raise
        it and agree it -- their own included -- did exactly that (D-TER-4).
        Judged on the person, not the role, so holding two roles buys
        nothing.

        Args:
            payout_id: The payout to approve.
            firm_id: The owning firm.
            actor_id: The user approving it.
            expected_version: The version the caller last read, if any.

        Returns:
            The approved payout.

        Raises:
            ValidationError: If it is not a draft, or owes nothing.
            AuthorizationError: If the actor is the payee or the accruer.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != CommissionPayoutStatus.DRAFT.value:
            raise ValidationError("Only a draft payout can be approved.")
        if row.payable_amount <= ZERO and row.clawback_amount <= ZERO:
            raise ValidationError("A payout of nothing cannot be approved.")
        self._assert_not_own(row, actor_id, doing="approve")
        if row.created_by == actor_id:
            raise AuthorizationError(
                "The person who accrued a payout cannot approve it. Approval "
                "is a second person agreeing what the first stated."
            )
        before = self._snapshot(row)
        if row.payable_amount > ZERO:
            entry = self._posting.post_commission_accrual(
                firm_id=firm_id,
                payout_id=row.id,
                reference=self.reference_for(row),
                accrued_on=row.accrued_on,
                amount=Decimal(str(row.payable_amount)),
                actor_id=actor_id,
            )
            row.journal_entry_id = entry.id
        # A period whose earnings were wholly taken by a clawback owes
        # nothing and posts nothing: the expense it would have booked is
        # exactly the expense the earlier period overstated. Approving it
        # still matters -- it is what makes the recovery final.
        row.status = CommissionPayoutStatus.APPROVED.value
        row.approved_by = actor_id
        row.approved_at = utc_now()
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.payout.approved",
            entity_type="commission_payout",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def pay(
        self,
        payout_id: UUID,
        data: CommissionPayoutPay,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionPayout:
        """Settle an approved payout against the account the money left.

        Args:
            payout_id: The payout being paid.
            data: When it was paid and from where.
            firm_id: The owning firm.
            actor_id: The user recording the payment.
            expected_version: The version the caller last read, if any.

        Returns:
            The paid payout.

        The money leaves through the firm's **cash or bank** control account
        and nothing else. `JournalEntryEngine._load_accounts` only asked that
        the account was this firm's, so the credit leg could land on Trade
        Receivables, on Sales, or on Commission Payable itself -- which marked
        the payout PAID and moved no money (D-TER-5). Receipts and payments
        resolve theirs from the CASH / BANK purposes; this does the same.

        And not before it was accrued: a payment dated ahead of the accrual
        leaves the payable in debit between the two dates.

        **The payer is a third person**: not the payee, and not the approver
        (D-TER-4). Whoever agreed the debt must not be the one who moves the
        cash, which is the same line `COMMISSION_PAY` draws between roles,
        drawn here between people so that one person holding both roles is
        still refused.

        Raises:
            ValidationError: If it has not been approved, the account is not
                the firm's cash or bank, or the date precedes the accrual.
            AuthorizationError: If the actor is the payee or the approver.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != CommissionPayoutStatus.APPROVED.value:
            raise ValidationError(
                "Only an approved payout can be paid. Approve it first, which "
                "is what recognises the debt."
            )
        self._assert_not_own(row, actor_id, doing="pay")
        if row.approved_by == actor_id:
            raise AuthorizationError(
                "The person who approved a payout cannot pay it. Paying is a "
                "second person releasing what the first agreed."
            )
        if data.paid_on < row.accrued_on:
            raise ValidationError(
                "A payout cannot be paid before it was accrued "
                f"(accrued on {row.accrued_on.isoformat()})."
            )
        money_account_id = self._money_account(firm_id, data)
        before = self._snapshot(row)
        if row.payable_amount > ZERO:
            entry = self._posting.post_commission_payment(
                firm_id=firm_id,
                payout_id=row.id,
                # Its own reference, not the accrual's: a journal reference
                # is unique, so sharing one made an approved payout
                # impossible to pay -- the payment entry collided with the
                # accrual that had just been posted for it.
                reference=f"{self.reference_for(row)}-PAY",
                paid_on=data.paid_on,
                amount=Decimal(str(row.payable_amount)),
                money_account_id=money_account_id,
                actor_id=actor_id,
            )
            row.payment_journal_entry_id = entry.id
        # Nothing to pay when a clawback took the whole period; marking it
        # PAID records that the person has settled up.
        row.money_account_id = money_account_id
        row.paid_on = data.paid_on
        row.paid_by = actor_id
        row.status = CommissionPayoutStatus.PAID.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.payout.paid",
            entity_type="commission_payout",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    def _money_account(self, firm_id: UUID, data: CommissionPayoutPay) -> UUID:
        """Resolve the cash or bank account the payment leaves through.

        A `method` is resolved through the firm's control accounts, which
        refuse with a message naming the purpose when none is nominated. An
        account named outright has to be one of those same two.

        Args:
            firm_id: The owning firm.
            data: What the caller said about where the money left.

        Returns:
            The ledger account to credit.

        Raises:
            ValidationError: If the account named is neither the firm's cash
                nor its bank account.

        """
        controls = ControlAccountService(self._session)
        if data.method is not None:
            purpose = (
                ControlAccountPurpose.CASH
                if data.method is CommissionPaymentMethodEnum.CASH
                else ControlAccountPurpose.BANK
            )
            return controls.resolve(firm_id, purpose)
        mapping = controls.mapping(firm_id)
        allowed = {
            mapping.get(ControlAccountPurpose.CASH.value),
            mapping.get(ControlAccountPurpose.BANK.value),
        } - {None}
        if data.money_account_id not in allowed:
            raise ValidationError(
                "Commission is paid from the firm's cash or bank account -- the "
                "ones nominated under its control accounts -- and that account "
                "is neither."
            )
        assert data.money_account_id is not None
        return data.money_account_id

    def cancel(
        self,
        payout_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionPayout:
        """Withdraw a payout, reversing the accrual if one was posted.

        A paid payout cannot be cancelled: the money has gone, and undoing
        that is a payment in the other direction rather than a status change.

        Args:
            payout_id: The payout to withdraw.
            firm_id: The owning firm.
            actor_id: The user withdrawing it.
            expected_version: The version the caller last read, if any.

        Returns:
            The cancelled payout.

        Raises:
            ValidationError: If it has already been paid or cancelled.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status == CommissionPayoutStatus.PAID.value:
            raise ValidationError(
                "This payout has been paid. Record a payment the other way "
                "rather than cancelling it."
            )
        if row.status == CommissionPayoutStatus.CANCELLED.value:
            raise ValidationError("This payout is already cancelled.")
        before = self._snapshot(row)
        if row.journal_entry_id is not None:
            # A mirror is right here: what is being undone is worth exactly
            # what it was worth when it happened, unlike a stock reversal.
            self._journals.reverse_entry(
                row.journal_entry_id,
                firm_id=firm_id,
                reference_number=f"{self.reference_for(row)}-REV",
                journal_date=row.accrued_on,
                actor_id=actor_id,
            )
        row.status = CommissionPayoutStatus.CANCELLED.value
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="commission.payout.cancelled",
            entity_type="commission_payout",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._snapshot(row),
        )
        return row

    # ------------------------------------------------------------------
    # Responses
    # ------------------------------------------------------------------

    @staticmethod
    def reference_for(row: CommissionPayout) -> str:
        """Build the reference the journals carry.

        Derived from the period and the row rather than drawn from the
        document-numbering framework: a payout is an internal accrual, not a
        document anybody outside the firm ever sees, and giving it a numbering
        rule would make every firm configure one before it could pay anybody.

        This is the **accrual's** reference. The payment suffixes `-PAY` and a
        cancellation `-REV`, because a journal reference is unique and three
        entries against one payout cannot share one.
        """
        return f"COMM-{row.period_start:%Y%m}-{str(row.id)[:8]}"

    def payout_response(
        self, row: CommissionPayout, names: dict[UUID, str]
    ) -> CommissionPayoutResponse:
        """Build the response for one payout.

        Args:
            row: The stored payout.
            names: The firm's people by id.

        Returns:
            The response model.

        """
        return CommissionPayoutResponse(
            id=row.id,
            salesman_id=row.salesman_id,
            salesman_name=names.get(row.salesman_id) or FORMER_MEMBER_LABEL,
            period_start=row.period_start,
            period_end=row.period_end,
            basis=row.basis,
            measured_amount=row.measured_amount,
            earned_amount=row.earned_amount,
            adjustment_amount=row.adjustment_amount,
            adjustment_reason=row.adjustment_reason,
            clawback_amount=row.clawback_amount,
            payable_amount=row.payable_amount,
            status=CommissionPayoutStatusEnum(row.status),
            accrued_on=row.accrued_on,
            accrued_by=row.created_by,
            approved_by=row.approved_by,
            approved_at=row.approved_at,
            paid_by=row.paid_by,
            paid_on=row.paid_on,
            money_account_id=row.money_account_id,
            journal_entry_id=row.journal_entry_id,
            payment_journal_entry_id=row.payment_journal_entry_id,
            notes=row.notes,
            version=row.version,
        )

    @staticmethod
    def _snapshot(row: CommissionPayout) -> dict[str, object]:
        """Describe a payout for the audit trail."""
        return {
            "salesman_id": str(row.salesman_id),
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "basis": row.basis,
            "measured_amount": str(row.measured_amount),
            "earned_amount": str(row.earned_amount),
            "adjustment_amount": str(row.adjustment_amount),
            "adjustment_reason": row.adjustment_reason,
            "clawback_amount": str(row.clawback_amount),
            "payable_amount": str(row.payable_amount),
            "status": row.status,
            "accrued_on": row.accrued_on.isoformat(),
            "accrued_by": str(row.created_by) if row.created_by else None,
            "approved_by": str(row.approved_by) if row.approved_by else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "paid_by": str(row.paid_by) if row.paid_by else None,
            "paid_on": row.paid_on.isoformat() if row.paid_on else None,
            "journal_entry_id": (
                str(row.journal_entry_id) if row.journal_entry_id else None
            ),
            "payment_journal_entry_id": (
                str(row.payment_journal_entry_id)
                if row.payment_journal_entry_id
                else None
            ),
        }

    def names_for(self, firm_id: UUID) -> dict[UUID, str]:
        """Return the firm's people by id, through the platform store.

        Args:
            firm_id: The firm whose members to name.

        Returns:
            A mapping of user id to display name.

        """
        return self._commission.names_for(firm_id)

    def utc_today(self) -> date:
        """Return today in UTC, which is the only clock this repo reads."""
        return utc_now().date()
