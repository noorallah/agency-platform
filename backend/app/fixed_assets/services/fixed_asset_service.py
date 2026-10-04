"""Fixed assets: classes, the register, depreciation and disposal (PG-13).

An asset reaches the register two ways:

* **From a bill.** A purchase-bill line marked capital goods names an asset
  class; approving the bill raises one asset per such line, at the line's
  value before tax (in rupees), and the bill debits the class's asset account
  instead of leaving the value to the stock accrual. The line puts nothing
  into stock. Its GST is claimed in full with the rest of the bill's.
* **By hand.** An asset the firm already held when it started here (an
  *opening* asset, with the depreciation charged up to ``opening_as_of``) or
  one bought outside a bill. Typing one books nothing: its cost reached the
  ledger by the journal or the opening balance that brought it.

**Depreciation** (Companies Act, Schedule II) is charged by a run over a
period: every active asset, pro rata by days, one journal per run -- Dr the
expense, Cr accumulated depreciation, per pair of accounts. Runs go forward
and never overlap; the latest can be cancelled, which reverses its journal.

**Disposal** first charges depreciation to the day, then takes the asset off
the books: Dr accumulated depreciation, Dr cash or bank for the sale money,
Cr the asset's cost, and the gain or loss to ``ASSET_DISPOSAL_GAIN_LOSS``.

The **Income-tax block schedule** is a view over the same register and posts
nothing (``app/fixed_assets/services/it_block.py``).
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.branches.models import Branch
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_ledger
from app.finance.models import FinancialYear, LedgerAccount
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.fixed_assets.models import (
    AssetClass,
    DepreciationRun,
    DepreciationRunLine,
    FixedAsset,
)
from app.fixed_assets.repositories import FixedAssetRepository
from app.fixed_assets.schemas import (
    AssetClassCreate,
    AssetClassResponse,
    AssetClassUpdate,
    DepreciationRunCreate,
    DepreciationRunLineResponse,
    DepreciationRunResponse,
    FixedAssetCreate,
    FixedAssetDispose,
    FixedAssetResponse,
    FixedAssetSchedule,
    FixedAssetUpdate,
    ItBlockSchedule,
    ItBlockScheduleRow,
    ScheduleEntry,
)
from app.fixed_assets.services.depreciation import (
    HUNDRED,
    ChargeBasis,
    charge_for,
    days_between,
)
from app.fixed_assets.services.it_block import (
    BlockAsset,
    it_block_schedule,
    year_end,
    year_start,
)
from app.products.models import Product
from app.vendors.models import Vendor

ACTIVE = "ACTIVE"
DISPOSED = "DISPOSED"
POSTED = "POSTED"
CANCELLED = "CANCELLED"
PERIODIC = "PERIODIC"
DISPOSAL = "DISPOSAL"
#: The financial year a firm with no year on its books is taken to keep.
_DEFAULT_YEAR_START = date(2000, 4, 1)
#: Fields depreciation is worked out from: fixed once a run charged the asset.
_DEPRECIATION_FIELDS = (
    "asset_class_id",
    "acquisition_date",
    "put_to_use_date",
    "cost",
    "residual_value",
    "opening_accumulated_depreciation",
    "opening_as_of",
    "opening_it_wdv",
)
#: The account type each class override must be.
_ACCOUNT_TYPES = {
    "asset_account_id": "ASSET",
    "accumulated_depreciation_account_id": "ASSET",
    "depreciation_expense_account_id": "EXPENSE",
}
_MONEY_PURPOSE = {
    "CASH": ControlAccountPurpose.CASH,
    "BANK": ControlAccountPurpose.BANK,
}


class FixedAssetService:
    """Keep asset classes and the register; run depreciation; dispose."""

    def __init__(self, session: Session) -> None:
        """Bind the service and its repository to a session it does not own."""
        self._session = session
        self._rows = FixedAssetRepository(session)
        self._controls = ControlAccountService(session)

    # == classes ===========================================================
    def class_page(
        self,
        firm_id: UUID,
        *,
        search: str | None,
        active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AssetClass], int]:
        """Return one page of the firm's asset classes and the total."""
        return self._rows.class_page(
            firm_id, search=search, active=active, page=page, page_size=page_size
        )

    def get_class(self, class_id: UUID, *, firm_id: UUID) -> AssetClass:
        """Return one of the firm's asset classes."""
        row = self._rows.asset_class(class_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("Asset class not found.")
        return row

    def create_class(
        self, data: AssetClassCreate, *, firm_id: UUID, actor_id: UUID
    ) -> AssetClass:
        """Add an asset class and commit.

        Raises:
            ValidationError: If the code is taken, the method lacks what it
                is worked out from, or an account is not the firm's of the
                right type.

        """
        code = data.code.strip().upper()
        if self._rows.class_by_code(firm_id, code) is not None:
            raise ValidationError(f"Asset class {code} already exists.")
        values = data.model_dump()
        _check_rule(
            data.depreciation_method,
            rate=data.rate_percent,
            life=data.useful_life_years,
            residual=data.residual_percent,
        )
        self._check_accounts(values, firm_id=firm_id)
        row = AssetClass(
            firm_id=firm_id,
            **{**values, "code": code, "name": data.name.strip()},
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._flush_or_conflict(f"Asset class {code} already exists.")
        self._audit_class("asset_class.created", row, actor_id)
        self._session.commit()
        return row

    def update_class(
        self,
        class_id: UUID,
        data: AssetClassUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> AssetClass:
        """Change a class; a field left out is left alone; commit.

        A change governs depreciation charged from now on; what was charged
        stands.
        """
        row = self.get_class(class_id, firm_id=firm_id)
        values = data.model_dump(exclude_unset=True)
        for field in (
            "code",
            "name",
            "depreciation_method",
            "residual_percent",
            "it_block_rate_percent",
            "is_active",
        ):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        if "code" in values:
            code = str(values["code"]).strip().upper()
            clash = self._rows.class_by_code(firm_id, code)
            if clash is not None and clash.id != row.id:
                raise ValidationError(f"Asset class {code} already exists.")
            values["code"] = code
        _check_rule(
            values.get("depreciation_method", row.depreciation_method),
            rate=values.get("rate_percent", row.rate_percent),
            life=values.get("useful_life_years", row.useful_life_years),
            residual=values.get("residual_percent", row.residual_percent),
        )
        self._check_accounts(values, firm_id=firm_id)
        for field, value in values.items():
            setattr(row, field, value.strip() if field == "name" else value)
        row.updated_by = actor_id
        self._flush_or_conflict("That asset class code is taken.")
        self._audit_class("asset_class.updated", row, actor_id)
        self._session.commit()
        return row

    def delete_class(self, class_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Remove a class no asset belongs to, and commit.

        Raises:
            ValidationError: If an asset on the register is in the class.

        """
        row = self.get_class(class_id, firm_id=firm_id)
        if self._rows.class_in_use(row.id):
            raise ValidationError(
                f"Asset class {row.code} has assets on the register. Move them "
                "to another class, or mark this one inactive."
            )
        _soft_delete(row, actor_id)
        self._audit_class("asset_class.deleted", row, actor_id)
        self._session.commit()

    @staticmethod
    def class_responses(rows: list[AssetClass]) -> list[AssetClassResponse]:
        """Shape asset classes; they hang nothing off themselves."""
        return [AssetClassResponse.model_validate(row) for row in rows]

    # == assets ============================================================
    def page(
        self,
        firm_id: UUID,
        *,
        search: str | None,
        status: str | None,
        asset_class_id: UUID | None,
        branch_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[FixedAsset], int]:
        """Return one page of the register and the total."""
        return self._rows.asset_page(
            firm_id,
            search=search,
            status=status,
            asset_class_id=asset_class_id,
            branch_id=branch_id,
            page=page,
            page_size=page_size,
        )

    def get(self, asset_id: UUID, *, firm_id: UUID) -> FixedAsset:
        """Return one asset on the firm's register."""
        row = self._rows.asset(asset_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("Fixed asset not found.")
        return row

    def create(
        self, data: FixedAssetCreate, *, firm_id: UUID, actor_id: UUID
    ) -> FixedAsset:
        """Put an asset on the register by hand and commit."""
        row = self.stage_create(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_create(
        self, data: FixedAssetCreate, *, firm_id: UUID, actor_id: UUID
    ) -> FixedAsset:
        """Put an asset on the register by hand; flush, do not commit.

        Raises:
            ValidationError: If the class, supplier or branch is not the
                firm's, or the dates and opening figures disagree.

        """
        klass = self._usable_class(data.asset_class_id, firm_id)
        self._check_vendor(data.vendor_id, firm_id)
        self._check_branch(data.branch_id, firm_id)
        cost = quantize_ledger(data.cost)
        residual = (
            quantize_ledger(data.residual_value)
            if data.residual_value is not None
            else quantize_ledger(cost * klass.residual_percent / HUNDRED)
        )
        row = FixedAsset(
            firm_id=firm_id,
            asset_number=self._next_asset_number(firm_id),
            name=data.name.strip(),
            asset_class_id=klass.id,
            vendor_id=data.vendor_id,
            acquisition_date=data.acquisition_date,
            put_to_use_date=data.put_to_use_date or data.acquisition_date,
            quantity=data.quantity,
            cost=cost,
            residual_value=residual,
            opening_accumulated_depreciation=quantize_ledger(
                data.opening_accumulated_depreciation
            ),
            opening_as_of=data.opening_as_of,
            opening_it_wdv=(
                quantize_ledger(data.opening_it_wdv)
                if data.opening_it_wdv is not None
                else None
            ),
            branch_id=data.branch_id,
            location=data.location,
            remarks=data.remarks,
            status=ACTIVE,
            created_by=actor_id,
            updated_by=actor_id,
        )
        _check_asset(row)
        self._session.add(row)
        self._flush_or_conflict("That asset number is taken; save again.")
        self._audit("fixed_asset.created", row, actor_id)
        return row

    def update(
        self,
        asset_id: UUID,
        data: FixedAssetUpdate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> FixedAsset:
        """Change an active asset; a field left out is left alone; commit.

        Raises:
            ValidationError: If the asset was disposed, or a field depreciation
                is worked out from changes after a run charged the asset, or a
                bill's asset is given another cost.

        """
        row = self.get(asset_id, firm_id=firm_id)
        if row.status != ACTIVE:
            raise ValidationError(f"Asset {row.asset_number} was disposed.")
        values = data.model_dump(exclude_unset=True)
        for field in (
            "name",
            "asset_class_id",
            "acquisition_date",
            "put_to_use_date",
            "cost",
            "residual_value",
            "opening_accumulated_depreciation",
        ):
            if field in values and values[field] is None:
                raise ValidationError(f"{field} cannot be blank.")
        moving = [
            field
            for field in _DEPRECIATION_FIELDS
            if field in values and values[field] != getattr(row, field)
        ]
        if moving and self._rows.charged([row.id]):
            raise ValidationError(
                f"Asset {row.asset_number} has been depreciated, so "
                f"{', '.join(moving)} cannot change. Cancel the runs that "
                "charged it first."
            )
        if (
            row.purchase_invoice_id is not None
            and "cost" in values
            and values["cost"] != row.cost
        ):
            raise ValidationError(
                f"Asset {row.asset_number} costs what its bill charged; change "
                "the bill, not the asset."
            )
        if "asset_class_id" in values:
            self._usable_class(values["asset_class_id"], firm_id)
        if "branch_id" in values:
            self._check_branch(values["branch_id"], firm_id)
        for field, value in values.items():
            if field in ("cost", "residual_value", "opening_accumulated_depreciation"):
                value = quantize_ledger(value)
            setattr(row, field, value.strip() if field == "name" else value)
        _check_asset(row)
        row.updated_by = actor_id
        self._audit("fixed_asset.updated", row, actor_id)
        self._session.commit()
        return row

    def delete(self, asset_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Take a hand-typed asset off the register, and commit.

        Raises:
            ValidationError: If a bill raised it (cancel the bill), it was
                depreciated, or it was disposed.

        """
        row = self.get(asset_id, firm_id=firm_id)
        if row.purchase_invoice_id is not None:
            raise ValidationError(
                f"Asset {row.asset_number} was raised by a bill; cancelling the "
                "bill takes it off the register."
            )
        if row.status != ACTIVE or self._rows.charged([row.id]):
            raise ValidationError(
                f"Asset {row.asset_number} has been depreciated or disposed, so "
                "it stays on the register."
            )
        _soft_delete(row, actor_id)
        self._audit("fixed_asset.deleted", row, actor_id)
        self._session.commit()

    def responses(
        self, rows: list[FixedAsset], *, as_of: date | None = None
    ) -> list[FixedAssetResponse]:
        """Shape assets with what they stand at, reading each table once."""
        if not rows:
            return []
        classes = self._rows.classes(row.asset_class_id for row in rows)
        charged = self._rows.charged((row.id for row in rows), as_of=as_of)
        invoices = self._rows.invoice_numbers(row.purchase_invoice_id for row in rows)
        shaped = []
        for row in rows:
            klass = classes.get(row.asset_class_id)
            total, last = charged.get(row.id, (ZERO, None))
            accumulated = Decimal(str(row.opening_accumulated_depreciation)) + total
            shaped.append(
                FixedAssetResponse(
                    id=row.id,
                    asset_number=row.asset_number,
                    name=row.name,
                    asset_class_id=row.asset_class_id,
                    asset_class_code=klass.code if klass else "",
                    asset_class_name=klass.name if klass else "",
                    purchase_invoice_id=row.purchase_invoice_id,
                    purchase_invoice_line_id=row.purchase_invoice_line_id,
                    purchase_invoice_number=(
                        invoices.get(row.purchase_invoice_id)
                        if row.purchase_invoice_id
                        else None
                    ),
                    vendor_id=row.vendor_id,
                    acquisition_date=row.acquisition_date,
                    put_to_use_date=row.put_to_use_date,
                    quantity=row.quantity,
                    cost=row.cost,
                    residual_value=row.residual_value,
                    opening_accumulated_depreciation=(
                        row.opening_accumulated_depreciation
                    ),
                    opening_as_of=row.opening_as_of,
                    opening_it_wdv=row.opening_it_wdv,
                    accumulated_depreciation=quantize_ledger(accumulated),
                    net_book_value=quantize_ledger(
                        Decimal(str(row.cost)) - accumulated
                    ),
                    depreciated_to=last or row.opening_as_of,
                    branch_id=row.branch_id,
                    location=row.location,
                    status=row.status,
                    disposed_on=row.disposed_on,
                    sale_amount=row.sale_amount,
                    disposal_method=row.disposal_method,
                    disposal_reason=row.disposal_reason,
                    disposal_gain_loss=row.disposal_gain_loss,
                    disposal_journal_entry_id=row.disposal_journal_entry_id,
                    remarks=row.remarks,
                    version=row.version,
                )
            )
        return shaped

    # -- from a bill ---------------------------------------------------------
    def stage_from_invoice(
        self,
        *,
        firm_id: UUID,
        invoice_id: UUID,
        invoice_date: date,
        vendor_id: UUID | None,
        branch_id: UUID | None,
        lines: list[tuple[UUID, UUID, UUID, str | None, Decimal, Decimal]],
        actor_id: UUID,
    ) -> list[tuple[UUID, Decimal]]:
        """Raise one asset per capital-goods line of an approved bill; flush.

        Args:
            firm_id: The owning firm.
            invoice_id: The bill being approved.
            invoice_date: Its date: the asset's acquisition and, until the
                firm says otherwise, put-to-use date.
            vendor_id: The supplier.
            branch_id: The bill's branch, where the asset is taken to be.
            lines: One (line id, asset class id, product id, description,
                quantity, rupee value before tax) per capital-goods line.
            actor_id: The approving user.

        Returns:
            One (asset account, value) per line, for the bill's journal.

        Raises:
            ValidationError: If a class is not the firm's or is inactive, or
                the firm has no fixed-asset account to debit.

        """
        if not lines:
            return []
        products = {
            row.id: row.name
            for row in self._session.scalars(
                select(Product).where(Product.id.in_({line[2] for line in lines}))
            ).all()
        }
        legs: list[tuple[UUID, Decimal]] = []
        for line_id, class_id, product_id, description, quantity, value in lines:
            klass = self._usable_class(class_id, firm_id)
            cost = quantize_ledger(value)
            row = FixedAsset(
                firm_id=firm_id,
                asset_number=self._next_asset_number(firm_id),
                name=(description or products.get(product_id) or "Asset")[:200],
                asset_class_id=klass.id,
                purchase_invoice_id=invoice_id,
                purchase_invoice_line_id=line_id,
                vendor_id=vendor_id,
                acquisition_date=invoice_date,
                put_to_use_date=invoice_date,
                quantity=quantity,
                cost=cost,
                residual_value=quantize_ledger(cost * klass.residual_percent / HUNDRED),
                branch_id=branch_id,
                status=ACTIVE,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(row)
            self._session.flush()
            self._audit("fixed_asset.created", row, actor_id)
            legs.append((self._account(klass, "asset_account_id", firm_id), cost))
        return legs

    def stage_withdraw_for_invoice(
        self, invoice_id: UUID, *, invoice_number: str, actor_id: UUID
    ) -> None:
        """Take a cancelled bill's assets off the register; flush.

        Raises:
            ValidationError: If one has been depreciated or disposed: the bill
                cannot be cancelled under it.

        """
        assets = self._rows.assets_of_invoice(invoice_id)
        charged = self._rows.charged(asset.id for asset in assets)
        for asset in assets:
            if asset.status != ACTIVE or asset.id in charged:
                raise ValidationError(
                    f"Bill {invoice_number} raised asset {asset.asset_number}, "
                    "which has been depreciated or disposed. Cancel its "
                    "depreciation runs first; a disposed asset keeps its bill."
                )
        for asset in assets:
            _soft_delete(asset, actor_id)
            self._audit("fixed_asset.withdrawn", asset, actor_id)
        self._session.flush()

    # == depreciation runs ==================================================
    def run_page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        run_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DepreciationRun], int]:
        """Return one page of the firm's depreciation runs and the total."""
        return self._rows.run_page(
            firm_id, status=status, run_type=run_type, page=page, page_size=page_size
        )

    def get_run(self, run_id: UUID, *, firm_id: UUID) -> DepreciationRun:
        """Return one of the firm's depreciation runs."""
        row = self._rows.run(run_id, firm_id=firm_id)
        if row is None:
            raise ResourceNotFoundError("Depreciation run not found.")
        return row

    def run(
        self, data: DepreciationRunCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DepreciationRun:
        """Charge the period's depreciation on every active asset; commit."""
        row = self.stage_run(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_run(
        self, data: DepreciationRunCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DepreciationRun:
        """Charge the period's depreciation and post it; flush only.

        Raises:
            ValidationError: If the period is back to front, overlaps a posted
                run or lies before the latest, or nothing is due in it.

        """
        if data.period_from > data.period_to:
            raise ValidationError("The period ends before it starts.")
        clash = self._rows.overlapping_run(
            firm_id, period_from=data.period_from, period_to=data.period_to
        )
        if clash is not None:
            raise ValidationError(
                f"Depreciation run {clash.run_number} already charged "
                f"{clash.period_from.isoformat()} to {clash.period_to.isoformat()}. "
                "Cancel it, or run a period after it."
            )
        latest = self._rows.latest_run(firm_id)
        if latest is not None and data.period_from < latest.period_to:
            raise ValidationError(
                f"Runs go forward: {latest.run_number} charged up to "
                f"{latest.period_to.isoformat()}. Cancel it to run an earlier "
                "period."
            )
        assets = self._rows.active_assets(firm_id)
        classes = self._rows.classes(asset.asset_class_id for asset in assets)
        charged = self._rows.charged(asset.id for asset in assets)
        planned: list[tuple[FixedAsset, date, int, Decimal, Decimal]] = []
        for asset in assets:
            total, last = charged.get(asset.id, (ZERO, None))
            start = max(data.period_from, _depreciates_from(asset, last))
            if start > data.period_to:
                continue
            days = days_between(start, data.period_to)
            book = _book_value(asset, total)
            amount = charge_for(
                _basis(asset, classes[asset.asset_class_id]),
                book_value=book,
                days=days,
            )
            if amount > ZERO:
                planned.append((asset, start, days, book, amount))
        if not planned:
            raise ValidationError(
                f"No asset is due any depreciation from "
                f"{data.period_from.isoformat()} to {data.period_to.isoformat()}."
            )
        run = self._new_run(
            firm_id,
            run_type=PERIODIC,
            period_from=data.period_from,
            period_to=data.period_to,
            remarks=data.remarks,
            actor_id=actor_id,
        )
        self._post_lines(run, planned, classes, actor_id=actor_id)
        self._audit_run("depreciation_run.posted", run, actor_id)
        self._session.flush()
        return run

    def cancel_run(
        self, run_id: UUID, reason: str, *, firm_id: UUID, actor_id: UUID
    ) -> DepreciationRun:
        """Take a periodic run back, reversing its journal; commit.

        Raises:
            ValidationError: If it is already cancelled, is a disposal's own
                charge, a later run charged one of its assets, or one of them
                has since been disposed.

        """
        run = self.get_run(run_id, firm_id=firm_id)
        if run.status != POSTED:
            raise ValidationError(f"Run {run.run_number} was already cancelled.")
        if not reason.strip():
            raise ValidationError("Say why the run is cancelled.")
        if run.run_type != PERIODIC:
            raise ValidationError(
                f"Run {run.run_number} charged a disposal and stands with it."
            )
        asset_ids = [
            line.fixed_asset_id for line in self._rows.run_lines([run.id])[run.id]
        ]
        if self._rows.charged_after(
            asset_ids, after=run.period_to, except_run_id=run.id
        ):
            raise ValidationError(
                f"A later run charged assets {run.run_number} charged. Cancel "
                "the later runs first, latest first."
            )
        disposed = [
            asset.asset_number
            for asset in self._rows.assets(asset_ids).values()
            if asset.status == DISPOSED
        ]
        if disposed:
            raise ValidationError(
                f"{', '.join(sorted(disposed))} has since been disposed at the "
                f"book value {run.run_number} left, so the run stands."
            )
        if run.journal_entry_id is not None:
            reversal = JournalEntryEngine(self._session).reverse_entry(
                run.journal_entry_id,
                firm_id=firm_id,
                reference_number=f"{run.run_number}-REV",
                actor_id=actor_id,
            )
            run.reversal_journal_entry_id = reversal.id
        run.status = CANCELLED
        run.cancel_reason = reason.strip()
        run.updated_by = actor_id
        self._audit_run("depreciation_run.cancelled", run, actor_id)
        self._session.commit()
        return run

    def run_responses(
        self, rows: list[DepreciationRun]
    ) -> list[DepreciationRunResponse]:
        """Shape runs with their lines, reading each table once."""
        if not rows:
            return []
        lines = self._rows.run_lines(row.id for row in rows)
        assets = self._rows.assets(
            line.fixed_asset_id for group in lines.values() for line in group
        )
        shaped = []
        for row in rows:
            shaped.append(
                DepreciationRunResponse(
                    id=row.id,
                    run_number=row.run_number,
                    run_type=row.run_type,
                    book=row.book,
                    period_from=row.period_from,
                    period_to=row.period_to,
                    status=row.status,
                    total_amount=row.total_amount,
                    journal_entry_id=row.journal_entry_id,
                    reversal_journal_entry_id=row.reversal_journal_entry_id,
                    posted_at=row.posted_at,
                    remarks=row.remarks,
                    cancel_reason=row.cancel_reason,
                    version=row.version,
                    lines=[
                        DepreciationRunLineResponse(
                            id=line.id,
                            fixed_asset_id=line.fixed_asset_id,
                            asset_number=(
                                assets[line.fixed_asset_id].asset_number
                                if line.fixed_asset_id in assets
                                else ""
                            ),
                            asset_name=(
                                assets[line.fixed_asset_id].name
                                if line.fixed_asset_id in assets
                                else ""
                            ),
                            asset_class_id=line.asset_class_id,
                            from_date=line.from_date,
                            to_date=line.to_date,
                            days=line.days,
                            opening_book_value=line.opening_book_value,
                            amount=line.amount,
                        )
                        for line in lines.get(row.id, [])
                    ],
                )
            )
        return shaped

    # == disposal ===========================================================
    def dispose(
        self,
        asset_id: UUID,
        data: FixedAssetDispose,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> FixedAsset:
        """Sell or scrap an asset and commit."""
        row = self.stage_dispose(asset_id, data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_dispose(
        self,
        asset_id: UUID,
        data: FixedAssetDispose,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> FixedAsset:
        """Charge depreciation to the day, then take the asset off; flush.

        Raises:
            ValidationError: If it was already disposed, the date is before it
                was bought or before depreciation already charged, or an
                account is missing.

        """
        asset = self.get(asset_id, firm_id=firm_id)
        if asset.status != ACTIVE:
            raise ValidationError(f"Asset {asset.asset_number} was already disposed.")
        on = data.disposal_date
        if on < asset.acquisition_date:
            raise ValidationError(
                f"Asset {asset.asset_number} was acquired on "
                f"{asset.acquisition_date.isoformat()}; it cannot leave before."
            )
        if asset.opening_as_of is not None and on <= asset.opening_as_of:
            raise ValidationError(
                f"Asset {asset.asset_number} was brought in as held on "
                f"{asset.opening_as_of.isoformat()}; dispose of it after that."
            )
        total, last = self._rows.charged([asset.id]).get(asset.id, (ZERO, None))
        if last is not None and on < last:
            raise ValidationError(
                f"Depreciation on {asset.asset_number} is charged to "
                f"{last.isoformat()}. Dispose of it on or after that day, or "
                "cancel the runs that charged past it."
            )
        klass = self.get_class(asset.asset_class_id, firm_id=firm_id)
        start = _depreciates_from(asset, last)
        charge = ZERO
        if start <= on:
            book = _book_value(asset, total)
            days = days_between(start, on)
            charge = charge_for(_basis(asset, klass), book_value=book, days=days)
            if charge > ZERO:
                run = self._new_run(
                    firm_id,
                    run_type=DISPOSAL,
                    period_from=start,
                    period_to=on,
                    remarks=f"Depreciation to the disposal of {asset.asset_number}",
                    actor_id=actor_id,
                )
                self._post_lines(
                    run,
                    [(asset, start, days, book, charge)],
                    {klass.id: klass},
                    actor_id=actor_id,
                )
                self._audit_run("depreciation_run.posted", run, actor_id)
        cost = Decimal(str(asset.cost))
        accumulated = (
            Decimal(str(asset.opening_accumulated_depreciation)) + total + charge
        )
        sale = quantize_ledger(data.sale_amount)
        entry = DocumentPostingService(self._session).post_asset_disposal(
            firm_id=firm_id,
            asset_id=asset.id,
            reference_number=asset.asset_number,
            on=on,
            asset_account_id=self._account(klass, "asset_account_id", firm_id),
            accumulated_account_id=self._account(
                klass, "accumulated_depreciation_account_id", firm_id
            ),
            money_account_id=self._controls.resolve(
                firm_id, _MONEY_PURPOSE[data.method]
            ),
            cost=cost,
            accumulated=accumulated,
            sale_amount=sale,
            actor_id=actor_id,
        )
        before = asset.status
        asset.status = DISPOSED
        asset.disposed_on = on
        asset.sale_amount = sale
        asset.disposal_method = data.method
        asset.disposal_reason = data.reason.strip()
        asset.disposal_gain_loss = quantize_ledger(sale - (cost - accumulated))
        asset.disposal_journal_entry_id = entry.id
        asset.updated_by = actor_id
        self._audit("fixed_asset.disposed", asset, actor_id, before_status=before)
        self._session.flush()
        return asset

    # == reports ============================================================
    def schedule(self, asset_id: UUID, *, firm_id: UUID) -> FixedAssetSchedule:
        """Return what was charged on an asset, then what is still to come."""
        asset = self.get(asset_id, firm_id=firm_id)
        klass = self.get_class(asset.asset_class_id, firm_id=firm_id)
        accumulated = Decimal(str(asset.opening_accumulated_depreciation))
        cost = Decimal(str(asset.cost))
        charged: list[ScheduleEntry] = []
        last: date | None = None
        for line, number in self._rows.lines_of_asset(asset.id):
            accumulated += Decimal(str(line.amount))
            charged.append(
                ScheduleEntry(
                    from_date=line.from_date,
                    to_date=line.to_date,
                    days=line.days,
                    opening_book_value=line.opening_book_value,
                    amount=line.amount,
                    accumulated_depreciation=quantize_ledger(accumulated),
                    closing_book_value=quantize_ledger(cost - accumulated),
                    depreciation_run_id=line.depreciation_run_id,
                    run_number=number,
                )
            )
            last = line.to_date if last is None else max(last, line.to_date)
        projected: list[ScheduleEntry] = []
        if asset.status == ACTIVE:
            anchor = self._year_anchor(firm_id)
            start = _depreciates_from(asset, last)
            basis = _basis(asset, klass)
            for _ in range(100):
                end = year_end(year_start(start, anchor))
                book = cost - accumulated
                days = days_between(start, end)
                amount = charge_for(basis, book_value=book, days=days)
                if amount <= ZERO:
                    break
                accumulated += amount
                projected.append(
                    ScheduleEntry(
                        from_date=start,
                        to_date=end,
                        days=days,
                        opening_book_value=quantize_ledger(book),
                        amount=amount,
                        accumulated_depreciation=quantize_ledger(accumulated),
                        closing_book_value=quantize_ledger(cost - accumulated),
                        projected=True,
                    )
                )
                start = end + timedelta(days=1)
        return FixedAssetSchedule(
            fixed_asset_id=asset.id,
            asset_number=asset.asset_number,
            depreciation_method=klass.depreciation_method,
            cost=asset.cost,
            residual_value=asset.residual_value,
            opening_accumulated_depreciation=asset.opening_accumulated_depreciation,
            charged=charged,
            projected=projected,
        )

    def it_block_schedule(
        self, financial_year_id: UUID, *, firm_id: UUID
    ) -> ItBlockSchedule:
        """Return the Income-tax block schedule of one of the firm's years."""
        year = self._session.get(FinancialYear, financial_year_id)
        if year is None or year.is_deleted or year.firm_id != firm_id:
            raise ResourceNotFoundError("Financial year not found.")
        assets = self._rows.all_assets(firm_id)
        classes = self._rows.classes(asset.asset_class_id for asset in assets)
        members = []
        for asset in assets:
            klass = classes[asset.asset_class_id]
            opening_from = (
                asset.opening_as_of + timedelta(days=1)
                if asset.opening_as_of is not None
                else None
            )
            members.append(
                BlockAsset(
                    block_rate=Decimal(str(klass.it_block_rate_percent)),
                    class_name=klass.name,
                    put_to_use_date=asset.put_to_use_date,
                    cost=Decimal(str(asset.cost)),
                    opening_from=opening_from,
                    opening_wdv=(
                        Decimal(str(asset.opening_it_wdv))
                        if asset.opening_it_wdv is not None
                        else Decimal(str(asset.cost))
                        - Decimal(str(asset.opening_accumulated_depreciation))
                    ),
                    disposed_on=asset.disposed_on,
                    sale_amount=Decimal(str(asset.sale_amount or ZERO)),
                )
            )
        rows = it_block_schedule(members, year_starts_on=year.starts_on)
        return ItBlockSchedule(
            financial_year_id=year.id,
            starts_on=year.starts_on,
            ends_on=year.ends_on,
            blocks=[ItBlockScheduleRow.model_validate(row) for row in rows],
        )

    # == helpers ============================================================
    def _new_run(
        self,
        firm_id: UUID,
        *,
        run_type: str,
        period_from: date,
        period_to: date,
        remarks: str | None,
        actor_id: UUID,
    ) -> DepreciationRun:
        """Add a posted run header and flush it."""
        number = self._rows.next_number(firm_id, DepreciationRun)
        run = DepreciationRun(
            firm_id=firm_id,
            run_number=f"DEP-{number:05d}",
            run_type=run_type,
            book="COMPANIES_ACT",
            period_from=period_from,
            period_to=period_to,
            status=POSTED,
            posted_at=utc_now(),
            remarks=remarks,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(run)
        self._flush_or_conflict("That run number is taken; run it again.")
        return run

    def _post_lines(
        self,
        run: DepreciationRun,
        planned: list[tuple[FixedAsset, date, int, Decimal, Decimal]],
        classes: dict[UUID, AssetClass],
        *,
        actor_id: UUID,
    ) -> None:
        """Write a run's lines and post its journal, per pair of accounts."""
        legs: dict[tuple[UUID, UUID], Decimal] = defaultdict(lambda: ZERO)
        for asset, start, days, book, amount in planned:
            klass = classes[asset.asset_class_id]
            self._session.add(
                DepreciationRunLine(
                    depreciation_run_id=run.id,
                    firm_id=run.firm_id,
                    fixed_asset_id=asset.id,
                    asset_class_id=klass.id,
                    from_date=start,
                    to_date=run.period_to,
                    days=days,
                    opening_book_value=quantize_ledger(book),
                    amount=amount,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            pair = (
                self._account(klass, "depreciation_expense_account_id", run.firm_id),
                self._account(
                    klass, "accumulated_depreciation_account_id", run.firm_id
                ),
            )
            legs[pair] += amount
        run.total_amount = sum(legs.values(), ZERO)
        entry = DocumentPostingService(self._session).post_depreciation(
            firm_id=run.firm_id,
            run_id=run.id,
            reference_number=run.run_number,
            on=run.period_to,
            legs=[
                (expense, accumulated, value)
                for (expense, accumulated), value in legs.items()
            ],
            actor_id=actor_id,
        )
        run.journal_entry_id = entry.id

    def _account(self, klass: AssetClass, field: str, firm_id: UUID) -> UUID:
        """Return the class's own account for ``field``, else the firm's."""
        own: UUID | None = getattr(klass, field)
        if own is not None:
            return own
        purpose = {
            "asset_account_id": ControlAccountPurpose.FIXED_ASSET_COST,
            "accumulated_depreciation_account_id": (
                ControlAccountPurpose.ACCUMULATED_DEPRECIATION
            ),
            "depreciation_expense_account_id": (
                ControlAccountPurpose.DEPRECIATION_EXPENSE
            ),
        }[field]
        return self._controls.resolve(firm_id, purpose)

    def _check_accounts(self, values: dict[str, object], *, firm_id: UUID) -> None:
        """Refuse an override that is not the firm's live account of its type."""
        for field, kind in _ACCOUNT_TYPES.items():
            account_id = values.get(field)
            if account_id is None:
                continue
            account = self._session.get(LedgerAccount, account_id)
            if account is None or account.is_deleted or account.firm_id != firm_id:
                raise ValidationError(f"{field} is not one of this firm's accounts.")
            if account.account_type != kind:
                raise ValidationError(
                    f"{field} must be an {kind.lower()} account; {account.code} "
                    f"is {account.account_type.lower()}."
                )

    def _usable_class(self, class_id: UUID, firm_id: UUID) -> AssetClass:
        """Return a live, active class of the firm, or refuse."""
        klass = self._rows.asset_class(class_id, firm_id=firm_id)
        if klass is None:
            raise ValidationError("The asset class is not one of this firm's.")
        if not klass.is_active:
            raise ValidationError(f"Asset class {klass.code} is inactive.")
        return klass

    def _check_vendor(self, vendor_id: UUID | None, firm_id: UUID) -> None:
        """Refuse a supplier that is not the firm's."""
        if vendor_id is None:
            return
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.is_deleted or vendor.firm_id != firm_id:
            raise ValidationError("The supplier is not one of this firm's.")

    def _check_branch(self, branch_id: UUID | None, firm_id: UUID) -> None:
        """Refuse a branch that is not the firm's."""
        if branch_id is None:
            return
        branch = self._session.get(Branch, branch_id)
        if branch is None or branch.is_deleted or branch.firm_id != firm_id:
            raise ValidationError("The branch is not one of this firm's.")

    def _next_asset_number(self, firm_id: UUID) -> str:
        """Return the next asset number of the firm."""
        return f"FA-{self._rows.next_number(firm_id, FixedAsset):05d}"

    def _year_anchor(self, firm_id: UUID) -> date:
        """Return a first day of the firm's financial year, from its books."""
        starts = self._session.scalar(
            select(FinancialYear.starts_on)
            .where(
                FinancialYear.firm_id == firm_id,
                FinancialYear.is_deleted.is_(False),
            )
            .order_by(FinancialYear.starts_on.desc())
            .limit(1)
        )
        return starts or _DEFAULT_YEAR_START

    def _flush_or_conflict(self, message: str) -> None:
        """Flush, turning a unique-key clash into a 409 naming it."""
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    def _audit(
        self,
        action: str,
        row: FixedAsset,
        actor_id: UUID,
        *,
        before_status: str | None = None,
    ) -> None:
        """Write one audit row for an asset."""
        record_audit(
            self._session,
            action=action,
            entity_type="fixed_asset",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data=(
                {"status": before_status} if before_status is not None else None
            ),
            after_data={
                "asset_number": row.asset_number,
                "name": row.name,
                "asset_class_id": str(row.asset_class_id),
                "cost": str(row.cost),
                "put_to_use_date": row.put_to_use_date.isoformat(),
                "purchase_invoice_id": (
                    str(row.purchase_invoice_id) if row.purchase_invoice_id else None
                ),
                "status": row.status,
                "disposed_on": (
                    row.disposed_on.isoformat() if row.disposed_on else None
                ),
                "sale_amount": (
                    str(row.sale_amount) if row.sale_amount is not None else None
                ),
                "disposal_reason": row.disposal_reason,
            },
        )

    def _audit_class(self, action: str, row: AssetClass, actor_id: UUID) -> None:
        """Write one audit row for an asset class."""
        record_audit(
            self._session,
            action=action,
            entity_type="asset_class",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "code": row.code,
                "name": row.name,
                "depreciation_method": row.depreciation_method,
                "rate_percent": (
                    str(row.rate_percent) if row.rate_percent is not None else None
                ),
                "useful_life_years": (
                    str(row.useful_life_years)
                    if row.useful_life_years is not None
                    else None
                ),
                "residual_percent": str(row.residual_percent),
                "it_block_rate_percent": str(row.it_block_rate_percent),
                "is_active": row.is_active,
            },
        )

    def _audit_run(self, action: str, row: DepreciationRun, actor_id: UUID) -> None:
        """Write one audit row for a depreciation run."""
        record_audit(
            self._session,
            action=action,
            entity_type="depreciation_run",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            after_data={
                "run_number": row.run_number,
                "run_type": row.run_type,
                "period_from": row.period_from.isoformat(),
                "period_to": row.period_to.isoformat(),
                "total_amount": str(row.total_amount),
                "status": row.status,
                "cancel_reason": row.cancel_reason,
            },
        )


def _check_rule(
    method: str,
    *,
    rate: Decimal | None,
    life: Decimal | None,
    residual: Decimal | None,
) -> None:
    """Refuse a class whose method lacks what it is worked out from."""
    if method == "SLM" and rate is None and life is None:
        raise ValidationError("Straight line needs a useful life or a rate.")
    if method == "WDV" and rate is None and (life is None or not residual):
        raise ValidationError(
            "Written-down value needs a rate, or a useful life and a residual "
            "percent to derive one from."
        )


def _check_asset(row: FixedAsset) -> None:
    """Refuse dates and opening figures that disagree."""
    if row.put_to_use_date < row.acquisition_date:
        raise ValidationError("An asset cannot be put to use before it is acquired.")
    if Decimal(str(row.residual_value)) > Decimal(str(row.cost)):
        raise ValidationError("The residual value cannot exceed the cost.")
    opening = Decimal(str(row.opening_accumulated_depreciation))
    if (opening > ZERO or row.opening_it_wdv is not None) and row.opening_as_of is None:
        raise ValidationError(
            "Say the day the opening depreciation was charged to (opening_as_of)."
        )
    if opening > Decimal(str(row.cost)) - Decimal(str(row.residual_value)):
        raise ValidationError(
            "The opening depreciation cannot take the asset below its residual "
            "value."
        )
    if row.opening_as_of is not None and row.opening_as_of < row.acquisition_date:
        raise ValidationError("An asset cannot be held before it was acquired.")


def _depreciates_from(asset: FixedAsset, charged_to: date | None) -> date:
    """Return the first day not yet charged: after use began, the opening and runs."""
    start = asset.put_to_use_date
    if asset.opening_as_of is not None:
        start = max(start, asset.opening_as_of + timedelta(days=1))
    if charged_to is not None:
        start = max(start, charged_to + timedelta(days=1))
    return start


def _book_value(asset: FixedAsset, charged: Decimal) -> Decimal:
    """Return cost less opening depreciation and every posted charge."""
    return (
        Decimal(str(asset.cost))
        - Decimal(str(asset.opening_accumulated_depreciation))
        - charged
    )


def _basis(asset: FixedAsset, klass: AssetClass) -> ChargeBasis:
    """Return what the asset's charge is worked out from."""
    return ChargeBasis(
        method=klass.depreciation_method,
        cost=Decimal(str(asset.cost)),
        residual_value=Decimal(str(asset.residual_value)),
        rate_percent=(
            Decimal(str(klass.rate_percent)) if klass.rate_percent is not None else None
        ),
        useful_life_years=(
            Decimal(str(klass.useful_life_years))
            if klass.useful_life_years is not None
            else None
        ),
    )


def _soft_delete(row: AssetClass | FixedAsset, actor_id: UUID) -> None:
    """Mark a row deleted, by whom and when."""
    row.is_deleted = True
    row.deleted_at = utc_now()
    row.deleted_by = actor_id
    row.updated_by = actor_id
