"""Transactional application service for finance master data.

The service owns the accounting calendar and the chart of accounts. Journal
posting lives in :mod:`app.finance.services.journal_engine` and reporting in
:mod:`app.finance.services.general_ledger_service`.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
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
            raise ValidationError("A locked financial year cannot be modified.")
        before = {"name": year.name, "is_active": year.is_active}
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
            after_data={"name": year.name, "is_active": year.is_active},
        )
        self._session.flush()
        return year

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
        if data.starts_on < year.starts_on or data.ends_on > year.ends_on:
            raise ValidationError(
                "The accounting period must fall inside its financial year."
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
        before: dict[str, object] = {"status": period.status, "name": period.name}
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
        if data.starts_on is not None:
            period.starts_on = data.starts_on
        if data.ends_on is not None:
            period.ends_on = data.ends_on
        if period.ends_on <= period.starts_on:
            raise ValidationError("Accounting period must end after it starts.")
        if data.status is not None:
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
            after_data={"status": period.status, "name": period.name},
        )
        self._session.flush()
        return period

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
        before = {"name": group.name, "is_active": group.is_active}
        if data.parent_group_id is not None:
            if data.parent_group_id == group.id:
                raise ValidationError("An account group cannot be its own parent.")
            self.get_account_group(data.parent_group_id, firm_id=firm_id)
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
            after_data={"name": group.name, "is_active": group.is_active},
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
        before = {"name": account.name, "is_active": account.is_active}
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
            after_data={"name": account.name, "is_active": account.is_active},
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
            after_data={"name": centre.name, "is_active": centre.is_active},
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
            after_data={"name": centre.name, "is_active": centre.is_active},
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
