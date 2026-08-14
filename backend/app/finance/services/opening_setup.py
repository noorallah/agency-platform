"""Give a firm the finance setup its documents need before they can post.

The sample firms had no chart of accounts, no accounting periods and no journal
or voucher types — not an incomplete setup, none at all. Documents post through
``DocumentPostingService``, which refuses rather than guesses, so without this a
firm cannot approve an invoice.

The chart below is a conventional distribution chart, not a claim about any
particular firm's conventions. It is **seed data**: changing a code or a name
later is an edit here, not a migration. A firm that wants a different chart
builds one through the finance API and remaps its control accounts.

Every step is idempotent, so this can be re-run after a partial failure or after
``reset_tenancy_layout`` rebuilds a store.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models import (
    AccountGroup,
    AccountingPeriod,
    FinancialYear,
    JournalType,
    LedgerAccount,
    VoucherType,
)
from app.finance.schemas import (
    AccountGroupCreate,
    AccountingPeriodCreate,
    AccountTypeEnum,
    FinancialYearCreate,
    JournalTypeCreate,
    LedgerAccountCreate,
    VoucherTypeCreate,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.finance_service import FinanceService


@dataclass(frozen=True, slots=True)
class SeedAccount:
    """One account in the default chart, and what it is used for."""

    code: str
    name: str
    account_type: AccountTypeEnum
    group: str
    purpose: ControlAccountPurpose | None = None


GROUPS: tuple[tuple[str, str, AccountTypeEnum], ...] = (
    ("CA", "Current Assets", AccountTypeEnum.ASSET),
    ("CL", "Current Liabilities", AccountTypeEnum.LIABILITY),
    ("REV", "Revenue", AccountTypeEnum.INCOME),
    ("EXP", "Direct Expenses", AccountTypeEnum.EXPENSE),
)

CHART: tuple[SeedAccount, ...] = (
    SeedAccount(
        "1000", "Cash", AccountTypeEnum.ASSET, "CA", ControlAccountPurpose.CASH
    ),
    SeedAccount(
        "1010", "Bank", AccountTypeEnum.ASSET, "CA", ControlAccountPurpose.BANK
    ),
    SeedAccount(
        "1100",
        "Trade Receivables",
        AccountTypeEnum.ASSET,
        "CA",
        ControlAccountPurpose.ACCOUNTS_RECEIVABLE,
    ),
    SeedAccount(
        "1200",
        "Inventory",
        AccountTypeEnum.ASSET,
        "CA",
        ControlAccountPurpose.INVENTORY,
    ),
    SeedAccount(
        "1300",
        "Input Tax",
        AccountTypeEnum.ASSET,
        "CA",
        ControlAccountPurpose.INPUT_TAX,
    ),
    SeedAccount(
        "2100",
        "Trade Payables",
        AccountTypeEnum.LIABILITY,
        "CL",
        ControlAccountPurpose.ACCOUNTS_PAYABLE,
    ),
    SeedAccount(
        "2300",
        "Goods Received Not Invoiced",
        AccountTypeEnum.LIABILITY,
        "CL",
        ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED,
    ),
    SeedAccount(
        "2200",
        "Output Tax",
        AccountTypeEnum.LIABILITY,
        "CL",
        ControlAccountPurpose.OUTPUT_TAX,
    ),
    SeedAccount(
        "4000",
        "Sales",
        AccountTypeEnum.INCOME,
        "REV",
        ControlAccountPurpose.SALES_REVENUE,
    ),
    SeedAccount(
        "4100",
        "Sales Returns",
        AccountTypeEnum.INCOME,
        "REV",
        ControlAccountPurpose.SALES_RETURNS,
    ),
    SeedAccount(
        "4200",
        "Discount Received",
        AccountTypeEnum.INCOME,
        "REV",
        ControlAccountPurpose.DISCOUNT_RECEIVED,
    ),
    SeedAccount(
        "4900",
        "Rounding",
        AccountTypeEnum.INCOME,
        "REV",
        ControlAccountPurpose.ROUNDING,
    ),
    SeedAccount(
        "5000",
        "Purchases",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.PURCHASE_EXPENSE,
    ),
    SeedAccount(
        "5100",
        "Purchase Returns",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.PURCHASE_RETURNS,
    ),
    SeedAccount(
        "5200",
        "Cost of Goods Sold",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.COST_OF_GOODS_SOLD,
    ),
    SeedAccount(
        "5400",
        "Purchase Price Variance",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.PURCHASE_PRICE_VARIANCE,
    ),
    SeedAccount(
        "5300",
        "Discount Allowed",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.DISCOUNT_ALLOWED,
    ),
    SeedAccount(
        "5500",
        "Inventory Adjustment",
        AccountTypeEnum.EXPENSE,
        "EXP",
        ControlAccountPurpose.INVENTORY_ADJUSTMENT,
    ),
)


def seed_finance_setup(
    session: Session, *, firm_id: UUID, year_starts_on: date, actor_id: UUID
) -> dict[str, int]:
    """Create the chart, calendar and posting references a firm needs.

    Args:
        session: A session already bound to the firm's store.
        firm_id: The firm to set up.
        year_starts_on: First day of the financial year to create. Twelve
            monthly periods are opened from here.
        actor_id: The user credited with the setup.

    Returns:
        Counts of what was created, so a caller can report a no-op honestly.

    """
    finance = FinanceService(session)
    controls = ControlAccountService(session)
    created = {"groups": 0, "accounts": 0, "periods": 0, "mappings": 0, "types": 0}

    groups: dict[str, UUID] = {}
    for code, name, account_type in GROUPS:
        existing = session.scalar(
            select(AccountGroup).where(
                AccountGroup.firm_id == firm_id,
                AccountGroup.code == code,
                AccountGroup.is_deleted.is_(False),
            )
        )
        if existing is None:
            existing = finance.create_account_group(
                AccountGroupCreate(code=code, name=name, account_type=account_type),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            created["groups"] += 1
        groups[code] = existing.id

    accounts: dict[str, UUID] = {}
    for entry in CHART:
        existing_account = session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.firm_id == firm_id,
                LedgerAccount.code == entry.code,
                LedgerAccount.is_deleted.is_(False),
            )
        )
        if existing_account is None:
            existing_account = finance.create_ledger_account(
                LedgerAccountCreate(
                    account_group_id=groups[entry.group],
                    code=entry.code,
                    name=entry.name,
                    account_type=entry.account_type,
                ),
                firm_id=firm_id,
                actor_id=actor_id,
            )
            created["accounts"] += 1
        accounts[entry.code] = existing_account.id

    year_ends_on = date(year_starts_on.year + 1, year_starts_on.month, 1) - timedelta(
        days=1
    )
    year = session.scalar(
        select(FinancialYear).where(
            FinancialYear.firm_id == firm_id,
            FinancialYear.starts_on == year_starts_on,
            FinancialYear.is_deleted.is_(False),
        )
    )
    if year is None:
        label = f"{year_starts_on.year}-{year_starts_on.year + 1}"
        year = finance.create_financial_year(
            FinancialYearCreate(
                code=f"FY{year_starts_on.year}",
                name=f"Financial Year {label}",
                starts_on=year_starts_on,
                ends_on=year_ends_on,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )

    for index, (starts_on, ends_on) in enumerate(_months(year_starts_on), start=1):
        exists = session.scalar(
            select(AccountingPeriod.id).where(
                AccountingPeriod.firm_id == firm_id,
                AccountingPeriod.financial_year_id == year.id,
                AccountingPeriod.period_number == index,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
        if exists is not None:
            continue
        finance.create_accounting_period(
            AccountingPeriodCreate(
                financial_year_id=year.id,
                period_number=index,
                code=f"P{index:02d}",
                name=starts_on.strftime("%B %Y"),
                starts_on=starts_on,
                ends_on=ends_on,
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        created["periods"] += 1

    if (
        session.scalar(
            select(JournalType.id).where(
                JournalType.firm_id == firm_id,
                JournalType.code == "GEN",
                JournalType.is_deleted.is_(False),
            )
        )
        is None
    ):
        finance.create_journal_type(
            JournalTypeCreate(code="GEN", name="General"),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        created["types"] += 1
    if (
        session.scalar(
            select(VoucherType.id).where(
                VoucherType.firm_id == firm_id,
                VoucherType.code == "JV",
                VoucherType.is_deleted.is_(False),
            )
        )
        is None
    ):
        finance.create_voucher_type(
            VoucherTypeCreate(code="JV", name="Journal Voucher"),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        created["types"] += 1

    configured = controls.mapping(firm_id)
    for entry in CHART:
        if entry.purpose is None or entry.purpose.value in configured:
            continue
        controls.assign(firm_id, entry.purpose, accounts[entry.code], actor_id=actor_id)
        created["mappings"] += 1

    session.flush()
    return created


def _months(start: date) -> list[tuple[date, date]]:
    """Return twelve consecutive month spans beginning at ``start``."""
    spans: list[tuple[date, date]] = []
    year, month = start.year, start.month
    for _ in range(12):
        last_day = monthrange(year, month)[1]
        spans.append((date(year, month, 1), date(year, month, last_day)))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return spans
