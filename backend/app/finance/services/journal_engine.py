"""Double-entry journal engine.

The engine owns the transition of a journal entry from draft to posted: it
validates that an entry balances, that its period accepts postings, and that
every referenced account belongs to the firm, then writes the ledger balances
and the immutable posting trail that reporting reads.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    DEBIT_BALANCE_ACCOUNT_TYPES,
    AccountingPeriod,
    GLPosting,
    JournalEntry,
    JournalLine,
    JournalStatus,
    JournalType,
    LedgerAccount,
    LedgerBalance,
    PeriodStatus,
    PostingStatus,
    VoucherType,
)

ZERO = Decimal("0")
MONEY = Decimal("0.01")


def quantize_money(value: Decimal | None) -> Decimal:
    """Round a monetary value to two decimal places."""
    if value is None:
        return ZERO
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class JournalLineData:
    """Carry one debit or credit leg into the engine."""

    ledger_account_id: UUID
    debit_amount: Decimal = field(default=ZERO)
    credit_amount: Decimal = field(default=ZERO)
    cost_center_id: UUID | None = None
    profit_center_id: UUID | None = None
    description: str | None = None


class JournalEntryEngine:
    """Create, post, and reverse double-entry journal entries."""

    def __init__(self, session: Session) -> None:
        """Bind the engine to one request unit of work."""
        self._session = session

    def create_entry(
        self,
        *,
        firm_id: UUID,
        journal_type_id: UUID,
        voucher_type_id: UUID,
        accounting_period_id: UUID,
        journal_date: date,
        reference_number: str,
        description: str | None,
        remarks: str | None = None,
        lines: list[JournalLineData],
        source_module: str | None = None,
        source_id: UUID | None = None,
        actor_id: UUID,
    ) -> JournalEntry:
        """Create one balanced draft journal entry."""
        if len(lines) < 2:
            raise ValidationError(
                "A journal entry needs at least one debit and one credit line."
            )
        period = self._require_open_period(accounting_period_id, firm_id=firm_id)
        if not (period.starts_on <= journal_date <= period.ends_on):
            raise ValidationError(
                "The journal date must fall inside the accounting period."
            )
        self._require_reference(
            journal_type_id, JournalType, firm_id, "Journal type not found."
        )
        self._require_reference(
            voucher_type_id, VoucherType, firm_id, "Voucher type not found."
        )

        total_debit = quantize_money(sum((line.debit_amount for line in lines), ZERO))
        total_credit = quantize_money(sum((line.credit_amount for line in lines), ZERO))
        if total_debit != total_credit:
            raise ValidationError(
                f"Journal entry is not balanced: debit {total_debit}, "
                f"credit {total_credit}."
            )
        if total_debit == ZERO:
            raise ValidationError("A journal entry must carry a non-zero amount.")

        accounts = self._load_accounts(lines, firm_id=firm_id)
        entry = JournalEntry(
            firm_id=firm_id,
            journal_type_id=journal_type_id,
            voucher_type_id=voucher_type_id,
            accounting_period_id=accounting_period_id,
            journal_date=journal_date,
            reference_number=reference_number,
            description=description,
            remarks=remarks,
            status=JournalStatus.DRAFT.value,
            total_debit=total_debit,
            total_credit=total_credit,
            is_balanced=True,
            source_module=source_module,
            source_id=source_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        for index, data in enumerate(lines, start=1):
            account = accounts[data.ledger_account_id]
            self._validate_line_dimensions(account, data)
            entry.lines.append(
                JournalLine(
                    ledger_account_id=data.ledger_account_id,
                    cost_center_id=data.cost_center_id,
                    profit_center_id=data.profit_center_id,
                    line_number=index,
                    debit_amount=quantize_money(data.debit_amount),
                    credit_amount=quantize_money(data.credit_amount),
                    description=data.description,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.add(entry)
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(
                "A journal entry with this reference number already exists."
            ) from error

        record_audit(
            self._session,
            action="finance.journal_entry.created",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "reference_number": entry.reference_number,
                "total_debit": str(entry.total_debit),
                "total_credit": str(entry.total_credit),
            },
        )
        return entry

    def post_entry(
        self, journal_entry_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> JournalEntry:
        """Post a draft entry to the general ledger."""
        entry = self.get_entry(journal_entry_id, firm_id=firm_id)
        if entry.status != JournalStatus.DRAFT.value:
            raise ValidationError(
                f"Only draft entries can be posted; this entry is "
                f"{entry.status.lower()}."
            )
        if not entry.is_balanced:
            raise ValidationError("An unbalanced entry cannot be posted.")
        # Re-check at posting time: the period may have closed since creation.
        self._require_open_period(entry.accounting_period_id, firm_id=firm_id)

        posted_at = utc_now()
        for line in entry.lines:
            self._post_line(
                entry, line, firm_id=firm_id, actor_id=actor_id, posted_at=posted_at
            )
        entry.status = JournalStatus.POSTED.value
        entry.posted_at = posted_at
        entry.updated_by = actor_id
        entry.version += 1
        self._session.flush()

        record_audit(
            self._session,
            action="finance.journal_entry.posted",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": JournalStatus.DRAFT.value},
            after_data={"status": entry.status},
        )
        return entry

    def reverse_entry(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        reference_number: str,
        accounting_period_id: UUID | None = None,
        journal_date: date | None = None,
        actor_id: UUID,
    ) -> JournalEntry:
        """Create and post a mirror entry that cancels a posted entry."""
        original = self.get_entry(journal_entry_id, firm_id=firm_id)
        if original.status != JournalStatus.POSTED.value:
            raise ValidationError("Only posted entries can be reversed.")

        target_period_id = accounting_period_id or original.accounting_period_id
        period = self._require_open_period(target_period_id, firm_id=firm_id)
        target_date = journal_date or period.starts_on
        if not (period.starts_on <= target_date <= period.ends_on):
            target_date = period.starts_on

        reversal_lines = [
            JournalLineData(
                ledger_account_id=line.ledger_account_id,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
                description=f"Reversal of {original.reference_number}",
            )
            for line in original.lines
        ]
        reversal = self.create_entry(
            firm_id=firm_id,
            journal_type_id=original.journal_type_id,
            voucher_type_id=original.voucher_type_id,
            accounting_period_id=target_period_id,
            journal_date=target_date,
            reference_number=reference_number,
            description=f"Reversal of {original.reference_number}",
            lines=reversal_lines,
            source_module=original.source_module,
            source_id=original.source_id,
            actor_id=actor_id,
        )
        reversal.reversal_of_id = original.id
        self.post_entry(reversal.id, firm_id=firm_id, actor_id=actor_id)

        original.status = JournalStatus.REVERSED.value
        original.updated_by = actor_id
        original.version += 1
        record_audit(
            self._session,
            action="finance.journal_entry.reversed",
            entity_type="journal_entry",
            entity_id=original.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "status": original.status,
                "reversal_entry_id": str(reversal.id),
            },
        )
        return reversal

    def get_entry(self, journal_entry_id: UUID, *, firm_id: UUID) -> JournalEntry:
        """Return one journal entry or raise when it is unavailable."""
        entry = self._session.scalar(
            select(JournalEntry).where(
                JournalEntry.id == journal_entry_id,
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry is None:
            raise ResourceNotFoundError("Journal entry not found.")
        return entry

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _post_line(
        self,
        entry: JournalEntry,
        line: JournalLine,
        *,
        firm_id: UUID,
        actor_id: UUID,
        posted_at: object,
    ) -> None:
        """Apply one journal line to its ledger balance and posting trail."""
        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == line.ledger_account_id,
                LedgerBalance.accounting_period_id == entry.accounting_period_id,
            )
        )
        if balance is None:
            opening = self._opening_balance(
                line.ledger_account_id, entry.accounting_period_id, firm_id=firm_id
            )
            balance = LedgerBalance(
                firm_id=firm_id,
                ledger_account_id=line.ledger_account_id,
                accounting_period_id=entry.accounting_period_id,
                opening_balance=opening,
                period_debit=ZERO,
                period_credit=ZERO,
                closing_balance=opening,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(balance)
            self._session.flush()

        balance.period_debit = quantize_money(balance.period_debit + line.debit_amount)
        balance.period_credit = quantize_money(
            balance.period_credit + line.credit_amount
        )
        balance.closing_balance = self._closing_balance(
            line.ledger_account.account_type, balance
        )
        balance.updated_by = actor_id

        self._session.add(
            GLPosting(
                firm_id=firm_id,
                journal_entry_id=entry.id,
                journal_line_id=line.id,
                ledger_account_id=line.ledger_account_id,
                accounting_period_id=entry.accounting_period_id,
                posting_date=posted_at,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                status=PostingStatus.POSTED.value,
                posted_by=actor_id,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    def _opening_balance(
        self, ledger_account_id: UUID, accounting_period_id: UUID, *, firm_id: UUID
    ) -> Decimal:
        """Carry the previous period's closing balance into a new period."""
        period = self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
            )
        )
        if period is None:
            return ZERO
        previous = self._session.scalar(
            select(LedgerBalance)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.ledger_account_id == ledger_account_id,
                LedgerBalance.firm_id == firm_id,
                AccountingPeriod.ends_on < period.starts_on,
            )
            .order_by(AccountingPeriod.ends_on.desc())
            .limit(1)
        )
        return previous.closing_balance if previous is not None else ZERO

    def _closing_balance(self, account_type: str, balance: LedgerBalance) -> Decimal:
        """Compute a closing balance using the account's normal balance side."""
        if account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
            movement = balance.period_debit - balance.period_credit
        else:
            movement = balance.period_credit - balance.period_debit
        return quantize_money(balance.opening_balance + movement)

    def _require_open_period(
        self, accounting_period_id: UUID, *, firm_id: UUID
    ) -> AccountingPeriod:
        """Return the period only when it still accepts postings."""
        period = self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
        if period is None:
            raise ValidationError("Accounting period not found for the active firm.")
        if period.status != PeriodStatus.OPEN.value:
            raise ValidationError(
                f"Accounting period {period.code} is {period.status.lower()} "
                f"and cannot accept postings."
            )
        return period

    def _require_reference(
        self,
        entity_id: UUID,
        model: type[JournalType] | type[VoucherType],
        firm_id: UUID,
        message: str,
    ) -> None:
        """Confirm a supporting master record belongs to the firm."""
        found = self._session.scalar(
            select(model.id).where(
                model.id == entity_id,
                model.firm_id == firm_id,
                model.is_deleted.is_(False),
            )
        )
        if found is None:
            raise ValidationError(message)

    def _load_accounts(
        self, lines: list[JournalLineData], *, firm_id: UUID
    ) -> dict[UUID, LedgerAccount]:
        """Load and validate every ledger account referenced by the lines."""
        requested = {line.ledger_account_id for line in lines}
        accounts = {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_(requested),
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.is_deleted.is_(False),
                )
            ).all()
        }
        missing = requested - accounts.keys()
        if missing:
            raise ValidationError(
                "One or more ledger accounts are unavailable for the active firm."
            )
        inactive = [a.code for a in accounts.values() if not a.is_active]
        if inactive:
            raise ValidationError(
                f"Ledger accounts are inactive: {', '.join(sorted(inactive))}."
            )
        return accounts

    def _validate_line_dimensions(
        self, account: LedgerAccount, data: JournalLineData
    ) -> None:
        """Enforce the cost and profit centre requirements of an account."""
        if account.requires_cost_center and data.cost_center_id is None:
            raise ValidationError(
                f"Ledger account {account.code} requires a cost centre."
            )
        if account.requires_profit_center and data.profit_center_id is None:
            raise ValidationError(
                f"Ledger account {account.code} requires a profit centre."
            )
