"""PMT-06 deposits for a quarterly filer's first two months (GST-7, A83).

Under QRMP a quarter's GSTR-3B is filed once, but tax is deposited each month:
by the 25th of the next month for months 1 and 2, on PMT-06. Circular
143/13/2020 gives two ways to work the amount out, and the firm's GST
settings say which it uses:

* **Fixed sum** -- 35% of the tax paid in cash for the last quarter, if that
  quarter was filed quarterly; the whole of its last month's cash if it was
  filed monthly. Nothing to compute, which is why most small firms use it.
* **Self-assessment** -- the tax of the quarter so far, less its credit, less
  what the cash ledger already holds. The same set-off a settlement works
  out, over the months to date.

Both are suggestions: the person records what the challan actually paid, per
head. A deposit sets nothing off -- it posts Dr *GST Electronic Cash Ledger*
/ Cr the bank -- and the quarter's settlement uses it head by head before
asking the bank for more. What no settlement has used yet is the balance,
derived in ``cash_ledger_balance``.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models import AccountType, LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.gst_returns.models import (
    HEADS,
    GstCashDeposit,
    GstCashDepositStatus,
    GstPayment,
    GstPaymentStatus,
)
from app.gst_returns.services.filing_frequency import (
    FIXED_SUM,
    FilingFrequencyService,
    FilingPlan,
    month_bounds,
    quarter_label,
    quarter_months,
    shift,
)
from app.gst_returns.services.gst_payment_service import (
    GstPaymentService,
    cash_ledger_balance,
)

SOURCE_MODULE = "gst_cash_deposit"
#: The fixed sum is 35% of the last quarter's cash (rule 61A, circular 143).
FIXED_SUM_SHARE = Decimal("0.35")


def _rupees(value: Decimal) -> Decimal:
    """Round to whole rupees, as a challan is paid."""
    return quantize_ledger(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class DepositSuggestion:
    """What a month's PMT-06 deposit should be, and why."""

    return_period: str
    method: str
    due_date: date
    amounts: dict[str, Decimal]
    #: How the amounts were reached, in a sentence.
    basis: str
    #: What standing deposits for the month already paid, per head.
    deposited: dict[str, Decimal]

    @property
    def total(self) -> Decimal:
        """Return the suggested deposit across the heads."""
        return sum((self.amounts[head] for head in HEADS), ZERO)


class GstCashDepositService:
    """Suggest, record and take back PMT-06 deposits."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def suggestion(
        self, firm_id: UUID, return_period: str, *, method: str | None = None
    ) -> DepositSuggestion:
        """Return what month 1 or 2 of a quarter should deposit; writes nothing.

        Raises:
            ValidationError: For a month that takes no PMT-06 deposit.

        """
        plan = FilingFrequencyService(self._session).plan(firm_id)
        plan.require_deposit_month(return_period)
        chosen = method or plan.payment_method
        deposited = self._deposited(firm_id, [return_period])
        if chosen == FIXED_SUM:
            amounts, basis = self._fixed_sum(firm_id, plan, return_period)
        else:
            amounts, basis = self._self_assessed(firm_id, plan, return_period)
        return DepositSuggestion(
            return_period=return_period,
            method=chosen,
            due_date=plan.pmt06_due(return_period),
            amounts=amounts,
            basis=basis,
            deposited=deposited,
        )

    def record(
        self,
        firm_id: UUID,
        return_period: str,
        *,
        deposit_date: date,
        money_account_id: UUID,
        amounts: dict[str, Decimal],
        actor_id: UUID,
        method: str | None = None,
        challan_cpin: str | None = None,
        challan_cin: str | None = None,
        narration: str | None = None,
    ) -> GstCashDeposit:
        """Record a PMT-06 challan and post it; the caller commits.

        Raises:
            ValidationError: For a month that takes no deposit, a date before
                the month or in the future, a quarter already settled, an
                empty or negative amount, or an account the firm cannot pay
                from.

        """
        plan = FilingFrequencyService(self._session).plan(firm_id)
        plan.require_deposit_month(return_period)
        first, _ = month_bounds(return_period)
        if deposit_date < first:
            raise ValidationError(
                f"A deposit for {return_period} is paid once the month has "
                f"begun, not on {deposit_date.isoformat()}."
            )
        if deposit_date > firm_today(self._session, firm_id):
            raise ValidationError("A deposit cannot have been paid in the future.")
        quarter_end = quarter_months(return_period)[2]
        settled = self._settled_from(firm_id, quarter_end)
        if settled is not None:
            raise ValidationError(
                f"{quarter_label(return_period)} is already settled ({settled}). "
                "Reverse that settlement first to record a deposit for it."
            )
        values = {
            head: quantize_ledger(Decimal(str(amounts.get(head, ZERO) or ZERO)))
            for head in HEADS
        }
        if any(value < ZERO for value in values.values()):
            raise ValidationError("A deposit cannot be negative.")
        total = sum(values.values(), ZERO)
        if total == ZERO:
            raise ValidationError("A deposit has to pay something under some head.")
        money = self._session.get(LedgerAccount, money_account_id)
        if (
            money is None
            or money.firm_id != firm_id
            or money.is_deleted
            or money.account_type != AccountType.ASSET.value
        ):
            raise ValidationError(
                "Choose the bank or cash account the challan was paid from."
            )

        deposit_id = uuid4()
        control = ControlAccountService(self._session)
        cpin = (challan_cpin or "").strip() or None
        lines = [
            JournalLineData(
                ledger_account_id=control.resolve(
                    firm_id, ControlAccountPurpose.GST_CASH_LEDGER
                ),
                debit_amount=total,
                description=f"PMT-06 deposit for {return_period}",
            ),
            JournalLineData(
                ledger_account_id=money_account_id,
                credit_amount=total,
                description=f"GST challan {cpin or ''}".strip(),
            ),
        ]
        sequence = 1 + (
            self._session.scalar(
                select(func.count(GstCashDeposit.id)).where(
                    GstCashDeposit.firm_id == firm_id,
                    GstCashDeposit.return_period == return_period,
                )
            )
            or 0
        )
        context = DocumentPostingService(self._session).context_for(
            firm_id, deposit_date
        )
        engine = JournalEntryEngine(self._session)
        entry = engine.create_entry(
            firm_id=firm_id,
            journal_type_id=context.journal_type_id,
            voucher_type_id=context.voucher_type_id,
            accounting_period_id=context.accounting_period_id,
            journal_date=deposit_date,
            reference_number=f"PMT06-{return_period}-{sequence}",
            description=f"GST deposited on PMT-06 for {return_period}",
            lines=lines,
            actor_id=actor_id,
            source_module=SOURCE_MODULE,
            source_id=deposit_id,
        )
        engine.post_entry(entry.id, firm_id=firm_id, actor_id=actor_id)
        row = GstCashDeposit(
            id=deposit_id,
            firm_id=firm_id,
            return_period=return_period,
            deposit_date=deposit_date,
            method=method or plan.payment_method,
            money_account_id=money_account_id,
            challan_cpin=cpin,
            challan_cin=(challan_cin or "").strip() or None,
            narration=(narration or "").strip() or None,
            status=GstCashDepositStatus.POSTED.value,
            journal_entry_id=entry.id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        for head in HEADS:
            setattr(row, f"amount_{head}", values[head])
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="gst_cash_deposit.recorded",
            entity_type="gst_cash_deposit",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "return_period": return_period,
                "method": row.method,
                "total": str(total),
                "challan_cpin": row.challan_cpin,
            },
        )
        return row

    def reverse(
        self, deposit_id: UUID, *, firm_id: UUID, actor_id: UUID, reason: str
    ) -> GstCashDeposit:
        """Take back a deposit recorded in error; the caller commits.

        Raises:
            ResourceNotFoundError: If it is not the firm's.
            ValidationError: If it is already reversed, or its quarter is
                settled -- the settlement may have used it.

        """
        row = self.get(deposit_id, firm_id=firm_id)
        if row.status != GstCashDepositStatus.POSTED.value:
            raise ValidationError("This deposit is already reversed.")
        settled = self._settled_from(firm_id, quarter_months(row.return_period)[2])
        if settled is not None:
            raise ValidationError(
                f"{settled} is settled and may have used this deposit. Reverse "
                f"{settled} first."
            )
        mirror = JournalEntryEngine(self._session).reverse_entry(
            row.journal_entry_id,
            firm_id=firm_id,
            reference_number=f"PMT06-{row.return_period}-{str(row.id)[:8]}-REV",
            journal_date=row.deposit_date,
            actor_id=actor_id,
        )
        row.status = GstCashDepositStatus.REVERSED.value
        row.reversal_journal_entry_id = mirror.id
        row.reversed_at = utc_now()
        row.reversed_by = actor_id
        row.reversal_reason = reason
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="gst_cash_deposit.reversed",
            entity_type="gst_cash_deposit",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"return_period": row.return_period, "reason": reason},
        )
        return row

    def get(self, deposit_id: UUID, *, firm_id: UUID) -> GstCashDeposit:
        """Return one of the firm's deposits."""
        row = self._session.get(GstCashDeposit, deposit_id)
        if row is None or row.firm_id != firm_id or row.is_deleted:
            raise ResourceNotFoundError("GST deposit not found.")
        return row

    def list_deposits(self, firm_id: UUID) -> list[GstCashDeposit]:
        """Return every deposit of the firm, newest month first."""
        return list(
            self._session.scalars(
                select(GstCashDeposit)
                .where(
                    GstCashDeposit.firm_id == firm_id,
                    GstCashDeposit.is_deleted.is_(False),
                )
                .order_by(
                    GstCashDeposit.return_period.desc(),
                    GstCashDeposit.deposit_date.desc(),
                    GstCashDeposit.created_at.desc(),
                )
            ).all()
        )

    def balance(self, firm_id: UUID) -> dict[str, Decimal]:
        """Return the deposits no settlement has used yet, per head."""
        return cash_ledger_balance(self._session, firm_id)

    # ---- working out -----------------------------------------------------

    def _fixed_sum(
        self, firm_id: UUID, plan: FilingPlan, month: str
    ) -> tuple[dict[str, Decimal], str]:
        """Return 35% of the last quarter's cash, or its last month's whole."""
        previous_end = shift(quarter_months(month)[0], -1)
        payment = self._standing(firm_id, previous_end)
        if payment is None:
            return (
                {head: ZERO for head in HEADS},
                f"No settlement of {previous_end} is recorded, so there is no "
                "fixed sum to work out: state what the challan paid, or use "
                "self-assessment.",
            )
        cash = {
            head: Decimal(str(getattr(payment, f"cash_{head}")))
            + Decimal(str(getattr(payment, f"reverse_charge_{head}")))
            for head in HEADS
        }
        if plan.is_quarterly(previous_end):
            return (
                {head: _rupees(cash[head] * FIXED_SUM_SHARE) for head in HEADS},
                f"35% of the tax paid in cash for {quarter_label(previous_end)}.",
            )
        return (
            {head: _rupees(cash[head]) for head in HEADS},
            f"The tax paid in cash for {previous_end}, the last month filed "
            "monthly.",
        )

    def _self_assessed(
        self, firm_id: UUID, plan: FilingPlan, month: str
    ) -> tuple[dict[str, Decimal], str]:
        """Return the quarter's cash so far, less what the cash ledger holds."""
        first_month = quarter_months(month)[0]
        first, _ = month_bounds(first_month)
        _, last = month_bounds(month)
        preview = GstPaymentService(self._session).work_out(
            firm_id,
            month,
            first=first,
            last=last,
            due=plan.pmt06_due(month),
        )
        balance = cash_ledger_balance(self._session, firm_id)
        return (
            {
                head: _rupees(max(preview.cash(head) - max(balance[head], ZERO), ZERO))
                for head in HEADS
            },
            f"The tax from {first:%d %b} to {last:%d %b %Y} less its credit, "
            "less what the cash ledger already holds.",
        )

    def _deposited(self, firm_id: UUID, months: list[str]) -> dict[str, Decimal]:
        """Return what the standing deposits of the months paid, per head."""
        totals = {head: ZERO for head in HEADS}
        for row in self._session.scalars(
            select(GstCashDeposit).where(
                GstCashDeposit.firm_id == firm_id,
                GstCashDeposit.is_deleted.is_(False),
                GstCashDeposit.status == GstCashDepositStatus.POSTED.value,
                GstCashDeposit.return_period.in_(months),
            )
        ).all():
            for head in HEADS:
                totals[head] += Decimal(str(getattr(row, f"amount_{head}")))
        return totals

    def _standing(self, firm_id: UUID, return_period: str) -> GstPayment | None:
        """Return the standing settlement of one period, if recorded."""
        return self._session.scalar(
            select(GstPayment).where(
                GstPayment.firm_id == firm_id,
                GstPayment.is_deleted.is_(False),
                GstPayment.status == GstPaymentStatus.POSTED.value,
                GstPayment.return_period == return_period,
            )
        )

    def _settled_from(self, firm_id: UUID, return_period: str) -> str | None:
        """Return the earliest standing settlement at or after a period."""
        return self._session.scalar(
            select(func.min(GstPayment.return_period)).where(
                GstPayment.firm_id == firm_id,
                GstPayment.is_deleted.is_(False),
                GstPayment.status == GstPaymentStatus.POSTED.value,
                GstPayment.return_period >= return_period,
            )
        )


__all__ = ["DepositSuggestion", "GstCashDepositService"]
