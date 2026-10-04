"""Soft-delete-aware reads for RFQs and supplier quotations."""

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.products.models import Product
from app.rfq.models import (
    Rfq,
    RfqLine,
    RfqSupplier,
    SupplierQuotation,
    SupplierQuotationLine,
)
from app.vendors.models import Vendor


class RfqRepository:
    """Read RFQs and their children, each table once per call."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session it does not own."""
        self._session = session

    def get(self, rfq_id: UUID, *, firm_id: UUID) -> Rfq | None:
        """Return one live RFQ of the firm, or None."""
        row = self._session.get(Rfq, rfq_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Rfq], int]:
        """Return one page of the firm's RFQs, newest first, and the total."""
        query = select(Rfq).where(Rfq.firm_id == firm_id, Rfq.is_deleted.is_(False))
        if status:
            query = query.where(Rfq.status == status)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(Rfq.rfq_number.ilike(pattern), Rfq.notes.ilike(pattern))
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(Rfq.rfq_date.desc(), Rfq.rfq_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def lines(self, rfq_ids: Iterable[UUID]) -> dict[UUID, list[RfqLine]]:
        """Return the live lines of each RFQ, in line order."""
        grouped: dict[UUID, list[RfqLine]] = defaultdict(list)
        ids = list(rfq_ids)
        if not ids:
            return grouped
        for line in self._session.scalars(
            select(RfqLine)
            .where(RfqLine.rfq_id.in_(ids), RfqLine.is_deleted.is_(False))
            .order_by(RfqLine.line_number.asc())
        ).all():
            grouped[line.rfq_id].append(line)
        return grouped

    def suppliers(
        self, rfq_ids: Iterable[UUID], *, include_deleted: bool = False
    ) -> dict[UUID, list[RfqSupplier]]:
        """Return the invited suppliers of each RFQ, in invitation order."""
        grouped: dict[UUID, list[RfqSupplier]] = defaultdict(list)
        ids = list(rfq_ids)
        if not ids:
            return grouped
        query = select(RfqSupplier).where(RfqSupplier.rfq_id.in_(ids))
        if not include_deleted:
            query = query.where(RfqSupplier.is_deleted.is_(False))
        for row in self._session.scalars(
            query.order_by(RfqSupplier.created_at.asc(), RfqSupplier.id.asc())
        ).all():
            grouped[row.rfq_id].append(row)
        return grouped

    def quotations(
        self, rfq_ids: Iterable[UUID]
    ) -> dict[UUID, list[SupplierQuotation]]:
        """Return the live quotations of each RFQ."""
        grouped: dict[UUID, list[SupplierQuotation]] = defaultdict(list)
        ids = list(rfq_ids)
        if not ids:
            return grouped
        for row in self._session.scalars(
            select(SupplierQuotation)
            .where(
                SupplierQuotation.rfq_id.in_(ids),
                SupplierQuotation.is_deleted.is_(False),
            )
            .order_by(SupplierQuotation.quote_date.asc(), SupplierQuotation.id.asc())
        ).all():
            grouped[row.rfq_id].append(row)
        return grouped

    def quotation_lines(
        self, quotation_ids: Iterable[UUID], *, include_deleted: bool = False
    ) -> dict[UUID, list[SupplierQuotationLine]]:
        """Return the lines of each quotation."""
        grouped: dict[UUID, list[SupplierQuotationLine]] = defaultdict(list)
        ids = list(quotation_ids)
        if not ids:
            return grouped
        query = select(SupplierQuotationLine).where(
            SupplierQuotationLine.quotation_id.in_(ids)
        )
        if not include_deleted:
            query = query.where(SupplierQuotationLine.is_deleted.is_(False))
        for row in self._session.scalars(query).all():
            grouped[row.quotation_id].append(row)
        return grouped

    def quotation_for(self, rfq_id: UUID, vendor_id: UUID) -> SupplierQuotation | None:
        """Return the supplier's quotation on the RFQ, deleted or not."""
        return self._session.scalar(
            select(SupplierQuotation).where(
                SupplierQuotation.rfq_id == rfq_id,
                SupplierQuotation.vendor_id == vendor_id,
            )
        )

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

    def live_rfq_for_requisition(self, requisition_id: UUID) -> Rfq | None:
        """Return an RFQ not cancelled that was started from the requisition."""
        return self._session.scalar(
            select(Rfq).where(
                Rfq.source_requisition_id == requisition_id,
                Rfq.is_deleted.is_(False),
                Rfq.status != "CANCELLED",
            )
        )
