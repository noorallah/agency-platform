"""Firm-scoped REST endpoints for staff advances.

An employee's account, an advance out of cash or a bank account, and its
recovery, without the chart of accounts or the journal screen. The rights are
the expense screen's: whoever records the firm's rent records an advance.
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
from app.finance.models import AccountType, LedgerAccount
from app.staff_advances.models import StaffAdvanceEntry
from app.staff_advances.schemas import (
    EmployeeCreate,
    EmployeeRecord,
    StaffAdvanceAccountChoices,
    StaffAdvanceAccountRecord,
    StaffAdvanceCancelRequest,
    StaffAdvanceCreate,
    StaffAdvanceResponse,
)
from app.staff_advances.services import EmployeeBalance, StaffAdvanceService
from app.staff_advances.services.staff_advance_service import SIDE_MONEY, SIDE_SALARY

router = APIRouter(
    prefix="/api/v1/staff-advances",
    tags=["Staff advances"],
    responses=STANDARD_ERROR_RESPONSES,
)

StaffAdvanceViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EXPENSE_VIEW")
]
StaffAdvanceCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EXPENSE_CREATE")
]
StaffAdvanceCancelScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("EXPENSE_CANCEL")
]


def _employee(row: EmployeeBalance) -> EmployeeRecord:
    """Build the record for one employee."""
    return EmployeeRecord(
        account_id=row.account.id,
        code=row.account.code,
        name=row.account.name,
        is_active=row.account.is_active,
        advanced=row.advanced,
        recovered=row.recovered,
        owes=row.owes,
    )


def _to_responses(
    service: StaffAdvanceService, rows: list[StaffAdvanceEntry]
) -> list[StaffAdvanceResponse]:
    """Build the responses for several entries, reading their accounts once."""
    accounts = service.accounts_named(rows)
    missing = LedgerAccount(code="", name="", account_type="")
    responses: list[StaffAdvanceResponse] = []
    for row in rows:
        employee = accounts.get(row.employee_account_id, missing)
        other = accounts.get(row.other_account_id, missing)
        responses.append(
            StaffAdvanceResponse(
                id=row.id,
                entry_number=row.entry_number,
                entry_date=row.entry_date,
                kind=row.kind,
                employee_account_id=row.employee_account_id,
                employee_name=employee.name,
                other_account_id=row.other_account_id,
                other_account_code=other.code,
                other_account_name=other.name,
                other_side=(
                    SIDE_SALARY
                    if other.account_type == AccountType.EXPENSE.value
                    else SIDE_MONEY
                ),
                amount=row.amount,
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


def _one(service: StaffAdvanceService, row: StaffAdvanceEntry) -> StaffAdvanceResponse:
    """Build the response for one entry."""
    return _to_responses(service, [row])[0]


@router.get("", response_model=PaginatedResponse[StaffAdvanceResponse])
def list_staff_advances(
    scope: StaffAdvanceViewScope,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str, Query()] = "",
    employee_account_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    entry_from: Annotated[date | None, Query()] = None,
    entry_to: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[StaffAdvanceResponse]:
    """List advances and recoveries, newest first; one employee's when named."""
    service = StaffAdvanceService(db)
    rows, total = service.list_entries(
        firm_id=scope.firm_id,
        page=page,
        page_size=page_size,
        search=search,
        employee_account_id=employee_account_id,
        status=status_filter,
        date_from=entry_from,
        date_to=entry_to,
    )
    return PaginatedResponse(
        data=_to_responses(service, list(rows)),
        pagination=PaginationParams(page=page, page_size=page_size).metadata(total),
    )


@router.get("/employees", response_model=ApiResponse[list[EmployeeRecord]])
def list_employees(
    scope: StaffAdvanceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[EmployeeRecord]]:
    """Return every employee with what he was advanced and what he still owes.

    The figures are the balance of his account in the ledger, so an advance
    paid by a cheque or a journal counts as one recorded here does. Declared
    above `/{entry_id}`, as every literal path here is.
    """
    return ApiResponse(
        data=[
            _employee(row) for row in StaffAdvanceService(db).employees(scope.firm_id)
        ]
    )


@router.post(
    "/employees",
    response_model=ApiResponse[EmployeeRecord],
    status_code=status.HTTP_201_CREATED,
)
def add_employee(
    payload: EmployeeCreate,
    scope: StaffAdvanceCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[EmployeeRecord]:
    """Open an account for one employee under Staff Advances.

    The group is opened with the first employee. A second employee of the
    same name is refused.
    """
    row = StaffAdvanceService(db).add_employee(
        payload.name, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(
        data=_employee(row), message=f"{row.account.name} added ({row.account.code})."
    )


@router.get("/accounts", response_model=ApiResponse[StaffAdvanceAccountChoices])
def staff_advance_account_choices(
    scope: StaffAdvanceViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[StaffAdvanceAccountChoices]:
    """Return the accounts the advance and recovery forms offer."""
    service = StaffAdvanceService(db)
    return ApiResponse(
        data=StaffAdvanceAccountChoices(
            money_accounts=[
                StaffAdvanceAccountRecord(
                    id=row.id, code=row.code, name=row.name, kind=kind
                )
                for row, kind in service.money_accounts(scope.firm_id)
            ],
            salary_accounts=[
                StaffAdvanceAccountRecord(id=row.id, code=row.code, name=row.name)
                for row in service.salary_accounts(scope.firm_id)
            ],
        )
    )


@router.post(
    "",
    response_model=ApiResponse[StaffAdvanceResponse],
    status_code=status.HTTP_201_CREATED,
)
def record_staff_advance(
    payload: StaffAdvanceCreate,
    scope: StaffAdvanceCreateScope,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiResponse[StaffAdvanceResponse]:
    """Record an advance or a recovery and post its journal.

    An advance: Dr the employee, Cr the cash or bank account. A recovery: Cr
    the employee, Dr the salary's expense account or the money account it was
    paid back into; more than he owes is refused. An advance out of a cash
    account that would stand below zero answers 409 with `details.reason`
    `cash_below_zero` and saves nothing; the same body with
    `cash_below_zero_confirmed` saves it.
    """
    service = StaffAdvanceService(db)
    row = service.record(
        payload,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        ask_before_cash_below_zero=not payload.cash_below_zero_confirmed,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=_one(service, row), message=f"{row.entry_number} recorded and posted."
    )


@router.post("/{entry_id}/cancel", response_model=ApiResponse[StaffAdvanceResponse])
def cancel_staff_advance(
    entry_id: UUID,
    payload: StaffAdvanceCancelRequest,
    scope: StaffAdvanceCancelScope,
    response: Response,
    expected_version: ExpectedVersion,
    db: Session = Depends(get_db),
) -> ApiResponse[StaffAdvanceResponse]:
    """Take an entry back with a mirror journal; the original stays."""
    service = StaffAdvanceService(db)
    assert_version(
        service.get(entry_id, firm_id=scope.firm_id).version, expected_version
    )
    row = service.cancel(
        entry_id,
        firm_id=scope.firm_id,
        actor_id=scope.actor_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(row)
    set_etag(response, row)
    return ApiResponse(
        data=_one(service, row), message=f"{row.entry_number} cancelled."
    )
