"""Backlog ACC-3: how a receipt's or payment's money moved.

Tally asks a bank voucher for its transaction type (cheque, e-fund transfer)
with the instrument's number and date; Zoho Books asks every payment its mode
(cash, cheque, bank transfer, UPI, card). A settlement now records its mode,
held to its method -- cash is cash, the rest go through a bank -- and the
cheque's own date beside its number, and the bank book shows both.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as SchemaError

from app.core.pagination import ReportWindow
from app.finance.services.books_register import BooksRegisterService
from app.finance.services.control_accounts import ControlAccountPurpose
from app.settlements.schemas import (
    SettlementCreate,
    SettlementMethodEnum,
    SettlementModeEnum,
)
from app.settlements.services import ReceiptService
from tests.unit.test_settlements import WHEN, _Books, _receipt, _session_factory


def _create(books: _Books, **fields: object) -> SettlementCreate:
    """Build a receipt of 300 from the seeded customer."""
    payload: dict[str, object] = {
        "party_id": books.customer.id,
        "settlement_date": WHEN,
        "amount": Decimal("300.00"),
        "method": SettlementMethodEnum.BANK,
    }
    payload.update(fields)
    return SettlementCreate.model_validate(payload)


def test_cash_is_recorded_as_cash_and_a_bank_receipt_may_say_nothing() -> None:
    """Blank takes CASH for the cash method; a bank mode is never guessed."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")

    cash = _receipt(books, "100.00")
    bank = _receipt(books, "100.00", method=SettlementMethodEnum.BANK)

    assert cash.payment_mode == "CASH"
    assert bank.payment_mode is None


def test_the_mode_must_agree_with_the_method() -> None:
    """A UPI receipt into the cash account would put bank money in the till."""
    books = _Books(_session_factory()())

    with pytest.raises(SchemaError, match="goes through a bank"):
        _create(
            books,
            method=SettlementMethodEnum.CASH,
            payment_mode=SettlementModeEnum.UPI,
        )
    with pytest.raises(SchemaError, match="goes through a bank"):
        _create(books, payment_mode=SettlementModeEnum.CASH)


def test_a_cheque_keeps_its_number_and_date_and_the_bank_book_shows_them() -> None:
    """The cheque's own date is not the day it was recorded."""
    books = _Books(_session_factory()())
    books.owe_us("1000.00")

    row = ReceiptService(books.session).create(
        _create(
            books,
            payment_mode=SettlementModeEnum.CHEQUE,
            instrument_reference="004512",
            instrument_date=date(2026, 4, 18),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert row.payment_mode == "CHEQUE"
    assert row.instrument_date == date(2026, 4, 18)
    book = BooksRegisterService(books.session).money_book(
        books.firm.id,
        ControlAccountPurpose.BANK,
        ReportWindow(date(2026, 4, 1), date(2026, 4, 30)),
    )
    [entry] = [line for line in book if line.row_type == "ENTRY"]
    assert entry.mode == "Cheque"
    assert entry.instrument == "004512 18-04-2026"
