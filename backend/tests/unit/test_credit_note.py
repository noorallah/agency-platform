"""A credit note that reverses the tax it charged.

A credit note already existed, as a bare row in
`customer_receivable_transactions`. It reduced what the customer owed and
reversed **no output tax at all** -- so a firm agreeing a rate difference
after invoicing credited the customer the gross amount and went on declaring
tax on a price nobody paid.

These are the cases that decide whether the document that closes it can be
trusted:

- the tax comes off at the rate the **invoice** charged, not at today's;
- nothing can be credited twice, or credited beyond what was charged;
- approving posts *and* moves the balance, and cancelling undoes both.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.credit_note.models import CreditNote, CreditNoteStatus
from app.credit_note.schemas import (
    CreditNoteCreate,
    CreditNoteLineWrite,
    CreditNoteReasonEnum,
    CreditNoteUpdate,
)
from app.credit_note.services import CreditNoteService
from app.customers.models import Customer
from app.finance.models import JournalEntry, JournalLine
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.products.models import Product
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine

WHEN = date(2026, 4, 20)


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
    """A firm with a chart, a customer and one approved invoice."""

    def __init__(
        self, session: Session, *, freight: str = "0", charges: str = "0"
    ) -> None:
        """Seed everything a credit note needs to have something to credit."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Credit Firm",
            code="CRED",
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
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Customer One",
            display_name="Customer One",
            currency_code="INR",
            status="ACTIVE",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Product One",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add_all([self.branch, self.customer, self.product])
        session.commit()
        self.invoice, self.line = self._invoice(freight=freight, charges=charges)

    def _invoice(
        self, *, freight: str = "0", charges: str = "0"
    ) -> tuple[SalesInvoice, SalesInvoiceLine]:
        """Bill 10 at 100 with 18% tax, and approve it.

        `freight` and `charges` are part of what the line was taxed on --
        `SalesInvoiceService._line_net_amount` adds both to the base -- so a
        test about what may be credited has to be able to put them there.
        """
        invoice = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            invoice_number="SI-1",
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal("1180.00"),
        )
        self.session.add(invoice)
        self.session.flush()
        line = SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=self.firm.id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=uuid4(),
            source_document_number="SO-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=self.product.id,
            delivered_quantity=Decimal("10"),
            current_invoice_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            gross_amount=Decimal("1000"),
            freight_amount=Decimal(freight),
            charges_amount=Decimal(charges),
            # 18% of everything the invoice taxes: gross less discounts, plus
            # the delivery charge and the line charges.
            tax_amount=(
                (Decimal("1000") + Decimal(freight) + Decimal(charges))
                * Decimal("18")
                / Decimal("100")
            ),
            net_amount=Decimal("1180"),
        )
        self.session.add(line)
        self.session.commit()
        return invoice, line

    def note(
        self,
        taxable: str = "100",
        *,
        reason: CreditNoteReasonEnum = CreditNoteReasonEnum.RATE_DIFFERENCE,
    ) -> CreditNote:
        """Raise one credit note against the invoice line."""
        row = CreditNoteService(self.session).create_note(
            CreditNoteCreate(
                sales_invoice_id=self.invoice.id,
                credit_note_date=WHEN,
                reason=reason,
                lines=[
                    CreditNoteLineWrite(
                        sales_invoice_line_id=self.line.id,
                        line_number=1,
                        quantity=Decimal("10"),
                        taxable_amount=Decimal(taxable),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Resolve one of the firm's control accounts."""
        from app.finance.models import FirmControlAccount

        account_id = self.session.scalar(
            select(FirmControlAccount.ledger_account_id).where(
                FirmControlAccount.firm_id == self.firm.id,
                FirmControlAccount.purpose == purpose.value,
                FirmControlAccount.is_deleted.is_(False),
            )
        )
        assert account_id is not None, f"{purpose.value} is not mapped"
        return account_id

    def legs(self, entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return one journal's lines, by account."""
        return {
            line.ledger_account_id: (line.debit_amount, line.credit_amount)
            for line in self.session.scalars(
                select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
            ).all()
        }


def test_the_tax_comes_off_at_the_rate_the_invoice_charged() -> None:
    """The whole reason this document names an invoice line.

    100 credited against a line taxed at 18% reverses 18 of tax. Reading the
    rate off the tax profile instead would let an edit in September change
    what comes off a March supply -- the same fault the invoice's own
    inheritance rule exists to prevent, one document later.
    """
    books = _Books(_session_factory()())

    note = books.note("100")

    assert note.taxable_amount == Decimal("100.00")
    assert note.tax_amount == Decimal("18.00")
    assert note.total_amount == Decimal("118.00")


def test_a_line_taxed_at_nothing_reverses_nothing() -> None:
    """An exempt supply has no tax to give back."""
    books = _Books(_session_factory()())
    books.line.tax_amount = Decimal("0")
    books.session.commit()

    note = books.note("100")

    assert note.tax_amount == Decimal("0.00")
    assert note.total_amount == Decimal("100.00")


def test_approving_posts_the_credit_the_tax_and_the_receivable() -> None:
    """Three legs, and the third is the point.

    The bare receivable adjustment posts two and reverses no tax at all, so a
    firm crediting a rate difference kept declaring tax on a price nobody
    paid.
    """
    books = _Books(_session_factory()())
    note = books.note("100")

    approved = CreditNoteService(books.session).approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    assert approved.status == CreditNoteStatus.APPROVED.value
    assert approved.journal_entry_id is not None
    legs = books.legs(approved.journal_entry_id)
    assert legs[books.account(ControlAccountPurpose.SALES_RETURNS)] == (
        Decimal("100.00"),
        Decimal("0.00"),
    )
    assert legs[books.account(ControlAccountPurpose.OUTPUT_TAX)] == (
        Decimal("18.00"),
        Decimal("0.00"),
    )
    assert legs[books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE)] == (
        Decimal("0.00"),
        Decimal("118.00"),
    )


def test_approving_also_reduces_what_the_customer_owes() -> None:
    """Both books, or neither.

    A credit note that posted to the ledger and left the customer's balance
    alone would drive the subsidiary ledger and the general one apart by its
    value -- which is the defect the lower-level receivable path is documented
    as still having on its own.
    """
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("1180.00")
    books.session.commit()
    note = books.note("100")

    CreditNoteService(books.session).approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    books.session.refresh(books.customer)

    assert books.customer.current_outstanding == Decimal("1062.0000")


def test_cancelling_reverses_the_journal_and_the_balance() -> None:
    """A posted entry is history; it is mirrored, never deleted."""
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("1180.00")
    books.session.commit()
    note = books.note("100")
    service = CreditNoteService(books.session)
    approved = service.approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    original = approved.journal_entry_id

    service.cancel_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    books.session.refresh(books.customer)

    mirror = books.session.scalars(
        select(JournalEntry).where(JournalEntry.reversal_of_id == original)
    ).one()
    legs = books.legs(mirror.id)
    assert legs[books.account(ControlAccountPurpose.OUTPUT_TAX)] == (
        Decimal("0.00"),
        Decimal("18.00"),
    )
    assert books.customer.current_outstanding == Decimal("1180.0000")


def test_a_line_cannot_be_credited_beyond_what_it_was_charged() -> None:
    """Crediting more than was charged is money the firm never took."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        books.note("1001")


def test_the_cap_counts_what_other_credit_notes_already_took() -> None:
    """Two notes of 600 against a line charged 1000 is 200 too much.

    Each is legal alone, which is exactly why the cap has to look at the
    others rather than at this note in isolation.
    """
    books = _Books(_session_factory()())
    books.note("600")

    with pytest.raises(ValidationError):
        books.note("600")


def test_a_cancelled_note_releases_what_it_had_claimed() -> None:
    """Otherwise a note raised in error would block the corrected one."""
    books = _Books(_session_factory()())
    first = books.note("600")
    CreditNoteService(books.session).cancel_note(
        first.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    second = books.note("600")

    assert second.taxable_amount == Decimal("600.00")


def test_the_taxable_base_excludes_the_tax_already_on_the_line() -> None:
    """The cap is what was charged before tax, not the line's net amount.

    `net_amount` includes the tax, so capping on it would let a credit note
    credit the tax twice -- once inside the taxable value and once as the
    reversal beside it. The line was charged 1000 and billed 1180.
    """
    books = _Books(_session_factory()())

    note = books.note("1000")

    assert note.taxable_amount == Decimal("1000.00")
    with pytest.raises(ValidationError):
        books.note("1")


def test_a_draft_invoice_cannot_be_credited() -> None:
    """A draft is not a sale, so there is nothing to credit."""
    books = _Books(_session_factory()())
    books.invoice.status = "DRAFT"
    books.session.commit()

    with pytest.raises(ValidationError):
        books.note("100")


def test_a_line_outside_the_invoice_is_refused() -> None:
    """A credit note credits the supply it names, and only that one."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        CreditNoteService(books.session).create_note(
            CreditNoteCreate(
                sales_invoice_id=books.invoice.id,
                credit_note_date=WHEN,
                lines=[
                    CreditNoteLineWrite(
                        sales_invoice_line_id=uuid4(),
                        line_number=1,
                        taxable_amount=Decimal("100"),
                    )
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_approved_note_cannot_be_edited() -> None:
    """The journal is posted; changing the record would leave the two apart."""
    books = _Books(_session_factory()())
    note = books.note("100")
    service = CreditNoteService(books.session)
    service.approve_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()

    with pytest.raises(ValidationError):
        service.update_note(
            note.id,
            CreditNoteUpdate(remarks="late"),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_one_firm_s_credit_notes_are_invisible_to_another() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    books.note("100")

    rows, total = CreditNoteService(books.session).list_notes(
        firm_scope=uuid4(), page=1, page_size=20
    )

    assert total == 0
    assert rows == []


def test_a_credit_running_to_a_fraction_of_a_paisa_still_posts() -> None:
    """The receivable ledger carries two decimals; a document carries four.

    `sales_invoice` hit this and fixed it privately, `sales_return` carried
    the identical defect untouched, and this was the third copy -- an approved
    credit note whose total ran past two decimals raised a pydantic error
    rather than posting, so the whole approval failed. Invisible until a
    seeded credit note reached it, which is what the demo history is for.
    """
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("1180.00")
    books.session.commit()
    # 231.66 plus 18% is 273.3588 -- four decimals, which the receivable
    # ledger's schema refuses outright.
    note = books.note("231.66")

    CreditNoteService(books.session).approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    books.session.refresh(books.customer)

    # And rounded the way the journal rounded it, so the two books agree.
    assert books.customer.current_outstanding == Decimal("906.6400")


def test_the_receivable_and_the_journal_credit_the_same_amount() -> None:
    """Rounding a sum is not always rounding the parts.

    The journal rounds the taxable value and the tax separately and adds
    them; a receivable rounding the document total instead can land a paisa
    away, and nothing then says which of the two books is right.
    """
    books = _Books(_session_factory()())
    books.customer.current_outstanding = Decimal("10000.00")
    books.session.commit()
    note = books.note("231.665")

    CreditNoteService(books.session).approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    books.session.refresh(books.customer)
    row = books.session.get(CreditNote, note.id)
    assert row is not None
    receivable_credit = Decimal("10000.00") - books.customer.current_outstanding
    posted = books.session.scalars(
        select(JournalLine).where(JournalLine.journal_entry_id == row.journal_entry_id)
    ).all()
    ledger_credit = sum(
        (Decimal(str(leg.credit_amount)) for leg in posted), Decimal("0")
    )

    assert receivable_credit == ledger_credit


# ---------------------------------------------------------------------------
# What a line was charged, when the charge included delivery
# ---------------------------------------------------------------------------
#
# Found by the 2026-09-03 module review. `_charged_taxable` returned
# `gross - discount - bill_discount`, which was the whole taxable value until
# #191 put freight inside it. `SalesInvoiceService` taxes
# `gross - discounts + charges_amount + freight_amount`, so the credit note
# was working from a smaller base than the tax it is reversing was computed
# on.


def _freighted() -> "_Books":
    """Build a firm whose invoice line carries 50 of delivery, taxed with it."""
    return _Books(_session_factory()(), freight="50")


def test_a_line_may_be_credited_for_the_delivery_it_was_charged() -> None:
    """The cap is what the customer was charged, delivery included.

    A line of 1,000 with 50 of delivery was taxed on 1,050, so 1,050 is what
    a full credit has to be able to take back. The cap stopped at 1,000 and
    refused the rest -- a customer who returns the lot could not be credited
    what they paid.
    """
    books = _freighted()

    note = CreditNoteService(books.session).create_note(
        CreditNoteCreate(
            sales_invoice_id=books.invoice.id,
            credit_note_date=WHEN,
            reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=books.line.id,
                    line_number=1,
                    quantity=Decimal("10"),
                    taxable_amount=Decimal("1050"),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    assert note is not None


def test_the_rate_is_read_off_the_base_the_tax_was_charged_on() -> None:
    """Delivery in the denominator, or the reversal is too big.

    Tax of 189 was charged on 1,050. Dividing it by 1,000 gives 18.9%, so
    crediting 1,000 reversed 189 of output tax where 180 was charged on that
    part of the supply -- more tax handed back than was ever collected on it.
    """
    books = _freighted()

    note = CreditNoteService(books.session).create_note(
        CreditNoteCreate(
            sales_invoice_id=books.invoice.id,
            credit_note_date=WHEN,
            reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=books.line.id,
                    line_number=1,
                    quantity=Decimal("10"),
                    taxable_amount=Decimal("1000"),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    assert Decimal(str(note.tax_amount)) == Decimal("180.0000")


def test_line_charges_count_the_same_way() -> None:
    """`charges_amount` is inside the base too, and was left out with it."""
    books = _Books(_session_factory()(), charges="100")

    note = CreditNoteService(books.session).create_note(
        CreditNoteCreate(
            sales_invoice_id=books.invoice.id,
            credit_note_date=WHEN,
            reason=CreditNoteReasonEnum.RATE_DIFFERENCE,
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=books.line.id,
                    line_number=1,
                    quantity=Decimal("10"),
                    taxable_amount=Decimal("1100"),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )

    assert Decimal(str(note.tax_amount)) == Decimal("198.0000")
