"""A deposit against a specific order, and setting it against the bill.

Two halves. The **link** records why the money arrived -- a note, not a
ring-fence: the cash is the customer's balance either way, and cancelling the
order does not make the deposit vanish. The **allocation** is the half that was
missing entirely: `ADVANCE_APPLY` has been a declared receivable transaction
type since the settlements module shipped and nothing could reach it, so a
deposit taken before the bill existed sat on the account with no way to say
which bill it settled.

The case that decides whether the allocation can be trusted: **it posts no
journal.** The receipt already debited cash and credited receivables, and the
invoice already debited receivables; applying the advance decides which invoice
the credit belongs to and moves no ledger account. A journal here would count
the money twice.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.customers.schemas import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services import CustomerService
from app.finance.models import JournalEntry
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice
from app.sales_order.models import SalesOrder
from app.sales_order.services import SalesOrderService
from app.settlements.models import Settlement
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import PaymentService, ReceiptService
from app.vendors.models import Vendor

WHEN = date(2026, 6, 10)


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Books:
    """A firm with a chart, a customer, an order and an invoice."""

    def __init__(self, session: Session) -> None:
        """Seed everything an advance needs to have somewhere to go."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Advance Firm",
            code="ADVN",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-1",
            name="Branch One",
            display_name="Branch One",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        session.add(self.branch)
        session.flush()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="WH-1",
            name="Warehouse One",
            display_name="Warehouse One",
            status="ACTIVE",
        )
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
        )
        self.other = Customer(
            firm_id=self.firm.id,
            code="C2",
            customer_type="BUSINESS",
            name="Someone Else",
            display_name="Someone Else",
            currency_code="INR",
            status="ACTIVE",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add_all([self.warehouse, self.customer, self.other, self.product])
        session.commit()
        self.order = self._order()

    def _order(self, customer: Customer | None = None) -> SalesOrder:
        """Raise an approved order for the customer."""
        order = SalesOrder(
            firm_id=self.firm.id,
            customer_id=(customer or self.customer).id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            order_number=f"SO-{uuid4().hex[:6].upper()}",
            order_date=WHEN,
            status="APPROVED",
            currency_code="INR",
        )
        self.session.add(order)
        self.session.commit()
        return order

    def invoice(self, number: str, total: str) -> SalesInvoice:
        """Bill the customer, so there is something to apply money to."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            invoice_number=number,
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal(total),
        )
        self.session.add(row)
        self.session.commit()
        # Approving an invoice posts what the customer owes. The fixture has
        # to do it too, or the balance stays at zero and applying an advance
        # is refused for a reason that has nothing to do with the advance.
        CustomerService(self.session).post_receivable_transaction(
            self.customer.id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.INVOICE,
                amount=Decimal(total),
                transaction_date=WHEN,
                reference_number=number,
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )
        return row

    def receipt(
        self,
        amount: str,
        *,
        against: SalesOrder | None = None,
        customer: Customer | None = None,
    ) -> Settlement:
        """Take money in, optionally naming the order it came in against."""
        row = ReceiptService(self.session).create(
            SettlementCreate(
                party_id=(customer or self.customer).id,
                settlement_date=WHEN,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                allocations=[],
                sales_order_id=None if against is None else against.id,
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def apply(
        self, receipt: Settlement, invoice: SalesInvoice, amount: str
    ) -> Settlement:
        """Set the money against the bill."""
        return ReceiptService(self.session).allocate(
            receipt.id,
            invoice_id=invoice.id,
            amount=Decimal(amount),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )


def test_a_receipt_records_the_order_it_came_in_against() -> None:
    """Which is what makes "what has this customer paid us for X" answerable."""
    books = _Books(_session_factory()())

    row = books.receipt("5000", against=books.order)

    assert row.sales_order_id == books.order.id


def test_an_order_reports_what_was_received_against_it() -> None:
    """Both figures: what came in, and what is left of it."""
    books = _Books(_session_factory()())
    books.receipt("5000", against=books.order)
    books.receipt("2500", against=books.order)
    # Not against the order, so it belongs to neither total.
    books.receipt("999")

    summary = SalesOrderService(books.session).advances(
        books.order.id, firm_scope=books.firm.id
    )

    assert summary.total_received == Decimal("7500.00")
    assert summary.total_unapplied == Decimal("7500.00")
    assert len(summary.receipts) == 2


def test_another_customer_s_order_cannot_be_named() -> None:
    """It would answer the question with somebody else's money."""
    books = _Books(_session_factory()())
    theirs = books._order(customer=books.other)  # noqa: SLF001

    with pytest.raises(ValidationError, match="different customer"):
        books.receipt("5000", against=theirs)


def test_a_payment_to_a_vendor_cannot_name_a_sales_order() -> None:
    """A field accepted and discarded is worse than one refused."""
    books = _Books(_session_factory()())
    vendor = Vendor(
        firm_id=books.firm.id,
        code="V1",
        name="Supplier",
        display_name="Supplier",
        status="ACTIVE",
    )
    books.session.add(vendor)
    books.session.commit()

    with pytest.raises(ValidationError, match="Only a receipt"):
        PaymentService(books.session).create(
            SettlementCreate(
                party_id=vendor.id,
                settlement_date=WHEN,
                amount=Decimal("100"),
                method=SettlementMethodEnum.BANK,
                allocations=[],
                sales_order_id=books.order.id,
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_order_from_another_firm_is_not_found() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())

    with pytest.raises(ResourceNotFoundError):
        ReceiptService(books.session).create(
            SettlementCreate(
                party_id=books.customer.id,
                settlement_date=WHEN,
                amount=Decimal("100"),
                method=SettlementMethodEnum.BANK,
                allocations=[],
                sales_order_id=uuid4(),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_applying_an_advance_clears_the_invoice() -> None:
    """The half that was missing entirely.

    `ADVANCE_APPLY` was a declared transaction type nothing could reach, so a
    deposit taken before the bill existed sat on the account with no way to
    say which bill it settled.
    """
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    invoice = books.invoice("SI-1", "3000")

    row = books.apply(receipt, invoice, "3000")

    assert row.allocated_amount == Decimal("3000.00")
    assert row.unallocated_amount == Decimal("2000.00")


def test_applying_an_advance_posts_no_journal() -> None:
    """The money already moved when the receipt was recorded.

    Applying it decides which invoice the receivable credit belongs to, which
    is the subsidiary ledger's business. A journal here counts it twice.
    """
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    invoice = books.invoice("SI-1", "3000")
    before = books.session.scalar(select(func.count()).select_from(JournalEntry))

    books.apply(receipt, invoice, "3000")

    assert (
        books.session.scalar(select(func.count()).select_from(JournalEntry)) == before
    )


def test_more_than_the_receipt_holds_is_refused() -> None:
    """Allocating money that never arrived writes a lie into the books."""
    books = _Books(_session_factory()())
    receipt = books.receipt("1000", against=books.order)
    invoice = books.invoice("SI-1", "3000")

    with pytest.raises(ValidationError, match="left unapplied"):
        books.apply(receipt, invoice, "2000")


def test_more_than_the_invoice_owes_is_refused() -> None:
    """The invoice would report as over-paid and the ageing would go negative."""
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    invoice = books.invoice("SI-1", "1000")

    with pytest.raises(ValidationError, match="owes only"):
        books.apply(receipt, invoice, "2000")


def test_the_same_invoice_cannot_be_applied_to_twice() -> None:
    """Two allocations against one invoice are one allocation."""
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    invoice = books.invoice("SI-1", "3000")
    books.apply(receipt, invoice, "1000")

    with pytest.raises(ValidationError, match="already applied"):
        books.apply(receipt, invoice, "500")


def test_a_reversed_receipt_holds_nothing_to_apply() -> None:
    """The money went back."""
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    invoice = books.invoice("SI-1", "3000")
    ReceiptService(books.session).reverse(
        receipt.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque returned.",
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="reversed"):
        books.apply(receipt, invoice, "1000")


def test_a_reversed_receipt_leaves_the_order_s_totals() -> None:
    """It is money the firm does not have -- but the row stays on the list.

    A deposit that vanished from the screen leaves nobody able to say why the
    figure changed.
    """
    books = _Books(_session_factory()())
    receipt = books.receipt("5000", against=books.order)
    ReceiptService(books.session).reverse(
        receipt.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque returned.",
    )
    books.session.commit()

    summary = SalesOrderService(books.session).advances(
        books.order.id, firm_scope=books.firm.id
    )

    assert summary.total_received == Decimal("0.00")
    assert len(summary.receipts) == 1
    assert summary.receipts[0].status == "REVERSED"


def test_a_receipt_naming_no_order_is_still_a_receipt() -> None:
    """The link is optional, so nothing changes for a firm that never uses it."""
    books = _Books(_session_factory()())

    row = books.receipt("1000")

    assert row.sales_order_id is None
    assert row.unallocated_amount == Decimal("1000.00")


def test_applying_a_receipt_that_already_cleared_the_balance_posts_nothing() -> None:
    """The ordinary case, and the one that was wrong.

    A deposit taken while the customer already owes something goes straight
    off the balance and creates **no advance at all**. Posting `ADVANCE_APPLY`
    for it would take the same rupees off twice -- and the guard inside
    `post_receivable_transaction` refused the whole allocation with "exceeds
    unapplied advance", which is how driving it against a real store found
    this.
    """
    books = _Books(_session_factory()())
    # Billed first, so the receipt has something to clear.
    invoice = books.invoice("SI-1", "3000")
    receipt = books.receipt("3000", against=books.order)
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("0.0000")
    outstanding_before = books.customer.current_outstanding

    row = books.apply(receipt, invoice, "3000")
    books.session.refresh(books.customer)

    assert row.allocated_amount == Decimal("3000.00")
    # The balance is untouched: the money came off it when it arrived.
    assert books.customer.current_outstanding == outstanding_before


def test_only_the_part_that_became_an_advance_moves_the_balance() -> None:
    """A receipt bigger than what was owed splits, and so does the allocation.

    2,000 owed and 5,000 received: 2,000 came off the balance and 3,000
    became an advance. Allocating the whole 5,000 to a later bill may take
    only that 3,000 off the balance again.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", "2000")
    receipt = books.receipt("5000", against=books.order)
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("3000.0000")
    later = books.invoice("SI-2", "5000")
    books.session.refresh(books.customer)
    before = books.customer.current_outstanding

    books.apply(receipt, later, "5000")
    books.session.refresh(books.customer)

    assert books.customer.unapplied_advance_balance == Decimal("0.0000")
    assert books.customer.current_outstanding == before - Decimal("3000.0000")


def test_a_second_allocation_cannot_reuse_the_balance_part() -> None:
    """The part that came off the balance is used up once, not per invoice.

    2,000 owed and 5,000 received: 2,000 came off the balance, 3,000 became an
    advance. Spread across two later bills of 2,500, the first draws 500 from
    the advance and the second draws 2,500 -- 3,000 in all, which is exactly
    what the advance held. Letting each allocation claim the balance part
    afresh would leave 500 of the advance stranded for ever.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", "2000")
    receipt = books.receipt("5000", against=books.order)
    first = books.invoice("SI-2", "2500")
    second = books.invoice("SI-3", "2500")
    books.session.refresh(books.customer)
    assert books.customer.unapplied_advance_balance == Decimal("3000.0000")

    books.apply(receipt, first, "2500")
    books.apply(receipt, second, "2500")
    books.session.refresh(books.customer)

    assert books.customer.unapplied_advance_balance == Decimal("0.0000")
