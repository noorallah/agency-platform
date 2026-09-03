"""Sales invoice workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.business.gating import assert_feature_fields
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.core.utils.pricing import (
    LineDiscount,
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
)
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CreditControlService
from app.customers.services.customer_service import CustomerService
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteStatus
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
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales.services.scope_resolution import resolve_sales_scope
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceAccountingEvent,
    SalesInvoiceAttachment,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
    SalesInvoiceNote,
    SalesInvoiceSource,
)
from app.sales_invoice.schemas import (
    BillableDocument,
    BillableLine,
    SalesInvoiceAccountingEventResponse,
    SalesInvoiceAccountingEventType,
    SalesInvoiceAttachmentResponse,
    SalesInvoiceAttachmentWrite,
    SalesInvoiceCreate,
    SalesInvoiceCustomerOutstandingRecord,
    SalesInvoiceImportRequest,
    SalesInvoiceLineResponse,
    SalesInvoiceLineTaxResponse,
    SalesInvoiceListFilters,
    SalesInvoiceNoteResponse,
    SalesInvoiceNoteWrite,
    SalesInvoiceReconciliationRecord,
    SalesInvoiceRegisterRecord,
    SalesInvoiceResponse,
    SalesInvoiceSourceResponse,
    SalesInvoiceSourceType,
    SalesInvoiceStatus,
    SalesInvoiceSummary,
)
from app.sales_invoice.services.sales_chain_service import SalesChainService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderStatus
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.schemas import ConversionRequest
from app.uom.services import UomService

ZERO = Decimal("0")

# The two line shapes a sales invoice can be raised from. Naming the union lets
# the helpers below say what they accept instead of taking ``object`` and
# reaching for attributes mypy cannot see.
SourceLine = DeliveryNoteLine | SalesOrderLine


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


def _receivable_amount(value: Decimal) -> Decimal:
    """Round an invoice total to the scale the receivable ledger stores.

    Kept as a name local to this module, delegating to the shared helper. It
    was a private copy of that rounding until 2026-08-24, which is exactly how
    `sales_return` came to carry the same defect untouched: the fix lived here
    and its sibling never saw it.
    """
    return quantize_ledger(value)


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


@dataclass(frozen=True, slots=True)
class _PricedInvoiceLine:
    """One invoice line, priced but not yet taxed or written.

    The two passes exist because a discount on the whole bill has to be split
    across the lines before tax is asked for, and the split cannot be known
    until every line has been priced. Everything the second pass needs and
    cannot cheaply recompute is carried here -- the quantity in particular,
    which may have come through a UOM conversion.
    """

    index: int
    spec: dict[str, object]
    source_line: SourceLine
    source_type: str
    invoice_quantity: Decimal
    source_quantity: Decimal
    already_invoiced: Decimal
    conversion_factor: Decimal
    source_uom_id: UUID | None
    unit_price: Decimal
    charges_amount: Decimal
    gross_amount: Decimal
    free_quantity: Decimal
    discount: LineDiscount


class SalesInvoiceService(TransactionalDocumentService):
    """Coordinate customer invoice lifecycle and source-document validation."""

    DOCUMENT = DocumentTypeSpec(
        code="SALES_INVOICE",
        name="Sales Invoice",
        description="Customer invoice document",
        category="FINANCE",
        module="sales_invoice",
        prefix="SI",
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
        filters: SalesInvoiceListFilters,
        page: int,
        page_size: int,
        search: str | None,
        sort_by: str,
        descending: bool,
    ) -> tuple[list[SalesInvoice], int]:
        """List sales invoices for the visible firm scope."""
        columns = {
            "invoice_number": SalesInvoice.invoice_number,
            "invoice_date": SalesInvoice.invoice_date,
            "due_date": SalesInvoice.due_date,
            "grand_total": SalesInvoice.grand_total,
            "status": SalesInvoice.status,
            "created_at": SalesInvoice.created_at,
            "updated_at": SalesInvoice.updated_at,
        }
        statement = select(SalesInvoice).where(SalesInvoice.firm_id == firm_scope)
        count = (
            select(func.count())
            .select_from(SalesInvoice)
            .where(SalesInvoice.firm_id == firm_scope)
        )
        if not filters.include_deleted:
            statement = statement.where(SalesInvoice.is_deleted.is_(False))
            count = count.where(SalesInvoice.is_deleted.is_(False))
        if filters.customer_id is not None:
            statement = statement.where(SalesInvoice.customer_id == filters.customer_id)
            count = count.where(SalesInvoice.customer_id == filters.customer_id)
        if filters.branch_id is not None:
            statement = statement.where(SalesInvoice.branch_id == filters.branch_id)
            count = count.where(SalesInvoice.branch_id == filters.branch_id)
        if filters.salesman_id is not None:
            statement = statement.where(SalesInvoice.salesman_id == filters.salesman_id)
            count = count.where(SalesInvoice.salesman_id == filters.salesman_id)
        if filters.territory_id is not None:
            statement = statement.where(
                SalesInvoice.territory_id == filters.territory_id
            )
            count = count.where(SalesInvoice.territory_id == filters.territory_id)
        if filters.status is not None:
            statement = statement.where(SalesInvoice.status == filters.status.value)
            count = count.where(SalesInvoice.status == filters.status.value)
        if filters.invoice_from is not None:
            statement = statement.where(
                SalesInvoice.invoice_date >= filters.invoice_from
            )
            count = count.where(SalesInvoice.invoice_date >= filters.invoice_from)
        if filters.invoice_to is not None:
            statement = statement.where(SalesInvoice.invoice_date <= filters.invoice_to)
            count = count.where(SalesInvoice.invoice_date <= filters.invoice_to)
        if filters.due_from is not None:
            statement = statement.where(SalesInvoice.due_date >= filters.due_from)
            count = count.where(SalesInvoice.due_date >= filters.due_from)
        if filters.due_to is not None:
            statement = statement.where(SalesInvoice.due_date <= filters.due_to)
            count = count.where(SalesInvoice.due_date <= filters.due_to)
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesInvoice.invoice_number.ilike(token),
                SalesInvoice.customer_invoice_number.ilike(token),
                SalesInvoice.reference_number.ilike(token),
                SalesInvoice.remarks.ilike(token),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, SalesInvoice.created_at)
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

    def summary(self, *, firm_scope: UUID) -> SalesInvoiceSummary:
        """Return aggregate sales invoice values for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
            ).all()
        )
        overdue = sum(
            1
            for row in rows
            if row.due_date is not None
            and row.due_date < utc_now().date()
            and row.status
            not in {SalesInvoiceStatus.CANCELLED.value, SalesInvoiceStatus.CLOSED.value}
        )
        return SalesInvoiceSummary(
            total=len(rows),
            draft=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.DRAFT.value
            ),
            approved=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.APPROVED.value
            ),
            cancelled=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.CANCELLED.value
            ),
            closed=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.CLOSED.value
            ),
            total_value=self._q(sum((row.grand_total for row in rows), ZERO)),
            pending_invoices=sum(
                1 for row in rows if row.status == SalesInvoiceStatus.DRAFT.value
            ),
            overdue_invoices=overdue,
        )

    def create_invoice(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Create one sales invoice and commit it."""
        row = self.stage_invoice(data, firm_id=firm_id, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_invoice(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Create one sales invoice without committing it.

        See `SalesOrderService.stage_order`. This is the last document in the
        chain, so it is usually the caller that commits -- but it must not
        commit itself, or the documents synthesised before it would be durable
        while its own approval could still refuse.
        """
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        # Raise whatever earlier documents this firm has chosen not to type.
        # A firm on the whole chain gets its payload back untouched, so this
        # costs one settings read and changes nothing for anybody else.
        data = SalesChainService(self._session).ensure_invoice_source(
            data, firm_id=firm_id, actor_id=actor_id
        )
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_id=firm_id
        )
        branch_id = data.branch_id or header["branch_id"]
        customer_id = data.customer_id or header["customer_id"]
        salesman_id = data.salesman_id or header.get("salesman_id")
        territory_id = data.territory_id or header.get("territory_id")
        route_id = data.route_id or header.get("route_id")
        business_profile_id = data.business_profile_id
        if customer_id != header["customer_id"]:
            raise ValidationError("Invoice customer must match all source documents.")
        if branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        if data.salesman_id is not None and header.get("salesman_id") not in {
            None,
            data.salesman_id,
        }:
            raise ValidationError("Invoice salesman must match all source documents.")
        if data.territory_id is not None and header.get("territory_id") not in {
            None,
            data.territory_id,
        }:
            raise ValidationError("Invoice territory must match all source documents.")
        if data.route_id is not None and header.get("route_id") not in {
            None,
            data.route_id,
        }:
            raise ValidationError("Invoice route must match all source documents.")
        self._validate_scope_references(
            firm_id=firm_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
        )
        salesman_id, territory_id, route_id = self._fill_missing_scope(
            firm_id=firm_id,
            customer_id=customer_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
            on_date=data.invoice_date,
        )
        self._validate_customer_invoice_number(
            firm_id=firm_id,
            customer_id=customer_id,
            customer_invoice_number=data.customer_invoice_number,
        )
        invoice_number = (
            data.invoice_number.strip().upper()
            if data.invoice_number
            else self._documents.reserve_number(
                numbering_rule.id,
                firm_id=firm_id,
                financial_year_label=self._financial_year_label(
                    data.invoice_date, firm_id
                ),
                branch_code=self._scope_code(branch_id),
                company_code=self._company_code(firm_id),
                document_date=data.invoice_date,
                actor_id=actor_id,
            )
        )
        # Read once for the two fields below; the customer's terms decide when
        # payment falls due and its billing address decides the place of supply.
        customer = self._session.get(Customer, customer_id)
        row = SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            salesman_id=salesman_id,
            territory_id=territory_id,
            route_id=route_id,
            branch_id=branch_id,
            business_profile_id=business_profile_id,
            invoice_number=invoice_number,
            invoice_date=data.invoice_date,
            customer_invoice_number=(
                data.customer_invoice_number.strip()
                if data.customer_invoice_number
                else None
            ),
            currency_code=(
                data.currency_code.strip().upper() if data.currency_code else None
            ),
            exchange_rate=data.exchange_rate,
            payment_terms=data.payment_terms,
            due_date=data.due_date or self._due_date(customer, data.invoice_date),
            place_of_supply=self._place_of_supply(customer),
            reference_number=data.reference_number,
            remarks=data.remarks,
            # A record of how this bill was raised, not a permission:
            # true when the bill dispatched its own goods.
            allow_direct_sales_order=self._raised_its_own_dispatch(
                data, firm_id=firm_id
            ),
            allow_over_invoice=data.allow_over_invoice,
            over_invoice_percent=self._q(data.over_invoice_percent),
            status=SalesInvoiceStatus.DRAFT.value,
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
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_invoiced_quantity = line_totals[
            "total_already_invoiced_quantity"
        ]
        row.total_free_quantity = line_totals["total_free_quantity"]
        row.total_current_invoice_quantity = line_totals[
            "total_current_invoice_quantity"
        ]
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
            invoice=row,
            action="CREATED",
            from_state=None,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_invoice.created",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"invoice_number": row.invoice_number, "status": row.status},
        )
        self._flush_or_conflict("Sales invoice number already exists in this firm.")
        return row

    def update_invoice(
        self,
        invoice_id: UUID,
        data: SalesInvoiceCreate,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> SalesInvoice:
        """Replace one sales invoice."""
        assert_feature_fields(
            self._session,
            firm_id,
            feature="ATTACHMENTS",
            values={"attachments": data.attachments},
        )
        row = self.get_invoice(invoice_id, firm_scope=firm_id)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft sales invoices can be updated.")
        self._delete_children(row.id)
        header, source_rows, line_specs = self._prepare_invoice_sources(data, firm_id)
        row.customer_id = data.customer_id or header["customer_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        row.business_profile_id = data.business_profile_id
        salesman_id, territory_id, route_id = self._fill_missing_scope(
            firm_id=firm_id,
            customer_id=row.customer_id,
            salesman_id=data.salesman_id or header.get("salesman_id"),
            territory_id=data.territory_id or header.get("territory_id"),
            route_id=data.route_id or header.get("route_id"),
            on_date=data.invoice_date,
        )
        row.salesman_id = salesman_id
        row.territory_id = territory_id
        row.route_id = route_id
        row.invoice_date = data.invoice_date
        row.customer_invoice_number = (
            data.customer_invoice_number.strip()
            if data.customer_invoice_number
            else None
        )
        row.currency_code = (
            data.currency_code.strip().upper() if data.currency_code else None
        )
        row.exchange_rate = data.exchange_rate
        row.payment_terms = data.payment_terms
        row.due_date = data.due_date
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        row.allow_over_invoice = data.allow_over_invoice
        row.over_invoice_percent = self._q(data.over_invoice_percent)
        row.additional_charges = self._q(data.additional_charges)
        row.round_off = self._q(data.round_off)
        row.updated_by = actor_id
        if row.customer_id != header["customer_id"]:
            raise ValidationError("Invoice customer must match all source documents.")
        if row.branch_id != header["branch_id"]:
            raise ValidationError("Invoice branch must match all source documents.")
        if data.salesman_id is not None and header.get("salesman_id") not in {
            None,
            data.salesman_id,
        }:
            raise ValidationError("Invoice salesman must match all source documents.")
        if data.territory_id is not None and header.get("territory_id") not in {
            None,
            data.territory_id,
        }:
            raise ValidationError("Invoice territory must match all source documents.")
        if data.route_id is not None and header.get("route_id") not in {
            None,
            data.route_id,
        }:
            raise ValidationError("Invoice route must match all source documents.")
        self._validate_scope_references(
            firm_id=firm_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
        )
        self._validate_customer_invoice_number(
            firm_id=firm_id,
            customer_id=row.customer_id,
            customer_invoice_number=row.customer_invoice_number,
            current_id=row.id,
        )
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.total_source_quantity = line_totals["total_source_quantity"]
        row.total_already_invoiced_quantity = line_totals[
            "total_already_invoiced_quantity"
        ]
        row.total_free_quantity = line_totals["total_free_quantity"]
        row.total_current_invoice_quantity = line_totals[
            "total_current_invoice_quantity"
        ]
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
            document_type=self._document_type(firm_id),
            invoice=row,
            action="EDITED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_invoice.updated",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
        )
        self._session.commit()
        return row

    def approve_invoice(
        self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Approve one sales invoice and commit it."""
        row = self.stage_approval(invoice_id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def stage_approval(
        self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Approve one sales invoice without committing it.

        Posts the receivable and the revenue journal. `post_receivable_transaction`
        has always taken `commit=False` here for the same reason the rest of
        this split exists: the money and the document have to land together.
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft sales invoices can be approved.")
        # Approval is what puts the amount on the customer's account, so it is
        # the last point at which a limit can still be enforced.
        customer = self._session.get(Customer, row.customer_id)
        if customer is not None:
            CreditControlService(self._session).assert_within_limit(
                customer, additional_amount=self._q(row.grand_total)
            )
        before = row.status
        row.status = SalesInvoiceStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        CustomerService(self._session).post_receivable_transaction(
            row.customer_id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.INVOICE,
                transaction_date=row.invoice_date,
                amount=_receivable_amount(row.grand_total),
                reference_type="SALES_INVOICE",
                reference_id=row.id,
                reference_number=row.invoice_number,
                remarks=f"Invoice {row.invoice_number} approved.",
            ),
            firm_scope=firm_scope,
            actor_id=actor_id,
            commit=False,
        )
        # Posting runs before the commit and is allowed to fail the approval. An
        # approved invoice with no journal is the gap this closes, so a missing
        # control account or a closed period refuses the approval outright.
        #
        # Revenue takes everything that is not tax: the taxable base plus any
        # line charges, header charges and round-off. Those belong in their own
        # accounts and will move there when this posts a line per component;
        # lumping them into revenue keeps the entry balanced and the receivable
        # exactly equal to what the customer owes.
        DocumentPostingService(self._session).post_sales_invoice(
            firm_id=firm_scope,
            invoice_id=row.id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            taxable_amount=self._q(row.grand_total - row.tax_total),
            tax_amount=self._q(row.tax_total),
            total_amount=self._q(row.grand_total),
            actor_id=actor_id,
        )
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="APPROVED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_invoice.approved",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
        )
        return row

    def cancel_invoice(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> SalesInvoice:
        """Cancel one sales invoice."""
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status in {
            SalesInvoiceStatus.CANCELLED.value,
            SalesInvoiceStatus.CLOSED.value,
        }:
            raise ValidationError("This sales invoice can no longer be cancelled.")
        before = row.status
        row.status = SalesInvoiceStatus.CANCELLED.value
        row.cancel_reason = reason
        row.updated_by = actor_id
        if before == SalesInvoiceStatus.APPROVED.value:
            # The invoice posted revenue, tax and a receivable when it was
            # approved. Cancelling it reduced the customer's balance and left
            # all three in the ledger, so the receivable control account
            # overstated by the whole invoice from that moment on. Reversing
            # the entry mirrors what it raised, which is right in a way that
            # booking the lot as a sales return would not be.
            self._reverse_invoice_posting(row, firm_scope=firm_scope, actor_id=actor_id)
            CustomerService(self._session).post_receivable_transaction(
                row.customer_id,
                CustomerReceivableTransactionCreate(
                    transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
                    transaction_date=utc_now().date(),
                    amount=_receivable_amount(row.grand_total),
                    reference_type="SALES_INVOICE",
                    reference_id=row.id,
                    reference_number=row.invoice_number,
                    remarks=reason
                    or f"Auto reversal for cancelled invoice {row.invoice_number}.",
                ),
                firm_scope=firm_scope,
                actor_id=actor_id,
                commit=False,
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
            action="sales_invoice.cancelled",
            entity_type="sales_invoice",
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
    ) -> SalesInvoice:
        """Close one sales invoice."""
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == SalesInvoiceStatus.CLOSED.value:
            raise ValidationError("This sales invoice is already closed.")
        before = row.status
        row.status = SalesInvoiceStatus.CLOSED.value
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
            action="sales_invoice.closed",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"reason": reason},
        )
        self._session.commit()
        return row

    def get_invoice(self, invoice_id: UUID, *, firm_scope: UUID) -> SalesInvoice:
        """Return one sales invoice."""
        row = self._session.scalar(
            select(SalesInvoice).where(
                SalesInvoice.id == invoice_id,
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Sales invoice not found.")
        return row

    def invoice_response(self, row: SalesInvoice) -> SalesInvoiceResponse:
        """Render one sales invoice row as its API contract."""
        sources = list(
            self._session.scalars(
                select(SalesInvoiceSource).where(
                    SalesInvoiceSource.sales_invoice_id == row.id,
                    SalesInvoiceSource.is_deleted.is_(False),
                )
            ).all()
        )
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .where(
                    SalesInvoiceLine.sales_invoice_id == row.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLine.line_number.asc())
            ).all()
        )
        # Read for the whole invoice rather than per line: a bill with thirty
        # lines would otherwise be thirty queries, the shape `values_for_many`
        # exists to avoid.
        taxes: dict[UUID, list[SalesInvoiceLineTax]] = defaultdict(list)
        if lines:
            for component in self._session.scalars(
                select(SalesInvoiceLineTax)
                .where(
                    SalesInvoiceLineTax.sales_invoice_line_id.in_(
                        [item.id for item in lines]
                    ),
                    SalesInvoiceLineTax.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceLineTax.sequence.asc())
            ):
                taxes[component.sales_invoice_line_id].append(component)
        attachments = list(
            self._session.scalars(
                select(SalesInvoiceAttachment).where(
                    SalesInvoiceAttachment.sales_invoice_id == row.id,
                    SalesInvoiceAttachment.is_deleted.is_(False),
                )
            ).all()
        )
        notes = list(
            self._session.scalars(
                select(SalesInvoiceNote).where(
                    SalesInvoiceNote.sales_invoice_id == row.id,
                    SalesInvoiceNote.is_deleted.is_(False),
                )
            ).all()
        )
        accounting_events = list(
            self._session.scalars(
                select(SalesInvoiceAccountingEvent).where(
                    SalesInvoiceAccountingEvent.sales_invoice_id == row.id,
                    SalesInvoiceAccountingEvent.is_deleted.is_(False),
                )
            ).all()
        )
        warning = self._duplicate_warning(
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            customer_invoice_number=row.customer_invoice_number,
            current_id=row.id,
        )
        return SalesInvoiceResponse(
            id=row.id,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
            branch_id=row.branch_id,
            business_profile_id=row.business_profile_id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            customer_invoice_number=row.customer_invoice_number,
            place_of_supply=row.place_of_supply,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_direct_sales_order=row.allow_direct_sales_order,
            allow_over_invoice=row.allow_over_invoice,
            over_invoice_percent=row.over_invoice_percent,
            status=SalesInvoiceStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_invoiced_quantity=row.total_already_invoiced_quantity,
            total_current_invoice_quantity=row.total_current_invoice_quantity,
            version=row.version,
            total_free_quantity=row.total_free_quantity,
            bill_discount_percent=row.bill_discount_percent,
            bill_discount_amount=row.bill_discount_amount,
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
            lines=[self._line_response(item, taxes[item.id]) for item in lines],
            sources=[self._source_response(item) for item in sources],
            attachments=[self._attachment_response(item) for item in attachments],
            notes=[self._note_response(item) for item in notes],
            accounting_events=[
                self._accounting_event_response(item) for item in accounting_events
            ],
            duplicate_warning=warning,
        )

    def timeline(
        self, *, invoice_id: UUID, firm_scope: UUID, page: int, page_size: int
    ) -> tuple[list[DocumentLifecycleEvent], int]:
        """Return one page of lifecycle events for an invoice, and the total."""
        return self._documents.list_timeline(
            firm_id=firm_scope,
            document_id=invoice_id,
            page=page,
            page_size=page_size,
            sort_direction=True,
        )

    def pending_invoices(self, *, firm_scope: UUID) -> list[SalesInvoice]:
        """List invoices still in draft, not yet approved."""
        return list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status == SalesInvoiceStatus.DRAFT.value,
                )
            ).all()
        )

    def overdue_invoices(self, *, firm_scope: UUID) -> list[SalesInvoice]:
        """List live invoices past their due date.

        Cancelled and closed invoices are excluded: neither is still owing.
        """
        today = utc_now().date()
        return list(
            self._session.scalars(
                select(SalesInvoice).where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.due_date.is_not(None),
                    SalesInvoice.due_date < today,
                    SalesInvoice.status.not_in(
                        [
                            SalesInvoiceStatus.CANCELLED.value,
                            SalesInvoiceStatus.CLOSED.value,
                        ]
                    ),
                )
            ).all()
        )

    def register_report(self, *, firm_scope: UUID) -> list[SalesInvoiceRegisterRecord]:
        """Return the register report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesInvoice)
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
                .order_by(
                    SalesInvoice.invoice_date.desc(), SalesInvoice.created_at.desc()
                )
            ).all()
        )
        return [
            SalesInvoiceRegisterRecord(
                invoice_id=row.id,
                invoice_number=row.invoice_number,
                customer_invoice_number=row.customer_invoice_number,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                grand_total=row.grand_total,
                status=SalesInvoiceStatus(row.status),
            )
            for row in rows
        ]

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[SalesInvoiceCustomerOutstandingRecord]:
        """Return the outstanding report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(Customer).where(
                    Customer.firm_id == firm_scope,
                    Customer.is_deleted.is_(False),
                )
            ).all()
        )
        counts: dict[UUID, int] = defaultdict(int)
        for row in self._session.scalars(
            select(SalesInvoice).where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status == SalesInvoiceStatus.APPROVED.value,
            )
        ):
            counts[row.customer_id] += 1
        return [
            SalesInvoiceCustomerOutstandingRecord(
                customer_id=customer.id,
                customer_name=customer.name,
                outstanding_amount=self._q(customer.current_outstanding),
                invoice_count=counts[customer.id],
            )
            for customer in rows
            if customer.current_outstanding > ZERO
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID
    ) -> list[SalesInvoiceReconciliationRecord]:
        """Return the reconciliation report for the visible firm scope."""
        rows = list(
            self._session.scalars(
                select(SalesInvoiceLine)
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        )
        result: list[SalesInvoiceReconciliationRecord] = []
        for row in rows:
            pending = self._q(
                row.delivered_quantity
                - row.already_invoiced_quantity
                - row.current_invoice_quantity
            )
            result.append(
                SalesInvoiceReconciliationRecord(
                    source_document_type=SalesInvoiceSourceType(
                        row.source_document_type
                    ),
                    source_document_id=row.source_document_id,
                    source_document_number=row.source_document_number,
                    source_document_line_id=row.source_document_line_id,
                    source_document_line_number=row.source_document_line_number,
                    delivered_quantity=row.delivered_quantity,
                    already_invoiced_quantity=row.already_invoiced_quantity,
                    current_invoice_quantity=row.current_invoice_quantity,
                    pending_quantity=pending if pending >= ZERO else ZERO,
                )
            )
        return result

    def export_invoices_csv(
        self, *, firm_scope: UUID, search: str | None = None
    ) -> str:
        """Export matching sales invoices as CSV."""
        rows, _ = self.list_invoices(
            firm_scope=firm_scope,
            filters=SalesInvoiceListFilters(),
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
                "customer_invoice_number",
                "invoice_date",
                "customer_id",
                "branch_id",
                "status",
                "grand_total",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.invoice_number,
                    row.customer_invoice_number or "",
                    row.invoice_date.isoformat(),
                    str(row.customer_id),
                    str(row.branch_id),
                    row.status,
                    str(row.grand_total),
                ]
            )
        return buffer.getvalue()

    def import_invoices(
        self, data: SalesInvoiceImportRequest, *, firm_id: UUID, actor_id: UUID
    ) -> list[SalesInvoice]:
        """Import a validated batch of sales invoices atomically.

        It looped over a committing method while claiming to be atomic. See
        `SalesOrderService.import_orders`.
        """
        rows = [
            self.stage_invoice(record, firm_id=firm_id, actor_id=actor_id)
            for record in data.records
        ]
        self._session.commit()
        return rows

    def _replace_sources(
        self,
        row: SalesInvoice,
        source_rows: list[dict[str, object]],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceSource).filter(
            SalesInvoiceSource.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for item in source_rows:
            source = SalesInvoiceSource(
                sales_invoice_id=row.id,
                firm_id=firm_id,
                source_document_type=item["source_document_type"],
                source_document_id=item["source_document_id"],
                source_document_number=item["source_document_number"],
                source_document_date=item["source_document_date"],
                customer_id=item["customer_id"],
                branch_id=item["branch_id"],
                created_by=actor_id,
                updated_by=actor_id,
            )
            self._session.add(source)

    def _bill_discount_shares(
        self,
        row: SalesInvoice,
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
        row: SalesInvoice,
        line_specs: list[dict[str, object]],
        *,
        bill_percent: Decimal | None,
        bill_amount: Decimal | None,
        firm_id: UUID,
        invoice_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> dict[str, Decimal]:
        self._session.query(SalesInvoiceLine).filter(
            SalesInvoiceLine.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
        # Every line is priced before any of them is taxed or written, so the
        # discount on the whole bill can be split across them first.
        priced: list[_PricedInvoiceLine] = []
        for index, spec in enumerate(line_specs, start=1):
            source_type = self._source_type(spec["source_document_type"])
            source_line: SourceLine | None
            if source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value:
                source_line = self._session.scalar(
                    select(DeliveryNoteLine).where(
                        DeliveryNoteLine.id == spec["source_document_line_id"]
                    )
                )
            else:
                source_line = self._session.scalar(
                    select(SalesOrderLine).where(
                        SalesOrderLine.id == spec["source_document_line_id"]
                    )
                )
            if source_line is None:
                raise ResourceNotFoundError("Source document line not found.")
            requested_quantity = self._q(Decimal(str(spec["current_invoice_quantity"])))
            source_quantity = self._source_quantity(spec, source_line)
            source_uom_id = self._source_uom_id(source_line)
            invoice_uom_id = spec.get("invoice_uom_id")
            conversion_factor = self._q(
                Decimal(str(spec.get("conversion_factor", Decimal("1"))))
            )
            invoice_quantity = requested_quantity
            if (
                source_uom_id is not None
                and invoice_uom_id is not None
                and invoice_uom_id != source_uom_id
            ):
                conversion = self._uom.convert_quantity(
                    ConversionRequest(
                        product_id=self._product_id(source_line),
                        from_uom_id=invoice_uom_id,
                        to_uom_id=source_uom_id,
                        quantity=requested_quantity,
                        conversion_date=invoice_date,
                    ),
                    firm_scope=firm_id,
                )
                invoice_quantity = self._q(conversion.converted_quantity)
                conversion_factor = self._q(conversion.conversion_factor)
            already_invoiced = self._already_invoiced_quantity(
                firm_id=firm_id,
                source_document_line_id=source_line.id,
            )
            allowed_quantity = source_quantity
            if row.allow_over_invoice:
                allowed_quantity = self._q(
                    source_quantity
                    + (
                        source_quantity
                        * self._q(row.over_invoice_percent)
                        / Decimal("100")
                    )
                )
            if invoice_quantity + already_invoiced > allowed_quantity:
                raise ValidationError(
                    "Invoice quantity exceeds the available source quantity."
                )
            unit_price = self._q(Decimal(str(spec.get("unit_price", ZERO))))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            gross_amount = self._q(invoice_quantity * unit_price)
            # Resolved before the tax call, not after it. The percentage never
            # reached this module: it was stored on the line and the tax base
            # and the subtotal were both computed from the amount alone, so a
            # ten percent order was billed at full price with `10` sitting on
            # the invoice line as a lie.
            line_discount = self._invoice_line_discount(
                spec=spec,
                source_line=source_line,
                gross=gross_amount,
                invoice_quantity=invoice_quantity,
                source_quantity=source_quantity,
            )
            free_quantity = self._invoice_free_quantity(
                spec=spec,
                source_line=source_line,
                invoice_quantity=invoice_quantity,
                source_quantity=source_quantity,
            )
            priced.append(
                _PricedInvoiceLine(
                    index=index,
                    spec=spec,
                    source_line=source_line,
                    source_type=source_type,
                    invoice_quantity=invoice_quantity,
                    source_quantity=source_quantity,
                    already_invoiced=already_invoiced,
                    conversion_factor=conversion_factor,
                    source_uom_id=source_uom_id,
                    unit_price=unit_price,
                    charges_amount=charges_amount,
                    gross_amount=gross_amount,
                    free_quantity=free_quantity,
                    discount=line_discount,
                )
            )

        # The bill discount is split across the lines here, between pricing
        # them and taxing them. It has to reach a taxable value to reduce any
        # tax, which is what `header_discount_amount` on a purchase order does
        # not do -- that one is subtracted after tax and so the customer pays
        # tax on money they were never charged.
        shares = self._bill_discount_shares(
            row,
            percent=bill_percent,
            amount=bill_amount,
            taxables=[
                self._q(item.gross_amount - item.discount.amount) for item in priced
            ],
        )

        for position, item in enumerate(priced):
            index = item.index
            spec = item.spec
            priced_source: SourceLine = item.source_line
            source_type = item.source_type
            invoice_quantity = item.invoice_quantity
            source_quantity = item.source_quantity
            already_invoiced = item.already_invoiced
            conversion_factor = item.conversion_factor
            source_uom_id = item.source_uom_id
            unit_price = item.unit_price
            charges_amount = item.charges_amount
            gross_amount = item.gross_amount
            free_quantity = item.free_quantity
            line_discount = item.discount
            bill_share = shares[position]
            discount_amount = self._q(line_discount.amount + bill_share)
            line_tax = self._resolve_tax(
                invoice_date=invoice_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                product_id=self._product_id(priced_source),
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                invoice_value=self._line_net_amount(
                    quantity=invoice_quantity,
                    unit_price=unit_price,
                    discount_amount=discount_amount,
                    charges_amount=charges_amount,
                ),
                actor_id=actor_id,
            )
            tax_amount = line_tax.total
            net_amount = self._q(
                gross_amount - discount_amount + charges_amount + tax_amount
            )
            line = SalesInvoiceLine(
                sales_invoice_id=row.id,
                firm_id=firm_id,
                line_number=index,
                source_document_type=source_type,
                source_document_id=spec["source_document_id"],
                source_document_number=self._source_document_number(
                    spec, priced_source
                ),
                source_document_line_id=priced_source.id,
                source_document_line_number=self._source_line_number(priced_source),
                product_id=self._product_id(priced_source),
                description=self._source_description(priced_source),
                delivered_quantity=source_quantity,
                already_invoiced_quantity=already_invoiced,
                current_invoice_quantity=invoice_quantity,
                free_quantity=free_quantity,
                unit_price=unit_price,
                discount_percent=line_discount.percent,
                discount_amount=line_discount.amount,
                bill_discount_amount=bill_share,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=line_tax.profile_id,
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                order_uom_id=spec.get("order_uom_id") or source_uom_id,
                invoice_uom_id=spec.get("invoice_uom_id"),
                conversion_factor=conversion_factor,
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
            # lines are rebuilt on every edit, and `ondelete="CASCADE"` takes
            # the components with them.
            self._session.flush()
            for sequence, component in enumerate(line_tax.components, start=1):
                self._session.add(
                    SalesInvoiceLineTax(
                        sales_invoice_line_id=line.id,
                        firm_id=firm_id,
                        sequence=sequence,
                        tax_component_id=component.tax_component_id,
                        component_code=component.code,
                        component_label=component.label,
                        percentage=component.percentage,
                        base_amount=component.base_amount,
                        amount=component.amount,
                        included_in_price=component.included_in_price,
                        recoverable=component.recoverable,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
            totals["total_source_quantity"] += source_quantity
            totals["total_already_invoiced_quantity"] += already_invoiced
            totals["total_current_invoice_quantity"] += invoice_quantity
            totals["total_free_quantity"] += free_quantity
            totals["line_discount_total"] += discount_amount
            # subtotal is the taxable base: gross less discount, before tax and
            # before charges. Line charges used to be folded in here, which made
            # this module's subtotal mean something different from every other
            # document's; they are carried separately and added to grand_total.
            totals["subtotal"] += self._q(gross_amount - discount_amount)
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

    def _replace_attachments(
        self,
        row: SalesInvoice,
        attachments: list[SalesInvoiceAttachmentWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceAttachment).filter(
            SalesInvoiceAttachment.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for attachment in attachments:
            self._session.add(
                SalesInvoiceAttachment(
                    sales_invoice_id=row.id,
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
        row: SalesInvoice,
        notes: list[SalesInvoiceNoteWrite],
        *,
        actor_id: UUID,
        firm_id: UUID,
    ) -> None:
        self._session.query(SalesInvoiceNote).filter(
            SalesInvoiceNote.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        for note in notes:
            self._session.add(
                SalesInvoiceNote(
                    sales_invoice_id=row.id,
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
        self, row: SalesInvoice, *, actor_id: UUID, firm_id: UUID
    ) -> None:
        self._session.query(SalesInvoiceAccountingEvent).filter(
            SalesInvoiceAccountingEvent.sales_invoice_id == row.id
        ).delete(synchronize_session=False)
        events = [
            (
                SalesInvoiceAccountingEventType.SALES_REVENUE.value,
                "Sales Revenue",
                "CREDIT",
                row.subtotal,
            ),
            (
                SalesInvoiceAccountingEventType.OUTPUT_TAX.value,
                "Output Tax",
                "CREDIT",
                row.tax_total,
            ),
            (
                SalesInvoiceAccountingEventType.ACCOUNTS_RECEIVABLE.value,
                "Accounts Receivable",
                "DEBIT",
                row.grand_total,
            ),
        ]
        for event_type, account_name, direction, amount in events:
            self._session.add(
                SalesInvoiceAccountingEvent(
                    sales_invoice_id=row.id,
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
        self, data: SalesInvoiceCreate, firm_id: UUID
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
            if source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value:
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
                        "route_id": note.route_id,
                    }
                )
            elif source_type == SalesInvoiceSourceType.SALES_ORDER.value:
                # Reaching here means the firm raises its own delivery notes --
                # `SalesChainService` has already converted this source into
                # the note it dispatched otherwise. Billing an order directly
                # would post revenue with no movement behind it: no stock out,
                # no cost of goods sold, and the order's reservation left open
                # for ever. It used to be permitted by a boolean the caller set
                # on itself, which is not a control.
                raise ValidationError(
                    "This firm ships on a delivery note before it bills. "
                    "Dispatch the order, or turn the delivery-note stage off."
                )
            else:
                raise ValidationError("Unsupported source document type.")
        if not source_rows:
            raise ValidationError("At least one source document is required.")
        first = source_rows[0]
        for field in (
            "customer_id",
            "branch_id",
            "salesman_id",
            "territory_id",
            "route_id",
        ):
            value = _optional_uuid(first.get(field))
            if value is not None:
                header[field] = value
        for source in source_rows[1:]:
            if (
                source["customer_id"] != header["customer_id"]
                or source["branch_id"] != header["branch_id"]
            ):
                raise ValidationError(
                    "All source documents must belong to the same customer and branch."
                )
            if (
                header.get("salesman_id") not in {None, source.get("salesman_id")}
                and source.get("salesman_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same salesman."
                )
            if (
                header.get("territory_id") not in {None, source.get("territory_id")}
                and source.get("territory_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same territory."
                )
            if (
                header.get("route_id") not in {None, source.get("route_id")}
                and source.get("route_id") is not None
            ):
                raise ValidationError(
                    "All source documents must belong to the same route."
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

    def _validate_line_sources(
        self, lines: list[dict[str, object]], source_ids: set[UUID]
    ) -> None:
        for line in lines:
            if line["source_document_id"] not in source_ids:
                raise ValidationError(
                    "Every invoice line must reference a selected source document."
                )

    def _delete_children(self, invoice_id: UUID) -> None:
        self._session.query(SalesInvoiceAccountingEvent).filter(
            SalesInvoiceAccountingEvent.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceLine).filter(
            SalesInvoiceLine.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceSource).filter(
            SalesInvoiceSource.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceAttachment).filter(
            SalesInvoiceAttachment.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceNote).filter(
            SalesInvoiceNote.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)

    @staticmethod
    def _due_date(customer: Customer | None, invoice_date: date) -> date | None:
        """Return when payment falls due, from the customer's terms.

        A customer carries `payment_terms_days` and every traced invoice
        carried `due_date = NULL`, because nothing put the two together. The
        caller's own date always wins -- this only fills the gap.
        """
        if customer is None or not customer.payment_terms_days:
            return None
        return invoice_date + timedelta(days=int(customer.payment_terms_days))

    @staticmethod
    def _place_of_supply(customer: Customer | None) -> str | None:
        """Return the state the supply is made in.

        Copied onto the invoice rather than read through the customer at print
        time: it decides CGST + SGST against IGST, and a customer who moves must
        not change the tax treatment of an invoice already issued.

        The state lives on the address, not on the customer -- a customer can
        hold several. The billing address is what a tax invoice is addressed
        to, so that one is preferred, then whichever address is flagged as the
        default for billing, then any live address at all.
        """
        if customer is None:
            return None
        live = [
            address
            for address in (customer.addresses or [])
            if not address.is_deleted and address.state
        ]
        for match in (
            lambda address: address.address_type == "BILLING",
            lambda address: bool(address.is_default_billing),
            lambda address: True,
        ):
            for address in live:
                if match(address):
                    return str(address.state)
        return None

    def _resolve_tax(
        self,
        *,
        invoice_date: date,
        firm_id: UUID,
        actor_id: UUID,
        business_profile_id: UUID | None,
        customer_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID | None,
        product_id: UUID,
        tax_profile_id: UUID | None,
        invoice_value: Decimal,
    ) -> _LineTax:
        """Work out the line's tax, and keep everything that decided it.

        This used to return one number and discard the rest, which is why an
        invoice line recorded `tax_amount` and a NULL `tax_profile_id` -- the
        profile it resolved was thrown away along with the component breakup.
        A printed tax invoice has to state both, so both are returned and
        stored.
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
            transaction_type="SALES_INVOICE",
            transaction_date=invoice_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={"source": "sales_invoice"},
        )
        response = self._tax.simulate(request, firm_scope=firm_id, actor_id=actor_id)
        return _LineTax(
            # The resolved profile, not the one the caller sent: a client that
            # names none still gets the product's, and the line should say so.
            profile_id=response.applied_tax_profile_id or tax_profile_id,
            total=self._q(response.total_tax_amount),
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

    def _source_quantity(self, spec: dict[str, object], source_line: object) -> Decimal:
        """How much of the source line an invoice may charge for.

        `current_delivery_quantity`, **not** `delivered_quantity`. The latter
        is what physically left the warehouse -- charged goods plus free ones,
        converted into inventory units -- which is right for stock and wrong
        twice over here.

        It let an invoice **charge for goods that were given away**: a note
        delivering 12 with 1 free capped billing at 13, and billing that
        thirteenth unit at 195.00 plus tax was accepted against a seeded note.
        And it pro-rated inherited free goods by the wrong denominator, so
        billing all 12 carried 12/13 of a free unit and the printed bill read
        "12 + 0.923 free" -- a fraction of a gift nobody can hand over.

        The units were wrong as well. `invoice_quantity` is converted into the
        source line's *sales* UOM, which is what `current_delivery_quantity`
        is stored in; `delivered_quantity` is post-conversion inventory units,
        so for any product whose two units differ the cap was inflated by the
        whole conversion factor.
        """
        if (
            self._source_type(spec["source_document_type"])
            == SalesInvoiceSourceType.DELIVERY_NOTE.value
        ):
            return self._q(getattr(source_line, "current_delivery_quantity", ZERO))
        return self._q(getattr(source_line, "quantity", ZERO))

    def billable_documents(
        self,
        *,
        firm_scope: UUID,
        limit: int = 50,
    ) -> list[BillableDocument]:
        """Return what is still waiting to be billed, newest first.

        Delivery notes that have been dispatched and sales orders that were
        approved and never delivered against -- the two things an invoice can
        be raised from. A document appears only while some line still has
        quantity left, so a fully billed note drops out of the list rather
        than being offered and then refused.

        The remaining quantity is derived the same way ``create_invoice``
        derives it, through ``_already_invoiced_quantity``, so the number
        offered here is the number the save will accept. Cancelled invoices do
        not count against a line, which means cancelling one puts its quantity
        back on this list.
        """
        documents: list[BillableDocument] = []

        # What every invoice has already taken from each delivery line, as a
        # subquery rather than a loop: the filter below needs it before it can
        # know which notes are worth returning.
        invoiced = (
            select(
                SalesInvoiceLine.source_document_line_id.label("line_id"),
                func.coalesce(
                    func.sum(SalesInvoiceLine.current_invoice_quantity), ZERO
                ).label("taken"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
            )
            .group_by(SalesInvoiceLine.source_document_line_id)
            .subquery()
        )

        # The limit is applied to notes that still have something left, not to
        # candidates that are then filtered -- otherwise a firm whose newest
        # fifty notes are all billed sees an empty list while older billable
        # ones sit behind them. Found by asking for one and getting none.
        open_notes = (
            select(DeliveryNoteLine.delivery_note_id)
            .outerjoin(invoiced, invoiced.c.line_id == DeliveryNoteLine.id)
            .where(
                DeliveryNoteLine.is_deleted.is_(False),
                or_(
                    DeliveryNoteLine.current_delivery_quantity
                    - func.coalesce(invoiced.c.taken, ZERO)
                    > ZERO,
                    # A note whose only content is a gift has no charged
                    # quantity left from the moment it is dispatched, so the
                    # test above hid the whole note and the goods that had
                    # left the warehouse were never billable at all. Such a
                    # line is owed until an invoice line references it --
                    # counted in rows, because its quantity is zero either
                    # way.
                    and_(
                        DeliveryNoteLine.current_delivery_quantity <= ZERO,
                        DeliveryNoteLine.free_quantity > ZERO,
                        invoiced.c.line_id.is_(None),
                    ),
                ),
            )
        )

        notes = self._session.scalars(
            select(DeliveryNote)
            .where(
                DeliveryNote.firm_id == firm_scope,
                DeliveryNote.is_deleted.is_(False),
                DeliveryNote.status.in_(
                    [
                        DeliveryNoteStatus.DISPATCHED.value,
                        DeliveryNoteStatus.COMPLETED.value,
                        DeliveryNoteStatus.CLOSED.value,
                    ]
                ),
                DeliveryNote.id.in_(open_notes),
            )
            .order_by(DeliveryNote.delivery_date.desc())
            .limit(limit)
        ).all()

        for note in notes:
            lines = self._session.scalars(
                select(DeliveryNoteLine)
                .where(
                    DeliveryNoteLine.delivery_note_id == note.id,
                    DeliveryNoteLine.is_deleted.is_(False),
                )
                .order_by(DeliveryNoteLine.line_number.asc())
            ).all()
            billable = [
                line
                for line in (
                    self._billable_line(
                        firm_id=firm_scope,
                        line_id=item.id,
                        line_number=item.line_number,
                        product_id=item.product_id,
                        description=item.description,
                        source_quantity=self._q(item.current_delivery_quantity),
                        unit_price=self._q(item.unit_price),
                        discount_percent=self._q(item.discount_percent),
                        discount_amount=self._q(item.discount_amount),
                        free_quantity=self._q(item.free_quantity),
                    )
                    for item in lines
                )
                if line is not None
            ]
            if not billable:
                continue
            documents.append(
                BillableDocument(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_number=note.delivery_note_number,
                    document_date=note.delivery_date,
                    customer_id=note.customer_id,
                    customer_name=self._customer_name(note.customer_id),
                    branch_id=note.branch_id,
                    lines=billable,
                )
            )

        documents.extend(self._billable_orders(firm_scope=firm_scope, limit=limit))
        return documents

    def _raised_its_own_dispatch(
        self, data: SalesInvoiceCreate, *, firm_id: UUID
    ) -> bool:
        """Report whether this bill shipped the goods it charges for.

        True when the firm's configuration leaves the delivery note to the
        service, which is the only way an invoice now reaches approval without
        somebody having dispatched its goods by hand. Recorded so a reader can
        tell the two kinds of bill apart afterwards.
        """
        return (
            not SalesWorkflowService(self._session)
            .settings_for(firm_id)
            .delivery_note_stage
        )

    def _billable_orders(
        self, *, firm_scope: UUID, limit: int
    ) -> list[BillableDocument]:
        """Approved orders that nothing has been dispatched against.

        Billing before dispatch is a real thing -- a firm that takes payment
        up front invoices the order -- and `allow_direct_sales_order` has
        always permitted it. What must not happen is an order and its own
        delivery note both being offered: `_already_invoiced_quantity` is keyed
        on the **source line id**, and an order line and the delivery line
        raised from it are different ids, so billing both would charge the
        customer twice for one set of goods and no guard would notice.

        So an order is offered only while it has no delivery note at all. Once
        anything ships, the note is the document that knows what left.

        And only where the firm leaves delivery notes to the service, since
        that is the only configuration in which billing an order dispatches
        anything. Offering one to a firm that ships by hand invites a bill the
        service now refuses.
        """
        if (
            SalesWorkflowService(self._session)
            .settings_for(firm_scope)
            .delivery_note_stage
        ):
            return []
        delivered = select(DeliveryNote.sales_order_id).where(
            DeliveryNote.firm_id == firm_scope,
            DeliveryNote.is_deleted.is_(False),
            DeliveryNote.status != DeliveryNoteStatus.CANCELLED.value,
        )

        invoiced = (
            select(
                SalesInvoiceLine.source_document_line_id.label("line_id"),
                func.coalesce(
                    func.sum(SalesInvoiceLine.current_invoice_quantity), ZERO
                ).label("taken"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
            )
            .group_by(SalesInvoiceLine.source_document_line_id)
            .subquery()
        )

        open_orders = (
            select(SalesOrderLine.sales_order_id)
            .outerjoin(invoiced, invoiced.c.line_id == SalesOrderLine.id)
            .where(
                SalesOrderLine.is_deleted.is_(False),
                SalesOrderLine.quantity - func.coalesce(invoiced.c.taken, ZERO) > ZERO,
            )
        )

        orders = self._session.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.firm_id == firm_scope,
                SalesOrder.is_deleted.is_(False),
                SalesOrder.status == SalesOrderStatus.APPROVED.value,
                SalesOrder.id.notin_(delivered),
                SalesOrder.id.in_(open_orders),
            )
            .order_by(SalesOrder.order_date.desc())
            .limit(limit)
        ).all()

        documents: list[BillableDocument] = []
        for order in orders:
            lines = self._session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == order.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number.asc())
            ).all()
            billable = [
                line
                for line in (
                    self._billable_line(
                        firm_id=firm_scope,
                        line_id=item.id,
                        line_number=item.line_number,
                        product_id=item.product_id,
                        description=item.description,
                        source_quantity=self._q(item.quantity),
                        unit_price=self._q(item.unit_price),
                        discount_percent=self._q(item.discount_percent),
                        discount_amount=self._q(item.discount_amount),
                        free_quantity=self._q(item.free_quantity),
                    )
                    for item in lines
                )
                if line is not None
            ]
            if not billable:
                continue
            documents.append(
                BillableDocument(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_number=order.order_number,
                    document_date=order.order_date,
                    customer_id=order.customer_id,
                    customer_name=self._customer_name(order.customer_id),
                    branch_id=order.branch_id,
                    lines=billable,
                )
            )
        return documents

    def _billable_line(
        self,
        *,
        firm_id: UUID,
        line_id: UUID,
        line_number: int,
        product_id: UUID | None,
        description: str | None,
        source_quantity: Decimal,
        unit_price: Decimal,
        discount_percent: Decimal,
        discount_amount: Decimal,
        free_quantity: Decimal,
    ) -> BillableLine | None:
        """Return one line's remaining quantity, or None if it is fully billed.

        A line whose whole content is a gift -- nothing charged for, goods
        supplied free -- has a remaining quantity of zero from the moment it
        is written, and reading that as "fully billed" excluded it from every
        list of what a document still owes. The goods had already left the
        warehouse, so the bill the customer reads was silent about stock that
        was physically gone.

        It is offered exactly once, counted by **invoice lines** rather than
        by quantity: zero minus zero is zero however many times the gift has
        already been stated, so the quantity test can never say it is done.
        """
        already = self._already_invoiced_quantity(
            firm_id=firm_id, source_document_line_id=line_id
        )
        remaining = self._q(source_quantity - already)
        if remaining <= ZERO:
            gift_only = source_quantity <= ZERO < free_quantity
            if not gift_only or self._already_invoiced(
                firm_id=firm_id, source_document_line_id=line_id
            ):
                return None
        return BillableLine(
            source_document_line_id=line_id,
            line_number=line_number,
            product_id=product_id,
            description=description,
            source_quantity=source_quantity,
            already_invoiced_quantity=already,
            remaining_quantity=remaining,
            unit_price=unit_price,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            free_quantity=free_quantity,
        )

    def _customer_name(self, customer_id: UUID | None) -> str:
        """Name the customer so a picker is not a list of UUIDs."""
        if customer_id is None:
            return ""
        customer = self._session.get(Customer, customer_id)
        return "" if customer is None else (customer.display_name or customer.name)

    def _already_invoiced_quantity(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> Decimal:
        total = self._session.scalar(
            select(
                func.coalesce(func.sum(SalesInvoiceLine.current_invoice_quantity), ZERO)
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLine.source_document_line_id == source_document_line_id,
            )
        )
        return self._q(total or ZERO)

    def _already_invoiced(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> bool:
        """Say whether any live invoice line already bills this source line.

        Counted in rows, not in quantity. A line whose whole content is a gift
        bills a quantity of zero, so summing quantities can never tell the
        first statement of it from the second.
        """
        found = self._session.scalar(
            select(SalesInvoiceLine.id)
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLine.source_document_line_id == source_document_line_id,
            )
            .limit(1)
        )
        return found is not None

    def _conversion_factor(self, spec: dict[str, object]) -> Decimal:
        return self._q(Decimal(str(spec.get("conversion_factor", Decimal("1")))))

    def _source_type(self, value: object) -> str:
        return value.value if hasattr(value, "value") else str(value)

    def _source_uom_id(self, source_line: SourceLine) -> UUID | None:
        return getattr(source_line, "sales_uom_id", None) or getattr(
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
        if isinstance(source_line, DeliveryNoteLine):
            note = self._session.scalar(
                select(DeliveryNote).where(
                    DeliveryNote.id == source_line.delivery_note_id
                )
            )
            if note is not None:
                return note.delivery_note_number
            return str(source_number or "")
        order = self._session.scalar(
            select(SalesOrder).where(SalesOrder.id == source_line.sales_order_id)
        )
        if order is not None:
            return order.order_number
        return str(source_number or "")

    def _product_id(self, source_line: SourceLine) -> UUID:
        return source_line.product_id

    def _invoice_free_quantity(
        self,
        *,
        spec: dict[str, object],
        source_line: SourceLine,
        invoice_quantity: Decimal,
        source_quantity: Decimal,
    ) -> Decimal:
        """Return how much this line supplies free.

        Inherited from the document being billed rather than typed again, and
        pro-rated by the share being billed: half an order invoiced carries
        half the free goods it was promised. An explicit figure wins, and an
        explicit zero refuses the inheritance.

        Refused above what the source line offered, because an invoice states
        what was supplied and the goods left on somebody else's document. A
        bill claiming free goods nobody dispatched is a bill the warehouse
        cannot reconcile.
        """
        offered = self._q(
            Decimal(str(getattr(source_line, "free_quantity", ZERO) or ZERO))
        )
        asked = spec.get("free_quantity")
        if asked is None:
            if offered <= ZERO:
                return ZERO
            if source_quantity <= ZERO:
                # The source line charged for nothing, so there is no share to
                # pro-rate by: what it supplied free is the whole of what it
                # supplied. Returning zero here dropped the gift off the bill
                # entirely while the goods had already been dispatched.
                return offered
            return self._q(offered * invoice_quantity / source_quantity)
        claimed = self._q(Decimal(str(asked)))
        if claimed > offered:
            raise ValidationError(
                "Free quantity exceeds what the source document supplied free."
            )
        return claimed

    def _invoice_line_discount(
        self,
        *,
        spec: dict[str, object],
        source_line: object,
        gross: Decimal,
        invoice_quantity: Decimal,
        source_quantity: Decimal,
    ) -> LineDiscount:
        """Return the discount for one invoice line.

        What the line itself says wins. Where it says nothing, the discount is
        **inherited from the document being billed** rather than re-read from
        the customer: a price agreed on an order in March is not rewritten by
        an edit to the customer master in August. It is the same reasoning that
        stops this module re-deriving territory and salesman.

        A percentage inherits cleanly across a partial invoice, because a rate
        does not care about quantity. An absolute amount is pro-rated by the
        share being billed -- and across several partial invoices that can
        leave a residual of a fraction of a paisa, which nothing trues up. At
        four decimal places that is under a paisa per line, and a percentage
        has no residual at all.
        """
        percent = spec.get("discount_percent")
        amount = spec.get("discount_amount")
        if percent is None and amount is None:
            inherited_percent = getattr(source_line, "discount_percent", None)
            inherited_amount = getattr(source_line, "discount_amount", None)
            if inherited_percent:
                percent = inherited_percent
            elif inherited_amount and source_quantity > ZERO:
                amount = self._q(
                    Decimal(str(inherited_amount)) * invoice_quantity / source_quantity
                )
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

    def _fill_missing_scope(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        salesman_id: UUID | None,
        territory_id: UUID | None,
        route_id: UUID | None,
        on_date: date,
    ) -> tuple[UUID | None, UUID | None, UUID | None]:
        """Derive the territory, route and salesman this invoice never got.

        Fills blanks only. An invoice raised from an order or a delivery note
        inherits all three, and re-deriving them would let the invoice drift
        from the document it bills -- a customer moved to another round last
        week must not retag the order they placed last month. So what arrived
        from a source, or from the caller, is left exactly as it is; only a
        standalone invoice with nothing to inherit is resolved from the
        customer's own assignments.
        """
        if territory_id is not None and salesman_id is not None:
            return salesman_id, territory_id, route_id
        derived = resolve_sales_scope(
            self._session, firm_id=firm_id, customer_id=customer_id, on_date=on_date
        )
        return (
            salesman_id if salesman_id is not None else derived.salesman_id,
            territory_id if territory_id is not None else derived.territory_id,
            route_id if route_id is not None else derived.route_id,
        )

    def _validate_scope_references(
        self,
        *,
        firm_id: UUID,
        salesman_id: UUID | None,
        territory_id: UUID | None,
        route_id: UUID | None,
    ) -> None:
        if salesman_id is not None:
            # The third copy of this check, and the third to reach for `users`
            # on the request session -- `sales_order` and `delivery_note` were
            # the other two. All three were invisible until the demo seed put
            # a salesman on a round, at which point every document derived one
            # and the whole chain failed at the invoice.
            #
            # It also asks the right question now: membership of *this* firm,
            # not mere existence somewhere.
            members = FirmMetadataReader(self._session).active_member_count(
                firm_id, [salesman_id]
            )
            if members != 1:
                raise ValidationError("Salesman is not an active member of this firm.")
        if territory_id is not None:
            territory = self._session.scalar(
                select(SalesTerritoryNode.id).where(
                    SalesTerritoryNode.id == territory_id,
                    SalesTerritoryNode.firm_id == firm_id,
                    SalesTerritoryNode.is_deleted.is_(False),
                )
            )
            if territory is None:
                raise ValidationError("Territory not found in this firm.")
        if route_id is not None:
            route = self._session.scalar(
                select(TerritoryRouteProfile.id).where(
                    TerritoryRouteProfile.id == route_id,
                    TerritoryRouteProfile.is_deleted.is_(False),
                )
            )
            if route is None:
                raise ValidationError("Route profile not found.")

    def _validate_customer_invoice_number(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        customer_invoice_number: str | None,
        current_id: UUID | None = None,
    ) -> None:
        warning = self._duplicate_warning(
            firm_id=firm_id,
            customer_id=customer_id,
            customer_invoice_number=customer_invoice_number,
            current_id=current_id,
        )
        if warning is not None:
            raise ConflictError(warning)

    def _duplicate_warning(
        self,
        *,
        firm_id: UUID,
        customer_id: UUID,
        customer_invoice_number: str | None,
        current_id: UUID | None,
    ) -> str | None:
        normalized_number = (
            customer_invoice_number.strip() if customer_invoice_number else None
        )
        if not normalized_number:
            return None
        statement = select(SalesInvoice.id).where(
            SalesInvoice.firm_id == firm_id,
            SalesInvoice.customer_id == customer_id,
            SalesInvoice.customer_invoice_number == normalized_number,
            SalesInvoice.is_deleted.is_(False),
        )
        if current_id is not None:
            statement = statement.where(SalesInvoice.id != current_id)
        if self._session.scalar(statement) is not None:
            return "A sales invoice with this customer invoice number already exists."
        return None

    def _reverse_invoice_posting(
        self,
        row: SalesInvoice,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> None:
        """Cancel the journal an approved invoice wrote, if it wrote one.

        Found by `scripts/verify_sample_data.py`, which compares what customers
        owe against the receivable control account: cancelling an approved
        invoice moved the first and not the second.
        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "sales_invoice",
                JournalEntry.source_id == row.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # Nothing posted, so there is nothing to take back -- a firm that
            # approved invoices before posting existed is in this state.
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
        invoice: SalesInvoice,
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
                source_module_code="SALES_INVOICE",
                document_number=invoice.invoice_number,
                action=action,
                from_state=from_state,
                to_state=to_state,
                remarks=remarks,
                details_json={
                    "invoice_number": invoice.invoice_number,
                    "customer_invoice_number": invoice.customer_invoice_number,
                    "grand_total": str(invoice.grand_total),
                },
                snapshot_json={
                    "status": invoice.status,
                    "customer_id": str(invoice.customer_id),
                    "branch_id": str(invoice.branch_id),
                },
                actor_id=actor_id,
            ),
            actor_id=actor_id,
        )

    def _attachment_response(
        self, row: SalesInvoiceAttachment
    ) -> SalesInvoiceAttachmentResponse:
        return SalesInvoiceAttachmentResponse.model_validate(row)

    def _note_response(self, row: SalesInvoiceNote) -> SalesInvoiceNoteResponse:
        return SalesInvoiceNoteResponse.model_validate(row)

    def _source_response(self, row: SalesInvoiceSource) -> SalesInvoiceSourceResponse:
        return SalesInvoiceSourceResponse(
            id=row.id,
            source_document_type=SalesInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_date=row.source_document_date,
            customer_id=row.customer_id,
            branch_id=row.branch_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _accounting_event_response(
        self, row: SalesInvoiceAccountingEvent
    ) -> SalesInvoiceAccountingEventResponse:
        return SalesInvoiceAccountingEventResponse(
            id=row.id,
            event_type=SalesInvoiceAccountingEventType(row.event_type),
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
        row: SalesInvoiceLine,
        taxes: list[SalesInvoiceLineTax] | None = None,
    ) -> SalesInvoiceLineResponse:
        return SalesInvoiceLineResponse(
            id=row.id,
            sales_invoice_id=row.sales_invoice_id,
            line_number=row.line_number,
            source_document_type=SalesInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            description=row.description,
            delivered_quantity=row.delivered_quantity,
            already_invoiced_quantity=row.already_invoiced_quantity,
            current_invoice_quantity=row.current_invoice_quantity,
            unit_price=row.unit_price,
            discount_percent=row.discount_percent,
            free_quantity=row.free_quantity,
            discount_amount=row.discount_amount,
            bill_discount_amount=row.bill_discount_amount,
            charges_amount=row.charges_amount,
            gross_amount=row.gross_amount,
            tax_profile_id=row.tax_profile_id,
            tax_amount=row.tax_amount,
            net_amount=row.net_amount,
            packaging_type_id=row.packaging_type_id,
            order_uom_id=row.order_uom_id,
            invoice_uom_id=row.invoice_uom_id,
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
                SalesInvoiceLineTaxResponse(
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
                )
                for component in (taxes or [])
            ],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
