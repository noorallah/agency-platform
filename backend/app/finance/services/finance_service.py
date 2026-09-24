"""Transactional application service for finance master data.

The service owns the accounting calendar and the chart of accounts. Journal
posting lives in :mod:`app.finance.services.journal_engine` and reporting in
:mod:`app.finance.services.general_ledger_service`.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import (
    PROFIT_LOSS_ACCOUNT_TYPES,
    AccountGroup,
    AccountingPeriod,
    CostCenter,
    FinancialYear,
    JournalEntry,
    JournalType,
    LedgerAccount,
    PeriodStatus,
    ProfitCenter,
    VoucherType,
)
from app.finance.schemas import (
    AccountGroupCreate,
    AccountGroupUpdate,
    AccountingPeriodCreate,
    AccountingPeriodUpdate,
    CostCenterCreate,
    CostCenterUpdate,
    FinancialYearCreate,
    FinancialYearUpdate,
    JournalTypeCreate,
    LedgerAccountCreate,
    LedgerAccountUpdate,
    ProfitCenterCreate,
    ProfitCenterUpdate,
    VoucherTypeCreate,
)
from app.finance.services.control_accounts import (
    PURPOSE_LABELS,
    ControlAccountService,
)

#: The editable fields each finance master's audit row records, before and
#: after (D-FIN-13). The rows recorded ``name`` and ``is_active`` whatever was
#: edited, so ticking an account's cost-centre requirement left two rows that
#: read the same on both sides.
PERIOD_AUDIT_FIELDS = ("code", "name", "description", "starts_on", "ends_on", "status")
GROUP_AUDIT_FIELDS = (
    "name",
    "description",
    "parent_group_id",
    "sort_order",
    "is_active",
)
ACCOUNT_AUDIT_FIELDS = (
    "name",
    "description",
    "account_group_id",
    "is_balance_sheet",
    "is_profit_loss",
    "requires_cost_center",
    "requires_profit_center",
    "is_active",
)
CENTRE_AUDIT_FIELDS = ("name", "description", "is_active")


def audit_snapshot(row: object, fields: Sequence[str]) -> dict[str, object]:
    """Return the named fields of a row as JSON-safe values for an audit row."""
    snapshot: dict[str, object] = {}
    for name in fields:
        value = getattr(row, name)
        if isinstance(value, UUID | Decimal):
            value = str(value)
        elif isinstance(value, date):
            value = value.isoformat()
        snapshot[name] = value
    return snapshot


class FinanceService:
    """Coordinate validated finance master mutations and queries."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one request unit of work."""
        self._session = session

    # ------------------------------------------------------------------
    # Financial years
    # ------------------------------------------------------------------

    def create_financial_year(
        self, data: FinancialYearCreate, *, firm_id: UUID, actor_id: UUID
    ) -> FinancialYear:
        """Create one financial year for the active firm."""
        self._reject_overlapping_year(
            firm_id=firm_id, starts_on=data.starts_on, ends_on=data.ends_on
        )
        year = FinancialYear(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            year, ConflictError("A financial year with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.financial_year.created",
            entity_type="financial_year",
            entity_id=year.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": year.code, "name": year.name},
        )
        self._session.flush()
        return year

    def list_financial_years(self, *, firm_id: UUID) -> Sequence[FinancialYear]:
        """Return every financial year owned by the firm."""
        return self._session.scalars(
            self._active(select(FinancialYear), FinancialYear, firm_id).order_by(
                FinancialYear.starts_on.desc()
            )
        ).all()

    def get_financial_year(self, year_id: UUID, *, firm_id: UUID) -> FinancialYear:
        """Return one financial year or raise when it is unavailable."""
        year = self._session.scalar(
            self._active(select(FinancialYear), FinancialYear, firm_id).where(
                FinancialYear.id == year_id
            )
        )
        if year is None:
            raise ResourceNotFoundError("Financial year not found.")
        return year

    def update_financial_year(
        self,
        year_id: UUID,
        data: FinancialYearUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> FinancialYear:
        """Apply a partial update to one financial year."""
        year = self.get_financial_year(year_id, firm_id=firm_id)
        if year.is_locked:
            # Locking is the year-end close, and it is final by design: a
            # year that could be unlocked through the same form that locked it
            # protects nothing. The refusal covers `is_locked: false` too.
            raise ValidationError(
                f"Financial year {year.code} is locked. A locked year cannot "
                "be modified or unlocked."
            )
        before = self._year_snapshot(year)
        starts_on = data.starts_on or year.starts_on
        ends_on = data.ends_on or year.ends_on
        if ends_on <= starts_on:
            raise ValidationError("Financial year must end after it starts.")
        if data.starts_on is not None or data.ends_on is not None:
            self._reject_overlapping_year(
                firm_id=firm_id,
                starts_on=starts_on,
                ends_on=ends_on,
                exclude_id=year.id,
            )
            # A year moved without its periods left them outside it (D-FIN-6).
            # The periods are what journals are posted into, so they are moved
            # first, and the year can then only be re-dated around them.
            stranded = self._session.scalars(
                self._active(select(AccountingPeriod), AccountingPeriod, firm_id)
                .where(
                    AccountingPeriod.financial_year_id == year.id,
                    or_(
                        AccountingPeriod.starts_on < starts_on,
                        AccountingPeriod.ends_on > ends_on,
                    ),
                )
                .order_by(AccountingPeriod.starts_on.asc())
            ).all()
            if stranded:
                raise ValidationError(
                    f"Financial year {year.code} cannot run {starts_on} to "
                    f"{ends_on}: its period"
                    f"{'' if len(stranded) == 1 else 's'} "
                    f"{', '.join(period.code for period in stranded)} would fall "
                    "outside it."
                )
        year.starts_on = starts_on
        year.ends_on = ends_on
        if data.name is not None:
            year.name = data.name
        if data.description is not None:
            year.description = data.description
        if data.is_active is not None:
            year.is_active = data.is_active
        if data.is_locked is not None:
            year.is_locked = data.is_locked
        year.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.financial_year.updated",
            entity_type="financial_year",
            entity_id=year.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=self._year_snapshot(year),
        )
        self._session.flush()
        return year

    @staticmethod
    def _year_snapshot(year: FinancialYear) -> dict[str, object]:
        """Return what an audit row says about a year, the lock included.

        The trail recorded the name and the active flag only, so a year being
        locked -- the one change here that cannot be undone -- left no trace
        in it (D-FIN-3).
        """
        return {
            "name": year.name,
            "starts_on": year.starts_on.isoformat(),
            "ends_on": year.ends_on.isoformat(),
            "description": year.description,
            "is_active": year.is_active,
            "is_locked": year.is_locked,
        }

    def _refuse_locked_year(self, year_id: UUID, *, firm_id: UUID) -> None:
        """Refuse to touch a period whose financial year is locked."""
        year = self.get_financial_year(year_id, firm_id=firm_id)
        if year.is_locked:
            raise ValidationError(
                f"Financial year {year.code} is locked, so its accounting "
                "periods cannot be added, closed, reopened or edited."
            )

    def delete_financial_year(
        self, year_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Soft delete one financial year that carries no periods."""
        year = self.get_financial_year(year_id, firm_id=firm_id)
        if year.is_locked:
            raise ValidationError("A locked financial year cannot be deleted.")
        period_count = self._session.scalar(
            select(func.count())
            .select_from(AccountingPeriod)
            .where(
                AccountingPeriod.financial_year_id == year.id,
                AccountingPeriod.is_deleted.is_(False),
            )
        )
        if period_count:
            raise ValidationError(
                "Delete the accounting periods before deleting the financial year."
            )
        self._soft_delete(year, actor_id=actor_id)
        record_audit(
            self._session,
            action="finance.financial_year.deleted",
            entity_type="financial_year",
            entity_id=year.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"code": year.code},
        )
        self._session.flush()

    # ------------------------------------------------------------------
    # Accounting periods
    # ------------------------------------------------------------------

    def create_accounting_period(
        self, data: AccountingPeriodCreate, *, firm_id: UUID, actor_id: UUID
    ) -> AccountingPeriod:
        """Create one accounting period inside an existing financial year."""
        year = self.get_financial_year(data.financial_year_id, firm_id=firm_id)
        self._refuse_locked_year(year.id, firm_id=firm_id)
        if data.starts_on < year.starts_on or data.ends_on > year.ends_on:
            raise ValidationError(
                "The accounting period must fall inside its financial year."
            )
        self._reject_overlapping_period(
            firm_id=firm_id, starts_on=data.starts_on, ends_on=data.ends_on
        )
        period = AccountingPeriod(
            firm_id=firm_id,
            financial_year_id=year.id,
            period_number=data.period_number,
            code=data.code,
            name=data.name,
            starts_on=data.starts_on,
            ends_on=data.ends_on,
            status=PeriodStatus.OPEN.value,
            description=data.description,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            period,
            ConflictError("An accounting period with this code or number exists."),
        )
        record_audit(
            self._session,
            action="finance.accounting_period.created",
            entity_type="accounting_period",
            entity_id=period.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": period.code, "period_number": period.period_number},
        )
        self._session.flush()
        return period

    def list_accounting_periods(
        self, *, firm_id: UUID, financial_year_id: UUID | None = None
    ) -> Sequence[AccountingPeriod]:
        """Return accounting periods, optionally limited to one financial year."""
        statement = self._active(select(AccountingPeriod), AccountingPeriod, firm_id)
        if financial_year_id is not None:
            statement = statement.where(
                AccountingPeriod.financial_year_id == financial_year_id
            )
        return self._session.scalars(
            statement.order_by(AccountingPeriod.period_number.asc())
        ).all()

    def get_accounting_period(
        self, period_id: UUID, *, firm_id: UUID
    ) -> AccountingPeriod:
        """Return one accounting period or raise when it is unavailable."""
        period = self._session.scalar(
            self._active(select(AccountingPeriod), AccountingPeriod, firm_id).where(
                AccountingPeriod.id == period_id
            )
        )
        if period is None:
            raise ResourceNotFoundError("Accounting period not found.")
        return period

    def update_accounting_period(
        self,
        period_id: UUID,
        data: AccountingPeriodUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> AccountingPeriod:
        """Apply a partial update, including open/close/lock transitions."""
        period = self.get_accounting_period(period_id, firm_id=firm_id)
        # A locked year freezes every period in it, reopening included -- the
        # lock is what makes a filed year's figures final (D-FIN-3).
        self._refuse_locked_year(period.financial_year_id, firm_id=firm_id)
        before = audit_snapshot(period, PERIOD_AUDIT_FIELDS)
        # A locked period is frozen: the only edit it accepts is being reopened.
        # Compare on the stored string so the schema and model enums cannot drift.
        locked = period.status == PeriodStatus.LOCKED.value
        reopening = data.status is not None and data.status.value == (
            PeriodStatus.OPEN.value
        )
        if locked and not reopening:
            raise ValidationError("A locked accounting period can only be reopened.")
        if data.name is not None:
            period.name = data.name
        if data.description is not None:
            period.description = data.description
        starts_on = data.starts_on or period.starts_on
        ends_on = data.ends_on or period.ends_on
        if ends_on <= starts_on:
            raise ValidationError("Accounting period must end after it starts.")
        if (starts_on, ends_on) != (period.starts_on, period.ends_on):
            self._assert_period_can_move(
                period, starts_on=starts_on, ends_on=ends_on, firm_id=firm_id
            )
            period.starts_on = starts_on
            period.ends_on = ends_on
        if data.status is not None:
            self._assert_period_order(period, status=data.status.value, firm_id=firm_id)
            period.status = data.status.value
        period.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.accounting_period.updated",
            entity_type="accounting_period",
            entity_id=period.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=audit_snapshot(period, PERIOD_AUDIT_FIELDS),
        )
        self._session.flush()
        return period

    def delete_accounting_period(
        self, period_id: UUID, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Soft delete one accounting period that holds no journals (D-FIN-15).

        No endpoint deleted a period, so a year that had any could never be
        deleted either -- its own delete asks for its periods to go first.
        A period anything was written into keeps its place.
        """
        period = self.get_accounting_period(period_id, firm_id=firm_id)
        self._refuse_locked_year(period.financial_year_id, firm_id=firm_id)
        journals = self._session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.accounting_period_id == period.id,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if journals:
            raise ValidationError(
                f"Accounting period {period.code} holds {journals} journal "
                f"entr{'y' if journals == 1 else 'ies'}, so it cannot be deleted."
            )
        self._soft_delete(period, actor_id=actor_id)
        record_audit(
            self._session,
            action="finance.accounting_period.deleted",
            entity_type="accounting_period",
            entity_id=period.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=audit_snapshot(period, PERIOD_AUDIT_FIELDS),
        )
        self._session.flush()

    def _assert_period_order(
        self, period: AccountingPeriod, *, status: str, firm_id: UUID
    ) -> None:
        """Close periods oldest first and reopen them newest first (D-FIN-15).

        A posting carries its movement into every later period's stored
        balance, so with periods closed in any order a closed month still
        moved whenever an earlier open one was posted into. Decided by the
        usual convention: a period closes only once every earlier one is
        closed, and reopens only while every later one is open.
        """
        if status == period.status:
            return
        opening = status == PeriodStatus.OPEN.value
        base = self._active(select(AccountingPeriod), AccountingPeriod, firm_id)
        if opening:
            blocker = self._session.scalar(
                base.where(
                    AccountingPeriod.starts_on > period.ends_on,
                    AccountingPeriod.status != PeriodStatus.OPEN.value,
                )
                .order_by(AccountingPeriod.starts_on.desc())
                .limit(1)
            )
            if blocker is not None:
                raise ValidationError(
                    f"{blocker.code}, which comes after it, is "
                    f"{blocker.status.lower()}. Reopen the later periods "
                    f"first, newest first, before reopening {period.code}."
                )
            return
        if period.status != PeriodStatus.OPEN.value:
            # CLOSED to LOCKED, or back: the period is shut either way.
            return
        blocker = self._session.scalar(
            base.where(
                AccountingPeriod.ends_on < period.starts_on,
                AccountingPeriod.status == PeriodStatus.OPEN.value,
            )
            .order_by(AccountingPeriod.starts_on.asc())
            .limit(1)
        )
        if blocker is not None:
            raise ValidationError(
                f"{blocker.code}, which comes before it, is still open. Close "
                f"the earlier periods first, oldest first, before closing "
                f"{period.code}."
            )

    # ------------------------------------------------------------------
    # Account groups
    # ------------------------------------------------------------------

    def create_account_group(
        self, data: AccountGroupCreate, *, firm_id: UUID, actor_id: UUID
    ) -> AccountGroup:
        """Create one account group."""
        if data.parent_group_id is not None:
            parent = self.get_account_group(data.parent_group_id, firm_id=firm_id)
            if parent.account_type != data.account_type.value:
                raise ValidationError(
                    "An account group must share its parent's account type."
                )
        group = AccountGroup(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            account_type=data.account_type.value,
            parent_group_id=data.parent_group_id,
            description=data.description,
            sort_order=data.sort_order,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            group, ConflictError("An account group with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.account_group.created",
            entity_type="account_group",
            entity_id=group.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": group.code, "account_type": group.account_type},
        )
        self._session.flush()
        return group

    def list_account_groups(self, *, firm_id: UUID) -> Sequence[AccountGroup]:
        """Return every account group owned by the firm."""
        return self._session.scalars(
            self._active(select(AccountGroup), AccountGroup, firm_id).order_by(
                AccountGroup.sort_order.asc(), AccountGroup.code.asc()
            )
        ).all()

    def get_account_group(self, group_id: UUID, *, firm_id: UUID) -> AccountGroup:
        """Return one account group or raise when it is unavailable."""
        group = self._session.scalar(
            self._active(select(AccountGroup), AccountGroup, firm_id).where(
                AccountGroup.id == group_id
            )
        )
        if group is None:
            raise ResourceNotFoundError("Account group not found.")
        return group

    def update_account_group(
        self,
        group_id: UUID,
        data: AccountGroupUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> AccountGroup:
        """Apply a partial update to one account group."""
        group = self.get_account_group(group_id, firm_id=firm_id)
        before = audit_snapshot(group, GROUP_AUDIT_FIELDS)
        if data.parent_group_id is not None:
            if data.parent_group_id == group.id:
                raise ValidationError("An account group cannot be its own parent.")
            parent = self.get_account_group(data.parent_group_id, firm_id=firm_id)
            # D-FIN-15: the create asked this and the edit did not, so a group
            # could move under another type, or under its own descendant --
            # a loop no report walking the tree would ever leave.
            if parent.account_type != group.account_type:
                raise ValidationError(
                    "An account group must share its parent's account type."
                )
            ancestor: AccountGroup | None = parent
            while ancestor is not None and ancestor.parent_group_id is not None:
                if ancestor.parent_group_id == group.id:
                    raise ValidationError(
                        f"{parent.code} sits under {group.code}, so it cannot "
                        f"also be {group.code}'s parent."
                    )
                ancestor = self._session.get(AccountGroup, ancestor.parent_group_id)
            group.parent_group_id = data.parent_group_id
        if data.name is not None:
            group.name = data.name
        if data.description is not None:
            group.description = data.description
        if data.sort_order is not None:
            group.sort_order = data.sort_order
        if data.is_active is not None:
            group.is_active = data.is_active
        group.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.account_group.updated",
            entity_type="account_group",
            entity_id=group.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=audit_snapshot(group, GROUP_AUDIT_FIELDS),
        )
        self._session.flush()
        return group

    # ------------------------------------------------------------------
    # Ledger accounts
    # ------------------------------------------------------------------

    def create_ledger_account(
        self, data: LedgerAccountCreate, *, firm_id: UUID, actor_id: UUID
    ) -> LedgerAccount:
        """Create one ledger account under an existing account group."""
        group = self.get_account_group(data.account_group_id, firm_id=firm_id)
        if group.account_type != data.account_type.value:
            raise ValidationError(
                "A ledger account must share its group's account type."
            )
        # Which statement the account belongs on follows its type unless the
        # caller says otherwise. An administrator can still put a memo account
        # on the profit and loss; what they should not have to do is remember
        # to tick "profit and loss" on an income account.
        on_profit_loss = data.account_type.value in PROFIT_LOSS_ACCOUNT_TYPES
        account = LedgerAccount(
            firm_id=firm_id,
            account_group_id=group.id,
            code=data.code,
            name=data.name,
            account_type=data.account_type.value,
            description=data.description,
            is_balance_sheet=(
                not on_profit_loss
                if data.is_balance_sheet is None
                else data.is_balance_sheet
            ),
            is_profit_loss=(
                on_profit_loss if data.is_profit_loss is None else data.is_profit_loss
            ),
            requires_cost_center=data.requires_cost_center,
            requires_profit_center=data.requires_profit_center,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            account, ConflictError("A ledger account with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.ledger_account.created",
            entity_type="ledger_account",
            entity_id=account.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": account.code, "account_type": account.account_type},
        )
        self._session.flush()
        return account

    def list_ledger_accounts(
        self,
        *,
        firm_id: UUID,
        account_group_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> Sequence[LedgerAccount]:
        """Return ledger accounts, optionally filtered by group and status."""
        statement = self._active(select(LedgerAccount), LedgerAccount, firm_id)
        if account_group_id is not None:
            statement = statement.where(
                LedgerAccount.account_group_id == account_group_id
            )
        if is_active is not None:
            statement = statement.where(LedgerAccount.is_active.is_(is_active))
        return self._session.scalars(statement.order_by(LedgerAccount.code.asc())).all()

    def get_ledger_account(self, account_id: UUID, *, firm_id: UUID) -> LedgerAccount:
        """Return one ledger account or raise when it is unavailable."""
        account = self._session.scalar(
            self._active(select(LedgerAccount), LedgerAccount, firm_id).where(
                LedgerAccount.id == account_id
            )
        )
        if account is None:
            raise ResourceNotFoundError("Ledger account not found.")
        return account

    def update_ledger_account(
        self,
        account_id: UUID,
        data: LedgerAccountUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> LedgerAccount:
        """Apply a partial update to one ledger account."""
        account = self.get_ledger_account(account_id, firm_id=firm_id)
        before = audit_snapshot(account, ACCOUNT_AUDIT_FIELDS)
        if data.account_group_id is not None:
            group = self.get_account_group(data.account_group_id, firm_id=firm_id)
            if group.account_type != account.account_type:
                raise ValidationError(
                    "A ledger account must share its group's account type."
                )
            account.account_group_id = group.id
        if data.name is not None:
            account.name = data.name
        if data.description is not None:
            account.description = data.description
        if data.is_balance_sheet is not None:
            account.is_balance_sheet = data.is_balance_sheet
        if data.is_profit_loss is not None:
            account.is_profit_loss = data.is_profit_loss
        if data.requires_cost_center is not None:
            account.requires_cost_center = data.requires_cost_center
        if data.requires_profit_center is not None:
            account.requires_profit_center = data.requires_profit_center
        if data.is_active is False and account.is_active:
            # D-FIN-8: a mapped account switched off refused every document of
            # its purpose at approval ("Ledger accounts are inactive: 1100").
            # The mapping is re-pointed first, then the account can go.
            mapped = ControlAccountService(self._session).purposes_of(
                firm_id, account.id
            )
            if mapped:
                raise ValidationError(
                    f"{account.code} {account.name} is the firm's "
                    f"{', '.join(PURPOSE_LABELS[purpose] for purpose in mapped)} "
                    "account, so it cannot be deactivated. Map "
                    f"{'that purpose' if len(mapped) == 1 else 'those purposes'} "
                    "to another account first."
                )
        if data.is_active is not None:
            account.is_active = data.is_active
        account.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.ledger_account.updated",
            entity_type="ledger_account",
            entity_id=account.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=audit_snapshot(account, ACCOUNT_AUDIT_FIELDS),
        )
        self._session.flush()
        return account

    # ------------------------------------------------------------------
    # Cost and profit centres
    # ------------------------------------------------------------------

    def create_cost_center(
        self, data: CostCenterCreate, *, firm_id: UUID, actor_id: UUID
    ) -> CostCenter:
        """Create one cost centre."""
        centre = CostCenter(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            centre, ConflictError("A cost centre with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.cost_center.created",
            entity_type="cost_center",
            entity_id=centre.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": centre.code},
        )
        self._session.flush()
        return centre

    def list_cost_centers(self, *, firm_id: UUID) -> Sequence[CostCenter]:
        """Return every cost centre owned by the firm."""
        return self._session.scalars(
            self._active(select(CostCenter), CostCenter, firm_id).order_by(
                CostCenter.code.asc()
            )
        ).all()

    def update_cost_center(
        self,
        centre_id: UUID,
        data: CostCenterUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> CostCenter:
        """Apply a partial update to one cost centre."""
        centre = self._session.scalar(
            self._active(select(CostCenter), CostCenter, firm_id).where(
                CostCenter.id == centre_id
            )
        )
        if centre is None:
            raise ResourceNotFoundError("Cost centre not found.")
        before = audit_snapshot(centre, CENTRE_AUDIT_FIELDS)
        if data.name is not None:
            centre.name = data.name
        if data.description is not None:
            centre.description = data.description
        if data.is_active is not None:
            centre.is_active = data.is_active
        centre.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.cost_center.updated",
            entity_type="cost_center",
            entity_id=centre.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=audit_snapshot(centre, CENTRE_AUDIT_FIELDS),
        )
        self._session.flush()
        return centre

    def create_profit_center(
        self, data: ProfitCenterCreate, *, firm_id: UUID, actor_id: UUID
    ) -> ProfitCenter:
        """Create one profit centre."""
        centre = ProfitCenter(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            centre, ConflictError("A profit centre with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.profit_center.created",
            entity_type="profit_center",
            entity_id=centre.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": centre.code},
        )
        self._session.flush()
        return centre

    def list_profit_centers(self, *, firm_id: UUID) -> Sequence[ProfitCenter]:
        """Return every profit centre owned by the firm."""
        return self._session.scalars(
            self._active(select(ProfitCenter), ProfitCenter, firm_id).order_by(
                ProfitCenter.code.asc()
            )
        ).all()

    def update_profit_center(
        self,
        centre_id: UUID,
        data: ProfitCenterUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> ProfitCenter:
        """Apply a partial update to one profit centre."""
        centre = self._session.scalar(
            self._active(select(ProfitCenter), ProfitCenter, firm_id).where(
                ProfitCenter.id == centre_id
            )
        )
        if centre is None:
            raise ResourceNotFoundError("Profit centre not found.")
        before = audit_snapshot(centre, CENTRE_AUDIT_FIELDS)
        if data.name is not None:
            centre.name = data.name
        if data.description is not None:
            centre.description = data.description
        if data.is_active is not None:
            centre.is_active = data.is_active
        centre.updated_by = actor_id
        record_audit(
            self._session,
            action="finance.profit_center.updated",
            entity_type="profit_center",
            entity_id=centre.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data=audit_snapshot(centre, CENTRE_AUDIT_FIELDS),
        )
        self._session.flush()
        return centre

    # ------------------------------------------------------------------
    # Journal and voucher types
    # ------------------------------------------------------------------

    def create_journal_type(
        self, data: JournalTypeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> JournalType:
        """Create one journal type."""
        row = JournalType(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            row, ConflictError("A journal type with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.journal_type.created",
            entity_type="journal_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code},
        )
        self._session.flush()
        return row

    def list_journal_types(self, *, firm_id: UUID) -> Sequence[JournalType]:
        """Return every journal type owned by the firm."""
        return self._session.scalars(
            self._active(select(JournalType), JournalType, firm_id).order_by(
                JournalType.code.asc()
            )
        ).all()

    def create_voucher_type(
        self, data: VoucherTypeCreate, *, firm_id: UUID, actor_id: UUID
    ) -> VoucherType:
        """Create one voucher type."""
        row = VoucherType(
            firm_id=firm_id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._add_or_conflict(
            row, ConflictError("A voucher type with this code already exists.")
        )
        record_audit(
            self._session,
            action="finance.voucher_type.created",
            entity_type="voucher_type",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code},
        )
        self._session.flush()
        return row

    def list_voucher_types(self, *, firm_id: UUID) -> Sequence[VoucherType]:
        """Return every voucher type owned by the firm."""
        return self._session.scalars(
            self._active(select(VoucherType), VoucherType, firm_id).order_by(
                VoucherType.code.asc()
            )
        ).all()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _reject_overlapping_year(
        self,
        *,
        firm_id: UUID,
        starts_on: object,
        ends_on: object,
        exclude_id: UUID | None = None,
    ) -> None:
        """Reject a financial year that overlaps an existing one."""
        statement = self._active(select(FinancialYear), FinancialYear, firm_id).where(
            FinancialYear.starts_on <= ends_on,
            FinancialYear.ends_on >= starts_on,
        )
        if exclude_id is not None:
            statement = statement.where(FinancialYear.id != exclude_id)
        if self._session.scalar(statement) is not None:
            raise ValidationError(
                "The financial year overlaps an existing financial year."
            )

    def _reject_overlapping_period(
        self,
        *,
        firm_id: UUID,
        starts_on: date,
        ends_on: date,
        exclude_id: UUID | None = None,
    ) -> None:
        """Reject a period that shares any day with another of the firm's.

        Two periods covering one date left posting to pick between them with
        an unordered query (D-FIN-6), so which month a document landed in
        depended on the database's mood. A day belongs to one period.
        """
        statement = self._active(
            select(AccountingPeriod), AccountingPeriod, firm_id
        ).where(
            AccountingPeriod.starts_on <= ends_on,
            AccountingPeriod.ends_on >= starts_on,
        )
        if exclude_id is not None:
            statement = statement.where(AccountingPeriod.id != exclude_id)
        clash = self._session.scalar(
            statement.order_by(AccountingPeriod.starts_on.asc()).limit(1)
        )
        if clash is not None:
            raise ValidationError(
                f"The accounting period {starts_on} to {ends_on} overlaps "
                f"{clash.code} ({clash.starts_on} to {clash.ends_on})."
            )

    def _assert_period_can_move(
        self,
        period: AccountingPeriod,
        *,
        starts_on: date,
        ends_on: date,
        firm_id: UUID,
    ) -> None:
        """Refuse a re-dating that would strand journals or clash (D-FIN-6).

        The update checked only that the end followed the start, so a period
        could leave its year, overlap its neighbour, or stop covering the
        journals posted into it -- whose dates then belonged to no period that
        claimed them. A period with journals keeps its dates; one without must
        stay inside its year and clear of every other period.
        """
        journals = self._session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.accounting_period_id == period.id,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if journals:
            raise ValidationError(
                f"Accounting period {period.code} holds {journals} journal "
                f"entr{'y' if journals == 1 else 'ies'}, so its dates cannot "
                "change."
            )
        year = self.get_financial_year(period.financial_year_id, firm_id=firm_id)
        if starts_on < year.starts_on or ends_on > year.ends_on:
            raise ValidationError(
                "The accounting period must fall inside its financial year."
            )
        self._reject_overlapping_period(
            firm_id=firm_id, starts_on=starts_on, ends_on=ends_on, exclude_id=period.id
        )

    def _active[ModelT](
        self, statement: Select[tuple[ModelT]], model: type[ModelT], firm_id: UUID
    ) -> Select[tuple[ModelT]]:
        """Restrict a statement to live rows owned by the active firm."""
        return statement.where(
            model.firm_id == firm_id,  # type: ignore[attr-defined]
            model.is_deleted.is_(False),  # type: ignore[attr-defined]
        )

    def _soft_delete(self, entity: object, *, actor_id: UUID) -> None:
        """Mark one entity as logically deleted."""
        entity.is_deleted = True  # type: ignore[attr-defined]
        entity.deleted_at = utc_now()  # type: ignore[attr-defined]
        entity.deleted_by = actor_id  # type: ignore[attr-defined]
        entity.updated_by = actor_id  # type: ignore[attr-defined]

    def _add_or_conflict(self, instance: object, conflict: ConflictError) -> None:
        """Insert one row, translating a uniqueness violation into a conflict.

        The savepoint is opened *before* the row is added. ``begin_nested()``
        flushes pending work before emitting the SAVEPOINT, so adding first
        would push the failing INSERT outside the savepoint and defeat it —
        which is exactly what happened on the first two attempts at this.

        Rolling back only to the savepoint matters because this service no
        longer commits after every operation: its router owns the transaction,
        so the bare ``rollback()`` this used to do would discard everything the
        caller had done since its last commit, not just the row that clashed.

        Args:
            instance: The row to insert.
            conflict: The error to raise in place of the database's.

        Raises:
            ConflictError: If the insert violates a uniqueness constraint.

        """
        savepoint = self._session.begin_nested()
        self._session.add(instance)
        try:
            self._session.flush()
        except IntegrityError as error:
            savepoint.rollback()
            raise conflict from error
        savepoint.commit()
