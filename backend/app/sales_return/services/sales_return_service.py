"""Sales return workflow: goods back from a customer, stock back on the shelf.

The mirror of ``app/purchase_return`` on the sales side. A purchase return
sends goods to a supplier and takes them out of stock; this takes them back
from a customer and puts them in, credits what the customer no longer owes, and
returns the cost of the goods to inventory.

Until this existed a customer could be credit-noted for goods they sent back --
which moved the money -- while the units stayed counted as sold, so inventory
understated what was on the shelf permanently and the only correction was a
manual stock adjustment nobody knew to make.
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

from app.batch_serial.services import BatchSerialService
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CustomerService
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
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
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.inventory.models import StockLedgerEntry
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.services.scope_resolution import resolve_sales_scope
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_return.models import (
    SalesReturn,
    SalesReturnAttachment,
    SalesReturnLine,
    SalesReturnNote,
    SalesReturnSource,
)
from app.sales_return.schemas import (
    SalesReturnAttachmentResponse,
    SalesReturnAttachmentWrite,
    SalesReturnByCustomerRecord,
    SalesReturnByProductRecord,
    SalesReturnCreate,
    SalesReturnImportRequest,
    SalesReturnLineResponse,
    SalesReturnListFilters,
    SalesReturnNoteResponse,
    SalesReturnNoteWrite,
    SalesReturnReconciliationRecord,
    SalesReturnRegisterRecord,
    SalesReturnResponse,
    SalesReturnSourceResponse,
    SalesReturnSourceType,
    SalesReturnStatus,
    SalesReturnSummary,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")

#: The line shapes a sales return can be raised from.
SourceLine = DeliveryNoteLine | SalesInvoiceLine

#: Statuses that no longer hold a claim on the source document's quantity.
_SPENT_STATUSES = (SalesReturnStatus.CANCELLED.value,)


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


def _decimal(value: object, default: Decimal = ZERO) -> Decimal:
    """Read a Decimal out of an untyped line spec."""
    return Decimal(str(value)) if value is not None else default


class SalesReturnService(TransactionalDocumentService):
    """Coordinate customer return lifecycle, stock intake and posting."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_RETURN",
        name="Sales Return",
        description="Customer return document",
        category="SALES",
        module="sales_return",
        prefix="SR",
        states=(
            DocumentStateSpec("DRAFT", "Draft", 1, allows_edit=True),
            DocumentStateSpec("APPROVED", "Approved", 2),
            DocumentStateSpec("COMPLETED", "Completed", 3),
            DocumentStateSpec("CANCELLED", "Cancelled", 4, is_terminal=True),
            DocumentStateSpec("CLOSED", "Closed", 5, is_terminal=True),
        ),
    )

    def __init__(self, session: Session) -> None:
        """Bind the lifecycle base plus this module's collaborators."""
        super().__init__(session)
        self._tax = TaxRuleService(session)
        self._uom = UomService(session)
        self._inventory = InventoryService(session)
        self._posting = DocumentPostingService(session)
        self._customers = CustomerService(session)

    # ---- reads ---------------------------------------------------------

    def list_returns(
        self,
        *,
        firm_scope: UUID,
        filters: SalesReturnListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SalesReturn], int]:
        """List sales returns for the visible firm scope."""
        columns = {
            "return_number": SalesReturn.return_number,
            "return_date": SalesReturn.return_date,
            "warehouse_id": SalesReturn.warehouse_id,
            "grand_total": SalesReturn.grand_total,
            "status": SalesReturn.status,
            "created_at": SalesReturn.created_at,
            "updated_at": SalesReturn.updated_at,
        }
        statement = select(SalesReturn).where(SalesReturn.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(SalesReturn)
            .where(SalesReturn.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(SalesReturn.is_deleted.is_(False))
            count = count.where(SalesReturn.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(SalesReturn.customer_id == filters.customer_id)
            count = count.where(SalesReturn.customer_id == filters.customer_id)
        if filters.branch_id is not None:
            statement = statement.where(SalesReturn.branch_id == filters.branch_id)
            count = count.where(SalesReturn.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                SalesReturn.warehouse_id == filters.warehouse_id
            )
            count = count.where(SalesReturn.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(SalesReturn.status == filters.status.value)
            count = count.where(SalesReturn.status == filters.status.value)
        if filters.return_from is not None:
            statement = statement.where(SalesReturn.return_date >= filters.return_from)
            count = count.where(SalesReturn.return_date >= filters.return_from)
        if filters.return_to is not None:
            statement = statement.where(SalesReturn.return_date <= filters.return_to)
            count = count.where(SalesReturn.return_date <= filters.return_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesReturn.return_number.ilike(token),
                SalesReturn.customer_return_number.ilike(token),
                SalesReturn.reference_number.ilike(token),
                SalesReturn.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, SalesReturn.created_at)
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

    def summary(self, *, firm_scope: UUID) -> SalesReturnSummary:
        """Return aggregate sales return values for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesReturn).where(
                    SalesReturn.firm_id == firm_scope,
                    SalesReturn.is_deleted.is_(False),
                )
            ).all()
        )
        live = [row for row in rows if row.status not in _SPENT_STATUSES]
        return SalesReturnSummary(
            total_returns=len(rows),
            draft_returns=sum(
                1 for row in rows if row.status == SalesReturnStatus.DRAFT.value
            ),
            approved_returns=sum(
                1 for row in rows if row.status == SalesReturnStatus.APPROVED.value
            ),
            completed_returns=sum(
                1 for row in rows if row.status == SalesReturnStatus.COMPLETED.value
            ),
            cancelled_returns=sum(
                1 for row in rows if row.status == SalesReturnStatus.CANCELLED.value
            ),
            total_return_value=self._q(sum((row.grand_total for row in live), ZERO)),
            total_restock_quantity=self._q(
                sum((row.total_restock_quantity for row in live), ZERO)
            ),
        )

    def get_return(self, return_id: UUID, *, firm_scope: UUID) -> SalesReturn:
        """Return one sales return within the visible firm scope."""
        row = self._session.scalar(
            select(SalesReturn).where(
                SalesReturn.id == return_id,
                SalesReturn.firm_id == firm_scope,
                SalesReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales return not found.")
        return row

    def timeline(
        self, return_id: UUID, *, firm_scope: UUID
    ) -> list[DocumentLifecycleEvent]:
        """Return the lifecycle history of one sales return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
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

    def create_return(
        self, data: SalesReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesReturn:
        """Create one sales return in draft."""
        row = self._stage_return(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def _stage_return(
        self, data: SalesReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesReturn:
        """Build one sales return without committing it.

        Split out so an import can stage a whole batch and commit once. A loop
        over ``create_return`` would commit each row as it went, which is the
        shape that made the branch and warehouse imports impossible to finish:
        a batch whose fifth row clashed returned 409 with four rows already
        written, and the corrected file then failed on those four as duplicates.
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
        header, source_rows, line_specs = self._prepare_sources(data, firm_id=firm_id)
        customer_id = data.customer_id or header["customer_id"]
        branch_id = data.branch_id or header["branch_id"]
        if customer_id != header["customer_id"]:
            raise ValidationError("Return customer must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Return branch must match all source documents.")
        return_number = (
            data.return_number.strip().upper()
            if data.return_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.return_date, firm_id
                ),
                branch_code=self._scope_code(branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.return_date,
                actor_id=actor_id,
            )
        )
        scope_salesman, scope_territory = self._fill_missing_scope(
            firm_id=firm_id,
            customer_id=customer_id,
            salesman_id=header.get("salesman_id"),
            territory_id=header.get("territory_id"),
            on_date=data.return_date,
        )
        row = SalesReturn(
            firm_id=firm_id,
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=data.warehouse_id,
            salesman_id=scope_salesman,
            territory_id=scope_territory,
            business_profile_id=data.business_profile_id,
            return_number=return_number,
            return_date=data.return_date,
            customer_return_number=(
                data.customer_return_number.strip()
                if data.customer_return_number
                else None
            ),
            customer_return_date=data.customer_return_date,
            reference_delivery_note_number=data.reference_delivery_note_number,
            reference_invoice_number=data.reference_invoice_number,
            return_reason=data.return_reason,
            currency_code=(
                data.currency_code.strip().upper() if data.currency_code else None
            ),
            exchange_rate=data.exchange_rate,
            reference_number=data.reference_number,
            remarks=data.remarks,
            allow_over_return=data.allow_over_return,
            over_return_percent=self._q(data.over_return_percent),
            status=SalesReturnStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        # Not a bare flush: a duplicate number clashes here, before the
        # catch-all below is reached, and an IntegrityError escaping the
        # service is a 500 where the caller should be told 409.
        self._flush_or_conflict("Sales return number already exists in this firm.")
        self._apply_children(row, data, source_rows, line_specs, actor_id=actor_id)
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
            action="sales_return.created",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"return_number": row.return_number, "status": row.status},
        )
        self._flush_or_conflict("Sales return number already exists in this firm.")
        return row

    def update_return(
        self,
        return_id: UUID,
        data: SalesReturnCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> SalesReturn:
        """Replace one draft sales return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != SalesReturnStatus.DRAFT.value:
            raise ValidationError("Only draft sales returns can be edited.")
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        header, source_rows, line_specs = self._prepare_sources(
            data, firm_id=firm_scope
        )
        before: dict[str, object] = {
            "return_date": row.return_date.isoformat(),
            "grand_total": str(row.grand_total),
        }
        row.customer_id = data.customer_id or header["customer_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.warehouse_id = data.warehouse_id
        row.salesman_id, row.territory_id = self._fill_missing_scope(
            firm_id=firm_scope,
            customer_id=row.customer_id,
            salesman_id=header.get("salesman_id"),
            territory_id=header.get("territory_id"),
            on_date=data.return_date,
        )
        row.business_profile_id = data.business_profile_id
        row.return_date = data.return_date
        row.customer_return_number = (
            data.customer_return_number.strip() if data.customer_return_number else None
        )
        row.customer_return_date = data.customer_return_date
        row.reference_delivery_note_number = data.reference_delivery_note_number
        row.reference_invoice_number = data.reference_invoice_number
        row.return_reason = data.return_reason
        row.currency_code = (
            data.currency_code.strip().upper() if data.currency_code else None
        )
        row.exchange_rate = data.exchange_rate
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.allow_over_return = data.allow_over_return
        row.over_return_percent = self._q(data.over_return_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        self._delete_children(row.id)
        self._apply_children(row, data, source_rows, line_specs, actor_id=actor_id)
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
            action="sales_return.updated",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data=before,
            after_data={
                "return_date": row.return_date.isoformat(),
                "grand_total": str(row.grand_total),
            },
        )
        self._flush_or_conflict("Sales return number already exists in this firm.")
        self._session.commit()
        return row

    def approve_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesReturn:
        """Approve one draft sales return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == SalesReturnStatus.APPROVED.value:
            return row
        if row.status != SalesReturnStatus.DRAFT.value:
            raise ValidationError("Only draft sales returns can be approved.")
        before = row.status
        row.status = SalesReturnStatus.APPROVED.value
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
            action="sales_return.approved",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def complete_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesReturn:
        """Take the goods back into stock and credit the customer.

        Three things happen together and none of them is optional. The stock
        arrives, what the customer owes falls by the credit, and the cost of the
        goods goes back into inventory out of cost of sales. Doing the first
        without the last two is what a credit note alone used to do in reverse:
        one book moves and the other does not.
        """
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == SalesReturnStatus.COMPLETED.value:
            return row
        if row.status in {
            SalesReturnStatus.CANCELLED.value,
            SalesReturnStatus.CLOSED.value,
        }:
            raise ValidationError("Cancelled/closed sales returns cannot be completed.")
        if row.status != SalesReturnStatus.APPROVED.value:
            raise ValidationError("Only approved sales returns can be completed.")
        lines = self._lines_of(row.id)
        if not lines:
            raise ValidationError("Sales return must contain at least one line.")
        movement_ids: list[UUID] = []
        for line in lines:
            warehouse_id = line.warehouse_id or row.warehouse_id
            batch_id = self._resolve_return_batch(line)
            if batch_id is not None:
                line.batch_id = batch_id
            transaction = self._inventory.record_sales_return(
                firm_scope=firm_scope,
                actor_id=actor_id,
                branch_id=row.branch_id,
                warehouse_id=warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                reference_number=row.return_number,
                transaction_date=row.return_date,
                return_quantity=line.current_return_quantity,
                restock_quantity=line.restock_quantity,
                damaged_quantity=line.damaged_quantity,
                scrap_quantity=line.scrap_quantity,
                entered_quantity=line.current_return_quantity,
                entered_uom_id=line.return_uom_id or line.sales_uom_id,
                conversion_version=line.conversion_version,
                remarks=line.remarks or row.remarks,
                batch_id=batch_id,
            )
            line.inventory_transaction_id = transaction.id
            line.updated_by = actor_id
            movement_ids.append(transaction.id)
        # What the goods are worth coming back, read from the ledger rows the
        # movements above wrote rather than from the return's own prices. The
        # customer is credited a selling price; stock returns at the cost it is
        # carried at, and the two are never the same number.
        stock_value = self._movement_value(movement_ids)
        # Both postings run before the commit and either may fail the
        # completion. Stock that arrived with no journal behind it is how the
        # inventory control account stops reconciling, which is the whole
        # reason this document exists.
        credit = self._posting.post_sales_return(
            firm_id=firm_scope,
            return_id=row.id,
            return_number=row.return_number,
            return_date=row.return_date,
            taxable_amount=self._q(row.grand_total - row.tax_total),
            tax_amount=row.tax_total,
            total_amount=row.grand_total,
            actor_id=actor_id,
        )
        row.journal_entry_id = None if credit is None else credit.id
        cost_entry = self._posting.post_goods_return_to_stock(
            firm_id=firm_scope,
            document_id=row.id,
            document_number=row.return_number,
            return_date=row.return_date,
            cost_amount=stock_value,
            source_module="sales_return",
            actor_id=actor_id,
        )
        row.cost_journal_entry_id = None if cost_entry is None else cost_entry.id
        # A return worth nothing moves no balance either, and the receivable
        # service refuses an amount of zero outright.
        if row.grand_total > ZERO:
            self._customers.post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
                    transaction_date=row.return_date,
                    amount=self._q(row.grand_total),
                    reference_type="SALES_RETURN",
                    reference_id=row.id,
                    reference_number=row.return_number,
                    remarks=f"Sales return {row.return_number} completed.",
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
                commit=False,
            )
        before = row.status
        row.status = SalesReturnStatus.COMPLETED.value
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
            action="sales_return.completed",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "stock_value": str(stock_value)},
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
    ) -> SalesReturn:
        """Cancel one sales return, undoing it if it had completed."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == SalesReturnStatus.CANCELLED.value:
            return row
        if row.status == SalesReturnStatus.CLOSED.value:
            raise ValidationError("Closed sales returns cannot be cancelled.")
        before = row.status
        if before == SalesReturnStatus.COMPLETED.value:
            # It took stock in, credited the customer and moved cost out of
            # sales. All three have to come back out together, or cancelling
            # leaves the firm holding goods it has been paid for.
            stock_value = self._reverse_inventory(
                row, firm_scope=firm_scope, actor_id=actor_id
            )
            self._reverse_postings(
                row,
                firm_scope=firm_scope,
                actor_id=actor_id,
                stock_value=stock_value,
            )
            self._reverse_receivable(
                row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
            )
        row.status = SalesReturnStatus.CANCELLED.value
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
            action="sales_return.cancelled",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status, "cancel_reason": reason or ""},
        )
        self._session.commit()
        return row

    def close_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesReturn:
        """Close one completed sales return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == SalesReturnStatus.CLOSED.value:
            return row
        if row.status != SalesReturnStatus.COMPLETED.value:
            raise ValidationError("Only completed sales returns can be closed.")
        before = row.status
        row.status = SalesReturnStatus.CLOSED.value
        row.closed_at = utc_now()
        row.close_reason = reason
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
            action="sales_return.closed",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def delete_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Soft-delete one draft sales return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != SalesReturnStatus.DRAFT.value:
            raise ValidationError(
                "Only draft sales returns can be deleted; cancel the rest."
            )
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="sales_return.deleted",
            entity_type="sales_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": row.status},
        )
        self._session.commit()

    # ---- reversal ------------------------------------------------------

    def _reverse_receivable(
        self,
        row: SalesReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> None:
        """Undo the credit note by its own recorded deltas, not by its total.

        A credit note is applied up to what the customer owes and the rest
        becomes an unapplied advance: 500 against an outstanding 300 is 300 off
        the balance and 200 of advance. Only that row remembers the split.

        Cancelling used to post a fresh INVOICE for the whole amount, which put
        all of it back on the balance and left the advance standing, so the
        customer owed more than they had before the return and held an advance
        no money ever paid for. Net exposure came out right -- outstanding minus
        advance -- which is why it went unnoticed; the two figures were
        individually wrong and cancelled each other out. `settlements` has done
        it this way since it was written.
        """
        original = self._session.scalar(
            select(CustomerReceivableTransaction).where(
                CustomerReceivableTransaction.reference_type == "SALES_RETURN",
                CustomerReceivableTransaction.reference_id == row.id,
                CustomerReceivableTransaction.transaction_type
                == CustomerReceivableTransactionType.CREDIT_NOTE.value,
                CustomerReceivableTransaction.is_deleted.is_(False),
            )
        )
        if original is None:
            # A return worth nothing moved no balance to undo.
            return
        self._customers.reverse_receivable_transaction(
            original.id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            reference_number=f"{row.return_number}-REV",
            remarks=reason or f"Cancelled sales return {row.return_number}.",
            commit=False,
        )

    def _reverse_inventory(
        self, row: SalesReturn, *, firm_scope: UUID, actor_id: UUID
    ) -> Decimal:
        """Take back out the stock a completed return brought in.

        Returns what the movements actually removed. The goods came in at the
        average of the day the return completed and leave at the average of the
        day it is cancelled, and the cost journal has to follow the second
        figure rather than mirror the first.
        """
        movement_ids: list[UUID] = []
        for line in self._lines_of(row.id):
            if line.inventory_transaction_id is None:
                continue
            movement = self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=f"Cancelled sales return {row.return_number}",
            )
            if movement is not None:
                movement_ids.append(movement.id)
            line.inventory_transaction_id = None
            line.updated_by = actor_id
        return self._movement_value(movement_ids)

    def _reverse_postings(
        self,
        row: SalesReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        stock_value: Decimal,
    ) -> None:
        """Mirror both journals a completed return posted.

        Both, not one. The credit and the cost are separate entries because
        they answer separate questions, and reversing only the money would
        leave the goods valued as though they were still on the shelf.
        """
        # The credit note mirrors exactly: it is what the customer was told
        # they are owed, and cancelling makes the whole of it void.
        if row.journal_entry_id is not None:
            JournalEntryEngine(self._session).reverse_entry(
                row.journal_entry_id,
                firm_id=firm_scope,
                reference_number=f"{row.return_number}-REV",
                actor_id=actor_id,
            )
        # The cost entry does not. It brought goods in at the average of the
        # day the return completed; they leave at the average of today, and
        # mirroring credits inventory with a figure no movement removed.
        if row.cost_journal_entry_id is not None:
            self._posting.reverse_goods_return_to_stock(
                firm_id=firm_scope,
                entry_id=row.cost_journal_entry_id,
                document_number=row.return_number,
                stock_value=stock_value,
                actor_id=actor_id,
            )
        row.journal_entry_id = None
        row.cost_journal_entry_id = None

    # ---- children ------------------------------------------------------

    def _apply_children(
        self,
        row: SalesReturn,
        data: SalesReturnCreate,
        source_rows: list[dict[str, object]],
        line_specs: list[dict[str, object]],
        *,
        actor_id: UUID,
    ) -> None:
        """Write the sources, lines, attachments and notes, and roll up totals."""
        firm_id = row.firm_id
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_id,
            return_date=data.return_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = totals["total_source_quantity"]
        row.total_already_returned_quantity = totals["total_already_returned_quantity"]
        row.total_current_return_quantity = totals["total_current_return_quantity"]
        row.total_restock_quantity = totals["total_restock_quantity"]
        row.line_discount_total = totals["line_discount_total"]
        row.subtotal = totals["subtotal"]
        row.tax_total = totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, firm_id=firm_id, actor_id=actor_id
        )
        self._replace_notes(row, data.notes, firm_id=firm_id, actor_id=actor_id)

    def _replace_sources(
        self,
        row: SalesReturn,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesReturnSource).filter(
            SalesReturnSource.sales_return_id == row.id
        ).delete(synchronize_session=False)
        for source in source_rows:
            self._session.add(
                SalesReturnSource(
                    sales_return_id=row.id,
                    firm_id=firm_id,
                    source_document_type=str(source["source_document_type"]),
                    source_document_id=source["source_document_id"],
                    source_document_number=str(source["source_document_number"]),
                    source_document_date=source["source_document_date"],
                    customer_id=source["customer_id"],
                    branch_id=source["branch_id"],
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _replace_lines(
        self,
        row: SalesReturn,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        return_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(SalesReturnLine).filter(
            SalesReturnLine.sales_return_id == row.id
        ).delete(synchronize_session=False)
        totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            source_line = self._source_line(
                source_type, spec["source_document_line_id"]
            )
            requested = self._q(_decimal(spec["current_return_quantity"]))
            dispatched = self._source_quantity(source_type, source_line)
            source_uom_id = self._source_uom_id(source_line)
            return_uom_id = _optional_uuid(spec.get("return_uom_id"))
            conversion_factor = self._q(
                _decimal(spec.get("conversion_factor"), Decimal("1"))
            )
            return_quantity = requested
            if (
                source_uom_id is not None
                and return_uom_id is not None
                and return_uom_id != source_uom_id
            ):
                conversion = self._uom.convert_quantity(
                    ConversionRequest(
                        product_id=source_line.product_id,
                        from_uom_id=return_uom_id,
                        to_uom_id=source_uom_id,
                        quantity=requested,
                        conversion_date=return_date,
                    ),
                    firm_scope=firm_id,
                )
                return_quantity = self._q(conversion.converted_quantity)
                conversion_factor = self._q(conversion.conversion_factor)
            already_returned = self._already_returned_quantity(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
                exclude_return_id=row.id,
            )
            if (
                not row.allow_over_return
                and return_quantity + already_returned > dispatched
            ):
                raise ValidationError(
                    "Return quantity exceeds what was dispatched on the source "
                    f"document ({dispatched} sent, {already_returned} already "
                    "returned)."
                )
            # The buckets are validated against the requested quantity, so they
            # are converted with it rather than re-derived: a line entered in
            # cases and returned in pieces must not have its damaged count
            # silently stay in the other unit.
            scale = return_quantity / requested if requested != ZERO else Decimal("1")
            damaged = self._q(_decimal(spec.get("damaged_quantity")) * scale)
            scrap = self._q(_decimal(spec.get("scrap_quantity")) * scale)
            restock = self._q(return_quantity - damaged - scrap)
            unit_price = self._q(
                _decimal(spec["unit_price"])
                if spec.get("unit_price") is not None
                else _decimal(getattr(source_line, "unit_price", ZERO))
            )
            discount_amount = self._q(_decimal(spec.get("discount_amount")))
            charges_amount = self._q(_decimal(spec.get("charges_amount")))
            tax_profile_id = _optional_uuid(spec.get("tax_profile_id")) or getattr(
                source_line, "tax_profile_id", None
            )
            tax_amount = self._tax_amount(
                return_date=return_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id"))
                or row.warehouse_id,
                product_id=source_line.product_id,
                tax_profile_id=tax_profile_id,
                invoice_value=self._q(
                    return_quantity * unit_price - discount_amount + charges_amount
                ),
                actor_id=actor_id,
            )
            gross_amount = self._q(return_quantity * unit_price)
            net_amount = self._q(
                gross_amount - discount_amount + charges_amount + tax_amount
            )
            self._session.add(
                SalesReturnLine(
                    sales_return_id=row.id,
                    firm_id=firm_id,
                    line_number=index,
                    source_document_type=source_type,
                    source_document_id=spec["source_document_id"],
                    source_document_number=self._source_document_number(source_line),
                    source_document_line_id=source_line.id,
                    source_document_line_number=int(source_line.line_number),
                    product_id=source_line.product_id,
                    description=getattr(source_line, "description", None),
                    dispatched_quantity=dispatched,
                    already_returned_quantity=already_returned,
                    current_return_quantity=return_quantity,
                    restock_quantity=restock,
                    damaged_quantity=damaged,
                    scrap_quantity=scrap,
                    reason_code=spec.get("reason_code"),
                    item_condition=spec.get("item_condition"),
                    is_damaged=bool(spec.get("is_damaged", False)),
                    is_expired=bool(spec.get("is_expired", False)),
                    unit_price=unit_price,
                    discount_percent=self._q(_decimal(spec.get("discount_percent"))),
                    discount_amount=discount_amount,
                    charges_amount=charges_amount,
                    gross_amount=gross_amount,
                    tax_profile_id=tax_profile_id,
                    tax_amount=tax_amount,
                    net_amount=net_amount,
                    packaging_type_id=_optional_uuid(spec.get("packaging_type_id")),
                    sales_uom_id=source_uom_id,
                    return_uom_id=return_uom_id,
                    conversion_factor=conversion_factor,
                    warehouse_id=_optional_uuid(spec.get("warehouse_id"))
                    or row.warehouse_id,
                    storage_node_id=_optional_uuid(spec.get("storage_node_id")),
                    batch_number=spec.get("batch_number"),
                    expiry_date=spec.get("expiry_date"),
                    manufacturing_date=spec.get("manufacturing_date"),
                    remarks=spec.get("remarks"),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            totals["total_source_quantity"] += dispatched
            totals["total_already_returned_quantity"] += already_returned
            totals["total_current_return_quantity"] += return_quantity
            totals["total_restock_quantity"] += restock
            totals["line_discount_total"] += discount_amount
            # The taxable base: gross less discount, before tax and charges,
            # which is what `subtotal` means on every other document here.
            totals["subtotal"] += self._q(gross_amount - discount_amount)
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: SalesReturn,
        attachments: list[SalesReturnAttachmentWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesReturnAttachment).filter(
            SalesReturnAttachment.sales_return_id == row.id
        ).delete(synchronize_session=False)
        for item in attachments:
            self._session.add(
                SalesReturnAttachment(
                    sales_return_id=row.id,
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
        row: SalesReturn,
        notes: list[SalesReturnNoteWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesReturnNote).filter(
            SalesReturnNote.sales_return_id == row.id
        ).delete(synchronize_session=False)
        for item in notes:
            self._session.add(
                SalesReturnNote(
                    sales_return_id=row.id,
                    firm_id=firm_id,
                    note_type=item.note_type,
                    note=item.note,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _delete_children(self, return_id: UUID) -> None:
        for model in (
            SalesReturnLine,
            SalesReturnSource,
            SalesReturnAttachment,
            SalesReturnNote,
        ):
            self._session.query(model).filter(
                model.sales_return_id == return_id
            ).delete(synchronize_session=False)

    def _fill_missing_scope(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        salesman_id: UUID | None,
        territory_id: UUID | None,
        on_date: date,
    ) -> tuple[UUID | None, UUID | None]:
        """Derive the territory and salesman this return never inherited.

        A return always cites a source, so normally both arrive from the
        invoice or delivery note being returned and are kept untouched -- the
        return belongs where the sale did, whatever round the customer is on
        now. Only a source that predates scope resolution, and so carries
        nothing, is filled from the customer's own assignments.
        """
        if territory_id is not None and salesman_id is not None:
            return salesman_id, territory_id
        derived = resolve_sales_scope(
            self._session, firm_id=firm_id, customer_id=customer_id, on_date=on_date
        )
        return (
            salesman_id if salesman_id is not None else derived.salesman_id,
            territory_id if territory_id is not None else derived.territory_id,
        )

    # ---- sources -------------------------------------------------------

    def _prepare_sources(
        self, data: SalesReturnCreate, *, firm_id: UUID
    ) -> tuple[dict[str, UUID], list[dict[str, object]], list[dict[str, object]]]:
        lines = [item.model_dump(mode="python") for item in data.lines]
        sources = [item.model_dump(mode="python") for item in data.source_documents]
        if not sources:
            sources = [
                {"source_document_type": source_type, "source_document_id": source_id}
                for source_type, source_id in {
                    (
                        self._source_type(item["source_document_type"]),
                        item["source_document_id"],
                    )
                    for item in lines
                }
            ]
        source_rows: list[dict[str, object]] = []
        for source in sources:
            source_type = self._source_type(source["source_document_type"])
            source_id = source["source_document_id"]
            if source_type == SalesReturnSourceType.DELIVERY_NOTE.value:
                note = self._session.scalar(
                    select(DeliveryNote).where(
                        DeliveryNote.id == source_id,
                        DeliveryNote.firm_id == firm_id,
                        DeliveryNote.is_deleted.is_(False),
                    )
                )
                if note is None:
                    raise ResourceNotFoundError("Delivery note not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": note.id,
                        "source_document_number": note.delivery_note_number,
                        "source_document_date": note.delivery_date,
                        "customer_id": note.customer_id,
                        "branch_id": note.branch_id,
                        "salesman_id": note.salesman_id,
                        "territory_id": note.territory_id,
                    }
                )
            elif source_type == SalesReturnSourceType.SALES_INVOICE.value:
                invoice = self._session.scalar(
                    select(SalesInvoice).where(
                        SalesInvoice.id == source_id,
                        SalesInvoice.firm_id == firm_id,
                        SalesInvoice.is_deleted.is_(False),
                    )
                )
                if invoice is None:
                    raise ResourceNotFoundError("Sales invoice not found.")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": invoice.id,
                        "source_document_number": invoice.invoice_number,
                        "source_document_date": invoice.invoice_date,
                        "customer_id": invoice.customer_id,
                        "branch_id": invoice.branch_id,
                        "salesman_id": invoice.salesman_id,
                        "territory_id": invoice.territory_id,
                    }
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        header: dict[str, UUID] = {}
        for field in ("customer_id", "branch_id", "salesman_id", "territory_id"):
            value = _optional_uuid(first.get(field))
            if value is not None:
                header[field] = value
        for source in source_rows[1:]:
            if (
                source["customer_id"] != header["customer_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same customer and "
                    "branch."
                )
        selected = {
            source_id
            for item in source_rows
            if (source_id := _optional_uuid(item["source_document_id"])) is not None
        }
        for line in lines:
            if line["source_document_id"] not in selected:
                raise ValidationError(
                    "Every return line must reference a selected source document."
                )
        return header, source_rows, lines

    def _source_line(self, source_type: str, line_id: object) -> SourceLine:
        row: SourceLine | None
        if source_type == SalesReturnSourceType.DELIVERY_NOTE.value:
            row = self._session.scalar(
                select(DeliveryNoteLine).where(DeliveryNoteLine.id == line_id)
            )
        else:
            row = self._session.scalar(
                select(SalesInvoiceLine).where(SalesInvoiceLine.id == line_id)
            )
        if row is None:
            raise ResourceNotFoundError("Source document line not found.")
        return row

    def _source_quantity(self, source_type: str, source_line: SourceLine) -> Decimal:
        """How much the source document actually sent the customer."""
        if source_type == SalesReturnSourceType.DELIVERY_NOTE.value:
            return self._q(getattr(source_line, "current_delivery_quantity", ZERO))
        return self._q(getattr(source_line, "current_invoice_quantity", ZERO))

    def _source_uom_id(self, source_line: SourceLine) -> UUID | None:
        return (
            getattr(source_line, "sales_uom_id", None)
            or getattr(source_line, "invoice_uom_id", None)
            or getattr(source_line, "inventory_uom_id", None)
        )

    def _source_document_number(self, source_line: SourceLine) -> str:
        """Read the number off the source header, narrowed on the line's class."""
        if isinstance(source_line, DeliveryNoteLine):
            note = self._session.get(DeliveryNote, source_line.delivery_note_id)
            return "" if note is None else note.delivery_note_number
        invoice = self._session.get(SalesInvoice, source_line.sales_invoice_id)
        return "" if invoice is None else invoice.invoice_number

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _already_returned_quantity(
        self,
        *,
        firm_id: UUID,
        source_document_line_id: UUID,
        exclude_return_id: UUID | None = None,
    ) -> Decimal:
        """How much of this source line has already gone back.

        A return being edited excludes its own lines: they are about to be
        replaced, and counting them would make the second save of an unchanged
        document fail as an over-return.
        """
        statement = (
            select(func.coalesce(func.sum(SalesReturnLine.current_return_quantity), 0))
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(
                SalesReturn.firm_id == firm_id,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.not_in(_SPENT_STATUSES),
                SalesReturnLine.is_deleted.is_(False),
                SalesReturnLine.source_document_line_id == source_document_line_id,
            )
        )
        if exclude_return_id is not None:
            statement = statement.where(SalesReturn.id != exclude_return_id)
        return self._q(self._session.scalar(statement) or ZERO)

    def _resolve_return_batch(self, line: SalesReturnLine) -> UUID | None:
        """Resolve the batch these goods are going back into.

        A return never creates a batch. A number nobody was ever shipped is a
        typing mistake to correct, not stock history to invent, and putting
        goods into a batch that never existed would leave a batch holding units
        that were never received.
        """
        number = (line.batch_number or "").strip()
        if not number:
            return None
        return (
            BatchSerialService(self._session)
            .resolve_for_issue(
                firm_scope=line.firm_id,
                product_id=line.product_id,
                batch_number=number,
            )
            .id
        )

    def _movement_value(self, movement_ids: list[UUID]) -> Decimal:
        if not movement_ids:
            return ZERO
        return self._q(
            self._session.scalar(
                select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                    StockLedgerEntry.transaction_id.in_(movement_ids),
                    StockLedgerEntry.is_deleted.is_(False),
                )
            )
            or ZERO
        )

    def _lines_of(self, return_id: UUID) -> list[SalesReturnLine]:
        return list(
            self._session.scalars(
                select(SalesReturnLine)
                .where(
                    SalesReturnLine.sales_return_id == return_id,
                    SalesReturnLine.is_deleted.is_(False),
                )
                .order_by(SalesReturnLine.line_number.asc())
            ).all()
        )

    def _tax_amount(
        self,
        *,
        return_date: date,
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
        response = self._tax.simulate(
            TaxRuleSimulationRequest(
                transaction_type="SALES_RETURN",
                transaction_date=return_date,
                business_profile_id=business_profile_id,
                tax_profile_id=tax_profile_id,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                customer_id=customer_id,
                product_id=product_id,
                invoice_value=invoice_value,
                additional_context={"source": "sales_return"},
            ),
            firm_scope=firm_id,
            actor_id=actor_id,
        )
        return self._q(response.total_tax_amount)

    # ---- import and export ---------------------------------------------

    def import_returns(
        self, data: SalesReturnImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[SalesReturn]:
        """Create a validated batch of sales returns in one transaction.

        The whole batch lands or none of it does. Anything else asks somebody
        to work out which rows of their file already went in before they can
        correct it and try again -- and a refused record leaves its own header
        flushed on the session, so without the rollback the caller inherits
        half a document as well as the committed ones.
        """
        try:
            rows = [
                self._stage_return(record, firm_id=firm_scope, actor_id=actor_id)
                for record in data.records
            ]
        except Exception:
            self._session.rollback()
            raise
        self._session.commit()
        return rows

    def export_returns_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        """Export matching sales returns as CSV."""
        rows, _ = self.list_returns(
            firm_scope=firm_scope,
            filters=SalesReturnListFilters(),
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
                "customer_return_number",
                "return_date",
                "customer_id",
                "branch_id",
                "warehouse_id",
                "status",
                "total_current_return_quantity",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.return_number,
                    row.customer_return_number,
                    row.return_date.isoformat(),
                    str(row.customer_id),
                    str(row.branch_id),
                    str(row.warehouse_id),
                    row.status,
                    str(row.total_current_return_quantity),
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    # ---- responses -----------------------------------------------------

    def return_response(self, row: SalesReturn) -> SalesReturnResponse:
        """Build the full response for one sales return."""
        lines = self._lines_of(row.id)
        sources = list(
            self._session.scalars(
                select(SalesReturnSource).where(
                    SalesReturnSource.sales_return_id == row.id,
                    SalesReturnSource.is_deleted.is_(False),
                )
            ).all()
        )
        attachments = list(
            self._session.scalars(
                select(SalesReturnAttachment).where(
                    SalesReturnAttachment.sales_return_id == row.id,
                    SalesReturnAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(SalesReturnNote).where(
                    SalesReturnNote.sales_return_id == row.id,
                    SalesReturnNote.is_deleted.is_(False),
                )
            ).all()
        )
        return SalesReturnResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            business_profile_id=row.business_profile_id,
            return_number=row.return_number,
            return_date=row.return_date,
            customer_return_number=row.customer_return_number,
            customer_return_date=row.customer_return_date,
            reference_delivery_note_number=row.reference_delivery_note_number,
            reference_invoice_number=row.reference_invoice_number,
            return_reason=row.return_reason,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_over_return=row.allow_over_return,
            over_return_percent=row.over_return_percent,
            status=SalesReturnStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_returned_quantity=row.total_already_returned_quantity,
            total_current_return_quantity=row.total_current_return_quantity,
            total_restock_quantity=row.total_restock_quantity,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            journal_entry_id=row.journal_entry_id,
            cost_journal_entry_id=row.cost_journal_entry_id,
            approved_at=row.approved_at,
            completed_at=row.completed_at,
            closed_at=row.closed_at,
            cancel_reason=row.cancel_reason,
            close_reason=row.close_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version,
            lines=[
                SalesReturnLineResponse.model_validate(line, from_attributes=True)
                for line in lines
            ],
            sources=[
                SalesReturnSourceResponse.model_validate(source, from_attributes=True)
                for source in sources
            ],
            attachments=[
                SalesReturnAttachmentResponse.model_validate(item, from_attributes=True)
                for item in attachments
            ],
            notes=[
                SalesReturnNoteResponse.model_validate(item, from_attributes=True)
                for item in notes
            ],
        )

    # ---- reports -------------------------------------------------------

    def register_report(self, *, firm_scope: UUID) -> list[SalesReturnRegisterRecord]:
        """Every sales return raised, with what it was worth."""
        return [
            SalesReturnRegisterRecord(
                return_id=row.id,
                return_number=row.return_number,
                customer_return_number=row.customer_return_number,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=row.warehouse_id,
                return_date=row.return_date,
                grand_total=row.grand_total,
                status=SalesReturnStatus(row.status),
            )
            for row in self._session.scalars(
                select(SalesReturn)
                .where(
                    SalesReturn.firm_id == firm_scope,
                    SalesReturn.is_deleted.is_(False),
                )
                .order_by(SalesReturn.return_date.desc())
            ).all()
        ]

    def by_customer_report(
        self, *, firm_scope: UUID
    ) -> list[SalesReturnByCustomerRecord]:
        """Total returned value and count per customer."""
        rows = list(
            self._session.scalars(
                select(SalesReturn).where(
                    SalesReturn.firm_id == firm_scope,
                    SalesReturn.is_deleted.is_(False),
                    SalesReturn.status.not_in(_SPENT_STATUSES),
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for row in rows:
            totals[row.customer_id] += row.grand_total
            counts[row.customer_id] += 1
        names = {
            customer.id: customer.display_name
            for customer in self._session.scalars(
                select(Customer).where(Customer.id.in_(list(totals.keys())))
            ).all()
        }
        return [
            SalesReturnByCustomerRecord(
                customer_id=customer_id,
                customer_name=names.get(customer_id, str(customer_id)),
                return_amount=self._q(amount),
                return_count=counts[customer_id],
            )
            for customer_id, amount in totals.items()
        ]

    def by_product_report(
        self, *, firm_scope: UUID
    ) -> list[SalesReturnByProductRecord]:
        """Total returned quantity and value per product."""
        lines = self._report_lines(firm_scope=firm_scope)
        quantities: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        restocked: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        amounts: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for line, _ in lines:
            quantities[line.product_id] += line.current_return_quantity
            restocked[line.product_id] += line.restock_quantity
            amounts[line.product_id] += line.net_amount
            counts[line.product_id] += 1
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(list(quantities.keys())))
            ).all()
        }
        return [
            SalesReturnByProductRecord(
                product_id=product_id,
                product_code=(
                    products[product_id].code
                    if product_id in products
                    else str(product_id)
                ),
                product_name=(
                    products[product_id].name
                    if product_id in products
                    else str(product_id)
                ),
                return_quantity=self._q(quantity),
                restock_quantity=self._q(restocked[product_id]),
                return_amount=self._q(amounts[product_id]),
                return_count=counts[product_id],
            )
            for product_id, quantity in quantities.items()
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID
    ) -> list[SalesReturnReconciliationRecord]:
        """Return lines set against the documents they were dispatched on."""
        lines = self._report_lines(firm_scope=firm_scope)
        names = {
            product.id: product.name
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line, _ in lines])
                )
            ).all()
        }
        records: list[SalesReturnReconciliationRecord] = []
        for line, header in lines:
            pending = self._q(
                line.dispatched_quantity
                - line.already_returned_quantity
                - line.current_return_quantity
            )
            records.append(
                SalesReturnReconciliationRecord(
                    return_id=header.id,
                    return_number=header.return_number,
                    return_date=header.return_date,
                    source_document_type=SalesReturnSourceType(
                        line.source_document_type
                    ),
                    source_document_id=line.source_document_id,
                    source_document_number=line.source_document_number,
                    source_document_line_id=line.source_document_line_id,
                    source_document_line_number=line.source_document_line_number,
                    product_id=line.product_id,
                    product_name=names.get(line.product_id, str(line.product_id)),
                    dispatched_quantity=line.dispatched_quantity,
                    already_returned_quantity=line.already_returned_quantity,
                    current_return_quantity=line.current_return_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                    restock_quantity=line.restock_quantity,
                    reason_code=line.reason_code,
                    is_damaged=line.is_damaged,
                    is_expired=line.is_expired,
                )
            )
        return records

    def _report_lines(
        self, *, firm_scope: UUID
    ) -> list[tuple[SalesReturnLine, SalesReturn]]:
        """Every live return line in scope, with the return it belongs to.

        Cancelled returns are left out: a cancelled return did not happen, and
        counting its lines overstates every line report against the header ones.
        """
        return [
            (line, header)
            for line, header in self._session.execute(
                select(SalesReturnLine, SalesReturn)
                .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
                .where(
                    SalesReturn.firm_id == firm_scope,
                    SalesReturn.is_deleted.is_(False),
                    SalesReturn.status.not_in(_SPENT_STATUSES),
                    SalesReturnLine.is_deleted.is_(False),
                )
            ).all()
        ]

    # ---- lifecycle plumbing --------------------------------------------

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document: SalesReturn,
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
                source_module_code="SALES_RETURN",
                document_number=document.return_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "return_number": document.return_number,
                    "customer_return_number": document.customer_return_number or "",
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
