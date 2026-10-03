"""TDS challans: the deposit of what the firm deducted (ACC-7, decision A79).

A challan gathers open deductions under one section, posts Dr TDS payable /
Dr interest and fees / Cr bank, takes each deduction once, and is cancelled
with a mirror that frees them. The 26Q return names the challan per row; a
supplier's usual section is kept on the supplier.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError, ValidationError
from app.expenses.schemas import ExpenseCreate
from app.expenses.services import ExpenseService
from app.finance.schemas.tds_challans import (
    DeductionKind,
    DeductionRef,
    TdsChallanCreate,
)
from app.finance.services.tds_challans import TdsChallanService, challan_cin
from app.finance.services.tds_return import TdsReturnService, return_quarter
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import PaymentService
from app.vendors.models import Vendor
from app.vendors.schemas import VendorCreate
from tests.unit.test_expenses import _Books

BANK, TDS_PAYABLE, INTEREST = "1010", "2700", "6930"
WHEN = date(2026, 4, 20)


def _vendor(books: _Books) -> Vendor:
    vendor = Vendor(
        firm_id=books.firm.id,
        code="V1",
        name="Vendor One",
        display_name="Vendor One",
        pan="AAACV1234A",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(vendor)
    books.session.commit()
    return vendor


def _payment(books: _Books, vendor: Vendor, tds: str, section: str) -> UUID:
    row = PaymentService(books.session).create(
        SettlementCreate(
            party_id=vendor.id,
            settlement_date=WHEN,
            amount=Decimal("100000.00"),
            method=SettlementMethodEnum.BANK,
            tds_amount=Decimal(tds),
            tds_section=section,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row.id


def _expense(books: _Books, tds: str, section: str = "194I") -> UUID:
    row = ExpenseService(books.session).create(
        ExpenseCreate(
            expense_date=WHEN,
            expense_account_id=books.account("6000"),
            paid_from_account_id=books.account(BANK),
            amount=Decimal("30000.00"),
            payee="Sharma Properties",
            payee_pan="ABCDE1234F",
            tds_amount=Decimal(tds),
            tds_section=section,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row.id


def _challan(
    books: _Books, refs: list[DeductionRef], **over: object
) -> TdsChallanCreate:
    values: dict[str, object] = {
        "deposited_on": date(2026, 5, 6),
        "bsr_code": "0510308",
        "challan_serial": "123",
        "section": "194I",
        "paid_from_account_id": books.account(BANK),
        "deductions": refs,
    }
    values.update(over)
    return TdsChallanCreate(**values)  # type: ignore[arg-type]


def test_a_challan_pays_the_deductions_and_posts_tax_and_charges() -> None:
    books = _Books()
    first = _expense(books, "3000.00")
    second = _expense(books, "1000.00")
    service = TdsChallanService(books.session)
    assert len(service.open_deductions(books.firm.id, section="194I")) == 2

    row = service.create(
        _challan(
            books,
            [
                DeductionRef(kind=DeductionKind.EXPENSE, id=first),
                DeductionRef(kind=DeductionKind.EXPENSE, id=second),
            ],
            interest_amount=Decimal("60"),
            fee_amount=Decimal("200"),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert row.tax_amount == Decimal("4000.00")
    assert row.challan_serial == "00123"
    legs = books.postings(row.journal_entry_id)
    assert legs[TDS_PAYABLE] == (Decimal("4000.00"), Decimal("0.00"))
    assert legs[INTEREST] == (Decimal("260.00"), Decimal("0.00"))
    assert legs[BANK] == (Decimal("0.00"), Decimal("4260.00"))
    assert service.open_deductions(books.firm.id) == []

    [answer] = service.responses([row])
    assert answer.cin == challan_cin("0510308", date(2026, 5, 6), "00123")
    assert answer.cin == "05103080605202600123"
    assert answer.total_amount == Decimal("4260.00")
    assert answer.is_late is False
    assert [item.tds_amount for item in answer.items] == [
        Decimal("3000.00"),
        Decimal("1000.00"),
    ]


def test_a_deduction_is_paid_once_and_cancelling_frees_it() -> None:
    books = _Books()
    expense = _expense(books, "3000.00")
    service = TdsChallanService(books.session)
    refs = [DeductionRef(kind=DeductionKind.EXPENSE, id=expense)]
    row = service.create(
        _challan(books, refs), firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="not open"):
        service.create(
            _challan(books, refs, challan_serial="124"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )

    service.cancel(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Wrong BSR"
    )
    books.session.commit()
    assert books.net(TDS_PAYABLE) == Decimal("-3000.00")
    assert [o.id for o in service.open_deductions(books.firm.id)] == [expense]

    again = service.create(
        _challan(books, refs), firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert again.status == "POSTED"
    assert books.net(TDS_PAYABLE) == Decimal("0.00")


def test_the_key_holds_a_deduction_two_challans_race_for() -> None:
    books = _Books()
    expense = _expense(books, "3000.00")
    service = TdsChallanService(books.session)
    refs = [DeductionRef(kind=DeductionKind.EXPENSE, id=expense)]
    service.create(
        _challan(books, refs), firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    # Skip the read, as a racing request would: the partial key refuses it.
    service.open_deductions = (  # type: ignore[method-assign]
        lambda *args, **kwargs: [
            *TdsChallanService(books.session).open_deductions(books.firm.id),
            _open_row(expense),
        ]
    )
    with pytest.raises(ConflictError):
        service.create(
            _challan(books, refs, challan_serial="999"),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def _open_row(expense: UUID) -> object:
    from app.finance.schemas.tds_challans import OpenDeductionRecord

    return OpenDeductionRecord(
        kind=DeductionKind.EXPENSE,
        id=expense,
        document_number="X",
        document_date=WHEN,
        party_name="",
        pan=None,
        section="194I",
        gross_amount=Decimal("30000"),
        tds_amount=Decimal("3000.00"),
        due_date=date(2026, 5, 7),
    )


def test_a_challan_pays_one_section_and_the_counterfoil_must_agree() -> None:
    books = _Books()
    vendor = _vendor(books)
    payment = _payment(books, vendor, "1000.00", "194C")
    expense = _expense(books, "3000.00")
    service = TdsChallanService(books.session)
    with pytest.raises(ValidationError, match="one section"):
        service.create(
            _challan(
                books,
                [
                    DeductionRef(kind=DeductionKind.EXPENSE, id=expense),
                    DeductionRef(kind=DeductionKind.PAYMENT, id=payment),
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="counterfoil"):
        service.create(
            _challan(
                books,
                [DeductionRef(kind=DeductionKind.EXPENSE, id=expense)],
                tax_amount=Decimal("3100"),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(ValidationError, match="bank or cash"):
        service.create(
            _challan(
                books,
                [DeductionRef(kind=DeductionKind.EXPENSE, id=expense)],
                paid_from_account_id=books.account("6000"),
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )
    with pytest.raises(PydanticValidationError, match="seven digits"):
        _challan(books, [], bsr_code="12345")


def test_a_late_deposit_says_so_and_a_payment_can_be_carried() -> None:
    books = _Books()
    vendor = _vendor(books)
    payment = _payment(books, vendor, "1000.00", "194C")
    service = TdsChallanService(books.session)
    row = service.create(
        _challan(
            books,
            [DeductionRef(kind=DeductionKind.PAYMENT, id=payment)],
            section="194C",
            deposited_on=date(2026, 5, 9),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    [answer] = service.responses([row])
    assert answer.is_late is True
    assert answer.items[0].party_name == "Vendor One"
    assert answer.items[0].pan == "AAACV1234A"


def test_the_26q_rows_name_the_challan_that_paid_them() -> None:
    books = _Books()
    paid = _expense(books, "3000.00")
    _expense(books, "1000.00")
    TdsChallanService(books.session).create(
        _challan(books, [DeductionRef(kind=DeductionKind.EXPENSE, id=paid)]),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    tds_return = TdsReturnService(books.session).build(
        books.firm.id, return_quarter("2026-27", "Q1")
    )
    by_amount = {row.tds_amount: row for row in tds_return.deductees}
    assert by_amount[Decimal("3000.00")].challan_serial == "00123"
    assert by_amount[Decimal("3000.00")].challan_bsr_code == "0510308"
    assert by_amount[Decimal("3000.00")].challan_date == date(2026, 5, 6)
    assert by_amount[Decimal("1000.00")].challan_serial == ""
    [due] = tds_return.challans
    assert (due.tds_amount, due.deposited, due.outstanding) == (
        Decimal("4000.00"),
        Decimal("3000.00"),
        Decimal("1000.00"),
    )
    assert any("name no challan" in problem for problem in tds_return.problems)


def test_a_supplier_keeps_its_usual_section() -> None:
    created = VendorCreate(code="V9", name="Transport Co", default_tds_section="194c")
    assert created.default_tds_section == "194C"
    assert (
        VendorCreate(code="V9", name="X", default_tds_section=" ").default_tds_section
        is None
    )
    with pytest.raises(PydanticValidationError, match="not a TDS section"):
        VendorCreate(code="V9", name="X", default_tds_section="999")
