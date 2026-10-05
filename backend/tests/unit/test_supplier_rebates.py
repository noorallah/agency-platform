"""Supplier volume rebates (BUY-13, decision A124).

Purchases from the supplier in the period -- approved bills at taxable value,
less returns -- reach a slab, and that slab's rate applies to all of them.
After the period the rebate is accrued once (Dr rebates receivable, Cr
supplier incentives), then settled by a ``SUPPLIER_REBATE`` adjustment set
against the supplier's bills (Dr payable, Cr rebates receivable).
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.party_adjustments.models import PartyAdjustment
from app.party_adjustments.schemas import (
    PartyAdjustmentAllocationWrite,
    PartyAdjustmentCreate,
    PartyAdjustmentKindEnum,
    PartyAdjustmentSideEnum,
)
from app.party_adjustments.services import PartyAdjustmentService
from app.purchase_invoice.models import PurchaseInvoice
from app.supplier_rebates.models import SupplierRebateAgreement
from app.supplier_rebates.schemas import (
    RebateSlabWrite,
    SupplierRebateCreate,
    SupplierRebateResponse,
    SupplierRebateUpdate,
)
from app.supplier_rebates.services import SupplierRebateService
from tests.unit.test_purchase_analysis import _bill, _product
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

APRIL = (date(2026, 4, 1), date(2026, 4, 30))
RECEIVABLE, INCENTIVES, PAYABLES = "1410", "4320", "2100"


def _books() -> _Books:
    return _Books(_session_factory()())


def _agreement(
    books: _Books, *, period: tuple[date, date] = APRIL, code: str = "VR-1"
) -> SupplierRebateAgreement:
    return SupplierRebateService(books.session).create(
        SupplierRebateCreate(
            vendor_id=books.vendor.id,
            code=code,
            name="Volume rebate, April",
            period_from=period[0],
            period_to=period[1],
            slabs=[
                RebateSlabWrite(threshold=Decimal("0"), rate_percent=Decimal("1")),
                RebateSlabWrite(threshold=Decimal("5000"), rate_percent=Decimal("2")),
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def _view(books: _Books, row: SupplierRebateAgreement) -> SupplierRebateResponse:
    service = SupplierRebateService(books.session)
    return service.responses([service.get(row.id, firm_id=books.firm.id)])[0]


def _legs(books: _Books, entry_id: UUID | None) -> dict[str, tuple[Decimal, Decimal]]:
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == entry_id)
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}


def _accrue(books: _Books, row: SupplierRebateAgreement) -> SupplierRebateAgreement:
    return SupplierRebateService(books.session).accrue(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id
    )


def _settle(
    books: _Books, row: SupplierRebateAgreement, bill: UUID, amount: str
) -> PartyAdjustment:
    service = PartyAdjustmentService(books.session)
    draft = service.create(
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.SUPPLIER_REBATE,
            adjustment_date=WHEN + timedelta(days=15),
            vendor_id=books.vendor.id,
            amount=Decimal(amount),
            reason="Supplier's credit note for the April volume rebate.",
            rebate_agreement_id=row.id,
            allocations=[
                PartyAdjustmentAllocationWrite(
                    side=PartyAdjustmentSideEnum.SUPPLIER,
                    bill_id=bill,
                    amount=Decimal(amount),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    approved = service.approve(
        draft.id,
        firm_scope=books.firm.id,
        actor_id=uuid4(),
        may_approve_above_threshold=True,
    )
    books.session.commit()
    return approved


def test_the_slab_reached_sets_the_rate_on_the_whole_volume() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "1180")  # taxable 1,000
    row = _agreement(books)

    first = _view(books, row)
    assert (first.volume, first.rate_percent, first.earned) == (
        Decimal("1000.00"),
        Decimal("1"),
        Decimal("10.00"),
    )
    assert (first.next_threshold, first.to_next) == (
        Decimal("5000"),
        Decimal("4000.00"),
    )

    _bill(books, "PI-2", product, "4720")  # taxable 4,000: 5,000 in all
    second = _view(books, row)
    assert (second.volume, second.rate_percent, second.earned) == (
        Decimal("5000.00"),
        Decimal("2"),
        Decimal("100.00"),
    )
    assert second.next_threshold is None


def test_only_this_suppliers_approved_bills_in_the_period_count() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "1180")
    _bill(books, "PI-2", product, "1180")
    draft = books.session.scalars(
        select(PurchaseInvoice).where(PurchaseInvoice.invoice_number == "PI-2")
    ).one()
    draft.status = "DRAFT"
    books.session.commit()
    may = _agreement(books, period=(date(2026, 5, 1), date(2026, 5, 31)), code="VR-5")

    assert _view(books, _agreement(books)).volume == Decimal("1000.00")
    assert _view(books, may).volume == Decimal("0.00")


def test_the_period_must_be_over_before_it_is_accrued() -> None:
    books = _books()
    today = utc_now().date()
    row = _agreement(books, period=(today - timedelta(days=10), today))

    with pytest.raises(ValidationError, match="accrue it after"):
        _accrue(books, row)


def test_accrual_books_the_rebate_and_keeps_what_it_booked() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "5900")  # taxable 5,000: the 2% slab
    row = _accrue(books, _agreement(books))

    assert _legs(books, row.accrual_journal_id) == {
        RECEIVABLE: (Decimal("100.00"), Decimal("0.00")),
        INCENTIVES: (Decimal("0.00"), Decimal("100.00")),
    }
    # A bill booked into the period afterwards does not move what was booked.
    _bill(books, "PI-9", product, "1180")
    after = _view(books, row)
    assert (after.status, after.volume, after.earned, after.to_settle) == (
        "ACCRUED",
        Decimal("5000.00"),
        Decimal("100.00"),
        Decimal("100.00"),
    )
    with pytest.raises(ValidationError, match="accrued cannot be accrued"):
        _accrue(books, row)
    with pytest.raises(ValidationError, match="cannot be changed"):
        SupplierRebateService(books.session).update(
            row.id,
            SupplierRebateUpdate(name="New name"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_nothing_earned_is_not_accrued() -> None:
    books = _books()
    with pytest.raises(ValidationError, match="nothing to accrue"):
        _accrue(books, _agreement(books))


def test_the_suppliers_credit_is_set_against_its_bills() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "5900")
    bill = books.session.scalars(select(PurchaseInvoice)).one()
    row = _accrue(books, _agreement(books))

    settled = _settle(books, row, bill.id, "60.00")

    assert _legs(books, settled.journal_entry_id) == {
        PAYABLES: (Decimal("60.00"), Decimal("0.00")),
        RECEIVABLE: (Decimal("0.00"), Decimal("60.00")),
    }
    view = _view(books, row)
    assert (view.settled, view.to_settle) == (Decimal("60.00"), Decimal("40.00"))
    with pytest.raises(ValidationError, match="40.00 still to settle"):
        _settle(books, row, bill.id, "50.00")
    with pytest.raises(ValidationError, match="already set against"):
        SupplierRebateService(books.session).reverse_accrual(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id
        )


def test_a_rebate_still_counting_cannot_be_settled() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "5900")
    bill = books.session.scalars(select(PurchaseInvoice)).one()

    with pytest.raises(ValidationError, match="Only an accrued rebate"):
        _settle(books, _agreement(books), bill.id, "10.00")


def test_an_accrual_with_nothing_settled_can_be_reversed() -> None:
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "5900")
    row = _accrue(books, _agreement(books))
    booked = row.accrual_journal_id

    reversed_row = SupplierRebateService(books.session).reverse_accrual(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id
    )

    assert reversed_row.status == "ACTIVE"
    assert reversed_row.accrued_amount is None
    assert booked is not None
    # The mirror takes the 100 back off both accounts.
    mirrored = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(LedgerAccount.code.in_((RECEIVABLE, INCENTIVES)))
    ).all()
    net = {
        code: sum(
            (d - c for k, d, c in mirrored if k == code),
            Decimal("0"),
        )
        for code in (RECEIVABLE, INCENTIVES)
    }
    assert net == {RECEIVABLE: Decimal("0.00"), INCENTIVES: Decimal("0.00")}


def test_a_rebate_settlement_must_name_its_agreement() -> None:
    with pytest.raises(ValueError, match="Name the rebate agreement"):
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.SUPPLIER_REBATE,
            adjustment_date=WHEN,
            vendor_id=uuid4(),
            amount=Decimal("1"),
            reason="Rebate",
        )
    with pytest.raises(ValueError, match="Only a rebate settlement"):
        PartyAdjustmentCreate(
            kind=PartyAdjustmentKindEnum.SUPPLIER_WRITE_BACK,
            adjustment_date=WHEN,
            vendor_id=uuid4(),
            amount=Decimal("1"),
            reason="Write back",
            rebate_agreement_id=uuid4(),
        )


def test_a_reversed_rebate_can_be_accrued_again() -> None:
    """D-BUY-34: the second accrual takes a reference the first did not."""
    books = _books()
    product = _product(books, "A")
    _bill(books, "PI-1", product, "5900")
    row = _accrue(books, _agreement(books))
    first = row.accrual_journal_id
    service = SupplierRebateService(books.session)
    service.reverse_accrual(row.id, firm_id=books.firm.id, actor_id=books.actor_id)

    again = _accrue(books, row)

    assert again.status == "ACCRUED"
    assert again.accrual_journal_id not in (None, first)
    references = sorted(
        books.session.scalars(
            select(JournalEntry.reference_number).where(
                JournalEntry.source_module == "supplier_rebates",
                JournalEntry.source_id == row.id,
                JournalEntry.reversal_of_id.is_(None),
            )
        ).all()
    )
    assert references == [f"REBATE-{row.code}", f"REBATE-{row.code}-2"]
