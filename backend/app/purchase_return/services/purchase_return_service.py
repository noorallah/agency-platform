"""Purchase return workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.batch_serial.services import BatchSerialService
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.pricing import LineDiscount, resolve_line_discount
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
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.inventory.models import StockLedgerEntry
from app.inventory.services import InventoryService
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnAccountingEvent,
    PurchaseReturnAttachment,
    PurchaseReturnLine,
    PurchaseReturnNote,
    PurchaseReturnSource,
)
from app.purchase_return.schemas import (
    PurchaseReturnAccountingEventResponse,
    PurchaseReturnAccountingEventType,
    PurchaseReturnAttachmentResponse,
    PurchaseReturnAttachmentWrite,
    PurchaseReturnByProductRecord,
    PurchaseReturnByVendorRecord,
    PurchaseReturnCreate,
    PurchaseReturnImportRequest,
    PurchaseReturnLineResponse,
    PurchaseReturnListFilters,
    PurchaseReturnNoteResponse,
    PurchaseReturnNoteWrite,
    PurchaseReturnReconciliationRecord,
    PurchaseReturnRegisterRecord,
    PurchaseReturnResponse,
    PurchaseReturnSourceResponse,
    PurchaseReturnSourceType,
    PurchaseReturnStatus,
    PurchaseReturnSummary,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService
from app.vendors.models import Vendor

ZERO = Decimal("0")

# The line shapes this document can be raised from. Naming the union lets the
# helpers below say what they accept instead of taking ``object`` and reaching
# for attributes mypy cannot see.
SourceLine = GoodsReceiptLine | PurchaseInvoiceLine | PurchaseOrderLine


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


class PurchaseReturnService(TransactionalDocumentService):
    """Coordinate supplier return lifecycle and source-document validation."""

    DOCUMENT = DocumentTypeSpec(
        code="PURCHASE_RETURN",
        name="Purchase Return",
        description="Supplier return document",
        category="PURCHASE",
        module="purchase_return",
        prefix="PR",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("COMPLETED", "Completed", 3),
            DocumentStateSpec("CANCELLED", "Cancelled", 4, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 5, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)
        self._inventory = InventoryService(session)
        self._posting = DocumentPostingService(session)

    def list_returns(
        self,
        *,
        firm_scope: UUID,
        filters: PurchaseReturnListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[PurchaseReturn], int]:
        """List purchase returns for the visible firm scope."""
        columns = {
            "return_number": PurchaseReturn.return_number,
            "return_date": PurchaseReturn.return_date,
            "warehouse_id": PurchaseReturn.warehouse_id,
            "grand_total": PurchaseReturn.grand_total,
            "status": PurchaseReturn.status,
            "created_at": PurchaseReturn.created_at,
            "updated_at": PurchaseReturn.updated_at,
        }
        statement = select(PurchaseReturn).where(PurchaseReturn.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(PurchaseReturn)
            .where(PurchaseReturn.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(PurchaseReturn.is_deleted.is_(False))
            count = count.where(PurchaseReturn.is_deleted.is_(False))
        if filters.vendor_id is not None:
            statement = statement.where(PurchaseReturn.vendor_id == filters.vendor_id)
            count = count.where(PurchaseReturn.vendor_id == filters.vendor_id)
        if filters.branch_id is not None:
            statement = statement.where(PurchaseReturn.branch_id == filters.branch_id)
            count = count.where(PurchaseReturn.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                PurchaseReturn.warehouse_id == filters.warehouse_id
            )
            count = count.where(PurchaseReturn.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(PurchaseReturn.status == filters.status.value)
            count = count.where(PurchaseReturn.status == filters.status.value)
        if filters.return_from is not None:
            statement = statement.where(
                PurchaseReturn.return_date >= filters.return_from
            )
            count = count.where(PurchaseReturn.return_date >= filters.return_from)
        if filters.return_to is not None:
            statement = statement.where(PurchaseReturn.return_date <= filters.return_to)
            count = count.where(PurchaseReturn.return_date <= filters.return_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                PurchaseReturn.return_number.ilike(token),
                PurchaseReturn.supplier_return_number.ilike(token),
                PurchaseReturn.reference_number.ilike(token),
                PurchaseReturn.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, PurchaseReturn.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    sort_column.desc() if descending else sort_column.asc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> PurchaseReturnSummary:
        """Return aggregate purchase return values for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                )
            ).all()
        )
        return PurchaseReturnSummary(
            total=len(rows),
            draft=sum(
                1 for row in rows if row.status == PurchaseReturnStatus.DRAFT.value
            ),
            approved=sum(
                1 for row in rows if row.status == PurchaseReturnStatus.APPROVED.value
            ),
            completed=sum(
                1 for row in rows if row.status == PurchaseReturnStatus.COMPLETED.value
            ),
            cancelled=sum(
                1 for row in rows if row.status == PurchaseReturnStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in rows if row.status == PurchaseReturnStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
        )

    def create_return(
        self, data: PurchaseReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Create one purchase return."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_return_sources(
            data, firm_id=firm_id
        )
        branch_id = data.branch_id or header["branch_id"]
        vendor_id = data.vendor_id or header["vendor_id"]
        business_profile_id = data.business_profile_id
        if vendor_id != header["vendor_id"]:
            raise ValidationError("Return vendor must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Return branch must match all source documents.")
        if data.supplier_return_number:
            self._validate_supplier_return_number(
                firm_id=firm_id,
                vendor_id=vendor_id,
                supplier_return_number=data.supplier_return_number,
            )
        return_number = (
            data.return_number.strip().upper()
            if data.return_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.return_date, firm_id
                ),
                branch_code=self._scope_code(branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.return_date,
                actor_id=actor_id,
            )
        )
        row = PurchaseReturn(
            firm_id=firm_id,
            vendor_id=vendor_id,
            branch_id=branch_id,
            warehouse_id=data.warehouse_id,
            business_profile_id=business_profile_id,
            return_number=return_number,
            return_date=data.return_date,
            supplier_return_number=(
                data.supplier_return_number.strip()
                if data.supplier_return_number
                else None
            ),
            supplier_return_date=data.supplier_return_date,
            reference_grn_number=data.reference_grn_number,
            reference_invoice_number=data.reference_invoice_number,
            return_reason=data.return_reason,
            currency_code=(
                data.currency_code.strip().upper() if data.currency_code else None
            ),
            exchange_rate=data.exchange_rate,
            payment_terms=data.payment_terms,
            due_date=data.due_date,
            reference_number=data.reference_number,
            remarks=data.remarks,
            allow_direct_purchase_order=data.allow_direct_purchase_order,
            allow_over_return=data.allow_over_return,
            over_return_percent=self._q(data.over_return_percent),
            status=PurchaseReturnStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_id,
            return_date=data.return_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_returned_quantity = line_totals[
            "total_already_returned_quantity"
        ]
        row.total_current_return_quantity = line_totals["total_current_return_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_id
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_id)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_id)
        self._record_event(
            firm_id=firm_id,
            document_type=document_type,
            document=row,
            action="CREATED",
            from_state=None,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_return.created",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"return_number": row.return_number, "status": row.status},
        )
        self._flush_or_conflict("Purchase return number already exists in this firm.")
        self._session.commit()
        return row

    def update_return(
        self,
        return_id: UUID,
        data: PurchaseReturnCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseReturn:
        """Replace one purchase return."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != PurchaseReturnStatus.DRAFT.value:
            raise ValidationError("Only draft purchase returns can be updated.")
        self._delete_children(row.id)
        header, source_rows, line_specs = self._prepare_return_sources(data, firm_scope)
        row.vendor_id = data.vendor_id or header["vendor_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.warehouse_id = data.warehouse_id
        row.business_profile_id = data.business_profile_id
        row.return_date = data.return_date
        row.supplier_return_number = (
            data.supplier_return_number.strip() if data.supplier_return_number else None
        )
        row.supplier_return_date = data.supplier_return_date
        row.reference_grn_number = data.reference_grn_number
        row.reference_invoice_number = data.reference_invoice_number
        row.return_reason = data.return_reason
        row.currency_code = (
            data.currency_code.strip().upper() if data.currency_code else None
        )
        row.exchange_rate = data.exchange_rate
        row.payment_terms = data.payment_terms
        row.due_date = data.due_date
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.allow_direct_purchase_order = data.allow_direct_purchase_order
        row.allow_over_return = data.allow_over_return
        row.over_return_percent = self._q(data.over_return_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        if row.supplier_return_number:
            self._validate_supplier_return_number(
                firm_id=firm_scope,
                vendor_id=row.vendor_id,
                supplier_return_number=row.supplier_return_number,
                current_id=row.id,
            )
        self._replace_sources(row, source_rows, firm_id=firm_scope, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_scope,
            return_date=data.return_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_returned_quantity = line_totals[
            "total_already_returned_quantity"
        ]
        row.total_current_return_quantity = line_totals["total_current_return_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_scope
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_scope)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_return.updated",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def approve_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Approve one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != PurchaseReturnStatus.DRAFT.value:
            raise ValidationError("Only draft purchase returns can be approved.")
        before = row.status
        row.status = PurchaseReturnStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="APPROVED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_return.approved",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def complete_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Complete one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == PurchaseReturnStatus.COMPLETED.value:
            return row
        if row.status in {
            PurchaseReturnStatus.CANCELLED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            raise ValidationError(
                "Cancelled/closed purchase returns cannot be completed."
            )
        if row.status != PurchaseReturnStatus.APPROVED.value:
            raise ValidationError("Only approved purchase returns can be completed.")
        lines = list(
            self._session.scalars(
                select(PurchaseReturnLine).where(
                    PurchaseReturnLine.purchase_return_id == row.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                )
            ).all()
        )
        if not lines:
            raise ValidationError("Purchase return must contain at least one line.")
        movement_ids: list[UUID] = []
        for line in lines:
            if line.warehouse_id is None:
                raise ValidationError(
                    "Warehouse is required on all return lines before completion."
                )
            current_qty = line.current_return_quantity
            rejected_qty = line.rejected_quantity
            sellable_qty = self._q(current_qty - rejected_qty)
            if sellable_qty < ZERO:
                raise ValidationError(
                    "Rejected quantity cannot exceed returned quantity."
                )
            batch_id = self._resolve_return_batch(line)
            if batch_id is not None:
                line.batch_id = batch_id
            transaction = self._inventory.record_purchase_return(
                firm_scope=firm_scope,
                actor_id=actor_id,
                branch_id=row.branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                reference_number=row.return_number,
                transaction_date=row.return_date,
                return_quantity=current_qty,
                sellable_quantity=sellable_qty,
                damaged_quantity=rejected_qty if line.is_damaged else ZERO,
                scrap_quantity=rejected_qty if line.is_scrap else ZERO,
                quarantine_quantity=(
                    rejected_qty if line.item_condition == "QUARANTINE" else ZERO
                ),
                entered_quantity=current_qty,
                entered_uom_id=line.return_uom_id or line.purchase_uom_id,
                conversion_version=line.conversion_version,
                remarks=line.remarks or row.remarks,
                batch_id=batch_id,
            )
            line.inventory_transaction_id = transaction.id
            line.updated_by = actor_id
            movement_ids.append(transaction.id)
        # What the goods actually cost, taken from the stock ledger rows the
        # movements above wrote. The return is priced at what the supplier will
        # credit; stock leaves at the moving average it was carried at, and the
        # two are routinely different.
        stock_value = self._q(
            self._session.scalar(
                select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                    StockLedgerEntry.transaction_id.in_(movement_ids),
                    StockLedgerEntry.is_deleted.is_(False),
                )
            )
            or ZERO
        )
        # Posting runs before the commit and may fail the completion, matching
        # every other document: goods that left stock with no journal behind
        # them are how the inventory control account stops reconciling.
        self._posting.post_purchase_return(
            firm_id=firm_scope,
            return_id=row.id,
            return_number=row.return_number,
            return_date=row.return_date,
            stock_value=stock_value,
            tax_amount=row.tax_total,
            total_amount=row.grand_total,
            actor_id=actor_id,
        )
        before = row.status
        row.status = PurchaseReturnStatus.COMPLETED.value
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="COMPLETED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_return.completed",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def _resolve_return_batch(self, line: PurchaseReturnLine) -> UUID | None:
        """Return the batch this line is sending back, if it names one.

        The number is typed off the carton being crated up for the supplier.
        Resolving it is what takes the goods out of that batch's stock row
        instead of the product's untracked one -- without it a batch could be
        received, sold from, and then returned against stock that was never in
        it, leaving the batch holding goods that have left the building.

        ``require_batch_on_issue`` is the product saying its goods cannot leave
        unidentified, and a return to the supplier is stock leaving. Dispatch
        already refuses to ship it untracked; a return that did not would be
        the same hole in the same guarantee, one document along.

        Returns:
            The batch id, or None where the line names no batch and the product
            does not require one -- which posts against the product exactly as
            it did before.

        """
        number = (line.batch_number or "").strip()
        if not number:
            product = self._session.get(Product, line.product_id)
            if product is not None and product.require_batch_on_issue:
                raise ValidationError(
                    f"{product.code} may only be issued from a batch, so the "
                    "batch number is required to return it."
                )
            return None
        return (
            BatchSerialService(self._session)
            .resolve_for_issue(
                firm_scope=line.firm_id,
                product_id=line.product_id,
                batch_number=number,
            )
            .id
        )

    def cancel_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
        """Cancel one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status in {
            PurchaseReturnStatus.CANCELLED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            raise ValidationError("This purchase return can no longer be cancelled.")
        before = row.status
        reversed_lines, stock_value = self._reverse_inventory(
            row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        # The goods are back on the shelf; the payable, the input tax and the
        # inventory credit have to come back off the books with them.
        self._reverse_posting(
            row, firm_scope=firm_scope, actor_id=actor_id, stock_value=stock_value
        )
        row.status = PurchaseReturnStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="CANCELLED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="purchase_return.cancelled",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reason": reason,
                "reversed_inventory_lines": reversed_lines,
            },
        )
        self._session.commit()
        return row

    def _reverse_inventory(
        self,
        document: PurchaseReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> tuple[int, Decimal]:
        """Undo the stock this return moved out, if it had already completed.

        Completing a return takes goods off the shelf. Cancelling it afterwards
        must put them back, otherwise the firm loses stock it still holds.

        Reports what the movements actually put back as well as how many lines
        they covered, because the journal has to be taken off the books at that
        figure rather than at the one the return was priced at -- goods come
        back at the average the stock is carried at now.

        Args:
            document: The return being cancelled.
            firm_scope: The owning firm.
            actor_id: The user cancelling the return.
            reason: Optional cancellation reason, stored on the reversal.

        Returns:
            How many lines were reversed, and the value they put back.

        """
        reversed_lines = 0
        movement_ids: list[UUID] = []
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == document.id,
                PurchaseReturnLine.inventory_transaction_id.is_not(None),
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all():
            if line.inventory_transaction_id is None:
                continue
            movement = self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason or f"Purchase return {document.return_number} cancelled.",
            )
            if movement is not None:
                movement_ids.append(movement.id)
            line.inventory_transaction_id = None
            line.updated_by = actor_id
            reversed_lines += 1
        return reversed_lines, self._movement_value(movement_ids)

    def _movement_value(self, movement_ids: list[UUID]) -> Decimal:
        """Return what the stock ledger says those movements were worth."""
        if not movement_ids:
            return ZERO
        total = self._session.scalar(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                StockLedgerEntry.transaction_id.in_(movement_ids),
                StockLedgerEntry.is_deleted.is_(False),
            )
        )
        return Decimal(str(total or 0))

    def _reverse_posting(
        self,
        document: PurchaseReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        stock_value: Decimal,
    ) -> None:
        """Take the completion's journal back off the books.

        Nothing did this until 2026-08-22. Completing a return debited payables
        for the supplier's credit note, reversed the input tax and credited
        inventory; cancelling put the goods back on the shelf and left every
        one of those postings standing, so the firm still showed the supplier
        owing it for goods it had kept. `goods_receipt` carried the same defect
        until 2026-08-18 -- this is its mirror, found by cancelling one on
        seeded data and watching the store go 199.07 out.

        `reversal_of_id IS NULL` matters for the same reason it does there:
        `reverse_entry` copies the source ids onto the mirror it posts, so
        without it a second pass would reverse the reversal.
        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "purchase_return",
                JournalEntry.source_id == document.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # A return cancelled before it completed posted nothing.
            return
        self._posting.reverse_purchase_return(
            firm_id=firm_scope,
            entry_id=entry_id,
            return_number=document.return_number,
            stock_value=stock_value,
            actor_id=actor_id,
        )

    def close_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
        """Close one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == PurchaseReturnStatus.CLOSED.value:
            raise ValidationError("This purchase return is already closed.")
        before = row.status
        row.status = PurchaseReturnStatus.CLOSED.value
        row.close_reason = reason
        row.closed_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="CLOSED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="purchase_return.closed",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_return(self, return_id: UUID, *, firm_scope: UUID) -> PurchaseReturn:
        """Return one purchase return."""
        row = self._session.scalar(
            select(PurchaseReturn).where(
                PurchaseReturn.id == return_id,
                PurchaseReturn.firm_id == firm_scope,
                PurchaseReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase return not found.")
        return row

    def return_response(self, row: PurchaseReturn) -> PurchaseReturnResponse:
        """Render one purchase return row as its API contract."""
        sources = list(
            self._session.scalars(
                select(PurchaseReturnSource).where(
                    PurchaseReturnSource.purchase_return_id == row.id,
                    PurchaseReturnSource.is_deleted.is_(False),
                )
            ).all()
        )
        lines = list(
            self._session.scalars(
                select(PurchaseReturnLine)
                .where(
                    PurchaseReturnLine.purchase_return_id == row.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                )
                .order_by(PurchaseReturnLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(PurchaseReturnAttachment).where(
                    PurchaseReturnAttachment.purchase_return_id == row.id,
                    PurchaseReturnAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(PurchaseReturnNote).where(
                    PurchaseReturnNote.purchase_return_id == row.id,
                    PurchaseReturnNote.is_deleted.is_(False),
                )
            ).all()
        )
        accounting_events = list(
            self._session.scalars(
                select(PurchaseReturnAccountingEvent).where(
                    PurchaseReturnAccountingEvent.purchase_return_id == row.id,
                    PurchaseReturnAccountingEvent.is_deleted.is_(False),
                )
            ).all()
        )
        warning = self._duplicate_warning(
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            supplier_return_number=row.supplier_return_number,
            current_id=row.id,
        )
        return PurchaseReturnResponse(
            id=row.id,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            return_number=row.return_number,
            return_date=row.return_date,
            supplier_return_number=row.supplier_return_number,
            supplier_return_date=row.supplier_return_date,
            reference_grn_number=row.reference_grn_number,
            reference_invoice_number=row.reference_invoice_number,
            return_reason=row.return_reason,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_direct_purchase_order=row.allow_direct_purchase_order,
            allow_over_return=row.allow_over_return,
            over_return_percent=row.over_return_percent,
            status=PurchaseReturnStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_returned_quantity=row.total_already_returned_quantity,
            total_current_return_quantity=row.total_current_return_quantity,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            approved_at=row.approved_at,
            closed_at=row.closed_at,
            cancel_reason=row.cancel_reason,
            close_reason=row.close_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            lines=[self._line_response(item) for item in lines],
            sources=[self._source_response(item) for item in sources],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            accounting_events=[
                self._accounting_event_response(item) for item in accounting_events
            ],
            duplicate_warning=warning,
        )

    def timeline(
        self, *, return_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return the lifecycle timeline for one purchase return."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=return_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_returns(self, *, firm_scope: UUID) -> list[PurchaseReturn]:
        """List returns still in draft, not yet approved."""
        return list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status == PurchaseReturnStatus.DRAFT.value,
                )
            ).all()
        )

    def overdue_returns(self, *, firm_scope: UUID) -> list[PurchaseReturn]:
        """List live returns past their due date.

        Cancelled and closed returns are excluded: neither is still owing.
        """
        today = utc_now().date()
        return list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.due_date.is_not(None),
                    PurchaseReturn.due_date < today,
                    PurchaseReturn.status.not_in(
                        [
                            PurchaseReturnStatus.CANCELLED.value,
                            PurchaseReturnStatus.CLOSED.value,
                        ]
                    ),
                )
            ).all()
        )

    def register_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseReturnRegisterRecord]:
        """Return the register report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(PurchaseReturn)
                .where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                )
                .order_by(
                    PurchaseReturn.return_date.desc(), PurchaseReturn.created_at.desc()
                )
            ).all()
        )
        return [
            PurchaseReturnRegisterRecord(
                return_id=row.id,
                return_number=row.return_number,
                supplier_return_number=row.supplier_return_number,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                return_date=row.return_date,
                grand_total=row.grand_total,
                status=PurchaseReturnStatus(row.status),
            )
            for row in rows
        ]

    def by_vendor_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseReturnByVendorRecord]:
        """Total returned value and count per vendor."""
        rows = list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for row in rows:
            totals[row.vendor_id] += row.grand_total
            counts[row.vendor_id] += 1
        vendor_names = {
            vendor.id: vendor.display_name
            for vendor in self._session.scalars(
                select(Vendor).where(Vendor.id.in_(list(totals.keys())))
            ).all()
        }
        return [
            PurchaseReturnByVendorRecord(
                vendor_id=vendor_id,
                vendor_name=vendor_names.get(vendor_id, str(vendor_id)),
                return_amount=self._q(amount),
                return_count=counts[vendor_id],
            )
            for vendor_id, amount in totals.items()
        ]

    def by_product_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseReturnByProductRecord]:
        """Total returned quantity and value per product.

        The report is per product, which is what its name says; it used to
        answer with the per-line reconciliation, which carries no product at
        all.
        """
        lines = self._report_lines(firm_scope=firm_scope)
        quantities: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        amounts: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for line, _ in lines:
            quantities[line.product_id] += line.current_return_quantity
            amounts[line.product_id] += line.net_amount
            counts[line.product_id] += 1
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(list(quantities.keys())))
            ).all()
        }
        return [
            PurchaseReturnByProductRecord(
                product_id=product_id,
                product_code=(
                    products[product_id].code
                    if product_id in products
                    else str(product_id)
                ),
                product_name=(
                    products[product_id].name
                    if product_id in products
                    else str(product_id)
                ),
                return_quantity=self._q(quantity),
                return_amount=self._q(amounts[product_id]),
                return_count=counts[product_id],
            )
            for product_id, quantity in quantities.items()
        ]

    def _report_lines(
        self, *, firm_scope: UUID
    ) -> list[tuple[PurchaseReturnLine, PurchaseReturn]]:
        """Every live return line in scope, with the return it belongs to.

        Cancelled returns are left out, the way the by-vendor totals always
        left them out. A cancelled return did not happen, and counting its
        lines overstated every line-level report against the header ones.
        """
        return [
            (line, header)
            for line, header in self._session.execute(
                select(PurchaseReturnLine, PurchaseReturn)
                .join(
                    PurchaseReturn,
                    PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
                )
                .where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                    PurchaseReturnLine.is_deleted.is_(False),
                )
            ).all()
        ]

    def reconciliation_report(
        self,
        *,
        firm_scope: UUID,
        damaged_only: bool = False,
        expired_only: bool = False,
    ) -> list[PurchaseReturnReconciliationRecord]:
        """Return lines set against the receipts they came from.

        ``damaged_only`` and ``expired_only`` are what the damaged and expired
        reports are: the line records the condition on ``is_damaged`` and
        ``is_expired``, and both reports used to filter on a quantity instead,
        so they answered "anything returned" and "nearly everything".
        """
        lines = self._report_lines(firm_scope=firm_scope)
        product_names = {
            product.id: product.name
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line, _ in lines])
                )
            ).all()
        }
        result: list[PurchaseReturnReconciliationRecord] = []
        for row, header in lines:
            if damaged_only and not row.is_damaged:
                continue
            if expired_only and not row.is_expired:
                continue
            pending = self._q(
                row.received_quantity
                - row.already_returned_quantity
                - row.current_return_quantity
            )
            result.append(
                PurchaseReturnReconciliationRecord(
                    return_id=header.id,
                    return_number=header.return_number,
                    return_date=header.return_date,
                    source_document_type=PurchaseReturnSourceType(
                        row.source_document_type
                    ),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    product_id=row.product_id,
                    product_name=product_names.get(row.product_id, str(row.product_id)),
                    received_quantity=row.received_quantity,
                    already_returned_quantity=row.already_returned_quantity,
                    current_return_quantity=row.current_return_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                    reason_code=row.reason_code,
                    is_damaged=row.is_damaged,
                    is_expired=row.is_expired,
                )
            )
        return result

    def export_returns_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        """Export matching purchase returns as CSV."""
        rows, _ = self.list_returns(
            firm_scope=firm_scope,
            filters=PurchaseReturnListFilters(),
            page=1,
            page_size=5000,
            search=search,
            sort_by="created_at",
            descending=True,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "return_number",
                "supplier_return_number",
                "return_date",
                "vendor_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.return_number,
                    row.supplier_return_number,
                    row.return_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_returns(
        self, data: PurchaseReturnImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseReturn]:
        """Import a validated batch of purchase returns atomically."""
        return [
            self.create_return(record, firm_id=firm_scope, actor_id=actor_id)
            for record in data.records
        ]

    def _replace_sources(
        self,
        row: PurchaseReturn,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnSource).filter(
            PurchaseReturnSource.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = PurchaseReturnSource(
                purchase_return_id=row.id,
                firm_id=firm_id,
                source_document_type=item["source_document_type"],
                source_document_id=item["source_document_id"],
                source_document_number=item["source_document_number"],
                source_document_date=item["source_document_date"],
                vendor_id=item["vendor_id"],
                branch_id=item["branch_id"],
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(source)

    def _replace_lines(
        self,
        row: PurchaseReturn,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        return_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(PurchaseReturnLine).filter(
            PurchaseReturnLine.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            source_line: SourceLine | None
            if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
                source_line = self._session.scalar(
                    select(GoodsReceiptLine).where(
                        GoodsReceiptLine.id == spec["source_document_line_id"]
                    )
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
                source_line = self._session.scalar(
                    select(PurchaseInvoiceLine).where(
                        PurchaseInvoiceLine.id == spec["source_document_line_id"]
                    )
                )
            else:
                source_line = self._session.scalar(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.id == spec["source_document_line_id"]
                    )
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            requested_quantity = self._q(Decimal(str(spec["current_return_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            return_uom_id = spec.get("return_uom_id")
            conversion_factor = self._q(
                Decimal(str(spec.get("conversion_factor", Decimal("1"))))
            )
            return_quantity = requested_quantity
            if (
                source_uom_id is not None
                and return_uom_id is not None
                and return_uom_id != source_uom_id
            ):
                conversion = self._uom.convert_quantity(
                    ConversionRequest(
                        product_id=self._product_id(source_line),
                        from_uom_id=return_uom_id,
                        to_uom_id=source_uom_id,
                        quantity=requested_quantity,
                        conversion_date=return_date,
                    ),
                    firm_scope=firm_id,
                )
                return_quantity = self._q(conversion.converted_quantity)
                conversion_factor = self._q(conversion.conversion_factor)
            already_returned = self._already_returned_quantity(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
            )
            if (
                not row.allow_over_return
                and return_quantity + already_returned > source_quantity
            ):
                raise ValidationError(
                    "Return quantity exceeds the available source quantity."
                )
            unit_price = self._q(Decimal(str(spec.get("unit_price", ZERO))))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            gross_amount = self._q(return_quantity * unit_price)
            line_discount = self._line_discount(
                spec=spec, source_line=source_line, gross=gross_amount
            )
            discount_amount = line_discount.amount
            tax_amount = self._tax_amount(
                return_date=return_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                product_id=self._product_id(source_line),
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                invoice_value=self._line_net_amount(
                    quantity=return_quantity,
                    unit_price=unit_price,
                    discount_amount=discount_amount,
                    charges_amount=charges_amount,
                ),
                actor_id=actor_id,
            )
            net_amount = self._q(
                gross_amount - discount_amount + charges_amount + tax_amount
            )
            line = PurchaseReturnLine(
                purchase_return_id=row.id,
                firm_id=firm_id,
                line_number=index,
                source_document_type=source_type,
                source_document_id=spec["source_document_id"],
                source_document_number=self._source_document_number(spec, source_line),
                source_document_line_id=source_line.id,
                source_document_line_number=self._source_line_number(source_line),
                product_id=self._product_id(source_line),
                description=self._source_description(source_line),
                received_quantity=source_quantity,
                already_returned_quantity=already_returned,
                current_return_quantity=return_quantity,
                rejected_quantity=self._q(
                    Decimal(str(spec.get("rejected_quantity", ZERO)))
                ),
                reason_code=spec.get("reason_code"),
                item_condition=spec.get("item_condition"),
                replacement_required=bool(spec.get("replacement_required", False)),
                refund_required=bool(spec.get("refund_required", False)),
                is_scrap=bool(spec.get("is_scrap", False)),
                is_damaged=bool(spec.get("is_damaged", False)),
                is_expired=bool(spec.get("is_expired", False)),
                unit_price=unit_price,
                discount_percent=line_discount.percent,
                discount_amount=discount_amount,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                purchase_uom_id=spec.get("purchase_uom_id"),
                return_uom_id=spec.get("return_uom_id"),
                conversion_factor=conversion_factor,
                conversion_version=spec.get("conversion_version"),
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                storage_node_id=spec.get("storage_node_id"),
                batch_number=spec.get("batch_number"),
                expiry_date=spec.get("expiry_date"),
                manufacturing_date=spec.get("manufacturing_date"),
                remarks=spec.get("remarks"),
                accounting_event_reference=f"{row.return_number}:{index}",
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(line)
            totals["total_source_quantity"] += source_quantity
            totals["total_already_returned_quantity"] += already_returned
            totals["total_current_return_quantity"] += return_quantity
            totals["line_discount_total"] += discount_amount
            # subtotal is the taxable base: gross less discount, before tax and
            # before charges. Line charges used to be folded in here, which made
            # this module's subtotal mean something different from every other
            # document's; they are carried separately and added to grand_total.
            totals["subtotal"] += self._q(gross_amount - discount_amount)
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: PurchaseReturn,
        attachments: list[PurchaseReturnAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnAttachment).filter(
            PurchaseReturnAttachment.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                PurchaseReturnAttachment(
                    purchase_return_id=row.id,
                    firm_id=firm_id,
                    file_name=attachment.file_name,
                    mime_type=attachment.mime_type,
                    file_path=attachment.file_path,
                    attachment_kind=attachment.attachment_kind,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_notes(
        self,
        row: PurchaseReturn,
        notes: list[PurchaseReturnNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnNote).filter(
            PurchaseReturnNote.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                PurchaseReturnNote(
                    purchase_return_id=row.id,
                    firm_id=firm_id,
                    note_type=(
                        note.note_type.value
                        if hasattr(note.note_type, "value")
                        else str(note.note_type)
                    ),
                    note=note.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_accounting_events(
        self, row: PurchaseReturn, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(PurchaseReturnAccountingEvent).filter(
            PurchaseReturnAccountingEvent.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (
                PurchaseReturnAccountingEventType.PURCHASE_RETURN.value,
                "Purchase Return",
                "CREDIT",
                row.subtotal,
            ),
            (
                PurchaseReturnAccountingEventType.INPUT_TAX_REVERSAL.value,
                "Input Tax Reversal",
                "CREDIT",
                row.tax_total,
            ),
            (
                PurchaseReturnAccountingEventType.VENDOR_RECEIVABLE.value,
                "Vendor Receivable",
                "DEBIT",
                row.grand_total,
            ),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                PurchaseReturnAccountingEvent(
                    purchase_return_id=row.id,
                    firm_id=firm_id,
                    event_type=event_type,
                    account_name=account_name,
                    direction=direction,
                    amount=self._q(amount),
                    narration=f"Placeholder accounting event for {row.return_number}",
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _prepare_return_sources(
        self, data: PurchaseReturnCreate, firm_id: UUID
    ) -> tuple[dict[str, UUID], list[dict[str, object]], list[dict[str, object]]]:
        lines = [item.model_dump(mode="python") for item in data.lines]
        sources = [item.model_dump(mode="python") for item in data.source_documents]
        inferred_sources = {
            (
                self._source_type(item["source_document_type"]),
                item["source_document_id"],
            )
            for item in lines
        }
        if not sources:
            sources = [
                {"source_document_type": source_type, "source_document_id": source_id}
                for source_type, source_id in inferred_sources
            ]
        source_rows: list[dict[str, object]] = []
        header: dict[str, UUID] = {}
        for source in sources:
            source_type = self._source_type(source["source_document_type"])
            source_id = source["source_document_id"]
            if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
                receipt = self._session.scalar(
                    select(GoodsReceipt).where(
                        GoodsReceipt.id == source_id,
                        GoodsReceipt.firm_id == firm_id,
                        GoodsReceipt.is_deleted.is_(False),
                    )
                )
                if receipt is None:
                    raise ResourceNotFoundError("Goods receipt not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": receipt.id,
                        "source_document_number": receipt.grn_number,
                        "source_document_date": receipt.receipt_date,
                        "vendor_id": receipt.vendor_id,
                        "branch_id": receipt.branch_id,
                    }
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
                invoice = self._session.scalar(
                    select(PurchaseInvoice).where(
                        PurchaseInvoice.id == source_id,
                        PurchaseInvoice.firm_id == firm_id,
                        PurchaseInvoice.is_deleted.is_(False),
                    )
                )
                if invoice is None:
                    raise ResourceNotFoundError("Purchase invoice not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": invoice.id,
                        "source_document_number": invoice.invoice_number,
                        "source_document_date": invoice.invoice_date,
                        "vendor_id": invoice.vendor_id,
                        "branch_id": invoice.branch_id,
                    }
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_ORDER.value:
                if not data.allow_direct_purchase_order:
                    raise ValidationError("Direct purchase order return is disabled.")
                order = self._session.scalar(
                    select(PurchaseOrder).where(
                        PurchaseOrder.id == source_id,
                        PurchaseOrder.firm_id == firm_id,
                        PurchaseOrder.is_deleted.is_(False),
                    )
                )
                if order is None:
                    raise ResourceNotFoundError("Purchase order not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": order.id,
                        "source_document_number": order.po_number,
                        "source_document_date": order.purchase_date,
                        "vendor_id": order.vendor_id,
                        "branch_id": order.branch_id,
                    }
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        for field in ("vendor_id", "branch_id"):
            value = _optional_uuid(first.get(field))
            if value is not None:
                header[field] = value
        for source in source_rows[1:]:
            if (
                source["vendor_id"] != header["vendor_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same vendor and branch."
                )
        self._validate_line_sources(
            lines,
            {
                source_id
                for row in source_rows
                if (source_id := _optional_uuid(row["source_document_id"])) is not None
            },
        )
        return header, source_rows, lines

    def _validate_line_sources(
        self, lines: list[dict[str, object]], source_ids: set[UUID]
    ) -> None:
        for line in lines:
            if line["source_document_id"] not in source_ids:
                raise ValidationError(
                    "Every return line must reference a selected source document."
                )

    def _delete_children(self, return_id: UUID) -> None:
        self._session.query(PurchaseReturnAccountingEvent).filter(
            PurchaseReturnAccountingEvent.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnLine).filter(
            PurchaseReturnLine.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnSource).filter(
            PurchaseReturnSource.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnAttachment).filter(
            PurchaseReturnAttachment.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnNote).filter(
            PurchaseReturnNote.purchase_return_id == return_id
        ).delete(synchronize_session=False)

    def _tax_amount(
        self,
        *,
        return_date: date,
        firm_id: UUID,
        actor_id: UUID,
        business_profile_id: UUID | None,
        vendor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID | None,
        product_id: UUID,
        tax_profile_id: UUID | None,
        invoice_value: Decimal,
    ) -> Decimal:
        if invoice_value <= ZERO:
            return ZERO
        # A product names a tax group, not a version, so the rate is decided by
        # the document date. An explicitly named profile must also have been in
        # force then, or the document would carry a rate that never applied.
        tax_service = TaxFrameworkService(self._session)
        if tax_profile_id is None:
            product = self._session.get(Product, product_id)
            resolved = (
                tax_service.resolve_profile_for_product(
                    product, return_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, return_date, firm_scope=firm_id
            )
        request = TaxRuleSimulationRequest(
            transaction_type="PURCHASE_RETURN",
            transaction_date=return_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            vendor_id=vendor_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "purchase_return"},
        )
        response = self._tax.simulate(request, firm_scope=firm_id, actor_id=actor_id)
        return self._q(response.total_tax_amount)

    def _source_quantity(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> Decimal:
        source_type = self._source_type(spec["source_document_type"])
        if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            return self._q(getattr(source_line, "accepted_quantity", ZERO))
        if source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
            return self._q(getattr(source_line, "current_invoice_quantity", ZERO))
        return self._q(getattr(source_line, "ordered_quantity", ZERO))

    def _already_returned_quantity(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> Decimal:
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(PurchaseReturnLine.current_return_quantity), ZERO
                )
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturnLine.source_document_line_id == source_document_line_id,
            )
        )
        return self._q(total or ZERO)

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: SourceLine) -> UUID | None:
        return (
            getattr(source_line, "purchase_uom_id", None)
            or getattr(source_line, "invoice_uom_id", None)
            or getattr(source_line, "inventory_uom_id", None)
        )

    def _source_line_number(self, source_line: SourceLine) -> int:
        return int(source_line.line_number)

    def _source_description(self, source_line: SourceLine) -> str | None:
        return getattr(source_line, "description", None)

    def _source_document_number(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> str:
        source_number = spec.get("source_document_number")
        if source_number:
            return str(source_number)
        # Narrowed on the line's own class rather than on the parallel
        # ``source_document_type`` string, which can disagree with it.
        if isinstance(source_line, GoodsReceiptLine):
            receipt = self._session.scalar(
                select(GoodsReceipt).where(
                    GoodsReceipt.id == source_line.goods_receipt_id
                )
            )
            if receipt is not None:
                return receipt.grn_number
            return str(source_number or "")
        if isinstance(source_line, PurchaseInvoiceLine):
            invoice = self._session.scalar(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.id == source_line.purchase_invoice_id
                )
            )
            if invoice is not None:
                return invoice.invoice_number
            return str(source_number or "")
        order = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == source_line.purchase_order_id
            )
        )
        if order is not None:
            return order.po_number
        return str(source_number or "")

    def _product_id(self, source_line: SourceLine) -> UUID:
        return source_line.product_id

    def _line_discount(
        self,
        *,
        spec: dict[str, object],
        source_line: object,
        gross: Decimal,
    ) -> LineDiscount:
        """Return the discount for one line.

        What the line itself says wins; where it says nothing, the **rate** on
        the source line carries over. A rate is inherited and an absolute
        amount is not, because a rate does not care about quantity: this
        document may cover part of the source line, and copying a whole-line
        amount onto a part of it would discount more than was ever agreed.

        The percentage was stored and never applied before this: the tax base
        and the subtotal were both computed from the amount alone, so a line
        carrying `10` was billed at full price.
        """
        percent = spec.get("discount_percent")
        amount = spec.get("discount_amount")
        if percent is None and amount is None:
            percent = getattr(source_line, "discount_percent", None) or None
        return resolve_line_discount(
            gross=gross,
            percent=None if percent is None else Decimal(str(percent)),
            amount=None if amount is None else Decimal(str(amount)),
        )

    def _line_net_amount(
        self,
        *,
        quantity: Decimal,
        unit_price: Decimal,
        discount_amount: Decimal,
        charges_amount: Decimal,
    ) -> Decimal:
        return self._q(quantity * unit_price - discount_amount + charges_amount)

    def _validate_supplier_return_number(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_return_number: str | None,
        current_id: UUID | None = None,
    ) -> None:
        if not supplier_return_number:
            return
        if self._duplicate_warning(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_return_number=supplier_return_number,
            current_id=current_id,
        ):
            return

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_return_number: str | None,
        current_id: UUID | None,
    ) -> str | None:
        if not supplier_return_number:
            return None
        statement = select(PurchaseReturn.id).where(
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.vendor_id == vendor_id,
            PurchaseReturn.supplier_return_number == supplier_return_number,
            PurchaseReturn.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(PurchaseReturn.id != current_id)
        if self._session.scalar(statement) is not None:
            return "A purchase return with this supplier return number already exists."
        return None

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document: PurchaseReturn,
        action: str,
        from_state: str | None,
        to_state: str | None,
        actor_id: UUID,
        remarks: str | None = None,
    ) -> None:
        self._documents.record_event(
            firm_id,
            DocumentLifecycleEventCreate(
                document_type_id=document_type.id,
                source_document_id=document.id,
                source_module_code="PURCHASE_RETURN",
                document_number=document.return_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "return_number": document.return_number,
                    "supplier_return_number": document.supplier_return_number or "",
                    "grand_total": str(document.grand_total),
                },
                snapshot_json={
                    "status": document.status,
                    "vendor_id": str(document.vendor_id),
                    "branch_id": str(document.branch_id),
                },
                actor_id=actor_id,
            ),
            actor_id=actor_id,
        )

    def _attachment_response(
        self, row: PurchaseReturnAttachment
    ) -> PurchaseReturnAttachmentResponse:
        return PurchaseReturnAttachmentResponse.model_validate(row)

    def _note_response(self, row: PurchaseReturnNote) -> PurchaseReturnNoteResponse:
        return PurchaseReturnNoteResponse.model_validate(row)

    def _source_response(
        self, row: PurchaseReturnSource
    ) -> PurchaseReturnSourceResponse:
        return PurchaseReturnSourceResponse(
            id=row.id,
            source_document_type=PurchaseReturnSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: PurchaseReturnAccountingEvent
    ) -> PurchaseReturnAccountingEventResponse:
        return PurchaseReturnAccountingEventResponse(
            id=row.id,
            event_type=PurchaseReturnAccountingEventType(row.event_type),
            account_name=row.account_name,
            direction=row.direction,
            amount=row.amount,
            narration=row.narration,
            source_line_id=row.source_line_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _line_response(self, row: PurchaseReturnLine) -> PurchaseReturnLineResponse:
        return PurchaseReturnLineResponse(
            id=row.id,
            purchase_return_id=row.purchase_return_id,
            line_number=row.line_number,
            source_document_type=PurchaseReturnSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            received_quantity=row.received_quantity,
            already_returned_quantity=row.already_returned_quantity,
            current_return_quantity=row.current_return_quantity,
            rejected_quantity=row.rejected_quantity,
            reason_code=row.reason_code,
            item_condition=row.item_condition,
            replacement_required=row.replacement_required,
            refund_required=row.refund_required,
            is_scrap=row.is_scrap,
            is_damaged=row.is_damaged,
            is_expired=row.is_expired,
            unit_price=row.unit_price,
            discount_percent=row.discount_percent,
            discount_amount=row.discount_amount,
            charges_amount=row.charges_amount,
            gross_amount=row.gross_amount,
            tax_profile_id=row.tax_profile_id,
            tax_amount=row.tax_amount,
            net_amount=row.net_amount,
            packaging_type_id=row.packaging_type_id,
            purchase_uom_id=row.purchase_uom_id,
            return_uom_id=row.return_uom_id,
            conversion_factor=row.conversion_factor,
            conversion_version=row.conversion_version,
            warehouse_id=row.warehouse_id,
            storage_node_id=row.storage_node_id,
            batch_number=row.batch_number,
            expiry_date=row.expiry_date,
            manufacturing_date=row.manufacturing_date,
            remarks=row.remarks,
            accounting_event_reference=row.accounting_event_reference,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
