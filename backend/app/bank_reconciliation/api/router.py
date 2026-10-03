"""Firm-scoped REST endpoints for bank reconciliation (ACC-1, decision A125).

The finance codes rather than a namespace of its own: reading statements and
the reconciliation statement is ``LEDGER_VIEW``, and importing a statement or
matching it -- which says what the bank cleared, the fact a BRS rests on -- is
``JOURNAL_POST``, the code that writes to the bank ledger in the first place.

Literal paths are declared **above** ``/{id}`` ones, because FastAPI matches
in declaration order.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.bank_reconciliation.schemas import (
    AutoMatchRequest,
    AutoMatchResponse,
    BankAccountRecord,
    BankReconciliationStatement,
    BankStatementLineResponse,
    BankStatementResponse,
    BookEntryResponse,
    ManualMatchRequest,
    StatementLineStatusEnum,
)
from app.bank_reconciliation.services import (
    BankReconciliationService,
    BankStatementFileImporter,
)
from app.bank_reconciliation.services.statement_import import (
    template_csv,
    template_workbook,
)
from app.common.file_import import (
    ImportReportResponse,
    file_format_of,
    report_response,
)
from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.constants import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.core.utils.dates import utc_now
from app.imports.services import columns_for_kind, mapped_content, parse_mapping

router = APIRouter(
    prefix="/api/v1/bank-reconciliation",
    tags=["Bank Reconciliation"],
    responses=STANDARD_ERROR_RESPONSES,
)

BankViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("LEDGER_VIEW")]
BankWriteScope = Annotated[ResolvedFirmScope, firm_permission_scope("JOURNAL_POST")]


@router.get("/accounts", response_model=ApiResponse[list[BankAccountRecord]])
def list_bank_accounts(
    scope: BankViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[BankAccountRecord]]:
    """Return the firm's bank accounts, with the lines left to match on each."""
    return ApiResponse(data=BankReconciliationService(db).bank_accounts(scope.firm_id))


@router.get("/import-template")
def bank_statement_import_template(
    scope: BankViewScope,
    format: Literal["csv", "xlsx"] = "xlsx",
) -> StreamingResponse:
    """Download the bank statement template, with notes on every column."""
    if format == "csv":
        return StreamingResponse(
            iter([template_csv()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="bank-statement.csv"'
            },
        )
    return StreamingResponse(
        iter([template_workbook()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bank-statement.xlsx"'},
    )


@router.post(
    "/statements/import-file", response_model=ApiResponse[ImportReportResponse]
)
async def import_bank_statement(
    scope: BankWriteScope,
    file: Annotated[UploadFile, File()],
    ledger_account_id: Annotated[UUID, Form()],
    db: Session = Depends(get_db),
    name: Annotated[str | None, Form()] = None,
    apply: Annotated[bool, Form()] = False,
    mapping: Annotated[str | None, Form()] = None,
) -> ApiResponse[ImportReportResponse]:
    """Check a CSV or XLSX statement, and with ``apply`` import it whole.

    Every problem is returned with its row and column; an apply that finds
    any writes nothing and says so with ``imported: false``.
    """
    file_format = file_format_of(file.filename)
    content, file_format = mapped_content(
        await file.read(),
        file_format,
        parse_mapping(mapping),
        columns_for_kind(db, "bank-statement"),
    )
    report = BankStatementFileImporter(db).run(
        content,
        file_format=file_format,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        ledger_account_id=ledger_account_id,
        name=name or file.filename,
        apply=apply,
    )
    return ApiResponse(data=report_response(report))


@router.get("/statements", response_model=PaginatedResponse[BankStatementResponse])
def list_bank_statements(
    scope: BankViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    ledger_account_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BankStatementResponse]:
    """Return a page of imported statements, the latest first."""
    rows, total = BankReconciliationService(db).list_statements(
        firm_id=scope.firm_id,
        ledger_account_id=ledger_account_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.delete("/statements/{statement_id}", status_code=status.HTTP_200_OK)
def delete_bank_statement(
    statement_id: UUID,
    scope: BankWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    """Take a statement off with its lines; what it cleared goes back to uncleared."""
    BankReconciliationService(db).delete_statement(
        statement_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=None, message="Statement removed.")


@router.get("/lines", response_model=PaginatedResponse[BankStatementLineResponse])
def list_bank_statement_lines(
    scope: BankViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    ledger_account_id: UUID | None = None,
    statement_id: UUID | None = None,
    line_status: Annotated[
        StatementLineStatusEnum | None, Query(alias="status")
    ] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BankStatementLineResponse]:
    """Return a page of statement lines, in the bank's order, with their matches."""
    rows, total = BankReconciliationService(db).list_lines(
        firm_id=scope.firm_id,
        ledger_account_id=ledger_account_id,
        statement_id=statement_id,
        status=line_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.delete(
    "/lines/{statement_line_id}/matches",
    response_model=ApiResponse[BankStatementLineResponse],
)
def unmatch_bank_statement_line(
    statement_line_id: UUID,
    scope: BankWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BankStatementLineResponse]:
    """Undo a line's match; the entries it cleared go back to uncleared."""
    row = BankReconciliationService(db).unmatch(
        statement_line_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=row, message="Line unmatched.")


@router.get("/book-entries", response_model=PaginatedResponse[BookEntryResponse])
def list_uncleared_book_entries(
    scope: BankViewScope,
    ledger_account_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BookEntryResponse]:
    """Return the bank account's entries no statement line accounts for yet."""
    rows, total = BankReconciliationService(db).book_entries(
        firm_id=scope.firm_id,
        ledger_account_id=ledger_account_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=rows,
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.post("/auto-match", response_model=ApiResponse[AutoMatchResponse])
def auto_match_bank_lines(
    payload: AutoMatchRequest,
    scope: BankWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AutoMatchResponse]:
    """Match every unmatched line that has exactly one good entry in the books."""
    result = BankReconciliationService(db).auto_match(
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        ledger_account_id=payload.ledger_account_id,
        statement_id=payload.statement_id,
    )
    return ApiResponse(
        data=result,
        message=f"{result.matched} matched; {result.left_unmatched} left to match.",
    )


@router.post(
    "/matches",
    response_model=ApiResponse[BankStatementLineResponse],
    status_code=status.HTTP_201_CREATED,
)
def match_bank_line(
    payload: ManualMatchRequest,
    scope: BankWriteScope,
    db: Session = Depends(get_db),
) -> ApiResponse[BankStatementLineResponse]:
    """Tie one line to the entries it accounts for; they must add up to it."""
    row = BankReconciliationService(db).match(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    return ApiResponse(data=row, message="Line matched.")


@router.get("/statement", response_model=ApiResponse[BankReconciliationStatement])
def bank_reconciliation_statement(
    scope: BankViewScope,
    ledger_account_id: UUID,
    as_on: date | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[BankReconciliationStatement]:
    """Return the bank reconciliation statement as on a date (today if left out)."""
    return ApiResponse(
        data=BankReconciliationService(db).reconciliation_statement(
            firm_id=scope.firm_id,
            ledger_account_id=ledger_account_id,
            as_on=as_on or utc_now().date(),
        )
    )
