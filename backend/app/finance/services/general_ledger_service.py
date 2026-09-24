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
    PROFIT_LOSS_ACCOUNT_TYPES,
    AccountingPeriod,
    AccountType,
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LedgerBalance,
)
from app.finance.schemas import (
    AccountSummary,
    AccountTypeEnum,
    BalanceSheetLine,
    BalanceSheetReport,
    GeneralLedgerLine,
    GeneralLedgerReport,
    ProfitLossLine,
    ProfitLossReport,
    TrialBalanceLine,
    TrialBalanceReport,
)
from app.finance.services.control_accounts import EXPECTED_TYPE

# Two decimal places, because this constant is what an untouched figure is
# reported as. `Decimal("0")` serialises as `"0"` next to a stored `"0.00"`,
# and a statement whose columns disagree about how to write nothing looks
# unfinished in exactly the place people are checking the arithmetic.
ZERO = Decimal("0.00")


class GeneralLedgerService:
    """Produce trial balance, ledger statement, and account summary reports."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session

    def trial_balance(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> TrialBalanceReport:
        """Return the trial balance for one accounting period.

        The standard layout: the opening and the closing balance each split by
        side, the period's movement between them, and every column totalled.
        The Total row used to put the closing balances split by side under the
        movement columns, so it was not the sum of the figures above it
        (D-FIN-18). Balanced is judged on the closing columns, which is the
        question a trial balance answers.
        """
        self._require_period(firm_id=firm_id, accounting_period_id=accounting_period_id)
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
        totals = dict.fromkeys(
            (
                "opening_debit",
                "opening_credit",
                "period_debit",
                "period_credit",
                "closing_debit",
                "closing_credit",
            ),
            ZERO,
        )

        for balance, account in rows:
            opening_debit, opening_credit = self._present_balance(
                account.account_type, balance.opening_balance
            )
            closing_debit, closing_credit = self._present_balance(
                account.account_type, balance.closing_balance
            )
            line = TrialBalanceLine(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=AccountTypeEnum(account.account_type),
                opening_balance=balance.opening_balance,
                opening_debit=opening_debit,
                opening_credit=opening_credit,
                period_debit=balance.period_debit,
                period_credit=balance.period_credit,
                closing_balance=balance.closing_balance,
                closing_debit=closing_debit,
                closing_credit=closing_credit,
            )
            for key in totals:
                totals[key] += getattr(line, key)
            lines.append(line)

        return TrialBalanceReport(
            accounting_period_id=accounting_period_id,
            generated_at=utc_now(),
            lines=lines,
            total_opening_debit=totals["opening_debit"],
            total_opening_credit=totals["opening_credit"],
            total_period_debit=totals["period_debit"],
            total_period_credit=totals["period_credit"],
            total_closing_debit=totals["closing_debit"],
            total_closing_credit=totals["closing_credit"],
            total_debit=totals["closing_debit"],
            total_credit=totals["closing_credit"],
            is_balanced=totals["closing_debit"] == totals["closing_credit"],
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
        self._require_period(firm_id=firm_id, accounting_period_id=accounting_period_id)

        balance = self._session.scalar(
            select(LedgerBalance).where(
                LedgerBalance.ledger_account_id == ledger_account_id,
                LedgerBalance.accounting_period_id == accounting_period_id,
                LedgerBalance.firm_id == firm_id,
            )
        )
        # No stored row means the account was not posted to in this period --
        # which is not the same as having nothing. It may be carrying a balance
        # from an earlier one, and a statement that opens at zero because
        # nothing happened this month is telling the reader the account is
        # empty. Trade Receivables read `opening 0, closing 0` for March 2027
        # in the seeded firm while the firm was owed 249,236.70.
        opening = (
            balance.opening_balance
            if balance is not None
            else self._carried_opening(
                firm_id=firm_id,
                ledger_account_id=ledger_account_id,
                accounting_period_id=accounting_period_id,
            )
        )
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

    def balance_sheet(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> BalanceSheetReport:
        """Return the balance sheet as at one period end.

        As at, not for: every account holding a balance appears, whether or not
        it moved in this period, which is the same pair of queries the trial
        balance uses.

        Earnings are computed rather than read. Nothing in this ledger posts a
        year-end closing entry, so income and expense accounts accumulate
        indefinitely and their net *is* the firm's earnings -- carrying it into
        equity is what makes the sheet balance, and it does so to the rupee on
        the seeded firm. Without it the sheet is short by everything the firm
        has ever made, and no chart of accounts can fix that because the entry
        that would do it is never written.
        """
        period = self._require_period(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        )

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

        sections: dict[str, list[BalanceSheetLine]] = {
            AccountType.ASSET: [],
            AccountType.LIABILITY: [],
            AccountType.EQUITY: [],
        }
        earnings = ZERO
        control_sides = self._control_account_sides(firm_id)
        for balance, account in rows:
            if account.account_type in PROFIT_LOSS_ACCOUNT_TYPES:
                # Income carries a credit balance and expense a debit, both
                # stored positive in their own direction, so income less
                # expense is the accumulated result.
                earnings += (
                    -balance.closing_balance
                    if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES
                    else balance.closing_balance
                )
                continue
            amount = balance.closing_balance
            section_type = account.account_type
            if account.account_type == AccountType.CONTROL:
                # D-FIN-7: CONTROL is not a section of a balance sheet, and the
                # sheet used to leave these out -- while the control-account
                # mapping allows one for receivables, payables, both taxes,
                # GRNI, commission, TCS and loyalty payable. A firm that mapped
                # as allowed got a sheet that could never balance. It goes
                # where its purpose puts it; one mapped to nothing goes by the
                # side its balance lies on, so no balance leaves the sheet.
                #
                # The ledger keeps CONTROL credit-normal (it is not a debit
                # type), so an asset reads the stored figure negated.
                section_type = control_sides.get(account.id) or (
                    AccountType.ASSET
                    if balance.closing_balance < ZERO
                    else AccountType.LIABILITY
                )
                if section_type == AccountType.ASSET:
                    amount = -balance.closing_balance
            section = sections.get(section_type)
            if section is None:
                # MEMO is off the statement by definition. It is not quietly
                # absorbed somewhere: if one holds a balance the sheet stops
                # balancing and says so.
                continue
            section.append(
                BalanceSheetLine(
                    ledger_account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    account_type=AccountTypeEnum(account.account_type),
                    amount=amount,
                )
            )

        this_year = self.profit_and_loss(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        ).year_to_date_net_profit
        assets = sections[AccountType.ASSET]
        liabilities = sections[AccountType.LIABILITY]
        equity = sections[AccountType.EQUITY]
        total_assets = sum((line.amount for line in assets), ZERO)
        total_liabilities = sum((line.amount for line in liabilities), ZERO)
        total_equity = sum((line.amount for line in equity), ZERO) + earnings
        return BalanceSheetReport(
            accounting_period_id=accounting_period_id,
            financial_year_id=period.financial_year_id,
            generated_at=utc_now(),
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            retained_earnings_brought_forward=earnings - this_year,
            result_for_the_year=this_year,
            is_balanced=total_assets == total_liabilities + total_equity,
        )

    def profit_and_loss(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> ProfitLossReport:
        """Return the profit and loss for one period, with the year to date.

        Built from movement rather than from balances, which is what makes it a
        different report from the trial balance: a period contributes what
        happened in it, and an account that saw nothing contributes nothing. So
        there is no balance to carry here -- the omission that had to be fixed
        in the other two reports would be the correct answer in this one.

        Sections are decided by `account_type`, not by the `is_profit_loss`
        flag on the account. The type is structural -- the ledger already uses
        it to decide which side an account increases on -- while the flag is a
        column somebody has to remember to set, and every account in the seeded
        demo firm carries it as `False`, Sales and Purchases included. A report
        that reads it would have come back empty on every firm that exists.
        """
        period = self._require_period(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        )

        # Every income and expense movement in the financial year up to and
        # including this period. Profit resets at the year, so the year is the
        # boundary; one query serves both columns, and the period's own figures
        # are the subset written against it.
        rows = self._session.execute(
            select(LedgerBalance, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                LedgerAccount.account_type.in_(PROFIT_LOSS_ACCOUNT_TYPES),
                AccountingPeriod.financial_year_id == period.financial_year_id,
                AccountingPeriod.starts_on <= period.starts_on,
            )
        ).all()

        totals: dict[UUID, tuple[LedgerAccount, Decimal, Decimal]] = {}
        for balance, account in rows:
            movement = (
                balance.period_debit - balance.period_credit
                if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES
                else balance.period_credit - balance.period_debit
            )
            _, in_period, year_to_date = totals.get(account.id, (account, ZERO, ZERO))
            if balance.accounting_period_id == accounting_period_id:
                in_period += movement
            totals[account.id] = (account, in_period, year_to_date + movement)

        income: list[ProfitLossLine] = []
        expenses: list[ProfitLossLine] = []
        for account, in_period, year_to_date in totals.values():
            # An account that did nothing all year is not a line. It is the
            # same judgement the trial balance makes about a zero balance: a
            # report listing every account ever created is a worse report.
            if in_period == ZERO and year_to_date == ZERO:
                continue
            line = ProfitLossLine(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=AccountTypeEnum(account.account_type),
                period_amount=in_period,
                year_to_date_amount=year_to_date,
            )
            if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
                expenses.append(line)
            else:
                income.append(line)
        income.sort(key=lambda line: line.account_code)
        expenses.sort(key=lambda line: line.account_code)

        total_income = sum((line.period_amount for line in income), ZERO)
        total_expense = sum((line.period_amount for line in expenses), ZERO)
        ytd_income = sum((line.year_to_date_amount for line in income), ZERO)
        ytd_expense = sum((line.year_to_date_amount for line in expenses), ZERO)
        return ProfitLossReport(
            accounting_period_id=accounting_period_id,
            financial_year_id=period.financial_year_id,
            generated_at=utc_now(),
            income=income,
            expenses=expenses,
            total_income=total_income,
            total_expense=total_expense,
            net_profit=total_income - total_expense,
            year_to_date_income=ytd_income,
            year_to_date_expense=ytd_expense,
            year_to_date_net_profit=ytd_income - ytd_expense,
        )

    def account_summary(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> list[AccountSummary]:
        """Return one balance row per account with movement for the period."""
        self._require_period(firm_id=firm_id, accounting_period_id=accounting_period_id)
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

    def _firm_period(
        self, firm_id: UUID, accounting_period_id: UUID
    ) -> AccountingPeriod | None:
        """Return the period when it is the firm's own and live, else None."""
        return self._session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.id == accounting_period_id,
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.is_deleted.is_(False),
            )
        )

    def _require_period(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> AccountingPeriod:
        """Return the firm's own period or refuse as not found (D-FIN-14).

        The reports read the period with ``session.get`` and no firm check, so
        in the shared store one firm's report on another's period answered
        with its own figures on the other's calendar.
        """
        period = self._firm_period(firm_id, accounting_period_id)
        if period is None:
            raise ResourceNotFoundError("Accounting period not found.")
        return period

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
        period = self._firm_period(firm_id, accounting_period_id)
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

    def _carried_opening(
        self, *, firm_id: UUID, ledger_account_id: UUID, accounting_period_id: UUID
    ) -> Decimal:
        """Return the balance one account carries into a period it did not move in.

        The single-account form of :meth:`_carried_balances`, and it stays a
        `LIMIT 1` rather than reusing that method: a statement asks about one
        account, and loading every balance the firm holds to read one of them
        is the shape that makes a report slow as a firm accumulates years.
        """
        period = self._firm_period(firm_id, accounting_period_id)
        if period is None:
            return ZERO
        balance = self._session.scalar(
            select(LedgerBalance)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerBalance.ledger_account_id == ledger_account_id,
                AccountingPeriod.ends_on < period.starts_on,
            )
            .order_by(AccountingPeriod.ends_on.desc())
            .limit(1)
        )
        return balance.closing_balance if balance is not None else ZERO

    def _control_account_sides(self, firm_id: UUID) -> dict[UUID, AccountType]:
        """Return which side of the sheet each mapped account belongs on.

        Read from the purposes it is mapped to, through the same
        ``EXPECTED_TYPE`` table that allowed a CONTROL account there: a
        receivable or input-tax purpose is an asset, the payables are
        liabilities. An account mapped to purposes on both sides is left out
        of the answer, so its balance decides.
        """
        expected = {purpose.value: types for purpose, types in EXPECTED_TYPE.items()}
        sides: dict[UUID, set[AccountType]] = {}
        for account_id, purpose in self._session.execute(
            select(FirmControlAccount.ledger_account_id, FirmControlAccount.purpose)
            .join(
                LedgerAccount,
                LedgerAccount.id == FirmControlAccount.ledger_account_id,
            )
            .where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
                LedgerAccount.account_type == AccountType.CONTROL.value,
            )
        ).all():
            allowed = expected.get(purpose, frozenset())
            for side in (AccountType.ASSET, AccountType.LIABILITY):
                if side.value in allowed:
                    sides.setdefault(account_id, set()).add(side)
        return {
            account_id: next(iter(found))
            for account_id, found in sides.items()
            if len(found) == 1
        }

    def _present_balance(
        self, account_type: str, closing_balance: Decimal
    ) -> tuple[Decimal, Decimal]:
        """Split a balance into its trial-balance debit and credit sides."""
        if account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
            if closing_balance >= ZERO:
                return closing_balance, ZERO
            return ZERO, -closing_balance
        if closing_balance >= ZERO:
            return ZERO, closing_balance
        return -closing_balance, ZERO
