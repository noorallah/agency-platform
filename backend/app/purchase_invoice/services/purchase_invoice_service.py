"""Purchase invoice workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import case, func, or_, select, true
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.business.models.framework import AttributeEntityType
from app.business.services import document_attributes
from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_today
from app.common.report_names import (
    branch_names,
    product_names,
    vendor_names,
    vendors_matching,
)
from app.core.database.batch import children_by_parent
from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.pagination import WHOLE_HISTORY, ReportRows, ReportWindow, mapped_like
from app.core.utils.chunks import chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.core.utils.pricing import (
    LineDiscount,
    inherited_share,
    resolve_line_discount,
)
from app.core.utils.quantities import plain_quantity
from app.document_files.services import purchase_invoice_file_counts
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
from app.finance.currency import (
    check_currency,
    is_foreign,
    normalize_currency,
    to_base,
)
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.goods_receipt.billing import receipt_line_billing
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.rules import posted_receipt_line, require_posted_receipt
from app.goods_receipt.schemas import GoodsReceiptStatus
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.inventory.models import StockLedgerEntry
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderStatus
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceAccountingEvent,
    PurchaseInvoiceAttachment,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
    PurchaseInvoiceNote,
    PurchaseInvoiceSource,
)
from app.purchase_invoice.schemas import (
    PurchaseInvoiceAccountingEventResponse,
    PurchaseInvoiceAccountingEventType,
    PurchaseInvoiceAttachmentResponse,
    PurchaseInvoiceAttachmentWrite,
    PurchaseInvoiceCreate,
    PurchaseInvoiceImportRequest,
    PurchaseInvoiceLineResponse,
    PurchaseInvoiceLineTaxResponse,
    PurchaseInvoiceListFilters,
    PurchaseInvoiceMsmeDueRecord,
    PurchaseInvoiceNoteResponse,
    PurchaseInvoiceNoteWrite,
    PurchaseInvoiceOverdueRecord,
    PurchaseInvoicePaymentNow,
    PurchaseInvoicePreview,
    PurchaseInvoiceReconciliationRecord,
    PurchaseInvoiceRegisterRecord,
    PurchaseInvoiceResponse,
    PurchaseInvoiceSourceResponse,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceStatus,
    PurchaseInvoiceSummary,
    PurchaseInvoiceVendorOutstandingRecord,
)
from app.purchase_invoice.services.msme import (
    default_due_date,
    msme_pay_by,
    msme_warning,
)
from app.sales.services.document_preview import purchase_line_companions
from app.settlements.models import Settlement
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementAllocationWrite,
    SettlementCreate,
)
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.gst_compliance import GstComplianceService
from app.tax.services.gst_time_limits import credit_time_limit_warning
from app.tax.services.place_of_supply import PURCHASE_INTERSTATE
from app.tax.services.rule_stamp import stamps_tax_rules
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.services import (
    UomService,
    assert_quantity_fits_unit,
    exact_quantity,
    unit_named,
)
from app.vendors.models import Vendor

if TYPE_CHECKING:
    from app.finance.services.tds_sections import TdsProposal

ZERO = Decimal("0")

# The line shapes this document can be raised from. Naming the union lets the
# helpers below say what they accept instead of taking ``object`` and reaching
# for attributes mypy cannot see.
SourceLine = GoodsReceiptLine | PurchaseOrderLine


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


def _required_uuid(value: object) -> UUID:
    """Read a UUID the line spec must carry."""
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True, slots=True)
class _LineTaxComponent:
    """One tax component charged on one line, as the engine reported it."""

    tax_component_id: UUID | None
    code: str
    label: str
    percentage: Decimal
    base_amount: Decimal
    amount: Decimal
    included_in_price: bool
    recoverable: bool


@dataclass(frozen=True, slots=True)
class _LineTax:
    """What the rule engine decided for one line, kept rather than discarded."""

    profile_id: UUID | None
    total: Decimal
    components: list[_LineTaxComponent]
    #: The engine decided the firm owes this tax itself (backlog 68 row 8):
    #: `total` is then nothing, and the components are what it owes.
    reverse_charge: bool = False
    #: False when a tax rule says *Input credit blocked* (backlog 78 row 1).
    input_credit_allowed: bool | None = None


class SelfInvoiceNumbering(TransactionalDocumentService):
    """Issue the next self-invoice number for a reverse-charge supply.

    Its own series (prefix ``SI``), never the purchase bill's: a self-invoice
    is a tax invoice the firm raises on itself, and GSTR-1's document summary
    declares its series separately. Reserves under the series lock and
    flushes; it never commits, so a refused approval takes the number back.
    """

    DOCUMENT = DocumentTypeSpec(
        code="RCM_SELF_INVOICE",
        name="Self Invoice (Reverse Charge)",
        description="Self-invoice for an inward supply under reverse charge",
        category="FINANCE",
        module="purchase_invoice",
        # Its own, not the sales invoice's ``SI``. A number is issued by
        # stepping over numbers of the same document type and over journal
        # references, and a self-invoice posts no journal under its number:
        # the next sales invoice walked onto SI-26-27-000002, two GST
        # documents under one serial number (D-BUY-58). ``RSI-26-27-000001``
        # is the 16 characters rule 46(b) allows.
        prefix="RSI",
        states=(DocumentStateSpec("ISSUED", "Issued", 1, is_terminal=True),),
    )

    def issue(self, *, firm_id: UUID, on: date, actor_id: UUID) -> str:
        """Return the series' next number for a bill dated ``on``."""
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        return self._issue_number(
            rule,
            typed=None,
            number_column=PurchaseInvoice.self_invoice_number,  # type: ignore[arg-type]
            firm_id=firm_id,
            document_date=on,
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )


class PurchaseInvoiceService(TransactionalDocumentService):
    """Coordinate supplier invoice lifecycle and source-document validation."""

    DOCUMENT = DocumentTypeSpec(
        code="PURCHASE_INVOICE",
        name="Purchase Invoice",
        description="Supplier invoice document",
        category="FINANCE",
        module="purchase_invoice",
        prefix="PI",
        include_branch_code=True,
        include_company_code=True,
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

    def list_invoices(
        self,
        *,
        firm_scope: UUID,
        filters: PurchaseInvoiceListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[PurchaseInvoice], int]:
        """List purchase invoices for the visible firm scope."""
        columns = {
            "invoice_number": PurchaseInvoice.invoice_number,
            "invoice_date": PurchaseInvoice.invoice_date,
            "due_date": PurchaseInvoice.due_date,
            "grand_total": PurchaseInvoice.grand_total,
            "status": PurchaseInvoice.status,
            "created_at": PurchaseInvoice.created_at,
            "updated_at": PurchaseInvoice.updated_at,
        }
        statement = select(PurchaseInvoice).where(PurchaseInvoice.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(PurchaseInvoice)
            .where(PurchaseInvoice.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(PurchaseInvoice.is_deleted.is_(False))
            count = count.where(PurchaseInvoice.is_deleted.is_(False))
        if filters.vendor_id is not None:
            statement = statement.where(PurchaseInvoice.vendor_id == filters.vendor_id)
            count = count.where(PurchaseInvoice.vendor_id == filters.vendor_id)
        if filters.branch_id is not None:
            statement = statement.where(PurchaseInvoice.branch_id == filters.branch_id)
            count = count.where(PurchaseInvoice.branch_id == filters.branch_id)
        if filters.status is not None:
            statement = statement.where(PurchaseInvoice.status == filters.status.value)
            count = count.where(PurchaseInvoice.status == filters.status.value)
        if filters.invoice_from is not None:
            statement = statement.where(
                PurchaseInvoice.invoice_date >= filters.invoice_from
            )
            count = count.where(PurchaseInvoice.invoice_date >= filters.invoice_from)
        if filters.invoice_to is not None:
            statement = statement.where(
                PurchaseInvoice.invoice_date <= filters.invoice_to
            )
            count = count.where(PurchaseInvoice.invoice_date <= filters.invoice_to)
        if filters.due_from is not None:
            statement = statement.where(PurchaseInvoice.due_date >= filters.due_from)
            count = count.where(PurchaseInvoice.due_date >= filters.due_from)
        if filters.due_to is not None:
            statement = statement.where(PurchaseInvoice.due_date <= filters.due_to)
            count = count.where(PurchaseInvoice.due_date <= filters.due_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                PurchaseInvoice.invoice_number.ilike(token),
                PurchaseInvoice.supplier_invoice_number.ilike(token),
                PurchaseInvoice.reference_number.ilike(token),
                PurchaseInvoice.remarks.ilike(token),
                PurchaseInvoice.vendor_id.in_(vendors_matching(token)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, PurchaseInvoice.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    sort_column.desc() if descending else sort_column.asc(),
                    # Newest first within the chosen column, then a stable key:
                    # a day's bills came back in random order (D-UI-10).
                    PurchaseInvoice.created_at.desc(),
                    PurchaseInvoice.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> PurchaseInvoiceSummary:
        """Return aggregate purchase invoice values for the visible firm scope.

        Counted and summed in SQL, one row per status, rather than loading every
        document the firm ever raised (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    PurchaseInvoice.status,
                    func.count(),
                    func.coalesce(func.sum(PurchaseInvoice.grand_total), 0),
                )
                .where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                )
                .group_by(PurchaseInvoice.status)
            ).all()
        }

        def count(status: PurchaseInvoiceStatus) -> int:
            """Return how many documents are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        # The tile and the overdue report must agree, so the tile counts the
        # report's rows: bills past due that still owe something (D-RPT-2).
        # Counted off the owing bills themselves: building the report's rows
        # to count them read every one back (backlog 56 C, step 4).
        today = firm_today(self._session, firm_scope)
        overdue = sum(
            1
            for record in self._owing(firm_scope=firm_scope)
            if record.due_date is not None and record.due_date < today
        )
        return PurchaseInvoiceSummary(
            total=sum(number for number, _ in by_status.values()),
            draft=count(PurchaseInvoiceStatus.DRAFT),
            approved=count(PurchaseInvoiceStatus.APPROVED),
            cancelled=count(PurchaseInvoiceStatus.CANCELLED),
            closed=count(PurchaseInvoiceStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
            pending_invoices=count(PurchaseInvoiceStatus.DRAFT),
            overdue_invoices=overdue,
        )

    def create_invoice(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoice:
        """Create one purchase invoice and commit it."""
        self._refuse_empty_bill_lines(data)
        row = self.stage_invoice(data, firm_id=firm_id, actor_id=actor_id)
        if data.attributes:
            document_attributes.store(
                self._session,
                AttributeEntityType.PURCHASE_INVOICE,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        # Fields the source documents hold carry to this one (MST-6).
        document_attributes.carry_from_sources(
            self._session,
            AttributeEntityType.PURCHASE_INVOICE,
            row.id,
            [
                (line.source_document_type, line.source_document_id)
                for line in self._session.scalars(
                    select(PurchaseInvoiceLine)
                    .where(
                        PurchaseInvoiceLine.purchase_invoice_id == row.id,
                        PurchaseInvoiceLine.is_deleted.is_(False),
                    )
                    .order_by(PurchaseInvoiceLine.line_number)
                )
            ],
            firm_id=row.firm_id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def _refuse_empty_bill_lines(self, data: PurchaseInvoiceCreate) -> None:
        """Refuse a bill line of 0 with nothing free, where it is saved (D-BUY-53).

        It saved, and was refused only at approval in the ledger's words: "A
        journal entry must carry a non-zero amount." A preview is not asked:
        the line being typed has no quantity yet.

        The free goods may be the line's own (a bill of products) or its
        source line's: a receipt line of free goods alone is billed at 0 so
        the bill shows it and the order reads complete (86 #27).
        """
        empty = [
            line
            for line in data.lines
            if line.current_invoice_quantity <= 0 and not (line.free_quantity or 0) > 0
        ]
        if not empty:
            return
        source_ids = [
            line.source_document_line_id
            for line in empty
            if line.source_document_line_id is not None
        ]
        gifted: set[UUID] = set()
        for model in (GoodsReceiptLine, PurchaseOrderLine):
            if source_ids:
                gifted.update(
                    self._session.scalars(
                        select(model.id).where(
                            model.id.in_(source_ids), model.free_quantity > 0
                        )
                    ).all()
                )
        self._refuse_lines_for_nothing(
            (
                (line.line_number, line.current_invoice_quantity, None)
                for line in empty
                if line.source_document_line_id not in gifted
            ),
            does="bills",
            document="bill",
        )

    def preview_invoice(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoicePreview:
        """Price a bill exactly as saving it would, then save nothing.

        Staged through the save path -- the receipt's prices where none is
        typed, discounts, tax at the rates in force -- read back, and the unit
        of work rolled back: no bill, no number used up, no audit row. The
        response carries the duplicate-number warning the save would, so the
        clerk learns of a bill entered twice while typing it.
        """
        try:
            row = self.stage_invoice(data, firm_id=firm_id, actor_id=actor_id)
            response = self.invoice_response(row)
            interstate = (
                self._tax.inward_transaction_type(
                    "PURCHASE_INVOICE",
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
        return PurchaseInvoicePreview(
            invoice=response, interstate=interstate, lines=lines
        )

    def stage_invoice(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> PurchaseInvoice:
        """Build one purchase invoice as a draft without committing it."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        # Raise whatever earlier documents this firm has chosen not to type.
        # A firm on the whole chain gets its payload back untouched, so this
        # costs one settings read and changes nothing for anybody else.
        from app.purchase_invoice.services.purchase_chain_service import (
            PurchaseChainService,
        )

        chain = PurchaseChainService(self._session)
        # Read before anything fills it in: silence takes the order's
        # currency ahead of the supplier's (D-BUY-39).
        typed_currency = "currency_code" in data.model_fields_set
        if not typed_currency:
            data = self._with_order_currency(data, firm_id=firm_id)
        # Before the chain, so an order and receipt it raises carry the
        # bill's currency and rate and the stock lands in rupees (PG-12).
        data = self._with_supplier_currency(data, vendor_id=data.vendor_id)
        # Asked here, in the bill's words: the order the chain raises next
        # asks the same of itself and would name a document nobody typed
        # (D-BUY-51).
        check_currency(data.currency_code, data.exchange_rate)
        data = chain.ensure_invoice_source(data, firm_id=firm_id, actor_id=actor_id)
        own_receipts = frozenset(receipt.id for receipt in chain.raised_receipts)
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_id=firm_id, own_receipts=own_receipts
        )
        branch_id = data.branch_id or header["branch_id"]
        vendor_id = data.vendor_id or header["vendor_id"]
        business_profile_id = data.business_profile_id
        if vendor_id != header["vendor_id"]:
            raise ValidationError("Invoice vendor must match all source documents.")
        self._refuse_blocked(vendor_id)
        if branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        data = self._with_supplier_currency(data, vendor_id=vendor_id)
        self._refuse_another_currency(data, firm_id=firm_id)
        self._validate_supplier_invoice_number(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_invoice_number=data.supplier_invoice_number,
        )
        invoice_number = self._issue_number(
            numbering_rule,
            typed=data.invoice_number.strip().upper() if data.invoice_number else None,
            number_column=PurchaseInvoice.invoice_number,
            firm_id=firm_id,
            document_date=data.invoice_date,
            actor_id=actor_id,
            branch_code=self._scope_code(branch_id),
            company_code=self._company_code(firm_id),
        )
        row = PurchaseInvoice(
            firm_id=firm_id,
            vendor_id=vendor_id,
            branch_id=branch_id,
            business_profile_id=business_profile_id,
            invoice_number=invoice_number,
            invoice_date=data.invoice_date,
            supplier_invoice_number=data.supplier_invoice_number.strip(),
            supplier_invoice_date=data.supplier_invoice_date,
            supplier_irn=data.supplier_irn,
            currency_code=normalize_currency(data.currency_code),
            exchange_rate=data.exchange_rate,
            payment_terms=data.payment_terms,
            due_date=default_due_date(
                self._session.get(Vendor, vendor_id),
                typed=data.due_date,
                invoice_date=data.invoice_date,
            ),
            msme_pay_by=msme_pay_by(
                self._session.get(Vendor, vendor_id),
                invoice_date=data.invoice_date,
                supplier_invoice_date=data.supplier_invoice_date,
            ),
            reference_number=data.reference_number,
            remarks=data.remarks,
            status=PurchaseInvoiceStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        self._stamp_raised(row, chain.raised_orders, chain.raised_receipts)
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
            own_receipts=own_receipts,
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
        row.reverse_charge_tax_total = line_totals["reverse_charge_tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._stage_tcs(row, data, previous_total=None)
        self._stage_currency(row)
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
            action="purchase_invoice.created",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"invoice_number": row.invoice_number, "status": row.status},
        )
        self._flush_or_conflict("Purchase invoice number already exists in this firm.")
        return row

    def update_invoice(
        self,
        invoice_id: UUID,
        data: PurchaseInvoiceCreate,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseInvoice:
        """Replace one purchase invoice."""
        assert_feature_fields(
            self._session,
            firm_scope,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != PurchaseInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft purchase invoices can be updated.")
        self._refuse_empty_bill_lines(data)
        # Absent keeps the IRN on file: a client that never showed it cannot
        # clear it. Read before the chain may hand back a rebuilt request.
        if "supplier_irn" in data.model_fields_set:
            row.supplier_irn = data.supplier_irn
        # Absent keeps the bill's currency and rate (PG-12); filled in before
        # the chain so an order it raises again carries them too.
        kept = {
            field: getattr(row, field)
            for field in ("currency_code", "exchange_rate")
            if field not in data.model_fields_set
        }
        if kept:
            data = data.model_copy(update=kept)
        # In the bill's words, before an order raised again asks (D-BUY-51).
        check_currency(data.currency_code, data.exchange_rate)
        self._delete_children(row.id)
        own_receipts = frozenset(receipt.id for receipt in self._raised_receipts(row))
        if any(line.source_document_line_id is None for line in data.lines):
            # A bill of products restates the whole purchase. The order and
            # the receipt it raised before are drafts that moved nothing, so
            # they are withdrawn and raised again from what the bill now says
            # -- the one-person firm edits the bill, never the documents
            # behind it.
            self._withdraw_raised(
                row,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=f"Replaced when {row.invoice_number} was edited.",
            )
            from app.purchase_invoice.services.purchase_chain_service import (
                PurchaseChainService,
            )

            chain = PurchaseChainService(self._session)
            data = chain.ensure_invoice_source(
                data, firm_id=firm_scope, actor_id=actor_id
            )
            self._stamp_raised(row, chain.raised_orders, chain.raised_receipts)
            own_receipts = frozenset(receipt.id for receipt in chain.raised_receipts)
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_scope, own_receipts=own_receipts
        )
        row.vendor_id = data.vendor_id or header["vendor_id"]
        self._refuse_blocked(row.vendor_id)
        self._refuse_another_currency(data, firm_id=firm_scope)
        row.branch_id = data.branch_id or header["branch_id"]
        row.business_profile_id = data.business_profile_id
        row.invoice_date = data.invoice_date
        row.supplier_invoice_number = data.supplier_invoice_number.strip()
        row.supplier_invoice_date = data.supplier_invoice_date
        row.currency_code = normalize_currency(data.currency_code)
        row.exchange_rate = data.exchange_rate
        row.payment_terms = data.payment_terms
        vendor = self._session.get(Vendor, row.vendor_id)
        row.due_date = default_due_date(
            vendor, typed=data.due_date, invoice_date=data.invoice_date
        )
        row.msme_pay_by = msme_pay_by(
            vendor,
            invoice_date=data.invoice_date,
            supplier_invoice_date=data.supplier_invoice_date,
        )
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        previous_total = row.grand_total
        self._validate_supplier_invoice_number(
            firm_id=firm_scope,
            vendor_id=row.vendor_id,
            supplier_invoice_number=row.supplier_invoice_number,
            current_id=row.id,
        )
        self._replace_sources(row, source_rows, firm_id=firm_scope, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            firm_id=firm_scope,
            invoice_date=data.invoice_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
            own_receipts=own_receipts,
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
        row.reverse_charge_tax_total = line_totals["reverse_charge_tax_total"]
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + row.additional_charges
            + row.round_off
        )
        self._stage_tcs(row, data, previous_total=previous_total)
        self._stage_currency(row)
        self._replace_attachments(
            row, data.attachments, actor_id=actor_id, firm_id=firm_scope
        )
        self._replace_notes(row, data.notes, actor_id=actor_id, firm_id=firm_scope)
        self._replace_accounting_events(row, actor_id=actor_id, firm_id=firm_scope)
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="purchase_invoice.updated",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        if "attributes" in data.model_fields_set:
            document_attributes.store(
                self._session,
                AttributeEntityType.PURCHASE_INVOICE,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        self._session.commit()
        return row

    def approve_invoice(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_exceed_tolerance: bool = True,
        tds_amount: Decimal | None = None,
    ) -> PurchaseInvoice:
        """Approve one purchase invoice.

        ``may_exceed_tolerance`` says the caller holds
        PURCHASE_APPROVE_OVER_TOLERANCE; without it a bill priced past the
        firm's tolerance over its order is refused, naming the lines (BUY-10).
        ``tds_amount`` overrides the 194C/194J deduction the bill proposes
        (PG-5); None takes the proposal.
        """
        row = self.stage_approve(
            invoice_id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            may_exceed_tolerance=may_exceed_tolerance,
            tds_amount=tds_amount,
        )
        self._session.commit()
        return row

    def approve_and_pay(
        self,
        invoice_id: UUID,
        payment: PurchaseInvoicePaymentNow,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_exceed_tolerance: bool = True,
        tds_amount: Decimal | None = None,
    ) -> tuple[PurchaseInvoice, Settlement]:
        """Approve a bill and pay it over the counter, in one commit (PG-3).

        The payment is an ordinary one -- the row ``POST /payments`` writes,
        allocated to this bill -- so reversing it is the usual reversal and a
        part payment leaves the rest outstanding. Both are staged and committed
        once: a payment refused (no cash account mapped, more than the bill
        owes) rolls the approval back with it, receipt raised by the buying
        stage switches included, rather than leaving a bill approved that the
        person meant to have paid.

        More than the bill owes is refused rather than kept as an advance: a
        counter purchase pays the bill, and money ahead of a bill is recorded
        on its own through ``/payments``.
        """
        # Imported here: the settlements service reads this module's models.
        from app.settlements.services import PaymentService

        bill = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if is_foreign(bill.currency_code):
            # Paid now is rupees over the counter; a bill in another currency
            # is paid in that currency at the day's rate (PG-12).
            raise ValidationError(
                f"Bill {bill.invoice_number} is in {bill.currency_code}. "
                "Approve it, then pay it through Payments in "
                f"{bill.currency_code} at the day's rate."
            )
        try:
            row = self.stage_approve(
                invoice_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                may_exceed_tolerance=may_exceed_tolerance,
                tds_amount=tds_amount,
            )
            payments = PaymentService(self._session)
            owing = next(
                (
                    record.outstanding_amount
                    for record in payments.outstanding_invoices(
                        firm_id=firm_scope, party_id=row.vendor_id
                    )
                    if record.invoice_id == row.id
                ),
                ZERO,
            )
            amount = payment.amount if payment.amount is not None else owing
            if amount <= ZERO:
                raise ValidationError(
                    f"Bill {row.invoice_number} owes nothing once approved, so "
                    "there is nothing to pay now."
                )
            if amount > owing:
                raise ValidationError(
                    f"Bill {row.invoice_number} owes {owing}, so {amount} "
                    "cannot be paid against it now. Record an advance through "
                    "Payments."
                )
            settlement = payments.create(
                SettlementCreate(
                    party_id=row.vendor_id,
                    settlement_date=payment.payment_date or row.invoice_date,
                    amount=amount,
                    method=payment.method,
                    payment_mode=payment.payment_mode,
                    instrument_reference=payment.instrument_reference,
                    instrument_date=payment.instrument_date,
                    narration=payment.narration
                    or f"Paid against bill {row.invoice_number}",
                    allocations=[
                        SettlementAllocationWrite(invoice_id=row.id, amount=amount)
                    ],
                ),
                firm_id=firm_scope,
                actor_id=actor_id,
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return row, settlement

    def stage_approve(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        may_exceed_tolerance: bool = True,
        tds_amount: Decimal | None = None,
    ) -> PurchaseInvoice:
        """Approve one purchase invoice and flush, leaving the commit to the caller.

        Flushed so a query that follows in the same transaction -- what the bill
        still owes, for a payment made with it -- sees it approved on a session
        that does not autoflush, as a request's does not.
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != PurchaseInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft purchase invoices can be approved.")
        # Levels of sign-off the firm's rules call for (PLT-1).
        from app.approvals.services import ApprovalChainService

        ApprovalChainService(self._session).assert_cleared(
            firm_scope, "PURCHASE_INVOICE", row.id, row.grand_total, actor_id
        )
        if not may_exceed_tolerance:
            self._assert_within_tolerance(row, firm_id=firm_scope)
        # A bill that raised its own receipt brings the goods in now: its
        # approval is the receipt's completion -- stock in, Dr inventory / Cr
        # goods received not invoiced -- and the bill below clears that
        # accrual in the same transaction. Only its own draft receipts; a
        # receipt a person raised was completed by them.
        # Capital goods (PG-13) are an asset, not stock: the bill's own
        # receipt brings them in without a stock movement or an accrual.
        capital_lines = self._capital_lines(row.id)
        receipts = GoodsReceiptService(self._session)
        for receipt in self._raised_receipts(row):
            if receipt.status == GoodsReceiptStatus.DRAFT.value:
                receipts.stage_complete(
                    receipt.id,
                    firm_scope=firm_scope,
                    actor_id=actor_id,
                    capital_line_ids=frozenset(
                        line.source_document_line_id for line in capital_lines
                    ),
                )
        self._refuse_capital_goods_in_stock(capital_lines)
        # Checked again where the payable is raised, so a draft saved before
        # the check existed cannot post against a line it does not own.
        self._refuse_foreign_lines(row, firm_id=firm_scope)
        self._refuse_past_left_to_bill(row)
        # TDS under 194C or 194J is deducted at the earlier of credit and
        # payment (PG-5), so the bill proposes it as it is credited -- worked
        # out before the bill counts as approved, so it is not its own past.
        # A bill in another currency is from a supplier abroad, outside both
        # sections (PG-12): nothing is proposed and a deduction is refused.
        foreign = is_foreign(row.currency_code)
        if foreign and tds_amount is not None and tds_amount > ZERO:
            raise ValidationError(
                "TDS under 194C or 194J is not deducted on a bill in another "
                "currency. A payment abroad is withheld under section 195, "
                "which is not worked out here.",
                details={"field": "tds_amount"},
            )
        tds = (
            None
            if foreign
            else self._stage_tds(row, firm_id=firm_scope, override=tds_amount)
        )
        before = row.status
        row.status = PurchaseInvoiceStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        # A supply under reverse charge needs a self-invoice (rule 47A), from
        # its own series and never the bill's, issued as the liability is
        # recorded (backlog 68 row 8). Kept on a cancelled bill, as a
        # cancelled voucher keeps its number.
        reverse_charge = self._tax_by_component(row.id, reverse_charge=True)
        if row.self_invoice_number is None and any(
            amount > ZERO for amount in reverse_charge.values()
        ):
            row.self_invoice_number = SelfInvoiceNumbering(self._session).issue(
                firm_id=firm_scope, on=row.invoice_date, actor_id=actor_id
            )
        # Posting runs before the commit and may fail the approval, matching the
        # sales side. Goods value clears the receipt accrual rather than touching
        # inventory, which was already valued at what the receipt cost.
        # A bill in another currency posts in rupees at its own rate (PG-12),
        # each leg converted on its own; the accrual is what the receipt's
        # movement cost, so any gap is a price variance as on any bill.
        if foreign and row.exchange_rate is not None:
            rate = row.exchange_rate
            base_tax = row.base_tax_total or ZERO
            base_total = row.base_grand_total or ZERO
            goods_amount = base_total - base_tax
            tax_amount = base_tax
            total_amount = base_total
            by_component = self._in_rupees(self._tax_by_component(row.id), rate)
            reverse_charge = self._in_rupees(reverse_charge, rate)
            blocked = to_base(self._blocked_tax(row.id), rate)
        else:
            goods_amount = self._q(row.grand_total - row.tax_total)
            tax_amount = self._q(row.tax_total)
            total_amount = self._q(row.grand_total)
            by_component = self._tax_by_component(row.id)
            blocked = self._blocked_tax(row.id)
        capital_amounts = self._stage_assets(
            row, capital_lines, firm_id=firm_scope, actor_id=actor_id
        )
        DocumentPostingService(self._session).post_purchase_invoice(
            firm_id=firm_scope,
            invoice_id=row.id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            goods_amount=goods_amount,
            accrued_amount=self._accrued_cost(row.id),
            tax_amount=tax_amount,
            total_amount=total_amount,
            actor_id=actor_id,
            tax_by_component=by_component,
            reverse_charge_by_component=reverse_charge,
            blocked_tax_amount=blocked,
            tds_amount=row.tds_amount,
            tcs_amount=row.tcs_amount,
            capital_amounts=capital_amounts,
        )
        # Warned, not refused: the bill is owed whatever its terms say, and
        # paying it in time is what the warning is for (backlog 68 row 2).
        supplier = self._session.get(Vendor, row.vendor_id)
        msme_remark = msme_warning(
            pay_by=row.msme_pay_by,
            due_date=row.due_date,
            vendor_name=supplier.display_name if supplier else "The supplier",
        )
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="APPROVED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=msme_remark,
        )
        record_audit(
            self._session,
            action="purchase_invoice.approved",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=tds,
        )
        self._session.flush()
        return row

    def _capital_lines(self, invoice_id: UUID) -> list[PurchaseInvoiceLine]:
        """Return the bill's capital-goods lines (PG-13), in line order."""
        return list(
            self._session.scalars(
                select(PurchaseInvoiceLine)
                .where(
                    PurchaseInvoiceLine.purchase_invoice_id == invoice_id,
                    PurchaseInvoiceLine.is_deleted.is_(False),
                    PurchaseInvoiceLine.is_capital_goods.is_(True),
                )
                .order_by(PurchaseInvoiceLine.line_number)
            ).all()
        )

    def _refuse_capital_goods_in_stock(
        self, lines: Sequence[PurchaseInvoiceLine]
    ) -> None:
        """Refuse a capital-goods line whose receipt already put it in stock.

        Capital goods never enter stock (PG-13). The bill's own receipt is
        completed without a movement for them, and so is a receipt whose
        line the order or the receiver marked capital goods (D-BUY-40). A
        line a person received into stock has already moved the goods in,
        and taking them out again is a stock issue, not a bill's business:
        the message says how to receive it as capital goods instead.

        Raises:
            ValidationError: Naming the line and the receipt.

        """
        receipt_lines = [
            line.source_document_line_id
            for line in lines
            if line.source_document_type
            == PurchaseInvoiceSourceType.GOODS_RECEIPT.value
        ]
        if not receipt_lines:
            return
        stocked = set(
            self._session.scalars(
                select(GoodsReceiptLine.id).where(
                    GoodsReceiptLine.id.in_(receipt_lines),
                    GoodsReceiptLine.inventory_transaction_id.is_not(None),
                )
            ).all()
        )
        for line in lines:
            if line.source_document_line_id in stocked:
                raise ValidationError(
                    f"Line {line.line_number} is capital goods, but "
                    f"{line.source_document_number} already took it into "
                    "stock. Untick capital goods on this line; or cancel "
                    f"{line.source_document_number} and mark the line capital "
                    "goods on the order or the receipt, so it is received "
                    "without entering stock.",
                    details={"field": "is_capital_goods"},
                )

    def _stage_assets(
        self,
        row: PurchaseInvoice,
        lines: Sequence[PurchaseInvoiceLine],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[tuple[UUID, Decimal]]:
        """Raise the bill's fixed assets and return the legs to debit (PG-13).

        Each asset costs its line's value before tax, in rupees: a bill in
        another currency is converted at its own rate, as its journal is.
        """
        if not lines:
            return []
        # Imported here: fixed assets read this module's models.
        from app.fixed_assets.services import FixedAssetService

        rate = (
            row.exchange_rate
            if is_foreign(row.currency_code) and row.exchange_rate is not None
            else Decimal("1")
        )
        return FixedAssetService(self._session).stage_from_invoice(
            firm_id=firm_id,
            invoice_id=row.id,
            invoice_date=row.invoice_date,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            lines=[
                (
                    line.id,
                    line.asset_class_id,
                    line.product_id,
                    line.description,
                    line.current_invoice_quantity,
                    (line.net_amount - line.tax_amount) * rate,
                )
                for line in lines
                if line.asset_class_id is not None
            ],
            actor_id=actor_id,
        )

    @staticmethod
    def _stage_tcs(
        row: PurchaseInvoice,
        data: PurchaseInvoiceCreate,
        *,
        previous_total: Decimal | None,
    ) -> None:
        """Stamp the TCS the supplier charged on the bill (206C(1H), PG-6).

        A typed amount wins; with only a rate the amount is the rate on the
        grand total, which is the section's base -- the bill including GST.
        An edit naming neither field keeps the bill's: a rate-worked amount
        follows the new total, a typed one stays as typed. TCS is never part
        of GST's taxable value, so nothing here touches the lines or the tax.
        ``previous_total`` is the grand total before an edit; None on create.
        """
        sent = data.model_fields_set
        if previous_total is None or sent & {"tcs_rate_percent", "tcs_amount"}:
            rate = (
                data.tcs_rate_percent
                if previous_total is None or "tcs_rate_percent" in sent
                else row.tcs_rate_percent
            )
            # Absent beside a sent rate means "work it out from the rate".
            typed = data.tcs_amount
        else:
            rate = row.tcs_rate_percent
            worked = (
                None
                if rate is None
                else quantize_ledger(previous_total * rate / Decimal("100"))
            )
            # Still what the rate gave on the old total: it follows the new one.
            typed = (
                None if worked == quantize_ledger(row.tcs_amount) else row.tcs_amount
            )
        row.tcs_rate_percent = rate
        if typed is not None:
            row.tcs_amount = quantize_ledger(typed)
        elif rate is not None:
            row.tcs_amount = quantize_ledger(row.grand_total * rate / Decimal("100"))
        else:
            row.tcs_amount = ZERO

    def _with_supplier_currency(
        self, data: PurchaseInvoiceCreate, *, vendor_id: UUID | None
    ) -> PurchaseInvoiceCreate:
        """Start a bill that names no currency in its supplier's (PG-12)."""
        if "currency_code" in data.model_fields_set or vendor_id is None:
            return data
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None or vendor.currency_code is None:
            return data
        return data.model_copy(update={"currency_code": vendor.currency_code})

    def _billed_orders(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID
    ) -> list[tuple[str, str | None, Decimal | None]]:
        """Return each order behind the bill: its number, currency and rate.

        The orders of the receipts the lines bill, and any order a line
        bills directly (a firm that types no receipts). In order-number
        order, a currency of None for rupees.
        """
        receipt_ids = {
            line.source_document_id
            for line in data.lines
            if line.source_document_line_id is not None
            and self._source_type(line.source_document_type)
            == PurchaseInvoiceSourceType.GOODS_RECEIPT.value
        }
        order_ids = {
            line.source_document_id
            for line in data.lines
            if line.source_document_line_id is not None
            and self._source_type(line.source_document_type)
            == PurchaseInvoiceSourceType.PURCHASE_ORDER.value
        }
        if receipt_ids:
            order_ids |= set(
                self._session.scalars(
                    select(GoodsReceipt.purchase_order_id).where(
                        GoodsReceipt.id.in_(receipt_ids),
                        GoodsReceipt.firm_id == firm_id,
                    )
                ).all()
            )
        if not order_ids:
            return []
        return [
            (
                number,
                normalize_currency(currency) if is_foreign(currency) else None,
                rate,
            )
            for number, currency, rate in self._session.execute(
                select(
                    PurchaseOrder.po_number,
                    PurchaseOrder.currency_code,
                    PurchaseOrder.exchange_rate,
                )
                .where(
                    PurchaseOrder.id.in_(order_ids),
                    PurchaseOrder.firm_id == firm_id,
                )
                .order_by(PurchaseOrder.po_number)
            ).all()
        ]

    def _with_order_currency(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID
    ) -> PurchaseInvoiceCreate:
        """Start a bill that names no currency in its order's (D-BUY-39).

        The order priced the goods in a currency and the receipt valued them
        at its rate, so the bill for them is in that currency -- rupees for a
        rupee order, whatever the supplier's own default. A rate the bill
        does not type is the order's; the supplier's bill usually carries its
        own, and the difference is then a price variance.
        """
        orders = self._billed_orders(data, firm_id=firm_id)
        if not orders:
            return data
        _, currency, rate = orders[0]
        # Set even when it is None: a currency the bill now states, so the
        # supplier's default does not replace a rupee order's rupees.
        update: dict[str, object] = {"currency_code": currency}
        if currency is not None and "exchange_rate" not in data.model_fields_set:
            update["exchange_rate"] = rate
        return data.model_copy(update=update)

    def _refuse_another_currency(
        self, data: PurchaseInvoiceCreate, *, firm_id: UUID
    ) -> None:
        """Refuse a bill in a currency other than its order's (D-BUY-39).

        The receipt valued the stock in rupees at the order's rate. A bill
        in another currency -- 1,000 USD against goods ordered and received
        for 1,000 rupees, or the reverse -- would post almost its whole
        value to price variance, so it is refused by name instead.

        Raises:
            ValidationError: Naming the order and both currencies.

        """
        billed = (
            normalize_currency(data.currency_code)
            if is_foreign(data.currency_code)
            else None
        )
        for number, currency, _ in self._billed_orders(data, firm_id=firm_id):
            if currency == billed:
                continue
            raise ValidationError(
                f"Purchase order {number} is in {currency or 'rupees'}, and "
                f"its goods were received at that value, so its bill is in "
                f"{currency or 'rupees'} too. This bill is in "
                f"{billed or 'rupees'}: bill it in {currency or 'rupees'}, or "
                "raise the order in the supplier's currency before receiving "
                "the goods.",
                details={"field": "currency_code"},
            )

    @staticmethod
    def _stage_currency(row: PurchaseInvoice) -> None:
        """Check the bill's currency and stamp its rupee totals (PG-12).

        A bill in rupees carries none: its own totals are rupees. One in
        another currency needs its rate, and its goods and its tax are each
        converted and rounded to the ledger on their own, then summed --
        rounding the sum is not rounding the parts. TCS under 206C(1H) is
        charged by an Indian seller, so a foreign bill carrying one is
        refused rather than posted.

        Raises:
            ValidationError: If a foreign currency has no rate, the code is
                not ISO, or a foreign bill carries TCS.

        """
        check_currency(row.currency_code, row.exchange_rate)
        if not is_foreign(row.currency_code) or row.exchange_rate is None:
            row.base_tax_total = None
            row.base_grand_total = None
            return
        if row.tcs_amount > ZERO:
            raise ValidationError(
                "TCS under 206C(1H) is charged by a seller in India; a bill in "
                "another currency carries none.",
                details={"field": "tcs_amount"},
            )
        base_tax = to_base(row.tax_total, row.exchange_rate)
        base_goods = to_base(row.grand_total - row.tax_total, row.exchange_rate)
        row.base_tax_total = base_tax
        row.base_grand_total = base_goods + base_tax

    @staticmethod
    def _in_rupees(amounts: dict[str, Decimal], rate: Decimal) -> dict[str, Decimal]:
        """Convert each tax head of a foreign bill at its rate, one by one."""
        return {code: to_base(amount, rate) for code, amount in amounts.items()}

    def _stage_tds(
        self, row: PurchaseInvoice, *, firm_id: UUID, override: Decimal | None
    ) -> dict[str, object] | None:
        """Stamp the bill's 194C/194J deduction; return what the trail keeps.

        The proposal is always worked out and kept on the bill, so an
        override shows beside the figure it replaced, and the trail records
        both. An override of more than nothing needs the supplier to be under
        194C or 194J -- the section is what the challan and the return file
        it under.

        Raises:
            ValidationError: If the override is negative, not less than the
                bill, or names a deduction for a supplier under neither
                section.

        """
        vendor = self._session.get(Vendor, row.vendor_id)
        if vendor is None:
            return None
        base = self._tds_base(row)
        proposal = self._tds_proposal(row, vendor, firm_id=firm_id)
        if proposal.section is None:
            if override is not None and override > ZERO:
                raise ValidationError(
                    "TDS on a bill is worked out under 194C or 194J. Set the "
                    "supplier's TDS section first, or deduct on the payment.",
                    details={"field": "tds_amount"},
                )
            return None
        deducted = proposal.proposed if override is None else quantize_ledger(override)
        if deducted < ZERO or (deducted > ZERO and deducted >= row.grand_total):
            raise ValidationError(
                "TDS deducted must be less than what the bill owes.",
                details={"field": "tds_amount"},
            )
        row.tds_proposed_amount = proposal.proposed
        row.tds_amount = deducted
        row.tds_base_amount = base
        row.tds_section = proposal.section if deducted > ZERO else None
        return {
            "tds_section": proposal.section,
            "tds_base_amount": str(base),
            "tds_rate_percent": str(proposal.rate_percent),
            "tds_rate_basis": proposal.rate_basis,
            "tds_threshold_crossed": proposal.threshold_crossed,
            "tds_proposed_amount": str(proposal.proposed),
            "tds_amount": str(deducted),
            "tds_overridden": override is not None and deducted != proposal.proposed,
        }

    @staticmethod
    def _tds_base(row: PurchaseInvoice) -> Decimal:
        """Return what 194C or 194J is worked on: the bill before GST.

        The one place the base is decided (D-BUY-37): the lines and the
        additional charges, which a contractor's or a professional's bill
        carries as part of the fee.
        """
        return quantize_ledger(row.subtotal + row.additional_charges)

    def _tds_proposal(
        self, row: PurchaseInvoice, vendor: Vendor, *, firm_id: UUID
    ) -> TdsProposal:
        """Work out the bill's 194C/194J proposal, as approval stamps it."""
        # Imported here: the finance services read this module's models.
        from app.finance.services.tds_sections import TdsSectionService

        return TdsSectionService(self._session).propose(
            vendor,
            firm_id=firm_id,
            on=row.invoice_date,
            bill_amount=self._tds_base(row),
            bill_total=row.grand_total,
            exclude_invoice_id=row.id,
        )

    def tds_proposal(self, invoice_id: UUID, *, firm_scope: UUID) -> TdsProposal:
        """Return what approving this bill would propose under 194C or 194J.

        Asked by the Approve dialog, so the figure it shows is worked on the
        base approval uses and cannot drift from it (D-BUY-37). A bill in
        another currency is outside both sections (PG-12) and is answered
        with no section and nothing proposed, as approval treats it.

        Raises:
            ResourceNotFoundError: If the bill, or its supplier, is not the
                firm's.

        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        vendor = self._session.get(Vendor, row.vendor_id)
        if vendor is None:
            raise ResourceNotFoundError("Supplier not found.")
        proposal = self._tds_proposal(row, vendor, firm_id=firm_scope)
        if is_foreign(row.currency_code):
            return replace(
                proposal,
                section=None,
                rate_percent=ZERO,
                rate_basis="",
                threshold_crossed="",
                due=ZERO,
                proposed=ZERO,
                applies=False,
            )
        return proposal

    def tolerance_breaches(self, row: PurchaseInvoice, *, firm_id: UUID) -> list[str]:
        """Return how a bill runs over its order beyond the firm's tolerance.

        BUY-10. Each line continuing an order -- directly, or through the
        receipt that received it -- is compared with the order line's rate:
        past ``bill_price_tolerance_percent`` it is named. The bill's total
        excess over the order prices past ``bill_tolerance_amount`` is named
        too. A bill typed with no order behind it has nothing to compare.
        """
        from app.goods_receipt.models import GoodsReceiptLine
        from app.purchase.models import PurchaseOrderLine
        from app.purchase.services.workflow_settings_service import (
            PurchaseWorkflowService,
        )

        policy = PurchaseWorkflowService(self._session).settings_response(firm_id)
        percent = policy.bill_price_tolerance_percent
        amount = policy.bill_tolerance_amount
        if percent is None and amount is None:
            return []
        breaches: list[str] = []
        excess = ZERO
        for line in self._session.scalars(
            select(PurchaseInvoiceLine)
            .where(
                PurchaseInvoiceLine.purchase_invoice_id == row.id,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
            .order_by(PurchaseInvoiceLine.line_number.asc())
        ).all():
            order_line_id = None
            if line.source_document_type == "PURCHASE_ORDER":
                order_line_id = line.source_document_line_id
            elif line.source_document_type == "GOODS_RECEIPT":
                received = self._session.get(
                    GoodsReceiptLine, line.source_document_line_id
                )
                order_line_id = (
                    None if received is None else received.purchase_order_line_id
                )
            ordered = (
                self._session.get(PurchaseOrderLine, order_line_id)
                if order_line_id is not None
                else None
            )
            if ordered is None:
                continue
            agreed = Decimal(str(ordered.unit_price))
            billed = Decimal(str(line.unit_price))
            over = billed - agreed
            if over <= ZERO:
                continue
            excess += over * Decimal(str(line.current_invoice_quantity))
            if percent is not None and agreed > ZERO:
                share = over / agreed * Decimal("100")
                if share > Decimal(str(percent)):
                    breaches.append(
                        f"line {line.line_number}: billed at {billed:.2f} against "
                        f"{agreed:.2f} ordered ({share:.1f}% over, tolerance "
                        f"{Decimal(str(percent)):.1f}%)"
                    )
        if amount is not None and excess > Decimal(str(amount)):
            breaches.append(
                f"the bill runs {self._q(excess):.2f} over its order's prices "
                f"(tolerance {Decimal(str(amount)):.2f})"
            )
        return breaches

    def _assert_within_tolerance(self, row: PurchaseInvoice, *, firm_id: UUID) -> None:
        """Refuse a bill past the firm's tolerance over its order (BUY-10).

        Raises:
            AuthorizationError: Naming each line and the total that run over.

        """
        breaches = self.tolerance_breaches(row, firm_id=firm_id)
        if breaches:
            raise AuthorizationError(
                f"{row.invoice_number} is priced past the firm's tolerance over "
                f"its order -- {'; '.join(breaches)}. Approving it needs the "
                "approve over tolerance permission (PURCHASE_APPROVE_OVER_"
                "TOLERANCE), or correct the bill."
            )

    def set_supplier_irn(
        self,
        invoice_id: UUID,
        irn: str | None,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PurchaseInvoice:
        """Record or clear the supplier's IRN on a bill (backlog 78 row 5).

        The IRN moves no money and no stock, so it may be written on an
        approved bill too -- the QR code is often read after the bill was
        booked. A cancelled bill is history and keeps what it had.
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == PurchaseInvoiceStatus.CANCELLED.value:
            raise ValidationError("A cancelled purchase invoice cannot be changed.")
        before = row.supplier_irn
        if before == irn:
            return row
        row.supplier_irn = irn
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="purchase_invoice.supplier_irn_set",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"supplier_irn": before},
            after_data={"supplier_irn": irn},
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
    ) -> PurchaseInvoice:
        """Cancel one purchase invoice, taking back the journal it posted."""
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status in {
            PurchaseInvoiceStatus.CANCELLED.value,
            PurchaseInvoiceStatus.CLOSED.value,
        }:
            raise ValidationError("This purchase invoice can no longer be cancelled.")
        self._assert_nothing_rests_on(row)
        before = row.status
        row.status = PurchaseInvoiceStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        if before == PurchaseInvoiceStatus.DRAFT.value:
            # The order and receipt a draft raised for itself carried nothing
            # yet -- the receipt completes only at approval -- so they go
            # with the bill. Flushed first so the receipt no longer reads as
            # billed. After approval the goods had arrived, and taking them
            # back is a purchase return, not a cancellation.
            self._session.flush()
            self._withdraw_raised(
                row,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=f"{row.invoice_number} was cancelled.",
            )
        if before == PurchaseInvoiceStatus.APPROVED.value:
            # Approval posted Dr goods-received-not-invoiced, Dr input tax,
            # Cr payable. Cancelling used to change the status and leave all
            # three, so the payable carried a bill that no longer existed --
            # and the receipt, no longer invoiced, could be cancelled too,
            # clearing the same accrual a second time (D-BUY-2, driven on
            # TEST01: 2300 left debited 600 on its own). The entry faces the
            # supplier, not the stock, so a mirror is the right reversal.
            # The assets its capital-goods lines raised go with it (PG-13),
            # unless one has been depreciated or disposed since.
            from app.fixed_assets.services import FixedAssetService

            FixedAssetService(self._session).stage_withdraw_for_invoice(
                row.id, invoice_number=row.invoice_number, actor_id=actor_id
            )
            self._reverse_invoice_posting(row, firm_scope=firm_scope, actor_id=actor_id)
        # Supplier credit set against this bill is free again: the bill's
        # payable is gone, the return's debit still stands (D-FIN-19). Nothing
        # posts -- applying it posted nothing either.
        from app.settlements.services.supplier_credits import (
            withdraw_credit_applications,
        )

        withdraw_credit_applications(
            self._session,
            firm_id=firm_scope,
            actor_id=actor_id,
            purchase_invoice_id=row.id,
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
            action="purchase_invoice.cancelled",
            entity_type="purchase_invoice",
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
    ) -> PurchaseInvoice:
        """Close one approved purchase invoice.

        Closing says a bill is finished with, so only an approved bill -- one
        that posted -- can be. It refused only one already closed, so a DRAFT
        bill that never posted, or a CANCELLED one, could be closed and then
        read as settled business (D-BUY-12, driven on TEST01 on 2026-09-18:
        PI-2026-2027-000008 closed from DRAFT).
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == PurchaseInvoiceStatus.CLOSED.value:
            raise ValidationError("This purchase invoice is already closed.")
        if row.status != PurchaseInvoiceStatus.APPROVED.value:
            raise ValidationError(
                f"Only approved purchase invoices can be closed; "
                f"{row.invoice_number} is {row.status.lower()}."
            )
        before = row.status
        row.status = PurchaseInvoiceStatus.CLOSED.value
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
            action="purchase_invoice.closed",
            entity_type="purchase_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> PurchaseInvoice:
        """Return one purchase invoice."""
        row = self._session.scalar(
            select(PurchaseInvoice).where(
                PurchaseInvoice.id == invoice_id,
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Purchase invoice not found.")
        return row

    def invoice_response(self, row: PurchaseInvoice) -> PurchaseInvoiceResponse:
        """Render one purchase invoice row as its API contract."""
        return self.invoice_responses([row])[0]

    def invoice_responses(
        self, rows: Sequence[PurchaseInvoice]
    ) -> list[PurchaseInvoiceResponse]:
        """Render a page of purchase invoices, reading each child table once.

        One query per child table for the whole page, grouped by invoice in
        Python, rather than about eight per invoice (backlog 56 C, step 3).
        The single-invoice builder is this with a list of one.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        sources = children_by_parent(
            self._session,
            PurchaseInvoiceSource,
            PurchaseInvoiceSource.purchase_invoice_id,
            ids,
        )
        lines = children_by_parent(
            self._session,
            PurchaseInvoiceLine,
            PurchaseInvoiceLine.purchase_invoice_id,
            ids,
            PurchaseInvoiceLine.line_number.asc(),
        )
        taxes = children_by_parent(
            self._session,
            PurchaseInvoiceLineTax,
            PurchaseInvoiceLineTax.purchase_invoice_line_id,
            [item.id for group in lines.values() for item in group],
            PurchaseInvoiceLineTax.sequence.asc(),
        )
        attachments = children_by_parent(
            self._session,
            PurchaseInvoiceAttachment,
            PurchaseInvoiceAttachment.purchase_invoice_id,
            ids,
        )
        notes = children_by_parent(
            self._session,
            PurchaseInvoiceNote,
            PurchaseInvoiceNote.purchase_invoice_id,
            ids,
        )
        accounting_events = children_by_parent(
            self._session,
            PurchaseInvoiceAccountingEvent,
            PurchaseInvoiceAccountingEvent.purchase_invoice_id,
            ids,
        )
        warnings = self._duplicate_warnings(rows)
        irn_warnings = self._irn_warnings(rows)
        vendors = {
            found[0]: (found[1], found[2])
            for found in self._session.execute(
                select(Vendor.id, Vendor.display_name, Vendor.code).where(
                    Vendor.id.in_({row.vendor_id for row in rows})
                )
            )
        }
        answer = [
            self._invoice_response(
                row,
                lines=lines[row.id],
                taxes=taxes,
                sources=sources[row.id],
                attachments=attachments[row.id],
                notes=notes[row.id],
                accounting_events=accounting_events[row.id],
                warning=warnings.get(row.id),
                irn_warning=irn_warnings.get(row.id),
                vendor=vendors.get(row.vendor_id),
            )
            for row in rows
        ]
        # The firm's own fields, one read for the page (MST-6).
        fields = document_attributes.responses_for_many(
            self._session, AttributeEntityType.PURCHASE_INVOICE, [r.id for r in rows]
        )
        # Uploaded files, counted for the page in one grouped read (PG-4).
        files = purchase_invoice_file_counts(self._session, ids)
        for response in answer:
            response.attributes = fields.get(response.id, [])
            response.attached_file_count = files.get(response.id, 0)
        return answer

    def _invoice_response(
        self,
        row: PurchaseInvoice,
        *,
        lines: list[PurchaseInvoiceLine],
        taxes: dict[UUID, list[PurchaseInvoiceLineTax]],
        sources: list[PurchaseInvoiceSource],
        attachments: list[PurchaseInvoiceAttachment],
        notes: list[PurchaseInvoiceNote],
        accounting_events: list[PurchaseInvoiceAccountingEvent],
        warning: str | None,
        vendor: tuple[str, str] | None,
        irn_warning: str | None = None,
    ) -> PurchaseInvoiceResponse:
        """Build one invoice's response from what the page already read."""
        return PurchaseInvoiceResponse(
            id=row.id,
            version=row.version,
            firm_id=row.firm_id,
            vendor_id=row.vendor_id,
            vendor_name=vendor[0] if vendor else "",
            vendor_code=vendor[1] if vendor else "",
            branch_id=row.branch_id,
            business_profile_id=row.business_profile_id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            supplier_invoice_number=row.supplier_invoice_number,
            supplier_invoice_date=row.supplier_invoice_date,
            supplier_irn=row.supplier_irn,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            status=PurchaseInvoiceStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_invoiced_quantity=row.total_already_invoiced_quantity,
            total_current_invoice_quantity=row.total_current_invoice_quantity,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            reverse_charge_tax_total=row.reverse_charge_tax_total,
            self_invoice_number=row.self_invoice_number,
            tds_section=row.tds_section,
            tds_base_amount=row.tds_base_amount,
            tds_proposed_amount=row.tds_proposed_amount,
            tds_amount=row.tds_amount,
            tcs_rate_percent=row.tcs_rate_percent,
            tcs_amount=row.tcs_amount,
            amount_owed=quantize_ledger(row.grand_total)
            + quantize_ledger(row.tcs_amount)
            - quantize_ledger(row.tds_amount),
            # In rupees (PG-12): at the bill's rate for a bill in another
            # currency, the bill's own figures for a rupee one.
            base_tax_total=(
                row.base_tax_total
                if row.base_tax_total is not None
                else quantize_ledger(row.tax_total)
            ),
            base_grand_total=(
                row.base_grand_total
                if row.base_grand_total is not None
                else quantize_ledger(row.grand_total)
            ),
            base_amount_owed=(
                row.base_grand_total
                if row.base_grand_total is not None
                else quantize_ledger(row.grand_total)
            )
            + quantize_ledger(row.tcs_amount)
            - quantize_ledger(row.tds_amount),
            approved_at=row.approved_at,
            closed_at=row.closed_at,
            cancel_reason=row.cancel_reason,
            close_reason=row.close_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            lines=[self._line_response(item, taxes.get(item.id, [])) for item in lines],
            sources=[self._source_response(item) for item in sources],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            accounting_events=[
                self._accounting_event_response(item) for item in accounting_events
            ],
            duplicate_warning=warning,
            irn_warning=irn_warning,
            credit_time_limit_warning=self._credit_time_limit_warning(row, lines),
        )

    @staticmethod
    def _credit_time_limit_warning(
        row: PurchaseInvoice, lines: list[PurchaseInvoiceLine]
    ) -> str | None:
        """Say whether the bill's credit is past its last date (backlog GST-3).

        CGST s.16(4): credit on a supplier's invoice is claimed by 30
        November after the end of the year it is dated in. The bill is
        judged on the day it is entered (`invoice_date`, which decides the
        return the credit goes into) against the supplier's own date. Only
        credit actually at stake is warned: a cancelled bill, or one whose
        tax is all blocked or ineligible, claims nothing. A warning, not a
        refusal -- the annual return's date is not recorded, so 30 November
        is only the outer limit, and the bill is still owed.
        """
        if row.status == PurchaseInvoiceStatus.CANCELLED.value:
            return None
        claims = row.reverse_charge_tax_total > 0 or any(
            line.itc_eligibility == "ELIGIBLE" and line.tax_amount > 0 for line in lines
        )
        if not claims:
            return None
        return credit_time_limit_warning(row.supplier_invoice_date, row.invoice_date)

    def timeline(
        self, *, invoice_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return the lifecycle timeline for one purchase invoice."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=invoice_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_invoices(self, *, firm_scope: UUID) -> list[PurchaseInvoice]:
        """List invoices still in draft, not yet approved."""
        return list(
            self._session.scalars(
                select(PurchaseInvoice).where(
                    PurchaseInvoice.firm_id == firm_scope,
                    PurchaseInvoice.is_deleted.is_(False),
                    PurchaseInvoice.status == PurchaseInvoiceStatus.DRAFT.value,
                )
            ).all()
        )

    def _owing(self, *, firm_scope: UUID) -> list[OutstandingInvoiceRecord]:
        """Every bill of the firm still owing something, as Record Payment sees it.

        One derivation for what a bill owes -- total less posted payments,
        completed returns off its lines and applied supplier credit, over the
        states that are debts at all -- so a report and the payment screen
        cannot disagree (D-RPT-2). Imported here because the settlement service
        imports this module's models.
        """
        from app.settlements.services.settlement_service import PaymentService

        return PaymentService(self._session).outstanding_invoices(
            firm_id=firm_scope, party_id=None
        )

    def _refuse_blocked(self, vendor_id: UUID | None) -> None:
        """Refuse a new or edited bill from a blocked supplier (backlog 69 row 4).

        Approving, paying and returning what was already billed stay open: a
        block stops new business, it does not cancel what was owed.
        """
        vendor = None if vendor_id is None else self._session.get(Vendor, vendor_id)
        if vendor is not None and vendor.status == "BLOCKED":
            why = f": {vendor.blocked_reason}" if vendor.blocked_reason else ""
            raise ValidationError(
                f"{vendor.display_name} is blocked{why}; no new bill can be "
                "entered from them."
            )

    def _vendor_names(self, vendor_ids: set[UUID]) -> dict[UUID, str]:
        """Read the display names of the vendors named, in one query."""
        if not vendor_ids:
            return {}
        return {
            vendor_id: name
            for part in chunks(list(vendor_ids))
            for vendor_id, name in self._session.execute(
                select(Vendor.id, Vendor.display_name).where(Vendor.id.in_(part))
            ).all()
        }

    def msme_dues_report(
        self, *, firm_scope: UUID, as_of: date | None = None
    ) -> list[PurchaseInvoiceMsmeDueRecord]:
        """List unpaid bills to micro and small suppliers, soonest first.

        Read off what Record Payment says is owed, so a bill paid in full
        leaves the list the day it is paid; only bills stamped with a legal
        date (``msme_pay_by``) are listed (backlog 68 row 2).
        """
        today = as_of or firm_today(self._session, firm_scope)
        owing = {
            record.invoice_id: record
            for record in self._owing(firm_scope=firm_scope)
            if not record.is_opening_bill
        }
        if not owing:
            return []
        rows = [
            row
            for part in chunks(list(owing))
            for row in self._session.execute(
                select(
                    PurchaseInvoice.id,
                    PurchaseInvoice.invoice_number,
                    PurchaseInvoice.supplier_invoice_number,
                    PurchaseInvoice.vendor_id,
                    PurchaseInvoice.invoice_date,
                    PurchaseInvoice.due_date,
                    PurchaseInvoice.msme_pay_by,
                    Vendor.display_name,
                    Vendor.udyam_number,
                    Vendor.msme_category,
                )
                .join(Vendor, Vendor.id == PurchaseInvoice.vendor_id)
                .where(
                    PurchaseInvoice.id.in_(part),
                    PurchaseInvoice.msme_pay_by.is_not(None),
                )
            ).all()
        ]
        records: list[PurchaseInvoiceMsmeDueRecord] = []
        for row in rows:
            days_left = (row.msme_pay_by - today).days
            records.append(
                PurchaseInvoiceMsmeDueRecord(
                    invoice_id=row.id,
                    invoice_number=row.invoice_number,
                    supplier_invoice_number=row.supplier_invoice_number,
                    vendor_id=row.vendor_id,
                    vendor_name=row.display_name,
                    udyam_number=row.udyam_number,
                    msme_category=row.msme_category,
                    invoice_date=row.invoice_date,
                    due_date=row.due_date,
                    pay_by=row.msme_pay_by,
                    days_left=days_left,
                    state=(
                        "OVERDUE"
                        if days_left < 0
                        else "DUE_SOON" if days_left <= 7 else "OPEN"
                    ),
                    outstanding_amount=owing[row.id].outstanding_amount,
                )
            )
        return sorted(records, key=lambda item: (item.pay_by, item.invoice_number))

    def overdue_report(
        self, *, firm_scope: UUID, due_within: int | None = None
    ) -> list[PurchaseInvoiceOverdueRecord]:
        """List the bills past their due date that still owe something.

        Judged on what is owed rather than on status: a bill paid in full used
        to stay here until somebody closed it by hand, and a DRAFT with a past
        due date was listed before it was approved (D-RPT-2). A bill entered
        without a due date is never overdue -- nothing derives one from the
        payment terms.
        """
        today = firm_today(self._session, firm_scope)
        # ``due_within`` turns the list round to what falls due from today
        # to that many days ahead (ACC-6): 0 is today, 7 the week ahead.
        last = None if due_within is None else today + timedelta(days=due_within)
        owing = [
            record
            for record in self._owing(firm_scope=firm_scope)
            if record.due_date is not None
            and (
                record.due_date < today
                if last is None
                else today <= record.due_date <= last
            )
        ]
        # The two things the row needs of the bill, never the whole row, and
        # in chunks: a firm's overdue bills can be more ids than one statement
        # may name.
        bills: dict[UUID, tuple[str | None, Decimal]] = {}
        if owing:
            bills = {
                bill_id: (number, total)
                for part in chunks([item.invoice_id for item in owing])
                for bill_id, number, total in self._session.execute(
                    select(
                        PurchaseInvoice.id,
                        PurchaseInvoice.supplier_invoice_number,
                        PurchaseInvoice.grand_total,
                    ).where(PurchaseInvoice.id.in_(part))
                ).all()
            }
        names = self._vendor_names(
            {record.party_id for record in owing if record.party_id is not None}
        )
        records: list[PurchaseInvoiceOverdueRecord] = []
        for record in owing:
            if record.due_date is None or record.party_id is None:  # pragma: no cover
                continue
            # A supplier's opening bill is owed and can be overdue like any
            # other, but it is not a purchase invoice, so the record carries
            # what the row would have said.
            row = bills.get(record.invoice_id)
            records.append(
                PurchaseInvoiceOverdueRecord(
                    invoice_id=record.invoice_id,
                    invoice_number=record.invoice_number,
                    supplier_invoice_number=None if row is None else row[0],
                    vendor_id=record.party_id,
                    vendor_name=names.get(record.party_id, str(record.party_id)),
                    invoice_date=record.invoice_date,
                    due_date=record.due_date,
                    days_overdue=max((today - record.due_date).days, 0),
                    days_until_due=max((record.due_date - today).days, 0),
                    grand_total=record.invoice_total if row is None else row[1],
                    allocated_amount=record.allocated_amount,
                    outstanding_amount=record.outstanding_amount,
                )
            )
        records.sort(key=lambda item: (item.due_date, item.invoice_number))
        return records

    def register_report(
        self,
        *,
        firm_scope: UUID,
        statuses: Sequence[str] | None = None,
        window: ReportWindow = WHOLE_HISTORY,
    ) -> list[PurchaseInvoiceRegisterRecord]:
        """Return the register report, optionally narrowed to some statuses.

        The pending report answers this shape too, rather than whole
        documents with their five extra reads per row (D-RPT-16).

        The supplier and the branch are named as well as identified, in one
        read each for the whole report: the grid derives its columns from the
        row, so a register of ids alone read as UUIDs (D-RPT-17).

        The total is in rupees: a bill in another currency shows what its
        journal posted, not its figure as typed (D-BUY-35).
        """
        rows = window.fetch(
            self._session,
            select(PurchaseInvoice)
            .where(
                PurchaseInvoice.firm_id == firm_scope,
                PurchaseInvoice.is_deleted.is_(False),
                *(
                    ()
                    if statuses is None
                    else (PurchaseInvoice.status.in_(list(statuses)),)
                ),
                *window.dated(PurchaseInvoice.invoice_date),
            )
            .order_by(
                PurchaseInvoice.invoice_date.desc(),
                PurchaseInvoice.created_at.desc(),
                PurchaseInvoice.id.desc(),
            ),
        )
        suppliers = vendor_names(self._session, (row.vendor_id for row in rows))
        branches = branch_names(self._session, (row.branch_id for row in rows))
        records = [
            PurchaseInvoiceRegisterRecord(
                invoice_id=row.id,
                invoice_number=row.invoice_number,
                supplier_invoice_number=row.supplier_invoice_number,
                vendor_id=row.vendor_id,
                vendor_name=suppliers.get(row.vendor_id, str(row.vendor_id)),
                branch_id=row.branch_id,
                branch_name=branches.get(row.branch_id, str(row.branch_id)),
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                grand_total=(
                    row.base_grand_total
                    if is_foreign(row.currency_code)
                    and row.base_grand_total is not None
                    else row.grand_total
                ),
                status=PurchaseInvoiceStatus(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[PurchaseInvoiceVendorOutstandingRecord]:
        """Report what is still owed to each supplier, and on how many bills.

        Summed from the same per-bill derivation Record Payment offers, so a
        supplier paid in full drops off the day the payment posts; it used to
        sum ``grand_total`` of every non-cancelled bill, drafts included, and
        never read an allocation (D-RPT-2). Largest debt first.
        """
        totals: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        counts: dict[UUID, int] = defaultdict(int)
        for record in self._owing(firm_scope=firm_scope):
            if record.party_id is None:  # pragma: no cover - always set
                continue
            totals[record.party_id] += record.outstanding_amount
            counts[record.party_id] += 1
        names = self._vendor_names(set(totals))
        records = [
            PurchaseInvoiceVendorOutstandingRecord(
                vendor_id=vendor_id,
                vendor_name=names.get(vendor_id, str(vendor_id)),
                outstanding_amount=self._q(amount),
                invoice_count=counts[vendor_id],
            )
            for vendor_id, amount in totals.items()
        ]
        records.sort(key=lambda item: (-item.outstanding_amount, item.vendor_name))
        return records

    def reconciliation_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PurchaseInvoiceReconciliationRecord]:
        """Say what is billed against each received line, and what is left.

        One row per source line, summed over the bills that still stand: a
        cancelled bill billed nothing, a draft has not billed yet (D-RPT-13).
        Most recently billed first.

        The window picks the source lines billed on a bill dated inside it;
        the sums still run over every bill of those lines. Grouped and paged
        in SQL, as the sales-invoice reconciliation is: reading every line of
        the firm took 5 s on the volume firm (backlog 56 C, step 4).
        """
        live = (
            PurchaseInvoice.firm_id == firm_scope,
            PurchaseInvoice.is_deleted.is_(False),
            PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
            PurchaseInvoiceLine.is_deleted.is_(False),
        )
        joined = (
            PurchaseInvoice,
            PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
        )
        in_window = (
            select(PurchaseInvoiceLine.source_document_line_id)
            .join(*joined)
            .where(*live, *window.dated(PurchaseInvoice.invoice_date))
        )
        is_draft = PurchaseInvoice.status == PurchaseInvoiceStatus.DRAFT.value
        quantity = PurchaseInvoiceLine.current_invoice_quantity
        grouped = (
            select(
                PurchaseInvoiceLine.source_document_line_id,
                func.coalesce(func.sum(case((is_draft, ZERO), else_=quantity)), 0),
                func.coalesce(func.sum(case((is_draft, quantity), else_=ZERO)), 0),
            )
            .join(*joined)
            .where(
                *live,
                PurchaseInvoiceLine.firm_id == firm_scope,
                PurchaseInvoiceLine.source_document_line_id.in_(in_window),
            )
            .group_by(PurchaseInvoiceLine.source_document_line_id)
            # Latest bill date first; the group key breaks a tie.
            .order_by(
                func.max(PurchaseInvoice.invoice_date).desc(),
                PurchaseInvoiceLine.source_document_line_id,
            )
        )
        total: int | None = None
        if window.page is not None:
            total = int(
                self._session.scalar(
                    select(func.count()).select_from(grouped.order_by(None).subquery())
                )
                or 0
            )
            grouped = grouped.offset((window.page - 1) * window.page_size).limit(
                window.page_size
            )
        sums = {
            line_id: (Decimal(str(billed)), Decimal(str(drafted)))
            for line_id, billed, drafted in self._session.execute(grouped).all()
        }
        lines: dict[UUID, list[tuple[PurchaseInvoiceLine, str]]] = {
            line_id: [] for line_id in sums
        }
        for part in chunks(list(sums)):
            for line, number in self._session.execute(
                select(PurchaseInvoiceLine, PurchaseInvoice.invoice_number)
                .join(*joined)
                .where(*live, PurchaseInvoiceLine.source_document_line_id.in_(part))
                .order_by(
                    PurchaseInvoice.invoice_date.desc(),
                    PurchaseInvoice.created_at.desc(),
                )
            ).all():
                lines[line.source_document_line_id].append((line, number))
        products = product_names(
            self._session, (found[0][0].product_id for found in lines.values())
        )
        result: list[PurchaseInvoiceReconciliationRecord] = []
        for line_id, (billed, drafted) in sums.items():
            newest, _ = lines[line_id][0]
            pending = self._q(newest.received_quantity - billed - drafted)
            result.append(
                PurchaseInvoiceReconciliationRecord(
                    source_document_type=PurchaseInvoiceSourceType(
                        newest.source_document_type
                    ),
                    source_document_id=newest.source_document_id,
                    source_document_number=newest.source_document_number,
                    source_document_line_id=newest.source_document_line_id,
                    source_document_line_number=newest.source_document_line_number,
                    product_id=newest.product_id,
                    product_code=products.get(newest.product_id, ("", ""))[0],
                    product_name=products.get(
                        newest.product_id, ("", str(newest.product_id))
                    )[1],
                    received_quantity=newest.received_quantity,
                    invoiced_quantity=self._q(billed),
                    draft_quantity=self._q(drafted),
                    pending_quantity=pending if pending >= ZERO else ZERO,
                    invoice_numbers=", ".join(number for _, number in lines[line_id]),
                )
            )
        return result if total is None else ReportRows(result, total_records=total)

    def export_invoices_csv(
        self, *, firm_scope: UUID, search: str | None = None
    ) -> str:
        """Export matching purchase invoices as CSV."""
        rows, _ = self.list_invoices(
            firm_scope=firm_scope,
            filters=PurchaseInvoiceListFilters(),
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
                "supplier_invoice_number",
                "invoice_date",
                "vendor_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.invoice_number,
                    row.supplier_invoice_number,
                    row.invoice_date.isoformat(),
                    str(row.vendor_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_invoices(
        self, data: PurchaseInvoiceImportRequest, *, firm_scope: UUID, actor_id: UUID
    ) -> list[PurchaseInvoice]:
        """Import a validated batch of purchase invoices atomically."""
        return [
            self.create_invoice(record, firm_id=firm_scope, actor_id=actor_id)
            for record in data.records
        ]

    def _replace_sources(
        self,
        row: PurchaseInvoice,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceSource).filter(
            PurchaseInvoiceSource.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = PurchaseInvoiceSource(
                purchase_invoice_id=row.id,
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

    @stamps_tax_rules(PurchaseInvoiceLine, "purchase_invoice_id")
    def _replace_lines(
        self,
        row: PurchaseInvoice,
        line_specs: list[dict[str, object]],
        *,
        firm_id: UUID,
        invoice_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
        own_receipts: frozenset[UUID] = frozenset(),
    ) -> dict[str, Decimal]:
        self._delete_line_taxes(row.id)
        self._session.query(PurchaseInvoiceLine).filter(
            PurchaseInvoiceLine.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            source_line: SourceLine | None
            if source_type == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
                # The line must be one of the receipt's own (D-BUY-17).
                source_line = posted_receipt_line(
                    self._session,
                    firm_id=firm_id,
                    receipt_id=_required_uuid(spec["source_document_id"]),
                    line_id=_required_uuid(spec["source_document_line_id"]),
                    verb="billed",
                    own_drafts=own_receipts,
                )
            else:
                source_line = self._session.scalar(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.id == spec["source_document_line_id"]
                    )
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            requested_quantity = self._q(Decimal(str(spec["current_invoice_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            invoice_uom_id = spec.get("invoice_uom_id")
            assert_quantity_fits_unit(
                self._session,
                quantity=requested_quantity,
                uom_id=invoice_uom_id or source_uom_id,
                product_id=self._product_id(source_line),
                firm_id=firm_id,
            )
            conversion_factor = self._q(
                Decimal(str(spec.get("conversion_factor", Decimal("1"))))
            )
            already_invoiced = self._already_invoiced_quantity(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
            )
            returned_unbilled = ZERO
            if isinstance(source_line, GoodsReceiptLine):
                # Goods sent back before any bill reached them are not the
                # supplier's to bill (D-BUY-26).
                returned_unbilled = self._q(
                    receipt_line_billing(self._session, [source_line])[
                        source_line.id
                    ].returned_unbilled
                )
            # In the source line's unit, which is what the cap below and
            # every later reader counts in: by the rule for the pair, else
            # through the product's stock unit, so 24 PIECE bills a receipt
            # of 2 BOX with only the box-to-piece rule. What was typed is
            # kept beside it and the line is costed from that: 17 PIECE at
            # 60.00 are 1,020.00, not 1.4167 boxes' 1,020.02 (D-PRC-37).
            typed = self._uom.continued_quantity(
                product_id=self._product_id(source_line),
                quantity=requested_quantity,
                from_uom_id=_optional_uuid(invoice_uom_id),
                to_uom_id=source_uom_id,
                on_date=invoice_date,
                firm_scope=firm_id,
                left=source_quantity - returned_unbilled - already_invoiced,
            )
            invoice_quantity = typed.quantity
            if typed.entered is not None:
                conversion_factor = typed.stored_factor
            # No request can lift this cap: a body flag the caller set switched
            # it off entirely, and 60 was billed against a receipt of 6
            # (D-BUY-15).
            if (
                invoice_quantity + already_invoiced
                > source_quantity - returned_unbilled
            ):
                left = max(source_quantity - returned_unbilled - already_invoiced, ZERO)
                # In the source line's unit, and saying so: "bills 1.5000
                # where 1.4167 is left" told somebody who had typed 18 PIECE
                # against a receipt in boxes nothing (D-PRC-62).
                unit = unit_named(self._session, source_uom_id)
                raise ValidationError(
                    "Invoice quantity exceeds the available source quantity: "
                    f"line {index} bills {plain_quantity(invoice_quantity)}{unit} "
                    f"where {plain_quantity(left)}{unit} is left to bill "
                    f"({plain_quantity(source_quantity)}{unit} received, "
                    f"{plain_quantity(already_invoiced)}{unit} on other bills, "
                    f"{plain_quantity(returned_unbilled)}{unit} returned before "
                    "billing)."
                )
            # What the line says wins; where it says nothing, the receipt's or
            # order's price carries over, as its discount rate does. It used to
            # default to zero, so a bill sent without prices was worth nothing
            # (D-BUY-3).
            stated_price = spec.get("unit_price")
            typed_price: Decimal | None = None
            if stated_price is None:
                stated_price = getattr(source_line, "unit_price", None) or ZERO
            else:
                # Typed for the unit the line was typed in; the row keeps the
                # price of one of the source line's unit (60.00 a piece is
                # 720.00 a box, exactly, so a bill at the receipt's own price
                # shows no variance).
                typed_price = self._q(Decimal(str(stated_price)))
                stated_price = typed.price_per_source_unit(typed_price)
            unit_price = self._q(Decimal(str(stated_price)))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            # Worth what was typed: seventeen pieces at a piece's price.
            gross_amount = self._q(
                typed.worth(typed_price=typed_price, source_price=unit_price)
            )
            if (
                typed.entered is not None
                and typed_price is None
                and already_invoiced > ZERO
                and invoice_quantity + already_invoiced
                == source_quantity - returned_unbilled
            ):
                # The part that completes the source line takes what the
                # earlier parts left of its worth, so the bills of a receipt
                # add up to the receipt to the paisa however a box divides.
                gross_amount = self._completing_worth(
                    firm_id=firm_id,
                    source_line_id=source_line.id,
                    whole=(source_quantity - returned_unbilled) * unit_price,
                    price=unit_price,
                    otherwise=gross_amount,
                )
            line_discount = self._line_discount(
                spec=spec, source_line=source_line, gross=gross_amount
            )
            discount_amount = line_discount.amount
            # The source line's share of the order's whole-order discount, for
            # the part of it billed here, comes off before tax (D-BUY-19).
            bill_share = min(
                inherited_share(
                    getattr(source_line, "bill_discount_amount", ZERO) or ZERO,
                    part=invoice_quantity,
                    whole=source_quantity,
                ),
                self._q(gross_amount - discount_amount),
            )
            line_tax = self._resolve_tax(
                document_id=row.id,
                line_number=index,
                invoice_date=invoice_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                vendor_id=row.vendor_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                product_id=self._product_id(source_line),
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                # Taxed on what the line is worth, which for a line typed
                # in another unit is not its stored quantity times its
                # price (D-PRC-37).
                invoice_value=self._line_net_amount(
                    quantity=Decimal("1"),
                    unit_price=gross_amount,
                    discount_amount=discount_amount + bill_share,
                    charges_amount=charges_amount,
                ),
                actor_id=actor_id,
            )
            tax_amount = line_tax.total
            eligibility = self._itc_eligibility(
                spec.get("itc_eligibility"),
                product_id=self._product_id(source_line),
                line_tax=line_tax,
            )
            net_amount = self._q(
                gross_amount
                - discount_amount
                - bill_share
                + charges_amount
                + tax_amount
            )
            capital, asset_class_id = self._capital_goods(
                spec, firm_id=firm_id, source_line=source_line
            )
            line = PurchaseInvoiceLine(
                purchase_invoice_id=row.id,
                firm_id=firm_id,
                line_number=index,
                source_document_type=source_type,
                source_document_id=spec["source_document_id"],
                source_document_number=self._source_document_number(spec, source_line),
                source_document_line_id=source_line.id,
                source_document_line_number=self._source_line_number(source_line),
                product_id=self._product_id(source_line),
                description=self._source_description(source_line),
                received_quantity=source_quantity,
                already_invoiced_quantity=already_invoiced,
                current_invoice_quantity=invoice_quantity,
                unit_price=unit_price,
                discount_percent=line_discount.percent,
                discount_amount=discount_amount,
                bill_discount_amount=bill_share,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=line_tax.profile_id,
                itc_eligibility=eligibility,
                is_capital_goods=capital,
                asset_class_id=asset_class_id,
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                # A line that names no unit bills in its source line's --
                # the quantity check above already read it that way, and a
                # line stored with none shows a blank unit in the HSN
                # summary (D-BUY-49).
                purchase_uom_id=spec.get("purchase_uom_id") or source_uom_id,
                invoice_uom_id=invoice_uom_id or source_uom_id,
                conversion_factor=conversion_factor,
                entered_quantity=typed.entered,
                conversion_version=spec.get("conversion_version"),
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
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
            # Flushed here so the components have a line id to hang from. The
            # lines are rebuilt on every edit; `_delete_line_taxes` takes the
            # components off first, because the bulk delete below bypasses the
            # ORM cascade and SQLite enforces none.
            self._session.flush()
            for sequence, component in enumerate(line_tax.components, start=1):
                self._session.add(
                    PurchaseInvoiceLineTax(
                        purchase_invoice_line_id=line.id,
                        firm_id=firm_id,
                        sequence=sequence,
                        tax_component_id=component.tax_component_id,
                        component_code=component.code,
                        component_label=component.label,
                        percentage=component.percentage,
                        base_amount=component.base_amount,
                        amount=component.amount,
                        included_in_price=component.included_in_price,
                        # Credit the line gives up is never recoverable,
                        # whatever the component says (backlog 78 row 1).
                        # Reverse charge keeps the component's own: its
                        # credit is claimed apart, in 4(A)(3).
                        recoverable=component.recoverable
                        and (line_tax.reverse_charge or eligibility == "ELIGIBLE"),
                        reverse_charge=line_tax.reverse_charge,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
                if line_tax.reverse_charge and not component.included_in_price:
                    totals["reverse_charge_tax_total"] += component.amount
            totals["total_source_quantity"] += source_quantity
            totals["total_already_invoiced_quantity"] += already_invoiced
            totals["total_current_invoice_quantity"] += invoice_quantity
            totals["line_discount_total"] += discount_amount
            # subtotal is the taxable base: gross less discount, before tax and
            # before charges. Line charges used to be folded in here, which made
            # this module's subtotal mean something different from every other
            # document's; they are carried separately and added to grand_total.
            totals["subtotal"] += self._q(gross_amount - discount_amount - bill_share)
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        totals["reverse_charge_tax_total"] += ZERO
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: PurchaseInvoice,
        attachments: list[PurchaseInvoiceAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceAttachment).filter(
            PurchaseInvoiceAttachment.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                PurchaseInvoiceAttachment(
                    purchase_invoice_id=row.id,
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
        row: PurchaseInvoice,
        notes: list[PurchaseInvoiceNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(PurchaseInvoiceNote).filter(
            PurchaseInvoiceNote.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                PurchaseInvoiceNote(
                    purchase_invoice_id=row.id,
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
        self, row: PurchaseInvoice, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(PurchaseInvoiceAccountingEvent).filter(
            PurchaseInvoiceAccountingEvent.purchase_invoice_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (
                PurchaseInvoiceAccountingEventType.PURCHASE_EXPENSE.value,
                "Purchase Expense",
                "DEBIT",
                row.subtotal,
            ),
            (
                PurchaseInvoiceAccountingEventType.INPUT_TAX.value,
                "Input Tax",
                "DEBIT",
                row.tax_total,
            ),
            (
                PurchaseInvoiceAccountingEventType.ACCOUNTS_PAYABLE.value,
                "Accounts Payable",
                "CREDIT",
                row.grand_total,
            ),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                PurchaseInvoiceAccountingEvent(
                    purchase_invoice_id=row.id,
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
        self,
        data: PurchaseInvoiceCreate,
        firm_id: UUID,
        *,
        own_receipts: frozenset[UUID] = frozenset(),
    ) -> tuple[dict[str, UUID], list[dict[str, object]], list[dict[str, object]]]:
        if any(line.source_document_line_id is None for line in data.lines):
            # The chain turns product lines into receipt lines for a firm that
            # switched its stages off; one still bare here is a firm that did
            # not, or a mixture the chain refused to guess at.
            raise ValidationError(
                "Each bill line must name the goods receipt line it bills."
            )
        if any(line.product_id is not None for line in data.lines):
            raise ValidationError(
                "A bill line names either a goods receipt line or a product, "
                "not both."
            )
        if any(line.free_quantity is not None for line in data.lines):
            raise ValidationError(
                "Free goods are the goods receipt's. A bill line naming a "
                "receipt cannot state its own."
            )
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
        # set was all it took to bill a purchase order for ten when nothing
        # had arrived -- 1,180 owed to the supplier, 1,000 of it booked as a
        # price variance, and not one unit on the shelf. Checked on the lines
        # as well as the sources, since a line names its own source type.
        if any(
            self._source_type(item["source_document_type"])
            == PurchaseInvoiceSourceType.PURCHASE_ORDER.value
            for item in (*sources, *lines)
        ):
            raise ValidationError(
                "A supplier bill is raised against the goods receipt that "
                "brought the goods in, never straight against the purchase "
                "order. Receive the goods first."
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
            if source_type == PurchaseInvoiceSourceType.GOODS_RECEIPT.value:
                receipt = self._session.scalar(
                    select(GoodsReceipt).where(
                        GoodsReceipt.id == source_id,
                        GoodsReceipt.firm_id == firm_id,
                        GoodsReceipt.is_deleted.is_(False),
                    )
                )
                if receipt is None:
                    raise ResourceNotFoundError("Goods receipt not found.")
                require_posted_receipt(
                    receipt, "billed", own_draft=receipt.id in own_receipts
                )
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

    def _stamp_raised(
        self,
        row: PurchaseInvoice,
        orders: Sequence[PurchaseOrder],
        receipts: Sequence[GoodsReceipt],
    ) -> None:
        """Mark the order and receipt this bill raised as its own."""
        for order in orders:
            order.raised_by_purchase_invoice_id = row.id
        for receipt in receipts:
            receipt.raised_by_purchase_invoice_id = row.id

    def _raised_receipts(self, row: PurchaseInvoice) -> list[GoodsReceipt]:
        """Return the goods receipts this bill raised for itself."""
        return list(
            self._session.scalars(
                select(GoodsReceipt).where(
                    GoodsReceipt.raised_by_purchase_invoice_id == row.id,
                    GoodsReceipt.firm_id == row.firm_id,
                    GoodsReceipt.is_deleted.is_(False),
                )
            ).all()
        )

    def _withdraw_raised(
        self,
        row: PurchaseInvoice,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str,
    ) -> None:
        """Cancel the draft receipt and the order this bill raised for itself.

        Only what it raised, and only while nothing has arrived: a receipt a
        person raised is theirs whatever the firm's stage says now, and a
        completed receipt put stock on the shelf that a purchase return, not
        a cancellation, takes back.
        """
        receipts = GoodsReceiptService(self._session)
        for receipt in self._raised_receipts(row):
            if receipt.status == GoodsReceiptStatus.DRAFT.value:
                receipts.stage_cancel(
                    receipt.id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
                )
        orders = PurchaseService(self._session)
        for order in self._session.scalars(
            select(PurchaseOrder).where(
                PurchaseOrder.raised_by_purchase_invoice_id == row.id,
                PurchaseOrder.firm_id == row.firm_id,
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.status.in_(
                    (
                        PurchaseOrderStatus.DRAFT.value,
                        PurchaseOrderStatus.SUBMITTED.value,
                        PurchaseOrderStatus.APPROVED.value,
                    )
                ),
            )
        ).all():
            orders.stage_cancel(
                order.id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
            )

    def _refuse_foreign_lines(self, row: PurchaseInvoice, *, firm_id: UUID) -> None:
        """Refuse a saved bill whose line bills another receipt's line."""
        for line in self._session.scalars(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.purchase_invoice_id == row.id,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
        ):
            if (
                line.source_document_type
                == PurchaseInvoiceSourceType.GOODS_RECEIPT.value
            ):
                posted_receipt_line(
                    self._session,
                    firm_id=firm_id,
                    receipt_id=line.source_document_id,
                    line_id=line.source_document_line_id,
                    verb="billed",
                )

    def _refuse_past_left_to_bill(self, row: PurchaseInvoice) -> None:
        """Refuse a bill for more of a receipt line than is left to bill.

        Checked at approval as well as on save, because a return can complete
        between the two: a draft bill for all 6 of a receipt line is refused
        once 2 of them have gone back before billing (D-BUY-26). Left to bill
        is what was accepted, less approved bills, less what went back first.
        """
        quantities: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        for line_id, quantity in self._session.execute(
            select(
                PurchaseInvoiceLine.source_document_line_id,
                PurchaseInvoiceLine.current_invoice_quantity,
            ).where(
                PurchaseInvoiceLine.purchase_invoice_id == row.id,
                PurchaseInvoiceLine.source_document_type
                == PurchaseInvoiceSourceType.GOODS_RECEIPT.value,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
        ).all():
            quantities[line_id] += self._q(quantity)
        if not quantities:
            return
        receipt_lines = self._session.scalars(
            select(GoodsReceiptLine).where(GoodsReceiptLine.id.in_(list(quantities)))
        ).all()
        positions = receipt_line_billing(
            self._session, receipt_lines, except_invoice_id=row.id
        )
        numbers: dict[UUID, str] = {
            receipt_id: number
            for receipt_id, number in self._session.execute(
                select(GoodsReceipt.id, GoodsReceipt.grn_number).where(
                    GoodsReceipt.id.in_(
                        {line.goods_receipt_id for line in receipt_lines}
                    )
                )
            ).all()
        }
        refused: list[str] = []
        for line in sorted(
            receipt_lines, key=lambda item: (item.goods_receipt_id, item.line_number)
        ):
            position = positions[line.id]
            if quantities[line.id] <= self._q(position.left_to_bill):
                continue
            # Counted in the receipt line's unit, which is what the cap
            # counts in, and said so: "1.5000 where 1.4167 is left" told
            # somebody who typed 18 PIECE nothing (D-PRC-62).
            unit = unit_named(
                self._session, line.purchase_uom_id or line.inventory_uom_id
            )
            refused.append(
                f"{numbers.get(line.goods_receipt_id, 'the receipt')} line "
                f"{line.line_number} bills {plain_quantity(quantities[line.id])}"
                f"{unit} where {plain_quantity(position.left_to_bill)}{unit} is "
                f"left to bill ({plain_quantity(position.accepted)}{unit} "
                f"received, {plain_quantity(position.billed)}{unit} billed, "
                f"{plain_quantity(position.returned_unbilled)}{unit} returned "
                "before billing)"
            )
        if refused:
            raise ValidationError(
                f"{row.invoice_number} bills more than is left to bill: "
                + "; ".join(refused)
                + ". Change the bill's quantity to what the supplier billed for "
                "the goods the firm kept."
            )

    def _validate_line_sources(
        self, lines: list[dict[str, object]], source_ids: set[UUID]
    ) -> None:
        for line in lines:
            if line["source_document_id"] not in source_ids:
                raise ValidationError(
                    "Every invoice line must reference a selected source document."
                )

    def _tax_by_component(
        self, invoice_id: UUID, *, reverse_charge: bool = False
    ) -> dict[str, Decimal]:
        """Sum the bill's tax per component code, off the rows its lines keep.

        What the posting splits the input tax by, one account per GST head
        (D-CMP-20). Empty for a bill whose lines carry no rows -- one written
        before they existed -- and the posting then books the total as it
        always did.

        With ``reverse_charge`` it sums the other half instead: the tax the
        firm owes itself under reverse charge (backlog 68 row 8), which the
        supplier did not charge and the payable never includes.
        """
        totals: dict[str, Decimal] = {}
        for code, amount in self._session.execute(
            select(
                PurchaseInvoiceLineTax.component_code,
                func.coalesce(func.sum(PurchaseInvoiceLineTax.amount), 0),
            )
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .where(
                PurchaseInvoiceLine.purchase_invoice_id == invoice_id,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLineTax.is_deleted.is_(False),
                PurchaseInvoiceLineTax.included_in_price.is_(False),
                PurchaseInvoiceLineTax.reverse_charge.is_(reverse_charge),
                # Only what is claimed is input tax; the rest is a cost
                # (backlog 78 row 1). Reverse charge keeps all its heads:
                # the liability is owed whether or not the credit is.
                (
                    true()
                    if reverse_charge
                    else PurchaseInvoiceLineTax.recoverable.is_(True)
                ),
            )
            .group_by(PurchaseInvoiceLineTax.component_code)
        ).all():
            totals[code] = self._q(Decimal(str(amount)))
        return totals

    def _blocked_tax(self, invoice_id: UUID) -> Decimal:
        """Sum the tax on the bill the firm may not claim (backlog 78 row 1).

        Charged by the supplier and part of the payable, but blocked under
        s.17(5) or otherwise ineligible: the posting books it as a cost of the
        purchase rather than as input tax.
        """
        total = self._session.scalar(
            select(func.coalesce(func.sum(PurchaseInvoiceLineTax.amount), 0))
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .where(
                PurchaseInvoiceLine.purchase_invoice_id == invoice_id,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLineTax.is_deleted.is_(False),
                PurchaseInvoiceLineTax.included_in_price.is_(False),
                PurchaseInvoiceLineTax.reverse_charge.is_(False),
                PurchaseInvoiceLineTax.recoverable.is_(False),
            )
        )
        return self._q(Decimal(str(total or 0)))

    def _capital_goods(
        self,
        spec: dict[str, object],
        *,
        firm_id: UUID,
        source_line: SourceLine | None = None,
    ) -> tuple[bool, UUID | None]:
        """Return whether a line is capital goods, and its asset class (PG-13).

        A class on a line that is not capital goods is dropped rather than
        kept, so the two cannot disagree. A line billing a receipt line that
        was received as capital goods is capital goods (D-BUY-40): silence
        takes the mark, and unticking it is refused, because nothing came
        into stock for the bill to clear.

        Raises:
            ValidationError: If a capital-goods line names no class, or one
                that is not the firm's live, active class; or a line received
                as capital goods is billed as stock.

        """
        stated = spec.get("is_capital_goods")
        received_as_capital = isinstance(source_line, GoodsReceiptLine) and bool(
            source_line.is_capital_goods
        )
        if received_as_capital and stated is False:
            raise ValidationError(
                f"Line {spec.get('line_number')} was received as capital "
                "goods, so nothing entered stock for this bill to clear. "
                "Tick capital goods and choose its asset class.",
                details={"field": "is_capital_goods"},
            )
        if not (stated or received_as_capital):
            return False, None
        # Imported here: fixed assets read this module's models.
        from app.fixed_assets.models import AssetClass

        class_id = _optional_uuid(spec.get("asset_class_id"))
        line_number = spec.get("line_number")
        if class_id is None:
            raise ValidationError(
                f"Line {line_number} is capital goods: choose its asset class.",
                details={"field": "asset_class_id"},
            )
        klass = self._session.get(AssetClass, class_id)
        if (
            klass is None
            or klass.is_deleted
            or klass.firm_id != firm_id
            or not klass.is_active
        ):
            raise ValidationError(
                f"Line {line_number} names an asset class that is not one of "
                "this firm's active classes.",
                details={"field": "asset_class_id"},
            )
        return True, class_id

    def _itc_eligibility(
        self,
        stated: object,
        *,
        product_id: UUID | None,
        line_tax: _LineTax,
    ) -> str:
        """Decide whether a line's tax is claimable credit (backlog 78 row 1).

        What the line says wins; then the product's own setting where it is
        not ELIGIBLE; then a tax rule's *Input credit blocked*; else ELIGIBLE.
        The product before the rule because it is the narrower statement: a
        rule speaks for a class of goods, the product for this one.
        """
        if stated:
            return str(stated)
        product = self._session.get(Product, product_id) if product_id else None
        if product is not None and (product.itc_eligibility or "ELIGIBLE") != (
            "ELIGIBLE"
        ):
            return str(product.itc_eligibility)
        if line_tax.input_credit_allowed is False:
            return "BLOCKED"
        return "ELIGIBLE"

    def _delete_line_taxes(self, invoice_id: UUID) -> None:
        """Take the tax components off every line of one invoice.

        The lines are removed with a bulk `query().delete()`, which never
        loads them, so the ORM cascade does not fire; PostgreSQL's
        `ondelete="CASCADE"` would take the components anyway, but SQLite
        enforces no foreign keys under the unit suite and would leave them
        orphaned. Deleting them by name first is the same on both.
        """
        line_ids = select(PurchaseInvoiceLine.id).where(
            PurchaseInvoiceLine.purchase_invoice_id == invoice_id
        )
        self._session.query(PurchaseInvoiceLineTax).filter(
            PurchaseInvoiceLineTax.purchase_invoice_line_id.in_(line_ids)
        ).delete(synchronize_session=False)

    def _delete_children(self, invoice_id: UUID) -> None:
        self._session.query(PurchaseInvoiceAccountingEvent).filter(
            PurchaseInvoiceAccountingEvent.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._delete_line_taxes(invoice_id)
        self._session.query(PurchaseInvoiceLine).filter(
            PurchaseInvoiceLine.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceSource).filter(
            PurchaseInvoiceSource.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceAttachment).filter(
            PurchaseInvoiceAttachment.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(PurchaseInvoiceNote).filter(
            PurchaseInvoiceNote.purchase_invoice_id == invoice_id
        ).delete(synchronize_session=False)

    def _resolve_tax(
        self,
        *,
        invoice_date: date,
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
    ) -> _LineTax:
        """Work out the line's tax, and keep everything that decided it.

        This used to return one number and discard the rest, which is why a
        bill line recorded `tax_amount` and a NULL `tax_profile_id` -- the
        profile it resolved was thrown away along with the component breakup.
        The input-tax ledger and GSTR-3B need the breakup (D-CMP-20), so both
        are returned and stored.
        """
        if invoice_value <= ZERO:
            return _LineTax(profile_id=tax_profile_id, total=ZERO, components=[])
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
                return _LineTax(profile_id=None, total=ZERO, components=[])
            tax_profile_id = resolved.id
        else:
            tax_service.assert_profile_effective_on(
                tax_profile_id, invoice_date, firm_scope=firm_id
            )
        request = TaxRuleSimulationRequest(
            # The supply's own nature, not just the document's name: a
            # supplier in another state charges IGST (D-CMP-14).
            transaction_type=self._tax.inward_transaction_type(
                "PURCHASE_INVOICE",
                firm_id=firm_id,
                branch_id=branch_id,
                vendor_id=vendor_id,
            ),
            transaction_date=invoice_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            vendor_id=vendor_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={
                "source": "purchase_invoice",
                "document_type": "PURCHASE_INVOICE",
            },
        )
        response = self._tax.simulate(
            request,
            firm_scope=firm_id,
            actor_id=actor_id,
            document_id=document_id,
            line_number=line_number,
        )
        return _LineTax(
            # The resolved profile, not the one the caller sent: a client that
            # names none still gets the product's, and the line should say so.
            profile_id=response.applied_tax_profile_id or tax_profile_id,
            total=self._q(response.total_tax_amount),
            reverse_charge=response.reverse_charge,
            input_credit_allowed=response.input_credit_allowed,
            components=[
                _LineTaxComponent(
                    tax_component_id=component.tax_component_id,
                    code=component.code,
                    label=component.label,
                    percentage=self._q(component.percentage),
                    base_amount=self._q(response.base_amount),
                    amount=self._q(component.amount),
                    included_in_price=component.included_in_price,
                    recoverable=component.recoverable,
                )
                for component in response.applied_components
            ],
        )

    def _source_quantity(
        self, spec: dict[str, object], source_line: SourceLine
    ) -> Decimal:
        if (
            self._source_type(spec["source_document_type"])
            == PurchaseInvoiceSourceType.GOODS_RECEIPT.value
        ):
            return self._q(getattr(source_line, "accepted_quantity", ZERO))
        return self._q(getattr(source_line, "ordered_quantity", ZERO))

    def _completing_worth(
        self,
        *,
        firm_id: UUID,
        source_line_id: UUID,
        whole: Decimal,
        price: Decimal,
        otherwise: Decimal,
    ) -> Decimal:
        """Return what the part that completes a source line is worth.

        What is left of the whole line's worth after the parts billed
        before, each rounded to the paisa as the ledger rounds it: rounding
        the sum is not rounding the parts. Only where every earlier part was
        billed at the source line's own price -- one that typed another
        price is the supplier's own figure, and this part is then simply
        worth what it bills (``otherwise``).
        """
        earlier = self._session.execute(
            select(PurchaseInvoiceLine.unit_price, PurchaseInvoiceLine.gross_amount)
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.source_document_line_id == source_line_id,
            )
        ).all()
        if any(self._q(Decimal(str(was))) != price for was, _ in earlier):
            return otherwise
        left = quantize_ledger(whole) - sum(
            (quantize_ledger(Decimal(str(gross))) for _, gross in earlier), ZERO
        )
        return self._q(left) if left > ZERO else otherwise

    def _already_invoiced_quantity(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> Decimal:
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(PurchaseInvoiceLine.current_invoice_quantity), ZERO
                )
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.firm_id == firm_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.source_document_line_id == source_document_line_id,
            )
        )
        return self._q(total or ZERO)

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: SourceLine) -> UUID | None:
        return getattr(source_line, "purchase_uom_id", None) or getattr(
            source_line, "inventory_uom_id", None
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

    def _validate_supplier_invoice_number(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_invoice_number: str,
        current_id: UUID | None = None,
    ) -> None:
        if self._duplicate_warning(
            firm_id=firm_id,
            vendor_id=vendor_id,
            supplier_invoice_number=supplier_invoice_number,
            current_id=current_id,
        ):
            return

    def _duplicate_warnings(self, rows: Sequence[PurchaseInvoice]) -> dict[UUID, str]:
        """Answer `_duplicate_warning` for a page of invoices in one query."""
        holders: dict[tuple[UUID, UUID, str], set[UUID]] = defaultdict(set)
        for found_id, firm_id, vendor_id, number in self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoice.firm_id,
                PurchaseInvoice.vendor_id,
                PurchaseInvoice.supplier_invoice_number,
            ).where(
                PurchaseInvoice.firm_id.in_({row.firm_id for row in rows}),
                PurchaseInvoice.supplier_invoice_number.in_(
                    {row.supplier_invoice_number for row in rows}
                ),
                PurchaseInvoice.is_deleted.is_(False),
            )
        ):
            holders[(firm_id, vendor_id, number)].add(found_id)
        return {
            row.id: (
                "A purchase invoice with this supplier invoice number already exists."
            )
            for row in rows
            if holders.get(
                (row.firm_id, row.vendor_id, row.supplier_invoice_number), set()
            )
            - {row.id}
        }

    def _irn_warnings(self, rows: Sequence[PurchaseInvoice]) -> dict[UUID, str]:
        """Say which bills' IRNs want a look, for a page in a fixed few reads.

        Backlog 78 row 5: a supplier past the e-invoicing threshold issues no
        valid B2B tax invoice without an IRN (CGST rule 48(4)), so credit on
        its bill is at risk. Warned when the firm's check is WARN (the
        default), the supplier is marked as e-invoicing and the bill carries
        none. Separately, an IRN names one invoice, so a second bill carrying
        it is the same bill entered twice -- said whatever the setting.
        """
        live = [
            row for row in rows if row.status != PurchaseInvoiceStatus.CANCELLED.value
        ]
        if not live:
            return {}
        found: dict[UUID, str] = {}
        settings = GstComplianceService(self._session)
        checking = {
            firm_id
            for firm_id in {row.firm_id for row in live}
            if settings.settings_response(firm_id).supplier_irn_check == "WARN"
        }
        missing = [
            row for row in live if row.firm_id in checking and not row.supplier_irn
        ]
        if missing:
            e_invoicing = {
                vendor_id: name
                for vendor_id, name in self._session.execute(
                    select(Vendor.id, Vendor.display_name).where(
                        Vendor.id.in_({row.vendor_id for row in missing}),
                        Vendor.issues_e_invoices.is_(True),
                    )
                )
            }
            for row in missing:
                if row.vendor_id in e_invoicing:
                    found[row.id] = (
                        f"{e_invoicing[row.vendor_id]} e-invoices, and this bill "
                        "has no IRN: without one it is not a valid tax invoice "
                        "(CGST rule 48(4)) and its credit is at risk. Record "
                        "the IRN printed under the bill's QR code."
                    )
        irns = {row.supplier_irn for row in live if row.supplier_irn}
        if irns:
            holders: dict[tuple[UUID, str], list[tuple[UUID, str]]] = defaultdict(list)
            for found_id, firm_id, irn, number in self._session.execute(
                select(
                    PurchaseInvoice.id,
                    PurchaseInvoice.firm_id,
                    PurchaseInvoice.supplier_irn,
                    PurchaseInvoice.invoice_number,
                ).where(
                    PurchaseInvoice.supplier_irn.in_(irns),
                    PurchaseInvoice.status != PurchaseInvoiceStatus.CANCELLED.value,
                    PurchaseInvoice.is_deleted.is_(False),
                )
            ):
                holders[(firm_id, irn)].append((found_id, number))
            for row in live:
                if not row.supplier_irn:
                    continue
                others = sorted(
                    number
                    for found_id, number in holders.get(
                        (row.firm_id, row.supplier_irn), []
                    )
                    if found_id != row.id
                )
                if others:
                    found[row.id] = (
                        f"{', '.join(others)} already carries this IRN: an IRN "
                        "names one invoice, so this may be the same bill twice."
                    )
        return found

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        vendor_id: UUID,
        supplier_invoice_number: str,
        current_id: UUID | None,
    ) -> str | None:
        statement = select(PurchaseInvoice.id).where(
            PurchaseInvoice.firm_id == firm_id,
            PurchaseInvoice.vendor_id == vendor_id,
            PurchaseInvoice.supplier_invoice_number == supplier_invoice_number,
            PurchaseInvoice.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(PurchaseInvoice.id != current_id)
        if self._session.scalar(statement) is not None:
            return (
                "A purchase invoice with this supplier invoice number already exists."
            )
        return None

    def _accrued_cost(self, invoice_id: UUID) -> Decimal:
        """Return the share of the receipts' accrual this invoice clears.

        The goods receipt accrued at the stock ledger's cost, so the invoice has
        to clear the accrual at that same number. Anything else the supplier
        billed is a price variance.

        Only the share this invoice bills, pro rata by quantity: billing 4 of
        a received 10 used to clear the whole line's accrual, so the accrual
        went to zero with 6 still unbilled, 600 of nothing was booked as a
        favourable variance, and the bill for the 6 cleared another 1000
        (D-BUY-7, driven on TEST01 on 2026-09-18). The bills are replayed in
        approval order and the one that completes the receipt takes what is
        left rather than its own rounded share, so however the cost divides,
        the bills together clear exactly what the receipt posted -- rounding
        the sum is not rounding the parts. A bill past that point clears
        nothing, and the whole of its value is variance.

        Lines sourced from a purchase order rather than a receipt accrued
        nothing, so they contribute nothing here and the whole of their value
        becomes variance — which is the honest answer when stock was invoiced
        without ever being received.

        Args:
            invoice_id: The invoice being approved.

        Returns:
            What this invoice clears of the accrual its receipts posted.

        """
        receipts = self._receipts_billed_by(invoice_id)
        if not receipts:
            return ZERO
        # Every line of every receipt this bill touches, with what its movement
        # actually cost -- the figure the receipt accrued.
        lines: dict[UUID, dict[UUID, tuple[Decimal, Decimal]]] = defaultdict(dict)
        for line_id, receipt_id, accepted, cost in self._session.execute(
            select(
                GoodsReceiptLine.id,
                GoodsReceiptLine.goods_receipt_id,
                GoodsReceiptLine.accepted_quantity,
                func.coalesce(func.sum(StockLedgerEntry.total_cost), 0),
            )
            .outerjoin(
                StockLedgerEntry,
                StockLedgerEntry.transaction_id
                == GoodsReceiptLine.inventory_transaction_id,
            )
            .where(
                GoodsReceiptLine.goods_receipt_id.in_(list(receipts)),
                GoodsReceiptLine.is_deleted.is_(False),
            )
            .group_by(
                GoodsReceiptLine.id,
                GoodsReceiptLine.goods_receipt_id,
                GoodsReceiptLine.accepted_quantity,
            )
        ).all():
            lines[receipt_id][line_id] = (
                self._q(accepted),
                self._q(Decimal(str(cost or 0))),
            )
        # What went back before billing already took its share of the
        # accrual off (D-BUY-26), and is never billed: the bill that completes
        # the receipt clears what is left after it.
        positions = receipt_line_billing(
            self._session,
            self._session.scalars(
                select(GoodsReceiptLine).where(
                    GoodsReceiptLine.goods_receipt_id.in_(list(receipts)),
                    GoodsReceiptLine.is_deleted.is_(False),
                )
            ).all(),
        )
        accrued = ZERO
        for receipt_id, receipt_lines in lines.items():
            posted = self._posted_bills_on(receipt_lines, except_invoice_id=invoice_id)
            posted[invoice_id] = receipts[receipt_id]
            # A bill typed in pieces against a box clears the pieces' share,
            # not the share of a box rounded to four places: 0.5833 of a box
            # at 720.00 cleared 419.98 where seven pieces cost 420.00, and
            # two paise went to purchase price variance (D-PRC-37).
            unrounded = self._unrounded_billed(receipt_lines)
            accrued += self._replay_accrual(
                receipt_lines,
                list(posted.values()),
                exact=[
                    {
                        line_id: quantity + unrounded.get((bill_id, line_id), ZERO)
                        for line_id, quantity in bill.items()
                    }
                    for bill_id, bill in posted.items()
                ],
                returned={
                    line_id: self._q(positions[line_id].returned_unbilled)
                    for line_id in receipt_lines
                    if line_id in positions
                },
                returned_cost=sum(
                    (
                        positions[line_id].returned_cost
                        for line_id in receipt_lines
                        if line_id in positions
                    ),
                    ZERO,
                ),
            )[-1]
        return accrued

    def _receipts_billed_by(self, invoice_id: UUID) -> dict[UUID, dict[UUID, Decimal]]:
        """Return, per receipt this invoice bills, its quantity per receipt line."""
        billed: dict[UUID, dict[UUID, Decimal]] = defaultdict(dict)
        for receipt_id, line_id, quantity in self._session.execute(
            select(
                GoodsReceiptLine.goods_receipt_id,
                GoodsReceiptLine.id,
                func.sum(PurchaseInvoiceLine.current_invoice_quantity),
            )
            .select_from(PurchaseInvoiceLine)
            .join(
                GoodsReceiptLine,
                GoodsReceiptLine.id == PurchaseInvoiceLine.source_document_line_id,
            )
            .where(
                PurchaseInvoiceLine.purchase_invoice_id == invoice_id,
                PurchaseInvoiceLine.is_deleted.is_(False),
            )
            .group_by(GoodsReceiptLine.goods_receipt_id, GoodsReceiptLine.id)
        ).all():
            billed[receipt_id][line_id] = self._q(quantity)
        return billed

    def _posted_bills_on(
        self,
        receipt_lines: dict[UUID, tuple[Decimal, Decimal]],
        *,
        except_invoice_id: UUID,
    ) -> dict[UUID, dict[UUID, Decimal]]:
        """Return the bills already posted against these lines, oldest first.

        Read from the rows rather than the invoice being approved, whose own
        status is still pending on a request session that does not autoflush.
        A cancelled bill's journal is reversed, so it clears nothing here.
        """
        rows = self._session.execute(
            select(
                PurchaseInvoice.id,
                PurchaseInvoiceLine.source_document_line_id,
                func.sum(PurchaseInvoiceLine.current_invoice_quantity),
            )
            .join(
                PurchaseInvoice,
                PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id,
            )
            .where(
                PurchaseInvoice.id != except_invoice_id,
                PurchaseInvoice.is_deleted.is_(False),
                PurchaseInvoice.approved_at.is_not(None),
                PurchaseInvoice.status.in_(
                    [
                        PurchaseInvoiceStatus.APPROVED.value,
                        PurchaseInvoiceStatus.CLOSED.value,
                    ]
                ),
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.source_document_line_id.in_(list(receipt_lines)),
            )
            .group_by(
                PurchaseInvoice.id,
                PurchaseInvoice.approved_at,
                PurchaseInvoiceLine.source_document_line_id,
            )
            .order_by(PurchaseInvoice.approved_at, PurchaseInvoice.id)
        ).all()
        bills: dict[UUID, dict[UUID, Decimal]] = {}
        for bill_id, line_id, quantity in rows:
            bills.setdefault(bill_id, {})[line_id] = self._q(quantity)
        return bills

    def _unrounded_billed(
        self, receipt_lines: dict[UUID, tuple[Decimal, Decimal]]
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return what rounding took off each bill's quantity of these lines.

        Per bill and receipt line, the quantity typed in another unit less
        the four places it is stored at in the receipt line's unit; nothing
        for a line typed in the receipt's own unit.
        """
        drift: dict[tuple[UUID, UUID], Decimal] = defaultdict(lambda: ZERO)
        for bill_id, line_id, stored, entered, factor in self._session.execute(
            select(
                PurchaseInvoiceLine.purchase_invoice_id,
                PurchaseInvoiceLine.source_document_line_id,
                PurchaseInvoiceLine.current_invoice_quantity,
                PurchaseInvoiceLine.entered_quantity,
                PurchaseInvoiceLine.conversion_factor,
            ).where(
                PurchaseInvoiceLine.is_deleted.is_(False),
                PurchaseInvoiceLine.entered_quantity.is_not(None),
                PurchaseInvoiceLine.source_document_line_id.in_(list(receipt_lines)),
            )
        ).all():
            drift[(bill_id, line_id)] += exact_quantity(
                stored, entered, factor
            ) - Decimal(str(stored))
        return drift

    def _replay_accrual(
        self,
        receipt_lines: dict[UUID, tuple[Decimal, Decimal]],
        bills: list[dict[UUID, Decimal]],
        *,
        returned: dict[UUID, Decimal] | None = None,
        returned_cost: Decimal = ZERO,
        exact: list[dict[UUID, Decimal]] | None = None,
    ) -> list[Decimal]:
        """Return what each bill in turn clears of one receipt's accrual.

        A bill takes each line's cost in proportion to the quantity it bills of
        what the receipt accepted; the bill that completes the receipt takes
        whatever the earlier ones left, so the rounding residual lands on the
        last bill and the receipt nets to zero; a bill after that takes
        nothing.

        ``returned`` is what each line sent back before billing, and
        ``returned_cost`` what those returns took off the accrual (D-BUY-26):
        the goods count toward completing the receipt, and their cost is not
        the completing bill's to clear.

        ``exact`` is each bill's quantities before they were rounded to the
        receipt line's unit, for a bill typed in another one: its share is
        worked on those, while what completes the receipt is still counted
        on the stored quantities, which add up to it exactly.
        """
        posted = quantize_ledger(
            sum((cost for _, cost in receipt_lines.values()), ZERO)
        ) - quantize_ledger(returned_cost)
        billed: dict[UUID, Decimal] = {
            line_id: (returned or {}).get(line_id, ZERO) for line_id in receipt_lines
        }
        cleared = ZERO
        complete = False
        shares: list[Decimal] = []
        for position, bill in enumerate(bills):
            if complete:
                shares.append(ZERO)
                continue
            share = ZERO
            for line_id, quantity in bill.items():
                accepted, cost = receipt_lines[line_id]
                open_quantity = max(accepted - billed[line_id], ZERO)
                worked = quantity if exact is None else exact[position][line_id]
                if accepted > ZERO:
                    share += cost * min(worked, open_quantity) / accepted
                billed[line_id] += quantity
            complete = all(
                billed[line_id] >= accepted
                for line_id, (accepted, _) in receipt_lines.items()
            )
            amount = max(posted - cleared, ZERO) if complete else quantize_ledger(share)
            cleared += amount
            shares.append(amount)
        return shares

    def _assert_nothing_rests_on(self, row: PurchaseInvoice) -> None:
        """Refuse to cancel a bill that a payment or a return rests on.

        Each has its own undo -- reverse the payment, cancel the return -- and
        doing that first keeps the books telling one story: a payment applied
        to a cancelled bill would clear a debt that no longer exists. The
        refusal names what is in the way, as the sales invoice's does.
        """
        # Imported here: both modules import the invoice model.
        from app.debit_note.models import DebitNote, DebitNoteStatus
        from app.purchase_return.models import PurchaseReturn, PurchaseReturnSource
        from app.settlements.models import Settlement, SettlementAllocation

        blockers: list[str] = []
        payments = self._session.scalars(
            select(Settlement.settlement_number)
            .join(
                SettlementAllocation,
                SettlementAllocation.settlement_id == Settlement.id,
            )
            .where(
                SettlementAllocation.purchase_invoice_id == row.id,
                SettlementAllocation.is_deleted.is_(False),
                Settlement.status == "POSTED",
                Settlement.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        if payments:
            blockers.append("payment " + ", ".join(sorted(payments)))
        # A write-back or set-off naming the bill (backlog 74 row 2).
        from app.party_adjustments.services.allocations import (
            adjustment_numbers_against,
        )

        adjustments = adjustment_numbers_against(
            self._session, column="purchase_invoice_id", bill_id=row.id
        )
        if adjustments:
            blockers.append("party adjustment " + ", ".join(adjustments))
        # The returns that name the bill, and the ones that name its goods
        # receipt or another bill of it and were set against this one
        # (D-PRC-80): each claims from the supplier what this bill charged.
        from app.purchase_return.billing import returns_resting_on

        named = select(PurchaseReturnSource.purchase_return_id).where(
            PurchaseReturnSource.source_document_type == "PURCHASE_INVOICE",
            PurchaseReturnSource.source_document_id == row.id,
        )
        placed = sorted(returns_resting_on(self._session, invoice_id=row.id), key=str)
        returns = self._session.scalars(
            select(PurchaseReturn.return_number)
            .where(
                or_(PurchaseReturn.id.in_(named), PurchaseReturn.id.in_(placed)),
                PurchaseReturn.status != "CANCELLED",
                PurchaseReturn.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        if returns:
            blockers.append("purchase return " + ", ".join(sorted(returns)))
        # A debit note claims against this bill's lines at the rate it charged;
        # cancelling the bill under it would leave the claim naming nothing.
        notes = self._session.scalars(
            select(DebitNote.debit_note_number).where(
                DebitNote.purchase_invoice_id == row.id,
                DebitNote.status != DebitNoteStatus.CANCELLED.value,
                DebitNote.is_deleted.is_(False),
            )
        ).all()
        if notes:
            blockers.append("debit note " + ", ".join(sorted(notes)))
        # TDS deducted on the bill and already deposited (PG-5): cancelling
        # would take the deduction off a challan the government holds.
        from app.finance.models.tds_challan import TdsChallan, TdsChallanItem

        challans = self._session.scalars(
            select(TdsChallan.challan_number)
            .join(TdsChallanItem, TdsChallanItem.challan_id == TdsChallan.id)
            .where(
                TdsChallanItem.purchase_invoice_id == row.id,
                TdsChallanItem.is_live.is_(True),
                TdsChallan.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        if challans:
            blockers.append("TDS challan " + ", ".join(sorted(challans)))
        if blockers:
            raise ValidationError(
                f"{row.invoice_number} cannot be cancelled while it has "
                + "; ".join(blockers)
                + ". Reverse or cancel those first."
            )

    def _reverse_invoice_posting(
        self, row: PurchaseInvoice, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Cancel the journal an approved invoice wrote, if it wrote one.

        `reversal_of_id IS NULL` matters: `reverse_entry` copies the source
        module and id onto the mirror it posts, so without it a second pass
        would find that mirror and reverse the reversal.
        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "purchase_invoice",
                JournalEntry.source_id == row.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # Nothing posted, so there is nothing to take back -- a firm that
            # approved bills before posting existed is in this state.
            return
        JournalEntryEngine(self._session).reverse_entry(
            entry_id,
            firm_id=firm_scope,
            reference_number=f"{row.invoice_number}-REV",
            actor_id=actor_id,
        )

    def _record_event(
        self,
        *,
        firm_id: UUID,
        document_type: DocumentTypeDefinition,
        invoice: PurchaseInvoice,
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
                source_module_code="PURCHASE_INVOICE",
                document_number=invoice.invoice_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "invoice_number": invoice.invoice_number,
                    "supplier_invoice_number": invoice.supplier_invoice_number,
                    "grand_total": str(invoice.grand_total),
                },
                snapshot_json={
                    "status": invoice.status,
                    "vendor_id": str(invoice.vendor_id),
                    "branch_id": str(invoice.branch_id),
                },
                actor_id=actor_id,
            ),
            actor_id=actor_id,
        )

    def _attachment_response(
        self, row: PurchaseInvoiceAttachment
    ) -> PurchaseInvoiceAttachmentResponse:
        return PurchaseInvoiceAttachmentResponse.model_validate(row)

    def _note_response(self, row: PurchaseInvoiceNote) -> PurchaseInvoiceNoteResponse:
        return PurchaseInvoiceNoteResponse.model_validate(row)

    def _source_response(
        self, row: PurchaseInvoiceSource
    ) -> PurchaseInvoiceSourceResponse:
        return PurchaseInvoiceSourceResponse(
            id=row.id,
            source_document_type=PurchaseInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            vendor_id=row.vendor_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: PurchaseInvoiceAccountingEvent
    ) -> PurchaseInvoiceAccountingEventResponse:
        return PurchaseInvoiceAccountingEventResponse(
            id=row.id,
            event_type=PurchaseInvoiceAccountingEventType(row.event_type),
            account_name=row.account_name,
            direction=row.direction,
            amount=row.amount,
            narration=row.narration,
            source_line_id=row.source_line_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _line_response(
        self,
        row: PurchaseInvoiceLine,
        taxes: list[PurchaseInvoiceLineTax] | None = None,
    ) -> PurchaseInvoiceLineResponse:
        return PurchaseInvoiceLineResponse(
            id=row.id,
            tax_rule_code=row.tax_rule_code,
            tax_rule_version=row.tax_rule_version,
            purchase_invoice_id=row.purchase_invoice_id,
            line_number=row.line_number,
            source_document_type=PurchaseInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            received_quantity=row.received_quantity,
            already_invoiced_quantity=row.already_invoiced_quantity,
            current_invoice_quantity=row.current_invoice_quantity,
            unit_price=row.unit_price,
            discount_percent=row.discount_percent,
            discount_amount=row.discount_amount,
            bill_discount_amount=row.bill_discount_amount,
            charges_amount=row.charges_amount,
            gross_amount=row.gross_amount,
            tax_profile_id=row.tax_profile_id,
            itc_eligibility=row.itc_eligibility or "ELIGIBLE",
            is_capital_goods=bool(row.is_capital_goods),
            asset_class_id=row.asset_class_id,
            tax_amount=row.tax_amount,
            net_amount=row.net_amount,
            packaging_type_id=row.packaging_type_id,
            purchase_uom_id=row.purchase_uom_id,
            invoice_uom_id=row.invoice_uom_id,
            entered_quantity=row.entered_quantity,
            conversion_factor=row.conversion_factor,
            conversion_version=row.conversion_version,
            warehouse_id=row.warehouse_id,
            storage_node_id=row.storage_node_id,
            batch_number=row.batch_number,
            expiry_date=row.expiry_date,
            manufacturing_date=row.manufacturing_date,
            remarks=row.remarks,
            accounting_event_reference=row.accounting_event_reference,
            taxes=[
                PurchaseInvoiceLineTaxResponse(
                    id=component.id,
                    sequence=component.sequence,
                    tax_component_id=component.tax_component_id,
                    component_code=component.component_code,
                    component_label=component.component_label,
                    percentage=component.percentage,
                    base_amount=component.base_amount,
                    amount=component.amount,
                    included_in_price=component.included_in_price,
                    recoverable=component.recoverable,
                    reverse_charge=component.reverse_charge,
                )
                for component in (taxes or [])
            ],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
