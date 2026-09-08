"""Which ledger account each kind of document posting lands in.

Automatic posting has never existed: no module outside ``app/finance`` imports
finance, and the three ``*_accounting_events`` tables hold hardcoded account
*names* with narration reading "Placeholder accounting event for …". A previous
attempt guessed accounts by matching on their name and was removed.

Guessing is the wrong shape. Which account a firm posts its receivables or its
cost of goods sold to is a decision that firm's accountant makes, and it differs
between firms on the same chart of accounts. This maps a fixed set of *purposes*
— what the posting means — onto whichever account the firm nominates, so the
posting rules stay in code and the account numbers stay in data.

A purpose with no mapping is an error naming the purpose, never a fallback: a
journal posted to a guessed account is worse than a journal refused.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import BusinessRuleError, ValidationError
from app.finance.models import (
    FirmControlAccount,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)


class ControlAccountPurpose(StrEnum):
    """What a posting line means, independent of the account it lands in."""

    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"
    SALES_REVENUE = "SALES_REVENUE"
    SALES_RETURNS = "SALES_RETURNS"
    PURCHASE_EXPENSE = "PURCHASE_EXPENSE"
    PURCHASE_RETURNS = "PURCHASE_RETURNS"
    OUTPUT_TAX = "OUTPUT_TAX"
    INPUT_TAX = "INPUT_TAX"
    INVENTORY = "INVENTORY"
    GOODS_RECEIVED_NOT_INVOICED = "GOODS_RECEIVED_NOT_INVOICED"
    COST_OF_GOODS_SOLD = "COST_OF_GOODS_SOLD"
    PURCHASE_PRICE_VARIANCE = "PURCHASE_PRICE_VARIANCE"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"
    OPENING_BALANCE_EQUITY = "OPENING_BALANCE_EQUITY"
    DISCOUNT_ALLOWED = "DISCOUNT_ALLOWED"
    COMMISSION_EXPENSE = "COMMISSION_EXPENSE"
    COMMISSION_PAYABLE = "COMMISSION_PAYABLE"
    #: What was collected from a buyer and is owed to the government. A
    #: liability of its own rather than Output Tax: it is not GST, it is
    #: filed on a different return, and netting the two would put a
    #: quarterly TCS payment inside a monthly GST one.
    TCS_PAYABLE = "TCS_PAYABLE"
    #: What a loyalty scheme costs the firm, booked when the points are
    #: earned rather than when they are spent -- the cost belongs to the month
    #: it was incurred in, not to whenever customers happen to collect.
    LOYALTY_EXPENSE = "LOYALTY_EXPENSE"
    #: What the firm owes customers in unspent credit.
    LOYALTY_PAYABLE = "LOYALTY_PAYABLE"
    DISCOUNT_RECEIVED = "DISCOUNT_RECEIVED"
    ROUNDING = "ROUNDING"
    CASH = "CASH"
    BANK = "BANK"


# The account classification each purpose must resolve to. Posting revenue to an
# expense account is a configuration mistake worth refusing at mapping time
# rather than discovering in a trial balance.
EXPECTED_TYPE: dict[ControlAccountPurpose, frozenset[str]] = {
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE: frozenset({"ASSET", "CONTROL"}),
    ControlAccountPurpose.ACCOUNTS_PAYABLE: frozenset({"LIABILITY", "CONTROL"}),
    ControlAccountPurpose.SALES_REVENUE: frozenset({"INCOME"}),
    ControlAccountPurpose.SALES_RETURNS: frozenset({"INCOME", "EXPENSE"}),
    ControlAccountPurpose.PURCHASE_EXPENSE: frozenset({"EXPENSE"}),
    ControlAccountPurpose.PURCHASE_RETURNS: frozenset({"EXPENSE", "INCOME"}),
    ControlAccountPurpose.OUTPUT_TAX: frozenset({"LIABILITY", "CONTROL"}),
    ControlAccountPurpose.INPUT_TAX: frozenset({"ASSET", "CONTROL"}),
    ControlAccountPurpose.INVENTORY: frozenset({"ASSET"}),
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED: frozenset(
        {"LIABILITY", "CONTROL"}
    ),
    ControlAccountPurpose.COST_OF_GOODS_SOLD: frozenset({"EXPENSE"}),
    # A favourable variance is a credit to the same account, so income
    # is allowed for firms that prefer to book it there.
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE: frozenset({"EXPENSE", "INCOME"}),
    # A write-off is a cost and a favourable count is its contra, so the same
    # account takes both sides; a firm that would rather book gains separately
    # can map it to an income account instead.
    ControlAccountPurpose.INVENTORY_ADJUSTMENT: frozenset({"EXPENSE", "INCOME"}),
    # Day-one balances are what the owners put in, so this is equity. It is the
    # counterpart the chart never had: without it opening stock had nothing to
    # credit and could not post at all.
    ControlAccountPurpose.OPENING_BALANCE_EQUITY: frozenset({"EQUITY"}),
    ControlAccountPurpose.DISCOUNT_ALLOWED: frozenset({"EXPENSE"}),
    # What the firm has agreed to pay its salespeople, and what it still
    # owes them until it does. Two purposes rather than one, because an
    # approved payout is a liability that outlives the month it was
    # earned in -- booking the expense straight against cash would say the
    # firm owes nobody the moment it recognises the cost.
    ControlAccountPurpose.COMMISSION_EXPENSE: frozenset({"EXPENSE"}),
    ControlAccountPurpose.COMMISSION_PAYABLE: frozenset({"LIABILITY", "CONTROL"}),
    ControlAccountPurpose.TCS_PAYABLE: frozenset({"LIABILITY", "CONTROL"}),
    ControlAccountPurpose.LOYALTY_EXPENSE: frozenset({"EXPENSE"}),
    ControlAccountPurpose.LOYALTY_PAYABLE: frozenset({"LIABILITY", "CONTROL"}),
    ControlAccountPurpose.DISCOUNT_RECEIVED: frozenset({"INCOME"}),
    ControlAccountPurpose.ROUNDING: frozenset({"INCOME", "EXPENSE"}),
    ControlAccountPurpose.CASH: frozenset({"ASSET"}),
    ControlAccountPurpose.BANK: frozenset({"ASSET"}),
}


#: What each purpose means to somebody reading the screen, in the order the
#: enum declares them. The code is the key everywhere else; this is the label.
PURPOSE_LABELS: dict[ControlAccountPurpose, str] = {
    ControlAccountPurpose.ACCOUNTS_RECEIVABLE: "Accounts receivable",
    ControlAccountPurpose.ACCOUNTS_PAYABLE: "Accounts payable",
    ControlAccountPurpose.SALES_REVENUE: "Sales revenue",
    ControlAccountPurpose.SALES_RETURNS: "Sales returns",
    ControlAccountPurpose.PURCHASE_EXPENSE: "Purchases",
    ControlAccountPurpose.PURCHASE_RETURNS: "Purchase returns",
    ControlAccountPurpose.OUTPUT_TAX: "Output tax",
    ControlAccountPurpose.INPUT_TAX: "Input tax",
    ControlAccountPurpose.INVENTORY: "Inventory",
    ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED: "Goods received not invoiced",
    ControlAccountPurpose.COST_OF_GOODS_SOLD: "Cost of goods sold",
    ControlAccountPurpose.PURCHASE_PRICE_VARIANCE: "Purchase price variance",
    ControlAccountPurpose.INVENTORY_ADJUSTMENT: "Inventory adjustment",
    ControlAccountPurpose.OPENING_BALANCE_EQUITY: "Opening balance equity",
    ControlAccountPurpose.DISCOUNT_ALLOWED: "Discount allowed",
    ControlAccountPurpose.COMMISSION_EXPENSE: "Commission expense",
    ControlAccountPurpose.COMMISSION_PAYABLE: "Commission payable",
    ControlAccountPurpose.TCS_PAYABLE: "TCS payable",
    ControlAccountPurpose.LOYALTY_EXPENSE: "Loyalty expense",
    ControlAccountPurpose.LOYALTY_PAYABLE: "Loyalty payable",
    ControlAccountPurpose.DISCOUNT_RECEIVED: "Discount received",
    ControlAccountPurpose.ROUNDING: "Rounding",
    ControlAccountPurpose.CASH: "Cash",
    ControlAccountPurpose.BANK: "Bank",
}


@dataclass(frozen=True, slots=True)
class ControlAccountView:
    """One purpose as the mapping screen shows it."""

    purpose: ControlAccountPurpose
    label: str
    expected_types: tuple[str, ...]
    ledger_account_id: UUID | None
    account_code: str | None
    account_name: str | None
    #: Lines already posted to the mapped account. Once there are any, the
    #: mapping is held: re-pointing it would leave two accounts each holding
    #: part of one story, with nothing to say which a report should believe.
    posted_lines: int


class ControlAccountService:
    """Resolve and maintain a firm's document-posting account mapping."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a session it does not own."""
        self._session = session

    def mapping(self, firm_id: UUID) -> dict[str, UUID]:
        """Return the firm's whole mapping, purpose to ledger account."""
        rows = self._session.scalars(
            select(FirmControlAccount).where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.is_deleted.is_(False),
            )
        ).all()
        return {row.purpose: row.ledger_account_id for row in rows}

    def resolve(self, firm_id: UUID, purpose: ControlAccountPurpose) -> UUID:
        """Return the account a purpose posts to.

        Args:
            firm_id: The owning firm.
            purpose: What the posting line means.

        Returns:
            The nominated ledger account id.

        Raises:
            ValidationError: If the firm has not nominated an account. The
                message names the purpose so the gap is actionable.

        """
        account_id = self.mapping(firm_id).get(purpose.value)
        if account_id is None:
            raise ValidationError(
                f"No ledger account is configured for {purpose.value}. "
                "Set the firm's control accounts before posting this document."
            )
        return account_id

    def assign(
        self,
        firm_id: UUID,
        purpose: ControlAccountPurpose,
        ledger_account_id: UUID,
        *,
        actor_id: UUID,
    ) -> FirmControlAccount:
        """Nominate the account a purpose posts to.

        Args:
            firm_id: The owning firm.
            purpose: What the posting line means.
            ledger_account_id: The account to post it to.
            actor_id: The user making the change.

        Returns:
            The stored mapping row.

        Raises:
            ValidationError: If the account does not belong to the firm, is
                inactive, or is the wrong classification for the purpose.

        """
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ValidationError("Ledger account not found for this firm.")
        expected = EXPECTED_TYPE[purpose]
        if account.account_type not in expected:
            raise ValidationError(
                f"{purpose.value} must post to a "
                f"{' or '.join(sorted(expected))} account, "
                f"but {account.code} is {account.account_type}."
            )
        row = self._session.scalar(
            select(FirmControlAccount).where(
                FirmControlAccount.firm_id == firm_id,
                FirmControlAccount.purpose == purpose.value,
                FirmControlAccount.is_deleted.is_(False),
            )
        )
        if row is None:
            row = FirmControlAccount(
                firm_id=firm_id, purpose=purpose.value, created_by=actor_id
            )
            self._session.add(row)
        row.ledger_account_id = ledger_account_id
        row.updated_by = actor_id
        self._session.flush()
        return row

    def posted_lines(self, firm_id: UUID, ledger_account_id: UUID) -> int:
        """Count the POSTED journal lines on one of the firm's accounts."""
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(JournalLine)
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                .where(
                    JournalEntry.firm_id == firm_id,
                    JournalEntry.status == JournalStatus.POSTED.value,
                    JournalEntry.is_deleted.is_(False),
                    JournalLine.ledger_account_id == ledger_account_id,
                    JournalLine.is_deleted.is_(False),
                )
            )
            or 0
        )

    def overview(self, firm_id: UUID) -> list[ControlAccountView]:
        """Every purpose, mapped or not, in declaration order.

        The whole list rather than only the mapped rows, because the screen's
        job is to show the gaps: an unmapped purpose is the one that refuses
        a document at approval.
        """
        configured = self.mapping(firm_id)
        accounts = {
            row.id: row
            for row in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_(list(configured.values())),
                    LedgerAccount.firm_id == firm_id,
                )
            )
        }
        views: list[ControlAccountView] = []
        for purpose in ControlAccountPurpose:
            account_id = configured.get(purpose.value)
            account = accounts.get(account_id) if account_id else None
            views.append(
                ControlAccountView(
                    purpose=purpose,
                    label=PURPOSE_LABELS[purpose],
                    expected_types=tuple(sorted(EXPECTED_TYPE[purpose])),
                    ledger_account_id=account_id,
                    account_code=account.code if account else None,
                    account_name=account.name if account else None,
                    posted_lines=(
                        self.posted_lines(firm_id, account_id) if account_id else 0
                    ),
                )
            )
        return views

    def reassign(
        self,
        firm_id: UUID,
        purpose: ControlAccountPurpose,
        ledger_account_id: UUID,
        *,
        actor_id: UUID,
    ) -> FirmControlAccount:
        """Map a purpose from the screen, with the guard `assign` does not carry.

        `assign` is what the seed and the tests use and it re-points freely.
        A person re-pointing a purpose that already has postings behind it is
        a different case: every existing line stays on the old account, so
        the trial balance still balances while two accounts each hold part
        of one story. Refused by name, with the count -- a transfer entry and
        a new account in the next period is the way, and that is a decision
        for whoever keeps the books rather than something to do quietly.

        Mapping an unmapped purpose, or re-pointing one nothing has posted
        to, is an ordinary edit. Choosing the same account again is a no-op.

        Raises:
            BusinessRuleError: If the current account has posted lines and
                a different one was chosen.
            ValidationError: If the account is not the firm's, inactive, or
                the wrong classification (from `assign`).

        """
        current = self.mapping(firm_id).get(purpose.value)
        if current is not None and current != ledger_account_id:
            posted = self.posted_lines(firm_id, current)
            if posted:
                account = self._session.get(LedgerAccount, current)
                name = f"{account.code} {account.name}" if account else "its account"
                raise BusinessRuleError(
                    f"{PURPOSE_LABELS[purpose]} has {posted} posted "
                    f"line{'' if posted == 1 else 's'} on {name}. Re-pointing it "
                    "would leave two accounts each holding part of one story; "
                    "post a transfer entry and map the new account from the "
                    "next period instead."
                )
        row = self.assign(firm_id, purpose, ledger_account_id, actor_id=actor_id)
        record_audit(
            self._session,
            action="control_account.assigned",
            entity_type="firm_control_account",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"ledger_account_id": str(current) if current else None},
            after_data={
                "purpose": purpose.value,
                "ledger_account_id": str(ledger_account_id),
            },
        )
        return row

    def missing(
        self, firm_id: UUID, purposes: tuple[ControlAccountPurpose, ...]
    ) -> tuple[ControlAccountPurpose, ...]:
        """Return which of the given purposes the firm has not mapped.

        Lets a caller report every gap at once instead of failing on the first.
        """
        configured = self.mapping(firm_id)
        return tuple(p for p in purposes if p.value not in configured)
