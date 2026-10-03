"""Bring a bank's statement in from the file the bank gives (ACC-1, A125).

Every Indian bank exports a statement as a spreadsheet with a date, a
narration, a cheque or reference number, a withdrawal column, a deposit
column and a running balance -- under its own headings. The template names
them ``Date``, ``Description``, ``Reference``, ``Withdrawal``, ``Deposit`` and
``Balance``, and reads the common bank spellings of each ("Txn Date",
"Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Closing
Balance"); anything else is mapped on the import screen (decision B3).

The check names every problem by row and column and writes nothing; the
import writes one statement and all of its lines, or nothing. A row is money
in **or** out, never both and never neither. **A row identical to a line
already imported on the account is refused**, naming its statement -- banks'
downloads overlap, and the same deposit twice would match twice. Two
identical rows inside one file are the bank's business (two ATM withdrawals
of the same amount on one day) and are kept.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bank_reconciliation.models import BankStatement, BankStatementLine
from app.bank_reconciliation.services.reconciliation_service import (
    BankReconciliationService,
)
from app.common import file_import
from app.common.audit.services import record_audit
from app.common.file_import import (
    Column,
    FileFormat,
    ImportIssue,
    ImportReport,
    ImportRow,
    RowReader,
    parse_date,
    read_rows,
)

__all__ = ["COLUMNS", "BankStatementFileImporter", "template_csv", "template_workbook"]

ZERO = Decimal("0")

COLUMNS: tuple[Column, ...] = (
    Column(
        "Date",
        ("txndate", "transactiondate", "trandate", "valuedate", "postingdate"),
        True,
        "The day the bank shows the money moving. dd-mm-yyyy, dd/mm/yyyy, "
        "yyyy-mm-dd or an Excel date.",
        "01-04-2026",
    ),
    Column(
        "Description",
        ("narration", "particulars", "details", "remarks", "transactiondetails"),
        False,
        "The bank's narration, as printed.",
        "NEFT-SHARMA TRADERS",
    ),
    Column(
        "Reference",
        (
            "chqrefno",
            "chequeno",
            "chqno",
            "refno",
            "referenceno",
            "utr",
            "utrno",
            "instrumentno",
        ),
        False,
        "The cheque number, UTR or the bank's reference. It is what matching "
        "looks for on a receipt or payment.",
        "UTR123456",
    ),
    Column(
        "Withdrawal",
        ("withdrawalamt", "withdrawalamount", "debit", "debitamount", "dr"),
        False,
        "Money out of the account. Fill this or Deposit, not both.",
        "",
    ),
    Column(
        "Deposit",
        ("depositamt", "depositamount", "credit", "creditamount", "cr"),
        False,
        "Money into the account. Fill this or Withdrawal, not both.",
        "25000.00",
    ),
    Column(
        "Balance",
        ("closingbalance", "runningbalance", "balanceamt", "availablebalance"),
        False,
        "The balance the bank printed after the line. It is what the "
        "reconciliation statement checks itself against.",
        "125000.00",
    ),
)


@dataclass(frozen=True, slots=True)
class _Row:
    """One checked row, ready to become a line."""

    number: int
    on: date
    description: str | None
    reference: str | None
    withdrawal: Decimal
    deposit: Decimal
    balance: Decimal | None

    def identity(self) -> tuple[object, ...]:
        """Return what makes two lines the same line."""
        return (
            self.on,
            self.withdrawal,
            self.deposit,
            self.reference or "",
            self.description or "",
            self.balance,
        )


def _identity(line: BankStatementLine) -> tuple[object, ...]:
    """Return a stored line's identity, shaped as :meth:`_Row.identity`."""
    return (
        line.line_date,
        Decimal(line.withdrawal),
        Decimal(line.deposit),
        line.reference or "",
        line.description or "",
        None if line.balance is None else Decimal(line.balance),
    )


class BankStatementFileImporter:
    """Check a statement file row by row, and import it whole or not at all."""

    def __init__(self, session: Session) -> None:
        """Work on one request's session."""
        self._session = session

    def run(
        self,
        content: bytes,
        *,
        file_format: FileFormat,
        firm_id: UUID,
        actor_id: UUID,
        ledger_account_id: UUID,
        name: str | None,
        apply: bool,
    ) -> ImportReport[BankStatement]:
        """Check every row; with ``apply``, write the statement and its lines."""
        account = BankReconciliationService(self._session).bank_account(
            ledger_account_id, firm_id=firm_id
        )
        rows, used, ignored = read_rows(content, file_format, COLUMNS)
        report: ImportReport[BankStatement] = ImportReport(
            columns_used=used, columns_ignored=ignored
        )
        missing = []
        if "Date" not in used:
            missing.append("a Date column")
        if "Withdrawal" not in used and "Deposit" not in used:
            missing.append("a Withdrawal or Deposit column")
        if missing:
            report.issues.append(
                ImportIssue(
                    row=1,
                    code=None,
                    column=None,
                    message="The heading row has no "
                    + " and no ".join(missing)
                    + ". Download the template to see the headings.",
                )
            )
            return report
        stored = self._stored(firm_id, account.id)
        checked: list[_Row] = []
        for row in rows:
            if not any(row.cells.values()):
                report.skipped_blank += 1
                continue
            report.rows += 1
            line = self._check_row(row, stored, report)
            if line is not None:
                checked.append(line)
        if report.rows == 0 and not report.issues:
            report.issues.append(
                ImportIssue(1, None, None, "The file has no statement lines.")
            )
        if report.issues:
            return report
        report.to_create = len(checked)
        if not apply:
            return report
        statement = self._write(
            checked,
            firm_id=firm_id,
            actor_id=actor_id,
            ledger_account_id=account.id,
            name=name,
        )
        self._session.commit()
        self._session.refresh(statement)
        report.records = [statement]
        report.imported = True
        return report

    def _stored(
        self, firm_id: UUID, ledger_account_id: UUID
    ) -> dict[tuple[object, ...], str]:
        """Return every live line on the account by identity, to its statement."""
        found: dict[tuple[object, ...], str] = {}
        for line, statement_name in self._session.execute(
            select(BankStatementLine, BankStatement.name)
            .join(BankStatement, BankStatement.id == BankStatementLine.statement_id)
            .where(
                BankStatementLine.firm_id == firm_id,
                BankStatementLine.ledger_account_id == ledger_account_id,
                BankStatementLine.is_deleted.is_(False),
            )
        ).all():
            found.setdefault(_identity(line), statement_name)
        return found

    @staticmethod
    def _check_row(
        row: ImportRow,
        stored: dict[tuple[object, ...], str],
        report: ImportReport[BankStatement],
    ) -> _Row | None:
        """Check one row; nothing is written."""
        issues: list[ImportIssue] = []
        reader = RowReader(row, row.cells.get("Reference", "").strip(), issues)
        raw_date = reader.text("Date")
        on = parse_date(raw_date) if raw_date else None
        if not raw_date:
            reader.fail("Date", "is required.")
        elif on is None:
            reader.fail("Date", f"'{raw_date}' is not a date.")
        withdrawal = reader.number("Withdrawal") or ZERO
        deposit = reader.number("Deposit") or ZERO
        balance = reader.number("Balance")
        if withdrawal < ZERO:
            reader.fail("Withdrawal", "cannot be negative.")
        if deposit < ZERO:
            reader.fail("Deposit", "cannot be negative.")
        if withdrawal > ZERO and deposit > ZERO:
            reader.fail(
                "Deposit", "and Withdrawal are both filled; a line is one or the other."
            )
        elif withdrawal == ZERO and deposit == ZERO and not issues:
            reader.fail(
                "Deposit", "or Withdrawal is required; the line moves no money."
            )
        for heading, value in (("Withdrawal", withdrawal), ("Deposit", deposit)):
            if value != value.quantize(Decimal("0.01")):
                reader.fail(heading, "has more than two decimals.")
        if issues or on is None:
            report.issues.extend(issues)
            return None
        line = _Row(
            number=row.number,
            on=on,
            description=reader.text("Description").strip() or None,
            reference=reader.text("Reference").strip()[:120] or None,
            withdrawal=withdrawal,
            deposit=deposit,
            balance=balance,
        )
        earlier = stored.get(line.identity())
        if earlier is not None:
            reader.fail(
                "Date",
                f"this line is already imported, in {earlier}. Take the lines "
                "already imported out of the file.",
            )
            report.issues.extend(issues)
            return None
        return line

    def _write(
        self,
        rows: Sequence[_Row],
        *,
        firm_id: UUID,
        actor_id: UUID,
        ledger_account_id: UUID,
        name: str | None,
    ) -> BankStatement:
        """Stage the statement and its lines, and audit it."""
        from_date = min(row.on for row in rows)
        to_date = max(row.on for row in rows)
        statement = BankStatement(
            firm_id=firm_id,
            ledger_account_id=ledger_account_id,
            name=(name or "").strip()[:200]
            or f"Statement {from_date.isoformat()} to {to_date.isoformat()}",
            from_date=from_date,
            to_date=to_date,
            line_count=len(rows),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(statement)
        self._session.flush()
        for number, row in enumerate(rows, start=1):
            self._session.add(
                BankStatementLine(
                    statement_id=statement.id,
                    firm_id=firm_id,
                    ledger_account_id=ledger_account_id,
                    line_number=number,
                    line_date=row.on,
                    description=row.description,
                    reference=row.reference,
                    withdrawal=row.withdrawal,
                    deposit=row.deposit,
                    balance=row.balance,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()
        record_audit(
            self._session,
            action="bank_statement.imported",
            entity_type="bank_statement",
            entity_id=statement.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=None,
            after_data={
                "name": statement.name,
                "ledger_account_id": str(ledger_account_id),
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "line_count": len(rows),
            },
        )
        return statement


def template_csv() -> str:
    """Build the CSV template: the headings and one example row."""
    return file_import.template_csv(COLUMNS)


def template_workbook() -> bytes:
    """Build the XLSX template: the sheet to fill and the notes."""
    return file_import.template_workbook(
        sheet_title="Statement",
        columns=COLUMNS,
        notes=[
            "One row is one line of the bank statement, in the bank's order.",
            "A line is a Withdrawal or a Deposit; the other is left blank.",
            "Lines already imported on this account are refused, so an "
            "overlapping download has to be trimmed first.",
        ],
        lists_header=[],
        lists=[],
    )
