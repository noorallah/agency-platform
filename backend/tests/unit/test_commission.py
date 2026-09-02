"""Salesman commission: earned on money collected, at a dated rate.

Every test here drives real receipts through `ReceiptService` rather than
writing `settlement_allocations` by hand. The two facts the report depends on
-- that an allocation exists at all, and that its settlement was not later
reversed -- are written by that service, so a fixture that inserts the rows
itself would be testing a shape nothing produces.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.commission.models import CommissionRule
from app.commission.schemas import (
    CommissionBasisEnum,
    CommissionRuleCreate,
    CommissionRuleStatusEnum,
    CommissionRuleUpdate,
    CommissionSlabModeEnum,
    CommissionSlabWrite,
)
from app.commission.services import CommissionService
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.customers.models import Customer
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales_invoice.models import SalesInvoice
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import ReceiptService

#: Every receipt lands inside the seeded 2026-2027 financial year.
WHEN = date(2026, 4, 20)
LATER = date(2026, 7, 15)
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
    """A firm with a chart of accounts, a customer and two salesmen."""

    def __init__(self, session: Session, code: str = "ACME") -> None:
        """Seed everything a receipt needs to exist."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name=f"{code} Firm",
            code=code,
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
        session.commit()
        self.branch_id = uuid4()
        self.customer = Customer(
            firm_id=self.firm.id,
            code=f"C1-{code}",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        session.add(self.customer)
        session.commit()
        self.asha = self.salesman("Asha Rao", f"asha@{code.lower()}.example.com")
        self.bala = self.salesman("Bala Iyer", f"bala@{code.lower()}.example.com")

    def salesman(self, name: str, email: str) -> UUID:
        """Add one active member of the firm and return their id."""
        user = User(email=email, full_name=name, password_hash="x", is_active=True)
        self.session.add(user)
        self.session.flush()
        self.session.add(
            UserFirm(user_id=user.id, firm_id=self.firm.id, is_active=True)
        )
        self.session.commit()
        return user.id

    def invoice(
        self, number: str, total: str, salesman_id: UUID | None
    ) -> SalesInvoice:
        """Add one approved sales invoice, tagged with who sold it."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch_id,
            salesman_id=salesman_id,
            invoice_number=number,
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal(total),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def receipt(
        self, invoice: SalesInvoice, amount: str, when: date = WHEN
    ) -> Settlement:
        """Collect money against one invoice."""
        row = ReceiptService(self.session).create(
            SettlementCreate(
                party_id=self.customer.id,
                settlement_date=when,
                amount=Decimal(amount),
                method=SettlementMethodEnum.CASH,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=invoice.id, amount=Decimal(amount)
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def rule(
        self,
        percentage: str,
        *,
        salesman_id: UUID | None = None,
        effective_from: date = date(2026, 4, 1),
        effective_to: date | None = None,
        status: CommissionRuleStatusEnum = CommissionRuleStatusEnum.ACTIVE,
        basis: CommissionBasisEnum = CommissionBasisEnum.COLLECTED,
        slab_mode: CommissionSlabModeEnum = CommissionSlabModeEnum.MARGINAL,
        max_commission_amount: Decimal | None = None,
        slabs: list[tuple[str, str | None, str]] | None = None,
    ) -> CommissionRule:
        """Declare one commission rate."""
        row = CommissionService(self.session).create_rule(
            CommissionRuleCreate(
                salesman_id=salesman_id,
                percentage=Decimal(percentage),
                effective_from=effective_from,
                effective_to=effective_to,
                status=status,
                basis=basis,
                slab_mode=slab_mode,
                max_commission_amount=max_commission_amount,
                slabs=[
                    CommissionSlabWrite(
                        from_amount=Decimal(low),
                        to_amount=None if high is None else Decimal(high),
                        percentage=Decimal(rate),
                    )
                    for low, high, rate in (slabs or [])
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def report(
        self, salesman_id: UUID | None = None
    ) -> dict[UUID | None, tuple[Decimal, Decimal]]:
        """Return collected and commission by salesman for the whole year."""
        result = CommissionService(self.session).report(
            firm_id=self.firm.id,
            from_date=YEAR[0],
            to_date=YEAR[1],
            salesman_id=salesman_id,
        )
        return {
            row.salesman_id: (row.collected_amount, row.commission_amount)
            for row in result.rows
        }


def test_collected_money_lands_with_the_invoice_s_own_salesman() -> None:
    """Attribution is the tag the invoice carried, and the rate is per person.

    Not the customer's territory assignment today: that would move a March
    payout to whoever holds the round in August.
    """
    books = _Books(_session_factory()())
    books.rule("5", salesman_id=books.asha)
    books.rule("2", salesman_id=books.bala)
    hers = books.invoice("SI-1", "1000.00", books.asha)
    his = books.invoice("SI-2", "1000.00", books.bala)
    books.receipt(hers, "400.00")
    books.receipt(his, "500.00")

    rows = books.report()
    assert rows[books.asha] == (Decimal("400.00"), Decimal("20.00"))
    assert rows[books.bala] == (Decimal("500.00"), Decimal("10.00"))


def test_commission_follows_the_money_and_not_the_invoice() -> None:
    """On a COLLECTED rule, an invoice raised and not paid earns nothing.

    That is the whole reason the trigger is the receipt: paying on invoiced
    value pays for sales the firm may never be paid for. Since slabs landed the
    report *shows* the person's invoiced value beside the payout rather than
    omitting them, which is why this now reads the row rather than its absence
    -- a salesman who billed 1,000 and collected none of it is exactly who a
    firm wants to see on the report.
    """
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha)
    invoice = books.invoice("SI-1", "1000.00", books.asha)

    unpaid = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    assert unpaid.rows[0].invoiced_amount == Decimal("1000.00")
    assert unpaid.rows[0].collected_amount == Decimal("0.00")
    assert unpaid.total_commission_amount == Decimal("0.00")

    books.receipt(invoice, "250.00")
    assert books.report()[books.asha] == (Decimal("250.00"), Decimal("25.00"))


def test_a_reversed_receipt_earns_nobody_anything() -> None:
    """Money taken back is money that was never collected.

    The allocation row stays -- it is the record of what the receipt had
    cleared -- so the only thing that says the money went back is the
    settlement's status, and the report has to read it.
    """
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha)
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    kept = books.receipt(invoice, "300.00")
    taken_back = books.receipt(invoice, "200.00")

    ReceiptService(books.session).reverse(
        taken_back.id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque bounced.",
    )
    books.session.commit()

    assert kept.id != taken_back.id
    assert books.report()[books.asha] == (Decimal("300.00"), Decimal("30.00"))


def test_an_invoice_with_no_salesman_is_bucketed_and_not_dropped() -> None:
    """Money that belongs to nobody still has to appear.

    A report whose rows silently omit it cannot be reconciled against the cash
    book, and the gap looks like a defect in the attribution rather than like
    invoices nobody tagged.
    """
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha)
    hers = books.invoice("SI-1", "1000.00", books.asha)
    orphan = books.invoice("SI-2", "1000.00", None)
    books.receipt(hers, "100.00")
    books.receipt(orphan, "700.00")

    result = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    unassigned = [row for row in result.rows if row.salesman_id is None]
    assert len(unassigned) == 1
    assert unassigned[0].salesman_name == "Unassigned"
    assert unassigned[0].collected_amount == Decimal("700.00")
    # No rule can name nobody, so the bucket earns nothing -- and the firm-wide
    # default must not quietly pay it out either.
    assert unassigned[0].commission_amount == Decimal("0.00")
    assert result.total_collected_amount == Decimal("800.00")
    assert result.rows[-1].salesman_id is None, "the bucket sorts last"


def test_the_firm_wide_default_does_not_pay_the_unassigned_bucket() -> None:
    """A default is what a *person* with no rule of their own is paid.

    The test above asserts the bucket earns nothing, but its firm has no
    firm-wide rule, so it passed while `_rate_for` was reading the default for
    an owner of None. Driving a seeded store found it: every one of ELEC01's
    49 invoices carries no salesman, so the whole of a 3% default was reported
    as commission payable to nobody. The collected figure stays -- it has to
    reconcile against the cash book -- and only the payout is zero.
    """
    books = _Books(_session_factory()())
    books.rule("3")
    orphan = books.invoice("SI-1", "1000.00", None)
    books.receipt(orphan, "500.00")

    result = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    unassigned = [row for row in result.rows if row.salesman_id is None]
    assert unassigned[0].collected_amount == Decimal("500.00")
    assert unassigned[0].commission_amount == Decimal("0.00")
    assert result.total_commission_amount == Decimal("0.00")


def test_the_firm_wide_default_pays_a_salesman_with_no_rule_of_their_own() -> None:
    """A rule of one's own beats the default; the default beats nothing."""
    books = _Books(_session_factory()())
    books.rule("3")
    books.rule("8", salesman_id=books.asha)
    hers = books.invoice("SI-1", "1000.00", books.asha)
    his = books.invoice("SI-2", "1000.00", books.bala)
    books.receipt(hers, "100.00")
    books.receipt(his, "100.00")

    rows = books.report()
    assert rows[books.asha] == (Decimal("100.00"), Decimal("8.00"))
    assert rows[books.bala] == (Decimal("100.00"), Decimal("3.00"))


def test_a_firm_that_declared_no_rate_pays_nothing_and_still_reports() -> None:
    """No rule is not an error: the firm has agreed to pay nothing."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    books.receipt(invoice, "600.00")

    assert books.report()[books.asha] == (Decimal("600.00"), Decimal("0.00"))


def test_the_rate_in_force_is_the_one_the_money_arrived_under() -> None:
    """A window is judged on the settlement date, not on today.

    Two receipts against one invoice can fall either side of a rate change,
    which is why collections are rated row by row rather than summed first.
    """
    books = _Books(_session_factory()())
    books.rule(
        "10",
        salesman_id=books.asha,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 6, 30),
    )
    books.rule("4", salesman_id=books.asha, effective_from=date(2026, 7, 1))
    invoice = books.invoice("SI-1", "5000.00", books.asha)
    books.receipt(invoice, "1000.00", when=WHEN)
    books.receipt(invoice, "1000.00", when=LATER)

    # 10% of the April receipt plus 4% of the July one.
    assert books.report()[books.asha] == (Decimal("2000.00"), Decimal("140.00"))


def test_money_collected_before_a_rate_existed_earns_at_no_rate() -> None:
    """A rule that starts in July does not reach back into April."""
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha, effective_from=date(2026, 7, 1))
    invoice = books.invoice("SI-1", "5000.00", books.asha)
    books.receipt(invoice, "1000.00", when=WHEN)

    assert books.report()[books.asha] == (Decimal("1000.00"), Decimal("0.00"))


def test_an_inactive_rule_pays_nothing() -> None:
    """Status is the administrator's switch, and the window is history."""
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha, status=CommissionRuleStatusEnum.INACTIVE)
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    books.receipt(invoice, "500.00")

    assert books.report()[books.asha] == (Decimal("500.00"), Decimal("0.00"))


def test_the_period_is_read_against_the_day_the_money_arrived() -> None:
    """A receipt outside the reported window is outside the report."""
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha)
    invoice = books.invoice("SI-1", "5000.00", books.asha)
    books.receipt(invoice, "100.00", when=WHEN)
    books.receipt(invoice, "900.00", when=LATER)

    april = CommissionService(books.session).report(
        firm_id=books.firm.id,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
    )
    assert april.total_collected_amount == Decimal("100.00")
    assert april.total_commission_amount == Decimal("10.00")


def test_a_report_of_one_person_holds_only_that_person() -> None:
    """The salesman filter narrows the rows, not the arithmetic."""
    books = _Books(_session_factory()())
    books.rule("5", salesman_id=books.asha)
    books.rule("5", salesman_id=books.bala)
    books.receipt(books.invoice("SI-1", "1000.00", books.asha), "400.00")
    books.receipt(books.invoice("SI-2", "1000.00", books.bala), "600.00")

    rows = books.report(salesman_id=books.bala)
    assert set(rows) == {books.bala}
    assert rows[books.bala] == (Decimal("600.00"), Decimal("30.00"))


def test_a_report_names_the_salesman() -> None:
    """A row nobody can identify is a row nobody can act on."""
    books = _Books(_session_factory()())
    books.rule("5", salesman_id=books.asha)
    books.receipt(books.invoice("SI-1", "1000.00", books.asha), "400.00")

    result = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    assert result.rows[0].salesman_name == "Asha Rao"
    assert result.rows[0].invoice_count == 1


def test_a_second_active_rule_over_the_same_days_is_refused() -> None:
    """Two rates in force on one day leave the payout to query order."""
    books = _Books(_session_factory()())
    books.rule(
        "5",
        salesman_id=books.asha,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 9, 30),
    )

    with pytest.raises(ConflictError):
        books.rule("7", salesman_id=books.asha, effective_from=date(2026, 6, 1))

    # The same window for a different person, and for the firm-wide default,
    # are different scopes and must both be allowed.
    books.rule("7", salesman_id=books.bala, effective_from=date(2026, 6, 1))
    books.rule("1", effective_from=date(2026, 6, 1))


def test_an_edit_that_says_nothing_about_a_field_leaves_it_alone() -> None:
    """An omission is not an instruction.

    A write model that dumps in full has reset a status, a credit limit and a
    vendor's whole address book in this codebase already.
    """
    books = _Books(_session_factory()())
    rule = books.rule(
        "5",
        salesman_id=books.asha,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 9, 30),
    )

    CommissionService(books.session).update_rule(
        rule.id,
        CommissionRuleUpdate(percentage=Decimal("6")),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert rule.percentage == Decimal("6")
    assert rule.salesman_id == books.asha, "scope untouched"
    assert rule.effective_to == date(2026, 9, 30), "window untouched"
    assert rule.status == CommissionRuleStatusEnum.ACTIVE.value


def test_an_explicit_null_still_opens_the_window() -> None:
    """Absent means leave alone; null means clear. Both have to work."""
    books = _Books(_session_factory()())
    rule = books.rule(
        "5",
        salesman_id=books.asha,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 9, 30),
    )

    CommissionService(books.session).update_rule(
        rule.id,
        CommissionRuleUpdate(effective_to=None),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert rule.effective_to is None


def test_a_retired_rule_stops_paying_and_stays_on_the_record() -> None:
    """Soft delete, because the rule still explains what it already paid."""
    books = _Books(_session_factory()())
    rule = books.rule("10", salesman_id=books.asha)
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    books.receipt(invoice, "500.00")

    CommissionService(books.session).delete_rule(
        rule.id, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    assert rule.is_deleted is True
    assert books.report()[books.asha] == (Decimal("500.00"), Decimal("0.00"))


def test_a_backwards_period_is_refused() -> None:
    """A report to a date before its from-date is a typo, not an empty result."""
    books = _Books(_session_factory()())
    with pytest.raises(ValidationError):
        CommissionService(books.session).report(
            firm_id=books.firm.id,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 5, 1),
        )


def test_one_firm_cannot_see_another_firm_s_collections() -> None:
    """Firm scope is on every query, including the report's."""
    session = _session_factory()()
    books = _Books(session)
    other = _Books(session, code="OTHER")
    books.rule("10", salesman_id=books.asha)
    books.receipt(books.invoice("SI-1", "1000.00", books.asha), "500.00")

    assert (
        CommissionService(session)
        .report(firm_id=other.firm.id, from_date=YEAR[0], to_date=YEAR[1])
        .rows
        == []
    )


def test_every_rule_mutation_is_audited() -> None:
    """A rate change is a money decision, so it leaves a trail."""
    books = _Books(_session_factory()())
    rule = books.rule("5", salesman_id=books.asha)
    service = CommissionService(books.session)
    service.update_rule(
        rule.id,
        CommissionRuleUpdate(percentage=Decimal("6")),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    service.delete_rule(rule.id, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    actions = books.session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == rule.id)
    ).all()
    assert set(actions) == {
        "commission.rule.created",
        "commission.rule.updated",
        "commission.rule.deleted",
    }


# ----------------------------------------------------------------------
# The ladder
# ----------------------------------------------------------------------

#: A ladder a firm would actually agree: 2% to 100k, 3% to 200k, 5% above.
LADDER = [("0", "100000", "2"), ("100000", "200000", "3"), ("200000", None, "5")]


def _earned(books: "_Books", salesman_id: UUID) -> Decimal:
    """Return what one person earned across the whole year."""
    result = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    [row] = [row for row in result.rows if row.salesman_id == salesman_id]
    return row.commission_amount


def _collect(books: "_Books", number: str, amount: str, salesman_id: UUID) -> None:
    """Bill one amount and collect all of it."""
    books.receipt(books.invoice(number, amount, salesman_id), amount)


def test_a_marginal_ladder_charges_each_portion_at_its_own_rate() -> None:
    """The way income tax reads: 120,000 pays 2,000 on the first 100,000.

    Then 3% of the 20,000 above it, so 2,600 -- not 3,600.
    """
    books = _Books(_session_factory()())
    books.rule("0", salesman_id=books.asha, slabs=LADDER)
    _collect(books, "SI-1", "120000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("2600.00")


def test_a_whole_amount_ladder_charges_everything_at_the_rung_reached() -> None:
    """The more common incentive scheme, and the more motivating one.

    Crossing a threshold lifts everything already earned: the same 120,000
    pays 3% of all of it. A firm that means this and gets MARGINAL underpays
    by a third, which is why the mode is declared rather than inferred.
    """
    books = _Books(_session_factory()())
    books.rule(
        "0",
        salesman_id=books.asha,
        slab_mode=CommissionSlabModeEnum.WHOLE_AMOUNT,
        slabs=LADDER,
    )
    _collect(books, "SI-1", "120000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("3600.00")


def test_an_amount_landing_on_a_boundary_belongs_to_the_rung_above() -> None:
    """A rate quoted "from 100,000" pays at exactly 100,000, not below it.

    The bands are half-open, and the off-by-one here is a whole rung of
    somebody's money.
    """
    books = _Books(_session_factory()())
    books.rule(
        "0",
        salesman_id=books.asha,
        slab_mode=CommissionSlabModeEnum.WHOLE_AMOUNT,
        slabs=LADDER,
    )
    _collect(books, "SI-1", "100000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("3000.00")


def test_a_cap_limits_what_was_earned_and_not_what_was_sold() -> None:
    """Capping the subtotal first would push it down a rung and pay less.

    250,000 on the ladder earns 2,000 + 3,000 + 2,500 = 7,500, capped to
    5,000. Capping the *value* instead would move the arithmetic onto a lower
    rung and answer something else entirely -- the ceiling a firm agrees is on
    the payout, not on the trading.
    """
    books = _Books(_session_factory()())
    books.rule(
        "0",
        salesman_id=books.asha,
        slabs=LADDER,
        max_commission_amount=Decimal("5000"),
    )
    _collect(books, "SI-1", "250000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("5000.00")


def test_a_cap_nobody_reached_leaves_a_smaller_earning_alone() -> None:
    """A ceiling that did not bite changes nothing."""
    books = _Books(_session_factory()())
    books.rule(
        "0",
        salesman_id=books.asha,
        slabs=LADDER,
        max_commission_amount=Decimal("5000"),
    )
    _collect(books, "SI-1", "50000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("1000.00")


def test_a_rule_with_no_ladder_still_pays_its_flat_rate() -> None:
    """Every rule written before slabs existed keeps its arrangement."""
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha)
    _collect(books, "SI-1", "1000.00", books.asha)

    assert _earned(books, books.asha) == Decimal("100.00")


@pytest.mark.parametrize(
    ("slabs", "because"),
    [
        (
            [("0", "100", "2"), ("200", None, "3")],
            "a gap is an amount the rule cannot answer for",
        ),
        (
            [("0", "100", "2"), ("50", None, "3")],
            "an overlap is two answers to one question",
        ),
        (
            [("1000", None, "2")],
            "a ladder starting above zero leaves the first rupee uncovered",
        ),
        (
            [("0", None, "2"), ("100", None, "3")],
            "only the highest rung may be open-ended",
        ),
    ],
)
def test_a_ladder_that_is_not_whole_is_refused(
    slabs: list[tuple[str, str | None, str]], because: str
) -> None:
    """Each of these would leave a payout to whichever rung was read first."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.rule("0", salesman_id=books.asha, slabs=slabs)


def test_an_invoiced_rule_pays_on_what_was_billed() -> None:
    """Some firms pay a salaried team on sales value, not on collections.

    Both figures are still reported -- a firm paying one way still wants to
    see the other -- but only the declared basis earns.
    """
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha, basis=CommissionBasisEnum.INVOICED)
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    books.receipt(invoice, "400.00")

    result = CommissionService(books.session).report(
        firm_id=books.firm.id, from_date=YEAR[0], to_date=YEAR[1]
    )
    [row] = result.rows
    assert row.invoiced_amount == Decimal("1000.00")
    assert row.collected_amount == Decimal("400.00")
    assert row.basis == "INVOICED"
    # 10% of what was billed, not of what arrived.
    assert row.commission_amount == Decimal("100.00")


def test_money_measured_the_other_way_earns_nothing() -> None:
    """A rule pays one way, so one sale is never paid for twice.

    The overlap guard already refuses a second live rule over the same person
    and days whatever its basis; this is the belt to that brace.
    """
    books = _Books(_session_factory()())
    books.rule("10", salesman_id=books.asha, basis=CommissionBasisEnum.COLLECTED)
    invoice = books.invoice("SI-1", "1000.00", books.asha)
    books.receipt(invoice, "1000.00")

    assert _earned(books, books.asha) == Decimal("100.00")


def test_a_rate_change_runs_each_ladder_on_its_own_subtotal() -> None:
    """A slab is a function of the value earned under *one* arrangement.

    April's 60,000 and July's 60,000 fall either side of a rate change, so
    each is measured against the ladder in force when the money arrived.
    Pooling them would carry April's volume into July's thresholds and pay a
    rung nobody agreed.
    """
    books = _Books(_session_factory()())
    ladder = [("0", "100000", "2"), ("100000", None, "10")]
    books.rule(
        "0",
        salesman_id=books.asha,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 6, 30),
        slabs=ladder,
    )
    books.rule(
        "0",
        salesman_id=books.asha,
        effective_from=date(2026, 7, 1),
        slabs=ladder,
    )
    books.receipt(books.invoice("SI-1", "60000.00", books.asha), "60000.00", when=WHEN)
    books.receipt(books.invoice("SI-2", "60000.00", books.asha), "60000.00", when=LATER)

    # 2% of 60,000 twice. Pooled, the second 20,000 would have earned 10%.
    assert _earned(books, books.asha) == Decimal("2400.00")


def test_saving_a_ladder_replaces_the_one_before_it() -> None:
    """A ladder is one arrangement, so a rung is never merged by position.

    Reconciled instead, an edit that removes the top band would leave it in
    force and keep paying a rate the firm has withdrawn.
    """
    books = _Books(_session_factory()())
    rule = books.rule("0", salesman_id=books.asha, slabs=LADDER)
    service = CommissionService(books.session)
    service.update_rule(
        rule.id,
        CommissionRuleUpdate(
            slabs=[
                CommissionSlabWrite(from_amount=Decimal("0"), percentage=Decimal("1"))
            ]
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    [only] = service.slabs_of(rule)
    assert only.to_amount is None
    _collect(books, "SI-1", "250000.00", books.asha)
    assert _earned(books, books.asha) == Decimal("2500.00")


def test_an_omitted_ladder_is_left_alone() -> None:
    """Absent means leave alone; an empty list means go back to a flat rate."""
    books = _Books(_session_factory()())
    rule = books.rule("0", salesman_id=books.asha, slabs=LADDER)
    service = CommissionService(books.session)
    service.update_rule(
        rule.id,
        CommissionRuleUpdate(max_commission_amount=Decimal("9999")),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert len(service.slabs_of(rule)) == 3

    service.update_rule(
        rule.id,
        CommissionRuleUpdate(percentage=Decimal("4"), slabs=[]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert service.slabs_of(rule) == []
    _collect(books, "SI-1", "1000.00", books.asha)
    assert _earned(books, books.asha) == Decimal("40.00")
