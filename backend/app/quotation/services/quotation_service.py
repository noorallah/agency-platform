"""Quotation workflow: an offer that commits nothing until it is accepted.

The defining property of this module is what it does **not** do. A quotation
reserves no stock, moves no customer balance and writes no journal. Everything
the firm actually promises happens at conversion, through
``SalesOrderService.create_order`` -- so credit control, tax resolution and unit
conversion are applied when the order exists rather than months earlier when
somebody quoted a price, and a quote written against a credit limit that has
since been cut is refused at the point it matters.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.common.report_names import customer_names
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.pricing import (
    LineDiscount,
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
)
from app.customers.models import Customer, CustomerGroup
from app.customers.services.trading_status import (
    assert_customer_takes_new_documents,
)
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import DocumentLifecycleEventCreate
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)
from app.pricing.services.price_list_service import PriceListResolver
from app.products.models import Product
from app.products.services.trading_status import assert_product_takes_new_lines
from app.promotions.schemas import (
    PromotionEvaluationRequest,
    PromotionLineRequest,
)
from app.promotions.services import PromotionService
from app.quotation.models import (
    SalesQuotation,
    SalesQuotationAttachment,
    SalesQuotationLine,
    SalesQuotationNote,
)
from app.quotation.schemas import (
    QuotationAttachmentResponse,
    QuotationAttachmentWrite,
    QuotationConversionRecord,
    QuotationCreate,
    QuotationImportRequest,
    QuotationLineResponse,
    QuotationLineWrite,
    QuotationListFilters,
    QuotationNoteResponse,
    QuotationNoteWrite,
    QuotationPreview,
    QuotationPreviewLine,
    QuotationRegisterRecord,
    QuotationResponse,
    QuotationStatus,
    QuotationSummary,
)
from app.sales.services.scope_resolution import resolve_sales_scope
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_order.services.sales_order_service import PromotionBenefits
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.place_of_supply import SALES_INTERSTATE
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.services import assert_quantity_fits_unit

ZERO = Decimal("0")

#: Statuses in which an offer is no longer on the table.
_SETTLED = (
    QuotationStatus.DECLINED.value,
    QuotationStatus.CONVERTED.value,
    QuotationStatus.CANCELLED.value,
)


class QuotationService(TransactionalDocumentService):
    """Coordinate the quotation lifecycle and its conversion to an order."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_QUOTATION",
        name="Sales Quotation",
        description="Customer quotation document",
        category="SALES",
        module="quotation",
        prefix="QT",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("SENT", "Sent", 2, allows_edit=True),
            DocumentStateSpec("ACCEPTED", "Accepted", 3),
            DocumentStateSpec("DECLINED", "Declined", 4, is_terminal=True),
            DocumentStateSpec("CONVERTED", "Converted", 5, is_terminal=True),
            DocumentStateSpec("CANCELLED", "Cancelled", 6, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._tax = TaxRuleService(session)

    # ---- reads ---------------------------------------------------------

    def list_quotations(
        self,
        *,
        firm_scope: UUID,
        filters: QuotationListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SalesQuotation], int]:
        """List quotations for the visible firm scope."""
        columns = {
            "quotation_number": SalesQuotation.quotation_number,
            "quotation_date": SalesQuotation.quotation_date,
            "valid_until": SalesQuotation.valid_until,
            "grand_total": SalesQuotation.grand_total,
            "status": SalesQuotation.status,
            "created_at": SalesQuotation.created_at,
        }
        statement = select(SalesQuotation).where(SalesQuotation.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(SalesQuotation)
            .where(SalesQuotation.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(SalesQuotation.is_deleted.is_(False))
            count = count.where(SalesQuotation.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(
                SalesQuotation.customer_id == filters.customer_id
            )
            count = count.where(SalesQuotation.customer_id == filters.customer_id)
        if filters.branch_id is not None:
            statement = statement.where(SalesQuotation.branch_id == filters.branch_id)
            count = count.where(SalesQuotation.branch_id == filters.branch_id)
        if filters.salesman_id is not None:
            statement = statement.where(
                SalesQuotation.salesman_id == filters.salesman_id
            )
            count = count.where(SalesQuotation.salesman_id == filters.salesman_id)
        if filters.status is not None:
            statement = statement.where(SalesQuotation.status == filters.status.value)
            count = count.where(SalesQuotation.status == filters.status.value)
        if filters.quotation_from is not None:
            statement = statement.where(
                SalesQuotation.quotation_date >= filters.quotation_from
            )
            count = count.where(SalesQuotation.quotation_date >= filters.quotation_from)
        if filters.quotation_to is not None:
            statement = statement.where(
                SalesQuotation.quotation_date <= filters.quotation_to
            )
            count = count.where(SalesQuotation.quotation_date <= filters.quotation_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesQuotation.quotation_number.ilike(token),
                SalesQuotation.customer_reference.ilike(token),
                SalesQuotation.reference_number.ilike(token),
                SalesQuotation.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        column = columns.get(sort_by, SalesQuotation.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    column.desc() if descending else column.asc(),
                    # Newest first within the chosen column, then a stable key.
                    SalesQuotation.created_at.desc(),
                    SalesQuotation.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_quotation(self, quotation_id: UUID, *, firm_scope: UUID) -> SalesQuotation:
        """Return one quotation within the visible firm scope."""
        row = self._session.scalar(
            select(SalesQuotation).where(
                SalesQuotation.id == quotation_id,
                SalesQuotation.firm_id == firm_scope,
                SalesQuotation.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Quotation not found.")
        return row

    def summary(self, *, firm_scope: UUID) -> QuotationSummary:
        """Summarise quotations for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesQuotation).where(
                    SalesQuotation.firm_id == firm_scope,
                    SalesQuotation.is_deleted.is_(False),
                )
            ).all()
        )
        today = utc_now().date()

        def count(status: QuotationStatus) -> int:
            return sum(1 for row in rows if row.status == status.value)

        converted = [
            row for row in rows if row.status == QuotationStatus.CONVERTED.value
        ]
        return QuotationSummary(
            total_quotations=len(rows),
            draft_quotations=count(QuotationStatus.DRAFT),
            sent_quotations=count(QuotationStatus.SENT),
            accepted_quotations=count(QuotationStatus.ACCEPTED),
            declined_quotations=count(QuotationStatus.DECLINED),
            converted_quotations=len(converted),
            # Expiry is a date, not a status, so it is counted rather than
            # filtered: a sent quotation that lapsed on Friday is both.
            expired_quotations=sum(
                1
                for row in rows
                if row.valid_until < today and row.status not in _SETTLED
            ),
            total_quoted_value=self._q(sum((row.grand_total for row in rows), ZERO)),
            total_converted_value=self._q(
                sum((row.grand_total for row in converted), ZERO)
            ),
        )

    def timeline(
        self, quotation_id: UUID, *, firm_scope: UUID
    ) -> list[DocumentLifecycleEvent]:
        """Return the lifecycle history of one quotation."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        return list(
            self._session.scalars(
                select(DocumentLifecycleEvent)
                .where(
                    DocumentLifecycleEvent.firm_id == firm_scope,
                    DocumentLifecycleEvent.source_document_id == row.id,
                    DocumentLifecycleEvent.is_deleted.is_(False),
                )
                .order_by(DocumentLifecycleEvent.created_at.asc())
            ).all()
        )

    # ---- writes --------------------------------------------------------

    def create_quotation(
        self, data: QuotationCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesQuotation:
        """Create one quotation in draft."""
        row = self._stage_quotation(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def preview_quotation(
        self, data: QuotationCreate, *, firm_id: UUID, actor_id: UUID
    ) -> QuotationPreview:
        """Price an offer exactly as saving it would, then save nothing.

        The draft is staged through the same path as a save -- so the price
        list, the customer's and group's rates, promotions, the bill discount,
        freight and tax are the ones the save would reach -- read back, and
        the whole unit of work rolled back: no quotation, no number used up,
        no audit row, no tax log. The request's session is its own, so there
        is nothing else in it to lose.
        """
        try:
            row = self._stage_quotation(data, firm_id=firm_id, actor_id=actor_id)
            response = self.quotation_response(row)
            interstate = (
                self._tax.outward_transaction_type(
                    "SALES_QUOTATION",
                    firm_id=firm_id,
                    branch_id=data.branch_id,
                    customer_id=data.customer_id,
                )
                == SALES_INTERSTATE
            )
            lines = self._preview_lines(
                response,
                firm_id=firm_id,
                customer_id=data.customer_id,
                warehouse_id=data.warehouse_id,
            )
        finally:
            self._session.rollback()
        return QuotationPreview(quotation=response, interstate=interstate, lines=lines)

    def _preview_lines(
        self,
        response: QuotationResponse,
        *,
        firm_id: UUID,
        customer_id: UUID,
        warehouse_id: UUID | None,
    ) -> list[QuotationPreviewLine]:
        """Each line's last price to this customer and its free stock."""
        # Imported here: the sales invoice module reads quotations.
        from app.inventory.models import InventoryRecord
        from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

        product_ids = {line.product_id for line in response.lines}
        last: dict[UUID, tuple[Decimal, str, date]] = {}
        if product_ids:
            billed = self._session.execute(
                select(
                    SalesInvoiceLine.product_id,
                    SalesInvoiceLine.unit_price,
                    SalesInvoice.invoice_number,
                    SalesInvoice.invoice_date,
                )
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(
                    SalesInvoice.firm_id == firm_id,
                    SalesInvoice.customer_id == customer_id,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoice.status.in_(["APPROVED", "CLOSED"]),
                    SalesInvoiceLine.product_id.in_(product_ids),
                )
                .order_by(
                    SalesInvoice.invoice_date.desc(),
                    SalesInvoice.created_at.desc(),
                )
            ).all()
            for product_id, price, number, on in billed:
                last.setdefault(product_id, (price, number, on))
        stock: dict[UUID, Decimal] = {}
        if product_ids and warehouse_id is not None:
            for product_id, available in self._session.execute(
                select(
                    InventoryRecord.product_id,
                    func.coalesce(func.sum(InventoryRecord.available_quantity), 0),
                )
                .where(
                    InventoryRecord.firm_id == firm_id,
                    InventoryRecord.warehouse_id == warehouse_id,
                    InventoryRecord.is_deleted.is_(False),
                    InventoryRecord.product_id.in_(product_ids),
                )
                .group_by(InventoryRecord.product_id)
            ).all():
                stock[product_id] = Decimal(str(available))
        result: list[QuotationPreviewLine] = []
        for line in response.lines:
            previous = last.get(line.product_id)
            result.append(
                QuotationPreviewLine(
                    line_number=line.line_number,
                    product_id=line.product_id,
                    last_price=previous[0] if previous else None,
                    last_invoice_number=previous[1] if previous else None,
                    last_invoice_date=previous[2] if previous else None,
                    available_quantity=stock.get(line.product_id, Decimal("0")),
                )
            )
        return result

    def _stage_quotation(
        self, data: QuotationCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesQuotation:
        """Build one quotation without committing it.

        Split out so an import can stage a whole batch and commit once, rather
        than leaving half a file written when a later row is refused.
        """
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        customer = self._require_customer(data.customer_id, firm_id=firm_id)
        assert_customer_takes_new_documents(customer, document="quotation")
        quotation_number = self._issue_number(
            numbering_rule,
            typed=data.quotation_number,
            number_column=SalesQuotation.quotation_number,
            firm_id=firm_id,
            document_date=data.quotation_date,
            actor_id=actor_id,
            branch_code=self._scope_code(data.branch_id),
            company_code=self._company_code(firm_id),
        )
        scope = resolve_sales_scope(
            self._session,
            firm_id=firm_id,
            customer_id=data.customer_id,
            territory_id=data.territory_id,
            salesman_id=data.salesman_id,
            on_date=data.quotation_date,
        )
        row = SalesQuotation(
            firm_id=firm_id,
            customer_id=data.customer_id,
            salesman_id=scope.salesman_id,
            territory_id=scope.territory_id,
            branch_id=data.branch_id,
            warehouse_id=data.warehouse_id,
            business_profile_id=data.business_profile_id,
            quotation_number=quotation_number,
            quotation_date=data.quotation_date,
            valid_until=data.valid_until,
            customer_reference=data.customer_reference,
            reference_number=data.reference_number,
            payment_terms=data.payment_terms,
            delivery_terms=data.delivery_terms,
            currency_code=data.currency_code,
            exchange_rate=data.exchange_rate,
            remarks=data.remarks,
            status=QuotationStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        # Not a bare flush: a duplicate number clashes here, before the
        # catch-all below is reached, and an IntegrityError escaping the
        # service is a 500 where the caller should be told 409 -- which is the
        # likeliest way a batch import goes wrong.
        self._flush_or_conflict("Quotation number already exists in this firm.")
        self._apply_children(row, data, actor_id=actor_id)
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
            action="quotation.created",
            entity_type="quotation",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "quotation_number": row.quotation_number,
                "status": row.status,
            },
        )
        self._flush_or_conflict("Quotation number already exists in this firm.")
        return row

    def update_quotation(
        self,
        quotation_id: UUID,
        data: QuotationCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> SalesQuotation:
        """Replace one quotation that has not been decided on.

        A sent quotation can still be edited -- a customer asking for a revised
        price is the ordinary case, and forcing a new document for it would
        lose the thread. Once accepted, declined or converted it is a record of
        what was agreed and stops being editable.
        """
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status not in {
            QuotationStatus.DRAFT.value,
            QuotationStatus.SENT.value,
        }:
            raise ValidationError("Only draft or sent quotations can be edited.")
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        customer = self._require_customer(data.customer_id, firm_id=firm_scope)
        # A quotation already sent carries on when its customer goes inactive;
        # moving it to one who is, is a new offer to them (D-MST-6).
        if data.customer_id != row.customer_id:
            assert_customer_takes_new_documents(customer, document="quotation")
        before: dict[str, object] = {
            "grand_total": str(row.grand_total),
            "valid_until": row.valid_until.isoformat(),
        }
        scope = resolve_sales_scope(
            self._session,
            firm_id=firm_scope,
            customer_id=data.customer_id,
            territory_id=data.territory_id,
            salesman_id=data.salesman_id,
            on_date=data.quotation_date,
        )
        row.customer_id = data.customer_id
        row.salesman_id = scope.salesman_id
        row.territory_id = scope.territory_id
        row.branch_id = data.branch_id
        row.warehouse_id = data.warehouse_id
        row.business_profile_id = data.business_profile_id
        row.quotation_date = data.quotation_date
        row.valid_until = data.valid_until
        row.customer_reference = data.customer_reference
        row.reference_number = data.reference_number
        row.payment_terms = data.payment_terms
        row.delivery_terms = data.delivery_terms
        row.currency_code = data.currency_code
        row.exchange_rate = data.exchange_rate
        row.remarks = data.remarks
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        self._apply_children(row, data, actor_id=actor_id)
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
            action="quotation.updated",
            entity_type="quotation",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={
                "grand_total": str(row.grand_total),
                "valid_until": row.valid_until.isoformat(),
            },
        )
        self._flush_or_conflict("Quotation number already exists in this firm.")
        self._session.commit()
        return row

    def send_quotation(
        self, quotation_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesQuotation:
        """Mark a quotation as sent to the customer."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status == QuotationStatus.SENT.value:
            return row
        if row.status != QuotationStatus.DRAFT.value:
            raise ValidationError("Only draft quotations can be sent.")
        if self.is_expired(row):
            raise ValidationError(
                f"Quotation {row.quotation_number} expired on {row.valid_until}. "
                "Extend its validity before sending it."
            )
        return self._move(
            row,
            QuotationStatus.SENT,
            action="SENT",
            firm_scope=firm_scope,
            actor_id=actor_id,
            stamp="sent_at",
        )

    def accept_quotation(
        self,
        quotation_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesQuotation:
        """Record that the customer accepted the offer."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status == QuotationStatus.ACCEPTED.value:
            return row
        if row.status not in {
            QuotationStatus.DRAFT.value,
            QuotationStatus.SENT.value,
        }:
            raise ValidationError("This quotation can no longer be accepted.")
        if self.is_expired(row):
            raise ValidationError(
                f"Quotation {row.quotation_number} expired on {row.valid_until} "
                "and cannot be accepted at those prices."
            )
        return self._move(
            row,
            QuotationStatus.ACCEPTED,
            action="ACCEPTED",
            firm_scope=firm_scope,
            actor_id=actor_id,
            stamp="decided_at",
            remarks=reason,
        )

    def decline_quotation(
        self,
        quotation_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesQuotation:
        """Record that the customer said no, and why."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status == QuotationStatus.DECLINED.value:
            return row
        if row.status in _SETTLED:
            raise ValidationError("This quotation can no longer be declined.")
        row.decline_reason = reason
        return self._move(
            row,
            QuotationStatus.DECLINED,
            action="DECLINED",
            firm_scope=firm_scope,
            actor_id=actor_id,
            stamp="decided_at",
            remarks=reason,
        )

    def cancel_quotation(
        self,
        quotation_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesQuotation:
        """Withdraw a quotation the firm no longer stands behind."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status == QuotationStatus.CANCELLED.value:
            return row
        if row.status == QuotationStatus.DECLINED.value:
            # Declined is terminal: the customer said no, and cancelling it
            # would overwrite that answer with the firm's (D-SELL-28).
            raise ValidationError(
                "This quotation was declined by the customer; it cannot be "
                "cancelled."
            )
        if row.status == QuotationStatus.CONVERTED.value:
            raise ValidationError(
                "This quotation became an order; cancel the order instead."
            )
        row.cancel_reason = reason
        return self._move(
            row,
            QuotationStatus.CANCELLED,
            action="CANCELLED",
            firm_scope=firm_scope,
            actor_id=actor_id,
            remarks=reason,
        )

    def convert_quotation(
        self,
        quotation_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        order_date: date | None = None,
        delivery_date: date | None = None,
    ) -> tuple[SalesQuotation, SalesOrder]:
        """Turn an accepted quotation into a sales order.

        The order is built through ``SalesOrderService.create_order`` rather
        than by writing rows here, so everything an order is subject to --
        credit control, tax resolution at the order's date, unit conversion,
        stock snapshots, its own numbering -- happens now, on the order,
        instead of being frozen at whatever was true when the quote was typed.

        The quoted unit prices carry over; the tax does not. A quotation
        offered in March at 12% is still an offer of that net price when it
        becomes an order in April at 18%, and the invoice will charge what the
        rate is then.

        Returns:
            The quotation, now CONVERTED, and the order it became.

        Raises:
            ValidationError: If it was not accepted, has expired, or was
                already converted.

        """
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status == QuotationStatus.CONVERTED.value:
            raise ValidationError(
                f"Quotation {row.quotation_number} already became "
                f"{row.converted_sales_order_number}."
            )
        if row.status != QuotationStatus.ACCEPTED.value:
            raise ValidationError("Only an accepted quotation can become an order.")
        if self.is_expired(row):
            raise ValidationError(
                f"Quotation {row.quotation_number} expired on {row.valid_until} "
                "and cannot be converted at those prices."
            )
        lines = self._lines_of(row.id)
        if not lines:
            raise ValidationError("Quotation must contain at least one line.")
        # Staged, not created: `create_order` commits, and the CONVERTED move
        # below was a second commit, so a failure between them left an order
        # beside a quotation still ACCEPTED -- and convertible again, into a
        # second order for one agreement (D-SELL-14, 2026-09-19). Both halves
        # are written and committed once, together.
        order = SalesOrderService(self._session).stage_order(
            SalesOrderCreate(
                customer_id=row.customer_id,
                salesman_id=row.salesman_id,
                territory_id=row.territory_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                business_profile_id=row.business_profile_id,
                order_date=order_date or utc_now().date(),
                delivery_date=delivery_date,
                customer_reference=row.customer_reference,
                reference_number=row.quotation_number,
                currency_code=row.currency_code,
                exchange_rate=row.exchange_rate,
                remarks=row.remarks,
                additional_charges=row.additional_charges,
                round_off=row.round_off,
                # The deal carries over as the deal, not as each line's share
                # of it. The order re-splits it across whatever lines it ends
                # up with, which keeps the two documents' arithmetic the same
                # rather than merely similar. Only a **typed** bill discount
                # is handed over: an offer's is the order's to find again on
                # its own date and claim (D-SELL-9, D-SELL-32), and handing
                # it a zero read as "refuse every offer on the bill".
                bill_discount_amount=self._typed_bill_discount(row),
                # Freight carries over the same way, and is re-split by the
                # order across whatever lines it ends up with. The charge that
                # was **asked**, not what was left after an offer waived it:
                # the order asks the offers again, and handing it the waived
                # figure would keep the waiver after the offer had gone.
                freight_amount=self._q(row.freight_amount + row.freight_waived_amount),
                lines=[
                    SalesOrderLineWrite(
                        line_number=line.line_number,
                        product_id=line.product_id,
                        description=line.description,
                        quantity=line.quantity,
                        free_quantity=line.free_quantity,
                        sales_uom_id=line.sales_uom_id,
                        inventory_uom_id=line.inventory_uom_id,
                        packaging_type_id=line.packaging_type_id,
                        unit_price=line.unit_price,
                        **self._typed_discount(line),
                        tax_profile_id=line.tax_profile_id,
                        warehouse_id=line.warehouse_id,
                        remarks=line.remarks,
                    )
                    for line in lines
                    # A line of nothing charged is a gift an offer added: the
                    # write schema refuses a quantity of zero, so nobody typed
                    # it. The order's own offers add it again if it is still
                    # given, and claim it (D-SELL-32).
                    if line.quantity > ZERO
                ],
            ),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        row.converted_sales_order_id = order.id
        row.converted_sales_order_number = order.order_number
        row.converted_at = utc_now()
        converted = self._move(
            row,
            QuotationStatus.CONVERTED,
            action="CONVERTED",
            firm_scope=firm_scope,
            actor_id=actor_id,
            remarks=f"Became {order.order_number}",
            commit=False,
        )
        self._session.commit()
        return converted, order

    @staticmethod
    def _typed_bill_discount(row: SalesQuotation) -> Decimal | None:
        """Return the bill discount a converted order is handed, if any.

        Only one somebody typed. A quotation saved before the source was
        recorded (NULL) could only have had a typed one, so its figure stands
        as it always did.
        """
        if row.bill_discount_amount <= ZERO:
            return None
        if row.bill_discount_source in (None, "typed"):
            return row.bill_discount_amount
        return None

    @staticmethod
    def _typed_discount(line: SalesQuotationLine) -> dict[str, Decimal | None]:
        """Return the discount a converted order line is handed, if any.

        Only what somebody **typed** on the quotation carries over as typed,
        in the form they typed it. Everything the pricing rule derived -- an
        offer, a price list, the customer's or their segment's standing rate
        -- is left for the order to derive again, exactly as it would for an
        order raised directly.

        Handing the order both figures of every line, as this did, made every
        line "priced by hand": the promotion engine skipped it, no claim was
        staged and none was counted at approval, so an offer's limits never
        saw a converted order, and the order read `amount` for a discount an
        offer had given (D-SELL-9, 2026-09-19).
        """
        # A line saved before the source was recorded cannot say where its
        # discount came from, so the quoted figure stands as it always did.
        if line.discount_source in (None, "amount"):
            return {"discount_percent": None, "discount_amount": line.discount_amount}
        if line.discount_source == "percent":
            return {"discount_percent": line.discount_percent, "discount_amount": None}
        return {"discount_percent": None, "discount_amount": None}

    def delete_quotation(
        self, quotation_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Soft-delete a quotation nobody has been sent."""
        row = self.get_quotation(quotation_id, firm_scope=firm_scope)
        if row.status != QuotationStatus.DRAFT.value:
            raise ValidationError(
                "Only a draft quotation can be deleted; cancel the rest so the "
                "record of what was offered survives."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="quotation.deleted",
            entity_type="quotation",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"quotation_number": row.quotation_number},
        )
        self._session.commit()

    # ---- rules ---------------------------------------------------------

    def is_expired(self, row: SalesQuotation) -> bool:
        """Whether the quoted prices have lapsed.

        ``utc_now().date()``, never the server's local date: everything here is
        stored in UTC, and on a non-UTC deployment the local date is already
        tomorrow for part of every day -- which would expire a quotation early.
        """
        return row.valid_until < utc_now().date()

    def can_convert(self, row: SalesQuotation) -> bool:
        """Whether this quotation could become an order right now."""
        return row.status == QuotationStatus.ACCEPTED.value and not self.is_expired(row)

    # ---- children ------------------------------------------------------

    def _apply_children(
        self, row: SalesQuotation, data: QuotationCreate, *, actor_id: UUID
    ) -> None:
        totals = self._replace_lines(
            row,
            lines=data.lines,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            freight_amount=data.freight_amount,
            actor_id=actor_id,
        )
        row.line_discount_total = totals["line_discount_total"]
        row.subtotal = totals["subtotal"]
        row.tax_total = totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(row, data.attachments, actor_id=actor_id)
        self._replace_notes(row, data.notes, actor_id=actor_id)

    def _customer_discount(self, customer_id: UUID) -> Decimal | None:
        """Return the customer's standing discount, if they have one.

        None rather than zero when there is no customer or no arrangement, so
        the shared rule can tell "nothing agreed" from "agreed nothing".
        """
        customer = self._session.get(Customer, customer_id)
        if customer is None or customer.default_discount_percent <= ZERO:
            return None
        return self._q(customer.default_discount_percent)

    def _customer_group(self, customer_id: UUID) -> tuple[UUID | None, Decimal | None]:
        """Return the customer's segment and what that segment is normally given.

        None rather than zero for the rate, so the shared rule can tell "no
        segment arrangement" from "a segment that agreed nothing".
        """
        customer = self._session.get(Customer, customer_id)
        if customer is None or customer.customer_group_id is None:
            return None, None
        # The customer's own firm's live segment, and nothing else: read by id
        # alone, another firm's segment in the shared store -- or one retired
        # since -- went on pricing this firm's documents (D-MST-3).
        group = self._session.scalar(
            select(CustomerGroup).where(
                CustomerGroup.id == customer.customer_group_id,
                CustomerGroup.firm_id == customer.firm_id,
                CustomerGroup.is_deleted.is_(False),
            )
        )
        if group is None or not group.is_active:
            return None, None
        rate = self._q(group.default_discount_percent)
        return group.id, (rate if rate > ZERO else None)

    def _promotions(
        self,
        row: SalesQuotation,
        *,
        lines: list[QuotationLineWrite],
        grosses: list[Decimal],
        customer_group_id: UUID | None,
        bill_priced: bool = False,
        freight_amount: Decimal | None = None,
    ) -> PromotionBenefits:
        """Ask the firm's promotions what this offer would earn.

        Evaluated once per document, never committing, exactly as the sales
        order does -- with one difference: **nothing is staged**. A quotation
        is an offer, not a claim; the order it becomes stages its own pending
        redemption when it is priced and claims it when it is approved.

        Told about the bill and the delivery charge the way the order tells
        it, so an offer on the whole bill, a gift and free shipping reach the
        quotation too. Only the line discounts used to, and a quotation read
        higher than the order it became (D-SELL-32, 2026-09-19).
        """
        outcome = PromotionService(self._session).evaluate(
            PromotionEvaluationRequest(
                transaction_type="SALES_QUOTATION",
                transaction_date=row.quotation_date,
                customer_id=row.customer_id,
                customer_group_id=customer_group_id,
                branch_id=row.branch_id,
                territory_id=row.territory_id,
                salesman_id=row.salesman_id,
                caller_priced_bill=bill_priced,
                freight_amount=self._q(freight_amount or ZERO),
                lines=[
                    PromotionLineRequest(
                        line_number=index + 1,
                        product_id=item.product_id,
                        quantity=self._q(item.quantity),
                        gross=grosses[index],
                        caller_priced=(
                            item.discount_percent is not None
                            or item.discount_amount is not None
                        ),
                    )
                    for index, item in enumerate(lines)
                ],
            ),
            firm_scope=row.firm_id,
        )
        return PromotionBenefits(outcome)

    @staticmethod
    def _gift_lines(
        benefits: PromotionBenefits, *, lines: list[QuotationLineWrite]
    ) -> list[QuotationLineWrite]:
        """Turn what the engine gave away into lines the quotation shows.

        The sales order's rule, so the offer and the order read alike: goods
        supplied free and nothing charged, an explicit zero rate so no
        standing discount reaches a line worth nothing, and a gift the caller
        already typed is not doubled. Built without validation because the
        write schema refuses a quantity of zero -- which is also what lets
        the conversion tell these lines from typed ones and leave them to the
        order's own offers.
        """
        gifts = benefits.gifts()
        if not gifts:
            return []
        typed = {item.product_id for item in lines}
        next_number = max((item.line_number for item in lines), default=0) + 1
        added: list[QuotationLineWrite] = []
        for gift in gifts:
            if gift.product_id in typed:
                continue
            added.append(
                QuotationLineWrite.model_construct(
                    line_number=next_number + len(added),
                    product_id=gift.product_id,
                    description=f"Free with {gift.promotion_code}",
                    quantity=ZERO,
                    free_quantity=gift.quantity,
                    unit_price=ZERO,
                    discount_percent=ZERO,
                    discount_amount=None,
                    sales_uom_id=None,
                    inventory_uom_id=None,
                    packaging_type_id=None,
                    tax_profile_id=None,
                    warehouse_id=None,
                    remarks=None,
                )
            )
        return added

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
        row: SalesQuotation,
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
        the rate it represents, rather than whatever the caller sent, so the
        two figures on the document agree with each other and with its lines.
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
        row: SalesQuotation,
        *,
        lines: list[QuotationLineWrite],
        bill_percent: Decimal | None,
        bill_amount: Decimal | None,
        freight_amount: Decimal | None = None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        """Reconcile the lines on their line number.

        Matched rather than deleted and re-inserted, which is the rule every
        document here follows: re-inserting mints a new id for every line on
        every save, and anything holding a reference to one is left pointing
        at nothing.
        """
        existing = {
            line.line_number: line
            for line in self._session.scalars(
                select(SalesQuotationLine).where(
                    SalesQuotationLine.sales_quotation_id == row.id
                )
            ).all()
        }
        seen: set[int] = set()
        subtotal = ZERO
        tax_total = ZERO
        discount_total = ZERO
        # Read once for the whole document rather than per line. A line that
        # says nothing about a discount gets this; one that says anything at
        # all, including zero, does not.
        customer_discount = self._customer_discount(row.customer_id)
        # Snapshot on the header: the lines below may each override it, so the
        # document keeps what the standing rate was on the day it was raised.
        row.customer_discount_percent = customer_discount or ZERO
        # Built once for the document, not once per line: which lists apply
        # depends on the customer, the territory and the date, none of which
        # change between lines.
        prices = PriceListResolver(
            self._session,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            territory_id=row.territory_id,
            on=row.quotation_date,
        )

        # Every line is priced before any of them is written, because a
        # discount on the whole bill has to be split across the lines *before*
        # tax is asked for. Tax is charged per line, so a document-level
        # deduction that never reaches a taxable value reduces no tax -- which
        # is what `header_discount_amount` does on a purchase order, and the
        # reason that shape is not copied here.
        products: list[Product] = []
        grosses: list[Decimal] = []
        for item in lines:
            product = self._session.scalar(
                select(Product).where(
                    Product.id == item.product_id, Product.is_deleted.is_(False)
                )
            )
            if product is None:
                raise ValidationError("Product not found for quotation line.")
            # A product withdrawn from sale is not quoted (D-MST-12). Every
            # line here was typed by somebody -- a quotation inherits nothing
            # -- so there is no already-agreed line to spare.
            assert_product_takes_new_lines(product, document="quotation")
            products.append(product)
            grosses.append(self._q(self._q(item.quantity) * self._q(item.unit_price)))
        # The firm's live offers and the customer's segment, asked once for the
        # whole document the way a sales order asks them. A quotation that
        # ignored both quoted a worse price than the order it became would
        # have been given directly -- and since the conversion carries the
        # quoted rate over as agreed, no offer ever reached such an order
        # (plan item 9.4, 2026-09-13).
        group_id, group_discount = self._customer_group(row.customer_id)
        bill_typed = bill_amount is not None or bill_percent is not None
        benefits = self._promotions(
            row,
            lines=lines,
            grosses=grosses,
            customer_group_id=group_id,
            bill_priced=bill_typed,
            freight_amount=freight_amount,
        )
        # A gift is a line, appended after the engine has answered and before
        # anything is priced, exactly as the order does it.
        gifts = self._gift_lines(benefits, lines=lines)
        for gift in gifts:
            product = self._session.scalar(
                select(Product).where(
                    Product.id == gift.product_id, Product.is_deleted.is_(False)
                )
            )
            if product is None:
                raise ValidationError("Product not found for a promotion's gift.")
            products.append(product)
            grosses.append(ZERO)
        lines = list(lines) + gifts
        priced: list[LineDiscount] = [
            resolve_line_discount(
                gross=grosses[index],
                percent=item.discount_percent,
                amount=item.discount_amount,
                promotion_amount=benefits.line_discount(index),
                price_list_percent=prices.rate_for(item.product_id, item.quantity),
                customer_default=customer_discount,
                customer_group_default=group_discount,
            )
            for index, item in enumerate(lines)
        ]
        row.bill_discount_source = (
            "typed"
            if bill_typed
            else ("promotion" if benefits.bill_discount() is not None else "none")
        )
        shares = self._bill_discount_shares(
            row,
            percent=bill_percent,
            # Typed wins; an offer's applies only where nothing was typed --
            # the precedence every line follows, and the order's.
            amount=bill_amount if bill_typed else benefits.bill_discount(),
            taxables=[
                self._q(gross - line.amount)
                for gross, line in zip(grosses, priced, strict=True)
            ],
        )
        asked_freight = self._q(freight_amount or ZERO)
        row.freight_waived_amount = min(benefits.freight_waived(), asked_freight)
        freight = self._freight_shares(
            row,
            # What an offer waived comes off before the split, so the lines
            # carry -- and are taxed on -- what the customer would be charged.
            freight=self._q(asked_freight - row.freight_waived_amount),
            taxables=[
                self._q(gross - line.amount)
                for gross, line in zip(grosses, priced, strict=True)
            ],
        )

        for index, item in enumerate(lines):
            product = products[index]
            line_discount = priced[index]
            quantity = self._q(item.quantity)
            # Refused on the quotation, not first when it becomes an order.
            assert_quantity_fits_unit(
                self._session,
                quantity=quantity,
                uom_id=item.sales_uom_id or item.inventory_uom_id,
                product_id=item.product_id,
                firm_id=row.firm_id,
            )
            gross = grosses[index]
            discount = line_discount.amount
            bill_share = shares[index]
            freight_share = freight[index]
            # Freight raises the taxable value; the bill discount
            # lowers it. Both reach the line so the tax is charged on
            # what the customer is actually being asked to pay.
            taxable = self._q(gross - discount - bill_share + freight_share)
            tax = self._tax_amount(
                document_id=row.id,
                line_number=item.line_number,
                quotation_date=row.quotation_date,
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
            line = existing.get(item.line_number)
            if line is None:
                line = SalesQuotationLine(
                    sales_quotation_id=row.id,
                    firm_id=row.firm_id,
                    line_number=item.line_number,
                    created_by=actor_id,
                )
                self._session.add(line)
            line.product_id = item.product_id
            line.description = item.description or product.name
            line.quantity = quantity
            # An offer's free goods apply where the line asked for none, as on
            # the order.
            line.free_quantity = self._q(item.free_quantity) or self._q(
                benefits.free_quantity(index)
            )
            line.sales_uom_id = item.sales_uom_id
            line.inventory_uom_id = item.inventory_uom_id
            line.packaging_type_id = item.packaging_type_id
            line.unit_price = self._q(item.unit_price)
            line.discount_percent = line_discount.percent
            line.discount_source = line_discount.source
            line.discount_amount = discount
            line.bill_discount_amount = bill_share
            line.freight_amount = freight_share
            line.gross_amount = gross
            line.tax_profile_id = item.tax_profile_id
            line.tax_amount = tax
            line.net_amount = self._q(taxable + tax)
            line.warehouse_id = item.warehouse_id or row.warehouse_id
            line.remarks = item.remarks
            line.updated_by = actor_id
            seen.add(item.line_number)
            subtotal += taxable
            tax_total += tax
            discount_total += discount
        for line_number, line in existing.items():
            if line_number not in seen:
                self._session.delete(line)
        self._session.flush()
        return {
            "subtotal": self._q(subtotal),
            "tax_total": self._q(tax_total),
            "line_discount_total": self._q(discount_total),
        }

    def _replace_attachments(
        self,
        row: SalesQuotation,
        attachments: list[QuotationAttachmentWrite],
        *,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesQuotationAttachment).filter(
            SalesQuotationAttachment.sales_quotation_id == row.id
        ).delete(synchronize_session=False)
        for item in attachments:
            self._session.add(
                SalesQuotationAttachment(
                    sales_quotation_id=row.id,
                    firm_id=row.firm_id,
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
        row: SalesQuotation,
        notes: list[QuotationNoteWrite],
        *,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesQuotationNote).filter(
            SalesQuotationNote.sales_quotation_id == row.id
        ).delete(synchronize_session=False)
        for item in notes:
            self._session.add(
                SalesQuotationNote(
                    sales_quotation_id=row.id,
                    firm_id=row.firm_id,
                    note_type=item.note_type,
                    note=item.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _lines_of(self, quotation_id: UUID) -> list[SalesQuotationLine]:
        return list(
            self._session.scalars(
                select(SalesQuotationLine)
                .where(
                    SalesQuotationLine.sales_quotation_id == quotation_id,
                    SalesQuotationLine.is_deleted.is_(False),
                )
                .order_by(SalesQuotationLine.line_number.asc())
            ).all()
        )

    def _require_customer(self, customer_id: UUID, *, firm_id: UUID) -> Customer:
        customer = self._session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.firm_id == firm_id,
                Customer.is_deleted.is_(False),
            )
        )
        if customer is None:
            raise ResourceNotFoundError("Customer not found.")
        return customer

    def _tax_amount(
        self,
        *,
        quotation_date: date,
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
    ) -> Decimal:
        """Return the tax the offer would carry if billed on its own date."""
        if invoice_value <= ZERO:
            return ZERO
        tax_service = TaxFrameworkService(self._session)
        if tax_profile_id is None:
            product = self._session.get(Product, product_id)
            resolved = (
                tax_service.resolve_profile_for_product(
                    product, quotation_date, firm_scope=firm_id
                )
                if product is not None
                else None
            )
            if resolved is None:
                return ZERO
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, quotation_date, firm_scope=firm_id
            )
        response = self._tax.simulate(
            TaxRuleSimulationRequest(
                # The supply's own nature, not just the document's name: a buyer in
                # another state is charged IGST (D-CMP-1).
                transaction_type=self._tax.outward_transaction_type(
                    "SALES_QUOTATION",
                    firm_id=firm_id,
                    branch_id=branch_id,
                    customer_id=customer_id,
                ),
                transaction_date=quotation_date,
                business_profile_id=business_profile_id,
                tax_profile_id=tax_profile_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                customer_id=customer_id,
                product_id=product_id,
                invoice_value=invoice_value,
                additional_context={
                    "source": "quotation",
                    "document_type": "SALES_QUOTATION",
                },
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
            document_id=document_id,
            line_number=line_number,
        )
        return self._q(response.total_tax_amount)

    # ---- import and export ---------------------------------------------

    def import_quotations(
        self, data: QuotationImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[SalesQuotation]:
        """Create a validated batch of quotations in one transaction.

        The whole batch lands or none of it does, so a file that is refused
        can be corrected and sent again as it stands.
        """
        try:
            rows = [
                self._stage_quotation(record, firm_id=firm_scope, actor_id=actor_id)
                for record in data.records
            ]
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return rows

    def export_quotations_csv(
        self, *, firm_scope: UUID, search: str | None = None
    ) -> str:
        """Export matching quotations as CSV.

        ``is_expired`` is carried as its own column rather than left to be read
        off ``status``: a quotation reads ``SENT`` the day before and the day
        after its prices lapse, and that is exactly the row somebody exporting
        a pipeline needs to be able to tell apart.
        """
        rows, _ = self.list_quotations(
            firm_scope=firm_scope,
            filters=QuotationListFilters(),
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
                "quotation_number",
                "quotation_date",
                "valid_until",
                "customer_id",
                "branch_id",
                "status",
                "is_expired",
                "grand_total",
                "decline_reason",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.quotation_number,
                    row.quotation_date.isoformat(),
                    row.valid_until.isoformat(),
                    str(row.customer_id),
                    str(row.branch_id),
                    row.status,
                    str(self.is_expired(row)).lower(),
                    str(row.grand_total),
                    row.decline_reason,
                ]
            )
        return buffer.getvalue()

    # ---- responses -----------------------------------------------------

    def quotation_response(self, row: SalesQuotation) -> QuotationResponse:
        """Build the full response for one quotation."""
        attachments = list(
            self._session.scalars(
                select(SalesQuotationAttachment).where(
                    SalesQuotationAttachment.sales_quotation_id == row.id,
                    SalesQuotationAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(SalesQuotationNote).where(
                    SalesQuotationNote.sales_quotation_id == row.id,
                    SalesQuotationNote.is_deleted.is_(False),
                )
            ).all()
        )
        return QuotationResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            quotation_number=row.quotation_number,
            quotation_date=row.quotation_date,
            valid_until=row.valid_until,
            customer_reference=row.customer_reference,
            reference_number=row.reference_number,
            payment_terms=row.payment_terms,
            delivery_terms=row.delivery_terms,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            remarks=row.remarks,
            status=QuotationStatus(row.status),
            customer_discount_percent=row.customer_discount_percent,
            bill_discount_percent=row.bill_discount_percent,
            bill_discount_amount=row.bill_discount_amount,
            bill_discount_source=row.bill_discount_source,
            freight_amount=row.freight_amount,
            freight_waived_amount=row.freight_waived_amount,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            sent_at=row.sent_at,
            decided_at=row.decided_at,
            converted_at=row.converted_at,
            converted_sales_order_id=row.converted_sales_order_id,
            converted_sales_order_number=row.converted_sales_order_number,
            decline_reason=row.decline_reason,
            cancel_reason=row.cancel_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version,
            is_expired=self.is_expired(row),
            can_convert=self.can_convert(row),
            lines=[
                QuotationLineResponse.model_validate(line, from_attributes=True)
                for line in self._lines_of(row.id)
            ],
            attachments=[
                QuotationAttachmentResponse.model_validate(item, from_attributes=True)
                for item in attachments
            ],
            notes=[
                QuotationNoteResponse.model_validate(item, from_attributes=True)
                for item in notes
            ],
        )

    # ---- reports -------------------------------------------------------

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[QuotationRegisterRecord]:
        """Every quotation raised, with what became of it.

        The customer is named as well as identified: the grid derives its
        columns from the row, so a register carrying only ids showed a screen
        of UUIDs (D-RPT-17). One read for the whole report.

        `is_expired` rides beside the status because expiry is a date rather
        than a status: a SENT offer past `valid_until` still reads SENT, and
        the register had nothing to say whether its prices still stood
        (D-RPT-19). Derived by `is_expired`, the same rule the document's own
        response and the conversion report use.
        """
        rows = window.fetch(
            self._session,
            select(SalesQuotation)
            .where(
                SalesQuotation.firm_id == firm_scope,
                SalesQuotation.is_deleted.is_(False),
                *window.dated(SalesQuotation.quotation_date),
            )
            .order_by(
                SalesQuotation.quotation_date.desc(),
                SalesQuotation.created_at.desc(),
                SalesQuotation.id.desc(),
            ),
        )
        customers = customer_names(self._session, (row.customer_id for row in rows))
        records = [
            QuotationRegisterRecord(
                quotation_id=row.id,
                quotation_number=row.quotation_number,
                customer_id=row.customer_id,
                customer_name=customers.get(row.customer_id, str(row.customer_id)),
                quotation_date=row.quotation_date,
                valid_until=row.valid_until,
                status=QuotationStatus(row.status),
                is_expired=self.is_expired(row),
                grand_total=row.grand_total,
                converted_sales_order_number=row.converted_sales_order_number,
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def conversion_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[QuotationConversionRecord]:
        """How many quotations turned into orders, per customer."""
        rows = list(
            self._session.scalars(
                select(SalesQuotation).where(
                    SalesQuotation.firm_id == firm_scope,
                    SalesQuotation.is_deleted.is_(False),
                    SalesQuotation.status != QuotationStatus.CANCELLED.value,
                    *window.dated(SalesQuotation.quotation_date),
                )
            ).all()
        )
        quoted_count: dict[UUID, int] = defaultdict(int)
        quoted_value: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        converted_count: dict[UUID, int] = defaultdict(int)
        converted_value: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        declined_count: dict[UUID, int] = defaultdict(int)
        expired_count: dict[UUID, int] = defaultdict(int)
        # Expiry is a date, not a status (see `summary`): a sent offer past
        # its date has lapsed, and the catalogue promises to say how many.
        today = utc_now().date()
        for row in rows:
            quoted_count[row.customer_id] += 1
            quoted_value[row.customer_id] += row.grand_total
            if row.status == QuotationStatus.CONVERTED.value:
                converted_count[row.customer_id] += 1
                converted_value[row.customer_id] += row.grand_total
            elif row.status == QuotationStatus.DECLINED.value:
                declined_count[row.customer_id] += 1
            elif row.valid_until < today:
                expired_count[row.customer_id] += 1
        names = {
            customer.id: customer.display_name
            for customer in self._session.scalars(
                select(Customer).where(Customer.id.in_(list(quoted_count.keys())))
            ).all()
        }
        return [
            QuotationConversionRecord(
                customer_id=customer_id,
                customer_name=names.get(customer_id, str(customer_id)),
                quoted_count=count,
                quoted_value=self._q(quoted_value[customer_id]),
                converted_count=converted_count[customer_id],
                converted_value=self._q(converted_value[customer_id]),
                declined_count=declined_count[customer_id],
                expired_count=expired_count[customer_id],
                open_count=count
                - converted_count[customer_id]
                - declined_count[customer_id]
                - expired_count[customer_id],
            )
            for customer_id, count in quoted_count.items()
        ]

    # ---- lifecycle plumbing --------------------------------------------

    def _move(
        self,
        row: SalesQuotation,
        status: QuotationStatus,
        *,
        action: str,
        firm_scope: UUID,
        actor_id: UUID,
        stamp: str | None = None,
        remarks: str | None = None,
        commit: bool = True,
    ) -> SalesQuotation:
        """Apply one lifecycle transition, with its event and audit row.

        `commit=False` leaves the transaction to a caller composing the move
        with other writes, as conversion does with the order it stages.
        """
        before = row.status
        row.status = status.value
        row.updated_by = actor_id
        if stamp is not None:
            setattr(row, stamp, utc_now())
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action=action,
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=remarks,
        )
        record_audit(
            self._session,
            action=f"quotation.{action.lower()}",
            entity_type="quotation",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "remarks": remarks or ""},
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return row

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document: SalesQuotation,
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
                source_module_code="SALES_QUOTATION",
                document_number=document.quotation_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "quotation_number": document.quotation_number,
                    "valid_until": document.valid_until.isoformat(),
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
