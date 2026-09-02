"""Raise the sales documents a firm has chosen not to type itself.

The chain is quotation, sales order, delivery note, invoice, and a firm decides
per stage which of them its people fill in. This is what fills in the rest: a
bill arriving with bare product lines is turned into a sales order, a delivery
note and then the bill, and a bill arriving against an order is given the
delivery note that order never got.

Two things this deliberately does not do. It does not move stock or post to the
ledger itself -- it drives the same services a person would, so goods still
leave at dispatch and cost of goods sold still belongs to the delivery note.
And it never commits: everything it stages belongs to the caller's transaction,
so a bill that fails at approval leaves no order and no dispatched note behind
it. That is the whole reason the `stage_*` methods exist.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
    SalesInvoiceSourceWrite,
)
from app.sales_order.models import SalesOrder, SalesOrderLine, SalesWorkflowSettings
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_order.services.workflow_settings_service import SalesWorkflowService

ZERO = Decimal("0")


class SalesChainService:
    """Synthesise the sales documents a firm's configuration skips."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def ensure_invoice_source(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoiceCreate:
        """Return an invoice payload whose every line names a delivery note.

        Unchanged for a firm on the whole chain, which is every firm until one
        turns a stage off -- the bare-line and order-sourced paths below are
        the only ones that write anything.
        """
        settings = SalesWorkflowService(self._session).settings_for(firm_id)
        bare = [line for line in data.lines if line.source_document_line_id is None]
        if not bare:
            if settings.delivery_note_stage:
                return data
            return self._note_for_order(data, firm_id=firm_id, actor_id=actor_id)
        if len(bare) != len(data.lines):
            raise ValidationError(
                "An invoice bills either documents already raised or bare "
                "product lines, never a mixture of the two."
            )
        return self._order_and_note(
            data, firm_id=firm_id, actor_id=actor_id, settings=settings
        )

    def _order_and_note(
        self,
        data: SalesInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        settings: SalesWorkflowSettings,
    ) -> SalesInvoiceCreate:
        """Raise the order and the delivery note a bare bill implies."""
        if settings.sales_order_stage or settings.delivery_note_stage:
            raise ValidationError(
                "This firm raises a sales order and a delivery note before it "
                "bills, so an invoice line must name the document it bills."
            )
        if data.customer_id is None:
            raise ValidationError(
                "A bill raised without a source must name a customer."
            )
        branch_id, warehouse_id = self._resolve_place(
            firm_id=firm_id,
            branch_id=data.branch_id or settings.default_branch_id,
            warehouse_id=settings.default_warehouse_id,
        )
        order = SalesOrderService(self._session).stage_order(
            SalesOrderCreate(
                customer_id=data.customer_id,
                salesman_id=data.salesman_id,
                territory_id=data.territory_id,
                route_id=data.route_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                business_profile_id=data.business_profile_id,
                order_date=data.invoice_date,
                reference_number=data.reference_number,
                currency_code=data.currency_code,
                exchange_rate=data.exchange_rate,
                remarks=data.remarks,
                additional_charges=data.additional_charges,
                round_off=data.round_off,
                bill_discount_percent=data.bill_discount_percent,
                bill_discount_amount=data.bill_discount_amount,
                lines=[
                    SalesOrderLineWrite(
                        line_number=line.line_number,
                        product_id=self._product_of(line),
                        quantity=line.current_invoice_quantity,
                        free_quantity=line.free_quantity or ZERO,
                        sales_uom_id=line.invoice_uom_id,
                        packaging_type_id=line.packaging_type_id,
                        unit_price=line.unit_price,
                        discount_percent=line.discount_percent,
                        discount_amount=line.discount_amount,
                        tax_profile_id=line.tax_profile_id,
                        warehouse_id=line.warehouse_id or warehouse_id,
                        storage_node_id=line.storage_node_id,
                        remarks=line.remarks,
                    )
                    for line in data.lines
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        SalesOrderService(self._session).stage_approval(
            order.id, firm_scope=firm_id, actor_id=actor_id
        )
        return self._dispatch_and_rebind(
            data,
            order=order,
            quantities=None,
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _note_for_order(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoiceCreate:
        """Dispatch the order a bill names, for a firm that types no notes.

        The order is the firm's own document here -- somebody raised and
        approved it -- so only the note is missing, and it ships exactly what
        the bill charges for.
        """
        order_ids = {
            line.source_document_id
            for line in data.lines
            if line.source_document_type == SalesInvoiceSourceType.SALES_ORDER
        }
        if not order_ids:
            return data
        if len(order_ids) > 1:
            raise ValidationError(
                "A bill that dispatches its own goods bills one sales order at "
                "a time."
            )
        order = self._session.scalar(
            select(SalesOrder).where(
                SalesOrder.id == order_ids.pop(),
                SalesOrder.firm_id == firm_id,
                SalesOrder.is_deleted.is_(False),
            )
        )
        if order is None:
            raise ResourceNotFoundError("Sales order not found.")
        quantities = {
            line.source_document_line_id: line.current_invoice_quantity
            for line in data.lines
            if line.source_document_line_id is not None
        }
        return self._dispatch_and_rebind(
            data,
            order=order,
            quantities=quantities,
            firm_id=firm_id,
            actor_id=actor_id,
        )

    def _dispatch_and_rebind(
        self,
        data: SalesInvoiceCreate,
        *,
        order: SalesOrder,
        quantities: dict[UUID, Decimal] | None,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SalesInvoiceCreate:
        """Raise, approve and dispatch the note, then bill it instead.

        `quantities` names how much of each order line to ship; None ships the
        whole order, which is what a bare bill means.
        """
        order_lines = list(
            self._session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == order.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
        )
        notes = DeliveryNoteService(self._session)
        note = notes.stage_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=data.invoice_date,
                remarks=data.remarks,
                additional_charges=data.additional_charges,
                round_off=data.round_off,
                bill_discount_percent=data.bill_discount_percent,
                bill_discount_amount=data.bill_discount_amount,
                lines=[
                    self._note_line(line, quantities)
                    for line in order_lines
                    if self._shipping(line, quantities) > ZERO
                ],
            ),
            firm_id=firm_id,
            actor_id=actor_id,
        )
        notes.stage_approval(note.id, firm_scope=firm_id, actor_id=actor_id)
        notes.stage_dispatch(note.id, firm_scope=firm_id, actor_id=actor_id)
        return self._rebind(data, note=note)

    def _note_line(
        self, line: SalesOrderLine, quantities: dict[UUID, Decimal] | None
    ) -> DeliveryNoteLineWrite:
        """Ship one order line, carrying the deal the order already struck.

        The discounts come off the persisted order line rather than the
        request, so the two documents cannot disagree about what was agreed.
        """
        shipping = self._shipping(line, quantities)
        free = line.free_quantity
        if quantities is not None and line.quantity > ZERO and free > ZERO:
            # Ship the share of the gift that goes with the share being taken,
            # in the same scale the quantity columns use.
            free = (free * shipping / line.quantity).quantize(Decimal("0.0001"))
        return DeliveryNoteLineWrite(
            sales_order_line_id=line.id,
            line_number=line.line_number,
            description=line.description,
            current_delivery_quantity=shipping,
            free_quantity=free,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent or None,
            discount_amount=line.discount_amount or None,
            tax_profile_id=line.tax_profile_id,
            packaging_type_id=line.packaging_type_id,
            sales_uom_id=line.sales_uom_id,
            inventory_uom_id=line.inventory_uom_id,
            warehouse_id=line.warehouse_id,
            storage_node_id=line.storage_node_id,
            remarks=line.remarks,
        )

    @staticmethod
    def _shipping(
        line: SalesOrderLine, quantities: dict[UUID, Decimal] | None
    ) -> Decimal:
        """Report how much of one order line this dispatch carries."""
        if quantities is None:
            return line.quantity
        return quantities.get(line.id, ZERO)

    def _rebind(
        self, data: SalesInvoiceCreate, *, note: DeliveryNote
    ) -> SalesInvoiceCreate:
        """Point the bill at the note that now holds the goods.

        Billing is capped on `current_delivery_quantity` -- what the customer
        is charged for -- and never on `delivered_quantity`, which has the free
        goods folded into it and is measured in inventory units.
        """
        note_lines = list(
            self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
        )
        lines = [
            SalesInvoiceLineWrite(
                source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                source_document_id=note.id,
                source_document_line_id=note_line.id,
                line_number=note_line.line_number,
                current_invoice_quantity=note_line.current_delivery_quantity,
                unit_price=note_line.unit_price,
                # Left unstated so the invoice inherits the note's free goods
                # and its discount pro-rata, the same way any other bill does.
                tax_profile_id=note_line.tax_profile_id,
                packaging_type_id=note_line.packaging_type_id,
                invoice_uom_id=note_line.sales_uom_id,
                warehouse_id=note_line.warehouse_id,
                storage_node_id=note_line.storage_node_id,
                remarks=note_line.remarks,
            )
            for note_line in note_lines
        ]
        return data.model_copy(
            update={
                "source_documents": [
                    SalesInvoiceSourceWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                    )
                ],
                "lines": lines,
            }
        )

    @staticmethod
    def _product_of(line: SalesInvoiceLineWrite) -> UUID:
        """Return the product a bare line names."""
        if line.product_id is None:
            raise ValidationError("A bare invoice line must name a product.")
        return line.product_id

    def _resolve_place(
        self,
        *,
        firm_id: UUID,
        branch_id: UUID | None,
        warehouse_id: UUID | None,
    ) -> tuple[UUID, UUID]:
        """Decide where a synthesised sale ships from.

        The request wins, then the firm's configured defaults, then the branch
        and warehouse the firm marked default. Dispatch refuses a line with no
        warehouse, and a firm whose delivery-note stage is automatic never sees
        a field to type one into -- so failing here, by name, beats failing
        three documents later with a message about a note the user never saw.
        """
        if branch_id is None:
            branch_id = self._session.scalar(
                select(Branch.id).where(
                    Branch.firm_id == firm_id,
                    Branch.is_default.is_(True),
                    Branch.is_deleted.is_(False),
                )
            )
        if branch_id is None:
            raise ValidationError(
                "This firm has no default branch, so a bill cannot decide "
                "where its goods ship from."
            )
        if warehouse_id is None:
            warehouse_id = self._session.scalar(
                select(Warehouse.id).where(
                    Warehouse.branch_id == branch_id,
                    Warehouse.is_default.is_(True),
                    Warehouse.is_deleted.is_(False),
                )
            )
        if warehouse_id is None:
            raise ValidationError(
                "This branch has no default warehouse, so a bill cannot decide "
                "where its goods ship from."
            )
        return branch_id, warehouse_id
