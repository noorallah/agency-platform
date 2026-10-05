"""Transactional service for enterprise purchase management."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.gating import assert_feature_fields
from app.business.models.framework import AttributeEntityType
from app.business.services import document_attributes
from app.common.audit.services import record_audit
from app.common.firm_metadata import platform_reader
from app.common.report_names import vendors_matching
from app.core.database.batch import children_by_parent
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.chunks import chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO
from app.core.utils.pricing import (
    LinePrice,
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
    resolve_supplier_unit_price,
)
from app.document_framework.models import (
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
from app.finance.currency import check_currency, normalize_currency
from app.goods_receipt.models import GoodsReceipt
from app.identity.models import User
from app.products.models import Product
from app.purchase.models import (
    PurchaseAttachment,
    PurchaseDeliverySchedule,
    PurchaseNote,
    PurchaseOrder,
    PurchaseOrderHistory,
    PurchaseOrderLine,
    PurchaseOrderRevision,
)
from app.purchase.schemas import (
    PurchaseAttachmentResponse,
    PurchaseDeliveryScheduleResponse,
    PurchaseLineWrite,
    PurchaseNoteResponse,
    PurchaseOrderAmend,
    PurchaseOrderByBuyerRecord,
    PurchaseOrderByProductRecord,
    PurchaseOrderByVendorRecord,
    PurchaseOrderCreate,
    PurchaseOrderImportRequest,
    PurchaseOrderLineResponse,
    PurchaseOrderListFilters,
    PurchaseOrderOverdueRecord,
    PurchaseOrderPendingRecord,
    PurchaseOrderPreview,
    PurchaseOrderRegisterRecord,
    PurchaseOrderResponse,
    PurchaseOrderRevisionResponse,
    PurchaseOrderStatus,
    PurchaseOrderUpdate,
    PurchaseQuantityHint,
    PurchaseSummary,
)
from app.purchase.services.approval_limit import PurchaseApprovalLimitService
from app.purchase.services.line_quantities import (
    LineQuantities,
    billing_status,
    is_complete,
    line_status,
    order_line_quantities,
)
from app.sales.services.document_preview import purchase_line_companions
from app.supplier_schemes.schemas import SupplierSchemeSuggestion
from app.supplier_schemes.services import LineScheme, line_schemes
from app.tax.models import TaxProfile
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.place_of_supply import PURCHASE_INTERSTATE
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
from app.vendors.services.order_quantities import quantity_hints


def _batch_is_expired(batch: BatchRecord) -> bool:
    """Return whether a batch has expired as of today.

    Expiry is decided by the date. Nothing sets ``status = 'EXPIRED'``, so the
    original status check never fired and expired stock could be purchased.
    """
    if batch.status == "DESTROYED":
        return False
    if batch.status == "EXPIRED":
        return True
    return batch.expiry_date is not None and batch.expiry_date <= utc_now().date()


class PurchaseService(TransactionalDocumentService):
    """Coordinate purchase order lifecycle, calculations, and integrations."""

    DOCUMENT = DocumentTypeSpec(
        code="PURCHASE_ORDER",
        name="Purchase Order",
        description="Reusable purchase document type.",
        category="PURCHASE",
        module="purchase",
        prefix="PO",
        include_branch_code=True,
        include_company_code=True,
        rule_code="PURCHASE_ORDER_DEFAULT",
        rule_name="Purchase Order Default Numbering",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 10, allows_edit=True),
            # Sent for approval but not yet approved. Declared here as well as
            # in the status enum, because a lifecycle event naming a state the
            # framework does not know is a timeline entry nobody can read.
            DocumentStateSpec("SUBMITTED", "Submitted", 15, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 20, allows_edit=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 90, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 100, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._uom = UomService(session)
        self._tax = TaxRuleService(session)
        #: The last timestamp handed to a history row by this instance, so the
        #: next one can be made strictly later. See `_history_time`.
        self._last_history_at: datetime | None = None

    def list_orders(
        self,
        *,
        firm_scope: UUID,
        filters: PurchaseOrderListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[PurchaseOrder], int]:
        """List orders."""
        statement = select(PurchaseOrder).where(PurchaseOrder.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(PurchaseOrder.is_deleted.is_(False))
            count = count.where(PurchaseOrder.is_deleted.is_(False))
        if filters.vendor_id is not None:
            statement = statement.where(PurchaseOrder.vendor_id == filters.vendor_id)
            count = count.where(PurchaseOrder.vendor_id == filters.vendor_id)
        if filters.status is not None:
            statement = statement.where(PurchaseOrder.status == filters.status.value)
            count = count.where(PurchaseOrder.status == filters.status.value)
        if filters.branch_id is not None:
            statement = statement.where(PurchaseOrder.branch_id == filters.branch_id)
            count = count.where(PurchaseOrder.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                PurchaseOrder.warehouse_id == filters.warehouse_id
            )
            count = count.where(PurchaseOrder.warehouse_id == filters.warehouse_id)
        if filters.buyer_id is not None:
            statement = statement.where(PurchaseOrder.buyer_id == filters.buyer_id)
            count = count.where(PurchaseOrder.buyer_id == filters.buyer_id)
        if filters.sent is not None:
            sent_clause = (
                PurchaseOrder.sent_at.is_not(None)
                if filters.sent
                else PurchaseOrder.sent_at.is_(None)
            )
            statement = statement.where(sent_clause)
            count = count.where(sent_clause)
        if filters.purchase_type is not None:
            statement = statement.where(
                PurchaseOrder.purchase_type == filters.purchase_type.value
            )
            count = count.where(
                PurchaseOrder.purchase_type == filters.purchase_type.value
            )
        if filters.created_from is not None:
            statement = statement.where(
                PurchaseOrder.purchase_date >= filters.created_from
            )
            count = count.where(PurchaseOrder.purchase_date >= filters.created_from)
        if filters.created_to is not None:
            statement = statement.where(
                PurchaseOrder.purchase_date <= filters.created_to
            )
            count = count.where(PurchaseOrder.purchase_date <= filters.created_to)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                PurchaseOrder.po_number.ilike(term),
                PurchaseOrder.reference_number.ilike(term),
                PurchaseOrder.external_reference.ilike(term),
                PurchaseOrder.remarks.ilike(term),
                PurchaseOrder.vendor_id.in_(vendors_matching(term)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = getattr(PurchaseOrder, sort_by, PurchaseOrder.created_at)
        order_by = sort_column.desc() if descending else sort_column.asc()
        rows = list(
            self._session.scalars(
                statement.order_by(
                    order_by,
                    # Newest first within the chosen column, then a stable key.
                    PurchaseOrder.created_at.desc(),
                    PurchaseOrder.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> PurchaseSummary:
        """Summarize purchase orders for the visible firm scope.

        Counted and summed in SQL, one row per status, rather than loading every
        order the firm ever raised (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    PurchaseOrder.status,
                    func.count(),
                    func.coalesce(func.sum(PurchaseOrder.grand_total), 0),
                )
                .where(
                    PurchaseOrder.firm_id == firm_scope,
                    PurchaseOrder.is_deleted.is_(False),
                )
                .group_by(PurchaseOrder.status)
            ).all()
        }

        def count(status: PurchaseOrderStatus) -> int:
            """Return how many documents are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        not_overdue = (
            PurchaseOrderStatus.CANCELLED.value,
            PurchaseOrderStatus.CLOSED.value,
            PurchaseOrderStatus.RECEIVED.value,
        )
        overdue = int(
            self._session.scalar(
                select(func.count()).where(
                    PurchaseOrder.firm_id == firm_scope,
                    PurchaseOrder.is_deleted.is_(False),
                    PurchaseOrder.expected_delivery_date.is_not(None),
                    PurchaseOrder.expected_delivery_date < utc_now().date(),
                    PurchaseOrder.status.not_in(not_overdue),
                )
            )
            or 0
        )
        open_statuses = (
            PurchaseOrderStatus.SUBMITTED,
            PurchaseOrderStatus.APPROVED,
            PurchaseOrderStatus.ORDERED,
            PurchaseOrderStatus.PARTIALLY_ORDERED,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        return PurchaseSummary(
            total=sum(number for number, _ in by_status.values()),
            draft=count(PurchaseOrderStatus.DRAFT),
            open=sum(count(status) for status in open_statuses),
            cancelled=count(PurchaseOrderStatus.CANCELLED),
            closed=count(PurchaseOrderStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
            overdue_delivery=overdue,
        )

    def create_order(
        self, data: PurchaseOrderCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseOrder:
        """Create order, always as a draft, and commit it."""
        row = self.stage_order(data, firm_id=firm_id, actor_id=actor_id)
        if data.attributes:
            document_attributes.store(
                self._session,
                AttributeEntityType.PURCHASE_ORDER,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        self._session.commit()
        return row

    def preview_order(
        self, data: PurchaseOrderCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseOrderPreview:
        """Price an order exactly as saving it would, then save nothing.

        Staged through the save path -- line discounts, the header discount,
        tax at the rates in force -- read back, and the unit of work rolled
        back: no order, no number used up, no audit row. The request's session
        is its own, so there is nothing else in it to lose.
        """
        hints = [
            PurchaseQuantityHint(
                line_number=hint.line_number,
                product_id=hint.product_id,
                quantity=hint.quantity,
                minimum_order_quantity=hint.minimum_order_quantity,
                order_multiple=hint.order_multiple,
                suggested_quantity=hint.suggested_quantity,
                message=hint.describe(),
            )
            for hint in quantity_hints(
                self._session,
                firm_id=firm_id,
                vendor_id=data.vendor_id,
                on=data.purchase_date,
                lines=[
                    (number, line.product_id, line.ordered_quantity)
                    for number, line in enumerate(data.lines, start=1)
                ],
            )
        ]
        try:
            row = self.stage_order(
                data, firm_id=firm_id, actor_id=actor_id, check_quantities=False
            )
            response = self.order_response(row)
            interstate = (
                self._tax.inward_transaction_type(
                    "PURCHASE_ORDER",
                    firm_id=firm_id,
                    branch_id=data.branch_id,
                    vendor_id=data.vendor_id,
                )
                == PURCHASE_INTERSTATE
            )
            lines = purchase_line_companions(
                self._session,
                firm_id=firm_id,
                vendor_id=data.vendor_id,
                lines=[
                    (
                        line.line_number,
                        line.product_id,
                        line.warehouse_id or data.warehouse_id,
                    )
                    for line in response.lines
                ],
            )
        finally:
            self._session.rollback()
        return PurchaseOrderPreview(
            order=response,
            interstate=interstate,
            lines=lines,
            quantity_hints=hints,
            scheme_suggestions=self._scheme_suggestions(data, firm_id=firm_id),
        )

    def _scheme_suggestions(
        self, data: PurchaseOrderCreate, *, firm_id: UUID
    ) -> list[SupplierSchemeSuggestion]:
        """Return the other-product free goods the lines earn (PG-11).

        Offered, never written: saving takes the lines as sent, so the gift
        line exists only once the client adds it with the scheme's id.
        """
        outcomes = line_schemes(
            self._session,
            firm_id=firm_id,
            vendor_id=data.vendor_id,
            on=data.purchase_date,
            lines=[
                (
                    line.product_id,
                    line.ordered_quantity,
                    line.free_quantity,
                    line.scheme_id,
                )
                for line in data.lines
            ],
        )
        earned = [
            (number, outcome)
            for number, outcome in enumerate(outcomes, start=1)
            if outcome.other is not None and outcome.other.free_product_id
        ]
        if not earned:
            return []
        free_ids = {
            outcome.other.free_product_id
            for _, outcome in earned
            if outcome.other is not None
        }
        products = {
            product_id: (code, name)
            for product_id, code, name in self._session.execute(
                select(Product.id, Product.code, Product.name).where(
                    Product.id.in_(free_ids)
                )
            ).all()
        }
        carried = {
            (line.product_id, line.scheme_id): number
            for number, line in enumerate(data.lines, start=1)
            if line.scheme_id is not None
        }
        suggestions: list[SupplierSchemeSuggestion] = []
        for number, outcome in earned:
            scheme = outcome.other
            if scheme is None or scheme.free_product_id is None:
                continue
            code, name = products.get(scheme.free_product_id, ("", ""))
            suggestions.append(
                SupplierSchemeSuggestion(
                    line_number=number,
                    scheme_id=scheme.id,
                    scheme_label=outcome.other_label or "",
                    free_product_id=scheme.free_product_id,
                    free_product_code=code,
                    free_product_name=name,
                    free_quantity=outcome.other_quantity,
                    existing_line_number=carried.get(
                        (scheme.free_product_id, scheme.id)
                    ),
                )
            )
        return suggestions

    def stage_order(
        self,
        data: PurchaseOrderCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
        check_quantities: bool = True,
    ) -> PurchaseOrder:
        """Build one order as a draft without committing it.

        A create used to write whatever status it was given, so an order could
        be born APPROVED -- 64 in the shared store were, from the seeder -- and
        the import's Status column did the same. Approval is the control point
        `approve_order` exists to be; a status a caller can state on the way in
        is a way round it. A payload saying DRAFT, or nothing, is accepted; any
        other status is refused by name rather than quietly turned into a draft,
        because a caller who asked for APPROVED believes they got it.
        """
        if data.status is not None and data.status != PurchaseOrderStatus.DRAFT:
            raise ValidationError(
                "A new purchase order is saved as a draft. Its status cannot be "
                f"set to {data.status.value} when it is created: submit it, then "
                "approve it."
            )
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        # An order in another currency needs its rate where it is typed, not
        # at the dock when the goods arrive (D-BUY-39).
        check_currency(
            data.currency_code, data.exchange_rate, document="purchase order"
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        self._validate_scope_references(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            vendor_id=data.vendor_id,
        )
        branch_code, company_code = self._scope_codes(
            firm_id=firm_id, branch_id=data.branch_id
        )
        po_number = self._issue_number(
            numbering_rule,
            typed=data.po_number.strip() if data.po_number else None,
            number_column=PurchaseOrder.po_number,
            firm_id=firm_id,
            document_date=data.purchase_date,
            actor_id=actor_id,
            branch_code=branch_code,
            company_code=company_code,
        )
        row = PurchaseOrder(
            firm_id=firm_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            vendor_id=data.vendor_id,
            buyer_id=data.buyer_id,
            tax_profile_id=data.tax_profile_id,
            po_number=po_number,
            vendor_contact=data.vendor_contact,
            vendor_address=data.vendor_address,
            department=data.department,
            purchase_type=data.purchase_type.value,
            purchase_category=data.purchase_category,
            purchase_date=data.purchase_date,
            expected_delivery_date=data.expected_delivery_date,
            payment_terms=data.payment_terms,
            delivery_terms=data.delivery_terms,
            currency_code=normalize_currency(data.currency_code),
            exchange_rate=data.exchange_rate,
            reference_number=data.reference_number,
            external_reference=data.external_reference,
            priority=data.priority,
            remarks=data.remarks,
            status=PurchaseOrderStatus.DRAFT.value,
            header_discount_amount=data.header_discount_amount,
            additional_charges=data.additional_charges,
            round_off=data.round_off,
            created_by=actor_id,
            updated_by=actor_id,
        )
        if row.expected_delivery_date is None:
            row.expected_delivery_date = self._expected_from_lead_time(row, data.lines)
        self._session.add(row)
        self._flush_or_conflict("Purchase order number already exists in this firm.")
        # An order a supplier bill raises records what was billed, so the
        # supplier's terms are not for it to break (BUY-5).
        if check_quantities:
            self._assert_order_quantities(row, data.lines)
        totals = self._replace_lines(row, data=data, actor_id=actor_id)
        row.subtotal = totals["subtotal"]
        row.line_discount_total = totals["line_discount_total"]
        row.tax_total = totals["tax_total"]
        row.grand_total = totals["grand_total"]
        self._replace_schedules(row, data=data, actor_id=actor_id)
        self._replace_attachments(row, data=data, actor_id=actor_id)
        self._replace_notes(row, data=data, actor_id=actor_id)
        self._history(
            order=row,
            action="purchase.created",
            from_status=None,
            to_status=row.status,
            actor_id=actor_id,
            details={"po_number": row.po_number},
        )
        self._record_document_event(
            firm_id=firm_id,
            document_type=document_type,
            order=row,
            action="CREATED",
            from_state=None,
            to_state=row.status,
            actor_id=actor_id,
            details={"po_number": row.po_number},
        )
        record_audit(
            self._session,
            action="purchase.created",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"po_number": row.po_number, "status": row.status},
        )
        self._flush_or_conflict("Purchase order number already exists in this firm.")
        return row

    def update_order(
        self,
        order_id: UUID,
        data: PurchaseOrderUpdate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseOrder:
        """Change order."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_order(order_id, firm_scope=firm_scope)
        self._assert_order_editable(row)
        self._validate_scope_references(
            firm_id=firm_scope,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            vendor_id=data.vendor_id,
        )
        before_status = row.status
        self._write_version(row, data, actor_id=actor_id)
        self._history(
            order=row,
            action="purchase.updated",
            from_status=before_status,
            to_status=row.status,
            actor_id=actor_id,
            details={"po_number": row.po_number},
        )
        # After the edit's own entry, so the trail reads in the order it
        # happened: the document changed, and that withdrew the approval.
        self._withdraw_approval(row, before_status=before_status, actor_id=actor_id)
        self._record_document_event(
            firm_id=firm_scope,
            document_type=self._ensure_document_setup(
                firm_id=firm_scope, actor_id=actor_id
            )[0],
            order=row,
            action="EDITED",
            from_state=before_status,
            to_state=row.status,
            actor_id=actor_id,
            details={"po_number": row.po_number},
        )
        record_audit(
            self._session,
            action="purchase.updated",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before_status},
            after_data={"status": row.status, "grand_total": str(row.grand_total)},
        )
        self._flush_or_conflict("Purchase order update conflicts with existing data.")
        if "attributes" in data.model_fields_set:
            document_attributes.store(
                self._session,
                AttributeEntityType.PURCHASE_ORDER,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        self._session.commit()
        return row

    def _write_currency(
        self, row: PurchaseOrder, data: PurchaseOrderUpdate | PurchaseOrderAmend
    ) -> None:
        """Write the order's currency and rate from an edit (D-BUY-39).

        Absent keeps what the order holds: a client that never showed the
        two fields cannot turn an import into a rupee order. Once goods have
        been received the stock is valued, so neither may change.

        Raises:
            ValidationError: If a foreign currency has no rate, or either
                changes after a receipt.

        """
        sent = data.model_fields_set
        currency = (
            normalize_currency(data.currency_code)
            if "currency_code" in sent
            else row.currency_code
        )
        rate = data.exchange_rate if "exchange_rate" in sent else row.exchange_rate
        check_currency(currency, rate, document="purchase order")
        if (currency, rate) == (row.currency_code, row.exchange_rate):
            return
        received = self._session.scalar(
            select(GoodsReceipt.grn_number)
            .where(
                GoodsReceipt.purchase_order_id == row.id,
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceipt.status.in_(("COMPLETED", "CLOSED")),
            )
            .limit(1)
        )
        if received is not None:
            raise ValidationError(
                f"{received} has already valued this order's goods at its "
                "currency and rate, so neither can change. A different rate "
                "on the supplier's bill is typed on the bill.",
                details={"field": "exchange_rate"},
            )
        row.currency_code = currency
        row.exchange_rate = rate

    def _write_version(
        self,
        row: PurchaseOrder,
        data: PurchaseOrderUpdate | PurchaseOrderAmend,
        *,
        actor_id: UUID,
    ) -> None:
        """Write the header, lines and children an edit or amendment sends."""
        row.branch_id = data.branch_id
        row.warehouse_id = data.warehouse_id
        row.vendor_id = data.vendor_id
        row.buyer_id = data.buyer_id
        row.tax_profile_id = data.tax_profile_id
        row.vendor_contact = data.vendor_contact
        row.vendor_address = data.vendor_address
        row.department = data.department
        row.purchase_type = data.purchase_type.value
        row.purchase_category = data.purchase_category
        row.purchase_date = data.purchase_date
        row.expected_delivery_date = data.expected_delivery_date
        row.payment_terms = data.payment_terms
        row.delivery_terms = data.delivery_terms
        self._write_currency(row, data)
        row.reference_number = data.reference_number
        row.external_reference = data.external_reference
        row.priority = data.priority
        row.remarks = data.remarks
        row.header_discount_amount = data.header_discount_amount
        row.additional_charges = data.additional_charges
        row.round_off = data.round_off
        row.updated_by = actor_id
        self._assert_order_quantities(row, data.lines)
        totals = self._replace_lines(row, data=data, actor_id=actor_id)
        row.subtotal = totals["subtotal"]
        row.line_discount_total = totals["line_discount_total"]
        row.tax_total = totals["tax_total"]
        row.grand_total = totals["grand_total"]
        self._replace_schedules(row, data=data, actor_id=actor_id)
        self._replace_attachments(row, data=data, actor_id=actor_id)
        self._replace_notes(row, data=data, actor_id=actor_id)

    def amend_order(
        self,
        order_id: UUID,
        data: PurchaseOrderAmend,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_approve: bool,
    ) -> PurchaseOrder:
        """Amend an approved order formally and commit (BUY-8, decision A102).

        The version it replaces is kept in ``purchase_order_revisions`` and
        the order's ``revision_number`` moves on, so the print reads
        "Amendment N". The supplier cannot change; a line already received
        keeps its product and cannot drop below what came in. An amendment
        that raises the total is itself an approval of the new total, so it
        needs PURCHASE_APPROVE (``may_approve``) within the amender's limit;
        one that lowers it or moves only terms does not. The status is then
        re-derived from what was received.

        Raises:
            ValidationError: For a draft, cancelled or closed order, a changed
                supplier, or a received line cut or changed.
            AuthorizationError: When the total rises and the amender may not
                approve it.

        """
        from app.goods_receipt.services import GoodsReceiptService
        from app.purchase.services.line_quantities import order_line_quantities

        row = self.get_order(order_id, firm_scope=firm_scope)
        amendable = {
            PurchaseOrderStatus.APPROVED.value,
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
            PurchaseOrderStatus.RECEIVED.value,
        }
        if row.status not in amendable:
            raise ValidationError(
                "Only an approved order is amended; a draft or submitted one is "
                "simply edited, and a cancelled or closed one is history."
            )
        if data.vendor_id != row.vendor_id:
            raise ValidationError(
                "An amendment cannot change the supplier. Cancel the order and "
                "raise a new one."
            )
        lines = list(
            self._session.scalars(
                select(PurchaseOrderLine)
                .where(
                    PurchaseOrderLine.purchase_order_id == row.id,
                    PurchaseOrderLine.is_deleted.is_(False),
                )
                .order_by(PurchaseOrderLine.line_number.asc())
            ).all()
        )
        received = order_line_quantities(self._session, lines)
        sent = {number: line for number, line in enumerate(data.lines, start=1)}
        problems: list[str] = []
        for line in lines:
            got = received.get(line.id)
            if got is None or got.received <= ZERO:
                continue
            new = sent.get(line.line_number)
            if new is None or new.product_id != line.product_id:
                problems.append(
                    f"line {line.line_number} has {got.received.normalize():f} "
                    "received and must stay, for the same product"
                )
            elif new.ordered_quantity < got.received:
                problems.append(
                    f"line {line.line_number} cannot drop to "
                    f"{new.ordered_quantity.normalize():f}; "
                    f"{got.received.normalize():f} was received"
                )
        if problems:
            raise ValidationError(
                f"{row.po_number} cannot be amended that way: "
                + "; ".join(problems)
                + "."
            )
        before_total = Decimal(str(row.grand_total))
        before_status = row.status
        snapshot = self._snapshot(row, lines)
        self._write_version(row, data, actor_id=actor_id)
        self._session.flush()
        if Decimal(str(row.grand_total)) > before_total:
            if not may_approve:
                raise AuthorizationError(
                    f"The amendment raises {row.po_number} from "
                    f"{self._q(before_total)} to {self._q(row.grand_total)}, "
                    "which is an approval of the new total. It needs the "
                    "approve purchases permission (PURCHASE_APPROVE)."
                )
            PurchaseApprovalLimitService(self._session).enforce(
                firm_scope, actor_id, order_amount=row.grand_total
            )
        self._session.add(
            PurchaseOrderRevision(
                firm_id=firm_scope,
                purchase_order_id=row.id,
                revision_number=row.revision_number,
                grand_total=before_total,
                snapshot_json=json.dumps(snapshot, default=str),
                reason=data.reason,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        row.revision_number += 1
        GoodsReceiptService(self._session).resync_order_status(
            row, firm_id=firm_scope, actor_id=actor_id
        )
        details = {
            "po_number": row.po_number,
            "revision_number": row.revision_number,
            "reason": data.reason,
            "grand_total_before": str(before_total),
            "grand_total_after": str(row.grand_total),
        }
        self._history(
            order=row,
            action="purchase.amended",
            from_status=before_status,
            to_status=row.status,
            actor_id=actor_id,
            details=details,
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=self._ensure_document_setup(
                firm_id=firm_scope, actor_id=actor_id
            )[0],
            order=row,
            action="AMENDED",
            from_state=before_status,
            to_state=row.status,
            actor_id=actor_id,
            details=details,
        )
        record_audit(
            self._session,
            action="purchase.amended",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"grand_total": str(before_total)},
            after_data=details,
        )
        self._flush_or_conflict(
            "Purchase order amendment conflicts with existing data."
        )
        self._session.commit()
        return row

    def list_revisions(
        self, order_id: UUID, *, firm_scope: UUID
    ) -> list[PurchaseOrderRevisionResponse]:
        """Return the order's earlier versions, oldest first (BUY-8)."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        return [
            PurchaseOrderRevisionResponse(
                id=revision.id,
                revision_number=revision.revision_number,
                grand_total=revision.grand_total,
                reason=revision.reason,
                amended_by=revision.created_by,
                amended_at=revision.created_at,
                snapshot=json.loads(revision.snapshot_json),
            )
            for revision in self._session.scalars(
                select(PurchaseOrderRevision)
                .where(
                    PurchaseOrderRevision.purchase_order_id == row.id,
                    PurchaseOrderRevision.is_deleted.is_(False),
                )
                .order_by(PurchaseOrderRevision.revision_number.asc())
            ).all()
        ]

    @staticmethod
    def _snapshot(
        row: PurchaseOrder, lines: list[PurchaseOrderLine]
    ) -> dict[str, object]:
        """Describe the order as it stands, for its revision row."""
        return {
            "revision_number": row.revision_number,
            "purchase_date": row.purchase_date,
            "expected_delivery_date": row.expected_delivery_date,
            "payment_terms": row.payment_terms,
            "delivery_terms": row.delivery_terms,
            "header_discount_amount": row.header_discount_amount,
            "additional_charges": row.additional_charges,
            "subtotal": row.subtotal,
            "tax_total": row.tax_total,
            "grand_total": row.grand_total,
            "remarks": row.remarks,
            "lines": [
                {
                    "line_number": line.line_number,
                    "product_id": line.product_id,
                    "description": line.description,
                    "ordered_quantity": line.ordered_quantity,
                    "free_quantity": line.free_quantity,
                    "unit_price": line.unit_price,
                    "discount_percent": line.discount_percent,
                    "discount_amount": line.discount_amount,
                    "tax_amount": line.tax_amount,
                    "net_amount": line.net_amount,
                }
                for line in lines
            ],
        }

    def get_order(
        self, order_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> PurchaseOrder:
        """Return order."""
        statement = select(PurchaseOrder).where(
            PurchaseOrder.id == order_id,
            PurchaseOrder.firm_id == firm_scope,
        )
        if not include_deleted:
            statement = statement.where(PurchaseOrder.is_deleted.is_(False))
        row = self._session.scalar(statement)
        if row is None:
            raise ResourceNotFoundError("Purchase order not found.")
        return row

    def _assert_order_editable(self, order: PurchaseOrder) -> None:
        """Refuse an edit the order's own history makes meaningless.

        Cancelled and closed were always refused. Received was not, and had to
        be: the quantities and prices on those lines are what a goods receipt
        was matched against and what stock was posted at, so editing them
        leaves the receipt describing a document that no longer says what it
        said. Cancel the order or raise a purchase return instead.
        """
        refusal = {
            PurchaseOrderStatus.CANCELLED.value: (
                "Cancelled purchase orders cannot be updated."
            ),
            PurchaseOrderStatus.CLOSED.value: (
                "Closed purchase orders cannot be updated."
            ),
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value: (
                "Goods have been received against this order, so its lines "
                "cannot be changed. Cancel the receipt first, or raise a "
                "purchase return."
            ),
            PurchaseOrderStatus.RECEIVED.value: (
                "This order has been received in full, so its lines cannot be "
                "changed. Raise a purchase return instead."
            ),
        }.get(order.status)
        if refusal is not None:
            raise ValidationError(refusal)

    def _withdraw_approval(
        self, order: PurchaseOrder, *, before_status: str, actor_id: UUID
    ) -> None:
        """Send an edited order back for approval.

        Editing used to write `data.status` straight onto the row, and
        `PurchaseOrderUpdate` gives that field a default of DRAFT -- so a
        client that said nothing about the status silently reset an APPROVED
        order to DRAFT, and a PARTIALLY_RECEIVED one too, where nothing could
        ever move it back. The desktop hid it by always sending the status it
        last read, which produced the opposite fault: an approved order could
        be edited from any amount to any other and stay approved.

        The status is now the lifecycle endpoints' alone. The one status change
        an edit legitimately causes is this one: approving is a statement about
        a particular document, so changing the document withdraws it, and the
        order goes round again. Editing a DRAFT or SUBMITTED order changes
        nothing -- neither has been approved yet.
        """
        if before_status != PurchaseOrderStatus.APPROVED.value:
            return
        order.status = PurchaseOrderStatus.DRAFT.value
        self._history(
            order=order,
            action="purchase.approval_withdrawn",
            from_status=before_status,
            to_status=order.status,
            actor_id=actor_id,
            details={"reason": "The order was edited after approval."},
        )

    def _assert_order_removable(self, order: PurchaseOrder) -> None:
        """Refuse to delete an order goods have already been received against.

        Cancelling a received order was refused; deleting one was not, and
        delete is the more destructive of the two. A receipt records its
        purchase_order_id, so removing the order leaves the receipt pointing at
        a document no listing shows.
        """
        if order.status == PurchaseOrderStatus.RECEIVED.value:
            raise ValidationError("Received purchase orders cannot be deleted.")
        received = self._session.scalar(
            select(GoodsReceipt.id)
            .where(
                GoodsReceipt.purchase_order_id == order.id,
                GoodsReceipt.is_deleted.is_(False),
            )
            .limit(1)
        )
        if received is not None:
            raise ValidationError(
                "Goods have been received against this order; cancel it instead."
            )

    def delete_order(self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        """Soft delete a purchase order nothing has been received against."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        self._assert_order_removable(row)
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._history(
            order=row,
            action="purchase.deleted",
            from_status=row.status,
            to_status=row.status,
            actor_id=actor_id,
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase.deleted",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": row.status},
        )
        self._session.commit()

    def restore_order(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseOrder:
        """Restore order."""
        row = self.get_order(order_id, firm_scope=firm_scope, include_deleted=True)
        row.is_deleted = False
        row.deleted_at = None
        row.deleted_by = None
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._history(
            order=row,
            action="purchase.restored",
            from_status=row.status,
            to_status=row.status,
            actor_id=actor_id,
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase.restored",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def submit_order(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseOrder:
        """Send a draft order for approval and commit."""
        row = self.stage_submit(order_id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_submit(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseOrder:
        """Send a draft order for approval without committing.

        The first half of the control point this module never had. Until now
        the only way an order reached any status was for the client to state
        one on create or update -- `cancel` and `close` were the sole real
        transitions -- so `SUBMITTED` existed in the enum, was filtered on by
        the Open Orders tab, and could not be produced by anything a user did.
        """
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status == PurchaseOrderStatus.SUBMITTED.value:
            return row
        if row.status != PurchaseOrderStatus.DRAFT.value:
            raise ValidationError("Only draft purchase orders can be submitted.")
        has_lines = self._session.scalar(
            select(PurchaseOrderLine.id)
            .where(
                PurchaseOrderLine.purchase_order_id == row.id,
                PurchaseOrderLine.is_deleted.is_(False),
            )
            .limit(1)
        )
        if has_lines is None:
            raise ValidationError("A purchase order with no lines cannot be submitted.")
        return self._transition(
            row,
            to_status=PurchaseOrderStatus.SUBMITTED,
            action="purchase.submitted",
            event="SUBMITTED",
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def approve_order(
        self,
        order_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_exceed_budget: bool = True,
    ) -> PurchaseOrder:
        """Approve a submitted order and commit."""
        row = self.stage_approval(
            order_id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            may_exceed_budget=may_exceed_budget,
        )
        self._session.commit()
        return row

    def stage_approval(
        self,
        order_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        enforce_limit: bool = True,
        may_exceed_budget: bool = True,
    ) -> PurchaseOrder:
        """Approve a submitted order, committing the firm to buy, unsaved.

        Deliberately requires SUBMITTED rather than accepting a draft. An
        approval anyone can skip is not a control point, and a two-step flow is
        the reason purchase orders differ from sales orders here --
        `SalesOrderService.approve_order` goes straight from DRAFT because the
        thing it guards is credit, checked at that moment, not a second pair of
        eyes.

        ``enforce_limit`` is False only where a supplier bill raises the order
        for a firm that switched the order stage off: nobody typed that order,
        so there is no approval of it for a limit to govern (BACKLOG 68 row 4).
        """
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status == PurchaseOrderStatus.APPROVED.value:
            return row
        if row.status != PurchaseOrderStatus.SUBMITTED.value:
            raise ValidationError(
                "Only submitted purchase orders can be approved. "
                "Submit the order first."
            )
        # An order a supplier bill raised nobody typed or submitted.
        if enforce_limit:
            # Levels of sign-off the firm's rules call for (PLT-1).
            from app.approvals.services import ApprovalChainService

            ApprovalChainService(self._session).assert_cleared(
                firm_scope, "PURCHASE_ORDER", row.id, row.grand_total, actor_id
            )
        # Warns only: whether the vendor may supply the goods (backlog 54).
        licence_remark, licence_details = LicenceCheckService(
            self._session
        ).approve_purchase(LicenceDocument.PURCHASE_ORDER, row.id, firm_id=firm_scope)
        # The approver's limit (backlog 68 row 4): above it the order stays
        # submitted and the refusal names the amount it needs.
        limit_details = (
            PurchaseApprovalLimitService(self._session).enforce(
                firm_scope, actor_id, order_amount=row.grand_total
            )
            if enforce_limit
            else None
        )
        if limit_details:
            licence_details = {**(licence_details or {}), **limit_details}
        # Purchase budgets (BUY-14): not for an order nobody typed.
        if enforce_limit:
            budget_remark = self._check_budgets(
                row, may_exceed_budget=may_exceed_budget
            )
            if budget_remark:
                licence_remark = (
                    f"{licence_remark} {budget_remark}"
                    if licence_remark
                    else budget_remark
                )
        # Past a rate contract's quantity (PG-9): warns, never refuses, and
        # the trail keeps what the approver was told.
        contract_remark = self._rate_contract_remark(row)
        if contract_remark:
            licence_remark = (
                f"{licence_remark} {contract_remark}"
                if licence_remark
                else contract_remark
            )
        return self._transition(
            row,
            to_status=PurchaseOrderStatus.APPROVED,
            action="purchase.approved",
            event="APPROVED",
            firm_scope=firm_scope,
            actor_id=actor_id,
            remarks=licence_remark,
            details=licence_details,
        )

    def _rate_contract_remark(self, row: PurchaseOrder) -> str | None:
        """Return the over-draw warning for an order about to be approved."""
        from app.rate_contracts.services.rates import overdraw_warnings

        lines = self._session.execute(
            select(
                PurchaseOrderLine.rate_contract_line_id,
                PurchaseOrderLine.ordered_quantity,
            ).where(
                PurchaseOrderLine.purchase_order_id == row.id,
                PurchaseOrderLine.is_deleted.is_(False),
            )
        ).all()
        return overdraw_warnings(
            self._session,
            [(row.id, row.status, [(line_id, qty) for line_id, qty in lines])],
        ).get(row.id)

    def _check_budgets(
        self, row: PurchaseOrder, *, may_exceed_budget: bool
    ) -> str | None:
        """Warn about, or refuse, an approval past a purchase budget (BUY-14).

        Raises:
            AuthorizationError: When the firm requires approval past a budget
                and the approver may not give it.

        """
        from app.purchase.services.budgets import PurchaseBudgetService
        from app.purchase.services.workflow_settings_service import (
            PurchaseWorkflowService,
        )

        over = [
            check
            for check in PurchaseBudgetService(self._session).check_order(row)
            if check.exceeded
        ]
        if not over:
            return None
        message = "; ".join(
            f"{check.label} -- {check.used + check.this_order:.2f} of "
            f"{check.amount:.2f}"
            for check in over
        )
        policy = PurchaseWorkflowService(self._session).settings_response(row.firm_id)
        if policy.budget_policy == "NEEDS_APPROVAL" and not may_exceed_budget:
            raise AuthorizationError(
                f"{row.po_number} takes a purchase budget past its amount "
                f"({message}). Approving it needs the approve over budget "
                "permission (PURCHASE_APPROVE_OVER_BUDGET)."
            )
        return f"Over budget: {message}."

    def _transition(
        self,
        row: PurchaseOrder,
        *,
        to_status: PurchaseOrderStatus,
        action: str,
        event: str,
        firm_scope: UUID,
        actor_id: UUID,
        remarks: str | None = None,
        details: dict[str, object] | None = None,
    ) -> PurchaseOrder:
        """Move an order to a new status, leaving the trail the others leave.

        Factored out rather than copied twice: `cancel_order` and `close_order`
        each write a history row, a lifecycle event and an audit entry, and a
        transition that quietly skipped one of the three would be invisible
        until somebody went looking for the history that was never written.
        """
        before = row.status
        row.status = to_status.value
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._history(
            order=row,
            action=action,
            from_status=before,
            to_status=row.status,
            actor_id=actor_id,
            details={},
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action=event,
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
            details=details or {},
        )
        record_audit(
            self._session,
            action=action,
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.flush()
        return row

    #: The states in which an order is a promise to the supplier and can be
    #: sent: approved, and not yet finished or withdrawn.
    _SENDABLE = frozenset(
        {
            PurchaseOrderStatus.APPROVED.value,
            PurchaseOrderStatus.PARTIALLY_ORDERED.value,
            PurchaseOrderStatus.ORDERED.value,
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
        }
    )

    def mark_sent(
        self, order_id: UUID, *, via: str, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseOrder:
        """Record that an approved order reached the supplier, and how.

        Backlog 69 row 6. Marking again records the latest sending -- a
        resend by another route is the same promise -- and both are on the
        timeline.
        """
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status not in self._SENDABLE:
            raise ValidationError("Only an approved order can be sent to the supplier.")
        before = {"sent_at": row.sent_at, "sent_via": row.sent_via}
        row.sent_at = utc_now()
        row.sent_via = via
        row.sent_by = actor_id
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action="SENT",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
            remarks=f"Sent to the supplier by {via.lower()}.",
            details={"via": via},
        )
        record_audit(
            self._session,
            action="purchase.sent",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={
                "sent_at": (
                    None if before["sent_at"] is None else str(before["sent_at"])
                ),
                "sent_via": before["sent_via"],
            },
            after_data={"sent_at": str(row.sent_at), "sent_via": via},
        )
        self._session.commit()
        return row

    def cancel_order(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> PurchaseOrder:
        """Cancel order and commit."""
        row = self.stage_cancel(
            order_id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        self._session.commit()
        return row

    def stage_cancel(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> PurchaseOrder:
        """Cancel order without committing."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status in {
            PurchaseOrderStatus.CANCELLED.value,
            PurchaseOrderStatus.CLOSED.value,
        }:
            return row
        if row.status == PurchaseOrderStatus.RECEIVED.value:
            raise ValidationError("Received purchase orders cannot be cancelled.")
        before = row.status
        row.status = PurchaseOrderStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._history(
            order=row,
            action="purchase.cancelled",
            from_status=before,
            to_status=row.status,
            actor_id=actor_id,
            details={"reason": reason or ""},
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action="CANCELLED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
            details={"reason": reason or ""},
        )
        record_audit(
            self._session,
            action="purchase.cancelled",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "reason": reason or ""},
        )
        self._session.flush()
        return row

    def close_order(
        self, order_id: UUID, *, firm_scope: UUID, actor_id: UUID, reason: str | None
    ) -> PurchaseOrder:
        """Close order."""
        row = self.get_order(order_id, firm_scope=firm_scope)
        if row.status == PurchaseOrderStatus.CLOSED.value:
            return row
        if row.status == PurchaseOrderStatus.CANCELLED.value:
            raise ValidationError("Cancelled purchase orders cannot be closed.")
        before = row.status
        row.status = PurchaseOrderStatus.CLOSED.value
        row.close_reason = reason
        row.updated_by = actor_id
        document_type = self._ensure_document_setup(
            firm_id=firm_scope, actor_id=actor_id
        )[0]
        self._history(
            order=row,
            action="purchase.closed",
            from_status=before,
            to_status=row.status,
            actor_id=actor_id,
            details={"reason": reason or ""},
        )
        self._record_document_event(
            firm_id=firm_scope,
            document_type=document_type,
            order=row,
            action="CLOSED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=reason,
            details={"reason": reason or ""},
        )
        record_audit(
            self._session,
            action="purchase.closed",
            entity_type="purchase_order",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "reason": reason or ""},
        )
        self._session.commit()
        return row

    def import_orders(
        self,
        data: PurchaseOrderImportRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> list[PurchaseOrder]:
        """Import orders."""
        self._validate_import_records(data.records, firm_scope=firm_scope)
        return [
            self.create_order(record, firm_id=firm_scope, actor_id=actor_id)
            for record in data.records
        ]

    def import_orders_csv(
        self, csv_content: str, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseOrder]:
        """Import orders csv."""
        reader = csv.DictReader(io.StringIO(csv_content))
        records: list[PurchaseOrderCreate] = []
        for row in reader:
            branch_id = (row.get("BranchId") or "").strip()
            warehouse_id = (row.get("WarehouseId") or "").strip()
            vendor_id = (row.get("VendorId") or "").strip()
            product_id = (row.get("ProductId") or "").strip()
            purchase_date = (row.get("PurchaseDate") or "").strip()
            ordered_qty = (row.get("OrderedQty") or "").strip()
            unit_price = (row.get("UnitPrice") or "").strip()
            if not (
                branch_id
                and warehouse_id
                and vendor_id
                and product_id
                and purchase_date
                and ordered_qty
                and unit_price
            ):
                continue
            records.append(
                self._import_record(
                    branch_id=branch_id,
                    warehouse_id=warehouse_id,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    purchase_date=purchase_date,
                    ordered_quantity=ordered_qty,
                    unit_price=unit_price,
                    po_number=(row.get("PoNumber") or "").strip() or None,
                    remarks=(row.get("Remarks") or "").strip() or None,
                    purchase_uom_id=(row.get("PurchaseUomId") or "").strip() or None,
                    inventory_uom_id=(row.get("InventoryUomId") or "").strip() or None,
                    tax_profile_id=(row.get("TaxProfileId") or "").strip() or None,
                    expected_delivery_date=(
                        (row.get("ExpectedDeliveryDate") or "").strip() or None
                    ),
                    status=(row.get("Status") or "").strip() or None,
                )
            )
        return self.import_orders(
            PurchaseOrderImportRequest(records=records),
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def import_orders_xlsx(
        self, workbook_bytes: bytes, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseOrder]:
        """Import orders xlsx."""
        try:
            from openpyxl import load_workbook  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValidationError(
                "XLSX import dependency is unavailable. Install openpyxl."
            ) from error
        workbook = load_workbook(filename=BytesIO(workbook_bytes), read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(value or "").strip() for value in rows[0]]
        index = {name: position for position, name in enumerate(header)}
        records: list[PurchaseOrderCreate] = []
        for values in rows[1:]:

            def _cell(name: str, row: tuple[object, ...] = tuple(values)) -> str:
                """Read one named cell from this row.

                ``row`` is bound at definition time on purpose: without it the
                closure would read whichever row the loop had reached by the
                time it was called.
                """
                position = index.get(name, -1)
                if position < 0 or position >= len(row):
                    return ""
                return str(row[position] or "").strip()

            branch_id = _cell("BranchId")
            warehouse_id = _cell("WarehouseId")
            vendor_id = _cell("VendorId")
            product_id = _cell("ProductId")
            purchase_date = _cell("PurchaseDate")
            ordered_qty = _cell("OrderedQty")
            unit_price = _cell("UnitPrice")
            if not (
                branch_id
                and warehouse_id
                and vendor_id
                and product_id
                and purchase_date
                and ordered_qty
                and unit_price
            ):
                continue
            records.append(
                self._import_record(
                    branch_id=branch_id,
                    warehouse_id=warehouse_id,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    purchase_date=purchase_date,
                    ordered_quantity=ordered_qty,
                    unit_price=unit_price,
                    po_number=_cell("PoNumber") or None,
                    remarks=_cell("Remarks") or None,
                    purchase_uom_id=_cell("PurchaseUomId") or None,
                    inventory_uom_id=_cell("InventoryUomId") or None,
                    tax_profile_id=_cell("TaxProfileId") or None,
                    expected_delivery_date=_cell("ExpectedDeliveryDate") or None,
                    status=_cell("Status") or None,
                )
            )
        return self.import_orders(
            PurchaseOrderImportRequest(records=records),
            firm_scope=firm_scope,
            actor_id=actor_id,
        )

    def export_orders_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        """Export orders csv."""
        rows, _ = self.list_orders(
            firm_scope=firm_scope,
            filters=PurchaseOrderListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="purchase_date",
            descending=True,
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "PO Number",
                "Date",
                "Vendor ID",
                "Branch ID",
                "Warehouse ID",
                "Status",
                "Subtotal",
                "Tax Total",
                "Grand Total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.po_number,
                    row.purchase_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    str(row.warehouse_id),
                    row.status,
                    str(row.subtotal),
                    str(row.tax_total),
                    str(row.grand_total),
                ]
            )
        return output.getvalue()

    def export_orders_xlsx(self, *, firm_scope: UUID, search: str | None) -> bytes:
        """Export orders xlsx."""
        try:
            from openpyxl import Workbook
        except ImportError as error:
            raise ValidationError(
                "XLSX export dependency is unavailable. Install openpyxl."
            ) from error
        rows, _ = self.list_orders(
            firm_scope=firm_scope,
            filters=PurchaseOrderListFilters(include_deleted=False),
            page=1,
            page_size=5000,
            search=search,
            sort_by="purchase_date",
            descending=True,
        )
        workbook = Workbook()
        sheet = workbook.active
        if sheet is None:
            raise ValidationError("Unable to generate purchase export workbook.")
        sheet.title = "PurchaseOrders"
        sheet.append(
            [
                "PO Number",
                "Date",
                "Vendor ID",
                "Branch ID",
                "Warehouse ID",
                "Status",
                "Subtotal",
                "Tax Total",
                "Grand Total",
            ]
        )
        for row in rows:
            sheet.append(
                [
                    row.po_number,
                    row.purchase_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    str(row.warehouse_id),
                    row.status,
                    # openpyxl writes Decimal natively, so there is no reason to
                    # round-trip money through binary floating point here.
                    self._q(row.subtotal),
                    self._q(row.tax_total),
                    self._q(row.grand_total),
                ]
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def order_response(self, row: PurchaseOrder) -> PurchaseOrderResponse:
        """Order response."""
        return self.order_responses([row])[0]

    def order_responses(
        self, rows: Sequence[PurchaseOrder]
    ) -> list[PurchaseOrderResponse]:
        """Render a page of purchase orders, reading each child table once.

        One query per child table for the whole page, grouped by order in
        Python, rather than four per order (backlog 56 C, step 3). The
        single-order builder is this with a list of one.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        lines = children_by_parent(
            self._session,
            PurchaseOrderLine,
            PurchaseOrderLine.purchase_order_id,
            ids,
            PurchaseOrderLine.line_number.asc(),
        )
        order_of_line = {
            item.id: order_id for order_id, group in lines.items() for item in group
        }
        # One read in delivery-date order across the page, so each order's
        # share keeps the order its own read gave it.
        schedules: dict[UUID, list[PurchaseDeliverySchedule]] = defaultdict(list)
        if order_of_line:
            for schedule in self._session.scalars(
                select(PurchaseDeliverySchedule)
                .where(
                    PurchaseDeliverySchedule.is_deleted.is_(False),
                    PurchaseDeliverySchedule.purchase_order_line_id.in_(
                        list(order_of_line)
                    ),
                )
                .order_by(PurchaseDeliverySchedule.delivery_date.asc())
            ):
                order_id = order_of_line[schedule.purchase_order_line_id]
                schedules[order_id].append(schedule)
        attachments = children_by_parent(
            self._session,
            PurchaseAttachment,
            PurchaseAttachment.purchase_order_id,
            ids,
        )
        notes = children_by_parent(
            self._session,
            PurchaseNote,
            PurchaseNote.purchase_order_id,
            ids,
        )
        # What the page's lines have been through downstream, read once for
        # the page (backlog 69 row 5).
        quantities = order_line_quantities(
            self._session, [item for group in lines.values() for item in group]
        )
        answer = [
            self._order_response(
                row,
                quantities=quantities,
                lines=lines[row.id],
                # A schedule counts only under its own firm, as it always did.
                schedules=[
                    item for item in schedules[row.id] if item.firm_id == row.firm_id
                ],
                attachments=attachments[row.id],
                notes=notes[row.id],
            )
            for row in rows
        ]
        # The firm's own fields, one read for the page (MST-6).
        fields = document_attributes.responses_for_many(
            self._session, AttributeEntityType.PURCHASE_ORDER, [r.id for r in rows]
        )
        for response in answer:
            response.attributes = fields.get(response.id, [])
        # Rate contracts drawn past their quantity (PG-9), derived for the
        # page in two reads -- none when no line draws on a contract.
        from app.rate_contracts.services.rates import overdraw_warnings

        over = overdraw_warnings(
            self._session,
            (
                (
                    row.id,
                    row.status,
                    [
                        (item.rate_contract_line_id, item.ordered_quantity)
                        for item in lines[row.id]
                    ],
                )
                for row in rows
            ),
        )
        for response in answer:
            response.rate_contract_warning = over.get(response.id)
        return answer

    def _order_response(
        self,
        row: PurchaseOrder,
        *,
        lines: list[PurchaseOrderLine],
        schedules: list[PurchaseDeliverySchedule],
        attachments: list[PurchaseAttachment],
        notes: list[PurchaseNote],
        quantities: dict[UUID, LineQuantities] | None = None,
    ) -> PurchaseOrderResponse:
        """Build one order's response from what the page already read."""
        payload = PurchaseOrderResponse.model_validate(row).model_dump(mode="python")
        figures = [
            (quantities or {}).get(item.id)
            or LineQuantities(
                ordered=item.ordered_quantity, free_ordered=item.free_quantity
            )
            for item in lines
        ]
        payload["lines"] = [
            {
                **PurchaseOrderLineResponse.model_validate(item).model_dump(
                    mode="python"
                ),
                # Derived from the quantities, never read from the column,
                # which nothing writes after creation (D-BUY-24).
                "status": line_status(row.status, figure),
                "received_quantity": figure.received,
                "accepted_quantity": figure.accepted,
                "rejected_quantity": figure.rejected,
                "damaged_quantity": figure.damaged,
                "returned_quantity": figure.returned,
                "invoiced_quantity": figure.invoiced,
                "pending_receipt_quantity": figure.pending_receipt,
                "to_invoice_quantity": figure.to_invoice,
            }
            for item, figure in zip(lines, figures, strict=True)
        ]
        payload["billing_status"] = billing_status(figures)
        payload["is_complete"] = is_complete(figures)
        payload["delivery_schedules"] = [
            PurchaseDeliveryScheduleResponse.model_validate(
                {
                    "id": entry.id,
                    "purchase_order_line_id": entry.purchase_order_line_id,
                    "line_number": self._line_number(
                        lines, entry.purchase_order_line_id
                    ),
                    "delivery_date": entry.delivery_date,
                    "quantity": entry.quantity,
                    "status": entry.status,
                    "remarks": entry.remarks,
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                }
            ).model_dump(mode="python")
            for entry in schedules
        ]
        payload["attachments"] = [
            PurchaseAttachmentResponse.model_validate(item).model_dump(mode="python")
            for item in attachments
        ]
        payload["notes"] = [
            PurchaseNoteResponse.model_validate(item).model_dump(mode="python")
            for item in notes
        ]
        return PurchaseOrderResponse.model_validate(payload)

    def order_history(
        self, *, order_id: UUID, firm_scope: UUID
    ) -> list[PurchaseOrderHistory]:
        """Order history."""
        self.get_order(order_id, firm_scope=firm_scope, include_deleted=True)
        return list(
            self._session.scalars(
                select(PurchaseOrderHistory)
                .where(
                    PurchaseOrderHistory.purchase_order_id == order_id,
                    PurchaseOrderHistory.firm_id == firm_scope,
                    PurchaseOrderHistory.is_deleted.is_(False),
                )
                .order_by(PurchaseOrderHistory.created_at.asc())
            ).all()
        )

    def _line_number(self, lines: list[PurchaseOrderLine], line_id: UUID) -> int:
        """Line number."""
        for line in lines:
            if line.id == line_id:
                return line.line_number
        return 0

    @stamps_tax_rules(PurchaseOrderLine, "purchase_order_id")
    def _expected_from_lead_time(
        self, order: PurchaseOrder, lines: Sequence[PurchaseLineWrite]
    ) -> date | None:
        """Date a new order is expected, from the supplier's lead time (BUY-6).

        The longest lead time the supplier's catalogue quotes for the lines
        ordered, counted from the order's date; None when none is quoted.
        """
        from app.vendors.services.supplier_catalogue import current_rows

        terms = current_rows(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            product_ids=[line.product_id for line in lines],
            on=order.purchase_date,
        )
        quoted = [
            row.lead_time_days
            for row in terms.values()
            if row.lead_time_days is not None
        ]
        if not quoted:
            return None
        return order.purchase_date + timedelta(days=max(quoted))

    def _assert_order_quantities(
        self, order: PurchaseOrder, lines: Sequence[PurchaseLineWrite]
    ) -> None:
        """Refuse lines off the supplier's terms, if the firm says so (BUY-5).

        And, for every firm, a line that orders nothing and nothing free.

        Raises:
            ValidationError: Naming each line and the quantity that would do,
                when the firm's order quantity policy is ``REFUSE``; or the
                line that orders nothing.

        """
        from app.purchase.services.workflow_settings_service import (
            PurchaseWorkflowService,
        )

        # Whatever the firm's policy: a blank free quantity on a line of 0
        # earns nothing from a scheme either (D-BUY-53).
        self._refuse_lines_for_nothing(
            (
                (number, line.ordered_quantity, line.free_quantity)
                for number, line in enumerate(lines, start=1)
            ),
            does="orders",
            document="order",
        )
        policy = PurchaseWorkflowService(self._session).settings_response(order.firm_id)
        if policy.order_quantity_policy != "REFUSE":
            return
        hints = quantity_hints(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            on=order.purchase_date,
            lines=[
                (number, line.product_id, line.ordered_quantity)
                for number, line in enumerate(lines, start=1)
            ],
        )
        if hints:
            raise ValidationError(
                "The supplier's order terms are not met -- "
                + "; ".join(hint.describe() for hint in hints)
                + "."
            )

    def _replace_lines(
        self,
        order: PurchaseOrder,
        *,
        data: PurchaseOrderCreate | PurchaseOrderUpdate | PurchaseOrderAmend,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        """Replace lines."""
        priced, sources, schemes = self._priced_from_supplier(order, data.lines)
        data = data.model_copy(update={"lines": priced})
        # Lines are matched on their line number and updated in place;
        # re-inserting them minted a new UUID per line on every save, and
        # downstream documents reference those ids with no foreign key.
        existing = {
            existing_line.line_number: existing_line
            for existing_line in self._session.scalars(
                select(PurchaseOrderLine).where(
                    PurchaseOrderLine.purchase_order_id == order.id
                )
            ).all()
        }
        seen: set[int] = set()
        gross_total = Decimal("0")
        line_discount_total = Decimal("0")
        tax_total = Decimal("0")
        # The whole-order discount is split across the lines *before* tax, in
        # proportion to what each is worth after its own discount. It used to
        # come off the grand total after tax, so it lowered no taxable value
        # and the input tax was overstated by the tax on it (D-BUY-19).
        taxables = [
            self._q(
                self._q(line.ordered_quantity * (line.unit_price or ZERO))
                - self._line_discount_amount(
                    line, self._q(line.ordered_quantity * (line.unit_price or ZERO))
                )
            )
            for line in data.lines
        ]
        header_discount = resolve_bill_discount(
            taxable=self._q(sum(taxables, ZERO)),
            amount=data.header_discount_amount or None,
        ).amount
        shares = apportion(header_discount, taxables)
        for idx, line in enumerate(data.lines, start=1):
            product = self._active_product(order.firm_id, line.product_id)
            conversion = self._conversion(
                quantity=line.ordered_quantity + (line.free_quantity or ZERO),
                purchase_uom_id=line.purchase_uom_id,
                inventory_uom_id=line.inventory_uom_id,
                product_id=product.id,
                purchase_date=order.purchase_date,
                firm_id=order.firm_id,
            )
            gross_amount = self._q(line.ordered_quantity * (line.unit_price or ZERO))
            discount_amount = self._line_discount_amount(line, gross_amount)
            bill_share = shares[idx - 1]
            taxable = self._q(gross_amount - discount_amount - bill_share)
            # A product names its tax group, not a version, so the rate is
            # resolved from the document date. product.tax_profile_id has not
            # existed since the group_code refactor and raised AttributeError
            # whenever neither the line nor the order named a profile.
            tax_profile_id = line.tax_profile_id or order.tax_profile_id
            if tax_profile_id is None:
                resolved = TaxFrameworkService(
                    self._session
                ).resolve_profile_for_product(
                    product, order.purchase_date, firm_scope=order.firm_id
                )
                tax_profile_id = resolved.id if resolved else None
            tax_amount = self._line_tax_amount(
                document_id=order.id,
                line_number=idx,
                firm_id=order.firm_id,
                actor_id=actor_id,
                tax_profile_id=tax_profile_id,
                vendor_id=order.vendor_id,
                branch_id=order.branch_id,
                product_id=product.id,
                purchase_date=order.purchase_date,
                taxable=taxable,
            )
            net_amount = self._q(taxable + tax_amount)
            row = PurchaseOrderLine(
                purchase_order_id=order.id,
                firm_id=order.firm_id,
                line_number=idx,
                product_id=product.id,
                description=line.description or product.name,
                vendor_product_code=line.vendor_product_code,
                purchase_uom_id=line.purchase_uom_id or product.purchase_uom_id,
                inventory_uom_id=line.inventory_uom_id or product.inventory_uom_id,
                conversion_factor=conversion["factor"],
                conversion_version=conversion["version"],
                ordered_quantity=self._q(line.ordered_quantity),
                free_quantity=self._q(line.free_quantity or ZERO),
                base_quantity=conversion["converted"],
                unit_price=self._q(line.unit_price or ZERO),
                discount_percent=self._q(line.discount_percent or ZERO),
                discount_amount=discount_amount,
                bill_discount_amount=bill_share,
                gross_amount=gross_amount,
                tax_profile_id=tax_profile_id,
                tax_amount=tax_amount,
                net_amount=net_amount,
                # Where the price came from, and the contract it draws on (PG-9).
                rate_source=sources[idx - 1][0],
                rate_contract_line_id=sources[idx - 1][1],
                # The supplier scheme its free goods came from (PG-11).
                scheme_id=schemes[idx - 1].scheme_id,
                scheme_name=schemes[idx - 1].scheme_name,
                batch_required=line.batch_required,
                expiry_required=line.expiry_required,
                serial_required=line.serial_required,
                is_capital_goods=line.is_capital_goods,
                manufacturing_date=line.manufacturing_date,
                expiry_date=line.expiry_date,
                warehouse_id=line.warehouse_id or order.warehouse_id,
                storage_node_id=line.storage_node_id,
                remarks=line.remarks,
                status=PurchaseOrderStatus.ORDERED.value,
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._validate_line_dates(row)
            self._validate_storage_scope(
                order.firm_id, row.warehouse_id, row.storage_node_id
            )
            persisted = existing.get(idx)
            if persisted is None:
                self._session.add(row)
            else:
                self._apply_line_values(
                    persisted,
                    row,
                    actor_id=actor_id,
                    preserve=("received_quantity", "invoiced_quantity"),
                )
            seen.add(idx)
            gross_total += gross_amount
            line_discount_total += discount_amount
            tax_total += tax_amount
        for line_number, obsolete in existing.items():
            if line_number not in seen:
                self._session.delete(obsolete)
        self._session.flush()
        # subtotal is the taxable base — gross less line discount, before tax —
        # which is what every other transactional document reports. This module
        # used to report gross before discount under the same name.
        subtotal = self._q(gross_total - line_discount_total)
        grand_total = self._q(
            subtotal
            - header_discount
            + tax_total
            + data.additional_charges
            + data.round_off
        )
        return {
            "subtotal": subtotal,
            "line_discount_total": self._q(line_discount_total),
            "tax_total": self._q(tax_total),
            "grand_total": grand_total,
        }

    def _priced_from_supplier(
        self, order: PurchaseOrder, lines: list[PurchaseLineWrite]
    ) -> tuple[
        list[PurchaseLineWrite], list[tuple[str, UUID | None]], list[LineScheme]
    ]:
        """Fill each blank price, discount and free quantity from the supplier.

        A blank price takes, most specific first, the rate of a rate contract
        in force with the supplier on the order's date (PG-9), the supplier's
        price list's fixed rate at the line's quantity, the supplier's
        catalogue price (BUY-4), a dated price revision, else the product's
        purchase price -- ranked in ``resolve_supplier_unit_price``. A blank
        supplier code takes the catalogue's; a blank discount takes the
        contract's rate where the contract priced the line, else the list's,
        else the supplier's standing discount, through the same
        ``resolve_line_discount``. A blank free quantity takes the supplier's
        free scheme on the same product (PG-11, ``line_schemes``). A typed
        value, zero included, stands.

        Returns:
            The priced lines; per line where its price came from and the
            contract line it draws on, if any; and per line the scheme its
            free goods came from.

        """
        from app.pricing.services.price_list_service import SupplierPriceResolver
        from app.products.services.price_revisions import price_in_force
        from app.rate_contracts.services.rates import contract_lines_in_force
        from app.vendors.services.supplier_catalogue import current_rows

        product_ids = [line.product_id for line in lines]
        # The supplier's catalogue (BUY-4): their code on a line that names
        # none, and their price below a price list's fixed rate.
        catalogue = current_rows(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            product_ids=product_ids,
            on=order.purchase_date,
        )
        if catalogue:
            lines = [
                (
                    line.model_copy(
                        update={
                            "vendor_product_code": catalogue[
                                line.product_id
                            ].supplier_product_code
                        }
                    )
                    if not line.vendor_product_code
                    and line.product_id in catalogue
                    and catalogue[line.product_id].supplier_product_code
                    else line
                )
                for line in lines
            ]
        contracts = contract_lines_in_force(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            product_ids=product_ids,
            on=order.purchase_date,
        )
        vendor = self._session.get(Vendor, order.vendor_id)
        standing = (
            Decimal(str(vendor.standing_discount_percent or 0)) if vendor else ZERO
        )
        lists = SupplierPriceResolver(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            on=order.purchase_date,
        )
        # The supplier's free schemes (PG-11), resolved for every line at once.
        schemes = line_schemes(
            self._session,
            firm_id=order.firm_id,
            vendor_id=order.vendor_id,
            on=order.purchase_date,
            lines=[
                (
                    line.product_id,
                    line.ordered_quantity,
                    line.free_quantity,
                    line.scheme_id,
                )
                for line in lines
            ],
        )
        priced: list[PurchaseLineWrite] = []
        sources: list[tuple[str, UUID | None]] = []
        for line, scheme in zip(lines, schemes, strict=True):
            product = self._session.get(Product, line.product_id)
            # A contract's rate is per its own unit; a line in another unit is
            # not priced from it, so a drawn quantity never needs converting.
            unit = line.purchase_uom_id or getattr(product, "purchase_uom_id", None)
            contract = next(
                (
                    candidate
                    for candidate in contracts.get(line.product_id, [])
                    if candidate.uom_id is None or candidate.uom_id == unit
                ),
                None,
            )
            listed = catalogue.get(line.product_id)

            def fallback(product_id: UUID = line.product_id) -> LinePrice:
                """Return a dated revision's price, else the product's own."""
                revised = price_in_force(
                    self._session,
                    product_id,
                    "purchase_price",
                    on=order.purchase_date,
                )
                if revised is not None:
                    return LinePrice(price=revised, source="PRICE_REVISION")
                own = self._session.get(Product, product_id)
                return LinePrice(
                    price=Decimal(str(getattr(own, "purchase_price", 0) or 0)),
                    source="PRODUCT",
                )

            resolved = resolve_supplier_unit_price(
                typed=line.unit_price,
                contract_rate=(
                    Decimal(str(contract.rate)) if contract is not None else None
                ),
                list_rate=lists.price_for(line.product_id, line.ordered_quantity),
                catalogue_rate=(
                    Decimal(str(listed.unit_price))
                    if listed is not None and listed.unit_price is not None
                    else None
                ),
                fallback=fallback,
            )
            from_contract = resolved.source == "RATE_CONTRACT" and contract is not None
            sources.append(
                (resolved.source, contract.id if from_contract and contract else None)
            )
            update: dict[str, object] = {}
            if line.free_quantity != scheme.free_quantity:
                update["free_quantity"] = scheme.free_quantity
            price = resolved.price
            if line.unit_price is None:
                update["unit_price"] = price
            if line.discount_percent is None:
                resolved_discount = resolve_line_discount(
                    gross=self._q(line.ordered_quantity * price),
                    amount=line.discount_amount or None,
                    # The contract's discount is the arrangement where the
                    # contract priced the line, zero included.
                    price_list_percent=(
                        Decimal(str(contract.discount_percent))
                        if from_contract and contract is not None
                        else lists.rate_for(line.product_id, line.ordered_quantity)
                    ),
                    customer_default=standing if standing > ZERO else None,
                )
                update["discount_percent"] = resolved_discount.percent
                update["discount_amount"] = (
                    line.discount_amount if line.discount_amount else ZERO
                )
            priced.append(line.model_copy(update=update) if update else line)
        return priced, sources, schemes

    def _line_discount_amount(
        self, line: PurchaseLineWrite, gross_amount: Decimal
    ) -> Decimal:
        """Return a line's own discount: the typed amount, else the rate."""
        if line.discount_amount <= 0:
            return self._q(
                gross_amount * (line.discount_percent or ZERO) / Decimal("100")
            )
        return self._q(line.discount_amount)

    def _replace_schedules(
        self,
        order: PurchaseOrder,
        *,
        data: PurchaseOrderCreate | PurchaseOrderUpdate | PurchaseOrderAmend,
        actor_id: UUID,
    ) -> None:
        """Replace schedules."""
        line_map = {
            item.line_number: item
            for item in self._session.scalars(
                select(PurchaseOrderLine).where(
                    PurchaseOrderLine.purchase_order_id == order.id
                )
            ).all()
        }
        self._session.query(PurchaseDeliverySchedule).where(
            PurchaseDeliverySchedule.firm_id == order.firm_id,
            (
                PurchaseDeliverySchedule.purchase_order_line_id.in_(
                    [item.id for item in line_map.values()]
                )
                if line_map
                else false()
            ),
        ).delete(synchronize_session=False)
        for schedule in data.delivery_schedules:
            line = line_map.get(schedule.line_number)
            if line is None:
                raise ValidationError(
                    f"Delivery schedule references unknown line {schedule.line_number}."
                )
            self._session.add(
                PurchaseDeliverySchedule(
                    purchase_order_line_id=line.id,
                    firm_id=order.firm_id,
                    delivery_date=schedule.delivery_date,
                    quantity=self._q(schedule.quantity),
                    status="PENDING",
                    remarks=schedule.remarks,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_attachments(
        self,
        order: PurchaseOrder,
        *,
        data: PurchaseOrderCreate | PurchaseOrderUpdate | PurchaseOrderAmend,
        actor_id: UUID,
    ) -> None:
        """Replace attachments."""
        self._session.query(PurchaseAttachment).filter(
            PurchaseAttachment.purchase_order_id == order.id
        ).delete(synchronize_session=False)
        for item in data.attachments:
            self._session.add(
                PurchaseAttachment(
                    purchase_order_id=order.id,
                    firm_id=order.firm_id,
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
        order: PurchaseOrder,
        *,
        data: PurchaseOrderCreate | PurchaseOrderUpdate | PurchaseOrderAmend,
        actor_id: UUID,
    ) -> None:
        """Replace notes."""
        self._session.query(PurchaseNote).filter(
            PurchaseNote.purchase_order_id == order.id
        ).delete(synchronize_session=False)
        for item in data.notes:
            self._session.add(
                PurchaseNote(
                    purchase_order_id=order.id,
                    firm_id=order.firm_id,
                    note_type=item.note_type.value,
                    note=item.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _history_time(self) -> datetime:
        """Return a timestamp strictly later than the last history row's.

        `created_at` defaults to `func.now()`, which in PostgreSQL is the
        *transaction's* start time -- identical for every row a request
        writes. So the two rows an edit of an approved order leaves, the edit
        itself and the withdrawal of its approval, carried the same timestamp,
        and `order_history` orders on `created_at` alone: the trail could read
        "approval withdrawn, then edited", which is backwards, and no client
        could sort it right either (D-BUY-8).

        Stamped here rather than left to the database, and made strictly
        increasing rather than merely re-read, because the system clock's
        resolution is coarse enough on Windows for two consecutive reads to
        return the same microsecond.
        """
        now = utc_now()
        if self._last_history_at is not None and now <= self._last_history_at:
            now = self._last_history_at + timedelta(microseconds=1)
        self._last_history_at = now
        return now

    def _history(
        self,
        *,
        order: PurchaseOrder,
        action: str,
        from_status: str | None,
        to_status: str | None,
        actor_id: UUID,
        details: dict[str, object] | None = None,
        remarks: str | None = None,
    ) -> None:
        """History ."""
        self._session.add(
            PurchaseOrderHistory(
                purchase_order_id=order.id,
                firm_id=order.firm_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
                remarks=remarks,
                details_json=json.dumps(details or {}),
                created_at=self._history_time(),
                created_by=actor_id,
                updated_by=actor_id,
            )
        )

    def _record_document_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        order: PurchaseOrder,
        action: str,
        from_state: str | None,
        to_state: str | None,
        actor_id: UUID,
        details: dict[str, object] | None = None,
        remarks: str | None = None,
    ) -> None:
        """Record document event."""
        self._documents.record_event(
            firm_id,
            DocumentLifecycleEventCreate(
                document_type_id=document_type.id,
                source_document_id=order.id,
                source_module_code="PURCHASE",
                document_number=order.po_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json=details,
                actor_id=actor_id,
            ),
            actor_id,
        )

    def _validate_scope_references(
        self, *, firm_id: UUID, branch_id: UUID, warehouse_id: UUID, vendor_id: UUID
    ) -> None:
        """Validate scope references."""
        branch = self._session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.firm_id == firm_id,
                Branch.is_deleted.is_(False),
            )
        )
        if branch is None:
            raise ValidationError("Selected branch is not available in this firm.")
        if branch.status != "ACTIVE":
            raise ValidationError("Inactive branches cannot be used in purchases.")
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Selected warehouse is not available in this firm.")
        if warehouse.status != "ACTIVE":
            raise ValidationError("Inactive warehouses cannot be used in purchases.")
        if warehouse.branch_id != branch.id:
            raise ValidationError("Warehouse does not belong to selected branch.")
        vendor = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if vendor is None:
            raise ValidationError("Selected vendor is not available in this firm.")
        if vendor.status == "BLOCKED":
            why = f": {vendor.blocked_reason}" if vendor.blocked_reason else ""
            raise ValidationError(
                "Inactive or blocked vendors cannot be used in purchases. "
                f"{vendor.display_name} is blocked{why}; no new order can be "
                "raised to them."
            )
        if vendor.status != "ACTIVE":
            raise ValidationError(
                "Inactive or blocked vendors cannot be used in purchases."
            )

    def _validate_storage_scope(
        self, firm_id: UUID, warehouse_id: UUID | None, storage_node_id: UUID | None
    ) -> None:
        """Validate storage scope."""
        if warehouse_id is None or storage_node_id is None:
            return
        warehouse = self._session.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.firm_id == firm_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if warehouse is None:
            raise ValidationError("Line warehouse is unavailable for this firm.")
        storage = self._session.scalar(
            select(WarehouseStorageNode).where(
                WarehouseStorageNode.id == storage_node_id,
                WarehouseStorageNode.warehouse_id == warehouse_id,
                WarehouseStorageNode.is_deleted.is_(False),
            )
        )
        if storage is None:
            raise ValidationError(
                "Line storage area is unavailable for selected warehouse."
            )
        if not storage.is_active:
            raise ValidationError("Inactive storage areas cannot be used in purchases.")

    def _active_product(self, firm_id: UUID, product_id: UUID) -> Product:
        """Active product."""
        row = self._session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.firm_id == firm_id,
                Product.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ValidationError("Selected product is not available in this firm.")
        if row.status == "DISCONTINUED":
            # Sold until gone, never bought again (STK-17).
            raise ValidationError(
                f"{row.code} ({row.name}) is discontinued: it is sold until the "
                "stock is gone but not bought again. Set it active to order it."
            )
        if row.status != "ACTIVE":
            raise ValidationError("Inactive/blocked products cannot be purchased.")
        return row

    def _line_tax_amount(
        self,
        *,
        firm_id: UUID,
        actor_id: UUID,
        tax_profile_id: UUID | None,
        vendor_id: UUID,
        branch_id: UUID | None,
        product_id: UUID,
        purchase_date: date,
        taxable: Decimal,
        document_id: UUID | None = None,
        line_number: int | None = None,
    ) -> Decimal:
        """Line tax amount."""
        if tax_profile_id is None:
            return Decimal("0")
        self._assert_tax_profile_available(tax_profile_id, firm_id=firm_id)
        simulation = self._tax.simulate(
            TaxRuleSimulationRequest(
                # The supply's own nature, not just the document's name: a
                # supplier in another state charges IGST (D-CMP-14).
                transaction_type=self._tax.inward_transaction_type(
                    "PURCHASE",
                    firm_id=firm_id,
                    branch_id=branch_id,
                    vendor_id=vendor_id,
                ),
                transaction_date=purchase_date,
                tax_profile_id=tax_profile_id,
                branch_id=branch_id,
                vendor_id=vendor_id,
                product_id=product_id,
                invoice_value=self._q(taxable),
                additional_context={
                    "source": "purchase_order",
                    "document_type": "PURCHASE",
                },
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            document_id=document_id,
            line_number=line_number,
        )
        return self._q(simulation.total_tax_amount)

    def _conversion(
        self,
        *,
        quantity: Decimal,
        purchase_uom_id: UUID | None,
        inventory_uom_id: UUID | None,
        product_id: UUID,
        purchase_date: date,
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
                conversion_date=purchase_date,
            ),
            firm_scope=firm_id,
        )
        return {
            "factor": response.conversion_factor,
            "converted": self._q(response.converted_quantity),
            "version": response.version_number,
        }

    def _validate_line_dates(self, line: PurchaseOrderLine) -> None:
        """Validate line dates."""
        if line.expiry_required and line.expiry_date is None:
            raise ValidationError(
                "Expiry date is required for lines marked as expiry-required."
            )
        if (
            line.manufacturing_date is not None
            and line.expiry_date is not None
            and line.expiry_date < line.manufacturing_date
        ):
            raise ValidationError("Expiry date cannot be before manufacturing date.")
        if line.expiry_date is not None:
            existing_batch = self._session.scalar(
                select(BatchRecord).where(
                    BatchRecord.firm_id == line.firm_id,
                    BatchRecord.product_id == line.product_id,
                    BatchRecord.expiry_date == line.expiry_date,
                    BatchRecord.is_deleted.is_(False),
                )
            )
            if existing_batch is not None and _batch_is_expired(existing_batch):
                raise ValidationError("Expired products cannot be purchased.")

    def _assert_tax_profile_available(
        self, profile_id: UUID, *, firm_id: UUID, document_date: date | None = None
    ) -> None:
        """Reject a profile that is unavailable, or not in force on the document."""
        service = TaxFrameworkService(self._session)
        if document_date is None:
            profile = self._session.scalar(
                select(TaxProfile).where(
                    TaxProfile.id == profile_id,
                    TaxProfile.firm_id == firm_id,
                    TaxProfile.is_deleted.is_(False),
                )
            )
            if profile is None:
                raise ValidationError(
                    "Selected tax profile is not available in this firm."
                )
            if profile.status != "ACTIVE":
                raise ValidationError(
                    "Inactive tax profiles cannot be used in purchases."
                )
            return
        service.assert_profile_effective_on(
            profile_id, document_date, firm_scope=firm_id
        )

    def _validate_import_records(
        self, records: list[PurchaseOrderCreate], *, firm_scope: UUID
    ) -> None:
        """Validate import records."""
        explicit_numbers = [
            record.po_number.strip().upper()
            for record in records
            if record.po_number and record.po_number.strip()
        ]
        duplicate_numbers = {
            number for number in explicit_numbers if explicit_numbers.count(number) > 1
        }
        if duplicate_numbers:
            duplicate_list = ", ".join(sorted(duplicate_numbers))
            raise ConflictError(
                "Duplicate purchase order numbers found in import payload: "
                f"{duplicate_list}."
            )
        if not explicit_numbers:
            return
        existing = self._session.scalars(
            select(PurchaseOrder.po_number).where(
                PurchaseOrder.firm_id == firm_scope,
                func.upper(PurchaseOrder.po_number).in_(explicit_numbers),
            )
        ).all()
        if existing:
            duplicate_list = ", ".join(sorted({item for item in existing if item}))
            raise ConflictError(
                f"Purchase order numbers already exist in this firm: {duplicate_list}."
            )

    def _import_record(
        self,
        *,
        branch_id: str,
        warehouse_id: str,
        vendor_id: str,
        product_id: str,
        purchase_date: str,
        ordered_quantity: str,
        unit_price: str,
        po_number: str | None,
        remarks: str | None,
        purchase_uom_id: str | None,
        inventory_uom_id: str | None,
        tax_profile_id: str | None,
        expected_delivery_date: str | None,
        status: str | None,
    ) -> PurchaseOrderCreate:
        """Import record."""
        payload: dict[str, object] = {
            "po_number": po_number,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "vendor_id": vendor_id,
            "purchase_date": purchase_date,
            "remarks": remarks,
            "lines": [
                {
                    "product_id": product_id,
                    "purchase_uom_id": purchase_uom_id,
                    "inventory_uom_id": inventory_uom_id,
                    "ordered_quantity": ordered_quantity,
                    "unit_price": unit_price,
                    "tax_profile_id": tax_profile_id,
                }
            ],
        }
        if expected_delivery_date:
            payload["expected_delivery_date"] = expected_delivery_date
        if status:
            payload["status"] = status
        return PurchaseOrderCreate.model_validate(payload)

    # ---- reports -------------------------------------------------------

    #: The statuses that mean the vendor still owes goods.
    #: ``_resync_order_status`` derives these by summing the completed
    #: receipts, so reading the status is reading what the receipts already
    #: said -- a second way of working the same thing out is a second answer
    #: waiting to disagree with the first.
    _AWAITING = (
        PurchaseOrderStatus.APPROVED.value,
        PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
    )

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrderRegisterRecord]:
        """Return every purchase order raised, newest first.

        Args:
            firm_scope: The firm whose orders to list.
            window: The days, on `purchase_date`, and the page to answer; the
                orders are paged in SQL.

        Returns:
            One record per order, cancelled ones included -- a register states
            what was raised, and an order called off was still raised.

        """
        rows = window.fetch(
            self._session, self._report_orders_statement(firm_scope, window)
        )
        names = self._vendor_names({row.vendor_id for row in rows})
        records = [
            PurchaseOrderRegisterRecord(
                order_id=row.id,
                po_number=row.po_number,
                purchase_date=row.purchase_date,
                expected_delivery_date=row.expected_delivery_date,
                vendor_id=row.vendor_id,
                vendor_name=names.get(row.vendor_id, str(row.vendor_id)),
                buyer_id=row.buyer_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                status=PurchaseOrderStatus(row.status),
                grand_total=row.grand_total,
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def pending_report(self, *, firm_scope: UUID) -> list[PurchaseOrderPendingRecord]:
        """Return orders the vendor still owes goods against.

        Args:
            firm_scope: The firm whose orders to list.

        Returns:
            One record per order still in the receiving part of its life.

        """
        rows = [
            row
            for row in self._report_orders(firm_scope)
            if row.status in self._AWAITING
        ]
        names = self._vendor_names({row.vendor_id for row in rows})
        return [
            PurchaseOrderPendingRecord(
                order_id=row.id,
                po_number=row.po_number,
                purchase_date=row.purchase_date,
                expected_delivery_date=row.expected_delivery_date,
                vendor_id=row.vendor_id,
                vendor_name=names.get(row.vendor_id, str(row.vendor_id)),
                status=PurchaseOrderStatus(row.status),
                order_value=row.grand_total,
            )
            for row in rows
        ]

    def overdue_report(self, *, firm_scope: UUID) -> list[PurchaseOrderOverdueRecord]:
        """Return orders whose goods were expected and have not all arrived.

        An order carrying no expected date is left out rather than counted as
        overdue: nobody named a day, so no day has been missed.

        Args:
            firm_scope: The firm whose orders to list.

        Returns:
            One record per late order, worst first.

        """
        # Today in UTC. Everything stored here is UTC, so the server's own
        # date is already tomorrow, or still yesterday, for part of every day.
        today = utc_now().date()
        rows = [
            row
            for row in self._report_orders(firm_scope)
            if row.status in self._AWAITING
            and row.expected_delivery_date is not None
            and row.expected_delivery_date < today
        ]
        names = self._vendor_names({row.vendor_id for row in rows})
        records = [
            PurchaseOrderOverdueRecord(
                order_id=row.id,
                po_number=row.po_number,
                purchase_date=row.purchase_date,
                expected_delivery_date=row.expected_delivery_date,
                days_overdue=(today - row.expected_delivery_date).days,
                vendor_id=row.vendor_id,
                vendor_name=names.get(row.vendor_id, str(row.vendor_id)),
                status=PurchaseOrderStatus(row.status),
                order_value=row.grand_total,
            )
            for row in rows
            if row.expected_delivery_date is not None
        ]
        return sorted(records, key=lambda record: -record.days_overdue)

    def by_vendor_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrderByVendorRecord]:
        """Return ordered value and count per vendor.

        Cancelled orders are left out: an order called off was never a
        purchase, and counting it overstates what the firm has committed.

        Args:
            firm_scope: The firm whose orders to total.
            window: The days, on `purchase_date`, to total over.

        Returns:
            One record per vendor, largest first.

        """
        totals: dict[UUID, Decimal] = {}
        counts: dict[UUID, int] = {}
        for row in self._live_report_orders(firm_scope, window):
            totals[row.vendor_id] = totals.get(row.vendor_id, ZERO) + Decimal(
                str(row.grand_total)
            )
            counts[row.vendor_id] = counts.get(row.vendor_id, 0) + 1
        names = self._vendor_names(set(counts))
        return [
            PurchaseOrderByVendorRecord(
                vendor_id=vendor_id,
                vendor_name=names.get(vendor_id, str(vendor_id)),
                order_count=counts[vendor_id],
                total_value=total,
            )
            for vendor_id, total in sorted(totals.items(), key=lambda item: -item[1])
        ]

    def by_buyer_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrderByBuyerRecord]:
        """Return ordered value and count per buyer.

        An order naming no buyer contributes nothing rather than being pooled
        under a blank name: the column is nullable, and a row headed by nobody
        is not a person's purchasing record.

        Args:
            firm_scope: The firm whose orders to total.
            window: The days, on `purchase_date`, to total over.

        Returns:
            One record per buyer, largest first.

        """
        totals: dict[UUID, Decimal] = {}
        counts: dict[UUID, int] = {}
        for row in self._live_report_orders(firm_scope, window):
            if row.buyer_id is None:
                continue
            totals[row.buyer_id] = totals.get(row.buyer_id, ZERO) + Decimal(
                str(row.grand_total)
            )
            counts[row.buyer_id] = counts.get(row.buyer_id, 0) + 1
        names = self._buyer_names(set(counts))
        return [
            PurchaseOrderByBuyerRecord(
                buyer_id=buyer_id,
                buyer_name=names.get(buyer_id, str(buyer_id)),
                order_count=counts[buyer_id],
                total_value=total,
            )
            for buyer_id, total in sorted(totals.items(), key=lambda item: -item[1])
        ]

    def by_product_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrderByProductRecord]:
        """Return what the firm is buying, by quantity and by value.

        Args:
            firm_scope: The firm whose orders to total.
            window: The days, on `purchase_date`, to total over.

        Returns:
            One record per product, most-ordered first.

        """
        # Grouped in SQL: it read every live order of the window and then all
        # their lines whole, 3.8 s for a year on the volume firm (backlog 56 C,
        # step 4).
        grouped = self._session.execute(
            select(
                PurchaseOrderLine.product_id,
                func.coalesce(func.sum(PurchaseOrderLine.ordered_quantity), 0),
                func.coalesce(func.sum(PurchaseOrderLine.net_amount), 0),
                func.count(func.distinct(PurchaseOrderLine.purchase_order_id)),
            )
            .join(
                PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
            )
            .where(
                PurchaseOrder.firm_id == firm_scope,
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.status != PurchaseOrderStatus.CANCELLED.value,
                *window.dated(PurchaseOrder.purchase_date),
                PurchaseOrderLine.is_deleted.is_(False),
            )
            .group_by(PurchaseOrderLine.product_id)
        ).all()
        if not grouped:
            return []
        quantities: dict[UUID, Decimal] = {}
        values: dict[UUID, Decimal] = {}
        counts: dict[UUID, int] = {}
        for product_id, quantity, value, count in grouped:
            quantities[product_id] = Decimal(str(quantity))
            values[product_id] = Decimal(str(value))
            counts[product_id] = int(count)
        products = {
            product_id: (code, name)
            for part in chunks(list(quantities))
            for product_id, code, name in self._session.execute(
                select(Product.id, Product.code, Product.name).where(
                    Product.id.in_(part)
                )
            ).all()
        }
        return [
            PurchaseOrderByProductRecord(
                product_id=product_id,
                product_code=products.get(product_id, ("", ""))[0],
                product_name=products.get(product_id, ("", str(product_id)))[1],
                ordered_quantity=quantity,
                total_value=values[product_id],
                order_count=counts[product_id],
            )
            for product_id, quantity in sorted(
                quantities.items(), key=lambda item: -item[1]
            )
        ]

    def _report_orders(
        self, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrder]:
        """Return every order this firm raised in ``window``, newest first."""
        return list(
            self._session.scalars(
                self._report_orders_statement(firm_scope, window)
            ).all()
        )

    @staticmethod
    def _report_orders_statement(
        firm_scope: UUID, window: ReportWindow
    ) -> Select[tuple[PurchaseOrder]]:
        """Select the orders raised in ``window``, on their `purchase_date`."""
        return (
            select(PurchaseOrder)
            .where(
                PurchaseOrder.firm_id == firm_scope,
                PurchaseOrder.is_deleted.is_(False),
                *window.dated(PurchaseOrder.purchase_date),
            )
            .order_by(
                PurchaseOrder.purchase_date.desc(),
                PurchaseOrder.created_at.desc(),
                PurchaseOrder.id.desc(),
            )
        )

    def _live_report_orders(
        self, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseOrder]:
        """Return the orders that still stand, cancelled ones left out."""
        return [
            row
            for row in self._report_orders(firm_scope, window)
            if row.status != PurchaseOrderStatus.CANCELLED.value
        ]

    def _vendor_names(self, ids: set[UUID]) -> dict[UUID, str]:
        """Read the vendor names in one query rather than one per row."""
        if not ids:
            return {}
        return {
            row.id: row.display_name
            for row in self._session.scalars(
                select(Vendor).where(Vendor.id.in_(list(ids)))
            ).all()
        }

    def _buyer_names(self, ids: set[UUID]) -> dict[UUID, str]:
        """Name the buyers, reading the store that actually holds the users.

        That table lives only in the platform schema, so a tenant session
        cannot see it -- the trap this repo has hit eight times, every one of
        them latent until a document carried the id. SQLite keeps every table
        in one schema, so the unit suite reads it on the request session and
        could never catch this; only ``tests/integration/`` can.
        """
        if not ids:
            return {}
        statement = select(User.id, User.full_name).where(User.id.in_(list(ids)))
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            rows = list(self._session.execute(statement).all())
        else:
            with platform_reader() as reader:
                rows = list(reader.execute(statement).all())
        return {row[0]: row[1] for row in rows}
