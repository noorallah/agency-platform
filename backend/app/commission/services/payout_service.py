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
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.commission.models import CommissionPayout, CommissionPayoutStatus
from app.commission.schemas.payout import (
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
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
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

        Args:
            data: The period, optionally narrowed to one person.
            firm_id: The owning firm.
            actor_id: The user running the accrual.

        Returns:
            The payouts created, biggest first.

        Raises:
            ConflictError: If a live payout already covers part of the period
                for one of the people it would accrue for.

        """
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
            payout = CommissionPayout(
                firm_id=firm_id,
                salesman_id=row.salesman_id,
                period_start=data.period_start,
                period_end=data.period_end,
                basis=row.basis,
                measured_amount=measured,
                earned_amount=row.commission_amount,
                adjustment_amount=ZERO,
                payable_amount=row.commission_amount,
                status=CommissionPayoutStatus.DRAFT.value,
                accrued_on=accrued_on,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(payout)
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
        payable = Decimal(str(row.earned_amount)) + Decimal(str(row.adjustment_amount))
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

    def approve(
        self,
        payout_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> CommissionPayout:
        """Recognise the debt and post the accrual journal.

        Args:
            payout_id: The payout to approve.
            firm_id: The owning firm.
            actor_id: The user approving it.
            expected_version: The version the caller last read, if any.

        Returns:
            The approved payout.

        Raises:
            ValidationError: If it is not a draft, or owes nothing.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != CommissionPayoutStatus.DRAFT.value:
            raise ValidationError("Only a draft payout can be approved.")
        if row.payable_amount <= ZERO:
            raise ValidationError("A payout of nothing cannot be approved.")
        before = self._snapshot(row)
        entry = self._posting.post_commission_accrual(
            firm_id=firm_id,
            payout_id=row.id,
            reference=self.reference_for(row),
            accrued_on=row.accrued_on,
            amount=Decimal(str(row.payable_amount)),
            actor_id=actor_id,
        )
        row.journal_entry_id = entry.id
        row.status = CommissionPayoutStatus.APPROVED.value
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

        The account is not checked here: `JournalEntryEngine._load_accounts`
        already refuses an id that is not this firm's live chart, before
        anything posts. A second check in this service would change no
        outcome, and a guard that changes no outcome is the thing this repo's
        review checklist exists to keep out.

        Raises:
            ValidationError: If it has not been approved, or the account named
                is not one of this firm's live ledger accounts.

        """
        row = self.get_payout(payout_id, firm_id=firm_id)
        assert_version(row.version, expected_version)
        if row.status != CommissionPayoutStatus.APPROVED.value:
            raise ValidationError(
                "Only an approved payout can be paid. Approve it first, which "
                "is what recognises the debt."
            )
        before = self._snapshot(row)
        entry = self._posting.post_commission_payment(
            firm_id=firm_id,
            payout_id=row.id,
            # Its own reference, not the accrual's: a journal reference is
            # unique, so sharing one made an approved payout impossible to
            # pay -- the payment entry collided with the accrual that had
            # just been posted for it.
            reference=f"{self.reference_for(row)}-PAY",
            paid_on=data.paid_on,
            amount=Decimal(str(row.payable_amount)),
            money_account_id=data.money_account_id,
            actor_id=actor_id,
        )
        row.payment_journal_entry_id = entry.id
        row.money_account_id = data.money_account_id
        row.paid_on = data.paid_on
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
            payable_amount=row.payable_amount,
            status=CommissionPayoutStatusEnum(row.status),
            accrued_on=row.accrued_on,
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
            "payable_amount": str(row.payable_amount),
            "status": row.status,
            "accrued_on": row.accrued_on.isoformat(),
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
