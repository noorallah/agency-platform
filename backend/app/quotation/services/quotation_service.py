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
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer
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
from app.products.models import Product
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
    QuotationRegisterRecord,
    QuotationResponse,
    QuotationStatus,
    QuotationSummary,
)
from app.sales.services.scope_resolution import resolve_sales_scope
from app.sales_order.models import SalesOrder
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService

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
                statement.order_by(column.desc() if descending else column.asc())
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
        self._require_customer(data.customer_id, firm_id=firm_id)
        quotation_number = data.quotation_number or self._documents.reserve_number(
            numbering_rule.id,
            firm_id=firm_id,
            financial_year_label=self._financial_year_label(
                data.quotation_date, firm_id
            ),
            branch_code=self._scope_code(data.branch_id),
            company_code=self._company_code(firm_id),
            document_date=data.quotation_date,
            actor_id=actor_id,
        )
        scope = resolve_sales_scope(
            self._session,
            firm_id=firm_id,
            customer_id=data.customer_id,
            territory_id=data.territory_id,
            salesman_id=data.salesman_id,
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
        self._require_customer(data.customer_id, firm_id=firm_scope)
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
        order = SalesOrderService(self._session).create_order(
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
                        discount_percent=line.discount_percent,
                        discount_amount=line.discount_amount,
                        tax_profile_id=line.tax_profile_id,
                        warehouse_id=line.warehouse_id,
                        remarks=line.remarks,
                    )
                    for line in lines
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
        )
        return converted, order

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
        totals = self._replace_lines(row, lines=data.lines, actor_id=actor_id)
        row.line_discount_total = totals["line_discount_total"]
        row.subtotal = totals["subtotal"]
        row.tax_total = totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal + row.tax_total + row.additional_charges + row.round_off
        )
        self._replace_attachments(row, data.attachments, actor_id=actor_id)
        self._replace_notes(row, data.notes, actor_id=actor_id)

    def _replace_lines(
        self,
        row: SalesQuotation,
        *,
        lines: list[QuotationLineWrite],
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
        for item in lines:
            product = self._session.scalar(
                select(Product).where(
                    Product.id == item.product_id, Product.is_deleted.is_(False)
                )
            )
            if product is None:
                raise ValidationError("Product not found for quotation line.")
            quantity = self._q(item.quantity)
            gross = self._q(quantity * self._q(item.unit_price))
            discount = self._q(
                item.discount_amount
                if item.discount_amount > ZERO
                else gross * self._q(item.discount_percent) / Decimal("100")
            )
            taxable = self._q(gross - discount)
            tax = self._tax_amount(
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
            line.free_quantity = self._q(item.free_quantity)
            line.sales_uom_id = item.sales_uom_id
            line.inventory_uom_id = item.inventory_uom_id
            line.packaging_type_id = item.packaging_type_id
            line.unit_price = self._q(item.unit_price)
            line.discount_percent = self._q(item.discount_percent)
            line.discount_amount = discount
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
                transaction_type="SALES_QUOTATION",
                transaction_date=quotation_date,
                business_profile_id=business_profile_id,
                tax_profile_id=tax_profile_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                customer_id=customer_id,
                product_id=product_id,
                invoice_value=invoice_value,
                additional_context={"source": "quotation"},
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
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

    def register_report(self, *, firm_scope: UUID) -> list[QuotationRegisterRecord]:
        """Every quotation raised, with what became of it."""
        return [
            QuotationRegisterRecord(
                quotation_id=row.id,
                quotation_number=row.quotation_number,
                customer_id=row.customer_id,
                quotation_date=row.quotation_date,
                valid_until=row.valid_until,
                status=QuotationStatus(row.status),
                grand_total=row.grand_total,
                converted_sales_order_number=row.converted_sales_order_number,
            )
            for row in self._session.scalars(
                select(SalesQuotation)
                .where(
                    SalesQuotation.firm_id == firm_scope,
                    SalesQuotation.is_deleted.is_(False),
                )
                .order_by(SalesQuotation.quotation_date.desc())
            ).all()
        ]

    def conversion_report(self, *, firm_scope: UUID) -> list[QuotationConversionRecord]:
        """How many quotations turned into orders, per customer."""
        rows = list(
            self._session.scalars(
                select(SalesQuotation).where(
                    SalesQuotation.firm_id == firm_scope,
                    SalesQuotation.is_deleted.is_(False),
                    SalesQuotation.status != QuotationStatus.CANCELLED.value,
                )
            ).all()
        )
        quoted_count: dict[UUID, int] = defaultdict(int)
        quoted_value: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        converted_count: dict[UUID, int] = defaultdict(int)
        converted_value: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        declined_count: dict[UUID, int] = defaultdict(int)
        for row in rows:
            quoted_count[row.customer_id] += 1
            quoted_value[row.customer_id] += row.grand_total
            if row.status == QuotationStatus.CONVERTED.value:
                converted_count[row.customer_id] += 1
                converted_value[row.customer_id] += row.grand_total
            elif row.status == QuotationStatus.DECLINED.value:
                declined_count[row.customer_id] += 1
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
    ) -> SalesQuotation:
        """Apply one lifecycle transition, with its event and audit row."""
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
        self._session.commit()
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
