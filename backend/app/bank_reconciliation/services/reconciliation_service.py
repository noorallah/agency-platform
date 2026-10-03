"""Match a bank's statement to the books, and say what stands between them.

Decision A125 (ACC-1). The books' side of a bank account is its postings --
whatever wrote them: a receipt, a payment, a contra voucher, an expense or a
hand journal -- so matching works on ``gl_postings`` on the bank ledger and
never on one document type. Money into the bank is a debit on the account and
a deposit on the statement; money out is a credit and a withdrawal.

* **Auto-match** ties a line to a posting of the same amount whose journal is
  dated within :data:`MATCH_WINDOW_DAYS` of it. A posting whose cheque number,
  UTR or journal reference appears on the line ranks first; a line with two
  equally good candidates, or two lines wanting one posting, are left for a
  person -- a wrong match is worse than none.
* **A manual match** ties one line to one or more postings that sum to it
  exactly: one deposit slip of three cheques.
* **A reversed pair** -- an entry and the entry reversing it, both unmatched
  -- nets to nothing and the bank never saw it, so it is left out of the
  candidates and out of the reconciling items.
* **The reconciliation statement** as on a date starts from the book balance,
  takes off deposits not yet cleared, adds back payments not yet presented,
  and adds what the bank shows that the books do not have yet. A posting dated
  before the first imported statement that no line accounts for is taken as
  cleared before reconciling began -- otherwise the opening balance would sit
  as an uncleared deposit for ever.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.bank_reconciliation.models import (
    BankReconciliationMatch,
    BankStatement,
    BankStatementLine,
    StatementLineStatus,
)
from app.bank_reconciliation.schemas import (
    AutoMatchResponse,
    BankAccountRecord,
    BankReconciliationStatement,
    BankStatementLineResponse,
    BankStatementResponse,
    BookEntryResponse,
    ManualMatchRequest,
    MatchedPostingResponse,
    ReconcilingItem,
    StatementLineStatusEnum,
)
from app.common.audit.services import record_audit
from app.contra.models import ContraVoucher
from app.contra.schemas import MoneyAccountKindEnum
from app.contra.services import ContraVoucherService
from app.core.exceptions import (
    BusinessRuleError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.utils.chunks import over_chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.settlements.models import Settlement

#: How far a journal's date may sit from the bank's and still auto-match.
MATCH_WINDOW_DAYS = 3
#: A reference shorter than this is not looked for inside a narration.
MIN_REFERENCE_LENGTH = 4
ZERO = Decimal("0")

_PostingRow = tuple[
    UUID, UUID, UUID | None, date, str, str | None, str | None, Decimal, Decimal
]


def _key(value: str | None) -> str:
    """Reduce a reference to its letters and digits, upper case."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


@dataclass(frozen=True, slots=True)
class _Posting:
    """One posting on the bank account, as matching sees it."""

    id: UUID
    journal_entry_id: UUID
    reversal_of_id: UUID | None
    journal_date: date
    reference_number: str
    description: str | None
    source_module: str | None
    amount: Decimal


def _line_amount(line: BankStatementLine) -> Decimal:
    """Return a line's money into the bank: deposits positive."""
    return Decimal(line.deposit) - Decimal(line.withdrawal)


def _without_reversed_pairs(postings: Sequence[_Posting]) -> list[_Posting]:
    """Drop an entry and its reversal when both are in ``postings``."""
    journals = {posting.journal_entry_id for posting in postings}
    reversed_ids = {
        posting.reversal_of_id
        for posting in postings
        if posting.reversal_of_id in journals
    }
    return [
        posting
        for posting in postings
        if posting.journal_entry_id not in reversed_ids
        and posting.reversal_of_id not in reversed_ids
    ]


class BankReconciliationService:
    """Statements, matches and the reconciliation statement of a bank account."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    # ---- accounts ---------------------------------------------------------

    def bank_accounts(self, firm_id: UUID) -> list[BankAccountRecord]:
        """Return the firm's bank accounts, with what is left to match on each."""
        accounts = [
            account
            for account in ContraVoucherService(self._session).money_accounts(firm_id)
            if account.kind == MoneyAccountKindEnum.BANK
        ]
        unmatched: dict[UUID, int] = dict(
            self._session.execute(  # type: ignore[arg-type]
                select(BankStatementLine.ledger_account_id, func.count())
                .where(
                    BankStatementLine.firm_id == firm_id,
                    BankStatementLine.is_deleted.is_(False),
                    BankStatementLine.status == StatementLineStatus.UNMATCHED.value,
                )
                .group_by(BankStatementLine.ledger_account_id)
            ).all()
        )
        last: dict[UUID, date] = dict(
            self._session.execute(  # type: ignore[arg-type]
                select(BankStatement.ledger_account_id, func.max(BankStatement.to_date))
                .where(
                    BankStatement.firm_id == firm_id,
                    BankStatement.is_deleted.is_(False),
                )
                .group_by(BankStatement.ledger_account_id)
            ).all()
        )
        return [
            BankAccountRecord(
                id=account.id,
                code=account.code,
                name=account.name,
                unmatched_lines=int(unmatched.get(account.id, 0)),
                last_statement_date=last.get(account.id),
            )
            for account in accounts
        ]

    def bank_account(self, ledger_account_id: UUID, *, firm_id: UUID) -> LedgerAccount:
        """Return one of the firm's bank accounts, or refuse it by name."""
        account = self._session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.id == ledger_account_id,
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if account is None:
            raise ResourceNotFoundError("Ledger account not found.")
        banks = {
            row.id
            for row in ContraVoucherService(self._session).money_accounts(firm_id)
            if row.kind == MoneyAccountKindEnum.BANK
        }
        if account.id not in banks:
            raise ValidationError(
                f"{account.code} {account.name} is not a bank account. A bank "
                "statement is reconciled against the bank ledger account "
                "nominated in control accounts, or one in the same group."
            )
        return account

    # ---- statements -------------------------------------------------------

    def list_statements(
        self,
        *,
        firm_id: UUID,
        ledger_account_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BankStatementResponse], int]:
        """Return a page of imported statements, the latest first."""
        filters = [
            BankStatement.firm_id == firm_id,
            BankStatement.is_deleted.is_(False),
        ]
        if ledger_account_id is not None:
            filters.append(BankStatement.ledger_account_id == ledger_account_id)
        total = self._session.scalar(
            select(func.count()).select_from(BankStatement).where(*filters)
        )
        rows = self._session.scalars(
            select(BankStatement)
            .where(*filters)
            .order_by(
                BankStatement.to_date.desc(),
                BankStatement.created_at.desc(),
                BankStatement.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return self.statement_responses(rows), int(total or 0)

    def statement_responses(
        self, rows: Sequence[BankStatement]
    ) -> list[BankStatementResponse]:
        """Build statement responses, reading names and counts once."""
        if not rows:
            return []
        accounts = {
            account.id: account
            for account in self._session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.id.in_({row.ledger_account_id for row in rows})
                )
            ).all()
        }
        matched: dict[UUID, int] = dict(
            self._session.execute(  # type: ignore[arg-type]
                select(BankStatementLine.statement_id, func.count())
                .where(
                    BankStatementLine.statement_id.in_([row.id for row in rows]),
                    BankStatementLine.is_deleted.is_(False),
                    BankStatementLine.status == StatementLineStatus.MATCHED.value,
                )
                .group_by(BankStatementLine.statement_id)
            ).all()
        )
        return [
            BankStatementResponse(
                id=row.id,
                ledger_account_id=row.ledger_account_id,
                ledger_account_code=accounts[row.ledger_account_id].code,
                ledger_account_name=accounts[row.ledger_account_id].name,
                name=row.name,
                from_date=row.from_date,
                to_date=row.to_date,
                line_count=row.line_count,
                matched_count=int(matched.get(row.id, 0)),
                created_at=row.created_at,
                version=row.version,
            )
            for row in rows
        ]

    def delete_statement(
        self, statement_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Take a statement off, with its lines and every match they made.

        The postings its lines cleared go back to uncleared; the books
        themselves are not touched, since matching never wrote to them.
        """
        statement = self._session.scalar(
            select(BankStatement).where(
                BankStatement.id == statement_id,
                BankStatement.firm_id == firm_id,
                BankStatement.is_deleted.is_(False),
            )
        )
        if statement is None:
            raise ResourceNotFoundError("Bank statement not found.")
        lines = self._session.scalars(
            select(BankStatementLine).where(
                BankStatementLine.statement_id == statement.id,
                BankStatementLine.is_deleted.is_(False),
            )
        ).all()
        now = utc_now()
        matches = self._live_matches([line.id for line in lines])
        for row in [*matches, *lines, statement]:
            row.is_deleted = True
            row.deleted_at = now
            row.deleted_by = actor_id
            row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="bank_statement.deleted",
            entity_type="bank_statement",
            entity_id=statement.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={
                "name": statement.name,
                "ledger_account_id": str(statement.ledger_account_id),
                "from_date": statement.from_date.isoformat(),
                "to_date": statement.to_date.isoformat(),
                "line_count": statement.line_count,
                "matches_removed": len(matches),
            },
            after_data=None,
        )
        self._session.commit()

    # ---- lines ------------------------------------------------------------

    def list_lines(
        self,
        *,
        firm_id: UUID,
        ledger_account_id: UUID | None,
        statement_id: UUID | None,
        status: StatementLineStatusEnum | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BankStatementLineResponse], int]:
        """Return a page of statement lines in the bank's order."""
        filters = [
            BankStatementLine.firm_id == firm_id,
            BankStatementLine.is_deleted.is_(False),
        ]
        if ledger_account_id is not None:
            filters.append(BankStatementLine.ledger_account_id == ledger_account_id)
        if statement_id is not None:
            filters.append(BankStatementLine.statement_id == statement_id)
        if status is not None:
            filters.append(BankStatementLine.status == status.value)
        if date_from is not None:
            filters.append(BankStatementLine.line_date >= date_from)
        if date_to is not None:
            filters.append(BankStatementLine.line_date <= date_to)
        total = self._session.scalar(
            select(func.count()).select_from(BankStatementLine).where(*filters)
        )
        rows = self._session.scalars(
            select(BankStatementLine)
            .where(*filters)
            .order_by(
                BankStatementLine.line_date.asc(),
                BankStatementLine.statement_id.asc(),
                BankStatementLine.line_number.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return self.line_responses(rows), int(total or 0)

    def line_responses(
        self, rows: Sequence[BankStatementLine]
    ) -> list[BankStatementLineResponse]:
        """Build line responses, reading every line's matches in one go."""
        matches: dict[UUID, list[MatchedPostingResponse]] = {}
        if rows:
            for match, posting, entry in self._session.execute(
                select(BankReconciliationMatch, GLPosting, JournalEntry)
                .join(GLPosting, GLPosting.id == BankReconciliationMatch.gl_posting_id)
                .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
                .where(
                    BankReconciliationMatch.statement_line_id.in_(
                        [row.id for row in rows]
                    ),
                    BankReconciliationMatch.is_deleted.is_(False),
                )
                .order_by(JournalEntry.journal_date, JournalEntry.reference_number)
            ).all():
                matches.setdefault(match.statement_line_id, []).append(
                    MatchedPostingResponse(
                        match_id=match.id,
                        gl_posting_id=posting.id,
                        journal_entry_id=entry.id,
                        journal_date=entry.journal_date,
                        reference_number=entry.reference_number,
                        description=entry.description,
                        amount=Decimal(posting.debit_amount)
                        - Decimal(posting.credit_amount),
                        matched_how=match.matched_how,
                    )
                )
        return [
            BankStatementLineResponse(
                id=row.id,
                statement_id=row.statement_id,
                line_number=row.line_number,
                line_date=row.line_date,
                description=row.description,
                reference=row.reference,
                withdrawal=row.withdrawal,
                deposit=row.deposit,
                balance=row.balance,
                status=StatementLineStatusEnum(row.status),
                matches=matches.get(row.id, []),
            )
            for row in rows
        ]

    # ---- the books' side --------------------------------------------------

    def book_entries(
        self,
        *,
        firm_id: UUID,
        ledger_account_id: UUID,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BookEntryResponse], int]:
        """Return a page of the account's postings no line accounts for yet."""
        self.bank_account(ledger_account_id, firm_id=firm_id)
        postings = _without_reversed_pairs(
            self._unmatched_postings(
                firm_id, ledger_account_id, date_from=date_from, date_to=date_to
            )
        )
        window = postings[(page - 1) * page_size : page * page_size]
        instruments = self._instrument_references(
            [posting.journal_entry_id for posting in window]
        )
        return [
            BookEntryResponse(
                gl_posting_id=posting.id,
                journal_entry_id=posting.journal_entry_id,
                journal_date=posting.journal_date,
                reference_number=posting.reference_number,
                instrument_reference=instruments.get(posting.journal_entry_id),
                description=posting.description,
                source_module=posting.source_module,
                amount=posting.amount,
            )
            for posting in window
        ], len(postings)

    def _postings_query(
        self, firm_id: UUID, ledger_account_id: UUID
    ) -> Select[_PostingRow]:
        """Select the account's postings with their journal's facts."""
        return (
            select(
                GLPosting.id,
                GLPosting.journal_entry_id,
                JournalEntry.reversal_of_id,
                JournalEntry.journal_date,
                JournalEntry.reference_number,
                JournalEntry.description,
                JournalEntry.source_module,
                GLPosting.debit_amount,
                GLPosting.credit_amount,
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(
                GLPosting.firm_id == firm_id,
                GLPosting.ledger_account_id == ledger_account_id,
                GLPosting.is_deleted.is_(False),
            )
        )

    @staticmethod
    def _posting(row: Iterable[object]) -> _Posting:
        """Build a posting from one row of :meth:`_postings_query`."""
        (
            posting_id,
            journal_id,
            reversal_of_id,
            journal_date,
            reference,
            description,
            source,
            debit,
            credit,
        ) = tuple(row)
        return _Posting(
            id=posting_id,  # type: ignore[arg-type]
            journal_entry_id=journal_id,  # type: ignore[arg-type]
            reversal_of_id=reversal_of_id,  # type: ignore[arg-type]
            journal_date=journal_date,  # type: ignore[arg-type]
            reference_number=reference,  # type: ignore[arg-type]
            description=description,  # type: ignore[arg-type]
            source_module=source,  # type: ignore[arg-type]
            amount=Decimal(str(debit)) - Decimal(str(credit)),
        )

    def _unmatched_postings(
        self,
        firm_id: UUID,
        ledger_account_id: UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[_Posting]:
        """Return the account's postings no live match holds, oldest first."""
        matched = (
            select(BankReconciliationMatch.id)
            .where(
                BankReconciliationMatch.gl_posting_id == GLPosting.id,
                BankReconciliationMatch.is_deleted.is_(False),
            )
            .exists()
        )
        query = self._postings_query(firm_id, ledger_account_id).where(~matched)
        if date_from is not None:
            query = query.where(JournalEntry.journal_date >= date_from)
        if date_to is not None:
            query = query.where(JournalEntry.journal_date <= date_to)
        query = query.order_by(
            JournalEntry.journal_date.asc(), JournalEntry.reference_number.asc()
        )
        return [self._posting(row) for row in self._session.execute(query).all()]

    @over_chunks("journal_ids")
    def _instrument_references(self, journal_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Return the cheque number or UTR each journal's document recorded."""
        if not journal_ids:
            return {}
        found: dict[UUID, str] = {}
        for journal_id, reference in self._session.execute(
            select(ContraVoucher.journal_entry_id, ContraVoucher.reference).where(
                ContraVoucher.journal_entry_id.in_(journal_ids),
                ContraVoucher.reference.is_not(None),
            )
        ).all():
            found[journal_id] = reference
        for journal_id, reference in self._session.execute(
            select(Settlement.journal_entry_id, Settlement.instrument_reference).where(
                Settlement.journal_entry_id.in_(journal_ids),
                Settlement.instrument_reference.is_not(None),
            )
        ).all():
            found[journal_id] = reference
        return found

    # ---- matching ---------------------------------------------------------

    def auto_match(
        self,
        *,
        firm_id: UUID,
        actor_id: UUID,
        ledger_account_id: UUID,
        statement_id: UUID | None,
    ) -> AutoMatchResponse:
        """Match every line that has exactly one good posting."""
        self.bank_account(ledger_account_id, firm_id=firm_id)
        filters = [
            BankStatementLine.firm_id == firm_id,
            BankStatementLine.ledger_account_id == ledger_account_id,
            BankStatementLine.is_deleted.is_(False),
            BankStatementLine.status == StatementLineStatus.UNMATCHED.value,
        ]
        if statement_id is not None:
            filters.append(BankStatementLine.statement_id == statement_id)
        lines = self._session.scalars(
            select(BankStatementLine)
            .where(*filters)
            .order_by(BankStatementLine.line_date, BankStatementLine.line_number)
        ).all()
        if not lines:
            return AutoMatchResponse(matched=0, left_unmatched=0)
        window = timedelta(days=MATCH_WINDOW_DAYS)
        postings = _without_reversed_pairs(
            self._unmatched_postings(
                firm_id,
                ledger_account_id,
                date_from=min(line.line_date for line in lines) - window,
                date_to=max(line.line_date for line in lines) + window,
            )
        )
        by_amount: dict[Decimal, list[_Posting]] = {}
        for posting in postings:
            by_amount.setdefault(posting.amount, []).append(posting)
        instruments = self._instrument_references(
            [posting.journal_entry_id for posting in postings]
        )
        chosen: dict[UUID, _Posting] = {}
        for line in lines:
            candidates = [
                posting
                for posting in by_amount.get(_line_amount(line), [])
                if abs((posting.journal_date - line.line_date).days)
                <= MATCH_WINDOW_DAYS
            ]
            pick = self._pick(line, candidates, instruments)
            if pick is not None:
                chosen[line.id] = pick
        wanted = Counter(posting.id for posting in chosen.values())
        matched_lines: list[str] = []
        for line in lines:
            pick = chosen.get(line.id)
            if pick is None or wanted[pick.id] > 1:
                continue
            self._add_match(
                line, pick.id, firm_id=firm_id, actor_id=actor_id, how="AUTO"
            )
            matched_lines.append(str(line.id))
        if matched_lines:
            self._session.flush()
            record_audit(
                self._session,
                action="bank_reconciliation.auto_matched",
                entity_type="ledger_account",
                entity_id=ledger_account_id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=None,
                after_data={"statement_line_ids": matched_lines},
            )
        self._session.commit()
        return AutoMatchResponse(
            matched=len(matched_lines), left_unmatched=len(lines) - len(matched_lines)
        )

    @staticmethod
    def _pick(
        line: BankStatementLine,
        candidates: Sequence[_Posting],
        instruments: dict[UUID, str],
    ) -> _Posting | None:
        """Return the one posting a line should take, or None when unsure."""
        reference = _key(line.reference)
        narration = _key(line.description)

        def named(posting: _Posting) -> bool:
            """Say whether the line names the posting's reference."""
            for value in (
                instruments.get(posting.journal_entry_id),
                posting.reference_number,
            ):
                wanted = _key(value)
                if not wanted:
                    continue
                if wanted == reference:
                    return True
                if len(wanted) >= MIN_REFERENCE_LENGTH and (
                    wanted in narration or (reference and wanted in reference)
                ):
                    return True
            return False

        referenced = [posting for posting in candidates if named(posting)]
        if len(referenced) == 1:
            return referenced[0]
        if not referenced and len(candidates) == 1:
            return candidates[0]
        return None

    def match(
        self, request: ManualMatchRequest, *, firm_id: UUID, actor_id: UUID
    ) -> BankStatementLineResponse:
        """Tie one line to the postings it accounts for; they must sum to it."""
        line = self._line(request.statement_line_id, firm_id=firm_id)
        if line.status == StatementLineStatus.MATCHED.value:
            raise BusinessRuleError(
                f"Line {line.line_number} of {line.line_date.isoformat()} is "
                "already matched. Unmatch it first."
            )
        wanted = list(dict.fromkeys(request.gl_posting_ids))
        rows = [
            self._posting(row)
            for row in self._session.execute(
                self._postings_query(firm_id, line.ledger_account_id).where(
                    GLPosting.id.in_(wanted)
                )
            ).all()
        ]
        if len(rows) != len(wanted):
            raise ValidationError(
                "One or more of the chosen entries is not on this bank account."
            )
        taken = self._session.scalars(
            select(BankReconciliationMatch.gl_posting_id).where(
                BankReconciliationMatch.gl_posting_id.in_(wanted),
                BankReconciliationMatch.is_deleted.is_(False),
            )
        ).all()
        if taken:
            names = sorted(row.reference_number for row in rows if row.id in taken)
            raise BusinessRuleError(
                f"{', '.join(names)} already cleared against another line."
            )
        total = sum((row.amount for row in rows), ZERO)
        if total != _line_amount(line):
            raise ValidationError(
                f"The chosen entries come to {total:,.2f}; the line is "
                f"{_line_amount(line):,.2f}. They must add up to it exactly."
            )
        for row in rows:
            self._add_match(
                line, row.id, firm_id=firm_id, actor_id=actor_id, how="MANUAL"
            )
        self._session.flush()
        record_audit(
            self._session,
            action="bank_reconciliation.matched",
            entity_type="bank_statement_line",
            entity_id=line.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=None,
            after_data={"gl_posting_ids": [str(row.id) for row in rows]},
        )
        self._session.commit()
        return self.line_responses([line])[0]

    def unmatch(
        self, statement_line_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> BankStatementLineResponse:
        """Undo a line's match; its postings go back to uncleared."""
        line = self._line(statement_line_id, firm_id=firm_id)
        matches = self._live_matches([line.id])
        if not matches:
            raise BusinessRuleError("This line is not matched.")
        now = utc_now()
        for match in matches:
            match.is_deleted = True
            match.deleted_at = now
            match.deleted_by = actor_id
            match.updated_by = actor_id
        line.status = StatementLineStatus.UNMATCHED.value
        line.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="bank_reconciliation.unmatched",
            entity_type="bank_statement_line",
            entity_id=line.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"gl_posting_ids": [str(m.gl_posting_id) for m in matches]},
            after_data=None,
        )
        self._session.commit()
        return self.line_responses([line])[0]

    def _line(self, line_id: UUID, *, firm_id: UUID) -> BankStatementLine:
        """Return a live statement line of the firm, or raise."""
        line = self._session.scalar(
            select(BankStatementLine).where(
                BankStatementLine.id == line_id,
                BankStatementLine.firm_id == firm_id,
                BankStatementLine.is_deleted.is_(False),
            )
        )
        if line is None:
            raise ResourceNotFoundError("Bank statement line not found.")
        return line

    def _live_matches(self, line_ids: Sequence[UUID]) -> list[BankReconciliationMatch]:
        """Return the live matches of the given lines."""
        if not line_ids:
            return []
        return list(
            self._session.scalars(
                select(BankReconciliationMatch).where(
                    BankReconciliationMatch.statement_line_id.in_(line_ids),
                    BankReconciliationMatch.is_deleted.is_(False),
                )
            ).all()
        )

    def _add_match(
        self,
        line: BankStatementLine,
        gl_posting_id: UUID,
        *,
        firm_id: UUID,
        actor_id: UUID,
        how: str,
    ) -> None:
        """Record that a line clears a posting, on the line's date."""
        self._session.add(
            BankReconciliationMatch(
                firm_id=firm_id,
                statement_line_id=line.id,
                gl_posting_id=gl_posting_id,
                cleared_on=line.line_date,
                matched_how=how,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        line.status = StatementLineStatus.MATCHED.value
        line.updated_by = actor_id

    # ---- the reconciliation statement -------------------------------------

    def reconciliation_statement(
        self, *, firm_id: UUID, ledger_account_id: UUID, as_on: date
    ) -> BankReconciliationStatement:
        """Return the bank reconciliation statement as on a date."""
        account = self.bank_account(ledger_account_id, firm_id=firm_id)
        book_balance = ContraVoucherService(self._session).balance_on(
            account.id, firm_id=firm_id, on=as_on
        )
        started = self._session.scalar(
            select(func.min(BankStatement.from_date)).where(
                BankStatement.firm_id == firm_id,
                BankStatement.ledger_account_id == account.id,
                BankStatement.is_deleted.is_(False),
            )
        )
        cleared = (
            select(BankReconciliationMatch.id)
            .where(
                BankReconciliationMatch.gl_posting_id == GLPosting.id,
                BankReconciliationMatch.is_deleted.is_(False),
                BankReconciliationMatch.cleared_on <= as_on,
            )
            .exists()
        )
        matched_at_all = (
            select(BankReconciliationMatch.id)
            .where(
                BankReconciliationMatch.gl_posting_id == GLPosting.id,
                BankReconciliationMatch.is_deleted.is_(False),
            )
            .exists()
        )
        query = self._postings_query(firm_id, account.id).where(
            JournalEntry.journal_date <= as_on, ~cleared
        )
        if started is not None:
            # Before the first statement, only what a line accounts for is
            # outstanding; the rest cleared before reconciling began.
            query = query.where((JournalEntry.journal_date >= started) | matched_at_all)
        outstanding = _without_reversed_pairs(
            [
                self._posting(row)
                for row in self._session.execute(
                    query.order_by(
                        JournalEntry.journal_date, JournalEntry.reference_number
                    )
                ).all()
            ]
        )
        instruments = self._instrument_references(
            [posting.journal_entry_id for posting in outstanding]
        )
        deposits: list[ReconcilingItem] = []
        payments: list[ReconcilingItem] = []
        for posting in outstanding:
            if posting.amount == ZERO:
                continue
            item = ReconcilingItem(
                on=posting.journal_date,
                reference=instruments.get(posting.journal_entry_id)
                or posting.reference_number,
                description=posting.description,
                amount=posting.amount,
                gl_posting_id=posting.id,
            )
            (deposits if posting.amount > ZERO else payments).append(item)
        bank_only = self._bank_only(firm_id, account.id, as_on)
        deposits_total = sum((item.amount for item in deposits), ZERO)
        payments_total = -sum((item.amount for item in payments), ZERO)
        bank_only_net = sum((item.amount for item in bank_only), ZERO)
        per_books = quantize_ledger(
            book_balance - deposits_total + payments_total + bank_only_net
        )
        printed = self._session.scalar(
            select(BankStatementLine.balance)
            .join(BankStatement, BankStatement.id == BankStatementLine.statement_id)
            .where(
                BankStatementLine.firm_id == firm_id,
                BankStatementLine.ledger_account_id == account.id,
                BankStatementLine.is_deleted.is_(False),
                BankStatementLine.balance.is_not(None),
                BankStatementLine.line_date <= as_on,
            )
            .order_by(
                BankStatementLine.line_date.desc(),
                BankStatement.to_date.desc(),
                BankStatement.created_at.desc(),
                BankStatementLine.line_number.desc(),
                BankStatementLine.id.desc(),
            )
            .limit(1)
        )
        statement_balance = None if printed is None else Decimal(printed)
        return BankReconciliationStatement(
            ledger_account_id=account.id,
            ledger_account_code=account.code,
            ledger_account_name=account.name,
            as_on=as_on,
            reconciled_from=started,
            book_balance=book_balance,
            deposits_not_cleared=deposits,
            deposits_not_cleared_total=quantize_ledger(deposits_total),
            payments_not_presented=payments,
            payments_not_presented_total=quantize_ledger(payments_total),
            bank_only=bank_only,
            bank_only_net=quantize_ledger(bank_only_net),
            bank_balance_per_books=per_books,
            statement_balance=statement_balance,
            difference=(
                None
                if statement_balance is None
                else quantize_ledger(statement_balance - per_books)
            ),
        )

    def _bank_only(
        self, firm_id: UUID, ledger_account_id: UUID, as_on: date
    ) -> list[ReconcilingItem]:
        """Return what the bank shows by the date that the books do not yet.

        An unmatched line, and a matched line's posting dated after the date
        -- bank charges the books took up a few days later.
        """
        items = [
            ReconcilingItem(
                on=line.line_date,
                reference=line.reference,
                description=line.description,
                amount=_line_amount(line),
                statement_line_id=line.id,
            )
            for line in self._session.scalars(
                select(BankStatementLine)
                .where(
                    BankStatementLine.firm_id == firm_id,
                    BankStatementLine.ledger_account_id == ledger_account_id,
                    BankStatementLine.is_deleted.is_(False),
                    BankStatementLine.status == StatementLineStatus.UNMATCHED.value,
                    BankStatementLine.line_date <= as_on,
                )
                .order_by(BankStatementLine.line_date, BankStatementLine.line_number)
            ).all()
        ]
        for line, entry, debit, credit in self._session.execute(
            select(
                BankStatementLine,
                JournalEntry,
                GLPosting.debit_amount,
                GLPosting.credit_amount,
            )
            .join(
                BankReconciliationMatch,
                BankReconciliationMatch.statement_line_id == BankStatementLine.id,
            )
            .join(GLPosting, GLPosting.id == BankReconciliationMatch.gl_posting_id)
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(
                BankStatementLine.firm_id == firm_id,
                BankStatementLine.ledger_account_id == ledger_account_id,
                BankStatementLine.is_deleted.is_(False),
                BankReconciliationMatch.is_deleted.is_(False),
                BankReconciliationMatch.cleared_on <= as_on,
                JournalEntry.journal_date > as_on,
            )
            .order_by(BankStatementLine.line_date, BankStatementLine.line_number)
        ).all():
            items.append(
                ReconcilingItem(
                    on=line.line_date,
                    reference=line.reference,
                    description=(
                        f"{line.description or ''} -- in the books on "
                        f"{entry.journal_date.isoformat()} ({entry.reference_number})"
                    ).strip(" -"),
                    amount=Decimal(debit) - Decimal(credit),
                    statement_line_id=line.id,
                )
            )
        return items
