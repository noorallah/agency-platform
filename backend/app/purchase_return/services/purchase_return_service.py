"""Purchase return workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import financial_year_label, utc_now
from app.core.utils.money import quantize_money
from app.document_framework.models import (
    DocumentNumberingRule,
    DocumentStateDefinition,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentNumberingRuleCreate,
    DocumentStateCreate,
    DocumentTypeCreate,
)
from app.document_framework.services.document_framework_service import (
    DocumentFrameworkService,
)
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
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
    PurchaseReturnVendorOutstandingRecord,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService
from app.vendors.models import Vendor

ZERO = Decimal("0")


class PurchaseReturnService:
    """Coordinate supplier return lifecycle and source-document validation."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._documents = DocumentFrameworkService(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)
        self._inventory = InventoryService(session)

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
                financial_year_label=self._financial_year_label(data.return_date, firm_id),
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
            )
            line.inventory_transaction_id = transaction.id
            line.updated_by = actor_id
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

    def cancel_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status in {
            PurchaseReturnStatus.CANCELLED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            raise ValidationError("This purchase return can no longer be cancelled.")
        before = row.status
        reversed_lines = self._reverse_inventory(
            row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
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
    ) -> int:
        """Undo the stock this return moved out, if it had already completed.

        Completing a return takes goods off the shelf. Cancelling it afterwards
        must put them back, otherwise the firm loses stock it still holds.

        Args:
            document: The return being cancelled.
            firm_scope: The owning firm.
            actor_id: The user cancelling the return.
            reason: Optional cancellation reason, stored on the reversal.

        Returns:
            The number of lines whose stock movement was reversed.

        """
        reversed_lines = 0
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == document.id,
                PurchaseReturnLine.inventory_transaction_id.is_not(None),
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all():
            if line.inventory_transaction_id is None:
                continue
            self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason or f"Purchase return {document.return_number} cancelled.",
            )
            line.inventory_transaction_id = None
            line.updated_by = actor_id
            reversed_lines += 1
        return reversed_lines

    def close_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
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

    def timeline(self, *, return_id: UUID, firm_scope: UUID, page: int, page_size: int):
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=return_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_returns(self, *, firm_scope: UUID) -> list[PurchaseReturn]:
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
        today = date.today()
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

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseReturnVendorOutstandingRecord]:
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
        vendor_names: dict[UUID, str] = {}
        for row in rows:
            totals[row.vendor_id] += row.grand_total
            counts[row.vendor_id] += 1
        vendors = list(
            self._session.scalars(
                select(Vendor).where(Vendor.id.in_(list(totals.keys())))
            ).all()
        )
        for vendor in vendors:
            vendor_names[vendor.id] = vendor.display_name
        return [
            PurchaseReturnVendorOutstandingRecord(
                vendor_id=vendor_id,
                vendor_name=vendor_names.get(vendor_id, str(vendor_id)),
                return_amount=self._q(amount),
                return_count=counts[vendor_id],
            )
            for vendor_id, amount in totals.items()
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseReturnReconciliationRecord]:
        rows = list(
            self._session.scalars(
                select(PurchaseReturnLine)
                .join(
                    PurchaseReturn,
                    PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
                )
                .where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturnLine.is_deleted.is_(False),
                )
            ).all()
        )
        result: list[PurchaseReturnReconciliationRecord] = []
        for row in rows:
            pending = self._q(
                row.received_quantity
                - row.already_returned_quantity
                - row.current_return_quantity
            )
            result.append(
                PurchaseReturnReconciliationRecord(
                    source_document_type=PurchaseReturnSourceType(
                        row.source_document_type
                    ),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    received_quantity=row.received_quantity,
                    already_returned_quantity=row.already_returned_quantity,
                    current_return_quantity=row.current_return_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                )
            )
        return result

    def export_returns_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
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
        totals = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
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
            tax_amount = self._tax_amount(
                return_date=return_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=spec.get("warehouse_id"),
                product_id=self._product_id(source_line),
                tax_profile_id=spec.get("tax_profile_id"),
                invoice_value=self._line_net_amount(
                    quantity=return_quantity,
                    unit_price=Decimal(str(spec.get("unit_price", ZERO))),
                    discount_amount=Decimal(str(spec.get("discount_amount", ZERO))),
                    charges_amount=Decimal(str(spec.get("charges_amount", ZERO))),
                ),
                actor_id=actor_id,
            )
            unit_price = self._q(Decimal(str(spec.get("unit_price", ZERO))))
            discount_amount = self._q(Decimal(str(spec.get("discount_amount", ZERO))))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            gross_amount = self._q(return_quantity * unit_price)
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
                discount_percent=self._q(
                    Decimal(str(spec.get("discount_percent", ZERO)))
                ),
                discount_amount=discount_amount,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=spec.get("tax_profile_id"),
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                purchase_uom_id=spec.get("purchase_uom_id"),
                return_uom_id=spec.get("return_uom_id"),
                conversion_factor=conversion_factor,
                conversion_version=spec.get("conversion_version"),
                warehouse_id=spec.get("warehouse_id"),
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
                document = self._session.scalar(
                    select(GoodsReceipt).where(
                        GoodsReceipt.id == source_id,
                        GoodsReceipt.firm_id == firm_id,
                        GoodsReceipt.is_deleted.is_(False),
                    )
                )
                if document is None:
                    raise ResourceNotFoundError("Goods receipt not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": document.id,
                        "source_document_number": document.grn_number,
                        "source_document_date": document.receipt_date,
                        "vendor_id": document.vendor_id,
                        "branch_id": document.branch_id,
                    }
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
                document = self._session.scalar(
                    select(PurchaseInvoice).where(
                        PurchaseInvoice.id == source_id,
                        PurchaseInvoice.firm_id == firm_id,
                        PurchaseInvoice.is_deleted.is_(False),
                    )
                )
                if document is None:
                    raise ResourceNotFoundError("Purchase invoice not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": document.id,
                        "source_document_number": document.invoice_number,
                        "source_document_date": document.invoice_date,
                        "vendor_id": document.vendor_id,
                        "branch_id": document.branch_id,
                    }
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_ORDER.value:
                if not data.allow_direct_purchase_order:
                    raise ValidationError("Direct purchase order return is disabled.")
                document = self._session.scalar(
                    select(PurchaseOrder).where(
                        PurchaseOrder.id == source_id,
                        PurchaseOrder.firm_id == firm_id,
                        PurchaseOrder.is_deleted.is_(False),
                    )
                )
                if document is None:
                    raise ResourceNotFoundError("Purchase order not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": document.id,
                        "source_document_number": document.po_number,
                        "source_document_date": document.purchase_date,
                        "vendor_id": document.vendor_id,
                        "branch_id": document.branch_id,
                    }
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        header["vendor_id"] = first["vendor_id"]
        header["branch_id"] = first["branch_id"]
        for source in source_rows[1:]:
            if (
                source["vendor_id"] != header["vendor_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same vendor and branch."
                )
        self._validate_line_sources(
            lines, {row["source_document_id"] for row in source_rows}
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

    def _source_quantity(self, spec: dict[str, object], source_line: object) -> Decimal:
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

    def _source_uom_id(self, source_line: object) -> UUID | None:
        return (
            getattr(source_line, "purchase_uom_id", None)
            or getattr(source_line, "invoice_uom_id", None)
            or getattr(source_line, "inventory_uom_id", None)
        )

    def _source_line_number(self, source_line: object) -> int:
        return int(source_line.line_number)

    def _source_description(self, source_line: object) -> str | None:
        return getattr(source_line, "description", None)

    def _source_document_number(
        self, spec: dict[str, object], source_line: object
    ) -> str:
        source_number = spec.get("source_document_number")
        if source_number:
            return str(source_number)
        source_type = self._source_type(spec["source_document_type"])
        if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            document = self._session.scalar(
                select(GoodsReceipt).where(
                    GoodsReceipt.id == source_line.goods_receipt_id
                )
            )
            if document is not None:
                return document.grn_number
        if source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
            document = self._session.scalar(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.id == source_line.purchase_invoice_id
                )
            )
            if document is not None:
                return document.invoice_number
        document = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == source_line.purchase_order_id
            )
        )
        if document is not None:
            return document.po_number
        return str(source_number or "")

    def _product_id(self, source_line: object) -> UUID:
        return source_line.product_id

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

    def _ensure_document_setup(
        self, *, firm_id: UUID, actor_id: UUID
    ) -> tuple[DocumentTypeDefinition, DocumentNumberingRule]:
        document_type = self._session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.code == "PURCHASE_RETURN",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if document_type is None:
            document_type = self._documents.create_type(
                firm_id,
                DocumentTypeCreate(
                    code="PURCHASE_RETURN",
                    name="Purchase Return",
                    description="Supplier return document",
                    category="PURCHASE",
                    is_active=True,
                    configuration={"module": "purchase_return"},
                ),
                actor_id,
            )
        for state_code, name, sort_order in [
            ("DRAFT", "Draft", 1),
            ("APPROVED", "Approved", 2),
            ("COMPLETED", "Completed", 3),
            ("CANCELLED", "Cancelled", 4),
            ("CLOSED", "Closed", 5),
        ]:
            if not self._state_exists(
                firm_id=firm_id, document_type_id=document_type.id, code=state_code
            ):
                self._documents.create_state(
                    firm_id,
                    DocumentStateCreate(
                        document_type_id=document_type.id,
                        code=state_code,
                        name=name,
                        sort_order=sort_order,
                        is_default=state_code == "DRAFT",
                        is_terminal=state_code in {"COMPLETED", "CANCELLED", "CLOSED"},
                        allows_edit=state_code == "DRAFT",
                        allows_print=True,
                        allows_email=True,
                        allows_export_pdf=True,
                        transition_rules={
                            "module": "purchase_return",
                            "state": state_code,
                        },
                        is_active=True,
                    ),
                    actor_id,
                )
        numbering_rule = self._session.scalar(
            select(DocumentNumberingRule).where(
                DocumentNumberingRule.firm_id == firm_id,
                DocumentNumberingRule.document_type_id == document_type.id,
                DocumentNumberingRule.is_deleted.is_(False),
            )
        )
        if numbering_rule is None:
            numbering_rule = self._documents.create_numbering_rule(
                firm_id,
                DocumentNumberingRuleCreate(
                    document_type_id=document_type.id,
                    code="PURCHASE_RETURN_DEFAULT",
                    name="Purchase Return Default",
                    prefix="PR",
                    suffix=None,
                    separator="-",
                    include_financial_year=True,
                    include_branch_code=False,
                    include_company_code=False,
                    auto_reset=True,
                    manual_allowed=False,
                    sequence_padding=6,
                    next_sequence=1,
                    is_default=True,
                    is_active=True,
                    configuration={"module": "purchase_return"},
                ),
                actor_id,
            )
        return document_type, numbering_rule

    def _state_exists(
        self, *, firm_id: UUID, document_type_id: UUID, code: str
    ) -> bool:
        return (
            self._session.scalar(
                select(DocumentStateDefinition.id).where(
                    DocumentStateDefinition.firm_id == firm_id,
                    DocumentStateDefinition.document_type_id == document_type_id,
                    DocumentStateDefinition.code == code,
                    DocumentStateDefinition.is_deleted.is_(False),
                )
            )
            is not None
        )

    def _document_type(self, firm_id: UUID) -> DocumentTypeDefinition:
        row = self._session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm_id,
                DocumentTypeDefinition.code == "PURCHASE_RETURN",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase return document type not found.")
        return row

    def _financial_year_label(self, on: date, firm_id: UUID) -> str:
        """Return the firm's financial-year label for a document date.

        Args:
            on: The document date.
            firm_id: The owning firm, whose ``financial_year_start`` decides
                when the year begins.

        Returns:
            The shared ``YYYY-YYYY`` label.

        """
        start_month = self._session.scalar(
            select(Firm.financial_year_start).where(Firm.id == firm_id)
        )
        return financial_year_label(
            on, start_month=start_month.month if start_month is not None else 4
        )

    def _scope_code(self, branch_id: UUID | None) -> str | None:
        return str(branch_id)[:8].upper() if branch_id is not None else None

    def _company_code(self, firm_id: UUID) -> str | None:
        return str(firm_id)[:8].upper()

    def _flush_or_conflict(self, message: str) -> None:
        """Flush pending work, converting a unique-key clash into a conflict.

        The rollback matters: without it a failed flush leaves the session
        unusable for every statement that follows.

        Args:
            message: The conflict message surfaced to the caller.

        Raises:
            ConflictError: If the flush violates a database constraint.

        """
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise ConflictError(message) from error

    @staticmethod
    def _q(value: Decimal | int | str | None) -> Decimal:
        """Round a monetary amount to the shared storage scale.

        Args:
            value: The amount to round; ``None`` is treated as zero.

        Returns:
            The amount quantized by :func:`quantize_money`.

        """
        return quantize_money(value)

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
