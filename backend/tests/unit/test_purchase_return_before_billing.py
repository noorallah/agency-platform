"""D-BUY-26: a return before billing reverses GRNI and lowers what is left to bill.

QA01's PR-2026-2027-000001 sent 2 of 6 received (cost 100, GST 18%) back off a
goods receipt nothing had billed yet, and posted it as a debit note: Dr Trade
Payables 236 / Cr Inventory 200 / Cr Input Tax 36. No bill had raised the
payable and no input credit had been taken, so until a bill arrived the books
showed the supplier at -236 and input tax at -36 -- and the bill then offered
all 6, deducting the 2 a second time when the supplier billed only 4.

A receipt line's return is now taken first off what is still to bill: that
part reverses the receipt's accrual (Dr goods received not invoiced / Cr
inventory) at the receipt's cost, with no tax and no payable, and the bill may
bill only what is left. Only what goes back beyond that is a debit note.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.services import GoodsReceiptService
from app.gst_returns.services.gstr_service import GstReturnService
from app.inventory.models import InventoryRecord
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.models import PurchaseReturnLine
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
    return_tax_by_component,
)
from app.sales.models import GeoCountry
from app.settlements.services.supplier_credits import supplier_credits
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleWrite,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
from tests.unit.test_goods_receipt import _Fixture, _session_factory
from tests.unit.test_output_tax_by_head import _legs, _net

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

D = Decimal
TRADE_PAYABLES = "2100"
GRNI = "2300"
INVENTORY = "1200"


def _taxed(fixture: _Fixture) -> None:
    """Charge the product 18% local GST, CGST 9 + SGST 9."""
    session = fixture.session
    fixture.firm.gst_number = "33AABCU9603R1ZM"
    country = GeoCountry(
        code="IN", name="India", iso2="IN", iso3="IND", phone_code="+91"
    )
    session.add(country)
    session.commit()
    from app.business.models import BusinessProfile

    profile = session.scalars(
        select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
    ).one()
    framework = TaxFrameworkService(session)
    system = framework.create_system(
        TaxSystemWrite(country_id=country.id, code="GST", name="GST"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    components = [
        framework.create_component(
            TaxComponentWrite(
                tax_system_id=system.id,
                code=code,
                name=code,
                label=code,
                percentage="9",
            ),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
        for code in ("CGST", "SGST")
    ]
    tax_profile = framework.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=profile.id,
            code="GST_18_LOCAL",
            name="GST 18 local",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "9",
                    "calculation_order": order,
                    "recoverable": True,
                }
                for order, component in enumerate(components, start=1)
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=profile.id,
            code="GST_BUY",
            name="GST on purchases",
            priority=10,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": tax_profile.id,
                }
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.product.tax_profile_group_code = "GST_18_LOCAL"
    session.commit()


def _received(code: str, quantity: str = "6") -> tuple[_Fixture, GoodsReceipt]:
    """Receive ``quantity`` at 100 each on a completed goods receipt."""
    fixture = _Fixture(_session_factory()(), code)
    _taxed(fixture)
    receipts = GoodsReceiptService(fixture.session)
    receipt = receipts.create_receipt(
        fixture.receipt_payload(quantity),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    return fixture, receipt


def _receipt_line(fixture: _Fixture, receipt: GoodsReceipt) -> GoodsReceiptLine:
    """Return the receipt's single line."""
    return fixture.session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()


def _bill(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    quantity: str,
    *,
    number: str,
    approve: bool = True,
) -> PurchaseInvoice:
    """Bill ``quantity`` of the receipt line at 100 each."""
    line = _receipt_line(fixture, receipt)
    service = PurchaseInvoiceService(fixture.session)
    bill = service.create_invoice(
        PurchaseInvoiceCreate(
            supplier_invoice_number=number,
            supplier_invoice_date=date(2026, 8, 6),
            invoice_date=date(2026, 8, 6),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_invoice_quantity=D(quantity),
                    unit_price=D("100"),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.session.commit()
    if approve:
        service.approve_invoice(
            bill.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )
        fixture.session.commit()
    return bill


def _send_back(fixture: _Fixture, receipt: GoodsReceipt, quantity: str) -> UUID:
    """Return ``quantity`` off the receipt line, through to completion."""
    line = _receipt_line(fixture, receipt)
    returns = PurchaseReturnService(fixture.session)
    sent = returns.create_return(
        PurchaseReturnCreate(
            return_date=date(2026, 8, 7),
            warehouse_id=fixture.warehouse.id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line.id,
                    line_number=1,
                    current_return_quantity=D(quantity),
                    unit_price=D("100"),
                    warehouse_id=fixture.warehouse.id,
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    returns.approve_return(
        sent.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    returns.complete_return(
        sent.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.commit()
    return sent.id


def _cancel(fixture: _Fixture, return_id: UUID) -> None:
    """Cancel the return."""
    PurchaseReturnService(fixture.session).cancel_return(
        return_id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id, reason="Kept"
    )
    fixture.session.commit()


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


def _split(session: Session, return_id: UUID) -> tuple[D, D]:
    """Return the line's unbilled quantity and what it took off GRNI."""
    line = session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == return_id
        )
    ).one()
    return D(str(line.unbilled_quantity)), D(str(line.grni_amount))


def _left_to_bill(fixture: _Fixture, receipt: GoodsReceipt) -> tuple[D, D]:
    """Return what the receipt's response says is left to bill, qty and value."""
    fixture.session.expire_all()
    service = GoodsReceiptService(fixture.session)
    response = service.receipt_response(
        service.get_receipt(receipt.id, firm_scope=fixture.firm.id)
    )
    assert response.lines[0].left_to_bill_quantity == response.left_to_bill_quantity
    return response.left_to_bill_quantity, response.left_to_bill_amount


def _credit(fixture: _Fixture, return_id: UUID) -> D:
    """Return the supplier credit the return gives."""
    found = supplier_credits(
        fixture.session, firm_id=fixture.firm.id, source_ids=[return_id]
    )
    return found[0].credit_amount if found else D("0")


def test_a_return_before_billing_reverses_grni_and_takes_no_tax() -> None:
    """2 of 6 back before any bill: Dr GRNI 200 / Cr Inventory 200, nothing else."""
    fixture, receipt = _received("RBB1")
    session = fixture.session
    assert _left_to_bill(fixture, receipt) == (D("6"), D("708.00"))

    return_id = _send_back(fixture, receipt, "2")

    legs = _journal(session, return_id)
    assert legs == {
        GRNI: (D("200.00"), D("0.00")),
        INVENTORY: (D("0.00"), D("200.00")),
    }, "no payable, no input tax, no variance"
    assert _split(session, return_id) == (D("2"), D("200"))
    assert _net(session, fixture.firm.id, GRNI) == D("-400.00")
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, "1300") == D("0.00")
    assert return_tax_by_component(session, return_id) == {}
    assert _credit(fixture, return_id) == D("0")
    assert _left_to_bill(fixture, receipt) == (D("4"), D("472.00"))

    # The bill may bill what is left, and not one more.
    with pytest.raises(ValidationError, match="4.0000 is left to bill"):
        _bill(fixture, receipt, "6", number="SUP-6", approve=False)
    session.rollback()
    _bill(fixture, receipt, "4", number="SUP-4")
    assert _net(session, fixture.firm.id, GRNI) == D("0.00"), "the accrual clears"
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("-472.00")
    assert _left_to_bill(fixture, receipt) == (D("0"), D("0.00"))

    # GSTR-3B reverses nothing for it: no credit was taken on those 2.
    summary = GstReturnService(session).gstr3b(
        firm_scope=fixture.firm.id,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )
    reversed_ = summary["itc_reversed"]
    assert isinstance(reversed_, dict)
    assert float(reversed_["central_tax"]) == 0.0


def test_a_draft_bill_for_the_whole_receipt_is_refused_at_approval() -> None:
    """A return completed while a draft bill holds all 6 stops its approval."""
    fixture, receipt = _received("RBB2")
    bill = _bill(fixture, receipt, "6", number="SUP-ALL", approve=False)
    _send_back(fixture, receipt, "2")

    with pytest.raises(ValidationError, match="bills more than is left to bill"):
        PurchaseInvoiceService(fixture.session).approve_invoice(
            bill.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
        )


def test_a_return_after_full_billing_is_still_a_debit_note() -> None:
    """All 6 billed, then 2 back: Dr Payables 236 / Cr Inventory 200 / Cr GST 36."""
    fixture, receipt = _received("RBB3")
    _bill(fixture, receipt, "6", number="SUP-6")
    session = fixture.session

    return_id = _send_back(fixture, receipt, "2")

    legs = _journal(session, return_id)
    assert legs[TRADE_PAYABLES] == (D("236.00"), D("0.00"))
    assert legs[INVENTORY] == (D("0.00"), D("200.00"))
    assert legs["1320"] == (D("0.00"), D("18.00"))
    assert legs["1330"] == (D("0.00"), D("18.00"))
    assert GRNI not in legs
    assert _split(session, return_id) == (D("0"), D("0"))
    assert _credit(fixture, return_id) == D("236.00")
    assert _net(session, fixture.firm.id, GRNI) == D("0.00")

    _cancel(fixture, return_id)
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("-708.00")
    assert _net(session, fixture.firm.id, "1320") == D("54.00")
    assert _net(session, fixture.firm.id, INVENTORY) == D("600.00")


def test_a_return_past_what_was_left_splits_into_grni_and_a_debit_note() -> None:
    """6 received, 3 billed, 4 back: 3 off GRNI, 1 as a debit note."""
    fixture, receipt = _received("RBB4")
    _bill(fixture, receipt, "3", number="SUP-3")
    session = fixture.session

    return_id = _send_back(fixture, receipt, "4")

    assert _split(session, return_id) == (D("3"), D("300"))
    legs = _journal(session, return_id)
    assert legs[GRNI] == (D("300.00"), D("0.00"))
    assert legs[TRADE_PAYABLES] == (D("118.00"), D("0.00"))
    assert legs[INVENTORY] == (D("0.00"), D("400.00"))
    assert legs["1320"] == (D("0.00"), D("9.00"))
    assert legs["1330"] == (D("0.00"), D("9.00"))
    assert sum(d for d, _ in legs.values()) == sum(c for _, c in legs.values())
    assert _net(session, fixture.firm.id, GRNI) == D("0.00")
    assert return_tax_by_component(session, return_id) == {
        "CGST": D("9.0000"),
        "SGST": D("9.0000"),
    }
    assert _credit(fixture, return_id) == D("118.00")
    assert _left_to_bill(fixture, receipt) == (D("0"), D("0.00"))

    # Cancelling mirrors the journal: the accrual, the payable and the stock
    # are back where the bill of 3 left them, and the 3 are billable again.
    _cancel(fixture, return_id)
    assert _net(session, fixture.firm.id, GRNI) == D("-300.00")
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("-354.00")
    assert _net(session, fixture.firm.id, INVENTORY) == D("600.00")
    assert _net(session, fixture.firm.id, "1320") == D("27.00")
    assert _left_to_bill(fixture, receipt) == (D("3"), D("354.00"))


def test_cancelling_a_return_before_billing_restores_the_accrual() -> None:
    """The 2 come back onto the shelf and onto what is left to bill."""
    fixture, receipt = _received("RBB5")
    session = fixture.session
    return_id = _send_back(fixture, receipt, "2")

    _cancel(fixture, return_id)

    assert _net(session, fixture.firm.id, GRNI) == D("-600.00")
    assert _net(session, fixture.firm.id, INVENTORY) == D("600.00")
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _left_to_bill(fixture, receipt) == (D("6"), D("708.00"))
    _bill(fixture, receipt, "6", number="SUP-6")
    assert _net(session, fixture.firm.id, GRNI) == D("0.00")


def test_a_receipt_with_goods_sent_back_cannot_be_cancelled() -> None:
    """Cancelling it would take the stock and the accrual off twice."""
    fixture, receipt = _received("RBB6")
    _send_back(fixture, receipt, "2")

    with pytest.raises(ValidationError, match="Cancel that purchase return first"):
        GoodsReceiptService(fixture.session).cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="wrong",
        )


def test_a_return_of_goods_already_sold_is_refused() -> None:
    """D-BUY-45: a return completed for goods no longer there, to -2 on hand."""
    fixture, receipt = _received("NEG45")
    held = fixture.session.scalars(select(InventoryRecord)).one()
    # Five of the six received have since been sold.
    held.current_quantity = D("1.0000")
    held.available_quantity = D("1.0000")
    fixture.session.commit()

    with pytest.raises(ValidationError) as refusal:
        _send_back(fixture, receipt, "2")
    assert str(refusal.value.message) == (
        "This location holds 1.0000 available, so 2.0000 cannot be returned "
        "to the supplier from it."
    )
    fixture.session.rollback()
    fixture.session.refresh(held)
    assert held.current_quantity == D("1.0000")
    assert not fixture.session.scalars(
        select(JournalEntry).where(JournalEntry.source_module == "purchase_return")
    ).all()

    # What is there may go back.
    _send_back(fixture, receipt, "1")
    fixture.session.refresh(held)
    assert held.current_quantity == D("0")
    # A product the firm lets run negative is not held to it.
    fixture.product.allow_negative_stock = True
    fixture.session.commit()
    _send_back(fixture, receipt, "2")
    fixture.session.refresh(held)
    assert held.current_quantity == D("-2")
