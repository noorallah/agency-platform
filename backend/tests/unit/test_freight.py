"""A delivery charge, taxed with the goods it delivers.

Freight is the mirror image of a bill discount: one reduces each line's taxable
value and the other raises it, both are split across the lines by the same
`apportion`, and both give the rounding residual to the largest line.

The cases that decide whether it can be trusted:

- it **reaches the tax**, or it is a document-level figure that reduces nothing
  -- the mistake `header_discount_amount` makes on a purchase order;
- the shares **sum exactly** to the header figure, or the document does not add
  up to itself;
- it comes **on top of** the discounts rather than netting against them, so a
  discounted line still carries its share; and
- `additional_charges` is left outside the tax, because that is what it is for.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.products.models import Product
from app.quotation.models import SalesQuotation, SalesQuotationLine
from app.quotation.schemas import QuotationCreate, QuotationLineWrite
from app.quotation.services import QuotationService

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
    """A firm that can raise a quotation with two lines."""

    def __init__(self, session: Session) -> None:
        """Seed the firm and its masters."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Freight Firm",
            code="FRGT",
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
        self.first = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.second = Product(
            firm_id=self.firm.id,
            code="SKU-2",
            name="Shampoo 180ml",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add_all([self.warehouse, self.customer, self.first, self.second])
        session.commit()

    def quote(
        self,
        *,
        freight: str | None = None,
        bill_discount: str | None = None,
        line_discount: str | None = None,
        charges: str = "0",
    ) -> SalesQuotation:
        """Raise a quotation for 1,000 and 3,000 of goods."""
        return QuotationService(self.session).create_quotation(
            QuotationCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                quotation_date=WHEN,
                valid_until=date(2026, 12, 31),
                additional_charges=Decimal(charges),
                freight_amount=None if freight is None else Decimal(freight),
                bill_discount_amount=(
                    None if bill_discount is None else Decimal(bill_discount)
                ),
                lines=[
                    QuotationLineWrite(
                        line_number=1,
                        product_id=self.first.id,
                        quantity=Decimal("10"),
                        unit_price=Decimal("100"),
                        discount_amount=(
                            None if line_discount is None else Decimal(line_discount)
                        ),
                    ),
                    QuotationLineWrite(
                        line_number=2,
                        product_id=self.second.id,
                        quantity=Decimal("10"),
                        unit_price=Decimal("300"),
                    ),
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def lines(self, row: SalesQuotation) -> list[SalesQuotationLine]:
        """Return the quotation's lines, in order."""
        return list(
            self.session.scalars(
                select(SalesQuotationLine)
                .where(SalesQuotationLine.sales_quotation_id == row.id)
                .order_by(SalesQuotationLine.line_number.asc())
            ).all()
        )


def test_freight_is_split_across_the_lines_by_what_they_are_worth() -> None:
    """A line worth three times another carries three times the freight."""
    books = _Books(_session_factory()())

    row = books.quote(freight="400")
    lines = books.lines(row)

    assert row.freight_amount == Decimal("400.0000")
    assert lines[0].freight_amount == Decimal("100.0000")
    assert lines[1].freight_amount == Decimal("300.0000")


def test_the_shares_sum_to_the_header_figure() -> None:
    """A document whose lines do not add up to itself is unreconcilable.

    1,000 and 3,000 splitting 100 gives 25 and 75 exactly; the awkward figure
    below does not divide, and the residual goes to the larger line.
    """
    books = _Books(_session_factory()())

    row = books.quote(freight="100.01")
    lines = books.lines(row)

    assert sum(line.freight_amount for line in lines) == row.freight_amount


def test_freight_raises_what_the_line_is_taxed_on() -> None:
    """Or it is a document-level figure that taxes nothing.

    That is what `header_discount_amount` does on a purchase order, and it is
    the mistake this design exists to avoid.
    """
    books = _Books(_session_factory()())

    without = books.quote()
    with_freight = books.quote(freight="400")

    assert with_freight.subtotal == without.subtotal + Decimal("400.0000")


def test_freight_comes_on_top_of_a_discount_rather_than_netting_against_it() -> None:
    """A discounted line still carries its share of the delivery."""
    books = _Books(_session_factory()())

    row = books.quote(freight="400", bill_discount="400")
    lines = books.lines(row)

    # The two cancel in the total and both survive on the line, which is what
    # lets a bill show what was charged and what was taken off.
    assert row.bill_discount_amount == Decimal("400.0000")
    assert row.freight_amount == Decimal("400.0000")
    assert lines[0].bill_discount_amount == Decimal("100.0000")
    assert lines[0].freight_amount == Decimal("100.0000")


def test_a_line_discounted_to_nothing_carries_no_freight() -> None:
    """It is worth nothing to deliver, and the weights say so."""
    books = _Books(_session_factory()())

    row = books.quote(freight="400", line_discount="1000")
    lines = books.lines(row)

    assert lines[0].freight_amount == Decimal("0.0000")
    assert lines[1].freight_amount == Decimal("400.0000")


def test_additional_charges_stay_outside_the_tax() -> None:
    """They are for additions that really are outside the tax.

    Re-taxing them would change the meaning of every document that carries
    one, which is why freight got a field of its own.
    """
    books = _Books(_session_factory()())

    plain = books.quote()
    charged = books.quote(charges="400")

    # It reaches the total but not the taxable value, which is the difference
    # between it and freight.
    assert charged.subtotal == plain.subtotal
    assert charged.grand_total == plain.grand_total + Decimal("400.0000")


def test_no_freight_leaves_every_figure_where_it_was() -> None:
    """Shipping this changes nothing for a firm that never charges delivery."""
    books = _Books(_session_factory()())

    row = books.quote()

    assert row.freight_amount == Decimal("0.0000")
    assert all(line.freight_amount == Decimal("0.0000") for line in books.lines(row))


def test_negative_freight_is_refused() -> None:
    """A delivery charge that gives money back is a discount.

    There is already a field for that, and two ways to express one thing is
    how the two come to disagree.
    """
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        QuotationService(books.session)._freight_shares(  # noqa: SLF001
            books.quote(),
            freight=Decimal("-1"),
            taxables=[Decimal("100")],
        )


def test_freight_carries_into_the_order_as_the_deal() -> None:
    """Re-split by the order across whatever lines it ends up with.

    Copying each line's share instead agrees only while both documents hold
    the same lines, which is the rule the bill discount already follows.
    """
    books = _Books(_session_factory()())
    service = QuotationService(books.session)
    row = books.quote(freight="400")
    service.send_quotation(row.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    service.accept_quotation(row.id, firm_scope=books.firm.id, actor_id=books.actor_id)

    _quotation, order = service.convert_quotation(
        row.id,
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        order_date=WHEN,
    )

    assert order.freight_amount == Decimal("400.0000")
