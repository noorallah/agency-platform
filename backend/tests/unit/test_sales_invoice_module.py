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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
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
from app.customers.models import Customer
from app.finance.models import JournalEntry, JournalLine, JournalStatus
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.identity.system_seed import SYSTEM_PERMISSION_CODES
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
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

    outstanding = get_customer_outstanding(scope=scope, db=session)
    assert len(outstanding) == 1
    assert outstanding[0].invoice_count == 1
    assert outstanding[0].outstanding_amount > Decimal("0")


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
    assert result.status == SalesInvoiceStatus.CANCELLED
    assert (
        service.get_invoice(invoice_id, firm_scope=firm.id).cancel_reason == "duplicate"
    )


def test_subtotal_is_the_taxable_base_and_charges_land_in_grand_total() -> None:
    """subtotal excludes tax and line charges; grand_total includes charges.

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
