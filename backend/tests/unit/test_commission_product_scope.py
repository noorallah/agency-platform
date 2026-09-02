"""A commission rule that names the goods it is about, and a per-unit rate.

A rate used to be a statement about a whole document. These are the cases that
decide whether making it a statement about *lines* can be trusted:

- an **unscoped** rule still measures exactly the document, because the shares
  of an invoice sum to the invoice -- otherwise every existing arrangement
  quietly changes what it pays;
- the **narrower** rule wins for the lines it names while the broader one
  still covers the rest, which is what "3% on everything, 5% on the cold
  chain" means;
- a **per-unit** rate multiplies cases, not rupees, and is refused where that
  cannot mean anything.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.commission.schemas import (
    CommissionBasisEnum,
    CommissionRateTypeEnum,
    CommissionRuleCreate,
)
from app.commission.services import CommissionService
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.products.models import Product, ProductCategory
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

WHEN = date(2026, 4, 20)
YEAR = (date(2026, 4, 1), date(2027, 3, 31))


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
    """A firm selling two things, one of them in a category of its own."""

    def __init__(self, session: Session) -> None:
        """Seed a firm, a salesman, a customer and two products."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Scope Firm",
            code="SCOP",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        self.branch_id = uuid4()
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
        )
        session.add(self.customer)
        user = User(
            email="asha@scope.example.com",
            full_name="Asha Rao",
            password_hash="x",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(UserFirm(user_id=user.id, firm_id=self.firm.id, is_active=True))
        self.asha = user.id
        self.chilled = ProductCategory(
            firm_id=self.firm.id, code="COLD", name="Cold chain", path="COLD"
        )
        self.dry = ProductCategory(
            firm_id=self.firm.id, code="DRY", name="Dry goods", path="DRY"
        )
        session.add_all([self.chilled, self.dry])
        session.flush()
        self.milk = self._product("MILK", "Milk", self.chilled.id)
        self.rice = self._product("RICE", "Rice", self.dry.id)
        session.commit()

    def _product(self, code: str, name: str, category_id: UUID) -> Product:
        """Add one product in a category."""
        row = Product(
            firm_id=self.firm.id,
            code=code,
            name=name,
            category_id=category_id,
            product_type="GOODS",
            status="ACTIVE",
        )
        self.session.add(row)
        self.session.flush()
        return row

    def invoice(self, number: str, lines: list[tuple[Product, str, str]]) -> None:
        """Bill some lines, tagged to Asha, and approve it.

        Each line is (product, quantity, net amount). The invoice's total is
        the sum of the line nets, which is what a real invoice's is.
        """
        total = sum(Decimal(net) for _, _, net in lines)
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch_id,
            salesman_id=self.asha,
            invoice_number=number,
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=total,
        )
        self.session.add(row)
        self.session.flush()
        for index, (product, quantity, net) in enumerate(lines, start=1):
            self.session.add(
                SalesInvoiceLine(
                    sales_invoice_id=row.id,
                    firm_id=self.firm.id,
                    line_number=index,
                    source_document_type="SALES_ORDER",
                    source_document_id=uuid4(),
                    source_document_number=f"SO-{index}",
                    source_document_line_id=uuid4(),
                    source_document_line_number=index,
                    product_id=product.id,
                    delivered_quantity=Decimal(quantity),
                    current_invoice_quantity=Decimal(quantity),
                    unit_price=Decimal(net) / Decimal(quantity),
                    gross_amount=Decimal(net),
                    net_amount=Decimal(net),
                )
            )
        self.session.commit()

    def rule(
        self,
        percentage: str = "0",
        *,
        product: Product | None = None,
        category: ProductCategory | None = None,
        rate_type: CommissionRateTypeEnum = CommissionRateTypeEnum.PERCENT,
        per_unit_amount: str = "0",
        basis: CommissionBasisEnum = CommissionBasisEnum.INVOICED,
        salesman: bool = True,
    ) -> None:
        """Agree one arrangement."""
        CommissionService(self.session).create_rule(
            CommissionRuleCreate(
                salesman_id=self.asha if salesman else None,
                percentage=Decimal(percentage),
                effective_from=date(2026, 4, 1),
                basis=basis,
                product_id=None if product is None else product.id,
                product_category_id=None if category is None else category.id,
                rate_type=rate_type,
                per_unit_amount=Decimal(per_unit_amount),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def earned(self) -> Decimal:
        """Return what Asha earned across the whole year."""
        result = CommissionService(self.session).report(
            firm_id=self.firm.id, from_date=YEAR[0], to_date=YEAR[1]
        )
        [row] = [row for row in result.rows if row.salesman_id == self.asha]
        return row.commission_amount


def test_an_unscoped_rule_still_measures_the_whole_document() -> None:
    """The invariant every existing arrangement depends on.

    The report resolves per line now, so an unscoped rule matches all of them
    and their shares must sum to the invoice exactly. If they did not, every
    rule written before scoping existed would quietly start paying a slightly
    different number.
    """
    books = _Books(_session_factory()())
    books.rule("10")
    books.invoice("SI-1", [(books.milk, "10", "600.00"), (books.rice, "5", "400.00")])

    assert books.earned() == Decimal("100.00")


def test_a_rule_naming_a_product_pays_only_on_that_product() -> None:
    """The cold chain pays better than dry goods, which is the whole point."""
    books = _Books(_session_factory()())
    books.rule("10", product=books.milk)
    books.invoice("SI-1", [(books.milk, "10", "600.00"), (books.rice, "5", "400.00")])

    assert books.earned() == Decimal("60.00")


def test_the_narrower_rule_wins_and_the_broader_one_covers_the_rest() -> None:
    """A firm saying 3% on everything and 5% on the cold chain means one deal.

    It only works if the product rule takes its own lines while the unscoped
    one still takes the others -- if the narrower rule simply replaced the
    broader, the dry goods would earn nothing.
    """
    books = _Books(_session_factory()())
    books.rule("3")
    books.rule("5", product=books.milk)
    books.invoice("SI-1", [(books.milk, "10", "600.00"), (books.rice, "5", "400.00")])

    # 5% of 600 plus 3% of 400.
    assert books.earned() == Decimal("42.00")


def test_a_product_rule_beats_a_category_rule_on_the_same_line() -> None:
    """The product is the narrower of the two, so it is the one that applies."""
    books = _Books(_session_factory()())
    books.rule("4", category=books.chilled)
    books.rule("9", product=books.milk)
    books.invoice("SI-1", [(books.milk, "10", "600.00")])

    assert books.earned() == Decimal("54.00")


def test_a_category_rule_covers_every_product_in_it() -> None:
    """One rung up from a product, and the reason categories are worth having."""
    books = _Books(_session_factory()())
    cheese = books._product("CHZ", "Cheese", books.chilled.id)
    books.session.commit()
    books.rule("10", category=books.chilled)
    books.invoice("SI-1", [(books.milk, "10", "600.00"), (cheese, "2", "200.00")])

    assert books.earned() == Decimal("80.00")


def test_a_persons_own_unscoped_rule_beats_a_firm_wide_product_rule() -> None:
    """Whose rule it is outranks what it is about.

    A rate agreed with one person is an arrangement with them; a firm-wide
    rule is what everybody else gets. Letting the firm-wide rule win because
    it happens to name a product would override a deal somebody negotiated.
    """
    books = _Books(_session_factory()())
    books.rule("2", product=books.milk, salesman=False)
    books.rule("7")
    books.invoice("SI-1", [(books.milk, "10", "600.00")])

    assert books.earned() == Decimal("42.00")


def test_a_per_unit_rate_pays_for_cases_and_ignores_the_price() -> None:
    """Two rupees a case is two rupees a case whatever the case sold for."""
    books = _Books(_session_factory()())
    books.rule(
        product=books.milk,
        rate_type=CommissionRateTypeEnum.PER_UNIT,
        per_unit_amount="2.5",
    )
    books.invoice("SI-1", [(books.milk, "10", "600.00")])

    assert books.earned() == Decimal("25.00")


def test_a_per_unit_rate_on_collections_is_refused() -> None:
    """Money collected has no cases in it."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.rule(
            product=books.milk,
            rate_type=CommissionRateTypeEnum.PER_UNIT,
            per_unit_amount="2.5",
            basis=CommissionBasisEnum.COLLECTED,
        )


def test_a_per_unit_rate_across_everything_is_refused() -> None:
    """It would add cases of biscuits to litres of oil."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.rule(rate_type=CommissionRateTypeEnum.PER_UNIT, per_unit_amount="2.5")


def test_naming_both_a_product_and_a_category_is_refused() -> None:
    """Two answers to one question; the product is the narrower."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.rule("5", product=books.milk, category=books.chilled)


def test_two_rules_over_the_same_days_for_different_goods_are_allowed() -> None:
    """The overlap guard is about one scope, not about one person's calendar.

    Refusing these would make the whole feature unusable: a product rule can
    only exist beside the broader rule it narrows.
    """
    books = _Books(_session_factory()())
    books.rule("3")
    books.rule("5", product=books.milk)
    books.rule("4", category=books.dry)


def test_two_rules_over_the_same_days_for_the_same_product_are_refused() -> None:
    """Two rates for one person and one product leave the payout to luck."""
    books = _Books(_session_factory()())
    books.rule("5", product=books.milk)

    with pytest.raises(ConflictError):
        books.rule("6", product=books.milk)


def test_a_scoped_rule_takes_its_share_of_each_receipt() -> None:
    """A payment clears a share of every line it settles.

    Half the bill collected against an invoice whose milk is 60% of it earns
    the milk rule 60% of that half -- not all of it, and not none of it.
    """
    from app.finance.services.opening_setup import seed_finance_setup
    from app.settlements.schemas import (
        SettlementAllocationWrite,
        SettlementCreate,
        SettlementMethodEnum,
    )
    from app.settlements.services import ReceiptService

    books = _Books(_session_factory()())
    seed_finance_setup(
        books.session,
        firm_id=books.firm.id,
        year_starts_on=date(2026, 4, 1),
        actor_id=books.actor_id,
    )
    books.session.commit()
    books.rule("10", product=books.milk, basis=CommissionBasisEnum.COLLECTED)
    books.invoice("SI-1", [(books.milk, "10", "600.00"), (books.rice, "5", "400.00")])
    invoice = books.session.query(SalesInvoice).one()
    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("500.00"),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=invoice.id, amount=Decimal("500.00")
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    # 60% of the 500 collected is the milk's, and 10% of that is 30.
    assert books.earned() == Decimal("30.00")


def test_the_shares_add_up_to_the_document_and_not_to_the_lines() -> None:
    """An invoice's total is not the sum of its line net amounts.

    Tax, rounding and header charges live above the lines, so a share derived
    from a line's own net would leave a commission report that does not
    reconcile against the invoices behind it -- and would quietly change what
    every unscoped rule pays. The share is the **document's** total
    apportioned across the lines, which is why `apportion` is the helper here.

    Whether commission should be paid on tax at all is a separate question and
    a firm's to answer; this asserts only that scoping the rules changed
    nothing about what an unscoped one measures.
    """
    books = _Books(_session_factory()())
    books.rule("10")
    # Lines netting 1,000, billed at 1,180 once tax is added at the header.
    row = SalesInvoice(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        branch_id=books.branch_id,
        salesman_id=books.asha,
        invoice_number="SI-TAX",
        invoice_date=WHEN,
        status="APPROVED",
        grand_total=Decimal("1180.00"),
    )
    books.session.add(row)
    books.session.flush()
    for index, (product, quantity, net) in enumerate(
        [(books.milk, "10", "600.00"), (books.rice, "5", "400.00")], start=1
    ):
        books.session.add(
            SalesInvoiceLine(
                sales_invoice_id=row.id,
                firm_id=books.firm.id,
                line_number=index,
                source_document_type="SALES_ORDER",
                source_document_id=uuid4(),
                source_document_number=f"SO-{index}",
                source_document_line_id=uuid4(),
                source_document_line_number=index,
                product_id=product.id,
                delivered_quantity=Decimal(quantity),
                current_invoice_quantity=Decimal(quantity),
                unit_price=Decimal(net) / Decimal(quantity),
                gross_amount=Decimal(net),
                net_amount=Decimal(net),
            )
        )
    books.session.commit()

    assert books.earned() == Decimal("118.00")
