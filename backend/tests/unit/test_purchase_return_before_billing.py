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

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.debit_note.models import DebitNote
from app.debit_note.schemas import (
    DebitNoteCreate,
    DebitNoteLineWrite,
    DebitNoteReasonEnum,
)
from app.debit_note.services import DebitNoteService
from app.finance.models import JournalEntry
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.services import GoodsReceiptService
from app.gst_returns.services.gstr_service import GstReturnService
from app.inventory.models import InventoryRecord
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.billing import bill_line_claims
from app.purchase_return.models import (
    PurchaseReturn,
    PurchaseReturnBillPlacement,
    PurchaseReturnLine,
)
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
    # Counted plainly: it read "6.0000 where 4.0000 is left" (D-PRC-62).
    with pytest.raises(
        ValidationError,
        match=(
            r"line 1 bills 6 where 4 is left to bill "
            r"\(6 received, 0 on other bills, 2 returned before billing\)"
        ),
    ):
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


def test_a_bill_line_that_names_no_unit_takes_its_receipt_lines() -> None:
    """D-BUY-49: stored with none, it showed a blank unit in the HSN summary."""
    fixture, receipt = _received("UNIT49")
    line = _receipt_line(fixture, receipt)
    # The receipt was typed in a unit; the bill's line says nothing of one.
    unit = line.purchase_uom_id or line.inventory_uom_id or uuid4()
    line.purchase_uom_id = unit
    fixture.session.commit()

    bill = _bill(fixture, receipt, "4", number="SUP-UNIT", approve=False)

    billed = fixture.session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    assert (billed.purchase_uom_id, billed.invoice_uom_id) == (unit, unit)


def test_a_bill_or_a_return_of_nothing_is_refused_where_it_is_saved() -> None:
    """D-BUY-53: a bill of 0 saved, a return of 0 saved, approved and completed."""
    fixture, receipt = _received("ZERO53")
    with pytest.raises(ValidationError) as refusal:
        _bill(fixture, receipt, "0", number="SUP-ZERO", approve=False)
    assert str(refusal.value.message) == (
        "Line 1 bills a quantity of 0 and nothing free. Type a quantity, or "
        "leave the line off the bill."
    )
    fixture.session.rollback()
    assert fixture.session.scalars(select(PurchaseInvoice)).all() == []

    with pytest.raises(ValidationError) as refusal:
        _send_back(fixture, receipt, "0")
    assert str(refusal.value.message) == (
        "Line 1 returns a quantity of 0 and nothing free. Type a quantity, or "
        "leave the line off the return."
    )
    fixture.session.rollback()
    assert fixture.session.scalars(select(PurchaseReturnLine)).all() == []


# ---- a return after a debit note (D-PRC-67) ---------------------------------
#
# A supplier bill of 1,699.20 took a price-difference debit note of 472.00 and
# was then returned in full for 1,699.20: 2,171.20 claimed against a bill of
# 1,699.20, Trade Payables 472.00 in debit. The buying twin of D-SELL-88.

INPUT_CGST = "1320"


def _bill_line(fixture: _Fixture, bill: PurchaseInvoice) -> PurchaseInvoiceLine:
    """Return the bill's single line."""
    return fixture.session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()


def _debit_note(
    fixture: _Fixture, bill: PurchaseInvoice, taxable: str, *, approve: bool = True
) -> UUID:
    """Claim ``taxable`` before tax against the bill's line, as a price difference."""
    notes = DebitNoteService(fixture.session)
    note = notes.create_note(
        DebitNoteCreate(
            purchase_invoice_id=bill.id,
            debit_note_date=date(2026, 8, 7),
            reason=DebitNoteReasonEnum.PRICE_DIFFERENCE,
            lines=[
                DebitNoteLineWrite(
                    purchase_invoice_line_id=_bill_line(fixture, bill).id,
                    line_number=1,
                    taxable_amount=D(taxable),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.session.commit()
    if approve:
        _approve_note(fixture, note.id)
    return note.id


def _approve_note(fixture: _Fixture, note_id: UUID) -> None:
    """Approve the debit note."""
    DebitNoteService(fixture.session).approve_note(
        note_id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.commit()


def _raise_return(
    fixture: _Fixture,
    quantity: str,
    *,
    receipt: GoodsReceipt | None = None,
    bill: PurchaseInvoice | None = None,
) -> UUID:
    """Save and approve a return of ``quantity`` off the receipt or off the bill."""
    if bill is not None:
        kind = PurchaseReturnSourceType.PURCHASE_INVOICE
        document_id, line_id = bill.id, _bill_line(fixture, bill).id
    else:
        assert receipt is not None
        kind = PurchaseReturnSourceType.GOODS_RECEIPT
        document_id, line_id = receipt.id, _receipt_line(fixture, receipt).id
    returns = PurchaseReturnService(fixture.session)
    sent = returns.create_return(
        PurchaseReturnCreate(
            return_date=date(2026, 8, 8),
            warehouse_id=fixture.warehouse.id,
            source_documents=[
                {"source_document_type": kind, "source_document_id": document_id}
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=kind,
                    source_document_id=document_id,
                    source_document_line_id=line_id,
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
    fixture.session.commit()
    return sent.id


def _complete(fixture: _Fixture, return_id: UUID) -> None:
    """Complete the return."""
    PurchaseReturnService(fixture.session).complete_return(
        return_id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.commit()


def _claimed(session: Session, return_id: UUID) -> tuple[D, D]:
    """Return what the return's one line claims before tax, and its tax."""
    line = session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == return_id
        )
    ).one()
    return D(str(line.net_amount - line.tax_amount)), D(str(line.tax_amount))


def _room(fixture: _Fixture, bill: PurchaseInvoice) -> tuple[D, D, D]:
    """Return a bill line's claimed, returned and still claimable, before tax."""
    [line] = DebitNoteService(fixture.session).claimable_lines(
        bill.id, firm_id=fixture.firm.id
    )
    return line.already_claimed, line.already_returned, line.claimable


@pytest.mark.parametrize("off", ["bill", "receipt"])
def test_a_return_after_a_debit_note_claims_what_the_bill_is_still_worth(
    off: str,
) -> None:
    """2 billed 236.00, 94.40 claimed by a note, both sent back: 141.60, not 236.00."""
    fixture, receipt = _received(f"DN67{off[0]}", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    session = fixture.session
    _debit_note(fixture, bill, "80")
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("-141.60")

    return_id = (
        _raise_return(fixture, "2", bill=bill)
        if off == "bill"
        else _raise_return(fixture, "2", receipt=receipt)
    )
    assert _claimed(session, return_id) == (D("120.0000"), D("21.6000"))
    _complete(fixture, return_id)

    legs = _journal(session, return_id)
    assert legs[TRADE_PAYABLES] == (D("141.60"), D("0.00"))
    assert legs[INPUT_CGST] == (D("0.00"), D("10.80"))
    # The supplier is owed nothing and owes nothing; every paisa of input
    # credit the bill took has come off once.
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_CGST) == D("0.00")
    assert _room(fixture, bill) == (D("80.0000"), D("120.0000"), D("0.0000"))
    # And nothing more can be claimed against the line by a note.
    with pytest.raises(ValidationError, match="more than is left of the bill line"):
        _debit_note(fixture, bill, "10", approve=False)


def test_the_units_of_a_bill_line_share_what_a_debit_note_left() -> None:
    """One of the two back at 60.00, then the other at the 60.00 that is left."""
    fixture, receipt = _received("DN67S", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    _debit_note(fixture, bill, "80")

    first = _raise_return(fixture, "1", bill=bill)
    _complete(fixture, first)
    second = _raise_return(fixture, "1", receipt=receipt)
    _complete(fixture, second)

    assert _claimed(fixture.session, first) == (D("60.0000"), D("10.8000"))
    assert _claimed(fixture.session, second) == (D("60.0000"), D("10.8000"))
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")


def test_a_return_priced_before_a_debit_note_does_not_complete_past_the_bill() -> None:
    """Saved at 200.00, then 80.00 is claimed by a note: completing is refused."""
    fixture, receipt = _received("DN67P", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    return_id = _raise_return(fixture, "2", receipt=receipt)
    assert _claimed(fixture.session, return_id) == (D("200.0000"), D("36.0000"))
    # The return has not completed, so the note has the whole line to claim on.
    _debit_note(fixture, bill, "80")

    with pytest.raises(ValidationError) as refusal:
        _complete(fixture, return_id)
    note_number = fixture.session.scalars(select(DebitNote.debit_note_number)).one()
    assert str(refusal.value.message) == (
        f"Line 1: these goods are now worth 120.00 before tax on "
        f"{bill.invoice_number} where the return claims 200.00. Standing "
        f"against the supplier's bills for them now: debit note {note_number} "
        f"for 80.00 on {bill.invoice_number}. The return was priced when it "
        "was saved, and one of those has been approved, completed or raised "
        "ahead of it since. No more can be claimed from a supplier than they "
        "billed. Cancel this return and raise it again, and it will be priced "
        "on what the bill is still worth."
    )
    fixture.session.rollback()
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("-141.60")


def test_a_debit_note_saved_before_the_goods_went_back_is_not_approved() -> None:
    """A draft note of 80.00, then both units go back off the receipt for 200.00."""
    fixture, receipt = _received("DN67A", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    note_id = _debit_note(fixture, bill, "80", approve=False)
    # A draft note has claimed nothing, so the return is priced in full.
    return_id = _raise_return(fixture, "2", receipt=receipt)
    _complete(fixture, return_id)
    assert _claimed(fixture.session, return_id) == (D("200.0000"), D("36.0000"))

    with pytest.raises(ValidationError, match="more than is left of the bill line"):
        _approve_note(fixture, note_id)
    fixture.session.rollback()
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")


def test_a_return_off_a_receipt_billed_in_parts_is_netted_bill_by_bill() -> None:
    """Billed 3 and 3; 150.00 claimed on the first bill; 4 back off the receipt.

    The bills are taken earliest first: 3 units of the first, worth the
    150.00 the note left, and 1 of the second at its full 100.00.
    """
    fixture, receipt = _received("DN67B")
    first = _bill(fixture, receipt, "3", number="SUP-A")
    second = _bill(fixture, receipt, "3", number="SUP-B")
    _debit_note(fixture, first, "150")

    return_id = _raise_return(fixture, "4", receipt=receipt)
    assert _claimed(fixture.session, return_id) == (D("250.0000"), D("45.0000"))
    _complete(fixture, return_id)

    assert _room(fixture, first) == (D("150.0000"), D("150.0000"), D("0.0000"))
    assert _room(fixture, second) == (D("0.0000"), D("100.0000"), D("200.0000"))
    # 708.00 billed, less 177.00 by the note, less 295.00 returned.
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("-236.00")
    # The two still held, both on the second bill, are worth all of what is left.
    rest = _raise_return(fixture, "2", receipt=receipt)
    assert _claimed(fixture.session, rest) == (D("200.0000"), D("36.0000"))


def test_only_the_billed_part_of_a_return_is_netted_by_a_debit_note() -> None:
    """6 received, 3 billed with 150.00 claimed, 4 back: 3 off GRNI, 1 at 50.00."""
    fixture, receipt = _received("DN67U")
    bill = _bill(fixture, receipt, "3", number="SUP-3")
    _debit_note(fixture, bill, "150")
    session = fixture.session

    return_id = _raise_return(fixture, "4", receipt=receipt)
    _complete(fixture, return_id)

    assert _split(session, return_id) == (D("3"), D("300"))
    legs = _journal(session, return_id)
    assert legs[GRNI] == (D("300.00"), D("0.00"))
    assert legs[TRADE_PAYABLES] == (D("59.00"), D("0.00"))
    assert legs[INPUT_CGST] == (D("0.00"), D("4.50"))
    # 354.00 billed, less 177.00 by the note, less 59.00 for the unit returned.
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("-118.00")
    assert _room(fixture, bill) == (D("150.0000"), D("50.0000"), D("100.0000"))


# A return never claims more than its supplier bill charged (D-PRC-71).


def _bill_at(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    quantity: str,
    *,
    price: str = "100",
    line_charges: str = "0",
    header_charges: str = "0",
) -> PurchaseInvoice:
    """Bill ``quantity`` of the receipt line at ``price``, with its charges."""
    line = _receipt_line(fixture, receipt)
    service = PurchaseInvoiceService(fixture.session)
    bill = service.create_invoice(
        PurchaseInvoiceCreate(
            supplier_invoice_number=f"SUP-{price}-{quantity}",
            supplier_invoice_date=date(2026, 8, 6),
            invoice_date=date(2026, 8, 6),
            additional_charges=D(header_charges),
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
                    unit_price=D(price),
                    charges_amount=D(line_charges),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    fixture.session.commit()
    service.approve_invoice(
        bill.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.commit()
    return bill


def _typed_return(
    fixture: _Fixture,
    quantity: str,
    *,
    receipt: GoodsReceipt | None = None,
    bill: PurchaseInvoice | None = None,
    price: str | None = None,
    line_charges: str = "0",
    header_charges: str = "0",
) -> UUID:
    """Save and approve a return that types a price or charges, or neither."""
    if bill is not None:
        kind = PurchaseReturnSourceType.PURCHASE_INVOICE
        document_id, line_id = bill.id, _bill_line(fixture, bill).id
    else:
        assert receipt is not None
        kind = PurchaseReturnSourceType.GOODS_RECEIPT
        document_id, line_id = receipt.id, _receipt_line(fixture, receipt).id
    returns = PurchaseReturnService(fixture.session)
    try:
        sent = returns.create_return(
            PurchaseReturnCreate(
                return_date=date(2026, 8, 8),
                warehouse_id=fixture.warehouse.id,
                additional_charges=D(header_charges),
                source_documents=[
                    {"source_document_type": kind, "source_document_id": document_id}
                ],
                lines=[
                    PurchaseReturnLineWrite(
                        source_document_type=kind,
                        source_document_id=document_id,
                        source_document_line_id=line_id,
                        line_number=1,
                        current_return_quantity=D(quantity),
                        unit_price=None if price is None else D(price),
                        charges_amount=D(line_charges),
                        warehouse_id=fixture.warehouse.id,
                    )
                ],
            ),
            firm_id=fixture.firm.id,
            actor_id=fixture.actor_id,
        )
    except ValidationError:
        fixture.session.rollback()
        raise
    returns.approve_return(
        sent.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.commit()
    return sent.id


def test_a_return_can_type_a_price_a_line_charge_and_a_header_charge() -> None:
    """The three figures a return can state over its bill are all writable.

    Which is why each needs the cap: none of them is read off the bill.
    """
    line_fields = PurchaseReturnLineWrite.model_fields
    assert {
        "unit_price",
        "discount_percent",
        "discount_amount",
        "charges_amount",
    } <= set(line_fields)
    assert {"additional_charges", "round_off"} <= set(PurchaseReturnCreate.model_fields)
    # And no other money a caller can type: the tax and the totals are worked.
    assert not {"tax_amount", "net_amount", "gross_amount"} & set(line_fields)


@pytest.mark.parametrize("off", ["bill", "receipt"])
def test_a_price_typed_over_the_bills_is_refused_by_name(off: str) -> None:
    """2 billed at 100.00, sent back at 150.00 each: 300.00 against 200.00."""
    fixture, receipt = _received(f"P71P{off[0]}", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")

    with pytest.raises(ValidationError) as refusal:
        if off == "bill":
            _typed_return(fixture, "2", price="150", bill=bill)
        else:
            _typed_return(fixture, "2", price="150", receipt=receipt)

    assert str(refusal.value.message) == (
        f"Line 1: the return claims 300.00 before tax for goods that "
        f"{bill.invoice_number} billed at 200.00, and they are still worth "
        "200.00 on it. No more can be claimed from a supplier than they "
        "billed. Lower the price or the charge to the bill's, or leave them "
        "out and the line claims what the bill is still worth."
    )


@pytest.mark.parametrize("off", ["bill", "receipt"])
def test_a_line_charge_the_bill_never_made_is_refused(off: str) -> None:
    """2 billed 200.00 with no charge of their own, sent back with 50.00 of one."""
    fixture, receipt = _received(f"P71C{off[0]}", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")

    with pytest.raises(ValidationError) as refusal:
        if off == "bill":
            _typed_return(fixture, "2", line_charges="50", bill=bill)
        else:
            _typed_return(fixture, "2", line_charges="50", receipt=receipt)

    assert "the return claims 250.00 before tax" in str(refusal.value.message)
    assert "billed at 200.00" in str(refusal.value.message)


def test_a_line_takes_back_its_share_of_the_bill_lines_own_charges() -> None:
    """2 billed 200.00 and 20.00 of charges: one goes back with 10.00, not 11.00."""
    fixture, receipt = _received("P71LC", "2")
    bill = _bill_at(fixture, receipt, "2", line_charges="20")

    with pytest.raises(ValidationError, match="billed at 110.00"):
        _typed_return(fixture, "1", bill=bill, line_charges="11")
    return_id = _typed_return(fixture, "1", bill=bill, line_charges="10")

    assert _claimed(fixture.session, return_id)[0] == D("110.0000")
    _complete(fixture, return_id)


@pytest.mark.parametrize("off", ["bill", "receipt"])
def test_a_price_typed_under_the_bills_stands(off: str) -> None:
    """2 billed at 100.00 go back at 80.00: 160.00 is claimed, and it completes."""
    fixture, receipt = _received(f"P71U{off[0]}", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")

    if off == "bill":
        return_id = _typed_return(fixture, "2", price="80", bill=bill)
    else:
        return_id = _typed_return(fixture, "2", price="80", receipt=receipt)
    _complete(fixture, return_id)

    assert _claimed(fixture.session, return_id) == (D("160.0000"), D("28.8000"))
    # 236.00 billed, 188.80 claimed back.
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("-47.20")


def test_header_charges_claim_back_only_what_the_bill_charged_that_way() -> None:
    """A bill with 30.00 of header charges: 30.00 comes back once, and no more."""
    fixture, receipt = _received("P71H", "2")
    bill = _bill_at(fixture, receipt, "2", header_charges="30")

    with pytest.raises(ValidationError) as refusal:
        _typed_return(fixture, "1", bill=bill, header_charges="30.01")
    assert str(refusal.value.message) == (
        f"This return claims 30.01 of additional charges, and "
        f"{bill.invoice_number} charged 30.00 of them, 0.00 already claimed "
        "back by other returns. No more can be claimed from a supplier than "
        "they billed. Lower the charges to 30.00 or less."
    )
    _typed_return(fixture, "1", bill=bill, header_charges="30")
    # The other unit, off the receipt this time: the same bill, nothing left.
    with pytest.raises(ValidationError, match="30.00 already claimed back"):
        _typed_return(fixture, "1", receipt=receipt, header_charges="1")
    _typed_return(fixture, "1", receipt=receipt)


def test_header_charges_on_a_bill_that_made_none_are_refused() -> None:
    """2 billed 200.00 with no header charge, sent back with 50.00 of them."""
    fixture, receipt = _received("P71H0", "2")
    _bill(fixture, receipt, "2", number="SUP-2")

    with pytest.raises(ValidationError, match="charged 0.00 of them"):
        _typed_return(fixture, "2", receipt=receipt, header_charges="50")


def test_goods_no_bill_has_reached_go_back_at_what_the_receipt_took_them_in_at() -> (
    None
):
    """6 received at 100.00 and not billed: 2 back at 150.00 is refused."""
    fixture, receipt = _received("P71R")

    with pytest.raises(ValidationError) as refusal:
        _typed_return(fixture, "2", receipt=receipt, price="150")
    assert str(refusal.value.message) == (
        f"Line 1: the return states 300.00 before tax for goods that "
        f"{receipt.grn_number} took in at 200.00, and no supplier bill has "
        "charged them yet. Goods cannot go back at more than they came in "
        "for. Lower the price or the charge, or leave them out and the line "
        "takes the receipt's own price."
    )
    return_id = _typed_return(fixture, "2", receipt=receipt, price="90")
    assert _claimed(fixture.session, return_id)[0] == D("180.0000")
    _complete(fixture, return_id)


def test_a_receipt_billed_for_less_goes_back_at_what_the_bill_charged() -> None:
    """Received at 100.00, billed at 90.00: the return reads 100.00 and claims 90.00.

    Nothing was typed over the receipt's own price, so nothing is refused;
    the line is valued at what its bill is worth.
    """
    fixture, receipt = _received("P71L", "2")
    _bill_at(fixture, receipt, "2", price="90")

    return_id = _raise_return(fixture, "2", receipt=receipt)
    assert _claimed(fixture.session, return_id) == (D("180.0000"), D("32.4000"))
    _complete(fixture, return_id)

    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(fixture.session, fixture.firm.id, INPUT_CGST) == D("0.00")


def test_a_return_saved_over_its_bill_is_refused_again_at_completion() -> None:
    """A return on file from before the cap, at 150.00 a unit: it does not complete."""
    fixture, receipt = _received("P71X", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    return_id = _typed_return(fixture, "2", bill=bill)
    line = fixture.session.scalars(
        select(PurchaseReturnLine).where(
            PurchaseReturnLine.purchase_return_id == return_id
        )
    ).one()
    # As it was saved before the cap ran on every line.
    line.unit_price, line.gross_amount = D("150"), D("300")
    line.tax_amount, line.net_amount = D("54"), D("354")
    fixture.session.commit()

    with pytest.raises(ValidationError) as refusal:
        _complete(fixture, return_id)
    assert str(refusal.value.message) == (
        f"Line 1: the return claims 300.00 before tax for goods that "
        f"{bill.invoice_number} billed at 200.00, and they are still worth "
        "200.00 on it. No more can be claimed from a supplier than they "
        "billed. Cancel this return and raise it again, and it will be "
        "priced on what the goods are still worth."
    )
    fixture.session.rollback()
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("-236.00")


def test_header_charges_saved_over_the_bill_are_refused_again_at_completion() -> None:
    """A return on file with 50.00 of header charges its bill never made."""
    fixture, receipt = _received("P71Y", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    return_id = _typed_return(fixture, "2", bill=bill)
    row = fixture.session.get(PurchaseReturn, return_id)
    assert row is not None
    row.additional_charges = D("50")
    row.grand_total = row.grand_total + D("50")
    fixture.session.commit()

    with pytest.raises(ValidationError, match="claims 50.00 of additional charges"):
        _complete(fixture, return_id)
    fixture.session.rollback()
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("-236.00")


# Where a return's units were placed is decided once, at completion (D-PRC-73).

INPUT_SGST = "1330"
_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261006_0347_purchase_return_bill_placements.py"
)


def _parts(
    code: str, bills: int, note_on: int | None
) -> tuple[_Fixture, GoodsReceipt, list[PurchaseInvoice]]:
    """Receive one unit per bill and bill them apart, 40.00 claimed on one."""
    fixture, receipt = _received(code, str(bills))
    billed = [
        _bill(fixture, receipt, "1", number=f"SUP-{index}") for index in range(bills)
    ]
    if note_on is not None:
        _debit_note(fixture, billed[note_on], "40")
    return fixture, receipt, billed


def _back(
    fixture: _Fixture,
    receipt: GoodsReceipt,
    bills: list[PurchaseInvoice],
    route: str,
) -> UUID:
    """Send one unit back off the receipt ("r") or off a bill by its index."""
    if route == "r":
        return_id = _raise_return(fixture, "1", receipt=receipt)
    else:
        return_id = _raise_return(fixture, "1", bill=bills[int(route)])
    _complete(fixture, return_id)
    return return_id


def _rooms(fixture: _Fixture, bills: list[PurchaseInvoice]) -> list[tuple[D, D, D]]:
    """Return each bill line's claimed, returned and claimable."""
    fixture.session.expire_all()
    return [_room(fixture, bill) for bill in bills]


def test_a_unit_off_the_receipt_then_the_first_bills_own_line() -> None:
    """Two bills of 100.00, 40.00 claimed on the second: 100.00 then 60.00.

    The first return was placed on the first bill and claimed its 100.00;
    naming that bill's line afterwards cannot move it. 2,171.20 was claimed
    against bills of 1,699.20 this way (PRCQ-72).
    """
    fixture, receipt, bills = _parts("PL73A", 2, 1)
    session = fixture.session

    first = _back(fixture, receipt, bills, "r")
    assert _claimed(session, first) == (D("100.0000"), D("18.0000"))
    assert _rooms(fixture, bills) == [
        (D("0.0000"), D("100.0000"), D("0.0000")),
        (D("40.0000"), D("0.0000"), D("60.0000")),
    ]

    second = _back(fixture, receipt, bills, "0")
    assert _claimed(session, second) == (D("60.0000"), D("10.8000"))
    # The first return stays where it was placed, for every reader.
    assert _rooms(fixture, bills) == [
        (D("0.0000"), D("100.0000"), D("0.0000")),
        (D("40.0000"), D("60.0000"), D("0.0000")),
    ]
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_CGST) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_SGST) == D("0.00")


def test_the_mirror_with_the_debit_note_on_the_first_bill() -> None:
    """40.00 claimed on the first bill: 60.00 off the receipt, then 100.00."""
    fixture, receipt, bills = _parts("PL73M", 2, 0)

    first = _back(fixture, receipt, bills, "r")
    second = _back(fixture, receipt, bills, "0")

    assert _claimed(fixture.session, first) == (D("60.0000"), D("10.8000"))
    assert _claimed(fixture.session, second) == (D("100.0000"), D("18.0000"))
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(fixture.session, fixture.firm.id, INPUT_CGST) == D("0.00")


@pytest.mark.parametrize("note_on", [None, 0, 1, 2])
@pytest.mark.parametrize(
    "routes",
    [
        ("r", "0", "r"),
        ("r", "0", "1"),
        ("0", "r", "r"),
        ("1", "r", "0"),
        ("r", "r", "0"),
        ("2", "0", "r"),
        ("r", "1", "2"),
        ("r", "r", "r"),
    ],
)
def test_returns_by_either_route_claim_what_three_bills_charged(
    routes: tuple[str, str, str], note_on: int | None
) -> None:
    """Three bills of 100.00, a note on each in turn, every unit back.

    Whatever order the routes come in, what is claimed is what was billed:
    never more, and with every unit back never less.
    """
    code = "P" + "".join(routes) + str(note_on)
    fixture, receipt, bills = _parts(code, 3, note_on)
    session = fixture.session
    note = D("0") if note_on is None else D("40")
    claimed = D("0")
    before = _rooms(fixture, bills)
    for route in routes:
        return_id = _back(fixture, receipt, bills, route)
        claimed += _claimed(session, return_id)[0]
        after = _rooms(fixture, bills)
        # Never more off a bill line than it billed.
        assert all(taken + back <= D("100") for taken, back, _ in after)
        # And what an earlier return took off a line is still off it.
        assert all(now[1] >= then[1] for now, then in zip(after, before, strict=True))
        before = after
        assert _net(session, fixture.firm.id, TRADE_PAYABLES) <= D("0.00")

    assert claimed == D("300") - note
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_CGST) == D("0.00")
    assert all(room == D("0.0000") for _, _, room in before)


def test_a_cancelled_return_gives_its_place_back() -> None:
    """Off the receipt and cancelled: the first bill's unit is whole again."""
    fixture, receipt, bills = _parts("PL73C", 2, 1)
    session = fixture.session

    gone = _back(fixture, receipt, bills, "r")
    _cancel(fixture, gone)
    assert _rooms(fixture, bills) == [
        (D("0.0000"), D("0.0000"), D("100.0000")),
        (D("40.0000"), D("0.0000"), D("60.0000")),
    ]

    first = _back(fixture, receipt, bills, "0")
    second = _back(fixture, receipt, bills, "r")
    assert _claimed(session, first) == (D("100.0000"), D("18.0000"))
    assert _claimed(session, second) == (D("60.0000"), D("10.8000"))
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")


def _stored(session: Session) -> list[tuple[UUID, UUID, D, D]]:
    """Return every placement: return line, bill line, units and value."""
    session.expire_all()
    return sorted(
        (
            (
                row.purchase_return_line_id,
                row.purchase_invoice_line_id,
                D(str(row.quantity)).quantize(D("0.0001")),
                D(str(row.taxable_amount)).quantize(D("0.0001")),
            )
            for row in session.scalars(select(PurchaseReturnBillPlacement)).all()
        ),
        key=str,
    )


def test_completion_stores_where_each_unit_fell() -> None:
    """Off the receipt lands on the first bill; off that bill's line, the second."""
    fixture, receipt, bills = _parts("PL73S", 2, 1)
    first = _back(fixture, receipt, bills, "r")
    second = _back(fixture, receipt, bills, "0")
    lines = [_bill_line(fixture, bill).id for bill in bills]

    placed = {
        row.purchase_return_id: (
            row.purchase_invoice_line_id,
            D(str(row.quantity)),
            D(str(row.taxable_amount)),
        )
        for row in fixture.session.scalars(select(PurchaseReturnBillPlacement)).all()
    }
    assert placed == {
        first: (lines[0], D("1"), D("100")),
        second: (lines[1], D("1"), D("60")),
    }


def test_the_backfill_places_completed_returns_as_completion_does() -> None:
    """Migration 0347 on a store with no rows writes what the service stores."""
    spec = importlib.util.spec_from_file_location("_placements_0347", _MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    fixture, receipt, bills = _parts("PL73F", 3, 1)
    session = fixture.session
    for route in ("r", "0", "r"):
        _back(fixture, receipt, bills, route)
    written = _stored(session)
    assert len(written) == 3

    session.execute(delete(PurchaseReturnBillPlacement))
    session.commit()
    migration._backfill(session.connection())
    session.commit()
    assert _stored(session) == written

    # Run again, it adds nothing.
    migration._backfill(session.connection())
    session.commit()
    assert _stored(session) == written


def test_a_debit_note_reads_the_placement_a_later_return_cannot_move() -> None:
    """Both routes used, both bills spent: neither has room for a note."""
    fixture, receipt, bills = _parts("PL73N", 2, None)

    _back(fixture, receipt, bills, "r")
    _back(fixture, receipt, bills, "0")

    for bill in bills:
        with pytest.raises(ValidationError, match="more than is left of the bill"):
            _debit_note(fixture, bill, "10", approve=False)
        fixture.session.rollback()


# A bill is held from cancelling by the returns set against it (D-PRC-80).


def _cancel_bill(fixture: _Fixture, bill: PurchaseInvoice) -> None:
    """Cancel the supplier bill, leaving the session clean after a refusal."""
    try:
        PurchaseInvoiceService(fixture.session).cancel_invoice(
            bill.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="Keyed wrongly",
        )
    except ValidationError:
        fixture.session.rollback()
        raise
    fixture.session.commit()


def _return_number(fixture: _Fixture, return_id: UUID) -> str:
    """Return the purchase return's number."""
    row = fixture.session.get(PurchaseReturn, return_id)
    assert row is not None
    return row.return_number


def _bill_status(fixture: _Fixture, bill: PurchaseInvoice) -> str:
    """Return the bill's status as the store holds it."""
    fixture.session.expire_all()
    row = fixture.session.get(PurchaseInvoice, bill.id)
    assert row is not None
    return row.status


@pytest.mark.parametrize("completed", [True, False])
def test_a_bill_does_not_cancel_under_a_return_off_the_receipt_set_on_it(
    completed: bool,
) -> None:
    """Two bills of one unit, a unit back off the receipt: it is the first bill's.

    The first bill cancelled under it (200) and the supplier's credit stood
    with no bill behind it. The second, which the return took nothing of,
    cancels as before.
    """
    fixture, receipt, bills = _parts(f"C80R{int(completed)}", 2, None)
    return_id = _raise_return(fixture, "1", receipt=receipt)
    if completed:
        _complete(fixture, return_id)

    with pytest.raises(ValidationError) as refusal:
        _cancel_bill(fixture, bills[0])
    assert str(refusal.value.message) == (
        f"{bills[0].invoice_number} cannot be cancelled while it has purchase "
        f"return {_return_number(fixture, return_id)}. Reverse or cancel those "
        "first."
    )
    assert _bill_status(fixture, bills[0]) == "APPROVED"

    _cancel_bill(fixture, bills[1])
    assert _bill_status(fixture, bills[1]) == "CANCELLED"


def test_a_bill_does_not_cancel_under_a_return_that_spilled_onto_it() -> None:
    """A unit off the receipt, then one on the first bill's own line.

    The second return names the first bill and its unit fell on the second:
    cancelling the second left the supplier in debit by the whole of it.
    """
    fixture, receipt, bills = _parts("C80S", 2, None)
    first = _back(fixture, receipt, bills, "r")
    second = _back(fixture, receipt, bills, "0")

    with pytest.raises(ValidationError) as refusal:
        _cancel_bill(fixture, bills[1])
    assert str(refusal.value.message) == (
        f"{bills[1].invoice_number} cannot be cancelled while it has purchase "
        f"return {_return_number(fixture, second)}. Reverse or cancel those "
        "first."
    )
    # The first bill is held by both: one placed on it, one naming its line.
    with pytest.raises(ValidationError) as both:
        _cancel_bill(fixture, bills[0])
    numbers = ", ".join(
        sorted([_return_number(fixture, first), _return_number(fixture, second)])
    )
    assert f"purchase return {numbers}." in str(both.value.message)
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")

    # With the return that fell on it cancelled, the bill cancels.
    _cancel(fixture, second)
    _cancel_bill(fixture, bills[1])
    assert _bill_status(fixture, bills[1]) == "CANCELLED"
    assert _net(fixture.session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")


def test_a_return_that_took_nothing_of_a_bill_does_not_hold_it() -> None:
    """3 received, 1 billed, 1 back before any bill reached it, a draft of 1.

    The return reversed the receipt's accrual and claimed nothing from the
    supplier, so neither the approved bill nor the draft is held by it.
    """
    fixture, receipt = _received("C80U", "3")
    billed = _bill(fixture, receipt, "1", number="SUP-A")
    sent = _send_back(fixture, receipt, "1")
    assert _split(fixture.session, sent)[0] == D("1.0000")
    draft = _bill(fixture, receipt, "1", number="SUP-B", approve=False)

    _cancel_bill(fixture, draft)
    _cancel_bill(fixture, billed)
    assert _bill_status(fixture, draft) == "CANCELLED"
    assert _bill_status(fixture, billed) == "CANCELLED"


# Returns open at once are placed in one order, whoever asks (D-PRC-81).


@pytest.mark.parametrize("first_done", ["receipt", "bill"])
def test_two_returns_open_by_two_routes_complete_in_either_order(
    first_done: str,
) -> None:
    """Two bills of 100.00, 40.00 claimed on the second, both units open.

    A unit off the receipt (the first bill's, 100.00) and a unit on the
    first bill's own line (which spills to the second, 60.00), both saved
    before either completes. Completed receipt first, the first was refused
    for a debit note nobody had approved, came to 60.00 when raised again,
    and the second completed at 60.00: 160.00 claimed against 200.00 with
    every unit back.
    """
    fixture, receipt, bills = _parts(f"O81{first_done[0]}", 2, 1)
    session = fixture.session
    off_receipt = _raise_return(fixture, "1", receipt=receipt)
    on_the_bill = _raise_return(fixture, "1", bill=bills[0])
    assert _claimed(session, off_receipt) == (D("100.0000"), D("18.0000"))
    assert _claimed(session, on_the_bill) == (D("60.0000"), D("10.8000"))

    order = [off_receipt, on_the_bill]
    for return_id in order if first_done == "receipt" else reversed(order):
        _complete(fixture, return_id)

    # Each completed at what it was saved at, on the bill it was priced on.
    assert _claimed(session, off_receipt) == (D("100.0000"), D("18.0000"))
    assert _claimed(session, on_the_bill) == (D("60.0000"), D("10.8000"))
    lines = [_bill_line(fixture, bill).id for bill in bills]
    placed = {
        row.purchase_return_id: (
            row.purchase_invoice_line_id,
            D(str(row.taxable_amount)).quantize(D("0.01")),
        )
        for row in session.scalars(select(PurchaseReturnBillPlacement)).all()
    }
    assert placed == {
        off_receipt: (lines[0], D("100.00")),
        on_the_bill: (lines[1], D("60.00")),
    }
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_CGST) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_SGST) == D("0.00")
    assert all(room == D("0.0000") for _, _, room in _rooms(fixture, bills))


def test_a_draft_saved_again_keeps_its_place_ahead_of_a_later_return() -> None:
    """The earlier of two open returns is priced the same whenever it is asked."""
    fixture, receipt, bills = _parts("O81P", 2, 1)
    off_receipt = _raise_return(fixture, "1", receipt=receipt)
    on_the_bill = _raise_return(fixture, "1", bill=bills[0])
    line = _bill_line(fixture, bills[0])
    row = fixture.session.get(PurchaseReturn, off_receipt)
    assert row is not None

    # Asked for the earlier return, the later one is not ahead of it.
    claims = bill_line_claims(
        fixture.session,
        [line],
        exclude_return_id=off_receipt,
        ahead_of=(row.return_date, row.return_number),
    )[line.id]
    assert claims.returned_quantity == D("0.0000")
    # Asked for the later one, the earlier holds the first bill's unit.
    later = fixture.session.get(PurchaseReturn, on_the_bill)
    assert later is not None
    claims = bill_line_claims(
        fixture.session,
        [line],
        exclude_return_id=on_the_bill,
        ahead_of=(later.return_date, later.return_number),
    )[line.id]
    assert (claims.returned_quantity, claims.returned_taxable) == (
        D("1.0000"),
        D("100.0000"),
    )


def test_the_refusal_at_completion_names_what_moved_ahead() -> None:
    """A return dated earlier completes onto the bill an open return was priced on.

    The open return then falls on the second bill, where a debit note left
    60.00: the refusal names the return that took the first bill and the
    note on the second, and blames neither for being "approved since".
    """
    fixture, receipt, bills = _parts("O81N", 2, 1)
    waiting = _raise_return(fixture, "1", bill=bills[0])
    assert _claimed(fixture.session, waiting)[0] == D("100.0000")
    # Dated the day before, so it stands ahead of the open return.
    ahead = _send_back(fixture, receipt, "1")
    note_number = fixture.session.scalars(select(DebitNote.debit_note_number)).one()

    with pytest.raises(ValidationError) as refusal:
        _complete(fixture, waiting)
    assert str(refusal.value.message) == (
        f"Line 1: these goods are now worth 60.00 before tax on "
        f"{bills[1].invoice_number} where the return claims 100.00. Standing "
        f"against the supplier's bills for them now: debit note {note_number} "
        f"for 40.00 on {bills[1].invoice_number}; purchase return "
        f"{_return_number(fixture, ahead)} for 100.00 on "
        f"{bills[0].invoice_number}. The return was priced when it was saved, "
        "and one of those has been approved, completed or raised ahead of it "
        "since. No more can be claimed from a supplier than they billed. "
        "Cancel this return and raise it again, and it will be priced on what "
        "the bill is still worth."
    )
    fixture.session.rollback()


def test_a_return_cut_to_a_bill_does_not_complete_once_it_is_worth_more() -> None:
    """The return ahead is cancelled and raised again behind the one it moved.

    The return on the first bill's line was cut to the 60.00 the second
    bill had left. With the first cancelled it falls on its own line, worth
    100.00; completing it at 60.00 left 40.00 nothing could claim.
    """
    fixture, receipt, bills = _parts("O81U", 2, 1)
    session = fixture.session
    off_receipt = _raise_return(fixture, "1", receipt=receipt)
    on_the_bill = _raise_return(fixture, "1", bill=bills[0])
    _cancel(fixture, off_receipt)
    again = _raise_return(fixture, "1", receipt=receipt)
    assert _claimed(session, again)[0] == D("60.0000")
    _complete(fixture, again)

    with pytest.raises(ValidationError) as refusal:
        _complete(fixture, on_the_bill)
    assert str(refusal.value.message) == (
        f"Line 1: these goods are now worth 100.00 before tax on "
        f"{bills[0].invoice_number} where the return claims 60.00, the figure "
        "it was cut to when it was saved. What stood against the supplier's "
        "bill then no longer does: a return or a debit note was cancelled, or "
        "the goods now come off another bill. Cancel this return and raise it "
        "again, and it will claim what the goods are worth now."
    )
    session.rollback()

    _cancel(fixture, on_the_bill)
    raised = _back(fixture, receipt, bills, "0")
    assert _claimed(session, raised)[0] == D("100.0000")
    assert _net(session, fixture.firm.id, TRADE_PAYABLES) == D("0.00")
    assert _net(session, fixture.firm.id, INPUT_CGST) == D("0.00")


def test_a_price_typed_under_the_bill_still_completes_as_typed() -> None:
    """A deduction is not a cut: 80.00 a unit on a bill at 100.00 completes."""
    fixture, receipt = _received("O81D", "2")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    return_id = _typed_return(fixture, "2", bill=bill, price="80")
    _complete(fixture, return_id)
    assert _claimed(fixture.session, return_id)[0] == D("160.0000")


def test_an_open_return_of_an_unbilled_unit_takes_nothing_of_the_bill() -> None:
    """4 received, 2 billed, 1 open off the receipt: the bill's 2 are whole.

    The open return will be set against what no bill has reached when it
    completes. Counted against the bill, both of the bill's units went back
    off its own line for 100.00, and the bill could not be cancelled.
    """
    fixture, receipt = _received("O81B", "4")
    bill = _bill(fixture, receipt, "2", number="SUP-2")
    waiting = _raise_return(fixture, "1", receipt=receipt)

    both = _raise_return(fixture, "2", bill=bill)
    assert _claimed(fixture.session, both) == (D("200.0000"), D("36.0000"))
    _cancel(fixture, both)

    _cancel_bill(fixture, bill)
    assert _bill_status(fixture, bill) == "CANCELLED"
    _complete(fixture, waiting)
    assert _split(fixture.session, waiting)[0] == D("1.0000")
