"""What comes back after a claim was raised comes off the next claim.

D-PRC-31: a claim of 120.00 was raised for August -- 60.00 for two free units
under the principal's "2 + 1" (it bears half of 2 x 60.00) and 60.00 for a
free unit typed on a bill. One of the offer's free units then came back. The
claim went on reading 120.00, no later preview showed anything negative, and
cost of goods sold had been credited for that unit twice, 30.00 of it by the
claim. Only cancelling the claim and raising it again netted it, which a
part-settled claim refuses.

A claim already raised is not rewritten. The next claim on the principal
carries a negative adjustment line -- the debit adjustment a distributor
carries forward -- naming the earlier claim and the return, taken once, and
never taking the new claim below zero. Every case runs on a request-shaped
session.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.credit_note.models import CreditNote, CreditNoteLine
from app.finance.models import FirmControlAccount, GLPosting
from app.finance.services.control_accounts import ControlAccountPurpose
from app.principal_claims.models import PrincipalClaim, PrincipalClaimLine
from app.principal_claims.services import (
    PrincipalClaimPreview,
    PrincipalClaimReceiptWrite,
    PrincipalClaimService,
    PrincipalClaimWrite,
)
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from tests.unit.test_principal_claim_free_goods import AUGUST, _Agency
from tests.unit.test_principal_claim_scheme_bills import SEPTEMBER, _Scheme
from tests.unit.test_sales_return_free_goods import _returned

D = Decimal
OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))


def _write(agency: _Agency, period: tuple[date, date]) -> PrincipalClaimWrite:
    """Describe a period's claim on ACME, dated the day the period ends."""
    return PrincipalClaimWrite(
        principal_id=agency.principal.id,
        period_from=period[0],
        period_to=period[1],
        claim_date=period[1],
    )


def _typed_free_bill(agency: _Agency, on: date) -> SalesInvoice:
    """Bill four at 100 on a day, one free unit typed: 60.00 to claim."""
    invoice = agency.bills.create_invoice(
        SalesInvoiceCreate(
            customer_id=agency.setup.customer.id,
            invoice_date=on,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=agency.setup.product.id,
                    line_number=1,
                    current_invoice_quantity=D("4"),
                    free_quantity=D("1"),
                    unit_price=D("100"),
                )
            ],
        ),
        firm_id=agency.firm_id,
        actor_id=agency.actor,
    )
    agency.bills.approve_invoice(
        invoice.id, firm_scope=agency.firm_id, actor_id=agency.actor
    )
    return invoice


class _Claimed:
    """August claimed at 120.00, then one of the offer's free units returned."""

    def __init__(self) -> None:
        """Bill, raise August's claim, and take a free unit back."""
        self.agency = _Agency()
        self.typed = self.agency.bill(free="1")
        self.agency.offer()
        self.schemed = self.agency.bill(free=None)
        self.service = PrincipalClaimService(self.agency.session)
        self.august: PrincipalClaim = self.service.raise_claim(
            _write(self.agency, AUGUST),
            firm_id=self.agency.firm_id,
            actor_id=self.agency.actor,
        )
        assert self.august.total_amount == D("120.00")
        self.back = _returned(self.agency, self.schemed, "1", free="1")
        self.agency.session.expire_all()

    def preview(self, period: tuple[date, date]) -> PrincipalClaimPreview:
        """Preview a later period's claim."""
        return self.service.preview(
            _write(self.agency, period), firm_id=self.agency.firm_id
        )

    def raise_(self, period: tuple[date, date]) -> PrincipalClaim:
        """Raise a later period's claim."""
        return self.service.raise_claim(
            _write(self.agency, period),
            firm_id=self.agency.firm_id,
            actor_id=self.agency.actor,
        )

    def balance(self, purpose: ControlAccountPurpose) -> Decimal:
        """Debit less credit on one of the firm's control accounts."""
        return self.agency.balance(purpose)


def test_the_claim_raised_stays_and_the_next_claim_takes_the_unit_back() -> None:
    """September: 60.00 of new free goods less 30.00 that came back: 30.00."""
    world = _Claimed()
    (view,) = world.service.responses([world.august])
    assert (view.total_amount, view.outstanding, view.status) == (
        D("120.00"),
        D("120.00"),
        "RAISED",
    )
    _typed_free_bill(world.agency, date(2026, 9, 3))

    preview = world.preview(SEPTEMBER)

    assert (
        preview.scheme_amount,
        preview.free_goods_amount,
        preview.total_amount,
        preview.adjustments_carried_forward,
    ) == (D("-30.00"), D("60.00"), D("30.00"), D("0"))
    assert [
        (line.kind, line.quantity, line.amount, line.adjusts_claim_number)
        for line in preview.lines
    ] == [
        ("FREE_GOODS", D("1.0000"), D("60.00"), None),
        ("SCHEME", D("-1.0000"), D("-30.00"), world.august.claim_number),
    ]
    assert preview.lines[1].description == (
        f"Came back after claim {world.august.claim_number} "
        f"({world.back.return_number}): Free goods under Acme 2 + 1"
    )


def test_the_ledger_takes_back_what_the_earlier_claim_credited() -> None:
    """Dr claims receivable 30.00, Cr cost of goods sold 60.00 less 30.00."""
    world = _Claimed()
    _typed_free_bill(world.agency, date(2026, 9, 3))
    owed = world.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE)
    sold = world.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD)

    claim = world.raise_(SEPTEMBER)

    assert (claim.scheme_amount, claim.free_goods_amount, claim.total_amount) == (
        D("-30.00"),
        D("60.00"),
        D("30.00"),
    )
    assert world.balance(ControlAccountPurpose.PRINCIPAL_CLAIM_RECEIVABLE) == owed + D(
        "30"
    )
    assert world.balance(ControlAccountPurpose.COST_OF_GOODS_SOLD) == sold - D("30")
    (held,) = world.agency.session.scalars(
        select(PrincipalClaimLine).where(
            PrincipalClaimLine.claim_id == claim.id, PrincipalClaimLine.amount < 0
        )
    )
    assert held.adjusts_line_id is not None
    (view,) = world.service.responses([claim])
    assert view.lines[1].adjusts_claim_number == world.august.claim_number


def test_what_came_back_is_taken_once() -> None:
    """A third claim finds nothing more owed for the same return."""
    world = _Claimed()
    _typed_free_bill(world.agency, date(2026, 9, 3))
    world.raise_(SEPTEMBER)
    _typed_free_bill(world.agency, date(2026, 10, 3))

    preview = world.preview(OCTOBER)

    assert [(line.kind, line.amount) for line in preview.lines] == [
        ("FREE_GOODS", D("60.00"))
    ]
    assert preview.adjustments_carried_forward == D("0")


def test_with_nothing_new_to_claim_the_adjustment_waits_and_says_so() -> None:
    """No claim is raised for less than nothing: the 30.00 is carried."""
    world = _Claimed()

    preview = world.preview(SEPTEMBER)

    assert (preview.lines, preview.total_amount) == ([], D("0"))
    assert preview.adjustments_carried_forward == D("30.00")
    with pytest.raises(ValidationError) as refused:
        world.raise_(SEPTEMBER)
    world.agency.session.rollback()
    assert str(refused.value.message) == (
        "Nothing is left to claim from Acme Ltd for that period. Goods or "
        "discounts worth 30.00 came back after earlier claims; that comes off "
        "the next claim on this principal that has something to claim."
    )


def test_a_claim_is_never_negative_and_the_rest_is_carried() -> None:
    """90.00 owed back against 60.00 of new claim: 0.00 now, 30.00 next time."""
    world = _Claimed()
    _returned(world.agency, world.typed, "1", free="1")
    world.agency.session.expire_all()
    _typed_free_bill(world.agency, date(2026, 9, 3))

    preview = world.preview(SEPTEMBER)
    assert (preview.total_amount, preview.adjustments_carried_forward) == (
        D("0.00"),
        D("30.00"),
    )
    # Oldest first: the offer's unit whole (30.00), then 30.00 of the typed
    # unit's 60.00, which is as far as the new claim reaches.
    assert sorted(line.amount for line in preview.lines) == [
        D("-30.00"),
        D("-30.00"),
        D("60.00"),
    ]
    claim = world.raise_(SEPTEMBER)
    (view,) = world.service.responses([claim])
    assert (view.total_amount, view.outstanding, view.status) == (
        D("0.00"),
        D("0.00"),
        "SETTLED",
    )

    _typed_free_bill(world.agency, date(2026, 10, 3))
    later = world.preview(OCTOBER)
    assert (later.total_amount, later.adjustments_carried_forward) == (
        D("30.00"),
        D("0"),
    )
    assert sorted(line.amount for line in later.lines) == [D("-30.00"), D("60.00")]


def test_the_earlier_claim_cannot_be_cancelled_from_under_its_adjustment() -> None:
    """The later claim is cancelled first; then the adjustment is owed again."""
    world = _Claimed()
    _typed_free_bill(world.agency, date(2026, 9, 3))
    september = world.raise_(SEPTEMBER)

    with pytest.raises(ValidationError) as refused:
        world.service.cancel(
            world.august.id,
            "raised early",
            firm_id=world.agency.firm_id,
            actor_id=world.agency.actor,
        )
    world.agency.session.rollback()
    assert str(refused.value.message) == (
        f"Claim {september.claim_number} takes back goods or a discount that "
        "came back after this claim was raised; cancel that claim first."
    )

    world.service.cancel(
        september.id,
        "raised early",
        firm_id=world.agency.firm_id,
        actor_id=world.agency.actor,
    )
    again = world.preview(SEPTEMBER)
    assert (again.scheme_amount, again.total_amount) == (D("-30.00"), D("30.00"))


def test_a_part_settled_claim_is_adjusted_all_the_same() -> None:
    """The principal paid 100.00 of August; the return still comes off."""
    world = _Claimed()
    bank = world.agency.session.scalar(
        select(FirmControlAccount.ledger_account_id).where(
            FirmControlAccount.firm_id == world.agency.firm_id,
            FirmControlAccount.purpose == ControlAccountPurpose.BANK.value,
        )
    )
    assert bank is not None
    world.service.record_receipt(
        world.august.id,
        PrincipalClaimReceiptWrite(
            received_on=date(2026, 9, 1),
            amount=D("100.00"),
            money_account_id=bank,
        ),
        firm_id=world.agency.firm_id,
        actor_id=world.agency.actor,
    )
    _typed_free_bill(world.agency, date(2026, 9, 3))

    preview = world.preview(SEPTEMBER)

    assert preview.total_amount == D("30.00")


def test_a_discount_returned_after_its_claim_comes_off_the_next() -> None:
    """20.00 claimed for a bill of 4; 2 come back; 10.00 off September's."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")
    service = PrincipalClaimService(firm.session)
    august = service.raise_claim(
        firm.write(), firm_id=firm.firm_id, actor_id=firm.actor
    )
    assert august.total_amount == D("20.00")
    firm.give_back(bill, "2")
    later = firm.bill(firm.note(firm.four(), "4"), "4", invoice_date=date(2026, 9, 3))
    promo = _promotional(firm)

    preview = firm.preview(SEPTEMBER)

    assert [
        (line.source_number, line.amount, line.adjusts_claim_number)
        for line in preview.lines
    ] == [
        (later.invoice_number, D("20.00"), None),
        (bill.invoice_number, D("-10.00"), august.claim_number),
    ]
    assert preview.lines[1].description.startswith(
        f"Came back after claim {august.claim_number} (SR-"
    )
    assert ": Promotion P10 on order SO-" in preview.lines[1].description
    claim = service.raise_claim(
        firm.write(SEPTEMBER), firm_id=firm.firm_id, actor_id=firm.actor
    )
    assert claim.total_amount == D("10.00")
    # 20.00 back to promotional expense for September, 10.00 taken off again.
    assert _promotional(firm) == promo - D("10")
    assert firm.preview(OCTOBER).lines == []


def _promotional(firm: _Scheme) -> Decimal:
    """Debit less credit on the firm's promotional expense account."""
    total = firm.session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .select_from(GLPosting)
        .join(
            FirmControlAccount,
            FirmControlAccount.ledger_account_id == GLPosting.ledger_account_id,
        )
        .where(
            FirmControlAccount.firm_id == firm.firm_id,
            FirmControlAccount.purpose
            == ControlAccountPurpose.PROMOTIONAL_EXPENSE.value,
            FirmControlAccount.is_deleted.is_(False),
            GLPosting.is_deleted.is_(False),
        )
    )
    return D(str(total or 0))


def test_a_credit_note_after_the_claim_comes_off_the_next() -> None:
    """Half the bill line's value credited after the claim: 10.00 back."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")
    service = PrincipalClaimService(firm.session)
    august = service.raise_claim(
        firm.write(), firm_id=firm.firm_id, actor_id=firm.actor
    )
    line = firm.bill_line(bill)
    note = CreditNote(
        firm_id=firm.firm_id,
        customer_id=bill.customer_id,
        branch_id=bill.branch_id,
        sales_invoice_id=bill.id,
        credit_note_number="CN-1",
        credit_note_date=date(2026, 9, 2),
        reason="RATE_DIFFERENCE",
        status="APPROVED",
        taxable_amount=D("180"),
    )
    firm.session.add(note)
    firm.session.flush()
    firm.session.add(
        CreditNoteLine(
            credit_note_id=note.id,
            firm_id=firm.firm_id,
            line_number=1,
            sales_invoice_line_id=line.id,
            product_id=line.product_id,
            taxable_amount=D("180"),
        )
    )
    firm.session.commit()
    firm.bill(firm.note(firm.four(), "4"), "4", invoice_date=date(2026, 9, 3))

    preview = firm.preview(SEPTEMBER)

    assert [line.amount for line in preview.lines] == [D("20.00"), D("-10.00")]
    assert preview.lines[1].description == (
        f"Came back after claim {august.claim_number} (CN-1): "
        f"{_first_line(firm, august).description}"
    )


def _first_line(firm: _Scheme, claim: PrincipalClaim) -> PrincipalClaimLine:
    """Return a claim's one line."""
    return firm.session.scalars(
        select(PrincipalClaimLine).where(PrincipalClaimLine.claim_id == claim.id)
    ).one()


def test_a_return_before_the_claim_was_netted_then_and_is_not_taken_again() -> None:
    """Raised at 10.00 after 2 of 4 came back: nothing is owed back later."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")
    firm.give_back(bill, "2")
    service = PrincipalClaimService(firm.session)
    august = service.raise_claim(
        firm.write(), firm_id=firm.firm_id, actor_id=firm.actor
    )
    assert august.total_amount == D("10.00")
    firm.bill(firm.note(firm.four(), "4"), "4", invoice_date=date(2026, 9, 3))

    preview = firm.preview(SEPTEMBER)

    assert [line.amount for line in preview.lines] == [D("20.00")]
    assert preview.adjustments_carried_forward == D("0")
