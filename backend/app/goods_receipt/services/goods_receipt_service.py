"""Goods receipt note workflow and inventory posting service."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from app.batch_serial.services import BatchSerialService
from app.batch_serial.services.batch_serial_service import expiry_from_shelf_life
from app.branches.models import Warehouse, WarehouseStorageNode
from app.business.gating import assert_feature_fields, feature_enabled
from app.common.audit.services import record_audit
from app.common.report_names import (
    branch_names,
    product_names,
    vendor_names,
    vendors_matching,
    warehouse_names,
)
from app.core.database.batch import children_by_parent
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.pricing import inherited_share
from app.document_files.services import goods_receipt_file_counts
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
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.goods_receipt.billing import (
    RETURNED_STATES,
    ReceiptLineBilling,
    has_left_to_bill,
    receipt_line_billing,
)
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
    GoodsReceiptRegisterRecord,
    GoodsReceiptResponse,
    GoodsReceiptStatus,
    GoodsReceiptSummary,
    GoodsReceiptUpdate,
)
from app.goods_receipt.serials import ReceiptSerials
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.inventory.schemas import QuarantineAction, StockQuarantineCreate
from app.inventory.services import InventoryService, LineConversion
from app.products.models import Product, ProductCategory
from app.purchase.models import PurchaseOrder, PurchaseOrderHistory, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderStatus
from app.purchase.services.line_quantities import order_line_quantities
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
)
from app.purchase_invoice.schemas import PurchaseInvoiceStatus
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.gst_compliance import GstComplianceService
from app.tax.services.rule_stamp import stamps_tax_rules
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.trade_licences.services.licence_check import (
    LicenceCheckService,
    LicenceDocument,
)
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService, assert_quantity_fits_unit
from app.vendors.models import Vendor

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
        self._serials = ReceiptSerials(session)

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
        if filters.billable:
            statement = statement.where(has_left_to_bill())
            count = count.where(has_left_to_bill())
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                GoodsReceipt.grn_number.ilike(token),
                GoodsReceipt.purchase_order_number.ilike(token),
                GoodsReceipt.invoice_reference.ilike(token),
                GoodsReceipt.vehicle_number.ilike(token),
                GoodsReceipt.transport_details.ilike(token),
                GoodsReceipt.vendor_id.in_(vendors_matching(token)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        rows = self._session.scalars(
            statement.order_by(
                (
                    columns.get(sort_by, GoodsReceipt.created_at).desc()
                    if descending
                    else columns.get(sort_by, GoodsReceipt.created_at).asc()
                ),
                # Newest first within the chosen column: by date alone, a
                # day's receipts came back in id order, which is random
                # (D-UI-10). created_at is the transaction's start instant,
                # shared by every row one request wrote, so the id still
                # settles a tie, and paging over one cannot show a row twice.
                GoodsReceipt.created_at.desc(),
                GoodsReceipt.id.desc() if descending else GoodsReceipt.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> GoodsReceiptSummary:
        """Summarize goods receipts for the visible firm scope.

        Counted and summed in SQL, one row per status, rather than loading every
        receipt the firm ever raised (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    GoodsReceipt.status,
                    func.count(),
                    func.coalesce(func.sum(GoodsReceipt.grand_total), 0),
                )
                .where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.is_deleted.is_(False),
                )
                .group_by(GoodsReceipt.status)
            ).all()
        }

        def count(status: GoodsReceiptStatus) -> int:
            """Return how many documents are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        live = (
            GoodsReceipt.firm_id == firm_scope,
            GoodsReceipt.is_deleted.is_(False),
        )
        pending_po_count = int(
            self._session.scalar(
                select(func.count(func.distinct(GoodsReceipt.purchase_order_id))).where(
                    *live, GoodsReceipt.status == GoodsReceiptStatus.DRAFT.value
                )
            )
            or 0
        )
        partial_po_count = int(
            self._session.scalar(
                select(func.count(func.distinct(GoodsReceipt.purchase_order_id))).where(
                    *live,
                    GoodsReceipt.total_current_receipt_quantity > 0,
                    GoodsReceipt.status != GoodsReceiptStatus.CANCELLED.value,
                )
            )
            or 0
        )
        return GoodsReceiptSummary(
            total=sum(number for number, _ in by_status.values()),
            draft=count(GoodsReceiptStatus.DRAFT),
            completed=count(GoodsReceiptStatus.COMPLETED),
            cancelled=count(GoodsReceiptStatus.CANCELLED),
            closed=count(GoodsReceiptStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
            pending_purchase_orders=pending_po_count,
            partial_purchase_orders=partial_po_count,
        )

    def create_receipt(
        self, data: GoodsReceiptCreate, *, firm_id: UUID, actor_id: UUID
    ) -> GoodsReceipt:
        """Create receipt and commit."""
        row = self.stage_receipt(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_receipt(
        self, data: GoodsReceiptCreate, *, firm_id: UUID, actor_id: UUID
    ) -> GoodsReceipt:
        """Build one receipt as a draft without committing it."""
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
        self._assert_order_receivable(purchase_order)
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=purchase_order.branch_id
        )
        grn_number = self._issue_number(
            numbering_rule,
            typed=data.grn_number.strip().upper() if data.grn_number else None,
            number_column=GoodsReceipt.grn_number,
            firm_id=firm_id,
            document_date=data.receipt_date,
            actor_id=actor_id,
            branch_code=branch_code,
            company_code=company_code,
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
            eway_bill_number=data.eway_bill_number,
            eway_bill_date=data.eway_bill_date,
            invoice_reference=data.invoice_reference,
            remarks=data.remarks,
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
        # Absent keeps the e-way bill on file: a client that never showed it
        # cannot clear it.
        if "eway_bill_number" in data.model_fields_set:
            row.eway_bill_number = data.eway_bill_number
        if "eway_bill_date" in data.model_fields_set:
            row.eway_bill_date = data.eway_bill_date
        row.invoice_reference = data.invoice_reference
        row.remarks = data.remarks
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
        """Complete receipt and commit."""
        row = self.stage_complete(receipt_id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_complete(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> GoodsReceipt:
        """Complete receipt -- stock in, accrual posted -- without committing."""
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
        # One serial per unit received on every serial-tracked line, none
        # already a unit of this firm (PG-10). Checked before anything posts.
        self._serials.check_counts(
            row,
            self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id == row.id,
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all(),
        )
        # Warns only: the goods are on the dock whatever it says (backlog 54).
        licence_remark, licence_details = LicenceCheckService(
            self._session
        ).approve_purchase(LicenceDocument.GOODS_RECEIPT, row.id, firm_id=firm_scope)
        self._post_inventory(row, purchase_order=purchase_order, actor_id=actor_id)
        before = row.status
        row.status = GoodsReceiptStatus.COMPLETED.value
        row.completed_at = utc_now()
        row.updated_by = actor_id
        # Flushed first so this receipt is COMPLETED in the database before
        # its own quantities are summed; otherwise it would be excluded from
        # the total it is supposed to complete.
        self._session.flush()
        self._resync_order_status(purchase_order, firm_id=firm_scope, actor_id=actor_id)
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            receipt=row,
            action="COMPLETED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=licence_remark,
            details=licence_details,
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
        self._session.flush()
        return row

    def cancel_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> GoodsReceipt:
        """Cancel receipt and commit."""
        row = self.stage_cancel(
            receipt_id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        self._session.commit()
        return row

    def stage_cancel(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> GoodsReceipt:
        """Cancel receipt without committing."""
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status in {
            GoodsReceiptStatus.CANCELLED.value,
            GoodsReceiptStatus.CLOSED.value,
        }:
            return row
        self._assert_receipt_cancellable(row, firm_scope=firm_scope)
        # A unit sold or sent back since it arrived cannot be un-received
        # (PG-10); checked before any stock moves back.
        self._serials.refuse_cancel(row)
        before = row.status
        reversed_lines, stock_value = self._reverse_inventory(
            row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        self._serials.withdraw(row, actor_id=actor_id)
        # The stock is back off the shelf; take the journal off the books too,
        # or the ledger keeps a debit for goods the firm no longer holds -- and
        # take it off at what the shelf actually gave back, not at what the
        # receipt paid.
        self._reverse_receipt_journal(
            row, firm_scope=firm_scope, actor_id=actor_id, stock_value=stock_value
        )
        row.status = GoodsReceiptStatus.CANCELLED.value
        # Flushed before the order is resynced so this receipt has already
        # stopped being COMPLETED and drops out of its own total. Cancelling
        # the only receipt against an order walks it back to APPROVED; the
        # status is derived from what is still completed rather than
        # decremented, so there is no subtractive path to get wrong.
        self._session.flush()
        self._resync_order_status(
            self._purchase_order(row.purchase_order_id, firm_id=firm_scope),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
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
        self._session.flush()
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

    def _assert_receipt_cancellable(
        self, receipt: GoodsReceipt, *, firm_scope: UUID
    ) -> None:
        """Refuse to cancel a receipt a supplier has already billed for.

        The accounting cannot be unwound from here. Receiving posted
        `Dr Inventory / Cr goods received not invoiced`; approving the invoice
        cleared that accrual and raised a payable. Reversing the receipt now
        would debit the accrual a second time and leave it with a balance
        nobody can explain, while the payable stayed exactly where it was.

        Handing goods back after they have been invoiced is a purchase return,
        which credits the supplier as well as taking the stock off. Cancel the
        invoice first if it was the invoice that was wrong.
        """
        billed = self._session.scalar(
            select(PurchaseInvoiceLine.id)
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoiceLine.source_document_id == receipt.id,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
            )
            .limit(1)
        )
        if billed is None:
            from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine

            # Goods sent back off the receipt already left the shelf and took
            # their share of the accrual off (D-BUY-26); cancelling the whole
            # receipt would take both off a second time.
            returned = self._session.scalar(
                select(PurchaseReturn.return_number)
                .join(
                    PurchaseReturnLine,
                    PurchaseReturnLine.purchase_return_id == PurchaseReturn.id,
                )
                .where(
                    PurchaseReturnLine.source_document_type == "GOODS_RECEIPT",
                    PurchaseReturnLine.source_document_id == receipt.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status.in_(RETURNED_STATES),
                )
                .limit(1)
            )
            if returned is None:
                return
            raise ValidationError(
                f"Goods sent back off {receipt.grn_number} on {returned} have "
                "already left the shelf. Cancel that purchase return first."
            )
        raise ValidationError(
            f"Goods receipt {receipt.grn_number} has been invoiced, so "
            "cancelling it would leave the accrual and the payable "
            "disagreeing. Cancel the purchase invoice first, or raise a "
            "purchase return."
        )

    def _reverse_receipt_journal(
        self,
        receipt: GoodsReceipt,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        stock_value: Decimal,
    ) -> None:
        """Cancel the journal completing this receipt wrote, if it wrote one.

        `_reverse_inventory` put the stock back and nothing put the ledger
        back: `post_goods_receipt` had exactly one caller, on the complete
        path, and `reverse_entry` was never called for a receipt. So the
        general ledger's inventory balance drifted **above** the warehouse by
        the value of every cancelled receipt, and goods received not invoiced
        carried a liability for goods that had gone back. Neither self-corrects
        and the two ledgers cannot be reconciled afterwards.

        `reversal_of_id IS NULL` matters: `reverse_entry` copies the source
        module and id onto the mirror it posts, so without it a second pass
        would find that mirror -- itself POSTED -- and reverse the reversal.
        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "goods_receipt",
                JournalEntry.source_id == receipt.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # A receipt cancelled before it was completed posted nothing, and
            # a firm that received stock before posting existed has no entry
            # to take back either.
            return
        # Not a mirror. The accrual goes back in full -- the firm owes nobody
        # for goods it handed back -- while inventory is credited with what the
        # warehouse actually removed, and the difference is a purchase price
        # variance, exactly as it is on a purchase return. Mirroring credited
        # inventory at the receipt price and put a seeded store 2,287.42 out in
        # one request.
        DocumentPostingService(self._session).reverse_goods_receipt(
            firm_id=firm_scope,
            entry_id=entry_id,
            document_number=receipt.grn_number,
            stock_value=stock_value,
            actor_id=actor_id,
        )

    def _reverse_inventory(
        self,
        receipt: GoodsReceipt,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> tuple[int, Decimal]:
        """Undo the stock this receipt posted, if it had already been completed.

        A cancelled receipt that keeps its goods-receipt movements leaves stock
        the firm never accepted, so cancellation has to reverse each posted line
        and forget its movement.

        Returns what the reversal actually took out as well as how many lines
        it touched, because the journal has to follow the stock rather than the
        receipt: goods leave at the moving average they are carried at, which
        is only the price they arrived at until something else arrives at
        another one.

        Args:
            receipt: The receipt being cancelled.
            firm_scope: The owning firm.
            actor_id: The user cancelling the receipt.
            reason: Optional cancellation reason, stored on the reversal.

        Returns:
            How many lines were reversed, and the stock value they removed.

        """
        reversed_lines = 0
        movement_ids: list[UUID] = []
        self._undo_inspection_holds(
            receipt, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        for line in self._session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.inventory_transaction_id.is_not(None),
                GoodsReceiptLine.is_deleted.is_(False),
            )
        ).all():
            if line.inventory_transaction_id is None:
                continue
            movement = self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason or f"Goods receipt {receipt.grn_number} cancelled.",
            )
            if movement is not None:
                movement_ids.append(movement.id)
            line.inventory_transaction_id = None
            line.updated_by = actor_id
            reversed_lines += 1
        return reversed_lines, self._movement_value(movement_ids)

    def _needs_inspection(self, product: Product) -> bool:
        """Say whether this product's goods wait for an inspection (BUY-9)."""
        if product.inspection_required:
            return True
        if product.category_id is None:
            return False
        category = self._session.get(ProductCategory, product.category_id)
        return bool(category is not None and category.inspection_required)

    def _hold_for_inspection(
        self,
        receipt: GoodsReceipt,
        line: GoodsReceiptLine,
        transaction: InventoryTransaction,
        *,
        actor_id: UUID,
    ) -> None:
        """Move what this line put into stock into quarantine (BUY-9).

        The goods are owned and valued as received -- the hold posts nothing --
        but cannot be sold or issued until an inspection passes them.
        """
        held = Decimal(str(transaction.current_quantity_delta))
        if held <= ZERO:
            return
        hold = self._inventory.stage_quarantine(
            StockQuarantineCreate(
                branch_id=receipt.branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                batch_id=line.batch_id,
                action=QuarantineAction.HOLD,
                quantity=held,
                reference_number=f"{receipt.grn_number}-QC{line.line_number}",
                transaction_date=receipt.receipt_date,
                remarks=f"Awaiting inspection: {receipt.grn_number}",
            ),
            firm_scope=receipt.firm_id,
            actor_id=actor_id,
        )
        line.inspection_status = "PENDING"
        line.inspection_transaction_id = hold.id
        line.inspection_quantity = held

    def _undo_inspection_holds(
        self,
        receipt: GoodsReceipt,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> None:
        """Release a cancelled receipt's pending holds before reversing it.

        Raises:
            ValidationError: If an inspection on it was already decided --
                the goods were passed or rejected, so the receipt is history
                and is undone with a purchase return.

        """
        lines = self._session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id,
                GoodsReceiptLine.inspection_status.is_not(None),
                GoodsReceiptLine.is_deleted.is_(False),
            )
        ).all()
        decided = [
            line.line_number for line in lines if line.inspection_status == "DONE"
        ]
        if decided:
            raise ValidationError(
                f"{receipt.grn_number} cannot be cancelled: line(s) "
                f"{', '.join(str(n) for n in decided)} were already inspected. "
                "Send the goods back with a purchase return instead."
            )
        for line in lines:
            if line.inspection_transaction_id is not None:
                self._inventory.reverse_transaction(
                    line.inspection_transaction_id,
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                    reason=reason or f"Goods receipt {receipt.grn_number} cancelled.",
                )
            line.inspection_status = None
            line.inspection_transaction_id = None
            line.inspection_quantity = None

    def _movement_value(self, movement_ids: list[UUID]) -> Decimal:
        """Return what the stock ledger says those movements were worth."""
        if not movement_ids:
            return Decimal("0")
        total = self._session.scalar(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                StockLedgerEntry.transaction_id.in_(movement_ids),
                StockLedgerEntry.is_deleted.is_(False),
            )
        )
        return Decimal(str(total or 0))

    def close_receipt(
        self, receipt_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> GoodsReceipt:
        """Close one completed receipt.

        Closing says the receipt's business is finished; a draft has not begun
        it -- no stock moved and nothing accrued -- and closing one recorded a
        receipt that never happened as complete for good (D-BUY-9, driven on
        TEST01 on 2026-09-18: a DRAFT receipt went to CLOSED through
        `/close`). A draft is cancelled, not closed, the way a sales return is.
        """
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status == GoodsReceiptStatus.CLOSED.value:
            return row
        if row.status != GoodsReceiptStatus.COMPLETED.value:
            raise ValidationError("Only completed goods receipts can be closed.")
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
        return self.receipt_responses([row])[0]

    def receipt_responses(
        self, rows: Sequence[GoodsReceipt]
    ) -> list[GoodsReceiptResponse]:
        """Render a page of receipts, reading each child table once.

        One query per child table for the whole page, grouped by receipt in
        Python, rather than five per receipt (backlog 56 C, step 3). The
        single-receipt builder is this with a list of one.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        lines = children_by_parent(
            self._session,
            GoodsReceiptLine,
            GoodsReceiptLine.goods_receipt_id,
            ids,
            GoodsReceiptLine.line_number.asc(),
        )
        attachments = children_by_parent(
            self._session,
            GoodsReceiptAttachment,
            GoodsReceiptAttachment.goods_receipt_id,
            ids,
        )
        notes = children_by_parent(
            self._session,
            GoodsReceiptNote,
            GoodsReceiptNote.goods_receipt_id,
            ids,
        )
        warnings = self._duplicate_warnings(rows)
        eway_warnings = self._eway_bill_warnings(rows)
        every_line = [line for found in lines.values() for line in found]
        billing = receipt_line_billing(self._session, every_line)
        # The serials typed on the page's lines, and which of their products
        # carry them, each read once for the page (PG-10).
        serials = self._serials.typed(line.id for line in every_line)
        tracked = self._serials.tracked(line.product_id for line in every_line)
        vendors = {
            found[0]: (found[1], found[2])
            for found in self._session.execute(
                select(Vendor.id, Vendor.display_name, Vendor.code).where(
                    Vendor.id.in_({row.vendor_id for row in rows})
                )
            )
        }
        answer = [
            self._receipt_response(
                row,
                lines=lines[row.id],
                attachments=attachments[row.id],
                notes=notes[row.id],
                warning=warnings.get(row.id),
                vendor=vendors.get(row.vendor_id),
                eway_warning=eway_warnings.get(row.id),
                billing=billing,
                serials=serials,
                tracked=tracked,
            )
            for row in rows
        ]
        # Uploaded files, counted for the page in one grouped read (PG-4).
        files = goods_receipt_file_counts(self._session, ids)
        for response in answer:
            response.attached_file_count = files.get(response.id, 0)
        return answer

    def _receipt_response(
        self,
        row: GoodsReceipt,
        *,
        lines: list[GoodsReceiptLine],
        attachments: list[GoodsReceiptAttachment],
        notes: list[GoodsReceiptNote],
        warning: str | None,
        vendor: tuple[str, str] | None,
        eway_warning: str | None = None,
        billing: dict[UUID, ReceiptLineBilling] | None = None,
        serials: dict[UUID, list[str]] | None = None,
        tracked: set[UUID] | None = None,
    ) -> GoodsReceiptResponse:
        """Build one receipt's response from what the page already read."""
        payload = GoodsReceiptResponse.model_validate(row).model_dump(mode="python")
        payload["lines"] = []
        left_quantity = ZERO
        left_amount = ZERO
        for item in lines:
            line = GoodsReceiptLineResponse.model_validate(item).model_dump(
                mode="python"
            )
            line["serial_tracked"] = item.product_id in (tracked or set())
            line["serial_numbers"] = list((serials or {}).get(item.id, []))
            position = (billing or {}).get(item.id)
            if position is not None:
                accepted = Decimal(str(item.accepted_quantity))
                left = position.left_to_bill
                amount = (
                    self._q(Decimal(str(item.net_amount)) * left / accepted)
                    if accepted > ZERO
                    else ZERO
                )
                line["billed_quantity"] = position.billed
                line["returned_unbilled_quantity"] = position.returned_unbilled
                line["left_to_bill_quantity"] = left
                line["left_to_bill_amount"] = amount
                left_quantity += left
                left_amount += amount
            payload["lines"].append(line)
        payload["left_to_bill_quantity"] = left_quantity
        payload["left_to_bill_amount"] = left_amount
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
        payload["duplicate_warning"] = warning
        payload["eway_bill_warning"] = eway_warning
        payload["vendor_name"] = vendor[0] if vendor else ""
        payload["vendor_code"] = vendor[1] if vendor else ""
        return GoodsReceiptResponse.model_validate(payload)

    def _eway_bill_warnings(self, rows: Sequence[GoodsReceipt]) -> dict[UUID, str]:
        """Say which receipts arrived above the e-way bill limit with none.

        Backlog 78 row 6, CGST rule 138: goods worth more than the firm's
        limit (50,000 unless it set its state's) travel on an e-way bill.
        The supplier or transporter raises it and the buyer records its
        number; for an unregistered supplier's goods the buyer raises it.
        Warned, never refused -- the goods are already on the dock.
        """
        live = [
            row
            for row in rows
            if row.status != GoodsReceiptStatus.CANCELLED.value
            and not row.eway_bill_number
        ]
        if not live:
            return {}
        settings = GstComplianceService(self._session)
        limits = {
            firm_id: settings.settings_response(firm_id).eway_bill_limit
            for firm_id in {row.firm_id for row in live}
        }
        over = [
            row
            for row in live
            if Decimal(str(row.grand_total or 0)) > limits[row.firm_id]
        ]
        if not over:
            return {}
        unregistered = {
            vendor_id
            for vendor_id, gst_type, gstin in self._session.execute(
                select(Vendor.id, Vendor.gst_registration_type, Vendor.gstin).where(
                    Vendor.id.in_({row.vendor_id for row in over})
                )
            )
            if gst_type == "UNREGISTERED" or (gst_type is None and not gstin)
        }
        found: dict[UUID, str] = {}
        for row in over:
            value = f"{Decimal(str(row.grand_total)):,.2f}"
            limit = f"{limits[row.firm_id]:,.0f}"
            who = (
                "The supplier is unregistered, so the e-way bill is yours to "
                "raise; record its number here."
                if row.vendor_id in unregistered
                else "Record the number from the supplier's e-way bill."
            )
            found[row.id] = (
                f"Goods worth {value} need an e-way bill above {limit} (CGST "
                f"rule 138), and none is recorded. {who}"
            )
        return found

    def set_eway_bill(
        self,
        receipt_id: UUID,
        *,
        number: str | None,
        on: date | None,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> GoodsReceipt:
        """Record or clear a receipt's e-way bill (backlog 78 row 6).

        The number moves no stock and no money, so a completed or closed
        receipt takes it too -- it is often typed after the goods are in. A
        cancelled receipt is history and keeps what it had.
        """
        row = self.get_receipt(receipt_id, firm_scope=firm_scope)
        if row.status == GoodsReceiptStatus.CANCELLED.value:
            raise ValidationError("A cancelled goods receipt cannot be changed.")
        on = on if number else None
        before: dict[str, object] = {
            "eway_bill_number": row.eway_bill_number,
            "eway_bill_date": (
                row.eway_bill_date.isoformat() if row.eway_bill_date else None
            ),
        }
        after: dict[str, object] = {
            "eway_bill_number": number,
            "eway_bill_date": on.isoformat() if on else None,
        }
        if before == after:
            return row
        row.eway_bill_number = number
        row.eway_bill_date = on
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="goods_receipt.eway_bill_set",
            entity_type="goods_receipt",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data=after,
        )
        self._session.commit()
        return row

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
        """Return the receipts still in draft, newest first."""
        return list(
            self._session.scalars(
                select(GoodsReceipt)
                .where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.status == GoodsReceiptStatus.DRAFT.value,
                    GoodsReceipt.is_deleted.is_(False),
                )
                .order_by(
                    GoodsReceipt.receipt_date.desc(), GoodsReceipt.created_at.desc()
                )
            ).all()
        )

    #: The states in which a receipt's goods have been taken into stock.
    #: Closing follows completing and takes nothing back out, so a closed
    #: receipt is as received as a completed one -- and "completed" used to
    #: mean the status alone, so the report shrank as the firm tidied up
    #: (D-RPT-15). `_received_quantities_for_po` counts the same pair.
    _RECEIVED_STATUSES = (
        GoodsReceiptStatus.COMPLETED.value,
        GoodsReceiptStatus.CLOSED.value,
    )

    def register_rows(
        self, rows: list[GoodsReceipt]
    ) -> list[GoodsReceiptRegisterRecord]:
        """Flatten receipts to one row each, naming vendor and warehouse.

        One read per table for the whole report; the warehouse used to be an
        id alone, and the grid derives its columns from the row (D-RPT-17).
        """
        names = vendor_names(self._session, (row.vendor_id for row in rows))
        warehouses = warehouse_names(self._session, (row.warehouse_id for row in rows))
        records = [
            GoodsReceiptRegisterRecord(
                receipt_id=row.id,
                grn_number=row.grn_number,
                receipt_date=row.receipt_date,
                purchase_order_id=row.purchase_order_id,
                purchase_order_number=row.purchase_order_number,
                vendor_id=row.vendor_id,
                vendor_name=names.get(row.vendor_id, str(row.vendor_id)),
                warehouse_id=row.warehouse_id,
                warehouse_name=warehouses.get(row.warehouse_id, str(row.warehouse_id)),
                status=row.status,
                total_current_receipt_quantity=row.total_current_receipt_quantity,
                total_accepted_quantity=row.total_accepted_quantity,
                total_rejected_quantity=row.total_rejected_quantity,
                total_damaged_quantity=row.total_damaged_quantity,
                grand_total=row.grand_total,
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def completed_receipts(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[GoodsReceipt]:
        """Return the receipts whose goods are in stock: completed, or closed after.

        Narrowed to the window on the receipt's own date, and paged in SQL.
        """
        return window.fetch(
            self._session,
            select(GoodsReceipt)
            .where(
                GoodsReceipt.firm_id == firm_scope,
                GoodsReceipt.status.in_(self._RECEIVED_STATUSES),
                GoodsReceipt.is_deleted.is_(False),
                *window.dated(GoodsReceipt.receipt_date),
            )
            .order_by(
                GoodsReceipt.receipt_date.desc(),
                GoodsReceipt.created_at.desc(),
                GoodsReceipt.id.desc(),
            ),
        )

    def _received_lines_where(
        self, firm_scope: UUID, *clauses: ColumnElement[bool]
    ) -> Select[Any]:
        """Lines of receipts whose goods arrived, narrowed by ``clauses``.

        A DRAFT has booked nothing in and a CANCELLED receipt took its stock
        back out, so damage or rejection on either is not something that
        happened at the gate; both used to be listed (D-RPT-15: a receipt with
        1 damaged and 1 rejected stayed in both reports after cancellation).
        """
        return (
            select(GoodsReceiptLine)
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(
                GoodsReceipt.firm_id == firm_scope,
                GoodsReceipt.status.in_(self._RECEIVED_STATUSES),
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceiptLine.is_deleted.is_(False),
                *clauses,
            )
            .order_by(
                GoodsReceipt.receipt_date.desc(),
                GoodsReceipt.id.desc(),
                GoodsReceiptLine.line_number,
                GoodsReceiptLine.id,
            )
        )

    def rejected_items(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[GoodsReceiptLine]:
        """Return the lines rejected on a receipt whose goods arrived."""
        return window.fetch(
            self._session,
            self._received_lines_where(
                firm_scope,
                GoodsReceiptLine.rejected_quantity > ZERO,
                *window.dated(GoodsReceipt.receipt_date),
            ),
        )

    def damaged_items(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[GoodsReceiptLine]:
        """Return the lines damaged on a receipt whose goods arrived."""
        return window.fetch(
            self._session,
            self._received_lines_where(
                firm_scope,
                GoodsReceiptLine.damaged_quantity > ZERO,
                *window.dated(GoodsReceipt.receipt_date),
            ),
        )

    def line_report_rows(
        self, lines: list[GoodsReceiptLine]
    ) -> list[GoodsReceiptLineResponse]:
        """Answer the rejected and damaged reports with the names they need.

        The lines carry `product_id` and `warehouse_id` and nothing to read
        them by, so both reports showed a UUID where the product belongs
        (D-RPT-17). One read for the products and one for the warehouses,
        whatever the report's length.
        """
        products = product_names(self._session, (line.product_id for line in lines))
        warehouses = warehouse_names(
            self._session, (line.warehouse_id for line in lines)
        )
        rows: list[GoodsReceiptLineResponse] = []
        for line in lines:
            record = GoodsReceiptLineResponse.model_validate(line)
            code, name = products.get(line.product_id, ("", str(line.product_id)))
            record.product_code = code
            record.product_name = name
            record.warehouse_name = warehouses.get(
                line.warehouse_id, str(line.warehouse_id)
            )
            rows.append(record)
        return mapped_like(lines, rows)

    def partially_received_purchase_orders(
        self, *, firm_scope: UUID
    ) -> list[GoodsReceiptPurchaseOrderReport]:
        """List the orders part received: some goods in, some still to come.

        Read off the orders the receiving side has moved to PARTIALLY_RECEIVED,
        with the quantities summed the way the order's own status is --
        `_received_quantities_for_po`, COMPLETED and CLOSED receipts alike --
        so the report and the order cannot disagree. It used to walk orders of
        every status and count COMPLETED receipts alone: close one receipt and
        the order read RECEIVED while the report said 6 of 10 (D-RPT-14). Names
        are read in one query each.
        """
        purchase_orders = list(
            self._session.scalars(
                select(PurchaseOrder)
                .where(
                    PurchaseOrder.firm_id == firm_scope,
                    PurchaseOrder.is_deleted.is_(False),
                    PurchaseOrder.status
                    == PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
                )
                .order_by(
                    PurchaseOrder.purchase_date.asc(), PurchaseOrder.po_number.asc()
                )
            ).all()
        )
        if not purchase_orders:
            return []
        order_ids = [order.id for order in purchase_orders]
        lines_by_order: dict[UUID, list[PurchaseOrderLine]] = defaultdict(list)
        for line in self._session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id.in_(order_ids),
                PurchaseOrderLine.is_deleted.is_(False),
            )
        ).all():
            lines_by_order[line.purchase_order_id].append(line)
        receipt_counts: dict[UUID, int] = {
            order_id: int(count)
            for order_id, count in self._session.execute(
                select(GoodsReceipt.purchase_order_id, func.count())
                .where(
                    GoodsReceipt.firm_id == firm_scope,
                    GoodsReceipt.purchase_order_id.in_(order_ids),
                    GoodsReceipt.status.in_(self._RECEIVED_STATUSES),
                    GoodsReceipt.is_deleted.is_(False),
                )
                .group_by(GoodsReceipt.purchase_order_id)
            ).all()
        }
        suppliers = vendor_names(
            self._session, (order.vendor_id for order in purchase_orders)
        )
        branches = branch_names(
            self._session, (order.branch_id for order in purchase_orders)
        )
        warehouses = warehouse_names(
            self._session, (order.warehouse_id for order in purchase_orders)
        )
        reports: list[GoodsReceiptPurchaseOrderReport] = []
        for purchase_order in purchase_orders:
            lines = lines_by_order.get(purchase_order.id, [])
            if not lines:
                continue
            taken = self._received_quantities_for_po(
                purchase_order.id, firm_id=firm_scope
            )
            ordered = sum((line.ordered_quantity for line in lines), ZERO)
            received = sum((taken.get(line.id, ZERO) for line in lines), ZERO)
            reports.append(
                GoodsReceiptPurchaseOrderReport(
                    purchase_order_id=purchase_order.id,
                    purchase_order_number=purchase_order.po_number,
                    vendor_id=purchase_order.vendor_id,
                    vendor_name=suppliers.get(
                        purchase_order.vendor_id, str(purchase_order.vendor_id)
                    ),
                    branch_id=purchase_order.branch_id,
                    branch_name=branches.get(
                        purchase_order.branch_id, str(purchase_order.branch_id)
                    ),
                    warehouse_id=purchase_order.warehouse_id,
                    warehouse_name=warehouses.get(
                        purchase_order.warehouse_id, str(purchase_order.warehouse_id)
                    ),
                    ordered_quantity=self._q(ordered),
                    received_quantity=self._q(received),
                    pending_quantity=self._q(ordered - received),
                    receipt_count=receipt_counts.get(purchase_order.id, 0),
                    status=purchase_order.status,
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

    @stamps_tax_rules(GoodsReceiptLine, "goods_receipt_id")
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
        kept: dict[int, GoodsReceiptLine] = {}
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
            # Capped at what the order line still owes, for every receipt: a
            # body flag switched this off and a body percentage widened it, so
            # 20 more came in against an order of 10 already received in full
            # (D-BUY-16).
            if prev_received + self._q(line.current_receipt_quantity) > (
                ordered_quantity
            ):
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
            # The order line's share of the whole-order discount, for the part
            # of it received, comes off before tax as it did on the order; the
            # stock is valued without it otherwise (D-BUY-19).
            bill_share = min(
                inherited_share(
                    purchase_line.bill_discount_amount,
                    part=accepted,
                    whole=ordered_quantity,
                ),
                self._q(gross_amount - discount_amount),
            )
            line_subtotal = self._q(gross_amount - discount_amount - bill_share)
            tax_amount = self._line_tax_amount(
                document_id=receipt.id,
                line_number=line.line_number,
                firm_id=firm_id,
                actor_id=actor_id,
                tax_profile_id=line.tax_profile_id or purchase_line.tax_profile_id,
                product_id=purchase_line.product_id,
                vendor_id=receipt.vendor_id,
                branch_id=receipt.branch_id,
                receipt_date=receipt.receipt_date,
                taxable=line_subtotal,
            )
            net_amount = self._q(line_subtotal + tax_amount)
            # Only the manufacturing date typed: the product's shelf life
            # fills the expiry (STK-18). A typed expiry always stands.
            expiry_date = line.expiry_date
            if (
                expiry_date is None
                and line.manufacturing_date is not None
                # Never fill what the firm's profile would then refuse.
                and feature_enabled(self._session, firm_id, "EXPIRY_TRACKING")
            ):
                shelf_life = self._session.scalar(
                    select(Product.shelf_life_days).where(
                        Product.id == purchase_line.product_id
                    )
                )
                expiry_date = expiry_from_shelf_life(
                    line.manufacturing_date, shelf_life
                )
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
                bill_discount_amount=bill_share,
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
                # A blank scheme takes the one the order line's free goods
                # came from (PG-11); a typed one stands.
                scheme_name=(line.scheme_name or "").strip()
                or (purchase_line.scheme_name if line.free_quantity > ZERO else None),
                expiry_date=expiry_date,
                manufacturing_date=line.manufacturing_date,
                mrp=line.mrp,
                selling_price=line.selling_price,
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
                kept[line.line_number] = row
            else:
                self._apply_line_values(
                    persisted,
                    row,
                    actor_id=actor_id,
                    preserve=("inventory_transaction_id",),
                )
                kept[line.line_number] = persisted
            seen.add(line.line_number)
        obsolete_lines = [
            obsolete
            for line_number, obsolete in existing.items()
            if line_number not in seen
        ]
        self._serials.clear_lines(line.id for line in obsolete_lines)
        for obsolete in obsolete_lines:
            self._session.delete(obsolete)
        self._session.flush()
        # The serials each line typed (PG-10). Absent leaves what the line
        # holds -- a client that never showed them cannot clear them -- and
        # an empty list clears it.
        for line in data.lines:
            if line.serial_numbers is not None:
                self._serials.replace(
                    receipt,
                    kept[line.line_number],
                    line.serial_numbers,
                    actor_id=actor_id,
                )
        self._serials.refuse_repeats(receipt, list(kept.values()))
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
            # The batch number is typed off the carton. Resolving it to a real
            # batch is what puts the goods in that batch's stock row instead of
            # the product's single one; without it the batch register and the
            # goods on the shelf stay two unrelated records of one delivery.
            batch_id: UUID | None = None
            # `require_batch_on_receipt` is the product saying its goods cannot
            # be taken in unidentified -- a medicine that has to be recallable,
            # a food with an expiry. It was stored, returned by the API and
            # read by nothing, so a receipt could take in batch-tracked stock
            # with no batch and the shortfall only surfaced at a recall, when
            # it is too late to fix.
            product = self._session.get(Product, line.product_id)
            if (
                product is not None
                and product.require_batch_on_receipt
                and not (line.batch_number or "").strip()
            ):
                raise ValidationError(
                    f"{product.code} must be received with a batch number."
                )
            if (line.batch_number or "").strip():
                batch_id = (
                    BatchSerialService(self._session)
                    .resolve_for_receipt(
                        firm_scope=receipt.firm_id,
                        actor_id=actor_id,
                        product_id=line.product_id,
                        batch_number=line.batch_number or "",
                        branch_id=receipt.branch_id,
                        warehouse_id=line.warehouse_id,
                        vendor_id=receipt.vendor_id,
                        expiry_date=line.expiry_date,
                        mrp=line.mrp,
                        selling_price=line.selling_price,
                        manufacturing_date=line.manufacturing_date,
                        shelf_life_days=(
                            product.shelf_life_days if product is not None else None
                        ),
                    )
                    .id
                )
                line.batch_id = batch_id
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
                line_conversion=LineConversion(
                    line.conversion_factor, line.inventory_uom_id
                ),
                remarks=line.remarks,
                batch_id=batch_id,
            )
            line.inventory_transaction_id = transaction.id
            # The units start their trail here, where the goods landed.
            self._serials.receive(receipt, line, transaction, actor_id=actor_id)
            if product is not None and self._needs_inspection(product):
                self._hold_for_inspection(receipt, line, transaction, actor_id=actor_id)
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
            if previous + line.current_receipt_quantity > expected:
                raise ValidationError(
                    "Receipt exceeds allowed quantity for purchase order line "
                    f"{purchase_line.line_number}."
                )

    def _assert_order_receivable(self, purchase_order: PurchaseOrder) -> None:
        """Refuse a receipt against an order nobody has committed the firm to.

        Nothing checked this. A draft purchase order could be received against
        and the receipt completed, which posts stock and posts to the ledger --
        so the approval step was bypassable entirely by any client that did not
        happen to filter its own picker, and the order stayed DRAFT afterwards
        because the status resync only moves an order already in the receiving
        part of its life.

        RECEIVED is allowed through; the quantity cap, not the status, is what
        refuses taking in more than was ordered (D-BUY-16).
        """
        receivable = {
            PurchaseOrderStatus.APPROVED.value,
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
            PurchaseOrderStatus.RECEIVED.value,
        }
        if purchase_order.status in receivable:
            return
        raise ValidationError(
            f"Purchase order {purchase_order.po_number} is "
            f"{purchase_order.status}; goods can only be received against an "
            "approved order."
        )

    def resync_order_status(
        self, purchase_order: PurchaseOrder, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Move the order to match what it holds; see `_resync_order_status`.

        Public for the purchase return: a return whose goods are to be
        replaced reopens what the order is owed (backlog 69 row 7).
        """
        self._resync_order_status(purchase_order, firm_id=firm_id, actor_id=actor_id)

    def _resync_order_status(
        self, purchase_order: PurchaseOrder, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Move the order to match what has actually been received.

        `PARTIALLY_RECEIVED` and `RECEIVED` were declared from the first
        migration and **nothing ever wrote them**, so a fully received order
        still read APPROVED and every screen had to derive "is this finished?"
        from the receipts. The guards that refuse to delete or cancel a
        RECEIVED order, and the dashboard's open count that already excludes
        one, were written for a status no code produced.

        Derived rather than incremented: the received quantity is summed from
        the completed receipts every time, so cancelling one walks the order
        back down without needing a second, subtractive path to get wrong.

        Only ever moves an order that is already in the receiving part of its
        life. A DRAFT, SUBMITTED, CANCELLED or CLOSED order is left exactly
        where it is -- receiving against a cancelled order is a different
        problem, and quietly reviving one here would hide it.
        """
        movable = {
            PurchaseOrderStatus.APPROVED.value,
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
            PurchaseOrderStatus.RECEIVED.value,
        }
        if purchase_order.status not in movable:
            return

        received = self._received_quantities_for_po(purchase_order.id, firm_id=firm_id)
        lines = self._session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == purchase_order.id,
                PurchaseOrderLine.is_deleted.is_(False),
            )
        ).all()
        if not lines:
            return

        total = ZERO
        complete = True
        for line in lines:
            got = received.get(line.id, ZERO)
            total += got
            if got < self._q(line.ordered_quantity):
                complete = False

        if complete:
            target = PurchaseOrderStatus.RECEIVED.value
        elif total > ZERO:
            target = PurchaseOrderStatus.PARTIALLY_RECEIVED.value
        else:
            # Every receipt against it has been cancelled.
            target = PurchaseOrderStatus.APPROVED.value
        if target == purchase_order.status:
            return

        before = purchase_order.status
        purchase_order.status = target
        purchase_order.updated_by = actor_id
        # The order's own trail, beside the audit row. Every other status this
        # order takes writes a `purchase_order_history` row, and receiving --
        # the one transition raised from outside the purchase module -- wrote
        # only an audit entry, so the Purchase Order screen's History tab
        # skipped from "approved" to "closed" with nothing to say the goods
        # ever arrived (D-BUY-8). The history table is the purchase module's,
        # but so is the status field this method already writes: receiving
        # moving the order is one of the four transitions that reach across.
        self._session.add(
            PurchaseOrderHistory(
                purchase_order_id=purchase_order.id,
                firm_id=firm_id,
                action="purchase.received_status_changed",
                from_status=before,
                to_status=target,
                details_json=json.dumps({"received_quantity": str(total)}),
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        record_audit(
            self._session,
            action="purchase.received_status_changed",
            entity_type="purchase_order",
            entity_id=purchase_order.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": before},
            after_data={"status": target},
        )

    def _received_quantities_for_po(
        self,
        purchase_order_id: UUID,
        *,
        firm_id: UUID,
        exclude_receipt_id: UUID | None = None,
    ) -> dict[UUID, Decimal]:
        """Return what each order line has taken in, per order line.

        A CLOSED receipt counts: closing says its business is finished, not
        that its goods left. Counting COMPLETED alone let a closed receipt's
        quantity be received a second time, and walked a fully received order
        back to PARTIALLY_RECEIVED when a later receipt was cancelled
        (D-BUY-16, driven on TEST01 on 2026-09-19).
        """
        statement = (
            select(
                GoodsReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(GoodsReceiptLine.current_receipt_quantity), 0),
            )
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(
                GoodsReceipt.firm_id == firm_id,
                GoodsReceipt.purchase_order_id == purchase_order_id,
                GoodsReceipt.status.in_(
                    (
                        GoodsReceiptStatus.COMPLETED.value,
                        GoodsReceiptStatus.CLOSED.value,
                    )
                ),
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceiptLine.is_deleted.is_(False),
            )
            .group_by(GoodsReceiptLine.purchase_order_line_id)
        )
        if exclude_receipt_id is not None:
            statement = statement.where(GoodsReceipt.id != exclude_receipt_id)
        received = {
            row[0]: self._q(row[1] or 0)
            for row in self._session.execute(statement).all()
        }
        # Goods sent back to be replaced are owed again: the order line takes
        # in that much more, and reads as not fully received until it has
        # (backlog 69 row 7).
        lines = self._session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == purchase_order_id,
                PurchaseOrderLine.is_deleted.is_(False),
            )
        ).all()
        for line_id, figures in order_line_quantities(self._session, lines).items():
            if figures.replaced > ZERO and line_id in received:
                received[line_id] = self._q(received[line_id] - figures.replaced)
        return received

    def _duplicate_warnings(self, rows: Sequence[GoodsReceipt]) -> dict[UUID, str]:
        """Answer `_duplicate_warning` for a page of receipts in one query."""
        holders: dict[tuple[object, ...], set[UUID]] = defaultdict(set)
        for found in self._session.execute(
            select(
                GoodsReceipt.id,
                GoodsReceipt.firm_id,
                GoodsReceipt.purchase_order_id,
                GoodsReceipt.receipt_date,
            ).where(
                GoodsReceipt.firm_id.in_({row.firm_id for row in rows}),
                GoodsReceipt.receipt_date.in_({row.receipt_date for row in rows}),
                GoodsReceipt.status == GoodsReceiptStatus.COMPLETED.value,
                GoodsReceipt.is_deleted.is_(False),
            )
        ):
            holders[tuple(found[1:])].add(found[0])
        return {
            row.id: (
                "A completed receipt already exists for the same purchase order "
                "and date."
            )
            for row in rows
            if holders.get(
                (row.firm_id, row.purchase_order_id, row.receipt_date), set()
            )
            - {row.id}
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
        # A line's quantity is refused here, where it is written, rather
        # than when its stock moves (D-CFG-11).
        assert_quantity_fits_unit(
            self._session,
            quantity=quantity,
            uom_id=purchase_uom_id or inventory_uom_id,
            product_id=product_id,
            firm_id=firm_id,
        )
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
            "version": response.version_number,
        }

    def _line_tax_amount(
        self,
        *,
        firm_id: UUID,
        actor_id: UUID,
        tax_profile_id: UUID | None,
        product_id: UUID,
        vendor_id: UUID | None,
        branch_id: UUID | None,
        receipt_date: date,
        taxable: Decimal,
        document_id: UUID | None = None,
        line_number: int | None = None,
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
                # The supply's own nature, not just the document's name: a
                # supplier in another state charges IGST (D-CMP-14).
                transaction_type=self._tax.inward_transaction_type(
                    "GOODS_RECEIPT",
                    firm_id=firm_id,
                    branch_id=branch_id,
                    vendor_id=vendor_id,
                ),
                transaction_date=receipt_date,
                tax_profile_id=tax_profile_id,
                branch_id=branch_id,
                vendor_id=vendor_id,
                product_id=product_id,
                invoice_value=self._q(taxable),
                additional_context={
                    "source": "goods_receipt",
                    "document_type": "GOODS_RECEIPT",
                },
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            document_id=document_id,
            line_number=line_number,
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
