"""Drive the whole document chain against PostgreSQL and read the books.

This exists because running the chain by hand found two shipping defects that
nothing else could: document numbering resolving ``firms`` on a tenant session,
and goods receipts posting nothing at all so inventory only ever went down. Both
passed every unit test, because SQLite puts every table in one schema and the
unit suite never assembles more than one document at a time.

The firm row goes in the platform store and its data in a disposable schema,
which is the arrangement that makes the tenancy mistakes visible.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.branches.models import Branch, Warehouse
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.schemas import GoodsReceiptCreate, GoodsReceiptLineWrite
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import ProductValuation
from app.products.models import Product
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate, PurchaseOrderStatus
from app.purchase.services import PurchaseService
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.vendors.models import Vendor

ACTOR = uuid4()


@pytest.fixture
def registered_firm(engine: Engine, temp_schema: str) -> Iterator[UUID]:
    """Register a firm in the platform store whose data lives in a temp schema.

    Firm-owned code resolves ``firms`` through the platform connection, so the
    row has to be there and not in the schema holding the firm's documents —
    exactly the split that broke document numbering.
    """
    firm_id = uuid4()
    code = f"IT{uuid4().hex[:6]}".upper()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    platform = factory()
    platform.execute(text("SET search_path TO platform"))
    platform.add(
        Firm(
            id=firm_id,
            name=f"Integration Firm {code}",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
    )
    platform.commit()
    # create_all also puts a firms table in the temp schema, and the firm-owned
    # tables there carry real foreign keys to it. A migrated firm schema has no
    # such table; this row only satisfies the local constraint.
    local = sessionmaker(
        bind=engine.execution_options(schema_translate_map={None: temp_schema}),
        expire_on_commit=False,
    )()
    local.execute(text(f'SET search_path TO "{temp_schema}"'))
    local.add(
        Firm(
            id=firm_id,
            name=f"Integration Firm {code}",
            code=code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
    )
    local.commit()
    local.close()
    try:
        yield firm_id
    finally:
        platform.execute(
            text("DELETE FROM platform.firms WHERE id = :id"), {"id": firm_id}
        )
        platform.commit()
        platform.close()


def _masters(
    session: Session, firm_id: UUID
) -> tuple[Branch, Warehouse, Vendor, Customer, Product]:
    """Create the master data one document chain needs."""
    branch = Branch(
        firm_id=firm_id,
        code="HO",
        name="Head Office",
        display_name="Head Office",
        currency_code="INR",
        working_hours={},
        status="ACTIVE",
    )
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        firm_id=firm_id,
        branch_id=branch.id,
        code="MAIN",
        name="Main",
        display_name="Main",
        status="ACTIVE",
    )
    vendor = Vendor(
        firm_id=firm_id,
        code="V1",
        name="Vendor One",
        display_name="Vendor One",
        status="ACTIVE",
    )
    customer = Customer(
        firm_id=firm_id,
        code="C1",
        customer_type="RETAIL",
        name="Customer One",
        display_name="Customer One",
        currency_code="INR",
        status="ACTIVE",
    )
    product = Product(
        firm_id=firm_id,
        code="SKU1",
        name="Stock Item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add_all([warehouse, vendor, customer, product])
    session.commit()
    return branch, warehouse, vendor, customer, product


def test_order_to_cash_reaches_a_balanced_ledger(
    temp_session: Session, registered_firm: UUID
) -> None:
    """Buy ten at 100, sell four at 150, and check stock, cost and the books."""
    firm_id = registered_firm
    session = temp_session
    branch, warehouse, vendor, customer, product = _masters(session, firm_id)
    seed_finance_setup(
        session, firm_id=firm_id, year_starts_on=date(2026, 4, 1), actor_id=ACTOR
    )
    session.commit()

    purchase = PurchaseService(session)
    order = purchase.create_order(
        PurchaseOrderCreate(
            vendor_id=vendor.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            purchase_date=date(2026, 8, 4),
            status=PurchaseOrderStatus.APPROVED,
            lines=[
                {
                    "product_id": str(product.id),
                    "ordered_quantity": "10",
                    "unit_price": "100",
                }
            ],
        ),
        firm_id=firm_id,
        actor_id=ACTOR,
    )
    # The number carries the firm's own code, which lives in the platform store.
    assert order.po_number.startswith(
        f"PO-{_firm_code(session, firm_id)}-HO-2026-2027-"
    )

    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    receipts = GoodsReceiptService(session)
    receipt = receipts.create_receipt(
        GoodsReceiptCreate(
            purchase_order_id=order.id,
            receipt_date=date(2026, 8, 4),
            lines=[
                GoodsReceiptLineWrite(
                    purchase_order_line_id=po_line.id,
                    line_number=1,
                    current_receipt_quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    warehouse_id=warehouse.id,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=ACTOR,
    )
    receipts.complete_receipt(receipt.id, firm_scope=firm_id, actor_id=ACTOR)

    valuation = session.scalar(
        select(ProductValuation).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.product_id == product.id,
        )
    )
    assert valuation.quantity_on_hand == Decimal("10.0000")
    assert valuation.average_cost == Decimal("100.000000")

    orders = SalesOrderService(session)
    sale = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 5),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("150"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=ACTOR,
    )
    orders.approve_order(sale.id, firm_scope=firm_id, actor_id=ACTOR)
    so_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == sale.id)
    )

    notes = DeliveryNoteService(session)
    note = notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=sale.id,
            delivery_date=date(2026, 8, 5),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=so_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    warehouse_id=warehouse.id,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=ACTOR,
    )
    notes.approve_note(note.id, firm_scope=firm_id, actor_id=ACTOR)
    notes.dispatch_note(note.id, firm_scope=firm_id, actor_id=ACTOR)

    valuation = session.scalar(
        select(ProductValuation).where(
            ProductValuation.firm_id == firm_id,
            ProductValuation.product_id == product.id,
        )
    )
    assert valuation.quantity_on_hand == Decimal("6.0000")
    assert valuation.total_value == Decimal("600.0000")

    dn_line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    invoices = SalesInvoiceService(session)
    invoice = invoices.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 5),
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=dn_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("150"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=ACTOR,
    )
    invoices.approve_invoice(invoice.id, firm_scope=firm_id, actor_id=ACTOR)
    session.commit()

    balances = _trial_balance(session, firm_id)
    debits = sum(dr for dr, _ in balances.values())
    credits = sum(cr for _, cr in balances.values())
    assert debits == credits, f"trial balance does not balance: {balances}"

    # Received 10 at 100, issued 4: six units of stock still capitalised.
    assert balances["1200"] == (Decimal("1000.00"), Decimal("400.00"))
    # Nothing has been invoiced by the supplier, so the accrual stands in full.
    assert balances["2300"][1] == Decimal("1000.00")
    assert balances["5200"][0] == Decimal("400.00"), "cost of goods sold"
    assert balances["4000"][1] == Decimal("600.00"), "revenue at the selling price"
    assert balances["1100"][0] == invoice.grand_total.quantize(Decimal("0.01"))


def _firm_code(session: Session, firm_id: UUID) -> str:
    """Read the firm's code from the platform store."""
    return session.execute(
        text("SELECT code FROM platform.firms WHERE id = :id"), {"id": firm_id}
    ).scalar_one()


def _trial_balance(
    session: Session, firm_id: UUID
) -> dict[str, tuple[Decimal, Decimal]]:
    """Return posted debits and credits per account code."""
    rows = session.execute(
        text(
            """
            select la.code,
                   coalesce(sum(jl.debit_amount), 0),
                   coalesce(sum(jl.credit_amount), 0)
            from journal_lines jl
            join ledger_accounts la on la.id = jl.ledger_account_id
            join journal_entries je on je.id = jl.journal_entry_id
            where je.firm_id = :firm and je.status = 'POSTED'
            group by la.code
            """
        ),
        {"firm": firm_id},
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}
