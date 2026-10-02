"""Backlog ACC-5: what is unfinished in a month, asked before it closes.

Closing lists draft journals and documents, approved documents no journal
names, money held on account and GST returns not recorded as filed. A firm
that warns (the default) closes anyway; one that blocks is refused while any
of the first three stands, and is told which.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry
from app.finance.schemas import AccountingPeriodUpdate, PeriodStatusEnum
from app.finance.services import FinanceService
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.period_close_checks import PeriodCloseChecks
from app.gst_returns.models import GstReturnFiling
from app.settlements.schemas import SettlementCreate, SettlementMethodEnum
from app.settlements.services import ReceiptService
from tests.unit.test_credit_note import WHEN, _Books
from tests.unit.test_credit_note import _session_factory as _note_session
from tests.unit.test_finance_module import _Book, _firm, _session_factory

APRIL = (date(2026, 4, 1), date(2026, 4, 30))


def _books() -> _Books:
    """Return the credit note fixture with its invoice out of the way.

    The fixture writes its invoice straight in as APPROVED with no journal --
    exactly what the check exists to find -- so it is given no value here.
    """
    books = _Books(_note_session()())
    books.invoice.grand_total = Decimal("0")
    books.session.commit()
    return books


def _codes(books: _Books) -> dict[str, list[str]]:
    """Return each listed item's code with its examples, for April."""
    result = PeriodCloseChecks(books.session).run(books.firm.id, *APRIL)
    return {item.code: item.examples for item in result.items}


def test_a_draft_document_and_an_unposted_one_are_named() -> None:
    """A note never approved, and one approved whose journal is gone."""
    books = _books()
    draft = books.note("10")
    assert f"Credit note {draft.credit_note_number}" in _codes(books)["DRAFT_DOCUMENTS"]

    approved = books.approved("10")
    assert "UNPOSTED_DOCUMENTS" not in _codes(books)
    # The journal no longer names the note: a posting that went missing.
    entry = books.session.get(JournalEntry, approved.journal_entry_id)
    assert entry is not None
    entry.source_id = uuid4()
    books.session.commit()

    assert _codes(books)["UNPOSTED_DOCUMENTS"] == [
        f"Credit note {approved.credit_note_number}"
    ]


def test_unfiled_returns_are_listed_until_marked_filed() -> None:
    """April traded, so its GSTR-1 and GSTR-3B are owed; filing clears them."""
    books = _books()
    assert _codes(books)["GST_NOT_FILED"] == ["GSTR-1 2026-04", "GSTR-3B 2026-04"]

    for kind in ("GSTR1", "GSTR3B"):
        books.session.add(
            GstReturnFiling(
                firm_id=books.firm.id,
                return_type=kind,
                return_period="2026-04",
                filed_on=date(2026, 5, 11),
            )
        )
    books.session.commit()

    assert "GST_NOT_FILED" not in _codes(books)


def test_a_firm_that_warns_closes_and_one_that_blocks_is_refused() -> None:
    """The policy decides; a draft journal is what stands in the way."""
    session = _session_factory()()
    firm = _firm(session)
    actor = uuid4()
    book = _Book(session, firm.id, actor)
    JournalEntryEngine(session).create_entry(
        firm_id=firm.id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 12),
        reference_number="JV-0001",
        description="Left in draft",
        lines=[
            JournalLineData(ledger_account_id=book.cash.id, debit_amount=Decimal("5")),
            JournalLineData(
                ledger_account_id=book.sales.id, credit_amount=Decimal("5")
            ),
        ],
        actor_id=actor,
    )
    session.commit()
    checks = PeriodCloseChecks(session)
    assert checks.close_check(firm.id) == "WARN"
    listed = checks.run(firm.id, *APRIL)
    assert [item.code for item in listed.items] == ["DRAFT_JOURNALS"]
    assert listed.items[0].examples == ["JV-0001"]
    assert listed.refuses is False

    checks.set_close_check(firm.id, "block", actor_id=actor)
    session.commit()
    with pytest.raises(ValidationError, match=r"P1 cannot be closed.*JV-0001"):
        FinanceService(session).update_accounting_period(
            book.period.id,
            AccountingPeriodUpdate(status=PeriodStatusEnum.CLOSED),
            firm_id=firm.id,
            actor_id=actor,
        )
    session.rollback()

    checks.set_close_check(firm.id, "WARN", actor_id=actor)
    closed = FinanceService(session).update_accounting_period(
        book.period.id,
        AccountingPeriodUpdate(status=PeriodStatusEnum.CLOSED),
        firm_id=firm.id,
        actor_id=actor,
    )
    assert closed.status == "CLOSED"
    trail = session.scalars(
        select(AuditLog).where(
            AuditLog.action == "finance.period_close_settings.updated"
        )
    ).all()
    assert [row.after_data for row in trail] == [
        {"close_check": "BLOCK"},
        {"close_check": "WARN"},
    ]


def test_only_warn_or_block_is_a_policy() -> None:
    """Anything else is refused by name."""
    session = _session_factory()()
    firm = _firm(session)

    with pytest.raises(ValidationError, match="WARN or BLOCK"):
        PeriodCloseChecks(session).set_close_check(firm.id, "MAYBE", actor_id=uuid4())


def test_money_on_account_is_listed_and_never_refuses() -> None:
    """An advance is often deliberate; a blocking firm still closes over it."""
    books = _books()
    ReceiptService(books.session).create(
        SettlementCreate(
            party_id=books.customer.id,
            settlement_date=WHEN,
            amount=Decimal("50.00"),
            method=SettlementMethodEnum.CASH,
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    checks = PeriodCloseChecks(books.session)
    checks.set_close_check(books.firm.id, "BLOCK", actor_id=books.actor_id)

    result = checks.run(books.firm.id, *APRIL)

    [held] = [item for item in result.items if item.code == "MONEY_ON_ACCOUNT"]
    assert held.blocks is False and held.examples[0].endswith("(50.00)")
    assert result.refuses is False
