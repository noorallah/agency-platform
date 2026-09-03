"""Commission on what a sale made, not on what it was worth.

The last item of the incentives spec, and it was blocked on one thing: the
invoice line carried no cost. It is now snapshotted there when the bill is
raised, from the stock ledger's own moving average, because re-reading it at
report time would answer about today rather than about the day.

The cases that decide whether a margin rule can be trusted:

- **an unknown cost is not a zero cost.** A line with nothing recorded
  contributes nothing to a margin rule; treating it as free would pay on the
  whole sale price, which is the worst number this report could produce;
- a sale below cost earns **nothing, not a negative**, because taking money off
  other sales to cover it is a different arrangement nobody asked for;
- and a VALUE rule is untouched, so no existing arrangement changes what it
  pays.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.commission.models import CommissionMeasure, CommissionRule
from app.commission.services import CommissionService
from app.core.database.base import Base
from app.customers.models import Customer
from app.firms.models import Firm
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

WHEN = date(2026, 6, 10)
PERIOD = (date(2026, 6, 1), date(2026, 6, 30))


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
    """A firm with one salesman, and invoices carrying a cost."""

    def __init__(self, session: Session) -> None:
        """Seed the firm and its masters."""
        self.session = session
        self.actor_id = uuid4()
        self.salesman_id = uuid4()
        self.firm = Firm(
            name="Margin Firm",
            code="MRGN",
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
        session.add_all([self.branch, self.customer, self.product])
        session.commit()

    def rule(
        self,
        *,
        percent: str = "10",
        measure: CommissionMeasure = CommissionMeasure.VALUE,
    ) -> CommissionRule:
        """Give the salesman an arrangement."""
        row = CommissionRule(
            firm_id=self.firm.id,
            salesman_id=self.salesman_id,
            percentage=Decimal(percent),
            basis="INVOICED",
            status="ACTIVE",
            effective_from=date(2026, 4, 1),
            measure=measure.value,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def invoice(
        self,
        number: str,
        *,
        total: str = "1000",
        cost: str | None = "600",
    ) -> SalesInvoice:
        """Bill one line, with or without a cost against it."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            salesman_id=self.salesman_id,
            invoice_number=number,
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal(total),
        )
        self.session.add(row)
        self.session.flush()
        self.session.add(
            SalesInvoiceLine(
                sales_invoice_id=row.id,
                firm_id=self.firm.id,
                line_number=1,
                source_document_type="DELIVERY_NOTE",
                source_document_id=uuid4(),
                source_document_number="DN-1",
                source_document_line_id=uuid4(),
                source_document_line_number=1,
                product_id=self.product.id,
                delivered_quantity=Decimal("10"),
                current_invoice_quantity=Decimal("10"),
                unit_price=Decimal("100"),
                gross_amount=Decimal(total),
                net_amount=Decimal(total),
                cost_amount=None if cost is None else Decimal(cost),
            )
        )
        self.session.commit()
        return row

    def earned(self) -> Decimal:
        """Return what the salesman earned over the period."""
        report = CommissionService(self.session).report(
            firm_id=self.firm.id, from_date=PERIOD[0], to_date=PERIOD[1]
        )
        for row in report.rows:
            if row.salesman_id == self.salesman_id:
                return row.commission_amount
        return Decimal("0")


def test_a_margin_rule_pays_on_the_margin() -> None:
    """1,000 billed against 600 of goods is 400 of margin, and 10% of it."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="600")

    assert books.earned() == Decimal("40.00")


def test_a_value_rule_is_untouched() -> None:
    """No existing arrangement changes what it pays."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.VALUE)
    books.invoice("SI-1", total="1000", cost="600")

    assert books.earned() == Decimal("100.00")


def test_an_unknown_cost_is_not_a_zero_cost() -> None:
    """A line with nothing recorded contributes nothing to a margin rule.

    Treating it as free would pay 10% of the whole 1,000 rather than of the
    margin -- the worst number this report could produce, and the reason the
    column is nullable.
    """
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost=None)

    assert books.earned() == Decimal("0.00")


def test_a_sale_below_cost_earns_nothing_rather_than_a_negative() -> None:
    """Taking money off other sales to cover it is a different arrangement."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="1500")

    assert books.earned() == Decimal("0.00")


def test_a_thin_markup_pays_far_less_than_the_same_turnover_would() -> None:
    """Which is the point of paying on margin at all."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="950")

    # Fifty of margin on a thousand of turnover.
    assert books.earned() == Decimal("5.00")


def test_margins_add_up_across_invoices() -> None:
    """Each line is measured on its own cost, not on an average of them."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="600")
    books.invoice("SI-2", total="2000", cost="1000")

    # 400 and 1,000 of margin.
    assert books.earned() == Decimal("140.00")


def test_a_known_cost_and_an_unknown_one_are_measured_separately() -> None:
    """The traced sale earns; the untraced one is skipped rather than guessed."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="600")
    books.invoice("SI-2", total="2000", cost=None)

    assert books.earned() == Decimal("40.00")


def test_the_measure_defaults_to_value() -> None:
    """A rule written before this existed pays exactly what it always did."""
    books = _Books(_session_factory()())
    row = CommissionRule(
        firm_id=books.firm.id,
        salesman_id=books.salesman_id,
        percentage=Decimal("10"),
        basis="INVOICED",
        status="ACTIVE",
        effective_from=date(2026, 4, 1),
    )
    books.session.add(row)
    books.session.commit()
    books.invoice("SI-1", total="1000", cost="600")

    assert row.measure == CommissionMeasure.VALUE.value
    assert books.earned() == Decimal("100.00")


def test_one_firm_s_costs_are_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    books.rule(percent="10", measure=CommissionMeasure.MARGIN)
    books.invoice("SI-1", total="1000", cost="600")

    report = CommissionService(books.session).report(
        firm_id=uuid4(), from_date=PERIOD[0], to_date=PERIOD[1]
    )

    assert all(row.commission_amount == Decimal("0") for row in report.rows)
