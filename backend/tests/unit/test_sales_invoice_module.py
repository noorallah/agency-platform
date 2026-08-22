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
    SalesInvoiceSourceType,
    SalesInvoiceStatus,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
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
    """Create an approved sales order and invoice it directly."""
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

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            allow_direct_sales_order=True,
            source_documents=[
                {
                    "source_document_type": SalesInvoiceSourceType.SALES_ORDER,
                    "source_document_id": order.id,
                }
            ],
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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

    service = SalesInvoiceService(session)
    invoice = service.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 4),
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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


def _order_line_for(
    session: Session,
    *,
    firm: object,
    branch: object,
    warehouse: object,
    customer: object,
    product: object,
) -> tuple[object, object]:
    """Raise an approved-shaped sales order and return it with its line."""
    order = SalesOrderService(session).create_order(
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
    return order, line


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
    order, order_line = _order_line_for(
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
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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
    order, order_line = _order_line_for(
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
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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
    order, order_line = _order_line_for(
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
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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
    order, order_line = _order_line_for(
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
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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
    order, order_line = _order_line_for(
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
            allow_direct_sales_order=True,
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.SALES_ORDER,
                    source_document_id=order.id,
                    source_document_line_id=order_line.id,
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
