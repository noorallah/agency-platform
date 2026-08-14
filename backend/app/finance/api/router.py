"""Firm-scoped REST endpoints for finance masters, journals, and reports."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.common.scope import ResolvedFirmScope, firm_permission_scope
from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.pagination import PaginationParams
from app.core.responses.models import ApiResponse, PaginatedResponse
from app.finance.schemas import (
    AccountGroupCreate,
    AccountGroupResponse,
    AccountGroupUpdate,
    AccountingPeriodCreate,
    AccountingPeriodResponse,
    AccountingPeriodUpdate,
    AccountSummary,
    CostCenterCreate,
    CostCenterResponse,
    CostCenterUpdate,
    FinancialYearCreate,
    FinancialYearResponse,
    FinancialYearUpdate,
    GeneralLedgerReport,
    JournalEntryCreate,
    JournalEntryResponse,
    JournalEntryReverse,
    JournalStatusEnum,
    JournalTypeCreate,
    JournalTypeResponse,
    LedgerAccountCreate,
    LedgerAccountResponse,
    LedgerAccountUpdate,
    ProfitCenterCreate,
    ProfitCenterResponse,
    ProfitCenterUpdate,
    ProfitLossReport,
    TrialBalanceReport,
    VoucherTypeCreate,
    VoucherTypeResponse,
)
from app.finance.services import (
    FinanceService,
    GeneralLedgerService,
    JournalEntryEngine,
    JournalLineData,
)

router = APIRouter(
    prefix="/api/v1/finance",
    tags=["Finance"],
    responses=STANDARD_ERROR_RESPONSES,
)


# Codes come from the seeded `accounting` and `financial_year` permission groups
# in app.identity.system_seed rather than a finance-specific namespace, so the
# existing ACCOUNTANT role grants these endpoints without further mapping.
MasterViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("ACCOUNT_VIEW")]
MasterManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("ACCOUNT_MANAGE")
]
YearViewScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("FINANCIAL_YEAR_VIEW")
]
YearManageScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("FINANCIAL_YEAR_CREATE")
]
PeriodCloseScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("FINANCIAL_YEAR_CLOSE")
]
JournalViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("JOURNAL_VIEW")]
JournalCreateScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("JOURNAL_CREATE")
]
JournalPostScope = Annotated[ResolvedFirmScope, firm_permission_scope("JOURNAL_POST")]
JournalReverseScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("JOURNAL_REVERSE")
]
LedgerViewScope = Annotated[ResolvedFirmScope, firm_permission_scope("LEDGER_VIEW")]
TrialBalanceScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("TRIAL_BALANCE_VIEW")
]
ProfitLossScope = Annotated[
    ResolvedFirmScope, firm_permission_scope("PROFIT_LOSS_VIEW")
]


# ----------------------------------------------------------------------
# Financial years and accounting periods
# ----------------------------------------------------------------------


@router.post(
    "/financial-years",
    response_model=ApiResponse[FinancialYearResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_financial_year(
    payload: FinancialYearCreate,
    scope: YearManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[FinancialYearResponse]:
    """Create one financial year for the active firm."""
    row = FinanceService(db).create_financial_year(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=FinancialYearResponse.model_validate(row))


@router.get("/financial-years", response_model=ApiResponse[list[FinancialYearResponse]])
def list_financial_years(
    scope: YearViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[FinancialYearResponse]]:
    """Return every financial year for the active firm."""
    rows = FinanceService(db).list_financial_years(firm_id=scope.firm_id)
    return ApiResponse(data=[FinancialYearResponse.model_validate(row) for row in rows])


@router.patch(
    "/financial-years/{year_id}", response_model=ApiResponse[FinancialYearResponse]
)
def update_financial_year(
    year_id: UUID,
    payload: FinancialYearUpdate,
    scope: YearManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[FinancialYearResponse]:
    """Apply a partial update to one financial year."""
    row = FinanceService(db).update_financial_year(
        year_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=FinancialYearResponse.model_validate(row))


@router.delete("/financial-years/{year_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_financial_year(
    year_id: UUID, scope: YearManageScope, db: Session = Depends(get_db)
) -> None:
    """Soft delete one financial year that carries no periods."""
    FinanceService(db).delete_financial_year(
        year_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()


@router.post(
    "/accounting-periods",
    response_model=ApiResponse[AccountingPeriodResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_accounting_period(
    payload: AccountingPeriodCreate,
    scope: YearManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AccountingPeriodResponse]:
    """Create one accounting period inside a financial year."""
    row = FinanceService(db).create_accounting_period(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=AccountingPeriodResponse.model_validate(row))


@router.get(
    "/accounting-periods", response_model=ApiResponse[list[AccountingPeriodResponse]]
)
def list_accounting_periods(
    scope: YearViewScope,
    financial_year_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AccountingPeriodResponse]]:
    """Return accounting periods, optionally for one financial year."""
    rows = FinanceService(db).list_accounting_periods(
        firm_id=scope.firm_id, financial_year_id=financial_year_id
    )
    return ApiResponse(
        data=[AccountingPeriodResponse.model_validate(row) for row in rows]
    )


@router.patch(
    "/accounting-periods/{period_id}",
    response_model=ApiResponse[AccountingPeriodResponse],
)
def update_accounting_period(
    period_id: UUID,
    payload: AccountingPeriodUpdate,
    scope: PeriodCloseScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AccountingPeriodResponse]:
    """Update one accounting period, including its open or closed status."""
    row = FinanceService(db).update_accounting_period(
        period_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=AccountingPeriodResponse.model_validate(row))


# ----------------------------------------------------------------------
# Chart of accounts
# ----------------------------------------------------------------------


@router.post(
    "/account-groups",
    response_model=ApiResponse[AccountGroupResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_account_group(
    payload: AccountGroupCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AccountGroupResponse]:
    """Create one account group."""
    row = FinanceService(db).create_account_group(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=AccountGroupResponse.model_validate(row))


@router.get("/account-groups", response_model=ApiResponse[list[AccountGroupResponse]])
def list_account_groups(
    scope: MasterViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[AccountGroupResponse]]:
    """Return every account group for the active firm."""
    rows = FinanceService(db).list_account_groups(firm_id=scope.firm_id)
    return ApiResponse(data=[AccountGroupResponse.model_validate(r) for r in rows])


@router.patch(
    "/account-groups/{group_id}", response_model=ApiResponse[AccountGroupResponse]
)
def update_account_group(
    group_id: UUID,
    payload: AccountGroupUpdate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[AccountGroupResponse]:
    """Apply a partial update to one account group."""
    row = FinanceService(db).update_account_group(
        group_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=AccountGroupResponse.model_validate(row))


@router.post(
    "/ledger-accounts",
    response_model=ApiResponse[LedgerAccountResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_ledger_account(
    payload: LedgerAccountCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LedgerAccountResponse]:
    """Create one ledger account."""
    row = FinanceService(db).create_ledger_account(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=LedgerAccountResponse.model_validate(row))


@router.get("/ledger-accounts", response_model=ApiResponse[list[LedgerAccountResponse]])
def list_ledger_accounts(
    scope: MasterViewScope,
    account_group_id: UUID | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[LedgerAccountResponse]]:
    """Return ledger accounts, optionally filtered by group and status."""
    rows = FinanceService(db).list_ledger_accounts(
        firm_id=scope.firm_id,
        account_group_id=account_group_id,
        is_active=is_active,
    )
    return ApiResponse(data=[LedgerAccountResponse.model_validate(r) for r in rows])


@router.patch(
    "/ledger-accounts/{account_id}",
    response_model=ApiResponse[LedgerAccountResponse],
)
def update_ledger_account(
    account_id: UUID,
    payload: LedgerAccountUpdate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[LedgerAccountResponse]:
    """Apply a partial update to one ledger account."""
    row = FinanceService(db).update_ledger_account(
        account_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=LedgerAccountResponse.model_validate(row))


# ----------------------------------------------------------------------
# Cost centres, profit centres, journal and voucher types
# ----------------------------------------------------------------------


@router.post(
    "/cost-centers",
    response_model=ApiResponse[CostCenterResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_cost_center(
    payload: CostCenterCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CostCenterResponse]:
    """Create one cost centre."""
    row = FinanceService(db).create_cost_center(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=CostCenterResponse.model_validate(row))


@router.get("/cost-centers", response_model=ApiResponse[list[CostCenterResponse]])
def list_cost_centers(
    scope: MasterViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[CostCenterResponse]]:
    """Return every cost centre for the active firm."""
    rows = FinanceService(db).list_cost_centers(firm_id=scope.firm_id)
    return ApiResponse(data=[CostCenterResponse.model_validate(r) for r in rows])


@router.patch(
    "/cost-centers/{centre_id}", response_model=ApiResponse[CostCenterResponse]
)
def update_cost_center(
    centre_id: UUID,
    payload: CostCenterUpdate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[CostCenterResponse]:
    """Apply a partial update to one cost centre."""
    row = FinanceService(db).update_cost_center(
        centre_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=CostCenterResponse.model_validate(row))


@router.post(
    "/profit-centers",
    response_model=ApiResponse[ProfitCenterResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_profit_center(
    payload: ProfitCenterCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProfitCenterResponse]:
    """Create one profit centre."""
    row = FinanceService(db).create_profit_center(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=ProfitCenterResponse.model_validate(row))


@router.get("/profit-centers", response_model=ApiResponse[list[ProfitCenterResponse]])
def list_profit_centers(
    scope: MasterViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[ProfitCenterResponse]]:
    """Return every profit centre for the active firm."""
    rows = FinanceService(db).list_profit_centers(firm_id=scope.firm_id)
    return ApiResponse(data=[ProfitCenterResponse.model_validate(r) for r in rows])


@router.patch(
    "/profit-centers/{centre_id}", response_model=ApiResponse[ProfitCenterResponse]
)
def update_profit_center(
    centre_id: UUID,
    payload: ProfitCenterUpdate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProfitCenterResponse]:
    """Apply a partial update to one profit centre."""
    row = FinanceService(db).update_profit_center(
        centre_id, payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=ProfitCenterResponse.model_validate(row))


@router.post(
    "/journal-types",
    response_model=ApiResponse[JournalTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_journal_type(
    payload: JournalTypeCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[JournalTypeResponse]:
    """Create one journal type."""
    row = FinanceService(db).create_journal_type(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=JournalTypeResponse.model_validate(row))


@router.get("/journal-types", response_model=ApiResponse[list[JournalTypeResponse]])
def list_journal_types(
    scope: MasterViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[JournalTypeResponse]]:
    """Return every journal type for the active firm."""
    rows = FinanceService(db).list_journal_types(firm_id=scope.firm_id)
    return ApiResponse(data=[JournalTypeResponse.model_validate(r) for r in rows])


@router.post(
    "/voucher-types",
    response_model=ApiResponse[VoucherTypeResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_voucher_type(
    payload: VoucherTypeCreate,
    scope: MasterManageScope,
    db: Session = Depends(get_db),
) -> ApiResponse[VoucherTypeResponse]:
    """Create one voucher type."""
    row = FinanceService(db).create_voucher_type(
        payload, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=VoucherTypeResponse.model_validate(row))


@router.get("/voucher-types", response_model=ApiResponse[list[VoucherTypeResponse]])
def list_voucher_types(
    scope: MasterViewScope, db: Session = Depends(get_db)
) -> ApiResponse[list[VoucherTypeResponse]]:
    """Return every voucher type for the active firm."""
    rows = FinanceService(db).list_voucher_types(firm_id=scope.firm_id)
    return ApiResponse(data=[VoucherTypeResponse.model_validate(r) for r in rows])


# ----------------------------------------------------------------------
# Journal entries
# ----------------------------------------------------------------------


@router.post(
    "/journal-entries",
    response_model=ApiResponse[JournalEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_journal_entry(
    payload: JournalEntryCreate,
    scope: JournalCreateScope,
    db: Session = Depends(get_db),
) -> ApiResponse[JournalEntryResponse]:
    """Create one balanced draft journal entry."""
    entry = JournalEntryEngine(db).create_entry(
        firm_id=scope.firm_id,
        journal_type_id=payload.journal_type_id,
        voucher_type_id=payload.voucher_type_id,
        accounting_period_id=payload.accounting_period_id,
        journal_date=payload.journal_date,
        reference_number=payload.reference_number,
        description=payload.description,
        remarks=payload.remarks,
        lines=[
            JournalLineData(
                ledger_account_id=line.ledger_account_id,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                description=line.description,
            )
            for line in payload.lines
        ],
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(data=JournalEntryResponse.model_validate(entry))


@router.get(
    "/journal-entries",
    response_model=PaginatedResponse[JournalEntryResponse],
)
def list_journal_entries(
    scope: JournalViewScope,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    sort_direction: Literal["asc", "desc"] = "desc",
    accounting_period_id: UUID | None = None,
    status_value: Annotated[JournalStatusEnum | None, Query(alias="status")] = None,
    journal_type_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[JournalEntryResponse]:
    """Return a page of journal entries for the firm in scope.

    The module could create an entry and read one back by id, and had no way to
    find one -- so everything the documents posted was unfindable unless
    somebody already knew its id.
    """
    params = PaginationParams(page=page, page_size=page_size)
    rows, total = JournalEntryEngine(db).list_entries(
        firm_id=scope.firm_id,
        page=params.page,
        page_size=params.page_size,
        search=search,
        accounting_period_id=accounting_period_id,
        status=status_value.value if status_value else None,
        journal_type_id=journal_type_id,
        descending=sort_direction == "desc",
    )
    return PaginatedResponse(
        data=[JournalEntryResponse.model_validate(row) for row in rows],
        pagination=params.metadata(total),
    )


@router.get(
    "/journal-entries/{entry_id}", response_model=ApiResponse[JournalEntryResponse]
)
def get_journal_entry(
    entry_id: UUID, scope: JournalViewScope, db: Session = Depends(get_db)
) -> ApiResponse[JournalEntryResponse]:
    """Return one journal entry with its lines."""
    entry = JournalEntryEngine(db).get_entry(entry_id, firm_id=scope.firm_id)
    return ApiResponse(data=JournalEntryResponse.model_validate(entry))


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=ApiResponse[JournalEntryResponse],
)
def post_journal_entry(
    entry_id: UUID, scope: JournalPostScope, db: Session = Depends(get_db)
) -> ApiResponse[JournalEntryResponse]:
    """Post one draft journal entry to the general ledger."""
    entry = JournalEntryEngine(db).post_entry(
        entry_id, firm_id=scope.firm_id, actor_id=scope.actor_id
    )
    db.commit()
    return ApiResponse(data=JournalEntryResponse.model_validate(entry))


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=ApiResponse[JournalEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
def reverse_journal_entry(
    entry_id: UUID,
    payload: JournalEntryReverse,
    scope: JournalReverseScope,
    db: Session = Depends(get_db),
) -> ApiResponse[JournalEntryResponse]:
    """Reverse one posted journal entry under a new reference."""
    reversal = JournalEntryEngine(db).reverse_entry(
        entry_id,
        firm_id=scope.firm_id,
        reference_number=payload.reference_number,
        accounting_period_id=payload.accounting_period_id,
        journal_date=payload.journal_date,
        actor_id=scope.actor_id,
    )
    db.commit()
    return ApiResponse(data=JournalEntryResponse.model_validate(reversal))


# ----------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------


@router.get("/trial-balance", response_model=ApiResponse[TrialBalanceReport])
def trial_balance(
    accounting_period_id: UUID,
    scope: TrialBalanceScope,
    db: Session = Depends(get_db),
) -> ApiResponse[TrialBalanceReport]:
    """Return the trial balance for one accounting period."""
    report = GeneralLedgerService(db).trial_balance(
        firm_id=scope.firm_id, accounting_period_id=accounting_period_id
    )
    return ApiResponse(data=report)


@router.get(
    "/general-ledger/{ledger_account_id}",
    response_model=ApiResponse[GeneralLedgerReport],
)
def general_ledger(
    ledger_account_id: UUID,
    accounting_period_id: UUID,
    scope: LedgerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[GeneralLedgerReport]:
    """Return the movement statement for one ledger account."""
    report = GeneralLedgerService(db).general_ledger(
        firm_id=scope.firm_id,
        ledger_account_id=ledger_account_id,
        accounting_period_id=accounting_period_id,
    )
    return ApiResponse(data=report)


@router.get("/profit-loss", response_model=ApiResponse[ProfitLossReport])
def profit_and_loss(
    accounting_period_id: UUID,
    scope: ProfitLossScope,
    db: Session = Depends(get_db),
) -> ApiResponse[ProfitLossReport]:
    """Return the profit and loss for one period, with the year to date."""
    report = GeneralLedgerService(db).profit_and_loss(
        firm_id=scope.firm_id, accounting_period_id=accounting_period_id
    )
    return ApiResponse(data=report)


@router.get("/account-summaries", response_model=ApiResponse[list[AccountSummary]])
def account_summaries(
    accounting_period_id: UUID,
    scope: LedgerViewScope,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AccountSummary]]:
    """Return one balance row per account for a period."""
    rows = GeneralLedgerService(db).account_summary(
        firm_id=scope.firm_id, accounting_period_id=accounting_period_id
    )
    return ApiResponse(data=rows)
