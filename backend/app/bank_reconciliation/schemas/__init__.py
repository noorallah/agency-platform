"""Wire shapes for bank statements and their reconciliation (ACC-1)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BankReconciliationSchema(BaseModel):
    """Base for every bank reconciliation schema: unknown fields refused."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class StatementLineStatusEnum(StrEnum):
    """Whether the books account for a statement line yet."""

    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"


class BankAccountRecord(BankReconciliationSchema):
    """One bank ledger account a statement can be imported against."""

    id: UUID
    code: str
    name: str
    unmatched_lines: int
    last_statement_date: date | None


class BankStatementResponse(BankReconciliationSchema):
    """One imported statement."""

    id: UUID
    ledger_account_id: UUID
    ledger_account_code: str
    ledger_account_name: str
    name: str
    from_date: date
    to_date: date
    line_count: int
    matched_count: int
    created_at: datetime
    version: int


class MatchedPostingResponse(BankReconciliationSchema):
    """One posting a statement line accounts for."""

    match_id: UUID
    gl_posting_id: UUID
    journal_entry_id: UUID
    journal_date: date
    reference_number: str
    description: str | None
    #: Money into the bank is positive, money out negative.
    amount: Decimal
    matched_how: str


class BankStatementLineResponse(BankReconciliationSchema):
    """One statement line and what it was matched to."""

    id: UUID
    statement_id: UUID
    line_number: int
    line_date: date
    description: str | None
    reference: str | None
    withdrawal: Decimal
    deposit: Decimal
    balance: Decimal | None
    status: StatementLineStatusEnum
    matches: list[MatchedPostingResponse]


class BookEntryResponse(BankReconciliationSchema):
    """One posting on the bank account the bank has not yet shown."""

    gl_posting_id: UUID
    journal_entry_id: UUID
    journal_date: date
    reference_number: str
    #: The cheque number or UTR the receipt, payment or contra recorded.
    instrument_reference: str | None
    description: str | None
    source_module: str | None
    #: Money into the bank is positive, money out negative.
    amount: Decimal


class ManualMatchRequest(BankReconciliationSchema):
    """Tie one statement line to the postings it accounts for."""

    statement_line_id: UUID
    gl_posting_ids: list[UUID] = Field(min_length=1, max_length=200)


class AutoMatchRequest(BankReconciliationSchema):
    """Match what can be matched unambiguously on one bank account."""

    ledger_account_id: UUID
    #: Only lines of this statement; every unmatched line when left out.
    statement_id: UUID | None = None


class AutoMatchResponse(BankReconciliationSchema):
    """What the matcher did."""

    matched: int
    #: Lines it looked at and could not match, or not unambiguously.
    left_unmatched: int


class ReconcilingItem(BankReconciliationSchema):
    """One item between the books and the bank on the date."""

    on: date
    reference: str | None
    description: str | None
    #: Money into the bank is positive, money out negative.
    amount: Decimal
    gl_posting_id: UUID | None = None
    statement_line_id: UUID | None = None


class BankReconciliationStatement(BankReconciliationSchema):
    """The bank reconciliation statement as on one date.

    ``bank_balance_per_books`` = ``book_balance`` - ``deposits_not_cleared``
    + ``payments_not_presented`` + ``bank_only_net``: the balance the bank
    should show if every item named here is all that stands between the two.
    ``difference`` is the balance the statement printed, where one was
    printed on or before the date, less that figure; zero means reconciled.
    """

    ledger_account_id: UUID
    ledger_account_code: str
    ledger_account_name: str
    as_on: date
    #: The first imported statement's start. A posting dated before it that
    #: no line accounts for is taken as cleared before reconciling began --
    #: the opening balance among them. None until a statement is imported.
    reconciled_from: date | None
    book_balance: Decimal
    deposits_not_cleared: list[ReconcilingItem]
    deposits_not_cleared_total: Decimal
    payments_not_presented: list[ReconcilingItem]
    payments_not_presented_total: Decimal
    #: Lines the bank shows that the books do not have by the date.
    bank_only: list[ReconcilingItem]
    bank_only_net: Decimal
    bank_balance_per_books: Decimal
    statement_balance: Decimal | None
    difference: Decimal | None


__all__ = [
    "AutoMatchRequest",
    "AutoMatchResponse",
    "BankAccountRecord",
    "BankReconciliationStatement",
    "BankStatementLineResponse",
    "BankStatementResponse",
    "BookEntryResponse",
    "ManualMatchRequest",
    "MatchedPostingResponse",
    "ReconcilingItem",
    "StatementLineStatusEnum",
]
