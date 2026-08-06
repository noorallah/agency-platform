"""Finance API routes - Chart of Accounts, Journal Entries, GL Reports."""

from decimal import Decimal
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import get_current_user
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.security import require_permission

from app.finance.models import (
    FinancialYear,
    AccountingPeriod,
    AccountGroup,
    LedgerAccount,
    CostCenter,
    ProfitCenter,
    JournalType,
    VoucherType,
    JournalEntry,
    LedgerBalance,
)
from app.finance.schemas import (
    FinancialYearCreate,
    FinancialYearResponse,
    AccountingPeriodCreate,
    AccountingPeriodResponse,
    AccountGroupCreate,
    AccountGroupResponse,
    LedgerAccountCreate,
    LedgerAccountResponse,
    CostCenterCreate,
    CostCenterResponse,
    ProfitCenterCreate,
    ProfitCenterResponse,
    JournalTypeCreate,
    JournalTypeResponse,
    VoucherTypeCreate,
    VoucherTypeResponse,
    JournalEntryCreate,
    JournalEntryResponse,
    JournalLineSchema,
    TrialBalanceReportSchema,
    GeneralLedgerReportSchema,
    AccountSummarySchema,
)
from app.finance.services import (
    JournalEntryEngine,
    JournalLineData,
    GeneralLedgerEngine,
)

router = APIRouter(prefix="/api/finance", tags=["finance"])


# ============================================================================
# Financial Years
# ============================================================================


@router.post("/financial-years", response_model=FinancialYearResponse)
async def create_financial_year(
    req: FinancialYearCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new financial year."""
    await require_permission(user, "finance:master:create")
    
    fy = FinancialYear(
        firm_id=user.firm_id,
        financial_year_code=req.financial_year_code,
        financial_year_name=req.financial_year_name,
        financial_year_start=req.financial_year_start,
        financial_year_end=req.financial_year_end,
        is_active=req.is_active,
        description=req.description,
        created_by=user.id,
    )
    db.add(fy)
    db.commit()
    db.refresh(fy)
    return fy


@router.get("/financial-years", response_model=list[FinancialYearResponse])
async def list_financial_years(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all financial years."""
    years = db.scalars(
        select(FinancialYear).where(FinancialYear.firm_id == user.firm_id)
    ).all()
    return years


# ============================================================================
# Accounting Periods
# ============================================================================


@router.post("/accounting-periods", response_model=AccountingPeriodResponse)
async def create_accounting_period(
    req: AccountingPeriodCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new accounting period."""
    await require_permission(user, "finance:master:create")
    
    period = AccountingPeriod(
        firm_id=user.firm_id,
        financial_year_id=req.financial_year_id,
        period_code=req.period_code,
        period_name=req.period_name,
        period_start=req.period_start,
        period_end=req.period_end,
        status=req.status.value,
        description=req.description,
        created_by=user.id,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.get("/accounting-periods", response_model=list[AccountingPeriodResponse])
async def list_accounting_periods(
    financial_year_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List accounting periods."""
    query = select(AccountingPeriod).where(AccountingPeriod.firm_id == user.firm_id)
    if financial_year_id:
        query = query.where(AccountingPeriod.financial_year_id == financial_year_id)
    
    periods = db.scalars(query).all()
    return periods


# ============================================================================
# Account Groups
# ============================================================================


@router.post("/account-groups", response_model=AccountGroupResponse)
async def create_account_group(
    req: AccountGroupCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create an account group."""
    await require_permission(user, "finance:master:create")
    
    group = AccountGroup(
        firm_id=user.firm_id,
        account_group_code=req.account_group_code,
        account_group_name=req.account_group_name,
        account_type=req.account_type.value,
        parent_group_id=req.parent_group_id,
        description=req.description,
        created_by=user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/account-groups", response_model=list[AccountGroupResponse])
async def list_account_groups(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all account groups."""
    groups = db.scalars(
        select(AccountGroup).where(AccountGroup.firm_id == user.firm_id)
    ).all()
    return groups


# ============================================================================
# Ledger Accounts (Chart of Accounts)
# ============================================================================


@router.post("/ledger-accounts", response_model=LedgerAccountResponse)
async def create_ledger_account(
    req: LedgerAccountCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new ledger account."""
    await require_permission(user, "finance:master:create")
    
    account = LedgerAccount(
        firm_id=user.firm_id,
        account_group_id=req.account_group_id,
        account_code=req.account_code,
        account_name=req.account_name,
        account_type=req.account_type.value,
        is_active=req.is_active,
        requires_cost_center=req.requires_cost_center,
        requires_profit_center=req.requires_profit_center,
        description=req.description,
        created_by=user.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/ledger-accounts", response_model=list[LedgerAccountResponse])
async def list_ledger_accounts(
    account_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List ledger accounts (Chart of Accounts)."""
    query = select(LedgerAccount).where(LedgerAccount.firm_id == user.firm_id)
    
    if account_type:
        query = query.where(LedgerAccount.account_type == account_type)
    if is_active is not None:
        query = query.where(LedgerAccount.is_active == is_active)
    
    query = query.order_by(LedgerAccount.account_code)
    accounts = db.scalars(query).all()
    return accounts


# ============================================================================
# Cost Centers
# ============================================================================


@router.post("/cost-centers", response_model=CostCenterResponse)
async def create_cost_center(
    req: CostCenterCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a cost center."""
    await require_permission(user, "finance:master:create")
    
    center = CostCenter(
        firm_id=user.firm_id,
        cost_center_code=req.cost_center_code,
        cost_center_name=req.cost_center_name,
        is_active=req.is_active,
        description=req.description,
        created_by=user.id,
    )
    db.add(center)
    db.commit()
    db.refresh(center)
    return center


@router.get("/cost-centers", response_model=list[CostCenterResponse])
async def list_cost_centers(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List cost centers."""
    centers = db.scalars(
        select(CostCenter).where(CostCenter.firm_id == user.firm_id)
    ).all()
    return centers


# ============================================================================
# Profit Centers
# ============================================================================


@router.post("/profit-centers", response_model=ProfitCenterResponse)
async def create_profit_center(
    req: ProfitCenterCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a profit center."""
    await require_permission(user, "finance:master:create")
    
    center = ProfitCenter(
        firm_id=user.firm_id,
        profit_center_code=req.profit_center_code,
        profit_center_name=req.profit_center_name,
        is_active=req.is_active,
        description=req.description,
        created_by=user.id,
    )
    db.add(center)
    db.commit()
    db.refresh(center)
    return center


@router.get("/profit-centers", response_model=list[ProfitCenterResponse])
async def list_profit_centers(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List profit centers."""
    centers = db.scalars(
        select(ProfitCenter).where(ProfitCenter.firm_id == user.firm_id)
    ).all()
    return centers


# ============================================================================
# Journal Types
# ============================================================================


@router.post("/journal-types", response_model=JournalTypeResponse)
async def create_journal_type(
    req: JournalTypeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a journal type."""
    await require_permission(user, "finance:master:create")
    
    jtype = JournalType(
        firm_id=user.firm_id,
        journal_type_code=req.journal_type_code,
        journal_type_name=req.journal_type_name,
        is_active=req.is_active,
        description=req.description,
        created_by=user.id,
    )
    db.add(jtype)
    db.commit()
    db.refresh(jtype)
    return jtype


@router.get("/journal-types", response_model=list[JournalTypeResponse])
async def list_journal_types(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List journal types."""
    jtypes = db.scalars(
        select(JournalType).where(JournalType.firm_id == user.firm_id)
    ).all()
    return jtypes


# ============================================================================
# Voucher Types
# ============================================================================


@router.post("/voucher-types", response_model=VoucherTypeResponse)
async def create_voucher_type(
    req: VoucherTypeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a voucher type."""
    await require_permission(user, "finance:master:create")
    
    vtype = VoucherType(
        firm_id=user.firm_id,
        voucher_type_code=req.voucher_type_code,
        voucher_type_name=req.voucher_type_name,
        is_active=req.is_active,
        description=req.description,
        created_by=user.id,
    )
    db.add(vtype)
    db.commit()
    db.refresh(vtype)
    return vtype


@router.get("/voucher-types", response_model=list[VoucherTypeResponse])
async def list_voucher_types(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List voucher types."""
    vtypes = db.scalars(
        select(VoucherType).where(VoucherType.firm_id == user.firm_id)
    ).all()
    return vtypes


# ============================================================================
# Journal Entries
# ============================================================================


@router.post("/journal-entries", response_model=JournalEntryResponse)
async def create_journal_entry(
    req: JournalEntryCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new journal entry (in DRAFT status)."""
    await require_permission(user, "finance:journal:create")
    
    engine = JournalEntryEngine(db)
    
    try:
        entry = engine.create_entry(
            firm_id=user.firm_id,
            journal_type_id=req.journal_type_id,
            voucher_type_id=req.voucher_type_id,
            accounting_period_id=req.accounting_period_id,
            journal_date=req.journal_date,
            reference_number=req.reference_number,
            description=req.description,
            lines=[
                JournalLineData(
                    ledger_account_id=line.ledger_account_id,
                    debit_amount=line.debit_amount,
                    credit_amount=line.credit_amount,
                    cost_center_id=line.cost_center_id,
                    profit_center_id=line.profit_center_id,
                    description=line.description,
                )
                for line in req.lines
            ],
            actor_id=user.id,
            remarks=req.remarks,
        )
        db.commit()
        db.refresh(entry)
        return entry
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/journal-entries", response_model=list[JournalEntryResponse])
async def list_journal_entries(
    accounting_period_id: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List journal entries."""
    query = select(JournalEntry).where(JournalEntry.firm_id == user.firm_id)
    
    if accounting_period_id:
        query = query.where(JournalEntry.accounting_period_id == accounting_period_id)
    if status:
        query = query.where(JournalEntry.journal_status == status)
    
    query = query.order_by(JournalEntry.journal_date.desc()).offset(skip).limit(limit)
    entries = db.scalars(query).all()
    return entries


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get a journal entry by ID."""
    entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.firm_id == user.firm_id,
        )
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry


@router.post("/journal-entries/{entry_id}/post")
async def post_journal_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Post a journal entry to the general ledger."""
    await require_permission(user, "finance:journal:post")
    
    entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.firm_id == user.firm_id,
        )
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    
    engine = JournalEntryEngine(db)
    try:
        engine.post_entry(entry_id)
        db.commit()
        db.refresh(entry)
        return {"message": "Journal entry posted successfully", "entry": entry}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# General Ledger Reports
# ============================================================================


@router.get("/trial-balance", response_model=TrialBalanceReportSchema)
async def get_trial_balance(
    accounting_period_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get trial balance for a period."""
    engine = GeneralLedgerEngine(db)
    report = engine.trial_balance(
        firm_id=user.firm_id,
        accounting_period_id=accounting_period_id,
    )
    return report


@router.get("/general-ledger/{ledger_account_id}", response_model=GeneralLedgerReportSchema)
async def get_general_ledger(
    ledger_account_id: UUID,
    accounting_period_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get general ledger detail for an account."""
    engine = GeneralLedgerEngine(db)
    report = engine.general_ledger(
        firm_id=user.firm_id,
        ledger_account_id=ledger_account_id,
        accounting_period_id=accounting_period_id,
    )
    return report


@router.get("/account-summaries", response_model=list[AccountSummarySchema])
async def get_account_summaries(
    accounting_period_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get summary of all accounts for a period."""
    engine = GeneralLedgerEngine(db)
    summaries = engine.account_summary(
        firm_id=user.firm_id,
        accounting_period_id=accounting_period_id,
    )
    return summaries
