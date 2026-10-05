"""PG-5 (§86 #10): TDS under 194C and 194J worked out, as 194Q is.

The supplier names its section; the bill proposes the deduction when it is
approved and the payment when money goes ahead of any bill -- the earlier of
credit and payment -- each as the year's tax due less what the year already
deducted, so a deduction is made once whichever document comes first. The
threshold sums are read from the documents of the April-March year. An
override is kept beside the proposal and the trail records both. Bills that
bore TDS join the challans and the 26Q return.

Sessions are shaped like a request's (no autoflush), as in the PG-3 tests.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, LedgerAccount
from app.finance.schemas.tds_challans import (
    DeductionKind,
    DeductionRef,
    TdsChallanCreate,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.tds_challans import TdsChallanService
from app.finance.services.tds_return import TdsReturnService, return_quarter
from app.finance.services.tds_sections import TdsSectionService
from app.purchase_invoice.api.router import approve_purchase_invoice
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import PurchaseInvoiceApproveRequest
from app.purchase_invoice.services import PurchaseInvoiceService
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService
from app.vendors.models import Vendor
from tests.unit.test_cash_purchase import APPROVER, _books, _postings, _scope
from tests.unit.test_settlements import WHEN, _Books

pytestmark = pytest.mark.typed_document_numbers

COMPANY_PAN = "AAACV1234A"


def _supplier(
    books: _Books,
    section: str | None,
    *,
    pan: str | None = COMPANY_PAN,
    technical: bool = False,
    vendor: Vendor | None = None,
) -> Vendor:
    """Put the books' supplier (or another) under a section."""
    row = vendor or books.vendor
    row.default_tds_section = section
    row.pan = pan
    row.tds_technical_services = technical
    books.session.commit()
    return row


def _other_vendor(books: _Books) -> Vendor:
    """Add a second supplier."""
    vendor = Vendor(
        firm_id=books.firm.id,
        code="V2",
        name="Consultant Two",
        display_name="Consultant Two",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(vendor)
    books.session.commit()
    return vendor


def _draft(
    books: _Books,
    taxable: str,
    *,
    tax: str = "0",
    vendor: Vendor | None = None,
) -> PurchaseInvoice:
    """Add one draft bill: ``taxable`` before GST, ``tax`` on top."""
    PurchaseInvoiceService(books.session)._ensure_document_setup(
        firm_id=books.firm.id, actor_id=books.actor_id
    )
    number = f"PI-{uuid4().hex[:8]}"
    row = PurchaseInvoice(
        firm_id=books.firm.id,
        vendor_id=(vendor or books.vendor).id,
        branch_id=books.branch_id,
        invoice_number=number,
        invoice_date=WHEN,
        supplier_invoice_number=f"S-{number}",
        supplier_invoice_date=WHEN,
        status="DRAFT",
        subtotal=Decimal(taxable),
        tax_total=Decimal(tax),
        grand_total=Decimal(taxable) + Decimal(tax),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _approve(
    books: _Books, bill: PurchaseInvoice, tds: Decimal | None = None
) -> PurchaseInvoice:
    """Approve through the endpoint, optionally overriding the TDS."""
    approve_purchase_invoice(
        invoice_id=bill.id,
        scope=_scope(books, *APPROVER),
        data=PurchaseInvoiceApproveRequest(tds_amount=tds),
        db=books.session,
    )
    books.session.expire_all()
    row = books.session.get(PurchaseInvoice, bill.id)
    assert row is not None
    return row


def _bill(
    books: _Books, taxable: str, *, tax: str = "0", vendor: Vendor | None = None
) -> PurchaseInvoice:
    """Add a bill and approve it, taking the proposal."""
    return _approve(books, _draft(books, taxable, tax=tax, vendor=vendor))


def _pay(
    books: _Books,
    amount: str,
    *,
    tds: str | None = None,
    bill: PurchaseInvoice | None = None,
) -> Settlement:
    """Record a payment to the supplier, against a bill or on account."""
    row = PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            tds_amount=None if tds is None else Decimal(tds),
            tds_section=None if tds is None else "194C",
            allocations=(
                []
                if bill is None
                else [
                    SettlementAllocationWrite(
                        invoice_id=bill.id, amount=Decimal(amount)
                    )
                ]
            ),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row


def _owed(books: _Books, bill_id: UUID) -> Decimal:
    """Return what one bill still owes the supplier."""
    for record in PaymentService(books.session).outstanding_invoices(
        firm_id=books.firm.id, party_id=None
    ):
        if record.invoice_id == bill_id:
            return record.outstanding_amount
    return Decimal("0")


def _code(books: _Books, purpose: ControlAccountPurpose) -> str:
    """Return the ledger code a purpose is mapped to."""
    account = books.session.get(LedgerAccount, books.account(purpose))
    assert account is not None
    return account.code


def test_one_bill_past_30000_under_194c_deducts_and_posts_to_tds_payable() -> None:
    books = _books()
    _supplier(books, "194C")

    at_limit = _bill(books, "30000.00")
    assert (at_limit.tds_amount, at_limit.tds_proposed_amount) == (
        Decimal("0"),
        Decimal("0.00"),
    ), "30,000 is the limit, not past it"
    assert at_limit.tds_section is None

    bill = _bill(books, "40000.00", tax="7200.00")
    # Past the single limit: 2% on this bill alone (a company's PAN), before GST.
    assert bill.tds_section == "194C"
    assert bill.tds_base_amount == Decimal("40000.00")
    assert bill.tds_proposed_amount == Decimal("800.00")
    assert bill.tds_amount == Decimal("800.00")
    assert _owed(books, bill.id) == Decimal("46400.00")

    entry = books.session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "purchase_invoice",
            JournalEntry.source_id == bill.id,
        )
    )
    assert entry is not None
    legs = _postings(books, entry.id)
    assert legs[_code(books, ControlAccountPurpose.TDS_PAYABLE)] == (
        Decimal("0.00"),
        Decimal("800.00"),
    )
    assert legs[_code(books, ControlAccountPurpose.ACCOUNTS_PAYABLE)] == (
        Decimal("0.00"),
        Decimal("46400.00"),
    )


def test_the_bills_own_proposal_is_worked_on_the_base_approval_uses() -> None:
    """D-BUY-37: lines plus additional charges, shown as it will be posted."""
    from app.purchase_invoice.api.router import purchase_invoice_tds_proposal

    books = _books()
    _supplier(books, "194C")
    draft = _draft(books, "28000.00", tax="5040.00")
    draft.additional_charges = Decimal("5000.00")
    draft.grand_total = Decimal("38040.00")
    books.session.commit()

    shown = purchase_invoice_tds_proposal(
        invoice_id=draft.id, scope=_scope(books, *APPROVER), db=books.session
    ).data
    assert shown is not None
    # 28,000 of lines alone is under the 30,000 limit and proposes nothing,
    # which is what the dialog used to show; 33,000 with the charges is past.
    on_lines_alone = TdsSectionService(books.session).supplier(
        books.vendor.id,
        firm_id=books.firm.id,
        on=WHEN,
        bill_amount=Decimal("28000.00"),
        bill_total=Decimal("38040.00"),
        exclude_invoice_id=draft.id,
    )
    assert on_lines_alone.proposed == Decimal("0.00")
    assert (shown.section, shown.this_document) == ("194C", Decimal("33000.00"))
    assert shown.proposed == Decimal("660.00")

    bill = _approve(books, draft)
    assert bill.tds_base_amount == shown.this_document
    assert bill.tds_proposed_amount == bill.tds_amount == shown.proposed


def test_small_bills_deduct_on_the_whole_year_from_the_one_that_crosses() -> None:
    """The year's total past 1,00,000 is taxed whole, caught up on one bill."""
    books = _books()
    _supplier(books, "194C")
    early = [_bill(books, "25000.00") for _ in range(4)]
    assert [row.tds_amount for row in early] == [
        Decimal("0")
    ] * 4, "1,00,000 is the limit"

    crossing = _bill(books, "25000.00")
    # 1,25,000 at 2%: the four earlier bills' tax comes due on this one.
    assert crossing.tds_amount == Decimal("2500.00")
    after = _bill(books, "10000.00")
    assert after.tds_amount == Decimal("200.00"), "from the crossing bill on"

    proposal = TdsSectionService(books.session).supplier(
        books.vendor.id, firm_id=books.firm.id, on=WHEN
    )
    assert proposal.threshold_crossed == "ANNUAL"
    assert (proposal.due, proposal.deducted, proposal.proposed) == (
        Decimal("2700.00"),
        Decimal("2700.00"),
        Decimal("0.00"),
    )


def test_no_pan_is_twenty_percent_and_a_person_one_percent() -> None:
    books = _books()
    _supplier(books, "194C", pan=None)
    assert _bill(books, "40000.00").tds_amount == Decimal("8000.00")

    other = _supplier(books, "194C", pan="ABCPE1234F", vendor=_other_vendor(books))
    person = _bill(books, "40000.00", vendor=other)
    assert person.tds_amount == Decimal("400.00"), "P in the PAN: an individual"
    proposal = TdsSectionService(books.session).supplier(
        other.id, firm_id=books.firm.id, on=WHEN
    )
    assert proposal.rate_basis == "INDIVIDUAL_HUF"


def test_deducted_once_when_the_bill_comes_first() -> None:
    books = _books()
    _supplier(books, "194C")
    bill = _bill(books, "50000.00", tax="9000.00")
    assert bill.tds_amount == Decimal("1000.00")

    payment = _pay(books, "58000.00", bill=bill)
    assert payment.tds_proposed_amount == Decimal("0.00"), "the bill bore it"
    assert payment.tds_amount == Decimal("0.00")
    assert _owed(books, bill.id) == Decimal("0")


def test_deducted_once_when_the_payment_comes_first() -> None:
    books = _books()
    _supplier(books, "194C")
    proposal = TdsSectionService(books.session).supplier(
        books.vendor.id,
        firm_id=books.firm.id,
        on=WHEN,
        advance_amount=Decimal("50000"),
    )
    assert proposal.proposed == Decimal("1000.00")
    advance = _pay(books, "50000.00", tds=str(proposal.proposed))
    assert advance.tds_proposed_amount == Decimal("1000.00")

    bill = _bill(books, "50000.00", tax="9000.00")
    # The advance already deducted on this money: the bill nets it off.
    assert bill.tds_proposed_amount == Decimal("0.00")
    assert bill.tds_amount == Decimal("0")
    assert _owed(books, bill.id) == Decimal("59000.00")


def test_194j_applies_past_30000_in_the_year() -> None:
    books = _books()
    _supplier(books, "194J")
    first = _bill(books, "20000.00")
    assert first.tds_amount == Decimal("0"), "194J has no single-bill limit"
    second = _bill(books, "15000.00")
    # 35,000 in the year at 10% on professional fees.
    assert second.tds_section == "194J"
    assert second.tds_amount == Decimal("3500.00")

    _supplier(books, "194J", technical=True)
    technical = TdsSectionService(books.session).supplier(
        books.vendor.id, firm_id=books.firm.id, on=WHEN, bill_amount=Decimal("1000")
    )
    assert (technical.rate_percent, technical.rate_basis) == (
        Decimal("2"),
        "TECHNICAL",
    )


def test_an_override_is_kept_beside_the_proposal_and_audited() -> None:
    books = _books()
    _supplier(books, "194C")
    bill = _approve(books, _draft(books, "40000.00"), tds=Decimal("0"))
    assert (bill.tds_proposed_amount, bill.tds_amount) == (
        Decimal("800.00"),
        Decimal("0"),
    )
    trail = books.session.scalar(
        select(AuditLog).where(
            AuditLog.action == "purchase_invoice.approved",
            AuditLog.entity_id == bill.id,
        )
    )
    assert trail is not None and trail.after_data is not None
    assert trail.after_data["tds_overridden"] is True
    assert trail.after_data["tds_proposed_amount"] == "800.00"
    assert trail.after_data["tds_amount"] == "0.00"

    # The shortfall is still due, so the payment proposes it; paid without it
    # is an override too, and the trail says so.
    payment = _pay(books, "40000.00", bill=bill)
    assert payment.tds_proposed_amount == Decimal("800.00")
    recorded = books.session.scalar(
        select(AuditLog).where(
            AuditLog.action == "settlement.payment.recorded",
            AuditLog.entity_id == payment.id,
        )
    )
    assert recorded is not None and recorded.after_data is not None
    assert recorded.after_data["tds_overridden"] is True


def test_an_override_needs_a_section_and_stays_below_the_bill() -> None:
    books = _books()
    _supplier(books, None)
    with pytest.raises(ValidationError, match="194C or 194J"):
        _approve(books, _draft(books, "40000.00"), tds=Decimal("100"))
    _supplier(books, "194C")
    with pytest.raises(ValidationError, match="less than"):
        _approve(books, _draft(books, "400.00"), tds=Decimal("400"))


def test_challans_and_26q_carry_194c_and_194j_bills() -> None:
    books = _books()
    _supplier(books, "194C")
    contract = _bill(books, "40000.00")
    consultant = _supplier(books, "194J", vendor=_other_vendor(books))
    fees = _bill(books, "50000.00", vendor=consultant)
    assert (contract.tds_amount, fees.tds_amount) == (
        Decimal("800.00"),
        Decimal("5000.00"),
    )

    challans = TdsChallanService(books.session)
    open_rows = challans.open_deductions(books.firm.id)
    assert {(row.kind, row.section) for row in open_rows} == {
        (DeductionKind.BILL, "194C"),
        (DeductionKind.BILL, "194J"),
    }
    challan = challans.create(
        TdsChallanCreate(
            deposited_on=WHEN.replace(month=5, day=6),
            bsr_code="0510308",
            challan_serial="123",
            section="194C",
            paid_from_account_id=books.account(ControlAccountPurpose.BANK),
            deductions=[DeductionRef(kind=DeductionKind.BILL, id=contract.id)],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert challan.tax_amount == Decimal("800.00")
    [line] = challans.responses([challan])[0].items
    assert (line.kind, line.document_number) == (
        DeductionKind.BILL,
        contract.invoice_number,
    )

    tds_return = TdsReturnService(books.session).build(
        books.firm.id, return_quarter("2026-27", "Q1")
    )
    rows = {row.section: row for row in tds_return.deductees}
    assert set(rows) == {"194C", "194J"}
    assert rows["194C"].document_type == "Bill"
    assert rows["194C"].amount_paid == Decimal("40000.00")
    assert rows["194C"].challan_serial == "00123"
    assert rows["194J"].tds_amount == Decimal("5000.00")
    assert rows["194J"].challan_serial == ""

    # A bill whose deduction is on a challan cannot be cancelled under it.
    with pytest.raises(ValidationError, match="TDS challan"):
        PurchaseInvoiceService(books.session).cancel_invoice(
            contract.id,
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            reason="wrong supplier",
        )


def test_settings_default_save_partly_and_are_checked() -> None:
    books = _books()
    service = TdsSectionService(books.session)
    contract, fees = service.all_settings(books.firm.id)
    assert (contract.section, contract.is_enabled) == ("194C", True)
    assert (contract.single_threshold_amount, contract.annual_threshold_amount) == (
        Decimal("30000"),
        Decimal("100000"),
    )
    assert (fees.rate_percent, fees.lower_rate_percent) == (
        Decimal("10"),
        Decimal("2"),
    )
    assert fees.single_threshold_amount is None

    saved = service.save_settings(
        books.firm.id, "194C", {"rate_percent": Decimal("2.5")}, actor_id=uuid4()
    )
    assert saved.rate_percent == Decimal("2.5")
    assert saved.lower_rate_percent == Decimal("1"), "a field not sent is kept"
    with pytest.raises(ValidationError, match="no single-bill limit"):
        service.save_settings(
            books.firm.id,
            "194J",
            {"single_threshold_amount": Decimal("1")},
            actor_id=uuid4(),
        )
    with pytest.raises(ValidationError, match="not worked out here"):
        service.settings(books.firm.id, "194Q")

    service.save_settings(
        books.firm.id, "194C", {"is_enabled": False}, actor_id=uuid4()
    )
    _supplier(books, "194C")
    assert _bill(books, "40000.00").tds_amount == Decimal("0"), "switched off"
