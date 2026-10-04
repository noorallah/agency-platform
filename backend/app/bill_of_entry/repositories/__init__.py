"""Soft-delete-aware reads for Bills of Entry (PG-12 part B)."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.bill_of_entry.models import (
    BillOfEntry,
    BillOfEntryAllocation,
    BillOfEntryDocument,
    BillOfEntryLine,
)
from app.goods_receipt.models import GoodsReceipt
from app.products.models import Product
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceSource
from app.vendors.models import Vendor

#: How a Bill of Entry names the documents its goods came on.
INVOICE = "PURCHASE_INVOICE"
RECEIPT = "GOODS_RECEIPT"


class BillOfEntryRepository:
    """Read Bills of Entry and what hangs off them, each table once per call."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session it does not own."""
        self._session = session

    def get(self, boe_id: UUID, *, firm_id: UUID) -> BillOfEntry | None:
        """Return one live Bill of Entry of the firm, or None."""
        row = self._session.get(BillOfEntry, boe_id)
        if row is None or row.is_deleted or row.firm_id != firm_id:
            return None
        return row

    def page(
        self,
        firm_id: UUID,
        *,
        status: str | None,
        vendor_id: UUID | None,
        from_date: date | None,
        to_date: date | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BillOfEntry], int]:
        """Return one page of the firm's Bills of Entry, newest first, and the total."""
        query: Select[tuple[BillOfEntry]] = select(BillOfEntry).where(
            BillOfEntry.firm_id == firm_id, BillOfEntry.is_deleted.is_(False)
        )
        if status:
            query = query.where(BillOfEntry.status == status.strip().upper())
        if vendor_id is not None:
            query = query.where(BillOfEntry.vendor_id == vendor_id)
        if from_date is not None:
            query = query.where(BillOfEntry.boe_date >= from_date)
        if to_date is not None:
            query = query.where(BillOfEntry.boe_date <= to_date)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    BillOfEntry.boe_number.ilike(pattern),
                    BillOfEntry.document_number.ilike(pattern),
                    BillOfEntry.port_code.ilike(pattern),
                )
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._session.scalars(
            query.order_by(
                BillOfEntry.boe_date.desc(),
                BillOfEntry.document_number.desc(),
                BillOfEntry.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(total or 0)

    def duplicate(
        self, firm_id: UUID, *, boe_number: str, port_code: str, boe_date: date
    ) -> BillOfEntry | None:
        """Return a live, uncancelled Bill of Entry customs already numbered so."""
        return self._session.scalar(
            select(BillOfEntry).where(
                BillOfEntry.firm_id == firm_id,
                BillOfEntry.is_deleted.is_(False),
                BillOfEntry.status != "CANCELLED",
                func.upper(BillOfEntry.boe_number) == boe_number.upper(),
                func.upper(BillOfEntry.port_code) == port_code.upper(),
                BillOfEntry.boe_date == boe_date,
            )
        )

    def lines(self, boe_ids: Iterable[UUID]) -> dict[UUID, list[BillOfEntryLine]]:
        """Return the live lines of each Bill of Entry, in line order."""
        grouped: dict[UUID, list[BillOfEntryLine]] = defaultdict(list)
        ids = list(boe_ids)
        if not ids:
            return grouped
        for line in self._session.scalars(
            select(BillOfEntryLine)
            .where(
                BillOfEntryLine.bill_of_entry_id.in_(ids),
                BillOfEntryLine.is_deleted.is_(False),
            )
            .order_by(BillOfEntryLine.line_number.asc())
        ).all():
            grouped[line.bill_of_entry_id].append(line)
        return grouped

    def documents(
        self, boe_ids: Iterable[UUID]
    ) -> dict[UUID, list[BillOfEntryDocument]]:
        """Return the bills and receipts each Bill of Entry names."""
        grouped: dict[UUID, list[BillOfEntryDocument]] = defaultdict(list)
        ids = list(boe_ids)
        if not ids:
            return grouped
        for link in self._session.scalars(
            select(BillOfEntryDocument)
            .where(
                BillOfEntryDocument.bill_of_entry_id.in_(ids),
                BillOfEntryDocument.is_deleted.is_(False),
            )
            .order_by(BillOfEntryDocument.created_at, BillOfEntryDocument.id)
        ).all():
            grouped[link.bill_of_entry_id].append(link)
        return grouped

    def allocations(self, boe_id: UUID) -> list[BillOfEntryAllocation]:
        """Return what a posted Bill of Entry landed on each receipt line."""
        return list(
            self._session.scalars(
                select(BillOfEntryAllocation).where(
                    BillOfEntryAllocation.bill_of_entry_id == boe_id,
                    BillOfEntryAllocation.is_deleted.is_(False),
                )
            ).all()
        )

    def invoices(self, ids: Iterable[UUID]) -> dict[UUID, PurchaseInvoice]:
        """Return the named bills, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(PurchaseInvoice).where(PurchaseInvoice.id.in_(wanted))
            ).all()
        }

    def receipts(self, ids: Iterable[UUID]) -> dict[UUID, GoodsReceipt]:
        """Return the named receipts, one read."""
        wanted = set(ids)
        if not wanted:
            return {}
        return {
            row.id: row
            for row in self._session.scalars(
                select(GoodsReceipt).where(GoodsReceipt.id.in_(wanted))
            ).all()
        }

    def receipts_of_invoices(self, invoice_ids: Iterable[UUID]) -> dict[UUID, UUID]:
        """Return receipt id -> bill id for every live receipt the bills reach.

        A bill reaches a receipt by naming it as a source, or by having raised
        it itself where the firm types only the bill. A cancelled receipt is
        not reached.
        """
        ids = list(set(invoice_ids))
        if not ids:
            return {}
        reached: dict[UUID, UUID] = {}
        for receipt_id, invoice_id in self._session.execute(
            select(
                PurchaseInvoiceSource.source_document_id,
                PurchaseInvoiceSource.purchase_invoice_id,
            ).where(
                PurchaseInvoiceSource.purchase_invoice_id.in_(ids),
                PurchaseInvoiceSource.source_document_type == RECEIPT,
                PurchaseInvoiceSource.is_deleted.is_(False),
            )
        ).all():
            reached.setdefault(receipt_id, invoice_id)
        for receipt_id, invoice_id in self._session.execute(
            select(GoodsReceipt.id, GoodsReceipt.raised_by_purchase_invoice_id).where(
                GoodsReceipt.raised_by_purchase_invoice_id.in_(ids),
                GoodsReceipt.is_deleted.is_(False),
            )
        ).all():
            if invoice_id is not None:
                reached.setdefault(receipt_id, invoice_id)
        live = self._session.scalars(
            select(GoodsReceipt.id).where(
                GoodsReceipt.id.in_(list(reached)),
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceipt.status != "CANCELLED",
            )
        ).all()
        return {receipt_id: reached[receipt_id] for receipt_id in live}

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
