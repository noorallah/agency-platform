"""Delivery note backend lifecycle, dispatch, and reporting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, platform_reader
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.pricing import (
    LineDiscount,
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
)
from app.customers.models import Customer
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteAttachment,
    DeliveryNoteLine,
    DeliveryNoteNote,
)
from app.delivery_note.schemas import (
    DeliveryNoteAttachmentResponse,
    DeliveryNoteAttachmentWrite,
    DeliveryNoteByDimensionRecord,
    DeliveryNoteCreate,
    DeliveryNoteImportRequest,
    DeliveryNoteLineResponse,
    DeliveryNoteLineWrite,
    DeliveryNoteListFilters,
    DeliveryNoteNoteResponse,
    DeliveryNoteNoteWrite,
    DeliveryNoteOrderProgressRecord,
    DeliveryNoteRegisterRecord,
    DeliveryNoteResponse,
    DeliveryNoteStatus,
    DeliveryNoteSummary,
)
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
from app.identity.models import User
from app.inventory.models import InventoryRecord, StockLedgerEntry
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderStatus
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")


def _source_product(
    source_lines: dict[UUID, SalesOrderLine], line_id: UUID | None
) -> UUID | None:
    """Return the product a delivery line is shipping.

    A delivery note line names an order line rather than a product, so pricing
    it against a price list has to go through the order to find out what is in
    the box.
    """
    if line_id is None:
        return None
    source = source_lines.get(line_id)
    return None if source is None else source.product_id


class DeliveryNoteService(TransactionalDocumentService):
    """Coordinate delivery note lifecycle, validation, and inventory dispatch."""

    DOCUMENT = DocumentTypeSpec(
        code="DELIVERY_NOTE",
        name="Delivery Note",
        description="Goods dispatch document",
        category="SALES",
        module="delivery_note",
        prefix="DN",
        include_branch_code=True,
        include_company_code=True,
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("DISPATCHED", "Dispatched", 3),
            DocumentStateSpec("COMPLETED", "Completed", 4, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 100, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)
        self._inventory = InventoryService(session)

    def list_notes(
        self,
        *,
        firm_scope: UUID,
        filters: DeliveryNoteListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[DeliveryNote], int]:
        """List delivery notes for the visible firm scope."""
        columns = {
            "delivery_note_number": DeliveryNote.delivery_note_number,
            "delivery_date": DeliveryNote.delivery_date,
            "status": DeliveryNote.status,
            "grand_total": DeliveryNote.grand_total,
            "created_at": DeliveryNote.created_at,
            "updated_at": DeliveryNote.updated_at,
        }
        statement = select(DeliveryNote).where(DeliveryNote.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(DeliveryNote)
            .where(DeliveryNote.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(DeliveryNote.is_deleted.is_(False))
            count = count.where(DeliveryNote.is_deleted.is_(False))
        if filters.sales_order_id is not None:
            statement = statement.where(
                DeliveryNote.sales_order_id == filters.sales_order_id
            )
            count = count.where(DeliveryNote.sales_order_id == filters.sales_order_id)
        if filters.customer_id is not None:
            statement = statement.where(DeliveryNote.customer_id == filters.customer_id)
            count = count.where(DeliveryNote.customer_id == filters.customer_id)
        if filters.branch_id is not None:
            statement = statement.where(DeliveryNote.branch_id == filters.branch_id)
            count = count.where(DeliveryNote.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                DeliveryNote.warehouse_id == filters.warehouse_id
            )
            count = count.where(DeliveryNote.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(DeliveryNote.status == filters.status.value)
            count = count.where(DeliveryNote.status == filters.status.value)
        if filters.delivery_from is not None:
            statement = statement.where(
                DeliveryNote.delivery_date >= filters.delivery_from
            )
            count = count.where(DeliveryNote.delivery_date >= filters.delivery_from)
        if filters.delivery_to is not None:
            statement = statement.where(
                DeliveryNote.delivery_date <= filters.delivery_to
            )
            count = count.where(DeliveryNote.delivery_date <= filters.delivery_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                DeliveryNote.delivery_note_number.ilike(token),
                DeliveryNote.sales_order_reference.ilike(token),
                DeliveryNote.vehicle.ilike(token),
                DeliveryNote.driver.ilike(token),
                DeliveryNote.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        order_column = columns.get(sort_by, DeliveryNote.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    order_column.desc() if descending else order_column.asc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> DeliveryNoteSummary:
        """Return aggregate delivery note values for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                )
            ).all()
        )
        progress = self.partially_delivered_orders(firm_scope=firm_scope)
        return DeliveryNoteSummary(
            total=len(rows),
            draft=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.DRAFT.value
            ),
            approved=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.APPROVED.value
            ),
            dispatched=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.DISPATCHED.value
            ),
            completed=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.COMPLETED.value
            ),
            cancelled=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in rows if row.status == DeliveryNoteStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
            pending_orders=sum(
                1 for item in progress if item.delivered_quantity <= ZERO
            ),
            partial_orders=sum(
                1
                for item in progress
                if item.delivered_quantity > ZERO and item.pending_quantity > ZERO
            ),
        )

    def create_note(
        self, data: DeliveryNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Create one delivery note and commit it."""
        row = self.stage_note(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_note(
        self, data: DeliveryNoteCreate, *, firm_id: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Create one delivery note without committing it.

        See `SalesOrderService.stage_order` for why the split exists: a caller
        composing the chain needs every step of it in one transaction.
        """
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
            values={"vehicle": data.vehicle, "driver": data.driver},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        order = self._sales_order(data.sales_order_id, firm_id=firm_id)
        # A sales order's status, compared against the sales order's own enum.
        # This read `DeliveryNoteStatus` members, which agreed only because
        # both enums spell APPROVED and CLOSED the same -- and would have
        # refused the second delivery against a part-delivered order the
        # moment that status started being written.
        if order.status not in {
            SalesOrderStatus.APPROVED.value,
            SalesOrderStatus.PARTIALLY_DELIVERED.value,
            SalesOrderStatus.DELIVERED.value,
            SalesOrderStatus.CLOSED.value,
        }:
            raise ValidationError(
                "Delivery notes can be created only from approved sales orders."
            )
        self._validate_scope_references(
            firm_id=firm_id,
            customer_id=order.customer_id,
            branch_id=order.branch_id,
            warehouse_id=order.warehouse_id,
            salesman_id=order.salesman_id,
            territory_id=order.territory_id,
            route_id=order.route_id,
        )
        note_number = (
            data.delivery_note_number
            if data.delivery_note_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.delivery_date, firm_id
                ),
                branch_code=self._scope_code(order.branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.delivery_date,
                actor_id=actor_id,
            )
        )
        row = DeliveryNote(
            firm_id=firm_id,
            sales_order_id=order.id,
            customer_id=order.customer_id,
            branch_id=order.branch_id,
            warehouse_id=order.warehouse_id,
            business_profile_id=order.business_profile_id,
            salesman_id=order.salesman_id,
            route_id=order.route_id,
            territory_id=order.territory_id,
            delivery_note_number=note_number,
            delivery_date=data.delivery_date,
            sales_order_reference=order.order_number,
            vehicle=data.vehicle,
            driver=data.driver,
            remarks=data.remarks,
            allow_over_delivery=data.allow_over_delivery,
            over_delivery_percent=self._q(data.over_delivery_percent),
            status=DeliveryNoteStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        totals = self._replace_lines(
            row,
            lines=data.lines,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            actor_id=actor_id,
        )
        row.total_ordered_quantity = totals["total_ordered_quantity"]
        row.total_previously_delivered_quantity = totals[
            "total_previously_delivered_quantity"
        ]
        row.total_current_delivery_quantity = totals["total_current_delivery_quantity"]
        row.total_free_quantity = totals["total_free_quantity"]
        row.line_discount_total = totals["line_discount_total"]
        row.subtotal = totals["subtotal"]
        row.tax_total = totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_id
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_id)
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
            action="delivery_note.created",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "delivery_note_number": row.delivery_note_number,
                "status": row.status,
            },
        )
        self._flush_or_conflict("Delivery note number already exists in this firm.")
        return row

    def update_note(
        self,
        note_id: UUID,
        data: DeliveryNoteCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> DeliveryNote:
        """Replace one delivery note."""
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
            values={"vehicle": data.vehicle, "driver": data.driver},
        )
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status != DeliveryNoteStatus.DRAFT.value:
            raise ValidationError("Only draft delivery notes can be updated.")
        order = self._sales_order(data.sales_order_id, firm_id=firm_scope)
        self._delete_children(note_id)
        row.sales_order_id = order.id
        row.customer_id = order.customer_id
        row.branch_id = order.branch_id
        row.warehouse_id = order.warehouse_id
        row.business_profile_id = order.business_profile_id
        row.salesman_id = order.salesman_id
        row.route_id = order.route_id
        row.territory_id = order.territory_id
        row.delivery_date = data.delivery_date
        row.sales_order_reference = order.order_number
        row.vehicle = data.vehicle
        row.driver = data.driver
        row.remarks = data.remarks
        row.allow_over_delivery = data.allow_over_delivery
        row.over_delivery_percent = self._q(data.over_delivery_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        totals = self._replace_lines(
            row,
            lines=data.lines,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            actor_id=actor_id,
        )
        row.total_ordered_quantity = totals["total_ordered_quantity"]
        row.total_previously_delivered_quantity = totals[
            "total_previously_delivered_quantity"
        ]
        row.total_current_delivery_quantity = totals["total_current_delivery_quantity"]
        row.total_free_quantity = totals["total_free_quantity"]
        row.line_discount_total = totals["line_discount_total"]
        row.subtotal = totals["subtotal"]
        row.tax_total = totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_scope
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="UPDATED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="delivery_note.updated",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "delivery_note_number": row.delivery_note_number,
                "status": row.status,
            },
        )
        self._flush_or_conflict("Delivery note number already exists in this firm.")
        self._session.commit()
        return row

    def approve_note(
        self, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Approve one delivery note and commit it."""
        row = self.stage_approval(note_id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_approval(
        self, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Approve one delivery note without committing it."""
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status != DeliveryNoteStatus.DRAFT.value:
            raise ValidationError("Only draft delivery notes can be approved.")
        row.status = DeliveryNoteStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="APPROVED",
            from_state=DeliveryNoteStatus.DRAFT.value,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="delivery_note.approved",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        return row

    def dispatch_note(
        self, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Dispatch one delivery note and commit it."""
        row = self.stage_dispatch(note_id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_dispatch(
        self, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Dispatch one delivery note without committing it.

        This is where stock leaves and cost of goods sold is posted, so it is
        the step a composed chain most needs rolled back with everything else:
        committing here and failing at the invoice is goods gone with nothing
        owed for them.
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status == DeliveryNoteStatus.DISPATCHED.value:
            return row
        if row.status != DeliveryNoteStatus.APPROVED.value:
            raise ValidationError("Only approved delivery notes can be dispatched.")
        self._dispatch_inventory(row=row, actor_id=actor_id)
        row.status = DeliveryNoteStatus.DISPATCHED.value
        row.dispatched_at = utc_now()
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="DISPATCHED",
            from_state=DeliveryNoteStatus.APPROVED.value,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="delivery_note.dispatched",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._resync_order_status(
            self._sales_order(row.sales_order_id, firm_id=firm_scope),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        return row

    def complete_note(
        self, note_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> DeliveryNote:
        """Complete one delivery note."""
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status == DeliveryNoteStatus.COMPLETED.value:
            return row
        if row.status in {
            DeliveryNoteStatus.CANCELLED.value,
            DeliveryNoteStatus.CLOSED.value,
        }:
            raise ValidationError(
                "Cancelled/closed delivery notes cannot be completed."
            )
        before = row.status
        if row.status == DeliveryNoteStatus.APPROVED.value:
            self._dispatch_inventory(row=row, actor_id=actor_id)
            row.dispatched_at = row.dispatched_at or utc_now()
        elif row.status != DeliveryNoteStatus.DISPATCHED.value:
            raise ValidationError(
                "Only approved or dispatched delivery notes can be completed."
            )
        row.status = DeliveryNoteStatus.COMPLETED.value
        row.completed_at = utc_now()
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
            action="delivery_note.completed",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def cancel_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> DeliveryNote:
        """Cancel one delivery note."""
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status in {
            DeliveryNoteStatus.DISPATCHED.value,
            DeliveryNoteStatus.COMPLETED.value,
            DeliveryNoteStatus.CLOSED.value,
            DeliveryNoteStatus.CANCELLED.value,
        }:
            raise ValidationError("This delivery note can no longer be cancelled.")
        before = row.status
        row.status = DeliveryNoteStatus.CANCELLED.value
        row.cancel_reason = reason.strip() if reason else None
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="CANCELLED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=row.cancel_reason,
        )
        record_audit(
            self._session,
            action="delivery_note.cancelled",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def close_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> DeliveryNote:
        """Close one delivery note."""
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status == DeliveryNoteStatus.CLOSED.value:
            return row
        if row.status == DeliveryNoteStatus.DRAFT.value:
            raise ValidationError("Draft delivery notes cannot be closed.")
        before = row.status
        row.status = DeliveryNoteStatus.CLOSED.value
        row.closed_at = utc_now()
        row.close_reason = reason.strip() if reason else None
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="CLOSED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=row.close_reason,
        )
        record_audit(
            self._session,
            action="delivery_note.closed",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def get_note(self, note_id: UUID, *, firm_scope: UUID) -> DeliveryNote:
        """Return one delivery note."""
        row = self._session.scalar(
            select(DeliveryNote).where(
                DeliveryNote.id == note_id,
                DeliveryNote.firm_id == firm_scope,
                DeliveryNote.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Delivery note not found.")
        return row

    def note_response(self, row: DeliveryNote) -> DeliveryNoteResponse:
        """Render one delivery note row as its API contract."""
        lines = list(
            self._session.scalars(
                select(DeliveryNoteLine)
                .where(DeliveryNoteLine.delivery_note_id == row.id)
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(DeliveryNoteAttachment).where(
                    DeliveryNoteAttachment.delivery_note_id == row.id
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(DeliveryNoteNote).where(
                    DeliveryNoteNote.delivery_note_id == row.id
                )
            ).all()
        )
        return DeliveryNoteResponse(
            id=row.id,
            version=row.version,
            firm_id=row.firm_id,
            sales_order_id=row.sales_order_id,
            customer_id=row.customer_id,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            salesman_id=row.salesman_id,
            route_id=row.route_id,
            territory_id=row.territory_id,
            delivery_note_number=row.delivery_note_number,
            delivery_date=row.delivery_date,
            sales_order_reference=row.sales_order_reference,
            vehicle=row.vehicle,
            driver=row.driver,
            remarks=row.remarks,
            allow_over_delivery=row.allow_over_delivery,
            over_delivery_percent=row.over_delivery_percent,
            status=DeliveryNoteStatus(row.status),
            total_ordered_quantity=row.total_ordered_quantity,
            total_previously_delivered_quantity=row.total_previously_delivered_quantity,
            total_current_delivery_quantity=row.total_current_delivery_quantity,
            total_free_quantity=row.total_free_quantity,
            customer_discount_percent=row.customer_discount_percent,
            bill_discount_percent=row.bill_discount_percent,
            bill_discount_amount=row.bill_discount_amount,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            approved_at=row.approved_at,
            dispatched_at=row.dispatched_at,
            completed_at=row.completed_at,
            closed_at=row.closed_at,
            cancel_reason=row.cancel_reason,
            close_reason=row.close_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            lines=[self._line_response(item) for item in lines],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            duplicate_warning=self._duplicate_warning(row),
        )

    def timeline(
        self, *, note_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return the lifecycle timeline for one delivery note."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=note_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def register_report(self, *, firm_scope: UUID) -> list[DeliveryNoteRegisterRecord]:
        """Return the register report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(DeliveryNote)
                .where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                )
                .order_by(
                    DeliveryNote.delivery_date.desc(), DeliveryNote.created_at.desc()
                )
            ).all()
        )
        return [
            DeliveryNoteRegisterRecord(
                delivery_note_id=row.id,
                delivery_note_number=row.delivery_note_number,
                delivery_date=row.delivery_date,
                sales_order_id=row.sales_order_id,
                sales_order_number=row.sales_order_reference,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                status=DeliveryNoteStatus(row.status),
                grand_total=row.grand_total,
            )
            for row in rows
        ]

    def pending_notes(self, *, firm_scope: UUID) -> list[DeliveryNote]:
        """List notes still open: draft or approved, not yet dispatched."""
        return list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    DeliveryNote.status.in_(
                        [
                            DeliveryNoteStatus.DRAFT.value,
                            DeliveryNoteStatus.APPROVED.value,
                        ]
                    ),
                )
            ).all()
        )

    def partially_delivered_orders(
        self, *, firm_scope: UUID
    ) -> list[DeliveryNoteOrderProgressRecord]:
        """Show how much of each sales order has actually been delivered."""
        order_rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                    SalesOrder.status != SalesOrderStatus.CANCELLED.value,
                )
            ).all()
        )
        result: list[DeliveryNoteOrderProgressRecord] = []
        for order in order_rows:
            lines = list(
                self._session.scalars(
                    select(SalesOrderLine).where(
                        SalesOrderLine.sales_order_id == order.id
                    )
                ).all()
            )
            ordered = self._q(sum((line.reservable_quantity for line in lines), ZERO))
            delivered = self._q(
                sum(
                    (
                        self._already_delivered_quantity(
                            firm_id=firm_scope,
                            sales_order_line_id=line.id,
                            include_statuses={
                                DeliveryNoteStatus.APPROVED.value,
                                DeliveryNoteStatus.DISPATCHED.value,
                                DeliveryNoteStatus.COMPLETED.value,
                                DeliveryNoteStatus.CLOSED.value,
                            },
                        )
                        for line in lines
                    ),
                    ZERO,
                )
            )
            pending = self._q(ordered - delivered)
            result.append(
                DeliveryNoteOrderProgressRecord(
                    sales_order_id=order.id,
                    sales_order_number=order.order_number,
                    ordered_quantity=ordered,
                    delivered_quantity=delivered,
                    pending_quantity=pending if pending > ZERO else ZERO,
                    status=(
                        "COMPLETED"
                        if pending <= ZERO
                        else ("PARTIAL" if delivered > ZERO else "PENDING")
                    ),
                )
            )
        return result

    def by_route_report(
        self, *, firm_scope: UUID
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Return the by route report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
                )
            ).all()
        )
        return self._aggregate_dimension(rows=rows, attr="route_id", dimension="route")

    def by_salesman_report(
        self, *, firm_scope: UUID
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Return the by salesman report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
                )
            ).all()
        )
        return self._aggregate_dimension(
            rows=rows, attr="salesman_id", dimension="salesman"
        )

    def by_warehouse_report(
        self, *, firm_scope: UUID
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Return the by warehouse report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
                )
            ).all()
        )
        return self._aggregate_dimension(
            rows=rows, attr="warehouse_id", dimension="warehouse"
        )

    def export_notes_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        """Export matching delivery notes as CSV."""
        rows, _ = self.list_notes(
            firm_scope=firm_scope,
            filters=DeliveryNoteListFilters(),
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
                "delivery_note_number",
                "delivery_date",
                "sales_order_reference",
                "customer_id",
                "branch_id",
                "warehouse_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.delivery_note_number,
                    row.delivery_date.isoformat(),
                    row.sales_order_reference,
                    str(row.customer_id),
                    str(row.branch_id),
                    str(row.warehouse_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_notes(
        self, data: DeliveryNoteImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[DeliveryNote]:
        """Import a validated batch of delivery notes atomically.

        It looped over a committing method while claiming to be atomic, so a
        batch that failed part-way left the records before it written and the
        corrected file unusable. See `SalesOrderService.import_orders`.
        """
        rows = [
            self.stage_note(record, firm_id=firm_scope, actor_id=actor_id)
            for record in data.records
        ]
        self._session.commit()
        return rows

    def _line_discount(
        self, item: DeliveryNoteLineWrite, *, source: SalesOrderLine | None
    ) -> LineDiscount:
        """Return the discount one dispatched line ships under.

        What the line itself says wins. Where it says nothing, the discount is
        **inherited from the order line being shipped** rather than re-read
        from the customer and the price lists -- the same rule the invoice
        already follows, and for the same reason: a price agreed on an order in
        March is not rewritten by an edit to the customer master in August.

        This module did re-read it, and lost two things by it. A standing rate
        changed after the order silently repriced goods already agreed. And
        every promotion vanished: an offer is applied when the order is priced,
        the note threw the result away, and the invoice then inherited the
        note -- so a customer promised a promoted price was billed the
        undiscounted one.

        A percentage inherits cleanly across a part shipment, because a rate
        does not care about quantity. An absolute amount is pro-rated by the
        share leaving the warehouse, since a whole-line figure copied onto half
        a line would discount more than was ever agreed.

        The price list and the customer's standing rate are deliberately not
        consulted here. The order already resolved both when it was priced, so
        a line that came out at nothing came out at nothing on purpose.
        """
        gross = self._q(
            self._q(item.current_delivery_quantity) * self._q(item.unit_price)
        )
        percent = item.discount_percent
        amount = item.discount_amount
        if percent is None and amount is None and source is not None:
            ordered = self._q(source.quantity)
            if source.discount_percent:
                percent = source.discount_percent
            elif source.discount_amount and ordered > ZERO:
                amount = self._q(
                    self._q(source.discount_amount)
                    * self._q(item.current_delivery_quantity)
                    / ordered
                )
        return resolve_line_discount(gross=gross, percent=percent, amount=amount)

    def _customer_discount(self, customer_id: UUID) -> Decimal | None:
        """Return the customer's standing discount, if they have one.

        None rather than zero when there is no customer or no arrangement, so
        the shared rule can tell "nothing agreed" from "agreed nothing".
        """
        customer = self._session.get(Customer, customer_id)
        if customer is None or customer.default_discount_percent <= ZERO:
            return None
        return self._q(customer.default_discount_percent)

    def _bill_discount_shares(
        self,
        row: DeliveryNote,
        *,
        percent: Decimal | None,
        amount: Decimal | None,
        taxables: list[Decimal],
    ) -> list[Decimal]:
        """Resolve the document's own discount and split it across the lines.

        Taken off what the lines already discounted to, never off the gross --
        off the gross, the two discounts are each computed as though the other
        had not happened, and the pair takes off more than either was agreed to.

        What is written back onto the header is the amount actually applied and
        the rate it represents, rather than whatever the caller sent.
        """
        resolved = resolve_bill_discount(
            taxable=self._q(sum(taxables, ZERO)),
            percent=percent,
            amount=amount,
        )
        row.bill_discount_percent = resolved.percent
        row.bill_discount_amount = resolved.amount
        return apportion(resolved.amount, taxables)

    def _replace_lines(
        self,
        row: DeliveryNote,
        *,
        lines: list[DeliveryNoteLineWrite],
        bill_percent: Decimal | None,
        bill_amount: Decimal | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        # Lines are matched on their line number and updated in place;
        # re-inserting them minted a new UUID per line on every save, and
        # downstream documents reference those ids with no foreign key.
        existing = {
            existing_line.line_number: existing_line
            for existing_line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == row.id
                )
            ).all()
        }
        seen: set[int] = set()
        source_lines = {
            item.id: item
            for item in self._session.scalars(
                select(SalesOrderLine).where(
                    SalesOrderLine.sales_order_id == row.sales_order_id
                )
            ).all()
        }
        if not source_lines:
            raise ValidationError("Sales order does not contain any lines.")
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        # Read once for the whole document rather than per line. A line that
        # says nothing about a discount gets this; one that says anything at
        # all, including zero, does not.
        customer_discount = self._customer_discount(row.customer_id)
        # Snapshot on the header: the lines below may each override it, so the
        # document keeps what the standing rate was on the day it was raised.
        row.customer_discount_percent = customer_discount or ZERO
        # Priced before the loop below writes anything, because a discount on
        # the whole document has to be split across the lines *before* tax is
        # asked for. Tax is charged per line, so a document-level deduction
        # that never reaches a taxable value reduces no tax -- which is what
        # `header_discount_amount` does on a purchase order, and the reason
        # that shape is not copied here. Nothing in this pass touches the
        # database, so every validation below still runs in its own order.
        priced = [
            self._line_discount(item, source=source_lines.get(item.sales_order_line_id))
            for item in lines
        ]
        shares = self._bill_discount_shares(
            row,
            percent=bill_percent,
            amount=bill_amount,
            taxables=[
                self._q(
                    self._q(item.current_delivery_quantity) * self._q(item.unit_price)
                    - line.amount
                )
                for item, line in zip(lines, priced, strict=True)
            ],
        )

        for index, item in enumerate(lines):
            bill_share = shares[index]
            source_line = source_lines.get(item.sales_order_line_id)
            if source_line is None:
                raise ValidationError(
                    "Delivery line must reference a sales order line."
                )
            warehouse_id = item.warehouse_id or source_line.warehouse_id
            if warehouse_id is None:
                raise ValidationError("Warehouse is required for delivery lines.")
            self._validate_storage_scope(
                firm_id=row.firm_id,
                warehouse_id=warehouse_id,
                storage_node_id=item.storage_node_id,
            )
            current_qty = self._q(item.current_delivery_quantity)
            free_qty = self._q(item.free_quantity)
            conversion = self._conversion(
                quantity=self._q(current_qty + free_qty),
                sales_uom_id=item.sales_uom_id or source_line.sales_uom_id,
                inventory_uom_id=item.inventory_uom_id or source_line.inventory_uom_id,
                product_id=source_line.product_id,
                delivery_date=row.delivery_date,
                firm_id=row.firm_id,
            )
            delivered_qty = self._q(conversion["converted"])
            ordered_qty = self._q(source_line.reservable_quantity)
            previous_delivered = self._already_delivered_quantity(
                firm_id=row.firm_id,
                sales_order_line_id=source_line.id,
                exclude_delivery_note_id=row.id,
                include_statuses={
                    DeliveryNoteStatus.APPROVED.value,
                    DeliveryNoteStatus.DISPATCHED.value,
                    DeliveryNoteStatus.COMPLETED.value,
                    DeliveryNoteStatus.CLOSED.value,
                },
            )
            allowed_qty = ordered_qty
            if row.allow_over_delivery:
                allowed_qty = self._q(
                    ordered_qty
                    + (
                        ordered_qty
                        * self._q(row.over_delivery_percent)
                        / Decimal("100")
                    )
                )
            if previous_delivered + delivered_qty > allowed_qty:
                raise ValidationError(
                    "Delivery quantity exceeds allowed quantity for the order line."
                )
            remaining_qty = self._q(ordered_qty - previous_delivered - delivered_qty)
            short_qty = self._q(remaining_qty if remaining_qty > ZERO else ZERO)
            gross = self._q(current_qty * self._q(item.unit_price))
            line_discount = priced[index]
            discount = line_discount.amount
            taxable = self._q(gross - discount - bill_share)
            tax = self._tax_amount(
                delivery_date=row.delivery_date,
                firm_id=row.firm_id,
                actor_id=actor_id,
                business_profile_id=row.business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=warehouse_id,
                product_id=source_line.product_id,
                tax_profile_id=item.tax_profile_id,
                invoice_value=taxable,
            )
            net = self._q(taxable + tax)
            line = DeliveryNoteLine(
                delivery_note_id=row.id,
                firm_id=row.firm_id,
                sales_order_line_id=source_line.id,
                line_number=item.line_number,
                product_id=source_line.product_id,
                description=item.description or source_line.description,
                ordered_quantity=ordered_qty,
                reserved_quantity=self._q(source_line.reserved_quantity),
                previously_delivered_quantity=previous_delivered,
                current_delivery_quantity=current_qty,
                free_quantity=free_qty,
                delivered_quantity=delivered_qty,
                remaining_quantity=remaining_qty if remaining_qty > ZERO else ZERO,
                damaged_quantity=self._q(item.damaged_quantity),
                short_shipment_quantity=short_qty,
                sales_uom_id=item.sales_uom_id or source_line.sales_uom_id,
                inventory_uom_id=item.inventory_uom_id or source_line.inventory_uom_id,
                packaging_type_id=item.packaging_type_id
                or source_line.packaging_type_id,
                conversion_factor=self._q(conversion["factor"]),
                conversion_version=conversion["version"],
                unit_price=self._q(item.unit_price),
                discount_percent=line_discount.percent,
                discount_amount=discount,
                bill_discount_amount=bill_share,
                gross_amount=gross,
                tax_profile_id=item.tax_profile_id,
                tax_amount=tax,
                net_amount=net,
                warehouse_id=warehouse_id,
                storage_node_id=item.storage_node_id,
                batch_number=item.batch_number,
                serial_numbers=item.serial_numbers,
                manufacturing_date=item.manufacturing_date,
                expiry_date=item.expiry_date,
                remarks=item.remarks,
                created_by=actor_id,
                updated_by=actor_id,
            )
            persisted = existing.get(item.line_number)
            if persisted is None:
                self._session.add(line)
            else:
                self._apply_line_values(persisted, line, actor_id=actor_id, preserve=())
            seen.add(item.line_number)
            totals["total_ordered_quantity"] += ordered_qty
            totals["total_previously_delivered_quantity"] += previous_delivered
            totals["total_current_delivery_quantity"] += delivered_qty
            totals["total_free_quantity"] += free_qty
            totals["line_discount_total"] += discount
            totals["subtotal"] += taxable
            totals["tax_total"] += tax
        for line_number, obsolete in existing.items():
            if line_number not in seen:
                self._session.delete(obsolete)
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: DeliveryNote,
        attachments: list[DeliveryNoteAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(DeliveryNoteAttachment).filter(
            DeliveryNoteAttachment.delivery_note_id == row.id
        ).delete(synchronize_session=False)
        for item in attachments:
            self._session.add(
                DeliveryNoteAttachment(
                    delivery_note_id=row.id,
                    firm_id=firm_id,
                    file_name=item.file_name,
                    mime_type=item.mime_type,
                    file_path=item.file_path,
                    attachment_kind=item.attachment_kind,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_notes(
        self,
        row: DeliveryNote,
        notes: list[DeliveryNoteNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(DeliveryNoteNote).filter(
            DeliveryNoteNote.delivery_note_id == row.id
        ).delete(synchronize_session=False)
        for item in notes:
            self._session.add(
                DeliveryNoteNote(
                    delivery_note_id=row.id,
                    firm_id=firm_id,
                    note_type=item.note_type.strip().upper(),
                    note=item.note.strip(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _dispatch_inventory(self, *, row: DeliveryNote, actor_id: UUID) -> None:
        lines = list(
            self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == row.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
        )
        if not lines:
            raise ValidationError(
                "Delivery note must contain at least one line before dispatch."
            )
        issued_cost = ZERO
        for line in lines:
            if line.inventory_transaction_id is not None:
                continue
            if line.warehouse_id is None:
                raise ValidationError(
                    "Warehouse is required on all lines before dispatch."
                )
            if line.delivered_quantity <= ZERO:
                continue
            source_line = self._session.scalar(
                select(SalesOrderLine).where(
                    SalesOrderLine.id == line.sales_order_line_id
                )
            )
            if source_line is None:
                raise ValidationError("Sales order line not found for dispatch.")
            available, _ = self._stock_snapshot(
                firm_id=row.firm_id,
                branch_id=row.branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
            )
            if available < line.delivered_quantity:
                raise ValidationError("Insufficient available stock for dispatch line.")
            release_qty = self._q(
                min(source_line.reserved_quantity, line.delivered_quantity)
            )
            if not row.allow_over_delivery and release_qty < line.delivered_quantity:
                raise ValidationError(
                    "Reservation is insufficient for dispatch quantity."
                )
            if release_qty > ZERO:
                # Let the batches go in the order the goods will ship in, so
                # the batch freed here is the one the allocation below draws
                # from -- both rank by earliest expiry.
                release_split = self._inventory.allocate_for_release(
                    firm_scope=row.firm_id,
                    branch_id=row.branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    quantity=release_qty,
                )
                entered_release = self._q(
                    line.current_delivery_quantity + line.free_quantity
                )
                released = None
                for batch_id, freed in release_split:
                    posted = self._inventory.release_sales_order_reservation(
                        firm_scope=row.firm_id,
                        actor_id=actor_id,
                        branch_id=row.branch_id,
                        warehouse_id=line.warehouse_id,
                        storage_node_id=line.storage_node_id,
                        product_id=line.product_id,
                        reference_number=row.sales_order_reference,
                        transaction_date=row.delivery_date,
                        release_quantity=freed,
                        entered_quantity=(
                            entered_release
                            if len(release_split) == 1
                            else self._q(entered_release * (freed / release_qty))
                        ),
                        entered_uom_id=line.sales_uom_id,
                        conversion_version=line.conversion_version,
                        remarks=f"delivery_note release line {line.line_number}",
                        batch_id=batch_id,
                    )
                    if released is None:
                        released = posted
                source_line.reserved_quantity = self._q(
                    source_line.reserved_quantity - release_qty
                )
                if released is not None:
                    line.released_reservation_transaction_id = released.id
            # A product held in one bay can be several stock rows now, one per
            # batch, so a line may have to come out of more than one of them --
            # earliest expiry first. One movement is posted per batch drawn
            # from; the line records the first, and the movements carry the
            # whole split.
            allocation = self._inventory.allocate_for_dispatch(
                firm_scope=row.firm_id,
                branch_id=row.branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                quantity=line.delivered_quantity,
            )
            entered_total = self._q(line.current_delivery_quantity + line.free_quantity)
            dispatched = None
            for batch_id, allocated in allocation:
                # The entered quantity is what the customer was billed in, so
                # it is apportioned with the split rather than repeated whole.
                share = (
                    entered_total
                    if len(allocation) == 1
                    else self._q(
                        entered_total
                        * (allocated / Decimal(str(line.delivered_quantity)))
                    )
                )
                posted = self._inventory.record_delivery_note_dispatch(
                    firm_scope=row.firm_id,
                    actor_id=actor_id,
                    branch_id=row.branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    reference_number=row.delivery_note_number,
                    transaction_date=row.delivery_date,
                    dispatch_quantity=allocated,
                    entered_quantity=share,
                    entered_uom_id=line.sales_uom_id,
                    conversion_version=line.conversion_version,
                    remarks=line.remarks or row.remarks,
                    batch_id=batch_id,
                )
                issued_cost += self._issue_cost(posted.id)
                if dispatched is None:
                    dispatched = posted
                    line.batch_id = batch_id
            if dispatched is None:
                raise ValidationError("Insufficient available stock for dispatch line.")
            line.inventory_transaction_id = dispatched.id
            line.updated_by = actor_id
        self._session.flush()
        # Goods leave stock here, not when the invoice is raised, so this is
        # where cost of goods sold belongs. Posting fails the dispatch for the
        # same reason it fails an invoice approval: stock that has moved with no
        # accounting entry behind it is the gap this closes.
        DocumentPostingService(self._session).post_goods_issue(
            firm_id=row.firm_id,
            document_id=row.id,
            document_number=row.delivery_note_number,
            issue_date=row.delivery_date,
            cost_amount=issued_cost,
            source_module="delivery_note",
            actor_id=actor_id,
        )

    def _issue_cost(self, transaction_id: UUID) -> Decimal:
        """Return what the stock ledger released for one movement.

        The moving average decides this, not the selling price on the invoice.
        """
        total = self._session.scalar(
            select(func.sum(StockLedgerEntry.total_cost)).where(
                StockLedgerEntry.transaction_id == transaction_id
            )
        )
        return self._q(total)

    def _delete_children(self, note_id: UUID) -> None:
        self._session.query(DeliveryNoteAttachment).filter(
            DeliveryNoteAttachment.delivery_note_id == note_id
        ).delete(synchronize_session=False)
        self._session.query(DeliveryNoteNote).filter(
            DeliveryNoteNote.delivery_note_id == note_id
        ).delete(synchronize_session=False)

    def _tax_amount(
        self,
        *,
        delivery_date: date,
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
                    product, delivery_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, delivery_date, firm_scope=firm_id
            )
        request = TaxRuleSimulationRequest(
            transaction_type="DELIVERY_NOTE",
            transaction_date=delivery_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "delivery_note"},
        )
        response = self._tax.simulate(request, firm_scope=firm_id, actor_id=actor_id)
        return self._q(response.total_tax_amount)

    def _conversion(
        self,
        *,
        quantity: Decimal,
        sales_uom_id: UUID | None,
        inventory_uom_id: UUID | None,
        product_id: UUID,
        delivery_date: date,
        firm_id: UUID,
    ) -> dict[str, Decimal | int | None]:
        if (
            sales_uom_id is None
            or inventory_uom_id is None
            or sales_uom_id == inventory_uom_id
        ):
            return {
                "factor": Decimal("1"),
                "converted": self._q(quantity),
                "version": None,
            }
        response = self._uom.convert_quantity(
            ConversionRequest(
                quantity=quantity,
                from_uom_id=sales_uom_id,
                to_uom_id=inventory_uom_id,
                product_id=product_id,
                conversion_date=delivery_date,
            ),
            firm_scope=firm_id,
        )
        return {
            "factor": response.conversion_factor,
            "converted": self._q(response.converted_quantity),
            "version": response.version_number,
        }

    def _stock_snapshot(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        product_id: UUID,
    ) -> tuple[Decimal, Decimal]:
        """Return what this product has available and reserved in one bay.

        A sum, not a row. Stock has been held per batch since the grain
        changed, so a product in one bay is as many rows as it has batches --
        and this read one of them with ``scalar()``, which does not complain
        about the others, it just returns the first. The gate below then
        compared a single batch's quantity against the whole line: sixty
        strips in March and forty in June refused a line of eighty, while
        ``allocate_for_dispatch`` -- which runs on the next line and splits
        across batches by design -- would have filled it without trouble.

        Untracked stock is one of the rows summed here, so a product nobody
        tracks behaves exactly as it did.
        """
        row = self._session.execute(
            select(
                func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0),
            ).where(
                InventoryRecord.firm_id == firm_id,
                InventoryRecord.branch_id == branch_id,
                InventoryRecord.warehouse_id == warehouse_id,
                InventoryRecord.storage_node_id == storage_node_id,
                InventoryRecord.product_id == product_id,
                InventoryRecord.is_deleted.is_(False),
            )
        ).first()
        if row is None:
            return ZERO, ZERO
        return self._q(row[0]), self._q(row[1])

    def _validate_storage_scope(
        self, *, firm_id: UUID, warehouse_id: UUID, storage_node_id: UUID | None
    ) -> None:
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
                "Inactive storage areas cannot be used for delivery notes."
            )

    def _validate_scope_references(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        salesman_id: UUID | None,
        territory_id: UUID | None,
        route_id: UUID | None,
    ) -> tuple[Customer, Branch, Warehouse]:
        customer = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is None:
            raise ValidationError("Customer not found in this firm.")
        branch = self._session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.firm_id == firm_id,
                Branch.is_deleted.is_(False),
            )
        )
        if branch is None:
            raise ValidationError("Branch not found in this firm.")
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.branch_id == branch_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Warehouse not found in this branch.")
        if salesman_id is not None:
            # Through `FirmMetadataReader`, not the request session: `users`
            # and `user_firms` live only in the platform schema, so selecting
            # `User` here raised `relation "<firm schema>.users" does not
            # exist` for every firm outside the platform store -- the sixth
            # time this trap has been sprung. It was invisible because nothing
            # sent a `salesman_id` until the desktop grew a picker for one.
            #
            # It also asks the right question. The old check accepted any user
            # that existed anywhere, so one firm could tag another firm's
            # people on its own documents; membership of *this* firm is what
            # makes somebody a salesman of it.
            members = FirmMetadataReader(self._session).active_member_count(
                firm_id, [salesman_id]
            )
            if members != 1:
                raise ValidationError("Salesman is not an active member of this firm.")
        if territory_id is not None:
            territory = self._session.scalar(
                select(SalesTerritoryNode).where(
                    SalesTerritoryNode.id == territory_id,
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if territory is None:
                raise ValidationError("Territory not found in this firm.")
        if route_id is not None:
            route = self._session.scalar(
                select(TerritoryRouteProfile).where(
                    TerritoryRouteProfile.id == route_id,
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
            if route is None:
                raise ValidationError("Route profile not found.")
        return customer, branch, warehouse

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document: DeliveryNote,
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
                source_module_code="DELIVERY_NOTE",
                document_number=document.delivery_note_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "delivery_note_number": document.delivery_note_number,
                    "grand_total": str(document.grand_total),
                },
                snapshot_json={
                    "status": document.status,
                    "customer_id": str(document.customer_id),
                    "branch_id": str(document.branch_id),
                },
                actor_id=actor_id,
            ),
            actor_id=actor_id,
        )

    def _sales_order(self, sales_order_id: UUID, *, firm_id: UUID) -> SalesOrder:
        row = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == sales_order_id,
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales order not found.")
        return row

    def _resync_order_status(
        self, order: SalesOrder, *, firm_id: UUID, actor_id: UUID
    ) -> None:
        """Move the sales order to match what has actually been dispatched.

        Derived rather than incremented: the delivered quantity is summed from
        the notes that have left the warehouse every time. That is how
        `goods_receipt` does it on the purchase side and the reason is the
        same -- an incrementing counter and a reversal are two chances to
        disagree.

        The walk-back branch is deliberate and, today, unreachable: only a
        DRAFT or APPROVED note can be cancelled, and neither has dispatched, so
        neither contributes to the total. `DISPATCHED` is terminal for
        cancellation. Keeping the derivation whole means the day that changes,
        this is already right.

        Only ever moves an order already in the delivering part of its life. A
        DRAFT, CANCELLED or CLOSED order is left exactly where it is:
        delivering against a cancelled order is a different problem, and
        quietly reviving one here would hide it.
        """
        movable = {
            SalesOrderStatus.APPROVED.value,
            SalesOrderStatus.PARTIALLY_DELIVERED.value,
            SalesOrderStatus.DELIVERED.value,
        }
        if order.status not in movable:
            return

        lines = self._session.scalars(
            select(SalesOrderLine).where(
                SalesOrderLine.sales_order_id == order.id,
                SalesOrderLine.is_deleted.is_(False),
            )
        ).all()
        if not lines:
            return

        total = ZERO
        complete = True
        for line in lines:
            sent = self._already_delivered_quantity(
                firm_id=firm_id, sales_order_line_id=line.id
            )
            total += sent
            if sent < self._q(line.reservable_quantity):
                complete = False

        if complete:
            target = SalesOrderStatus.DELIVERED.value
        elif total > ZERO:
            target = SalesOrderStatus.PARTIALLY_DELIVERED.value
        else:
            # Every note against it has been cancelled.
            target = SalesOrderStatus.APPROVED.value
        if target == order.status:
            return

        before = order.status
        order.status = target
        order.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_order.delivered_status_changed",
            entity_type="sales_order",
            entity_id=order.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"status": before},
            after_data={"status": target},
        )

    def _salesman_names(self, ids: set[UUID]) -> dict[UUID, str]:
        """Name the salesmen, reading the store that holds `users`.

        `users` lives only in the platform schema, so a tenant session cannot
        see it: on PostgreSQL this raised `UndefinedTable` and the report
        answered 503 -- but only once a document carried a salesman, which no
        seeded document did, so it sat latent. Fifth occurrence of the trap.

        SQLite keeps every table in one schema, so the unit suite reads it on
        the request session and could never have caught this.
        """
        if not ids:
            return {}
        statement = select(User.id, User.full_name).where(User.id.in_(ids))
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            rows = list(self._session.execute(statement).all())
        else:
            with platform_reader() as reader:
                rows = list(reader.execute(statement).all())
        return {row[0]: row[1] for row in rows}

    def _already_delivered_quantity(
        self,
        *,
        firm_id: UUID,
        sales_order_line_id: UUID,
        exclude_delivery_note_id: UUID | None = None,
        include_statuses: set[str] | None = None,
    ) -> Decimal:
        statuses = include_statuses or {
            DeliveryNoteStatus.DISPATCHED.value,
            DeliveryNoteStatus.COMPLETED.value,
            DeliveryNoteStatus.CLOSED.value,
        }
        statement = (
            select(func.coalesce(func.sum(DeliveryNoteLine.delivered_quantity), 0))
            .select_from(DeliveryNoteLine)
            .join(DeliveryNote, DeliveryNote.id == DeliveryNoteLine.delivery_note_id)
            .where(
                DeliveryNoteLine.firm_id == firm_id,
                DeliveryNoteLine.sales_order_line_id == sales_order_line_id,
                DeliveryNoteLine.is_deleted.is_(False),
                DeliveryNote.is_deleted.is_(False),
                DeliveryNote.status.in_(list(statuses)),
            )
        )
        if exclude_delivery_note_id is not None:
            statement = statement.where(DeliveryNote.id != exclude_delivery_note_id)
        return self._q(self._session.scalar(statement) or ZERO)

    def _aggregate_dimension(
        self, *, rows: list[DeliveryNote], attr: str, dimension: str
    ) -> list[DeliveryNoteByDimensionRecord]:
        quantities: dict[UUID | None, Decimal] = defaultdict(lambda: ZERO)
        values: dict[UUID | None, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID | None, int] = defaultdict(int)
        labels: dict[UUID | None, str] = {None: "Unassigned"}
        for row in rows:
            key = getattr(row, attr)
            counts[key] += 1
            values[key] += row.grand_total
            delivered = self._q(
                sum(
                    (
                        line.delivered_quantity
                        for line in self._session.scalars(
                            select(DeliveryNoteLine).where(
                                DeliveryNoteLine.delivery_note_id == row.id
                            )
                        ).all()
                    ),
                    ZERO,
                )
            )
            quantities[key] += delivered
            if key not in labels:
                if dimension == "route":
                    # A route profile has no name of its own -- it is a
                    # one-to-one extension of a territory, and the territory
                    # carries the name. Reading ``profile.name`` raised
                    # AttributeError for every firm that ran this report with a
                    # route on any note.
                    route_name = self._session.scalar(
                        select(SalesTerritoryNode.name)
                        .join(
                            TerritoryRouteProfile,
                            TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                        )
                        .where(TerritoryRouteProfile.id == key)
                    )
                    labels[key] = route_name or str(key)
                elif dimension == "salesman":
                    labels[key] = self._salesman_names({key}).get(key, str(key))
                else:
                    warehouse = self._session.scalar(
                        select(Warehouse).where(Warehouse.id == key)
                    )
                    labels[key] = warehouse.name if warehouse is not None else str(key)
        return [
            DeliveryNoteByDimensionRecord(
                dimension_id=key,
                dimension_name=labels.get(key, str(key)),
                note_count=counts[key],
                delivered_quantity=self._q(quantities[key]),
                total_value=self._q(values[key]),
            )
            for key in sorted(
                counts.keys(), key=lambda item: labels.get(item, str(item))
            )
        ]

    def _duplicate_warning(self, row: DeliveryNote) -> str | None:
        duplicate = self._session.scalar(
            select(DeliveryNote.id).where(
                DeliveryNote.firm_id == row.firm_id,
                DeliveryNote.id != row.id,
                DeliveryNote.sales_order_id == row.sales_order_id,
                DeliveryNote.delivery_date == row.delivery_date,
                DeliveryNote.vehicle == row.vehicle,
                DeliveryNote.is_deleted.is_(False),
                DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
            )
        )
        if duplicate is None:
            return None
        return (
            "Potential duplicate dispatch detected for this sales order/date/vehicle."
        )

    def _attachment_response(
        self, row: DeliveryNoteAttachment
    ) -> DeliveryNoteAttachmentResponse:
        return DeliveryNoteAttachmentResponse.model_validate(row)

    def _note_response(self, row: DeliveryNoteNote) -> DeliveryNoteNoteResponse:
        return DeliveryNoteNoteResponse.model_validate(row)

    def _line_response(self, row: DeliveryNoteLine) -> DeliveryNoteLineResponse:
        return DeliveryNoteLineResponse.model_validate(row)
