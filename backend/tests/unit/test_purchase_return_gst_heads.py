"""D-BUY-28: a return off a goods receipt reverses the GST heads its bill took.

The desktop raises a purchase return off the goods receipt, and such a line
named no bill, so `return_tax_by_component` found no components and the whole
tax was credited to the undivided `1300 Input Tax` -- while the bill had debited
`1320 Input CGST` and `1330 Input SGST`. QA01's PR-2026-2027-000001 left the
ledger at CGST 144 Dr, SGST 144 Dr, Input Tax 36 Cr. A receipt line now
reverses whatever billed it, head by head, exactly as a line raised off the
bill itself does.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.finance.models import JournalEntry
from app.goods_receipt.models import GoodsReceiptLine
from app.purchase_invoice.models import PurchaseInvoiceLine, PurchaseInvoiceLineTax
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
    return_tax_by_component,
)
from tests.unit.test_input_credit_eligibility import _bill
from tests.unit.test_output_tax_by_head import _legs, _net

D = Decimal


def _return_off_the_receipt(
    session: Session, firm_id: UUID, actor_id: UUID, bill_line: PurchaseInvoiceLine
) -> UUID:
    """Send 2 of the 4 back against the goods receipt the bill line billed.

    The receipt is cut to the 4 the bill billed, so the 2 go back off billed
    goods -- a debit note. Off the 6 nothing billed they would come off goods
    received not invoiced instead, with no tax (D-BUY-26).
    """
    receipt_line = session.get(GoodsReceiptLine, bill_line.source_document_line_id)
    assert receipt_line is not None
    receipt_line.current_receipt_quantity = D("4")
    receipt_line.accepted_quantity = D("4")
    session.commit()
    warehouse_id = session.scalars(
        select(Warehouse.id).where(Warehouse.firm_id == firm_id)
    ).one()
    returns = PurchaseReturnService(session)
    sent_back = returns.create_return(
        PurchaseReturnCreate(
            return_date=date(2026, 8, 3),
            warehouse_id=warehouse_id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": bill_line.source_document_id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=bill_line.source_document_id,
                    source_document_line_id=bill_line.source_document_line_id,
                    line_number=1,
                    current_return_quantity=D("2"),
                    unit_price=D("100"),
                    warehouse_id=warehouse_id,
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    returns.approve_return(sent_back.id, firm_scope=firm_id, actor_id=actor_id)
    returns.complete_return(sent_back.id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()
    return sent_back.id


def _journal(session: Session, return_id: UUID) -> dict[str, tuple[D, D]]:
    """Return the legs of the return's own journal, not its reversal."""
    entry_id = session.scalars(
        select(JournalEntry.id).where(
            JournalEntry.source_module == "purchase_return",
            JournalEntry.source_id == return_id,
            JournalEntry.reversal_of_id.is_(None),
        )
    ).one()
    return _legs(session, entry_id)


def _balanced(legs: dict[str, tuple[D, D]]) -> bool:
    """Say whether a journal's debits equal its credits."""
    return sum(d for d, _ in legs.values()) == sum(c for _, c in legs.values())


def test_a_return_off_the_receipt_reverses_cgst_and_sgst_not_input_tax() -> None:
    """2 of 4 at 100 back: CGST 18 and SGST 18 credited, 1300 untouched."""
    session, firm_id, _, actor_id, bill_line = _bill()
    assert bill_line.source_document_type == "GOODS_RECEIPT"

    return_id = _return_off_the_receipt(session, firm_id, actor_id, bill_line)

    legs = _journal(session, return_id)
    assert legs["1320"] == (D("0.00"), D("18.00")), "CGST reversed on its head"
    assert legs["1330"] == (D("0.00"), D("18.00")), "SGST reversed on its head"
    assert "1300" not in legs, "nothing on the undivided input tax account"
    assert legs["2100"] == (D("236.00"), D("0.00"))
    assert _balanced(legs)
    assert _net(session, firm_id, "1300") == D("0.00")
    assert _net(session, firm_id, "1320") == D("18.00")
    assert _net(session, firm_id, "1330") == D("18.00")
    assert return_tax_by_component(session, return_id) == {
        "CGST": D("18.0000"),
        "SGST": D("18.0000"),
    }, "GSTR-3B reads the same split the ledger posted"

    # Cancelling mirrors the original, so the heads go back to the bill's.
    PurchaseReturnService(session).cancel_return(
        return_id, firm_scope=firm_id, actor_id=actor_id, reason="Kept"
    )
    session.commit()
    assert _net(session, firm_id, "1300") == D("0.00")
    assert _net(session, firm_id, "1320") == D("36.00")
    assert _net(session, firm_id, "1330") == D("36.00")


def test_an_interstate_bill_has_its_igst_reversed() -> None:
    """A bill that charged IGST has the return take it off IGST, not 1300."""
    session, firm_id, _, actor_id, bill_line = _bill()
    rows = session.scalars(
        select(PurchaseInvoiceLineTax)
        .where(PurchaseInvoiceLineTax.purchase_invoice_line_id == bill_line.id)
        .order_by(PurchaseInvoiceLineTax.component_code)
    ).all()
    # The bill's breakup recorded as one IGST head of 72, as an interstate
    # supply would have been charged.
    rows[0].component_code = "IGST"
    rows[0].amount = D("72")
    rows[1].is_deleted = True
    session.commit()

    return_id = _return_off_the_receipt(session, firm_id, actor_id, bill_line)

    legs = _journal(session, return_id)
    assert legs["1310"] == (D("0.00"), D("36.00")), "IGST reversed on its head"
    assert "1300" not in legs
    assert "1320" not in legs
    assert "1330" not in legs
    assert _balanced(legs)


def test_a_blocked_bill_has_its_tax_taken_back_off_the_cost_not_input_tax() -> None:
    """D-TAX-1: what the bill could not claim is not reversed off input tax."""
    session, firm_id, _, actor_id, bill_line = _bill(rule_blocks=True)

    return_id = _return_off_the_receipt(session, firm_id, actor_id, bill_line)

    legs = _journal(session, return_id)
    assert legs["5450"] == (D("0.00"), D("36.00"))
    assert "1300" not in legs
    assert "1320" not in legs
    assert "1330" not in legs
    assert _balanced(legs)
    assert _net(session, firm_id, "5450") == D("36.00")
