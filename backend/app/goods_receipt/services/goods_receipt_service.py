"""Goods receipt note workflow and inventory posting service."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse, WarehouseStorageNode
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
)
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.finance.services.document_posting import DocumentPostingService
from app.goods_receipt.models import (
    GoodsReceipt,
    GoodsReceiptAttachment,
    GoodsReceiptLine,
    GoodsReceiptNote,
)
from app.goods_receipt.schemas import (
    GoodsReceiptAttachmentResponse,
    GoodsReceiptAttachmentWrite,
    GoodsReceiptCreate,
    GoodsReceiptLineResponse,
    GoodsReceiptListFilters,
    GoodsReceiptNoteResponse,
    GoodsReceiptNoteWrite,
    GoodsReceiptPurchaseOrderReport,
    GoodsReceiptResponse,
    GoodsReceiptStatus,
    GoodsReceiptSummary,
    GoodsReceiptUpdate,
)
from app.inventory.models import StockLedgerEntry
from app.inventory.services import InventoryService
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")


class GoodsReceiptService(TransactionalDocumentService):
    """Coordinate goods receipt notes, inventory posting, and document history."""

    DOCUMENT = DocumentTypeSpec(
        code="GOODS_RECEIPT_NOTE",
        name="Goods Receipt Note",
        description="Reusable goods receipt document type.",
        category="PURCHASE",
        module="goods_receipt",
        prefix="GRN",
        include_branch_code=True,
        include_company_code=True,
        rule_code="GRN_DEFAULT",
        rule_name="Goods Receipt Note Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            DocumentStateSpec("COMPLETED", "Completed", 20, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 100, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._inventory = InventoryService(session)
        self._uom = UomService(session)
        self._tax = TaxRuleService(session)

    def list_receipts(
        self,
        *,
        firm_scope: UUID,
        filters: GoodsReceiptListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[GoodsReceipt], int]:
        """List receipts."""
        columns = {
            "grn_number": GoodsReceipt.grn_number,
            "receipt_date": GoodsReceipt.receipt_date,
            "status": GoodsReceipt.status,
            "created_at": GoodsReceipt.created_at,
            "updated_at": GoodsReceipt.updated_at,
        }
        statement = select(GoodsReceipt).where(GoodsReceipt.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(GoodsReceipt)
            .where(GoodsReceipt.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(GoodsReceipt.is_deleted.is_(False))
            count = count.where(GoodsReceipt.is_deleted.is_(False))
        if filters.purchase_order_id is not None:
            statement = statement.where(
                GoodsReceipt.purchase_order_id == filters.purchase_order_id
            )
            count = count.where(
                GoodsReceipt.purchase_order_id == filters.purchase_order_id
            )
        if filters.vendor_id is not None:
            statement = statement.where(GoodsReceipt.vendor_id == filters.vendor_id)
            count = count.where(GoodsReceipt.vendor_id == filters.vendor_id)
        if filters.branch_id is not None:
            statement = statement.where(GoodsReceipt.branch_id == filters.branch_id)
            count = count.where(GoodsReceipt.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                GoodsReceipt.warehouse_id == filters.warehouse_id
            )
            count = count.where(GoodsReceipt.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(GoodsReceipt.status == filters.status.value)
            count = count.where(GoodsReceipt.status == filters.status.value)
        if filters.created_from is not None:
            statement = statement.where(
                GoodsReceipt.receipt_date >= filters.created_from
            )
            count = count.where(GoodsReceipt.receipt_date >= filters.created_from)
        if filters.created_to is not None:
            statement = statement.where(GoodsReceipt.receipt_date <= filters.created_to)
            count = count.where(GoodsReceipt.receipt_date <= filters.created_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                GoodsReceipt.grn_number.ilike(token),
                GoodsReceipt.purchase_order_number.ilike(token),
                GoodsReceipt.invoice_reference.ilike(token),
                GoodsReceipt.vehicle_number.ilike(token),
                GoodsReceipt.transport_details.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement.order_by(
                columns.get(sort_by, GoodsReceipt.created_at).desc()
                if descending
                else columns.get(sort_by, GoodsReceipt.created_at).asc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> GoodsReceiptSummary:
        """Summarize ."""
        receipts = list(
            self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )
        pending_po_count = len(
            {
                row.purchase_order_id
                for row in receipts
                if row.status == GoodsReceiptStatus.DRAFT.value
            }
        )
        partial_po_count = len(
            {
                row.purchase_order_id
                for row in receipts
                if row.total_current_receipt_quantity > 0
                and row.status != GoodsReceiptStatus.CANCELLED.value
            }
        )
        return GoodsReceiptSummary(
            total=len(receipts),
            draft=sum(
                1 for row in receipts if row.status == GoodsReceiptStatus.DRAFT.value
            ),
            completed=sum(
                1
                for row in receipts
                if row.status == GoodsReceiptStatus.COMPLETED.value
            ),
            cancelled=sum(
                1
                for row in receipts
                if row.status == GoodsReceiptStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in receipts if row.status == GoodsReceiptStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in receipts), ZERO)),
            pending_purchase_orders=pending_po_count,
            partial_purchase_orders=partial_po_count,
        )

    def create_receipt(
        self, data: GoodsReceiptCreate, *, firm_id: UUID, actor_id: UUID
    ) -> GoodsReceipt:
        """Create receipt."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        assert_feature_fields(
            self._session,
            firm_id,
            feature="VEHICLE_TRACKING",
            values={"vehicle_number": data.vehicle_number},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        purchase_order = self._purchase_order(data.purchase_order_id, firm_id=firm_id)
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=purchase_order.branch_id
        )
        grn_number = (
            data.grn_number.strip().upper()
            if data.grn_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.receipt_date, firm_id
                ),
                branch_code=branch_code,
                company_code=company_code,
                document_date=data.receipt_date,
                actor_id=actor_id,
            )
        )
        row = GoodsReceipt(
            firm_id=firm_id,
            purchase_order_id=purchase_order.id,
            purchase_order_number=purchase_order.po_number,
            vendor_id=purchase_order.vendor_id,
            branch_id=purchase_order.branch_id,
            warehouse_id=purchase_order.warehouse_id,
            received_by_id=data.received_by_id,
            grn_number=grn_number,
            receipt_date=data.receipt_date,
            transport_details=data.transport_details,
            vehicle_number=data.vehicle_number,
            invoice_reference=data.invoice_reference,
            remarks=data.remarks,
            allow_over_receipt=data.allow_over_receipt,
            over_receipt_percent=self._q(data.over_receipt_percent),
            status=GoodsReceiptStatus.DRAFT.value,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_lines(row, data=data, firm_id=firm_id, actor_id=actor_id)
        self._replace_attachments(row, data.attachments, actor_id=actor_id)
        self._replace_notes(row, data.notes, actor_id=actor_id)
        self._recalculate_totals(row)
        self._record_event(
            firm_id=firm_id,
            document_type=document_type,
            receipt=row,
            action="CREATED",
            from_state=None,
            to_state=row.status,
            actor_id=actor_id,
            details={"purchase_order_number": row.purchase_order_number},
        )
        record_audit(
            self._session,
            action="grn.created",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"grn_number": row.grn_number, "status": row.status},
        )
        self._flush_or_conflict("Goods receipt number already exists in this firm.")
        self._session.commit()
        return row

    def update_receipt(
        self,
        receipt_id: UUID,
        data: GoodsReceiptUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> GoodsReceipt:
        """Change receipt."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="VEHICLE_TRACKING",
            values={"vehicle_number": data.vehicle_number},
        )
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status != GoodsReceiptStatus.DRAFT.value:
            raise ValidationError("Only draft goods receipts can be updated.")
        purchase_order = self._purchase_order(row.purchase_order_id, firm_id=firm_scope)
        before_status = row.status
        row.receipt_date = data.receipt_date
        row.received_by_id = data.received_by_id
        row.transport_details = data.transport_details
        row.vehicle_number = data.vehicle_number
        row.invoice_reference = data.invoice_reference
        row.remarks = data.remarks
        row.allow_over_receipt = data.allow_over_receipt
        row.over_receipt_percent = self._q(data.over_receipt_percent)
        row.updated_by = actor_id
        self._replace_lines(row, data=data, firm_id=firm_scope, actor_id=actor_id)
        self._replace_attachments(row, data.attachments, actor_id=actor_id)
        self._replace_notes(row, data.notes, actor_id=actor_id)
        self._recalculate_totals(row)
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            receipt=row,
            action="EDITED",
            from_state=before_status,
            to_state=row.status,
            actor_id=actor_id,
            details={"purchase_order_number": purchase_order.po_number},
        )
        record_audit(
            self._session,
            action="grn.updated",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before_status},
        )
        self._session.commit()
        return row

    def complete_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> GoodsReceipt:
        """Complete receipt."""
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status == GoodsReceiptStatus.COMPLETED.value:
            return row
        if row.status in {
            GoodsReceiptStatus.CANCELLED.value,
            GoodsReceiptStatus.CLOSED.value,
        }:
            raise ValidationError(
                "Cancelled/closed goods receipts cannot be completed."
            )
        document_type, _ = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )
        purchase_order = self._purchase_order(row.purchase_order_id, firm_id=firm_scope)
        previous_map = self._received_quantities_for_po(
            purchase_order.id, firm_id=firm_scope, exclude_receipt_id=row.id
        )
        self._validate_lines(
            row, purchase_order=purchase_order, previous_map=previous_map
        )
        self._post_inventory(row, purchase_order=purchase_order, actor_id=actor_id)
        before = row.status
        row.status = GoodsReceiptStatus.COMPLETED.value
        row.completed_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            receipt=row,
            action="COMPLETED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="grn.completed",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def cancel_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> GoodsReceipt:
        """Cancel receipt."""
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status in {
            GoodsReceiptStatus.CANCELLED.value,
            GoodsReceiptStatus.CLOSED.value,
        }:
            return row
        before = row.status
        reversed_lines = self._reverse_inventory(
            row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        row.status = GoodsReceiptStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            receipt=row,
            action="CANCELLED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="grn.cancelled",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={
                "status": row.status,
                "reason": reason or "",
                "reversed_inventory_lines": reversed_lines,
            },
        )
        self._session.commit()
        return row

    def _receipt_unit_cost(self, line: GoodsReceiptLine) -> Decimal:
        """Return what one received unit actually cost.

        Free quantity is received but not paid for, so the line's net value is
        spread across everything that lands on the shelf. Charging the invoice
        price to free goods would overstate the stock value.

        Args:
            line: The receipt line being posted.

        Returns:
            The cost per received unit, or zero when nothing was received.

        """
        received = self._q(line.accepted_quantity + line.free_quantity)
        if received <= ZERO:
            return ZERO
        net = self._q(line.net_amount - line.tax_amount)
        return net / received

    def _reverse_inventory(
        self,
        receipt: GoodsReceipt,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> int:
        """Undo the stock this receipt posted, if it had already been completed.

        A cancelled receipt that keeps its goods-receipt movements leaves stock
        the firm never accepted, so cancellation has to reverse each posted line
        and forget its movement.

        Args:
            receipt: The receipt being cancelled.
            firm_scope: The owning firm.
            actor_id: The user cancelling the receipt.
            reason: Optional cancellation reason, stored on the reversal.

        Returns:
            The number of lines whose stock movement was reversed.

        """
        reversed_lines = 0
        for line in self._session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.inventory_transaction_id.is_not(None),
                GoodsReceiptLine.is_deleted.is_(False),
            )
        ).all():
            if line.inventory_transaction_id is None:
                continue
            self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason or f"Goods receipt {receipt.grn_number} cancelled.",
            )
            line.inventory_transaction_id = None
            line.updated_by = actor_id
            reversed_lines += 1
        return reversed_lines

    def close_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> GoodsReceipt:
        """Close receipt."""
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status == GoodsReceiptStatus.CLOSED.value:
            return row
        before = row.status
        row.status = GoodsReceiptStatus.CLOSED.value
        row.closed_reason = reason
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            receipt=row,
            action="CLOSED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="grn.closed",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "reason": reason or ""},
        )
        self._session.commit()
        return row

    def get_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> GoodsReceipt:
        """Return receipt."""
        statement = select(GoodsReceipt).where(
            GoodsReceipt.id == receipt_id,
            GoodsReceipt.firm_id == firm_scope,
        )
        if not include_deleted:
            statement = statement.where(GoodsReceipt.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Goods receipt not found.")
        return row

    def receipt_response(self, row: GoodsReceipt) -> GoodsReceiptResponse:
        """Return response."""
        lines = list(
            self._session.scalars(
                select(GoodsReceiptLine)
                .where(
                    GoodsReceiptLine.goods_receipt_id == row.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
                .order_by(GoodsReceiptLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(GoodsReceiptAttachment).where(
                    GoodsReceiptAttachment.goods_receipt_id == row.id,
                    GoodsReceiptAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(GoodsReceiptNote).where(
                    GoodsReceiptNote.goods_receipt_id == row.id,
                    GoodsReceiptNote.is_deleted.is_(False),
                )
            ).all()
        )
        payload = GoodsReceiptResponse.model_validate(row).model_dump(mode="python")
        payload["lines"] = [
            GoodsReceiptLineResponse.model_validate(item).model_dump(mode="python")
            for item in lines
        ]
        payload["attachments"] = [
            GoodsReceiptAttachmentResponse.model_validate(item).model_dump(
                mode="python"
            )
            for item in attachments
        ]
        payload["notes"] = [
            GoodsReceiptNoteResponse.model_validate(item).model_dump(mode="python")
            for item in notes
        ]
        payload["duplicate_warning"] = self._duplicate_warning(row)
        return GoodsReceiptResponse.model_validate(payload)

    def receipt_history(
        self, *, receipt_id: UUID, firm_scope: UUID
    ) -> list[DocumentLifecycleEvent]:
        """Return history."""
        self.get_receipt(receipt_id, firm_scope=firm_scope, include_deleted=True)
        rows, _ = self._documents.list_timeline(
            firm_scope,
            receipt_id,
            page=1,
            page_size=200,
            sort_direction=False,
        )
        return rows

    def pending_receipts(self, *, firm_scope: UUID) -> list[GoodsReceipt]:
        """Return receipts."""
        return list(
            self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.status == GoodsReceiptStatus.DRAFT.value,
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )

    def completed_receipts(self, *, firm_scope: UUID) -> list[GoodsReceipt]:
        """Return receipts."""
        return list(
            self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.status == GoodsReceiptStatus.COMPLETED.value,
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )

    def rejected_items(self, *, firm_scope: UUID) -> list[GoodsReceiptLine]:
        """Return items."""
        return list(
            self._session.scalars(
                select(GoodsReceiptLine)
                .join(
                    GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id
                )
                .where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceiptLine.rejected_quantity > ZERO,
                    GoodsReceiptLine.is_deleted.is_(False),
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )

    def damaged_items(self, *, firm_scope: UUID) -> list[GoodsReceiptLine]:
        """Return items."""
        return list(
            self._session.scalars(
                select(GoodsReceiptLine)
                .join(
                    GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id
                )
                .where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceiptLine.damaged_quantity > ZERO,
                    GoodsReceiptLine.is_deleted.is_(False),
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )

    def partially_received_purchase_orders(
        self, *, firm_scope: UUID
    ) -> list[GoodsReceiptPurchaseOrderReport]:
        """Return received purchase orders."""
        reports: list[GoodsReceiptPurchaseOrderReport] = []
        purchase_orders = list(
            self._session.scalars(
                select(PurchaseOrder).where(
                    PurchaseOrder.firm_id == firm_scope,
                    PurchaseOrder.is_deleted.is_(False),
                )
            ).all()
        )
        for purchase_order in purchase_orders:
            lines = list(
                self._session.scalars(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.purchase_order_id == purchase_order.id,
                        PurchaseOrderLine.is_deleted.is_(False),
                    )
                ).all()
            )
            if not lines:
                continue
            ordered = sum((line.ordered_quantity for line in lines), ZERO)
            received = sum(
                (
                    self._session.scalar(
                        select(
                            func.coalesce(
                                func.sum(GoodsReceiptLine.current_receipt_quantity), 0
                            )
                        )
                        .join(
                            GoodsReceipt,
                            GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id,
                        )
                        .where(
                            GoodsReceipt.firm_id == firm_scope,
                            GoodsReceipt.purchase_order_id == purchase_order.id,
                            GoodsReceipt.status == GoodsReceiptStatus.COMPLETED.value,
                            GoodsReceipt.is_deleted.is_(False),
                            GoodsReceiptLine.purchase_order_line_id == line.id,
                            GoodsReceiptLine.is_deleted.is_(False),
                        )
                    )
                    or ZERO
                )
                for line in lines
            )
            if ZERO < received < ordered:
                reports.append(
                    GoodsReceiptPurchaseOrderReport(
                        purchase_order_id=purchase_order.id,
                        purchase_order_number=purchase_order.po_number,
                        vendor_id=purchase_order.vendor_id,
                        branch_id=purchase_order.branch_id,
                        warehouse_id=purchase_order.warehouse_id,
                        ordered_quantity=self._q(ordered),
                        received_quantity=self._q(received),
                        pending_quantity=self._q(ordered - received),
                        receipt_count=int(
                            self._session.scalar(
                                select(func.count())
                                .select_from(GoodsReceipt)
                                .where(
                                    GoodsReceipt.firm_id == firm_scope,
                                    GoodsReceipt.purchase_order_id == purchase_order.id,
                                    GoodsReceipt.status
                                    == GoodsReceiptStatus.COMPLETED.value,
                                    GoodsReceipt.is_deleted.is_(False),
                                )
                            )
                            or 0
                        ),
                        status="PARTIAL",
                    )
                )
        return reports

    def import_receipts(
        self, data: list[GoodsReceiptCreate], *, firm_scope: UUID, actor_id: UUID
    ) -> list[GoodsReceipt]:
        """Import receipts."""
        return [
            self.create_receipt(item, firm_id=firm_scope, actor_id=actor_id)
            for item in data
        ]

    def export_receipts_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        """Export receipts csv."""
        rows, _ = self.list_receipts(
            firm_scope=firm_scope,
            filters=GoodsReceiptListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="receipt_date",
            descending=True,
        )
        lines = [
            "GRN Number,Date,Purchase Order,Vendor ID,Branch ID,Warehouse ID,"
            "Status,Subtotal,Tax Total,Grand Total"
        ]
        for row in rows:
            lines.append(
                ",".join(
                    [
                        row.grn_number,
                        row.receipt_date.isoformat(),
                        row.purchase_order_number,
                        str(row.vendor_id),
                        str(row.branch_id),
                        str(row.warehouse_id),
                        row.status,
                        str(row.subtotal),
                        str(row.tax_total),
                        str(row.grand_total),
                    ]
                )
            )
        return "\n".join(lines)

    def _replace_lines(
        self,
        receipt: GoodsReceipt,
        *,
        data: GoodsReceiptCreate | GoodsReceiptUpdate,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Replace lines."""
        # Lines are matched on their line number and updated in place;
        # re-inserting them minted a new UUID per line on every save, and
        # downstream documents reference those ids with no foreign key.
        existing = {
            existing_line.line_number: existing_line
            for existing_line in self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id == receipt.id
                )
            ).all()
        }
        seen: set[int] = set()
        purchase_lines = {
            line.id: line
            for line in self._session.scalars(
                select(PurchaseOrderLine).where(
                    PurchaseOrderLine.purchase_order_id == receipt.purchase_order_id,
                    PurchaseOrderLine.is_deleted.is_(False),
                )
            ).all()
        }
        previous_map = self._received_quantities_for_po(
            receipt.purchase_order_id, firm_id=firm_id, exclude_receipt_id=receipt.id
        )
        total_ordered = ZERO
        total_previous = ZERO
        total_current = ZERO
        total_accepted = ZERO
        total_rejected = ZERO
        total_damaged = ZERO
        total_free = ZERO
        total_discount = ZERO
        for line in data.lines:
            purchase_line = purchase_lines.get(line.purchase_order_line_id)
            if purchase_line is None:
                raise ValidationError(
                    "Receipt line references unknown purchase order line "
                    f"{line.purchase_order_line_id}."
                )
            ordered_quantity = self._q(purchase_line.ordered_quantity)
            prev_received = previous_map.get(purchase_line.id, ZERO)
            total_sellable = self._q(line.current_receipt_quantity + line.free_quantity)
            accepted = self._q(
                line.current_receipt_quantity
                - line.rejected_quantity
                - line.damaged_quantity
            )
            if accepted < ZERO:
                raise ValidationError("Accepted quantity cannot be negative.")
            if total_sellable < ZERO:
                raise ValidationError("Receipt quantity cannot be negative.")
            if not receipt.allow_over_receipt:
                limit = ordered_quantity + self._q(
                    ordered_quantity * receipt.over_receipt_percent / Decimal("100")
                )
                if prev_received + self._q(line.current_receipt_quantity) > limit:
                    raise ValidationError(
                        "Goods receipt exceeds allowed quantity for PO line "
                        f"{purchase_line.line_number}."
                    )
            conversion = self._conversion(
                quantity=total_sellable,
                purchase_uom_id=line.purchase_uom_id or purchase_line.purchase_uom_id,
                inventory_uom_id=line.inventory_uom_id
                or purchase_line.inventory_uom_id,
                product_id=purchase_line.product_id,
                receipt_date=receipt.receipt_date,
                firm_id=firm_id,
            )
            unit_price = self._q(line.unit_price or purchase_line.unit_price)
            description = line.description or purchase_line.description
            gross_amount = self._q(accepted * unit_price)
            discount_amount = self._q(
                line.discount_amount
                if line.discount_amount > ZERO
                else gross_amount * self._q(line.discount_percent) / Decimal("100")
            )
            if discount_amount > gross_amount:
                raise ValidationError("Discount cannot exceed the line amount.")
            line_subtotal = self._q(gross_amount - discount_amount)
            tax_amount = self._line_tax_amount(
                firm_id=firm_id,
                actor_id=actor_id,
                tax_profile_id=line.tax_profile_id or purchase_line.tax_profile_id,
                product_id=purchase_line.product_id,
                receipt_date=receipt.receipt_date,
                taxable=line_subtotal,
            )
            net_amount = self._q(line_subtotal + tax_amount)
            row = GoodsReceiptLine(
                goods_receipt_id=receipt.id,
                firm_id=firm_id,
                line_number=line.line_number,
                purchase_order_line_id=purchase_line.id,
                purchase_order_line_number=purchase_line.line_number,
                product_id=purchase_line.product_id,
                description=description,
                ordered_quantity=ordered_quantity,
                previously_received_quantity=self._q(prev_received),
                current_receipt_quantity=self._q(line.current_receipt_quantity),
                accepted_quantity=accepted,
                unit_price=unit_price,
                discount_percent=self._q(line.discount_percent),
                discount_amount=discount_amount,
                gross_amount=gross_amount,
                tax_profile_id=line.tax_profile_id or purchase_line.tax_profile_id,
                tax_amount=tax_amount,
                net_amount=net_amount,
                rejected_quantity=self._q(line.rejected_quantity),
                damaged_quantity=self._q(line.damaged_quantity),
                free_quantity=self._q(line.free_quantity),
                packaging_type_id=line.packaging_type_id,
                purchase_uom_id=line.purchase_uom_id or purchase_line.purchase_uom_id,
                inventory_uom_id=line.inventory_uom_id
                or purchase_line.inventory_uom_id,
                conversion_factor=conversion["factor"],
                conversion_version=conversion["version"],
                warehouse_id=line.warehouse_id or receipt.warehouse_id,
                storage_node_id=line.storage_node_id,
                batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                manufacturing_date=line.manufacturing_date,
                remarks=line.remarks,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._validate_storage_scope(
                firm_id=firm_id,
                warehouse_id=row.warehouse_id,
                storage_node_id=row.storage_node_id,
            )
            total_discount += discount_amount
            total_ordered += ordered_quantity
            total_previous += prev_received
            total_current += self._q(line.current_receipt_quantity)
            total_accepted += accepted
            total_rejected += self._q(line.rejected_quantity)
            total_damaged += self._q(line.damaged_quantity)
            total_free += self._q(line.free_quantity)
            persisted = existing.get(line.line_number)
            if persisted is None:
                self._session.add(row)
            else:
                self._apply_line_values(
                    persisted,
                    row,
                    actor_id=actor_id,
                    preserve=("inventory_transaction_id",),
                )
            seen.add(line.line_number)
        for line_number, obsolete in existing.items():
            if line_number not in seen:
                self._session.delete(obsolete)
        self._session.flush()
        receipt.total_ordered_quantity = self._q(total_ordered)
        receipt.total_previous_received_quantity = self._q(total_previous)
        receipt.total_current_receipt_quantity = self._q(total_current)
        receipt.total_accepted_quantity = self._q(total_accepted)
        receipt.total_rejected_quantity = self._q(total_rejected)
        receipt.total_damaged_quantity = self._q(total_damaged)
        receipt.total_free_quantity = self._q(total_free)
        receipt.line_discount_total = self._q(total_discount)
        # A goods receipt carries no charges or round-off: neither is accepted on
        # create, so both stay zero.
        receipt.additional_charges = ZERO
        receipt.round_off = ZERO
        # subtotal / tax_total / grand_total are deliberately not set here.
        # _recalculate_totals runs immediately after every caller of this method
        # and recomputed all three with a *different* formula, so anything
        # written here was dead and only served to suggest two answers existed.

    def _replace_attachments(
        self,
        receipt: GoodsReceipt,
        attachments: list[GoodsReceiptAttachmentWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Replace attachments."""
        self._session.query(GoodsReceiptAttachment).filter(
            GoodsReceiptAttachment.goods_receipt_id == receipt.id
        ).delete(synchronize_session=False)
        for item in attachments:
            self._session.add(
                GoodsReceiptAttachment(
                    goods_receipt_id=receipt.id,
                    firm_id=receipt.firm_id,
                    file_name=item.file_name,
                    mime_type=item.mime_type,
                    file_path=item.file_path,
                    attachment_kind=item.attachment_kind.strip().upper(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_notes(
        self,
        receipt: GoodsReceipt,
        notes: list[GoodsReceiptNoteWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Replace notes."""
        self._session.query(GoodsReceiptNote).filter(
            GoodsReceiptNote.goods_receipt_id == receipt.id
        ).delete(synchronize_session=False)
        for item in notes:
            self._session.add(
                GoodsReceiptNote(
                    goods_receipt_id=receipt.id,
                    firm_id=receipt.firm_id,
                    note_type=item.note_type.value,
                    note=item.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _post_inventory(
        self, receipt: GoodsReceipt, *, purchase_order: PurchaseOrder, actor_id: UUID
    ) -> None:
        """Post inventory."""
        received_cost = ZERO
        for line in self._session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.is_deleted.is_(False),
            )
        ).all():
            transaction = self._inventory.record_goods_receipt(
                firm_scope=receipt.firm_id,
                actor_id=actor_id,
                branch_id=receipt.branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                reference_number=receipt.grn_number,
                transaction_date=receipt.receipt_date,
                total_quantity=self._q(line.accepted_quantity + line.free_quantity),
                unit_cost=self._receipt_unit_cost(line),
                blocked_quantity=self._q(line.rejected_quantity),
                damaged_quantity=self._q(line.damaged_quantity),
                entered_quantity=self._q(
                    line.current_receipt_quantity
                    + line.free_quantity
                    + line.rejected_quantity
                    + line.damaged_quantity
                ),
                entered_uom_id=line.purchase_uom_id,
                conversion_version=line.conversion_version,
                remarks=line.remarks,
            )
            line.inventory_transaction_id = transaction.id
            line.updated_by = actor_id
            received_cost += self._receipt_cost(transaction.id)

        # Stock is on the shelf now; the supplier invoice is not here yet, so
        # the credit waits in goods received not invoiced. Without this the
        # inventory account is only ever credited by dispatches.
        DocumentPostingService(self._session).post_goods_receipt(
            firm_id=receipt.firm_id,
            document_id=receipt.id,
            document_number=receipt.grn_number,
            receipt_date=receipt.receipt_date,
            cost_amount=received_cost,
            actor_id=actor_id,
        )

    def _receipt_cost(self, transaction_id: UUID) -> Decimal:
        """Return what the stock ledger brought in for one movement."""
        total = self._session.scalar(
            select(func.sum(StockLedgerEntry.total_cost)).where(
                StockLedgerEntry.transaction_id == transaction_id
            )
        )
        return self._q(total)

    def _validate_lines(
        self,
        receipt: GoodsReceipt,
        *,
        purchase_order: PurchaseOrder,
        previous_map: dict[UUID, Decimal],
    ) -> None:
        """Validate lines."""
        line_map = {
            line.id: line
            for line in self._session.scalars(
                select(PurchaseOrderLine).where(
                    PurchaseOrderLine.purchase_order_id == purchase_order.id,
                    PurchaseOrderLine.is_deleted.is_(False),
                )
            ).all()
        }
        for line in self._session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.is_deleted.is_(False),
            )
        ).all():
            purchase_line = line_map.get(line.purchase_order_line_id)
            if purchase_line is None:
                raise ValidationError(
                    "Receipt line references an invalid purchase order line."
                )
            expected = self._q(purchase_line.ordered_quantity)
            previous = previous_map.get(purchase_line.id, ZERO)
            allowed = expected
            if receipt.allow_over_receipt:
                allowed += self._q(
                    expected * receipt.over_receipt_percent / Decimal("100")
                )
            if previous + line.current_receipt_quantity > allowed:
                raise ValidationError(
                    "Receipt exceeds allowed quantity for purchase order line "
                    f"{purchase_line.line_number}."
                )

    def _received_quantities_for_po(
        self,
        purchase_order_id: UUID,
        *,
        firm_id: UUID,
        exclude_receipt_id: UUID | None = None,
    ) -> dict[UUID, Decimal]:
        """Received quantities for po."""
        statement = (
            select(
                GoodsReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(GoodsReceiptLine.current_receipt_quantity), 0),
            )
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(
                GoodsReceipt.firm_id == firm_id,
                GoodsReceipt.purchase_order_id == purchase_order_id,
                GoodsReceipt.status == GoodsReceiptStatus.COMPLETED.value,
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceiptLine.is_deleted.is_(False),
            )
            .group_by(GoodsReceiptLine.purchase_order_line_id)
        )
        if exclude_receipt_id is not None:
            statement = statement.where(GoodsReceipt.id != exclude_receipt_id)
        return {
            row[0]: self._q(row[1] or 0)
            for row in self._session.execute(statement).all()
        }

    def _duplicate_warning(self, row: GoodsReceipt) -> str | None:
        """Duplicate warning."""
        match = self._session.scalar(
            select(GoodsReceipt.id).where(
                GoodsReceipt.firm_id == row.firm_id,
                GoodsReceipt.purchase_order_id == row.purchase_order_id,
                GoodsReceipt.receipt_date == row.receipt_date,
                GoodsReceipt.status == GoodsReceiptStatus.COMPLETED.value,
                GoodsReceipt.id != row.id,
                GoodsReceipt.is_deleted.is_(False),
            )
        )
        if match is None:
            return None
        return (
            "A completed receipt already exists for the same purchase order and date."
        )

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        receipt: GoodsReceipt,
        action: str,
        from_state: str | None,
        to_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record event."""
        self._documents.record_event(
            firm_id,
            DocumentLifecycleEventCreate(
                document_type_id=document_type.id,
                source_document_id=receipt.id,
                source_module_code="GOODS_RECEIPT",
                document_number=receipt.grn_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json=details,
                actor_id=actor_id,
            ),
            actor_id,
        )

    def _purchase_order(
        self, purchase_order_id: UUID, *, firm_id: UUID
    ) -> PurchaseOrder:
        """Purchase order."""
        row = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.firm_id == firm_id,
                PurchaseOrder.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase order not found.")
        return row

    def _validate_storage_scope(
        self, *, firm_id: UUID, warehouse_id: UUID, storage_node_id: UUID | None
    ) -> None:
        """Validate storage scope."""
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Warehouse is not available for this firm.")
        if storage_node_id is None:
            return
        storage = self._session.scalar(
            select(WarehouseStorageNode).where(
                WarehouseStorageNode.id == storage_node_id,
                WarehouseStorageNode.warehouse_id == warehouse_id,
                WarehouseStorageNode.is_deleted.is_(False),
            )
        )
        if storage is None:
            raise ValidationError(
                "Storage area does not belong to the selected warehouse."
            )
        if not storage.is_active:
            raise ValidationError(
                "Inactive storage areas cannot be used for goods receipts."
            )

    def _conversion(
        self,
        *,
        quantity: Decimal,
        purchase_uom_id: UUID | None,
        inventory_uom_id: UUID | None,
        product_id: UUID,
        receipt_date: date,
        firm_id: UUID,
    ) -> dict[str, Decimal | int | None]:
        """Conversion ."""
        if (
            purchase_uom_id is None
            or inventory_uom_id is None
            or purchase_uom_id == inventory_uom_id
        ):
            return {
                "factor": Decimal("1"),
                "converted": self._q(quantity),
                "version": None,
            }
        response = self._uom.convert_quantity(
            ConversionRequest(
                quantity=quantity,
                from_uom_id=purchase_uom_id,
                to_uom_id=inventory_uom_id,
                product_id=product_id,
                conversion_date=receipt_date,
            ),
            firm_scope=firm_id,
        )
        return {
            "factor": response.conversion_factor,
            "converted": self._q(response.converted_quantity),
            "version": response.version,
        }

    def _line_tax_amount(
        self,
        *,
        firm_id: UUID,
        actor_id: UUID,
        tax_profile_id: UUID | None,
        product_id: UUID,
        receipt_date: date,
        taxable: Decimal,
    ) -> Decimal:
        """Line tax amount."""
        # A product names a tax group, not a version, so the rate is decided by
        # the document date. An explicitly named profile must also have been in
        # force then, or the document would carry a rate that never applied.
        tax_service = TaxFrameworkService(self._session)
        if tax_profile_id is None:
            product = self._session.get(Product, product_id)
            resolved = (
                tax_service.resolve_profile_for_product(
                    product, receipt_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, receipt_date, firm_scope=firm_id
            )
        simulation = self._tax.simulate(
            TaxRuleSimulationRequest(
                transaction_type="GOODS_RECEIPT",
                transaction_date=receipt_date,
                tax_profile_id=tax_profile_id,
                product_id=product_id,
                invoice_value=self._q(taxable),
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
        )
        return self._q(simulation.total_tax_amount)

    def _recalculate_totals(self, receipt: GoodsReceipt) -> None:
        """Recalculate totals."""
        lines = list(
            self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id == receipt.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all()
        )
        receipt.subtotal = self._q(
            sum((line.net_amount - line.tax_amount for line in lines), ZERO)
        )
        receipt.tax_total = self._q(sum((line.tax_amount for line in lines), ZERO))
        receipt.grand_total = self._q(sum((line.net_amount for line in lines), ZERO))
