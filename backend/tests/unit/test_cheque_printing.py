"""Printing a supplier payment onto a cheque leaf (ACC-12, decision A66).

The cheque carries what left the bank, made out to the supplier's legal name
on the cheque's own date; only a posted bank payment made by cheque (or with
no mode recorded) has one; and each bank account keeps the offsets its leaf
needs, audited when saved.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.finance.services.control_accounts import ControlAccountPurpose
from app.settlements.api.router import payment_cheque, save_cheque_layout
from app.settlements.models import Settlement
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.schemas.cheque import ChequeLayoutUpdate
from app.settlements.services import PaymentService
from app.settlements.services.cheque_print import (
    ChequeContent,
    ChequeRenderer,
    ChequeService,
    indian_grouping,
)
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers


def _pay(books: _Books, method: str = "BANK", **extra: object) -> Settlement:
    return PaymentService(books.session).create(
        SettlementCreate.model_validate(
            {
                "party_id": books.vendor.id,
                "settlement_date": WHEN,
                "amount": Decimal("25000.00"),
                "method": SettlementMethodEnum(method),
                **extra,
            }
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (Decimal("1234567.89"), "12,34,567.89"),
        (Decimal("999"), "999.00"),
        (Decimal("100000"), "1,00,000.00"),
        (Decimal("12345678901.5"), "12,34,56,78,901.50"),
    ],
)
def test_figures_are_grouped_the_indian_way(amount: Decimal, text: str) -> None:
    assert indian_grouping(amount) == text


def test_a_cheque_is_one_leaf_sized_page() -> None:
    pdf = ChequeRenderer().render(
        ChequeContent("Vendor One Pvt Ltd", Decimal("98765432.10"), date(2026, 4, 20))
    )
    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 576 264.189" in pdf


def test_an_empty_payee_or_amount_is_refused() -> None:
    with pytest.raises(ValidationError, match="payable to"):
        ChequeRenderer().render(ChequeContent(" ", Decimal("1"), WHEN))
    with pytest.raises(ValidationError, match="more than nothing"):
        ChequeRenderer().render(ChequeContent("X", Decimal("0"), WHEN))
    with pytest.raises(ValidationError, match="too long"):
        ChequeRenderer().render(ChequeContent("W" * 120, Decimal("1"), WHEN))


def test_the_cheque_says_what_left_the_bank_to_the_legal_name() -> None:
    books = _Books(_session_factory()())
    books.vendor.legal_name = "Vendor One Private Limited"
    books.session.commit()
    payment = _pay(
        books,
        payment_mode="CHEQUE",
        instrument_reference="000123",
        instrument_date=date(2026, 4, 25),
    )
    payment.tds_amount = Decimal("250.00")

    content = ChequeService(books.session).cheque_content(payment)
    assert content.payee == "Vendor One Private Limited"
    assert content.amount == Decimal("24750.00")
    assert content.cheque_date == date(2026, 4, 25)

    other = ChequeService(books.session).cheque_content(payment, payee="Ravi Traders")
    assert other.payee == "Ravi Traders"


def test_a_bank_payment_with_no_mode_prints_on_its_own_date() -> None:
    books = _Books(_session_factory()())
    payment = _pay(books)
    content = ChequeService(books.session).cheque_content(payment)
    assert content.payee == "Vendor One"
    assert content.cheque_date == WHEN

    scope = type("Scope", (), {"firm_id": books.firm.id})()
    response = payment_cheque(payment.id, scope, None, books.session)  # type: ignore[arg-type]
    assert response.media_type == "application/pdf"


def test_cash_upi_and_reversed_payments_have_no_cheque() -> None:
    books = _Books(_session_factory()())
    service = ChequeService(books.session)
    with pytest.raises(ValidationError, match="cash payment"):
        service.cheque_content(_pay(books, "CASH"))
    with pytest.raises(ValidationError, match="made by UPI"):
        service.cheque_content(_pay(books, payment_mode="UPI"))
    reversed_payment = _pay(books, payment_mode="CHEQUE")
    reversed_payment.status = "REVERSED"
    with pytest.raises(ValidationError, match="reversed"):
        service.cheque_content(reversed_payment)
    with pytest.raises(ResourceNotFoundError):
        service.payment_cheque(uuid4(), firm_id=books.firm.id)


def test_a_layout_is_kept_per_bank_account_and_audited() -> None:
    books = _Books(_session_factory()())
    bank = books.account(ControlAccountPurpose.BANK)
    service = ChequeService(books.session)

    unsaved = service.layout_for(bank, firm_id=books.firm.id)
    assert (unsaved.offset_x_mm, unsaved.print_ac_payee) == (Decimal("0"), True)

    scope = type("Scope", (), {"firm_id": books.firm.id, "actor_id": books.actor_id})()
    save_cheque_layout(
        bank,
        ChequeLayoutUpdate(offset_x_mm=Decimal("2.5"), offset_y_mm=Decimal("-1")),
        scope,  # type: ignore[arg-type]
        books.session,
    )
    saved = service.save_layout(
        bank,
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        offset_x_mm=Decimal("3.0"),
        offset_y_mm=Decimal("-1.0"),
        print_ac_payee=False,
    )
    assert [row.id for row in service.layouts(firm_id=books.firm.id)] == [saved.id]
    assert saved.offset_x_mm == Decimal("3.0")
    assert saved.print_ac_payee is False
    audits = books.session.scalars(
        select(AuditLog).where(AuditLog.action == "cheque_layout.saved")
    ).all()
    assert len(audits) == 2
    assert service.test_print(bank, firm_id=books.firm.id).startswith(b"%PDF")

    with pytest.raises(ValidationError, match="at most 30"):
        service.save_layout(
            bank,
            firm_id=books.firm.id,
            actor_id=books.actor_id,
            offset_x_mm=Decimal("31"),
            offset_y_mm=Decimal("0"),
            print_ac_payee=True,
        )
    with pytest.raises(ResourceNotFoundError):
        service.test_print(uuid4(), firm_id=books.firm.id)
    with pytest.raises(SchemaError):
        ChequeLayoutUpdate(offset_x_mm=Decimal("40"))
