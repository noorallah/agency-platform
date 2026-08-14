"""Sales order backend lifecycle, reservation, and reporting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
from app.customers.services import CreditAssessment, CreditControlService
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
from app.identity.models import User
from app.inventory.models import InventoryRecord
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales_order.models import (
    SalesOrder,
    SalesOrderAttachment,
    SalesOrderLine,
    SalesOrderNote,
)
from app.sales_order.schemas import (
    SalesOrderAttachmentResponse,
    SalesOrderAttachmentWrite,
    SalesOrderBackOrderRecord,
    SalesOrderByCustomerRecord,
    SalesOrderBySalesmanRecord,
    SalesOrderByTerritoryRecord,
    SalesOrderCreate,
    SalesOrderImportRequest,
    SalesOrderLineResponse,
    SalesOrderLineWrite,
    SalesOrderListFilters,
    SalesOrderNoteResponse,
    SalesOrderNoteWrite,
    SalesOrderPendingRecord,
    SalesOrderRegisterRecord,
    SalesOrderResponse,
    SalesOrderStatus,
    SalesOrderSummary,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")


class SalesOrderService(TransactionalDocumentService):
    """Coordinate sales order lifecycle, totals, and stock reservation."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_ORDER",
        name="Sales Order",
        description="Customer sales order document",
        category="SALES",
        module="sales_order",
        prefix="SO",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("CANCELLED", "Cancelled", 3, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 4, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)
        self._inventory = InventoryService(session)

    def list_orders(
        self,
        *,
        firm_scope: UUID,
        filters: SalesOrderListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SalesOrder], int]:
        """List sales orders for the visible firm scope."""
        columns = {
            "order_number": SalesOrder.order_number,
            "order_date": SalesOrder.order_date,
            "delivery_date": SalesOrder.delivery_date,
            "grand_total": SalesOrder.grand_total,
            "status": SalesOrder.status,
            "created_at": SalesOrder.created_at,
            "updated_at": SalesOrder.updated_at,
        }
        statement = select(SalesOrder).where(SalesOrder.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(SalesOrder)
            .where(SalesOrder.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(SalesOrder.is_deleted.is_(False))
            count = count.where(SalesOrder.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(SalesOrder.customer_id == filters.customer_id)
            count = count.where(SalesOrder.customer_id == filters.customer_id)
        if filters.salesman_id is not None:
            statement = statement.where(SalesOrder.salesman_id == filters.salesman_id)
            count = count.where(SalesOrder.salesman_id == filters.salesman_id)
        if filters.territory_id is not None:
            statement = statement.where(SalesOrder.territory_id == filters.territory_id)
            count = count.where(SalesOrder.territory_id == filters.territory_id)
        if filters.branch_id is not None:
            statement = statement.where(SalesOrder.branch_id == filters.branch_id)
            count = count.where(SalesOrder.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(SalesOrder.warehouse_id == filters.warehouse_id)
            count = count.where(SalesOrder.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(SalesOrder.status == filters.status.value)
            count = count.where(SalesOrder.status == filters.status.value)
        if filters.order_from is not None:
            statement = statement.where(SalesOrder.order_date >= filters.order_from)
            count = count.where(SalesOrder.order_date >= filters.order_from)
        if filters.order_to is not None:
            statement = statement.where(SalesOrder.order_date <= filters.order_to)
            count = count.where(SalesOrder.order_date <= filters.order_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesOrder.order_number.ilike(token),
                SalesOrder.customer_reference.ilike(token),
                SalesOrder.reference_number.ilike(token),
                SalesOrder.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        order_column = columns.get(sort_by, SalesOrder.created_at)
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

    def summary(self, *, firm_scope: UUID) -> SalesOrderSummary:
        """Return aggregate sales order values for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                )
            ).all()
        )
        return SalesOrderSummary(
            total=len(rows),
            draft=sum(1 for row in rows if row.status == SalesOrderStatus.DRAFT.value),
            approved=sum(
                1 for row in rows if row.status == SalesOrderStatus.APPROVED.value
            ),
            cancelled=sum(
                1 for row in rows if row.status == SalesOrderStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in rows if row.status == SalesOrderStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
        )

    def create_order(
        self, data: SalesOrderCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesOrder:
        """Create one sales order."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        customer, _, _ = self._validate_scope_references(
            firm_id=firm_id,
            customer_id=data.customer_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            salesman_id=data.salesman_id,
            territory_id=data.territory_id,
            route_id=data.route_id,
        )
        order_number = (
            data.order_number
            if data.order_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.order_date, firm_id
                ),
                branch_code=self._scope_code(data.branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.order_date,
                actor_id=actor_id,
            )
        )
        row = SalesOrder(
            firm_id=firm_id,
            customer_id=data.customer_id,
            salesman_id=data.salesman_id,
            territory_id=data.territory_id,
            route_id=data.route_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            business_profile_id=data.business_profile_id,
            order_number=order_number,
            order_date=data.order_date,
            delivery_date=data.delivery_date,
            customer_reference=data.customer_reference,
            reference_number=data.reference_number,
            currency_code=data.currency_code,
            exchange_rate=data.exchange_rate,
            remarks=data.remarks,
            credit_limit_snapshot=self._q(customer.credit_limit),
            outstanding_balance_snapshot=self._q(customer.opening_balance),
            status=SalesOrderStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        totals = self._replace_lines(row, lines=data.lines, actor_id=actor_id)
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
            action="sales_order.created",
            entity_type="sales_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"order_number": row.order_number, "status": row.status},
        )
        self._flush_or_conflict("Sales order number already exists in this firm.")
        self._session.commit()
        return row

    def update_order(
        self,
        order_id: UUID,
        data: SalesOrderCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> SalesOrder:
        """Replace one sales order."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status != SalesOrderStatus.DRAFT.value:
            raise ValidationError("Only draft sales orders can be updated.")
        customer, _, _ = self._validate_scope_references(
            firm_id=firm_scope,
            customer_id=data.customer_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            salesman_id=data.salesman_id,
            territory_id=data.territory_id,
            route_id=data.route_id,
        )
        self._delete_children(order_id)
        row.customer_id = data.customer_id
        row.salesman_id = data.salesman_id
        row.territory_id = data.territory_id
        row.route_id = data.route_id
        row.branch_id = data.branch_id
        row.warehouse_id = data.warehouse_id
        row.business_profile_id = data.business_profile_id
        row.order_date = data.order_date
        row.delivery_date = data.delivery_date
        row.customer_reference = data.customer_reference
        row.reference_number = data.reference_number
        row.currency_code = data.currency_code
        row.exchange_rate = data.exchange_rate
        row.remarks = data.remarks
        row.credit_limit_snapshot = self._q(customer.credit_limit)
        row.outstanding_balance_snapshot = self._q(customer.opening_balance)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        totals = self._replace_lines(row, lines=data.lines, actor_id=actor_id)
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
            from_state=SalesOrderStatus.DRAFT.value,
            to_state=SalesOrderStatus.DRAFT.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_order.updated",
            entity_type="sales_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"order_number": row.order_number, "status": row.status},
        )
        self._flush_or_conflict("Sales order number already exists in this firm.")
        self._session.commit()
        return row

    def _assess_credit(
        self, order: SalesOrder, *, firm_scope: UUID
    ) -> CreditAssessment | None:
        """Check the customer against the firm's credit policy."""
        customer = self._session.get(Customer, order.customer_id)
        if customer is None:
            return None
        return CreditControlService(self._session).assert_within_limit(
            customer, additional_amount=self._q(order.grand_total)
        )

    def approve_order(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesOrder:
        """Approve one sales order."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status != SalesOrderStatus.DRAFT.value:
            raise ValidationError("Only draft sales orders can be approved.")
        # Credit is committed here, before any stock moves: approving the order
        # is the promise, invoicing only bills it. Under WARN this records the
        # assessment on the order; under BLOCK it raises before reserving.
        self._credit_assessment = self._assess_credit(row, firm_scope=firm_scope)
        self._reserve_inventory(row, actor_id=actor_id)
        row.status = SalesOrderStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        document_type = self._document_type(firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            document=row,
            action="APPROVED",
            from_state=SalesOrderStatus.DRAFT.value,
            to_state=SalesOrderStatus.APPROVED.value,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_order.approved",
            entity_type="sales_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"order_number": row.order_number, "status": row.status},
        )
        self._session.commit()
        return row

    def cancel_order(
        self,
        order_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesOrder:
        """Cancel one sales order."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status in {
            SalesOrderStatus.CANCELLED.value,
            SalesOrderStatus.CLOSED.value,
        }:
            raise ValidationError("Sales order is already closed for updates.")
        from_status = row.status
        if row.status == SalesOrderStatus.APPROVED.value:
            self._release_inventory(row, actor_id=actor_id)
        row.status = SalesOrderStatus.CANCELLED.value
        row.cancel_reason = reason.strip() if reason else None
        row.updated_by = actor_id
        document_type = self._document_type(firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            document=row,
            action="CANCELLED",
            from_state=from_status,
            to_state=row.status,
            actor_id=actor_id,
            remarks=row.cancel_reason,
        )
        record_audit(
            self._session,
            action="sales_order.cancelled",
            entity_type="sales_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"order_number": row.order_number, "status": row.status},
        )
        self._session.commit()
        return row

    def close_order(
        self,
        order_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesOrder:
        """Close one sales order."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status in {
            SalesOrderStatus.CANCELLED.value,
            SalesOrderStatus.CLOSED.value,
        }:
            raise ValidationError("Sales order is already closed for updates.")
        from_status = row.status
        if row.status == SalesOrderStatus.APPROVED.value:
            self._release_inventory(row, actor_id=actor_id)
        row.status = SalesOrderStatus.CLOSED.value
        row.closed_at = utc_now()
        row.close_reason = reason.strip() if reason else None
        row.updated_by = actor_id
        document_type = self._document_type(firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=document_type,
            document=row,
            action="CLOSED",
            from_state=from_status,
            to_state=row.status,
            actor_id=actor_id,
            remarks=row.close_reason,
        )
        record_audit(
            self._session,
            action="sales_order.closed",
            entity_type="sales_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"order_number": row.order_number, "status": row.status},
        )
        self._session.commit()
        return row

    def get_order(self, order_id: UUID, *, firm_scope: UUID) -> SalesOrder:
        """Return one sales order."""
        row = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == order_id,
                SalesOrder.firm_id == firm_scope,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales order not found.")
        return row

    def order_response(self, row: SalesOrder) -> SalesOrderResponse:
        """Render one sales order row as its API contract."""
        lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(SalesOrderLine.sales_order_id == row.id)
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(SalesOrderAttachment).where(
                    SalesOrderAttachment.sales_order_id == row.id
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(SalesOrderNote).where(SalesOrderNote.sales_order_id == row.id)
            ).all()
        )
        return SalesOrderResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            order_number=row.order_number,
            order_date=row.order_date,
            delivery_date=row.delivery_date,
            customer_reference=row.customer_reference,
            reference_number=row.reference_number,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            remarks=row.remarks,
            credit_limit_snapshot=row.credit_limit_snapshot,
            outstanding_balance_snapshot=row.outstanding_balance_snapshot,
            status=SalesOrderStatus(row.status),
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
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
        )

    def timeline(
        self, *, order_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return the lifecycle timeline for one sales order."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=order_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def register_report(self, *, firm_scope: UUID) -> list[SalesOrderRegisterRecord]:
        """Return the register report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesOrder)
                .where(
                    SalesOrder.firm_id == firm_scope, SalesOrder.is_deleted.is_(False)
                )
                .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc())
            ).all()
        )
        return [
            SalesOrderRegisterRecord(
                order_id=row.id,
                order_number=row.order_number,
                order_date=row.order_date,
                customer_id=row.customer_id,
                salesman_id=row.salesman_id,
                territory_id=row.territory_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                status=SalesOrderStatus(row.status),
                grand_total=row.grand_total,
            )
            for row in rows
        ]

    def pending_orders(self, *, firm_scope: UUID) -> list[SalesOrderPendingRecord]:
        """List orders still open: draft or approved, not yet closed."""
        rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                    SalesOrder.status.in_(
                        [SalesOrderStatus.DRAFT.value, SalesOrderStatus.APPROVED.value]
                    ),
                )
            ).all()
        )
        return [
            SalesOrderPendingRecord(
                order_id=row.id,
                order_number=row.order_number,
                customer_id=row.customer_id,
                delivery_date=row.delivery_date,
                status=SalesOrderStatus(row.status),
                pending_value=row.grand_total,
            )
            for row in rows
        ]

    def back_orders(self, *, firm_scope: UUID) -> list[SalesOrderBackOrderRecord]:
        """List order lines whose requested quantity exceeds free stock."""
        rows = list(
            self._session.scalars(
                select(SalesOrderLine)
                .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
                .where(
                    SalesOrder.firm_id == firm_scope, SalesOrder.is_deleted.is_(False)
                )
            ).all()
        )
        result: list[SalesOrderBackOrderRecord] = []
        for row in rows:
            back_qty = self._q(row.reservable_quantity - row.available_stock)
            if back_qty <= ZERO:
                continue
            order = self._session.scalar(
                select(SalesOrder).where(SalesOrder.id == row.sales_order_id)
            )
            if order is None:
                continue
            result.append(
                SalesOrderBackOrderRecord(
                    order_id=order.id,
                    order_number=order.order_number,
                    line_id=row.id,
                    product_id=row.product_id,
                    requested_quantity=row.reservable_quantity,
                    available_stock=row.available_stock,
                    back_order_quantity=back_qty,
                )
            )
        return result

    def orders_by_customer(
        self, *, firm_scope: UUID
    ) -> list[SalesOrderByCustomerRecord]:
        """Total order value and count per customer, cancellations excluded."""
        rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                    SalesOrder.status != SalesOrderStatus.CANCELLED.value,
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        names: dict[UUID, str] = {}
        for row in rows:
            totals[row.customer_id] += row.grand_total
            counts[row.customer_id] += 1
            if row.customer_id not in names:
                customer = self._session.scalar(
                    select(Customer).where(Customer.id == row.customer_id)
                )
                names[row.customer_id] = (
                    customer.name if customer is not None else str(row.customer_id)
                )
        return [
            SalesOrderByCustomerRecord(
                customer_id=customer_id,
                customer_name=names.get(customer_id, str(customer_id)),
                order_count=counts[customer_id],
                total_value=self._q(totals[customer_id]),
            )
            for customer_id in sorted(
                totals.keys(), key=lambda item: names.get(item, str(item))
            )
        ]

    def orders_by_salesman(
        self, *, firm_scope: UUID
    ) -> list[SalesOrderBySalesmanRecord]:
        """Total order value and count per salesman, cancellations excluded."""
        rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                    SalesOrder.status != SalesOrderStatus.CANCELLED.value,
                    SalesOrder.salesman_id.is_not(None),
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        names: dict[UUID, str] = {}
        for row in rows:
            if row.salesman_id is None:
                continue
            totals[row.salesman_id] += row.grand_total
            counts[row.salesman_id] += 1
            if row.salesman_id not in names:
                user = self._session.scalar(
                    select(User).where(User.id == row.salesman_id)
                )
                names[row.salesman_id] = (
                    user.full_name if user is not None else str(row.salesman_id)
                )
        return [
            SalesOrderBySalesmanRecord(
                salesman_id=salesman_id,
                salesman_name=names.get(salesman_id, str(salesman_id)),
                order_count=counts[salesman_id],
                total_value=self._q(totals[salesman_id]),
            )
            for salesman_id in sorted(
                totals.keys(), key=lambda item: names.get(item, str(item))
            )
        ]

    def orders_by_territory(
        self, *, firm_scope: UUID
    ) -> list[SalesOrderByTerritoryRecord]:
        """Total order value and count per territory, cancellations excluded."""
        rows = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.firm_id == firm_scope,
                    SalesOrder.is_deleted.is_(False),
                    SalesOrder.status != SalesOrderStatus.CANCELLED.value,
                    SalesOrder.territory_id.is_not(None),
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        names: dict[UUID, str] = {}
        for row in rows:
            if row.territory_id is None:
                continue
            totals[row.territory_id] += row.grand_total
            counts[row.territory_id] += 1
            if row.territory_id not in names:
                territory = self._session.scalar(
                    select(SalesTerritoryNode).where(
                        SalesTerritoryNode.id == row.territory_id
                    )
                )
                names[row.territory_id] = (
                    territory.name if territory is not None else str(row.territory_id)
                )
        return [
            SalesOrderByTerritoryRecord(
                territory_id=territory_id,
                territory_name=names.get(territory_id, str(territory_id)),
                order_count=counts[territory_id],
                total_value=self._q(totals[territory_id]),
            )
            for territory_id in sorted(
                totals.keys(), key=lambda item: names.get(item, str(item))
            )
        ]

    def export_orders_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        """Export matching sales orders as CSV."""
        rows, _ = self.list_orders(
            firm_scope=firm_scope,
            filters=SalesOrderListFilters(),
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
                "order_number",
                "order_date",
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
                    row.order_number,
                    row.order_date.isoformat(),
                    str(row.customer_id),
                    str(row.branch_id),
                    str(row.warehouse_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_orders(
        self, data: SalesOrderImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[SalesOrder]:
        """Import a validated batch of sales orders atomically."""
        return [
            self.create_order(record, firm_id=firm_scope, actor_id=actor_id)
            for record in data.records
        ]

    def _replace_lines(
        self,
        row: SalesOrder,
        *,
        lines: list[SalesOrderLineWrite],
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        # Lines are matched on their line number and updated in place. Deleting
        # and re-inserting them, as this did, minted a new UUID for every line on
        # every save. Downstream documents record source_document_line_id as a
        # bare UUID with no foreign key, so those references silently dangled
        # after an upstream edit — and the re-insert also reset reserved_quantity
        # to zero while the reservation movement stayed in the ledger.
        existing = {
            line.line_number: line
            for line in self._session.scalars(
                select(SalesOrderLine).where(SalesOrderLine.sales_order_id == row.id)
            ).all()
        }
        seen: set[int] = set()
        subtotal = ZERO
        tax_total = ZERO
        line_discount_total = ZERO
        for item in lines:
            product = self._session.scalar(
                select(Product).where(
                    Product.id == item.product_id, Product.is_deleted.is_(False)
                )
            )
            if product is None:
                raise ValidationError("Product not found for sales order line.")
            quantity = self._q(item.quantity)
            free_quantity = self._q(item.free_quantity)
            conversion = self._conversion(
                quantity=self._q(quantity + free_quantity),
                sales_uom_id=item.sales_uom_id,
                inventory_uom_id=item.inventory_uom_id,
                product_id=item.product_id,
                order_date=row.order_date,
                firm_id=row.firm_id,
            )
            gross = self._q(quantity * self._q(item.unit_price))
            discount = self._q(
                item.discount_amount
                if item.discount_amount > ZERO
                else (gross * self._q(item.discount_percent) / Decimal("100"))
            )
            taxable = self._q(gross - discount)
            tax = self._tax_amount(
                order_date=row.order_date,
                firm_id=row.firm_id,
                actor_id=actor_id,
                business_profile_id=row.business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=item.warehouse_id or row.warehouse_id,
                product_id=item.product_id,
                tax_profile_id=item.tax_profile_id,
                invoice_value=taxable,
            )
            net = self._q(taxable + tax)
            available_stock, reserved_stock = self._stock_snapshot(
                firm_id=row.firm_id,
                branch_id=row.branch_id,
                warehouse_id=item.warehouse_id or row.warehouse_id,
                storage_node_id=item.storage_node_id,
                product_id=item.product_id,
            )
            line = existing.get(item.line_number)
            if line is None:
                line = SalesOrderLine(
                    sales_order_id=row.id,
                    firm_id=row.firm_id,
                    line_number=item.line_number,
                    reserved_quantity=ZERO,
                    created_by=actor_id,
                )
                self._session.add(line)
            line.product_id = item.product_id
            line.description = item.description
            line.quantity = quantity
            line.free_quantity = free_quantity
            line.base_quantity = self._q(conversion["converted"])
            line.reservable_quantity = self._q(conversion["converted"])
            line.available_stock = available_stock
            line.reserved_stock = reserved_stock
            line.sales_uom_id = item.sales_uom_id
            line.inventory_uom_id = item.inventory_uom_id
            line.packaging_type_id = item.packaging_type_id
            line.conversion_factor = self._q(conversion["factor"])
            version = conversion["version"]
            line.conversion_version = None if version is None else int(version)
            line.unit_price = self._q(item.unit_price)
            line.discount_percent = self._q(item.discount_percent)
            line.discount_amount = discount
            line.gross_amount = gross
            line.tax_profile_id = item.tax_profile_id
            line.tax_amount = tax
            line.net_amount = net
            line.warehouse_id = item.warehouse_id or row.warehouse_id
            line.storage_node_id = item.storage_node_id
            line.remarks = item.remarks
            line.updated_by = actor_id
            seen.add(item.line_number)
            subtotal += taxable
            tax_total += tax
            line_discount_total += discount
        for line_number, line in existing.items():
            if line_number not in seen:
                self._session.delete(line)
        self._session.flush()
        return {
            "subtotal": self._q(subtotal),
            "tax_total": self._q(tax_total),
            "line_discount_total": self._q(line_discount_total),
        }

    def _replace_attachments(
        self,
        row: SalesOrder,
        attachments: list[SalesOrderAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesOrderAttachment).filter(
            SalesOrderAttachment.sales_order_id == row.id
        ).delete(synchronize_session=False)
        for item in attachments:
            self._session.add(
                SalesOrderAttachment(
                    sales_order_id=row.id,
                    firm_id=firm_id,
                    file_name=item.file_name.strip(),
                    mime_type=item.mime_type,
                    file_path=item.file_path.strip(),
                    attachment_kind=item.attachment_kind.strip().upper(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_notes(
        self,
        row: SalesOrder,
        notes: list[SalesOrderNoteWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesOrderNote).filter(
            SalesOrderNote.sales_order_id == row.id
        ).delete(synchronize_session=False)
        for item in notes:
            self._session.add(
                SalesOrderNote(
                    sales_order_id=row.id,
                    firm_id=firm_id,
                    note_type=item.note_type.strip().upper(),
                    note=item.note.strip(),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _delete_children(self, order_id: UUID) -> None:
        """Clear the child collections an update rebuilds wholesale.

        Lines are deliberately absent: ``_replace_lines`` reconciles them by
        line number so their identities survive an edit. Deleting them here as
        well would defeat that.
        """
        self._session.query(SalesOrderAttachment).filter(
            SalesOrderAttachment.sales_order_id == order_id
        ).delete(synchronize_session=False)
        self._session.query(SalesOrderNote).filter(
            SalesOrderNote.sales_order_id == order_id
        ).delete(synchronize_session=False)

    def _reserve_inventory(self, row: SalesOrder, *, actor_id: UUID) -> None:
        lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(SalesOrderLine.sales_order_id == row.id)
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        for line in lines:
            if line.reservable_quantity <= ZERO:
                continue
            # Stock is held per batch, so a reservation is held per batch too:
            # committing the product put the movement on the untracked row
            # whatever the goods were actually in, which drove that row's
            # available negative while the batch rows sat apparently free.
            allocation = self._inventory.allocate_for_reservation(
                firm_scope=row.firm_id,
                branch_id=row.branch_id,
                warehouse_id=line.warehouse_id or row.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                quantity=line.reservable_quantity,
            )
            entered_total = self._q(line.quantity + line.free_quantity)
            for batch_id, held in allocation:
                self._inventory.record_sales_order_reservation(
                    firm_scope=row.firm_id,
                    actor_id=actor_id,
                    branch_id=row.branch_id,
                    warehouse_id=line.warehouse_id or row.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    reference_number=row.order_number,
                    transaction_date=row.order_date,
                    reserve_quantity=held,
                    entered_quantity=self._share(
                        entered_total, held, line.reservable_quantity, allocation
                    ),
                    entered_uom_id=line.sales_uom_id,
                    conversion_version=line.conversion_version,
                    remarks=f"sales_order reserve line {line.line_number}",
                    batch_id=batch_id,
                )
            line.reserved_quantity = line.reservable_quantity
            line.updated_by = actor_id
        self._session.flush()

    def _share(
        self,
        entered_total: Decimal,
        part: Decimal,
        whole: Decimal,
        allocation: list[tuple[UUID | None, Decimal]],
    ) -> Decimal:
        """Apportion the quantity the customer was quoted across a split.

        The entered quantity is what the order was taken in -- cases, strips --
        so it belongs to the line and not to any one batch. A line held in one
        batch keeps it whole; a line split across two carries its share, so the
        movements still add up to what was ordered.
        """
        if len(allocation) == 1 or whole <= ZERO:
            return entered_total
        return self._q(entered_total * (part / whole))

    def _release_inventory(self, row: SalesOrder, *, actor_id: UUID) -> None:
        lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(SalesOrderLine.sales_order_id == row.id)
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        for line in lines:
            if line.reserved_quantity <= ZERO:
                continue
            # Release the batches that actually hold the reservation, not the
            # ones holding stock: letting go of a batch nobody held would drive
            # its reserved quantity negative.
            allocation = self._inventory.allocate_for_release(
                firm_scope=row.firm_id,
                branch_id=row.branch_id,
                warehouse_id=line.warehouse_id or row.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                quantity=line.reserved_quantity,
            )
            entered_total = self._q(line.quantity + line.free_quantity)
            for batch_id, released in allocation:
                self._inventory.release_sales_order_reservation(
                    firm_scope=row.firm_id,
                    actor_id=actor_id,
                    branch_id=row.branch_id,
                    warehouse_id=line.warehouse_id or row.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    reference_number=row.order_number,
                    transaction_date=utc_now().date(),
                    release_quantity=released,
                    entered_quantity=self._share(
                        entered_total, released, line.reserved_quantity, allocation
                    ),
                    entered_uom_id=line.sales_uom_id,
                    conversion_version=line.conversion_version,
                    remarks=f"sales_order release line {line.line_number}",
                    batch_id=batch_id,
                )
            line.reserved_quantity = ZERO
            line.updated_by = actor_id
        self._session.flush()

    def _tax_amount(
        self,
        *,
        order_date: date,
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
                    product, order_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, order_date, firm_scope=firm_id
            )
        request = TaxRuleSimulationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=order_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "sales_order"},
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
        order_date: date,
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
                conversion_date=order_date,
            ),
            firm_scope=firm_id,
        )
        return {
            "factor": response.conversion_factor,
            "converted": self._q(response.converted_quantity),
            "version": response.version,
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
        and this read one of them with ``scalar()``, which returns the first
        and says nothing about the rest. An order line for a batch-tracked
        product then reported one arbitrary batch's quantity as the stock
        behind it, which is the figure a salesperson decides on.

        The delivery note service carries the same helper and had the same
        defect, where it gates the dispatch rather than merely reporting.
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
            user = self._session.scalar(
                select(User).where(User.id == salesman_id, User.is_deleted.is_(False))
            )
            if user is None:
                raise ValidationError("Salesman user not found.")
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
        document: SalesOrder,
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
                source_module_code="SALES_ORDER",
                document_number=document.order_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "order_number": document.order_number,
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

    def _attachment_response(
        self, row: SalesOrderAttachment
    ) -> SalesOrderAttachmentResponse:
        return SalesOrderAttachmentResponse.model_validate(row)

    def _note_response(self, row: SalesOrderNote) -> SalesOrderNoteResponse:
        return SalesOrderNoteResponse.model_validate(row)

    def _line_response(self, row: SalesOrderLine) -> SalesOrderLineResponse:
        return SalesOrderLineResponse.model_validate(row)
