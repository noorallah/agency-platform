"""Purchase return workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.batch_serial.services import BatchSerialService
from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.common.report_names import (
    branch_names,
    vendor_names,
    vendors_matching,
    warehouse_names,
)
from app.core.database.batch import children_by_parent
from app.core.exceptions import (
    ApplicationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger, quantize_money
from app.core.utils.pricing import (
    LineDiscount,
    inherited_share,
    resolve_line_discount,
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
from app.finance.currency import is_foreign, normalize_currency, rupee_rate
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.goods_receipt.billing import (
    BILLED_STATES,
    ReceiptLineBilling,
    receipt_line_billing,
    receipt_line_costs,
)
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.rules import (
    POSTED_STATES,
    posted_receipt_line,
    require_posted_receipt,
)
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.inventory.services import InventoryService
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import PurchaseInvoiceStatus
from app.purchase_invoice.services.reverse_charge import (
    ReverseChargeShare,
    reverse_charge_share,
)
from app.purchase_invoice.services.rupees import bill_line_rupee_rates
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnAccountingEvent,
    PurchaseReturnAttachment,
    PurchaseReturnLine,
    PurchaseReturnNote,
    PurchaseReturnSource,
)
from app.purchase_return.schemas import (
    PurchaseReturnAccountingEventResponse,
    PurchaseReturnAccountingEventType,
    PurchaseReturnAttachmentResponse,
    PurchaseReturnAttachmentWrite,
    PurchaseReturnByProductRecord,
    PurchaseReturnByVendorRecord,
    PurchaseReturnCreate,
    PurchaseReturnImportRequest,
    PurchaseReturnLineResponse,
    PurchaseReturnListFilters,
    PurchaseReturnNoteResponse,
    PurchaseReturnNoteWrite,
    PurchaseReturnPreview,
    PurchaseReturnReconciliationRecord,
    PurchaseReturnRegisterRecord,
    PurchaseReturnResponse,
    PurchaseReturnSourceResponse,
    PurchaseReturnSourceType,
    PurchaseReturnStatus,
    PurchaseReturnSummary,
)
from app.purchase_return.serials import ReturnSerials
from app.sales.services.document_preview import purchase_line_companions
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.place_of_supply import PURCHASE_INTERSTATE
from app.tax.services.rule_stamp import stamps_tax_rules
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.services import (
    UomService,
    assert_quantity_fits_unit,
    price_per_source_unit,
)
from app.vendors.models import Vendor

ZERO = Decimal("0")

# The line shapes this document can be raised from. Naming the union lets the
# helpers below say what they accept instead of taking ``object`` and reaching
# for attributes mypy cannot see.
SourceLine = GoodsReceiptLine | PurchaseInvoiceLine | PurchaseOrderLine


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


def _required_uuid(value: object) -> UUID:
    """Read a UUID the line spec must carry."""
    return value if isinstance(value, UUID) else UUID(str(value))


#: A supplier bill a return can be raised against: it raised a payable that
#: still stands. CLOSED means nothing more to pay, not that nothing was bought.
_RETURNABLE_INVOICE_STATES = frozenset(
    {PurchaseInvoiceStatus.APPROVED.value, PurchaseInvoiceStatus.CLOSED.value}
)


class PurchaseReturnService(TransactionalDocumentService):
    """Coordinate supplier return lifecycle and source-document validation."""

    DOCUMENT = DocumentTypeSpec(
        code="PURCHASE_RETURN",
        name="Purchase Return",
        description="Supplier return document",
        category="PURCHASE",
        module="purchase_return",
        prefix="PR",
        include_branch_code=True,
        include_company_code=True,
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
        self._serials = ReturnSerials(session)

    def list_returns(
        self,
        *,
        firm_scope: UUID,
        filters: PurchaseReturnListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[PurchaseReturn], int]:
        """List purchase returns for the visible firm scope."""
        columns = {
            "return_number": PurchaseReturn.return_number,
            "return_date": PurchaseReturn.return_date,
            "warehouse_id": PurchaseReturn.warehouse_id,
            "grand_total": PurchaseReturn.grand_total,
            "status": PurchaseReturn.status,
            "created_at": PurchaseReturn.created_at,
            "updated_at": PurchaseReturn.updated_at,
        }
        statement = select(PurchaseReturn).where(PurchaseReturn.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(PurchaseReturn)
            .where(PurchaseReturn.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(PurchaseReturn.is_deleted.is_(False))
            count = count.where(PurchaseReturn.is_deleted.is_(False))
        if filters.vendor_id is not None:
            statement = statement.where(PurchaseReturn.vendor_id == filters.vendor_id)
            count = count.where(PurchaseReturn.vendor_id == filters.vendor_id)
        if filters.branch_id is not None:
            statement = statement.where(PurchaseReturn.branch_id == filters.branch_id)
            count = count.where(PurchaseReturn.branch_id == filters.branch_id)
        if filters.warehouse_id is not None:
            statement = statement.where(
                PurchaseReturn.warehouse_id == filters.warehouse_id
            )
            count = count.where(PurchaseReturn.warehouse_id == filters.warehouse_id)
        if filters.status is not None:
            statement = statement.where(PurchaseReturn.status == filters.status.value)
            count = count.where(PurchaseReturn.status == filters.status.value)
        if filters.return_from is not None:
            statement = statement.where(
                PurchaseReturn.return_date >= filters.return_from
            )
            count = count.where(PurchaseReturn.return_date >= filters.return_from)
        if filters.return_to is not None:
            statement = statement.where(PurchaseReturn.return_date <= filters.return_to)
            count = count.where(PurchaseReturn.return_date <= filters.return_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                PurchaseReturn.return_number.ilike(token),
                PurchaseReturn.supplier_return_number.ilike(token),
                PurchaseReturn.reference_number.ilike(token),
                PurchaseReturn.remarks.ilike(token),
                PurchaseReturn.vendor_id.in_(vendors_matching(token)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, PurchaseReturn.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    sort_column.desc() if descending else sort_column.asc(),
                    # Newest first within the chosen column, then a stable key.
                    PurchaseReturn.created_at.desc(),
                    PurchaseReturn.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> PurchaseReturnSummary:
        """Return aggregate purchase return values for the visible firm scope.

        Counted and summed in SQL, one row per status, rather than loading every
        document the firm ever raised (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    PurchaseReturn.status,
                    func.count(),
                    func.coalesce(func.sum(PurchaseReturn.grand_total), 0),
                )
                .where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                )
                .group_by(PurchaseReturn.status)
            ).all()
        }

        def count(status: PurchaseReturnStatus) -> int:
            """Return how many documents are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        return PurchaseReturnSummary(
            total=sum(number for number, _ in by_status.values()),
            draft=count(PurchaseReturnStatus.DRAFT),
            approved=count(PurchaseReturnStatus.APPROVED),
            completed=count(PurchaseReturnStatus.COMPLETED),
            cancelled=count(PurchaseReturnStatus.CANCELLED),
            closed=count(PurchaseReturnStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
        )

    def create_return(
        self, data: PurchaseReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Create one purchase return and commit it."""
        self._refuse_empty_return_lines(data)
        row = self.stage_return(data, firm_id=firm_id, actor_id=actor_id)
        self._refuse_unresolved_batches(row)
        self._session.commit()
        return row

    def _refuse_empty_return_lines(self, data: PurchaseReturnCreate) -> None:
        """Refuse a return line that sends nothing back, where saved (D-BUY-53)."""
        self._refuse_lines_for_nothing(
            (
                (line.line_number, line.current_return_quantity, None)
                for line in data.lines
            ),
            does="returns",
            document="return",
            free_goods=False,
        )

    def preview_return(
        self, data: PurchaseReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseReturnPreview:
        """Price a return exactly as saving it would, then save nothing.

        Staged through the save path -- the receipt's prices, tax at the
        rates in force -- read back, and the unit of work rolled back: no
        return, no number used up, no audit row.
        """
        try:
            row = self.stage_return(data, firm_id=firm_id, actor_id=actor_id)
            response = self.return_response(row)
            interstate = (
                self._tax.inward_transaction_type(
                    "PURCHASE_RETURN",
                    firm_id=firm_id,
                    branch_id=response.branch_id,
                    vendor_id=response.vendor_id,
                )
                == PURCHASE_INTERSTATE
            )
            lines = purchase_line_companions(
                self._session,
                firm_id=firm_id,
                vendor_id=response.vendor_id,
                lines=[
                    (line.line_number, line.product_id, line.warehouse_id)
                    for line in response.lines
                ],
            )
        finally:
            self._session.rollback()
        return PurchaseReturnPreview(
            purchase_return=response, interstate=interstate, lines=lines
        )

    def stage_return(
        self, data: PurchaseReturnCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Build one purchase return as a draft without committing it."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_return_sources(
            data, firm_id=firm_id
        )
        branch_id = data.branch_id or header["branch_id"]
        vendor_id = data.vendor_id or header["vendor_id"]
        business_profile_id = data.business_profile_id
        if vendor_id != header["vendor_id"]:
            raise ValidationError("Return vendor must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Return branch must match all source documents.")
        if data.supplier_return_number:
            self._validate_supplier_return_number(
                firm_id=firm_id,
                vendor_id=vendor_id,
                supplier_return_number=data.supplier_return_number,
            )
        currency_code, exchange_rate = self._source_currency(
            source_rows, firm_id=firm_id
        )
        return_number = self._issue_number(
            numbering_rule,
            typed=data.return_number.strip().upper() if data.return_number else None,
            number_column=PurchaseReturn.return_number,
            firm_id=firm_id,
            document_date=data.return_date,
            actor_id=actor_id,
            branch_code=self._scope_code(branch_id),
            company_code=self._company_code(firm_id),
        )
        row = PurchaseReturn(
            firm_id=firm_id,
            vendor_id=vendor_id,
            branch_id=branch_id,
            warehouse_id=data.warehouse_id,
            business_profile_id=business_profile_id,
            return_number=return_number,
            return_date=data.return_date,
            supplier_return_number=(
                data.supplier_return_number.strip()
                if data.supplier_return_number
                else None
            ),
            supplier_return_date=data.supplier_return_date,
            reference_grn_number=data.reference_grn_number,
            reference_invoice_number=data.reference_invoice_number,
            return_reason=data.return_reason,
            outcome=(data.outcome or "CREDIT"),
            # Never what was typed: a return is in the currency of what it
            # sends back, at that document's rate (D-BUY-41).
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            payment_terms=data.payment_terms,
            due_date=data.due_date,
            reference_number=data.reference_number,
            remarks=data.remarks,
            status=PurchaseReturnStatus.DRAFT.value,
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
            return_date=data.return_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
        )
        self._serials.pick(row, line_specs, {}, actor_id=actor_id)
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_returned_quantity = line_totals[
            "total_already_returned_quantity"
        ]
        row.total_current_return_quantity = line_totals["total_current_return_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_id
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_id)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_id)
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
            action="purchase_return.created",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"return_number": row.return_number, "status": row.status},
        )
        self._flush_or_conflict("Purchase return number already exists in this firm.")
        return row

    def update_return(
        self,
        return_id: UUID,
        data: PurchaseReturnCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseReturn:
        """Replace one purchase return."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != PurchaseReturnStatus.DRAFT.value:
            raise ValidationError("Only draft purchase returns can be updated.")
        self._refuse_empty_return_lines(data)
        # The lines are re-inserted below, so the units each named are carried
        # across by line number for a line that says nothing of them (PG-10).
        kept_serials = self._serials.kept(row)
        self._serials.clear(row)
        self._delete_children(row.id)
        header, source_rows, line_specs = self._prepare_return_sources(data, firm_scope)
        row.vendor_id = data.vendor_id or header["vendor_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.warehouse_id = data.warehouse_id
        row.business_profile_id = data.business_profile_id
        row.return_date = data.return_date
        row.supplier_return_number = (
            data.supplier_return_number.strip() if data.supplier_return_number else None
        )
        row.supplier_return_date = data.supplier_return_date
        row.reference_grn_number = data.reference_grn_number
        row.reference_invoice_number = data.reference_invoice_number
        row.return_reason = data.return_reason
        # Absent keeps what the return comes back as (69 row 7).
        if data.outcome is not None:
            row.outcome = data.outcome
        row.currency_code, row.exchange_rate = self._source_currency(
            source_rows, firm_id=firm_scope
        )
        row.payment_terms = data.payment_terms
        row.due_date = data.due_date
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        if row.supplier_return_number:
            self._validate_supplier_return_number(
                firm_id=firm_scope,
                vendor_id=row.vendor_id,
                supplier_return_number=row.supplier_return_number,
                current_id=row.id,
            )
        self._replace_sources(row, source_rows, firm_id=firm_scope, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_scope,
            return_date=data.return_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        self._serials.pick(row, line_specs, kept_serials, actor_id=actor_id)
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_returned_quantity = line_totals[
            "total_already_returned_quantity"
        ]
        row.total_current_return_quantity = line_totals["total_current_return_quantity"]
        row.line_discount_total = line_totals["line_discount_total"]
        row.subtotal = line_totals["subtotal"]
        row.tax_total = line_totals["tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_scope
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_scope)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            document=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_return.updated",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._refuse_unresolved_batches(row)
        self._session.commit()
        return row

    def approve_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Approve one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status != PurchaseReturnStatus.DRAFT.value:
            raise ValidationError("Only draft purchase returns can be approved.")
        before = row.status
        row.status = PurchaseReturnStatus.APPROVED.value
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
            action="purchase_return.approved",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        self._session.commit()
        return row

    def complete_return(
        self, return_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> PurchaseReturn:
        """Complete one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == PurchaseReturnStatus.COMPLETED.value:
            return row
        if row.status in {
            PurchaseReturnStatus.CANCELLED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            raise ValidationError(
                "Cancelled/closed purchase returns cannot be completed."
            )
        if row.status != PurchaseReturnStatus.APPROVED.value:
            raise ValidationError("Only approved purchase returns can be completed.")
        # Checked again where the stock leaves, so a return saved before the
        # check existed cannot send back goods through a line it does not own.
        self._refuse_foreign_lines(row, firm_id=firm_scope)
        lines = list(
            self._session.scalars(
                select(PurchaseReturnLine).where(
                    PurchaseReturnLine.purchase_return_id == row.id,
                    PurchaseReturnLine.is_deleted.is_(False),
                )
            ).all()
        )
        if not lines:
            raise ValidationError("Purchase return must contain at least one line.")
        movement_ids: list[UUID] = []
        for line in lines:
            # The header's warehouse when the line does not name one, exactly
            # as `SalesReturnService.complete_return` has always done. This
            # refused outright instead, which made a return created with only
            # the header warehouse -- a *required* field -- a document that
            # could be raised and approved and then never completed. Nothing
            # in the demo had ever completed one, so the dead end went unseen
            # until the history generator raised its first.
            warehouse_id = line.warehouse_id or row.warehouse_id
            if warehouse_id is None:
                raise ValidationError(
                    "Warehouse is required on all return lines before completion."
                )
            # What leaves the shelf: the charged units and the free ones
            # going back beside them (D-BUY-56).
            current_qty = self._q(line.current_return_quantity + line.free_quantity)
            rejected_qty = line.rejected_quantity
            sellable_qty = self._q(current_qty - rejected_qty)
            if sellable_qty < ZERO:
                raise ValidationError(
                    "Rejected quantity cannot exceed returned quantity."
                )
            batch_id = self._resolve_return_batch(line)
            if batch_id is not None:
                line.batch_id = batch_id
            transaction = self._inventory.record_purchase_return(
                firm_scope=firm_scope,
                actor_id=actor_id,
                branch_id=row.branch_id,
                warehouse_id=warehouse_id,
                storage_node_id=line.storage_node_id,
                product_id=line.product_id,
                reference_number=row.return_number,
                transaction_date=row.return_date,
                return_quantity=current_qty,
                sellable_quantity=sellable_qty,
                damaged_quantity=rejected_qty if line.is_damaged else ZERO,
                scrap_quantity=rejected_qty if line.is_scrap else ZERO,
                quarantine_quantity=(
                    rejected_qty if line.item_condition == "QUARANTINE" else ZERO
                ),
                entered_quantity=current_qty,
                entered_uom_id=self._counted_in(line),
                conversion_version=line.conversion_version,
                remarks=line.remarks or row.remarks,
                batch_id=batch_id,
                rejects_held=self._rejects_awaiting_return(line),
            )
            line.inventory_transaction_id = transaction.id
            line.updated_by = actor_id
            movement_ids.append(transaction.id)
            # The units named go back with the stock, one per unit (PG-10).
            self._serials.send_back(
                row,
                line,
                base_quantity=abs(Decimal(str(transaction.quantity))),
                warehouse_id=warehouse_id,
                movement_id=transaction.id,
                actor_id=actor_id,
            )
        # What the goods actually cost, taken from the stock ledger rows the
        # movements above wrote. The return is priced at what the supplier will
        # credit; stock leaves at the moving average it was carried at, and the
        # two are routinely different.
        stock_value = self._q(
            self._session.scalar(
                select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                    StockLedgerEntry.transaction_id.in_(movement_ids),
                    StockLedgerEntry.is_deleted.is_(False),
                )
            )
            or ZERO
        )
        # What went back before any bill reached it reverses the receipt's
        # accrual; only the rest is a debit note (D-BUY-26).
        grni_amount = self._split_against_billing(lines)
        self._session.flush()
        # A return of goods bought in another currency is priced in it; what
        # the supplier is debited with and the tax reversed post in rupees at
        # the bill's own rate, as the bill posted them (D-BUY-41). The stock
        # leg above is the movement's rupee cost, so a gap is a variance.
        self._stamp_billed_rate(row, lines)
        billed_total, billed_tax = return_billed_amounts(self._session, [row])[row.id]
        # Posting runs before the commit and may fail the completion, matching
        # every other document: goods that left stock with no journal behind
        # them are how the inventory control account stops reconciling.
        self._posting.post_purchase_return(
            firm_id=firm_scope,
            return_id=row.id,
            return_number=row.return_number,
            return_date=row.return_date,
            stock_value=stock_value,
            tax_amount=billed_tax,
            total_amount=billed_total,
            grni_amount=grni_amount,
            actor_id=actor_id,
            tax_by_component=self._tax_by_component(row.id),
            blocked_tax_amount=sum(
                return_tax_by_component(
                    self._session, row.id, claimable=False
                ).values(),
                ZERO,
            ),
            reverse_charge_by_component=return_reverse_charge(
                self._session, row.id
            ).owed,
        )
        before = row.status
        row.status = PurchaseReturnStatus.COMPLETED.value
        row.updated_by = actor_id
        if row.outcome == "REPLACEMENT":
            # The goods sent back are owed again on the order (69 row 7).
            self._session.flush()
            self._resync_replaced_orders(row, firm_scope=firm_scope, actor_id=actor_id)
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
            action="purchase_return.completed",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"status": before},
            after_data={"status": row.status},
        )
        self._session.commit()
        return row

    def _source_currency(
        self, source_rows: Sequence[dict[str, object]], *, firm_id: UUID
    ) -> tuple[str | None, Decimal | None]:
        """Return the currency and rate of the documents a return sends back.

        A supplier's bill in another currency (PG-12) carries its own; a goods
        receipt is in its order's, at the rate its stock was valued at. Both
        None for rupees. The bill's rate is preferred where a return names
        both, because the bill is what raised the payable (D-BUY-41).

        Raises:
            ValidationError: If the documents are in different currencies.

        """
        found: list[tuple[str | None, Decimal | None, bool]] = []
        for source in source_rows:
            source_id = _required_uuid(source["source_document_id"])
            is_bill = (
                source["source_document_type"]
                == PurchaseReturnSourceType.PURCHASE_INVOICE.value
            )
            if is_bill:
                pair = self._session.execute(
                    select(
                        PurchaseInvoice.currency_code, PurchaseInvoice.exchange_rate
                    ).where(
                        PurchaseInvoice.id == source_id,
                        PurchaseInvoice.firm_id == firm_id,
                    )
                ).first()
            else:
                pair = self._session.execute(
                    select(PurchaseOrder.currency_code, PurchaseOrder.exchange_rate)
                    .join(
                        GoodsReceipt,
                        GoodsReceipt.purchase_order_id == PurchaseOrder.id,
                    )
                    .where(
                        GoodsReceipt.id == source_id,
                        GoodsReceipt.firm_id == firm_id,
                    )
                ).first()
            code, rate = (None, None) if pair is None else (pair[0], pair[1])
            if is_foreign(code) and rate is not None:
                found.append((normalize_currency(code), Decimal(str(rate)), is_bill))
            else:
                found.append((None, None, is_bill))
        currencies = {code for code, _, _ in found}
        if len(currencies) > 1:
            named = ", ".join(sorted(code or "rupees" for code in currencies))
            raise ValidationError(
                f"These documents are in different currencies ({named}). Raise "
                "one purchase return for each currency.",
                details={"field": "source_documents"},
            )
        # Bills first: False sorts ahead of True.
        found.sort(key=lambda item: not item[2])
        code, rate, _ = found[0] if found else (None, None, False)
        return code, rate

    def _stamp_billed_rate(
        self, row: PurchaseReturn, lines: Sequence[PurchaseReturnLine]
    ) -> None:
        """Give a return in another currency the rate of the bill it reverses.

        A return raised off a goods receipt starts at its order's rate; once a
        bill has reached those goods, the bill's rate is what the payable and
        the input credit were posted at, and so what comes off them.
        """
        if not is_foreign(row.currency_code):
            return
        bill_lines = sorted(
            {
                bill_line_id
                for named in _billed_lines(self._session, lines).values()
                for bill_line_id, _ in named
            },
            key=str,
        )
        rates = bill_line_rupee_rates(self._session, bill_lines)
        for bill_line_id in bill_lines:
            rate = rates.get(bill_line_id)
            if rate is not None and rate != Decimal("1"):
                row.exchange_rate = rate
                return

    def _split_against_billing(self, lines: Sequence[PurchaseReturnLine]) -> Decimal:
        """Take each receipt line's return off what was still to bill first.

        A return raised off a goods receipt line is set first against the part
        of that line no approved bill has reached -- accepted, less billed,
        less what earlier returns took off it -- and only the rest against
        what was billed (D-BUY-26, the purchase-receipt return of ERPNext and
        Tally). The first part never became a payable or an input credit, so
        it comes off goods received not invoiced at the receipt's own cost and
        lowers what the supplier may still bill; the rest is the debit note.

        Each line's share of the accrual is in proportion to the quantity; the
        return that leaves nothing to bill or return on its receipt takes what
        the bills and earlier returns left, so the receipt's accrual nets to
        exactly zero, as the bill that completes a receipt does.

        Returns:
            What the return takes off goods received not invoiced.

        """
        for line in lines:
            line.unbilled_quantity = ZERO
            line.grni_amount = ZERO
        on_receipts = [
            line
            for line in lines
            if line.source_document_type == PurchaseReturnSourceType.GOODS_RECEIPT.value
        ]
        if not on_receipts:
            return ZERO
        receipt_ids = set(
            self._session.scalars(
                select(GoodsReceiptLine.goods_receipt_id).where(
                    GoodsReceiptLine.id.in_(
                        {line.source_document_line_id for line in on_receipts}
                    )
                )
            ).all()
        )
        receipt_lines = {
            line.id: line
            for line in self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id.in_(list(receipt_ids)),
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all()
        }
        positions = receipt_line_billing(self._session, receipt_lines.values())
        costs = receipt_line_costs(self._session, receipt_lines.values())
        taken: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        for line in sorted(on_receipts, key=lambda item: item.line_number):
            source_id = line.source_document_line_id
            position = positions.get(source_id)
            if position is None:
                continue
            open_quantity = max(position.left_to_bill - taken[source_id], ZERO)
            unbilled = self._q(
                min(Decimal(str(line.current_return_quantity)), open_quantity)
            )
            if unbilled <= ZERO:
                continue
            taken[source_id] += unbilled
            line.unbilled_quantity = unbilled
            if position.accepted > ZERO:
                line.grni_amount = quantize_ledger(
                    costs.get(source_id, ZERO) * unbilled / position.accepted
                )
        for receipt_id in receipt_ids:
            self._settle_receipt_residual(
                [
                    line
                    for line in on_receipts
                    if line.unbilled_quantity > ZERO
                    and receipt_lines[line.source_document_line_id].goods_receipt_id
                    == receipt_id
                ],
                [
                    line_id
                    for line_id, line in receipt_lines.items()
                    if line.goods_receipt_id == receipt_id
                ],
                positions=positions,
                costs=costs,
                taken=taken,
            )
        return sum((Decimal(str(line.grni_amount)) for line in on_receipts), ZERO)

    def _settle_receipt_residual(
        self,
        mine: list[PurchaseReturnLine],
        receipt_line_ids: list[UUID],
        *,
        positions: dict[UUID, ReceiptLineBilling],
        costs: dict[UUID, Decimal],
        taken: dict[UUID, Decimal],
    ) -> None:
        """Give the receipt's rounding residual to the return that finishes it.

        Only when this return leaves nothing on the receipt to bill or to
        return before billing: then its accrual is what the receipt posted,
        less what every approved bill cleared -- each its own rounded share,
        none of them having finished the receipt -- less earlier returns.
        """
        if not mine:
            return
        if any(
            positions[line_id].billed
            + positions[line_id].returned_unbilled
            + taken.get(line_id, ZERO)
            < positions[line_id].accepted
            for line_id in receipt_line_ids
        ):
            return
        posted = quantize_ledger(
            sum((costs.get(line_id, ZERO) for line_id in receipt_line_ids), ZERO)
        )
        bills: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        for bill_id, line_id, quantity in self._session.execute(
            select(
                PurchaseInvoiceLine.purchase_invoice_id,
                PurchaseInvoiceLine.source_document_line_id,
                PurchaseInvoiceLine.current_invoice_quantity,
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoiceLine.source_document_type
                == PurchaseReturnSourceType.GOODS_RECEIPT.value,
                PurchaseInvoiceLine.source_document_line_id.in_(receipt_line_ids),
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status.in_(BILLED_STATES),
            )
        ).all():
            accepted = positions[line_id].accepted
            if accepted > ZERO:
                bills[bill_id] += (
                    costs.get(line_id, ZERO) * Decimal(str(quantity)) / accepted
                )
        cleared = sum((quantize_ledger(share) for share in bills.values()), ZERO)
        cleared += sum(
            (positions[line_id].returned_cost for line_id in receipt_line_ids), ZERO
        )
        residual = posted - quantize_ledger(cleared)
        others = sum((Decimal(str(line.grni_amount)) for line in mine[:-1]), ZERO)
        if residual - others >= ZERO:
            mine[-1].grni_amount = residual - others

    def _rejects_awaiting_return(self, line: PurchaseReturnLine) -> Decimal:
        """Return what this line's receipt line still holds rejected for a return.

        An inspection that rejects goods "for a return" leaves them in
        quarantine until a purchase return sends them back (BUY-9). This is
        that quantity, in the stock unit, less what completed returns off the
        same receipt line have already taken from quarantine. A cancelled
        return drops its movement from its line, so it stops counting.
        """
        if line.source_document_type != PurchaseReturnSourceType.GOODS_RECEIPT.value:
            return ZERO
        receipt_line = self._session.get(GoodsReceiptLine, line.source_document_line_id)
        if receipt_line is None or receipt_line.inspection_rejected_action != "RETURN":
            return ZERO
        # Request sessions do not autoflush: an earlier line of this same
        # return has just been given its movement.
        self._session.flush()
        taken = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(InventoryTransaction.quarantine_quantity_delta), 0
                )
            )
            .join(
                PurchaseReturnLine,
                PurchaseReturnLine.inventory_transaction_id == InventoryTransaction.id,
            )
            .where(
                PurchaseReturnLine.source_document_line_id == receipt_line.id,
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturnLine.id != line.id,
            )
        )
        rejected = Decimal(str(receipt_line.inspection_rejected_quantity or ZERO))
        return max(ZERO, rejected + Decimal(str(taken or 0)))

    def _line_batch_number(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> str | None:
        """Return the batch a line sends back: typed, else its receipt line's.

        A receipt line names one batch, so a return off it that names none is
        returning that batch: the server already knows, and used to leave the
        line blank, approve it, and refuse it at Complete for want of the
        number (D-BUY-59). A line off a bill takes the batch of the receipt
        line the bill line billed. An order line names no batch.
        """
        typed = str(spec.get("batch_number") or "").strip()
        if typed:
            return typed
        receipt_line = self._receipt_line_behind(source_line)
        if receipt_line is None:
            return None
        return (receipt_line.batch_number or "").strip() or None

    def _refuse_unresolved_batches(self, row: PurchaseReturn) -> None:
        """Refuse at save a line whose batch completion would refuse (D-BUY-59).

        A product that may only leave from a batch with none named, or a
        number nobody ever received: both were told to the person only at
        Complete, after the return had been approved. A batch other than the
        one the line's receipt brought in is refused here too (D-BUY-64).
        Asked where the return is saved, not where it is previewed.

        Raises:
            ValidationError: In the words completion uses.

        """
        # Request sessions do not autoflush, and the lines were just written.
        self._session.flush()
        for line in self._session.scalars(
            select(PurchaseReturnLine)
            .where(
                PurchaseReturnLine.purchase_return_id == row.id,
                PurchaseReturnLine.is_deleted.is_(False),
            )
            .order_by(PurchaseReturnLine.line_number)
        ).all():
            self._resolve_return_batch(line)

    def _batch_brought_in(self, line: PurchaseReturnLine) -> str | None:
        """Return the batch a saved line's receipt line brought in, if any.

        A receipt line names one batch. The line may be off that receipt line
        or off a bill line billing it; a receipt line that named no batch says
        nothing about which may go back.
        """
        source_line: SourceLine | None = None
        if line.source_document_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            source_line = self._session.get(
                GoodsReceiptLine, line.source_document_line_id
            )
        elif line.source_document_type == (
            PurchaseReturnSourceType.PURCHASE_INVOICE.value
        ):
            source_line = self._session.get(
                PurchaseInvoiceLine, line.source_document_line_id
            )
        if source_line is None:
            return None
        receipt_line = self._receipt_line_behind(source_line)
        if receipt_line is None:
            return None
        return (receipt_line.batch_number or "").strip() or None

    def _resolve_return_batch(self, line: PurchaseReturnLine) -> UUID | None:
        """Return the batch this line is sending back, if it names one.

        The number is typed off the carton being crated up for the supplier.
        Resolving it is what takes the goods out of that batch's stock row
        instead of the product's untracked one -- without it a batch could be
        received, sold from, and then returned against stock that was never in
        it, leaving the batch holding goods that have left the building.

        A line whose receipt line named a batch may send back only that one
        (D-BUY-64): a slip of the hand otherwise drains another delivery's
        batch, perhaps another supplier's goods.

        ``require_batch_on_issue`` is the product saying its goods cannot leave
        unidentified, and a return to the supplier is stock leaving. Dispatch
        already refuses to ship it untracked; a return that did not would be
        the same hole in the same guarantee, one document along.

        Returns:
            The batch id, or None where the line names no batch and the product
            does not require one -- which posts against the product exactly as
            it did before.

        """
        number = (line.batch_number or "").strip()
        brought = self._batch_brought_in(line)
        if number and brought and number != brought:
            # Any batch the product was ever received into used to be taken,
            # and its stock went back on another delivery's paper (D-BUY-64).
            raise ValidationError(
                f"Line {line.line_number}: the goods receipt brought these "
                f"goods in as batch {brought}, so batch {number} cannot go "
                f"back against it. Return batch {brought} on this line, or "
                f"raise the return off the receipt that brought {number}.",
                details={"field": "lines"},
            )
        if not number:
            product = self._session.get(Product, line.product_id)
            if product is not None and product.require_batch_on_issue:
                raise ValidationError(
                    f"{product.code} may only be issued from a batch, so the "
                    "batch number is required to return it."
                )
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

    def cancel_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
        """Cancel one purchase return."""
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status in {
            PurchaseReturnStatus.CANCELLED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            raise ValidationError("This purchase return can no longer be cancelled.")
        self._refuse_while_refunded(row, firm_scope=firm_scope, doing="cancelled")
        # Units sent back come onto the shelf again; a draft's picks go.
        self._serials.take_back(row, actor_id=actor_id)
        before = row.status
        reversed_lines, stock_value = self._reverse_inventory(
            row, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )
        # The goods are back on the shelf; the payable, the input tax and the
        # inventory credit have to come back off the books with them.
        self._reverse_posting(
            row, firm_scope=firm_scope, actor_id=actor_id, stock_value=stock_value
        )
        row.status = PurchaseReturnStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        # The payables debit is reversed, so the supplier credit it gave is
        # gone and any bill it was set against owes that part again
        # (D-FIN-19).
        from app.settlements.services.supplier_credits import (
            withdraw_credit_applications,
        )

        withdraw_credit_applications(
            self._session,
            firm_id=firm_scope,
            actor_id=actor_id,
            purchase_return_id=row.id,
        )
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
            action="purchase_return.cancelled",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "reason": reason,
                "reversed_inventory_lines": reversed_lines,
            },
        )
        if row.outcome == "REPLACEMENT":
            # The goods it sent back are no longer owed again.
            self._resync_replaced_orders(row, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def set_outcome(
        self,
        return_id: UUID,
        outcome: str,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseReturn:
        """Say what the return comes back as, at any point before cancelling.

        Backlog 69 row 7. The supplier often decides after the goods have
        gone, so this is not tied to the draft. A return the supplier has
        already paid money back against stays a refund; one turned into, or
        out of, a replacement moves the order it reopens.
        """
        if outcome not in {"CREDIT", "REPLACEMENT", "REFUND"}:
            raise ValidationError(
                "A return comes back as CREDIT, REPLACEMENT or REFUND."
            )
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == PurchaseReturnStatus.CANCELLED.value:
            raise ValidationError("A cancelled return comes back as nothing.")
        before = row.outcome or "CREDIT"
        if before == outcome:
            return row
        if before == "REFUND":
            self._refuse_while_refunded(
                row, firm_scope=firm_scope, doing="changed from a refund"
            )
        row.outcome = outcome
        row.updated_by = actor_id
        self._session.flush()
        if "REPLACEMENT" in (before, outcome) and row.status in {
            PurchaseReturnStatus.COMPLETED.value,
            PurchaseReturnStatus.CLOSED.value,
        }:
            self._resync_replaced_orders(row, firm_scope=firm_scope, actor_id=actor_id)
        record_audit(
            self._session,
            action="purchase_return.outcome_changed",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"outcome": before},
            after_data={"outcome": outcome},
        )
        self._session.commit()
        return row

    def _refuse_while_refunded(
        self, row: PurchaseReturn, *, firm_scope: UUID, doing: str
    ) -> None:
        """Refuse while the supplier's money against the return stands."""
        from app.settlements.services.supplier_credits import live_refunds

        standing = [
            refund
            for refund in live_refunds(
                self._session, firm_id=firm_scope, source_id=row.id
            )
            if refund.status == "POSTED"
        ]
        if standing:
            raise ValidationError(
                f"{row.return_number} cannot be {doing}: the supplier has paid "
                f"{sum((refund.amount for refund in standing), ZERO)} back against "
                "it. Reverse the refund first."
            )

    def _resync_replaced_orders(
        self, row: PurchaseReturn, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Walk each order a replacement return reopens to what it now owes."""
        from app.goods_receipt.models import GoodsReceiptLine
        from app.goods_receipt.services.goods_receipt_service import (
            GoodsReceiptService,
        )
        from app.purchase.models import PurchaseOrder, PurchaseOrderLine
        from app.purchase_invoice.models import PurchaseInvoiceLine

        po_lines: set[UUID] = set()
        receipt_lines: set[UUID] = set()
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == row.id,
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all():
            if (
                line.source_document_type
                == PurchaseReturnSourceType.PURCHASE_ORDER.value
            ):
                po_lines.add(line.source_document_line_id)
            elif (
                line.source_document_type
                == PurchaseReturnSourceType.GOODS_RECEIPT.value
            ):
                receipt_lines.add(line.source_document_line_id)
            elif (
                line.source_document_type
                == PurchaseReturnSourceType.PURCHASE_INVOICE.value
            ):
                bill_line = self._session.get(
                    PurchaseInvoiceLine, line.source_document_line_id
                )
                if bill_line is None:
                    continue
                if bill_line.source_document_type == "PURCHASE_ORDER":
                    po_lines.add(bill_line.source_document_line_id)
                elif bill_line.source_document_type == "GOODS_RECEIPT":
                    receipt_lines.add(bill_line.source_document_line_id)
        if receipt_lines:
            po_lines.update(
                self._session.scalars(
                    select(GoodsReceiptLine.purchase_order_line_id).where(
                        GoodsReceiptLine.id.in_(list(receipt_lines))
                    )
                ).all()
            )
        if not po_lines:
            return
        receipts = GoodsReceiptService(self._session)
        for order in self._session.scalars(
            select(PurchaseOrder)
            .join(
                PurchaseOrderLine,
                PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
            )
            .where(PurchaseOrderLine.id.in_(list(po_lines)))
            .distinct()
        ).all():
            receipts.resync_order_status(order, firm_id=firm_scope, actor_id=actor_id)

    def _reverse_inventory(
        self,
        document: PurchaseReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None,
    ) -> tuple[int, Decimal]:
        """Undo the stock this return moved out, if it had already completed.

        Completing a return takes goods off the shelf. Cancelling it afterwards
        must put them back, otherwise the firm loses stock it still holds.

        Reports what the movements actually put back as well as how many lines
        they covered, because the journal has to be taken off the books at that
        figure rather than at the one the return was priced at -- goods come
        back at the average the stock is carried at now.

        Args:
            document: The return being cancelled.
            firm_scope: The owning firm.
            actor_id: The user cancelling the return.
            reason: Optional cancellation reason, stored on the reversal.

        Returns:
            How many lines were reversed, and the value they put back.

        """
        reversed_lines = 0
        movement_ids: list[UUID] = []
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == document.id,
                PurchaseReturnLine.inventory_transaction_id.is_not(None),
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ).all():
            if line.inventory_transaction_id is None:
                continue
            movement = self._inventory.reverse_transaction(
                line.inventory_transaction_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason or f"Purchase return {document.return_number} cancelled.",
            )
            if movement is not None:
                movement_ids.append(movement.id)
            line.inventory_transaction_id = None
            line.updated_by = actor_id
            reversed_lines += 1
        return reversed_lines, self._movement_value(movement_ids)

    def _movement_value(self, movement_ids: list[UUID]) -> Decimal:
        """Return what the stock ledger says those movements were worth."""
        if not movement_ids:
            return ZERO
        total = self._session.scalar(
            select(func.coalesce(func.sum(StockLedgerEntry.total_cost), 0)).where(
                StockLedgerEntry.transaction_id.in_(movement_ids),
                StockLedgerEntry.is_deleted.is_(False),
            )
        )
        return Decimal(str(total or 0))

    def _reverse_posting(
        self,
        document: PurchaseReturn,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        stock_value: Decimal,
    ) -> None:
        """Take the completion's journal back off the books.

        Nothing did this until 2026-08-22. Completing a return debited payables
        for the supplier's credit note, reversed the input tax and credited
        inventory; cancelling put the goods back on the shelf and left every
        one of those postings standing, so the firm still showed the supplier
        owing it for goods it had kept. `goods_receipt` carried the same defect
        until 2026-08-18 -- this is its mirror, found by cancelling one on
        seeded data and watching the store go 199.07 out.

        `reversal_of_id IS NULL` matters for the same reason it does there:
        `reverse_entry` copies the source ids onto the mirror it posts, so
        without it a second pass would reverse the reversal.
        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "purchase_return",
                JournalEntry.source_id == document.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # A return cancelled before it completed posted nothing.
            return
        self._posting.reverse_purchase_return(
            firm_id=firm_scope,
            entry_id=entry_id,
            return_number=document.return_number,
            stock_value=stock_value,
            actor_id=actor_id,
        )

    def close_return(
        self,
        return_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> PurchaseReturn:
        """Close one completed purchase return.

        Closing says a return is finished with, so only a completed one -- whose
        goods went out and whose journal posted -- can be. It refused only one
        already closed, so a DRAFT return that moved nothing could be closed
        and then read as done (D-BUY-13, driven on TEST01 on 2026-09-18:
        PR-2026-2027-000004 closed from DRAFT).
        """
        row = self.get_return(return_id, firm_scope=firm_scope)
        if row.status == PurchaseReturnStatus.CLOSED.value:
            raise ValidationError("This purchase return is already closed.")
        if row.status != PurchaseReturnStatus.COMPLETED.value:
            raise ValidationError(
                f"Only completed purchase returns can be closed; "
                f"{row.return_number} is {row.status.lower()}."
            )
        before = row.status
        row.status = PurchaseReturnStatus.CLOSED.value
        row.close_reason = reason
        row.closed_at = utc_now()
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
            action="purchase_return.closed",
            entity_type="purchase_return",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_return(self, return_id: UUID, *, firm_scope: UUID) -> PurchaseReturn:
        """Return one purchase return."""
        row = self._session.scalar(
            select(PurchaseReturn).where(
                PurchaseReturn.id == return_id,
                PurchaseReturn.firm_id == firm_scope,
                PurchaseReturn.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase return not found.")
        return row

    def return_response(self, row: PurchaseReturn) -> PurchaseReturnResponse:
        """Render one purchase return row as its API contract."""
        return self.return_responses([row])[0]

    def return_responses(
        self, rows: Sequence[PurchaseReturn]
    ) -> list[PurchaseReturnResponse]:
        """Render a page of purchase returns, reading each child table once.

        One query per child table for the whole page, grouped by return in
        Python, rather than seven per return (backlog 56 C, step 3). The
        single-return builder is this with a list of one.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        sources = children_by_parent(
            self._session,
            PurchaseReturnSource,
            PurchaseReturnSource.purchase_return_id,
            ids,
        )
        lines = children_by_parent(
            self._session,
            PurchaseReturnLine,
            PurchaseReturnLine.purchase_return_id,
            ids,
            PurchaseReturnLine.line_number.asc(),
        )
        attachments = children_by_parent(
            self._session,
            PurchaseReturnAttachment,
            PurchaseReturnAttachment.purchase_return_id,
            ids,
        )
        notes = children_by_parent(
            self._session,
            PurchaseReturnNote,
            PurchaseReturnNote.purchase_return_id,
            ids,
        )
        accounting_events = children_by_parent(
            self._session,
            PurchaseReturnAccountingEvent,
            PurchaseReturnAccountingEvent.purchase_return_id,
            ids,
        )
        warnings = self._duplicate_warnings(rows)
        vendors = {
            found[0]: (found[1], found[2])
            for found in self._session.execute(
                select(Vendor.id, Vendor.display_name, Vendor.code).where(
                    Vendor.id.in_({row.vendor_id for row in rows})
                )
            )
        }
        # The units the page's lines name, and which products carry them,
        # each read once for the page (PG-10).
        every_line = [line for found in lines.values() for line in found]
        serials = self._serials.named(line.id for line in every_line)
        tracked = self._serials.tracked(line.product_id for line in every_line)
        return [
            self._return_response(
                row,
                lines=lines[row.id],
                sources=sources[row.id],
                attachments=attachments[row.id],
                notes=notes[row.id],
                accounting_events=accounting_events[row.id],
                warning=warnings.get(row.id),
                vendor=vendors.get(row.vendor_id),
                serials=serials,
                tracked=tracked,
            )
            for row in rows
        ]

    def _return_response(
        self,
        row: PurchaseReturn,
        *,
        lines: list[PurchaseReturnLine],
        sources: list[PurchaseReturnSource],
        attachments: list[PurchaseReturnAttachment],
        notes: list[PurchaseReturnNote],
        accounting_events: list[PurchaseReturnAccountingEvent],
        warning: str | None,
        vendor: tuple[str, str] | None,
        serials: dict[UUID, list[str]] | None = None,
        tracked: set[UUID] | None = None,
    ) -> PurchaseReturnResponse:
        """Build one return's response from what the page already read."""
        return PurchaseReturnResponse(
            id=row.id,
            version=row.version,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            vendor_name=vendor[0] if vendor else "",
            vendor_code=vendor[1] if vendor else "",
            branch_id=row.branch_id,
            warehouse_id=row.warehouse_id,
            business_profile_id=row.business_profile_id,
            return_number=row.return_number,
            return_date=row.return_date,
            supplier_return_number=row.supplier_return_number,
            supplier_return_date=row.supplier_return_date,
            reference_grn_number=row.reference_grn_number,
            reference_invoice_number=row.reference_invoice_number,
            return_reason=row.return_reason,
            outcome=row.outcome or "CREDIT",
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            status=PurchaseReturnStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_returned_quantity=row.total_already_returned_quantity,
            total_current_return_quantity=row.total_current_return_quantity,
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
            lines=[
                self._line_response(item).model_copy(
                    update={
                        "serial_tracked": item.product_id in (tracked or set()),
                        "serial_numbers": list((serials or {}).get(item.id, [])),
                    }
                )
                for item in lines
            ],
            sources=[self._source_response(item) for item in sources],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            accounting_events=[
                self._accounting_event_response(item) for item in accounting_events
            ],
            duplicate_warning=warning,
        )

    def timeline(
        self, *, return_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return the lifecycle timeline for one purchase return."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=return_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_returns(self, *, firm_scope: UUID) -> list[PurchaseReturn]:
        """List returns still in draft, not yet approved."""
        return list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status == PurchaseReturnStatus.DRAFT.value,
                )
            ).all()
        )

    def overdue_returns(self, *, firm_scope: UUID) -> list[PurchaseReturn]:
        """List live returns past their due date.

        Cancelled and closed returns are excluded: neither is still owing.
        """
        today = firm_today(self._session, firm_scope)
        return list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.due_date.is_not(None),
                    PurchaseReturn.due_date < today,
                    PurchaseReturn.status.not_in(
                        [
                            PurchaseReturnStatus.CANCELLED.value,
                            PurchaseReturnStatus.CLOSED.value,
                        ]
                    ),
                )
            ).all()
        )

    def register_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseReturnRegisterRecord]:
        """Return the register report for the visible firm scope.

        Each id carries its name, in one read per table for the whole report:
        the grid derives its columns from the row, so a register of ids alone
        read as UUIDs (D-RPT-17).
        """
        rows = window.fetch(
            self._session,
            select(PurchaseReturn)
            .where(
                PurchaseReturn.firm_id == firm_scope,
                PurchaseReturn.is_deleted.is_(False),
                *window.dated(PurchaseReturn.return_date),
            )
            .order_by(
                PurchaseReturn.return_date.desc(),
                PurchaseReturn.created_at.desc(),
                PurchaseReturn.id.desc(),
            ),
        )
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        branches = branch_names(self._session, (row.branch_id for row in rows))
        warehouses = warehouse_names(self._session, (row.warehouse_id for row in rows))
        records = [
            PurchaseReturnRegisterRecord(
                return_id=row.id,
                return_number=row.return_number,
                supplier_return_number=row.supplier_return_number,
                vendor_id=row.vendor_id,
                vendor_name=suppliers.get(row.vendor_id, str(row.vendor_id)),
                branch_id=row.branch_id,
                branch_name=branches.get(row.branch_id, str(row.branch_id)),
                warehouse_id=row.warehouse_id,
                warehouse_name=warehouses.get(row.warehouse_id, str(row.warehouse_id)),
                return_date=row.return_date,
                grand_total=row.grand_total,
                status=PurchaseReturnStatus(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def by_vendor_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseReturnByVendorRecord]:
        """Total returned value and count per vendor."""
        rows = list(
            self._session.scalars(
                select(PurchaseReturn).where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                    *window.dated(PurchaseReturn.return_date),
                )
            ).all()
        )
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for row in rows:
            totals[row.vendor_id] += row.grand_total
            counts[row.vendor_id] += 1
        vendor_names = {
            vendor.id: vendor.display_name
            for vendor in self._session.scalars(
                select(Vendor).where(Vendor.id.in_(list(totals.keys())))
            ).all()
        }
        return [
            PurchaseReturnByVendorRecord(
                vendor_id=vendor_id,
                vendor_name=vendor_names.get(vendor_id, str(vendor_id)),
                return_amount=self._q(amount),
                return_count=counts[vendor_id],
            )
            for vendor_id, amount in totals.items()
        ]

    def by_product_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseReturnByProductRecord]:
        """Total returned quantity and value per product.

        The report is per product, which is what its name says; it used to
        answer with the per-line reconciliation, which carries no product at
        all.
        """
        lines = self._report_lines(firm_scope=firm_scope, window=window)
        quantities: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        amounts: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for line, _ in lines:
            quantities[line.product_id] += (
                line.current_return_quantity + line.free_quantity
            )
            amounts[line.product_id] += line.net_amount
            counts[line.product_id] += 1
        products = {
            product.id: product
            for product in self._session.scalars(
                select(Product).where(Product.id.in_(list(quantities.keys())))
            ).all()
        }
        return [
            PurchaseReturnByProductRecord(
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
                return_amount=self._q(amounts[product_id]),
                return_count=counts[product_id],
            )
            for product_id, quantity in quantities.items()
        ]

    def _tax_by_component(self, return_id: UUID) -> dict[str, Decimal]:
        """See `return_tax_by_component`; the posting and GSTR-3B share it."""
        return return_tax_by_component(self._session, return_id)

    def _report_lines(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[tuple[PurchaseReturnLine, PurchaseReturn]]:
        """Every live return line in scope, with the return it belongs to.

        Cancelled returns are left out, the way the by-vendor totals always
        left them out. A cancelled return did not happen, and counting its
        lines overstated every line-level report against the header ones.
        """
        return [
            (line, header)
            for line, header in self._session.execute(
                select(PurchaseReturnLine, PurchaseReturn)
                .join(
                    PurchaseReturn,
                    PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
                )
                .where(
                    PurchaseReturn.firm_id == firm_scope,
                    PurchaseReturn.is_deleted.is_(False),
                    PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                    PurchaseReturnLine.is_deleted.is_(False),
                    *window.dated(PurchaseReturn.return_date),
                )
                .order_by(
                    PurchaseReturn.return_date.desc(),
                    PurchaseReturn.id.desc(),
                    PurchaseReturnLine.line_number,
                )
            ).all()
        ]

    def reconciliation_report(
        self,
        *,
        firm_scope: UUID,
        damaged_only: bool = False,
        expired_only: bool = False,
        window: ReportWindow = WHOLE_HISTORY,
    ) -> list[PurchaseReturnReconciliationRecord]:
        """Return lines set against the receipts they came from.

        ``damaged_only`` and ``expired_only`` are what the damaged and expired
        reports are: the line records the condition on ``is_damaged`` and
        ``is_expired``, and both reports used to filter on a quantity instead,
        so they answered "anything returned" and "nearly everything".
        """
        lines = self._report_lines(firm_scope=firm_scope, window=window)
        product_names = {
            product.id: product.name
            for product in self._session.scalars(
                select(Product).where(
                    Product.id.in_([line.product_id for line, _ in lines])
                )
            ).all()
        }
        result: list[PurchaseReturnReconciliationRecord] = []
        for row, header in lines:
            if damaged_only and not row.is_damaged:
                continue
            if expired_only and not row.is_expired:
                continue
            # The line stores its bought units; the free ones went back beside
            # them and are counted, as the by-product report counts them. A
            # free-only return read as nothing returned (D-BUY-63).
            returning = self._q(row.current_return_quantity + row.free_quantity)
            # ``already_returned_quantity`` is what had gone back when the
            # line was saved, by the receipt or by a bill for it -- the count
            # the save's own cap used (D-BUY-66) -- so pending is what could
            # still go back once this return had.
            pending = self._q(
                row.received_quantity - row.already_returned_quantity - returning
            )
            result.append(
                PurchaseReturnReconciliationRecord(
                    return_id=header.id,
                    return_number=header.return_number,
                    return_date=header.return_date,
                    source_document_type=PurchaseReturnSourceType(
                        row.source_document_type
                    ),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    product_id=row.product_id,
                    product_name=product_names.get(row.product_id, str(row.product_id)),
                    received_quantity=row.received_quantity,
                    already_returned_quantity=row.already_returned_quantity,
                    current_return_quantity=returning,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                    reason_code=row.reason_code,
                    is_damaged=row.is_damaged,
                    is_expired=row.is_expired,
                )
            )
        return result

    def export_returns_csv(self, *, firm_scope: UUID, search: str | None = None) -> str:
        """Export matching purchase returns as CSV."""
        rows, _ = self.list_returns(
            firm_scope=firm_scope,
            filters=PurchaseReturnListFilters(),
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
                "supplier_return_number",
                "return_date",
                "vendor_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.return_number,
                    row.supplier_return_number,
                    row.return_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_returns(
        self, data: PurchaseReturnImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseReturn]:
        """Import a batch of purchase returns, all of them or none.

        Each record is staged with the checks a single save applies -- a line
        that returns nothing, the caps, the batch -- and the file is committed
        once. It used to loop over the committing ``create_return``, so a file
        refused at its second record left the first behind as a draft, and
        importing the corrected file wrote it twice (D-BUY-62).

        Raises:
            ApplicationError: The refusal of the first record that fails, in
                the words a single save uses, naming the record. Nothing of
                the file is kept.

        """
        rows: list[PurchaseReturn] = []
        for number, record in enumerate(data.records, start=1):
            try:
                self._refuse_empty_return_lines(record)
                row = self.stage_return(record, firm_id=firm_scope, actor_id=actor_id)
                self._refuse_unresolved_batches(row)
            except ApplicationError as error:
                self._session.rollback()
                error.message = (
                    f"Record {number} of {len(data.records)}: {error.message} "
                    "Nothing was imported."
                )
                error.args = (error.message,)
                raise
            except Exception:
                self._session.rollback()
                raise
            rows.append(row)
        self._session.commit()
        return rows

    def _replace_sources(
        self,
        row: PurchaseReturn,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnSource).filter(
            PurchaseReturnSource.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = PurchaseReturnSource(
                purchase_return_id=row.id,
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

    @stamps_tax_rules(PurchaseReturnLine, "purchase_return_id")
    def _replace_lines(
        self,
        row: PurchaseReturn,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        return_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(PurchaseReturnLine).filter(
            PurchaseReturnLine.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            source_line: SourceLine | None
            # A line must be one of its own source's lines (D-BUY-17).
            if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
                source_line = posted_receipt_line(
                    self._session,
                    firm_id=firm_id,
                    receipt_id=_required_uuid(spec["source_document_id"]),
                    line_id=_required_uuid(spec["source_document_line_id"]),
                    verb="returned",
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
                source_line = self._billed_invoice_line(
                    firm_id=firm_id,
                    invoice_id=_required_uuid(spec["source_document_id"]),
                    line_id=_required_uuid(spec["source_document_line_id"]),
                )
            else:
                source_line = self._session.scalar(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.id == spec["source_document_line_id"]
                    )
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            if getattr(source_line, "is_capital_goods", False):
                # Capital goods never entered stock (PG-13), so a return has
                # no movement to take out and would send the shelf negative.
                raise ValidationError(
                    f"Line {index} is capital goods: it was received as a "
                    "fixed asset and never entered stock, so it cannot go "
                    "back as a purchase return. Claim its value with a debit "
                    "note against the supplier's bill and dispose of the "
                    "asset under Fixed Assets.",
                    details={"field": "lines"},
                )
            requested_quantity = self._q(Decimal(str(spec["current_return_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            return_uom_id = spec.get("return_uom_id")
            assert_quantity_fits_unit(
                self._session,
                quantity=requested_quantity,
                uom_id=return_uom_id or source_uom_id,
                product_id=self._product_id(source_line),
                firm_id=firm_id,
            )
            conversion_factor = self._q(
                Decimal(str(spec.get("conversion_factor", Decimal("1"))))
            )
            return_quantity = requested_quantity
            if (
                source_uom_id is not None
                and return_uom_id is not None
                and return_uom_id != source_uom_id
            ):
                # In the source line's unit, which is what the caps below
                # count in and what the stock leaves in: by the rule for
                # the pair, else through the product's stock unit, so 12
                # PIECE go back off a receipt of 2 BOX as 1 BOX.
                converted, factor = self._uom.quantity_between(
                    product_id=self._product_id(source_line),
                    from_uom_id=_required_uuid(return_uom_id),
                    to_uom_id=source_uom_id,
                    quantity=requested_quantity,
                    on_date=return_date,
                    firm_scope=firm_id,
                )
                return_quantity = self._q(converted)
                conversion_factor = self._q(factor)
            converted_quantity = return_quantity
            # Request sessions do not autoflush, and an earlier line of this
            # same return may be sending back the same goods.
            self._session.flush()
            already_returned, already_free = self._already_returned(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
            )
            charged_left = self._q(source_quantity - already_returned)
            source_free = self._source_free_quantity(source_type, source_line)
            # A bill line and the receipt line it billed are the same goods:
            # what went back by either route counts against what came in
            # (D-BUY-61).
            came_in, goods_back = self._goods_position(
                firm_id=firm_id, source_line=source_line
            )
            by_another_route = ZERO
            if came_in is not None:
                by_another_route = max(self._q(goods_back - already_returned), ZERO)
                charged_left = min(charged_left, self._q(came_in - goods_back))
            # What the line records as gone back before it is what the cap
            # counted, by either document, so the line and the reconciliation
            # read "pending" as what can still go back (D-BUY-66). Counting
            # only the returns naming this source line left 10 pending on a
            # receipt line whose 10 had gone back off its bill.
            already_bought = self._q(source_quantity - charged_left)
            # No request can lift this cap: a body flag the caller set was all
            # it took to send back more than was received (D-SELL-29).
            return_quantity, free_quantity = self._split_free_goods(
                index,
                total=return_quantity,
                typed_free=self._typed_free(spec, requested_quantity, return_quantity),
                charged_left=charged_left,
                free_left=self._q(source_free - already_free),
                off_a_receipt=(
                    source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value
                ),
                by_another_route=by_another_route,
            )
            unit_price = self._unit_price(spec, source_line)
            if spec.get("unit_price") is not None:
                # Typed for the unit the line was typed in; restated for the
                # source line's unit the quantity is stored in. Before the
                # free goods are split off: both quantities are the whole
                # line here.
                unit_price = self._q(
                    price_per_source_unit(
                        unit_price,
                        typed_quantity=requested_quantity,
                        source_quantity=converted_quantity,
                    )
                )
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            gross_amount = self._q(return_quantity * unit_price)
            line_discount = self._line_discount(
                spec=spec, source_line=source_line, gross=gross_amount
            )
            discount_amount = line_discount.amount
            # The source line's share of the order's whole-order discount, for
            # the part of it returned here, comes off before tax (D-BUY-19).
            bill_share = min(
                inherited_share(
                    getattr(source_line, "bill_discount_amount", ZERO) or ZERO,
                    part=return_quantity,
                    whole=source_quantity,
                ),
                self._q(gross_amount - discount_amount),
            )
            tax_amount = self._tax_amount(
                document_id=row.id,
                line_number=index,
                return_date=return_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                product_id=self._product_id(source_line),
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                invoice_value=self._line_net_amount(
                    quantity=return_quantity,
                    unit_price=unit_price,
                    discount_amount=discount_amount + bill_share,
                    charges_amount=charges_amount,
                ),
                actor_id=actor_id,
            )
            net_amount = self._q(
                gross_amount
                - discount_amount
                - bill_share
                + charges_amount
                + tax_amount
            )
            line = PurchaseReturnLine(
                purchase_return_id=row.id,
                firm_id=firm_id,
                line_number=index,
                source_document_type=source_type,
                source_document_id=spec["source_document_id"],
                source_document_number=self._source_document_number(spec, source_line),
                source_document_line_id=source_line.id,
                source_document_line_number=self._source_line_number(source_line),
                product_id=self._product_id(source_line),
                description=self._source_description(source_line),
                # Everything the source line brought in and everything that
                # has gone back, free goods included, like the quantity this
                # line reads beside them (D-BUY-63) -- and by whichever
                # document it went (D-BUY-66).
                received_quantity=self._q(source_quantity + source_free),
                already_returned_quantity=self._q(already_bought + already_free),
                current_return_quantity=return_quantity,
                free_quantity=free_quantity,
                rejected_quantity=self._q(
                    Decimal(str(spec.get("rejected_quantity", ZERO)))
                ),
                reason_code=spec.get("reason_code"),
                item_condition=spec.get("item_condition"),
                replacement_required=bool(spec.get("replacement_required", False)),
                refund_required=bool(spec.get("refund_required", False)),
                is_scrap=bool(spec.get("is_scrap", False)),
                is_damaged=bool(spec.get("is_damaged", False)),
                is_expired=bool(spec.get("is_expired", False)),
                unit_price=unit_price,
                discount_percent=line_discount.percent,
                discount_amount=discount_amount,
                bill_discount_amount=bill_share,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                # The unit the quantities above are in: the source line's.
                # It was whatever the request sent, so a return naming no
                # unit against a line received by the box stored none, and
                # 1 BOX left the shelf as one piece.
                purchase_uom_id=source_uom_id or spec.get("purchase_uom_id"),
                return_uom_id=spec.get("return_uom_id"),
                conversion_factor=conversion_factor,
                conversion_version=spec.get("conversion_version"),
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                storage_node_id=spec.get("storage_node_id"),
                batch_number=self._line_batch_number(spec, source_line),
                expiry_date=spec.get("expiry_date"),
                manufacturing_date=spec.get("manufacturing_date"),
                remarks=spec.get("remarks"),
                accounting_event_reference=f"{row.return_number}:{index}",
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(line)
            totals["total_source_quantity"] += source_quantity + source_free
            totals["total_already_returned_quantity"] += already_bought + already_free
            totals["total_current_return_quantity"] += return_quantity + free_quantity
            totals["line_discount_total"] += discount_amount
            # subtotal is the taxable base: gross less discount, before tax and
            # before charges. Line charges used to be folded in here, which made
            # this module's subtotal mean something different from every other
            # document's; they are carried separately and added to grand_total.
            totals["subtotal"] += self._q(gross_amount - discount_amount - bill_share)
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: PurchaseReturn,
        attachments: list[PurchaseReturnAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnAttachment).filter(
            PurchaseReturnAttachment.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                PurchaseReturnAttachment(
                    purchase_return_id=row.id,
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
        row: PurchaseReturn,
        notes: list[PurchaseReturnNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseReturnNote).filter(
            PurchaseReturnNote.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                PurchaseReturnNote(
                    purchase_return_id=row.id,
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
        self, row: PurchaseReturn, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(PurchaseReturnAccountingEvent).filter(
            PurchaseReturnAccountingEvent.purchase_return_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (
                PurchaseReturnAccountingEventType.PURCHASE_RETURN.value,
                "Purchase Return",
                "CREDIT",
                row.subtotal,
            ),
            (
                PurchaseReturnAccountingEventType.INPUT_TAX_REVERSAL.value,
                "Input Tax Reversal",
                "CREDIT",
                row.tax_total,
            ),
            (
                PurchaseReturnAccountingEventType.VENDOR_RECEIVABLE.value,
                "Vendor Receivable",
                "DEBIT",
                row.grand_total,
            ),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                PurchaseReturnAccountingEvent(
                    purchase_return_id=row.id,
                    firm_id=firm_id,
                    event_type=event_type,
                    account_name=account_name,
                    direction=direction,
                    amount=self._q(amount),
                    narration=f"Placeholder accounting event for {row.return_number}",
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )

    def _prepare_return_sources(
        self, data: PurchaseReturnCreate, firm_id: UUID
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
        # No request can skip the receipt (D-BUY-14): a body flag the caller
        # set was all it took to send back four units against a purchase
        # order nothing had arrived on -- the shelf went to -4 and the
        # supplier was debited 472. Only goods that came in can go back, which
        # is the rule `require_posted_receipt` already holds a receipt to.
        if any(
            self._source_type(item["source_document_type"])
            == PurchaseReturnSourceType.PURCHASE_ORDER.value
            for item in (*sources, *lines)
        ):
            raise ValidationError(
                "A purchase return is raised against the goods receipt or the "
                "supplier bill, never straight against the purchase order: "
                "goods that were never received cannot be sent back."
            )
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
            if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
                receipt = self._session.scalar(
                    select(GoodsReceipt).where(
                        GoodsReceipt.id == source_id,
                        GoodsReceipt.firm_id == firm_id,
                        GoodsReceipt.is_deleted.is_(False),
                    )
                )
                if receipt is None:
                    raise ResourceNotFoundError("Goods receipt not found.")
                require_posted_receipt(receipt, "returned")
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": receipt.id,
                        "source_document_number": receipt.grn_number,
                        "source_document_date": receipt.receipt_date,
                        "vendor_id": receipt.vendor_id,
                        "branch_id": receipt.branch_id,
                    }
                )
            elif source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
                invoice = self._session.scalar(
                    select(PurchaseInvoice).where(
                        PurchaseInvoice.id == source_id,
                        PurchaseInvoice.firm_id == firm_id,
                        PurchaseInvoice.is_deleted.is_(False),
                    )
                )
                if invoice is None:
                    raise ResourceNotFoundError("Purchase invoice not found.")
                self._refuse_unreturnable_invoice(invoice)
                source_rows.append(
                    {
                        "source_document_type": source_type,
                        "source_document_id": invoice.id,
                        "source_document_number": invoice.invoice_number,
                        "source_document_date": invoice.invoice_date,
                        "vendor_id": invoice.vendor_id,
                        "branch_id": invoice.branch_id,
                    }
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        for field in ("vendor_id", "branch_id"):
            value = _optional_uuid(first.get(field))
            if value is not None:
                header[field] = value
        for source in source_rows[1:]:
            if (
                source["vendor_id"] != header["vendor_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same vendor and branch."
                )
        self._validate_line_sources(
            lines,
            {
                source_id
                for row in source_rows
                if (source_id := _optional_uuid(row["source_document_id"])) is not None
            },
        )
        return header, source_rows, lines

    @staticmethod
    def _refuse_unreturnable_invoice(invoice: PurchaseInvoice) -> None:
        """Refuse a supplier bill that does not stand.

        Only an APPROVED bill -- or a CLOSED one, closing meaning nothing more
        to pay rather than never bought -- has raised a payable a return can
        take back. A draft or cancelled bill was accepted as a return's source
        (D-BUY-17, the purchasing twin of D-SELL-6).
        """
        if invoice.status not in _RETURNABLE_INVOICE_STATES:
            raise ValidationError(
                f"{invoice.invoice_number} is {invoice.status.lower()}, so "
                "nothing can be returned against it: only goods on an approved "
                "supplier bill can go back against the bill."
            )

    def _billed_invoice_line(
        self, *, firm_id: UUID, invoice_id: UUID, line_id: UUID
    ) -> PurchaseInvoiceLine:
        """Return the bill line a return names, and only if it is the bill's."""
        invoice = self._session.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.id == invoice_id,
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
            )
        )
        if invoice is None:
            raise ResourceNotFoundError("Purchase invoice not found.")
        self._refuse_unreturnable_invoice(invoice)
        line = self._session.scalar(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.id == line_id,
                PurchaseInvoiceLine.purchase_invoice_id == invoice.id,
                PurchaseInvoiceLine.firm_id == firm_id,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
        )
        if line is None:
            raise ValidationError(
                f"{invoice.invoice_number} has no line {line_id}, so it cannot "
                "be returned against it: a line is returned against the "
                "supplier bill it belongs to."
            )
        return line

    def _refuse_foreign_lines(self, row: PurchaseReturn, *, firm_id: UUID) -> None:
        """Refuse a saved return whose line names another document's line."""
        for line in self._session.scalars(
            select(PurchaseReturnLine).where(
                PurchaseReturnLine.purchase_return_id == row.id,
                PurchaseReturnLine.is_deleted.is_(False),
            )
        ):
            if line.source_document_type == (
                PurchaseReturnSourceType.GOODS_RECEIPT.value
            ):
                posted_receipt_line(
                    self._session,
                    firm_id=firm_id,
                    receipt_id=line.source_document_id,
                    line_id=line.source_document_line_id,
                    verb="returned",
                )
            elif line.source_document_type == (
                PurchaseReturnSourceType.PURCHASE_INVOICE.value
            ):
                self._billed_invoice_line(
                    firm_id=firm_id,
                    invoice_id=line.source_document_id,
                    line_id=line.source_document_line_id,
                )

    def _validate_line_sources(
        self, lines: list[dict[str, object]], source_ids: set[UUID]
    ) -> None:
        for line in lines:
            if line["source_document_id"] not in source_ids:
                raise ValidationError(
                    "Every return line must reference a selected source document."
                )

    def _delete_children(self, return_id: UUID) -> None:
        self._session.query(PurchaseReturnAccountingEvent).filter(
            PurchaseReturnAccountingEvent.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnLine).filter(
            PurchaseReturnLine.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnSource).filter(
            PurchaseReturnSource.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnAttachment).filter(
            PurchaseReturnAttachment.purchase_return_id == return_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseReturnNote).filter(
            PurchaseReturnNote.purchase_return_id == return_id
        ).delete(synchronize_session=False)

    def _tax_amount(
        self,
        *,
        return_date: date,
        firm_id: UUID,
        actor_id: UUID,
        business_profile_id: UUID | None,
        vendor_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID | None,
        product_id: UUID,
        tax_profile_id: UUID | None,
        invoice_value: Decimal,
        document_id: UUID | None = None,
        line_number: int | None = None,
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
        request = TaxRuleSimulationRequest(
            # The supply's own nature, not just the document's name: goods
            # going back to a supplier in another state carry IGST (D-CMP-14).
            transaction_type=self._tax.inward_transaction_type(
                "PURCHASE_RETURN",
                firm_id=firm_id,
                branch_id=branch_id,
                vendor_id=vendor_id,
            ),
            transaction_date=return_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            vendor_id=vendor_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={
                "source": "purchase_return",
                "document_type": "PURCHASE_RETURN",
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

    def _source_quantity(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> Decimal:
        source_type = self._source_type(spec["source_document_type"])
        if source_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            return self._q(getattr(source_line, "accepted_quantity", ZERO))
        if source_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
            return self._q(getattr(source_line, "current_invoice_quantity", ZERO))
        return self._q(getattr(source_line, "ordered_quantity", ZERO))

    def _already_returned(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> tuple[Decimal, Decimal]:
        """Return what live returns already took off a source line.

        Returns:
            The charged units and the free units, in that order.

        """
        charged, free = self._session.execute(
            select(
                func.coalesce(
                    func.sum(PurchaseReturnLine.current_return_quantity), ZERO
                ),
                func.coalesce(func.sum(PurchaseReturnLine.free_quantity), ZERO),
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                PurchaseReturnLine.is_deleted.is_(False),
                PurchaseReturnLine.source_document_line_id == source_document_line_id,
            )
        ).one()
        return self._q(charged or ZERO), self._q(free or ZERO)

    def _receipt_line_behind(self, source_line: SourceLine) -> GoodsReceiptLine | None:
        """Return the receipt line whose goods a return line sends back.

        The receipt line itself, or the one a bill line billed. A bill line
        raised straight off an order (no longer possible, D-BUY-14) and an
        order line have no single receipt line behind them.
        """
        if isinstance(source_line, GoodsReceiptLine):
            return source_line
        if (
            isinstance(source_line, PurchaseInvoiceLine)
            and source_line.source_document_type
            == PurchaseReturnSourceType.GOODS_RECEIPT.value
            and source_line.source_document_line_id is not None
        ):
            return self._session.get(
                GoodsReceiptLine, source_line.source_document_line_id
            )
        return None

    def _goods_position(
        self, *, firm_id: UUID, source_line: SourceLine
    ) -> tuple[Decimal | None, Decimal]:
        """Return what came in of a line's goods and what has gone back.

        A bill line and the receipt line it billed are the same goods, and
        `_already_returned` counts one source line, so 6 received and billed
        went back as 6 off the bill and 6 more off the receipt, the supplier
        debited twice (D-BUY-61, the buying twin of D-SELL-7). The goods are
        the receipt line's: what came in on it, less every live return that
        names it or a bill line billing it, drafts included. A cancelled
        return stops counting.

        A bill raised straight off an order line -- a path closed since
        D-BUY-14, but such bills exist -- has every posted receipt line of
        that order line behind it, and they are counted together. Where such
        a bill has been returned against, the receipt lines of its order line
        are held to the same total.

        Returns:
            The bought units that came in, or None where nothing received
            stands behind the line, and the bought units already sent back.

        """
        receipt_line = self._receipt_line_behind(source_line)
        order_line_id: UUID | None = None
        if receipt_line is not None:
            order_line_id = receipt_line.purchase_order_line_id
        elif (
            isinstance(source_line, PurchaseInvoiceLine)
            and source_line.source_document_type
            == PurchaseReturnSourceType.PURCHASE_ORDER.value
        ):
            order_line_id = source_line.source_document_line_id
        if order_line_id is None:
            return None, ZERO
        came_in: Decimal | None = None
        back = ZERO
        if receipt_line is not None:
            came_in = self._q(receipt_line.accepted_quantity)
            back = self._goods_returned(
                firm_id=firm_id, receipt_line_ids=[receipt_line.id]
            )
        via_order = self._goods_returned(
            firm_id=firm_id, receipt_line_ids=[], order_line_id=order_line_id
        )
        if came_in is not None and via_order <= ZERO:
            return came_in, back
        received = self._session.execute(
            select(GoodsReceiptLine.id, GoodsReceiptLine.accepted_quantity)
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(
                GoodsReceiptLine.firm_id == firm_id,
                GoodsReceiptLine.purchase_order_line_id == order_line_id,
                GoodsReceiptLine.is_deleted.is_(False),
                GoodsReceipt.is_deleted.is_(False),
                GoodsReceipt.status.in_(POSTED_STATES),
            )
        ).all()
        order_in = self._q(sum((Decimal(str(row[1])) for row in received), ZERO))
        order_back = self._q(
            via_order
            + self._goods_returned(
                firm_id=firm_id, receipt_line_ids=[row[0] for row in received]
            )
        )
        if came_in is None:
            return order_in, order_back
        # Whichever of the two leaves less: the receipt line's own goods, or
        # the order line's once a bill straight off it has been returned.
        if order_in - order_back < came_in - back:
            return order_in, order_back
        return came_in, back

    def _goods_returned(
        self,
        *,
        firm_id: UUID,
        receipt_line_ids: Sequence[UUID],
        order_line_id: UUID | None = None,
    ) -> Decimal:
        """Sum the bought units live returns took of some receipt lines' goods.

        Counted whichever document the return names: the receipt line, or a
        bill line billing it. With ``order_line_id``, the returns naming a
        bill line raised straight off that order line instead.
        """
        bill_lines = select(PurchaseInvoiceLine.id).where(
            PurchaseInvoiceLine.firm_id == firm_id
        )
        off_a_bill = (
            PurchaseReturnLine.source_document_type
            == PurchaseReturnSourceType.PURCHASE_INVOICE.value
        )
        if order_line_id is not None:
            routes = and_(
                off_a_bill,
                PurchaseReturnLine.source_document_line_id.in_(
                    bill_lines.where(
                        PurchaseInvoiceLine.source_document_type
                        == PurchaseReturnSourceType.PURCHASE_ORDER.value,
                        PurchaseInvoiceLine.source_document_line_id == order_line_id,
                    )
                ),
            )
        elif not receipt_line_ids:
            return ZERO
        else:
            routes = or_(
                and_(
                    PurchaseReturnLine.source_document_type
                    == PurchaseReturnSourceType.GOODS_RECEIPT.value,
                    PurchaseReturnLine.source_document_line_id.in_(receipt_line_ids),
                ),
                and_(
                    off_a_bill,
                    PurchaseReturnLine.source_document_line_id.in_(
                        bill_lines.where(
                            PurchaseInvoiceLine.source_document_type
                            == PurchaseReturnSourceType.GOODS_RECEIPT.value,
                            PurchaseInvoiceLine.source_document_line_id.in_(
                                receipt_line_ids
                            ),
                        )
                    ),
                ),
            )
        returned = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(PurchaseReturnLine.current_return_quantity), ZERO
                )
            )
            .join(
                PurchaseReturn,
                PurchaseReturn.id == PurchaseReturnLine.purchase_return_id,
            )
            .where(
                PurchaseReturn.firm_id == firm_id,
                PurchaseReturn.is_deleted.is_(False),
                PurchaseReturn.status != PurchaseReturnStatus.CANCELLED.value,
                PurchaseReturnLine.is_deleted.is_(False),
                routes,
            )
        )
        return self._q(Decimal(str(returned or ZERO)))

    def _source_free_quantity(
        self, source_type: str, source_line: SourceLine
    ) -> Decimal:
        """Return the free goods a source line brought in (D-BUY-56).

        Free goods are the goods receipt's: it is the document that says how
        many arrived, and a bill names them only by naming its receipt line.
        So they go back off the receipt line, and a line raised off a bill
        or an order has none to send.
        """
        if source_type != PurchaseReturnSourceType.GOODS_RECEIPT.value:
            return ZERO
        return self._q(getattr(source_line, "free_quantity", ZERO) or ZERO)

    def _typed_free(
        self, spec: dict[str, object], requested: Decimal, converted: Decimal
    ) -> Decimal | None:
        """Return the free quantity the line typed, in the source line's unit."""
        typed = spec.get("free_quantity")
        if typed is None:
            return None
        free = self._q(Decimal(str(typed)))
        if requested > ZERO and converted != requested:
            # Typed in the return's unit, like the quantity it is part of.
            free = self._q(free * converted / requested)
        return free

    def _split_free_goods(
        self,
        line_number: int,
        *,
        total: Decimal,
        typed_free: Decimal | None,
        charged_left: Decimal,
        free_left: Decimal,
        off_a_receipt: bool,
        by_another_route: Decimal = ZERO,
    ) -> tuple[Decimal, Decimal]:
        """Split what a line sends back into charged units and free ones.

        What was received can go back, free goods included (D-BUY-56). The
        charged units are taken first, and only what goes back beyond them is
        free, unless the line says how many are free -- a damaged free carton
        returned on its own. The charged part is what is priced and credited;
        the free part is credited nothing.

        ``by_another_route`` is what has already gone back of the same goods
        against the other document -- the bill for a receipt line, the receipt
        for a bill line -- and is only said in the refusal (D-BUY-61).

        Returns:
            The charged quantity and the free quantity.

        Raises:
            ValidationError: If the line sends back more charged units, or
                more free ones, than the source line has left.

        """
        charged_left = max(charged_left, ZERO)
        free_left = max(free_left, ZERO)
        if typed_free is None:
            charged = min(total, charged_left)
            free = self._q(total - charged)
        else:
            if typed_free > total:
                raise ValidationError(
                    f"Line {line_number}: the free quantity is part of the "
                    "return quantity and cannot exceed it."
                )
            free = typed_free
            charged = self._q(total - free)
        if charged > charged_left or free > free_left:
            left = (
                f"{charged_left.normalize():f} bought and "
                f"{free_left.normalize():f} free"
                if off_a_receipt
                else f"{charged_left.normalize():f}; free goods go back off the "
                "goods receipt that brought them in"
            )
            elsewhere = ""
            if by_another_route > ZERO:
                against = (
                    "the supplier bill for them"
                    if off_a_receipt
                    else "the goods receipt that brought them in, or another "
                    "bill for it"
                )
                elsewhere = (
                    f" {by_another_route.normalize():f} of these goods have "
                    f"already gone back against {against}."
                )
            raise ValidationError(
                "Return quantity exceeds the available source quantity: "
                f"line {line_number} can still send back {left}.{elsewhere}"
            )
        return charged, free

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _counted_in(self, line: PurchaseReturnLine) -> UUID | None:
        """Return the unit a stored return line's quantity is counted in.

        The source line's unit, always: a quantity typed in another unit
        (``return_uom_id``) is converted into it before it is stored, so
        moving the stock in the typed unit took 1 piece off the shelf for 12
        PIECE sent back as 1 BOX. The line stores it as ``purchase_uom_id``;
        a line saved before it did is answered from its source line, so a
        draft from then still completes at the right quantity.
        """
        if line.purchase_uom_id is not None:
            return line.purchase_uom_id
        source: SourceLine | None
        if line.source_document_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            source = self._session.get(GoodsReceiptLine, line.source_document_line_id)
        elif line.source_document_type == (
            PurchaseReturnSourceType.PURCHASE_INVOICE.value
        ):
            source = self._session.get(
                PurchaseInvoiceLine, line.source_document_line_id
            )
        else:
            source = self._session.get(PurchaseOrderLine, line.source_document_line_id)
        return None if source is None else self._source_uom_id(source)

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: SourceLine) -> UUID | None:
        return (
            getattr(source_line, "purchase_uom_id", None)
            or getattr(source_line, "invoice_uom_id", None)
            or getattr(source_line, "inventory_uom_id", None)
        )

    def _source_line_number(self, source_line: SourceLine) -> int:
        return int(source_line.line_number)

    def _source_description(self, source_line: SourceLine) -> str | None:
        return getattr(source_line, "description", None)

    def _source_document_number(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> str:
        source_number = spec.get("source_document_number")
        if source_number:
            return str(source_number)
        # Narrowed on the line's own class rather than on the parallel
        # ``source_document_type`` string, which can disagree with it.
        if isinstance(source_line, GoodsReceiptLine):
            receipt = self._session.scalar(
                select(GoodsReceipt).where(
                    GoodsReceipt.id == source_line.goods_receipt_id
                )
            )
            if receipt is not None:
                return receipt.grn_number
            return str(source_number or "")
        if isinstance(source_line, PurchaseInvoiceLine):
            invoice = self._session.scalar(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.id == source_line.purchase_invoice_id
                )
            )
            if invoice is not None:
                return invoice.invoice_number
            return str(source_number or "")
        order = self._session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == source_line.purchase_order_id
            )
        )
        if order is not None:
            return order.po_number
        return str(source_number or "")

    def _product_id(self, source_line: SourceLine) -> UUID:
        return source_line.product_id

    def _unit_price(self, spec: dict[str, object], source_line: object) -> Decimal:
        """Return the price one return line is valued at.

        What the line says wins; where it says nothing, the source line's price
        carries over, the same as its discount rate. It used to default to
        zero, so a return sent without a price -- every one the seeder raised,
        and the test fixture's -- took its stock out at nothing: the value went
        to the write-off account and the supplier was debited 0 (D-BUY-3).
        """
        stated = spec.get("unit_price")
        if stated is None:
            stated = getattr(source_line, "unit_price", None) or ZERO
        return self._q(Decimal(str(stated)))

    def _line_discount(
        self,
        *,
        spec: dict[str, object],
        source_line: object,
        gross: Decimal,
    ) -> LineDiscount:
        """Return the discount for one line.

        What the line itself says wins; where it says nothing, the **rate** on
        the source line carries over. A rate is inherited and an absolute
        amount is not, because a rate does not care about quantity: this
        document may cover part of the source line, and copying a whole-line
        amount onto a part of it would discount more than was ever agreed.

        The percentage was stored and never applied before this: the tax base
        and the subtotal were both computed from the amount alone, so a line
        carrying `10` was billed at full price.
        """
        percent = spec.get("discount_percent")
        amount = spec.get("discount_amount")
        if percent is None and amount is None:
            percent = getattr(source_line, "discount_percent", None) or None
        return resolve_line_discount(
            gross=gross,
            percent=None if percent is None else Decimal(str(percent)),
            amount=None if amount is None else Decimal(str(amount)),
        )

    def _line_net_amount(
        self,
        *,
        quantity: Decimal,
        unit_price: Decimal,
        discount_amount: Decimal,
        charges_amount: Decimal,
    ) -> Decimal:
        return self._q(quantity * unit_price - discount_amount + charges_amount)

    def _validate_supplier_return_number(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_return_number: str | None,
        current_id: UUID | None = None,
    ) -> None:
        if not supplier_return_number:
            return
        if self._duplicate_warning(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_return_number=supplier_return_number,
            current_id=current_id,
        ):
            return

    def _duplicate_warnings(self, rows: Sequence[PurchaseReturn]) -> dict[UUID, str]:
        """Answer `_duplicate_warning` for a page of returns in one query."""
        numbered = [row for row in rows if row.supplier_return_number]
        if not numbered:
            return {}
        holders: dict[tuple[object, ...], set[UUID]] = defaultdict(set)
        for found in self._session.execute(
            select(
                PurchaseReturn.id,
                PurchaseReturn.firm_id,
                PurchaseReturn.vendor_id,
                PurchaseReturn.supplier_return_number,
            ).where(
                PurchaseReturn.firm_id.in_({row.firm_id for row in numbered}),
                PurchaseReturn.supplier_return_number.in_(
                    {row.supplier_return_number for row in numbered}
                ),
                PurchaseReturn.is_deleted.is_(False),
            )
        ):
            holders[tuple(found[1:])].add(found[0])
        return {
            row.id: "A purchase return with this supplier return number already exists."
            for row in numbered
            if holders.get(
                (row.firm_id, row.vendor_id, row.supplier_return_number), set()
            )
            - {row.id}
        }

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_return_number: str | None,
        current_id: UUID | None,
    ) -> str | None:
        if not supplier_return_number:
            return None
        statement = select(PurchaseReturn.id).where(
            PurchaseReturn.firm_id == firm_id,
            PurchaseReturn.vendor_id == vendor_id,
            PurchaseReturn.supplier_return_number == supplier_return_number,
            PurchaseReturn.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(PurchaseReturn.id != current_id)
        if self._session.scalar(statement) is not None:
            return "A purchase return with this supplier return number already exists."
        return None

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        document: PurchaseReturn,
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
                source_module_code="PURCHASE_RETURN",
                document_number=document.return_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "return_number": document.return_number,
                    "supplier_return_number": document.supplier_return_number or "",
                    "grand_total": str(document.grand_total),
                },
                snapshot_json={
                    "status": document.status,
                    "vendor_id": str(document.vendor_id),
                    "branch_id": str(document.branch_id),
                },
                actor_id=actor_id,
            ),
            actor_id=actor_id,
        )

    def _attachment_response(
        self, row: PurchaseReturnAttachment
    ) -> PurchaseReturnAttachmentResponse:
        return PurchaseReturnAttachmentResponse.model_validate(row)

    def _note_response(self, row: PurchaseReturnNote) -> PurchaseReturnNoteResponse:
        return PurchaseReturnNoteResponse.model_validate(row)

    def _source_response(
        self, row: PurchaseReturnSource
    ) -> PurchaseReturnSourceResponse:
        return PurchaseReturnSourceResponse(
            id=row.id,
            source_document_type=PurchaseReturnSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: PurchaseReturnAccountingEvent
    ) -> PurchaseReturnAccountingEventResponse:
        return PurchaseReturnAccountingEventResponse(
            id=row.id,
            event_type=PurchaseReturnAccountingEventType(row.event_type),
            account_name=row.account_name,
            direction=row.direction,
            amount=row.amount,
            narration=row.narration,
            source_line_id=row.source_line_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _line_response(self, row: PurchaseReturnLine) -> PurchaseReturnLineResponse:
        return PurchaseReturnLineResponse(
            id=row.id,
            tax_rule_code=row.tax_rule_code,
            tax_rule_version=row.tax_rule_version,
            purchase_return_id=row.purchase_return_id,
            line_number=row.line_number,
            source_document_type=PurchaseReturnSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            received_quantity=row.received_quantity,
            already_returned_quantity=row.already_returned_quantity,
            current_return_quantity=self._q(
                row.current_return_quantity + row.free_quantity
            ),
            free_quantity=row.free_quantity,
            rejected_quantity=row.rejected_quantity,
            unbilled_quantity=row.unbilled_quantity,
            grni_amount=row.grni_amount,
            reason_code=row.reason_code,
            item_condition=row.item_condition,
            replacement_required=row.replacement_required,
            refund_required=row.refund_required,
            is_scrap=row.is_scrap,
            is_damaged=row.is_damaged,
            is_expired=row.is_expired,
            unit_price=row.unit_price,
            discount_percent=row.discount_percent,
            discount_amount=row.discount_amount,
            bill_discount_amount=row.bill_discount_amount,
            charges_amount=row.charges_amount,
            gross_amount=row.gross_amount,
            tax_profile_id=row.tax_profile_id,
            tax_amount=row.tax_amount,
            net_amount=row.net_amount,
            packaging_type_id=row.packaging_type_id,
            purchase_uom_id=row.purchase_uom_id,
            return_uom_id=row.return_uom_id,
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


def _billed_lines(
    session: Session, lines: Sequence[PurchaseReturnLine]
) -> dict[UUID, list[tuple[UUID, Decimal]]]:
    """Name the bill lines each return line reverses, with each one's weight.

    A line raised off a bill reverses that bill line whole. A line raised off
    a goods receipt reverses whatever billed the receipt line -- the bill took
    the input credit, not the receipt -- shared over the standing bill lines
    in proportion to the quantity each billed. The desktop raises returns off
    the receipt, and such a line used to name no bill, so its tax fell to
    `INPUT_TAX` whole while the bill had debited CGST and SGST (D-BUY-28). A
    receipt line nothing has billed yet names none.
    """
    named: dict[UUID, list[tuple[UUID, Decimal]]] = {}
    receipt_lines: dict[UUID, UUID] = {}
    for line in lines:
        if line.source_document_type == PurchaseReturnSourceType.PURCHASE_INVOICE.value:
            named[line.id] = [(line.source_document_line_id, Decimal("1"))]
        elif line.source_document_type == PurchaseReturnSourceType.GOODS_RECEIPT.value:
            receipt_lines[line.id] = line.source_document_line_id
    if not receipt_lines:
        return named
    billed: dict[UUID, list[tuple[UUID, Decimal]]] = {}
    for bill_line_id, receipt_line_id, quantity in session.execute(
        select(
            PurchaseInvoiceLine.id,
            PurchaseInvoiceLine.source_document_line_id,
            PurchaseInvoiceLine.current_invoice_quantity,
        )
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        .where(
            PurchaseInvoiceLine.source_document_line_id.in_(
                set(receipt_lines.values())
            ),
            PurchaseInvoiceLine.source_document_type
            == PurchaseReturnSourceType.GOODS_RECEIPT.value,
            PurchaseInvoiceLine.is_deleted.is_(False),
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status.in_(
                (
                    PurchaseInvoiceStatus.APPROVED.value,
                    PurchaseInvoiceStatus.CLOSED.value,
                )
            ),
        )
    ).all():
        billed.setdefault(receipt_line_id, []).append(
            (bill_line_id, Decimal(str(quantity)))
        )
    for return_line_id, receipt_line_id in receipt_lines.items():
        bill_lines = billed.get(receipt_line_id, [])
        whole = sum((quantity for _, quantity in bill_lines), ZERO)
        if whole <= ZERO:
            continue
        named[return_line_id] = [
            (bill_line_id, quantity / whole) for bill_line_id, quantity in bill_lines
        ]
    return named


def _billed_share(line: PurchaseReturnLine) -> Decimal:
    """Return the part of a line that reverses a bill, as a fraction of it.

    What went back before billing (``unbilled_quantity``, D-BUY-26) took no
    input credit and raised no payable, so it reverses neither.
    """
    quantity = Decimal(str(line.current_return_quantity))
    if quantity <= ZERO:
        return Decimal("1")
    unbilled = min(Decimal(str(line.unbilled_quantity or ZERO)), quantity)
    return (quantity - unbilled) / quantity


def return_billed_amounts(
    session: Session, rows: Sequence[PurchaseReturn]
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return what each return takes off payables, and the tax in it.

    The debit note part only (D-BUY-26): the document total and its tax, less
    the value of what went back before any bill reached it, which came off
    goods received not invoiced instead. A return wholly against unbilled
    goods takes nothing off payables -- its rounding and charges included.
    The posting and the supplier's credit both read this, so the payable the
    journal debited and the credit the supplier is shown cannot drift.

    In rupees: a return of goods bought in another currency is worth its
    figures at the rate it carries, its bill's (D-BUY-41).
    """
    if not rows:
        return {}
    rupees = return_rupee_rates(session, rows)
    parts: dict[UUID, list[tuple[Decimal, Decimal, Decimal, Decimal]]] = defaultdict(
        list
    )
    for return_id, quantity, unbilled, net, tax in session.execute(
        select(
            PurchaseReturnLine.purchase_return_id,
            PurchaseReturnLine.current_return_quantity,
            PurchaseReturnLine.unbilled_quantity,
            PurchaseReturnLine.net_amount,
            PurchaseReturnLine.tax_amount,
        ).where(
            PurchaseReturnLine.purchase_return_id.in_([row.id for row in rows]),
            PurchaseReturnLine.is_deleted.is_(False),
        )
    ).all():
        parts[return_id].append(
            (
                Decimal(str(quantity)),
                Decimal(str(unbilled or ZERO)),
                Decimal(str(net)),
                Decimal(str(tax)),
            )
        )
    amounts: dict[UUID, tuple[Decimal, Decimal]] = {}
    for row in rows:
        total = Decimal(str(row.grand_total))
        tax_total = Decimal(str(row.tax_total))
        lines = parts.get(row.id, [])
        if lines and all(
            quantity > ZERO and unbilled >= quantity
            for quantity, unbilled, _, _ in lines
        ):
            amounts[row.id] = (ZERO, ZERO)
            continue
        for quantity, unbilled, net, tax in lines:
            if unbilled <= ZERO or quantity <= ZERO:
                continue
            share = min(unbilled, quantity) / quantity
            total -= quantize_money(net * share)
            tax_total -= quantize_money(tax * share)
        rate = rupees.get(row.id, Decimal("1"))
        amounts[row.id] = (max(total, ZERO) * rate, max(tax_total, ZERO) * rate)
    return amounts


def return_rupee_rates(
    session: Session, rows: Sequence[PurchaseReturn]
) -> dict[UUID, Decimal]:
    """Return the rupees one unit of each return's currency is worth.

    One for a return in rupees, which is every return but those of goods
    bought in another currency -- and nothing is read for them. A return's
    currency is stamped from its documents when it is saved (D-BUY-41); the
    column was a free box before that, so a rate is believed only where one
    of the return's documents really is in that currency.
    """
    rates = {row.id: Decimal("1") for row in rows}
    stamped = {
        row.id: row
        for row in rows
        if rupee_rate(row.currency_code, row.exchange_rate) != Decimal("1")
    }
    if not stamped:
        return rates
    bill = PurchaseReturnSourceType.PURCHASE_INVOICE.value
    in_currency: dict[UUID, set[str | None]] = defaultdict(set)
    for return_id, code in session.execute(
        select(PurchaseReturnSource.purchase_return_id, PurchaseInvoice.currency_code)
        .join(
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseReturnSource.source_document_id,
        )
        .where(
            PurchaseReturnSource.purchase_return_id.in_(list(stamped)),
            PurchaseReturnSource.source_document_type == bill,
            PurchaseReturnSource.is_deleted.is_(False),
        )
    ).all():
        in_currency[return_id].add(normalize_currency(code))
    for return_id, code in session.execute(
        select(PurchaseReturnSource.purchase_return_id, PurchaseOrder.currency_code)
        .join(
            GoodsReceipt,
            GoodsReceipt.id == PurchaseReturnSource.source_document_id,
        )
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id)
        .where(
            PurchaseReturnSource.purchase_return_id.in_(list(stamped)),
            PurchaseReturnSource.source_document_type != bill,
            PurchaseReturnSource.is_deleted.is_(False),
        )
    ).all():
        in_currency[return_id].add(normalize_currency(code))
    for return_id, row in stamped.items():
        if normalize_currency(row.currency_code) in in_currency[return_id]:
            rates[return_id] = rupee_rate(row.currency_code, row.exchange_rate)
    return rates


def return_tax_by_component(
    session: Session, return_id: UUID, *, claimable: bool = True
) -> dict[str, Decimal]:
    """Split a return's tax by component, in the proportions its bill charged.

    A return reverses the credit the bill claimed, head by head: each return
    line's tax is split in the same proportions as the
    `purchase_invoice_line_taxes` rows of the bill line(s) it reverses
    (D-CMP-20) -- the bill line it was raised off, or the bill lines that
    billed the receipt line it was raised off (D-BUY-28, `_billed_lines`). A
    line raised off an order, or off a receipt nothing has billed, names no
    bill, and its tax reverses `INPUT_TAX` as a whole, which is where a bill
    with no rows put it. The ledger posting and GSTR-3B's reversal table both
    read this.

    ``claimable`` False returns the other part instead: the share of tax the
    bill could not claim (backlog 78 row 1), which goes back to the cost
    account rather than coming off input tax.
    """
    from app.purchase_invoice.models import PurchaseInvoiceLineTax

    lines = session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == return_id,
            PurchaseReturnLine.is_deleted.is_(False),
        )
    ).all()
    reversed_bill_lines = _billed_lines(session, lines)
    if not reversed_bill_lines:
        return {}
    # Each head goes back in rupees at its bill's own rate (D-BUY-41).
    rupees = bill_line_rupee_rates(
        session,
        sorted(
            {
                bill_line_id
                for named in reversed_bill_lines.values()
                for bill_line_id, _ in named
            },
            key=str,
        ),
    )
    shares: dict[UUID, list[tuple[str, Decimal, bool]]] = {}
    for line_id, code, amount, recoverable in session.execute(
        select(
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            PurchaseInvoiceLineTax.component_code,
            PurchaseInvoiceLineTax.amount,
            PurchaseInvoiceLineTax.recoverable,
        ).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(
                {
                    bill_line_id
                    for named in reversed_bill_lines.values()
                    for bill_line_id, _ in named
                }
            ),
            PurchaseInvoiceLineTax.is_deleted.is_(False),
            PurchaseInvoiceLineTax.included_in_price.is_(False),
            # Reverse charge never sat in the bill's payable or its credit.
            PurchaseInvoiceLineTax.reverse_charge.is_(False),
        )
    ).all():
        shares.setdefault(line_id, []).append(
            (code, Decimal(str(amount)), bool(recoverable))
        )
    totals: dict[str, Decimal] = {}
    for line in lines:
        named = reversed_bill_lines.get(line.id, [])
        parts = [
            (code, amount * weight, recoverable)
            for bill_line_id, weight in named
            for code, amount, recoverable in shares.get(bill_line_id, [])
        ]
        # One return line reverses bills of one currency at one rate.
        rate = next(
            (
                rupees[bill_line_id]
                for bill_line_id, _ in named
                if bill_line_id in rupees
            ),
            Decimal("1"),
        )
        # Shared out over everything the bill line charged; only the part
        # asked for -- claimed, or blocked (backlog 78 row 1) -- is returned.
        charged = sum((amount for _, amount, _ in parts), ZERO)
        if charged <= ZERO:
            continue
        for code, amount, recoverable in parts:
            if recoverable is not claimable:
                continue
            totals[code] = totals.get(code, ZERO) + quantize_money(
                Decimal(str(line.tax_amount))
                * rate
                * _billed_share(line)
                * amount
                / charged
            )
    return totals


def return_reverse_charge(session: Session, return_id: UUID) -> ReverseChargeShare:
    """Return the reverse charge a purchase return takes off its bill.

    Backlog 68 row 8. Each line takes the share of its bill line's reverse
    charge that its value is of the bill line's -- the bill line it was raised
    off, or those that billed its receipt line, by `_billed_lines` (D-BUY-28).
    A line off an order, or off a receipt nothing has billed, takes nothing.
    The posting and GSTR-3B's 3.1(d) and 4(A)(3) both read this.
    """
    lines = session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == return_id,
            PurchaseReturnLine.is_deleted.is_(False),
        )
    ).all()
    reversed_bill_lines = _billed_lines(session, lines)
    return reverse_charge_share(
        session,
        (
            (
                bill_line_id,
                (Decimal(str(line.net_amount)) - Decimal(str(line.tax_amount)))
                * _billed_share(line)
                * weight,
            )
            for line in lines
            for bill_line_id, weight in reversed_bill_lines.get(line.id, [])
        ),
    )
