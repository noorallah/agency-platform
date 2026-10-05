"""The list-page summaries count and sum in SQL and answer as they always did.

Each used to load every document the firm ever raised to count them in Python
(backlog 56 C). Rows are written straight to the table with synthetic values
for every required column, so what is asserted is the summary's arithmetic and
nothing about how a document is created.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.database.base import Base
from app.core.utils.dates import utc_now
from app.delivery_note.models import DeliveryNote
from app.delivery_note.services import DeliveryNoteService
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.services import GoodsReceiptService
from app.purchase.models import PurchaseOrder
from app.purchase.services import PurchaseService
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.services import PurchaseReturnService
from app.quotation.models import SalesQuotation
from app.quotation.services import QuotationService
from app.sales_order.models import SalesOrder
from app.sales_order.services import SalesOrderService
from app.sales_return.models import SalesReturn
from app.sales_return.services import SalesReturnService


def _session() -> Session:
    """Return a session on an empty in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _add(session: Session, model: type[Any], **given: Any) -> None:  # noqa: ANN401
    """Insert one row, inventing a value for each required column not given."""
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name in given or column.nullable:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        kind = column.type
        if isinstance(kind, Boolean):
            values[column.name] = False
        elif isinstance(kind, DateTime):
            values[column.name] = utc_now()
        elif isinstance(kind, Date):
            values[column.name] = date(2026, 1, 1)
        elif isinstance(kind, Numeric):
            values[column.name] = Decimal("0")
        elif isinstance(kind, Integer):
            values[column.name] = 1
        elif isinstance(kind, String):
            values[column.name] = uuid.uuid4().hex[: kind.length or 32]
        else:
            values[column.name] = uuid.uuid4()
    values.update(given)
    session.add(model(**values))
    session.flush()


def _check(
    build: Callable[[Session], Any],
    model: type[Any],
    rows: list[tuple[str, str, bool]],
) -> Any:  # noqa: ANN401
    """Seed (status, grand_total, is_deleted) rows and summarise their firm."""
    session = _session()
    firm = uuid.uuid4()
    for status, total, deleted in rows:
        _add(
            session,
            model,
            firm_id=firm,
            status=status,
            grand_total=Decimal(total),
            is_deleted=deleted,
        )
    # Another firm's document must never reach this firm's figures.
    _add(
        session,
        model,
        firm_id=uuid.uuid4(),
        status="DRAFT",
        grand_total=Decimal("9999"),
    )
    session.commit()
    return build(session).summary(firm_scope=firm)


def test_sales_order_summary() -> None:
    """Counts by status, values summed over every live order."""
    got = _check(
        SalesOrderService,
        SalesOrder,
        [
            ("DRAFT", "100.50", False),
            ("DRAFT", "10", False),
            ("APPROVED", "200", False),
            ("CANCELLED", "5", False),
            ("CLOSED", "1", False),
            ("APPROVED", "777", True),
        ],
    )
    assert (got.total, got.draft, got.approved) == (5, 2, 1)
    assert (got.cancelled, got.closed) == (1, 1)
    assert got.total_value == Decimal("316.50")


def test_an_empty_firm_summarises_to_zeros() -> None:
    """No rows at all is zero counts and a zero value, not an error."""
    got = _check(SalesOrderService, SalesOrder, [])
    assert got.total == 0
    assert got.total_value == Decimal("0")


def test_delivery_note_summary() -> None:
    """Every status has its own figure; deleted notes are left out."""
    got = _check(
        DeliveryNoteService,
        DeliveryNote,
        [
            ("DRAFT", "1", False),
            ("APPROVED", "2", False),
            ("DISPATCHED", "4", False),
            ("DISPATCHED", "8", False),
            ("COMPLETED", "16", False),
            ("CANCELLED", "32", False),
            ("CLOSED", "64", False),
            ("CLOSED", "128", True),
        ],
    )
    assert (got.total, got.draft, got.approved, got.dispatched) == (7, 1, 1, 2)
    assert (got.completed, got.cancelled, got.closed) == (1, 1, 1)
    assert got.total_value == Decimal("127")
    assert (got.pending_orders, got.partial_orders) == (0, 0)


def test_purchase_invoice_summary() -> None:
    """Drafts are also the pending figure; all statuses sum into the value."""
    got = _check(
        PurchaseInvoiceService,
        PurchaseInvoice,
        [
            ("DRAFT", "10", False),
            ("DRAFT", "20", False),
            ("APPROVED", "30", False),
            ("CANCELLED", "40", False),
            ("CLOSED", "50", False),
            ("CLOSED", "60", True),
        ],
    )
    assert (got.total, got.draft, got.pending_invoices) == (5, 2, 2)
    assert (got.approved, got.cancelled, got.closed) == (1, 1, 1)
    assert got.total_value == Decimal("150")
    assert got.overdue_invoices == 0


def test_purchase_return_summary() -> None:
    """Counts by status, values summed over every live return."""
    got = _check(
        PurchaseReturnService,
        PurchaseReturn,
        [
            ("DRAFT", "1.25", False),
            ("APPROVED", "2", False),
            ("COMPLETED", "3", False),
            ("COMPLETED", "4", False),
            ("CANCELLED", "5", False),
            ("CLOSED", "6", False),
            ("DRAFT", "99", True),
        ],
    )
    assert (got.total, got.draft, got.approved, got.completed) == (6, 1, 1, 2)
    assert (got.cancelled, got.closed) == (1, 1)
    assert got.total_value == Decimal("21.25")


def test_sales_return_summary_leaves_cancelled_out_of_value_and_restock() -> None:
    """A cancelled return is counted but returned and restocked nothing.

    The value is what completed (and closed) returns credited; a draft or an
    approved return has credited nobody, and its stated total is the pending
    figure beside it (D-SELL-84). The sibling summaries sum every status,
    because a document total is all they mean; this one means a credit.
    """
    session = _session()
    firm = uuid.uuid4()
    for status, total, restock, deleted in [
        ("DRAFT", "10", "1", False),
        ("APPROVED", "20", "2", False),
        ("COMPLETED", "30", "3", False),
        ("CLOSED", "7", "0", False),
        ("CANCELLED", "400", "40", False),
        ("COMPLETED", "5000", "500", True),
    ]:
        _add(
            session,
            SalesReturn,
            firm_id=firm,
            status=status,
            grand_total=Decimal(total),
            total_restock_quantity=Decimal(restock),
            is_deleted=deleted,
        )
    session.commit()
    got = SalesReturnService(session).summary(firm_scope=firm)
    assert got.total_returns == 5
    assert (got.draft_returns, got.approved_returns) == (1, 1)
    assert (got.completed_returns, got.cancelled_returns) == (1, 1)
    assert got.total_return_value == Decimal("37")
    assert got.pending_return_value == Decimal("30")
    assert got.total_restock_quantity == Decimal("6")


def test_purchase_order_summary_counts_open_and_overdue() -> None:
    """Open is five statuses in one figure; overdue is a date, not a status."""
    session = _session()
    firm = uuid.uuid4()
    past, future = date(2000, 1, 1), date(2999, 1, 1)
    for status, total, due, deleted in [
        ("DRAFT", "1", past, False),
        ("SUBMITTED", "2", past, False),
        ("APPROVED", "4", future, False),
        ("ORDERED", "8", None, False),
        ("PARTIALLY_RECEIVED", "16", past, False),
        ("RECEIVED", "32", past, False),
        ("CANCELLED", "64", past, False),
        ("CLOSED", "128", past, False),
        ("SUBMITTED", "256", past, True),
    ]:
        _add(
            session,
            PurchaseOrder,
            firm_id=firm,
            status=status,
            grand_total=Decimal(total),
            expected_delivery_date=due,
            is_deleted=deleted,
        )
    session.commit()
    got = PurchaseService(session).summary(firm_scope=firm)
    assert got.total == 8
    assert (got.draft, got.open, got.cancelled, got.closed) == (1, 4, 1, 1)
    assert got.total_value == Decimal("255")
    # DRAFT, SUBMITTED and PARTIALLY_RECEIVED are past due; the rest are not.
    assert got.overdue_delivery == 3


def test_quotation_summary_counts_expiry_and_converted_value() -> None:
    """Expiry is a date counted beside the status; converted has its own value."""
    session = _session()
    firm = uuid.uuid4()
    past, future = date(2000, 1, 1), date(2999, 1, 1)
    for status, total, until, deleted in [
        ("DRAFT", "1", past, False),
        ("SENT", "2", past, False),
        ("SENT", "4", future, False),
        ("ACCEPTED", "8", past, False),
        ("DECLINED", "16", past, False),
        ("CONVERTED", "32", past, False),
        ("CONVERTED", "64", future, False),
        ("CONVERTED", "128", past, True),
    ]:
        _add(
            session,
            SalesQuotation,
            firm_id=firm,
            status=status,
            grand_total=Decimal(total),
            valid_until=until,
            is_deleted=deleted,
        )
    session.commit()
    got = QuotationService(session).summary(firm_scope=firm)
    assert got.total_quotations == 7
    assert (got.draft_quotations, got.sent_quotations) == (1, 2)
    assert (got.accepted_quotations, got.declined_quotations) == (1, 1)
    assert got.converted_quotations == 2
    # Lapsed and not yet settled: the draft, one sent, the accepted.
    assert got.expired_quotations == 3
    assert got.total_quoted_value == Decimal("127")
    assert got.total_converted_value == Decimal("96")


def test_goods_receipt_summary_counts_distinct_orders() -> None:
    """Pending and partial count purchase orders, not receipts."""
    session = _session()
    firm = uuid.uuid4()
    order_a, order_b, order_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for status, total, order, quantity, deleted in [
        ("DRAFT", "1", order_a, "0", False),
        ("DRAFT", "2", order_a, "5", False),
        ("DRAFT", "4", order_b, "0", False),
        ("COMPLETED", "8", order_b, "3", False),
        ("CANCELLED", "16", order_c, "9", False),
        ("CLOSED", "32", order_c, "0", False),
        ("DRAFT", "64", order_c, "7", True),
    ]:
        _add(
            session,
            GoodsReceipt,
            firm_id=firm,
            status=status,
            grand_total=Decimal(total),
            purchase_order_id=order,
            total_current_receipt_quantity=Decimal(quantity),
            is_deleted=deleted,
        )
    session.commit()
    got = GoodsReceiptService(session).summary(firm_scope=firm)
    assert (got.total, got.draft, got.completed) == (6, 3, 1)
    assert (got.cancelled, got.closed) == (1, 1)
    assert got.total_value == Decimal("63")
    assert got.pending_purchase_orders == 2
    assert got.partial_purchase_orders == 2
