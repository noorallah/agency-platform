"""A floor on a commission arrangement, and a bonus for meeting a target.

Two arrangements every distribution firm runs. The cases that decide whether
they can be trusted:

- a **floor** pays nothing at all below it, which is not the same as a
  zero-percent bottom slab -- a ladder pays from the first rupee once it is
  climbed;
- a **bonus** is paid only on a target actually met, and a person with no
  target has nothing to beat, so paying them would hand a bonus to everybody
  nobody set a number for;
- targets over a period are judged **taken together**, because a year holding
  twelve monthly numbers is met when the twelve achievements add up.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.commission.schemas import CommissionBasisEnum, CommissionRuleCreate
from app.commission.services import CommissionService
from app.core.database.base import Base
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales_invoice.models import SalesInvoice
from app.sales_targets.schemas import (
    SalesTargetBasis,
    SalesTargetPeriod,
    SalesTargetWrite,
)
from app.sales_targets.services import SalesTargetService

APRIL = (date(2026, 4, 1), date(2026, 4, 30))
MAY = (date(2026, 5, 1), date(2026, 5, 31))
BOTH = (date(2026, 4, 1), date(2026, 5, 31))


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
    """A firm, one salesman, and invoices tagged to them."""

    def __init__(self, session: Session) -> None:
        """Seed the firm, the customer and the salesman."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Bonus Firm",
            code="BONU",
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
            email="asha@bonus.example.com",
            full_name="Asha Rao",
            password_hash="x",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(UserFirm(user_id=user.id, firm_id=self.firm.id, is_active=True))
        self.asha = user.id
        session.commit()

    def invoice(self, number: str, total: str, on: date = date(2026, 4, 10)) -> None:
        """Bill one amount, tagged to Asha, and approve it."""
        self.session.add(
            SalesInvoice(
                firm_id=self.firm.id,
                customer_id=self.customer.id,
                branch_id=self.branch_id,
                salesman_id=self.asha,
                invoice_number=number,
                invoice_date=on,
                status="APPROVED",
                grand_total=Decimal(total),
            )
        )
        self.session.commit()

    def target(self, amount: str, period: tuple[date, date] = APRIL) -> None:
        """Set one target over a period."""
        SalesTargetService(self.session).create_target(
            SalesTargetWrite(
                salesman_id=self.asha,
                period_start=period[0],
                period_end=period[1],
                period_type=SalesTargetPeriod.MONTHLY,
                basis=SalesTargetBasis.INVOICED,
                target_amount=Decimal(amount),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def rule(
        self,
        percentage: str = "10",
        *,
        minimum_amount: str | None = None,
        bonus_percentage: str = "0",
    ) -> None:
        """Agree one arrangement, paid on invoiced value."""
        CommissionService(self.session).create_rule(
            CommissionRuleCreate(
                salesman_id=self.asha,
                percentage=Decimal(percentage),
                effective_from=date(2026, 4, 1),
                basis=CommissionBasisEnum.INVOICED,
                minimum_amount=(
                    None if minimum_amount is None else Decimal(minimum_amount)
                ),
                bonus_percentage=Decimal(bonus_percentage),
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()

    def row(self, period: tuple[date, date] = BOTH) -> tuple[Decimal, bool | None]:
        """Return what Asha earned over a window, and whether targets were met."""
        result = CommissionService(self.session).report(
            firm_id=self.firm.id, from_date=period[0], to_date=period[1]
        )
        [found] = [row for row in result.rows if row.salesman_id == self.asha]
        return found.commission_amount, found.target_met


def test_nothing_is_earned_below_the_floor() -> None:
    """A floor of ten lakh pays nothing at all below it, not a little."""
    books = _Books(_session_factory()())
    books.rule("10", minimum_amount="10000")
    books.invoice("SI-1", "9000.00")

    assert books.row()[0] == Decimal("0.00")


def test_reaching_the_floor_pays_on_all_of_it() -> None:
    """A floor is a threshold on the arrangement, not an exempt first slice.

    Paying only on the excess would be a ladder, and a ladder is what slabs
    are for -- they are different deals and a firm means one of them.
    """
    books = _Books(_session_factory()())
    books.rule("10", minimum_amount="10000")
    books.invoice("SI-1", "12000.00")

    assert books.row()[0] == Decimal("1200.00")


def test_a_bonus_is_paid_when_the_target_was_met() -> None:
    """The whole point: beating the number is worth more than making it."""
    books = _Books(_session_factory()())
    books.rule("10", bonus_percentage="5")
    books.target("10000", period=APRIL)
    books.invoice("SI-1", "12000.00")

    earned, met = books.row(APRIL)
    assert met is True
    assert earned == Decimal("1800.00")


def test_a_bonus_is_not_paid_when_the_target_was_missed() -> None:
    """A bonus for a number nobody made is not a bonus."""
    books = _Books(_session_factory()())
    books.rule("10", bonus_percentage="5")
    books.target("20000", period=APRIL)
    books.invoice("SI-1", "12000.00")

    earned, met = books.row(APRIL)
    assert met is False
    assert earned == Decimal("1200.00")


def test_somebody_with_no_target_earns_no_bonus() -> None:
    """Nobody set them a number, so there is nothing they beat.

    Reading a missing target as met would hand the bonus to everybody the
    firm never measured, which is the opposite of what a bonus is; reading it
    as missed would be a failure nobody could have avoided, which is why the
    report says null rather than False.
    """
    books = _Books(_session_factory()())
    books.rule("10", bonus_percentage="5")
    books.invoice("SI-1", "12000.00")

    earned, met = books.row(APRIL)
    assert met is None
    assert earned == Decimal("1200.00")


def test_targets_over_a_window_are_judged_together() -> None:
    """Twelve monthly numbers are met when the twelve achievements add up.

    Requiring every single month would make an annual bonus almost impossible
    to earn; requiring only one would make it almost impossible to miss. April
    falls short by 2,000 and May beats its number by 3,000, so together they
    are made.
    """
    books = _Books(_session_factory()())
    books.rule("10", bonus_percentage="5")
    books.target("10000", period=APRIL)
    books.target("10000", period=MAY)
    books.invoice("SI-1", "8000.00", on=date(2026, 4, 10))
    books.invoice("SI-2", "13000.00", on=date(2026, 5, 10))

    earned, met = books.row(BOTH)
    assert met is True
    assert earned == Decimal("3150.00")


def test_the_cap_still_holds_over_a_bonus() -> None:
    """A ceiling a firm agreed is a ceiling on what it pays, bonus included."""
    books = _Books(_session_factory()())
    CommissionService(books.session).create_rule(
        CommissionRuleCreate(
            salesman_id=books.asha,
            percentage=Decimal("10"),
            effective_from=date(2026, 4, 1),
            basis=CommissionBasisEnum.INVOICED,
            bonus_percentage=Decimal("5"),
            max_commission_amount=Decimal("1500"),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    books.target("10000", period=APRIL)
    books.invoice("SI-1", "12000.00")

    assert books.row(APRIL)[0] == Decimal("1500.00")


def test_a_floor_and_a_bonus_together_read_in_that_order() -> None:
    """Below the floor nothing is earned, and a bonus is not an exception.

    A bonus paid to somebody the arrangement pays nothing to would be money
    with no rate behind it.
    """
    books = _Books(_session_factory()())
    books.rule("10", minimum_amount="10000", bonus_percentage="5")
    books.target("5000", period=APRIL)
    books.invoice("SI-1", "9000.00")

    earned, met = books.row(APRIL)
    assert met is True, "the target was beaten"
    assert earned == Decimal("0.00"), "but the arrangement pays nothing yet"
