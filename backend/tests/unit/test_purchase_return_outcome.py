"""What a purchase return comes back as: credit, replacement or refund.

Backlog 69 row 7. A return off the goods receipt leaves the supplier owing the
firm (D-FIN-19). Until now the only way to collect that was to set it against
the supplier's next bill. A supplier who pays the money back, or who sends the
goods again, had nowhere to be recorded: the credit sat on the account and the
order read as fully received with goods missing from the shelf.

``outcome`` says which it is. A REFUND is paid back through
``/payments/supplier-credits/{id}/refunds`` (Dr cash or bank, Cr payables), and
the credit nets it. A REPLACEMENT reopens the order line for the quantity sent
back, so the order reads as partly received and the next receipt may take it in.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, JournalLine
from app.goods_receipt.services.goods_receipt_service import GoodsReceiptService
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.services.line_quantities import order_line_quantities
from app.purchase_invoice.services.payables_report import PayablesReportService
from app.purchase_return.api.router import set_purchase_return_outcome
from app.purchase_return.schemas import PurchaseReturnOutcomeRequest
from app.settlements.api.router import (
    list_supplier_refunds,
    record_supplier_refund,
    reverse_vendor_supplier_refund,
)
from app.settlements.models import SettlementMethod
from app.settlements.schemas import (
    SettlementMethodEnum,
    SupplierRefundCreate,
    SupplierRefundReverse,
)
from app.settlements.services.supplier_credits import (
    refund_supplier_credit,
    reverse_supplier_refund,
    supplier_credits,
)
from app.vendors.services.statement_service import SupplierStatementService
from tests.unit.test_purchase_return_module import (
    _approved_return,
    _firm,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers

WHEN = date(2026, 8, 3)


def _scope(firm_id: object) -> object:
    """Build the resolved firm scope a request carries."""
    return SimpleNamespace(firm_id=firm_id, actor_id=uuid4())


def _available(session: object, firm_id: object, return_id: object) -> Decimal:
    """Return what is left of one return's credit."""
    found = supplier_credits(
        session,  # type: ignore[arg-type]
        firm_id=firm_id,  # type: ignore[arg-type]
        source_ids=[return_id],  # type: ignore[list-item]
    )
    return found[0].available_amount if found else Decimal("0")


def test_a_refund_return_is_paid_back_and_the_credit_nets_it() -> None:
    """Record, refuse an over-refund and a cancel, reverse, and it is free again."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())
    assert _available(session, firm.id, row.id) == Decimal("400.00")

    # Meant to be set against a bill: paid back only once it says refund.
    with pytest.raises(ValidationError, match="not a refund"):
        refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("100"),
            refunded_on=WHEN,
            method=SettlementMethod.BANK,
            actor_id=uuid4(),
        )
    session.rollback()
    changed = set_purchase_return_outcome(
        return_id=row.id,
        data=PurchaseReturnOutcomeRequest(outcome="REFUND"),
        scope=_scope(firm.id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert changed is not None
    assert changed.outcome == "REFUND"

    refund = record_supplier_refund(
        return_id=row.id,
        payload=SupplierRefundCreate(
            amount=Decimal("300"),
            refunded_on=WHEN,
            method=SettlementMethodEnum.BANK,
            reference="UTR-1",
        ),
        scope=_scope(firm.id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert refund is not None
    assert refund.status == "POSTED"
    assert _available(session, firm.id, row.id) == Decimal("100.00")
    entry = session.get(JournalEntry, refund.journal_entry_id)
    assert entry is not None
    assert entry.source_module == "supplier_credit_refund"

    # No more than is left of it.
    with pytest.raises(ValidationError, match="only 100.00 of credit left"):
        refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("150"),
            refunded_on=WHEN,
            method=SettlementMethod.CASH,
            actor_id=uuid4(),
        )
    session.rollback()

    # The money stands, so the return cannot be cancelled or made a credit.
    with pytest.raises(ValidationError, match="Reverse the refund first"):
        service.cancel_return(row.id, firm_scope=firm.id, actor_id=uuid4(), reason="x")
    session.rollback()
    with pytest.raises(ValidationError, match="Reverse the refund first"):
        service.set_outcome(row.id, "CREDIT", firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    reversed_refund = reverse_vendor_supplier_refund(
        refund_id=refund.id,
        payload=SupplierRefundReverse(reason="Bounced"),
        scope=_scope(firm.id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert reversed_refund is not None
    assert reversed_refund.status == "REVERSED"
    assert reversed_refund.reversal_journal_entry_id is not None
    assert _available(session, firm.id, row.id) == Decimal("400.00")
    with pytest.raises(ValidationError, match="already been reversed"):
        reverse_vendor_supplier_refund(
            refund_id=refund.id,
            payload=SupplierRefundReverse(reason="Again"),
            scope=_scope(firm.id),  # type: ignore[arg-type]
            db=session,
        )
    session.rollback()

    listed = list_supplier_refunds(
        return_id=row.id,
        scope=_scope(firm.id),  # type: ignore[arg-type]
        db=session,
    ).data
    assert [item.status for item in listed or []] == ["REVERSED"]
    # With nothing standing, the cancel goes through.
    service.cancel_return(row.id, firm_scope=firm.id, actor_id=uuid4(), reason="x")
    assert supplier_credits(session, firm_id=firm.id) == []


def test_a_refund_and_its_reversal_are_on_the_supplier_statement() -> None:
    """D-BUY-48: the statement closed wrong by every refund a supplier paid."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())
    service.set_outcome(row.id, "REFUND", firm_scope=firm.id, actor_id=uuid4())
    # The fixture's bill is a bare row with no journal, so the check starts
    # out by its 1,000.00; what matters is that a refund does not move it.
    unbooked = (
        PayablesReportService(session)
        .report(firm.id, as_of=date(2027, 3, 31), vendor_id=row.vendor_id)
        .books_check.difference
    )
    refund = refund_supplier_credit(
        session,
        firm_id=firm.id,
        source_id=row.id,
        amount=Decimal("300"),
        refunded_on=row.return_date,
        method=SettlementMethod.BANK,
        actor_id=uuid4(),
    )
    session.commit()
    statements = SupplierStatementService(session)
    period = {"from_date": date(2026, 4, 1), "to_date": date(2027, 3, 31)}

    def payables() -> Decimal:
        """Return what the payables account holds, straight off the journal."""
        account = statements._payables_account(firm.id)
        total = session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalLine.credit_amount - JournalLine.debit_amount), 0
                )
            ).where(JournalLine.ledger_account_id == account)
        )
        return Decimal(str(total))

    def books_difference() -> Decimal | None:
        """Return the books check of the report narrowed to this supplier."""
        return (
            PayablesReportService(session)
            .report(firm.id, as_of=date(2027, 3, 31), vendor_id=row.vendor_id)
            .books_check.difference
        )

    statement = statements.statement(row.vendor_id, firm_scope=firm.id, **period)
    refunds = [line for line in statement.lines if line.transaction_type == "REFUND"]
    assert [(line.debit, line.credit) for line in refunds] == [
        (Decimal("0.00"), Decimal("300.00"))
    ]
    assert statement.closing_balance == payables()
    assert statements.balances(firm_scope=firm.id, as_of=date(2027, 3, 31)) == {
        row.vendor_id: payables()
    }
    assert books_difference() == unbooked

    reverse_supplier_refund(
        session, firm_id=firm.id, refund_id=refund.id, reason="x", actor_id=uuid4()
    )
    session.commit()
    statement = statements.statement(row.vendor_id, firm_scope=firm.id, **period)
    assert [
        (line.debit, line.credit)
        for line in statement.lines
        if line.transaction_type == "REFUND_REVERSAL"
    ] == [(Decimal("300.00"), Decimal("0.00"))]
    assert statement.closing_balance == payables()
    assert books_difference() == unbooked


def test_a_refund_waits_for_the_return_and_never_runs_ahead_of_today() -> None:
    """Before the return is completed there is no credit to pay back."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    service.set_outcome(row.id, "REFUND", firm_scope=firm.id, actor_id=uuid4())

    with pytest.raises(ValidationError, match="leaves no credit"):
        refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("10"),
            refunded_on=WHEN,
            method=SettlementMethod.BANK,
            actor_id=uuid4(),
        )
    session.rollback()
    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())
    with pytest.raises(ValidationError, match="on or after the return"):
        refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("10"),
            refunded_on=date(2026, 8, 1),
            method=SettlementMethod.BANK,
            actor_id=uuid4(),
        )
    session.rollback()
    with pytest.raises(ValidationError, match="future date"):
        refund_supplier_credit(
            session,
            firm_id=firm.id,
            source_id=row.id,
            amount=Decimal("10"),
            refunded_on=date(2099, 1, 1),
            method=SettlementMethod.BANK,
            actor_id=uuid4(),
        )


def _order_of(session: object) -> PurchaseOrder:
    """Return the fixture's one purchase order."""
    order = session.scalar(select(PurchaseOrder))  # type: ignore[attr-defined]
    assert order is not None
    return order  # type: ignore[no-any-return]


def test_a_replacement_return_reopens_the_order_line() -> None:
    """Receive 10, send 4 back to be replaced: the order owes 4 again."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    order = _order_of(session)
    receipts = GoodsReceiptService(session)
    receipts.resync_order_status(order, firm_id=firm.id, actor_id=uuid4())
    session.commit()
    assert order.status == "RECEIVED"

    service.set_outcome(row.id, "REPLACEMENT", firm_scope=firm.id, actor_id=uuid4())
    # Still only approved: nothing has gone back yet, so nothing is owed.
    assert order.status == "RECEIVED"
    service.complete_return(row.id, firm_scope=firm.id, actor_id=uuid4())
    session.refresh(order)
    assert order.status == "PARTIALLY_RECEIVED"

    line = session.scalar(select(PurchaseOrderLine))
    assert line is not None
    figures = order_line_quantities(session, [line])[line.id]
    assert figures.replaced == Decimal("4")
    assert figures.pending_receipt == Decimal("4")
    # The receipt cap now leaves room for the four again.
    assert receipts._received_quantities_for_po(order.id, firm_id=firm.id) == {
        line.id: Decimal("6")
    }

    # Changed to a credit after all: the order is whole again.
    service.set_outcome(row.id, "CREDIT", firm_scope=firm.id, actor_id=uuid4())
    session.refresh(order)
    assert order.status == "RECEIVED"
    assert order_line_quantities(session, [line])[line.id].pending_receipt == 0

    # And back; cancelling the return takes the replacement off too.
    service.set_outcome(row.id, "REPLACEMENT", firm_scope=firm.id, actor_id=uuid4())
    session.refresh(order)
    assert order.status == "PARTIALLY_RECEIVED"
    service.cancel_return(row.id, firm_scope=firm.id, actor_id=uuid4(), reason="x")
    session.refresh(order)
    assert order.status == "RECEIVED"


def test_a_return_defaults_to_credit_and_a_cancelled_one_takes_no_outcome() -> None:
    """New returns are credits; a cancelled return cannot be given an outcome."""
    session = _session_factory()()
    firm = _firm(session)
    service, row, _ = _approved_return(session, firm_id=firm.id)
    assert service.return_response(row).outcome == "CREDIT"
    with pytest.raises(ValidationError, match="CREDIT, REPLACEMENT or REFUND"):
        service.set_outcome(row.id, "SWAP", firm_scope=firm.id, actor_id=uuid4())
    service.cancel_return(row.id, firm_scope=firm.id, actor_id=uuid4(), reason="x")
    with pytest.raises(ValidationError, match="comes back as nothing"):
        service.set_outcome(row.id, "REFUND", firm_scope=firm.id, actor_id=uuid4())
