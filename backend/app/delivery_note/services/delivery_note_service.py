"""Delivery note backend lifecycle, dispatch, and reporting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.batch_serial.models import BatchRecord, SerialNumber
from app.batch_serial.schemas import (
    BatchSaleSettingsResponse,
    DispatchBatchCheck,
    DispatchBatchFinding,
    PickedSerial,
    SerialStatus,
)
from app.batch_serial.services.batch_sale_policy import (
    BatchSalePolicyService,
    describe_batches,
)
from app.batch_serial.services.batch_serial_service import BatchSerialService
from app.batch_serial.services.serial_trail_service import (
    DELIVERY_NOTE,
    LineRef,
    Pick,
    SerialTrailService,
)
from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.gating import assert_feature_fields
from app.business.models.framework import AttributeEntityType
from app.business.services import document_attributes
from app.common.audit.services import record_audit
from app.common.firm_metadata import (
    FirmMetadataReader,
    firm_date_of,
    platform_reader,
)
from app.common.report_names import (
    branch_names,
    customer_labels,
    customer_names,
    customers_matching,
    warehouse_names,
)
from app.core.database.batch import children_by_parent
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.chunks import chunks
from app.core.utils.dates import as_utc, utc_now
from app.core.utils.pricing import (
    LineDiscount,
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
)
from app.core.utils.report_labels import UNASSIGNED
from app.customers.models import Customer
from app.customers.services.ship_to import resolve_ship_to
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteAttachment,
    DeliveryNoteLine,
    DeliveryNoteLineBatch,
    DeliveryNoteNote,
)
from app.delivery_note.rules import (
    SHIPPED_STATES,
    delivered_by_order_line,
    goods_have_left,
    goods_have_left_clause,
)
from app.delivery_note.schemas import (
    DeliveryNoteAttachmentResponse,
    DeliveryNoteAttachmentWrite,
    DeliveryNoteBatchPick,
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
    DeliveryProofWrite,
)
from app.delivery_note.services.transporters import TransporterService
from app.document_files.services import FileParent, document_file_counts
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
from app.inventory.services import InventoryService, LineConversion
from app.messaging.services import MessagingDocument, stage_document_event
from app.products.models import Product
from app.products.services.kits import KitService
from app.products.services.stockless import stockless_products
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderStatus
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.rule_stamp import stamps_tax_rules
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.trade_licences.services.licence_check import (
    LicenceCheckService,
    LicenceDocument,
)
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService, assert_quantity_fits_unit

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


@dataclass(frozen=True)
class _HeldAt:
    """Where a sales order line's reservation sits: branch, warehouse, bay."""

    branch_id: UUID
    warehouse_id: UUID
    storage_node_id: UUID | None


#: The kind a proof-of-delivery photo or signature is filed under among the
#: note's attachments (backlog 67 row 6).
PROOF_OF_DELIVERY = "PROOF_OF_DELIVERY"

#: The note's transport details (backlog 67 row 5), written and kept together.
TRANSPORT_FIELDS: tuple[str, ...] = (
    "transporter_name",
    "transporter_gstin",
    "transport_mode",
    "lr_number",
    "lr_date",
    "distance_km",
)


def _challan(reason: str | None, note: str | None) -> tuple[str, str | None]:
    """Return the reason the goods go out and the words OTHER needs.

    Backlog 77 row 3. None is a sale. OTHER must say what it is; any other
    reason keeps no words, so a note changed back to a sale prints none.

    Raises:
        ValidationError: When OTHER is given without saying what it is.

    """
    chosen = reason or "SALE"
    words = (note or "").strip() or None
    if chosen != "OTHER":
        return chosen, None
    if words is None:
        raise ValidationError(
            "Say why the goods go out when the challan reason is Other."
        )
    return chosen, words


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
        self._trail = SerialTrailService(session)
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
        if filters.awaiting_delivery_proof:
            awaiting = self._awaiting_proof()
            statement = statement.where(awaiting)
            count = count.where(awaiting)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                DeliveryNote.delivery_note_number.ilike(token),
                DeliveryNote.sales_order_reference.ilike(token),
                DeliveryNote.vehicle.ilike(token),
                DeliveryNote.driver.ilike(token),
                DeliveryNote.transporter_name.ilike(token),
                DeliveryNote.lr_number.ilike(token),
                DeliveryNote.remarks.ilike(token),
                DeliveryNote.customer_id.in_(customers_matching(token)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        order_column = columns.get(sort_by, DeliveryNote.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    order_column.desc() if descending else order_column.asc(),
                    # Newest first within the chosen column, then a stable key.
                    DeliveryNote.created_at.desc(),
                    DeliveryNote.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> DeliveryNoteSummary:
        """Return aggregate delivery note values for the visible firm scope.

        Counted and summed in SQL, one row per status, rather than loading every
        document the firm ever raised (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    DeliveryNote.status,
                    func.count(),
                    func.coalesce(func.sum(DeliveryNote.grand_total), 0),
                )
                .where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                )
                .group_by(DeliveryNote.status)
            ).all()
        }

        def count(status: DeliveryNoteStatus) -> int:
            """Return how many documents are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        progress = self.partially_delivered_orders(firm_scope=firm_scope)
        awaiting = int(
            self._session.scalar(
                select(func.count())
                .select_from(DeliveryNote)
                .where(
                    DeliveryNote.firm_id == firm_scope,
                    DeliveryNote.is_deleted.is_(False),
                    self._awaiting_proof(),
                )
            )
            or 0
        )
        return DeliveryNoteSummary(
            awaiting_delivery_proof=awaiting,
            total=sum(number for number, _ in by_status.values()),
            draft=count(DeliveryNoteStatus.DRAFT),
            approved=count(DeliveryNoteStatus.APPROVED),
            dispatched=count(DeliveryNoteStatus.DISPATCHED),
            completed=count(DeliveryNoteStatus.COMPLETED),
            cancelled=count(DeliveryNoteStatus.CANCELLED),
            closed=count(DeliveryNoteStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
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
        if data.attributes:
            document_attributes.store(
                self._session,
                AttributeEntityType.DELIVERY_NOTE,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        # The order's fields carry to its note (MST-6).
        document_attributes.carry(
            self._session,
            AttributeEntityType.SALES_ORDER,
            row.sales_order_id,
            AttributeEntityType.DELIVERY_NOTE,
            row.id,
            firm_id=row.firm_id,
            actor_id=actor_id,
        )
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
        self._refuse_unless_order_open(order)
        self._refuse_if_held(order)
        self._validate_scope_references(
            firm_id=firm_id,
            customer_id=order.customer_id,
            branch_id=order.branch_id,
            warehouse_id=order.warehouse_id,
            salesman_id=order.salesman_id,
            territory_id=order.territory_id,
            route_id=order.route_id,
        )
        note_number = self._issue_number(
            numbering_rule,
            typed=data.delivery_note_number,
            number_column=DeliveryNote.delivery_note_number,
            firm_id=firm_id,
            document_date=data.delivery_date,
            actor_id=actor_id,
            branch_code=self._scope_code(order.branch_id),
            company_code=self._company_code(firm_id),
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
            shipping_address_id=self._ship_to(order, data.shipping_address_id),
            vehicle=data.vehicle,
            driver=data.driver,
            **{name: getattr(data, name) for name in TRANSPORT_FIELDS},
            freight_terms=data.freight_terms,
            **dict(
                zip(
                    ("challan_reason", "challan_reason_note"),
                    _challan(data.challan_reason, data.challan_reason_note),
                    strict=True,
                )
            ),
            remarks=data.remarks,
            status=DeliveryNoteStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._apply_transporter(row, data)
        self._session.flush()
        totals = self._replace_lines(
            row,
            lines=data.lines,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            freight_amount=data.freight_amount,
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
        self._refuse_unless_order_open(order)
        # A held order's draft may still have its vehicle, driver or remarks
        # put right; what it may not do is change what is to ship.
        if order.is_on_hold:
            asked = sorted(
                (
                    str(line.sales_order_line_id),
                    self._q(line.current_delivery_quantity),
                    self._q(line.free_quantity),
                )
                for line in data.lines
            )
            if order.id != row.sales_order_id or asked != self._to_ship(row.id):
                self._refuse_if_held(order)
        # Absent keeps the note's own ship-to, unless it now ships another
        # order, whose ship-to it takes.
        if "shipping_address_id" in data.model_fields_set:
            row.shipping_address_id = self._ship_to(order, data.shipping_address_id)
        elif order.id != row.sales_order_id:
            row.shipping_address_id = self._ship_to(order, None)
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
        # Absent keeps what the note says: an editor that never showed the
        # transport details must not clear them (backlog 67 row 5).
        for name in (*TRANSPORT_FIELDS, "freight_terms"):
            if name in data.model_fields_set:
                setattr(row, name, getattr(data, name))
        self._apply_transporter(row, data)
        # The same for why the goods go out (backlog 77 row 3).
        if "challan_reason" in data.model_fields_set:
            row.challan_reason, row.challan_reason_note = _challan(
                data.challan_reason, data.challan_reason_note
            )
        row.remarks = data.remarks
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        totals = self._replace_lines(
            row,
            lines=data.lines,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            freight_amount=data.freight_amount,
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
        if "attributes" in data.model_fields_set:
            document_attributes.store(
                self._session,
                AttributeEntityType.DELIVERY_NOTE,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        self._session.commit()
        return row

    def approve_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        licence_override_reason: str | None = None,
    ) -> DeliveryNote:
        """Approve one delivery note and commit it."""
        row = self.stage_approval(
            note_id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            licence_override_reason=licence_override_reason,
        )
        self._session.commit()
        return row

    def stage_approval(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        licence_override_reason: str | None = None,
        check_licences: bool = True,
    ) -> DeliveryNote:
        """Approve one delivery note without committing it.

        ``check_licences`` is false only for a note the chain raised for an
        invoice, which is checked at its own approval (backlog 54).
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status != DeliveryNoteStatus.DRAFT.value:
            raise ValidationError("Only draft delivery notes can be approved.")
        order = self._sales_order(row.sales_order_id, firm_id=firm_scope)
        self._refuse_unless_order_open(order)
        self._refuse_if_held(order)
        licence_remark, licence_details = (
            LicenceCheckService(self._session).approve_sale(
                LicenceDocument.DELIVERY_NOTE,
                row.id,
                firm_id=firm_scope,
                override_reason=licence_override_reason,
            )
            if check_licences
            else (None, None)
        )
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
            remarks=licence_remark,
            details=licence_details,
        )
        record_audit(
            self._session,
            action="delivery_note.approved",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=licence_details,
        )
        return row

    def dispatch_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        batch_reason: str | None = None,
    ) -> DeliveryNote:
        """Dispatch one delivery note by hand and commit it.

        By hand, so before any invoice: the firm's GST policy judges it
        (backlog 77 row 2). A bill dispatching the note it raised goes through
        `stage_dispatch` and is not judged -- the invoice is what ships it.
        The firm's batch rules are (backlog 79 row 6): ``batch_reason`` is why
        a near-expiry batch or a FEFO skip goes out, where the firm asks.
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        warning = (
            self._gst_dispatch_warning(row, firm_scope=firm_scope)
            if row.status == DeliveryNoteStatus.APPROVED.value
            else None
        )
        row = self.stage_dispatch(
            note_id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            gst_warning=warning,
            batch_reason=batch_reason,
            judge_batches=True,
        )
        self._session.commit()
        return row

    def batch_check(self, note_id: UUID, *, firm_scope: UUID) -> DispatchBatchCheck:
        """Say what dispatching this note would meet under the batch rules (79).

        The batches each line will take -- those a person chose, or the
        earliest-expiry split dispatch would draw -- judged as dispatch will
        judge them, so the screen can ask for a reason before it is refused.
        Dispatch itself stays the authority: stock can move in between.
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        policy = BatchSalePolicyService(self._session)
        rules = policy.settings_response(firm_scope)
        lines = self._session.scalars(
            select(DeliveryNoteLine)
            .where(
                DeliveryNoteLine.delivery_note_id == row.id,
                DeliveryNoteLine.is_deleted.is_(False),
            )
            .order_by(DeliveryNoteLine.line_number.asc())
        ).all()
        picks = self.batch_picks([line.id for line in lines])
        stock = BatchSerialService(self._session)
        findings: list[DispatchBatchFinding] = []
        needs_reason = False
        would_block = False
        keep_until = policy.keep_until(row.customer_id, on=row.delivery_date)
        for line in lines:
            if line.warehouse_id is None or line.delivered_quantity <= ZERO:
                continue
            if self._trail.is_serialised(line.product_id):
                continue
            fefo = [
                (item.batch_id, item.fefo)
                for item in stock.batch_availability(
                    firm_scope=firm_scope,
                    product_id=line.product_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    as_of=row.delivery_date,
                    quantity=line.delivered_quantity,
                    sales_order_line_id=line.sales_order_line_id,
                    near_expiry_days=rules.near_expiry_days,
                    keep_until=keep_until,
                )
                if item.fefo > ZERO
            ]
            chosen = [
                (pick.batch_id, self._q(pick.quantity))
                for pick in picks.get(line.id, [])
            ]
            split = chosen or fefo
            short = (
                policy.short_of(
                    [batch_id for batch_id, _ in split], keep_until=keep_until
                )
                if keep_until is not None
                else []
            )
            if short:
                would_block = would_block or rules.shelf_life_policy == "BLOCK"
                findings.append(
                    DispatchBatchFinding(
                        line_number=line.line_number,
                        kind="SHORT_SHELF_LIFE",
                        message=(
                            f"Line {line.line_number}: "
                            f"{describe_batches(short, row.delivery_date)} "
                            "expires before the customer's minimum shelf life "
                            f"({keep_until.isoformat() if keep_until else ''})."
                        ),
                    )
                )
            near = policy.near_expiry(
                firm_scope,
                [batch_id for batch_id, _ in split],
                as_of=row.delivery_date,
                days=rules.near_expiry_days,
            )
            if near:
                needs_reason = needs_reason or rules.near_expiry_policy == "REASON"
                findings.append(
                    DispatchBatchFinding(
                        line_number=line.line_number,
                        kind="NEAR_EXPIRY",
                        message=(
                            f"Line {line.line_number}: near expiry -- "
                            f"{describe_batches(near, row.delivery_date)}."
                        ),
                    )
                )
            as_split = {batch_id: self._q(qty) for batch_id, qty in fefo}
            if chosen and dict(chosen) != as_split:
                needs_reason = needs_reason or rules.fefo_skip_policy == "REASON"
                findings.append(
                    DispatchBatchFinding(
                        line_number=line.line_number,
                        kind="FEFO_SKIP",
                        message=(
                            f"Line {line.line_number}: a later batch is chosen "
                            "ahead of an earlier-expiring one."
                        ),
                    )
                )
        return DispatchBatchCheck(
            findings=findings,
            needs_reason=needs_reason,
            message=" ".join(item.message for item in findings) or None,
            would_block=would_block,
        )

    def _gst_dispatch_warning(
        self, row: DeliveryNote, *, firm_scope: UUID
    ) -> str | None:
        """Judge a hand dispatch under the firm's GST policy (backlog 77 row 2).

        Raises:
            ValidationError: When the firm blocks dispatch before the invoice.

        """
        from app.tax.services.gst_compliance import GstComplianceService

        return GstComplianceService(self._session).judge_dispatch(
            firm_scope,
            note_number=row.delivery_note_number,
            challan_reason=row.challan_reason or "SALE",
        )

    def stage_dispatch(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        gst_warning: str | None = None,
        batch_reason: str | None = None,
        judge_batches: bool = False,
    ) -> DeliveryNote:
        """Dispatch one delivery note without committing it.

        This is where stock leaves and cost of goods sold is posted, so it is
        the step a composed chain most needs rolled back with everything else:
        committing here and failing at the invoice is goods gone with nothing
        owed for them.

        ``judge_batches`` is a person dispatching: a firm rule that wants a
        reason for a near-expiry batch or a FEFO skip refuses without
        ``batch_reason``. A bill shipping the notes it raised for itself is
        recorded but not refused -- its counter has no picker yet (79).
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status == DeliveryNoteStatus.DISPATCHED.value:
            return row
        if row.status != DeliveryNoteStatus.APPROVED.value:
            raise ValidationError("Only approved delivery notes can be dispatched.")
        order = self._sales_order(row.sales_order_id, firm_id=firm_scope)
        self._refuse_unless_order_open(order)
        self._refuse_if_held(order)
        batch_notes = self._dispatch_inventory(
            row=row,
            actor_id=actor_id,
            batch_reason=batch_reason,
            judge_batches=judge_batches,
        )
        row.status = DeliveryNoteStatus.DISPATCHED.value
        row.dispatched_at = utc_now()
        row.updated_by = actor_id
        details: dict[str, object] = {}
        if gst_warning:
            details["gst_warning"] = gst_warning
        if batch_notes:
            details["batch_warnings"] = batch_notes
            if batch_reason and batch_reason.strip():
                details["batch_reason"] = batch_reason.strip()
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="DISPATCHED",
            from_state=DeliveryNoteStatus.APPROVED.value,
            to_state=row.status,
            actor_id=actor_id,
            details=details or None,
        )
        record_audit(
            self._session,
            action="delivery_note.dispatched",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=details or None,
        )
        stage_document_event(
            self._session,
            "DELIVERY_DISPATCHED",
            MessagingDocument(
                document_type="DELIVERY_NOTE",
                document_id=row.id,
                document_number=row.delivery_note_number,
                document_date=row.delivery_date,
                customer_id=row.customer_id,
                amount=row.grand_total,
            ),
            firm_id=firm_scope,
            actor_id=actor_id,
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
        gst_warning: str | None = None
        if row.status == DeliveryNoteStatus.APPROVED.value:
            # Completing an approved note dispatches it. One already on the
            # road is only being confirmed as received, which a hold on the
            # order cannot undo.
            order = self._sales_order(row.sales_order_id, firm_id=firm_scope)
            self._refuse_unless_order_open(order)
            self._refuse_if_held(order)
            gst_warning = self._gst_dispatch_warning(row, firm_scope=firm_scope)
            # Completing is a person dispatching too, so the batch rules judge
            # it; one that wants a reason is answered by dispatching first.
            self._dispatch_inventory(row=row, actor_id=actor_id, judge_batches=True)
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
            details={"gst_warning": gst_warning} if gst_warning else None,
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

    @staticmethod
    def _awaiting_proof() -> ColumnElement[bool]:
        """Match notes whose goods have left with no proof of delivery yet."""
        return and_(
            DeliveryNote.status.in_(
                (
                    DeliveryNoteStatus.DISPATCHED.value,
                    DeliveryNoteStatus.COMPLETED.value,
                )
            ),
            DeliveryNote.delivered_at.is_(None),
        )

    def record_delivery_proof(
        self,
        note_id: UUID,
        data: DeliveryProofWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> DeliveryNote:
        """Record that the customer received a note's goods (backlog 67 row 6).

        A note is **delivered** only with a proof: when, who received the
        goods, remarks, and optionally a photo or signature. It is a flag
        beside the status -- see the model -- so recording it changes nothing
        any other module reads, except that a DISPATCHED note is completed:
        the proof is the confirmation of receipt that completing always meant.
        A proof may be recorded again to correct it; the trail keeps both.
        """
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachment": data.attachment},
        )
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status not in {
            DeliveryNoteStatus.DISPATCHED.value,
            DeliveryNoteStatus.COMPLETED.value,
        }:
            raise ValidationError(
                "Proof of delivery is recorded for a note whose goods have "
                "left: dispatch it first."
            )
        delivered_at = as_utc(data.delivered_at)
        now = utc_now()
        if delivered_at > now + timedelta(minutes=5):
            raise ValidationError("The goods cannot have been received in the future.")
        # The day it fell on for the firm, not in UTC (D-CFG-25): goods handed
        # over at 01:00 on the note's own date in India are 19:30 UTC the day
        # before, and were refused as received before the note.
        if firm_date_of(self._session, firm_scope, delivered_at) < row.delivery_date:
            raise ValidationError(
                "The goods cannot have been received before the note's own date."
            )
        before = row.status
        corrected = row.delivered_at is not None
        row.delivered_at = delivered_at
        row.delivery_received_by = data.received_by
        row.delivery_remarks = data.remarks
        row.delivery_recorded_at = now
        row.delivery_recorded_by = actor_id
        if row.status == DeliveryNoteStatus.DISPATCHED.value:
            row.status = DeliveryNoteStatus.COMPLETED.value
            row.completed_at = now
        row.updated_by = actor_id
        if data.attachment is not None:
            self._session.add(
                DeliveryNoteAttachment(
                    delivery_note_id=row.id,
                    firm_id=firm_scope,
                    file_name=data.attachment.file_name,
                    mime_type=data.attachment.mime_type,
                    file_path=data.attachment.file_path,
                    attachment_kind=PROOF_OF_DELIVERY,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="DELIVERED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=data.remarks,
            details={
                "delivered_at": delivered_at.isoformat(),
                "received_by": data.received_by,
            },
        )
        record_audit(
            self._session,
            action=(
                "delivery_note.delivery_corrected"
                if corrected
                else "delivery_note.delivered"
            ),
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "delivered_at": delivered_at.isoformat(),
                "received_by": data.received_by,
                "status": row.status,
            },
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
        """Cancel one delivery note and commit it."""
        row = self.stage_cancel(
            note_id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        self._session.commit()
        return row

    def stage_cancel(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> DeliveryNote:
        """Cancel one delivery note without committing it."""
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
        return row

    def close_note(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> DeliveryNote:
        """Close one delivery note whose goods have left.

        Closing refused only a draft, so an APPROVED note that never dispatched
        could be closed -- and a closed note counts as delivered for its order
        and is offered for billing, while its reservation stayed held for good
        (D-SELL-4, driven 2026-09-19: the order read DELIVERED with 7 of 12
        shipped). A note that will not ship is cancelled, not closed.
        """
        row = self.get_note(note_id, firm_scope=firm_scope)
        if row.status == DeliveryNoteStatus.CLOSED.value:
            return row
        if not goods_have_left(row):
            raise ValidationError(
                f"Only dispatched or completed delivery notes can be closed; "
                f"{row.delivery_note_number} is {row.status.lower()}."
            )
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

    def _ship_to(self, order: SalesOrder, address_id: UUID | None) -> UUID | None:
        """Return where a note ships: the address named, else the order's.

        A note continues its order, so it inherits the order's ship-to
        (backlog 67 row 3) rather than re-reading the customer's default.
        """
        if address_id is None and order.shipping_address_id is not None:
            return order.shipping_address_id
        return resolve_ship_to(
            self._session, customer_id=order.customer_id, address_id=address_id
        )

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

    def _customer_name(self, customer_id: UUID) -> str:
        """Name the customer so a picker of notes is not a list of numbers."""
        customer = self._session.get(Customer, customer_id)
        return "" if customer is None else (customer.display_name or customer.name)

    def note_response(self, row: DeliveryNote) -> DeliveryNoteResponse:
        """Render one delivery note row as its API contract."""
        return self.note_responses([row])[0]

    def note_responses(
        self, rows: Sequence[DeliveryNote]
    ) -> list[DeliveryNoteResponse]:
        """Render a page of delivery notes, reading each child table once.

        One query per child table for the whole page, grouped by note in
        Python, rather than seven per note (backlog 56 C, step 3). The
        single-note builder is this with a list of one.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        # Children are read with their soft-deleted rows, as they always were.
        lines = children_by_parent(
            self._session,
            DeliveryNoteLine,
            DeliveryNoteLine.delivery_note_id,
            ids,
            DeliveryNoteLine.line_number.asc(),
            live_only=False,
        )
        attachments = children_by_parent(
            self._session,
            DeliveryNoteAttachment,
            DeliveryNoteAttachment.delivery_note_id,
            ids,
            live_only=False,
        )
        notes = children_by_parent(
            self._session,
            DeliveryNoteNote,
            DeliveryNoteNote.delivery_note_id,
            ids,
            live_only=False,
        )
        every_line = [item for group in lines.values() for item in group]
        products = self._products_named(every_line)
        serials = self._trail.picked_serials(line.id for line in every_line)
        batch_picks = self.batch_picks([line.id for line in every_line])
        names = customer_labels(self._session, (row.customer_id for row in rows))
        warnings = self._duplicate_warnings(rows)
        answer = [
            self._note_response_from(
                row,
                lines=lines[row.id],
                attachments=attachments[row.id],
                notes=notes[row.id],
                products=products,
                serials=serials,
                batch_picks=batch_picks,
                customer_name=names.get(row.customer_id, ""),
                warning=warnings.get(row.id),
            )
            for row in rows
        ]
        # The firm's own fields, one read for the page (MST-6).
        fields = document_attributes.responses_for_many(
            self._session, AttributeEntityType.DELIVERY_NOTE, [r.id for r in rows]
        )
        # Uploaded files, counted for the page in one grouped read (SG-6).
        files = document_file_counts(
            self._session, FileParent.DELIVERY_NOTE, [r.id for r in rows]
        )
        for response in answer:
            response.attributes = fields.get(response.id, [])
            response.attached_file_count = files.get(response.id, 0)
        return answer

    def _note_response_from(
        self,
        row: DeliveryNote,
        *,
        lines: list[DeliveryNoteLine],
        attachments: list[DeliveryNoteAttachment],
        notes: list[DeliveryNoteNote],
        products: dict[UUID, Product],
        serials: dict[UUID, list[PickedSerial]],
        customer_name: str,
        warning: str | None,
        batch_picks: dict[UUID, list[DeliveryNoteBatchPick]] | None = None,
    ) -> DeliveryNoteResponse:
        """Build one note's response from what the page already read."""
        return DeliveryNoteResponse(
            id=row.id,
            version=row.version,
            firm_id=row.firm_id,
            sales_order_id=row.sales_order_id,
            customer_id=row.customer_id,
            customer_name=customer_name,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            salesman_id=row.salesman_id,
            route_id=row.route_id,
            territory_id=row.territory_id,
            delivery_note_number=row.delivery_note_number,
            delivery_date=row.delivery_date,
            sales_order_reference=row.sales_order_reference,
            shipping_address_id=row.shipping_address_id,
            vehicle=row.vehicle,
            driver=row.driver,
            transporter_id=row.transporter_id,
            freight_terms=row.freight_terms,
            transporter_name=row.transporter_name,
            transporter_gstin=row.transporter_gstin,
            transport_mode=row.transport_mode,
            lr_number=row.lr_number,
            lr_date=row.lr_date,
            distance_km=row.distance_km,
            challan_reason=row.challan_reason or "SALE",
            challan_reason_note=row.challan_reason_note,
            remarks=row.remarks,
            status=DeliveryNoteStatus(row.status),
            total_ordered_quantity=row.total_ordered_quantity,
            total_previously_delivered_quantity=row.total_previously_delivered_quantity,
            total_current_delivery_quantity=row.total_current_delivery_quantity,
            total_free_quantity=row.total_free_quantity,
            customer_discount_percent=row.customer_discount_percent,
            bill_discount_percent=row.bill_discount_percent,
            bill_discount_amount=row.bill_discount_amount,
            freight_amount=row.freight_amount,
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
            is_delivered=row.delivered_at is not None,
            delivered_at=row.delivered_at,
            delivery_received_by=row.delivery_received_by,
            delivery_remarks=row.delivery_remarks,
            delivery_recorded_at=row.delivery_recorded_at,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            lines=[
                self._line_response(item, products.get(item.product_id)).model_copy(
                    update={
                        "serials": serials.get(item.id, []),
                        "batches": (batch_picks or {}).get(item.id, []),
                    }
                )
                for item in lines
            ],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            duplicate_warning=warning,
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

    def register_report(
        self,
        *,
        firm_scope: UUID,
        statuses: Sequence[str] | None = None,
        window: ReportWindow = WHOLE_HISTORY,
    ) -> list[DeliveryNoteRegisterRecord]:
        """Return the register report, optionally narrowed to some statuses.

        The pending report answers this shape too: it used to answer whole
        documents -- lines, attachments and notes per row -- while the desktop
        showed five columns of them (D-RPT-16).

        Every id carries its name, in one read per table for the whole report
        rather than one per row; the grid derives its columns from the row, so
        a register of ids alone read as UUIDs (D-RPT-17).
        """
        rows = window.fetch(
            self._session,
            select(DeliveryNote)
            .where(
                DeliveryNote.firm_id == firm_scope,
                DeliveryNote.is_deleted.is_(False),
                *(
                    ()
                    if statuses is None
                    else (DeliveryNote.status.in_(list(statuses)),)
                ),
                *window.dated(DeliveryNote.delivery_date),
            )
            .order_by(
                DeliveryNote.delivery_date.desc(),
                DeliveryNote.created_at.desc(),
                DeliveryNote.id.desc(),
            ),
        )
        customers = customer_names(self._session, (row.customer_id for row in rows))
        branches = branch_names(self._session, (row.branch_id for row in rows))
        warehouses = warehouse_names(self._session, (row.warehouse_id for row in rows))
        records = [
            DeliveryNoteRegisterRecord(
                delivery_note_id=row.id,
                delivery_note_number=row.delivery_note_number,
                delivery_date=row.delivery_date,
                sales_order_id=row.sales_order_id,
                sales_order_number=row.sales_order_reference,
                customer_id=row.customer_id,
                customer_name=customers.get(row.customer_id, str(row.customer_id)),
                branch_id=row.branch_id,
                branch_name=branches.get(row.branch_id, str(row.branch_id)),
                warehouse_id=row.warehouse_id,
                warehouse_name=warehouses.get(row.warehouse_id, str(row.warehouse_id)),
                status=DeliveryNoteStatus(row.status),
                grand_total=row.grand_total,
            )
            for row in rows
        ]
        return mapped_like(rows, records)

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
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[DeliveryNoteOrderProgressRecord]:
        """Show how much of each sales order has actually been delivered.

        "Delivered" is what left the warehouse -- the notes that dispatched,
        summed by `delivered_by_order_line`, which is the derivation the
        order's own status follows. An APPROVED note used to count here, so an
        order whose note was approved and never dispatched read 4 delivered
        while nothing had moved (D-RPT-9). One grouped read for the lines and
        one for the deliveries, rather than one query per line.
        """
        # One record per order, so the orders are paged in SQL, newest first.
        order_rows = window.fetch(
            self._session,
            select(SalesOrder)
            .where(
                SalesOrder.firm_id == firm_scope,
                SalesOrder.is_deleted.is_(False),
                SalesOrder.status != SalesOrderStatus.CANCELLED.value,
                *window.dated(SalesOrder.order_date),
            )
            .order_by(
                SalesOrder.order_date.desc(),
                SalesOrder.created_at.desc(),
                SalesOrder.id.desc(),
            ),
        )
        if not order_rows:
            return mapped_like(order_rows, [])
        order_ids = [order.id for order in order_rows]
        lines_by_order: dict[UUID, list[SalesOrderLine]] = defaultdict(list)
        # In chunks: a firm's open orders over two years are more ids than
        # one statement may name (backlog 56 C, found timing PERF01).
        for part in chunks(order_ids):
            for line in self._session.scalars(
                select(SalesOrderLine).where(
                    SalesOrderLine.sales_order_id.in_(part),
                    SalesOrderLine.is_deleted.is_(False),
                )
            ).all():
                lines_by_order[line.sales_order_id].append(line)
        sent = delivered_by_order_line(
            self._session, firm_id=firm_scope, sales_order_ids=order_ids
        )
        result: list[DeliveryNoteOrderProgressRecord] = []
        for order in order_rows:
            lines = lines_by_order.get(order.id, [])
            ordered = self._q(sum((line.reservable_quantity for line in lines), ZERO))
            delivered = self._q(
                sum(
                    (
                        min(sent.get(line.id, ZERO), line.reservable_quantity)
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
        return mapped_like(order_rows, result)

    def by_route_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Deliveries per route: dispatched notes only."""
        return self._aggregate_dimension(
            firm_scope=firm_scope,
            window=window,
            column=DeliveryNote.route_id,
            dimension="route",
        )

    def by_salesman_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Deliveries per salesperson: dispatched notes only."""
        return self._aggregate_dimension(
            firm_scope=firm_scope,
            window=window,
            column=DeliveryNote.salesman_id,
            dimension="salesman",
        )

    def by_warehouse_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Deliveries per warehouse: dispatched notes only."""
        return self._aggregate_dimension(
            firm_scope=firm_scope,
            window=window,
            column=DeliveryNote.warehouse_id,
            dimension="warehouse",
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

    @staticmethod
    def _unit_price(
        item: DeliveryNoteLineWrite, source: SalesOrderLine | None
    ) -> Decimal:
        """Return the price this line ships at.

        **Inherited from the order line being shipped** where the caller said
        nothing, for the same reason the discount is: a note ships the deal the
        order struck, and re-deciding the price one document later is how an
        agreement gets quietly rewritten.

        Silence and zero are different answers, as everywhere else here. Zero
        is goods given away; silence is "whatever was agreed". They used to be
        the same value, because the field defaulted to zero -- so a caller that
        omitted it dispatched at no price at all and every document downstream
        inherited the nothing.
        """
        if item.unit_price is not None:
            return Decimal(str(item.unit_price))
        if source is None:
            return ZERO
        return Decimal(str(source.unit_price or ZERO))

    def _line_discount(
        self,
        item: DeliveryNoteLineWrite,
        *,
        source: SalesOrderLine | None,
        unit_price: Decimal,
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
        gross = self._q(self._q(item.current_delivery_quantity) * unit_price)
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

    def _inherited_freight(
        self,
        lines: list[DeliveryNoteLineWrite],
        source_lines: dict[UUID, SalesOrderLine],
    ) -> Decimal:
        """Return the freight a note ships under when the caller says nothing.

        The order's charge, pro-rated by the share of each line leaving on
        this note -- the rule every other inherited amount follows here (a
        rate as itself, an amount by the share shipped). A note raised from an
        order carried none of the order's freight at all, so the charge a
        customer agreed to on the order vanished from the note and then from
        the bill raised on it (D-SELL-36). Zero remains an answer: a caller
        that sends 0 waives it, as with every other amount here.
        """
        total = ZERO
        for item in lines:
            source = source_lines.get(item.sales_order_line_id)
            if source is None or self._q(source.quantity) <= ZERO:
                continue
            total += (
                self._q(source.freight_amount)
                * self._q(item.current_delivery_quantity)
                / self._q(source.quantity)
            )
        return self._q(total)

    def _freight_shares(
        self,
        row: object,
        *,
        freight: Decimal | None,
        taxables: list[Decimal],
    ) -> list[Decimal]:
        """Split what the customer is charged for delivery across the lines.

        Delivery charged by the seller is ancillary to the supply of the goods,
        so it is taxed at the goods' own rate -- which is what apportioning it
        achieves. The mirror image of the bill discount, on the same weights
        and through the same `apportion`, so both sets of shares sum exactly to
        the header figures they split.

        Split on what the lines are worth **after their own discounts**, the
        same weights the bill discount uses. A line discounted to nothing
        carries no freight, which is right: it is worth nothing to deliver.

        Args:
            row: The document, whose header figure is written back.
            freight: What was asked for, or None for nothing.
            taxables: What each line is worth after its own discount.

        Returns:
            One share per line, summing exactly to the freight charged.

        Raises:
            ValidationError: If the freight is negative.

        """
        amount = self._q(freight or ZERO)
        if amount < ZERO:
            raise ValidationError("Freight cannot be negative.")
        row.freight_amount = amount  # type: ignore[attr-defined]
        return apportion(amount, taxables)

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

    @stamps_tax_rules(DeliveryNoteLine, "delivery_note_id")
    def _replace_lines(
        self,
        row: DeliveryNote,
        *,
        lines: list[DeliveryNoteLineWrite],
        bill_percent: Decimal | None,
        bill_amount: Decimal | None,
        freight_amount: Decimal | None = None,
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
        pinned_new: list[tuple[DeliveryNoteLine, UUID]] = []
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
        # `header_discount_amount` did on a purchase order until D-BUY-19
        # moved it onto the lines too. Nothing in this pass touches the
        # database, so every validation below still runs in its own order.
        # Resolved once and used everywhere below, so the price a line is
        # discounted at, taxed at and stored at cannot disagree.
        prices = [
            self._unit_price(item, source_lines.get(item.sales_order_line_id))
            for item in lines
        ]
        priced = [
            self._line_discount(
                item,
                source=source_lines.get(item.sales_order_line_id),
                unit_price=prices[index],
            )
            for index, item in enumerate(lines)
        ]
        shares = self._bill_discount_shares(
            row,
            percent=bill_percent,
            amount=bill_amount,
            taxables=[
                self._q(self._q(item.current_delivery_quantity) * price - line.amount)
                for item, price, line in zip(lines, prices, priced, strict=True)
            ],
        )
        if freight_amount is None:
            freight_amount = self._inherited_freight(lines, source_lines)
        freight = self._freight_shares(
            row,
            freight=freight_amount,
            taxables=[
                self._q(self._q(item.current_delivery_quantity) * price - line.amount)
                for item, price, line in zip(lines, prices, priced, strict=True)
            ],
        )

        for index, item in enumerate(lines):
            bill_share = shares[index]
            freight_share = freight[index]
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
            # No request can lift this cap: a body flag the caller set was all
            # it took to ship 30 more against an order for 12 already shipped
            # in full (D-SELL-31). A tolerance, if a firm wants one, is the
            # firm's setting to make, not the note's.
            if previous_delivered + delivered_qty > ordered_qty:
                raise ValidationError(
                    "Delivery quantity exceeds allowed quantity for the order line."
                )
            remaining_qty = self._q(ordered_qty - previous_delivered - delivered_qty)
            short_qty = self._q(remaining_qty if remaining_qty > ZERO else ZERO)
            gross = self._q(current_qty * prices[index])
            line_discount = priced[index]
            discount = line_discount.amount
            # Freight raises the taxable value; the bill discount
            # lowers it. Both reach the line so the tax is charged on
            # what the customer is actually being asked to pay.
            taxable = self._q(gross - discount - bill_share + freight_share)
            tax = self._tax_amount(
                document_id=row.id,
                line_number=item.line_number,
                shipping_address_id=row.shipping_address_id,
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
                # Stored as the rule gave it: stock moves at this factor (D-CFG-1).
                conversion_factor=Decimal(str(conversion["factor"])),
                conversion_version=conversion["version"],
                unit_price=prices[index],
                discount_percent=line_discount.percent,
                discount_amount=discount,
                bill_discount_amount=bill_share,
                freight_amount=freight_share,
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
                if item.batches is None and source_line.pinned_batch_id is not None:
                    pinned_new.append((line, source_line.pinned_batch_id))
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
                self._trail.clear_lines([obsolete.id])
                # Explicitly, not by the key's CASCADE, which SQLite skips.
                self._session.query(DeliveryNoteLineBatch).filter(
                    DeliveryNoteLineBatch.delivery_note_line_id == obsolete.id
                ).delete(synchronize_session=False)
                self._session.delete(obsolete)
        self._replace_serial_picks(row, lines, actor_id=actor_id)
        self._replace_batch_picks(row, lines, actor_id=actor_id)
        # A new line from an order line that pins a batch starts with that
        # batch picked (backlog 79 row 4), so dispatch ships what the customer
        # asked for; the person may still change it.
        if pinned_new:
            self._session.flush()
            for new_line, batch_id in pinned_new:
                if new_line.delivered_quantity > ZERO:
                    self.set_line_batches(
                        new_line,
                        [
                            DeliveryNoteBatchPick(
                                batch_id=batch_id, quantity=new_line.delivered_quantity
                            )
                        ],
                        label=f"Line {new_line.line_number}",
                        actor_id=actor_id,
                    )
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_batch_picks(
        self,
        row: DeliveryNote,
        lines: list[DeliveryNoteLineWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Record which batches each line takes, as a person chose (backlog 79).

        As with serial picks, only lines that said something are touched:
        ``batches`` absent keeps the line's choice, an empty list clears it
        back to earliest expiry first. Each batch must be the line's product's;
        whether it is in date and free to take is judged at dispatch, when the
        stock is what it is then.

        Raises:
            ValidationError: When a batch is not the line's product's.

        """
        stated = {
            item.line_number: item.batches for item in lines if item.batches is not None
        }
        if not stated:
            return
        self._session.flush()
        persisted = {
            line.line_number: line
            for line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == row.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            ).all()
        }
        for line_number, picks in stated.items():
            self.set_line_batches(
                persisted[line_number],
                picks,
                label=f"Line {line_number}",
                actor_id=actor_id,
            )
        self._session.flush()

    def set_line_batches(
        self,
        line: DeliveryNoteLine,
        picks: Sequence[DeliveryNoteBatchPick],
        *,
        label: str,
        actor_id: UUID,
    ) -> None:
        """Replace one note line's chosen batches; an empty list clears them.

        Shared by the note's own editor and by a counter bill choosing the
        batches of the note it raised for itself (backlog 79 row 2). ``label``
        names the line as the person typed it, which on a counter bill is the
        bill's line, not the note's.

        Raises:
            ValidationError: When a batch is not the line's product's, is named
                twice, or the product is serial-tracked.

        """
        if picks and self._trail.is_serialised(line.product_id):
            raise ValidationError(
                f"{label}: a serial-tracked product leaves from the batch of "
                "each unit picked, so its batches are not chosen separately."
            )
        if len({pick.batch_id for pick in picks}) != len(picks):
            raise ValidationError(
                f"{label}: a batch is named twice; give it once with the whole "
                "quantity."
            )
        for old in self._session.scalars(
            select(DeliveryNoteLineBatch).where(
                DeliveryNoteLineBatch.delivery_note_line_id == line.id
            )
        ).all():
            self._session.delete(old)
        for pick in picks:
            batch = self._session.get(BatchRecord, pick.batch_id)
            if (
                batch is None
                or batch.firm_id != line.firm_id
                or batch.product_id != line.product_id
                or batch.is_deleted
            ):
                raise ValidationError(f"{label}: that batch is not this product's.")
            self._session.add(
                DeliveryNoteLineBatch(
                    delivery_note_line_id=line.id,
                    firm_id=line.firm_id,
                    batch_id=batch.id,
                    quantity=self._q(pick.quantity),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def batch_picks(
        self, line_ids: Sequence[UUID]
    ) -> dict[UUID, list[DeliveryNoteBatchPick]]:
        """Return each line's chosen batches, for a page of lines at once."""
        if not line_ids:
            return {}
        found: dict[UUID, list[DeliveryNoteBatchPick]] = {}
        for pick in self._session.scalars(
            select(DeliveryNoteLineBatch)
            .where(
                DeliveryNoteLineBatch.delivery_note_line_id.in_(list(line_ids)),
                DeliveryNoteLineBatch.is_deleted.is_(False),
            )
            .order_by(DeliveryNoteLineBatch.created_at.asc())
        ).all():
            found.setdefault(pick.delivery_note_line_id, []).append(
                DeliveryNoteBatchPick(batch_id=pick.batch_id, quantity=pick.quantity)
            )
        return found

    def _chosen_split(
        self, line: DeliveryNoteLine, *, as_of: date
    ) -> list[tuple[UUID | None, Decimal]] | None:
        """Return the batches a person chose for a line, checked; None if none.

        They must add up to what the line delivers and each be in date on the
        note's own date. Whether each batch has the stock is refused at
        dispatch by `_assert_chosen_in_stock`, after this line's own hold is
        let go.

        Raises:
            ValidationError: When the quantities disagree or a batch expired.

        """
        picks = self.batch_picks([line.id]).get(line.id, [])
        if not picks:
            return None
        total = sum((pick.quantity for pick in picks), ZERO)
        if self._q(total) != self._q(line.delivered_quantity):
            raise ValidationError(
                f"Line {line.line_number}: the batches chosen add up to "
                f"{self._q(total)}, and the line delivers "
                f"{self._q(line.delivered_quantity)}."
            )
        # The same test dispatch applies when nobody chooses: a batch is out of
        # date on its expiry day, and one marked EXPIRED by hand is too.
        expired = self._session.scalars(
            select(BatchRecord).where(
                BatchRecord.id.in_([pick.batch_id for pick in picks]),
                BatchRecord.expired_condition(as_of),
            )
        ).first()
        if expired is not None:
            when = (
                f" on {expired.expiry_date.isoformat()}"
                if expired.expiry_date is not None
                else ""
            )
            raise ValidationError(
                f"Line {line.line_number}: batch {expired.batch_number} "
                f"expired{when}."
            )
        # Inside the product's stop-selling window (STK-5) it is not sold.
        from app.batch_serial.services.expiry_rules import expiry_rules

        rule = expiry_rules(self._session, line.firm_id, {line.product_id}).get(
            line.product_id
        )
        stop_at = rule.sell_until(as_of) if rule else None
        if stop_at is not None:
            closing = self._session.scalars(
                select(BatchRecord).where(
                    BatchRecord.id.in_([pick.batch_id for pick in picks]),
                    BatchRecord.expiry_date.is_not(None),
                    BatchRecord.expiry_date < stop_at,
                )
            ).first()
            if closing is not None and closing.expiry_date is not None:
                raise ValidationError(
                    f"Line {line.line_number}: batch {closing.batch_number} "
                    f"expires on {closing.expiry_date.isoformat()}, inside the "
                    f"{rule.stop_sale_days if rule else 0} days before expiry "
                    "this product stops being sold."
                )
        return [(pick.batch_id, self._q(pick.quantity)) for pick in picks]

    def _record_drawn(
        self,
        line: DeliveryNoteLine,
        allocation: list[tuple[UUID | None, Decimal]],
        *,
        actor_id: UUID,
    ) -> None:
        """Write down the batches dispatch drew when nobody chose (backlog 79).

        After dispatch a line's picks are what left, chosen or not, so the
        challan prints one row per batch and the note shows the split without
        rebuilding it from movements -- which carry a reference and a product,
        not a line, and cannot tell two lines of one product apart.
        """
        for batch_id, quantity in allocation:
            if batch_id is None:
                continue
            self._session.add(
                DeliveryNoteLineBatch(
                    delivery_note_line_id=line.id,
                    firm_id=line.firm_id,
                    batch_id=batch_id,
                    quantity=self._q(quantity),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _record_fefo_skip(
        self,
        row: DeliveryNote,
        line: DeliveryNoteLine,
        chosen: list[tuple[UUID | None, Decimal]],
        *,
        branch_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
        keep_until: date | None = None,
    ) -> bool:
        """Audit a chosen split that is not the one expiry order would draw (79).

        Choosing a later batch while an earlier one sits on the shelf is the
        decision a pharmacy is asked about afterwards, so the trail keeps both
        splits, and the reason where one was given. Asked after this line's
        own hold is let go, as the allocation it is compared with would be.
        Returns whether it was a skip.
        """
        if line.warehouse_id is None:
            return False
        # A product whose batch is always chosen by hand has no automatic
        # order to have skipped (STK-11).
        if self._inventory.issue_rule(line.product_id) == "PICK":
            return False
        try:
            fefo = self._inventory.allocate_for_dispatch(
                firm_scope=row.firm_id,
                branch_id=branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                quantity=line.delivered_quantity,
                as_of=row.delivery_date,
                keep_until=keep_until,
            )
        except ValidationError:
            fefo = []
        as_split = {str(batch_id): str(self._q(qty)) for batch_id, qty in fefo}
        chose = {str(batch_id): str(self._q(qty)) for batch_id, qty in chosen}
        if as_split == chose:
            return False
        after: dict[str, object] = {"line_number": line.line_number, "chosen": chose}
        if reason and reason.strip():
            after["reason"] = reason.strip()
        record_audit(
            self._session,
            action="delivery_note.fefo_skipped",
            entity_type="delivery_note",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=row.firm_id,
            before_data={"line_number": line.line_number, "earliest_expiry": as_split},
            after_data=after,
        )
        return True

    def _judge_batches(
        self,
        row: DeliveryNote,
        line: DeliveryNoteLine,
        allocation: list[tuple[UUID | None, Decimal]],
        *,
        fefo_skipped: bool,
        policy: BatchSalePolicyService,
        rules: BatchSaleSettingsResponse,
        reason: str | None,
        enforce: bool,
        actor_id: UUID,
        keep_until: date | None = None,
    ) -> list[str]:
        """Judge the batches one line takes under the firm's rules (79 row 6).

        A near-expiry batch leaving is recorded in the audit trail with the
        reason given; where the firm wants a reason for it, or for a FEFO
        skip, a person dispatching without one is refused by line and batch.

        Raises:
            ValidationError: When a rule wants a reason and none was given.

        """
        given = (reason or "").strip()
        notes: list[str] = []
        if keep_until is not None:
            short = policy.short_of(
                [batch_id for batch_id, qty in allocation if qty > ZERO],
                keep_until=keep_until,
            )
            if short:
                named = describe_batches(short, row.delivery_date)
                message = (
                    f"Line {line.line_number}: {named} expires before "
                    f"{keep_until.isoformat()}, the customer's minimum shelf life."
                )
                # A rule about the customer, not a question for whoever
                # dispatches: refused on a bill's own dispatch as well.
                if rules.shelf_life_policy == "BLOCK":
                    raise ValidationError(
                        f"{message} Choose a later batch, or change the "
                        "customer's minimum shelf life."
                    )
                notes.append(message)
                record_audit(
                    self._session,
                    action="delivery_note.short_shelf_life_dispatched",
                    entity_type="delivery_note",
                    entity_id=row.id,
                    actor_id=actor_id,
                    firm_id=row.firm_id,
                    after_data={
                        "line_number": line.line_number,
                        "batches": [str(batch.id) for batch in short],
                        "keep_until": keep_until.isoformat(),
                    },
                )
        near = policy.near_expiry(
            row.firm_id,
            [batch_id for batch_id, qty in allocation if qty > ZERO],
            as_of=row.delivery_date,
            days=rules.near_expiry_days,
        )
        if near:
            named = describe_batches(near, row.delivery_date)
            if enforce and rules.near_expiry_policy == "REASON" and not given:
                raise ValidationError(
                    f"Line {line.line_number}: {named} is near expiry, and the "
                    "firm asks for a reason before a near-expiry batch is "
                    "dispatched."
                )
            notes.append(f"Line {line.line_number}: near expiry -- {named}.")
            after: dict[str, object] = {
                "line_number": line.line_number,
                "batches": [str(batch.id) for batch in near],
                "described": named,
            }
            if given:
                after["reason"] = given
            record_audit(
                self._session,
                action="delivery_note.near_expiry_dispatched",
                entity_type="delivery_note",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=row.firm_id,
                after_data=after,
            )
        if fefo_skipped:
            if enforce and rules.fefo_skip_policy == "REASON" and not given:
                raise ValidationError(
                    f"Line {line.line_number}: the batches chosen skip an "
                    "earlier-expiring batch, and the firm asks for a reason "
                    "when that happens."
                )
            notes.append(
                f"Line {line.line_number}: a later batch was chosen ahead of an "
                "earlier-expiring one."
            )
        return notes

    def _replace_serial_picks(
        self,
        row: DeliveryNote,
        lines: list[DeliveryNoteLineWrite],
        *,
        actor_id: UUID,
    ) -> None:
        """Record which serialised units each line ships.

        Only lines that said something are touched: ``serial_ids`` absent
        leaves a line's picks as they were, and an empty list clears them.
        The count is not checked here -- a draft may be picked a unit at a
        time -- but dispatch refuses until it matches (D-STK-4).
        """
        stated = {
            item.line_number: item.serial_ids
            for item in lines
            if item.serial_ids is not None
        }
        if not stated:
            return
        self._session.flush()
        persisted = {
            line.line_number: line
            for line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == row.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            ).all()
        }
        for line_number, serial_ids in stated.items():
            line = persisted[line_number]
            self._trail.replace_picks(
                self._line_ref(line),
                serial_ids,
                check=self._on_the_shelf(line.warehouse_id),
                actor_id=actor_id,
            )

    @staticmethod
    def _on_the_shelf(
        warehouse_id: UUID | None,
    ) -> Callable[[SerialNumber], str | None]:
        """Return the check a picked unit must pass to leave this shelf."""

        def _may_leave(serial: SerialNumber) -> str | None:
            """Refuse a unit that is not on this line's shelf."""
            if serial.status != SerialStatus.AVAILABLE.value:
                return f"is {serial.status}, not AVAILABLE."
            if serial.warehouse_id != warehouse_id:
                return "is not in the warehouse this line ships from."
            return None

        return _may_leave

    def restate_serial_picks(
        self,
        note_id: UUID,
        picks: dict[UUID, list[UUID]],
        *,
        firm_scope: UUID,
        raised_by_sales_invoice_id: UUID,
        actor_id: UUID,
    ) -> None:
        """Change the units a bill's own note will ship, before it ships.

        A bill that dispatches its own goods hands its picks to the note it
        raises, and the note is approved at once -- so editing the draft bill
        had nowhere to change them (D-SELL-33). Only that bill may, and only
        while the note waits for the bill's approval to dispatch it.

        Args:
            note_id: The note the bill raised.
            picks: The units each note line ships, keyed by note line id.
            firm_scope: The owning firm.
            raised_by_sales_invoice_id: The bill restating them.
            actor_id: The user editing the bill.

        Raises:
            ValidationError: If the note is not that bill's, has shipped, or a
                line is not the note's.

        """
        note = self.get_note(note_id, firm_scope=firm_scope)
        if (
            note.raised_by_sales_invoice_id != raised_by_sales_invoice_id
            or note.status != DeliveryNoteStatus.APPROVED.value
        ):
            raise ValidationError(
                "Serial numbers are picked on the delivery note that ships the "
                "goods; this bill names a note that has already been dispatched."
            )
        lines = {
            line.id: line
            for line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            ).all()
        }
        for line_id, serial_ids in picks.items():
            line = lines.get(line_id)
            if line is None:
                raise ValidationError(
                    f"A bill line names a line that is not on "
                    f"{note.delivery_note_number}."
                )
            self._trail.replace_picks(
                self._line_ref(line),
                serial_ids,
                check=self._on_the_shelf(line.warehouse_id),
                actor_id=actor_id,
            )
        self._session.flush()

    def _units_by_batch(
        self,
        line_ref: LineRef,
        picks: list[Pick],
        *,
        branch_id: UUID,
        warehouse_id: UUID,
        storage_node_id: UUID | None,
        as_of: date,
    ) -> dict[UUID | None, list[Pick]] | None:
        """Group picked units by the batch each one belongs to.

        None when no picked unit names a batch, which leaves the batches to
        the allocator, earliest expiry first. Where they do, the unit decides:
        SAP Business One and Odoo ship a serial from the lot it belongs to,
        and a batch chosen by expiry would record a different lot against the
        very unit the customer holds. Each batch must still hold the units
        here and must not have expired on the note's date -- the same two
        refusals the allocator gives, said about the unit that caused them.
        """
        if not any(serial.batch_id is not None for _pick, serial in picks):
            return None
        label = line_ref.label(self._trail.product(line_ref.product_id))
        loose = [serial.serial_number for _pick, serial in picks if not serial.batch_id]
        if loose:
            raise ValidationError(
                f"{label}: serial {', '.join(loose)} names no batch while the "
                "line's other units do; give each unit its batch first."
            )
        grouped: dict[UUID | None, list[Pick]] = defaultdict(list)
        for pick, serial in picks:
            grouped[serial.batch_id].append((pick, serial))
        batches = {
            batch.id: batch
            for batch in self._session.scalars(
                select(BatchRecord).where(
                    BatchRecord.id.in_([key for key in grouped if key is not None])
                )
            ).all()
        }
        for batch_id, share in grouped.items():
            batch = batches.get(batch_id) if batch_id is not None else None
            number = batch.batch_number if batch is not None else str(batch_id)
            if (
                batch is not None
                and batch.expiry_date is not None
                # Out of date on its expiry date, as a batch is (D-STK-17).
                and batch.expiry_date <= as_of
            ):
                raise ValidationError(
                    f"{label}: serial {share[0][1].serial_number} is in batch "
                    f"{number}, which expired on {batch.expiry_date.isoformat()}."
                )
            held = self._q(
                self._session.scalar(
                    select(
                        func.coalesce(func.sum(InventoryRecord.available_quantity), 0)
                    ).where(
                        InventoryRecord.branch_id == branch_id,
                        InventoryRecord.warehouse_id == warehouse_id,
                        InventoryRecord.storage_node_id == storage_node_id,
                        InventoryRecord.product_id == line_ref.product_id,
                        InventoryRecord.batch_id == batch_id,
                        InventoryRecord.is_deleted.is_(False),
                    )
                )
            )
            if held < len(share):
                raise ValidationError(
                    f"{label}: {len(share)} of the picked units are in batch "
                    f"{number}, which has {held} available here."
                )
        return dict(grouped)

    @staticmethod
    def _line_ref(line: DeliveryNoteLine) -> LineRef:
        """Describe a note line to the serial trail."""
        return LineRef(
            firm_id=line.firm_id,
            document_type=DELIVERY_NOTE,
            document_id=line.delivery_note_id,
            line_id=line.id,
            line_number=line.line_number,
            product_id=line.product_id,
        )

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

    def _warehouse_branch(self, warehouse_id: UUID, *, fallback: UUID) -> UUID:
        """Return the branch a warehouse belongs to, or ``fallback`` if unknown."""
        branch_id = self._session.scalar(
            select(Warehouse.branch_id).where(Warehouse.id == warehouse_id)
        )
        return branch_id if branch_id is not None else fallback

    def _reservation_location(
        self, source_line: SalesOrderLine, note: DeliveryNote
    ) -> _HeldAt:
        """Say where the sales order holds the stock this line ships.

        ``SalesOrderService._reserve_inventory`` reserves at the order's
        branch, and at the line's warehouse or else the order's, so the
        release reads the same three. A line whose order cannot be read falls
        back to the note's own location, which is what dispatch did before.
        """
        order = self._session.get(SalesOrder, source_line.sales_order_id)
        if order is None:
            return _HeldAt(
                branch_id=note.branch_id,
                warehouse_id=source_line.warehouse_id or note.warehouse_id,
                storage_node_id=source_line.storage_node_id,
            )
        return _HeldAt(
            branch_id=order.branch_id,
            warehouse_id=source_line.warehouse_id or order.warehouse_id,
            storage_node_id=source_line.storage_node_id,
        )

    def _dispatch_inventory(
        self,
        *,
        row: DeliveryNote,
        actor_id: UUID,
        batch_reason: str | None = None,
        judge_batches: bool = False,
    ) -> list[str]:
        """Move every line's stock out, and say what the batch rules noticed."""
        policy = BatchSalePolicyService(self._session)
        rules = policy.settings_response(row.firm_id)
        # The customer's minimum shelf life, as a date the goods must last to
        # (backlog 79 row 6); None when they ask for none.
        keep_until = policy.keep_until(row.customer_id, on=row.delivery_date)
        batch_notes: list[str] = []
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
        services = stockless_products(
            self._session, (line.product_id for line in lines)
        )
        for line in lines:
            if line.inventory_transaction_id is not None:
                continue
            if line.product_id in services:
                # A service is delivered without stock leaving (backlog 87
                # #3): the order's nominal hold is let go, and there is no
                # movement, no batch and no cost of goods sold.
                self._deliver_service(line, actor_id=actor_id)
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
            # A serial-tracked product leaves unit by unit: the storekeeper
            # named the units on the note, one per unit leaving, and each has
            # to still be on this line's shelf. Refused before anything moves
            # so a short pick leaves the note APPROVED and the stock untouched
            # (D-STK-4).
            line_ref = self._line_ref(line)
            serialised = self._trail.is_serialised(line.product_id)
            picks = self._trail.line_picks(line.id) if serialised else []
            if serialised:
                self._trail.assert_count(
                    line_ref,
                    len(picks),
                    line.delivered_quantity,
                    verb="ships",
                    where="delivery note",
                )
                self._trail.check_issuable(
                    line_ref, picks, warehouse_id=line.warehouse_id
                )
            # Goods leave from the line's warehouse, which belongs to its own
            # branch -- not necessarily the note's, which comes from the order.
            # Pairing the note's branch with another branch's warehouse looked
            # for stock at a location holding nothing and refused the dispatch
            # (plan item 9.12, 2026-09-13).
            goods_branch_id = self._warehouse_branch(
                line.warehouse_id, fallback=row.branch_id
            )
            available, _ = self._stock_snapshot(
                firm_id=row.firm_id,
                branch_id=goods_branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
            )
            # What this line's order holds is released by this dispatch, so
            # it counts towards what can ship.
            own_hold = self._q(
                min(source_line.reserved_quantity, line.delivered_quantity)
            )
            # A kit shipped beyond what is assembled is assembled from its
            # components first, in this transaction (STK-15).
            if available + own_hold < line.delivered_quantity and KitService(
                self._session
            ).assemble_for_dispatch(
                firm_id=row.firm_id,
                branch_id=goods_branch_id,
                warehouse_id=line.warehouse_id,
                product_id=line.product_id,
                shortfall=line.delivered_quantity - available - own_hold,
                on=row.delivery_date,
                reference=row.delivery_note_number,
                actor_id=actor_id,
            ):
                available, _ = self._stock_snapshot(
                    firm_id=row.firm_id,
                    branch_id=goods_branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                )
            if available + own_hold < line.delivered_quantity:
                raise ValidationError("Insufficient available stock for dispatch line.")
            chosen = (
                None
                if serialised
                else self._chosen_split(line, as_of=row.delivery_date)
            )
            release_qty = self._q(
                min(source_line.reserved_quantity, line.delivered_quantity)
            )
            if release_qty < line.delivered_quantity:
                raise ValidationError(
                    "Reservation is insufficient for dispatch quantity."
                )
            if release_qty > ZERO:
                # The hold is let go where the order made it, which need not
                # be where the goods leave: an order reserved in one warehouse
                # and shipped from another released from the shipping one, so
                # dispatch was refused ("Reserved quantity cannot become
                # negative") or took another order's hold while the original
                # stayed on the shelf for ever (plan item 9.12, 2026-09-13).
                # Within the location the batches go in expiry order, so the
                # batch freed is the one the allocation below draws from when
                # the two locations are the same.
                held_at = self._reservation_location(source_line, row)
                release_split = self._inventory.allocate_for_release(
                    firm_scope=row.firm_id,
                    branch_id=held_at.branch_id,
                    warehouse_id=held_at.warehouse_id,
                    storage_node_id=held_at.storage_node_id,
                    product_id=line.product_id,
                    quantity=release_qty,
                    # The batches a person chose are let go first, so this
                    # order's own hold never stands in the way of its own pick.
                    prefer=[batch_id for batch_id, _ in chosen or [] if batch_id],
                    # And before either, what this order itself holds: the
                    # row's reserved figure is every order's, and letting go
                    # by expiry alone freed somebody else's batch (D-SELL-58).
                    own=self._inventory.held_by_reference(
                        firm_scope=row.firm_id,
                        reference_number=row.sales_order_reference,
                        product_id=line.product_id,
                        warehouse_id=held_at.warehouse_id,
                    ),
                )
                entered_release = self._q(
                    line.current_delivery_quantity + line.free_quantity
                )
                released = None
                for batch_id, freed in release_split:
                    posted = self._inventory.release_sales_order_reservation(
                        firm_scope=row.firm_id,
                        actor_id=actor_id,
                        branch_id=held_at.branch_id,
                        warehouse_id=held_at.warehouse_id,
                        storage_node_id=held_at.storage_node_id,
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
                        line_conversion=LineConversion(
                            line.conversion_factor, line.inventory_uom_id
                        ),
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
            fefo_skipped = False
            by_batch = self._units_by_batch(
                line_ref,
                picks,
                branch_id=goods_branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                as_of=row.delivery_date,
            )
            if by_batch is not None:
                # Units that carry a batch leave from it: the unit named is
                # the unit shipped, so its batch is not the allocator's to
                # choose.
                allocation = [
                    (batch_id, Decimal(len(share)))
                    for batch_id, share in by_batch.items()
                ]
                shares = list(by_batch.values())
            elif chosen is not None:
                # A person chose the batches (backlog 79): those, and only
                # those, leave.
                allocation = chosen
                self._assert_chosen_in_stock(
                    line, chosen, row=row, branch_id=goods_branch_id
                )
                fefo_skipped = self._record_fefo_skip(
                    row,
                    line,
                    chosen,
                    branch_id=goods_branch_id,
                    actor_id=actor_id,
                    reason=batch_reason,
                    keep_until=keep_until,
                )
                shares = self._trail.deal(
                    picks, [allocated for _, allocated in allocation]
                )
            else:
                allocation = self._inventory.allocate_for_dispatch(
                    firm_scope=row.firm_id,
                    branch_id=goods_branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    quantity=line.delivered_quantity,
                    # Expired stock is not dispatched, judged on the note's
                    # own date rather than today, so rebuilding a year of
                    # history posts what it posted at the time.
                    as_of=row.delivery_date,
                    # Nor is a batch too short-dated for this customer.
                    keep_until=keep_until,
                )
                shares = self._trail.deal(
                    picks, [allocated for _, allocated in allocation]
                )
            batch_notes.extend(
                self._judge_batches(
                    row,
                    line,
                    allocation,
                    fefo_skipped=fefo_skipped,
                    policy=policy,
                    rules=rules,
                    reason=batch_reason,
                    enforce=judge_batches,
                    actor_id=actor_id,
                    keep_until=keep_until,
                )
            )
            entered_total = self._q(line.current_delivery_quantity + line.free_quantity)
            dispatched = None
            for index, (batch_id, allocated) in enumerate(allocation):
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
                    branch_id=goods_branch_id,
                    warehouse_id=line.warehouse_id,
                    storage_node_id=line.storage_node_id,
                    product_id=line.product_id,
                    reference_number=row.delivery_note_number,
                    transaction_date=row.delivery_date,
                    dispatch_quantity=allocated,
                    entered_quantity=share,
                    entered_uom_id=line.sales_uom_id,
                    conversion_version=line.conversion_version,
                    line_conversion=LineConversion(
                        line.conversion_factor, line.inventory_uom_id
                    ),
                    remarks=line.remarks or row.remarks,
                    batch_id=batch_id,
                    serial_id=self._trail.single_serial(shares[index], allocated),
                )
                if shares[index]:
                    self._trail.mark_sold(
                        line_ref,
                        shares[index],
                        movement_id=posted.id,
                        owner=self._customer_name(row.customer_id),
                        reference=row.delivery_note_number,
                        actor_id=actor_id,
                    )
                issued_cost += self._issue_cost(posted.id)
                if dispatched is None:
                    dispatched = posted
                    line.batch_id = batch_id
            if dispatched is None:
                raise ValidationError("Insufficient available stock for dispatch line.")
            if chosen is None:
                self._record_drawn(line, allocation, actor_id=actor_id)
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
        return batch_notes

    def _deliver_service(self, line: DeliveryNoteLine, *, actor_id: UUID) -> None:
        """Let go of what the order held for a service line; move nothing."""
        source_line = self._session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.id == line.sales_order_line_id)
        )
        if source_line is None:
            raise ValidationError("Sales order line not found for dispatch.")
        source_line.reserved_quantity = self._q(
            max(source_line.reserved_quantity - line.delivered_quantity, ZERO)
        )
        line.updated_by = actor_id

    def _apply_transporter(self, row: DeliveryNote, data: DeliveryNoteCreate) -> None:
        """Name the note's carrier and fill what the request left blank.

        The master's name, GSTIN (or TRANSIN) and usual mode are copied onto
        the note wherever the request did not type one, so the challan and
        the e-way bill go on reading the note's own columns (backlog 87 #5).
        Absent leaves the note's carrier alone; null takes it off and keeps
        the text.

        Raises:
            ValidationError: If the transporter is not in use any more.

        """
        if "transporter_id" not in data.model_fields_set:
            return
        row.transporter_id = data.transporter_id
        if data.transporter_id is None:
            return
        carrier = TransporterService(self._session).get(
            data.transporter_id, row.firm_id
        )
        if not carrier.is_active:
            raise ValidationError(
                f"{carrier.name} is marked inactive. Choose another transporter "
                "or make it active again."
            )
        filled = (
            ("transporter_name", carrier.name),
            ("transporter_gstin", carrier.gstin or carrier.transporter_ref),
            ("transport_mode", carrier.default_mode),
        )
        for name, value in filled:
            if getattr(data, name) is None and value:
                setattr(row, name, value)

    def _assert_chosen_in_stock(
        self,
        line: DeliveryNoteLine,
        chosen: Sequence[tuple[UUID | None, Decimal]],
        *,
        row: DeliveryNote,
        branch_id: UUID,
    ) -> None:
        """Refuse a line whose chosen batches do not each hold what is asked.

        ``allocate_for_dispatch`` refuses a line it cannot cover; a line whose
        batches a person chose never reaches it, and the movement itself does
        not refuse, so a batch holding 2 shipped 3 and stood at -1 (D-SELL-50,
        2026-10-05). Judged after the line's own hold is let go, so stock the
        order reserved for this line counts as its own.
        """
        if line.warehouse_id is None:
            return
        asked: dict[UUID | None, Decimal] = {}
        for batch_id, quantity in chosen:
            asked[batch_id] = asked.get(batch_id, ZERO) + Decimal(str(quantity))
        for batch_id, quantity in asked.items():
            available = self._inventory.available_at(
                firm_scope=row.firm_id,
                branch_id=branch_id,
                warehouse_id=line.warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                batch_id=batch_id,
            )
            if quantity <= available:
                continue
            batch = (
                None if batch_id is None else self._session.get(BatchRecord, batch_id)
            )
            name = (
                "Stock with no batch"
                if batch is None
                else f"Batch {batch.batch_number}"
            )
            held = self._q(max(available, ZERO))
            raise ValidationError(
                f"Line {line.line_number}: {name} holds {held} available here, "
                f"and {self._q(quantity)} is chosen from it. Choose less from "
                "it, or another batch."
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
        document_id: UUID | None = None,
        line_number: int | None = None,
        shipping_address_id: UUID | None = None,
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
            # The supply's own nature, not just the document's name: a buyer in
            # another state is charged IGST (D-CMP-1).
            transaction_type=self._tax.outward_transaction_type(
                "DELIVERY_NOTE",
                firm_id=firm_id,
                branch_id=branch_id,
                customer_id=customer_id,
                shipping_address_id=shipping_address_id,
            ),
            transaction_date=delivery_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={
                "source": "delivery_note",
                "document_type": "DELIVERY_NOTE",
            },
        )
        response = self._tax.simulate(
            request,
            firm_scope=firm_id,
            actor_id=actor_id,
            document_id=document_id,
            line_number=line_number,
        )
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
        # A line's quantity is refused here, where it is written, rather
        # than when its stock moves (D-CFG-11).
        assert_quantity_fits_unit(
            self._session,
            quantity=quantity,
            uom_id=sales_uom_id or inventory_uom_id,
            product_id=product_id,
            firm_id=firm_id,
        )
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
        details: dict[str, object] | None = None,
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
                    **(details or {}),
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

    @staticmethod
    def _refuse_unless_order_open(order: SalesOrder) -> None:
        """Refuse to raise or move a note forward on an order that is not open.

        A sales order's status, compared against the sales order's own enum.
        This once read `DeliveryNoteStatus` members, which agreed only because
        both enums spell APPROVED and CLOSED the same. CLOSED was accepted as
        well, so goods could still be raised and shipped against an order that
        had been closed -- and whose reservations closing had released
        (D-SELL-11). Closing is how a firm says "nothing more on this order";
        only create was ever asked, so a note drafted or approved before the
        close still went out. Every step that moves a note forward asks now.
        """
        if order.status in {
            SalesOrderStatus.APPROVED.value,
            SalesOrderStatus.PARTIALLY_DELIVERED.value,
            SalesOrderStatus.DELIVERED.value,
        }:
            return
        raise ValidationError(
            "Delivery notes can be raised only against an approved sales order; "
            f"{order.order_number} is {order.status}."
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

    def _to_ship(self, note_id: UUID) -> list[tuple[str, Decimal, Decimal]]:
        """Return what a note's lines ship: order line, charged and free."""
        return sorted(
            (
                str(line.sales_order_line_id),
                self._q(line.current_delivery_quantity),
                self._q(line.free_quantity),
            )
            for line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == note_id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            )
        )

    @staticmethod
    def _refuse_if_held(order: SalesOrder) -> None:
        """Refuse to move a note forward while its order is on hold.

        The point of a hold. A flag the engine records that changed no outcome
        would be a switch somebody turns on believing the goods have stopped
        moving, while they carry on out of the warehouse. Only a note's create
        asked, so a note drafted before the hold was edited, approved and
        dispatched while the order read "on hold" (D-SELL-5, driven
        2026-09-19).

        The reason is quoted rather than run into the sentence: it is
        somebody's own words and usually ends with a full stop of its own,
        which read as "the LC.." when the sentence added another.
        """
        if not order.is_on_hold:
            return
        reason = (order.hold_reason or "").strip() or "no reason recorded"
        raise ValidationError(
            f"{order.order_number} is on hold and cannot be dispatched "
            f'("{reason}"). Release it first.'
        )

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
                # A shipped state counts only when the goods left: a note
                # closed before this refused it never dispatched (D-SELL-4).
                or_(
                    DeliveryNote.status.not_in(sorted(SHIPPED_STATES)),
                    goods_have_left_clause(),
                ),
            )
        )
        if exclude_delivery_note_id is not None:
            statement = statement.where(DeliveryNote.id != exclude_delivery_note_id)
        return self._q(self._session.scalar(statement) or ZERO)

    def _aggregate_dimension(
        self,
        *,
        firm_scope: UUID,
        window: ReportWindow,
        column: InstrumentedAttribute[UUID | None],
        dimension: str,
    ) -> list[DeliveryNoteByDimensionRecord]:
        """Count, value and quantity of the shipped notes, grouped in SQL.

        The by-route, by-salesman and by-warehouse reports say "delivered",
        and used to sum every non-cancelled note -- a DRAFT's typed quantity
        raised the warehouse's delivered total (D-RPT-9). Only a dispatched
        note has delivered anything, and `goods_have_left_clause` is the one
        test of that (D-SELL-4). Grouped in SQL: reading every note whole to
        add them up took 4-6 s for a year on the volume firm (backlog 56 C,
        step 4).
        """
        shipped = (
            DeliveryNote.firm_id == firm_scope,
            DeliveryNote.is_deleted.is_(False),
            goods_have_left_clause(),
            *window.dated(DeliveryNote.delivery_date),
        )
        counts: dict[UUID | None, int] = {}
        values: dict[UUID | None, Decimal] = {}
        for key, count, total in self._session.execute(
            select(
                column,
                func.count(),
                func.coalesce(func.sum(DeliveryNote.grand_total), 0),
            )
            .where(*shipped)
            .group_by(column)
        ).all():
            counts[key] = int(count)
            values[key] = Decimal(str(total))
        quantities: dict[UUID | None, Decimal] = {
            key: Decimal(str(total))
            for key, total in self._session.execute(
                select(
                    column,
                    func.coalesce(func.sum(DeliveryNoteLine.delivered_quantity), 0),
                )
                .join(
                    DeliveryNoteLine,
                    DeliveryNoteLine.delivery_note_id == DeliveryNote.id,
                )
                .where(*shipped, DeliveryNoteLine.is_deleted.is_(False))
                .group_by(column)
            ).all()
        }
        labels: dict[UUID | None, str] = {None: UNASSIGNED}
        # Every name in one read for the whole report, whichever dimension it
        # is grouped by: the route and warehouse labels used to cost one query
        # per distinct key (D-RPT-19).
        keys = {key for key in counts if key is not None}
        if dimension == "salesman":
            for person, person_name in self._salesman_names(keys).items():
                labels[person] = person_name
        elif dimension == "route":
            # A route profile has no name of its own -- it is a one-to-one
            # extension of a territory, and the territory carries the name.
            # Reading ``profile.name`` raised AttributeError for every firm
            # that ran this report with a route on any note.
            for profile_id, route_name in self._session.execute(
                select(TerritoryRouteProfile.id, SalesTerritoryNode.name)
                .join(
                    SalesTerritoryNode,
                    TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                )
                .where(TerritoryRouteProfile.id.in_(keys))
            ).all():
                if route_name:
                    labels[profile_id] = route_name
        else:
            for warehouse_id, warehouse_name in self._session.execute(
                select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(keys))
            ).all():
                labels[warehouse_id] = warehouse_name
        return [
            DeliveryNoteByDimensionRecord(
                dimension_id=key,
                dimension_name=labels.get(key, str(key)),
                note_count=counts[key],
                delivered_quantity=self._q(quantities.get(key, ZERO)),
                total_value=self._q(values[key]),
            )
            for key in sorted(
                counts.keys(), key=lambda item: labels.get(item, str(item))
            )
        ]

    def _duplicate_warnings(self, rows: Sequence[DeliveryNote]) -> dict[UUID, str]:
        """Answer `_duplicate_warning` for a page of notes in one query.

        The same test -- another live, uncancelled note of the firm for the
        same order, date and vehicle, a missing order or vehicle matching a
        missing one -- read once for every date on the page.
        """
        holders: dict[tuple[object, ...], set[UUID]] = defaultdict(set)
        for found in self._session.execute(
            select(
                DeliveryNote.id,
                DeliveryNote.firm_id,
                DeliveryNote.sales_order_id,
                DeliveryNote.delivery_date,
                DeliveryNote.vehicle,
            ).where(
                DeliveryNote.firm_id.in_({row.firm_id for row in rows}),
                DeliveryNote.delivery_date.in_({row.delivery_date for row in rows}),
                DeliveryNote.is_deleted.is_(False),
                DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
            )
        ):
            holders[tuple(found[1:])].add(found[0])
        return {
            row.id: (
                "Potential duplicate dispatch detected for this "
                "sales order/date/vehicle."
            )
            for row in rows
            if holders.get(
                (row.firm_id, row.sales_order_id, row.delivery_date, row.vehicle),
                set(),
            )
            - {row.id}
        }

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

    def _products_named(self, lines: list[DeliveryNoteLine]) -> dict[UUID, Product]:
        """Return the products a note's lines name, keyed by id.

        One query for the whole document rather than one per line. Soft-deleted
        products are included deliberately: a line names what was dispatched,
        and a product retired since still has to be nameable on the note that
        shipped it.
        """
        ids = {line.product_id for line in lines}
        if not ids:
            return {}
        return {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(ids))
            ).all()
        }

    def _line_response(
        self, row: DeliveryNoteLine, product: Product | None = None
    ) -> DeliveryNoteLineResponse:
        return DeliveryNoteLineResponse.model_validate(row).model_copy(
            update={
                "product_code": getattr(product, "code", None),
                "product_name": getattr(product, "name", None),
            }
        )
