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
    AccountingPeriod,
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
        rows.extend(
            self._carried_balances(
                firm_id=firm_id,
                accounting_period_id=accounting_period_id,
                already_listed={account.id for _, account in rows},
            )
        )
        rows.sort(key=lambda row: row[1].code)
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

    def _carried_balances(
        self,
        *,
        firm_id: UUID,
        accounting_period_id: UUID,
        already_listed: set[UUID],
    ) -> list[tuple[LedgerBalance, LedgerAccount]]:
        """Return accounts holding a balance that saw no movement this period.

        A `ledger_balances` row is written when an account is posted to, so the
        stored rows for a period are only the accounts that moved in it. Totting
        those up and calling the result a trial balance reported a firm out of
        balance whenever a quiet period touched one side and not the other --
        March 2027 in the seeded demo firm read `dr 0.00 cr 211217.50` with the
        ledger perfectly sound, because two accounts moved and the ones holding
        the other side did not.

        A trial balance lists every account with a balance. These are the rest:
        their opening is the closing balance they were left with, nothing moved,
        and the closing is the same figure. The row is built in memory and never
        added to the session -- writing a balance for a period nothing happened
        in would be inventing history to make a report look right.

        An account whose carried balance is zero is left out. It has nothing to
        say and a trial balance listing every account ever created is a worse
        report than one that does not.
        """
        period = self._session.get(AccountingPeriod, accounting_period_id)
        if period is None:
            return []
        # Every balance the firm holds from an earlier period, newest last, so
        # the final one seen per account is the one to carry. One query rather
        # than one per account: a firm has an account for every period it has
        # traded, and asking per account is how a report becomes a page load.
        history = self._session.execute(
            select(LedgerBalance, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                AccountingPeriod.ends_on < period.starts_on,
            )
            .order_by(AccountingPeriod.ends_on.asc())
        ).all()
        latest: dict[UUID, tuple[LedgerBalance, LedgerAccount]] = {}
        for balance, account in history:
            if account.id in already_listed:
                continue
            latest[account.id] = (balance, account)
        carried: list[tuple[LedgerBalance, LedgerAccount]] = []
        for balance, account in latest.values():
            if balance.closing_balance == ZERO:
                continue
            carried.append(
                (
                    LedgerBalance(
                        firm_id=firm_id,
                        ledger_account_id=account.id,
                        accounting_period_id=accounting_period_id,
                        opening_balance=balance.closing_balance,
                        period_debit=ZERO,
                        period_credit=ZERO,
                        closing_balance=balance.closing_balance,
                    ),
                    account,
                )
            )
        return carried

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
