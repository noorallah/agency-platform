"""Bank reconciliation: statements in, lines matched, the BRS out (ACC-1, A125).

Bank movements are made with contra vouchers -- cash deposited into the bank
is a deposit, cash drawn is a withdrawal -- because they post straight to the
bank ledger, which is the only thing matching looks at.
"""

# ruff: noqa: D103

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from app.bank_reconciliation.api.router import (
    auto_match_bank_lines,
    bank_reconciliation_statement,
    import_bank_statement,
    list_bank_accounts,
    list_bank_statement_lines,
    list_uncleared_book_entries,
)
from app.bank_reconciliation.models import (
    BankReconciliationMatch,
    BankStatement,
    BankStatementLine,
)
from app.bank_reconciliation.schemas import AutoMatchRequest, ManualMatchRequest
from app.bank_reconciliation.services import (
    BankReconciliationService,
    BankStatementFileImporter,
)
from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.contra.services import ContraVoucherService
from app.core.enums import TokenType
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.finance.models import GLPosting, LedgerAccount
from app.finance.services.period_close_checks import PeriodCloseChecks
from app.imports.services import IMPORT_KINDS
from tests.unit.test_contra_vouchers import BANK, CASH, _account, _books, _move
from tests.unit.test_settlements import WHEN, _Books

HEADER = "Date,Description,Reference,Withdrawal,Deposit,Balance\n"


def _scope(books: _Books) -> ResolvedFirmScope:
    user_id = uuid4()
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset({"LEDGER_VIEW", "JOURNAL_POST"}),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=books.firm.id,
    )


def _bank(books: _Books) -> LedgerAccount:
    return _account(books, BANK)


def _deposit(
    books: _Books, amount: str, when: date = WHEN, reference: str | None = None
) -> UUID:
    """Pay cash into the bank; return the bank-side posting."""
    voucher, _ = _move(
        books,
        _account(books, CASH).id,
        _bank(books).id,
        amount,
        when,
        reference,
    )
    return _bank_posting(books, voucher.journal_entry_id)


def _withdraw(
    books: _Books, amount: str, when: date = WHEN, reference: str | None = None
) -> UUID:
    """Draw cash from the bank; return the bank-side posting."""
    voucher, _ = _move(
        books,
        _bank(books).id,
        _account(books, CASH).id,
        amount,
        when,
        reference,
    )
    return _bank_posting(books, voucher.journal_entry_id)


def _bank_posting(books: _Books, journal_id: UUID) -> UUID:
    posting_id = books.session.scalar(
        select(GLPosting.id).where(
            GLPosting.journal_entry_id == journal_id,
            GLPosting.ledger_account_id == _bank(books).id,
        )
    )
    assert posting_id is not None
    return posting_id


def _import(
    books: _Books,
    body: str,
    *,
    apply: bool = True,
    account: UUID | None = None,
    name: str | None = "April",
) -> tuple[list[str], BankStatement | None]:
    report = BankStatementFileImporter(books.session).run(
        body.encode(),
        file_format="csv",
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=account or _bank(books).id,
        name=name,
        apply=apply,
    )
    return [issue.describe() for issue in report.issues], (
        report.records[0] if report.records else None
    )


def _lines(books: _Books) -> list[BankStatementLine]:
    return list(
        books.session.scalars(
            select(BankStatementLine)
            .where(BankStatementLine.is_deleted.is_(False))
            .order_by(BankStatementLine.line_date, BankStatementLine.line_number)
        ).all()
    )


def _service(books: _Books) -> BankReconciliationService:
    return BankReconciliationService(books.session)


# ---- accounts and import ----------------------------------------------------


def test_only_bank_accounts_are_offered() -> None:
    books = _books()
    rows = list_bank_accounts(_scope(books), db=books.session).data or []
    assert [row.code for row in rows] == [BANK]
    assert rows[0].unmatched_lines == 0


def test_a_check_writes_nothing_and_an_import_writes_the_statement() -> None:
    books = _books()
    body = (
        HEADER + "20-04-2026,NEFT IN,UTR1,,500.00,1500.00\n21/04/2026,ATM,,200,,1300\n"
    )
    issues, record = _import(books, body, apply=False)
    assert issues == [] and record is None
    assert _lines(books) == []

    issues, record = _import(books, body)
    assert issues == []
    assert record is not None
    assert (record.from_date, record.to_date, record.line_count) == (
        date(2026, 4, 20),
        date(2026, 4, 21),
        2,
    )
    lines = _lines(books)
    assert [(line.deposit, line.withdrawal) for line in lines] == [
        (Decimal("500.00"), Decimal("0")),
        (Decimal("0"), Decimal("200.00")),
    ]
    assert lines[0].reference == "UTR1"
    assert books.session.scalar(
        select(AuditLog.id).where(AuditLog.action == "bank_statement.imported")
    )


def test_the_banks_own_headings_are_read() -> None:
    books = _books()
    body = (
        "Txn Date,Narration,Chq./Ref.No.,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "20-04-2026,CHQ DEP,000123,,750,750\n"
    )
    issues, record = _import(books, body)
    assert issues == [] and record is not None
    assert _lines(books)[0].reference == "000123"


def test_a_bad_row_refuses_the_whole_file_by_row_and_column() -> None:
    books = _books()
    body = (
        HEADER
        + "20-04-2026,OK,,,100,\n"
        + "21-04-2026,BOTH,,10,20,\n"
        + "22-04-2026,NONE,,,,\n"
        + "someday,BAD,,5,,\n"
    )
    issues, record = _import(books, body)
    assert record is None
    assert _lines(books) == []
    assert any(issue.startswith("Row 3") and "Deposit" in issue for issue in issues)
    assert any(
        issue.startswith("Row 4") and "moves no money" in issue for issue in issues
    )
    assert any(issue.startswith("Row 5") and "not a date" in issue for issue in issues)


def test_a_line_already_imported_is_refused_naming_its_statement() -> None:
    books = _books()
    line = "20-04-2026,ATM,,200,,1300\n"
    issues, _ = _import(books, HEADER + line + line, name="First")
    # Two identical lines in one file are the bank's business.
    assert issues == []
    assert len(_lines(books)) == 2
    issues, record = _import(books, HEADER + line, name="Second")
    assert record is None
    assert len(issues) == 1 and "already imported, in First" in issues[0]


def test_a_statement_is_refused_on_an_account_that_is_not_a_bank() -> None:
    books = _books()
    with pytest.raises(ValidationError, match="is not a bank account"):
        _import(books, HEADER + "20-04-2026,X,,,1,\n", account=_account(books, CASH).id)


def test_the_import_endpoint_takes_a_file() -> None:
    books = _books()
    upload = UploadFile(
        file=BytesIO((HEADER + "20-04-2026,X,,,100,\n").encode()),
        filename="hdfc-april.csv",
    )
    response = asyncio.run(
        import_bank_statement(
            _scope(books),
            upload,
            _bank(books).id,
            db=books.session,
            name=None,
            apply=True,
            mapping=None,
        )
    )
    assert response.data is not None and response.data.imported
    statement = books.session.scalar(select(BankStatement))
    assert statement is not None and statement.name == "hdfc-april.csv"
    assert "bank-statement" in IMPORT_KINDS


# ---- matching ---------------------------------------------------------------


def test_auto_match_takes_the_one_entry_of_the_same_amount_nearby() -> None:
    books = _books()
    posting = _deposit(books, "500", WHEN)
    _import(books, HEADER + "22-04-2026,CASH DEP,,,500,\n")
    response = auto_match_bank_lines(
        AutoMatchRequest(ledger_account_id=_bank(books).id),
        _scope(books),
        db=books.session,
    )
    assert response.data is not None
    assert (response.data.matched, response.data.left_unmatched) == (1, 0)
    match = books.session.scalar(select(BankReconciliationMatch))
    assert match is not None
    assert match.gl_posting_id == posting
    assert match.cleared_on == date(2026, 4, 22)
    assert match.matched_how == "AUTO"


def test_auto_match_leaves_an_entry_outside_the_window() -> None:
    books = _books()
    _deposit(books, "500", WHEN)
    _import(books, HEADER + "24-04-2026,CASH DEP,,,500,\n")
    result = _service(books).auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=None,
    )
    assert (result.matched, result.left_unmatched) == (0, 1)


def test_a_reference_on_the_line_picks_between_two_equal_amounts() -> None:
    books = _books()
    _deposit(books, "500", WHEN, reference="CHQ-111111")
    wanted = _deposit(books, "500", WHEN, reference="CHQ-222222")
    _import(books, HEADER + "21-04-2026,CLG CHQ 222222,,,500,\n")
    result = _service(books).auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=None,
    )
    assert result.matched == 1
    match = books.session.scalar(select(BankReconciliationMatch))
    assert match is not None and match.gl_posting_id == wanted


def test_two_equal_amounts_and_no_reference_are_left_for_a_person() -> None:
    books = _books()
    _deposit(books, "500", WHEN)
    _deposit(books, "500", WHEN)
    _import(books, HEADER + "21-04-2026,CASH,,,500,\n")
    result = _service(books).auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=None,
    )
    assert result.matched == 0


def test_a_manual_match_takes_several_entries_that_add_up() -> None:
    books = _books()
    first = _deposit(books, "300", WHEN)
    second = _deposit(books, "200", WHEN)
    _import(books, HEADER + "21-04-2026,DEPOSIT SLIP,,,500,\n")
    line = _lines(books)[0]
    service = _service(books)
    with pytest.raises(ValidationError, match="add up to it exactly"):
        service.match(
            ManualMatchRequest(statement_line_id=line.id, gl_posting_ids=[first]),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    row = service.match(
        ManualMatchRequest(statement_line_id=line.id, gl_posting_ids=[first, second]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    assert row.status == "MATCHED"
    assert {match.gl_posting_id for match in row.matches} == {first, second}
    assert all(match.matched_how == "MANUAL" for match in row.matches)

    with pytest.raises(BusinessRuleError, match="already matched"):
        service.match(
            ManualMatchRequest(statement_line_id=line.id, gl_posting_ids=[first]),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )

    undone = service.unmatch(line.id, firm_id=books.firm.id, actor_id=books.actor_id)
    assert undone.status == "UNMATCHED" and undone.matches == []
    # The entries are free again, so they can be matched once more.
    again = service.match(
        ManualMatchRequest(statement_line_id=line.id, gl_posting_ids=[first, second]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    assert again.status == "MATCHED"


def test_an_entry_cleared_by_one_line_is_refused_for_another() -> None:
    books = _books()
    posting = _deposit(books, "500", WHEN)
    _import(books, HEADER + "21-04-2026,A,,,500,\n22-04-2026,B,,,500,\n")
    first, second = _lines(books)
    service = _service(books)
    service.match(
        ManualMatchRequest(statement_line_id=first.id, gl_posting_ids=[posting]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    with pytest.raises(BusinessRuleError, match="already cleared"):
        service.match(
            ManualMatchRequest(statement_line_id=second.id, gl_posting_ids=[posting]),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_entry_on_another_account_is_refused() -> None:
    books = _books()
    voucher, _ = _move(books, _bank(books).id, _account(books, CASH).id, "50")
    cash_side = books.session.scalar(
        select(GLPosting.id).where(
            GLPosting.journal_entry_id == voucher.journal_entry_id,
            GLPosting.ledger_account_id == _account(books, CASH).id,
        )
    )
    assert cash_side is not None
    _import(books, HEADER + "21-04-2026,A,,50,,\n")
    with pytest.raises(ValidationError, match="not on this bank account"):
        _service(books).match(
            ManualMatchRequest(
                statement_line_id=_lines(books)[0].id, gl_posting_ids=[cash_side]
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_cancelled_entry_and_its_reversal_are_not_offered() -> None:
    books = _books()
    voucher, _ = _move(books, _account(books, CASH).id, _bank(books).id, "900")
    ContraVoucherService(books.session).cancel(
        voucher.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="typo"
    )
    books.session.commit()
    kept = _deposit(books, "100", WHEN)
    rows = (
        list_uncleared_book_entries(
            _scope(books), _bank(books).id, db=books.session
        ).data
        or []
    )
    assert [row.gl_posting_id for row in rows] == [kept]
    assert rows[0].amount == Decimal("100.00")


def test_the_lines_list_carries_each_lines_matches() -> None:
    books = _books()
    _deposit(books, "500", WHEN)
    _import(books, HEADER + "21-04-2026,CASH,,,500,\n22-04-2026,CHARGES,,10,,\n")
    _service(books).auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=None,
    )
    page = list_bank_statement_lines(
        _scope(books), ledger_account_id=_bank(books).id, db=books.session
    )
    rows = page.data or []
    assert [row.status for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0].matches[0].amount == Decimal("500.00")
    assert page.pagination is not None and page.pagination.total_records == 2


# ---- the reconciliation statement -------------------------------------------


def test_the_brs_names_what_stands_between_the_books_and_the_bank() -> None:
    books = _books()
    cleared = _deposit(books, "1000", WHEN)
    _deposit(books, "400", WHEN + timedelta(days=5))  # not yet cleared
    _withdraw(books, "300", WHEN + timedelta(days=6), reference="CHQ 000777")
    # The bank: the 1000 cleared, it took 25 in charges and credited 5
    # interest; the 400 and the cheque for 300 have not reached it.
    _import(
        books,
        HEADER
        + "21-04-2026,CASH DEP,,,1000.00,1000.00\n"
        + "28-04-2026,CHARGES,,25.00,,975.00\n"
        + "29-04-2026,INTEREST,,,5.00,980.00\n",
    )
    first = _lines(books)[0]
    _service(books).match(
        ManualMatchRequest(statement_line_id=first.id, gl_posting_ids=[cleared]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    report = bank_reconciliation_statement(
        _scope(books), _bank(books).id, as_on=date(2026, 4, 30), db=books.session
    ).data
    assert report is not None
    assert report.book_balance == Decimal("1100.00")
    assert report.deposits_not_cleared_total == Decimal("400.00")
    assert report.payments_not_presented_total == Decimal("300.00")
    assert [item.reference for item in report.payments_not_presented] == ["CHQ 000777"]
    assert report.bank_only_net == Decimal("-20.00")
    assert report.bank_balance_per_books == Decimal("980.00")
    assert report.statement_balance == Decimal("980.00")
    assert report.difference == Decimal("0.00")
    assert report.reconciled_from == date(2026, 4, 21)

    # Before the bank cleared the 1000 it was outstanding too.
    earlier = _service(books).reconciliation_statement(
        firm_id=books.firm.id, ledger_account_id=_bank(books).id, as_on=WHEN
    )
    assert earlier.deposits_not_cleared_total == Decimal("1000.00")
    assert earlier.bank_balance_per_books == Decimal("0.00")


def test_entries_before_the_first_statement_count_as_cleared() -> None:
    books = _books()
    _deposit(books, "700", date(2026, 4, 2))
    _import(books, HEADER + "21-04-2026,INTEREST,,,3.00,703.00\n")
    report = _service(books).reconciliation_statement(
        firm_id=books.firm.id, ledger_account_id=_bank(books).id, as_on=WHEN
    )
    # The interest line is dated after the as-on date, so it does not count.
    assert report.deposits_not_cleared == []
    assert report.bank_balance_per_books == Decimal("700.00")
    assert report.statement_balance is None


def test_removing_a_statement_frees_what_it_cleared() -> None:
    books = _books()
    _deposit(books, "500", WHEN)
    _, statement = _import(books, HEADER + "21-04-2026,CASH,,,500,\n")
    assert statement is not None
    service = _service(books)
    service.auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=statement.id,
    )
    service.delete_statement(
        statement.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    assert _lines(books) == []
    assert (
        books.session.scalar(
            select(BankReconciliationMatch).where(
                BankReconciliationMatch.is_deleted.is_(False)
            )
        )
        is None
    )
    entries, total = service.book_entries(
        firm_id=books.firm.id,
        ledger_account_id=_bank(books).id,
        date_from=None,
        date_to=None,
        page=1,
        page_size=50,
    )
    assert total == 1 and entries[0].amount == Decimal("500.00")


def test_closing_the_month_lists_lines_not_reconciled() -> None:
    books = _books()
    _deposit(books, "500", WHEN)
    _import(books, HEADER + "21-04-2026,CASH,,,500,\n")
    checks = PeriodCloseChecks(books.session)
    april = (date(2026, 4, 1), date(2026, 4, 30))
    items = {item.code: item for item in checks.run(books.firm.id, *april).items}
    item = items["UNRECONCILED_BANK_LINES"]
    assert (item.count, item.blocks) == (1, False)
    assert item.examples == ["21-04-2026 CASH (500.00)"]
    _service(books).auto_match(
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        ledger_account_id=_bank(books).id,
        statement_id=None,
    )
    codes = {item.code for item in checks.run(books.firm.id, *april).items}
    assert "UNRECONCILED_BANK_LINES" not in codes
