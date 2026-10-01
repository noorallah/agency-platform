"""The last rate a party was billed, shown beside a line (backlog 55 G6).

Every sales and purchase document's preview carries, per line, what this
customer (or this supplier) was last billed for the product: the rate, the
discount rate on that line, and the bill's number and date. Only approved
and closed bills count, the newest wins, and one statement answers the whole
document however many years of bills there are.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.sales.services.document_preview import (
    line_companions,
    purchase_line_companions,
)
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

FIRM = uuid4()
BRANCH = uuid4()


@pytest.fixture
def session() -> Iterator[Session]:
    """Yield a session on a fresh in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        yield db


def _sale(
    db: Session,
    *,
    customer_id: UUID,
    product_id: UUID,
    number: str,
    on: date,
    price: str,
    discount: str = "0",
    status: str = "APPROVED",
) -> None:
    """Record one bill to ``customer_id`` with one line for ``product_id``."""
    invoice = SalesInvoice(
        firm_id=FIRM,
        customer_id=customer_id,
        branch_id=BRANCH,
        invoice_number=number,
        invoice_date=on,
        status=status,
    )
    db.add(invoice)
    db.flush()
    db.add(
        SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=FIRM,
            line_number=1,
            source_document_type="DELIVERY_NOTE",
            source_document_id=uuid4(),
            source_document_number="DN",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=product_id,
            delivered_quantity=Decimal("1"),
            current_invoice_quantity=Decimal("1"),
            unit_price=Decimal(price),
            discount_percent=Decimal(discount),
        )
    )
    db.flush()


def _bill(
    db: Session,
    *,
    vendor_id: UUID,
    product_id: UUID,
    number: str,
    on: date,
    price: str,
    discount: str = "0",
    status: str = "APPROVED",
) -> None:
    """Record one supplier bill from ``vendor_id`` for ``product_id``."""
    invoice = PurchaseInvoice(
        firm_id=FIRM,
        vendor_id=vendor_id,
        branch_id=BRANCH,
        invoice_number=number,
        invoice_date=on,
        supplier_invoice_number=f"S-{number}",
        supplier_invoice_date=on,
        status=status,
    )
    db.add(invoice)
    db.flush()
    db.add(
        PurchaseInvoiceLine(
            purchase_invoice_id=invoice.id,
            firm_id=FIRM,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=uuid4(),
            source_document_number="GR",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=product_id,
            received_quantity=Decimal("1"),
            unit_price=Decimal(price),
            discount_percent=Decimal(discount),
        )
    )
    db.flush()


def test_the_newest_approved_bill_to_this_customer_wins(session: Session) -> None:
    """Newest by date; drafts, cancellations and other customers are ignored."""
    customer, other = uuid4(), uuid4()
    soap, oil, never = uuid4(), uuid4(), uuid4()
    _sale(
        session,
        customer_id=customer,
        product_id=soap,
        number="SI1",
        on=date(2026, 1, 5),
        price="40",
    )
    _sale(
        session,
        customer_id=customer,
        product_id=soap,
        number="SI2",
        on=date(2026, 3, 9),
        price="42.5",
        discount="5",
    )
    _sale(
        session,
        customer_id=customer,
        product_id=soap,
        number="SI3",
        on=date(2026, 4, 1),
        price="99",
        status="DRAFT",
    )
    _sale(
        session,
        customer_id=customer,
        product_id=soap,
        number="SI4",
        on=date(2026, 4, 2),
        price="98",
        status="CANCELLED",
    )
    _sale(
        session,
        customer_id=other,
        product_id=soap,
        number="SI5",
        on=date(2026, 5, 1),
        price="10",
    )
    _sale(
        session,
        customer_id=customer,
        product_id=oil,
        number="SI6",
        on=date(2026, 2, 1),
        price="120",
        status="CLOSED",
    )

    lines = line_companions(
        session,
        firm_id=FIRM,
        customer_id=customer,
        lines=[(1, soap, None), (2, oil, None), (3, never, None)],
    )

    by_number = {line.line_number: line for line in lines}
    assert by_number[1].last_price == Decimal("42.5")
    assert by_number[1].last_discount_percent == Decimal("5")
    assert by_number[1].last_invoice_number == "SI2"
    assert by_number[1].last_invoice_date == date(2026, 3, 9)
    assert by_number[2].last_price == Decimal("120")
    assert by_number[2].last_invoice_number == "SI6"
    assert by_number[3].last_price is None
    assert by_number[3].last_discount_percent is None


def test_the_last_bill_from_this_supplier_is_the_purchase_twin(
    session: Session,
) -> None:
    """A supplier's last approved bill, never another supplier's."""
    vendor, other = uuid4(), uuid4()
    rice = uuid4()
    _bill(
        session,
        vendor_id=vendor,
        product_id=rice,
        number="PI1",
        on=date(2026, 1, 1),
        price="50",
        discount="2",
    )
    _bill(
        session,
        vendor_id=vendor,
        product_id=rice,
        number="PI2",
        on=date(2026, 6, 1),
        price="55",
        status="DRAFT",
    )
    _bill(
        session,
        vendor_id=other,
        product_id=rice,
        number="PI3",
        on=date(2026, 7, 1),
        price="30",
    )

    [line] = purchase_line_companions(
        session, firm_id=FIRM, vendor_id=vendor, lines=[(1, rice, None)]
    )

    assert line.last_price == Decimal("50")
    assert line.last_discount_percent == Decimal("2")
    assert line.last_invoice_number == "PI1"


def test_one_statement_answers_the_whole_document(session: Session) -> None:
    """The read does not grow with the number of lines or of past bills."""
    customer = uuid4()
    products = [uuid4() for _ in range(6)]
    for index, product in enumerate(products):
        for month in (1, 2, 3):
            _sale(
                session,
                customer_id=customer,
                product_id=product,
                number=f"SI{index}-{month}",
                on=date(2026, month, 1),
                price=str(10 + month),
            )
    engine: Engine = session.get_bind()  # type: ignore[assignment]
    statements: list[str] = []

    def count(*args: object) -> None:
        """Count each statement sent."""
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", count)
    try:
        lines = line_companions(
            session,
            firm_id=FIRM,
            customer_id=customer,
            lines=[(n + 1, p, None) for n, p in enumerate(products)],
        )
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert [line.last_price for line in lines] == [Decimal("13")] * 6
    # One for the rates, one for the firm-wide stock.
    assert len(statements) == 2
