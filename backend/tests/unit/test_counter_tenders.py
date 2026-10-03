"""A counter bill paid partly in cash and partly by UPI (SEL-12, decision A90).

The bill carries its tenders; approving it records one receipt per tender --
cash to the cash book, UPI to the bank -- each allocated to the bill. Their
sum is what was received, and more than the bill is still refused.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.sales_invoice.schemas import SalesInvoiceTenderWrite
from app.sales_invoice.services import SalesInvoiceService
from app.settlements.models.settlement import Settlement
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory


def _bill(tenders: list[SalesInvoiceTenderWrite]) -> tuple[object, object, object]:
    session = _session_factory()()
    setup = _Firm(session)
    setup.stages(quotation=False, sales_order=False, delivery_note=False)
    service = SalesInvoiceService(session)
    draft = service.create_invoice(
        setup.bare_bill().model_copy(update={"received_now_tenders": tenders}),
        firm_id=setup.firm.id,
        actor_id=uuid4(),
    )
    return session, setup, draft


def test_each_tender_becomes_its_own_receipt() -> None:
    session, setup, draft = _bill([])
    total = Decimal(str(draft.grand_total))  # type: ignore[attr-defined]
    cash = (total / 2).quantize(Decimal("0.01"))
    session2, setup2, draft2 = _bill(
        [
            SalesInvoiceTenderWrite(mode="CASH", amount=cash),
            SalesInvoiceTenderWrite(
                mode="UPI", amount=total - cash, reference="UTR123"
            ),
        ]
    )
    service = SalesInvoiceService(session2)  # type: ignore[arg-type]
    assert Decimal(str(draft2.received_now_amount)) == total  # type: ignore[attr-defined]
    approved = service.approve_invoice(
        draft2.id,  # type: ignore[attr-defined]
        firm_scope=setup2.firm.id,  # type: ignore[attr-defined]
        actor_id=uuid4(),
    )
    response = service.invoice_response(approved)
    assert [(t.mode, t.amount) for t in response.received_now_tenders] == [
        ("CASH", cash),
        ("UPI", total - cash),
    ]
    receipts = {
        row.id: row
        for row in session2.scalars(select(Settlement)).all()  # type: ignore[attr-defined]
    }
    modes = sorted(
        (receipts[t.settlement_id].method, receipts[t.settlement_id].payment_mode)
        for t in response.received_now_tenders
        if t.settlement_id is not None
    )
    assert modes == [("BANK", "UPI"), ("CASH", "CASH")]


def test_tenders_worth_more_than_the_bill_are_refused() -> None:
    session, setup, draft = _bill(
        [SalesInvoiceTenderWrite(mode="CARD", amount=Decimal("100000"))]
    )
    with pytest.raises(ValidationError, match="change is handed back"):
        SalesInvoiceService(session).approve_invoice(  # type: ignore[arg-type]
            draft.id,  # type: ignore[attr-defined]
            firm_scope=setup.firm.id,  # type: ignore[attr-defined]
            actor_id=uuid4(),
        )
