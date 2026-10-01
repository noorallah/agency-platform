"""General-ledger reporting built on stored balances and postings.

Reports read the balances and posting trail written by
:class:`app.finance.services.journal_engine.JournalEntryEngine`; they never
recompute totals from journal lines, so a report and the ledger cannot drift.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    DEBIT_BALANCE_ACCOUNT_TYPES,
    PROFIT_LOSS_ACCOUNT_TYPES,
    AccountingPeriod,
    AccountType,
    FinancialYear,
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
    ProfitLossRangeLine,
    ProfitLossRangeMonth,
    ProfitLossRangeReport,
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
        self,
        *,
        firm_id: UUID,
        accounting_period_id: UUID,
        to_period_id: UUID | None = None,
    ) -> TrialBalanceReport:
        """Return the trial balance for one accounting period, or a run of them.

        The standard layout: the opening and the closing balance each split by
        side, the period's movement between them, and every column totalled.
        The Total row used to put the closing balances split by side under the
        movement columns, so it was not the sum of the figures above it
        (D-FIN-18). Balanced is judged on the closing columns, which is the
        question a trial balance answers.

        With ``to_period_id`` it covers every month from
        ``accounting_period_id`` to that one (backlog 50 item 5): the opening
        is the first month's, the closing the last month's, and the movement
        the months' own, summed in SQL. Periods stay the unit and the span
        stays inside one financial year, as the profit and loss range does,
        because an income account starts again at the year.
        """
        period, last, months = self._span(
            firm_id=firm_id,
            from_period_id=accounting_period_id,
            to_period_id=to_period_id,
            what="A trial balance",
        )
        rows = self._range_balances(
            firm_id=firm_id, first=period, last=last, months=months
        )
        # An income or expense account starts every financial year at zero,
        # and what earlier years earned is one line under equity (D-FIN-22).
        # The stored balances run on across years -- the balance sheet reads
        # them that way -- so the year's start is taken off here, for display.
        brought_forward = self._brought_forward(
            firm_id=firm_id,
            period=period,
            account_ids=[
                account.id
                for _, account in rows
                if account.account_type in PROFIT_LOSS_ACCOUNT_TYPES
            ],
        )
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

        earned_before = ZERO
        for balance, account in rows:
            carried = brought_forward.get(account.id, ZERO)
            opening = balance.opening_balance - carried
            closing = balance.closing_balance - carried
            if carried:
                earned_before += (
                    -carried
                    if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES
                    else carried
                )
            if (
                opening == ZERO
                and closing == ZERO
                and balance.period_debit == ZERO
                and balance.period_credit == ZERO
            ):
                # Last year's income, carried into a year it did not move in.
                continue
            line = self._trial_balance_line(
                ledger_account_id=account.id,
                code=account.code,
                name=account.name,
                account_type=account.account_type,
                opening=opening,
                period_debit=balance.period_debit,
                period_credit=balance.period_credit,
                closing=closing,
            )
            for key in totals:
                totals[key] += getattr(line, key)
            lines.append(line)
        if earned_before != ZERO:
            line = self._trial_balance_line(
                ledger_account_id=None,
                code="P&L-BF",
                name="Profit and loss brought forward",
                account_type=AccountType.EQUITY.value,
                opening=earned_before,
                period_debit=ZERO,
                period_credit=ZERO,
                closing=earned_before,
            )
            for key in totals:
                totals[key] += getattr(line, key)
            lines.append(line)

        return TrialBalanceReport(
            accounting_period_id=accounting_period_id,
            to_period_id=None if last.id == period.id else last.id,
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
        self,
        *,
        firm_id: UUID,
        ledger_account_id: UUID,
        accounting_period_id: UUID,
        to_period_id: UUID | None = None,
    ) -> GeneralLedgerReport:
        """Return the movement statement for one account and period.

        With ``to_period_id`` the statement runs from the first month's
        opening through every posting of the months up to that one, in journal
        date order, to the last month's closing (backlog 50 item 5) -- within
        one financial year, as the trial balance range is.
        """
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Ledger account not found.")
        period, last, months = self._span(
            firm_id=firm_id,
            from_period_id=accounting_period_id,
            to_period_id=to_period_id,
            what="A ledger statement",
        )
        month_ids = [month.id for month in months]

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
        if account.account_type in PROFIT_LOSS_ACCOUNT_TYPES:
            # A new financial year opens an income or expense ledger at zero
            # (D-FIN-22); what it held before belongs to earlier years.
            opening -= self._brought_forward(
                firm_id=firm_id, period=period, account_ids=[account.id]
            ).get(account.id, ZERO)
        increases_on_debit = account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES

        # Ordered by the journal date, not by ``posting_date``. A back-dated
        # entry posted today carries today's wall clock, so ordering on it put
        # the statement in the sequence someone happened to press Post rather
        # than the sequence the business ran in -- and the running balance is
        # only meaningful in the latter.
        postings = self._session.execute(
            select(
                JournalEntry.id,
                JournalEntry.journal_date,
                JournalEntry.reference_number,
                JournalLine.description,
                JournalEntry.description,
                GLPosting.debit_amount,
                GLPosting.credit_amount,
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .join(JournalLine, JournalLine.id == GLPosting.journal_line_id)
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id == ledger_account_id,
                GLPosting.accounting_period_id.in_(month_ids),
            )
            .order_by(
                JournalEntry.journal_date.asc(),
                JournalEntry.reference_number.asc(),
            )
        ).all()

        running = opening
        lines: list[GeneralLedgerLine] = []
        for (
            entry_id,
            journal_date,
            reference_number,
            line_description,
            entry_description,
            debit,
            credit,
        ) in postings:
            movement = debit - credit if increases_on_debit else credit - debit
            running += movement
            lines.append(
                GeneralLedgerLine(
                    journal_entry_id=entry_id,
                    journal_date=journal_date,
                    reference_number=reference_number,
                    # The line's own narration, which is what says *what* this
                    # movement was; the entry description is the fallback. This
                    # read ``posting.error_message or entry.description``, so a
                    # narration typed on every line was never displayed, and a
                    # posting that had failed would have shown its error text
                    # as the ledger narration.
                    description=line_description or entry_description,
                    debit_amount=debit,
                    credit_amount=credit,
                    running_balance=running,
                )
            )

        if last.id == period.id:
            closing_row = balance
            total_debit = balance.period_debit if balance is not None else ZERO
            total_credit = balance.period_credit if balance is not None else ZERO
        else:
            closing_row = self._session.scalar(
                select(LedgerBalance).where(
                    LedgerBalance.ledger_account_id == ledger_account_id,
                    LedgerBalance.accounting_period_id == last.id,
                    LedgerBalance.firm_id == firm_id,
                )
            )
            debit_sum, credit_sum = self._session.execute(
                select(
                    func.coalesce(func.sum(LedgerBalance.period_debit), 0),
                    func.coalesce(func.sum(LedgerBalance.period_credit), 0),
                ).where(
                    LedgerBalance.ledger_account_id == ledger_account_id,
                    LedgerBalance.accounting_period_id.in_(month_ids),
                    LedgerBalance.firm_id == firm_id,
                )
            ).one()
            total_debit = Decimal(str(debit_sum)) + ZERO
            total_credit = Decimal(str(credit_sum)) + ZERO

        return GeneralLedgerReport(
            ledger_account_id=account.id,
            account_code=account.code,
            account_name=account.name,
            account_type=AccountTypeEnum(account.account_type),
            accounting_period_id=accounting_period_id,
            to_period_id=None if last.id == period.id else last.id,
            opening_balance=opening,
            total_debit=total_debit,
            total_credit=total_credit,
            closing_balance=(
                closing_row.closing_balance if closing_row is not None else running
            ),
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

    def profit_and_loss_range(
        self,
        *,
        firm_id: UUID,
        from_period_id: UUID,
        to_period_id: UUID,
        compare_previous_year: bool = False,
    ) -> ProfitLossRangeReport:
        """Return the profit and loss over a run of months (backlog 50).

        The Tally and Zoho convention: a whole financial year, a quarter, or
        any run of months, each month as its own column beside the total, and
        optionally the same months of the year before. Periods stay the unit,
        so a span can never cut a month in half; both ends must lie in one
        financial year, because profit resets at the year end.

        Args:
            firm_id: The firm.
            from_period_id: The first month of the span.
            to_period_id: The last month of the span, inclusive.
            compare_previous_year: Add the previous financial year's same
                months (by period number) as a comparison.

        Raises:
            ResourceNotFoundError: If either period is not the firm's.
            ValidationError: If the two periods are in different years, or the
                span runs backwards.

        """
        first, _, months = self._span(
            firm_id=firm_id,
            from_period_id=from_period_id,
            to_period_id=to_period_id,
            what="A profit and loss",
        )
        position = {period.id: index for index, period in enumerate(months)}
        accounts, movements = self._movements(firm_id, list(position))

        comparison_year: FinancialYear | None = None
        compared: dict[UUID, Decimal] = {}
        if compare_previous_year:
            comparison_year, compared_periods = self._previous_year_periods(
                firm_id,
                first.financial_year_id,
                [period.period_number for period in months],
            )
            if compared_periods:
                compared_accounts, compared_moves = self._movements(
                    firm_id, compared_periods
                )
                accounts.update(compared_accounts)
                for (account_id, _), amount in compared_moves.items():
                    compared[account_id] = compared.get(account_id, ZERO) + amount

        per_account: dict[UUID, list[Decimal]] = {}
        for (account_id, period_id), amount in movements.items():
            row = per_account.setdefault(account_id, [ZERO] * len(months))
            row[position[period_id]] += amount
        for account_id in compared:
            per_account.setdefault(account_id, [ZERO] * len(months))

        income: list[ProfitLossRangeLine] = []
        expenses: list[ProfitLossRangeLine] = []
        for account_id, by_month in per_account.items():
            account = accounts[account_id]
            total = sum(by_month, ZERO)
            comparison = compared.get(account_id, ZERO) if comparison_year else None
            if total == ZERO and not comparison:
                continue
            line = ProfitLossRangeLine(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=AccountTypeEnum(account.account_type),
                amount=total,
                months=by_month,
                comparison_amount=comparison,
            )
            if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES:
                expenses.append(line)
            else:
                income.append(line)
        income.sort(key=lambda line: line.account_code)
        expenses.sort(key=lambda line: line.account_code)

        total_income = sum((line.amount for line in income), ZERO)
        total_expense = sum((line.amount for line in expenses), ZERO)
        compared_income: Decimal | None = None
        compared_expense: Decimal | None = None
        if comparison_year is not None:
            compared_income = sum(
                (line.comparison_amount or ZERO for line in income), ZERO
            )
            compared_expense = sum(
                (line.comparison_amount or ZERO for line in expenses), ZERO
            )
        monthly = [
            sum((line.months[index] for line in income), ZERO)
            - sum((line.months[index] for line in expenses), ZERO)
            for index in range(len(months))
        ]
        return ProfitLossRangeReport(
            financial_year_id=first.financial_year_id,
            from_period_id=from_period_id,
            to_period_id=to_period_id,
            generated_at=utc_now(),
            months=[
                ProfitLossRangeMonth(
                    accounting_period_id=period.id,
                    name=period.name,
                    starts_on=period.starts_on,
                )
                for period in months
            ],
            income=income,
            expenses=expenses,
            total_income=total_income,
            total_expense=total_expense,
            net_profit=total_income - total_expense,
            monthly_net_profit=monthly,
            comparison_year_id=(
                None if comparison_year is None else comparison_year.id
            ),
            comparison_income=compared_income,
            comparison_expense=compared_expense,
            comparison_net_profit=(
                None
                if compared_income is None or compared_expense is None
                else compared_income - compared_expense
            ),
        )

    def _movements(
        self, firm_id: UUID, period_ids: list[UUID]
    ) -> tuple[dict[UUID, LedgerAccount], dict[tuple[UUID, UUID], Decimal]]:
        """Return each income and expense account's signed movement per period.

        Income counts on the credit side and expense on the debit, so a
        positive figure is always this much income or this much cost.
        """
        accounts: dict[UUID, LedgerAccount] = {}
        movements: dict[tuple[UUID, UUID], Decimal] = {}
        if not period_ids:
            return accounts, movements
        rows = self._session.execute(
            select(LedgerBalance, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == LedgerBalance.ledger_account_id)
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                LedgerAccount.account_type.in_(PROFIT_LOSS_ACCOUNT_TYPES),
                LedgerBalance.accounting_period_id.in_(period_ids),
            )
        ).all()
        for balance, account in rows:
            accounts[account.id] = account
            movement = (
                balance.period_debit - balance.period_credit
                if account.account_type in DEBIT_BALANCE_ACCOUNT_TYPES
                else balance.period_credit - balance.period_debit
            )
            key = (account.id, balance.accounting_period_id)
            movements[key] = movements.get(key, ZERO) + movement
        return accounts, movements

    def _previous_year_periods(
        self, firm_id: UUID, financial_year_id: UUID, period_numbers: list[int]
    ) -> tuple[FinancialYear | None, list[UUID]]:
        """Return the year ending the day before this one, and its same months."""
        year = self._session.get(FinancialYear, financial_year_id)
        if year is None:
            return None, []
        previous = self._session.scalar(
            select(FinancialYear).where(
                FinancialYear.firm_id == firm_id,
                FinancialYear.is_deleted.is_(False),
                FinancialYear.ends_on == year.starts_on - timedelta(days=1),
            )
        )
        if previous is None:
            return None, []
        periods = list(
            self._session.scalars(
                select(AccountingPeriod.id).where(
                    AccountingPeriod.firm_id == firm_id,
                    AccountingPeriod.financial_year_id == previous.id,
                    AccountingPeriod.is_deleted.is_(False),
                    AccountingPeriod.period_number.in_(period_numbers),
                )
            ).all()
        )
        return previous, periods

    def account_summary(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> list[AccountSummary]:
        """Return one balance row per account with movement for the period."""
        period = self._require_period(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        )
        rows = self._balances(
            firm_id=firm_id, accounting_period_id=accounting_period_id
        )
        brought_forward = self._brought_forward(
            firm_id=firm_id,
            period=period,
            account_ids=[
                account.id
                for _, account in rows
                if account.account_type in PROFIT_LOSS_ACCOUNT_TYPES
            ],
        )
        return [
            AccountSummary(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=AccountTypeEnum(account.account_type),
                opening_balance=balance.opening_balance
                - brought_forward.get(account.id, ZERO),
                period_debit=balance.period_debit,
                period_credit=balance.period_credit,
                closing_balance=balance.closing_balance
                - brought_forward.get(account.id, ZERO),
            )
            for balance, account in rows
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

    def _span(
        self,
        *,
        firm_id: UUID,
        from_period_id: UUID,
        to_period_id: UUID | None,
        what: str,
    ) -> tuple[AccountingPeriod, AccountingPeriod, list[AccountingPeriod]]:
        """Return the first and last month of a span and every month in it.

        One rule for every statement read over a run of months (backlog 50):
        both ends are the firm's own periods, in one financial year -- income
        and expense start again at the year, so a span across two would carry
        last year's result into this year's figures -- and not backwards. No
        ``to_period_id`` is the one month on its own.

        Raises:
            ResourceNotFoundError: If either period is not the firm's.
            ValidationError: If the two periods are in different years, or the
                span runs backwards.

        """
        first = self._require_period(
            firm_id=firm_id, accounting_period_id=from_period_id
        )
        if to_period_id is None or to_period_id == from_period_id:
            return first, first, [first]
        last = self._require_period(firm_id=firm_id, accounting_period_id=to_period_id)
        if first.financial_year_id != last.financial_year_id:
            raise ValidationError(
                f"{what} runs within one financial year; choose two months of "
                "the same year."
            )
        if first.starts_on > last.starts_on:
            raise ValidationError("The first month must come before the last.")
        months = list(
            self._session.scalars(
                select(AccountingPeriod)
                .where(
                    AccountingPeriod.firm_id == firm_id,
                    AccountingPeriod.financial_year_id == first.financial_year_id,
                    AccountingPeriod.is_deleted.is_(False),
                    AccountingPeriod.starts_on >= first.starts_on,
                    AccountingPeriod.starts_on <= last.starts_on,
                )
                .order_by(AccountingPeriod.starts_on.asc())
            ).all()
        )
        return first, last, months

    def _period_positions(
        self, *, firm_id: UUID, accounting_period_id: UUID
    ) -> list[tuple[LedgerBalance, LedgerAccount]]:
        """Return every account with a stored or carried balance in one period."""
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
        return rows

    def _range_balances(
        self,
        *,
        firm_id: UUID,
        first: AccountingPeriod,
        last: AccountingPeriod,
        months: list[AccountingPeriod],
    ) -> list[tuple[LedgerBalance, LedgerAccount]]:
        """Return each account's opening, movement and closing over a span.

        One month is the stored and carried balances as they are. Over several,
        the opening is the first month's, the closing the last month's -- both
        read the way a single month reads them, carried balances included --
        and the debits and credits between are summed in SQL over the months'
        stored balances. The rows are built in memory and never added to the
        session, as carried ones are.
        """
        if first.id == last.id:
            return self._period_positions(
                firm_id=firm_id, accounting_period_id=first.id
            )
        opening = {
            account.id: (balance.opening_balance, account)
            for balance, account in self._period_positions(
                firm_id=firm_id, accounting_period_id=first.id
            )
        }
        closing = {
            account.id: (balance.closing_balance, account)
            for balance, account in self._period_positions(
                firm_id=firm_id, accounting_period_id=last.id
            )
        }
        moved = (
            select(
                LedgerBalance.ledger_account_id.label("account_id"),
                func.sum(LedgerBalance.period_debit).label("debit"),
                func.sum(LedgerBalance.period_credit).label("credit"),
            )
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerBalance.accounting_period_id.in_([m.id for m in months]),
            )
            .group_by(LedgerBalance.ledger_account_id)
            .subquery()
        )
        movements: dict[UUID, tuple[Decimal, Decimal, LedgerAccount]] = {}
        for account, debit, credit in self._session.execute(
            select(LedgerAccount, moved.c.debit, moved.c.credit)
            .join(moved, moved.c.account_id == LedgerAccount.id)
            .where(LedgerAccount.is_deleted.is_(False))
        ).all():
            movements[account.id] = (
                Decimal(str(debit or 0)) + ZERO,
                Decimal(str(credit or 0)) + ZERO,
                account,
            )
        rows: list[tuple[LedgerBalance, LedgerAccount]] = []
        for account_id in set(opening) | set(closing) | set(movements):
            account = (
                opening.get(account_id)
                or closing.get(account_id)
                or (ZERO, movements[account_id][2])
            )[1]
            debit, credit, _ = movements.get(account_id, (ZERO, ZERO, account))
            rows.append(
                (
                    LedgerBalance(
                        firm_id=firm_id,
                        ledger_account_id=account_id,
                        accounting_period_id=last.id,
                        opening_balance=opening.get(account_id, (ZERO, account))[0],
                        period_debit=debit,
                        period_credit=credit,
                        closing_balance=closing.get(account_id, (ZERO, account))[0],
                    ),
                    account,
                )
            )
        rows.sort(key=lambda row: row[1].code)
        return rows

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

    def _brought_forward(
        self, *, firm_id: UUID, period: AccountingPeriod, account_ids: list[UUID]
    ) -> dict[UUID, Decimal]:
        """Return what each account had run up before this financial year began.

        The stored balances run on from one year into the next, and the
        balance sheet reads them that way: an income or expense account's
        closing is everything it has ever earned, which is what the sheet's
        earnings are. A trial balance and an account ledger answer a different
        question -- this year -- so they take this figure off an income or
        expense account (D-FIN-22). It is the closing balance of the last
        period, before the year starts, that the account was posted in.
        """
        if not account_ids:
            return {}
        year_starts = self._session.scalar(
            select(FinancialYear.starts_on).where(
                FinancialYear.id == period.financial_year_id
            )
        )
        if year_starts is None:
            return {}
        history = self._session.execute(
            select(LedgerBalance.ledger_account_id, LedgerBalance.closing_balance)
            .join(
                AccountingPeriod,
                AccountingPeriod.id == LedgerBalance.accounting_period_id,
            )
            .where(
                LedgerBalance.firm_id == firm_id,
                LedgerBalance.ledger_account_id.in_(account_ids),
                AccountingPeriod.ends_on < year_starts,
            )
            .order_by(AccountingPeriod.ends_on.asc())
        ).all()
        carried: dict[UUID, Decimal] = {}
        for account_id, closing in history:
            carried[account_id] = closing
        return carried

    def _trial_balance_line(
        self,
        *,
        ledger_account_id: UUID | None,
        code: str,
        name: str,
        account_type: str,
        opening: Decimal,
        period_debit: Decimal,
        period_credit: Decimal,
        closing: Decimal,
    ) -> TrialBalanceLine:
        """Build one trial balance row, each balance split by side."""
        opening_debit, opening_credit = self._present_balance(account_type, opening)
        closing_debit, closing_credit = self._present_balance(account_type, closing)
        return TrialBalanceLine(
            ledger_account_id=ledger_account_id,
            account_code=code,
            account_name=name,
            account_type=AccountTypeEnum(account_type),
            opening_balance=opening,
            opening_debit=opening_debit,
            opening_credit=opening_credit,
            period_debit=period_debit,
            period_credit=period_credit,
            closing_balance=closing,
            closing_debit=closing_debit,
            closing_credit=closing_credit,
        )

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
