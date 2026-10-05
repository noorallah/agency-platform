"""Rule 37: credit on a bill unpaid 180 days is reversed, and reclaimed (78.4).

The bill is the one `test_input_credit_eligibility` builds: 4 x 100 at 18%
local GST, CGST 36 + SGST 36, dated 2 August 2026, so its 180 days end on
29 January 2027.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.gst_returns.models import ItcReversal
from app.gst_returns.services.gstr_service import GstReturnService
from app.gst_returns.services.rule37 import Rule37Service
from app.purchase_invoice.models import PurchaseInvoice
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService
from app.tax.models import GstComplianceSettings
from tests.unit.test_input_credit_eligibility import _bill
from tests.unit.test_output_tax_by_head import _net

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
DAY_180 = date(2027, 1, 29)
LATER = date(2027, 2, 10)


def _mode(session: Session, firm_id: UUID, mode: str) -> None:
    session.add(GstComplianceSettings(firm_id=firm_id, rule37_mode=mode))
    session.commit()


def _pay(
    session: Session, firm_id: UUID, bill_id: UUID, actor_id: UUID, amount: str
) -> None:
    bill = session.get(PurchaseInvoice, bill_id)
    assert bill is not None
    PaymentService(session).create(
        SettlementCreate(
            party_id=bill.vendor_id,
            settlement_date=date(2027, 2, 20),
            amount=D(amount),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(invoice_id=bill_id, amount=D(amount))
            ],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    session.commit()


def test_nothing_is_due_inside_180_days() -> None:
    session, firm_id, _, _, _ = _bill()

    assert Rule37Service(session).rows(firm_id=firm_id, as_of=DAY_180) == []


def test_an_unpaid_bill_past_180_days_reverses_all_its_credit() -> None:
    session, firm_id, bill_id, _, _ = _bill()

    rows = Rule37Service(session).rows(firm_id=firm_id, as_of=LATER)

    assert [(row.purchase_invoice_id, row.action) for row in rows] == [
        (bill_id, "REVERSE")
    ]
    assert (rows[0].move["cgst"], rows[0].move["sgst"]) == (D("36.00"), D("36.00"))
    assert rows[0].days == 192


def test_a_part_paid_bill_reverses_the_unpaid_share() -> None:
    session, firm_id, bill_id, actor_id, _ = _bill()
    bill = session.get(PurchaseInvoice, bill_id)
    assert bill is not None
    half = str((D(str(bill.grand_total)) / 2).quantize(D("0.01")))
    _pay(session, firm_id, bill_id, actor_id, half)

    row = Rule37Service(session).rows(firm_id=firm_id, as_of=LATER)[0]

    assert row.move["cgst"] == D("18.00")


def test_report_mode_lists_but_does_not_post() -> None:
    session, firm_id, _, actor_id, _ = _bill()

    with pytest.raises(ValidationError, match="reported, not posted"):
        Rule37Service(session).post(firm_id=firm_id, as_of=LATER, actor_id=actor_id)


def test_posting_reverses_to_the_books_and_3b_then_payment_reclaims() -> None:
    session, firm_id, bill_id, actor_id, _ = _bill()
    _mode(session, firm_id, "POST")
    service = Rule37Service(session)

    made = service.post(firm_id=firm_id, as_of=LATER, actor_id=actor_id)
    session.commit()

    assert [row.movement for row in made] == ["REVERSAL"]
    assert _net(session, firm_id, "1320") == D("0.00")
    assert _net(session, firm_id, "5450") == D("72.00")
    february = GstReturnService(session).gstr3b(
        firm_scope=firm_id, from_date=date(2027, 2, 1), to_date=date(2027, 2, 28)
    )
    assert float(february["itc_reversed"]["central_tax"]) == 36.0  # type: ignore[index]
    assert float(february["itc_reversed_rule37"]["central_tax"]) == 36.0  # type: ignore[index]
    # Posting again moves nothing: what should stand reversed already does.
    assert service.rows(firm_id=firm_id, as_of=LATER) == []

    bill = session.get(PurchaseInvoice, bill_id)
    assert bill is not None
    _pay(session, firm_id, bill_id, actor_id, str(D(str(bill.grand_total))))
    rows = service.rows(firm_id=firm_id, as_of=date(2027, 3, 5))
    assert [row.action for row in rows] == ["RECLAIM"]
    service.post(firm_id=firm_id, as_of=date(2027, 3, 5), actor_id=actor_id)
    session.commit()

    assert _net(session, firm_id, "5450") == D("0.00")
    assert _net(session, firm_id, "1320") == D("36.00")
    march = GstReturnService(session).gstr3b(
        firm_scope=firm_id, from_date=date(2027, 3, 1), to_date=date(2027, 3, 31)
    )
    assert float(march["itc_reclaimed"]["central_tax"]) == 36.0  # type: ignore[index]
    assert float(march["eligible_itc"]["central_tax"]) == 36.0  # type: ignore[index]
    movements = session.scalars(
        select(ItcReversal.movement).order_by(ItcReversal.movement_date)
    ).all()
    assert movements == ["REVERSAL", "RECLAIM"]


def _in_usd(session: Session, bill_id: UUID, rate: str = "83") -> PurchaseInvoice:
    """Restate the fixture's bill as one in USD, stamped as saving one stamps it."""
    from app.finance.currency import to_base

    bill = session.get(PurchaseInvoice, bill_id)
    assert bill is not None
    bill.currency_code = "USD"
    bill.exchange_rate = D(rate)
    bill.base_tax_total = to_base(bill.tax_total, D(rate))
    bill.base_grand_total = bill.base_tax_total + to_base(
        bill.grand_total - bill.tax_total, D(rate)
    )
    session.commit()
    return bill


def test_a_foreign_bill_reverses_its_credit_in_rupees() -> None:
    """D-CMP-23: 36 USD of CGST at 83 is 2,988.00 of credit, never 36.00."""
    session, firm_id, bill_id, _, _ = _bill()
    bill = _in_usd(session, bill_id)

    (row,) = Rule37Service(session).rows(firm_id=firm_id, as_of=LATER)

    assert (row.move["cgst"], row.move["sgst"]) == (D("2988.00"), D("2988.00"))
    assert row.bill_total == bill.base_grand_total == D("39176.00")
    assert row.outstanding == D("39176.00")
