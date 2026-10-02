"""A debit note to a supplier: a claim with no goods going back (backlog 65 row 6).

The purchasing mirror of `test_credit_note.py`. The cases that decide whether
it can be trusted:

- the input tax comes off at the rate the **bill** charged, split by GST head
  the way the bill claimed it;
- nothing can be claimed beyond what is left of a bill line, net of earlier
  debit notes and purchase returns;
- approving posts a balanced journal *and* the bill owes less, and cancelling
  undoes both;
- the status is never writable through an update.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.debit_note.models import DebitNote, DebitNoteStatus
from app.debit_note.schemas import (
    DebitNoteCreate,
    DebitNoteLineWrite,
    DebitNoteReasonEnum,
    DebitNoteUpdate,
)
from app.debit_note.services import DebitNoteService
from app.document_framework.models import DocumentLifecycleEvent
from app.finance.models import JournalEntry, JournalLine
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    ControlAccountService,
)
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.gst_returns.services.gstr_service import GstReturnService
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES
from app.products.models import Product
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.settlements.services import PaymentService
from app.vendors.models import Vendor

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

WHEN = date(2026, 4, 20)


def _session() -> Session:
    """Create one shared in-memory database and open a session on it."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _Books:
    """A firm with a chart, a supplier and one approved bill of 10 at 100 + 18%."""

    def __init__(self) -> None:
        """Seed everything a debit note needs to have something to claim."""
        self.session = _session()
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Debit Firm",
            code="DEBT",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        seed_finance_setup(
            self.session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor_id,
        )
        self.vendor = Vendor(
            firm_id=self.firm.id,
            code="V1",
            name="Vendor One",
            display_name="Vendor One",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Product One",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.session.add_all([self.vendor, self.product])
        self.session.commit()
        self.invoice = PurchaseInvoice(
            firm_id=self.firm.id,
            vendor_id=self.vendor.id,
            branch_id=uuid4(),
            invoice_number="PI-1",
            invoice_date=WHEN,
            supplier_invoice_number="SUP-1",
            supplier_invoice_date=WHEN,
            status="APPROVED",
            subtotal=Decimal("1000"),
            tax_total=Decimal("180"),
            grand_total=Decimal("1180"),
        )
        self.session.add(self.invoice)
        self.session.flush()
        self.line = PurchaseInvoiceLine(
            purchase_invoice_id=self.invoice.id,
            firm_id=self.firm.id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=uuid4(),
            source_document_number="GRN-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=self.product.id,
            received_quantity=Decimal("10"),
            current_invoice_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            gross_amount=Decimal("1000"),
            tax_amount=Decimal("180"),
            net_amount=Decimal("1180"),
        )
        self.session.add(self.line)
        self.session.flush()
        for sequence, code in enumerate(("CGST", "SGST"), start=1):
            self.session.add(
                PurchaseInvoiceLineTax(
                    purchase_invoice_line_id=self.line.id,
                    firm_id=self.firm.id,
                    sequence=sequence,
                    component_code=code,
                    component_label=code,
                    percentage=Decimal("9"),
                    base_amount=Decimal("1000"),
                    amount=Decimal("90"),
                )
            )
        self.session.commit()

    def payload(
        self,
        taxable: str = "100",
        *,
        reason: DebitNoteReasonEnum = DebitNoteReasonEnum.PRICE_DIFFERENCE,
    ) -> DebitNoteCreate:
        """Describe one debit note against the bill line."""
        return DebitNoteCreate(
            purchase_invoice_id=self.invoice.id,
            debit_note_date=WHEN,
            reason=reason,
            lines=[
                DebitNoteLineWrite(
                    purchase_invoice_line_id=self.line.id,
                    line_number=1,
                    taxable_amount=Decimal(taxable),
                )
            ],
        )

    def note(self, taxable: str = "100") -> DebitNote:
        """Raise one draft debit note."""
        row = DebitNoteService(self.session).create_note(
            self.payload(taxable), firm_id=self.firm.id, actor_id=self.actor_id
        )
        self.session.commit()
        return row

    def approved(self, taxable: str = "100") -> DebitNote:
        """Raise and approve one debit note."""
        row = self.note(taxable)
        DebitNoteService(self.session).approve_note(
            row.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )
        self.session.commit()
        return row

    def account(self, purpose: ControlAccountPurpose) -> UUID:
        """Resolve one of the firm's control accounts."""
        return ControlAccountService(self.session).resolve(self.firm.id, purpose)

    def legs(self, entry_id: UUID) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return one journal's lines, by account."""
        return {
            line.ledger_account_id: (line.debit_amount, line.credit_amount)
            for line in self.session.scalars(
                select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
            ).all()
        }

    def owed(self) -> Decimal:
        """Return what the bill still owes, as Record Payment sees it."""
        return next(
            (
                record.outstanding_amount
                for record in PaymentService(self.session).outstanding_invoices(
                    firm_id=self.firm.id, party_id=self.vendor.id
                )
                if record.invoice_id == self.invoice.id
            ),
            Decimal("0"),
        )

    def purchase_return(self, taxable: str, *, status: str = "COMPLETED") -> None:
        """Record a return of goods off the bill line, as rows."""
        row = PurchaseReturn(
            firm_id=self.firm.id,
            vendor_id=self.vendor.id,
            branch_id=self.invoice.branch_id,
            warehouse_id=uuid4(),
            return_number=f"PR-{uuid4().hex[:6]}",
            return_date=WHEN,
            status=status,
            grand_total=Decimal(taxable) * Decimal("1.18"),
        )
        self.session.add(row)
        self.session.flush()
        self.session.add(
            PurchaseReturnLine(
                purchase_return_id=row.id,
                firm_id=self.firm.id,
                line_number=1,
                source_document_type="PURCHASE_INVOICE",
                source_document_id=self.invoice.id,
                source_document_number="PI-1",
                source_document_line_id=self.line.id,
                source_document_line_number=1,
                product_id=self.product.id,
                received_quantity=Decimal("10"),
                already_returned_quantity=Decimal("0"),
                current_return_quantity=Decimal("1"),
                tax_amount=Decimal(taxable) * Decimal("0.18"),
                net_amount=Decimal(taxable) * Decimal("1.18"),
            )
        )
        self.session.commit()


def test_the_input_tax_comes_off_at_the_rate_the_bill_charged() -> None:
    """100 claimed against a line taxed at 18% reverses 18 of input tax."""
    books = _Books()

    note = books.note("100")

    assert note.vendor_id == books.vendor.id
    assert note.status == DebitNoteStatus.DRAFT.value
    assert note.taxable_amount == Decimal("100.00")
    assert note.tax_amount == Decimal("18.00")
    assert note.total_amount == Decimal("118.00")
    assert note.debit_note_number


def test_a_preview_prices_the_note_and_saves_nothing() -> None:
    """The editor's tax is the note's, and nothing lands."""
    books = _Books()

    preview = DebitNoteService(books.session).preview_note(
        books.payload("100"), firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert preview.total_amount == Decimal("118.00")
    assert preview.lines[0].tax_rate_percent == Decimal("18.00")
    assert preview.supplier_invoice_number == "SUP-1"
    assert books.session.scalar(select(func.count()).select_from(DebitNote)) == 0


def test_the_claim_is_capped_by_what_is_left_of_the_line() -> None:
    """Net of earlier debit notes and of goods returned off the same line."""
    books = _Books()
    books.note("600")
    books.purchase_return("300")
    # A cancelled return gives its value back.
    books.purchase_return("50", status="CANCELLED")

    service = DebitNoteService(books.session)
    [line] = service.claimable_lines(books.invoice.id, firm_id=books.firm.id)
    assert (line.billed_taxable, line.already_claimed, line.already_returned) == (
        Decimal("1000.00"),
        Decimal("600.00"),
        Decimal("300.00"),
    )
    assert line.claimable == Decimal("100.00")

    with pytest.raises(ValidationError, match="more than is left"):
        service.create_note(
            books.payload("100.01"), firm_id=books.firm.id, actor_id=books.actor_id
        )
    books.session.rollback()
    assert books.note("100").total_amount == Decimal("118.00")


def test_a_note_names_only_its_own_bill_s_lines_and_only_an_approved_bill() -> None:
    """A foreign line is refused, and so is a draft bill."""
    books = _Books()
    service = DebitNoteService(books.session)
    bad = books.payload("10")
    bad.lines[0].purchase_invoice_line_id = uuid4()
    with pytest.raises(ValidationError, match="must name a line"):
        service.create_note(bad, firm_id=books.firm.id, actor_id=books.actor_id)
    books.session.rollback()

    books.invoice.status = "DRAFT"
    books.session.commit()
    with pytest.raises(ValidationError, match="only an approved supplier bill"):
        service.create_note(
            books.payload("10"), firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_approving_posts_a_balanced_journal_split_by_gst_head() -> None:
    """Dr payable 118; Cr price variance 100; Cr input CGST 9 and SGST 9."""
    books = _Books()

    note = books.approved("100")

    assert note.status == DebitNoteStatus.APPROVED.value
    assert note.journal_entry_id is not None
    legs = books.legs(note.journal_entry_id)
    assert legs[books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE)] == (
        Decimal("118.00"),
        Decimal("0.00"),
    )
    assert legs[books.account(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE)] == (
        Decimal("0.00"),
        Decimal("100.00"),
    )
    assert legs[books.account(ControlAccountPurpose.INPUT_TAX_CGST)] == (
        Decimal("0.00"),
        Decimal("9.00"),
    )
    assert legs[books.account(ControlAccountPurpose.INPUT_TAX_SGST)] == (
        Decimal("0.00"),
        Decimal("9.00"),
    )
    debits = sum((debit for debit, _ in legs.values()), Decimal("0"))
    credits = sum((credit for _, credit in legs.values()), Decimal("0"))
    assert debits == credits == Decimal("118.00")


def test_approving_reduces_what_the_bill_owes_and_cancelling_restores_it() -> None:
    """Derived, never written: the payable list reads the approved note."""
    books = _Books()
    assert books.owed() == Decimal("1180.00")

    draft = books.note("100")
    # A draft has posted nothing, so the bill owes it all still.
    assert books.owed() == Decimal("1180.00")

    service = DebitNoteService(books.session)
    service.approve_note(draft.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    assert books.owed() == Decimal("1062.00")

    service.cancel_note(
        draft.id,
        reason="supplier disputed the rate",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert draft.status == DebitNoteStatus.CANCELLED.value
    assert draft.cancel_reason == "supplier disputed the rate"
    assert books.owed() == Decimal("1180.00")

    mirror = books.session.scalars(
        select(JournalEntry).where(
            JournalEntry.reversal_of_id == draft.journal_entry_id
        )
    ).one()
    legs = books.legs(mirror.id)
    assert legs[books.account(ControlAccountPurpose.ACCOUNTS_PAYABLE)] == (
        Decimal("0.00"),
        Decimal("118.00"),
    )
    assert legs[books.account(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE)] == (
        Decimal("100.00"),
        Decimal("0.00"),
    )
    # A cancelled note gives its room on the line back.
    [line] = service.claimable_lines(books.invoice.id, firm_id=books.firm.id)
    assert line.claimable == Decimal("1000.00")


def test_a_claim_past_what_the_bill_was_worth_is_refused() -> None:
    """Past what it owes is supplier credit (A4); past what it was worth, no."""
    books = _Books()
    books.purchase_return("950")
    note = books.note("50")
    service = DebitNoteService(books.session)
    # The bill owed 1180 and the return took 1121 off it: 59 left, and the
    # note claims exactly that.
    assert books.owed() == Decimal("59.00")
    service.approve_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    assert books.owed() == Decimal("0")

    # Stand in for a bill worth only 100: the claim of 118 is past it.
    again = _Books()
    again.invoice.grand_total = Decimal("100")
    again.session.commit()
    late = again.note("100")
    with pytest.raises(ValidationError, match="only 100.00 left to claim against"):
        DebitNoteService(again.session).approve_note(
            late.id, firm_scope=again.firm.id, actor_id=again.actor_id
        )


def test_only_a_draft_is_edited_and_the_status_is_not_in_the_update() -> None:
    """A lifecycle status belongs to its transition endpoints."""
    books = _Books()
    note = books.note("100")
    service = DebitNoteService(books.session)

    with pytest.raises(PydanticValidationError):
        DebitNoteUpdate.model_validate({"status": "APPROVED"})

    service.update_note(
        note.id,
        DebitNoteUpdate(
            remarks="short by one carton",
            reason=DebitNoteReasonEnum.SHORT_SUPPLY,
            lines=[
                DebitNoteLineWrite(
                    purchase_invoice_line_id=books.line.id,
                    line_number=1,
                    quantity=Decimal("1"),
                    taxable_amount=Decimal("200"),
                )
            ],
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert note.status == DebitNoteStatus.DRAFT.value
    assert note.reason == "SHORT_SUPPLY"
    assert note.total_amount == Decimal("236.00")
    # The reference is untouched: absent means leave it alone.
    assert note.remarks == "short by one carton"

    service.approve_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    with pytest.raises(ValidationError, match="Only a draft"):
        service.update_note(
            note.id,
            DebitNoteUpdate(remarks="later"),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )


def test_the_trail_records_every_step_and_an_audit_row_for_each() -> None:
    """Created, edited, approved, cancelled -- on the timeline and the trail."""
    books = _Books()
    note = books.note("100")
    service = DebitNoteService(books.session)
    service.update_note(
        note.id,
        DebitNoteUpdate(reference_number="CLAIM-7"),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    service.approve_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    service.cancel_note(
        note.id,
        reason="raised twice",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    events = books.session.scalars(
        select(DocumentLifecycleEvent).where(
            DocumentLifecycleEvent.source_document_id == note.id
        )
    ).all()
    assert sorted((event.action, event.to_state) for event in events) == [
        ("APPROVED", "APPROVED"),
        ("CANCELLED", "CANCELLED"),
        ("CREATED", "DRAFT"),
        ("EDITED", "DRAFT"),
    ]
    actions = set(
        books.session.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == note.id)
        ).all()
    )
    assert actions == {
        "debit_note.created",
        "debit_note.updated",
        "debit_note.approved",
        "debit_note.cancelled",
    }
    with pytest.raises(ValidationError, match="already cancelled"):
        service.cancel_note(
            note.id, reason="again", firm_scope=books.firm.id, actor_id=books.actor_id
        )


def test_gstr3b_reverses_the_input_credit_by_head() -> None:
    """Table 4B counts an approved debit note the way it counts a return."""
    books = _Books()
    books.approved("100")
    books.note("50")  # a draft reverses nothing

    itc = GstReturnService(books.session)._input_tax_credit(
        firm_scope=books.firm.id, from_date=date(2026, 4, 1), to_date=date(2026, 4, 30)
    )

    reversed_ = itc["itc_reversed"]
    assert isinstance(reversed_, dict)
    assert reversed_["central_tax"] == 9.0
    assert reversed_["state_tax"] == 9.0


def test_a_bill_under_a_debit_note_cannot_be_cancelled() -> None:
    """The note would be left claiming against a bill that no longer stands."""
    from app.purchase_invoice.services import PurchaseInvoiceService

    books = _Books()
    books.note("100")
    with pytest.raises(ValidationError, match="debit note"):
        PurchaseInvoiceService(books.session)._assert_nothing_rests_on(books.invoice)


def test_the_register_lists_every_note_and_the_list_filters() -> None:
    """The register is the document list; the list filters by vendor and state."""
    from app.debit_note.api.router import debit_note_register, list_debit_notes

    books = _Books()
    books.approved("100")
    books.note("50")
    scope = SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id)

    page = debit_note_register(scope=scope, db=books.session)  # type: ignore[arg-type]
    assert page.pagination.total_records == 2
    assert {row.purchase_invoice_number for row in page.data} == {"PI-1"}

    drafts = list_debit_notes(
        scope=scope,  # type: ignore[arg-type]
        vendor_id=books.vendor.id,
        note_status=DebitNoteStatus.DRAFT,  # type: ignore[arg-type]
        db=books.session,
    )
    assert [row.total_amount for row in drafts.data] == [Decimal("59.0000")]
    assert drafts.data[0].vendor_name == "Vendor One"


def test_the_permissions_are_seeded_and_approval_is_held_back() -> None:
    """The purchase manager drafts; approving reverses claimed input tax."""
    codes = {"DEBIT_NOTE_VIEW", "DEBIT_NOTE_MANAGE", "DEBIT_NOTE_APPROVE"}
    assert set(PERMISSION_GROUPS["debit_note"]) == codes
    assert codes <= ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert codes <= ROLE_PERMISSION_CODES["FIRM_MANAGER"]
    manager = ROLE_PERMISSION_CODES["PURCHASE_MANAGER"]
    assert {"DEBIT_NOTE_VIEW", "DEBIT_NOTE_MANAGE"} <= manager
    assert "DEBIT_NOTE_APPROVE" not in manager
    assert "DEBIT_NOTE_VIEW" in ROLE_PERMISSION_CODES["VIEWER"]
