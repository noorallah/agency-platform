"""General Ledger Reporting Engine - GL reports and trial balance."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.finance.models import (
    LedgerAccount,
    LedgerBalance,
    GLPosting,
    AccountingPeriod,
    AccountType,
)


ZERO = Decimal("0")


class GeneralLedgerEngine:
    """
    General Ledger reporting and balance calculations.
    
    Provides:
    - Trial Balance (summary of all account balances)
    - GL detailed report (transaction-level detail)
    - Account-wise balance report
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def trial_balance(
        self,
        *,
        firm_id: UUID,
        accounting_period_id: UUID,
    ) -> TrialBalanceReport:
        """
        Generate Trial Balance (balance sheet + P&L accounts).
        
        Verifies double-entry compliance (total debits = total credits).
        """
        # Get all ledger balances for period
        balances = list(
            self._session.scalars(
                select(LedgerBalance)
                .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
                .where(
                    LedgerBalance.firm_id == firm_id,
                    LedgerBalance.accounting_period_id == accounting_period_id,
                )
                .order_by(LedgerAccount.account_code.asc())
            ).all()
        )

        lines = []
        total_debit = ZERO
        total_credit = ZERO

        for balance in balances:
            account = balance.ledger_account
            closing = balance.closing_balance

            # Classify debit/credit based on account type
            if account.account_type in ["ASSET", "EXPENSE"]:
                debit = closing if closing >= ZERO else ZERO
                credit = abs(closing) if closing < ZERO else ZERO
            else:
                # LIABILITY, INCOME, EQUITY
                credit = closing if closing >= ZERO else ZERO
                debit = abs(closing) if closing < ZERO else ZERO

            lines.append(
                TrialBalanceLineItem(
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_type=account.account_type,
                    debit_balance=debit,
                    credit_balance=credit,
                    closing_balance=closing,
                )
            )

            total_debit += debit
            total_credit += credit

        is_balanced = abs(total_debit - total_credit) < Decimal("0.01")

        return TrialBalanceReport(
            accounting_period_id=accounting_period_id,
            as_of=utc_now(),
            lines=lines,
            total_debit=total_debit,
            total_credit=total_credit,
            is_balanced=is_balanced,
        )

    def general_ledger(
        self,
        *,
        firm_id: UUID,
        ledger_account_id: UUID,
        accounting_period_id: UUID,
        include_opening_balance: bool = True,
    ) -> GeneralLedgerReport:
        """
        Get GL detail for a specific account and period.
        
        Shows:
        - Opening balance
        - All transactions (debits/credits)
        - Closing balance
        """
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
            )
        )
        if account is None:
            raise ValueError("Account not found.")

        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == ledger_account_id,
                LedgerBalance.accounting_period_id == accounting_period_id,
            )
        )

        postings = list(
            self._session.scalars(
                select(GLPosting)
                .where(
                    GLPosting.firm_id == firm_id,
                    GLPosting.ledger_account_id == ledger_account_id,
                    GLPosting.accounting_period_id == accounting_period_id,
                )
                .order_by(GLPosting.posting_date.asc())
            ).all()
        )

        lines = []
        running_balance = balance.opening_balance if balance else ZERO

        if include_opening_balance and balance:
            lines.append(
                GLDetailLine(
                    posting_date=None,
                    reference="Opening Balance",
                    debit=ZERO,
                    credit=ZERO,
                    running_balance=running_balance,
                )
            )

        for posting in postings:
            if posting.debit_amount > ZERO:
                running_balance += posting.debit_amount
            else:
                running_balance -= posting.credit_amount

            lines.append(
                GLDetailLine(
                    posting_date=posting.posting_date,
                    reference=posting.journal_entry_id,
                    debit=posting.debit_amount,
                    credit=posting.credit_amount,
                    running_balance=running_balance,
                )
            )

        return GeneralLedgerReport(
            account_code=account.account_code,
            account_name=account.account_name,
            account_type=account.account_type,
            opening_balance=balance.opening_balance if balance else ZERO,
            closing_balance=balance.closing_balance if balance else ZERO,
            total_debit=balance.period_debit if balance else ZERO,
            total_credit=balance.period_credit if balance else ZERO,
            lines=lines,
        )

    def account_summary(
        self,
        *,
        firm_id: UUID,
        accounting_period_id: UUID,
    ) -> list[AccountSummary]:
        """
        Get summary of all accounts with balances.
        """
        balances = list(
            self._session.scalars(
                select(LedgerBalance)
                .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
                .where(
                    LedgerBalance.firm_id == firm_id,
                    LedgerBalance.accounting_period_id == accounting_period_id,
                )
                .order_by(LedgerAccount.account_code.asc())
            ).all()
        )

        summaries = []
        for balance in balances:
            account = balance.ledger_account
            summaries.append(
                AccountSummary(
                    account_id=account.id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_type=account.account_type,
                    opening_balance=balance.opening_balance,
                    period_debit=balance.period_debit,
                    period_credit=balance.period_credit,
                    closing_balance=balance.closing_balance,
                )
            )

        return summaries


# Report DTOs
class TrialBalanceLineItem:
    def __init__(
        self,
        *,
        account_code: str,
        account_name: str,
        account_type: str,
        debit_balance: Decimal,
        credit_balance: Decimal,
        closing_balance: Decimal,
    ) -> None:
        self.account_code = account_code
        self.account_name = account_name
        self.account_type = account_type
        self.debit_balance = debit_balance
        self.credit_balance = credit_balance
        self.closing_balance = closing_balance


class TrialBalanceReport:
    def __init__(
        self,
        *,
        accounting_period_id: UUID,
        as_of: datetime,
        lines: list[TrialBalanceLineItem],
        total_debit: Decimal,
        total_credit: Decimal,
        is_balanced: bool,
    ) -> None:
        self.accounting_period_id = accounting_period_id
        self.as_of = as_of
        self.lines = lines
        self.total_debit = total_debit
        self.total_credit = total_credit
        self.is_balanced = is_balanced


class GLDetailLine:
    def __init__(
        self,
        *,
        posting_date: datetime | None,
        reference: str,
        debit: Decimal,
        credit: Decimal,
        running_balance: Decimal,
    ) -> None:
        self.posting_date = posting_date
        self.reference = reference
        self.debit = debit
        self.credit = credit
        self.running_balance = running_balance


class GeneralLedgerReport:
    def __init__(
        self,
        *,
        account_code: str,
        account_name: str,
        account_type: str,
        opening_balance: Decimal,
        closing_balance: Decimal,
        total_debit: Decimal,
        total_credit: Decimal,
        lines: list[GLDetailLine],
    ) -> None:
        self.account_code = account_code
        self.account_name = account_name
        self.account_type = account_type
        self.opening_balance = opening_balance
        self.closing_balance = closing_balance
        self.total_debit = total_debit
        self.total_credit = total_credit
        self.lines = lines


class AccountSummary:
    def __init__(
        self,
        *,
        account_id: UUID,
        account_code: str,
        account_name: str,
        account_type: str,
        opening_balance: Decimal,
        period_debit: Decimal,
        period_credit: Decimal,
        closing_balance: Decimal,
    ) -> None:
        self.account_id = account_id
        self.account_code = account_code
        self.account_name = account_name
        self.account_type = account_type
        self.opening_balance = opening_balance
        self.period_debit = period_debit
        self.period_credit = period_credit
        self.closing_balance = closing_balance
