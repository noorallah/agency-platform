"""A list page costs the same number of statements at 3 rows as at 12.

Every document list used to build each row's full response one row at a time
-- a sales invoice was about ten queries (sources, lines, taxes, attachments,
notes, accounting events, the duplicate check, names), so a 50-row page was
about 500 (backlog 56 C, step 3, ``docs/PERFORMANCE_AT_VOLUME.md``). Each now
reads every child table once for the page.

Each case seeds a firm's documents straight into the tables -- children and
the masters they name included -- then calls the list route function and
counts the statements SQLAlchemy sends. The count at twelve rows may exceed
the count at three by at most one. A second check proves the response did not
change shape: every row of the page equals the same document built alone,
which is how the detail endpoint builds it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.business.models import BusinessProfile
from app.common.scope import ResolvedFirmScope
from app.contra.api.router import list_contra_vouchers
from app.contra.models import ContraVoucher
from app.contra.services import ContraVoucherService
from app.core.enums import TokenType
from app.core.pagination import PaginationParams
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.credit_note.api.router import list_credit_notes
from app.credit_note.models import CreditNote, CreditNoteLine
from app.credit_note.services import CreditNoteService
from app.customers.models import Customer
from app.debit_note.api.router import list_debit_notes
from app.debit_note.models import DebitNote, DebitNoteLine
from app.debit_note.services import DebitNoteService
from app.delivery_note.api.router import list_delivery_notes
from app.delivery_note.models import (
    DeliveryNote,
    DeliveryNoteAttachment,
    DeliveryNoteLine,
    DeliveryNoteNote,
)
from app.delivery_note.services import DeliveryNoteService
from app.finance.api.router import get_journal_entry, list_journal_entries
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.goods_receipt.api.router import list_goods_receipts
from app.goods_receipt.models import (
    GoodsReceipt,
    GoodsReceiptAttachment,
    GoodsReceiptLine,
    GoodsReceiptNote,
)
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.api.router import (
    list_inventory,
    list_ledger,
    list_opening_stock,
    list_transactions,
)
from app.inventory.models import (
    InventoryRecord,
    InventoryTransaction,
    OpeningStockBatch,
    OpeningStockLine,
    StockLedgerEntry,
)
from app.inventory.services import InventoryService
from app.party_adjustments.api.router import list_party_adjustments
from app.party_adjustments.models import PartyAdjustment, PartyAdjustmentAllocation
from app.party_adjustments.services import PartyAdjustmentService
from app.products.models import Product
from app.purchase.api.router import list_purchase_orders
from app.purchase.models import (
    PurchaseAttachment,
    PurchaseDeliverySchedule,
    PurchaseNote,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.purchase.services import PurchaseService
from app.purchase_invoice.api.router import list_purchase_invoices
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceAccountingEvent,
    PurchaseInvoiceAttachment,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
    PurchaseInvoiceNote,
    PurchaseInvoiceSource,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.api.router import list_purchase_returns
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnAccountingEvent,
    PurchaseReturnLine,
    PurchaseReturnNote,
    PurchaseReturnSource,
)
from app.purchase_return.services import PurchaseReturnService
from app.quotation.api.router import list_quotations
from app.quotation.models import (
    SalesQuotation,
    SalesQuotationLine,
    SalesQuotationNote,
)
from app.quotation.services import QuotationService
from app.sales_invoice.api.router import list_sales_invoices
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceAccountingEvent,
    SalesInvoiceAttachment,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
    SalesInvoiceNote,
    SalesInvoiceSource,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.api.router import list_sales_orders
from app.sales_order.models import (
    SalesOrder,
    SalesOrderAttachment,
    SalesOrderLine,
    SalesOrderNote,
)
from app.sales_order.services import SalesOrderService
from app.sales_return.api.router import list_sales_returns
from app.sales_return.models import (
    SalesReturn,
    SalesReturnLine,
    SalesReturnNote,
    SalesReturnSource,
)
from app.sales_return.services import SalesReturnService
from app.settlements.api.router import _to_response, list_payments, list_receipts
from app.settlements.models import Settlement, SettlementAllocation
from app.settlements.services import PaymentService, ReceiptService
from app.vendors.models import Vendor
from tests.unit.test_document_summaries_in_sql import _add, _session

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class _World:
    """The masters every seeded document names."""

    firm: UUID
    customers: list[UUID]
    vendors: list[UUID]
    products: list[UUID]
    branch: UUID
    warehouse: UUID
    account: UUID


def _world(session: Session) -> _World:
    """Seed one firm's customers, suppliers, products and places."""
    firm = uuid.uuid4()
    customers = [uuid.uuid4() for _ in range(3)]
    vendors = [uuid.uuid4() for _ in range(3)]
    products = [uuid.uuid4() for _ in range(4)]
    for number, customer_id in enumerate(customers):
        _add(
            session,
            Customer,
            id=customer_id,
            firm_id=firm,
            code=f"C{number}",
            name=f"Customer {number} Ltd",
            display_name="" if number == 2 else f"Customer {number}",
        )
    for number, vendor_id in enumerate(vendors):
        _add(
            session,
            Vendor,
            id=vendor_id,
            firm_id=firm,
            code=f"V{number}",
            name=f"Vendor {number} Ltd",
            display_name=f"Vendor {number}",
        )
    for number, product_id in enumerate(products):
        _add(
            session,
            Product,
            id=product_id,
            firm_id=firm,
            code=f"P{number}",
            name=f"Product {number}",
            track_serial=False,
        )
    branch = uuid.uuid4()
    warehouse = uuid.uuid4()
    _add(session, Branch, id=branch, firm_id=firm, code="BR", name="Main")
    _add(
        session,
        Warehouse,
        id=warehouse,
        firm_id=firm,
        branch_id=branch,
        code="WH",
        name="Store",
    )
    account = uuid.uuid4()
    _add(session, LedgerAccount, id=account, firm_id=firm, code="1000", name="Cash")
    return _World(firm, customers, vendors, products, branch, warehouse, account)


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    """Build the scope a list handler receives once authorized."""
    user_id = uuid.uuid4()
    principal = Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


@contextmanager
def _counting(session: Session) -> Iterator[list[str]]:
    """Collect every statement the session's engine executes."""
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401
        """Keep the statement text."""
        seen.append(args[2])

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


Seed = Callable[[Session, _World, int], None]
ListPage = Callable[[Session, _World], Any]
Alone = Callable[[Session, Any], Any]


@dataclass
class _Case:
    """One list endpoint: how to seed it, list it, and build a row alone."""

    seed: Seed
    page: ListPage
    alone: Alone


def _statements(case: _Case, rows: int) -> tuple[int, Session, _World, Any]:
    """Seed ``rows`` documents, list them, and count the statements."""
    session = _session()
    world = _world(session)
    case.seed(session, world, rows)
    session.commit()
    session.expunge_all()
    with _counting(session) as seen:
        result = case.page(session, world)
    assert len(result.data) == rows
    return len(seen), session, world, result


def _pick[ItemT](items: list[ItemT], index: int) -> ItemT:
    """Cycle through ``items`` so documents name different masters."""
    return items[index % len(items)]


def _line_kwargs(world: _World, index: int, number: int) -> dict[str, Any]:
    """Name a product for line ``number`` of document ``index``."""
    return {
        "line_number": number,
        "product_id": _pick(world.products, index + number),
    }


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def _seed_sales_invoices(session: Session, world: _World, rows: int) -> None:
    """Invoices with sources, two taxed lines, notes, attachments, events."""
    for index in range(rows):
        invoice = uuid.uuid4()
        _add(
            session,
            SalesInvoice,
            id=invoice,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index // 2),
            branch_id=world.branch,
            status="APPROVED" if index % 2 else "DRAFT",
            # Every other pair shares a customer's number: the warning must
            # land on both, and on nothing else.
            customer_invoice_number=f"CUST-{index // 2}" if index % 3 else None,
        )
        _add(
            session,
            SalesInvoiceSource,
            sales_invoice_id=invoice,
            firm_id=world.firm,
            source_document_type="MANUAL",
            customer_id=_pick(world.customers, index),
            branch_id=world.branch,
        )
        for number in (2, 1):
            line = uuid.uuid4()
            _add(
                session,
                SalesInvoiceLine,
                id=line,
                sales_invoice_id=invoice,
                firm_id=world.firm,
                source_document_type="MANUAL",
                **_line_kwargs(world, index, number),
            )
            for sequence in (2, 1):
                _add(
                    session,
                    SalesInvoiceLineTax,
                    sales_invoice_line_id=line,
                    firm_id=world.firm,
                    sequence=sequence,
                    component_code=f"T{sequence}",
                )
        _add(session, SalesInvoiceNote, sales_invoice_id=invoice, firm_id=world.firm)
        _add(
            session,
            SalesInvoiceAttachment,
            sales_invoice_id=invoice,
            firm_id=world.firm,
        )
        _add(
            session,
            SalesInvoiceAccountingEvent,
            sales_invoice_id=invoice,
            firm_id=world.firm,
            event_type="SALES_REVENUE",
        )


def _seed_sales_orders(session: Session, world: _World, rows: int) -> None:
    """Orders with two lines, a note and an attachment each."""
    for index in range(rows):
        order = uuid.uuid4()
        _add(
            session,
            SalesOrder,
            id=order,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            status="DRAFT",
            is_on_hold=False,
        )
        for number in (2, 1):
            _add(
                session,
                SalesOrderLine,
                sales_order_id=order,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )
        _add(session, SalesOrderNote, sales_order_id=order, firm_id=world.firm)
        _add(session, SalesOrderAttachment, sales_order_id=order, firm_id=world.firm)


def _seed_delivery_notes(session: Session, world: _World, rows: int) -> None:
    """Seed notes of two lines, some pairs flagged as duplicate dispatches."""
    order = uuid.uuid4()
    for index in range(rows):
        note = uuid.uuid4()
        _add(
            session,
            DeliveryNote,
            id=note,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            sales_order_id=order if index % 3 == 0 else uuid.uuid4(),
            delivery_date=date(2026, 1, 1 + index % 2),
            vehicle="KA01" if index % 2 else None,
            status="DRAFT",
        )
        for number in (2, 1):
            _add(
                session,
                DeliveryNoteLine,
                delivery_note_id=note,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )
        _add(session, DeliveryNoteNote, delivery_note_id=note, firm_id=world.firm)
        _add(
            session,
            DeliveryNoteAttachment,
            delivery_note_id=note,
            firm_id=world.firm,
        )


def _seed_purchase_invoices(session: Session, world: _World, rows: int) -> None:
    """Supplier bills with sources, taxed lines, notes, attachments, events."""
    for index in range(rows):
        invoice = uuid.uuid4()
        _add(
            session,
            PurchaseInvoice,
            id=invoice,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index // 2),
            status="DRAFT",
            # Pairs share a supplier and a number, so each pair warns.
            supplier_invoice_number=f"SUP-{index // 2}",
        )
        _add(
            session,
            PurchaseInvoiceSource,
            purchase_invoice_id=invoice,
            firm_id=world.firm,
            source_document_type="MANUAL",
        )
        for number in (2, 1):
            line = uuid.uuid4()
            _add(
                session,
                PurchaseInvoiceLine,
                id=line,
                purchase_invoice_id=invoice,
                firm_id=world.firm,
                source_document_type="MANUAL",
                **_line_kwargs(world, index, number),
            )
            for sequence in (2, 1):
                _add(
                    session,
                    PurchaseInvoiceLineTax,
                    purchase_invoice_line_id=line,
                    firm_id=world.firm,
                    sequence=sequence,
                )
        _add(
            session,
            PurchaseInvoiceNote,
            purchase_invoice_id=invoice,
            firm_id=world.firm,
        )
        _add(
            session,
            PurchaseInvoiceAttachment,
            purchase_invoice_id=invoice,
            firm_id=world.firm,
        )
        _add(
            session,
            PurchaseInvoiceAccountingEvent,
            purchase_invoice_id=invoice,
            firm_id=world.firm,
            event_type="PURCHASE_EXPENSE",
        )


def _seed_purchase_orders(session: Session, world: _World, rows: int) -> None:
    """Orders with two lines, delivery schedules, a note and an attachment."""
    for index in range(rows):
        order = uuid.uuid4()
        _add(
            session,
            PurchaseOrder,
            id=order,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index),
            status="DRAFT",
        )
        for number in (2, 1):
            line = uuid.uuid4()
            _add(
                session,
                PurchaseOrderLine,
                id=line,
                purchase_order_id=order,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )
            for day in (9, 3):
                _add(
                    session,
                    PurchaseDeliverySchedule,
                    firm_id=world.firm,
                    purchase_order_line_id=line,
                    delivery_date=date(2026, 2, day + number),
                    status="PENDING",
                )
        _add(session, PurchaseNote, purchase_order_id=order, firm_id=world.firm)
        _add(session, PurchaseAttachment, purchase_order_id=order, firm_id=world.firm)


def _seed_goods_receipts(session: Session, world: _World, rows: int) -> None:
    """Receipts with two lines, a note and an attachment each."""
    order = uuid.uuid4()
    for index in range(rows):
        receipt = uuid.uuid4()
        _add(
            session,
            GoodsReceipt,
            id=receipt,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index),
            purchase_order_id=order if index % 2 else uuid.uuid4(),
            receipt_date=date(2026, 1, 1),
            status="COMPLETED" if index % 2 else "DRAFT",
        )
        for number in (2, 1):
            _add(
                session,
                GoodsReceiptLine,
                goods_receipt_id=receipt,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )
        _add(
            session,
            GoodsReceiptNote,
            goods_receipt_id=receipt,
            firm_id=world.firm,
            note_type="INTERNAL",
        )
        _add(
            session,
            GoodsReceiptAttachment,
            goods_receipt_id=receipt,
            firm_id=world.firm,
        )


def _seed_sales_returns(session: Session, world: _World, rows: int) -> None:
    """Seed returns with a source, two lines and a note each."""
    for index in range(rows):
        row = uuid.uuid4()
        _add(
            session,
            SalesReturn,
            id=row,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            status="DRAFT",
        )
        _add(
            session,
            SalesReturnSource,
            sales_return_id=row,
            firm_id=world.firm,
            source_document_type="SALES_INVOICE",
        )
        for number in (2, 1):
            _add(
                session,
                SalesReturnLine,
                sales_return_id=row,
                firm_id=world.firm,
                source_document_type="SALES_INVOICE",
                **_line_kwargs(world, index, number),
            )
        _add(session, SalesReturnNote, sales_return_id=row, firm_id=world.firm)


def _seed_credit_notes(session: Session, world: _World, rows: int) -> None:
    """Credit notes against invoices, two lines each."""
    for index in range(rows):
        invoice = uuid.uuid4()
        _add(
            session,
            SalesInvoice,
            id=invoice,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            status="APPROVED",
        )
        note = uuid.uuid4()
        _add(
            session,
            CreditNote,
            id=note,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            sales_invoice_id=invoice,
            reason="RATE_DIFFERENCE",
            status="DRAFT",
        )
        for number in (2, 1):
            _add(
                session,
                CreditNoteLine,
                credit_note_id=note,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )


def _seed_debit_notes(session: Session, world: _World, rows: int) -> None:
    """Debit notes against supplier bills, two lines each."""
    for index in range(rows):
        invoice = uuid.uuid4()
        _add(
            session,
            PurchaseInvoice,
            id=invoice,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index),
            status="APPROVED",
        )
        note = uuid.uuid4()
        _add(
            session,
            DebitNote,
            id=note,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index),
            purchase_invoice_id=invoice,
            reason="PRICE_DIFFERENCE",
            status="DRAFT",
        )
        for number in (2, 1):
            _add(
                session,
                DebitNoteLine,
                debit_note_id=note,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )


def _seed_party_adjustments(session: Session, world: _World, rows: int) -> None:
    """Set-offs clearing one sales and one purchase bill each."""
    for index in range(rows):
        sale = uuid.uuid4()
        bill = uuid.uuid4()
        _add(
            session,
            SalesInvoice,
            id=sale,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            invoice_number=f"SI-{index}",
            status="APPROVED",
        )
        _add(
            session,
            PurchaseInvoice,
            id=bill,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index),
            invoice_number=f"PI-{index}",
            status="APPROVED",
        )
        adjustment = uuid.uuid4()
        _add(
            session,
            PartyAdjustment,
            id=adjustment,
            firm_id=world.firm,
            adjustment_number=f"PA-{index:03d}",
            kind="SET_OFF",
            customer_id=_pick(world.customers, index),
            vendor_id=_pick(world.vendors, index),
            amount=Decimal("10.00"),
            reason="Same business",
            status="DRAFT",
        )
        for column, bill_id in (
            ("sales_invoice_id", sale),
            ("purchase_invoice_id", bill),
        ):
            _add(
                session,
                PartyAdjustmentAllocation,
                firm_id=world.firm,
                party_adjustment_id=adjustment,
                amount=Decimal("10.00"),
                **{column: bill_id},
            )


def _seed_contra_vouchers(session: Session, world: _World, rows: int) -> None:
    """Deposits from the world's cash into one bank account."""
    bank = uuid.uuid4()
    _add(session, LedgerAccount, id=bank, firm_id=world.firm, code="1010", name="Bank")
    for index in range(rows):
        _add(
            session,
            ContraVoucher,
            firm_id=world.firm,
            voucher_number=f"CV-{index:03d}",
            voucher_date=date(2026, 4, 1),
            kind="DEPOSIT",
            from_account_id=world.account,
            to_account_id=bank,
            amount=Decimal("10.00"),
            status="POSTED",
            journal_entry_id=uuid.uuid4(),
        )


def _seed_quotations(session: Session, world: _World, rows: int) -> None:
    """Quotations with two lines and a note each."""
    for index in range(rows):
        row = uuid.uuid4()
        _add(
            session,
            SalesQuotation,
            id=row,
            firm_id=world.firm,
            customer_id=_pick(world.customers, index),
            status="DRAFT",
        )
        for number in (2, 1):
            _add(
                session,
                SalesQuotationLine,
                sales_quotation_id=row,
                firm_id=world.firm,
                **_line_kwargs(world, index, number),
            )
        _add(session, SalesQuotationNote, sales_quotation_id=row, firm_id=world.firm)


def _seed_purchase_returns(session: Session, world: _World, rows: int) -> None:
    """Seed returns with sources, lines, notes and events."""
    for index in range(rows):
        row = uuid.uuid4()
        _add(
            session,
            PurchaseReturn,
            id=row,
            firm_id=world.firm,
            vendor_id=_pick(world.vendors, index // 2),
            status="DRAFT",
            supplier_return_number=f"SR-{index // 2}" if index % 3 else None,
        )
        _add(
            session,
            PurchaseReturnSource,
            purchase_return_id=row,
            firm_id=world.firm,
            source_document_type="MANUAL",
        )
        for number in (2, 1):
            _add(
                session,
                PurchaseReturnLine,
                purchase_return_id=row,
                firm_id=world.firm,
                source_document_type="MANUAL",
                **_line_kwargs(world, index, number),
            )
        _add(session, PurchaseReturnNote, purchase_return_id=row, firm_id=world.firm)
        _add(
            session,
            PurchaseReturnAccountingEvent,
            purchase_return_id=row,
            firm_id=world.firm,
            event_type="PURCHASE_RETURN",
        )


def _seed_settlements(direction: str) -> Seed:
    """Seed receipts (or payments) each allocated against two invoices."""

    def seed(session: Session, world: _World, rows: int) -> None:
        """Seed ``rows`` settlements of ``direction``."""
        receipt = direction == "RECEIPT"
        invoice_model = SalesInvoice if receipt else PurchaseInvoice
        for index in range(rows):
            settlement = uuid.uuid4()
            _add(
                session,
                Settlement,
                id=settlement,
                firm_id=world.firm,
                direction=direction,
                customer_id=_pick(world.customers, index) if receipt else None,
                vendor_id=None if receipt else _pick(world.vendors, index),
                amount=Decimal("100"),
                method="CASH",
                ledger_account_id=world.account,
                status="POSTED",
            )
            for _ in range(2):
                invoice = uuid.uuid4()
                party = (
                    {"customer_id": _pick(world.customers, index)}
                    if receipt
                    else {
                        "vendor_id": _pick(world.vendors, index),
                        "supplier_invoice_number": uuid.uuid4().hex[:8],
                    }
                )
                _add(
                    session,
                    invoice_model,
                    id=invoice,
                    firm_id=world.firm,
                    status="APPROVED",
                    **party,
                )
                _add(
                    session,
                    SettlementAllocation,
                    firm_id=world.firm,
                    settlement_id=settlement,
                    amount=Decimal("50"),
                    **(
                        {"sales_invoice_id": invoice}
                        if receipt
                        else {"purchase_invoice_id": invoice}
                    ),
                )

    return seed


def _seed_stock(session: Session, world: _World, rows: int) -> None:
    """One stock row per product, each with one movement and its ledger row."""
    profile = uuid.uuid4()
    _add(session, BusinessProfile, id=profile, code="DIST")
    for index in range(rows):
        product = uuid.uuid4()
        _add(
            session,
            Product,
            id=product,
            firm_id=world.firm,
            code=f"S{index:02d}",
            name=f"Stock {index}",
        )
        inventory = uuid.uuid4()
        common = {
            "firm_id": world.firm,
            "branch_id": world.branch,
            "warehouse_id": world.warehouse,
            "product_id": product,
            "business_profile_id": profile if index % 2 else None,
        }
        _add(session, InventoryRecord, id=inventory, status="ACTIVE", **common)
        movement = uuid.uuid4()
        _add(
            session,
            InventoryTransaction,
            id=movement,
            inventory_id=inventory,
            transaction_type="ADJUSTMENT",
            transaction_date=date(2026, 1, 1 + index),
            **common,
        )
        _add(
            session,
            StockLedgerEntry,
            transaction_id=movement,
            inventory_id=inventory,
            transaction_type="ADJUSTMENT",
            transaction_date=date(2026, 1, 1 + index),
            **common,
        )


def _seed_opening_stock(session: Session, world: _World, rows: int) -> None:
    """Opening-stock batches of three lines, some of them in a named bay."""
    bay = uuid.uuid4()
    _add(
        session,
        WarehouseStorageNode,
        id=bay,
        warehouse_id=world.warehouse,
        code="BAY1",
        name="Bay one",
    )
    for index in range(rows):
        batch = uuid.uuid4()
        _add(
            session,
            OpeningStockBatch,
            id=batch,
            firm_id=world.firm,
            branch_id=world.branch,
            warehouse_id=world.warehouse,
            reference_number=f"OS-{index:02d}",
            status="DRAFT",
        )
        for number in (3, 1, 2):
            _add(
                session,
                OpeningStockLine,
                opening_stock_batch_id=batch,
                storage_node_id=bay if number == 2 else None,
                **_line_kwargs(world, index, number),
            )


def _seed_journals(session: Session, world: _World, rows: int) -> None:
    """Journal entries of three lines each."""
    for index in range(rows):
        entry = uuid.uuid4()
        _add(
            session,
            JournalEntry,
            id=entry,
            firm_id=world.firm,
            journal_date=date(2026, 1, 1 + index),
            status="POSTED",
        )
        for number in (3, 1, 2):
            _add(
                session,
                JournalLine,
                journal_entry_id=entry,
                ledger_account_id=world.account,
                line_number=number,
            )


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def _get[ModelT](session: Session, model: type[ModelT], row_id: UUID) -> ModelT:
    """Load one row, failing loudly if it is not there."""
    found = session.get(model, row_id)
    assert found is not None
    return found


CASES: dict[str, _Case] = {
    "sales invoices": _Case(
        _seed_sales_invoices,
        lambda s, w: list_sales_invoices(
            scope=_scope(w.firm), db=s, pagination=PaginationParams(page_size=50)
        ),
        lambda s, r: SalesInvoiceService(s).invoice_response(
            _get(s, SalesInvoice, r.id)
        ),
    ),
    "sales orders": _Case(
        _seed_sales_orders,
        lambda s, w: list_sales_orders(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: SalesOrderService(s).order_response(_get(s, SalesOrder, r.id)),
    ),
    "delivery notes": _Case(
        _seed_delivery_notes,
        lambda s, w: list_delivery_notes(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: DeliveryNoteService(s).note_response(_get(s, DeliveryNote, r.id)),
    ),
    "purchase invoices": _Case(
        _seed_purchase_invoices,
        lambda s, w: list_purchase_invoices(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: PurchaseInvoiceService(s).invoice_response(
            _get(s, PurchaseInvoice, r.id)
        ),
    ),
    "purchase orders": _Case(
        _seed_purchase_orders,
        lambda s, w: list_purchase_orders(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: PurchaseService(s).order_response(_get(s, PurchaseOrder, r.id)),
    ),
    "goods receipts": _Case(
        _seed_goods_receipts,
        lambda s, w: list_goods_receipts(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: GoodsReceiptService(s).receipt_response(
            _get(s, GoodsReceipt, r.id)
        ),
    ),
    "sales returns": _Case(
        _seed_sales_returns,
        lambda s, w: list_sales_returns(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: SalesReturnService(s).return_response(_get(s, SalesReturn, r.id)),
    ),
    "credit notes": _Case(
        _seed_credit_notes,
        lambda s, w: list_credit_notes(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: CreditNoteService(s).note_response(_get(s, CreditNote, r.id)),
    ),
    "debit notes": _Case(
        _seed_debit_notes,
        lambda s, w: list_debit_notes(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: DebitNoteService(s).note_response(_get(s, DebitNote, r.id)),
    ),
    "party adjustments": _Case(
        _seed_party_adjustments,
        lambda s, w: list_party_adjustments(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: PartyAdjustmentService(s).response(_get(s, PartyAdjustment, r.id)),
    ),
    "contra vouchers": _Case(
        _seed_contra_vouchers,
        lambda s, w: list_contra_vouchers(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: ContraVoucherService(s).response(_get(s, ContraVoucher, r.id)),
    ),
    "quotations": _Case(
        _seed_quotations,
        lambda s, w: list_quotations(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: QuotationService(s).quotation_response(
            _get(s, SalesQuotation, r.id)
        ),
    ),
    "purchase returns": _Case(
        _seed_purchase_returns,
        lambda s, w: list_purchase_returns(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: PurchaseReturnService(s).return_response(
            _get(s, PurchaseReturn, r.id)
        ),
    ),
    "receipts": _Case(
        _seed_settlements("RECEIPT"),
        lambda s, w: list_receipts(
            scope=_scope(w.firm), page=1, page_size=50, search="", db=s
        ),
        lambda s, r: _to_response(ReceiptService(s), _get(s, Settlement, r.id)),
    ),
    "payments": _Case(
        _seed_settlements("PAYMENT"),
        lambda s, w: list_payments(
            scope=_scope(w.firm), page=1, page_size=50, search="", db=s
        ),
        lambda s, r: _to_response(PaymentService(s), _get(s, Settlement, r.id)),
    ),
    "inventory": _Case(
        _seed_stock,
        lambda s, w: list_inventory(
            scope=_scope(w.firm), db=s, status_value=None, page_size=50
        ),
        lambda s, r: InventoryService(s).inventory_response(
            _get(s, InventoryRecord, r.id)
        ),
    ),
    "inventory transactions": _Case(
        _seed_stock,
        lambda s, w: list_transactions(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: InventoryService(s).transaction_response(
            _get(s, InventoryTransaction, r.id)
        ),
    ),
    "stock ledger": _Case(
        _seed_stock,
        lambda s, w: list_ledger(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: InventoryService(s).ledger_response(
            _get(s, StockLedgerEntry, r.id)
        ),
    ),
    "opening stock": _Case(
        _seed_opening_stock,
        lambda s, w: list_opening_stock(
            scope=_scope(w.firm), db=s, status_value=None, page_size=50
        ),
        lambda s, r: InventoryService(s).opening_stock_batch_response(
            _get(s, OpeningStockBatch, r.id)
        ),
    ),
    "journal entries": _Case(
        _seed_journals,
        lambda s, w: list_journal_entries(scope=_scope(w.firm), db=s, page_size=50),
        lambda s, r: get_journal_entry(
            entry_id=r.id, scope=_scope(r.firm_id), db=s
        ).data,
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_a_page_costs_the_same_at_any_length(name: str) -> None:
    """Twelve rows cost at most one statement more than three."""
    case = CASES[name]
    small, *_ = _statements(case, 3)
    large, *_ = _statements(case, 12)
    assert large <= small + 1, f"{name}: {small} statements at 3 rows, {large} at 12"


@pytest.mark.parametrize("name", list(CASES))
def test_a_page_row_is_the_document_built_alone(name: str) -> None:
    """Each row of the page equals that document's own response."""
    case = CASES[name]
    _, session, _world_, result = _statements(case, 12)
    page = [row.model_dump() for row in result.data]
    session.expunge_all()
    alone = [case.alone(session, row).model_dump() for row in result.data]
    assert page == alone
