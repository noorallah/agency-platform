"""Which of a firm's accounts hold money, and what one held on a day.

One rule, read by the contra voucher, the expense and the settlement: there
were going to be three copies of it the day a second document asked whether
an account is cash.

**Which accounts hold money.** The firm's CASH and BANK control accounts, and
any other active ASSET account in the same account group as either -- a second
bank account, petty cash -- that no other control purpose claims.

**Cash or bank.** The CASH control account is cash and the BANK one is a bank.
Any other money account is cash when it sits in the cash account's group and
not the bank's, a bank in the reverse case, and -- where the two share a group,
as they do in the seeded chart -- cash when its name says "cash" (petty cash,
cash at branch) and a bank otherwise.

**Paying out of cash that is not there** (`ask_before_cash_goes_below_zero`).
A bank account may be overdrawn and the bank says so; a cash box cannot hold
less than nothing, so a payment that leaves one below zero is nearly always a
receipt not yet keyed or a wrong account chosen. The save is answered with a
question the screen must confirm, and saved when it is sent again confirmed.
It is never a refusal: the books may simply be behind.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models import (
    AccountGroup,
    AccountType,
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose

MONEY_PURPOSES = frozenset(
    {ControlAccountPurpose.CASH.value, ControlAccountPurpose.BANK.value}
)

#: The group every employee's advance account is opened in (row P4). Known
#: by its code, so a firm may rename it. An account in it is money a person
#: owes the firm, never money the firm holds.
STAFF_ADVANCES_GROUP_CODE = "CA-STAFF"

KIND_CASH = "CASH"
KIND_BANK = "BANK"

#: ``details.reason`` of the question below; the screen decides on it, never
#: on the sentence.
CASH_BELOW_ZERO = "cash_below_zero"


def _kind_of_account(
    account: LedgerAccount,
    *,
    cash_id: UUID | None,
    bank_id: UUID | None,
    cash_group: UUID | None,
    bank_group: UUID | None,
) -> str:
    """Say whether one money account is cash or a bank account."""
    if account.id == cash_id:
        return KIND_CASH
    if account.id == bank_id:
        return KIND_BANK
    in_cash = account.account_group_id == cash_group
    in_bank = account.account_group_id == bank_group
    if in_cash and not in_bank:
        return KIND_CASH
    if in_bank and not in_cash:
        return KIND_BANK
    return KIND_CASH if "cash" in account.name.lower() else KIND_BANK


def money_accounts(session: Session, firm_id: UUID) -> list[tuple[LedgerAccount, str]]:
    """Return every account money may move into or out of, with its kind.

    By account code. A firm that has nominated neither a cash nor a bank
    account has none.
    """
    mapped: dict[UUID, set[str]] = {}
    nominated: dict[str, UUID] = {}
    for account_id, purpose in session.execute(
        select(FirmControlAccount.ledger_account_id, FirmControlAccount.purpose).where(
            FirmControlAccount.firm_id == firm_id,
            FirmControlAccount.is_deleted.is_(False),
        )
    ).all():
        mapped.setdefault(account_id, set()).add(purpose)
        if purpose in MONEY_PURPOSES:
            nominated[purpose] = account_id
    if not nominated:
        return []
    groups: dict[UUID, UUID] = {
        account_id: group_id
        for account_id, group_id in session.execute(
            select(LedgerAccount.id, LedgerAccount.account_group_id).where(
                LedgerAccount.id.in_(nominated.values())
            )
        ).all()
    }
    cash_id = nominated.get(ControlAccountPurpose.CASH.value)
    bank_id = nominated.get(ControlAccountPurpose.BANK.value)
    cash_group = groups.get(cash_id) if cash_id else None
    bank_group = groups.get(bank_id) if bank_id else None
    wanted = {group for group in (cash_group, bank_group) if group is not None}
    candidates = session.scalars(
        select(LedgerAccount)
        .where(
            LedgerAccount.firm_id == firm_id,
            LedgerAccount.is_deleted.is_(False),
            LedgerAccount.is_active.is_(True),
            LedgerAccount.account_type == AccountType.ASSET.value,
            or_(
                LedgerAccount.account_group_id.in_(wanted),
                LedgerAccount.id.in_(nominated.values()),
            ),
        )
        .order_by(LedgerAccount.code.asc())
    ).all()
    return [
        (
            account,
            _kind_of_account(
                account,
                cash_id=cash_id,
                bank_id=bank_id,
                cash_group=cash_group,
                bank_group=bank_group,
            ),
        )
        for account in candidates
        if mapped.get(account.id, set()) <= MONEY_PURPOSES
    ]


def staff_advance_account_ids(session: Session, firm_id: UUID) -> set[UUID]:
    """Return the ids of every account in the firm's Staff Advances group.

    Read by the expense form, which offers every asset account the firm
    opened itself as a place money is paid from: an employee is not one.
    """
    return set(
        session.scalars(
            select(LedgerAccount.id)
            .join(AccountGroup, AccountGroup.id == LedgerAccount.account_group_id)
            .where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
                AccountGroup.firm_id == firm_id,
                AccountGroup.code == STAFF_ADVANCES_GROUP_CODE,
                AccountGroup.is_deleted.is_(False),
            )
        ).all()
    )


def balance_on(
    session: Session, account_id: UUID, *, firm_id: UUID, on: date
) -> Decimal:
    """Return what a money account held at the end of a day.

    Summed from every posting dated on or before it -- by the journal's
    own date, not when it was keyed, so a back-dated receipt counts on the
    day it says. Reversed originals and their mirrors both count, which
    nets them to nothing as it should.
    """
    total = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
        .where(
            GLPosting.firm_id == firm_id,
            GLPosting.ledger_account_id == account_id,
            JournalEntry.journal_date <= on,
        )
    )
    return quantize_ledger(Decimal(str(total or 0)))


def _money(value: Decimal) -> str:
    """Format an amount for a sentence."""
    return f"{value:,.2f}"


def ask_before_cash_goes_below_zero(
    session: Session,
    *,
    firm_id: UUID,
    account_id: UUID,
    journal_entry_id: UUID,
    on: date,
) -> None:
    """Ask before a journal already staged leaves a cash account below zero.

    Called **after** the document's journal is staged and before the router
    commits, so the amount is whatever really left the account -- less the tax
    deducted at source, in rupees for a payment abroad -- and no caller works
    it out a second time. Raising here rolls the staged document back: nothing
    is saved until the same request arrives confirmed.

    A bank account is never asked about, nor an account that is not the
    firm's money at all. The day judged is the document's own.

    Raises:
        ConflictError: With ``details.reason == "cash_below_zero"`` when the
            account is cash and stands below zero on the day after this.

    """
    session.flush()
    account = next(
        (
            row
            for row, kind in money_accounts(session, firm_id)
            if row.id == account_id and kind == KIND_CASH
        ),
        None,
    )
    if account is None:
        return
    after = balance_on(session, account_id, firm_id=firm_id, on=on)
    if after >= ZERO:
        return
    paid = quantize_ledger(
        Decimal(
            str(
                session.scalar(
                    select(
                        func.coalesce(
                            func.sum(GLPosting.credit_amount - GLPosting.debit_amount),
                            0,
                        )
                    ).where(
                        GLPosting.journal_entry_id == journal_entry_id,
                        GLPosting.ledger_account_id == account_id,
                    )
                )
                or 0
            )
        )
    )
    if paid <= ZERO:
        return
    holds = after + paid
    day = on.strftime("%d-%m-%Y")
    sentence = (
        f"{account.name} is already {_money(-holds)} below zero on {day} and "
        f"this pays {_money(paid)} more out of it."
        if holds < ZERO
        else f"{account.name} holds {_money(holds)} on {day} and this pays "
        f"{_money(paid)} out of it, which leaves it {_money(-after)} below zero."
    )
    raise ConflictError(
        f"{sentence} Save anyway?",
        details={
            "reason": CASH_BELOW_ZERO,
            "account_id": str(account.id),
            "account_name": account.name,
            "holds": str(holds),
            "paying": str(paid),
            "on": on.isoformat(),
        },
    )


__all__ = [
    "CASH_BELOW_ZERO",
    "KIND_BANK",
    "KIND_CASH",
    "MONEY_PURPOSES",
    "STAFF_ADVANCES_GROUP_CODE",
    "ask_before_cash_goes_below_zero",
    "balance_on",
    "money_accounts",
    "staff_advance_account_ids",
]
