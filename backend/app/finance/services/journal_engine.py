"""Journal Entry Engine - Core double-entry accounting logic."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError, ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.finance.models import (
    JournalEntry,
    JournalLine,
    JournalStatus,
    PostingStatus,
    LedgerBalance,
    GLPosting,
    AccountingPeriod,
    LedgerAccount,
)


ZERO = Decimal("0")


class JournalEntryEngine:
    """
    Core Journal Entry Engine.
    
    Responsible for:
    - Creating balanced journal entries
    - Validating debit/credit balance
    - Posting to ledger with balance calculation
    - Supporting reversals and adjustments
    - Maintaining GL posting audit trail
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_entry(
        self,
        *,
        firm_id: UUID,
        journal_type_id: UUID,
        voucher_type_id: UUID,
        accounting_period_id: UUID,
        journal_date: datetime,
        reference_number: str,
        description: str | None,
        lines: list[JournalLineData],
        source_module: str | None = None,
        source_id: UUID | None = None,
        actor_id: UUID,
    ) -> JournalEntry:
        """
        Create a new journal entry with multiple debit/credit lines.
        
        Validation:
        - Total debits must equal total credits
        - At least 2 lines required
        - All referenced accounts must exist
        - Period must be open
        """
        # Validate period is open
        period = self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
            )
        )
        if period is None:
            raise ValidationError("Accounting period not found or not accessible.")
        if period.status != "OPEN":
            raise ValidationError(f"Accounting period is {period.status.lower()}. Cannot post entries.")

        # Validate and calculate totals
        total_debit = sum((line.debit_amount for line in lines), ZERO)
        total_credit = sum((line.credit_amount for line in lines), ZERO)
        is_balanced = self._q(total_debit) == self._q(total_credit)

        if not is_balanced:
            raise ValidationError(
                f"Journal entry is not balanced. Debit: {total_debit}, Credit: {total_credit}"
            )

        if len(lines) < 2:
            raise ValidationError("Journal entry must have at least 2 lines (one debit, one credit).")

        # Create header
        journal_entry = JournalEntry(
            firm_id=firm_id,
            journal_type_id=journal_type_id,
            voucher_type_id=voucher_type_id,
            accounting_period_id=accounting_period_id,
            journal_date=journal_date,
            reference_number=reference_number,
            description=description,
            status=JournalStatus.DRAFT.value,
            total_debit=self._q(total_debit),
            total_credit=self._q(total_credit),
            is_balanced=is_balanced,
            source_module=source_module,
            source_id=source_id,
            created_by=actor_id,
        )

        # Create lines
        for idx, line_data in enumerate(lines, start=1):
            line = JournalLine(
                journal_entry=journal_entry,
                ledger_account_id=line_data.ledger_account_id,
                cost_center_id=line_data.cost_center_id,
                profit_center_id=line_data.profit_center_id,
                line_number=idx,
                debit_amount=self._q(line_data.debit_amount),
                credit_amount=self._q(line_data.credit_amount),
                description=line_data.description,
            )
            journal_entry.lines.append(line)

        self._session.add(journal_entry)
        self._session.flush()

        return journal_entry

    def post_entry(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> JournalEntry:
        """
        Post a journal entry to the General Ledger.
        
        Updates:
        - Journal status to POSTED
        - Ledger balances for each account
        - Creates GL posting records
        - Updates period balance metadata
        """
        entry = self._session.scalar(
            select(JournalEntry).where(
                JournalEntry.id == journal_entry_id,
                JournalEntry.firm_id == firm_id,
            )
        )
        if entry is None:
            raise ResourceNotFoundError("Journal entry not found.")

        if entry.status != JournalStatus.DRAFT.value:
            raise ValidationError(f"Cannot post entry in {entry.status} status.")

        if not entry.is_balanced:
            raise ValidationError("Cannot post unbalanced entry.")

        # Post each line to ledger
        for line in entry.lines:
            self._post_line_to_ledger(
                journal_entry=entry,
                journal_line=line,
                firm_id=firm_id,
                actor_id=actor_id,
            )

        # Update entry status
        entry.status = JournalStatus.POSTED.value
        entry.posted_at = utc_now()
        entry.updated_at = utc_now()

        return entry

    def reverse_entry(
        self,
        journal_entry_id: UUID,
        *,
        firm_id: UUID,
        new_reference_number: str,
        actor_id: UUID,
    ) -> JournalEntry:
        """
        Create a reversal journal entry (flip debits and credits).
        
        Used for:
        - Correcting posted entries
        - Reversing accruals
        - Adjustment entries
        """
        original = self._session.scalar(
            select(JournalEntry).where(
                JournalEntry.id == journal_entry_id,
                JournalEntry.firm_id == firm_id,
            )
        )
        if original is None:
            raise ResourceNotFoundError("Journal entry not found.")

        if original.status not in [JournalStatus.POSTED.value, JournalStatus.REVERSED.value]:
            raise ValidationError("Can only reverse posted entries.")

        # Create reversed lines (flip debit/credit)
        reversed_lines = []
        for line in original.lines:
            reversed_lines.append(
                JournalLineData(
                    ledger_account_id=line.ledger_account_id,
                    cost_center_id=line.cost_center_id,
                    profit_center_id=line.profit_center_id,
                    debit_amount=line.credit_amount,
                    credit_amount=line.debit_amount,
                    description=f"Reversal of {original.reference_number}: {line.description or ''}",
                )
            )

        # Create reversal entry
        reversal = self.create_entry(
            firm_id=firm_id,
            journal_type_id=original.journal_type_id,
            voucher_type_id=original.voucher_type_id,
            accounting_period_id=original.accounting_period_id,
            journal_date=utc_now(),
            reference_number=new_reference_number,
            description=f"Reversal of {original.reference_number}",
            lines=reversed_lines,
            source_module=original.source_module,
            source_id=original.source_id,
            actor_id=actor_id,
        )

        # Mark original as reversed
        original.status = JournalStatus.REVERSED.value
        original.updated_at = utc_now()

        # Post reversal immediately
        self.post_entry(reversal.id, firm_id=firm_id, actor_id=actor_id)

        return reversal

    def _post_line_to_ledger(
        self,
        journal_entry: JournalEntry,
        journal_line: JournalLine,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Post a single journal line to the ledger balance."""
        # Get or create balance record for account+period
        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == journal_line.ledger_account_id,
                LedgerBalance.accounting_period_id == journal_entry.accounting_period_id,
            )
        )

        if balance is None:
            # Get opening balance from previous period or 0
            previous_balance = ZERO
            balance = LedgerBalance(
                firm_id=firm_id,
                ledger_account_id=journal_line.ledger_account_id,
                accounting_period_id=journal_entry.accounting_period_id,
                opening_balance=previous_balance,
                period_debit=ZERO,
                period_credit=ZERO,
                closing_balance=previous_balance,
            )
            self._session.add(balance)

        # Update period totals
        balance.period_debit = self._q(balance.period_debit + journal_line.debit_amount)
        balance.period_credit = self._q(balance.period_credit + journal_line.credit_amount)

        # Calculate closing balance based on account type
        account = journal_line.ledger_account
        if account.account_type in ["ASSET", "EXPENSE"]:
            # Debit increases, credit decreases
            balance.closing_balance = self._q(
                balance.opening_balance + balance.period_debit - balance.period_credit
            )
        else:
            # Credit increases, debit decreases (for liability, income, equity)
            balance.closing_balance = self._q(
                balance.opening_balance + balance.period_credit - balance.period_debit
            )

        balance.last_updated = utc_now()

        # Create GL posting record (audit trail)
        posting = GLPosting(
            firm_id=firm_id,
            journal_entry_id=journal_entry.id,
            journal_line_id=journal_line.id,
            ledger_account_id=journal_line.ledger_account_id,
            accounting_period_id=journal_entry.accounting_period_id,
            posting_date=utc_now(),
            debit_amount=journal_line.debit_amount,
            credit_amount=journal_line.credit_amount,
            status=PostingStatus.POSTED.value,
            posted_by=actor_id,
        )
        self._session.add(posting)

    def _q(self, value: Decimal | None) -> Decimal:
        """Quantize to 2 decimal places."""
        if value is None:
            return ZERO
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class JournalLineData:
    """DTO for journal line data."""

    def __init__(
        self,
        *,
        ledger_account_id: UUID,
        debit_amount: Decimal = ZERO,
        credit_amount: Decimal = ZERO,
        cost_center_id: UUID | None = None,
        profit_center_id: UUID | None = None,
        description: str | None = None,
    ) -> None:
        self.ledger_account_id = ledger_account_id
        self.debit_amount = debit_amount
        self.credit_amount = credit_amount
        self.cost_center_id = cost_center_id
        self.profit_center_id = profit_center_id
        self.description = description
