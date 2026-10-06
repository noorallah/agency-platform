"""Sales invoice workflow, source matching, and placeholder accounting service."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, lazyload, load_only

from app.batch_serial.schemas import PickedSerial
from app.batch_serial.services.mrp_ceiling import refuse_above_batch_mrp
from app.batch_serial.services.serial_trail_service import SerialTrailService
from app.business.gating import assert_feature_fields
from app.business.models.framework import AttributeEntityType
from app.business.services import document_attributes
from app.common.audit.services import record_audit
from app.common.firm_metadata import FirmMetadataReader, firm_today
from app.common.report_names import (
    branch_names,
    customer_labels,
    customer_names,
    customers_matching,
    product_names,
    salesman_names,
    territory_names,
)
from app.core.database.batch import children_by_parent
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.pagination import WHOLE_HISTORY, ReportRows, ReportWindow, mapped_like
from app.core.utils.chunks import chunks
from app.core.utils.dates import utc_now
from app.core.utils.money import quantize_ledger
from app.core.utils.pricing import (
    LineDiscount,
    apportion,
    continued_free_goods,
    continued_share,
    resolve_bill_discount,
    resolve_line_discount,
)
from app.core.utils.quantities import plain_quantity
from app.customers.gst_registration import effective_type, sez_tax_warning
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CreditControlService
from app.customers.services.customer_service import CustomerService
from app.customers.services.ship_to import resolve_ship_to, ship_to_is_valid
from app.customers.services.trading_status import assert_customer_may_be_billed
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteLine,
    DeliveryNoteLineBatch,
)
from app.delivery_note.rules import goods_have_left_clause, require_dispatched_note
from app.delivery_note.schemas import DeliveryNoteBatchPick, DeliveryNoteStatus
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
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
from app.finance.models import JournalEntry, JournalStatus
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.inventory.models import StockLedgerEntry
from app.loyalty.services import LoyaltyService
from app.loyalty.services.redemption_reversal import RedemptionReversalService
from app.messaging.services import MessagingDocument, stage_document_event
from app.products.models import Product
from app.products.services.free_issue import assert_not_sold_at_a_price
from app.promotions.services import RedemptionService
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales.services.document_preview import line_companions
from app.sales.services.scope_resolution import (
    resolve_sales_scope,
    validate_named_route,
)
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceAccountingEvent,
    SalesInvoiceAttachment,
    SalesInvoiceCharge,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
    SalesInvoiceNote,
    SalesInvoiceSource,
    SalesInvoiceTender,
)
from app.sales_invoice.schemas import (
    BillableDocument,
    BillableLine,
    SalesInvoiceAccountingEventResponse,
    SalesInvoiceAccountingEventType,
    SalesInvoiceAttachmentResponse,
    SalesInvoiceAttachmentWrite,
    SalesInvoiceChargeResponse,
    SalesInvoiceChargeWrite,
    SalesInvoiceCreate,
    SalesInvoiceCustomerOutstandingRecord,
    SalesInvoiceImportRequest,
    SalesInvoiceLineResponse,
    SalesInvoiceLineTaxResponse,
    SalesInvoiceLineWrite,
    SalesInvoiceListFilters,
    SalesInvoiceNoteResponse,
    SalesInvoiceNoteWrite,
    SalesInvoiceOverdueRecord,
    SalesInvoicePreview,
    SalesInvoiceReconciliationRecord,
    SalesInvoiceRegisterRecord,
    SalesInvoiceResponse,
    SalesInvoiceSourceResponse,
    SalesInvoiceSourceType,
    SalesInvoiceSourceWrite,
    SalesInvoiceStatus,
    SalesInvoiceSummary,
    SalesInvoiceTenderResponse,
)
from app.sales_invoice.services.line_units import (
    unit_of_a_line_billing_a_document,
)
from app.sales_invoice.services.output_tax import invoice_tax_by_component
from app.sales_invoice.services.sales_chain_service import (
    SalesChainService,
    refuse_coupon_on_documents,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderStatus
from app.sales_order.services.discount_limit import (
    NOTE_REDUCTION_JUDGED,
    TYPED_SOURCES,
    DiscountLimitService,
    invoice_discounts,
    note_reduction,
)
from app.sales_order.services.price_floor import PriceFloorService, invoice_lines
from app.sales_order.services.sales_order_service import (
    SalesOrderService,
    normalized_coupon,
)
from app.sales_order.services.workflow_settings_service import SalesWorkflowService
from app.settlements.schemas import OutstandingInvoiceRecord
from app.tax.schemas import TaxRuleSimulationRequest
from app.tax.services.gst_buckets import TaxComponent, split_components
from app.tax.services.inclusive_rate import (
    PreTaxLine,
    billed_rate,
    derive_pre_tax,
)
from app.tax.services.place_of_supply import SALES_INTERSTATE
from app.tax.services.rule_stamp import stamps_tax_rules
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.trade_licences.services.licence_check import (
    LicenceCheckService,
    LicenceDocument,
)
from app.uom.services import (
    UomService,
    assert_quantity_fits_unit,
    exact_quantity,
    stock_unit_of,
    unit_named,
)

ZERO = Decimal("0")
#: An order's `bill_discount_source` where nobody typed its bill discount:
#: an offer gave it, or there is none.
OFFERED = frozenset({"promotion", "none"})

# The two line shapes a sales invoice can be raised from. Naming the union lets
# the helpers below say what they accept instead of taking ``object`` and
# reaching for attributes mypy cannot see.
SourceLine = DeliveryNoteLine | SalesOrderLine


def _optional_uuid(value: object) -> UUID | None:
    """Read a UUID out of an untyped line spec."""
    return value if isinstance(value, UUID) else None


def _walk_in_buyer(
    customer: Customer | None, data: SalesInvoiceCreate
) -> tuple[str | None, str | None]:
    """Return the buyer a walk-in bill names, as typed at the counter.

    Only a bill to the firm's *Cash sale* customer carries one (backlog 87
    #2): any other customer has a name of its own, and a second one typed on
    the bill would print a buyer the books do not know.

    Raises:
        ValidationError: When a buyer is typed on a bill to another customer.

    """
    name = (data.buyer_name or "").strip() or None
    phone = (data.buyer_phone or "").strip() or None
    if customer is not None and customer.is_cash_sale:
        return name, phone
    if name or phone:
        raise ValidationError(
            "A buyer's name and phone are typed only on a walk-in bill. This "
            "bill names a customer with a record; correct the customer instead."
        )
    return None, None


def _receivable_amount(value: Decimal) -> Decimal:
    """Round an invoice total to the scale the receivable ledger stores.

    Kept as a name local to this module, delegating to the shared helper. It
    was a private copy of that rounding until 2026-08-24, which is exactly how
    `sales_return` came to carry the same defect untouched: the fix lived here
    and its sibling never saw it.
    """
    return quantize_ledger(value)


def _buyer_gst_type(customer: Customer | None) -> str | None:
    """Return the buyer's GST standing to stamp on a bill (backlog 75 row 2).

    Stamped with the place of supply, and for the same reason: a customer
    re-classified later must not change how a bill already issued is filed.
    """
    if customer is None:
        return None
    return effective_type(customer.gst_registration_type, customer.gst_number)


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
    #: The fraction of the line's value billed as tax, which a rate typed
    #: with GST in it is divided by (backlog 64 row 4).
    billed_rate: Decimal = ZERO


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
    #: What was typed, where the line was typed in another unit than its
    #: source line's (D-PRC-37); None otherwise.
    entered_quantity: Decimal | None
    source_uom_id: UUID | None
    #: The unit the line was typed in, where it names another than the line
    #: it bills by either unit field (D-PRC-44); None otherwise.
    typed_uom_id: UUID | None
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
        if filters.is_held is not None:
            # The counter's parked bills, or everything but them (SG-7).
            statement = statement.where(SalesInvoice.is_held.is_(filters.is_held))
            count = count.where(SalesInvoice.is_held.is_(filters.is_held))
        if search:
            token = f"%{search.strip()}%"
            condition = or_(
                SalesInvoice.invoice_number.ilike(token),
                SalesInvoice.customer_invoice_number.ilike(token),
                SalesInvoice.reference_number.ilike(token),
                SalesInvoice.remarks.ilike(token),
                SalesInvoice.customer_id.in_(customers_matching(token)),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        sort_column = columns.get(sort_by, SalesInvoice.created_at)
        rows = list(
            self._session.scalars(
                statement.order_by(
                    sort_column.desc() if descending else sort_column.asc(),
                    # Newest first within the chosen column, then a stable key.
                    SalesInvoice.created_at.desc(),
                    SalesInvoice.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def summary(self, *, firm_scope: UUID) -> SalesInvoiceSummary:
        """Return aggregate sales invoice values for the visible firm scope.

        Counted and summed in SQL, one row per status. It loaded every invoice
        the firm ever raised to count them in Python, on every visit to the
        Sales Invoices page (backlog 56 C).
        """
        by_status: dict[str, tuple[int, Decimal]] = {
            status: (int(count), Decimal(str(total)))
            for status, count, total in self._session.execute(
                select(
                    SalesInvoice.status,
                    func.count(),
                    func.coalesce(func.sum(SalesInvoice.grand_total), 0),
                )
                .where(
                    SalesInvoice.firm_id == firm_scope,
                    SalesInvoice.is_deleted.is_(False),
                )
                .group_by(SalesInvoice.status)
            ).all()
        }

        def count(status: SalesInvoiceStatus) -> int:
            """Return how many invoices are in one status."""
            return by_status.get(status.value, (0, ZERO))[0]

        # The tile and the overdue report must agree, so the tile counts the
        # report's rows: invoices past due that still owe something (D-RPT-3).
        # Counted off the owing bills themselves: building the report's rows
        # to count them read every one of them back (backlog 56 C, step 4).
        today = firm_today(self._session, firm_scope)
        overdue = sum(
            1
            for record in self._owing(firm_scope=firm_scope)
            if record.due_date is not None and record.due_date < today
        )
        return SalesInvoiceSummary(
            total=sum(number for number, _ in by_status.values()),
            draft=count(SalesInvoiceStatus.DRAFT),
            approved=count(SalesInvoiceStatus.APPROVED),
            cancelled=count(SalesInvoiceStatus.CANCELLED),
            closed=count(SalesInvoiceStatus.CLOSED),
            total_value=self._q(sum((value for _, value in by_status.values()), ZERO)),
            pending_invoices=count(SalesInvoiceStatus.DRAFT),
            overdue_invoices=overdue,
        )

    def create_invoice(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Create one sales invoice and commit it."""
        row = self.stage_invoice(data, firm_id=firm_id, actor_id=actor_id)
        if data.attributes:
            document_attributes.store(
                self._session,
                AttributeEntityType.SALES_INVOICE,
                row.id,
                data.attributes,
                firm_id=row.firm_id,
                actor_id=actor_id,
            )
        # Fields the source documents hold carry to this one (MST-6).
        document_attributes.carry_from_sources(
            self._session,
            AttributeEntityType.SALES_INVOICE,
            row.id,
            [
                (line.source_document_type, line.source_document_id)
                for line in self._session.scalars(
                    select(SalesInvoiceLine)
                    .where(
                        SalesInvoiceLine.sales_invoice_id == row.id,
                        SalesInvoiceLine.is_deleted.is_(False),
                    )
                    .order_by(SalesInvoiceLine.line_number)
                )
            ],
            firm_id=row.firm_id,
            actor_id=actor_id,
        )
        self._session.commit()
        return row

    def preview_invoice(
        self, data: SalesInvoiceCreate, *, firm_id: UUID, actor_id: UUID
    ) -> SalesInvoicePreview:
        """Price an invoice exactly as saving it would, then save nothing.

        See `SalesOrderService.preview_order`: staged, read back, rolled back.
        """
        try:
            row = self.stage_invoice(data, firm_id=firm_id, actor_id=actor_id)
            response = self.invoice_response(row)
            interstate = (
                self._tax.outward_transaction_type(
                    "SALES_INVOICE",
                    firm_id=firm_id,
                    branch_id=response.branch_id,
                    # The invoice's own customer: one billed from its source
                    # documents names none in the request.
                    customer_id=response.customer_id,
                    shipping_address_id=response.shipping_address_id,
                )
                == SALES_INTERSTATE
            )
            lines = line_companions(
                self._session,
                firm_id=firm_id,
                customer_id=response.customer_id,
                lines=[
                    (line.line_number, line.product_id, line.warehouse_id)
                    for line in response.lines
                ],
            )
        finally:
            self._session.rollback()
        return SalesInvoicePreview(invoice=response, interstate=interstate, lines=lines)

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
        chain = SalesChainService(self._session)
        rate_includes_tax = (
            data.rate_includes_tax
            if data.rate_includes_tax is not None
            else bool(
                SalesWorkflowService(self._session)
                .settings_for(firm_id)
                .rate_includes_tax
            )
        )
        typed: dict[int, PreTaxLine] = {}

        def before_tax(
            bill: SalesInvoiceCreate, branch_id: UUID, warehouse_id: UUID
        ) -> SalesInvoiceCreate:
            """Read the bill's typed GST-inclusive rates back to pre-tax."""
            return self._typed_rates_before_tax(
                bill,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                firm_id=firm_id,
                actor_id=actor_id,
                typed=typed,
            )

        data = chain.ensure_invoice_source(
            data,
            firm_id=firm_id,
            actor_id=actor_id,
            inclusive=before_tax if rate_includes_tax else None,
        )
        # The chain numbers the order, the note and the bill's lines after the
        # lines typed, so the line number finds the note line each one bills.
        entered_rates = {
            line.source_document_line_id: (
                typed[line.line_number].entered_rate,
                typed[line.line_number].unit_price,
            )
            for line in data.lines
            if line.line_number in typed and line.source_document_line_id is not None
        }
        own_notes = frozenset(note.id for note in chain.raised_notes)
        document_type, numbering_rule = self._ensure_document_setup(
            firm_id=firm_id, actor_id=actor_id
        )
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_id=firm_id, own_notes=own_notes
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
        self._assert_named_route_fits(
            data.route_id,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            on_date=data.invoice_date,
        )
        self._validate_customer_invoice_number(
            firm_id=firm_id,
            customer_id=customer_id,
            customer_invoice_number=data.customer_invoice_number,
        )
        invoice_number = self._issue_number(
            numbering_rule,
            typed=data.invoice_number.strip().upper() if data.invoice_number else None,
            number_column=SalesInvoice.invoice_number,
            firm_id=firm_id,
            document_date=data.invoice_date,
            actor_id=actor_id,
            branch_code=self._scope_code(branch_id),
            company_code=self._company_code(firm_id),
        )
        # Read once for the two fields below; the customer's terms decide when
        # payment falls due and its billing address decides the place of supply.
        customer = self._session.get(Customer, customer_id)
        if customer is not None:
            # A new outlet waiting for the office takes orders, not bills.
            assert_customer_may_be_billed(customer)
        buyer_name, buyer_phone = _walk_in_buyer(customer, data)
        shipping_address_id = self._ship_to(
            data.shipping_address_id,
            customer_id=customer_id,
            source_rows=source_rows,
        )
        terms, terms_days = self._order_terms(source_rows)
        row = SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            shipping_address_id=shipping_address_id,
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
            payment_terms=data.payment_terms or terms,
            due_date=data.due_date
            or self._due_date(customer, data.invoice_date, days=terms_days),
            place_of_supply=self._place_of_supply(
                customer, shipping_address_id=shipping_address_id
            ),
            buyer_gst_registration_type=_buyer_gst_type(customer),
            reference_number=data.reference_number,
            remarks=data.remarks,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            received_now_amount=self._q(data.received_now_amount),
            received_now_method=data.received_now_method,
            received_now_reference=data.received_now_reference,
            rate_includes_tax=rate_includes_tax,
            # A record of how this bill was raised, not a permission: true
            # when the bill raised the note that ships its goods. What the
            # bill may do with a note is decided by the note's own stamp.
            allow_direct_sales_order=bool(own_notes),
            status=SalesInvoiceStatus.DRAFT.value,
            additional_charges=self._q(data.additional_charges),
            round_off=self._q(data.round_off),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        for note in chain.raised_notes:
            note.raised_by_sales_invoice_id = row.id
        for order in chain.raised_orders:
            order.raised_by_sales_invoice_id = row.id
        if data.received_now_tenders:
            self._replace_tenders(row, data, actor_id=actor_id)
        self._replace_sources(row, source_rows, firm_id=firm_id, actor_id=actor_id)
        line_totals = self._replace_lines(
            row,
            line_specs,
            bill_percent=data.bill_discount_percent,
            bill_amount=data.bill_discount_amount,
            freight_amount=data.freight_amount,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=business_profile_id,
            actor_id=actor_id,
            entered_rates=entered_rates,
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
        # Charges taxed at a rate of their own (SG-4): beside the lines, in
        # the tax and in what the customer owes.
        charges_total, charges_tax = self._replace_charges(
            row,
            data.charges or [],
            business_profile_id=business_profile_id,
            actor_id=actor_id,
        )
        row.tax_total = self._q(line_totals["tax_total"] + charges_tax)
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + charges_total
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
        # Absent leaves the bill's switch as it is (backlog 64 row 4).
        if data.rate_includes_tax is not None:
            row.rate_includes_tax = data.rate_includes_tax
        # What the request itself said, before anything below restates it:
        # absent means leave alone, and only this tells absent from null.
        sent = frozenset(data.model_fields_set)
        counter = self._own_counter_chain(row)
        data = self._keeping_what_the_bill_holds(
            row, data, sent=sent, own_orders=None if counter is None else counter[1]
        )
        # A draft counter bill whose edit changes what it ships has its
        # hidden order and note raised again, so all four always agree
        # (D-SELL-72, D-SELL-59).
        raised_again = (
            None
            if counter is None
            else self._raise_counter_chain_again(
                row,
                data,
                notes=counter[0],
                orders=counter[1],
                sent=sent,
                firm_id=firm_id,
                actor_id=actor_id,
            )
        )
        entered_rates: dict[UUID, tuple[Decimal, Decimal]]
        if raised_again is not None:
            data, own_notes, entered_rates = raised_again
        else:
            if counter is not None:
                # A counter bill that ships and charges what its order and
                # note already do, coupon included: the order holds the
                # coupon, and the bill that continues it carries none.
                data = data.model_copy(update={"coupon_code": None})
            if any(line.product_id is not None for line in data.lines):
                # Said by name, where it used to surface three layers down as
                # "Unsupported source document type." (D-SELL-69). Only a
                # counter bill -- one that raised its own order and note --
                # takes product lines on an edit.
                raise ValidationError(
                    f"{row.invoice_number} bills documents already raised, so "
                    "it is changed through the lines it has: send each line "
                    "back with its source_document_type, source_document_id "
                    "and source_document_line_id, as the bill returns them, "
                    "and no product_id."
                )
            # An edit bills the documents the first save raised, at their
            # prices.
            refuse_coupon_on_documents(data)
            own_notes = self._notes_raised_by(row)
            data = self._restate_own_serials(
                data, row=row, own_notes=own_notes, firm_id=firm_id, actor_id=actor_id
            )
            data = self._restate_own_batches(
                data, own_notes=own_notes, actor_id=actor_id
            )
            # A rate typed with GST in it is kept for each line still billed
            # at the rate it derived to (backlog 64 row 4).
            entered_rates = (
                {
                    line.source_document_line_id: (line.entered_rate, line.unit_price)
                    for line in self._session.scalars(
                        select(SalesInvoiceLine).where(
                            SalesInvoiceLine.sales_invoice_id == row.id,
                            SalesInvoiceLine.entered_rate.is_not(None),
                        )
                    ).all()
                    if line.entered_rate is not None
                }
                if row.rate_includes_tax
                else {}
            )
        self._delete_children(
            row.id, attachments="attachments" in sent, notes="notes" in sent
        )
        header, source_rows, line_specs = self._prepare_invoice_sources(
            data, firm_id, own_notes=own_notes
        )
        customer_before = row.customer_id
        row.customer_id = data.customer_id or header["customer_id"]
        row.branch_id = data.branch_id or header["branch_id"]
        # Absent keeps the bill's own ship-to while it still names the
        # buyer's address; otherwise it is inherited again from what it bills.
        if (
            "shipping_address_id" in sent
            or row.customer_id != customer_before
            or not ship_to_is_valid(
                self._session,
                customer_id=row.customer_id,
                address_id=row.shipping_address_id,
            )
        ):
            row.shipping_address_id = self._ship_to(
                data.shipping_address_id,
                customer_id=row.customer_id,
                source_rows=source_rows,
            )
        row.business_profile_id = data.business_profile_id
        salesman_id, territory_id, route_id = self._fill_missing_scope(
            firm_id=firm_id,
            customer_id=row.customer_id,
            salesman_id=data.salesman_id or header.get("salesman_id"),
            territory_id=data.territory_id or header.get("territory_id"),
            route_id=data.route_id or header.get("route_id"),
            on_date=data.invoice_date,
        )
        self._assert_named_route_fits(
            data.route_id,
            firm_id=firm_id,
            customer_id=row.customer_id,
            territory_id=territory_id,
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
        # What the bill leaves blank it inherits from the orders it continues
        # (backlog 67 row 4), exactly as a new bill does.
        terms, terms_days = self._order_terms(source_rows)
        row.payment_terms = data.payment_terms or terms
        row.due_date = data.due_date or self._due_date(
            self._session.get(Customer, row.customer_id),
            data.invoice_date,
            days=terms_days,
        )
        # A draft is re-priced on every save, against the buyer as they stand
        # now, so what it prints must follow the same answer (D-CMP-15).
        buyer = self._session.get(Customer, row.customer_id)
        row.place_of_supply = self._place_of_supply(
            buyer, shipping_address_id=row.shipping_address_id
        )
        # Absent leaves a walk-in bill's buyer alone; a bill moved to a
        # customer with a record drops it.
        if {"buyer_name", "buyer_phone"} & data.model_fields_set or not (
            buyer is not None and buyer.is_cash_sale
        ):
            row.buyer_name, row.buyer_phone = _walk_in_buyer(buyer, data)
        row.buyer_gst_registration_type = _buyer_gst_type(buyer)
        row.reference_number = data.reference_number
        row.remarks = data.remarks
        # Absent means leave alone: an editor that never showed the counter
        # payment must not clear it.
        if "received_now_amount" in data.model_fields_set:
            row.received_now_amount = self._q(data.received_now_amount)
        if "received_now_method" in data.model_fields_set:
            row.received_now_method = data.received_now_method
        if "received_now_reference" in data.model_fields_set:
            row.received_now_reference = data.received_now_reference
        if data.received_now_tenders is not None:
            self._replace_tenders(row, data, actor_id=actor_id)
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
            freight_amount=data.freight_amount,
            firm_id=firm_id,
            invoice_date=data.invoice_date,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
            entered_rates=entered_rates,
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
        # Absent leaves the bill's charges alone -- re-taxed all the same,
        # against the buyer and the date as they now stand, exactly as the
        # lines are; sent, they are replaced, and an empty list clears them.
        charges_total, charges_tax = self._replace_charges(
            row,
            (data.charges or []) if "charges" in data.model_fields_set else None,
            business_profile_id=data.business_profile_id,
            actor_id=actor_id,
        )
        row.tax_total = self._q(line_totals["tax_total"] + charges_tax)
        row.grand_total = self._q(
            row.subtotal
            + row.tax_total
            + line_totals["line_charges_total"]
            + charges_total
            + row.additional_charges
            + row.round_off
        )
        # Absent leaves the bill's attachments and notes alone; sent, each is
        # replaced whole, and an empty list clears it (D-SELL-79).
        if "attachments" in sent:
            self._replace_attachments(
                row, data.attachments, actor_id=actor_id, firm_id=firm_id
            )
        if "notes" in sent:
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
        if "attributes" in data.model_fields_set:
            document_attributes.store(
                self._session,
                AttributeEntityType.SALES_INVOICE,
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
        licence_override_reason: str | None = None,
        price_override_reason: str | None = None,
    ) -> SalesInvoice:
        """Approve one sales invoice and commit it."""
        row = self.stage_approval(
            invoice_id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            licence_override_reason=licence_override_reason,
            price_override_reason=price_override_reason,
        )
        self._session.commit()
        return row

    def hold_invoice(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        note: str | None = None,
    ) -> SalesInvoice:
        """Park a draft bill while the next customer is served (SG-7).

        **A flag, not a status**: the bill stays the draft it was, so nothing
        about how far it had got is lost and recalling it puts nothing back.
        It can still be edited while held; what it cannot be is approved.
        Holding a bill already held replaces the note and keeps when it was
        first parked.

        Raises:
            ValidationError: If the bill is not a draft.

        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError(
                f"Only a draft bill can be held; {row.invoice_number} is "
                f"{row.status.lower()}."
            )
        text = (note or "").strip() or None
        if not row.is_held:
            row.is_held = True
            row.held_at = utc_now()
        row.held_note = text
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="HELD",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
            remarks=text,
        )
        record_audit(
            self._session,
            action="sales_invoice.held",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"note": text},
        )
        self._session.commit()
        return row

    def recall_invoice(
        self, invoice_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> SalesInvoice:
        """Take a held bill back to the counter (SG-7).

        Raises:
            ValidationError: If the bill is not held.

        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if not row.is_held:
            raise ValidationError(f"{row.invoice_number} is not held.")
        note = row.held_note
        row.is_held = False
        row.held_at = None
        row.held_note = None
        row.updated_by = actor_id
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="RECALLED",
            from_state=row.status,
            to_state=row.status,
            actor_id=actor_id,
        )
        record_audit(
            self._session,
            action="sales_invoice.recalled",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"note": note},
        )
        self._session.commit()
        return row

    def dispatch_and_invoice(
        self,
        note_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        batch_reason: str | None = None,
    ) -> SalesInvoice:
        """Dispatch an approved delivery note and bill it, in one transaction.

        Backlog 77 row 2, decision A35. A tax invoice for goods is issued at
        or before their removal (CGST s.31), so a sale's note dispatched by
        hand is warned about or refused; this is the compliant path in one
        action. The note is dispatched, a bill of all of it is raised -- each
        line inheriting the note's price, discount and free goods -- and
        approved, and nothing lands unless all three do. Dated the day it
        happens, which is the day the goods leave.

        Raises:
            ValidationError: If the note is not approved, or the bill's own
                approval refuses (a licence, a price below its floor): then
                nothing is dispatched either.

        """
        notes = DeliveryNoteService(self._session)
        note = notes.get_note(note_id, firm_scope=firm_scope)
        if note.status != DeliveryNoteStatus.APPROVED.value:
            raise ValidationError(
                f"{note.delivery_note_number} is {note.status.lower()}: only an "
                "approved delivery note can be dispatched and invoiced."
            )
        # A person dispatching, so the firm's batch rules judge it (79 row 6).
        notes.stage_dispatch(
            note.id,
            firm_scope=firm_scope,
            actor_id=actor_id,
            batch_reason=batch_reason,
            judge_batches=True,
        )
        self._session.flush()
        lines = self._session.scalars(
            select(DeliveryNoteLine)
            .where(
                DeliveryNoteLine.delivery_note_id == note.id,
                DeliveryNoteLine.is_deleted.is_(False),
            )
            .order_by(DeliveryNoteLine.line_number.asc())
        ).all()
        bill = self.stage_invoice(
            SalesInvoiceCreate(
                customer_id=note.customer_id,
                branch_id=note.branch_id,
                invoice_date=firm_today(self._session, firm_scope),
                source_documents=[
                    SalesInvoiceSourceWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                    )
                ],
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=line.id,
                        line_number=number,
                        current_invoice_quantity=self._q(
                            line.current_delivery_quantity
                        ),
                    )
                    for number, line in enumerate(lines, start=1)
                ],
            ),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        row = self.stage_approval(bill.id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.commit()
        return row

    def _stage_received_now(
        self, row: SalesInvoice, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Record the money taken at the counter as a receipt (backlog 64 row 5).

        Through the receipt service, so it posts the same journal, moves the
        customer's balance by the same rule and is reversed the same way as
        any receipt; staged, so the bill and its payment land together or
        not at all. More than the bill comes to is refused rather than turned
        into an advance -- change is handed back, not kept on account.
        """
        amount = quantize_ledger(row.received_now_amount)
        if amount <= Decimal("0") or row.received_now_settlement_id is not None:
            return
        tenders = self._tenders_of(row.id)
        # Against what the customer is asked to pay -- the receivable the
        # journal debits, at the ledger's two decimals -- never the document's
        # four. A bill of 97.1376 posts 97.14, and comparing the money with
        # the unrounded figure refused the one amount that settles it while
        # the walk-in rule refused every other (D-SELL-83).
        payable = _receivable_amount(row.grand_total)
        if amount > payable:
            raise ValidationError(
                f"{amount} was received against a bill of {payable}. "
                "Enter what the bill is paid with; change is handed back."
            )
        from app.settlements.schemas import (
            SettlementAllocationWrite,
            SettlementCreate,
            SettlementMethodEnum,
            SettlementModeEnum,
        )
        from app.settlements.services import ReceiptService

        if tenders:
            # One receipt per tender (SEL-12): cash to the cash book, UPI and
            # card to the bank, each allocated to this bill.
            for tender in tenders:
                cash = tender.mode == "CASH"
                receipt = ReceiptService(self._session).create(
                    SettlementCreate(
                        party_id=row.customer_id,
                        settlement_date=row.invoice_date,
                        amount=Decimal(str(tender.amount)),
                        method=(
                            SettlementMethodEnum.CASH
                            if cash
                            else SettlementMethodEnum.BANK
                        ),
                        payment_mode=SettlementModeEnum(tender.mode),
                        instrument_reference=tender.reference,
                        narration=f"Received with {row.invoice_number}",
                        allocations=[
                            SettlementAllocationWrite(
                                invoice_id=row.id, amount=Decimal(str(tender.amount))
                            )
                        ],
                    ),
                    firm_id=firm_scope,
                    actor_id=actor_id,
                )
                tender.settlement_id = receipt.id
                if row.received_now_settlement_id is None:
                    row.received_now_settlement_id = receipt.id
            return
        receipt = ReceiptService(self._session).create(
            SettlementCreate(
                party_id=row.customer_id,
                settlement_date=row.invoice_date,
                amount=amount,
                method=SettlementMethodEnum(row.received_now_method or "CASH"),
                instrument_reference=row.received_now_reference,
                narration=f"Received with {row.invoice_number}",
                allocations=[
                    SettlementAllocationWrite(invoice_id=row.id, amount=amount)
                ],
            ),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        row.received_now_settlement_id = receipt.id

    def _replace_tenders(
        self,
        row: SalesInvoice,
        data: SalesInvoiceCreate,
        *,
        actor_id: UUID,
    ) -> None:
        """Replace a draft bill's tenders; their sum is what was received.

        Raises:
            ValidationError: Once the bill's counter payment is recorded.

        """
        if row.received_now_settlement_id is not None:
            raise ValidationError(
                "The counter payment of this bill is already recorded."
            )
        tenders = data.received_now_tenders or []
        for existing in self._tenders_of(row.id):
            self._session.delete(existing)
        self._session.flush()
        for sequence, tender in enumerate(tenders, start=1):
            self._session.add(
                SalesInvoiceTender(
                    firm_id=row.firm_id,
                    sales_invoice_id=row.id,
                    sequence=sequence,
                    mode=tender.mode,
                    amount=tender.amount,
                    reference=(tender.reference or "").strip() or None,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        if tenders:
            row.received_now_amount = self._q(
                sum((tender.amount for tender in tenders), Decimal("0"))
            )
            row.received_now_method = None
            row.received_now_reference = None
        self._session.flush()

    def _tenders_of(self, invoice_id: UUID) -> list[SalesInvoiceTender]:
        """Return a bill's tenders in the order they were given."""
        return list(
            self._session.scalars(
                select(SalesInvoiceTender)
                .where(
                    SalesInvoiceTender.sales_invoice_id == invoice_id,
                    SalesInvoiceTender.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceTender.sequence.asc())
            ).all()
        )

    def _replace_charges(
        self,
        row: SalesInvoice,
        charges: Sequence[SalesInvoiceChargeWrite] | None,
        *,
        business_profile_id: UUID | None,
        actor_id: UUID,
    ) -> tuple[Decimal, Decimal]:
        """Write a draft bill's separately taxed charges, taxed afresh (SG-4).

        Each charge is taxed as a line is -- through the rule engine, as the
        same kind of supply to the same buyer on the bill's own date -- by the
        profile it names, and one that names none carries no tax. The tax is
        kept by GST head as charged, which is what the posting, the print and
        the returns then read.

        Args:
            row: The draft bill, with its buyer, branch, date and ship-to set.
            charges: The charges to hold; None keeps the ones the bill has,
                taxed again like everything else on a draft that is saved.
            business_profile_id: The profile the bill is taxed under.
            actor_id: Who is saving the bill.

        Returns:
            What the charges come to before tax, and their tax.

        """
        held = self._charges_of(row.id)
        if charges is None:
            charges = [
                SalesInvoiceChargeWrite(
                    name=item.name,
                    amount=item.amount,
                    tax_profile_id=item.tax_profile_id,
                    hsn_sac=item.hsn_sac,
                )
                for item in held
            ]
        for existing in held:
            self._session.delete(existing)
        if held:
            self._session.flush()
        total = tax_total = ZERO
        for sequence, charge in enumerate(charges, start=1):
            amount = self._q(charge.amount)
            taxed = self._resolve_tax(
                document_id=row.id,
                shipping_address_id=row.shipping_address_id,
                invoice_date=row.invoice_date,
                firm_id=row.firm_id,
                business_profile_id=business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=None,
                product_id=None,
                tax_profile_id=charge.tax_profile_id,
                invoice_value=amount,
                actor_id=actor_id,
            )
            # Only what the customer is billed: tax already inside a price is
            # not added to the bill, so it is not a head of this charge.
            heads = split_components(
                [
                    TaxComponent(
                        code=component.code,
                        percentage=component.percentage,
                        amount=component.amount,
                    )
                    for component in taxed.components
                    if taxed.total != ZERO and not component.included_in_price
                ]
            )
            self._session.add(
                SalesInvoiceCharge(
                    firm_id=row.firm_id,
                    sales_invoice_id=row.id,
                    sequence=sequence,
                    name=charge.name.strip(),
                    hsn_sac=(charge.hsn_sac or "").strip() or None,
                    amount=amount,
                    tax_profile_id=charge.tax_profile_id,
                    tax_rate_percent=self._q(heads.rate),
                    tax_amount=taxed.total,
                    igst_amount=self._q(heads.igst),
                    cgst_amount=self._q(heads.cgst),
                    sgst_amount=self._q(heads.sgst),
                    cess_amount=self._q(heads.cess),
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            total += amount
            tax_total += taxed.total
        if charges:
            self._session.flush()
        return self._q(total), self._q(tax_total)

    def _charges_of(self, invoice_id: UUID) -> list[SalesInvoiceCharge]:
        """Return a bill's separately taxed charges in the order they were given."""
        return list(
            self._session.scalars(
                select(SalesInvoiceCharge)
                .where(
                    SalesInvoiceCharge.sales_invoice_id == invoice_id,
                    SalesInvoiceCharge.is_deleted.is_(False),
                )
                .order_by(SalesInvoiceCharge.sequence.asc())
            ).all()
        )

    def stage_approval(
        self,
        invoice_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        licence_override_reason: str | None = None,
        price_override_reason: str | None = None,
    ) -> SalesInvoice:
        """Approve one sales invoice without committing it.

        Posts the receivable and the revenue journal. `post_receivable_transaction`
        has always taken `commit=False` here for the same reason the rest of
        this split exists: the money and the document have to land together.
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status != SalesInvoiceStatus.DRAFT.value:
            raise ValidationError("Only draft sales invoices can be approved.")
        if row.is_held:
            # A held bill never posts (SG-7): it was parked on purpose, and
            # approving it from a list would bill a customer who has not
            # come back. Here rather than in the route, so bulk approve and
            # anything composing approval refuse it too.
            raise ValidationError(
                f"{row.invoice_number} is held. Recall it first, then approve it."
            )
        # Levels of sign-off the firm's rules call for (PLT-1).
        from app.approvals.services import ApprovalChainService

        ApprovalChainService(self._session).assert_cleared(
            firm_scope, "SALES_INVOICE", row.id, row.grand_total, actor_id
        )
        # Checked again here, not only when the draft is saved: a draft saved
        # before the save refused an undispatched note would otherwise still
        # post revenue for goods that never left (D-SELL-3). A bill that
        # raised its own note is the exception: its approval is the dispatch.
        # "Its own" is the note's stamp, not the firm's stage today -- a note
        # a person raised before the stage was switched off is theirs to
        # dispatch (D-CFG-16).
        to_ship: list[DeliveryNote] = []
        for note in self._billed_notes(row):
            if (
                note.raised_by_sales_invoice_id == row.id
                and note.status == DeliveryNoteStatus.APPROVED.value
            ):
                to_ship.append(note)
            else:
                require_dispatched_note(note, "billed")
        self._refuse_billing_returned_goods(row)
        # Approval is what puts the amount on the customer's account, so it is
        # the last point at which a limit can still be enforced.
        #
        # The customer is locked while the limit is judged and the balance
        # raised. Two approvals for one customer that both read the balance
        # before either posted would each see headroom the other was about to
        # use; the version check refused the second only as a generic conflict,
        # never with the credit decision. Locked, the second waits, reads the
        # balance the first left (`populate_existing`, not the copy this session
        # may already hold) and is judged on it (2026-09-15). Per customer, so
        # approvals for different customers do not queue.
        customer = self._session.scalar(
            select(Customer)
            .where(Customer.id == row.customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        walk_in = customer is not None and customer.is_cash_sale
        # Money is two decimals, like the receivable it is set against: both
        # sides of every comparison below are at the ledger's scale (D-SELL-83).
        received_now = quantize_ledger(row.received_now_amount)
        if walk_in and received_now > _receivable_amount(row.grand_total):
            # More than the bill comes to is change to hand back, as it is on
            # any counter bill; this said "Take the rest" (D-SELL-66).
            raise ValidationError(
                f"{received_now} was received against a bill of "
                f"{_receivable_amount(row.grand_total)}. "
                "Enter what the bill is paid with; change is handed back."
            )
        if walk_in and received_now != _receivable_amount(row.grand_total):
            # The cash customer is nobody in particular, so nothing can be
            # left owing on its account (backlog 87 #2).
            raise ValidationError(
                f"A walk-in bill is paid in full at the counter: "
                f"{row.invoice_number} comes to "
                f"{_receivable_amount(row.grand_total)} and "
                f"{received_now} was received. Take the rest, or "
                "bill a customer with a record to sell on credit."
            )
        if customer is not None:
            assert_customer_may_be_billed(customer)
            CreditControlService(self._session).assert_within_limit(
                customer, additional_amount=self._q(row.grand_total)
            )
        # Judged on the bill's date, before any stock leaves (backlog 54).
        licence_remark, licence_details = LicenceCheckService(
            self._session
        ).approve_sale(
            LicenceDocument.SALES_INVOICE,
            row.id,
            firm_id=firm_scope,
            override_reason=licence_override_reason,
        )
        # The bill is the sale, whatever the order said: it may have no order,
        # or re-price the one it bills (backlog 64 row 2). Before any stock
        # leaves, so a refusal leaves nothing moved.
        price_remark, price_details = PriceFloorService(self._session).enforce(
            firm_scope,
            invoice_lines(
                self._session.scalars(
                    select(SalesInvoiceLine).where(
                        SalesInvoiceLine.sales_invoice_id == row.id,
                        SalesInvoiceLine.is_deleted.is_(False),
                    )
                ).all()
            ),
            override_reason=price_override_reason,
            as_of=row.invoice_date,
        )
        # What the bill itself typed, against the approver's limit (backlog 64
        # row 3); what it inherited was judged when its order was approved.
        discount_details = DiscountLimitService(self._session).enforce(
            firm_scope,
            actor_id,
            lambda: invoice_discounts(self._judged_discount_lines(row)),
        )
        # A supply to an SEZ under an LUT carries no tax; one that charges some
        # is warned about rather than refused, because whether the LUT covers
        # this supply is the firm's to know (backlog 75 row 2).
        sez_remark, sez_details = sez_tax_warning(customer, row.tax_total)
        approval_remark = (
            " ".join(
                part for part in (licence_remark, price_remark, sez_remark) if part
            )
            or None
        )
        approval_details = (
            (licence_details or {})
            | (price_details or {})
            | (discount_details or {})
            | (sez_details or {})
        ) or None
        # Before any stock leaves, as an order claims before it reserves: an
        # offer that has run out refuses the approval by name.
        self._claim_own_offers(row, firm_scope=firm_scope, actor_id=actor_id)
        # The goods leave now, not when the draft was saved: a draft is a
        # proposal, and it used to ship the stock and post cost of goods sold
        # the moment it was typed (D-SELL-13, driven 2026-09-19).
        self._ship_on_approval(row, to_ship, firm_scope=firm_scope, actor_id=actor_id)
        # Once every line knows its batches: none may charge above the MRP
        # printed on them (backlog 79 row 7).
        self._refuse_above_batch_mrp(row)
        before = row.status
        row.status = SalesInvoiceStatus.APPROVED.value
        row.approved_at = utc_now()
        row.updated_by = actor_id
        # A bill that comes to nothing -- every line at a 100% discount, or
        # goods given free -- owes nothing, so it puts no row on the
        # customer's account; one for 0.00 was refused by the receivable's own
        # schema and the approval answered 500, with the goods already gone
        # and the note never billable (D-SELL-53). The stock and its cost
        # still moved with the dispatch above.
        if _receivable_amount(row.grand_total) > ZERO:
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
            # Owed per GST head (backlog 63.3), off the components the lines
            # recorded -- the figures GSTR-1 and 3B read.
            tax_by_component=invoice_tax_by_component(self._session, row.id),
            # The charges taxed at a rate of their own are income of their
            # own (SG-4): credited apart from the sales the goods made.
            other_charges_amount=sum(
                (Decimal(str(charge.amount)) for charge in self._charges_of(row.id)),
                ZERO,
            ),
        )
        # Credit the customer for the sale, in the approval's own transaction:
        # it posts, because a scheme costs the firm money the moment it
        # promises the points rather than whenever they are spent. It used to
        # be staged after `approve_invoice` had committed, and nothing
        # committed again, so no bill approved through the API or the desktop
        # ever earned (D-SELL-1, 2026-09-19).
        #
        # A walk-in bill earns nothing: the points would pool on an account
        # that belongs to nobody (backlog 87 #2).
        if not walk_in:
            LoyaltyService(self._session).stage_earning(
                row, firm_id=firm_scope, actor_id=actor_id
            )
        self._record_event(
            firm_id=firm_scope,
            document_type=self._document_type(firm_scope),
            invoice=row,
            action="APPROVED",
            from_state=before,
            to_state=row.status,
            actor_id=actor_id,
            remarks=approval_remark,
            details=approval_details,
        )
        record_audit(
            self._session,
            action="sales_invoice.approved",
            entity_type="sales_invoice",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data=approval_details,
        )
        # Messaging (backlog 51): staged in this transaction, so a rolled-back
        # approval leaves no message; a firm with messaging off gets nothing.
        stage_document_event(
            self._session,
            "SALES_INVOICE_APPROVED",
            MessagingDocument(
                document_type="SALES_INVOICE",
                document_id=row.id,
                document_number=row.invoice_number,
                document_date=row.invoice_date,
                customer_id=row.customer_id,
                amount=row.grand_total,
                due_date=row.due_date,
            ),
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        # Inside the staged approval, not after it: anything composing
        # approval then settles the counter payment too, which is the trap
        # loyalty earning fell into (D-SELL-1).
        self._stage_received_now(row, firm_scope=firm_scope, actor_id=actor_id)
        self._stamp_counter_shift(row, firm_scope=firm_scope, actor_id=actor_id)
        return row

    def _claim_own_offers(
        self, row: SalesInvoice, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Claim the offers a counter bill's own order was priced with.

        A counter bill raises a sales order nobody typed, and that order is
        approved at every **save** of the draft. Claiming there meant a
        draft, a held bill and every edit held a live claim, so unapproved
        bills could use up an offer limited to a few (D-SELL-85). The order's
        claims now stay PENDING until the bill is approved, and are made
        here by the function an order's approval calls: under the lock on
        the offer's version group, with the loser refused by the offer's
        name. An order a person typed claimed at its own approval and has
        nothing pending, so only orders carrying this bill's stamp are asked.
        """
        for order_id in self._session.scalars(
            select(SalesOrder.id)
            .where(
                SalesOrder.raised_by_sales_invoice_id == row.id,
                SalesOrder.is_deleted.is_(False),
            )
            .order_by(SalesOrder.id)
        ).all():
            RedemptionService(self._session).claim(
                firm_id=firm_scope, document_id=order_id, actor_id=actor_id
            )

    def _stamp_counter_shift(
        self, row: SalesInvoice, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Put a bill paid at the counter in the shift of the till that took it.

        The till is its **maker's**: counter staff raise bills and hold no
        approve code, so a manager approves them, and stamping the approver's
        shift left the cashier's drawer at its float (D-SELL-51). The
        approver's own shift takes the bill only when its maker has none open.

        Only a bill that took money at the counter, and only when one of the
        two has a shift open. **Somebody with none is not refused**: shifts
        are optional, and a firm that counts no drawer bills exactly as it
        did. The shift row is locked, so a bill either lands before the
        drawer is counted or finds the shift closed and is left out.
        """
        if Decimal(str(row.received_now_amount or 0)) <= Decimal("0"):
            return
        # Imported here: the shift service reads the invoice model.
        from app.counter_shifts.services import open_shift_of

        for cashier_id in dict.fromkeys((row.created_by, actor_id)):
            if cashier_id is None:
                continue
            shift = open_shift_of(self._session, firm_scope, cashier_id, lock=True)
            if shift is not None:
                row.counter_shift_id = shift.id
                return

    def _restate_own_serials(
        self,
        data: SalesInvoiceCreate,
        *,
        row: SalesInvoice,
        own_notes: frozenset[UUID],
        firm_id: UUID,
        actor_id: UUID,
    ) -> SalesInvoiceCreate:
        """Hand the units an edited draft names to the note it raised.

        On create the chain moves a line's ``serial_ids`` onto the note it
        raises; on an edit that note already exists, so the picks are
        restated on it here and taken off the payload (D-SELL-33). Any other
        line naming serials is still refused where the sources are read.
        """
        picks: dict[UUID, dict[UUID, list[UUID]]] = defaultdict(dict)
        kept: list[SalesInvoiceLineWrite] = []
        for line in data.lines:
            if (
                line.serial_ids is not None
                and line.source_document_type == SalesInvoiceSourceType.DELIVERY_NOTE
                and line.source_document_id in own_notes
                and line.source_document_line_id is not None
            ):
                picks[line.source_document_id][
                    line.source_document_line_id
                ] = line.serial_ids
                kept.append(line.model_copy(update={"serial_ids": None}))
            else:
                kept.append(line)
        if not picks:
            return data
        notes = DeliveryNoteService(self._session)
        for note_id, by_line in picks.items():
            notes.restate_serial_picks(
                note_id,
                by_line,
                firm_scope=firm_id,
                raised_by_sales_invoice_id=row.id,
                actor_id=actor_id,
            )
        return data.model_copy(update={"lines": kept})

    def _restate_own_batches(
        self,
        data: SalesInvoiceCreate,
        *,
        own_notes: frozenset[UUID],
        actor_id: UUID,
    ) -> SalesInvoiceCreate:
        """Hand the batches an edited draft names to the note it raised (79).

        As with serials: on create the chain carries a line's ``batches`` onto
        the note it raises; on an edit that note exists, so they are restated
        on its line here and taken off the payload. A line billing anybody
        else's note keeps them, and is refused where the sources are read.
        """
        notes = DeliveryNoteService(self._session)
        kept: list[SalesInvoiceLineWrite] = []
        changed = False
        for line in data.lines:
            if (
                line.batches is not None
                and line.source_document_type == SalesInvoiceSourceType.DELIVERY_NOTE
                and line.source_document_id in own_notes
                and line.source_document_line_id is not None
            ):
                note_line = self._session.get(
                    DeliveryNoteLine, line.source_document_line_id
                )
                if note_line is None or note_line.delivery_note_id not in own_notes:
                    raise ValidationError(
                        f"Line {line.line_number}: that delivery line is not "
                        "this bill's own."
                    )
                notes.set_line_batches(
                    note_line,
                    line.batches,
                    label=f"Line {line.line_number}",
                    actor_id=actor_id,
                )
                kept.append(line.model_copy(update={"batches": None}))
                changed = True
            else:
                kept.append(line)
        return data.model_copy(update={"lines": kept}) if changed else data

    def _billed_hsn(self, product_id: UUID | None) -> str | None:
        """Return the HSN or SAC code the product carries now, for the line.

        Read once, as the line is written, and kept on it (D-CMP-22).
        """
        if product_id is None:
            return None
        product = self._session.get(Product, product_id)
        code = (product.hsn_sac or "").strip() if product is not None else ""
        return code or None

    def _refuse_above_batch_mrp(self, row: SalesInvoice) -> None:
        """Refuse a line that charges more than the MRP of its batch (79 row 7).

        The MRP is printed per batch and includes tax, so a line is judged on
        what each charged stock unit costs the customer -- after its discounts,
        with its tax, freight left out -- against the lowest MRP among the
        batches it ships, the product's standing in for a batch with none.
        Only lines whose batches are known; the Legal Metrology rule is that
        nobody pays more than the pack says.

        Raises:
            ValidationError: Naming the line, the rate and the MRP.

        """
        lines = [
            line
            for line in self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.sales_invoice_id == row.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoiceLine.source_document_type
                    == SalesInvoiceSourceType.DELIVERY_NOTE.value,
                )
            ).all()
        ]
        picks = DeliveryNoteService(self._session).batch_picks(
            [line.source_document_line_id for line in lines]
        )
        # A bill line is counted and priced in its note line's unit, whatever
        # unit it was typed in, so the stock units one of it holds are the
        # note line's. The bill's own `conversion_factor` is the typed unit
        # against the note's -- a twelfth for pieces billed against a box --
        # and multiplying by it compared a box's price with a piece's MRP, or
        # divided it by twelve again: the goods had shipped and no bill of
        # them could be approved (D-PRC-36).
        stock_units = self._stock_units_per_note_unit(
            [line.source_document_line_id for line in lines]
        )
        for line in sorted(lines, key=lambda item: item.line_number):
            # The same judge the order and the note ask (D-PRC-7), so the
            # three cannot word it or work it out differently.
            refuse_above_batch_mrp(
                self._session,
                line_number=line.line_number,
                product_id=line.product_id,
                batch_ids=[
                    pick.batch_id
                    for pick in picks.get(line.source_document_line_id, [])
                ],
                paid=Decimal(str(line.net_amount))
                - Decimal(str(line.freight_amount or 0)),
                # Seven pieces, not the 0.5833 of a box the cap counts:
                # 6.9996 pieces would put the rate a paisa out (D-PRC-37).
                quantity=exact_quantity(
                    line.current_invoice_quantity,
                    line.entered_quantity,
                    line.conversion_factor,
                ),
                stock_units_per_unit=stock_units.get(line.source_document_line_id),
            )

    def _stock_units_per_note_unit(
        self, note_line_ids: Sequence[UUID]
    ) -> dict[UUID, Decimal]:
        """Return, per delivery note line, the stock units one of its unit holds.

        The factor the note line converted at when it shipped -- 12 for a
        line delivered by the box of twelve, one for a line in the stock
        unit -- read in one statement for the bill.
        """
        if not note_line_ids:
            return {}
        return {
            line_id: Decimal(str(factor or 1))
            for line_id, factor in self._session.execute(
                select(DeliveryNoteLine.id, DeliveryNoteLine.conversion_factor).where(
                    DeliveryNoteLine.id.in_(note_line_ids)
                )
            )
            .tuples()
            .all()
        }

    # ---- a draft counter bill is raised again when its edit changes it -----

    def _own_counter_chain(
        self, row: SalesInvoice
    ) -> tuple[list[DeliveryNote], list[SalesOrder]] | None:
        """Return the live note and order a counter bill raised for itself.

        None where the bill is not a counter bill: it raised no note, or the
        order behind its note is one a person raised.
        """
        notes = list(
            self._session.scalars(
                select(DeliveryNote).where(
                    DeliveryNote.raised_by_sales_invoice_id == row.id,
                    DeliveryNote.status == DeliveryNoteStatus.APPROVED.value,
                    DeliveryNote.is_deleted.is_(False),
                )
            ).all()
        )
        orders = list(
            self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.raised_by_sales_invoice_id == row.id,
                    SalesOrder.status.not_in(("CANCELLED", "CLOSED")),
                    SalesOrder.is_deleted.is_(False),
                )
            ).all()
        )
        return (notes, orders) if notes and orders else None

    def _keeping_what_the_bill_holds(
        self,
        row: SalesInvoice,
        data: SalesInvoiceCreate,
        *,
        sent: frozenset[str],
        own_orders: list[SalesOrder] | None,
    ) -> SalesInvoiceCreate:
        """Fill what an edit left out of the header from the bill itself.

        Absent means leave alone, and an explicit null or zero clears
        (D-SELL-79). The update used to read every header field straight off
        the request, so an edit that named only its lines cleared the
        reference and the remarks and dropped the bill discount -- and on a
        counter bill whose order was raised again, the freight too, since
        the new order was raised from the request and had none to inherit.

        A bill discount left out is carried **as it was typed**
        (``bill_discount_typed_as``, D-PRC-35). A typed amount is carried as
        the amount: 25.00 off is 25.00 off whatever the lines now come to,
        and only the rate shown beside it moves. Carried as its four-place
        rate it came back as 25.0001. A typed rate is carried as the rate,
        which is what still means the same on other quantities -- and so is
        a discount on a bill saved before the bill recorded which was typed.
        Freight is carried only
        for a bill that ships its own goods; any other bill inherits it from
        the notes it bills, pro-rated by the share billed (D-SELL-36), and
        that share is what an edit changes. There a null still means "as the
        notes say"; on a counter bill it means none.

        Only a bill discount **somebody typed** is carried. One the bill
        inherited from the documents it continues is inherited again, at
        whatever share the edit now bills; one an offer gave a counter
        bill's order is the offer's to give again when that order is priced.
        Carrying either as a typed rate would turn an arrangement into a
        decision, and judge it against the approver's discount limit
        (D-PRC-1). ``own_orders`` names the orders a counter bill raised for
        itself, None for any other bill.
        """
        ships_its_own = own_orders is not None
        if own_orders is not None:
            # Typed on the bill and so on its order -- or typed on an edit
            # that raised nothing again, which only the bill records.
            typed = row.bill_discount_source == "typed" or any(
                order.bill_discount_source not in OFFERED for order in own_orders
            )
        else:
            typed = row.bill_discount_source != "inherited"
        kept: dict[str, object] = {
            name: getattr(row, name)
            for name in (
                "business_profile_id",
                "customer_invoice_number",
                "currency_code",
                "exchange_rate",
                "payment_terms",
                "reference_number",
                "remarks",
                "additional_charges",
                "round_off",
            )
            if name not in sent
        }
        if (
            not {"bill_discount_percent", "bill_discount_amount"} & sent
            and typed
            and (
                row.bill_discount_amount > ZERO
                # A zero typed on a bill of documents refuses what they
                # would hand it, and stays the refusal it was.
                or (own_orders is None and row.bill_discount_source == "typed")
            )
        ):
            if row.bill_discount_typed_as == "amount":
                kept["bill_discount_amount"] = row.bill_discount_amount
            else:
                kept["bill_discount_percent"] = row.bill_discount_percent
        if ships_its_own:
            if "freight_amount" not in sent:
                kept["freight_amount"] = row.freight_amount
            elif data.freight_amount is None:
                kept["freight_amount"] = ZERO
        return data.model_copy(update=kept)

    def _raise_counter_chain_again(
        self,
        row: SalesInvoice,
        data: SalesInvoiceCreate,
        *,
        notes: list[DeliveryNote],
        orders: list[SalesOrder],
        sent: frozenset[str],
        firm_id: UUID,
        actor_id: UUID,
    ) -> (
        tuple[SalesInvoiceCreate, frozenset[UUID], dict[UUID, tuple[Decimal, Decimal]]]
        | None
    ):
        """Raise a draft counter bill's order and note again from its edit.

        A counter bill is one that raised its own sales order and delivery
        note (both carry its stamp). Its edit used to change the bill alone:
        a bill cut from 3 to 2 charged for 2 while its note still shipped 3,
        and one could not grow at all (D-SELL-72, D-SELL-59). An edit that
        changes what the bill ships -- a quantity, the lines, free goods, the
        batches or the units -- now withdraws the note and the order, which
        gives the reservation back, and raises them again from the bill's
        lines through the chain, all in the caller's transaction. The numbers
        of the withdrawn pair are spent; that is accepted.

        The lines may be sent either way: as products, the way a new counter
        bill is, or back by the source fields the bill returns, which are
        read as the same products at the same terms.

        A coupon is taken on any edit of a draft counter bill, because the
        bill is where its order is priced: one the order does not already
        hold raises the order again with it, the one it holds changes
        nothing, an explicit null takes it off, and silence keeps it. The
        edit that ships the same used to refuse a coupon the quantity edit
        took.

        Args:
            row: The draft counter bill.
            data: The edit, its header already filled from the bill.
            notes: The live notes the bill raised.
            orders: The live orders the bill raised.
            sent: The fields the request itself named.
            firm_id: The firm.
            actor_id: Who is editing.

        Returns:
            The payload rebound to the new note, that note's id, and the
            GST-inclusive rates typed -- or None where the edit ships and
            charges exactly what the note and order already do, and the bill
            is edited as any other is.

        """
        note_lines = {
            line.id: line
            for line in self._session.scalars(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id.in_([note.id for note in notes]),
                    DeliveryNoteLine.is_deleted.is_(False),
                )
            ).all()
        }
        for line in data.lines:
            if (
                line.source_document_line_id is not None
                and line.source_document_line_id not in note_lines
            ):
                raise ValidationError(
                    f"Line {line.line_number} names a document that is not "
                    f"{row.invoice_number}'s own. A counter bill is changed "
                    "through its own lines, or by sending product lines."
                )
        picked = self._own_picks(note_lines)
        order_lines = {
            line.id: line
            for line in self._session.scalars(
                select(SalesOrderLine).where(
                    SalesOrderLine.id.in_(
                        {line.sales_order_line_id for line in note_lines.values()}
                    )
                )
            ).all()
        }
        billed = {
            line.source_document_line_id: line
            for line in self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.sales_invoice_id == row.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        }
        held = next((order.coupon_code for order in orders if order.coupon_code), None)
        coupon = normalized_coupon(data.coupon_code) if "coupon_code" in sent else held
        # An offer the order was priced with may have run out since: another
        # bill was approved first and took the last of it. Saving again is
        # how this one is priced without, so that save raises the order
        # again even when nothing on the bill changed (D-SELL-85).
        spent = RedemptionService(self._session).has_run_out(
            firm_id=firm_id, document_ids=[order.id for order in orders]
        )
        if (
            coupon == held
            and not spent
            and self._ships_as_raised(data, note_lines, picked)
            and all(
                self._charges_as_raised(
                    line,
                    note_line=note_lines[line.source_document_line_id],
                    order_lines=order_lines,
                    was=billed.get(line.source_document_line_id),
                )
                for line in data.lines
                if line.source_document_line_id is not None
            )
        ):
            return None
        bare = self._as_product_lines(
            row, data, note_lines, picked, order_lines=order_lines, billed=billed
        )
        restated = data.model_copy(
            update={
                "customer_id": data.customer_id or row.customer_id,
                "branch_id": data.branch_id or row.branch_id,
                "coupon_code": coupon,
                "source_documents": [],
                "lines": bare,
            }
        )
        self._withdraw_unshipped_notes(
            row,
            firm_scope=firm_id,
            actor_id=actor_id,
            reason=f"Bill {row.invoice_number} was changed before approval.",
        )
        self._session.flush()
        chain = SalesChainService(self._session)
        typed: dict[int, PreTaxLine] = {}

        def before_tax(
            bill: SalesInvoiceCreate, branch_id: UUID, warehouse_id: UUID
        ) -> SalesInvoiceCreate:
            """Read the bill's typed GST-inclusive rates back to pre-tax."""
            return self._typed_rates_before_tax(
                bill,
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                firm_id=firm_id,
                actor_id=actor_id,
                typed=typed,
            )

        rebound = chain.ensure_invoice_source(
            restated,
            firm_id=firm_id,
            actor_id=actor_id,
            inclusive=before_tax if row.rate_includes_tax else None,
        )
        for note in chain.raised_notes:
            note.raised_by_sales_invoice_id = row.id
        for order in chain.raised_orders:
            order.raised_by_sales_invoice_id = row.id
        self._session.flush()
        entered_rates = {
            line.source_document_line_id: (
                typed[line.line_number].entered_rate,
                typed[line.line_number].unit_price,
            )
            for line in rebound.lines
            if line.line_number in typed and line.source_document_line_id is not None
        }
        return (
            rebound,
            frozenset(note.id for note in chain.raised_notes),
            entered_rates,
        )

    def _own_picks(
        self, note_lines: Mapping[UUID, DeliveryNoteLine]
    ) -> dict[UUID, tuple[dict[UUID, Decimal], list[UUID]]]:
        """Return the batches and units each of a bill's own note lines names."""
        batches: dict[UUID, dict[UUID, Decimal]] = defaultdict(dict)
        if note_lines:
            for pick in self._session.scalars(
                select(DeliveryNoteLineBatch).where(
                    DeliveryNoteLineBatch.delivery_note_line_id.in_(list(note_lines)),
                    DeliveryNoteLineBatch.is_deleted.is_(False),
                )
            ).all():
                batches[pick.delivery_note_line_id][pick.batch_id] = self._q(
                    pick.quantity
                )
        serials = SerialTrailService(self._session).picks(list(note_lines))
        return {
            line_id: (
                batches.get(line_id, {}),
                [serial.id for _, serial in serials.get(line_id, [])],
            )
            for line_id in note_lines
        }

    def _ships_as_raised(
        self,
        data: SalesInvoiceCreate,
        note_lines: Mapping[UUID, DeliveryNoteLine],
        picked: Mapping[UUID, tuple[dict[UUID, Decimal], list[UUID]]],
    ) -> bool:
        """Say whether an edit ships exactly what the bill's note already does.

        Every line of the note, once, at its quantity and free goods, with
        the batches and units it already names. Anything else -- a product
        line, a line left off, a quantity moved either way, another pick --
        is a change to what leaves.
        """
        named: set[UUID] = set()
        for line in data.lines:
            source_id = line.source_document_line_id
            if source_id is None or source_id in named:
                return False
            named.add(source_id)
            note_line = note_lines[source_id]
            if self._q(line.current_invoice_quantity) != self._q(
                note_line.current_delivery_quantity
            ):
                return False
            if line.free_quantity is not None and self._q(
                line.free_quantity
            ) != self._q(note_line.free_quantity):
                return False
            batches, serials = picked[source_id]
            if (
                line.batches is not None
                and {pick.batch_id: self._q(pick.quantity) for pick in line.batches}
                != batches
            ):
                return False
            if line.serial_ids is not None and set(line.serial_ids) != set(serials):
                return False
        return named == set(note_lines)

    @staticmethod
    def _typed_on_order(order_line: SalesOrderLine | None) -> bool:
        """Say whether somebody typed the discount an order line carries."""
        return order_line is not None and (
            order_line.discount_source in TYPED_SOURCES
            or (
                order_line.discount_source is None and order_line.discount_amount > ZERO
            )
        )

    def _charges_as_raised(
        self,
        line: SalesInvoiceLineWrite,
        *,
        note_line: DeliveryNoteLine,
        order_lines: Mapping[UUID, SalesOrderLine],
        was: SalesInvoiceLine | None,
    ) -> bool:
        """Say whether a line sent back charges what its order and note hold.

        A price or a discount changed on the bill alone left the order and
        the note at the old terms, and the next edit that raised them again
        read the terms back from there: a discount refused came back, a price
        cut went back up (D-SELL-77). So a line whose price or discount is
        not the one its order holds is a change, and the pair is raised again
        at the bill's terms.

        What the request leaves out is read off the bill's own line, so a
        draft whose bill already disagrees with its order -- one saved before
        this rule -- is put right by its next edit, whatever that edit says.
        A discount sent counts as the order's own only where the order's was
        typed too: sent, it is a decision, and an arrangement the order
        resolved for itself is not one.
        """
        order_line = order_lines.get(note_line.sales_order_line_id)
        price = line.unit_price
        if price is None and was is not None:
            price = was.unit_price
        if price is not None and self._q(price) != self._q(note_line.unit_price):
            return False
        if order_line is None:
            return True
        typed = self._typed_on_order(order_line)
        held = self._q(order_line.discount_amount)
        if line.discount_amount is not None:
            return typed and self._q(line.discount_amount) == held
        if line.discount_percent is not None:
            gross = self._q(
                line.current_invoice_quantity * self._q(note_line.unit_price)
            )
            return typed and self._q(gross * line.discount_percent / 100) == held
        if was is not None and was.discount_source in TYPED_SOURCES:
            return typed and self._q(was.discount_amount) == held
        return True

    def _as_product_lines(
        self,
        row: SalesInvoice,
        data: SalesInvoiceCreate,
        note_lines: Mapping[UUID, DeliveryNoteLine],
        picked: Mapping[UUID, tuple[dict[UUID, Decimal], list[UUID]]],
        *,
        order_lines: Mapping[UUID, SalesOrderLine],
        billed: Mapping[UUID, SalesInvoiceLine],
    ) -> list[SalesInvoiceLineWrite]:
        """Restate a counter bill's edit as the product lines it stands for.

        A line sent as a product is taken as typed. One sent back by its
        source fields is read as the same product at the terms **the bill's
        own line** holds (D-SELL-77): a price left out, or sent back as the
        bill returned it, is the bill's; a discount the request states is
        typed; one left out is the bill's where the bill typed it -- a zero
        typed there still refuses every arrangement -- then the order's where
        the order's was typed, and otherwise left blank so the customer's
        arrangement is resolved again. A gift an offer added is dropped so
        the offer is judged afresh on the new quantities. Batches and units
        are kept where the quantity is the same and nothing new was said.
        """
        lines: list[SalesInvoiceLineWrite] = []
        for line in data.lines:
            number = len(lines) + 1
            if line.source_document_line_id is None:
                lines.append(line.model_copy(update={"line_number": number}))
                continue
            note_line = note_lines[line.source_document_line_id]
            order_line = order_lines.get(note_line.sales_order_line_id)
            was = billed.get(note_line.id)
            if (
                order_line is not None
                and order_line.quantity <= ZERO
                and (order_line.description or "").startswith("Free with ")
            ):
                continue
            same_quantity = self._q(line.current_invoice_quantity) == self._q(
                note_line.current_delivery_quantity
            )
            unit_price = line.unit_price
            if unit_price is None or (
                was is not None and self._q(unit_price) == self._q(was.unit_price)
            ):
                # Unchanged: what was typed GST-inclusive is typed so again;
                # a price nobody typed stays the customer's own.
                if row.rate_includes_tax:
                    unit_price = None if was is None else was.entered_rate
                else:
                    unit_price = self._q(
                        note_line.unit_price if was is None else was.unit_price
                    )
            discount_percent = line.discount_percent
            discount_amount = line.discount_amount
            stated = discount_percent is not None or discount_amount is not None
            if not stated and was is not None and was.discount_source == "percent":
                # Typed on the bill itself: a rate goes with any quantity, and
                # a zero stays the refusal it was.
                discount_percent = self._q(was.discount_percent)
            elif not stated and was is not None and was.discount_source == "amount":
                discount_amount = (
                    self._q(
                        was.discount_amount
                        * line.current_invoice_quantity
                        / was.current_invoice_quantity
                    )
                    if was.current_invoice_quantity > ZERO
                    else self._q(was.discount_amount)
                )
            elif (
                not stated
                and order_line is not None
                and self._typed_on_order(order_line)
            ):
                if order_line.discount_percent > ZERO:
                    discount_percent = self._q(order_line.discount_percent)
                elif order_line.quantity > ZERO:
                    discount_amount = self._q(
                        order_line.discount_amount
                        * line.current_invoice_quantity
                        / order_line.quantity
                    )
            batches, serials = picked[note_line.id]
            free_quantity = line.free_quantity
            if free_quantity is None and same_quantity and note_line.free_quantity:
                free_quantity = self._q(note_line.free_quantity)
            if line.current_invoice_quantity <= ZERO and not (
                free_quantity is not None and free_quantity > ZERO
            ):
                # Said here in the words every other bill uses. The product
                # line built below refuses the same thing, but from inside
                # the service, where the schema's refusal answered 500
                # (D-SELL-78).
                raise ValidationError(
                    f"Line {line.line_number} bills a quantity of 0 and "
                    "supplies nothing free. Type a quantity, or leave the line "
                    "off the bill."
                )
            kept_batches = (
                [
                    DeliveryNoteBatchPick(batch_id=batch_id, quantity=quantity)
                    for batch_id, quantity in batches.items()
                ]
                if batches and same_quantity
                else None
            )
            lines.append(
                SalesInvoiceLineWrite(
                    product_id=note_line.product_id,
                    line_number=number,
                    current_invoice_quantity=line.current_invoice_quantity,
                    unit_price=unit_price,
                    free_quantity=free_quantity,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    tax_profile_id=line.tax_profile_id or note_line.tax_profile_id,
                    packaging_type_id=line.packaging_type_id
                    or note_line.packaging_type_id,
                    # Whichever field names a unit, else the note's own.
                    invoice_uom_id=line.invoice_uom_id
                    or line.order_uom_id
                    or note_line.sales_uom_id,
                    warehouse_id=line.warehouse_id or note_line.warehouse_id,
                    storage_node_id=line.storage_node_id or note_line.storage_node_id,
                    remarks=line.remarks,
                    serial_ids=(
                        line.serial_ids
                        if line.serial_ids is not None
                        else (serials or None)
                    ),
                    batches=line.batches if line.batches is not None else kept_batches,
                )
            )
        if not lines:
            raise ValidationError("A bill must keep at least one line.")
        return lines

    def _notes_raised_by(self, row: SalesInvoice) -> frozenset[UUID]:
        """Return the ids of the delivery notes this bill raised for itself."""
        return frozenset(
            self._session.scalars(
                select(DeliveryNote.id).where(
                    DeliveryNote.raised_by_sales_invoice_id == row.id,
                    DeliveryNote.is_deleted.is_(False),
                )
            ).all()
        )

    def _judged_discount_lines(self, row: SalesInvoice) -> list[object]:
        """Return the bill's lines with where each discount was really typed.

        A counter bill raises its own order and note and is then rebuilt to
        bill that note, so every line reads as inherited -- yet the rate was
        typed on this bill, and the order it raised was not judged (backlog
        64 row 3). For a note this bill raised itself, the source is read from
        the order line behind it: typed there means typed here.

        The discount on the whole bill is read the same way. A share the
        bill inherited from the documents it continues was judged on the
        order, and one an offer gave is nobody's hand at all, so neither is
        counted here; on a counter bill the order it raised says which
        (D-PRC-1).

        Each line also names the price the customer would otherwise pay, so
        a price typed below it is judged with the discounts (D-PRC-2).

        **Inherited means what the order agreed.** A discount or a price a
        delivery note typed below its order line is judged at the note's
        approval, which records that it was; a bill of that note inherits
        the note's terms. One from a note with no such record -- approved
        before notes were judged, or raised by this bill for an order a
        person typed -- is the bill's to answer for, and is judged here as
        typed (D-PRC-23). "Its own order" is one this bill raised: an order
        a person raised and somebody approved was judged then, and a bill
        that only ships it does not judge it again.
        """
        lines = list(
            self._session.scalars(
                select(SalesInvoiceLine).where(
                    SalesInvoiceLine.sales_invoice_id == row.id,
                    SalesInvoiceLine.is_deleted.is_(False),
                )
            ).all()
        )
        own_notes = {
            note.id
            for note in self._billed_notes(row)
            if note.raised_by_sales_invoice_id == row.id
        }
        inherited = row.bill_discount_source == "inherited"
        # What each line continues: the order line behind its note line, or
        # the order line it bills directly.
        continued = {
            note_line.id: (note_line, order_line)
            for note_line, order_line in self._session.execute(
                select(DeliveryNoteLine, SalesOrderLine)
                .join(
                    SalesOrderLine,
                    SalesOrderLine.id == DeliveryNoteLine.sales_order_line_id,
                )
                .where(
                    DeliveryNoteLine.id.in_(
                        [line.source_document_line_id for line in lines]
                    )
                )
            )
            .tuples()
            .all()
        }
        by_note_line = {
            note_line_id: order_line
            for note_line_id, (_, order_line) in continued.items()
        }
        direct = {
            order_line.id: order_line
            for order_line in self._session.scalars(
                select(SalesOrderLine).where(
                    SalesOrderLine.id.in_(
                        [
                            line.source_document_line_id
                            for line in lines
                            if line.source_document_line_id not in by_note_line
                        ]
                    )
                )
            ).all()
        }
        own_orders = {
            order.id: order
            for order in self._session.scalars(
                select(SalesOrder).where(
                    SalesOrder.id.in_(
                        {
                            by_note_line[line.source_document_line_id].sales_order_id
                            for line in lines
                            if line.source_document_id in own_notes
                            and line.source_document_line_id in by_note_line
                        }
                    ),
                    SalesOrder.raised_by_sales_invoice_id == row.id,
                )
            ).all()
        }
        # What each note line typed below its order line, for the notes this
        # bill did not price through an order of its own; and which of those
        # notes had it judged at their own approval.
        reductions = {
            note_line_id: reduction
            for note_line_id, (note_line, order_line) in continued.items()
            if order_line.sales_order_id not in own_orders
            and (reduction := note_reduction(note_line, order_line)) is not None
        }
        judged_notes = self._notes_judged_for_what_they_typed(
            {continued[note_line_id][0].delivery_note_id for note_line_id in reductions}
        )
        # A counter bill's order was priced from the bill, so its lines are
        # judged against the price the customer would otherwise pay; any
        # other bill against the price its order line agreed (D-PRC-2).
        limits = DiscountLimitService(self._session)
        ranked: dict[UUID, Decimal] = {}
        for order in own_orders.values():
            order_lines = [
                order_line
                for order_line in by_note_line.values()
                if order_line.sales_order_id == order.id
            ]
            prices = limits.customer_prices(
                order_lines,
                firm_id=order.firm_id,
                customer_id=order.customer_id,
                territory_id=order.territory_id,
                on=order.order_date,
            )
            ranked.update(
                {
                    order_line.id: prices[order_line.line_number]
                    for order_line in order_lines
                    if order_line.line_number in prices
                }
            )
        judged: list[object] = []
        for line in lines:
            order_line = by_note_line.get(line.source_document_line_id) or direct.get(
                line.source_document_line_id
            )
            own = (
                None
                if order_line is None or line.source_document_id not in own_notes
                else own_orders.get(order_line.sales_order_id)
            )
            source = (
                line.discount_source
                if own is None or order_line is None
                else order_line.discount_source
            )
            if own is not None:
                # Typed on the order the bill raised, or on the bill alone by
                # an edit that raised nothing again.
                bill_typed = not (inherited and own.bill_discount_source in OFFERED)
                customer_price = ranked.get(order_line.id) if order_line else None
            else:
                bill_typed = not inherited
                agreed_price = (
                    None if order_line is None else self._q(order_line.unit_price)
                )
                reduction = reductions.get(line.source_document_line_id)
                if reduction is not None:
                    note_line = continued[line.source_document_line_id][0]
                    if note_line.delivery_note_id in judged_notes:
                        # Judged on the note: its price is the agreed one.
                        agreed_price = self._q(note_line.unit_price)
                    else:
                        if reduction.typed_line and source == "inherited":
                            source = "amount"
                        bill_typed = bill_typed or reduction.typed_bill
                # A line typed in another unit than the line it bills is
                # stored in that line's unit -- quantity and price both -- so
                # the agreed price is already the price of the unit it is
                # in. It was left out on `conversion_factor != 1` and judged
                # on its typed discount alone.
                customer_price = agreed_price
            judged.append(
                SimpleNamespace(
                    line_number=line.line_number,
                    gross_amount=line.gross_amount,
                    discount_amount=line.discount_amount,
                    bill_discount_amount=(
                        line.bill_discount_amount if bill_typed else ZERO
                    ),
                    discount_source=source,
                    current_invoice_quantity=line.current_invoice_quantity,
                    unit_price=line.unit_price,
                    customer_price=customer_price,
                )
            )
        return judged

    def _notes_judged_for_what_they_typed(self, note_ids: set[UUID]) -> set[UUID]:
        """Return the notes whose approval judged a reduction they typed.

        Read off the note's APPROVED event, where its approval says so
        (``NOTE_REDUCTION_JUDGED``). Asked only for notes that typed one.
        """
        if not note_ids:
            return set()
        return {
            event.source_document_id
            for event in self._session.scalars(
                select(DocumentLifecycleEvent).where(
                    DocumentLifecycleEvent.source_document_id.in_(note_ids),
                    DocumentLifecycleEvent.action == "APPROVED",
                )
            ).all()
            if (event.details_json or {}).get(NOTE_REDUCTION_JUDGED)
        }

    def _billed_notes(self, row: SalesInvoice) -> list[DeliveryNote]:
        """Return the delivery notes a bill names as its sources."""
        return list(
            self._session.scalars(
                select(DeliveryNote)
                .join(
                    SalesInvoiceSource,
                    SalesInvoiceSource.source_document_id == DeliveryNote.id,
                )
                .where(
                    SalesInvoiceSource.sales_invoice_id == row.id,
                    SalesInvoiceSource.source_document_type
                    == SalesInvoiceSourceType.DELIVERY_NOTE.value,
                    SalesInvoiceSource.is_deleted.is_(False),
                )
            ).all()
        )

    def _ship_on_approval(
        self,
        row: SalesInvoice,
        notes: list[DeliveryNote],
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> None:
        """Dispatch the notes a bill raised for itself, and cost its lines.

        The lines were written while the goods were still on the shelf, so
        nothing could say what they cost; the dispatch's own movement does
        now, read the way every other bill reads it.
        """
        if not notes:
            return
        service = DeliveryNoteService(self._session)
        for note in notes:
            service.stage_dispatch(note.id, firm_scope=firm_scope, actor_id=actor_id)
        self._session.flush()
        shipped = {note.id for note in notes}
        costs = self._dispatch_costs(shipped)
        for line in self._session.scalars(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == row.id,
                SalesInvoiceLine.source_document_type
                == SalesInvoiceSourceType.DELIVERY_NOTE.value,
                SalesInvoiceLine.source_document_id.in_(shipped),
                SalesInvoiceLine.is_deleted.is_(False),
            )
        ).all():
            note_line = self._session.get(
                DeliveryNoteLine, line.source_document_line_id
            )
            if note_line is None:  # pragma: no cover - the bill was built on it
                continue
            line.cost_amount = self._line_cost(
                source_line=note_line,
                source_type=SalesInvoiceSourceType.DELIVERY_NOTE.value,
                invoice_quantity=self._q(line.current_invoice_quantity),
                source_quantity=self._q(line.delivered_quantity),
                costs=costs,
            )

    def _withdraw_unshipped_notes(
        self,
        row: SalesInvoice,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> None:
        """Cancel the notes a cancelled draft raised for itself.

        They were raised to carry this bill's goods and have not left; kept,
        they would hold the order's quantity against a sale that is off, with
        no screen offering them. A note another live bill also names is left
        alone, and so is one this bill did not raise: a person's note is
        theirs to cancel, whatever the firm's stage says now (D-CFG-16).
        """
        service = DeliveryNoteService(self._session)
        for note in self._billed_notes(row):
            if (
                note.status != DeliveryNoteStatus.APPROVED.value
                or note.raised_by_sales_invoice_id != row.id
            ):
                continue
            others = self._session.scalar(
                select(func.count(SalesInvoiceSource.id))
                .join(
                    SalesInvoice,
                    SalesInvoice.id == SalesInvoiceSource.sales_invoice_id,
                )
                .where(
                    SalesInvoiceSource.source_document_id == note.id,
                    SalesInvoiceSource.is_deleted.is_(False),
                    SalesInvoice.id != row.id,
                    SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                    SalesInvoice.is_deleted.is_(False),
                )
            )
            if others:
                continue
            reason = reason or (
                f"Bill {row.invoice_number} was cancelled before approval."
            )
            service.stage_cancel(
                note.id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
            )
            # A request's session does not flush on a read, and the order's
            # own cancel asks which of its notes still stand.
            self._session.flush()
            self._withdraw_own_order(
                row,
                note.sales_order_id,
                firm_scope=firm_scope,
                actor_id=actor_id,
                reason=reason,
            )

    def _withdraw_own_order(
        self,
        row: SalesInvoice,
        order_id: UUID,
        *,
        firm_scope: UUID,
        actor_id: UUID,
        reason: str,
    ) -> None:
        """Cancel the sales order a cancelled draft raised for itself.

        A bill typed straight in raises an order as well as a note, and the
        order's approval is what reserves the stock. Cancelling the note alone
        left the order APPROVED and the quantity held for a sale that was off,
        with no screen showing why, until every later sale of the product was
        refused for stock (D-SELL-54, driven 2026-10-05). Only the order this
        bill stamped goes: one a person raised, which a bill merely dispatched
        for a firm that types no notes, is theirs and stays approved.
        """
        order = self._session.get(SalesOrder, order_id)
        if (
            order is None
            or order.raised_by_sales_invoice_id != row.id
            or order.status in {"CANCELLED", "CLOSED"}
        ):
            return
        SalesOrderService(self._session).stage_cancel(
            order.id, firm_scope=firm_scope, actor_id=actor_id, reason=reason
        )

    def _assert_nothing_rests_on(self, row: SalesInvoice) -> None:
        """Refuse to cancel a bill that money, a correction or a filing rests on.

        Cancelling reverses the invoice's journal and takes its whole total off
        the customer's balance. It used to check nothing else, so a bill with a
        receipt applied, a live credit note or sales return, points spent on
        it, or a registration with the tax authority could be cancelled --
        leaving the receipt clearing a cancelled bill and the customer credited
        twice (found reviewing plan item 12.2, 2026-09-13). Each of those has
        its own undo -- reverse the receipt, cancel the note or return, cancel
        the registration -- and doing that first is what keeps the books
        telling one story. The refusal names what is in the way.
        """
        # Imported here: these modules import the invoice model, and a
        # module-level import would tie the invoice service to all four.
        from app.credit_note.models import CreditNote, CreditNoteStatus
        from app.einvoice.models import (
            EInvoiceRegistration,
            EWayBill,
            EWayBillStatus,
            RegistrationStatus,
        )
        from app.sales_return.models import SalesReturn, SalesReturnSource
        from app.settlements.models import Settlement, SettlementAllocation

        blockers: list[str] = []
        receipts = self._session.scalars(
            select(Settlement.settlement_number)
            .join(
                SettlementAllocation,
                SettlementAllocation.settlement_id == Settlement.id,
            )
            .where(
                SettlementAllocation.sales_invoice_id == row.id,
                SettlementAllocation.is_deleted.is_(False),
                Settlement.status == "POSTED",
                Settlement.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        if receipts:
            blockers.append("money applied from " + ", ".join(sorted(receipts)))
        # Credit a return or credit note left on another bill, set against
        # this one: it clears the bill as a receipt does, and would be left
        # clearing nothing (D-PRC-75).
        from app.settlements.services.customer_credits import (
            credit_numbers_against,
        )

        credits = credit_numbers_against(
            self._session, firm_id=row.firm_id, bill_id=row.id
        )
        if credits:
            blockers.append("credit applied from " + ", ".join(credits))
        # A write-off or set-off naming the bill, drafted or approved: it would
        # clear nothing once the bill was gone (backlog 74 row 2).
        from app.party_adjustments.services.allocations import (
            adjustment_numbers_against,
        )

        adjustments = adjustment_numbers_against(
            self._session, column="sales_invoice_id", bill_id=row.id
        )
        if adjustments:
            blockers.append("party adjustment " + ", ".join(adjustments))
        notes = self._session.scalars(
            select(CreditNote.credit_note_number).where(
                CreditNote.sales_invoice_id == row.id,
                CreditNote.status != CreditNoteStatus.CANCELLED.value,
                CreditNote.is_deleted.is_(False),
            )
        ).all()
        if notes:
            blockers.append("credit note " + ", ".join(sorted(notes)))
        from app.customer_debit_note.models import (
            CustomerDebitNote,
            CustomerDebitNoteStatus,
        )

        debits = self._session.scalars(
            select(CustomerDebitNote.debit_note_number).where(
                CustomerDebitNote.sales_invoice_id == row.id,
                CustomerDebitNote.status != CustomerDebitNoteStatus.CANCELLED.value,
                CustomerDebitNote.is_deleted.is_(False),
            )
        ).all()
        if debits:
            blockers.append("debit note " + ", ".join(sorted(debits)))
        returns = self._session.scalars(
            select(SalesReturn.return_number)
            .join(
                SalesReturnSource, SalesReturnSource.sales_return_id == SalesReturn.id
            )
            .where(
                SalesReturnSource.source_document_type == "SALES_INVOICE",
                SalesReturnSource.source_document_id == row.id,
                SalesReturn.status != "CANCELLED",
                SalesReturn.is_deleted.is_(False),
            )
            .distinct()
        ).all()
        # Goods this bill charged for can also come back against the note it
        # billed, and cancelling then takes the whole bill off the customer on
        # top of the credit that return gave (D-SELL-7). Only the returns
        # that took units of **this** bill: every return of the note used to
        # count, so a draft bill -- which has charged nobody -- could not be
        # withdrawn once anything had come back off its note, and went on
        # holding the note's units (D-PRC-77).
        from app.sales_return.billing import returns_resting_on

        off_the_note = returns_resting_on(
            self._session, firm_id=row.firm_id, invoice_id=row.id
        )
        if off_the_note:
            returns = sorted(
                set(returns)
                | set(
                    self._session.scalars(
                        select(SalesReturn.return_number).where(
                            SalesReturn.id.in_(off_the_note)
                        )
                    ).all()
                )
            )
        if returns:
            blockers.append("sales return " + ", ".join(returns))
        # Points spent on the bill are not a blocker (D-PRC-6): nothing could
        # reverse one, so such a bill could never be cancelled. They are not
        # money that changed hands, and `cancel_invoice` puts them back.
        registered = self._session.scalar(
            select(func.count(EInvoiceRegistration.id)).where(
                EInvoiceRegistration.sales_invoice_id == row.id,
                EInvoiceRegistration.status == RegistrationStatus.REGISTERED.value,
                EInvoiceRegistration.is_deleted.is_(False),
            )
        )
        if registered:
            blockers.append("its registration with the tax authority")
        # A bill whose registration was already withdrawn can still have its
        # e-way bill standing -- the goods may be on the road under it -- and
        # cancelling the invoice then leaves a live bill for a supply that no
        # longer exists (D-CMP-5).
        live_bills = self._session.scalars(
            select(EWayBill.eway_bill_number).where(
                EWayBill.sales_invoice_id == row.id,
                EWayBill.status == EWayBillStatus.GENERATED.value,
                EWayBill.is_deleted.is_(False),
            )
        ).all()
        if live_bills:
            blockers.append(
                "e-way bill " + ", ".join(sorted(str(n) for n in live_bills))
            )
        if blockers:
            raise ValidationError(
                f"{row.invoice_number} cannot be cancelled while it has "
                + "; ".join(blockers)
                + ". Reverse or cancel those first."
            )

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
        self._assert_nothing_rests_on(row)
        before = row.status
        row.status = SalesInvoiceStatus.CANCELLED.value
        row.cancel_reason = reason
        row.cancelled_at = utc_now()
        row.updated_by = actor_id
        if row.is_held:
            # A cancelled bill is not waiting for anybody (SG-7): it leaves
            # the counter's list of parked bills with its note kept.
            row.is_held = False
        if before == SalesInvoiceStatus.DRAFT.value and row.allow_direct_sales_order:
            self._withdraw_unshipped_notes(
                row, firm_scope=firm_scope, actor_id=actor_id
            )
        if before == SalesInvoiceStatus.APPROVED.value:
            # The invoice posted revenue, tax and a receivable when it was
            # approved. Cancelling it reduced the customer's balance and left
            # all three in the ledger, so the receivable control account
            # overstated by the whole invoice from that moment on. Reversing
            # the entry mirrors what it raised, which is right in a way that
            # booking the lot as a sales return would not be.
            reversed_on = self._reverse_invoice_posting(
                row, firm_scope=firm_scope, actor_id=actor_id
            )
            # Points spent on the bill come back first (D-PRC-6): each
            # redemption's journal mirrored and the customer's balance put
            # back by its own row, before the bill itself comes off it below.
            RedemptionReversalService(self._session).stage_for_cancelled_bill(
                row, firm_id=firm_scope, actor_id=actor_id
            )
            # The points the bill earned go with it, and their accrual with
            # them; kept, they could be spent from a sale that never happened
            # (D-SELL-2, 2026-09-19).
            LoyaltyService(self._session).stage_reversal(
                row, firm_id=firm_scope, actor_id=actor_id
            )
            # A bill that came to nothing put nothing on the account, so
            # there is nothing to take off it (D-SELL-53).
            if _receivable_amount(row.grand_total) > ZERO:
                CustomerService(self._session).post_receivable_transaction(
                    row.customer_id,
                    CustomerReceivableTransactionCreate(
                        transaction_type=CustomerReceivableTransactionType.CREDIT_NOTE,
                        # The reversal's own date, so the statement and 1100
                        # agree; and never before the bill (D-FIN-5), which a
                        # UTC "today" was until 05:30 in India.
                        transaction_date=reversed_on
                        or max(firm_today(self._session, firm_scope), row.invoice_date),
                        amount=_receivable_amount(row.grand_total),
                        reference_type="SALES_INVOICE",
                        reference_id=row.id,
                        reference_number=row.invoice_number,
                        remarks=reason
                        or f"Auto reversal for cancelled invoice "
                        f"{row.invoice_number}.",
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
        """Close one approved sales invoice.

        Closing says a bill is finished with, so only an approved bill -- one
        that posted -- can be. It refused only one already closed, so a DRAFT
        that never posted kept its quantity against the note for good, and a
        CANCELLED one took back the quantity its cancellation had released
        (D-SELL-12, driven on `fx_t0919psxt_s` on 2026-09-19). The twin of
        D-BUY-12.
        """
        row = self.get_invoice(invoice_id, firm_scope=firm_scope)
        if row.status == SalesInvoiceStatus.CLOSED.value:
            raise ValidationError("This sales invoice is already closed.")
        if row.status != SalesInvoiceStatus.APPROVED.value:
            raise ValidationError(
                f"Only approved sales invoices can be closed; "
                f"{row.invoice_number} is {row.status.lower()}."
            )
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
        return self.invoice_responses([row])[0]

    def invoice_responses(
        self, rows: Sequence[SalesInvoice]
    ) -> list[SalesInvoiceResponse]:
        """Render a page of invoices, reading each child table once.

        One query per child table for the whole page, grouped by invoice in
        Python, rather than about ten per invoice (backlog 56 C, step 3). The
        single-invoice builder is this with a list of one, so a list row and
        the invoice opened from it cannot differ.
        """
        if not rows:
            return []
        ids = [row.id for row in rows]
        sources = children_by_parent(
            self._session,
            SalesInvoiceSource,
            SalesInvoiceSource.sales_invoice_id,
            ids,
        )
        lines = children_by_parent(
            self._session,
            SalesInvoiceLine,
            SalesInvoiceLine.sales_invoice_id,
            ids,
            SalesInvoiceLine.line_number.asc(),
        )
        every_line = [item for group in lines.values() for item in group]
        taxes = children_by_parent(
            self._session,
            SalesInvoiceLineTax,
            SalesInvoiceLineTax.sales_invoice_line_id,
            [item.id for item in every_line],
            SalesInvoiceLineTax.sequence.asc(),
        )
        attachments = children_by_parent(
            self._session,
            SalesInvoiceAttachment,
            SalesInvoiceAttachment.sales_invoice_id,
            ids,
        )
        notes = children_by_parent(
            self._session,
            SalesInvoiceNote,
            SalesInvoiceNote.sales_invoice_id,
            ids,
        )
        accounting_events = children_by_parent(
            self._session,
            SalesInvoiceAccountingEvent,
            SalesInvoiceAccountingEvent.sales_invoice_id,
            ids,
        )
        # The tenders a counter bill was paid with (SEL-12), read once for
        # the page: one read per bill is what made the list cost grow with
        # its length.
        tenders = children_by_parent(
            self._session,
            SalesInvoiceTender,
            SalesInvoiceTender.sales_invoice_id,
            ids,
            SalesInvoiceTender.sequence.asc(),
        )
        # The separately taxed charges (SG-4), likewise once for the page.
        charges = children_by_parent(
            self._session,
            SalesInvoiceCharge,
            SalesInvoiceCharge.sales_invoice_id,
            ids,
            SalesInvoiceCharge.sequence.asc(),
        )
        warnings = self._duplicate_warnings(rows)
        # One query for every product on the page rather than one per line.
        # `description` is nullable and the seeded documents leave it null, so
        # a client with only `product_id` to work with can label a line nothing
        # better than "Line 1" -- which is what the credit-note and
        # sales-return pickers were reduced to.
        products = self._products_named(every_line)
        picked = self._own_note_picks_for(rows, lines, products)
        # The batches behind each line, one read for the page (backlog 79).
        chosen = DeliveryNoteService(self._session).batch_picks(
            [
                line.source_document_line_id
                for line in every_line
                if line.source_document_type
                == SalesInvoiceSourceType.DELIVERY_NOTE.value
            ]
        )
        names = customer_labels(self._session, (row.customer_id for row in rows))
        answer = [
            self._invoice_response(
                row,
                lines=lines[row.id],
                taxes=taxes,
                products=products,
                picked=picked,
                chosen=chosen,
                sources=sources[row.id],
                attachments=attachments[row.id],
                notes=notes[row.id],
                accounting_events=accounting_events[row.id],
                tenders=tenders[row.id],
                charges=charges[row.id],
                warning=warnings.get(row.id),
                customer_name=names.get(row.customer_id, ""),
            )
            for row in rows
        ]
        # The firm's own fields, one read for the page (MST-6).
        fields = document_attributes.responses_for_many(
            self._session, AttributeEntityType.SALES_INVOICE, [r.id for r in rows]
        )
        # Uploaded files, counted for the page in one grouped read (SG-6).
        files = document_file_counts(
            self._session, FileParent.SALES_INVOICE, [r.id for r in rows]
        )
        # A counter bill's bill discount is typed onto the order it raised
        # and reaches the bill as that order's share, so the row records
        # `inherited` -- which is what every rule reads, and is left alone.
        # To a reader it was typed: the response says so (third pricing
        # check, section D item 3). One read for the page, and only where a
        # bill was told a figure.
        told = [
            row.id
            for row in rows
            if row.bill_discount_source == "inherited"
            and row.bill_discount_typed_as is not None
        ]
        typed_on_own_order = (
            set(
                self._session.scalars(
                    select(SalesOrder.raised_by_sales_invoice_id).where(
                        SalesOrder.raised_by_sales_invoice_id.in_(told),
                        SalesOrder.is_deleted.is_(False),
                        SalesOrder.status != "CANCELLED",
                        SalesOrder.bill_discount_source == "typed",
                    )
                ).all()
            )
            if told
            else set()
        )
        for response in answer:
            response.attributes = fields.get(response.id, [])
            response.attached_file_count = files.get(response.id, 0)
            if response.id in typed_on_own_order:
                response.bill_discount_source = "typed"
        return answer

    def _invoice_response(
        self,
        row: SalesInvoice,
        *,
        lines: list[SalesInvoiceLine],
        taxes: dict[UUID, list[SalesInvoiceLineTax]],
        products: dict[UUID, Product],
        picked: dict[UUID, list[PickedSerial]],
        sources: list[SalesInvoiceSource],
        chosen: dict[UUID, list[DeliveryNoteBatchPick]] | None = None,
        attachments: list[SalesInvoiceAttachment],
        notes: list[SalesInvoiceNote],
        accounting_events: list[SalesInvoiceAccountingEvent],
        tenders: list[SalesInvoiceTender],
        charges: list[SalesInvoiceCharge],
        warning: str | None,
        customer_name: str,
    ) -> SalesInvoiceResponse:
        """Build one invoice's response from what the page already read."""
        return SalesInvoiceResponse(
            id=row.id,
            created_by=row.created_by,
            firm_id=row.firm_id,
            customer_id=row.customer_id,
            customer_name=customer_name,
            salesman_id=row.salesman_id,
            territory_id=row.territory_id,
            route_id=row.route_id,
            branch_id=row.branch_id,
            business_profile_id=row.business_profile_id,
            invoice_number=row.invoice_number,
            invoice_date=row.invoice_date,
            customer_invoice_number=row.customer_invoice_number,
            place_of_supply=row.place_of_supply,
            shipping_address_id=row.shipping_address_id,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            payment_terms=row.payment_terms,
            due_date=row.due_date,
            reference_number=row.reference_number,
            remarks=row.remarks,
            allow_direct_sales_order=row.allow_direct_sales_order,
            status=SalesInvoiceStatus(row.status),
            total_source_quantity=row.total_source_quantity,
            total_already_invoiced_quantity=row.total_already_invoiced_quantity,
            total_current_invoice_quantity=row.total_current_invoice_quantity,
            version=row.version,
            total_free_quantity=row.total_free_quantity,
            bill_discount_percent=row.bill_discount_percent,
            bill_discount_amount=row.bill_discount_amount,
            bill_discount_source=row.bill_discount_source,
            bill_discount_typed_as=row.bill_discount_typed_as,
            freight_amount=row.freight_amount,
            line_discount_total=row.line_discount_total,
            subtotal=row.subtotal,
            tax_total=row.tax_total,
            additional_charges=row.additional_charges,
            round_off=row.round_off,
            grand_total=row.grand_total,
            amount_payable=_receivable_amount(row.grand_total),
            buyer_name=row.buyer_name,
            buyer_phone=row.buyer_phone,
            received_now_amount=row.received_now_amount,
            received_now_method=row.received_now_method,
            received_now_reference=row.received_now_reference,
            received_now_settlement_id=row.received_now_settlement_id,
            received_now_tenders=[
                SalesInvoiceTenderResponse(
                    mode=tender.mode,
                    amount=tender.amount,
                    reference=tender.reference,
                    settlement_id=tender.settlement_id,
                )
                for tender in tenders
            ],
            charges=[
                SalesInvoiceChargeResponse.model_validate(charge) for charge in charges
            ],
            charges_total=self._q(
                sum((Decimal(str(charge.amount)) for charge in charges), ZERO)
            ),
            rate_includes_tax=bool(row.rate_includes_tax),
            is_held=bool(row.is_held),
            held_at=row.held_at,
            held_note=row.held_note,
            counter_shift_id=row.counter_shift_id,
            approved_at=row.approved_at,
            closed_at=row.closed_at,
            cancel_reason=row.cancel_reason,
            close_reason=row.close_reason,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at,
            lines=[
                self._line_response(
                    item,
                    taxes.get(item.id, []),
                    products.get(item.product_id),
                    serials=picked.get(item.source_document_line_id),
                    batches=(chosen or {}).get(item.source_document_line_id, []),
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

    def _owing(self, *, firm_scope: UUID) -> list[OutstandingInvoiceRecord]:
        """Every invoice of the firm still owing something, as Record Receipt sees it.

        One derivation -- ``settled_against``: money allocated from posted
        receipts, points spent, returns and credit notes against the bill --
        shared with Record Receipt and the ageing, so a report cannot disagree
        with either (D-RPT-3). Imported here because the settlement service
        imports this module's models.
        """
        from app.settlements.services.settlement_service import ReceiptService

        return ReceiptService(self._session).outstanding_invoices(
            firm_id=firm_scope, party_id=None
        )

    def overdue_report(
        self, *, firm_scope: UUID, due_within: int | None = None
    ) -> list[SalesInvoiceOverdueRecord]:
        """List the invoices past their due date that still owe something.

        Judged on what is owed rather than on status: a collected invoice
        stays APPROVED, so it used to be overdue for ever, and a DRAFT with a
        due date was listed although it never posted (D-RPT-3; 5 of WHOLE01's
        23 were paid in full).
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
        # The two things the row needs of the invoice, never the whole row.
        invoices: dict[UUID, tuple[str | None, Decimal]] = {}
        if owing:
            invoices = {
                invoice_id: (number, total)
                for part in chunks([item.invoice_id for item in owing])
                for invoice_id, number, total in self._session.execute(
                    select(
                        SalesInvoice.id,
                        SalesInvoice.customer_invoice_number,
                        SalesInvoice.grand_total,
                    ).where(SalesInvoice.id.in_(part))
                ).all()
            }
        names = self._customer_names(
            {record.party_id for record in owing if record.party_id is not None}
        )
        records: list[SalesInvoiceOverdueRecord] = []
        for record in owing:
            if record.due_date is None or record.party_id is None:  # pragma: no cover
                continue
            # A customer's opening bill is owed and can be overdue like any
            # other, but it is not a sales invoice, so the record carries what
            # the row would have said.
            row = invoices.get(record.invoice_id)
            records.append(
                SalesInvoiceOverdueRecord(
                    invoice_id=record.invoice_id,
                    invoice_number=record.invoice_number,
                    customer_invoice_number=None if row is None else row[0],
                    customer_id=record.party_id,
                    customer_name=names.get(record.party_id, str(record.party_id)),
                    invoice_date=record.invoice_date,
                    due_date=record.due_date,
                    days_overdue=max((today - record.due_date).days, 0),
                    days_until_due=max((record.due_date - today).days, 0),
                    # The bill as Record Receipt states it -- with any debit
                    # note raised on it (backlog 77 row 5) -- so the row's
                    # total less what was settled is what it still owes.
                    grand_total=record.invoice_total,
                    settled_amount=record.allocated_amount,
                    outstanding_amount=record.outstanding_amount,
                )
            )
        records.sort(key=lambda item: (item.due_date, item.invoice_number))
        return records

    def _customer_names(self, customer_ids: set[UUID]) -> dict[UUID, str]:
        """Read the display names of the customers named, in one query."""
        if not customer_ids:
            return {}
        return {
            customer_id: name
            for part in chunks(list(customer_ids))
            for customer_id, name in self._session.execute(
                select(Customer.id, Customer.display_name).where(Customer.id.in_(part))
            ).all()
        }

    def register_report(
        self,
        *,
        firm_scope: UUID,
        statuses: Sequence[str] | None = None,
        window: ReportWindow = WHOLE_HISTORY,
    ) -> list[SalesInvoiceRegisterRecord]:
        """Return the register report, optionally narrowed to some statuses.

        The pending report answers this shape too, rather than whole
        documents (D-RPT-16).

        The customer and the branch are named as well as identified, in one
        read each for the whole report: the grid derives its columns from the
        row, so a register of ids alone read as UUIDs (D-RPT-17).
        """
        rows = window.fetch(
            self._session,
            select(SalesInvoice)
            .where(
                SalesInvoice.firm_id == firm_scope,
                SalesInvoice.is_deleted.is_(False),
                *(
                    ()
                    if statuses is None
                    else (SalesInvoice.status.in_(list(statuses)),)
                ),
                *window.dated(SalesInvoice.invoice_date),
            )
            .order_by(
                SalesInvoice.invoice_date.desc(),
                SalesInvoice.created_at.desc(),
                SalesInvoice.id.desc(),
            ),
        )
        customers = customer_names(self._session, (row.customer_id for row in rows))
        branches = branch_names(self._session, (row.branch_id for row in rows))
        records = [
            SalesInvoiceRegisterRecord(
                invoice_id=row.id,
                invoice_number=row.invoice_number,
                customer_invoice_number=row.customer_invoice_number,
                customer_id=row.customer_id,
                customer_name=customers.get(row.customer_id, str(row.customer_id)),
                branch_id=row.branch_id,
                branch_name=branches.get(row.branch_id, str(row.branch_id)),
                invoice_date=row.invoice_date,
                due_date=row.due_date,
                grand_total=row.grand_total,
                status=SalesInvoiceStatus(row.status),
            )
            for row in rows
        ]
        return mapped_like(rows, records)

    def outstanding_report(
        self, *, firm_scope: UUID
    ) -> list[SalesInvoiceCustomerOutstandingRecord]:
        """Return the outstanding report for the visible firm scope.

        The customer is named by `display_name`, as every other report names
        one: this read `name`, the legal name, so the same customer appeared
        under two names on two screens (D-RPT-19).
        """
        rows = list(
            self._session.scalars(
                select(Customer).where(
                    Customer.firm_id == firm_scope,
                    Customer.is_deleted.is_(False),
                )
                # The name and the balance, without the addresses and
                # contacts every customer would otherwise load (PLT-4).
                .options(
                    load_only(Customer.display_name, Customer.current_outstanding),
                    lazyload("*"),
                )
            ).all()
        )
        # Bills still owing something, by the derivation Record Receipt uses;
        # every APPROVED invoice used to count, settled ones included (D-RPT-3).
        counts: dict[UUID, int] = defaultdict(int)
        for record in self._owing(firm_scope=firm_scope):
            if record.party_id is not None:
                counts[record.party_id] += 1
        return [
            SalesInvoiceCustomerOutstandingRecord(
                customer_id=customer.id,
                customer_name=customer.display_name,
                outstanding_amount=self._q(customer.current_outstanding),
                invoice_count=counts[customer.id],
            )
            for customer in rows
            if customer.current_outstanding > ZERO
        ]

    def reconciliation_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[SalesInvoiceReconciliationRecord]:
        """Say what is billed against each delivered line, and what is left.

        One row per source line, summed over the invoices that still stand:
        a cancelled invoice billed nothing, a draft has not billed yet
        (D-RPT-13). Most recently billed first.

        The window picks the source lines billed on an invoice dated inside
        it; the sums still run over every invoice of those lines, or a line
        billed half in March and half in April would show half pending. It
        is grouped and paged in SQL: reading every line of the firm into
        Python took 95 s over 549,057 lines (backlog 56 C, step 4).
        """
        live = (
            SalesInvoice.firm_id == firm_scope,
            SalesInvoice.is_deleted.is_(False),
            SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
            SalesInvoiceLine.is_deleted.is_(False),
        )
        joined = (SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
        in_window = (
            select(SalesInvoiceLine.source_document_line_id)
            .join(*joined)
            .where(*live, *window.dated(SalesInvoice.invoice_date))
        )
        is_draft = SalesInvoice.status == SalesInvoiceStatus.DRAFT.value
        quantity = SalesInvoiceLine.current_invoice_quantity
        grouped = (
            select(
                SalesInvoiceLine.source_document_line_id,
                func.coalesce(func.sum(case((is_draft, ZERO), else_=quantity)), 0),
                func.coalesce(func.sum(case((is_draft, quantity), else_=ZERO)), 0),
            )
            .join(*joined)
            .where(
                *live,
                SalesInvoiceLine.firm_id == firm_scope,
                SalesInvoiceLine.source_document_line_id.in_(in_window),
            )
            .group_by(SalesInvoiceLine.source_document_line_id)
            # Latest bill date first; the group key breaks a tie, so a page
            # never repeats or skips a line.
            .order_by(
                func.max(SalesInvoice.invoice_date).desc(),
                SalesInvoiceLine.source_document_line_id,
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
        # Every invoice line of the page's source lines, newest first, for the
        # line's own details and the invoice numbers.
        lines: dict[UUID, list[tuple[SalesInvoiceLine, str]]] = {
            line_id: [] for line_id in sums
        }
        for part in chunks(list(sums)):
            for line, number in self._session.execute(
                select(SalesInvoiceLine, SalesInvoice.invoice_number)
                .join(*joined)
                .where(*live, SalesInvoiceLine.source_document_line_id.in_(part))
                .order_by(
                    SalesInvoice.invoice_date.desc(), SalesInvoice.created_at.desc()
                )
            ).all():
                lines[line.source_document_line_id].append((line, number))
        products = product_names(
            self._session, (found[0][0].product_id for found in lines.values())
        )
        result: list[SalesInvoiceReconciliationRecord] = []
        for line_id, (billed, drafted) in sums.items():
            newest, _ = lines[line_id][0]
            pending = self._q(newest.delivered_quantity - billed - drafted)
            result.append(
                SalesInvoiceReconciliationRecord(
                    source_document_type=SalesInvoiceSourceType(
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
                    delivered_quantity=newest.delivered_quantity,
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

    def _inherited_freight(self, priced: list[_PricedInvoiceLine]) -> Decimal:
        """Return the freight a bill charges when the caller says nothing.

        The source line's own share of its document's freight, pro-rated by
        the share being billed -- from the note where the bill is raised on
        one, from the order where it is raised straight off the order. A bill
        carried none of it, so the delivery charge agreed on the order was
        never billed (D-SELL-36). Zero waives it, as every amount here does.
        """
        total = ZERO
        for item in priced:
            source = item.source_line
            basis = self._source_quantity(item.spec, source)
            if basis <= ZERO:
                continue
            billed = self._q(Decimal(str(item.spec["current_invoice_quantity"])))
            total += (
                self._q(getattr(source, "freight_amount", ZERO) or ZERO)
                * billed
                / basis
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
        row: SalesInvoice,
        *,
        percent: Decimal | None,
        amount: Decimal | None,
        taxables: list[Decimal],
        inherited: list[Decimal],
    ) -> list[Decimal]:
        """Resolve the document's discount and return each line's share.

        **A bill that says nothing charges what the order agreed.** Each line
        takes the share of the whole-document discount the line it bills
        carries, by the quantity billed (``inherited``), exactly as it takes
        a line discount amount; the header shows the total. Nothing read it,
        so an order approved at 5,265.16 with 200 off was billed at 5,501.16
        and the journal followed the bill (D-PRC-1). Freight was already
        carried (`_inherited_freight`); this is its twin.

        **A figure typed on the bill replaces it**, zero included, as a
        typed freight does: the bill then states its own discount, split
        across its lines by what each is worth. A figure equal to the one
        inherited is the inheritance sent back -- an editor re-saving the
        rate it was shown -- and keeps the source lines' own shares, so
        opening and saving a bill moves nothing.

        ``bill_discount_source`` records which, because the two are treated
        differently afterwards: only a typed one is judged against the
        approver's discount limit and carried across an edit that leaves it
        out.

        Taken off what the lines already discounted to, never off the gross --
        off the gross, the two discounts are each computed as though the other
        had not happened, and the pair takes off more than either was agreed to.

        What is written back onto the header is the amount actually applied and
        the rate it represents, rather than whatever the caller sent.
        """
        taxable = self._q(sum(taxables, ZERO))
        carried = self._q(sum(inherited, ZERO))
        rate = self._q(carried * 100 / taxable) if taxable > ZERO else ZERO
        # Which figure the bill was told, so an edit that says nothing can
        # carry that one. Recorded whether or not the figure turns out to be
        # the inheritance sent back: a counter bill's typed discount is typed
        # onto its own order and reaches the bill as that order's share.
        row.bill_discount_typed_as = (
            "amount"
            if amount is not None
            else ("percent" if percent is not None else None)
        )
        if amount is not None:
            restated = self._q(amount) == carried
        elif percent is not None:
            restated = self._q(percent) == rate
        else:
            restated = True
        if carried > ZERO and restated:
            row.bill_discount_percent = rate
            row.bill_discount_amount = carried
            row.bill_discount_source = "inherited"
            return inherited
        resolved = resolve_bill_discount(
            taxable=taxable,
            percent=percent,
            amount=amount,
        )
        row.bill_discount_percent = resolved.percent
        row.bill_discount_amount = resolved.amount
        row.bill_discount_source = (
            None if percent is None and amount is None else "typed"
        )
        return apportion(resolved.amount, taxables)

    @stamps_tax_rules(SalesInvoiceLine, "sales_invoice_id")
    def _replace_lines(
        self,
        row: SalesInvoice,
        line_specs: list[dict[str, object]],
        *,
        bill_percent: Decimal | None,
        bill_amount: Decimal | None,
        freight_amount: Decimal | None = None,
        firm_id: UUID,
        invoice_date: date,
        business_profile_id: UUID | None,
        actor_id: UUID,
        entered_rates: Mapping[UUID, tuple[Decimal, Decimal]] | None = None,
    ) -> dict[str, Decimal]:
        """Write the bill's lines, priced, discounted and taxed.

        ``entered_rates`` names, per source line, the GST-inclusive rate a
        person typed and the pre-tax rate it derived to; a line still billed
        at that pre-tax rate keeps the typed one beside it (backlog 64 row 4).
        """
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
            # Either unit field names the unit the line is typed in; one that
            # contradicts the line being billed is refused, not dropped
            # (D-PRC-44).
            invoice_uom_id = unit_of_a_line_billing_a_document(
                self._session,
                line_number=index,
                order_uom_id=_optional_uuid(spec.get("order_uom_id")),
                invoice_uom_id=_optional_uuid(spec.get("invoice_uom_id")),
                source_uom_id=source_uom_id,
                source_label=(
                    f"{self._source_document_number(spec, source_line)} line "
                    f"{self._source_line_number(source_line)}"
                ),
            )
            if invoice_uom_id is not None and source_uom_id is None:
                # The line billed names no unit, so it is counted in the
                # product's stock unit: a unit typed against it is converted
                # into that, never taken as the same thing.
                source_uom_id = stock_unit_of(
                    self._session.get(Product, self._product_id(source_line))
                )
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
            # In the source line's unit, which is what the cap below and
            # every later reader counts in: by the rule for the pair, else
            # through the product's stock unit, so 24 PIECE bill a note of
            # 2 BOX -- and 25 are more than was shipped -- with only the
            # box-to-piece rule a firm writes. What was typed is kept beside
            # it, and the line is priced from that: 7 PIECE are 0.5833 of a
            # box at four places and 700.00, not 699.96 (D-PRC-37).
            typed = self._uom.continued_quantity(
                product_id=self._product_id(source_line),
                quantity=requested_quantity,
                from_uom_id=invoice_uom_id,
                to_uom_id=source_uom_id,
                on_date=invoice_date,
                firm_scope=firm_id,
                left=source_quantity - already_invoiced,
            )
            invoice_quantity = typed.quantity
            if typed.entered is not None:
                conversion_factor = typed.stored_factor
            # No request can lift this cap: a body flag the caller set was all
            # it took to bill 50 against a note for 5 (D-SELL-30).
            if invoice_quantity + already_invoiced > source_quantity:
                raise ValidationError(
                    "Invoice quantity exceeds the available source quantity."
                )
            # Goods that came back before any bill reached them are not the
            # customer's to be charged for (D-SELL-55).
            came_back = self._returned_before_billing(source_line.id)
            if (
                came_back > ZERO
                and invoice_quantity + already_invoiced + came_back > source_quantity
            ):
                unit = unit_named(self._session, source_uom_id)
                left = max(source_quantity - already_invoiced - came_back, ZERO)
                raise ValidationError(
                    f"Line {index}: {plain_quantity(came_back)}{unit} of the "
                    f"{plain_quantity(source_quantity)}{unit} delivered came "
                    f"back before being billed, so {plain_quantity(left)}{unit} "
                    "is left to bill."
                )
            unit_price = self._invoice_unit_price(spec=spec, source_line=source_line)
            typed_price = None if spec.get("unit_price") is None else unit_price
            if typed_price is not None:
                # Typed for the unit the line was typed in; the row keeps
                # the price of one of the source line's unit, so 100.00 a
                # piece is stored as 1,200.00 a box.
                unit_price = self._q(typed.price_per_source_unit(typed_price))
            charges_amount = self._q(Decimal(str(spec.get("charges_amount", ZERO))))
            # Worth what was typed: seven pieces at a piece's price.
            gross_amount = self._q(
                typed.worth(typed_price=typed_price, source_price=unit_price)
            )
            if (
                typed.entered is not None
                and typed_price is None
                and already_invoiced > ZERO
                and invoice_quantity + already_invoiced == source_quantity
            ):
                # The part that completes the source line takes what the
                # earlier parts left of its worth, so the bills of a note
                # add up to the note to the paisa however a box divides.
                gross_amount = self._completing_worth(
                    firm_id=firm_id,
                    source_line_id=source_line.id,
                    whole=source_quantity * unit_price,
                    price=unit_price,
                    otherwise=gross_amount,
                )
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
                unit_price=unit_price,
                already_invoiced=already_invoiced,
            )
            free_quantity = self._invoice_free_quantity(
                spec=spec,
                source_line=source_line,
                invoice_quantity=invoice_quantity,
                source_quantity=source_quantity,
                already_invoiced=already_invoiced,
                firm_id=firm_id,
            )
            if invoice_quantity <= ZERO and free_quantity <= ZERO:
                # Judged here rather than on the request, because only the
                # source line says whether a line of nothing charged is a gift
                # (D-SELL-53: a bill of quantity 0 was stored, and could never
                # be approved).
                stated_free = self._already_invoiced_free(
                    firm_id=firm_id, source_document_line_id=source_line.id
                )
                if spec.get("free_quantity") is None and stated_free > ZERO:
                    # A gift line another bill has already stated (D-PRC-69).
                    unit = unit_named(self._session, source_uom_id)
                    raise ValidationError(
                        f"Line {index}: the free goods of "
                        f"{self._source_document_number(spec, source_line)} line "
                        f"{self._source_line_number(source_line)} are already "
                        f"stated on another bill "
                        f"({plain_quantity(stated_free)}{unit} free), so nothing "
                        "is left for this line to state. Leave the line off "
                        "the bill."
                    )
                raise ValidationError(
                    f"Line {index} bills a quantity of 0 and supplies nothing "
                    "free. Type a quantity, or leave the line off the bill."
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
                    entered_quantity=typed.entered,
                    source_uom_id=source_uom_id,
                    typed_uom_id=None if typed.entered is None else invoice_uom_id,
                    unit_price=unit_price,
                    charges_amount=charges_amount,
                    gross_amount=gross_amount,
                    free_quantity=free_quantity,
                    discount=line_discount,
                )
            )

        # Promotional stock is given, never sold at a price (BUY-1).
        assert_not_sold_at_a_price(
            self._session,
            firm_id,
            [(item.source_line.product_id, item.unit_price) for item in priced],
        )
        # The bill discount is split across the lines here, between pricing
        # them and taxing them. It has to reach a taxable value to reduce any
        # tax. `header_discount_amount` on a purchase order was subtracted
        # after tax, so tax was paid on money never charged, until D-BUY-19
        # moved it onto the lines too.
        taxables = [
            self._q(item.gross_amount - item.discount.amount) for item in priced
        ]
        shares = self._bill_discount_shares(
            row,
            percent=bill_percent,
            amount=bill_amount,
            taxables=taxables,
            inherited=[
                min(
                    continued_share(
                        self._q(
                            getattr(item.source_line, "bill_discount_amount", ZERO)
                            or ZERO
                        ),
                        before=item.already_invoiced,
                        part=item.invoice_quantity,
                        whole=item.source_quantity,
                    ),
                    taxable,
                )
                for item, taxable in zip(priced, taxables, strict=True)
            ],
        )
        # Costed once for the whole invoice rather than per line: the ledger
        # is read by note and product, and a line-by-line query would ask the
        # same question of the same note repeatedly.
        dispatch_costs = self._dispatch_costs(
            {
                item.source_line.delivery_note_id
                for item in priced
                if item.source_type == SalesInvoiceSourceType.DELIVERY_NOTE.value
                and hasattr(item.source_line, "delivery_note_id")
            }
        )
        if freight_amount is None:
            freight_amount = self._inherited_freight(priced)
        freight = self._freight_shares(row, freight=freight_amount, taxables=taxables)

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
            freight_share = freight[position]
            cost_amount = self._line_cost(
                source_line=priced_source,
                source_type=source_type,
                invoice_quantity=invoice_quantity,
                source_quantity=source_quantity,
                costs=dispatch_costs,
            )
            discount_amount = self._q(line_discount.amount + bill_share)
            line_tax = self._resolve_tax(
                document_id=row.id,
                line_number=index,
                shipping_address_id=row.shipping_address_id,
                invoice_date=invoice_date,
                firm_id=firm_id,
                business_profile_id=business_profile_id,
                customer_id=row.customer_id,
                branch_id=row.branch_id,
                warehouse_id=_optional_uuid(spec.get("warehouse_id")),
                product_id=self._product_id(priced_source),
                tax_profile_id=_optional_uuid(spec.get("tax_profile_id")),
                # Taxed on what the line is worth, which for a line typed
                # in another unit is not its stored quantity times its
                # price (D-PRC-37).
                invoice_value=self._line_net_amount(
                    quantity=Decimal("1"),
                    unit_price=gross_amount,
                    discount_amount=discount_amount,
                    charges_amount=charges_amount,
                    freight_amount=freight_share,
                ),
                actor_id=actor_id,
            )
            tax_amount = line_tax.total
            # Freight is billed, not only taxed: the line's share of it is in
            # what the line is worth, exactly as it is in what it was taxed on
            # (D-SELL-37).
            net_amount = self._q(
                gross_amount
                - discount_amount
                + charges_amount
                + freight_share
                + tax_amount
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
                hsn_sac=self._billed_hsn(self._product_id(priced_source)),
                description=self._source_description(priced_source),
                delivered_quantity=source_quantity,
                already_invoiced_quantity=already_invoiced,
                current_invoice_quantity=invoice_quantity,
                free_quantity=free_quantity,
                unit_price=unit_price,
                entered_rate=self._entered_rate(
                    entered_rates, priced_source.id, unit_price
                ),
                discount_percent=line_discount.percent,
                discount_source=line_discount.source,
                discount_amount=line_discount.amount,
                bill_discount_amount=bill_share,
                freight_amount=freight_share,
                cost_amount=cost_amount,
                charges_amount=charges_amount,
                gross_amount=gross_amount,
                tax_profile_id=line_tax.profile_id,
                tax_amount=tax_amount,
                net_amount=net_amount,
                packaging_type_id=spec.get("packaging_type_id"),
                # The unit the quantity is stored in: the line billed.
                order_uom_id=source_uom_id or spec.get("order_uom_id"),
                # The unit it was typed in, whichever field named it.
                invoice_uom_id=spec.get("invoice_uom_id") or item.typed_uom_id,
                conversion_factor=conversion_factor,
                entered_quantity=item.entered_quantity,
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
            # subtotal is the taxable base: gross less discount plus the line's
            # share of the freight, before tax and before charges. Line charges
            # used to be folded in here, which made this module's subtotal mean
            # something different from every other document's; they are carried
            # separately and added to grand_total. Freight was left out, so a
            # bill taxed the delivery and never billed it (D-SELL-37).
            totals["subtotal"] += self._q(
                gross_amount - discount_amount + freight_share
            )
            totals["line_charges_total"] += charges_amount
            totals["tax_total"] += tax_amount
        return {key: self._q(value) for key, value in totals.items()}

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
        the sum is not rounding the parts, and three bills of four pieces of
        a box of twelve at 1,000.00 were 333.33 three times. Only where
        every earlier part was billed at the source line's own price --
        one that typed another price made its own bargain, and this part is
        then simply worth what it bills (``otherwise``).
        """
        earlier = self._session.execute(
            select(SalesInvoiceLine.unit_price, SalesInvoiceLine.gross_amount)
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.firm_id == firm_id,
                SalesInvoice.is_deleted.is_(False),
                SalesInvoice.status != SalesInvoiceStatus.CANCELLED.value,
                SalesInvoiceLine.is_deleted.is_(False),
                SalesInvoiceLine.source_document_line_id == source_line_id,
            )
        ).all()
        if any(self._q(Decimal(str(was))) != price for was, _ in earlier):
            return otherwise
        left = quantize_ledger(whole) - sum(
            (quantize_ledger(Decimal(str(gross))) for _, gross in earlier), ZERO
        )
        return self._q(left) if left > ZERO else otherwise

    @staticmethod
    def _entered_rate(
        entered_rates: Mapping[UUID, tuple[Decimal, Decimal]] | None,
        source_line_id: UUID,
        unit_price: Decimal,
    ) -> Decimal | None:
        """Return the inclusive rate typed for a line, if it still applies.

        Only while the line bills at the pre-tax rate it was derived to: a
        rate changed since makes the typed figure a statement about another
        price.
        """
        if not entered_rates:
            return None
        kept = entered_rates.get(source_line_id)
        if kept is None or kept[1] != unit_price:
            return None
        return kept[0]

    def _billed_rate_at(
        self,
        value: Decimal,
        *,
        invoice_date: date,
        firm_id: UUID,
        actor_id: UUID,
        business_profile_id: UUID | None,
        customer_id: UUID,
        branch_id: UUID,
        warehouse_id: UUID,
        product_id: UUID,
        tax_profile_id: UUID | None,
        shipping_address_id: UUID | None,
    ) -> Decimal:
        """Return the tax billed on a line of this value, as a fraction."""
        return self._resolve_tax(
            invoice_date=invoice_date,
            firm_id=firm_id,
            actor_id=actor_id,
            business_profile_id=business_profile_id,
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            tax_profile_id=tax_profile_id,
            invoice_value=value,
            shipping_address_id=shipping_address_id,
        ).billed_rate

    def _typed_rates_before_tax(
        self,
        data: SalesInvoiceCreate,
        *,
        branch_id: UUID,
        warehouse_id: UUID,
        firm_id: UUID,
        actor_id: UUID,
        typed: dict[int, PreTaxLine],
    ) -> SalesInvoiceCreate:
        """Read each rate typed with GST in it back to its pre-tax rate.

        Backlog 64 row 4. Only a rate the bill states is read so: a line that
        types none takes the product's price, which is before tax, exactly as
        it always has. The tax asked about is the one the line will be
        charged -- same buyer, branch, ship-to, product and date -- through
        ``TaxRuleService.simulate``, which never commits. ``typed`` collects
        each line's figures by its line number for the lines written later.
        """
        customer_id = data.customer_id
        if customer_id is None:
            return data
        ship_to = self._ship_to(
            data.shipping_address_id, customer_id=customer_id, source_rows=[]
        )
        lines: list[SalesInvoiceLineWrite] = []
        for line in data.lines:
            product_id = line.product_id
            if line.unit_price is None or product_id is None:
                lines.append(line)
                continue
            derived = derive_pre_tax(
                quantity=line.current_invoice_quantity,
                entered_rate=line.unit_price,
                discount_percent=line.discount_percent,
                discount_amount=line.discount_amount,
                rate_at=partial(
                    self._billed_rate_at,
                    invoice_date=data.invoice_date,
                    firm_id=firm_id,
                    actor_id=actor_id,
                    business_profile_id=data.business_profile_id,
                    customer_id=customer_id,
                    branch_id=branch_id,
                    warehouse_id=line.warehouse_id or warehouse_id,
                    product_id=product_id,
                    tax_profile_id=line.tax_profile_id,
                    shipping_address_id=ship_to,
                ),
            )
            typed[line.line_number] = derived
            update: dict[str, object] = {"unit_price": derived.unit_price}
            if derived.discount_amount is not None:
                update["discount_amount"] = derived.discount_amount
            lines.append(line.model_copy(update=update))
        return data.model_copy(update={"lines": lines})

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
        self,
        data: SalesInvoiceCreate,
        firm_id: UUID,
        *,
        own_notes: frozenset[UUID] = frozenset(),
    ) -> tuple[dict[str, UUID], list[dict[str, object]], list[dict[str, object]]]:
        """Read the documents a bill names, and the header they agree on.

        ``own_notes`` are the delivery notes this bill raised for itself (the
        firm leaves that stage to the service): each is approved and waiting,
        and the bill's approval is what dispatches it (D-SELL-13). Every other
        note -- a person's included, even with the stage now off -- must have
        shipped its goods before it is billed (D-SELL-3, D-CFG-16).
        """
        if any(item.serial_ids for item in data.lines):
            # Left over only on a line billing a note already dispatched --
            # the chain moves them onto the note it raises. Taking them here
            # would record units the bill never moved.
            raise ValidationError(
                "Serial numbers are picked on the delivery note that ships the "
                "goods; this bill names a note that has already been dispatched."
            )
        if any(item.batches for item in data.lines):
            # The same for batches (backlog 79): a note somebody typed chose
            # its batches itself.
            raise ValidationError(
                "Batches are chosen on the delivery note that ships the goods; "
                "this bill names a note that has already been dispatched."
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
                if not (
                    note.id in own_notes
                    and note.status == DeliveryNoteStatus.APPROVED.value
                ):
                    require_dispatched_note(note, "billed")
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
            # Compared with the first note that names one, not only the
            # first note: a first note naming nobody let two different
            # salesmen through (SEL-1).
            for field in ("salesman_id", "territory_id", "route_id"):
                named = _optional_uuid(source.get(field))
                if header.get(field) is None and named is not None:
                    header[field] = named
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

    def _delete_children(
        self, invoice_id: UUID, *, attachments: bool, notes: bool
    ) -> None:
        """Clear the child rows an edit rebuilds.

        The lines, sources and accounting events always; the attachments and
        the notes only where the edit sent them, because an edit that leaves
        them out leaves them alone (D-SELL-79).
        """
        self._session.query(SalesInvoiceAccountingEvent).filter(
            SalesInvoiceAccountingEvent.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceLine).filter(
            SalesInvoiceLine.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        self._session.query(SalesInvoiceSource).filter(
            SalesInvoiceSource.sales_invoice_id == invoice_id
        ).delete(synchronize_session=False)
        if attachments:
            self._session.query(SalesInvoiceAttachment).filter(
                SalesInvoiceAttachment.sales_invoice_id == invoice_id
            ).delete(synchronize_session=False)
        if notes:
            self._session.query(SalesInvoiceNote).filter(
                SalesInvoiceNote.sales_invoice_id == invoice_id
            ).delete(synchronize_session=False)

    @staticmethod
    def _due_date(
        customer: Customer | None, invoice_date: date, *, days: int | None = None
    ) -> date | None:
        """Return when payment falls due, from the order's terms or the customer's.

        A customer carries `payment_terms_days` and every traced invoice
        carried `due_date = NULL`, because nothing put the two together. The
        caller's own date always wins -- this only fills the gap. ``days`` are
        the terms of the orders the bill continues (backlog 67 row 4), which
        outrank the customer's: the deal was struck on the order. No days of
        credit leaves the date blank, as it always has.
        """
        if days is None:
            days = customer.payment_terms_days if customer is not None else None
        if not days:
            return None
        return invoice_date + timedelta(days=int(days))

    def _order_terms(
        self, source_rows: list[dict[str, object]]
    ) -> tuple[str | None, int | None]:
        """Return the payment terms of the orders behind the notes a bill bills.

        A bill continues its orders, so it inherits the terms they were agreed
        on rather than re-reading the customer (backlog 67 row 4). Several
        orders on one bill fall due at the earliest of their terms -- the
        stricter promise is the one the customer made -- and the words are
        the first order's that has any.
        """
        note_ids = [
            note_id
            for item in source_rows
            if item["source_document_type"]
            == SalesInvoiceSourceType.DELIVERY_NOTE.value
            and (note_id := _optional_uuid(item["source_document_id"])) is not None
        ]
        if not note_ids:
            return None, None
        rows = self._session.execute(
            select(SalesOrder.payment_terms, SalesOrder.payment_terms_days)
            .join(DeliveryNote, DeliveryNote.sales_order_id == SalesOrder.id)
            .where(DeliveryNote.id.in_(note_ids))
            .order_by(SalesOrder.order_date.asc(), SalesOrder.order_number.asc())
        ).all()
        words = next((text for text, _ in rows if text), None)
        days = [int(value) for _, value in rows if value is not None]
        return words, (min(days) if days else None)

    def _ship_to(
        self,
        requested: UUID | None,
        *,
        customer_id: UUID,
        source_rows: list[dict[str, object]],
    ) -> UUID | None:
        """Return where a bill's goods went (backlog 67 row 3).

        The address named, checked as the buyer's own; else the ship-to of the
        delivery notes billed when they agree -- a bill continues them and
        inherits what they said; else the customer's default shipping address.
        Notes that went to different addresses leave the bill to the default
        unless the person names one, since a bill prints one ship-to.
        """
        if requested is not None:
            return resolve_ship_to(
                self._session, customer_id=customer_id, address_id=requested
            )
        note_ids = [
            note_id
            for item in source_rows
            if item["source_document_type"]
            == SalesInvoiceSourceType.DELIVERY_NOTE.value
            and (note_id := _optional_uuid(item["source_document_id"])) is not None
        ]
        if note_ids:
            inherited = set(
                self._session.scalars(
                    select(DeliveryNote.shipping_address_id).where(
                        DeliveryNote.id.in_(note_ids)
                    )
                ).all()
            )
            if len(inherited) == 1 and None not in inherited:
                return inherited.pop()
        return resolve_ship_to(self._session, customer_id=customer_id, address_id=None)

    def _place_of_supply(
        self, customer: Customer | None, *, shipping_address_id: UUID | None = None
    ) -> str | None:
        """Return the state the supply is made in, as the invoice prints it.

        Copied onto the invoice rather than read through the customer at print
        time: it decides CGST + SGST against IGST, and a customer who moves must
        not change the tax treatment of an invoice already issued.

        It is the state the tax was charged by -- the buyer's GSTIN, else the
        billing address -- named with its code, ``Karnataka (29)``, from the
        same resolver that picks IGST. It used to print the billing address's
        state text, so a registered buyer whose GSTIN is in another state got
        IGST under a place of supply naming the seller's own state (D-CMP-15).
        """
        if customer is None:
            return None
        return self._tax.place_of_supply(
            customer.id, shipping_address_id=shipping_address_id
        )

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
        product_id: UUID | None,
        tax_profile_id: UUID | None,
        invoice_value: Decimal,
        document_id: UUID | None = None,
        line_number: int | None = None,
        shipping_address_id: UUID | None = None,
    ) -> _LineTax:
        """Work out the line's tax, and keep everything that decided it.

        ``product_id`` is None for a charge on the bill (SG-4), which has no
        product to take a tax group from: it is taxed by the profile it
        names, and not at all where it names none.

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
            product = (
                self._session.get(Product, product_id)
                if product_id is not None
                else None
            )
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
            # The supply's own nature, not just the document's name: a buyer in
            # another state is charged IGST (D-CMP-1).
            transaction_type=self._tax.outward_transaction_type(
                "SALES_INVOICE",
                firm_id=firm_id,
                branch_id=branch_id,
                customer_id=customer_id,
                shipping_address_id=shipping_address_id,
            ),
            transaction_date=invoice_date,
            business_profile_id=business_profile_id,
            tax_profile_id=tax_profile_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            product_id=product_id,
            invoice_value=invoice_value,
            additional_context={
                "source": "sales_invoice",
                "document_type": "SALES_INVOICE",
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
            billed_rate=billed_rate(response),
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
        page: int = 1,
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

        ``page`` reads further back, ``limit`` at a time, so a client can reach
        every note still waiting rather than the newest fifty (D-SELL-18).
        """
        documents: list[BillableDocument] = []
        offset = (page - 1) * limit

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
        # What came back of each delivery line before any bill charged for
        # it: returned goods are not left to bill (D-SELL-55).
        from app.sales_return.models import SalesReturn, SalesReturnLine

        came_back = (
            select(
                SalesReturnLine.source_document_line_id.label("line_id"),
                func.coalesce(func.sum(SalesReturnLine.unbilled_quantity), ZERO).label(
                    "taken"
                ),
            )
            .join(SalesReturn, SalesReturn.id == SalesReturnLine.sales_return_id)
            .where(
                SalesReturn.firm_id == firm_scope,
                SalesReturn.is_deleted.is_(False),
                SalesReturn.status.in_(("COMPLETED", "CLOSED")),
                SalesReturnLine.is_deleted.is_(False),
                SalesReturnLine.source_document_type == "DELIVERY_NOTE",
                SalesReturnLine.unbilled_quantity > ZERO,
            )
            .group_by(SalesReturnLine.source_document_line_id)
            .subquery()
        )
        open_notes = (
            select(DeliveryNoteLine.delivery_note_id)
            .outerjoin(invoiced, invoiced.c.line_id == DeliveryNoteLine.id)
            .outerjoin(came_back, came_back.c.line_id == DeliveryNoteLine.id)
            .where(
                DeliveryNoteLine.is_deleted.is_(False),
                or_(
                    DeliveryNoteLine.current_delivery_quantity
                    - func.coalesce(invoiced.c.taken, ZERO)
                    - func.coalesce(came_back.c.taken, ZERO)
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
                # The goods left, not merely the status: a note closed without
                # dispatching was offered here (D-SELL-4).
                goods_have_left_clause(),
                DeliveryNote.id.in_(open_notes),
            )
            .order_by(
                DeliveryNote.delivery_date.desc(),
                DeliveryNote.delivery_note_number.desc(),
            )
            .offset(offset)
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
                        warehouse_id=item.warehouse_id,
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
                    sales_order_number=note.sales_order_reference or "",
                    salesman_id=note.salesman_id,
                    territory_id=note.territory_id,
                    route_id=note.route_id,
                )
            )

        documents.extend(
            self._billable_orders(firm_scope=firm_scope, limit=limit, offset=offset)
        )
        self._name_billable(documents)
        return documents

    def _name_billable(self, documents: list[BillableDocument]) -> None:
        """Name the branch, salesman, territory and route of every document.

        One read per kind for the whole page rather than per document. A route
        profile has no name of its own; the territory it extends carries it.
        """
        branches = branch_names(self._session, (row.branch_id for row in documents))
        people = salesman_names(self._session, (row.salesman_id for row in documents))
        territories = territory_names(
            self._session, (row.territory_id for row in documents)
        )
        route_ids = {row.route_id for row in documents if row.route_id is not None}
        routes: dict[UUID, str] = {}
        if route_ids:
            routes = {
                profile_id: name
                for profile_id, name in self._session.execute(
                    select(TerritoryRouteProfile.id, SalesTerritoryNode.name)
                    .join(
                        SalesTerritoryNode,
                        TerritoryRouteProfile.territory_id == SalesTerritoryNode.id,
                    )
                    .where(TerritoryRouteProfile.id.in_(route_ids))
                ).all()
            }
        for row in documents:
            if row.branch_id is not None:
                row.branch_name = branches.get(row.branch_id, "")
            if row.salesman_id is not None:
                row.salesman_name = people.get(row.salesman_id, "")
            if row.territory_id is not None:
                row.territory_name = territories.get(row.territory_id, "")
            if row.route_id is not None:
                row.route_name = routes.get(row.route_id, "")

    def _billable_orders(
        self, *, firm_scope: UUID, limit: int, offset: int = 0
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
            .order_by(SalesOrder.order_date.desc(), SalesOrder.order_number.desc())
            .offset(offset)
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
                        warehouse_id=item.warehouse_id or order.warehouse_id,
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
                    sales_order_number=order.order_number,
                    salesman_id=order.salesman_id,
                    territory_id=order.territory_id,
                    route_id=order.route_id,
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
        warehouse_id: UUID | None = None,
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
        # Less what came back before billing: returned goods are not left
        # to bill (D-SELL-55).
        remaining = self._q(
            source_quantity - already - self._returned_before_billing(line_id)
        )
        # And less the free goods that came back, so the bill is offered
        # what the customer still holds (D-PRC-61).
        free_quantity = max(
            self._q(free_quantity - self._free_returned_off_the_note(line_id)), ZERO
        )
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
            track_serial=self._tracks_serial(product_id),
            warehouse_id=warehouse_id,
        )

    def _tracks_serial(self, product_id: UUID | None) -> bool:
        """Say whether a product's units each carry a serial number."""
        if product_id is None:
            return False
        product = self._session.get(Product, product_id)
        return bool(product is not None and product.track_serial)

    def _customer_name(self, customer_id: UUID | None) -> str:
        """Name the customer so a picker is not a list of UUIDs."""
        if customer_id is None:
            return ""
        customer = self._session.get(Customer, customer_id)
        return "" if customer is None else (customer.display_name or customer.name)

    def _returned_before_billing(self, source_document_line_id: UUID) -> Decimal:
        """Return what came back of a delivery line before any bill charged it.

        A completed sales return takes its goods first from the part of the
        note line nobody was billed for, and records it on its own line; that
        quantity is no longer the customer's to be charged (D-SELL-55).
        """
        # Imported here: the return module imports this one's models.
        from app.sales_return.billing import returned_unbilled

        return self._q(
            returned_unbilled(self._session, [source_document_line_id]).get(
                source_document_line_id, ZERO
            )
        )

    def _free_returned_off_the_note(self, source_document_line_id: UUID) -> Decimal:
        """Return the free goods completed returns brought back off a note line.

        In the note line's unit, as a return line states them. Nothing for a
        line no return names -- an order line among them.
        """
        # Imported here: the return module imports this one's models.
        from app.sales_return.billing import free_returned_off_notes

        return self._q(
            free_returned_off_notes(self._session, [source_document_line_id]).get(
                source_document_line_id, ZERO
            )
        )

    def _refuse_billing_returned_goods(self, row: SalesInvoice) -> None:
        """Refuse to approve a bill for goods that came back while it waited.

        A draft has charged nothing, so a return completed against its note
        in the meantime took its goods off what was left to bill. Approving
        the draft unchanged would charge the customer for goods the firm has
        back on its shelf (D-SELL-55).
        """
        from app.sales_return.billing import note_line_billing

        lines = self._session.scalars(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == row.id,
                SalesInvoiceLine.source_document_type
                == SalesInvoiceSourceType.DELIVERY_NOTE.value,
                SalesInvoiceLine.is_deleted.is_(False),
            )
        ).all()
        positions = note_line_billing(
            self._session,
            {line.source_document_line_id for line in lines},
            exclude_invoice_id=row.id,
        )
        for line in lines:
            position = positions.get(line.source_document_line_id)
            if position is None or position.returned_unbilled <= ZERO:
                continue
            if self._q(line.current_invoice_quantity) > position.left_to_bill:
                unit = unit_named(self._session, line.order_uom_id)
                raise ValidationError(
                    f"{row.invoice_number} line {line.line_number}: "
                    f"{plain_quantity(position.returned_unbilled)}{unit} of the "
                    f"{plain_quantity(position.delivered)}{unit} delivered came "
                    "back before being billed, so "
                    f"{plain_quantity(position.left_to_bill)}{unit} is left "
                    "to bill. Change the bill to what the customer kept."
                )
        self._refuse_stating_free_goods_not_held(row, lines)

    def _refuse_stating_free_goods_not_held(
        self, row: SalesInvoice, lines: Sequence[SalesInvoiceLine]
    ) -> None:
        """Refuse to approve a bill stating free goods the customer no longer holds.

        The free figure is asked again at approval the way the charged
        quantity is (D-PRC-69): a draft saved before free goods came back off
        its note was approved still stating them, "0 + 2 free" where one was
        held. What may be stated is what the note line gave free, less what
        completed returns brought back off the note, less what other bills
        that charged the customer already state.
        """
        from app.sales_return.billing import free_returned_off_notes

        free_lines = [line for line in lines if self._q(line.free_quantity) > ZERO]
        if not free_lines:
            return
        note_line_ids = {line.source_document_line_id for line in free_lines}
        given = {
            line_id: self._q(quantity or ZERO)
            for line_id, quantity in self._session.execute(
                select(DeliveryNoteLine.id, DeliveryNoteLine.free_quantity).where(
                    DeliveryNoteLine.id.in_(note_line_ids)
                )
            ).all()
        }
        back = free_returned_off_notes(self._session, note_line_ids)
        stated = {
            line_id: self._q(quantity or ZERO)
            for line_id, quantity in self._session.execute(
                select(
                    SalesInvoiceLine.source_document_line_id,
                    func.coalesce(func.sum(SalesInvoiceLine.free_quantity), ZERO),
                )
                .join(
                    SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id
                )
                .where(
                    SalesInvoice.firm_id == row.firm_id,
                    SalesInvoice.id != row.id,
                    SalesInvoice.is_deleted.is_(False),
                    SalesInvoice.status.in_(
                        (
                            SalesInvoiceStatus.APPROVED.value,
                            SalesInvoiceStatus.CLOSED.value,
                        )
                    ),
                    SalesInvoiceLine.is_deleted.is_(False),
                    SalesInvoiceLine.source_document_type
                    == SalesInvoiceSourceType.DELIVERY_NOTE.value,
                    SalesInvoiceLine.source_document_line_id.in_(note_line_ids),
                )
                .group_by(SalesInvoiceLine.source_document_line_id)
            ).all()
        }
        for line in free_lines:
            source_id = line.source_document_line_id
            if source_id not in given:
                continue
            sent = given[source_id]
            came_back = self._q(back.get(source_id, ZERO))
            elsewhere = stated.get(source_id, ZERO)
            left = max(self._q(sent - came_back - elsewhere), ZERO)
            if self._q(line.free_quantity) <= left:
                continue
            unit = unit_named(self._session, line.order_uom_id)
            reason = (
                f"{plain_quantity(came_back)}{unit} of the "
                f"{plain_quantity(sent)}{unit} sent free came back before "
                "being billed"
                if came_back > ZERO
                else f"{plain_quantity(elsewhere)}{unit} of the "
                f"{plain_quantity(sent)}{unit} sent free are already stated "
                "on another bill"
            )
            raise ValidationError(
                f"{row.invoice_number} line {line.line_number}: {reason}, so "
                f"{plain_quantity(left)}{unit} is left to state free where "
                f"the bill states {plain_quantity(line.free_quantity)}{unit}. "
                "Change the bill to what the customer kept."
            )

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

    def _already_invoiced_free(
        self, *, firm_id: UUID, source_document_line_id: UUID
    ) -> Decimal:
        """Return the free goods other live bills already state of a line."""
        total = self._session.scalar(
            select(func.coalesce(func.sum(SalesInvoiceLine.free_quantity), ZERO))
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

    def _invoice_unit_price(
        self, *, spec: dict[str, object], source_line: object
    ) -> Decimal:
        """Return the price this line bills at.

        **Inherited from the line being billed** where the caller said
        nothing, for the same reason the discount and the free goods are: an
        invoice states the deal that was struck, and re-deciding the price one
        document later is how an agreement gets quietly rewritten.

        Silence and zero are different answers. Zero is goods given away;
        silence is "whatever was agreed". They used to be the same value,
        because the field defaulted to zero -- so a caller that named a source
        line and omitted the price was handed a bill for **nothing**, with no
        refusal and no clue on the document. Every other inheritable field on
        that line already worked this way; the price was the one that did not.
        """
        asked = spec.get("unit_price")
        if asked is not None:
            return self._q(Decimal(str(asked)))
        inherited = getattr(source_line, "unit_price", None)
        return self._q(Decimal(str(inherited or ZERO)))

    def _invoice_free_quantity(
        self,
        *,
        spec: dict[str, object],
        source_line: SourceLine,
        invoice_quantity: Decimal,
        source_quantity: Decimal,
        already_invoiced: Decimal,
        firm_id: UUID,
    ) -> Decimal:
        """Return how much this line supplies free.

        Inherited from the document being billed rather than typed again, and
        pro-rated by the share being billed: half an order invoiced carries
        half the free goods it was promised. An explicit figure wins, and an
        explicit zero refuses the inheritance.

        In whole units, as a note ships them (`continued_free_goods`): a part
        bill states what its share has earned and the earlier bills did not
        already state, and the bill that completes the line states the rest
        -- never a fraction of a gift, and never the same unit twice
        (D-PRC-4).

        Refused above what the source line offered, because an invoice states
        what was supplied and the goods left on somebody else's document. A
        bill claiming free goods nobody dispatched is a bill the warehouse
        cannot reconcile.
        """
        offered = self._q(
            Decimal(str(getattr(source_line, "free_quantity", ZERO) or ZERO))
        )
        # Less the free goods that came back off the note: the charged
        # quantity is netted the same way, and a bill that said "0 + 2 free"
        # after one of the two had come back stated goods the customer no
        # longer held (D-PRC-61).
        offered = max(
            self._q(offered - self._free_returned_off_the_note(source_line.id)),
            ZERO,
        )
        # And less what other live bills of the line already state: two part
        # bills of one note each restated its whole free line, "0 + 2 free"
        # on both for 2 given (D-PRC-69).
        stated = self._already_invoiced_free(
            firm_id=firm_id, source_document_line_id=source_line.id
        )
        left = max(self._q(offered - stated), ZERO)
        asked = spec.get("free_quantity")
        if asked is None:
            if offered <= ZERO:
                return ZERO
            if source_quantity <= ZERO:
                # The source line charged for nothing, so there is no share to
                # pro-rate by: what it supplied free is the whole of what it
                # supplied. Returning zero here dropped the gift off the bill
                # entirely while the goods had already been dispatched. It is
                # stated once, on the first bill that names the line; a later
                # bill has nothing of it left to state.
                return left
            return self._q(
                continued_free_goods(
                    offered,
                    before=already_invoiced,
                    part=invoice_quantity,
                    whole=source_quantity,
                    already=stated,
                )
            )
        claimed = self._q(Decimal(str(asked)))
        if claimed > offered:
            raise ValidationError(
                "Free quantity exceeds what the source document supplied free."
            )
        if claimed > left:
            unit = unit_named(self._session, self._source_uom_id(source_line))
            raise ValidationError(
                "Free quantity exceeds what the source document supplied free: "
                f"{self._source_document_number(spec, source_line)} line "
                f"{self._source_line_number(source_line)} gave "
                f"{plain_quantity(offered)}{unit} free and other bills already "
                f"state {plain_quantity(stated)}{unit}, so "
                f"{plain_quantity(left)}{unit} is left to state."
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
        unit_price: Decimal,
        already_invoiced: Decimal,
    ) -> LineDiscount:
        """Return the discount for one invoice line.

        What the line itself says wins. Where it says nothing, the discount is
        **inherited from the document being billed** rather than re-read from
        the customer: a price agreed on an order in March is not rewritten by
        an edit to the customer master in August. It is the same reasoning that
        stops this module re-deriving territory and salesman.

        At the source line's own price the bill takes **its slice of that
        line's amount** (`continued_share`), between where the earlier bills
        stopped (``already_invoiced``) and where this one stops, so the part
        bills of a line sum to its discount exactly and the bill that
        completes it takes what the rounding left -- as a note does of its
        order line (D-PRC-22). Billed at another price, the source line's
        rate is inherited as itself.
        """
        percent = spec.get("discount_percent")
        amount = spec.get("discount_amount")
        inherited = False
        if percent is None and amount is None:
            inherited_percent = getattr(source_line, "discount_percent", None)
            agreed = self._q(
                Decimal(str(getattr(source_line, "discount_amount", None) or ZERO))
            )
            same_price = unit_price == self._q(
                Decimal(str(getattr(source_line, "unit_price", None) or ZERO))
            )
            if agreed > ZERO and source_quantity > ZERO and same_price:
                amount = min(
                    continued_share(
                        agreed,
                        before=already_invoiced,
                        part=invoice_quantity,
                        whole=source_quantity,
                    ),
                    gross,
                )
                inherited = True
            elif inherited_percent:
                percent = inherited_percent
                inherited = True
            elif agreed > ZERO and source_quantity > ZERO:
                amount = self._q(agreed * invoice_quantity / source_quantity)
                inherited = True
        resolved = resolve_line_discount(
            gross=gross,
            percent=None if percent is None else Decimal(str(percent)),
            amount=None if amount is None else Decimal(str(amount)),
        )
        # Said so, so the approver's discount limit judges only what the bill
        # itself typed (backlog 64 row 3).
        return replace(resolved, source="inherited") if inherited else resolved

    def _line_cost(
        self,
        *,
        source_line: SourceLine,
        source_type: str,
        invoice_quantity: Decimal,
        source_quantity: Decimal,
        costs: dict[tuple[UUID, UUID], Decimal],
    ) -> Decimal | None:
        """Return what the goods on this line cost, or None where nothing says.

        **None is not zero.** An invoice raised straight off a sales order has
        no dispatch behind it, so nothing moved and nothing was costed; zero
        would say the goods were free, and a margin rule reading one as the
        other pays commission on the whole sale price.

        Pro-rated by the share being billed, the way the free goods and the
        discount already are: a note dispatching ten and an invoice billing
        four take four tenths of what the dispatch cost.

        Args:
            source_line: The delivery note line being billed.
            source_type: What kind of document that is.
            invoice_quantity: How much of it this bill takes.
            source_quantity: How much the note carried.
            costs: What each note and product's dispatch cost.

        Returns:
            The cost attributable to this line, or None where it is unknown.

        """
        if source_type != SalesInvoiceSourceType.DELIVERY_NOTE.value:
            return None
        note_id = getattr(source_line, "delivery_note_id", None)
        product_id = getattr(source_line, "product_id", None)
        if note_id is None or product_id is None:
            return None
        total = costs.get((note_id, product_id))
        if total is None:
            return None
        if source_quantity <= ZERO:
            # Nothing was dispatched on this line, so none of the movement's
            # cost belongs to it -- a gift-only line is the case.
            return ZERO
        share = self._q(invoice_quantity) / self._q(source_quantity)
        return self._q(total * share)

    def _dispatch_costs(self, note_ids: set[UUID]) -> dict[tuple[UUID, UUID], Decimal]:
        """Return what each delivery note's dispatch cost, by note and product.

        Read off the stock ledger, which is where the moving average that
        actually left the warehouse is recorded -- the same source every
        forward posting in this repo values a stock leg from. Nothing else
        knows it: the note carries what was charged, not what it cost.

        Keyed on the note **and the product** rather than the note line,
        because the ledger records a movement of goods and not a line of
        paperwork. A note with two lines of one product is one movement, and
        its cost is split back across them by quantity.

        Args:
            note_ids: The delivery notes to cost.

        Returns:
            Total dispatch cost per (note, product). Absent where nothing was
            costed, which the caller must read as "unknown" and not as zero.

        """
        if not note_ids:
            return {}
        numbers = {
            number: note_id
            for note_id, number in self._session.execute(
                select(DeliveryNote.id, DeliveryNote.delivery_note_number).where(
                    DeliveryNote.id.in_(note_ids)
                )
            ).all()
        }
        if not numbers:
            return {}
        costs: dict[tuple[UUID, UUID], Decimal] = {}
        rows = self._session.execute(
            select(
                StockLedgerEntry.reference_number,
                StockLedgerEntry.product_id,
                StockLedgerEntry.total_cost,
            ).where(
                StockLedgerEntry.reference_type == "DELIVERY_NOTE",
                StockLedgerEntry.reference_number.in_(numbers),
                StockLedgerEntry.transaction_type == "DISPATCH",
                StockLedgerEntry.total_cost.is_not(None),
                StockLedgerEntry.is_deleted.is_(False),
            )
        ).all()
        for number, product_id, total in rows:
            note_id = numbers.get(number)
            if note_id is None:  # pragma: no cover - the filter guarantees it
                continue
            key = (note_id, product_id)
            costs[key] = costs.get(key, ZERO) + self._q(total)
        return costs

    def _line_net_amount(
        self,
        *,
        quantity: Decimal,
        unit_price: Decimal,
        discount_amount: Decimal,
        charges_amount: Decimal,
        freight_amount: Decimal = ZERO,
    ) -> Decimal:
        """Return what this line is taxed on.

        Freight has a parameter of its own rather than riding on
        `charges_amount`: that is a charge somebody put on the line, and this
        is the line's share of a charge on the whole document. Folding one
        into the other would leave neither figure recoverable.
        """
        return self._q(
            quantity * unit_price - discount_amount + charges_amount + freight_amount
        )

    def _assert_named_route_fits(
        self,
        route_id: UUID | None,
        *,
        firm_id: UUID,
        customer_id: UUID,
        territory_id: UUID | None,
        on_date: date,
    ) -> None:
        """Check a route the **caller** named, and only that one.

        A route inherited from the order or the note is left as it came:
        the bill is a continuation of that document, and re-judging its
        round on the bill's date would refuse an invoice for a sale made
        while the round was still running. What somebody typed on the bill
        itself is judged on the bill's date (D-TER-9).
        """
        if route_id is None:
            return
        validate_named_route(
            self._session,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            route_id=route_id,
            on_date=on_date,
        )

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

    def _duplicate_warnings(self, rows: Sequence[SalesInvoice]) -> dict[UUID, str]:
        """Answer `_duplicate_warning` for a page of invoices in one query."""
        numbered = {
            row.id: (row.firm_id, row.customer_id, row.customer_invoice_number.strip())
            for row in rows
            if row.customer_invoice_number and row.customer_invoice_number.strip()
        }
        if not numbered:
            return {}
        # A page is at most MAX_PAGE_SIZE rows, so the numbers fit one read.
        holders: dict[tuple[UUID, UUID, str], set[UUID]] = defaultdict(set)
        for found_id, firm_id, customer_id, number in self._session.execute(
            select(
                SalesInvoice.id,
                SalesInvoice.firm_id,
                SalesInvoice.customer_id,
                SalesInvoice.customer_invoice_number,
            ).where(
                SalesInvoice.firm_id.in_({key[0] for key in numbered.values()}),
                SalesInvoice.customer_invoice_number.in_(
                    {key[2] for key in numbered.values()}
                ),
                SalesInvoice.is_deleted.is_(False),
            )
        ):
            holders[(firm_id, customer_id, number)].add(found_id)
        return {
            row_id: "A sales invoice with this customer invoice number already exists."
            for row_id, key in numbered.items()
            if holders.get(key, set()) - {row_id}
        }

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
    ) -> date | None:
        """Cancel the journal an approved invoice wrote, if it wrote one.

        Found by `scripts/verify_sample_data.py`, which compares what customers
        owe against the receivable control account: cancelling an approved
        invoice moved the first and not the second.

        Returns:
            The date the reversal was posted on, so the customer's statement
            row can carry the same one; None when nothing had posted.

        """
        entry_id = self._session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.firm_id == firm_scope,
                JournalEntry.source_module == "sales_invoice",
                JournalEntry.source_id == row.id,
                JournalEntry.status == JournalStatus.POSTED.value,
                # A reversal carries its original's source, so without this the
                # lookup can find a mirror and reverse the reversal.
                JournalEntry.reversal_of_id.is_(None),
                JournalEntry.is_deleted.is_(False),
            )
        )
        if entry_id is None:
            # Nothing posted, so there is nothing to take back -- a firm that
            # approved invoices before posting existed is in this state.
            return None
        reversal = JournalEntryEngine(self._session).reverse_entry(
            entry_id,
            firm_id=firm_scope,
            reference_number=f"{row.invoice_number}-REV",
            actor_id=actor_id,
        )
        return reversal.journal_date

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
        details: dict[str, object] | None = None,
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
                    **(details or {}),
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

    def _products_named(self, lines: list[SalesInvoiceLine]) -> dict[UUID, Product]:
        """Return the products a document's lines name, keyed by id.

        One query for the whole document. Soft-deleted products are included
        deliberately: a line names what was sold, and a product retired since
        still has to be nameable on the bill that sold it.
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

    def _own_note_picks_for(
        self,
        rows: Sequence[SalesInvoice],
        lines: dict[UUID, list[SalesInvoiceLine]],
        products: dict[UUID, Product],
    ) -> dict[UUID, list[PickedSerial]]:
        """Return the units each serial-tracked line's own note ships.

        Keyed by note line id, and only for a draft whose lines bill a note
        the bill raised for itself -- the one case where the bill, not a
        note somebody typed, names the units (D-SELL-33). Read for the whole
        page: one query for the notes the drafts raised, one for the picks.
        """
        drafts = [
            row.id for row in rows if row.status == SalesInvoiceStatus.DRAFT.value
        ]
        if not drafts:
            return {}
        own: dict[UUID, set[UUID]] = defaultdict(set)
        for chunk in chunks(drafts):
            for note_id, invoice_id in self._session.execute(
                select(DeliveryNote.id, DeliveryNote.raised_by_sales_invoice_id).where(
                    DeliveryNote.raised_by_sales_invoice_id.in_(chunk),
                    DeliveryNote.is_deleted.is_(False),
                )
            ):
                own[invoice_id].add(note_id)
        if not own:
            return {}
        line_ids = [
            item.source_document_line_id
            for invoice_id, notes in own.items()
            for item in lines.get(invoice_id, [])
            if item.source_document_id in notes
            and bool(getattr(products.get(item.product_id), "track_serial", False))
        ]
        if not line_ids:
            return {}
        picked = SerialTrailService(self._session).picked_serials(line_ids)
        return {line_id: picked.get(line_id, []) for line_id in line_ids}

    def _line_response(
        self,
        row: SalesInvoiceLine,
        taxes: list[SalesInvoiceLineTax] | None = None,
        product: Product | None = None,
        *,
        serials: list[PickedSerial] | None = None,
        batches: list[DeliveryNoteBatchPick] | None = None,
    ) -> SalesInvoiceLineResponse:
        return SalesInvoiceLineResponse(
            id=row.id,
            tax_rule_code=row.tax_rule_code,
            tax_rule_version=row.tax_rule_version,
            sales_invoice_id=row.sales_invoice_id,
            line_number=row.line_number,
            source_document_type=SalesInvoiceSourceType(row.source_document_type),
            source_document_id=row.source_document_id,
            source_document_number=row.source_document_number,
            source_document_line_id=row.source_document_line_id,
            source_document_line_number=row.source_document_line_number,
            product_id=row.product_id,
            product_code=getattr(product, "code", None),
            product_name=getattr(product, "name", None),
            description=row.description,
            delivered_quantity=row.delivered_quantity,
            already_invoiced_quantity=row.already_invoiced_quantity,
            current_invoice_quantity=row.current_invoice_quantity,
            unit_price=row.unit_price,
            entered_rate=row.entered_rate,
            discount_percent=row.discount_percent,
            free_quantity=row.free_quantity,
            discount_amount=row.discount_amount,
            bill_discount_amount=row.bill_discount_amount,
            freight_amount=row.freight_amount,
            charges_amount=row.charges_amount,
            gross_amount=row.gross_amount,
            tax_profile_id=row.tax_profile_id,
            tax_amount=row.tax_amount,
            net_amount=row.net_amount,
            packaging_type_id=row.packaging_type_id,
            order_uom_id=row.order_uom_id,
            invoice_uom_id=row.invoice_uom_id,
            conversion_factor=row.conversion_factor,
            entered_quantity=row.entered_quantity,
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
            picks_serials=serials is not None,
            serials=serials or [],
            batches=batches or [],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
