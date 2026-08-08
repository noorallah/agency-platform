"""Sales invoice workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
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
from app.identity.models import User
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceAccountingEvent,
    SalesInvoiceAttachment,
    SalesInvoiceLine,
    SalesInvoiceNote,
    SalesInvoiceSource,
)
from app.sales_invoice.schemas import (
    SalesInvoiceAccountingEventResponse,
    SalesInvoiceAccountingEventType,
    SalesInvoiceAttachmentResponse,
    SalesInvoiceAttachmentWrite,
    SalesInvoiceCreate,
    SalesInvoiceCustomerOutstandingRecord,
    SalesInvoiceImportRequest,
    SalesInvoiceLineResponse,
    SalesInvoiceListFilters,
    SalesInvoiceNoteResponse,
    SalesInvoiceNoteWrite,
    SalesInvoiceReconciliationRecord,
    SalesInvoiceRegisterRecord,
    SalesInvoiceResponse,
    SalesInvoiceSourceResponse,
    SalesInvoiceSourceType,
    SalesInvoiceStatus,
    SalesInvoiceSummary,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")


class SalesInvoiceService:
    """Coordinate customer invoice lifecycle and source-document validation."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._documents = DocumentFrameworkService(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)

    def list_invoices(
        self,
        *,
        firm_scope: UUID,
        filters: SalesInvoiceListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SalesInvoice], int]:
        columns = {
            "invoice_number": SalesInvoice.invoice_number,
            "invoice_date": SalesInvoice.invoice_date,
            "due_date": SalesInvoice.due_date,
            "grand_total": SalesInvoice.grand_total,
            "status": SalesInvoice.status,
            "created_at": SalesInvoice.created_at,
            "updated_at": SalesInvoice.updated_at,
        }
        statement = select(SalesInvoice).where(SalesInvoice.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(SalesInvoice)
            .where(SalesInvoice.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(SalesInvoice.is_deleted.is_(False))
            count = count.where(SalesInvoice.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(SalesInvoice.customer_id == filters.customer_id)
            count = count.where(SalesInvoice.customer_id == filters.customer_id)
        if filters.branch_id is not None:
            statement = statement.where(SalesInvoice.branch_id == filters.branch_id)
            count = count.where(SalesInvoice.branch_id == filters.branch_id)
        if filters.salesman_id is not None:
            statement = statement.where(SalesInvoice.salesman_id == filters.salesman_id)
            count = count.where(SalesInvoice.salesman_id == filters.salesman_id)
        if filters.territory_id is not None:
            statement = statement.where(
                SalesInvoice.territory_id == filters.territory_id
            )
            count = count.where(SalesInvoice.territory_id == filters.territory_id)
        if filters.status is not None:
            statement = statement.where(SalesInvoice.status == filters.status.value)
            count = count.where(SalesInvoice.status == filters.status.value)
        if filters.invoice_from is not None:
            statement = statement.where(
                SalesInvoice.invoice_date >= filters.invoice_from
            )
            count = count.where(SalesInvoice.invoice_date >= filters.invoice_from)
        if filters.invoice_to is not None:
            statement = statement.where(SalesInvoice.invoice_date <= filters.invoice_to)
            count = count.where(SalesInvoice.invoice_date <= filters.invoice_to)
        if filters.due_from is not None:
            statement = statement.where(SalesInvoice.due_date >= filters.due_from)
            count = count.where(SalesInvoice.due_date >= filters.due_from)
        if filters.due_to is not None:
            statement = statement.where(SalesInvoice.due_date <= filters.due_to)
            count = count.where(SalesInvoice.due_date <= filters.due_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesInvoice.invoice_number.ilike(token),
                SalesInvoice.customer_invoice_number.ilike(token),
                SalesInvoice.reference_number.ilike(token),
                SalesInvoice.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, SalesInvoice.created_at)
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

    def summary(self, *, firm_scope: UUID) -> SalesInvoiceSummary:
        rows = list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
            ).all()
        )
        overdue = sum(
            1
            for row in rows
            if row.due_date is not None
            and row.due_date < date.today()
            and row.status
            not in {SalesInvoiceStatus.CANCELLED.value, SalesInvoiceStatus.CLOSED.value}
        )
        return SalesInvoiceSummary(
            total=len(rows),
            draft=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.DRAFT.value
            ),
            approved=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.APPROVED.value
            ),
            cancelled=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
            pending_invoices=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.DRAFT.value
            ),
            overdue_invoices=overdue,
        )

    def create_invoice(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoice:
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_id=firm_id
        )
        branch_id = data.branch_id or header["branch_id"]
        customer_id = data.customer_id or header["customer_id"]
        salesman_id = data.salesman_id or header.get("salesman_id")
        territory_id = data.territory_id or header.get("territory_id")
        route_id = data.route_id or header.get("route_id")
        business_profile_id = data.business_profile_id
        if customer_id != header["customer_id"]:
            raise ValidationError("Invoice customer must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        if data.salesman_id is not None and header.get("salesman_id") not in {
            None,
            data.salesman_id,
        }:
            raise ValidationError("Invoice salesman must match all source documents.")
        if data.territory_id is not None and header.get("territory_id") not in {
            None,
            data.territory_id,
        }:
            raise ValidationError("Invoice territory must match all source documents.")
        if data.route_id is not None and header.get("route_id") not in {
            None,
            data.route_id,
        }:
            raise ValidationError("Invoice route must match all source documents.")
        self._validate_scope_references(
            firm_id=firm_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
        )
        self._validate_customer_invoice_number(
            firm_id=firm_id,
            customer_id=customer_id,
            customer_invoice_number=data.customer_invoice_number,
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
        row = SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
            branch_id=branch_id,
            business_profile_id=business_profile_id,
            invoice_number=invoice_number,
            invoice_date=data.invoice_date,
            customer_invoice_number=(
                data.customer_invoice_number.strip()
                if data.customer_invoice_number
                else None
            ),
            currency_code=(
                data.currency_code.strip().upper() if data.currency_code else None
            ),
            exchange_rate=data.exchange_rate,
            payment_terms=data.payment_terms,
            due_date=data.due_date,
            reference_number=data.reference_number,
            remarks=data.remarks,
            allow_direct_sales_order=data.allow_direct_sales_order,
            allow_over_invoice=data.allow_over_invoice,
            over_invoice_percent=self._q(data.over_invoice_percent),
            status=SalesInvoiceStatus.DRAFT.value,
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
        row.total_already_invoiced_quantity = line_totals[
            "total_already_invoiced_quantity"
        ]
        row.total_current_invoice_quantity = line_totals[
            "total_current_invoice_quantity"
        ]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_id
        )
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
            action="sales_invoice.created",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"invoice_number": row.invoice_number, "status": row.status},
        )
        self._flush_or_conflict("Sales invoice number already exists in this firm.")
        self._session.commit()
        return row

    def update_invoice(
        self,
        invoice_id: UUID,
        data: SalesInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SalesInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_id)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft sales invoices can be updated.")
        self._delete_children(row.id)
        header, source_rows, line_specs = self._prepare_invoice_sources(data, firm_id)
        row.customer_id = data.customer_id or header["customer_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.business_profile_id = data.business_profile_id
        row.salesman_id = data.salesman_id or header.get("salesman_id")
        row.territory_id = data.territory_id or header.get("territory_id")
        row.route_id = data.route_id or header.get("route_id")
        row.invoice_date = data.invoice_date
        row.customer_invoice_number = (
            data.customer_invoice_number.strip()
            if data.customer_invoice_number
            else None
        )
        row.currency_code = (
            data.currency_code.strip().upper() if data.currency_code else None
        )
        row.exchange_rate = data.exchange_rate
        row.payment_terms = data.payment_terms
        row.due_date = data.due_date
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.allow_direct_sales_order = data.allow_direct_sales_order
        row.allow_over_invoice = data.allow_over_invoice
        row.over_invoice_percent = self._q(data.over_invoice_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        if row.customer_id != header["customer_id"]:
            raise ValidationError("Invoice customer must match all source documents.")
        if row.branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        if data.salesman_id is not None and header.get("salesman_id") not in {
            None,
            data.salesman_id,
        }:
            raise ValidationError("Invoice salesman must match all source documents.")
        if data.territory_id is not None and header.get("territory_id") not in {
            None,
            data.territory_id,
        }:
            raise ValidationError("Invoice territory must match all source documents.")
        if data.route_id is not None and header.get("route_id") not in {
            None,
            data.route_id,
        }:
            raise ValidationError("Invoice route must match all source documents.")
        self._validate_scope_references(
            firm_id=firm_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
        )
        self._validate_customer_invoice_number(
            firm_id=firm_id,
            customer_id=row.customer_id,
            customer_invoice_number=row.customer_invoice_number,
            current_id=row.id,
        )
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_invoiced_quantity = line_totals[
            "total_already_invoiced_quantity"
        ]
        row.total_current_invoice_quantity = line_totals[
            "total_current_invoice_quantity"
        ]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_id
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_id)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_id)
        self._record_event(
            firm_id=firm_id,
            document_type=self._document_type(firm_id),
            invoice=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_invoice.updated",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()
        return row

    def approve_invoice(
        self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft sales invoices can be approved.")
        before = row.status
        row.status = SalesInvoiceStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        CustomerService(self._session).post_receivable_transaction(
            row.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.INVOICE,
                transaction_date=row.invoice_date,
                amount=self._q(row.grand_total),
                reference_type="SALES_INVOICE",
                reference_id=row.id,
                reference_number=row.invoice_number,
                remarks=f"Invoice {row.invoice_number} approved.",
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
            commit=False,
        )
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
            action="sales_invoice.approved",
            entity_type="sales_invoice",
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
    ) -> SalesInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status in {
            SalesInvoiceStatus.CANCELLED.value,
            SalesInvoiceStatus.CLOSED.value,
        }:
            raise ValidationError("This sales invoice can no longer be cancelled.")
        before = row.status
        row.status = SalesInvoiceStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        if before == SalesInvoiceStatus.APPROVED.value:
            CustomerService(self._session).post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
                    transaction_date=utc_now().date(),
                    amount=self._q(row.grand_total),
                    reference_type="SALES_INVOICE",
                    reference_id=row.id,
                    reference_number=row.invoice_number,
                    remarks=reason
                    or f"Auto reversal for cancelled invoice {row.invoice_number}.",
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
                commit=False,
            )
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
            action="sales_invoice.cancelled",
            entity_type="sales_invoice",
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
    ) -> SalesInvoice:
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == SalesInvoiceStatus.CLOSED.value:
            raise ValidationError("This sales invoice is already closed.")
        before = row.status
        row.status = SalesInvoiceStatus.CLOSED.value
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
            action="sales_invoice.closed",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> SalesInvoice:
        row = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        return row

    def invoice_response(self, row: SalesInvoice) -> SalesInvoiceResponse:
        sources = list(
            self._session.scalars(
                select(SalesInvoiceSource).where(
                    SalesInvoiceSource.sales_invoice_id == row.id,
                    SalesInvoiceSource.is_deleted.is_(False),
                )
            ).all()
        )
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == row.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(SalesInvoiceAttachment).where(
                    SalesInvoiceAttachment.sales_invoice_id == row.id,
                    SalesInvoiceAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(SalesInvoiceNote).where(
                    SalesInvoiceNote.sales_invoice_id == row.id,
                    SalesInvoiceNote.is_deleted.is_(False),
                )
            ).all()
        )
        accounting_events = list(
            self._session.scalars(
                select(SalesInvoiceAccountingEvent).where(
                    SalesInvoiceAccountingEvent.sales_invoice_id == row.id,
                    SalesInvoiceAccountingEvent.is_deleted.is_(False),
                )
            ).all()
        )
        warning = self._duplicate_warning(
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            customer_invoice_number=row.customer_invoice_number,
            current_id=row.id,
        )
        return SalesInvoiceResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
            branch_id=row.branch_id,
            business_profile_id=row.business_profile_id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            customer_invoice_number=row.customer_invoice_number,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_direct_sales_order=row.allow_direct_sales_order,
            allow_over_invoice=row.allow_over_invoice,
            over_invoice_percent=row.over_invoice_percent,
            status=SalesInvoiceStatus(row.status),
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
            accounting_events=[
                self._accounting_event_response(item) for item in accounting_events
            ],
            duplicate_warning=warning,
        )

    def timeline(
        self, *, invoice_id: UUID, firm_scope: UUID, page: int, page_size: int
    ):
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=invoice_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_invoices(self, *, firm_scope: UUID) -> list[SalesInvoice]:
        return list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status == SalesInvoiceStatus.DRAFT.value,
                )
            ).all()
        )

    def overdue_invoices(self, *, firm_scope: UUID) -> list[SalesInvoice]:
        today = date.today()
        return list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.due_date.is_not(None),
                    SalesInvoice.due_date < today,
                    SalesInvoice.status.not_in(
                        [
                            SalesInvoiceStatus.CANCELLED.value,
                            SalesInvoiceStatus.CLOSED.value,
                        ]
                    ),
                )
            ).all()
        )

    def register_report(self, *, firm_scope: UUID) -> list[SalesInvoiceRegisterRecord]:
        rows = list(
            self._session.scalars(
                select(SalesInvoice)
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
                .order_by(
                    SalesInvoice.invoice_date.desc(), SalesInvoice.created_at.desc()
                )
            ).all()
        )
        return [
            SalesInvoiceRegisterRecord(
                invoice_id=row.id,
                invoice_number=row.invoice_number,
                customer_invoice_number=row.customer_invoice_number,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                grand_total=row.grand_total,
                status=SalesInvoiceStatus(row.status),
            )
            for row in rows
        ]

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[SalesInvoiceCustomerOutstandingRecord]:
        rows = list(
            self._session.scalars(
                select(Customer).where(
                    Customer.firm_id == firm_scope,
                    Customer.is_deleted.is_(False),
                )
            ).all()
        )
        counts: dict[UUID, int] = defaultdict(int)
        for row in self._session.scalars(
            select(SalesInvoice).where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status == SalesInvoiceStatus.APPROVED.value,
            )
        ):
            counts[row.customer_id] += 1
        return [
            SalesInvoiceCustomerOutstandingRecord(
                customer_id=customer.id,
                customer_name=customer.name,
                outstanding_amount=self._q(customer.current_outstanding),
                invoice_count=counts[customer.id],
            )
            for customer in rows
            if customer.current_outstanding > ZERO
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID
    ) -> list[SalesInvoiceReconciliationRecord]:
        rows = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        )
        result: list[SalesInvoiceReconciliationRecord] = []
        for row in rows:
            pending = self._q(
                row.delivered_quantity
                - row.already_invoiced_quantity
                - row.current_invoice_quantity
            )
            result.append(
                SalesInvoiceReconciliationRecord(
                    source_document_type=SalesInvoiceSourceType(
                        row.source_document_type
                    ),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    delivered_quantity=row.delivered_quantity,
                    already_invoiced_quantity=row.already_invoiced_quantity,
                    current_invoice_quantity=row.current_invoice_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                )
            )
        return result

    def export_invoices_csv(
        self, *, firm_scope: UUID, search: str | None = None
    ) -> str:
        rows, _ = self.list_invoices(
            firm_scope=firm_scope,
            filters=SalesInvoiceListFilters(),
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
                "customer_invoice_number",
                "invoice_date",
                "customer_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.invoice_number,
                    row.customer_invoice_number or "",
                    row.invoice_date.isoformat(),
                    str(row.customer_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_invoices(
        self, data: SalesInvoiceImportRequest, *, firm_id: UUID, actor_id: UUID
    ) -> list[SalesInvoice]:
        return [
            self.create_invoice(record, firm_id=firm_id, actor_id=actor_id)
            for record in data.records
        ]

    def _replace_sources(
        self,
        row: SalesInvoice,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceSource).filter(
            SalesInvoiceSource.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = SalesInvoiceSource(
                sales_invoice_id=row.id,
                firm_id=firm_id,
                source_document_type=item["source_document_type"],
                source_document_id=item["source_document_id"],
                source_document_number=item["source_document_number"],
                source_document_date=item["source_document_date"],
                customer_id=item["customer_id"],
                branch_id=item["branch_id"],
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(source)

    def _replace_lines(
        self,
        row: SalesInvoice,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        invoice_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(SalesInvoiceLine).filter(
            SalesInvoiceLine.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        totals = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            if source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value:
                source_line = self._session.scalar(
                    select(DeliveryNoteLine).where(
                        DeliveryNoteLine.id == spec["source_document_line_id"]
                    )
                )
            else:
                source_line = self._session.scalar(
                    select(SalesOrderLine).where(
                        SalesOrderLine.id == spec["source_document_line_id"]
                    )
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            requested_quantity = self._q(Decimal(str(spec["current_invoice_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            invoice_uom_id = spec.get("invoice_uom_id")
            conversion_factor = self._q(
                Decimal(str(spec.get("conversion_factor", Decimal("1"))))
            )
            invoice_quantity = requested_quantity
            if (
                source_uom_id is not None
                and invoice_uom_id is not None
                and invoice_uom_id != source_uom_id
            ):
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
            allowed_quantity = source_quantity
            if row.allow_over_invoice:
                allowed_quantity = self._q(
                    source_quantity
                    + (
                        source_quantity
                        * self._q(row.over_invoice_percent)
                        / Decimal("100")
                    )
                )
            if invoice_quantity + already_invoiced > allowed_quantity:
                raise ValidationError(
                    "Invoice quantity exceeds the available source quantity."
                )
            tax_amount = self._tax_amount(
                invoice_date=invoice_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                customer_id=row.customer_id,
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
            net_amount = self._q(
                gross_amount - discount_amount + charges_amount + tax_amount
            )
            line = SalesInvoiceLine(
                sales_invoice_id=row.id,
                firm_id=firm_id,
                line_number=index,
                source_document_type=source_type,
                source_document_id=spec["source_document_id"],
                source_document_number=self._source_document_number(spec, source_line),
                source_document_line_id=source_line.id,
                source_document_line_number=self._source_line_number(source_line),
                product_id=self._product_id(source_line),
                description=self._source_description(source_line),
                delivered_quantity=source_quantity,
                already_invoiced_quantity=already_invoiced,
                current_invoice_quantity=invoice_quantity,
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
                order_uom_id=spec.get("order_uom_id") or source_uom_id,
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
            totals["subtotal"] += self._q(
                gross_amount - discount_amount + charges_amount
            )
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: SalesInvoice,
        attachments: list[SalesInvoiceAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceAttachment).filter(
            SalesInvoiceAttachment.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                SalesInvoiceAttachment(
                    sales_invoice_id=row.id,
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
        row: SalesInvoice,
        notes: list[SalesInvoiceNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceNote).filter(
            SalesInvoiceNote.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                SalesInvoiceNote(
                    sales_invoice_id=row.id,
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
        self, row: SalesInvoice, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(SalesInvoiceAccountingEvent).filter(
            SalesInvoiceAccountingEvent.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (
                SalesInvoiceAccountingEventType.SALES_REVENUE.value,
                "Sales Revenue",
                "CREDIT",
                row.subtotal,
            ),
            (
                SalesInvoiceAccountingEventType.OUTPUT_TAX.value,
                "Output Tax",
                "CREDIT",
                row.tax_total,
            ),
            (
                SalesInvoiceAccountingEventType.ACCOUNTS_RECEIVABLE.value,
                "Accounts Receivable",
                "DEBIT",
                row.grand_total,
            ),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                SalesInvoiceAccountingEvent(
                    sales_invoice_id=row.id,
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
        self, data: SalesInvoiceCreate, firm_id: UUID
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
            if source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value:
                document = self._session.scalar(
                    select(DeliveryNote).where(
                        DeliveryNote.id == source_id,
                        DeliveryNote.firm_id == firm_id,
                        DeliveryNote.is_deleted.is_(False),
                    )
                )
                if document is None:
                    raise ResourceNotFoundError("Delivery note not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": document.id,
                        "source_document_number": document.delivery_note_number,
                        "source_document_date": document.delivery_date,
                        "customer_id": document.customer_id,
                        "branch_id": document.branch_id,
                        "salesman_id": document.salesman_id,
                        "territory_id": document.territory_id,
                        "route_id": document.route_id,
                    }
                )
            elif source_type == SalesInvoiceSourceType.SALES_ORDER.value:
                if not data.allow_direct_sales_order:
                    raise ValidationError("Direct sales order invoicing is disabled.")
                document = self._session.scalar(
                    select(SalesOrder).where(
                        SalesOrder.id == source_id,
                        SalesOrder.firm_id == firm_id,
                        SalesOrder.is_deleted.is_(False),
                    )
                )
                if document is None:
                    raise ResourceNotFoundError("Sales order not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": document.id,
                        "source_document_number": document.order_number,
                        "source_document_date": document.order_date,
                        "customer_id": document.customer_id,
                        "branch_id": document.branch_id,
                        "salesman_id": document.salesman_id,
                        "territory_id": document.territory_id,
                        "route_id": document.route_id,
                    }
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        header["customer_id"] = first["customer_id"]
        header["branch_id"] = first["branch_id"]
        if first.get("salesman_id") is not None:
            header["salesman_id"] = first["salesman_id"]
        if first.get("territory_id") is not None:
            header["territory_id"] = first["territory_id"]
        if first.get("route_id") is not None:
            header["route_id"] = first["route_id"]
        for source in source_rows[1:]:
            if (
                source["customer_id"] != header["customer_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same customer and branch."
                )
            if (
                header.get("salesman_id") not in {None, source.get("salesman_id")}
                and source.get("salesman_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same salesman."
                )
            if (
                header.get("territory_id") not in {None, source.get("territory_id")}
                and source.get("territory_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same territory."
                )
            if (
                header.get("route_id") not in {None, source.get("route_id")}
                and source.get("route_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same route."
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
                    "Every invoice line must reference a selected source document."
                )

    def _delete_children(self, invoice_id: UUID) -> None:
        self._session.query(SalesInvoiceAccountingEvent).filter(
            SalesInvoiceAccountingEvent.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceLine).filter(
            SalesInvoiceLine.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceSource).filter(
            SalesInvoiceSource.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceAttachment).filter(
            SalesInvoiceAttachment.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceNote).filter(
            SalesInvoiceNote.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)

    def _tax_amount(
        self,
        *,
        invoice_date: date,
        firm_id: UUID,
        actor_id: UUID,
        business_profile_id: UUID | None,
        customer_id: UUID,
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
                    product, invoice_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, invoice_date, firm_scope=firm_id
            )
        request = TaxRuleSimulationRequest(
            transaction_type="SALES_INVOICE",
            transaction_date=invoice_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "sales_invoice"},
        )
        response = self._tax.simulate(request, firm_scope=firm_id, actor_id=actor_id)
        return self._q(response.total_tax_amount)

    def _source_quantity(self, spec: dict[str, object], source_line: object) -> Decimal:
        if (
            self._source_type(spec["source_document_type"])
            == SalesInvoiceSourceType.DELIVERY_NOTE.value
        ):
            return self._q(getattr(source_line, "delivered_quantity", ZERO))
        return self._q(getattr(source_line, "quantity", ZERO))

    def _already_invoiced_quantity(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> Decimal:
        total = self._session.scalar(
            select(
                func.coalesce(func.sum(SalesInvoiceLine.current_invoice_quantity), ZERO)
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLine.source_document_line_id == source_document_line_id,
            )
        )
        return self._q(total or ZERO)

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: object) -> UUID | None:
        return getattr(source_line, "sales_uom_id", None) or getattr(
            source_line, "inventory_uom_id", None
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
        if source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value:
            document = self._session.scalar(
                select(DeliveryNote).where(
                    DeliveryNote.id == source_line.delivery_note_id
                )
            )
            if document is not None:
                return document.delivery_note_number
        document = self._session.scalar(
            select(SalesOrder).where(SalesOrder.id == source_line.sales_order_id)
        )
        if document is not None:
            return document.order_number
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

    def _validate_scope_references(
        self,
        *,
        firm_id: UUID,
        salesman_id: UUID | None,
        territory_id: UUID | None,
        route_id: UUID | None,
    ) -> None:
        if salesman_id is not None:
            user = self._session.scalar(
                select(User.id).where(
                    User.id == salesman_id, User.is_deleted.is_(False)
                )
            )
            if user is None:
                raise ValidationError("Salesman user not found.")
        if territory_id is not None:
            territory = self._session.scalar(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.id == territory_id,
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if territory is None:
                raise ValidationError("Territory not found in this firm.")
        if route_id is not None:
            route = self._session.scalar(
                select(TerritoryRouteProfile.id).where(
                    TerritoryRouteProfile.id == route_id,
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
            if route is None:
                raise ValidationError("Route profile not found.")

    def _validate_customer_invoice_number(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        customer_invoice_number: str | None,
        current_id: UUID | None = None,
    ) -> None:
        warning = self._duplicate_warning(
            firm_id=firm_id,
            customer_id=customer_id,
            customer_invoice_number=customer_invoice_number,
            current_id=current_id,
        )
        if warning is not None:
            raise ConflictError(warning)

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        customer_invoice_number: str | None,
        current_id: UUID | None,
    ) -> str | None:
        normalized_number = (
            customer_invoice_number.strip() if customer_invoice_number else None
        )
        if not normalized_number:
            return None
        statement = select(SalesInvoice.id).where(
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.customer_id == customer_id,
            SalesInvoice.customer_invoice_number == normalized_number,
            SalesInvoice.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(SalesInvoice.id != current_id)
        if self._session.scalar(statement) is not None:
            return "A sales invoice with this customer invoice number already exists."
        return None

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        invoice: SalesInvoice,
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
                source_module_code="SALES_INVOICE",
                document_number=invoice.invoice_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "invoice_number": invoice.invoice_number,
                    "customer_invoice_number": invoice.customer_invoice_number,
                    "grand_total": str(invoice.grand_total),
                },
                snapshot_json={
                    "status": invoice.status,
                    "customer_id": str(invoice.customer_id),
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
                DocumentTypeDefinition.code == "SALES_INVOICE",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if document_type is None:
            document_type = self._documents.create_type(
                firm_id,
                DocumentTypeCreate(
                    code="SALES_INVOICE",
                    name="Sales Invoice",
                    description="Customer invoice document",
                    category="FINANCE",
                    is_active=True,
                    configuration={"module": "sales_invoice"},
                ),
                actor_id,
            )
        for state_code, name, sort_order in [
            ("DRAFT", "Draft", 1),
            ("APPROVED", "Approved", 2),
            ("CANCELLED", "Cancelled", 3),
            ("CLOSED", "Closed", 4),
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
                        is_terminal=state_code in {"CANCELLED", "CLOSED"},
                        allows_edit=state_code == "DRAFT",
                        allows_print=True,
                        allows_email=True,
                        allows_export_pdf=True,
                        transition_rules={
                            "module": "sales_invoice",
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
                    code="SALES_INVOICE_DEFAULT",
                    name="Sales Invoice Default",
                    prefix="SI",
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
                    configuration={"module": "sales_invoice"},
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
                DocumentTypeDefinition.code == "SALES_INVOICE",
                DocumentTypeDefinition.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales invoice document type not found.")
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

    def _attachment_response(
        self, row: SalesInvoiceAttachment
    ) -> SalesInvoiceAttachmentResponse:
        return SalesInvoiceAttachmentResponse.model_validate(row)

    def _note_response(self, row: SalesInvoiceNote) -> SalesInvoiceNoteResponse:
        return SalesInvoiceNoteResponse.model_validate(row)

    def _source_response(self, row: SalesInvoiceSource) -> SalesInvoiceSourceResponse:
        return SalesInvoiceSourceResponse(
            id=row.id,
            source_document_type=SalesInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            customer_id=row.customer_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: SalesInvoiceAccountingEvent
    ) -> SalesInvoiceAccountingEventResponse:
        return SalesInvoiceAccountingEventResponse(
            id=row.id,
            event_type=SalesInvoiceAccountingEventType(row.event_type),
            account_name=row.account_name,
            direction=row.direction,
            amount=row.amount,
            narration=row.narration,
            source_line_id=row.source_line_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _line_response(self, row: SalesInvoiceLine) -> SalesInvoiceLineResponse:
        return SalesInvoiceLineResponse(
            id=row.id,
            sales_invoice_id=row.sales_invoice_id,
            line_number=row.line_number,
            source_document_type=SalesInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            delivered_quantity=row.delivered_quantity,
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
            order_uom_id=row.order_uom_id,
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
