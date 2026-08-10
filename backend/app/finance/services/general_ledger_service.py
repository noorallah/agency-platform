"""General-ledger reporting built on stored balances and postings.

Reports read the balances and posting trail written by
:class:`app.finance.services.journal_engine.JournalEntryEngine`; they never
recompute totals from journal lines, so a report and the ledger cannot drift.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.finance.models import (
    DEBIT_BALANCE_ACCOUNT_TYPES,
    GLPosting,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LedgerBalance,
)
from app.finance.schemas import (
    AccountSummary,
    AccountTypeEnum,
    GeneralLedgerLine,
    GeneralLedgerReport,
    TrialBalanceLine,
    TrialBalanceReport,
)

ZERO = Decimal("0")


class GeneralLedgerService:
    """Produce trial balance, ledger statement, and account summary reports."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session

    def trial_balance(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> TrialBalanceReport:
        """Return the trial balance for one accounting period."""
        rows = self._balances(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        )
        lines: list[TrialBalanceLine] = []
        total_debit = ZERO
        total_credit = ZERO

        for balance, account in rows:
            debit, credit = self._present_balance(
                account.account_type, balance.closing_balance
            )
            total_debit += debit
            total_credit += credit
            lines.append(
                TrialBalanceLine(
                    ledger_account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    account_type=AccountTypeEnum(account.account_type),
                    opening_balance=balance.opening_balance,
                    period_debit=balance.period_debit,
                    period_credit=balance.period_credit,
                    closing_balance=balance.closing_balance,
                )
            )

        return TrialBalanceReport(
            accounting_period_id=accounting_period_id,
            generated_at=utc_now(),
            lines=lines,
            total_debit=total_debit,
            total_credit=total_credit,
            is_balanced=total_debit == total_credit,
        )

    def general_ledger(
        self, *, firm_id: UUID, ledger_account_id: UUID, accounting_period_id: UUID
    ) -> GeneralLedgerReport:
        """Return the movement statement for one account and period."""
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Ledger account not found.")

        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == ledger_account_id,
                LedgerBalance.accounting_period_id == accounting_period_id,
                LedgerBalance.firm_id == firm_id,
            )
        )
        opening = balance.opening_balance if balance is not None else ZERO
        increases_on_debit = account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES

        # Ordered by the journal date, not by ``posting_date``. A back-dated
        # entry posted today carries today's wall clock, so ordering on it put
        # the statement in the sequence someone happened to press Post rather
        # than the sequence the business ran in -- and the running balance is
        # only meaningful in the latter.
        postings = self._session.execute(
            select(GLPosting, JournalEntry, JournalLine)
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .join(JournalLine, JournalLine.id == GLPosting.journal_line_id)
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id == ledger_account_id,
                GLPosting.accounting_period_id == accounting_period_id,
            )
            .order_by(
                JournalEntry.journal_date.asc(),
                JournalEntry.reference_number.asc(),
            )
        ).all()

        running = opening
        lines: list[GeneralLedgerLine] = []
        for posting, entry, line in postings:
            movement = (
                posting.debit_amount - posting.credit_amount
                if increases_on_debit
                else posting.credit_amount - posting.debit_amount
            )
            running += movement
            lines.append(
                GeneralLedgerLine(
                    journal_entry_id=entry.id,
                    journal_date=entry.journal_date,
                    reference_number=entry.reference_number,
                    # The line's own narration, which is what says *what* this
                    # movement was; the entry description is the fallback. This
                    # read ``posting.error_message or entry.description``, so a
                    # narration typed on every line was never displayed, and a
                    # posting that had failed would have shown its error text
                    # as the ledger narration.
                    description=line.description or entry.description,
                    debit_amount=posting.debit_amount,
                    credit_amount=posting.credit_amount,
                    running_balance=running,
                )
            )

        return GeneralLedgerReport(
            ledger_account_id=account.id,
            account_code=account.code,
            account_name=account.name,
            account_type=AccountTypeEnum(account.account_type),
            accounting_period_id=accounting_period_id,
            opening_balance=opening,
            total_debit=balance.period_debit if balance is not None else ZERO,
            total_credit=balance.period_credit if balance is not None else ZERO,
            closing_balance=balance.closing_balance if balance is not None else running,
            lines=lines,
        )

    def account_summary(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> list[AccountSummary]:
        """Return one balance row per account with movement for the period."""
        return [
            AccountSummary(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=AccountTypeEnum(account.account_type),
                opening_balance=balance.opening_balance,
                period_debit=balance.period_debit,
                period_credit=balance.period_credit,
                closing_balance=balance.closing_balance,
            )
            for balance, account in self._balances(
                firm_id=firm_id, accounting_period_id=accounting_period_id
            )
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _balances(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> list[tuple[LedgerBalance, LedgerAccount]]:
        """Return every stored balance for a period with its account."""
        rows = self._session.execute(
            select(LedgerBalance, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerBalance.accounting_period_id == accounting_period_id,
                LedgerAccount.is_deleted.is_(False),
            )
            .order_by(LedgerAccount.code.asc())
        ).all()
        return [(balance, account) for balance, account in rows]

    def _present_balance(
        self, account_type: str, closing_balance: Decimal
    ) -> tuple[Decimal, Decimal]:
        """Split a closing balance into its trial-balance debit and credit sides."""
        if account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
            if closing_balance >= ZERO:
                return closing_balance, ZERO
            return ZERO, -closing_balance
        if closing_balance >= ZERO:
            return ZERO, closing_balance
        return -closing_balance, ZERO
