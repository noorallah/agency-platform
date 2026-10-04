"""Soft-delete-aware reads for rate contracts."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.rate_contracts.models import RateContract, RateContractLine
from app.vendors.models import Vendor


class RateContractRepository:
    """Read rate contracts and their lines, each table once per call."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session it does not own."""
        self._session = session

    def get(self, contract_id: UUID, *, firm_id: UUID) -> RateContract | None:
        """Return one live contract of the firm, or None."""
        row = self._session.get(RateContract, contract_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        today: date,
        vendor_id: UUID | None,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RateContract], int]:
        """Return one page of the firm's contracts, newest first, and the total.

        ``EXPIRED`` and ``ACTIVE`` are told apart by ``today``, since expiry
        is never stored.
        """
        query: Select[tuple[RateContract]] = select(RateContract).where(
            RateContract.firm_id == firm_id, RateContract.is_deleted.is_(False)
        )
        if vendor_id is not None:
            query = query.where(RateContract.vendor_id == vendor_id)
        if status:
            wanted = status.strip().upper()
            if wanted == "EXPIRED":
                query = query.where(
                    RateContract.status == "ACTIVE", RateContract.valid_to < today
                )
            elif wanted == "ACTIVE":
                query = query.where(
                    RateContract.status == "ACTIVE", RateContract.valid_to >= today
                )
            else:
                query = query.where(RateContract.status == wanted)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    RateContract.contract_number.ilike(pattern),
                    RateContract.reference.ilike(pattern),
                    RateContract.notes.ilike(pattern),
                )
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(
                RateContract.valid_from.desc(),
                RateContract.contract_number.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def lines(self, contract_ids: Iterable[UUID]) -> dict[UUID, list[RateContractLine]]:
        """Return the live lines of each contract, in line order."""
        grouped: dict[UUID, list[RateContractLine]] = defaultdict(list)
        ids = list(contract_ids)
        if not ids:
            return grouped
        for line in self._session.scalars(
            select(RateContractLine)
            .where(
                RateContractLine.contract_id.in_(ids),
                RateContractLine.is_deleted.is_(False),
            )
            .order_by(RateContractLine.line_number.asc())
        ).all():
            grouped[line.contract_id].append(line)
        return grouped

    def products(self, ids: Iterable[UUID]) -> dict[UUID, Product]:
        """Return the named products, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Product).where(Product.id.in_(wanted))
            ).all()
        }

    def vendors(self, ids: Iterable[UUID]) -> dict[UUID, Vendor]:
        """Return the named suppliers, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(Vendor).where(Vendor.id.in_(wanted))
            ).all()
        }

    def lock_vendor_contracts(
        self, firm_id: UUID, vendor_id: UUID
    ) -> list[RateContract]:
        """Lock and return every live contract of the supplier.

        Two activations for one supplier queue here, so the second sees the
        first's result: an overlap is a fact about a set of rows, and no key
        can refuse it.
        """
        return list(
            self._session.scalars(
                select(RateContract)
                .where(
                    RateContract.firm_id == firm_id,
                    RateContract.vendor_id == vendor_id,
                    RateContract.is_deleted.is_(False),
                )
                .order_by(RateContract.id.asc())
                .with_for_update()
            ).all()
        )

    def releases(
        self, line_ids: Iterable[UUID]
    ) -> list[tuple[PurchaseOrder, PurchaseOrderLine]]:
        """Return every live order line drawing on the contract lines."""
        ids = list(line_ids)
        if not ids:
            return []
        rows = self._session.execute(
            select(PurchaseOrder, PurchaseOrderLine)
            .join(
                PurchaseOrderLine,
                and_(
                    PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
                    PurchaseOrderLine.is_deleted.is_(False),
                ),
            )
            .where(
                PurchaseOrderLine.rate_contract_line_id.in_(ids),
                PurchaseOrder.is_deleted.is_(False),
            )
            .order_by(
                PurchaseOrder.purchase_date.asc(),
                PurchaseOrder.po_number.asc(),
                PurchaseOrderLine.line_number.asc(),
            )
        ).all()
        return [(order, line) for order, line in rows]
