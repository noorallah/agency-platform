"""Purchase invoice workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
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
from app.document_framework.services.document_framework_service import DocumentFrameworkService
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceAccountingEvent,
    PurchaseInvoiceAttachment,
    PurchaseInvoiceLine,
    PurchaseInvoiceNote,
    PurchaseInvoiceSource,
)
from app.purchase_invoice.schemas import (
    PurchaseInvoiceAccountingEventResponse,
    PurchaseInvoiceAccountingEventType,
    PurchaseInvoiceAttachmentResponse,
    PurchaseInvoiceAttachmentWrite,
    PurchaseInvoiceCreate,
    PurchaseInvoiceImportRequest,
    PurchaseInvoiceLineResponse,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceListFilters,
    PurchaseInvoiceNoteResponse,
    PurchaseInvoiceNoteWrite,
    PurchaseInvoiceReconciliationRecord,
    PurchaseInvoiceRegisterRecord,
    PurchaseInvoiceResponse,
    PurchaseInvoiceSourceResponse,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceStatus,
    PurchaseInvoiceSummary,
    PurchaseInvoiceVendorOutstandingRecord,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService
from app.vendors.models import Vendor

ZERO = Decimal("0")


class PurchaseInvoiceService:
    """Coordinate supplier invoice lifecycle and source-document validation."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._documents = DocumentFrameworkService(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)

    def list_invoices(
        self,
        *,
        firm_scope: UUID,
        filters: PurchaseInvoiceListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[PurchaseInvoice], int]:
        columns = {
            "invoice_number": PurchaseInvoice.invoice_number,
            "invoice_date": PurchaseInvoice.invoice_date,
            "due_date": PurchaseInvoice.due_date,
            "grand_total": PurchaseInvoice.grand_total,
            "status": PurchaseInvoice.status,
            "created_at": PurchaseInvoice.created_at,
            "updated_at": PurchaseInvoice.updated_at,
        }
        statement = select(PurchaseInvoice).where(PurchaseInvoice.firm_id == firm_scope)
        count = select(func.count()).select_from(PurchaseInvoice).where(
            PurchaseInvoice.firm_id == firm_scope
        )
        if not filters.include_deleted:
            statement = statement.where(PurchaseInvoice.is_deleted.is_(False))
            count = count.where(PurchaseInvoice.is_deleted.is_(False))
        if filters.vendor_id is not None:
            statement = statement.where(PurchaseInvoice.vendor_id == filters.vendor_id)
            count = count.where(PurchaseInvoice.vendor_id == filters.vendor_id)
        if filters.branch_id is not None:
            statement = statement.where(PurchaseInvoice.branch_id == filters.branch_id)
            count = count.where(PurchaseInvoice.branch_id == filters.branch_id)
        if filters.status is not None:
            statement = statement.where(PurchaseInvoice.status == filters.status.value)
            count = count.where(PurchaseInvoice.status == filters.status.value)
        if filters.invoice_from is not None:
            statement = statement.where(PurchaseInvoice.invoice_date >= filters.invoice_from)
            count = count.where(PurchaseInvoice.invoice_date >= filters.invoice_from)
        if filters.invoice_to is not None:
            statement = statement.where(PurchaseInvoice.invoice_date <= filters.invoice_to)
            count = count.where(PurchaseInvoice.invoice_date <= filters.invoice_to)
        if filters.due_from is not None:
            statement = statement.where(PurchaseInvoice.due_date >= filters.due_from)
            count = count.where(PurchaseInvoice.due_date >= filters.due_from)
        if filters.due_to is not None:
            statement = statement.where(PurchaseInvoice.due_date <= filters.due_to)
            count = count.where(PurchaseInvoice.due_date <= filters.due_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                PurchaseInvoice.invoice_number.ilike(token),
                PurchaseInvoice.supplier_invoice_number.ilike(token),
                PurchaseInvoice.reference_number.ilike(token),
                PurchaseInvoice.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, PurchaseInvoice.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(sort_column.desc() if descending else sort_column.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> PurchaseInvoiceSummary:
        rows = list(
            self._session.scalars(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                )
            ).all()
        )
        overdue = sum(
            1
            for row in rows
            if row.due_date is not None
            and row.due_date < date.today()
            and row.status not in {PurchaseInvoiceStatus.CANCELLED.value, PurchaseInvoiceStatus.CLOSED.value}
        )
        return PurchaseInvoiceSummary(
            total=len(rows),
            draft=sum(1 for row in rows if row.status == PurchaseInvoiceStatus.DRAFT.value),
            approved=sum(1 for row in rows if row.status == PurchaseInvoiceStatus.APPROVED.value),
            cancelled=sum(1 for row in rows if row.status == PurchaseInvoiceStatus.CANCELLED.value),
            closed=sum(1 for row in rows if row.status == PurchaseInvoiceStatus.CLOSED.value),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
            pending_invoices=sum(1 for row in rows if row.status == PurchaseInvoiceStatus.DRAFT.value),
            overdue_invoices=overdue,
        )

    def create_invoice(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoice:
        document_type, numbering_rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        header, source_rows, line_specs = self._prepare_invoice_sources(data, firm_id=firm_id)
        branch_id = data.branch_id or header["branch_id"]
        vendor_id = data.vendor_id or header["vendor_id"]
        business_profile_id = data.business_profile_id
        if vendor_id != header["vendor_id"]:
            raise ValidationError("Invoice vendor must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        self._validate_supplier_invoice_number(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_invoice_number=data.supplier_invoice_number,
        )
        invoice_number = (
            data.invoice_number.strip().upper()
            if data.invoice_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(data.invoice_date),
                branch_code=self._scope_code(branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.invoice_date,
                actor_id=actor_id,
            )
        )
        row = PurchaseInvoice(
            firm_id=firm_id,
            vendor_id=vendor_id,
            branch_id=branch_id,
            business_profile_id=business_profile_id,
            invoice_number=invoice_number,
            invoice_date=data.invoice_date,
            supplier_invoice_number=data.supplier_invoice_number.strip(),
            supplier_invoice_date=data.supplier_invoice_date,
            currency_code=(data.currency_code.strip().upper() if data.currency_code else None),
            exchange_rate=data.exchange_rate,
            payment_terms=data.payment_terms,
            due_date=data.due_date,
            reference_number=data.reference_number,
            remarks=data.remarks,
            allow_direct_purchase_order=data.allow_direct_purchase_order,
            allow_over_invoice=data.allow_over_invoice,
            over_invoice_percent=self._q(data.over_invoice_percent),
            status=PurchaseInvoiceStatus.DRAFT.value,
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
            invoice_date=data.invoice_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_invoiced_quantity = line_totals["total_already_invoiced_quantity"]
        row.total_current_invoice_quantity = line_totals["total_current_invoice_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(row, data.attachments, actor_id=actor_id, firm_id=firm_id)
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_id)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_id)
        self._record_event(
            firm_id=firm_id,
            document_type=document_type,
            invoice=row,
            action="CREATED",
            from_state=None,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_invoice.created",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"invoice_number": row.invoice_number, "status": row.status},
        )
        self._flush_or_conflict("Purchase invoice number already exists in this firm.")
        self._session.commit()
        return row

    def update_invoice(
        self,
        invoice_id: UUID,
        data: PurchaseInvoiceCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != PurchaseInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft purchase invoices can be updated.")
        self._delete_children(row.id)
        header, source_rows, line_specs = self._prepare_invoice_sources(data, firm_scope)
        row.vendor_id = data.vendor_id or header["vendor_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.business_profile_id = data.business_profile_id
        row.invoice_date = data.invoice_date
        row.supplier_invoice_number = data.supplier_invoice_number.strip()
        row.supplier_invoice_date = data.supplier_invoice_date
        row.currency_code = data.currency_code.strip().upper() if data.currency_code else None
        row.exchange_rate = data.exchange_rate
        row.payment_terms = data.payment_terms
        row.due_date = data.due_date
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.allow_direct_purchase_order = data.allow_direct_purchase_order
        row.allow_over_invoice = data.allow_over_invoice
        row.over_invoice_percent = self._q(data.over_invoice_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        self._validate_supplier_invoice_number(
            firm_id=firm_scope,
            vendor_id=row.vendor_id,
            supplier_invoice_number=row.supplier_invoice_number,
            current_id=row.id,
        )
        self._replace_sources(row, source_rows, firm_id=firm_scope, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_scope,
            invoice_date=data.invoice_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_invoiced_quantity = line_totals["total_already_invoiced_quantity"]
        row.total_current_invoice_quantity = line_totals["total_current_invoice_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(row, data.attachments, actor_id=actor_id, firm_id=firm_scope)
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_scope)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_invoice.updated",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def approve_invoice(self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> PurchaseInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != PurchaseInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft purchase invoices can be approved.")
        before = row.status
        row.status = PurchaseInvoiceStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="APPROVED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_invoice.approved",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def cancel_invoice(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status in {PurchaseInvoiceStatus.CANCELLED.value, PurchaseInvoiceStatus.CLOSED.value}:
            raise ValidationError("This purchase invoice can no longer be cancelled.")
        before = row.status
        row.status = PurchaseInvoiceStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="CANCELLED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="purchase_invoice.cancelled",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def close_invoice(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == PurchaseInvoiceStatus.CLOSED.value:
            raise ValidationError("This purchase invoice is already closed.")
        before = row.status
        row.status = PurchaseInvoiceStatus.CLOSED.value
        row.close_reason = reason
        row.closed_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="CLOSED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
        )
        record_audit(
            self._session,
            action="purchase_invoice.closed",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> PurchaseInvoice:
        row = self._session.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.id == invoice_id,
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase invoice not found.")
        return row

    def invoice_response(self, row: PurchaseInvoice) -> PurchaseInvoiceResponse:
        sources = list(
            self._session.scalars(
                select(PurchaseInvoiceSource).where(
                    PurchaseInvoiceSource.purchase_invoice_id == row.id,
                    PurchaseInvoiceSource.is_deleted.is_(False),
                )
            ).all()
        )
        lines = list(
            self._session.scalars(
                select(PurchaseInvoiceLine).where(
                    PurchaseInvoiceLine.purchase_invoice_id == row.id,
                    PurchaseInvoiceLine.is_deleted.is_(False),
                ).order_by(PurchaseInvoiceLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(PurchaseInvoiceAttachment).where(
                    PurchaseInvoiceAttachment.purchase_invoice_id == row.id,
                    PurchaseInvoiceAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(PurchaseInvoiceNote).where(
                    PurchaseInvoiceNote.purchase_invoice_id == row.id,
                    PurchaseInvoiceNote.is_deleted.is_(False),
                )
            ).all()
        )
        accounting_events = list(
            self._session.scalars(
                select(PurchaseInvoiceAccountingEvent).where(
                    PurchaseInvoiceAccountingEvent.purchase_invoice_id == row.id,
                    PurchaseInvoiceAccountingEvent.is_deleted.is_(False),
                )
            ).all()
        )
        warning = self._duplicate_warning(
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            supplier_invoice_number=row.supplier_invoice_number,
            current_id=row.id,
        )
        return PurchaseInvoiceResponse(
            id=row.id,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            business_profile_id=row.business_profile_id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            supplier_invoice_number=row.supplier_invoice_number,
            supplier_invoice_date=row.supplier_invoice_date,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_direct_purchase_order=row.allow_direct_purchase_order,
            allow_over_invoice=row.allow_over_invoice,
            over_invoice_percent=row.over_invoice_percent,
            status=PurchaseInvoiceStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_invoiced_quantity=row.total_already_invoiced_quantity,
            total_current_invoice_quantity=row.total_current_invoice_quantity,
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
            accounting_events=[self._accounting_event_response(item) for item in accounting_events],
            duplicate_warning=warning,
        )

    def timeline(self, *, invoice_id: UUID, firm_scope: UUID, page: int, page_size: int):
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=invoice_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_invoices(self, *, firm_scope: UUID) -> list[PurchaseInvoice]:
        return list(
            self._session.scalars(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status == PurchaseInvoiceStatus.DRAFT.value,
                )
            ).all()
        )

    def overdue_invoices(self, *, firm_scope: UUID) -> list[PurchaseInvoice]:
        today = date.today()
        return list(
            self._session.scalars(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.due_date.is_not(None),
                    PurchaseInvoice.due_date < today,
                    PurchaseInvoice.status.not_in(
                        [PurchaseInvoiceStatus.CANCELLED.value, PurchaseInvoiceStatus.CLOSED.value]
                    ),
                )
            ).all()
        )

    def register_report(self, *, firm_scope: UUID) -> list[PurchaseInvoiceRegisterRecord]:
        rows = list(
            self._session.scalars(
                select(PurchaseInvoice)
                .where(PurchaseInvoice.firm_id == firm_scope, PurchaseInvoice.is_deleted.is_(False))
                .order_by(PurchaseInvoice.invoice_date.desc(), PurchaseInvoice.created_at.desc())
            ).all()
        )
        return [
            PurchaseInvoiceRegisterRecord(
                invoice_id=row.id,
                invoice_number=row.invoice_number,
                supplier_invoice_number=row.supplier_invoice_number,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                grand_total=row.grand_total,
                status=PurchaseInvoiceStatus(row.status),
            )
            for row in rows
        ]

    def outstanding_report(self, *, firm_scope: UUID) -> list[PurchaseInvoiceVendorOutstandingRecord]:
        rows = list(
            self._session.scalars(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
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
            PurchaseInvoiceVendorOutstandingRecord(
                vendor_id=vendor_id,
                vendor_name=vendor_names.get(vendor_id, str(vendor_id)),
                outstanding_amount=self._q(amount),
                invoice_count=counts[vendor_id],
            )
            for vendor_id, amount in totals.items()
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseInvoiceReconciliationRecord]:
        rows = list(
            self._session.scalars(
                select(PurchaseInvoiceLine)
                .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id)
                .where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        )
        result: list[PurchaseInvoiceReconciliationRecord] = []
        for row in rows:
            pending = self._q(row.received_quantity - row.already_invoiced_quantity - row.current_invoice_quantity)
            result.append(
                PurchaseInvoiceReconciliationRecord(
                    source_document_type=PurchaseInvoiceSourceType(row.source_document_type),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    received_quantity=row.received_quantity,
                    already_invoiced_quantity=row.already_invoiced_quantity,
                    current_invoice_quantity=row.current_invoice_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                )
            )
        return result

    def export_invoices_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        rows, _ = self.list_invoices(
            firm_scope=firm_scope,
            filters=PurchaseInvoiceListFilters(),
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
                "invoice_number",
                "supplier_invoice_number",
                "invoice_date",
                "vendor_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.invoice_number,
                    row.supplier_invoice_number,
                    row.invoice_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_invoices(
        self, data: PurchaseInvoiceImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseInvoice]:
        return [self.create_invoice(record, firm_id=firm_scope, actor_id=actor_id) for record in data.records]

    def _replace_sources(
        self,
        row: PurchaseInvoice,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceSource).filter(
            PurchaseInvoiceSource.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = PurchaseInvoiceSource(
                purchase_invoice_id=row.id,
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
        row: PurchaseInvoice,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        invoice_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(PurchaseInvoiceLine).filter(
            PurchaseInvoiceLine.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        totals = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            if source_type == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
                source_line = self._session.scalar(
                    select(GoodsReceiptLine).where(GoodsReceiptLine.id == spec["source_document_line_id"])
                )
            else:
                source_line = self._session.scalar(
                    select(PurchaseOrderLine).where(PurchaseOrderLine.id == spec["source_document_line_id"])
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            requested_quantity = self._q(Decimal(str(spec["current_invoice_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            invoice_uom_id = spec.get("invoice_uom_id")
            conversion_factor = self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))
            invoice_quantity = requested_quantity
            if source_uom_id is not None and invoice_uom_id is not None and invoice_uom_id != source_uom_id:
                conversion = self._uom.convert_quantity(
                    ConversionRequest(
                        product_id=self._product_id(source_line),
                        from_uom_id=invoice_uom_id,
                        to_uom_id=source_uom_id,
                        quantity=requested_quantity,
                        conversion_date=invoice_date,
                    ),
                    firm_scope=firm_id,
                )
                invoice_quantity = self._q(conversion.converted_quantity)
                conversion_factor = self._q(conversion.conversion_factor)
            already_invoiced = self._already_invoiced_quantity(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
            )
            if not row.allow_over_invoice and invoice_quantity + already_invoiced > source_quantity:
                raise ValidationError("Invoice quantity exceeds the available source quantity.")
            tax_amount = self._tax_amount(
                invoice_date=invoice_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=spec.get("warehouse_id"),
                product_id=self._product_id(source_line),
                tax_profile_id=spec.get("tax_profile_id"),
                invoice_value=self._line_net_amount(
                    quantity=invoice_quantity,
                    unit_price=Decimal(str(spec.get("unit_price", ZERO))),
                    discount_amount=Decimal(str(spec.get("discount_amount", ZERO))),
                    charges_amount=Decimal(str(spec.get("charges_amount", ZERO))),
                ),
                actor_id=actor_id,
            )
            unit_price = self._q(Decimal(str(spec.get("unit_price", ZERO))))
            discount_amount = self._q(Decimal(str(spec.get("discount_amount", ZERO))))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            gross_amount = self._q(invoice_quantity * unit_price)
            net_amount = self._q(gross_amount - discount_amount + charges_amount + tax_amount)
            line = PurchaseInvoiceLine(
                purchase_invoice_id=row.id,
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
                already_invoiced_quantity=already_invoiced,
                current_invoice_quantity=invoice_quantity,
                unit_price=unit_price,
                discount_percent=self._q(Decimal(str(spec.get("discount_percent", ZERO)))),
                discount_amount=discount_amount,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=spec.get("tax_profile_id"),
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                purchase_uom_id=spec.get("purchase_uom_id"),
                invoice_uom_id=spec.get("invoice_uom_id"),
                conversion_factor=conversion_factor,
                conversion_version=spec.get("conversion_version"),
                warehouse_id=spec.get("warehouse_id"),
                storage_node_id=spec.get("storage_node_id"),
                batch_number=spec.get("batch_number"),
                expiry_date=spec.get("expiry_date"),
                manufacturing_date=spec.get("manufacturing_date"),
                remarks=spec.get("remarks"),
                accounting_event_reference=f"{row.invoice_number}:{index}",
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(line)
            totals["total_source_quantity"] += source_quantity
            totals["total_already_invoiced_quantity"] += already_invoiced
            totals["total_current_invoice_quantity"] += invoice_quantity
            totals["line_discount_total"] += discount_amount
            totals["subtotal"] += self._q(gross_amount - discount_amount + charges_amount)
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: PurchaseInvoice,
        attachments: list[PurchaseInvoiceAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceAttachment).filter(
            PurchaseInvoiceAttachment.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                PurchaseInvoiceAttachment(
                    purchase_invoice_id=row.id,
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
        row: PurchaseInvoice,
        notes: list[PurchaseInvoiceNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceNote).filter(
            PurchaseInvoiceNote.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                PurchaseInvoiceNote(
                    purchase_invoice_id=row.id,
                    firm_id=firm_id,
                    note_type=note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type),
                    note=note.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_accounting_events(
        self, row: PurchaseInvoice, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(PurchaseInvoiceAccountingEvent).filter(
            PurchaseInvoiceAccountingEvent.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (PurchaseInvoiceAccountingEventType.PURCHASE_EXPENSE.value, "Purchase Expense", "DEBIT", row.subtotal),
            (PurchaseInvoiceAccountingEventType.INPUT_TAX.value, "Input Tax", "DEBIT", row.tax_total),
            (PurchaseInvoiceAccountingEventType.ACCOUNTS_PAYABLE.value, "Accounts Payable", "CREDIT", row.grand_total),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                PurchaseInvoiceAccountingEvent(
                    purchase_invoice_id=row.id,
                    firm_id=firm_id,
                    event_type=event_type,
                    account_name=account_name,
                    direction=direction,
                    amount=self._q(amount),
                    narration=f"Placeholder accounting event for {row.invoice_number}",
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _prepare_invoice_sources(
        self, data: PurchaseInvoiceCreate, firm_id: UUID
    ) -> tuple[dict[str, UUID], list[dict[str, object]], list[dict[str, object]]]:
        lines = [item.model_dump(mode="python") for item in data.lines]
        sources = [item.model_dump(mode="python") for item in data.source_documents]
        inferred_sources = {
            (self._source_type(item["source_document_type"]), item["source_document_id"])
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
            if source_type == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
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
            elif source_type == PurchaseInvoiceSourceType.PURCHASE_ORDER.value:
                if not data.allow_direct_purchase_order:
                    raise ValidationError("Direct purchase order invoicing is disabled.")
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
            if source["vendor_id"] != header["vendor_id"] or source["branch_id"] != header["branch_id"]:
                raise ValidationError("All source documents must belong to the same vendor and branch.")
        self._validate_line_sources(lines, {row["source_document_id"] for row in source_rows})
        return header, source_rows, lines

    def _validate_line_sources(
        self, lines: list[dict[str, object]], source_ids: set[UUID]
    ) -> None:
        for line in lines:
            if line["source_document_id"] not in source_ids:
                raise ValidationError("Every invoice line must reference a selected source document.")

    def _delete_children(self, invoice_id: UUID) -> None:
        self._session.query(PurchaseInvoiceAccountingEvent).filter(
            PurchaseInvoiceAccountingEvent.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceLine).filter(
            PurchaseInvoiceLine.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceSource).filter(
            PurchaseInvoiceSource.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceAttachment).filter(
            PurchaseInvoiceAttachment.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceNote).filter(
            PurchaseInvoiceNote.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)

    def _tax_amount(
        self,
        *,
        invoice_date: date,
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
        if tax_profile_id is None or invoice_value <= ZERO:
            return ZERO
        request = TaxRuleSimulationRequest(
            transaction_type="PURCHASE_INVOICE",
            transaction_date=invoice_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            vendor_id=vendor_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "purchase_invoice"},
        )
        response = self._tax.simulate(request, firm_scope=firm_id, actor_id=actor_id)
        return self._q(response.total_tax_amount)

    def _source_quantity(self, spec: dict[str, object], source_line: object) -> Decimal:
        if self._source_type(spec["source_document_type"]) == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
            return self._q(getattr(source_line, "accepted_quantity", ZERO))
        return self._q(getattr(source_line, "ordered_quantity", ZERO))

    def _already_invoiced_quantity(self, *, firm_id: UUID, source_document_line_id: UUID) -> Decimal:
        total = self._session.scalar(
            select(func.coalesce(func.sum(PurchaseInvoiceLine.current_invoice_quantity), ZERO))
            .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id)
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.source_document_line_id == source_document_line_id,
            )
        )
        return self._q(total or ZERO)

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: object) -> UUID | None:
        return getattr(source_line, "purchase_uom_id", None) or getattr(source_line, "inventory_uom_id", None)

    def _source_line_number(self, source_line: object) -> int:
        return int(getattr(source_line, "line_number"))

    def _source_description(self, source_line: object) -> str | None:
        return getattr(source_line, "description", None)

    def _source_document_number(self, spec: dict[str, object], source_line: object) -> str:
        source_number = spec.get("source_document_number")
        if source_number:
            return str(source_number)
        source_type = self._source_type(spec["source_document_type"])
        if source_type == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
            document = self._session.scalar(
                select(GoodsReceipt).where(GoodsReceipt.id == getattr(source_line, "goods_receipt_id"))
            )
            if document is not None:
                return document.grn_number
        document = self._session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.id == getattr(source_line, "purchase_order_id"))
        )
        if document is not None:
            return document.po_number
        return str(source_number or "")

    def _product_id(self, source_line: object) -> UUID:
        return getattr(source_line, "product_id")

    def _line_net_amount(
        self, *, quantity: Decimal, unit_price: Decimal, discount_amount: Decimal, charges_amount: Decimal
    ) -> Decimal:
        return self._q(quantity * unit_price - discount_amount + charges_amount)

    def _validate_supplier_invoice_number(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_invoice_number: str,
        current_id: UUID | None = None,
    ) -> None:
        if self._duplicate_warning(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_invoice_number=supplier_invoice_number,
            current_id=current_id,
        ):
            return

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_invoice_number: str,
        current_id: UUID | None,
    ) -> str | None:
        statement = select(PurchaseInvoice.id).where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.vendor_id == vendor_id,
            PurchaseInvoice.supplier_invoice_number == supplier_invoice_number,
            PurchaseInvoice.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(PurchaseInvoice.id != current_id)
        if self._session.scalar(statement) is not None:
            return "A purchase invoice with this supplier invoice number already exists."
        return None

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        invoice: PurchaseInvoice,
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
                source_document_id=invoice.id,
                source_module_code="PURCHASE_INVOICE",
                document_number=invoice.invoice_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "invoice_number": invoice.invoice_number,
                    "supplier_invoice_number": invoice.supplier_invoice_number,
                    "grand_total": str(invoice.grand_total),
                },
                snapshot_json={
                    "status": invoice.status,
                    "vendor_id": str(invoice.vendor_id),
                    "branch_id": str(invoice.branch_id),
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
                DocumentTypeDefinition.code == "PURCHASE_INVOICE",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if document_type is None:
            document_type = self._documents.create_type(
                firm_id,
                DocumentTypeCreate(
                    code="PURCHASE_INVOICE",
                    name="Purchase Invoice",
                    description="Supplier invoice document",
                    category="FINANCE",
                    is_active=True,
                    configuration={"module": "purchase_invoice"},
                ),
                actor_id,
            )
        for state_code, name, sort_order in [
            ("DRAFT", "Draft", 1),
            ("APPROVED", "Approved", 2),
            ("CANCELLED", "Cancelled", 3),
            ("CLOSED", "Closed", 4),
        ]:
            if not self._state_exists(firm_id=firm_id, document_type_id=document_type.id, code=state_code):
                self._documents.create_state(
                    firm_id,
                    DocumentStateCreate(
                        document_type_id=document_type.id,
                        code=state_code,
                        name=name,
                        sort_order=sort_order,
                        is_default=state_code == "DRAFT",
                        is_terminal=state_code in {"CANCELLED", "CLOSED"},
                        allows_edit=state_code == "DRAFT",
                        allows_print=True,
                        allows_email=True,
                        allows_export_pdf=True,
                        transition_rules={"module": "purchase_invoice", "state": state_code},
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
                    code="PURCHASE_INVOICE_DEFAULT",
                    name="Purchase Invoice Default",
                    prefix="PI",
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
                    configuration={"module": "purchase_invoice"},
                ),
                actor_id,
            )
        return document_type, numbering_rule

    def _state_exists(self, *, firm_id: UUID, document_type_id: UUID, code: str) -> bool:
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
                DocumentTypeDefinition.code == "PURCHASE_INVOICE",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase invoice document type not found.")
        return row

    def _financial_year_label(self, on: date) -> str:
        return f"{on.year}"

    def _scope_code(self, branch_id: UUID | None) -> str | None:
        return str(branch_id)[:8].upper() if branch_id is not None else None

    def _company_code(self, firm_id: UUID) -> str | None:
        return str(firm_id)[:8].upper()

    def _flush_or_conflict(self, message: str) -> None:
        try:
            self._session.flush()
        except Exception as error:
            raise ConflictError(message) from error

    def _q(self, value: Decimal | int | str | None) -> Decimal:
        if value is None:
            return ZERO
        return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _attachment_response(self, row: PurchaseInvoiceAttachment) -> PurchaseInvoiceAttachmentResponse:
        return PurchaseInvoiceAttachmentResponse.model_validate(row)

    def _note_response(self, row: PurchaseInvoiceNote) -> PurchaseInvoiceNoteResponse:
        return PurchaseInvoiceNoteResponse.model_validate(row)

    def _source_response(self, row: PurchaseInvoiceSource) -> PurchaseInvoiceSourceResponse:
        return PurchaseInvoiceSourceResponse(
            id=row.id,
            source_document_type=PurchaseInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: PurchaseInvoiceAccountingEvent
    ) -> PurchaseInvoiceAccountingEventResponse:
        return PurchaseInvoiceAccountingEventResponse(
            id=row.id,
            event_type=PurchaseInvoiceAccountingEventType(row.event_type),
            account_name=row.account_name,
            direction=row.direction,
            amount=row.amount,
            narration=row.narration,
            source_line_id=row.source_line_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _line_response(self, row: PurchaseInvoiceLine) -> PurchaseInvoiceLineResponse:
        return PurchaseInvoiceLineResponse(
            id=row.id,
            purchase_invoice_id=row.purchase_invoice_id,
            line_number=row.line_number,
            source_document_type=PurchaseInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            received_quantity=row.received_quantity,
            already_invoiced_quantity=row.already_invoiced_quantity,
            current_invoice_quantity=row.current_invoice_quantity,
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
            invoice_uom_id=row.invoice_uom_id,
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
