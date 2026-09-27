"""Firm-scoped REST endpoints for expenses.

Recording an expense writes and posts its journal in the same request, so a
manager can book rent or fuel without the authority to post journals by hand.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.concurrency import ExpectedVersion, assert_version, set_etag
from app.core.constants.core import MAX_PAGE_SIZE
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.expenses.models import Expense
from app.expenses.schemas import (
    ExpenseAccountChoices,
    ExpenseAccountRecord,
    ExpenseCancelRequest,
    ExpenseCreate,
    ExpenseResponse,
)
from app.expenses.services import ExpenseService
from app.finance.models import LedgerAccount

router = APIRouter(
    prefix="/api/v1/expenses",
    tags=["Expenses"],
    responses=STANDARD_ERROR_RESPONSES,
)

ExpenseViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("EXPENSE_VIEW")]
ExpenseCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EXPENSE_CREATE")
]
# Taking money back off the books is a separate authority from recording it,
# the way reversing a journal is separate from posting one.
ExpenseCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EXPENSE_CANCEL")
]


def _to_responses(
    service: ExpenseService, rows: list[Expense]
) -> list[ExpenseResponse]:
    """Build the responses for several expenses, reading their accounts once."""
    accounts = service.accounts_named(rows)
    missing = LedgerAccount(code="", name="")
    responses: list[ExpenseResponse] = []
    for row in rows:
        spent_on = accounts.get(row.expense_account_id, missing)
        paid_from = accounts.get(row.paid_from_account_id, missing)
        responses.append(
            ExpenseResponse(
                id=row.id,
                expense_number=row.expense_number,
                expense_date=row.expense_date,
                expense_account_id=row.expense_account_id,
                expense_account_code=spent_on.code,
                expense_account_name=spent_on.name,
                paid_from_account_id=row.paid_from_account_id,
                paid_from_account_code=paid_from.code,
                paid_from_account_name=paid_from.name,
                amount=row.amount,
                payee=row.payee,
                reference=row.reference,
                narration=row.narration,
                status=row.status,
                journal_entry_id=row.journal_entry_id,
                reversal_journal_entry_id=row.reversal_journal_entry_id,
                cancel_reason=row.cancel_reason,
                cancelled_at=row.cancelled_at,
                version=row.version,
            )
        )
    return responses


def _one(service: ExpenseService, row: Expense) -> ExpenseResponse:
    """Build the response for one expense."""
    return _to_responses(service, [row])[0]


@router.get("", response_model=PaginatedResponse[ExpenseResponse])
def list_expenses(
    scope: ExpenseViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: str = Query(default=""),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    expense_from: Annotated[date | None, Query()] = None,
    expense_to: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ExpenseResponse]:
    """List the firm's expenses, newest first."""
    service = ExpenseService(db)
    rows, total = service.list_expenses(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status_filter,
        date_from=expense_from,
        date_to=expense_to,
    )
    return PaginatedResponse(
        data=_to_responses(service, list(rows)),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/accounts", response_model=ApiResponse[ExpenseAccountChoices])
def expense_account_choices(
    scope: ExpenseViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpenseAccountChoices]:
    """Return the accounts the expense form offers.

    Declared above `/{expense_id}`: FastAPI matches in declaration order, and
    under it "accounts" would be read as an id and answered 422.
    """
    service = ExpenseService(db)
    return ApiResponse(
        data=ExpenseAccountChoices(
            expense_accounts=[
                ExpenseAccountRecord(id=row.id, code=row.code, name=row.name)
                for row in service.expense_accounts(scope.firm_id)
            ],
            paid_from_accounts=[
                ExpenseAccountRecord(id=row.id, code=row.code, name=row.name)
                for row in service.paid_from_accounts(scope.firm_id)
            ],
        )
    )


@router.get("/{expense_id}", response_model=ApiResponse[ExpenseResponse])
def get_expense(
    expense_id: UUID,
    scope: ExpenseViewScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpenseResponse]:
    """Return one expense."""
    service = ExpenseService(db)
    row = service.get(expense_id, firm_id=scope.firm_id)
    set_etag(response, row)
    return ApiResponse(data=_one(service, row))


@router.post(
    "",
    response_model=ApiResponse[ExpenseResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_expense(
    payload: ExpenseCreate,
    scope: ExpenseCreateScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpenseResponse]:
    """Record money spent and post its journal: Dr the expense, Cr the money."""
    service = ExpenseService(db)
    row = service.create(payload, firm_id=scope.firm_id, actor_id=scope.actor_id)
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=_one(service, row),
        message=f"{row.expense_number} recorded and posted.",
    )


@router.post("/{expense_id}/cancel", response_model=ApiResponse[ExpenseResponse])
def cancel_expense(
    expense_id: UUID,
    payload: ExpenseCancelRequest,
    scope: ExpenseCancelScope,
    response: Response,
    expected_version: ExpectedVersion,
    db: Session = Depends(get_db),
) -> ApiResponse[ExpenseResponse]:
    """Take an expense back with a mirror journal; the original stays."""
    service = ExpenseService(db)
    assert_version(
        service.get(expense_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.cancel(
        expense_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=_one(service, row), message=f"{row.expense_number} cancelled."
    )
