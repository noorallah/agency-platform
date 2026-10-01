"""The day book, the cash book and the bank book (backlog 55 M9).

Tally's three registers of what happened, read straight from the ledger and
storing nothing:

* **Day book** -- every journal in the books over the dates, in date order:
  the voucher (the document's own number, which is what a posting journal is
  referenced by), what raised it, the narration and its two totals. Drafts
  and rejected journals never reached the books and are left out; a reversed
  journal and the mirror that reversed it both stay, because both happened.
* **Cash book / bank book** -- every posting to the firm's Cash (or Bank)
  account, with the balance it opened the dates at, the balance after each
  posting and the balance it closed at. The account is the one the control
  accounts map to CASH (or BANK); where that account sits in an account group
  of its own -- one no other control purpose maps into -- every asset account
  in the group belongs to the book too, so a firm that opened "SBI Current"
  beside "Bank" under a *Bank accounts* group reads both in one book. The
  seeded chart files Cash and Bank under Current Assets beside receivables
  and stock, so there the book is the mapped account alone.

**The running balance is computed in date order in SQL**, by a window sum over
the postings ordered by journal date, voucher and posting -- never read off a
stored balance, which is a snapshot in the order things were recorded. A page
of a long book therefore carries the right balance on its first row without
reading the rows before it. The opening and closing balances are rows of the
book (``row_type`` OPENING and CLOSING) so the paged grid shows them where a
reader expects them: first and last.

Every row names its journal (``journal_entry_id``) so the screen can open it,
and the document behind it (``source_module``, ``source_id``) where a
document raised it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ValidationError
from app.core.pagination.reports import ReportRows, ReportWindow
from app.core.utils.chunks import over_chunks
from app.finance.models import (
    AccountType,
    GLPosting,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
    VoucherType,
)
from app.finance.services.control_accounts import (
    PURPOSE_LABELS,
    ControlAccountPurpose,
    ControlAccountService,
)

ZERO = Decimal("0.00")

#: The journals that are in the books. A draft has not been posted and a
#: rejected one never will be.
IN_THE_BOOKS = (JournalStatus.POSTED.value, JournalStatus.REVERSED.value)


def source_label(source_module: str | None) -> str:
    """Name what raised a journal: ``sales_invoice`` reads *Sales invoice*."""
    if not source_module:
        return "Journal"
    spaced = source_module.replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:]


@dataclass(frozen=True)
class DayBookRow:
    """One journal of the day book."""

    journal_entry_id: UUID
    journal_date: date
    voucher: str
    voucher_type: str
    source: str
    source_module: str | None
    source_id: UUID | None
    narration: str | None
    debit: Decimal
    credit: Decimal
    status: str


@dataclass(frozen=True)
class MoneyBookRow:
    """One line of a cash or bank book, or its opening or closing balance."""

    row_type: str
    date: date | None
    voucher: str
    source: str
    particulars: str
    account: str
    narration: str | None
    receipt: Decimal | None
    payment: Decimal | None
    balance: Decimal
    journal_entry_id: UUID | None = None
    source_module: str | None = None
    source_id: UUID | None = None


class BooksRegisterService:
    """Read the day book and the cash and bank books for a firm."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    # ------------------------------------------------------------------
    # Day book
    # ------------------------------------------------------------------

    def day_book(self, firm_id: UUID, window: ReportWindow) -> list[DayBookRow]:
        """Return every journal in the books over the window, in date order.

        One row per journal with its totals, paged in SQL: a day book is the
        list of vouchers, and each opens to its lines.
        """
        statement = (
            select(
                JournalEntry.id,
                JournalEntry.journal_date,
                JournalEntry.reference_number,
                VoucherType.name,
                JournalEntry.source_module,
                JournalEntry.source_id,
                JournalEntry.description,
                JournalEntry.total_debit,
                JournalEntry.total_credit,
                JournalEntry.status,
            )
            .outerjoin(VoucherType, VoucherType.id == JournalEntry.voucher_type_id)
            .where(
                JournalEntry.firm_id == firm_id,
                JournalEntry.is_deleted.is_(False),
                JournalEntry.status.in_(IN_THE_BOOKS),
                *window.dated(JournalEntry.journal_date),
            )
            .order_by(
                JournalEntry.journal_date.asc(),
                JournalEntry.reference_number.asc(),
                JournalEntry.id.asc(),
            )
        )
        rows, total = self._page(statement, window)
        records = [
            DayBookRow(
                journal_entry_id=entry_id,
                journal_date=on,
                voucher=reference,
                voucher_type=voucher_type or "",
                source=source_label(module),
                source_module=module,
                source_id=source_id,
                narration=description,
                debit=debit,
                credit=credit,
                status=status,
            )
            for (
                entry_id,
                on,
                reference,
                voucher_type,
                module,
                source_id,
                description,
                debit,
                credit,
                status,
            ) in rows
        ]
        return ReportRows(records, total_records=total)

    # ------------------------------------------------------------------
    # Cash and bank books
    # ------------------------------------------------------------------

    def money_book(
        self,
        firm_id: UUID,
        purpose: ControlAccountPurpose,
        window: ReportWindow,
    ) -> list[MoneyBookRow]:
        """Return the cash (or bank) book over the window.

        The opening balance is every posting to the book's accounts dated
        before ``from_date``; the closing is the opening plus everything in
        the window. Both are rows, first and last, and a page asks SQL only
        for the postings it shows.

        Raises:
            ValidationError: If no account is mapped to the purpose, naming
                where to map it.

        """
        accounts = self.money_accounts(firm_id, purpose)
        names = dict(
            self._session.execute(
                select(LedgerAccount.id, LedgerAccount.name).where(
                    LedgerAccount.id.in_(accounts)
                )
            )
            .tuples()
            .all()
        )
        live = (
            GLPosting.firm_id == firm_id,
            GLPosting.ledger_account_id.in_(accounts),
            GLPosting.is_deleted.is_(False),
            JournalEntry.is_deleted.is_(False),
        )
        opening = ZERO
        if window.from_date is not None:
            opening += self._net(
                and_(*live, JournalEntry.journal_date < window.from_date)
            )
        in_window = and_(*live, *window.dated(JournalEntry.journal_date))
        count, movement = self._session.execute(
            select(
                func.count(GLPosting.id),
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                ),
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(in_window)
        ).one()
        entries = int(count or 0)
        closing = opening + Decimal(str(movement or 0))

        # The page over [opening] + postings + [closing].
        if window.page is None:
            start, size = 0, entries + 2
        else:
            start, size = (window.page - 1) * window.page_size, window.page_size
        end = start + size
        first_entry = max(start, 1) - 1
        last_entry = min(end, entries + 1) - 1
        take = max(last_entry - first_entry, 0)

        order = (
            JournalEntry.journal_date.asc(),
            JournalEntry.reference_number.asc(),
            GLPosting.id.asc(),
        )
        running = func.sum(GLPosting.debit_amount - GLPosting.credit_amount).over(
            order_by=order, rows=(None, 0)
        )
        postings: list[Any] = []
        if take:
            ranked = (
                select(
                    JournalEntry.id.label("entry_id"),
                    JournalEntry.journal_date.label("on"),
                    JournalEntry.reference_number.label("voucher"),
                    JournalEntry.source_module.label("module"),
                    JournalEntry.source_id.label("source_id"),
                    JournalEntry.description.label("entry_description"),
                    JournalLine.description.label("line_description"),
                    GLPosting.ledger_account_id.label("account_id"),
                    GLPosting.debit_amount.label("debit"),
                    GLPosting.credit_amount.label("credit"),
                    running.label("running"),
                    func.row_number().over(order_by=order).label("position"),
                )
                .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
                .join(JournalLine, JournalLine.id == GLPosting.journal_line_id)
                .where(in_window)
                .subquery()
            )
            postings = list(
                self._session.execute(
                    select(ranked)
                    .order_by(ranked.c.position)
                    .offset(first_entry)
                    .limit(take)
                ).all()
            )
        contra = _contra_accounts(
            self._session,
            journal_ids=[row.entry_id for row in postings],
            book_accounts=set(accounts),
        )

        rows: list[MoneyBookRow] = []
        if start == 0:
            rows.append(
                MoneyBookRow(
                    row_type="OPENING",
                    date=window.from_date,
                    voucher="",
                    source="",
                    particulars="Opening balance",
                    account="",
                    narration=None,
                    receipt=None,
                    payment=None,
                    balance=opening,
                )
            )
        for row in postings:
            rows.append(
                MoneyBookRow(
                    row_type="ENTRY",
                    date=row.on,
                    voucher=row.voucher,
                    source=source_label(row.module),
                    particulars=contra.get(row.entry_id, ""),
                    account=names.get(row.account_id, ""),
                    narration=row.line_description or row.entry_description,
                    receipt=row.debit,
                    payment=row.credit,
                    balance=opening + Decimal(str(row.running)),
                    journal_entry_id=row.entry_id,
                    source_module=row.module,
                    source_id=row.source_id,
                )
            )
        if start <= entries + 1 < end:
            rows.append(
                MoneyBookRow(
                    row_type="CLOSING",
                    date=window.to_date,
                    voucher="",
                    source="",
                    particulars="Closing balance",
                    account="",
                    narration=None,
                    receipt=None,
                    payment=None,
                    balance=closing,
                )
            )
        return ReportRows(rows, total_records=entries + 2)

    def money_accounts(
        self, firm_id: UUID, purpose: ControlAccountPurpose
    ) -> list[UUID]:
        """Return the accounts a cash or bank book reads.

        The account mapped to the purpose, and -- where its account group is
        its own, holding no account another purpose maps to -- every other
        live asset account in that group.

        Raises:
            ValidationError: If nothing is mapped to the purpose.

        """
        mapping = ControlAccountService(self._session).mapping(firm_id)
        mapped = mapping.get(purpose.value)
        if mapped is None:
            label = PURPOSE_LABELS.get(purpose, purpose.value)
            raise ValidationError(
                f"No account is mapped to {label}; map one under Control "
                "Accounts to read this book."
            )
        group_id = self._session.scalar(
            select(LedgerAccount.account_group_id).where(LedgerAccount.id == mapped)
        )
        siblings = list(
            self._session.execute(
                select(LedgerAccount.id, LedgerAccount.account_type).where(
                    LedgerAccount.firm_id == firm_id,
                    LedgerAccount.account_group_id == group_id,
                    LedgerAccount.is_deleted.is_(False),
                    LedgerAccount.id != mapped,
                )
            ).all()
        )
        others_mapped = {
            account_id
            for key, account_id in mapping.items()
            if key != purpose.value and account_id != mapped
        }
        if any(account_id in others_mapped for account_id, _ in siblings):
            return [mapped]
        return [mapped] + [
            account_id
            for account_id, account_type in siblings
            if account_type == AccountType.ASSET.value
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _net(self, condition: ColumnElement[bool]) -> Decimal:
        """Return debits less credits of the postings matching ``condition``."""
        value = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0
                )
            )
            .join(JournalEntry, JournalEntry.id == GLPosting.journal_entry_id)
            .where(condition)
        )
        return Decimal(str(value or 0)) + ZERO

    def _page(
        self, statement: Select[Any], window: ReportWindow
    ) -> tuple[list[Any], int]:
        """Read one page of ``statement``'s rows and how many there are."""
        if window.page is None:
            rows = list(self._session.execute(statement).all())
            return rows, len(rows)
        total = self._session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = list(
            self._session.execute(
                statement.offset((window.page - 1) * window.page_size).limit(
                    window.page_size
                )
            ).all()
        )
        return rows, int(total or 0)


@over_chunks("journal_ids")
def _contra_accounts(
    session: Session, *, journal_ids: list[UUID], book_accounts: set[UUID]
) -> dict[UUID, str]:
    """Name the other side of each journal -- Tally's *Particulars*.

    The account on the journal's other lines with the largest amount, and how
    many more there are when it has several: a receipt reads *Trade
    receivables*, a sale paid in cash *Sales (+1 more)* for the tax line.
    """
    if not journal_ids:
        return {}
    amounts: dict[UUID, dict[str, Decimal]] = {}
    for journal_id, account_id, name, amount in session.execute(
        select(
            JournalLine.journal_entry_id,
            JournalLine.ledger_account_id,
            LedgerAccount.name,
            func.sum(JournalLine.debit_amount + JournalLine.credit_amount),
        )
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(
            JournalLine.journal_entry_id.in_(journal_ids),
            JournalLine.is_deleted.is_(False),
        )
        .group_by(
            JournalLine.journal_entry_id,
            JournalLine.ledger_account_id,
            LedgerAccount.name,
        )
    ).all():
        if account_id in book_accounts:
            continue
        per = amounts.setdefault(journal_id, {})
        per[name] = per.get(name, ZERO) + Decimal(str(amount or 0))
    named: dict[UUID, str] = {}
    for journal_id, per in amounts.items():
        biggest = max(per.items(), key=lambda item: (item[1], item[0]))[0]
        more = len(per) - 1
        named[journal_id] = f"{biggest} (+{more} more)" if more else biggest
    return named
