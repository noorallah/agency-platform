"""The opening trial balance: where a firm's books stood on its first day here.

A firm moving from another tool arrives with cash in hand, money in the bank,
fixed assets, loans, capital and tax balances. Until this service the only way
to enter them was one hand-typed journal each, with the reference, type and
period chosen by hand and the difference worked out on paper (backlog 36).

Decided by the convention every package uses -- Tally's opening balances per
ledger, Xero's conversion balances: **one statement, as at one cutover date,
account by account, re-entered whole**. It is kept as **one posted journal**
rather than a table of its own, because the ledger already is the record and
a second copy would be one more thing to disagree with it. Replacing it
reverses the journal standing and posts the new one, so the history of what
was entered and when stays in the ledger too.

Three rules decide what may be on it:

- **Sub-ledger accounts are refused.** Receivables, payables and stock each
  have their own opening path -- a customer's opening balance, a supplier's
  opening bills, opening stock -- which keeps the party or the batch beside the
  ledger figure. A lump sum here would move the account with nothing
  underneath it, which is D-FIN-11's rule for hand journals.
- **Opening balance equity is refused as a line** because it is the answer:
  whatever the lines leave unbalanced lands there, the counterpart every other
  opening path already posts to.
- **All or nothing.** Every problem in the statement is reported at once,
  row by row, and nothing is written until all of it is right.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.money import ZERO, quantize_ledger, quantize_money
from app.finance.models import JournalEntry, JournalStatus, LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData

#: The journal's ``source_module``. It makes the entry a document's rather than
#: a hand journal's, so the journal screen's reverse refuses it and sends the
#: user here.
SOURCE_MODULE = "opening_balances"

#: References run OTB-1, OTB-2, ... -- one per statement entered, each
#: reversed as ``-REV`` when the next replaces it.
REFERENCE_PREFIX = "OTB-"


@dataclass(frozen=True, slots=True)
class OpeningLineInput:
    """One account's opening balance as entered."""

    account_code: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None = None


@dataclass(frozen=True, slots=True)
class OpeningLineView:
    """One account's opening balance as it stands in the ledger."""

    ledger_account_id: UUID
    account_code: str
    account_name: str
    account_type: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None


@dataclass(frozen=True, slots=True)
class OpeningTrialBalanceView:
    """The statement standing, and what it put to opening balance equity."""

    as_of_date: date | None
    journal_entry_id: UUID | None
    reference_number: str | None
    lines: list[OpeningLineView]
    total_debit: Decimal
    total_credit: Decimal
    #: Positive when the equity account was credited (assets exceed what was
    #: entered against them), negative when it was debited.
    equity_difference: Decimal


class OpeningTrialBalanceService:
    """Read and replace a firm's opening trial balance."""

    def __init__(self, session: Session) -> None:
        """Bind the service to a firm-store session."""
        self._session = session
        self._journals = JournalEntryEngine(session)
        self._control = ControlAccountService(session)
        self._posting = DocumentPostingService(session)

    def current(self, firm_id: UUID) -> OpeningTrialBalanceView:
        """Return the opening trial balance standing, or an empty one."""
        entry = self._standing(firm_id)
        if entry is None:
            return OpeningTrialBalanceView(
                as_of_date=None,
                journal_entry_id=None,
                reference_number=None,
                lines=[],
                total_debit=ZERO,
                total_credit=ZERO,
                equity_difference=ZERO,
            )
        equity_id = self._control.mapping(firm_id).get(
            ControlAccountPurpose.OPENING_BALANCE_EQUITY.value
        )
        accounts = {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_(
                        {line.ledger_account_id for line in entry.lines}
                    )
                )
            ).all()
        }
        lines: list[OpeningLineView] = []
        difference = ZERO
        for line in sorted(entry.lines, key=lambda row: row.line_number):
            if line.ledger_account_id == equity_id:
                difference += line.credit_amount - line.debit_amount
                continue
            account = accounts[line.ledger_account_id]
            lines.append(
                OpeningLineView(
                    ledger_account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    account_type=account.account_type,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                    description=line.description,
                )
            )
        lines.sort(key=lambda row: row.account_code)
        return OpeningTrialBalanceView(
            as_of_date=entry.journal_date,
            journal_entry_id=entry.id,
            reference_number=entry.reference_number,
            lines=lines,
            total_debit=sum((row.debit_amount for row in lines), ZERO),
            total_credit=sum((row.credit_amount for row in lines), ZERO),
            equity_difference=difference,
        )

    def replace(
        self,
        *,
        firm_id: UUID,
        as_of_date: date,
        lines: list[OpeningLineInput],
        actor_id: UUID,
    ) -> OpeningTrialBalanceView:
        """Replace the opening trial balance with this statement.

        The standing journal is reversed on its own date and the new one
        posted on ``as_of_date``, both inside the caller's transaction; the
        caller commits. An empty statement just takes the old one off.

        Raises:
            ValidationError: Naming every row that is wrong -- an unknown,
                inactive or repeated account, a sub-ledger account, opening
                balance equity itself -- or a date with no open period.

        """
        equity_id = self._control.resolve(
            firm_id, ControlAccountPurpose.OPENING_BALANCE_EQUITY
        )
        resolved = self._resolve_lines(firm_id, lines, equity_id)
        # Asked before anything is reversed, so a date with no open period
        # refuses the statement instead of leaving the firm with none.
        context = self._posting.context_for(firm_id, as_of_date) if resolved else None

        previous = self._standing(firm_id)
        if previous is not None:
            self._journals.reverse_entry(
                previous.id,
                firm_id=firm_id,
                reference_number=f"{previous.reference_number}-REV",
                journal_date=previous.journal_date,
                actor_id=actor_id,
            )

        posted: JournalEntry | None = None
        if context is not None:
            debit = sum((line.debit_amount for line in resolved), ZERO)
            credit = sum((line.credit_amount for line in resolved), ZERO)
            difference = debit - credit
            journal_lines = list(resolved)
            if difference != ZERO:
                journal_lines.append(
                    JournalLineData(
                        ledger_account_id=equity_id,
                        debit_amount=-difference if difference < ZERO else ZERO,
                        credit_amount=difference if difference > ZERO else ZERO,
                        description="Opening balance difference",
                    )
                )
            reference = self._next_reference(firm_id)
            entry = self._journals.create_entry(
                firm_id=firm_id,
                journal_type_id=context.journal_type_id,
                voucher_type_id=context.voucher_type_id,
                accounting_period_id=context.accounting_period_id,
                journal_date=as_of_date,
                reference_number=reference,
                description=f"Opening trial balance as at {as_of_date.isoformat()}",
                lines=journal_lines,
                source_module=SOURCE_MODULE,
                actor_id=actor_id,
            )
            posted = self._journals.post_entry(
                entry.id, firm_id=firm_id, actor_id=actor_id
            )

        record_audit(
            self._session,
            action="finance.opening_trial_balance.replaced",
            entity_type="journal_entry",
            entity_id=posted.id if posted is not None else firm_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=(
                {"journal_entry_id": str(previous.id)} if previous is not None else None
            ),
            after_data={
                "journal_entry_id": str(posted.id) if posted is not None else None,
                "as_of_date": as_of_date.isoformat(),
                "lines": len(resolved),
            },
        )
        self._session.flush()
        return self.current(firm_id)

    def _standing(self, firm_id: UUID) -> JournalEntry | None:
        """Return the posted opening journal nothing has reversed yet."""
        return self._session.scalar(
            select(JournalEntry)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.source_module == SOURCE_MODULE,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.is_deleted.is_(False),
            )
            .order_by(JournalEntry.created_at.desc())
            .limit(1)
        )

    def _next_reference(self, firm_id: UUID) -> str:
        """Return the first free OTB-n reference for the firm."""
        count = self._session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.source_module == SOURCE_MODULE,
                JournalEntry.reversal_of_id.is_(None),
            )
        )
        number = (count or 0) + 1
        while self._journals.reference_taken(
            f"{REFERENCE_PREFIX}{number}", firm_id=firm_id
        ):
            number += 1
        return f"{REFERENCE_PREFIX}{number}"

    def _resolve_lines(
        self, firm_id: UUID, lines: list[OpeningLineInput], equity_id: UUID
    ) -> list[JournalLineData]:
        """Turn account codes into journal lines, reporting every bad row."""
        codes = {line.account_code.strip() for line in lines}
        accounts = {
            account.code: account
            for account in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.code.in_(codes),
                    LedgerAccount.is_deleted.is_(False),
                )
            ).all()
        }
        closed = self._control.closed_to_hand_journals(firm_id)
        problems: list[str] = []
        seen: set[str] = set()
        resolved: list[JournalLineData] = []
        for row, line in enumerate(lines, start=1):
            code = line.account_code.strip()
            account = accounts.get(code)
            debit = quantize_ledger(quantize_money(line.debit_amount))
            credit = quantize_ledger(quantize_money(line.credit_amount))
            if account is None:
                problems.append(f"row {row}: no ledger account has code {code!r}")
                continue
            if code in seen:
                problems.append(f"row {row}: {code} appears more than once")
                continue
            seen.add(code)
            if not account.is_active:
                problems.append(f"row {row}: {code} {account.name} is inactive")
            elif account.id == equity_id:
                problems.append(
                    f"row {row}: {code} {account.name} is opening balance "
                    "equity, which takes the difference by itself"
                )
            elif account.id in closed:
                problems.append(
                    f"row {row}: {code} {account.name} is kept by its own "
                    "records -- enter customer balances on the customer, "
                    "supplier bills on the supplier and stock as opening stock"
                )
            elif (debit > ZERO) == (credit > ZERO):
                problems.append(
                    f"row {row}: {code} needs either a debit or a credit, not "
                    f"{'both' if debit > ZERO else 'neither'}"
                )
            else:
                resolved.append(
                    JournalLineData(
                        ledger_account_id=account.id,
                        debit_amount=debit,
                        credit_amount=credit,
                        description=line.description,
                    )
                )
        if problems:
            raise ValidationError(
                "The opening trial balance was not saved: " + "; ".join(problems) + "."
            )
        return resolved
