"""Contra vouchers: money moved between the firm's own accounts (74 row 3).

Deposit, withdrawal, bank-to-bank and cash-to-cash. Each posts Dr the account
the money went to, Cr the one it left, on save; cancelling mirrors it. The
account the money leaves going below zero on the voucher's date is a warning,
never a refusal, and it is judged by the journal's own date.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.common.scope import ResolvedFirmScope
from app.contra.api.router import (
    cancel_contra_voucher,
    contra_money_accounts,
    contra_register,
    get_contra_voucher,
    list_contra_vouchers,
    print_contra_voucher,
    record_contra_voucher,
)
from app.contra.models import ContraVoucher
from app.contra.schemas import (
    ContraKindEnum,
    ContraVoucherCancel,
    ContraVoucherCreate,
    MoneyAccountKindEnum,
)
from app.contra.services import ContraVoucherService
from app.core.enums import TokenType
from app.core.exceptions import ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.document_framework.models import DocumentLifecycleEvent
from app.finance.models import GLPosting, JournalEntry, LedgerAccount
from app.finance.services.control_accounts import ControlAccountPurpose
from tests.unit.test_settlements import WHEN, _Books, _session_factory

CASH, BANK = "1000", "1010"


def _books() -> _Books:
    return _Books(_session_factory()())


def _scope(books: _Books) -> ResolvedFirmScope:
    user_id = uuid4()
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset(
                {"JOURNAL_VIEW", "JOURNAL_POST", "JOURNAL_REVERSE", "REPORT_VIEW"}
            ),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=books.firm.id,
    )


def _account(books: _Books, code: str) -> LedgerAccount:
    row = books.session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.firm_id == books.firm.id, LedgerAccount.code == code
        )
    )
    assert row is not None
    return row


def _open_account(
    books: _Books, code: str, name: str, *, active: bool = True
) -> LedgerAccount:
    """Open another account in the group cash and bank sit in."""
    cash = _account(books, CASH)
    row = LedgerAccount(
        firm_id=books.firm.id,
        account_group_id=cash.account_group_id,
        code=code,
        name=name,
        account_type="ASSET",
        is_active=active,
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def _move(
    books: _Books,
    source: UUID,
    target: UUID,
    amount: str,
    when: date = WHEN,
    reference: str | None = None,
) -> tuple[ContraVoucher, str | None]:
    row, warning = ContraVoucherService(books.session).create(
        ContraVoucherCreate(
            voucher_date=when,
            from_account_id=source,
            to_account_id=target,
            amount=Decimal(amount),
            reference=reference,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    return row, warning


def _legs(books: _Books, entry_id: UUID | None) -> dict[str, tuple[Decimal, Decimal]]:
    rows = books.session.execute(
        select(LedgerAccount.code, GLPosting.debit_amount, GLPosting.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(GLPosting.journal_entry_id == entry_id)
    ).all()
    return {code: (debit, credit) for code, debit, credit in rows}


# ---- money accounts ---------------------------------------------------------


def test_money_accounts_are_cash_bank_and_the_accounts_grouped_with_them() -> None:
    books = _books()
    _open_account(books, "1020", "HDFC Current Account")
    _open_account(books, "1005", "Petty Cash")
    _open_account(books, "1030", "Old Bank", active=False)

    accounts = ContraVoucherService(books.session).money_accounts(books.firm.id)
    kinds = {row.code: row.kind for row in accounts}

    assert kinds == {
        CASH: MoneyAccountKindEnum.CASH,
        "1005": MoneyAccountKindEnum.CASH,
        BANK: MoneyAccountKindEnum.BANK,
        "1020": MoneyAccountKindEnum.BANK,
    }
    # Receivables, inventory and input tax share the group and are left out:
    # they are kept by their own documents.
    assert "1100" not in kinds and "1200" not in kinds and "1300" not in kinds
    # Cash first.
    assert [row.kind for row in accounts][:2] == [MoneyAccountKindEnum.CASH] * 2


def test_an_account_that_is_not_money_is_refused_by_name() -> None:
    books = _books()
    receivables = books.account(ControlAccountPurpose.ACCOUNTS_RECEIVABLE)
    with pytest.raises(ValidationError, match="not a cash or bank account"):
        _move(books, _account(books, CASH).id, receivables, "100.00")


def test_the_same_account_twice_is_refused() -> None:
    cash = uuid4()
    with pytest.raises(PydanticValidationError, match="two different accounts"):
        ContraVoucherCreate(
            voucher_date=WHEN,
            from_account_id=cash,
            to_account_id=cash,
            amount=Decimal("10.00"),
        )


def test_a_zero_amount_is_refused() -> None:
    with pytest.raises(PydanticValidationError):
        ContraVoucherCreate(
            voucher_date=WHEN,
            from_account_id=uuid4(),
            to_account_id=uuid4(),
            amount=Decimal("0"),
        )


# ---- kinds and posting ------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "target", "kind"),
    [
        (CASH, BANK, ContraKindEnum.DEPOSIT),
        (BANK, CASH, ContraKindEnum.WITHDRAWAL),
        (BANK, "1020", ContraKindEnum.BANK_TRANSFER),
        (CASH, "1005", ContraKindEnum.CASH_TRANSFER),
    ],
)
def test_each_kind_is_derived_and_posts_dr_to_cr_from(
    source: str, target: str, kind: ContraKindEnum
) -> None:
    books = _books()
    _open_account(books, "1020", "HDFC Current Account")
    _open_account(books, "1005", "Petty Cash")

    row, _ = _move(
        books, _account(books, source).id, _account(books, target).id, "2500.00"
    )

    assert row.kind == kind.value
    assert row.voucher_number.startswith("CV")
    assert _legs(books, row.journal_entry_id) == {
        target: (Decimal("2500.00"), Decimal("0.00")),
        source: (Decimal("0.00"), Decimal("2500.00")),
    }
    entry = books.session.get(JournalEntry, row.journal_entry_id)
    assert entry is not None
    assert (entry.source_module, entry.source_id) == ("contra", row.id)
    assert entry.reference_number == row.voucher_number
    assert entry.journal_date == WHEN


def test_saving_writes_the_timeline_and_the_audit_trail() -> None:
    books = _books()
    row, _ = _move(books, _account(books, BANK).id, _account(books, CASH).id, "10.00")
    events = books.session.scalars(
        select(DocumentLifecycleEvent.action).where(
            DocumentLifecycleEvent.source_document_id == row.id
        )
    ).all()
    assert list(events) == ["POSTED"]
    audit = books.session.scalars(
        select(AuditLog.action).where(AuditLog.entity_id == row.id)
    ).all()
    assert "contra_voucher.posted" in audit


# ---- cancelling ---------------------------------------------------------------


def test_cancelling_mirrors_the_journal_and_keeps_the_original() -> None:
    books = _books()
    row, _ = _move(books, _account(books, BANK).id, _account(books, CASH).id, "800.00")

    cancelled, _ = ContraVoucherService(books.session).cancel(
        row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="Typed twice"
    )
    books.session.commit()

    assert cancelled.status == "CANCELLED"
    assert cancelled.cancel_reason == "Typed twice"
    assert _legs(books, cancelled.reversal_journal_entry_id) == {
        BANK: (Decimal("800.00"), Decimal("0.00")),
        CASH: (Decimal("0.00"), Decimal("800.00")),
    }
    original = books.session.get(JournalEntry, row.journal_entry_id)
    mirror = books.session.get(JournalEntry, cancelled.reversal_journal_entry_id)
    assert original is not None and mirror is not None
    assert original.status == "REVERSED"
    assert mirror.reversal_of_id == original.id
    assert mirror.reference_number == f"{row.voucher_number}-CAN"
    service = ContraVoucherService(books.session)
    assert service.balance_on(
        _account(books, CASH).id, firm_id=books.firm.id, on=date(2027, 3, 31)
    ) == Decimal("0.00")
    events = books.session.scalars(
        select(DocumentLifecycleEvent.action).where(
            DocumentLifecycleEvent.source_document_id == row.id
        )
    ).all()
    assert list(events) == ["POSTED", "CANCELLED"]


def test_a_voucher_cancels_once_and_only_with_a_reason() -> None:
    books = _books()
    row, _ = _move(books, _account(books, BANK).id, _account(books, CASH).id, "50.00")
    service = ContraVoucherService(books.session)
    with pytest.raises(ValidationError, match="Say why"):
        service.cancel(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason=" "
        )
    service.cancel(row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="x")
    books.session.commit()
    with pytest.raises(ValidationError, match="already been cancelled"):
        service.cancel(
            row.id, firm_id=books.firm.id, actor_id=books.actor_id, reason="x"
        )


# ---- the below-zero warning ---------------------------------------------------


def test_depositing_cash_the_books_do_not_hold_warns_but_saves() -> None:
    books = _books()
    row, warning = _move(
        books, _account(books, CASH).id, _account(books, BANK).id, "500.00"
    )
    assert row.status == "POSTED"
    assert warning is not None
    assert "1000 Cash stands at -500.00 on 20-04-2026" in warning


def test_no_warning_when_the_money_was_there_that_day() -> None:
    books = _books()
    cash, bank = _account(books, CASH).id, _account(books, BANK).id
    _move(books, bank, cash, "1000.00", when=date(2026, 4, 10))
    _, warning = _move(books, cash, bank, "400.00", when=date(2026, 4, 20))
    assert warning is None


def test_a_back_dated_deposit_is_judged_on_its_own_date() -> None:
    books = _books()
    cash, bank = _account(books, CASH).id, _account(books, BANK).id
    # Cash arrives on the 20th...
    _move(books, bank, cash, "1000.00", when=date(2026, 4, 20))
    # ...and a deposit keyed afterwards is dated the 15th, before it was there.
    _, warning = _move(books, cash, bank, "400.00", when=date(2026, 4, 15))
    assert warning is not None
    assert "-400.00 on 15-04-2026" in warning


def test_the_router_says_the_warning_in_its_message() -> None:
    books = _books()
    answer = record_contra_voucher(
        ContraVoucherCreate(
            voucher_date=WHEN,
            from_account_id=_account(books, CASH).id,
            to_account_id=_account(books, BANK).id,
            amount=Decimal("75.00"),
        ),
        scope=_scope(books),
        response=Response(),
        db=books.session,
    )
    assert answer.data is not None
    assert answer.message is not None
    assert "recorded and posted. Warning:" in answer.message
    assert answer.data.balance_warning is not None
    assert answer.data.kind == ContraKindEnum.DEPOSIT


# ---- reads, register and print ------------------------------------------------


def test_list_get_register_and_print() -> None:
    books = _books()
    cash, bank = _account(books, CASH).id, _account(books, BANK).id
    first, _ = _move(books, bank, cash, "300.00", when=date(2026, 4, 5))
    second, _ = _move(
        books, cash, bank, "100.00", when=date(2026, 4, 25), reference="SLIP-9"
    )
    scope = _scope(books)

    page = list_contra_vouchers(
        scope=scope, db=books.session, date_from=date(2026, 4, 20)
    )
    assert [row.voucher_number for row in page.data] == [second.voucher_number]
    assert page.data[0].from_account_name == "Cash"
    assert page.data[0].to_account_name == "Bank"

    one = get_contra_voucher(
        second.id, scope=scope, response=Response(), db=books.session
    )
    assert one.data is not None and one.data.reference == "SLIP-9"

    register = contra_register(scope=scope, db=books.session)
    assert [row.voucher_number for row in register.data] == [
        second.voucher_number,
        first.voucher_number,
    ]

    accounts = contra_money_accounts(scope=scope, db=books.session)
    assert accounts.data is not None and len(accounts.data) == 2

    printed = print_contra_voucher(first.id, scope=scope, db=books.session)
    assert printed.media_type == "application/pdf"

    cancelled = cancel_contra_voucher(
        first.id,
        ContraVoucherCancel(reason="Wrong day"),
        scope=scope,
        response=Response(),
        db=books.session,
    )
    assert cancelled.data is not None
    assert cancelled.data.status.value == "CANCELLED"


def test_the_printed_voucher_is_a_pdf() -> None:
    books = _books()
    row, _ = _move(books, _account(books, BANK).id, _account(books, CASH).id, "1234.50")
    pdf, filename = ContraVoucherService(books.session).render_pdf(
        row.id, firm_id=books.firm.id
    )
    assert pdf.startswith(b"%PDF")
    assert filename == f"{row.voucher_number}.pdf"
