"""Soft-delete-aware reads for fixed assets (PG-13)."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.fixed_assets.models import (
    AssetClass,
    DepreciationRun,
    DepreciationRunLine,
    FixedAsset,
)
from app.purchase_invoice.models import PurchaseInvoice

POSTED = "POSTED"


class FixedAssetRepository:
    """Read classes, assets and runs, each table once per call."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session it does not own."""
        self._session = session

    # -- classes ---------------------------------------------------------
    def asset_class(self, class_id: UUID, *, firm_id: UUID) -> AssetClass | None:
        """Return one live class of the firm, or None."""
        row = self._session.get(AssetClass, class_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def class_by_code(self, firm_id: UUID, code: str) -> AssetClass | None:
        """Return the firm's live class with this code, any case."""
        return self._session.scalar(
            select(AssetClass).where(
                AssetClass.firm_id == firm_id,
                AssetClass.is_deleted.is_(False),
                func.upper(AssetClass.code) == code.upper(),
            )
        )

    def class_page(
        self,
        firm_id: UUID,
        *,
        search: str | None,
        active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AssetClass], int]:
        """Return one page of the firm's classes by code, and the total."""
        query: Select[tuple[AssetClass]] = select(AssetClass).where(
            AssetClass.firm_id == firm_id, AssetClass.is_deleted.is_(False)
        )
        if active is not None:
            query = query.where(AssetClass.is_active.is_(active))
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(AssetClass.code.ilike(pattern), AssetClass.name.ilike(pattern))
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(AssetClass.code.asc(), AssetClass.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def classes(self, ids: Iterable[UUID]) -> dict[UUID, AssetClass]:
        """Return the named classes, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(AssetClass).where(AssetClass.id.in_(wanted))
            ).all()
        }

    def class_in_use(self, class_id: UUID) -> bool:
        """Say whether a live asset belongs to the class."""
        return (
            self._session.scalar(
                select(FixedAsset.id)
                .where(
                    FixedAsset.asset_class_id == class_id,
                    FixedAsset.is_deleted.is_(False),
                )
                .limit(1)
            )
            is not None
        )

    # -- assets ----------------------------------------------------------
    def asset(self, asset_id: UUID, *, firm_id: UUID) -> FixedAsset | None:
        """Return one live asset of the firm, or None."""
        row = self._session.get(FixedAsset, asset_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def asset_page(
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
        """Return one page of the register by asset number, and the total."""
        query: Select[tuple[FixedAsset]] = select(FixedAsset).where(
            FixedAsset.firm_id == firm_id, FixedAsset.is_deleted.is_(False)
        )
        if status:
            query = query.where(FixedAsset.status == status.strip().upper())
        if asset_class_id is not None:
            query = query.where(FixedAsset.asset_class_id == asset_class_id)
        if branch_id is not None:
            query = query.where(FixedAsset.branch_id == branch_id)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    FixedAsset.asset_number.ilike(pattern),
                    FixedAsset.name.ilike(pattern),
                    FixedAsset.location.ilike(pattern),
                )
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(FixedAsset.asset_number.asc(), FixedAsset.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def active_assets(self, firm_id: UUID) -> list[FixedAsset]:
        """Return every live, undisposed asset of the firm."""
        return list(
            self._session.scalars(
                select(FixedAsset)
                .where(
                    FixedAsset.firm_id == firm_id,
                    FixedAsset.is_deleted.is_(False),
                    FixedAsset.status == "ACTIVE",
                )
                .order_by(FixedAsset.asset_number.asc())
            ).all()
        )

    def all_assets(self, firm_id: UUID) -> list[FixedAsset]:
        """Return every live asset of the firm, disposed ones included."""
        return list(
            self._session.scalars(
                select(FixedAsset).where(
                    FixedAsset.firm_id == firm_id, FixedAsset.is_deleted.is_(False)
                )
            ).all()
        )

    def assets_of_invoice(self, invoice_id: UUID) -> list[FixedAsset]:
        """Return the live assets a bill raised."""
        return list(
            self._session.scalars(
                select(FixedAsset).where(
                    FixedAsset.purchase_invoice_id == invoice_id,
                    FixedAsset.is_deleted.is_(False),
                )
            ).all()
        )

    def assets(self, ids: Iterable[UUID]) -> dict[UUID, FixedAsset]:
        """Return the named assets, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(FixedAsset).where(FixedAsset.id.in_(wanted))
            ).all()
        }

    def next_number(
        self, firm_id: UUID, model: type[FixedAsset] | type[DepreciationRun]
    ) -> int:
        """Return one more than the rows the firm ever numbered, deleted included."""
        return (
            int(
                self._session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.firm_id == firm_id)
                )
                or 0
            )
            + 1
        )

    def invoice_numbers(self, ids: Iterable[UUID | None]) -> dict[UUID, str]:
        """Return each named bill's number, one read."""
        wanted = {value for value in ids if value is not None}
        if not wanted:
            return {}
        return {
            invoice_id: number
            for invoice_id, number in self._session.execute(
                select(PurchaseInvoice.id, PurchaseInvoice.invoice_number).where(
                    PurchaseInvoice.id.in_(wanted)
                )
            ).all()
        }

    # -- what was charged --------------------------------------------------
    def _live_lines(self) -> Select[tuple[DepreciationRunLine]]:
        """Return the lines of posted runs."""
        return (
            select(DepreciationRunLine)
            .join(
                DepreciationRun,
                DepreciationRun.id == DepreciationRunLine.depreciation_run_id,
            )
            .where(
                DepreciationRunLine.is_deleted.is_(False),
                DepreciationRun.is_deleted.is_(False),
                DepreciationRun.status == POSTED,
            )
        )

    def charged(
        self, asset_ids: Iterable[UUID], *, as_of: date | None = None
    ) -> dict[UUID, tuple[Decimal, date | None]]:
        """Return what posted runs charged each asset, and the day charged to.

        ``as_of`` counts only spans that ended by then.
        """
        ids = list(set(asset_ids))
        if not ids:
            return {}
        query = (
            select(
                DepreciationRunLine.fixed_asset_id,
                func.coalesce(func.sum(DepreciationRunLine.amount), 0),
                func.max(DepreciationRunLine.to_date),
            )
            .join(
                DepreciationRun,
                DepreciationRun.id == DepreciationRunLine.depreciation_run_id,
            )
            .where(
                DepreciationRunLine.fixed_asset_id.in_(ids),
                DepreciationRunLine.is_deleted.is_(False),
                DepreciationRun.is_deleted.is_(False),
                DepreciationRun.status == POSTED,
            )
            .group_by(DepreciationRunLine.fixed_asset_id)
        )
        if as_of is not None:
            query = query.where(DepreciationRunLine.to_date <= as_of)
        return {
            asset_id: (Decimal(str(total)), last)
            for asset_id, total, last in self._session.execute(query).all()
        }

    def lines_of_asset(self, asset_id: UUID) -> list[tuple[DepreciationRunLine, str]]:
        """Return an asset's posted charges in date order, with the run number."""
        return [
            (line, number)
            for line, number in self._session.execute(
                select(DepreciationRunLine, DepreciationRun.run_number)
                .join(
                    DepreciationRun,
                    DepreciationRun.id == DepreciationRunLine.depreciation_run_id,
                )
                .where(
                    DepreciationRunLine.fixed_asset_id == asset_id,
                    DepreciationRunLine.is_deleted.is_(False),
                    DepreciationRun.is_deleted.is_(False),
                    DepreciationRun.status == POSTED,
                )
                .order_by(DepreciationRunLine.from_date.asc())
            ).all()
        ]

    # -- runs ------------------------------------------------------------
    def run(self, run_id: UUID, *, firm_id: UUID) -> DepreciationRun | None:
        """Return one live run of the firm, or None."""
        row = self._session.get(DepreciationRun, run_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def run_page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        run_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DepreciationRun], int]:
        """Return one page of the firm's runs, latest period first, and the total."""
        query: Select[tuple[DepreciationRun]] = select(DepreciationRun).where(
            DepreciationRun.firm_id == firm_id, DepreciationRun.is_deleted.is_(False)
        )
        if status:
            query = query.where(DepreciationRun.status == status.strip().upper())
        if run_type:
            query = query.where(DepreciationRun.run_type == run_type.strip().upper())
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(
                DepreciationRun.period_to.desc(),
                DepreciationRun.run_number.desc(),
                DepreciationRun.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def overlapping_run(
        self, firm_id: UUID, *, period_from: date, period_to: date
    ) -> DepreciationRun | None:
        """Return a posted periodic run sharing a day with the period."""
        return self._session.scalar(
            select(DepreciationRun)
            .where(
                DepreciationRun.firm_id == firm_id,
                DepreciationRun.is_deleted.is_(False),
                DepreciationRun.status == POSTED,
                DepreciationRun.run_type == "PERIODIC",
                DepreciationRun.period_from <= period_to,
                DepreciationRun.period_to >= period_from,
            )
            .order_by(DepreciationRun.period_from.asc())
            .limit(1)
        )

    def latest_run(self, firm_id: UUID) -> DepreciationRun | None:
        """Return the posted periodic run that reaches furthest."""
        return self._session.scalar(
            select(DepreciationRun)
            .where(
                DepreciationRun.firm_id == firm_id,
                DepreciationRun.is_deleted.is_(False),
                DepreciationRun.status == POSTED,
                DepreciationRun.run_type == "PERIODIC",
            )
            .order_by(DepreciationRun.period_to.desc())
            .limit(1)
        )

    def run_lines(
        self, run_ids: Iterable[UUID]
    ) -> dict[UUID, list[DepreciationRunLine]]:
        """Return each run's lines."""
        grouped: dict[UUID, list[DepreciationRunLine]] = defaultdict(list)
        ids = list(run_ids)
        if not ids:
            return grouped
        for line in self._session.scalars(
            select(DepreciationRunLine)
            .where(
                DepreciationRunLine.depreciation_run_id.in_(ids),
                DepreciationRunLine.is_deleted.is_(False),
            )
            .order_by(DepreciationRunLine.created_at, DepreciationRunLine.id)
        ).all():
            grouped[line.depreciation_run_id].append(line)
        return grouped

    def charged_after(
        self, asset_ids: Iterable[UUID], *, after: date, except_run_id: UUID
    ) -> bool:
        """Say whether another posted run charged any of the assets past ``after``."""
        ids = list(set(asset_ids))
        if not ids:
            return False
        return (
            self._session.scalar(
                self._live_lines()
                .where(
                    DepreciationRunLine.fixed_asset_id.in_(ids),
                    DepreciationRunLine.to_date > after,
                    DepreciationRunLine.depreciation_run_id != except_run_id,
                )
                .limit(1)
            )
            is not None
        )
