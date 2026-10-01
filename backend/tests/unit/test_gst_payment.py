"""Paying the month's GST: set-off by the statutory order, the challan posted.

Backlog 63. Section 49(5) and rule 88A decide what input credit may pay: IGST
credit first and wholly, CGST credit never against SGST nor SGST against
CGST, cess only against cess. After the challan is recorded the month's output
tax is cleared and the input tax holds only what carries forward.
"""

# ruff: noqa: D103

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.finance.models import GLPosting, LedgerAccount
from app.gst_returns.services import gstr_service
from app.gst_returns.services.gst_payment_service import (
    GstPaymentService,
    due_date,
    set_off,
)
from tests.unit.test_settlements import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

D = Decimal


def _heads(
    igst: str = "0", cgst: str = "0", sgst: str = "0", cess: str = "0"
) -> dict[str, Decimal]:
    return {"igst": D(igst), "cgst": D(cgst), "sgst": D(sgst), "cess": D(cess)}


# --- the statutory order --------------------------------------------------


def test_igst_credit_pays_igst_and_the_rest_is_cash() -> None:
    result = set_off(_heads(igst="18000"), _heads(igst="10000"))
    assert result.cash("igst") == D("8000")
    assert result.carried("igst") == D("0")


def test_cgst_credit_never_pays_sgst() -> None:
    result = set_off(_heads(sgst="5000"), _heads(cgst="5000"))
    assert result.cash("sgst") == D("5000")
    assert result.carried("cgst") == D("5000")
    assert ("cgst", "sgst") not in result.utilised


def test_sgst_credit_never_pays_cgst() -> None:
    result = set_off(_heads(cgst="3000"), _heads(sgst="3000"))
    assert result.cash("cgst") == D("3000")
    assert ("sgst", "cgst") not in result.utilised


def test_credit_beyond_the_liability_carries_forward() -> None:
    result = set_off(_heads(cgst="1000", sgst="1000"), _heads(cgst="4000", sgst="1500"))
    assert result.cash("cgst") == result.cash("sgst") == D("0")
    assert result.carried("cgst") == D("3000")
    assert result.carried("sgst") == D("500")


def test_igst_credit_is_used_wholly_first_and_split_to_leave_least_cash() -> None:
    # IGST credit 10,000 against IGST 2,000 leaves 8,000, which rule 88A says
    # must go to CGST and SGST before their own credit. CGST owes 5,000 with
    # 5,000 of its own credit; SGST owes 5,000 with none -- so the leftover
    # IGST covers SGST's shortfall first, and no cash is paid at all.
    result = set_off(
        _heads(igst="2000", cgst="5000", sgst="5000"),
        _heads(igst="10000", cgst="5000"),
    )
    assert result.used("igst") == D("10000")
    assert sum(result.cash(h) for h in ("igst", "cgst", "sgst")) == D("0")
    # The rest of the IGST credit (3,000) must still go to CGST before CGST's
    # own credit is touched, so 3,000 of CGST credit carries forward.
    assert result.carried("cgst") == D("3000")


def test_cgst_and_sgst_credit_pay_igst_after_their_own_head() -> None:
    result = set_off(_heads(igst="1000", cgst="500"), _heads(cgst="800", sgst="400"))
    assert result.utilised[("cgst", "cgst")] == D("500")
    assert result.utilised[("cgst", "igst")] == D("300")
    assert result.utilised[("sgst", "igst")] == D("400")
    assert result.cash("igst") == D("300")


def test_cess_is_paid_only_by_cess_credit() -> None:
    result = set_off(_heads(cess="700"), _heads(igst="5000"))
    assert result.cash("cess") == D("700")
    assert result.carried("igst") == D("5000")


def test_the_due_date_is_the_twentieth_of_the_next_month() -> None:
    assert due_date("2026-08") == date(2026, 9, 20)
    assert due_date("2026-12") == date(2027, 1, 20)


# --- recording the challan -------------------------------------------------


def _summary(
    output: dict[str, Decimal], itc: dict[str, Decimal]
) -> Callable[..., dict[str, object]]:
    def fake(
        self: object, *, firm_scope: UUID, from_date: date, to_date: date
    ) -> dict[str, object]:
        names = {"igst": "integrated_tax", "cgst": "central_tax", "sgst": "state_tax"}
        return {
            "outward_taxable_supplies": {
                names.get(k, k): str(v) for k, v in output.items()
            },
            "net_itc": {names.get(k, k): str(v) for k, v in itc.items()},
        }

    return fake


def _net(books: _Books, code: str) -> Decimal:
    value = books.session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(LedgerAccount.firm_id == books.firm.id, LedgerAccount.code == code)
    )
    return D(str(value))


def _account(books: _Books, code: str) -> UUID:
    found = books.session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == books.firm.id, LedgerAccount.code == code
        )
    )
    assert found is not None
    return found


def test_the_challan_clears_output_tax_and_uses_the_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary(_heads(igst="18000"), _heads(igst="10000")),
    )
    service = GstPaymentService(books.session)

    preview = service.preview(books.firm.id, "2026-04", payment_date=date(2026, 5, 20))
    assert preview.cash_total == D("8000.00")
    assert preview.days_late == 0

    row = service.record(
        books.firm.id,
        "2026-04",
        payment_date=date(2026, 5, 20),
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
        challan_cpin="26040000000001",
    )
    books.session.commit()

    assert (row.used_igst, row.cash_igst, row.carried_igst) == (
        D("10000.00"),
        D("8000.00"),
        D("0.00"),
    )
    # Output tax debited by the whole liability, input IGST credited by the
    # credit used, the bank by the cash.
    from app.finance.services.control_accounts import (
        ControlAccountPurpose,
        ControlAccountService,
    )

    control = ControlAccountService(books.session)
    output = books.session.get(
        LedgerAccount, control.resolve(books.firm.id, ControlAccountPurpose.OUTPUT_TAX)
    )
    input_igst = books.session.get(
        LedgerAccount,
        control.resolve(books.firm.id, ControlAccountPurpose.INPUT_TAX_IGST),
    )
    assert output is not None and input_igst is not None
    assert _net(books, output.code) == D("18000.00")
    assert _net(books, input_igst.code) == D("-10000.00")
    assert _net(books, "1010") == D("-8000.00")


def test_a_month_cannot_be_settled_twice_and_credit_carries_to_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary(_heads(cgst="1000", sgst="1000"), _heads(cgst="4000", sgst="1000")),
    )
    service = GstPaymentService(books.session)
    service.record(
        books.firm.id,
        "2026-04",
        payment_date=date(2026, 5, 15),
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="already recorded as paid"):
        service.record(
            books.firm.id,
            "2026-04",
            payment_date=date(2026, 5, 15),
            money_account_id=_account(books, "1010"),
            actor_id=books.actor_id,
        )

    # May: the 3,000 of CGST credit April carried is brought forward.
    preview = service.preview(books.firm.id, "2026-05")
    assert preview.previous_settled is True
    assert preview.brought_forward["cgst"] == D("3000.00")
    assert preview.set_off.credit["cgst"] == D("7000.00")


def test_late_payment_suggests_interest_and_books_it_to_an_expense(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary(_heads(igst="36500"), _heads()),
    )
    service = GstPaymentService(books.session)
    # Ten days after the 20th: 36,500 x 18% x 10 / 365 = 180.
    preview = service.preview(books.firm.id, "2026-04", payment_date=date(2026, 5, 30))
    assert preview.days_late == 10
    assert preview.suggested_interest == D("180.00")

    with pytest.raises(ValidationError, match="expense account the interest"):
        service.record(
            books.firm.id,
            "2026-04",
            payment_date=date(2026, 5, 30),
            money_account_id=_account(books, "1010"),
            actor_id=books.actor_id,
            interest_amount=D("180"),
        )
    service.record(
        books.firm.id,
        "2026-04",
        payment_date=date(2026, 5, 30),
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
        interest_amount=D("180"),
        interest_account_id=_account(books, "6500"),
    )
    books.session.commit()
    assert _net(books, "6500") == D("180.00")
    assert _net(books, "1010") == D("-36680.00")


def test_reversing_puts_the_books_back_and_only_the_latest_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary(_heads(igst="1000"), _heads(igst="400")),
    )
    service = GstPaymentService(books.session)
    april = service.record(
        books.firm.id,
        "2026-04",
        payment_date=date(2026, 5, 10),
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
    )
    may = service.record(
        books.firm.id,
        "2026-05",
        payment_date=date(2026, 6, 10),
        money_account_id=_account(books, "1010"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="Reverse 2026-05 first"):
        service.reverse(
            april.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="typo"
        )
    service.reverse(
        may.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="typo"
    )
    service.reverse(
        april.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="typo"
    )
    books.session.commit()
    assert _net(books, "1010") == D("0.00")
    assert april.status == may.status == "REVERSED"


def test_a_first_month_takes_the_opening_credit_from_the_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary(_heads(igst="5000"), _heads()),
    )
    preview = GstPaymentService(books.session).preview(
        books.firm.id, "2026-04", opening_credit=_heads(igst="2000")
    )
    assert preview.previous_settled is False
    assert preview.cash_total == D("3000.00")
