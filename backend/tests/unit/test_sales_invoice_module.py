"""Sales invoice router and lifecycle tests.

This module previously had no test at all. Every one of its handlers called its
service with the wrong keyword arguments, and its permission codes were absent
from the seeded catalogue, so the whole API was reachable only by platform
administrators — which is why none of it was ever exercised.
"""

import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import get_args
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.pagination import PaginationParams
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import (
    CreditControlSettings,
    Customer,
    CustomerAddress,
)
from app.customers.schemas import CreditEnforcement
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.finance.models import (
    GLPosting,
    JournalEntry,
    JournalLine,
    JournalStatus,
    LedgerAccount,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.identity.system_seed import SYSTEM_PERMISSION_CODES
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import GeoCountry
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_invoice.api.router import (
    ActionReasonRequest,
    SalesInvoiceApproveScope,
    SalesInvoiceCancelScope,
    SalesInvoiceCreateScope,
    SalesInvoiceExportScope,
    SalesInvoiceImportScope,
    SalesInvoiceUpdateScope,
    SalesInvoiceViewScope,
    cancel_sales_invoice,
    get_customer_outstanding,
    get_sales_invoice_timeline,
    list_sales_invoices,
)
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine, SalesInvoiceLineTax
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceResponse,
    SalesInvoiceSourceType,
    SalesInvoiceStatus,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import (
    SalesOrder,
    SalesOrderLine,
    SalesWorkflowSettings,
)
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleWrite,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from app.uom.models import uom as _uom_models  # noqa: F401


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper.

    Routers no longer carry a private resolver; membership is validated once in
    ``app.common.scope`` against the platform store.
    """
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )


def _session_factory() -> sessionmaker[Session]:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    """Create the owning firm."""
    row = Firm(
        name="Invoice Firm",
        code="SI-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    """Create a branch for the firm."""
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _warehouse(session: Session, *, firm_id: UUID, branch_id: UUID) -> Warehouse:
    """Create a warehouse under the branch."""
    row = Warehouse(
        firm_id=firm_id,
        branch_id=branch_id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    """Create the invoiced customer."""
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("50000"),
        opening_balance=Decimal("1000"),
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID) -> Product:
    """Create a stock item to sell."""
    row = Product(
        firm_id=firm_id,
        code="SKU-001",
        name="Product SKU-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    """Build the firm scope a router handler receives once authorized."""
    user_id = uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset({"SALES_VIEW", "SALES_CREATE", "SALES_APPROVE"}),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


def _invoice_from_sales_order(
    session: Session, *, firm_id: UUID
) -> tuple[SalesInvoiceService, UUID]:
    """Dispatch a four-by-hundred order and bill what left the warehouse.

    It used to bill the order directly, which the application no longer allows
    for a firm that ships on a delivery note -- and which was how a bill could
    post revenue with no stock movement and no cost of goods sold behind it.
    """
    branch = _branch(session, firm_id=firm_id)
    warehouse = _warehouse(session, firm_id=firm_id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm_id)
    product = _product(session, firm_id=firm_id)

    orders = SalesOrderService(session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None

    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("100"),
            reference_number="ADJ-OPENING",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm_id,
        actor_id=uuid4(),
    )
    orders.approve_order(order.id, firm_scope=firm_id, actor_id=uuid4())
    notes = DeliveryNoteService(session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    notes.approve_note(note.id, firm_scope=firm_id, actor_id=uuid4())
    notes.dispatch_note(note.id, firm_scope=firm_id, actor_id=uuid4())
    note_line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert note_line is not None

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 5),
            source_documents=[
                {
                    "source_document_type": SalesInvoiceSourceType.DELIVERY_NOTE,
                    "source_document_id": note.id,
                }
            ],
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    return service, invoice.id


def test_sales_invoice_router_enforces_seeded_sales_permissions() -> None:
    """Every scope alias carries an upper-snake-case code from the catalogue.

    The router previously enforced ``sales_invoice:read``/``:write``/``:approve``,
    which are absent from ``PERMISSION_GROUPS``. An unseeded code cannot be
    attached to a role, so the module became platform-admin-only.
    """
    aliases = {
        "view": SalesInvoiceViewScope,
        "create": SalesInvoiceCreateScope,
        "update": SalesInvoiceUpdateScope,
        "approve": SalesInvoiceApproveScope,
        "cancel": SalesInvoiceCancelScope,
        "export": SalesInvoiceExportScope,
        "import": SalesInvoiceImportScope,
    }
    catalogue = set(SYSTEM_PERMISSION_CODES)
    for name, alias in aliases.items():
        assert get_args(alias)[0] is ResolvedFirmScope, name

    source = inspect.getsourcefile(list_sales_invoices)
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    assert '"sales_invoice:' not in text
    for code in (
        "SALES_VIEW",
        "SALES_CREATE",
        "SALES_UPDATE",
        "SALES_APPROVE",
        "SALES_CANCEL",
        "SALES_EXPORT",
        "SALES_IMPORT",
    ):
        assert f'firm_permission_scope("{code}")' in text
        assert code in catalogue


def test_sales_invoice_created_from_sales_order_reaches_draft() -> None:
    """A direct sales-order invoice lands in DRAFT with a generated number."""
    session = _session_factory()()
    firm = _firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)

    response = service.invoice_response(
        service.get_invoice(invoice_id, firm_scope=firm.id)
    )
    assert response.status == SalesInvoiceStatus.DRAFT
    # The firm's financial year starts 1 April, and the invoice is dated
    # 2026-08-04, so the number must carry the shared YYYY-YYYY label. This
    # module previously emitted a bare calendar year while purchase orders in
    # the same period emitted 2026-2027.
    assert response.invoice_number.startswith("SI-2026-2027-")
    assert response.grand_total == Decimal("400.0000")
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None


def test_sales_invoice_list_endpoint_returns_pagination_metadata() -> None:
    """``GET /sales-invoices`` builds a valid PaginatedResponse.

    It previously passed ``total``/``page``/``page_size`` to a model that forbids
    extra fields and requires ``pagination``, so the endpoint always failed.
    """
    session = _session_factory()()
    firm = _firm(session)
    _invoice_from_sales_order(session, firm_id=firm.id)

    result = list_sales_invoices(
        scope=_scope(firm.id),
        db=session,
        pagination=PaginationParams(),
    )
    assert result.pagination.total_records == 1
    assert result.pagination.page == 1
    assert result.pagination.total_pages == 1
    assert len(result.data) == 1


def test_sales_invoice_timeline_and_outstanding_endpoints_resolve() -> None:
    """The timeline and outstanding handlers call their service correctly.

    ``timeline`` was called with ``firm_id`` against a ``firm_scope`` parameter,
    and the outstanding report called a method name that does not exist.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)
    scope = _scope(firm.id)
    # Approval now posts to the general ledger, so the firm needs its chart of
    # accounts, an open period and its control accounts first.
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())

    timeline = get_sales_invoice_timeline(
        scope=scope,
        db=session,
        invoice_id=invoice_id,
        pagination=PaginationParams(),
    )
    assert timeline.pagination.total_records >= 1
    assert timeline.data[0].source_document_id == invoice_id

    # Wrapped in the standard envelope like every other endpoint: these six
    # returned bare payloads, which is the exception CLAUDE.md says does not
    # exist.
    outstanding = get_customer_outstanding(scope=scope, db=session)
    assert len(outstanding.data) == 1
    assert outstanding.data[0].invoice_count == 1
    assert outstanding.data[0].outstanding_amount > Decimal("0")


def test_sales_invoice_cancel_endpoint_passes_the_reason_through() -> None:
    """``cancel`` forwards its reason as a keyword, not as a positional UUID."""
    session = _session_factory()()
    firm = _firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)

    result = cancel_sales_invoice(
        scope=_scope(firm.id),
        db=session,
        invoice_id=invoice_id,
        data=ActionReasonRequest(reason="duplicate"),
    )
    # The envelope, like every other module: the record is under `data`.
    assert result.data is not None
    assert result.data.status == SalesInvoiceStatus.CANCELLED
    assert (
        service.get_invoice(invoice_id, firm_scope=firm.id).cancel_reason == "duplicate"
    )


def test_subtotal_is_the_taxable_base_and_charges_land_in_grand_total() -> None:
    """Subtotal excludes tax and line charges; grand_total includes charges.

    This module folded line charges into ``subtotal``, so the same field name
    meant a different thing here than on a sales order or delivery note.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)

    orders = SalesOrderService(session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None
    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("100"),
            reference_number="ADJ-OPENING",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=uuid4())
    notes = DeliveryNoteService(session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    notes.approve_note(note.id, firm_scope=firm.id, actor_id=uuid4())
    notes.dispatch_note(note.id, firm_scope=firm.id, actor_id=uuid4())
    note_line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert note_line is not None

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("40"),
                    charges_amount=Decimal("10"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    response = service.invoice_response(invoice)
    # gross 400 - discount 40 = 360 taxable base, charges excluded.
    assert response.subtotal == Decimal("360.0000")
    assert response.line_discount_total == Decimal("40.0000")
    # ...and the 10.00 of line charges is still collected in the grand total.
    assert response.grand_total == Decimal("370.0000")


def test_approval_posts_a_journal_and_fails_when_it_cannot() -> None:
    """Approval and its journal succeed together or not at all.

    Finance was an island: approving an invoice moved a customer balance and
    left the ledger untouched. Posting is now part of approval, and an approved
    invoice with no journal is exactly the silent gap that is not acceptable.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)

    # Without control accounts the approval is refused, not silently skipped.
    with pytest.raises(ValidationError) as unconfigured:
        service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())
    assert "ACCOUNTS_RECEIVABLE" in str(unconfigured.value)
    session.rollback()
    assert (
        service.get_invoice(invoice_id, firm_scope=firm.id).status
        == SalesInvoiceStatus.DRAFT
    ), "a refused posting must leave the invoice unapproved"

    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    approved = service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())
    assert approved.status == SalesInvoiceStatus.APPROVED.value

    entry = session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "sales_invoice",
            JournalEntry.source_id == invoice_id,
        )
    )
    assert entry is not None, "approval must leave a journal behind"
    assert entry.status == JournalStatus.POSTED.value
    lines = session.scalars(
        select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
    ).all()
    debits = sum(line.debit_amount for line in lines)
    credits = sum(line.credit_amount for line in lines)
    assert debits == credits == Decimal("400.00"), "the entry must balance"


def test_a_blocking_firm_refuses_to_approve_past_the_credit_limit() -> None:
    """Approval is where the amount lands on the customer's account.

    credit_limit was recorded on every customer and enforced nowhere. Under a
    firm that has chosen BLOCK, approving the invoice that breaches the limit
    is now refused; the invoice stays in draft rather than being posted and
    reversed.
    """
    session = _session_factory()()
    firm = _firm(session)
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)

    invoice = session.get(SalesInvoice, invoice_id)
    assert invoice is not None
    customer = session.get(Customer, invoice.customer_id)
    assert customer is not None
    # Leave barely any headroom, then choose to block.
    customer.credit_limit = Decimal("100")
    session.add(
        CreditControlSettings(
            firm_id=firm.id,
            enforcement=CreditEnforcement.BLOCK.value,
            warn_at_percent=Decimal("80"),
            block_at_percent=Decimal("100"),
        )
    )
    session.commit()

    with pytest.raises(ValidationError, match="credit limit"):
        service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())

    session.expire_all()
    assert (
        session.get(SalesInvoice, invoice_id).status == SalesInvoiceStatus.DRAFT.value
    )


def test_the_default_policy_lets_the_same_invoice_through() -> None:
    """WARN is the default, so nothing stops trading until a firm opts in."""
    session = _session_factory()()
    firm = _firm(session)
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)

    invoice = session.get(SalesInvoice, invoice_id)
    assert invoice is not None
    customer = session.get(Customer, invoice.customer_id)
    assert customer is not None
    customer.credit_limit = Decimal("100")
    session.commit()

    approved = service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())
    assert approved.status == SalesInvoiceStatus.APPROVED.value


def test_cancelling_an_approved_invoice_takes_its_journal_back() -> None:
    """Otherwise the receivable account keeps an invoice the customer does not.

    Approving posts revenue, tax and a receivable. Cancelling reduced the
    customer's balance through a credit note and left all three in the ledger,
    so the receivable control account overstated by the whole invoice from that
    moment on -- found by `scripts/verify_sample_data.py`, which compares the
    two.

    The entry is reversed rather than booked as a sales return: a mirror of
    what the invoice raised puts revenue and tax back where they came from,
    which crediting a returns account would not.
    """
    session = _session_factory()()
    firm = _firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())

    def receivable() -> Decimal:
        return Decimal(
            str(
                session.scalar(
                    select(
                        func.coalesce(
                            func.sum(GLPosting.debit_amount - GLPosting.credit_amount),
                            0,
                        )
                    )
                    .join(
                        LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id
                    )
                    .where(LedgerAccount.code == "1100")
                )
            )
        )

    owed_after_approval = receivable()
    assert owed_after_approval > Decimal("0"), "approving raises a receivable"

    service.cancel_invoice(
        invoice_id, firm_scope=firm.id, actor_id=uuid4(), reason="duplicate"
    )

    assert receivable() == Decimal("0.00"), "cancelling takes it back"
    # Both entries stay: the invoice happened, and so did taking it back.
    entries = session.scalars(
        select(JournalEntry.reference_number).where(
            JournalEntry.source_module == "sales_invoice"
        )
    ).all()
    assert len(entries) >= 1
    reversals = session.scalars(
        select(JournalEntry.reference_number).where(
            JournalEntry.reference_number.like("%-REV")
        )
    ).all()
    assert len(reversals) == 1, "one mirror entry, named after the invoice"


def _dispatched_line_for(
    session: Session,
    *,
    firm: object,
    branch: object,
    warehouse: object,
    customer: object,
    product: object,
) -> tuple[object, object]:
    """Raise an order, ship it, and return the note with its line.

    Billing an order directly is no longer how a firm on the whole chain
    raises a bill, and it was never how the goods left the warehouse.
    """
    orders = SalesOrderService(session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("100"),
            reference_number="ADJ-OPENING",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=uuid4())
    notes = DeliveryNoteService(session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    notes.approve_note(note.id, firm_scope=firm.id, actor_id=uuid4())
    notes.dispatch_note(note.id, firm_scope=firm.id, actor_id=uuid4())
    note_line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert note_line is not None
    return note, note_line


def test_the_invoice_records_when_payment_falls_due() -> None:
    """The customer carries the terms and the invoice carried NULL.

    Nothing put the two together, so every traced invoice had no due date at
    all -- and a printed bill has to say when it is payable.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    customer.payment_terms_days = 21
    session.commit()
    product = _product(session, firm_id=firm.id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    invoice = SalesInvoiceService(session).create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    assert invoice.due_date == date(2026, 8, 25), "21 days from the invoice date"


def test_a_due_date_the_caller_gives_is_not_overwritten() -> None:
    """Deriving fills the gap; it does not overrule the person raising it."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    customer.payment_terms_days = 21
    session.commit()
    product = _product(session, firm_id=firm.id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    invoice = SalesInvoiceService(session).create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            due_date=date(2026, 9, 30),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    assert invoice.due_date == date(2026, 9, 30)


def test_the_invoice_fixes_the_place_of_supply_when_it_is_raised() -> None:
    """It decides CGST + SGST against IGST, so it cannot follow the customer.

    Reading it through the customer at print time would let an address change
    rewrite the tax treatment of an invoice already issued.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    session.add(
        CustomerAddress(
            customer_id=customer.id,
            address_type="BILLING",
            address_line1="23 Market Road",
            city="Pune",
            state="Maharashtra",
            country="IN",
            postal_code="411001",
            is_default_billing=True,
        )
    )
    session.commit()
    product = _product(session, firm_id=firm.id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    assert invoice.place_of_supply == "Maharashtra"
    assert service.invoice_response(invoice).place_of_supply == "Maharashtra"

    # The customer moves. The issued invoice does not.
    address = session.scalar(
        select(CustomerAddress).where(CustomerAddress.customer_id == customer.id)
    )
    assert address is not None
    address.state = "Karnataka"
    session.commit()
    session.refresh(invoice)
    assert invoice.place_of_supply == "Maharashtra"


def _gst_profile(session: Session, *, firm: object, actor_id: UUID) -> object:
    """Return an 18% tax split into two 9% components, the way GST is charged."""
    country = GeoCountry(
        code="IN",
        name="India",
        iso2="IN",
        iso3="IND",
        phone_code="+91",
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    business_profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        created_by=actor_id,
        updated_by=actor_id,
        default_settings={},
    )
    session.add_all([country, business_profile])
    session.commit()

    framework = TaxFrameworkService(session)
    system = framework.create_system(
        TaxSystemWrite(
            country_id=country.id, code="GST", name="Goods and Services Tax"
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    components = [
        framework.create_component(
            TaxComponentWrite(
                tax_system_id=system.id,
                code=code,
                name=name,
                label=name,
                percentage="9",
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        for code, name in (("CGST", "Central GST"), ("SGST", "State GST"))
    ]
    profile = framework.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=business_profile.id,
            code="GST_18_LOCAL",
            name="GST 18 local",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "9",
                    "calculation_order": order,
                }
                for order, component in enumerate(components, start=1)
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="SALES_DEFAULT",
            name="Sales default",
            priority=50,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": profile.id,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    return profile


def test_the_line_keeps_the_tax_it_charged_component_by_component() -> None:
    """One `tax_amount` cannot be printed on a tax invoice.

    A bill has to state CGST 9% 90.00 and SGST 9% 90.00, not "180.00 of tax".
    The breakup was computed by the rule engine and discarded, surviving only
    in `tax_rule_execution_logs`, which the retention job prunes -- and rules
    are effective-dated, so asking the engine again later can answer
    differently from what the customer was billed.
    """
    session = _session_factory()()
    actor_id = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    profile = _gst_profile(session, firm=firm, actor_id=actor_id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                    tax_profile_id=profile.id,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    stored = list(
        session.scalars(
            select(SalesInvoiceLineTax).order_by(SalesInvoiceLineTax.sequence.asc())
        ).all()
    )
    assert [row.component_code for row in stored] == ["CGST", "SGST"]
    assert [row.percentage for row in stored] == [Decimal("9.0000"), Decimal("9.0000")]
    assert [row.amount for row in stored] == [Decimal("90.0000"), Decimal("90.0000")]
    assert {row.base_amount for row in stored} == {Decimal("1000.0000")}
    assert sum(row.amount for row in stored) == invoice.tax_total

    response = service.invoice_response(invoice)
    line = response.lines[0]
    assert line.tax_amount == Decimal("180.0000")
    assert [component.component_code for component in line.taxes] == ["CGST", "SGST"]
    assert line.tax_profile_id == profile.id, (
        "the line records the profile that produced the tax, not the one the "
        "caller happened to send"
    )


def test_a_line_records_the_profile_the_product_resolved() -> None:
    """A client that names no profile still gets one, and the line says which.

    `tax_profile_id` was written straight from the request body, so an invoice
    raised without naming a profile stored NULL even though the engine had
    resolved one from the product.
    """
    session = _session_factory()()
    actor_id = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    profile = _gst_profile(session, firm=firm, actor_id=actor_id)
    # A product names a tax *group*, not a version: the rate a document carries
    # is decided by its own date, so a rate change needs no product edit.
    product.tax_profile_group_code = profile.group_code
    session.commit()
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    invoice = SalesInvoiceService(session).create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    line = session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert line is not None
    assert line.tax_profile_id == profile.id


def _order_for_invoicing(
    session: Session,
    *,
    firm_id: UUID,
    branch_id: UUID,
    warehouse_id: UUID,
    customer_id: UUID,
    product_id: UUID,
    discount_percent: Decimal | None = None,
) -> tuple[SalesOrder, SalesOrderLine]:
    """Raise a four-by-hundred order and return it with its only line."""
    order = SalesOrderService(session).create_order(
        SalesOrderCreate(
            customer_id=customer_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product_id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_percent=discount_percent,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    return order, line


def _invoice_one_line(
    session: Session,
    *,
    firm_id: UUID,
    branch_id: UUID,
    customer_id: UUID,
    note: DeliveryNote,
    note_line: DeliveryNoteLine,
    quantity: Decimal = Decimal("4"),
    discount_percent: Decimal | None = None,
    bill_discount_percent: Decimal | None = None,
    bill_discount_amount: Decimal | None = None,
    free_quantity: Decimal | None = None,
) -> SalesInvoiceResponse:
    """Bill one dispatched note line, and return what the client would see.

    These cases used to bill straight off a sales order, because that was the
    shortest fixture that would produce an invoice. It was also the reason the
    delivery-note path had no coverage at all, which is how a bill charging for
    goods that had been given away survived until 2026-08-24. Billing what was
    dispatched is both what the application now requires and the path worth
    testing.
    """
    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer_id,
            branch_id=branch_id,
            invoice_date=date(2026, 8, 5),
            bill_discount_percent=bill_discount_percent,
            bill_discount_amount=bill_discount_amount,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=quantity,
                    unit_price=Decimal("100"),
                    discount_percent=discount_percent,
                    free_quantity=free_quantity,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    return service.invoice_response(invoice)


class _Billing:
    """A firm with an order standing ready to be invoiced."""

    def __init__(self, session: Session, **order_kwargs: object) -> None:
        """Build the masters and raise the order."""
        self.session = session
        self.firm = _firm(session)
        self.branch = _branch(session, firm_id=self.firm.id)
        self.warehouse = _warehouse(
            session, firm_id=self.firm.id, branch_id=self.branch.id
        )
        self.customer = _customer(session, firm_id=self.firm.id)
        self.product = _product(session, firm_id=self.firm.id)
        self._note: tuple[DeliveryNote, DeliveryNoteLine] | None = None
        self.order, self.order_line = _order_for_invoicing(
            session,
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            customer_id=self.customer.id,
            product_id=self.product.id,
            **order_kwargs,  # type: ignore[arg-type]
        )

    def ships_on_the_bill(self) -> None:
        """Leave the delivery note to the service, as a counter firm does.

        The goods still have to be there: billing now dispatches them.
        """
        InventoryService(self.session).create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                product_id=self.product.id,
                quantity=Decimal("100"),
                reference_number="ADJ-COUNTER",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 3),
            ),
            firm_scope=self.firm.id,
            actor_id=uuid4(),
        )
        self.session.add(
            SalesWorkflowSettings(
                firm_id=self.firm.id,
                quotation_stage=False,
                sales_order_stage=True,
                delivery_note_stage=False,
            )
        )
        self.session.commit()

    def dispatch(
        self,
        quantity: Decimal = Decimal("4"),
        free_quantity: Decimal = Decimal("0"),
    ) -> tuple[DeliveryNote, DeliveryNoteLine]:
        """Ship the order once, so there is something to bill."""
        if self._note is None:
            note = _dispatched_note(
                self, quantity=quantity, free_quantity=free_quantity
            )
            line = self.session.scalar(
                select(DeliveryNoteLine).where(
                    DeliveryNoteLine.delivery_note_id == note.id
                )
            )
            assert line is not None
            self._note = (note, line)
        return self._note

    def bill(
        self,
        dispatch_quantity: Decimal = Decimal("4"),
        dispatch_free: Decimal = Decimal("0"),
        **kwargs: object,
    ) -> SalesInvoiceResponse:
        """Ship the order and invoice what left."""
        note, note_line = self.dispatch(dispatch_quantity, dispatch_free)
        return _invoice_one_line(
            self.session,
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            customer_id=self.customer.id,
            note=note,
            note_line=note_line,
            **kwargs,  # type: ignore[arg-type]
        )


def test_a_percentage_discount_reaches_the_bill() -> None:
    """It was stored on the line and never applied to anything.

    The tax base and the subtotal were both computed from the discount
    *amount* alone, so a ten percent order was invoiced at full price with
    ``discount_percent`` of 10 sitting on the invoice line as a lie. This is
    the test that fails against the code as it stood.
    """
    setup = _Billing(_session_factory()())

    response = setup.bill(discount_percent=Decimal("10"))

    assert response.line_discount_total == Decimal("40.0000")
    assert response.subtotal == Decimal("360.0000")
    assert response.grand_total == Decimal("360.0000")


def test_an_invoice_inherits_the_discount_from_the_line_it_bills() -> None:
    """The bill matches what was agreed, not what the master says today.

    The customer's standing rate is deliberately not re-read here: a price
    agreed on an order in March must not be rewritten by an edit to the
    customer in August. It is the same reasoning that stops this module
    re-deriving territory and salesman.
    """
    setup = _Billing(_session_factory()(), discount_percent=Decimal("10"))
    # The customer moves to a different arrangement after the order is placed.
    setup.customer.default_discount_percent = Decimal("25")
    setup.session.commit()

    response = setup.bill()

    assert response.line_discount_total == Decimal("40.0000")
    assert response.lines[0].discount_percent == Decimal("10.0000")


def test_an_invoice_line_can_say_no_discount_at_all() -> None:
    """An explicit zero overrides what the order agreed."""
    setup = _Billing(_session_factory()(), discount_percent=Decimal("10"))

    assert setup.bill(discount_percent=Decimal("0")).grand_total == Decimal("400.0000")


def test_an_inherited_amount_is_pro_rated_across_a_partial_invoice() -> None:
    """Half the order billed carries half the discount it was given.

    A rate needs no such handling, which is why a rate is inherited as itself;
    a whole-line amount copied onto part of a line would discount more than was
    ever agreed.
    """
    setup = _Billing(_session_factory()())
    setup.order_line.discount_percent = Decimal("0")
    setup.order_line.discount_amount = Decimal("40")
    setup.session.commit()

    response = setup.bill(quantity=Decimal("2"))

    assert response.line_discount_total == Decimal("20.0000")
    assert response.grand_total == Decimal("180.0000")


def test_a_bill_discount_reduces_the_tax_the_customer_is_charged() -> None:
    """The whole point of splitting it across the lines.

    A document-level deduction subtracted after tax -- the shape
    `header_discount_amount` takes on a purchase order -- leaves the customer
    paying tax on money they were never charged. Driven through a real GST
    profile, because a fixture with no tax cannot tell the two shapes apart.
    """
    session = _session_factory()()
    actor_id = uuid4()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    profile = _gst_profile(session, firm=firm, actor_id=actor_id)
    note, note_line = _dispatched_line_for(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
    )

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            bill_discount_percent=Decimal("10"),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("250"),
                    tax_profile_id=profile.id,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    response = service.invoice_response(invoice)
    # 1,000 gross, 100 off the whole bill, so 900 taxable rather than 1,000.
    assert response.bill_discount_amount == Decimal("100.0000")
    assert response.subtotal == Decimal("900.0000")
    # 18% of 900, not of 1,000: the tax followed the value down.
    assert response.tax_total == Decimal("162.0000")
    assert response.grand_total == Decimal("1062.0000")
    assert response.lines[0].bill_discount_amount == Decimal("100.0000")
    # And the stored breakup agrees, because it is what was charged.
    stored = list(session.scalars(select(SalesInvoiceLineTax)).all())
    assert {row.base_amount for row in stored} == {Decimal("900.0000")}


def test_the_line_keeps_its_own_discount_apart_from_its_share() -> None:
    """Two different facts about the line, so two columns.

    What the salesman agreed on this line is not the same as this line's share
    of a deal struck on the whole document, and the printed bill shows them
    separately.
    """
    setup = _Billing(_session_factory()())

    response = setup.bill(
        discount_percent=Decimal("10"), bill_discount_amount=Decimal("36")
    )

    line = response.lines[0]
    assert line.discount_amount == Decimal("40.0000")
    assert line.discount_percent == Decimal("10.0000")
    assert line.bill_discount_amount == Decimal("36.0000")
    assert response.subtotal == Decimal("324.0000")


def test_a_bill_states_what_was_given_away() -> None:
    """`free_quantity` existed on three documents and not on the invoice.

    So goods could be promised, ordered and dispatched free and then not be
    stated on the document the customer actually reads. A bill showing ten
    units when eleven arrived is a bill the customer queries, and the answer
    was nowhere on it.
    """
    setup = _Billing(_session_factory()())
    setup.order_line.free_quantity = Decimal("1")
    setup.session.commit()

    # The gift has to leave the warehouse on the note before the bill can
    # state it: an invoice inherits free goods from the line it bills.
    response = setup.bill(
        dispatch_quantity=Decimal("3"),
        dispatch_free=Decimal("1"),
        quantity=Decimal("3"),
    )

    assert response.lines[0].free_quantity == Decimal("1.0000")
    assert response.total_free_quantity == Decimal("1.0000")
    # Free is free: it is outside the gross and outside the tax base. Three
    # units are charged and a fourth is given, so the gross is three.
    assert response.lines[0].gross_amount == Decimal("300.0000")
    assert response.grand_total == Decimal("300.0000")


def test_free_goods_are_pro_rated_across_a_partial_invoice() -> None:
    """Half the order billed carries half the goods it was promised free."""
    setup = _Billing(_session_factory()())
    setup.order_line.free_quantity = Decimal("2")
    setup.session.commit()

    response = setup.bill(
        dispatch_quantity=Decimal("2"),
        dispatch_free=Decimal("2"),
        quantity=Decimal("1"),
    )

    assert response.lines[0].free_quantity == Decimal("1.0000")


def test_a_bill_cannot_invent_free_goods() -> None:
    """The goods left on somebody else's document.

    A bill claiming free goods nobody dispatched is one the warehouse cannot
    reconcile, so it is refused rather than recorded.
    """
    setup = _Billing(_session_factory()())
    setup.order_line.free_quantity = Decimal("1")
    setup.session.commit()

    with pytest.raises(ValidationError, match="exceeds what the source document"):
        setup.bill(free_quantity=Decimal("5"))


def test_a_bill_can_decline_to_pass_on_free_goods() -> None:
    """An explicit zero refuses the inheritance, as everywhere else here."""
    setup = _Billing(_session_factory()())
    setup.order_line.free_quantity = Decimal("1")
    setup.session.commit()

    response = setup.bill(free_quantity=Decimal("0"))

    assert response.lines[0].free_quantity == Decimal("0")
    assert response.total_free_quantity == Decimal("0")


def _dispatched_note(
    setup: _Billing,
    quantity: Decimal = Decimal("4"),
    free_quantity: Decimal = Decimal("0"),
) -> DeliveryNote:
    """Dispatch the setup's order so there is something to bill."""
    session = setup.session
    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            product_id=setup.product.id,
            quantity=Decimal("100"),
            reference_number="ADJ-BILLABLE",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=setup.firm.id,
        actor_id=uuid4(),
    )
    orders = SalesOrderService(session)
    orders.approve_order(setup.order.id, firm_scope=setup.firm.id, actor_id=uuid4())
    notes = DeliveryNoteService(session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=setup.order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=setup.order_line.id,
                    line_number=1,
                    current_delivery_quantity=quantity,
                    free_quantity=free_quantity,
                    unit_price=Decimal("100"),
                    # Carry the deal the order struck. A delivery note resolves
                    # a silent discount from the customer's *current* rate
                    # rather than from the order line it ships, so saying
                    # nothing here would let an edit to the master rewrite a
                    # price agreed weeks earlier.
                    discount_percent=setup.order_line.discount_percent or None,
                    discount_amount=setup.order_line.discount_amount or None,
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    notes.approve_note(note.id, firm_scope=setup.firm.id, actor_id=uuid4())
    notes.dispatch_note(note.id, firm_scope=setup.firm.id, actor_id=uuid4())
    return note


def _bill_note(
    setup: _Billing, note: DeliveryNote, quantity: Decimal
) -> SalesInvoiceResponse:
    """Bill one dispatched note line."""
    service = SalesInvoiceService(setup.session)
    dn_line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert dn_line is not None
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=dn_line.id,
                    line_number=1,
                    current_invoice_quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    return service.invoice_response(invoice)


def test_a_bill_cannot_charge_for_goods_that_were_given_away() -> None:
    """What may be billed is what was charged, not what left the warehouse.

    `delivered_quantity` is `current_delivery_quantity + free_quantity`
    converted into inventory units -- right for stock, because 4 really did
    leave -- and the invoice read it as the billable quantity. So a note
    charging for 3 and giving 1 capped billing at 4, and that fourth unit was
    billable at full price. Driven against a seeded note before the fix: the
    customer was charged 195.00 plus tax for a unit they had been given.

    The units were wrong too. `invoice_quantity` is converted into the source
    line's *sales* UOM, which is what `current_delivery_quantity` holds;
    `delivered_quantity` is post-conversion inventory units, so for any
    product whose two units differ the cap was inflated by the whole
    conversion factor.
    """
    setup = _Billing(_session_factory()())
    # Three charged and one free against an order line of four: the note's own
    # guard caps charged-plus-free at what was ordered.
    note = _dispatched_note(setup, quantity=Decimal("3"), free_quantity=Decimal("1"))

    _bill_note(setup, note, Decimal("3"))

    with pytest.raises(ValidationError):
        _bill_note(setup, note, Decimal("1"))


def test_billing_a_note_in_full_carries_the_whole_gift() -> None:
    """A fraction of a free unit is not something anybody can hand over.

    The pro-rata divided by charged-plus-free, so billing all 3 of the 3
    charged units carried 3/4 of the free one and the printed bill read
    "3 + 0.75 free".
    """
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup, quantity=Decimal("3"), free_quantity=Decimal("1"))

    response = _bill_note(setup, note, Decimal("3"))

    assert response.lines[0].free_quantity == Decimal("1.0000")
    # Free is still free: outside the gross and outside the tax base.
    assert response.lines[0].gross_amount == Decimal("300.0000")


def test_a_dispatched_note_is_offered_with_what_is_left_to_bill() -> None:
    """Offer only what a document still has left to bill.

    Nothing exposed this, so a client could only offer every document and let
    the save be refused -- nine times in ten on a firm that bills promptly.
    """
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup)

    billable = SalesInvoiceService(setup.session).billable_documents(
        firm_scope=setup.firm.id
    )

    assert [item.source_document_number for item in billable] == [
        note.delivery_note_number
    ]
    line = billable[0].lines[0]
    assert line.source_quantity == Decimal("4.0000")
    assert line.already_invoiced_quantity == Decimal("0")
    assert line.remaining_quantity == Decimal("4.0000")
    assert line.unit_price == Decimal("100.0000")
    # Named, so a picker is not a list of UUIDs.
    assert billable[0].customer_name


def test_a_partly_billed_note_offers_only_the_rest() -> None:
    """The number offered is the number the save will accept."""
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup)
    service = SalesInvoiceService(setup.session)
    dn_line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert dn_line is not None
    service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=dn_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    line = service.billable_documents(firm_scope=setup.firm.id)[0].lines[0]

    assert line.already_invoiced_quantity == Decimal("1.0000")
    assert line.remaining_quantity == Decimal("3.0000")


def test_a_fully_billed_note_drops_off_the_list() -> None:
    """Offered and then refused is the experience this exists to avoid."""
    setup = _Billing(_session_factory()())
    note = _dispatched_note(setup)
    service = SalesInvoiceService(setup.session)
    dn_line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert dn_line is not None
    service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=dn_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert service.billable_documents(firm_scope=setup.firm.id) == []


def test_an_undispatched_note_is_not_billable() -> None:
    """Nothing has left the warehouse, so there is nothing to charge for."""
    setup = _Billing(_session_factory()())
    _dispatched_note(setup, quantity=Decimal("3"))
    # A second note over the remaining one, left in draft.
    notes = DeliveryNoteService(setup.session)
    notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=setup.order.id,
            delivery_date=date(2026, 8, 6),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=setup.order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    billable = SalesInvoiceService(setup.session).billable_documents(
        firm_scope=setup.firm.id
    )

    assert len(billable) == 1


def test_billable_documents_stop_at_the_firm_boundary() -> None:
    """A picker must not offer another firm's paperwork."""
    session = _session_factory()()
    setup = _Billing(session)
    _dispatched_note(setup)
    other = Firm(
        name="Other Firm",
        code="SI-OTHER",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(other)
    session.commit()

    assert SalesInvoiceService(session).billable_documents(firm_scope=other.id) == []


def test_the_limit_counts_billable_notes_not_candidates() -> None:
    """Asking for one must return one, not filter one away and return none.

    The first cut applied the limit to delivery notes and *then* dropped the
    fully billed ones, so a firm whose newest notes are all invoiced saw an
    empty list while older billable ones sat behind them. Found by asking a
    running server for one and getting nothing back.
    """
    setup = _Billing(_session_factory()())
    older = _dispatched_note(setup, quantity=Decimal("1"))
    service = SalesInvoiceService(setup.session)

    # Bill the newer note in full so only the older one is left.
    newer = DeliveryNoteService(setup.session).create_note(
        DeliveryNoteCreate(
            sales_order_id=setup.order.id,
            delivery_date=date(2026, 8, 20),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=setup.order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    notes = DeliveryNoteService(setup.session)
    notes.approve_note(newer.id, firm_scope=setup.firm.id, actor_id=uuid4())
    notes.dispatch_note(newer.id, firm_scope=setup.firm.id, actor_id=uuid4())
    newer_line = setup.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == newer.id)
    )
    assert newer_line is not None
    service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 21),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=newer.id,
                    source_document_line_id=newer_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    billable = service.billable_documents(firm_scope=setup.firm.id, limit=1)

    assert [item.source_document_number for item in billable] == [
        older.delivery_note_number
    ]


def test_an_approved_order_with_nothing_shipped_can_be_billed() -> None:
    """Offer an approved order that nothing has shipped against.

    Billing before dispatch is real -- a firm paid up front invoices the order
    -- and it is now the firm's configuration that permits it rather than a
    boolean the caller set on its own invoice. An order is offered only where
    the delivery note is left to the service, because that is the only way
    billing one dispatches anything.
    """
    setup = _Billing(_session_factory()())
    setup.ships_on_the_bill()
    SalesOrderService(setup.session).approve_order(
        setup.order.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )

    billable = SalesInvoiceService(setup.session).billable_documents(
        firm_scope=setup.firm.id
    )

    assert [item.source_document_type for item in billable] == [
        SalesInvoiceSourceType.SALES_ORDER
    ]
    assert billable[0].source_document_number == setup.order.order_number
    assert billable[0].lines[0].remaining_quantity == Decimal("4.0000")


def test_an_order_stops_being_offered_once_anything_ships() -> None:
    """The rule that stops a customer being billed twice for one set of goods.

    `_already_invoiced_quantity` is keyed on the source **line** id, and an
    order line and the delivery line raised from it are different ids -- so
    offering both would let each be billed in full and no guard would notice.
    Once anything ships, the note is the document that knows what left.
    """
    setup = _Billing(_session_factory()())
    _dispatched_note(setup)

    billable = SalesInvoiceService(setup.session).billable_documents(
        firm_scope=setup.firm.id
    )

    assert [item.source_document_type for item in billable] == [
        SalesInvoiceSourceType.DELIVERY_NOTE
    ]


def test_a_draft_order_is_not_billable() -> None:
    """Nothing has been committed, so there is nothing to charge for."""
    setup = _Billing(_session_factory()())

    assert (
        SalesInvoiceService(setup.session).billable_documents(firm_scope=setup.firm.id)
        == []
    )


def test_an_order_billed_in_full_drops_off_the_list() -> None:
    """Same rule the delivery note follows."""
    setup = _Billing(_session_factory()())
    setup.ships_on_the_bill()
    service = SalesInvoiceService(setup.session)
    SalesOrderService(setup.session).approve_order(
        setup.order.id, firm_scope=setup.firm.id, actor_id=uuid4()
    )
    service.create_invoice(
        SalesInvoiceCreate(
            customer_id=setup.customer.id,
            branch_id=setup.branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=setup.order.id,
                    source_document_line_id=setup.order_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )

    assert service.billable_documents(firm_scope=setup.firm.id) == []
