"""Bulk actions on invoices, returns, notes and journals (backlog 56 A, rest).

Orders came first (#864); these extend the same rule to the documents a firm
approves in batches at the day's end: each ticked row goes through the single
action's own service, commits on its own, and a refused one holds nothing
back.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.scope import ResolvedFirmScope
from app.document_framework.schemas.bulk_actions import (
    BulkApproveRequest,
    BulkCancelRequest,
    BulkRow,
)
from app.finance.api.router import bulk_post_journal_entries
from app.finance.models import (
    AccountingPeriod,
    JournalEntry,
    JournalType,
    VoucherType,
)
from app.finance.services.journal_engine import JournalEntryEngine, JournalLineData
from app.finance.services.opening_setup import seed_finance_setup
from app.sales_invoice.api.router import (
    bulk_approve_sales_invoices,
    bulk_cancel_sales_invoices,
)
from app.sales_invoice.services import SalesInvoiceService
from tests.unit import test_sales_order_module as sales
from tests.unit.test_expenses import _Books as _Ledger
from tests.unit.test_sales_invoice_module import (
    _Billing,
    _invoice_one_line,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers


def _scope(firm_id: UUID, *codes: str) -> ResolvedFirmScope:
    return ResolvedFirmScope(
        principal=sales._principal(uuid4(), set(codes)), firm_id=firm_id
    )


def _two_draft_invoices() -> tuple[_Billing, list[UUID]]:
    setup = _Billing(_session_factory()())
    # Approval posts, so the firm needs its chart and an open period.
    seed_finance_setup(
        setup.session,
        firm_id=setup.firm.id,
        year_starts_on=date(2026, 4, 1),
        actor_id=uuid4(),
    )
    note, line = setup.dispatch()
    ids = [
        _invoice_one_line(
            setup.session,
            firm_id=setup.firm.id,
            branch_id=setup.branch.id,
            customer_id=setup.customer.id,
            note=note,
            note_line=line,
            quantity=Decimal("2"),
        ).id
        for _ in range(2)
    ]
    return setup, ids


def test_invoices_are_approved_each_on_its_own() -> None:
    setup, (first, second) = _two_draft_invoices()
    service = SalesInvoiceService(setup.session)
    service.approve_invoice(second, firm_scope=setup.firm.id, actor_id=uuid4())

    result = bulk_approve_sales_invoices(
        data=BulkApproveRequest(items=[BulkRow(id=first), BulkRow(id=second)]),
        scope=_scope(setup.firm.id, "SALES_APPROVE"),
        db=setup.session,
    ).data

    assert result is not None
    assert (result.done, result.refused) == (1, 1)
    outcomes = {row.id: row for row in result.results}
    assert outcomes[first].outcome == "DONE"
    assert outcomes[first].number
    assert outcomes[second].outcome == "REFUSED"
    setup.session.expire_all()
    assert service.get_invoice(first, firm_scope=setup.firm.id).status == "APPROVED"


def test_invoices_are_cancelled_with_one_reason() -> None:
    setup, ids = _two_draft_invoices()

    result = bulk_cancel_sales_invoices(
        data=BulkCancelRequest(
            items=[BulkRow(id=document) for document in ids], reason="Raised twice"
        ),
        scope=_scope(setup.firm.id, "SALES_CANCEL"),
        db=setup.session,
    ).data

    assert result is not None
    assert result.done == 2
    setup.session.expire_all()
    service = SalesInvoiceService(setup.session)
    assert {
        service.get_invoice(document, firm_scope=setup.firm.id).status
        for document in ids
    } == {"CANCELLED"}


def test_another_firm_s_invoice_is_refused_as_not_found() -> None:
    setup, (first, _) = _two_draft_invoices()
    result = bulk_approve_sales_invoices(
        data=BulkApproveRequest(items=[BulkRow(id=first)]),
        scope=_scope(uuid4(), "SALES_APPROVE"),
        db=setup.session,
    ).data
    assert result is not None
    assert (result.done, result.refused) == (0, 1)


def _draft_journal(books: _Ledger, reference: str) -> UUID:
    engine = JournalEntryEngine(books.session)
    on = date(2026, 4, 10)
    entry = engine.create_entry(
        firm_id=books.firm.id,
        journal_type_id=books.session.scalars(select(JournalType.id)).first(),  # type: ignore[arg-type]
        voucher_type_id=books.session.scalars(select(VoucherType.id)).first(),  # type: ignore[arg-type]
        accounting_period_id=books.session.scalars(
            select(AccountingPeriod.id).where(
                AccountingPeriod.firm_id == books.firm.id,
                AccountingPeriod.starts_on <= on,
                AccountingPeriod.ends_on >= on,
            )
        ).one(),
        journal_date=on,
        reference_number=reference,
        description="test",
        lines=[
            JournalLineData(
                ledger_account_id=books.account("6000"), debit_amount=Decimal("50")
            ),
            JournalLineData(
                ledger_account_id=books.account("1000"), credit_amount=Decimal("50")
            ),
        ],
        actor_id=books.actor_id,
    )
    books.session.commit()
    return entry.id


def test_draft_journals_are_posted_each_on_its_own() -> None:
    books = _Ledger()
    first = _draft_journal(books, "JV-A")
    second = _draft_journal(books, "JV-B")
    JournalEntryEngine(books.session).post_entry(
        second, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    result = bulk_post_journal_entries(
        data=BulkApproveRequest(items=[BulkRow(id=first), BulkRow(id=second)]),
        scope=_scope(books.firm.id, "JOURNAL_POST"),
        db=books.session,
    ).data

    assert result is not None
    assert (result.done, result.refused) == (1, 1)
    assert {row.number for row in result.results} == {"JV-A", "JV-B"}
    books.session.expire_all()
    posted = books.session.get(JournalEntry, first)
    assert posted is not None and posted.status == "POSTED"
