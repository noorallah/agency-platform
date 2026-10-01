"""A return or a debit note against a reverse-charge bill takes its tax off.

Backlog 68 row 8 left this open: the supplier charged a reverse-charge bill no
tax, so a purchase return or a debit note against it carries none of its own,
and the liability and the credit the bill raised stayed in full after the
goods went back or the price came down. Each now takes its line's share --
the share of the bill line's value -- off reverse-charge payable and input
credit, head by head, and off GSTR-3B's 3.1(d) and 4(A)(3) in its own period.
Cancelling either puts it all back.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.debit_note.schemas import DebitNoteCreate, DebitNoteLineWrite
from app.debit_note.services import DebitNoteService
from app.gst_returns.services.gstr_service import GstReturnService
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
)
from tests.unit.test_output_tax_by_head import _net, _reverse_charge_bill

D = Decimal
ZERO = D("0.00")


def _approved_bill() -> tuple[Session, UUID, UUID, UUID, PurchaseInvoiceLine]:
    """Approve the 4 x 100 reverse-charge bill: CGST 36 + SGST 36 owed."""
    session, service, firm_id, bill_id, actor_id = _reverse_charge_bill()
    service.approve_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()
    line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill_id
        )
    ).one()
    return session, firm_id, bill_id, actor_id, line


def _3b(session: Session, firm_id: UUID) -> tuple[float, float, float, float, float]:
    """Return 3.1(d)'s taxable, CGST, SGST and 4(A)(3)'s CGST, SGST for August."""
    summary = GstReturnService(session).gstr3b(
        firm_scope=firm_id, from_date=date(2026, 8, 1), to_date=date(2026, 8, 31)
    )
    inward = summary["inward_reverse_charge"]
    credit = summary["itc_reverse_charge"]
    assert isinstance(inward, dict)
    assert isinstance(credit, dict)
    return (
        inward["taxable_value"],
        inward["central_tax"],
        inward["state_tax"],
        credit["central_tax"],
        credit["state_tax"],
    )


def test_returning_half_the_goods_takes_half_the_reverse_charge_off() -> None:
    """Two of four go back: 18 + 18 no longer owed, and no longer claimed."""
    session, firm_id, bill_id, actor_id, line = _approved_bill()
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
                    "source_document_type": PurchaseReturnSourceType.PURCHASE_INVOICE,
                    "source_document_id": bill_id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_INVOICE,
                    source_document_id=bill_id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_return_quantity=D("2"),
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

    assert _net(session, firm_id, "2270") == D("-18.00"), "CGST still owed"
    assert _net(session, firm_id, "2280") == D("-18.00"), "SGST still owed"
    assert _net(session, firm_id, "1320") == D("18.00"), "CGST credit left"
    assert _net(session, firm_id, "1330") == D("18.00"), "SGST credit left"
    assert _net(session, firm_id, "2100") == D("-200.00"), "the payable halves"
    assert _3b(session, firm_id) == (200.0, 18.0, 18.0, 18.0, 18.0)

    returns.cancel_return(
        sent_back.id, firm_scope=firm_id, actor_id=actor_id, reason="Kept"
    )
    session.commit()
    assert _net(session, firm_id, "2270") == D("-36.00")
    assert _net(session, firm_id, "1320") == D("36.00")
    assert _3b(session, firm_id) == (400.0, 36.0, 36.0, 36.0, 36.0)


def test_a_debit_note_takes_its_share_of_the_reverse_charge_off() -> None:
    """100 claimed back off a 400 line: a quarter, 9 + 9, comes off."""
    session, firm_id, bill_id, actor_id, line = _approved_bill()
    notes = DebitNoteService(session)
    note = notes.create_note(
        DebitNoteCreate(
            purchase_invoice_id=bill_id,
            debit_note_date=date(2026, 8, 5),
            lines=[
                DebitNoteLineWrite(
                    purchase_invoice_line_id=line.id,
                    line_number=1,
                    taxable_amount=D("100"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    session.commit()
    notes.approve_note(note.id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()

    assert _net(session, firm_id, "2270") == D("-27.00")
    assert _net(session, firm_id, "2280") == D("-27.00")
    assert _net(session, firm_id, "1320") == D("27.00")
    assert _net(session, firm_id, "1330") == D("27.00")
    assert _net(session, firm_id, "2100") == D("-300.00")
    assert _3b(session, firm_id) == (300.0, 27.0, 27.0, 27.0, 27.0)

    notes.cancel_note(note.id, firm_scope=firm_id, actor_id=actor_id, reason="Void")
    session.commit()
    assert _net(session, firm_id, "2270") == D("-36.00")
    assert _net(session, firm_id, "1330") == D("36.00")
    assert _3b(session, firm_id) == (400.0, 36.0, 36.0, 36.0, 36.0)


def test_an_ordinary_bill_s_return_takes_no_reverse_charge_off() -> None:
    """A bill with no reverse charge gives nothing to take off."""
    from app.purchase_invoice.services.reverse_charge import reverse_charge_share

    session, firm_id, bill_id, actor_id, line = _approved_bill()
    share = reverse_charge_share(session, [(line.id, D("0"))])
    assert share.owed == {} and share.taxable == ZERO
    assert reverse_charge_share(session, []).owed == {}
    whole = reverse_charge_share(session, [(line.id, D("400"))])
    assert whole.owed == {"CGST": D("36.0000"), "SGST": D("36.0000")}
    assert PurchaseInvoiceService(session).get_invoice(
        bill_id, firm_scope=firm_id
    ).tax_total == D("0")
