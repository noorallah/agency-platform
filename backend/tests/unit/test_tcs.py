"""Tax collected at source, on the money rather than on the bill.

206C(1H) is charged on consideration **received**, so every case here is about
a receipt, not an invoice. The ones that decide whether the figure can be
defended:

- only the part of a receipt **above** the threshold is charged, so a receipt
  straddling the line pays on the excess and no more;
- the threshold is per buyer, per financial year, and the running total is
  **summed from the receipts** rather than kept as a counter, so a reversal
  cannot leave the two disagreeing;
- a firm below the turnover threshold, or one that has not switched the section
  on, collects nothing at all;
- and the tax **raises** what the buyer owes, because it is owed on top of the
  money they have just paid.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.finance.models import JournalLine
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import PaymentService, ReceiptService, RefundService
from app.tcs.models import TcsCollection, TcsCollectionStatus
from app.tcs.schemas import TcsSettingsWrite
from app.tcs.services import TcsService
from app.vendors.models import Vendor

WHEN = date(2026, 6, 10)
#: Fifty lakh, the figure the section names.
THRESHOLD = Decimal("5000000")


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
    """A firm in scope, with a buyer who has a PAN and one who has not."""

    def __init__(self, session: Session, *, enabled: bool = True) -> None:
        """Seed the firm, its chart, and two buyers."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Collecting Firm",
            code="TCS",
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
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
            pan_number="AAACR5055K",
        )
        self.anonymous = Customer(
            firm_id=self.firm.id,
            code="C2",
            customer_type="BUSINESS",
            name="No PAN Traders",
            display_name="No PAN Traders",
            currency_code="INR",
            status="ACTIVE",
        )
        session.add_all([self.customer, self.anonymous])
        session.commit()
        if enabled:
            self.enable()

    def enable(self, **overrides: object) -> None:
        """Put the firm in scope and switch the section on."""
        payload = {
            "is_enabled": True,
            "preceding_year_turnover": Decimal("150000000"),
        }
        payload.update(overrides)
        TcsService(self.session).write_settings(
            self.firm.id,
            TcsSettingsWrite(**payload),  # type: ignore[arg-type]
            actor_id=self.actor_id,
        )

    def receipt(
        self,
        amount: str,
        *,
        customer: Customer | None = None,
        on: date = WHEN,
    ) -> UUID:
        """Take money in, which is what raises the tax."""
        buyer = customer or self.customer
        row = ReceiptService(self.session).create(
            SettlementCreate(
                party_id=buyer.id,
                settlement_date=on,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                allocations=[],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row.id

    def collection(self, settlement_id: UUID) -> TcsCollection | None:
        """Return what was collected on one receipt, if anything."""
        return self.session.scalar(
            select(TcsCollection).where(
                TcsCollection.settlement_id == settlement_id,
                TcsCollection.is_deleted.is_(False),
            )
        )


def test_nothing_is_collected_below_the_threshold() -> None:
    """The first fifty lakh a buyer pays in the year attracts nothing."""
    books = _Books(_session_factory()())

    assert books.collection(books.receipt("1000000")) is None


def test_only_the_part_above_the_threshold_is_charged() -> None:
    """A receipt straddling the line pays on the excess and no more.

    Charging the whole receipt is the obvious mistake, and it over-collects by
    the entire remaining headroom -- here by 48 lakh, on a receipt of 52.
    """
    books = _Books(_session_factory()())
    books.receipt("4800000")

    row = books.collection(books.receipt("400000"))

    assert row is not None
    # 48 lakh already paid, 4 lakh now: 2 lakh of headroom left, so 2 lakh is
    # chargeable at 0.1%.
    assert row.cumulative_before == Decimal("4800000.00")
    assert row.taxable_amount == Decimal("200000.00")
    assert row.tcs_amount == Decimal("200.00")


def test_every_later_receipt_is_charged_in_full() -> None:
    """Once the buyer is past the threshold the headroom is gone."""
    books = _Books(_session_factory()())
    books.receipt("6000000")

    row = books.collection(books.receipt("100000"))

    assert row is not None
    assert row.taxable_amount == Decimal("100000.00")
    assert row.tcs_amount == Decimal("100.00")


def test_a_receipt_is_not_counted_as_money_paid_before_itself() -> None:
    """The running total excludes the receipt being charged.

    Counting it would make the first receipt over the threshold pay on itself
    twice over -- once as consideration and once as prior consideration.
    """
    books = _Books(_session_factory()())

    row = books.collection(books.receipt("6000000"))

    assert row is not None
    assert row.cumulative_before == Decimal("0.00")
    # Six crore less fifty lakh of headroom is one crore chargeable.
    assert row.taxable_amount == Decimal("1000000.00")


def test_a_buyer_with_no_pan_is_charged_the_higher_rate() -> None:
    """Section 206CC, on the same collection."""
    books = _Books(_session_factory()())

    row = books.collection(books.receipt("6000000", customer=books.anonymous))

    assert row is not None
    assert row.without_pan is True
    assert row.rate_percent == Decimal("1.000")
    assert row.tcs_amount == Decimal("10000.00")


def test_a_firm_below_the_turnover_threshold_collects_nothing() -> None:
    """The section applies to a seller, before it applies to any buyer."""
    books = _Books(_session_factory()(), enabled=False)
    books.enable(preceding_year_turnover=Decimal("50000000"))

    assert books.collection(books.receipt("6000000")) is None


def test_a_firm_that_has_not_switched_it_on_collects_nothing() -> None:
    """Shipping this must charge nobody until a firm asks for it."""
    books = _Books(_session_factory()(), enabled=False)

    assert books.collection(books.receipt("6000000")) is None


def test_the_tax_raises_what_the_buyer_owes() -> None:
    """It is owed **on top of** the money just paid.

    Taking it out of the receipt would leave the firm short by the tax on
    every collection, and would say the buyer had settled something they had
    not been billed for.
    """
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("8000000.00")
    books.session.commit()

    books.receipt("6000000")
    books.session.refresh(books.customer)

    # Eighty lakh less the sixty received, plus a thousand of tax now owed.
    assert books.customer.current_outstanding == Decimal("2001000.0000")


def test_the_collection_posts_to_the_ledger() -> None:
    """`Dr Accounts Receivable / Cr TCS Payable`, and it balances."""
    books = _Books(_session_factory()())

    row = books.collection(books.receipt("6000000"))

    assert row is not None
    assert row.journal_entry_id is not None
    legs = books.session.scalars(
        select(JournalLine).where(JournalLine.journal_entry_id == row.journal_entry_id)
    ).all()
    assert sum(Decimal(str(leg.debit_amount)) for leg in legs) == Decimal("1000.00")
    assert sum(Decimal(str(leg.credit_amount)) for leg in legs) == Decimal("1000.00")


def test_reversing_the_receipt_takes_the_tax_back() -> None:
    """The money is going back, so the tax collected on it goes back too."""
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("8000000.00")
    books.session.commit()
    settlement_id = books.receipt("6000000")

    ReceiptService(books.session).reverse(
        settlement_id,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="Cheque returned.",
    )
    books.session.commit()
    books.session.refresh(books.customer)
    row = books.collection(settlement_id)

    assert row is not None
    # Mirrored rather than deleted: a quarterly return may already have
    # reported it.
    assert row.status == TcsCollectionStatus.REVERSED.value
    assert row.reversal_journal_entry_id is not None
    assert books.customer.current_outstanding == Decimal("8000000.0000")


def test_a_reversed_receipt_stops_counting_towards_the_threshold() -> None:
    """It is money the firm does not have.

    Summed from the receipts rather than held as a counter, which is what
    makes this true without a second place to keep in step.
    """
    books = _Books(_session_factory()())
    first = books.receipt("4800000")
    ReceiptService(books.session).reverse(
        first, firm_id=books.firm.id, actor_id=books.actor_id, reason="Bounced."
    )
    books.session.commit()

    # With the first receipt reversed the buyer is back at nothing paid, so
    # this one is inside the threshold and attracts nothing.
    assert books.collection(books.receipt("400000")) is None


def test_the_threshold_resets_with_the_financial_year() -> None:
    """And it is the firm's own year, not the calendar's."""
    books = _Books(_session_factory()())
    # A second year, so both receipts land in an open period.
    seed_finance_setup(
        books.session,
        firm_id=books.firm.id,
        year_starts_on=date(2027, 4, 1),
        actor_id=books.actor_id,
    )
    books.receipt("6000000", on=date(2027, 3, 20))

    # The firm's year starts on 1 April, so a March receipt belongs to the
    # year ending and this one starts the count again.
    row = books.collection(books.receipt("400000", on=date(2027, 4, 5)))

    assert row is None


def test_a_preview_says_why_nothing_is_due() -> None:
    """A bare zero says too little.

    It cannot tell a buyer under the threshold from a firm that does not
    collect at all, and the two want different conversations.
    """
    books = _Books(_session_factory()(), enabled=False)

    answer = TcsService(books.session).preview(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        amount=Decimal("6000000"),
        on=WHEN,
    )

    assert answer.applicable is False
    assert "does not collect" in answer.reason


def test_a_preview_answers_before_the_receipt_exists() -> None:
    """Which is the point: the figure is needed when the money is asked for."""
    books = _Books(_session_factory()())
    books.receipt("4800000")

    answer = TcsService(books.session).preview(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        amount=Decimal("400000"),
        on=WHEN,
    )

    assert answer.applicable is True
    assert answer.taxable_amount == Decimal("200000.00")
    assert answer.tcs_amount == Decimal("200.00")


def test_settings_leave_an_omitted_field_alone() -> None:
    """A write model that dumps in full turns an omission into an instruction.

    Here it would reset a rate or a threshold a Finance Act had moved.
    """
    books = _Books(_session_factory()())
    service = TcsService(books.session)
    service.write_settings(
        books.firm.id,
        TcsSettingsWrite(rate_percent=Decimal("0.075")),
        actor_id=books.actor_id,
    )

    service.write_settings(
        books.firm.id,
        TcsSettingsWrite(threshold_amount=Decimal("7500000")),
        actor_id=books.actor_id,
    )
    answer = service.read_settings(books.firm.id)

    assert answer.rate_percent == Decimal("0.075")
    assert answer.threshold_amount == Decimal("7500000.00")
    assert answer.is_enabled is True


def test_a_firm_with_no_settings_reads_the_sections_own_defaults() -> None:
    """Not nulls: the screen has to show the rule the firm would be under."""
    books = _Books(_session_factory()(), enabled=False)

    answer = TcsService(books.session).read_settings(books.firm.id)

    assert answer.is_enabled is False
    assert answer.seller_in_scope is False
    assert answer.threshold_amount == THRESHOLD
    assert answer.rate_percent == Decimal("0.1")


def test_a_negative_receipt_is_refused_by_the_preview() -> None:
    """The same guard every amount in this repo carries."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        TcsService(books.session).preview(
            firm_id=books.firm.id,
            customer_id=books.customer.id,
            amount=Decimal("-1"),
            on=WHEN,
        )


def test_one_firm_s_receipts_never_count_towards_another_s_threshold() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    books.receipt("6000000")

    with pytest.raises(ResourceNotFoundError):
        # The customer belongs to this firm, so asking about them under
        # another firm's scope must not answer at all.
        TcsService(books.session).preview(
            firm_id=uuid4(),
            customer_id=books.customer.id,
            amount=Decimal("100000"),
            on=WHEN,
        )


def test_a_collection_records_why_the_number_is_what_it_is() -> None:
    """Re-deriving it against today's settings would answer about today."""
    books = _Books(_session_factory()())
    books.receipt("4800000")

    row = books.collection(books.receipt("400000"))

    assert row is not None
    assert row.consideration_amount == Decimal("400000.00")
    assert row.cumulative_before == Decimal("4800000.00")
    assert row.taxable_amount == Decimal("200000.00")
    assert row.rate_percent == Decimal("0.100")
    assert row.financial_year_start == date(2026, 4, 1)


def test_a_receipt_that_clears_invoices_is_still_charged_on_all_of_it() -> None:
    """The section says consideration received, whatever it settles."""
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("8000000.00")
    books.session.commit()

    row = books.collection(books.receipt("6000000"))

    assert row is not None
    assert row.consideration_amount == Decimal("6000000.00")


def test_money_going_out_is_never_charged() -> None:
    """A payment to a vendor is not consideration received.

    Driven rather than asserted about, because the direction check is one
    line and a test that never raises a payment cannot see it disappear.
    """
    books = _Books(_session_factory()())
    vendor = Vendor(
        firm_id=books.firm.id,
        code="V1",
        name="Packaging Supplier",
        display_name="Packaging Supplier",
        status="ACTIVE",
    )
    books.session.add(vendor)
    books.session.commit()

    paid = PaymentService(books.session).create(
        SettlementCreate(
            party_id=vendor.id,
            settlement_date=WHEN,
            amount=Decimal("6000000"),
            method=SettlementMethodEnum.BANK,
            allocations=[],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.collection(paid.id) is None


def test_a_refund_takes_the_buyer_back_below_the_threshold() -> None:
    """A refund hands back money the buyer had paid in.

    Leaving it in the running total would keep them over the threshold on
    money they no longer have with the firm, and every later receipt would be
    charged on consideration the firm had already returned.
    """
    books = _Books(_session_factory()())
    books.receipt("4800000")
    RefundService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("4800000"),
            method=SettlementMethodEnum.BANK,
            allocations=[],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.collection(books.receipt("400000")) is None


def test_the_register_names_the_buyer_and_the_receipt() -> None:
    """A grid of ids is a grid nobody can read.

    The question somebody brings to this list is "who, and against which
    receipt", and both were null on every row until they were resolved.
    """
    books = _Books(_session_factory()())
    settlement_id = books.receipt("6000000")

    service = TcsService(books.session)
    rows, total = service.list_collections(firm_id=books.firm.id)
    described = service.describe(rows)

    assert total == 1
    assert described[0].customer_name == "Kumar Stores"
    assert described[0].settlement_number is not None
    assert described[0].settlement_id == settlement_id
