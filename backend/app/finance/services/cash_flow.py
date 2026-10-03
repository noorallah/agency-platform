"""The cash flow statement, by the indirect method (ACC-9, decision A87).

Where the firm's cash came from and went over a run of months, the way a bank
reads it in a loan file (AS 3 / Ind AS 7, the indirect method Tally and Zoho
use): start from the profit, add back what moved working capital, then what
was spent on or raised from long-lived things.

It is read from the same balances as the trial balance and needs no other
source, because double entry does the reconciling: across every account the
period's debits equal its credits, so the cash and bank accounts' movement is
exactly the negative of every other account's. Each non-cash account's
**credit less debit** over the period is therefore its cash effect, and the
statement only sorts those effects into sections:

* **Operating** -- the net profit (every income and expense account), then the
  change in each current asset and current liability: receivables, stock,
  input and output tax, payables, provisions. "Current" is an account under
  the *Current Assets* or *Current Liabilities* group (``CA`` / ``CL``, or a
  group inside one), or a control account.
* **Investing** -- every other asset: fixed assets, investments, deposits.
* **Financing** -- every other liability and equity: loans, capital,
  drawings.
* **Cash** -- the accounts mapped to the cash and bank purposes, and any
  account under the *Cash-in-Hand* or *Bank Accounts* groups. Their opening
  and closing are the statement's first and last lines, and the sections must
  add up to the difference -- ``is_reconciled`` says whether they do.

There is no fixed-asset register, so depreciation is not added back by name;
a firm that posts it to an expense and credits an asset sees it in the profit
and again under investing, which nets to the same cash.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models import AccountGroup, AccountType, LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.general_ledger_service import GeneralLedgerService

ZERO = Decimal("0.00")
#: Groups whose accounts are cash (decision A22's sub-groups).
CASH_GROUPS = frozenset({"CA-CASH", "CA-BANK"})
#: Top groups whose accounts are working capital.
CURRENT_GROUPS = frozenset({"CA", "CL"})
#: Income and expense: their net is the profit.
PROFIT_LOSS = frozenset({AccountType.INCOME.value, AccountType.EXPENSE.value})


@dataclass(frozen=True, slots=True)
class CashFlowLine:
    """One account's cash effect over the period."""

    ledger_account_id: UUID | None
    account_code: str
    account_name: str
    #: Positive brought cash in; negative took it out.
    amount: Decimal


@dataclass(slots=True)
class CashFlowStatement:
    """The statement over a run of months."""

    from_date: date
    to_date: date
    net_profit: Decimal = ZERO
    operating: list[CashFlowLine] = field(default_factory=list)
    investing: list[CashFlowLine] = field(default_factory=list)
    financing: list[CashFlowLine] = field(default_factory=list)
    opening_cash: Decimal = ZERO
    closing_cash: Decimal = ZERO

    @property
    def operating_total(self) -> Decimal:
        """Return the cash from operations: profit plus working capital."""
        return self.net_profit + sum((x.amount for x in self.operating), ZERO)

    @property
    def investing_total(self) -> Decimal:
        """Return the cash spent on or raised from long-lived assets."""
        return sum((x.amount for x in self.investing), ZERO)

    @property
    def financing_total(self) -> Decimal:
        """Return the cash raised from or repaid to lenders and owners."""
        return sum((x.amount for x in self.financing), ZERO)

    @property
    def net_change(self) -> Decimal:
        """Return the three sections together."""
        return self.operating_total + self.investing_total + self.financing_total

    @property
    def is_reconciled(self) -> bool:
        """Return whether the sections explain the change in cash and bank."""
        return self.opening_cash + self.net_change == self.closing_cash


class CashFlowService:
    """Build the cash flow statement from the ledger's balances."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session
        self._ledger = GeneralLedgerService(session)

    def statement(
        self, *, firm_id: UUID, from_period_id: UUID, to_period_id: UUID
    ) -> CashFlowStatement:
        """Return the cash flow over a run of months in one financial year."""
        first, last, months = self._ledger._span(
            firm_id=firm_id,
            from_period_id=from_period_id,
            to_period_id=to_period_id,
            what="A cash flow statement",
        )
        rows = self._ledger._range_balances(
            firm_id=firm_id, first=first, last=last, months=months
        )
        cash_ids = self._cash_accounts(firm_id)
        tops = self._top_groups(firm_id)
        result = CashFlowStatement(from_date=first.starts_on, to_date=last.ends_on)
        for balance, account in rows:
            effect = Decimal(str(balance.period_credit)) - Decimal(
                str(balance.period_debit)
            )
            if account.id in cash_ids or self._in_cash_group(account, tops):
                result.opening_cash += self._debit_side(
                    account, balance.opening_balance
                )
                result.closing_cash += self._debit_side(
                    account, balance.closing_balance
                )
                continue
            if account.account_type in PROFIT_LOSS:
                result.net_profit += effect
                continue
            if account.account_type == AccountType.MEMO.value or effect == ZERO:
                continue
            line = CashFlowLine(
                ledger_account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                amount=effect,
            )
            found = tops.get(account.account_group_id)
            top = None if found is None else found[1]
            if account.account_type == AccountType.CONTROL.value or (
                top in CURRENT_GROUPS or top is None
            ):
                result.operating.append(line)
            elif account.account_type == AccountType.ASSET.value:
                result.investing.append(line)
            else:
                result.financing.append(line)
        return result

    # ---- classifying -----------------------------------------------------

    def _cash_accounts(self, firm_id: UUID) -> set[UUID]:
        """Return the accounts mapped to the cash and bank purposes."""
        mapping = ControlAccountService(self._session).mapping(firm_id)
        return {
            account_id
            for purpose, account_id in mapping.items()
            if purpose
            in (ControlAccountPurpose.CASH.value, ControlAccountPurpose.BANK.value)
        }

    def _top_groups(self, firm_id: UUID) -> dict[UUID, tuple[str, str]]:
        """Return each group's own code and its top ancestor's code."""
        groups = {
            group.id: group
            for group in self._session.scalars(
                select(AccountGroup).where(
                    AccountGroup.firm_id == firm_id,
                    AccountGroup.is_deleted.is_(False),
                )
            ).all()
        }
        tops: dict[UUID, tuple[str, str]] = {}
        for group_id, group in groups.items():
            cursor = group
            seen: set[UUID] = set()
            while cursor.parent_group_id in groups and cursor.id not in seen:
                seen.add(cursor.id)
                cursor = groups[cursor.parent_group_id]
            tops[group_id] = (group.code, cursor.code)
        return tops

    def _in_cash_group(
        self, account: LedgerAccount, tops: dict[UUID, tuple[str, str]]
    ) -> bool:
        """Return whether an account sits under Cash-in-Hand or Bank Accounts."""
        own = tops.get(account.account_group_id)
        return own is not None and own[0] in CASH_GROUPS

    @staticmethod
    def _debit_side(account: LedgerAccount, amount: Decimal) -> Decimal:
        """Return a cash balance as money held: debit-normal is positive."""
        value = Decimal(str(amount))
        if account.account_type == AccountType.ASSET.value:
            return value
        return -value


__all__ = ["CashFlowLine", "CashFlowService", "CashFlowStatement"]
