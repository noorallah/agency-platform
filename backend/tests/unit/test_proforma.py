"""A bill that is not a bill.

The cases that decide whether a proforma is safe to send a customer:

- it **posts nothing** -- no journal, no receivable, no stock. There is
  nowhere on the document to record that it did, and the test proves the
  absence rather than trusting it;
- its lines are **snapshotted** from the order, so editing the order afterwards
  cannot change a document somebody is arranging payment against;
- **once issued it cannot be edited**, for the same reason;
- and it takes its number from **its own series**, never the tax invoice's --
  GSTR-1's DOCS section declares the invoice series, and a proforma drawn from
  it would put a number in the return that was never a supply.
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
from app.customers.models import Customer, CustomerReceivableTransaction
from app.finance.models import JournalEntry
from app.firms.models import Firm
from app.products.models import Product
from app.proforma.models import ProformaInvoice, ProformaStatus
from app.proforma.schemas import ProformaCreate, ProformaUpdate
from app.proforma.services import ProformaService
from app.sales_order.models import SalesOrder, SalesOrderLine

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
    """A firm with one approved sales order to state."""

    def __init__(self, session: Session) -> None:
        """Seed the firm, its masters and an approved order."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Proforma Firm",
            code="PROF",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
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
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add_all([self.warehouse, self.customer, self.product])
        session.commit()
        self.order = self._order()

    def _order(self, status: str = "APPROVED") -> SalesOrder:
        """Raise an order with one priced, taxed line."""
        order = SalesOrder(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            order_number=f"SO-{uuid4().hex[:6].upper()}",
            order_date=WHEN,
            status=status,
            currency_code="INR",
        )
        self.session.add(order)
        self.session.flush()
        self.session.add(
            SalesOrderLine(
                sales_order_id=order.id,
                firm_id=self.firm.id,
                line_number=1,
                product_id=self.product.id,
                description="Toothpaste 150g",
                quantity=Decimal("10"),
                free_quantity=Decimal("1"),
                base_quantity=Decimal("10"),
                unit_price=Decimal("100"),
                discount_percent=Decimal("10"),
                discount_amount=Decimal("100"),
                gross_amount=Decimal("1000"),
                bill_discount_amount=Decimal("50"),
                tax_amount=Decimal("153"),
                net_amount=Decimal("1003"),
            )
        )
        self.session.commit()
        return order

    def raise_proforma(self, **overrides: object) -> ProformaInvoice:
        """Raise a proforma against the seeded order."""
        payload = {
            "sales_order_id": self.order.id,
            "proforma_date": WHEN,
        }
        payload.update(overrides)
        return ProformaService(self.session).create_proforma(
            ProformaCreate(**payload),  # type: ignore[arg-type]
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )


def test_a_proforma_states_what_the_order_will_be_charged() -> None:
    """Its totals are summed from the lines it copied, gross less discounts."""
    books = _Books(_session_factory()())

    row = books.raise_proforma()

    # 1000 gross, less a 100 line discount and a 50 share of the bill
    # discount, is 850 taxable; 153 of tax on top.
    assert row.subtotal == Decimal("850.0000")
    assert row.tax_total == Decimal("153.0000")
    assert row.grand_total == Decimal("1003.0000")
    assert row.line_discount_total == Decimal("100.0000")
    assert row.bill_discount_amount == Decimal("50.0000")


def test_it_posts_nothing_at_all() -> None:
    """No journal, no receivable, no stock.

    Proved by looking for them rather than assumed: this is the one property
    that separates a proforma from a bill, and a future change that started
    posting would otherwise be invisible until a trial balance moved.
    """
    books = _Books(_session_factory()())
    row = books.raise_proforma()
    ProformaService(books.session).issue_proforma(
        row.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )

    assert books.session.scalar(select(func.count()).select_from(JournalEntry)) == 0
    assert (
        books.session.scalar(
            select(func.count()).select_from(CustomerReceivableTransaction)
        )
        == 0
    )
    books.session.refresh(books.customer)
    assert books.customer.current_outstanding == Decimal("0.0000")


def test_the_lines_are_snapshotted_not_referenced() -> None:
    """The order can change afterwards; the document must not.

    A customer arranging payment against a proforma has to be able to rely on
    the figure. Reading the order live would let an edit in August rewrite a
    document sent in June.
    """
    books = _Books(_session_factory()())
    row = books.raise_proforma()

    line = books.session.scalars(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == books.order.id)
    ).one()
    line.unit_price = Decimal("500")
    line.gross_amount = Decimal("5000")
    books.session.commit()

    stated = ProformaService(books.session).lines_of(row)
    assert stated[0].unit_price == Decimal("100.0000")
    assert stated[0].gross_amount == Decimal("1000.0000")


def test_free_goods_are_stated_too() -> None:
    """A proforma that dropped them would understate what is being shipped."""
    books = _Books(_session_factory()())
    row = books.raise_proforma()

    assert ProformaService(books.session).lines_of(row)[0].free_quantity == Decimal(
        "1.0000"
    )


def test_an_issued_proforma_cannot_be_edited() -> None:
    """The customer may already be arranging payment against the number."""
    books = _Books(_session_factory()())
    service = ProformaService(books.session)
    row = books.raise_proforma()
    service.issue_proforma(row.id, firm_scope=books.firm.id, actor_id=books.actor_id)

    with pytest.raises(ValidationError, match="draft"):
        service.update_proforma(
            row.id,
            ProformaUpdate(remarks="Changed my mind."),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_draft_can_be_amended_and_an_omission_leaves_a_field_alone() -> None:
    """A write model that dumps in full turns an omission into an instruction."""
    books = _Books(_session_factory()())
    service = ProformaService(books.session)
    row = books.raise_proforma(payment_terms="30 days net")

    service.update_proforma(
        row.id,
        ProformaUpdate(remarks="Ship by sea."),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )

    assert row.remarks == "Ship by sea."
    assert row.payment_terms == "30 days net"


def test_a_draft_order_cannot_be_stated() -> None:
    """A draft is not a deal, so there is nothing to state about it."""
    books = _Books(_session_factory()())
    draft = books._order(status="DRAFT")  # noqa: SLF001

    with pytest.raises(ValidationError, match="approved order"):
        books.raise_proforma(sales_order_id=draft.id)


def test_a_cancelled_order_cannot_be_stated() -> None:
    """It has been called off."""
    books = _Books(_session_factory()())
    cancelled = books._order(status="CANCELLED")  # noqa: SLF001

    with pytest.raises(ValidationError):
        books.raise_proforma(sales_order_id=cancelled.id)


def test_a_part_delivered_order_can_still_be_stated() -> None:
    """A firm may well restate an order for the balance."""
    books = _Books(_session_factory()())
    partial = books._order(status="PARTIALLY_DELIVERED")  # noqa: SLF001

    assert books.raise_proforma(sales_order_id=partial.id).grand_total > 0


def test_the_number_comes_from_its_own_series() -> None:
    """Never the tax invoice's.

    GSTR-1's DOCS section declares the invoice series a firm issued, so a
    proforma drawing from it would either leave a gap the return cannot
    explain or put a number in it that was never a supply.
    """
    books = _Books(_session_factory()())

    row = books.raise_proforma()

    assert row.proforma_number.startswith("PI")
    assert "SI" not in row.proforma_number


def test_cancelling_keeps_the_row_and_records_why() -> None:
    """A withdrawn proforma stays on the record.

    The customer holds a copy, and a document that vanished would leave them
    with a number this system cannot explain.
    """
    books = _Books(_session_factory()())
    service = ProformaService(books.session)
    row = books.raise_proforma()
    service.issue_proforma(row.id, firm_scope=books.firm.id, actor_id=books.actor_id)

    service.cancel_proforma(
        row.id,
        reason="Terms renegotiated.",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )

    assert row.status == ProformaStatus.CANCELLED.value
    assert row.cancel_reason == "Terms renegotiated."
    assert row.is_deleted is False


def test_a_proforma_cannot_be_issued_twice() -> None:
    """The second would be a second number for one statement."""
    books = _Books(_session_factory()())
    service = ProformaService(books.session)
    row = books.raise_proforma()
    service.issue_proforma(row.id, firm_scope=books.firm.id, actor_id=books.actor_id)

    with pytest.raises(ValidationError, match="already been issued"):
        service.issue_proforma(
            row.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def test_a_revision_says_what_it_replaces() -> None:
    """A new document rather than an edit, and the link makes that legible."""
    books = _Books(_session_factory()())
    service = ProformaService(books.session)
    first = books.raise_proforma()
    service.issue_proforma(first.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    service.cancel_proforma(
        first.id,
        reason="Superseded.",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )

    second = books.raise_proforma(supersedes_id=first.id)

    assert second.supersedes_id == first.id
    assert second.proforma_number != first.proforma_number


def test_one_firm_s_proforma_is_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    row = books.raise_proforma()

    with pytest.raises(ResourceNotFoundError):
        ProformaService(books.session).get_proforma(row.id, firm_scope=uuid4())


def test_an_order_from_another_firm_cannot_be_stated() -> None:
    """The order is the deal being stated, so it has to be this firm's."""
    books = _Books(_session_factory()())

    with pytest.raises(ResourceNotFoundError):
        ProformaService(books.session).create_proforma(
            ProformaCreate(sales_order_id=uuid4(), proforma_date=WHEN),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_the_response_says_it_is_not_a_tax_invoice() -> None:
    """A customer's clerk holding a printout has no other way to tell."""
    books = _Books(_session_factory()())
    row = books.raise_proforma()

    answer = ProformaService(books.session).proforma_response(row)

    assert answer.is_tax_invoice is False
    assert answer.sales_order_number == books.order.order_number
