"""Backlog 78 row 1 and D-TAX-1: tax the firm may not claim is not credit.

A tax rule's *Input credit blocked* was computed by the engine and read by
nothing, so a car or catering bought on a bill still debited input tax and
GSTR-3B claimed it. Each bill line now carries its eligibility -- what the line
says, else the product's, else the rule's -- and blocked or ineligible tax is
booked to *Input Tax Not Claimable* (5450) instead of input tax. GSTR-3B shows
blocked credit in 4(A)(5) and reverses it in 4(B)(1) (CBIC circular 170);
ineligible credit stays out of 4(A) and is shown in 4(D)(2). A return or a debit
note off such a bill takes its share back off 5450, never off input tax.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Warehouse
from app.business.models import BusinessProfile
from app.debit_note.schemas import DebitNoteCreate, DebitNoteLineWrite
from app.debit_note.services import DebitNoteService
from app.finance.services.opening_setup import seed_finance_setup
from app.gst_returns.services.gstr_service import GstReturnService
from app.purchase_invoice.models import PurchaseInvoiceLine, PurchaseInvoiceLineTax
from app.purchase_invoice.schemas import PurchaseInvoiceCreate
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services.purchase_return_service import (
    PurchaseReturnService,
)
from app.sales.models import GeoCountry
from app.tax.schemas import TaxRuleWrite
from app.tax.services.tax_rule_service import TaxRuleService
from tests.unit import test_purchase_invoice_module as bills
from tests.unit.test_output_tax_by_head import _net

D = Decimal


def _bill(
    *,
    rule_blocks: bool = False,
    product_says: str = "ELIGIBLE",
    line_says: str | None = None,
) -> tuple[Session, UUID, UUID, UUID, PurchaseInvoiceLine]:
    """Bill and approve 4 x 100 at 18% local GST: CGST 36 + SGST 36."""
    session = bills._session_factory()()
    actor_id = uuid4()
    firm = bills._firm(session)
    firm.gst_number = "33AABCU9603R1ZM"
    session.commit()
    branch = bills._branch(session, firm_id=firm.id)
    warehouse = bills._warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = bills._vendor(session, firm_id=firm.id)
    order = bills._purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(bills.PurchaseOrderLine).where(
            bills.PurchaseOrderLine.purchase_order_id == order.id
        )
    )
    assert po_line is not None
    receipt, receipt_line = bills._received(session, po_line)
    tax_profile = bills._gst_profile(session, firm=firm, actor_id=actor_id)
    country = session.scalars(select(GeoCountry).where(GeoCountry.code == "IN")).one()
    profile = session.scalars(
        select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
    ).one()
    actions: list[dict[str, object]] = [
        {
            "sequence": 1,
            "action_type": "APPLY_TAX_PROFILE",
            "target_tax_profile_id": tax_profile.id,
        }
    ]
    if rule_blocks:
        actions.append({"sequence": 2, "action_type": "INPUT_CREDIT_BLOCKED"})
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=profile.id,
            code="GST_BUY",
            name="GST on purchases",
            priority=10,
            status="ACTIVE",
            actions=actions,
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    product = session.get(bills.Product, po_line.product_id)
    assert product is not None
    product.tax_profile_group_code = "GST_18_LOCAL"
    product.itc_eligibility = product_says
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    session.commit()
    payload = bills._bill_of(
        receipt, receipt_line, number="CAR-1", quantity="4", on=date(2026, 8, 2)
    )
    if line_says is not None:
        payload = PurchaseInvoiceCreate.model_validate(
            {
                **payload.model_dump(),
                "lines": [
                    {**payload.lines[0].model_dump(), "itc_eligibility": line_says}
                ],
            }
        )
    service = PurchaseInvoiceService(session)
    bill = service.create_invoice(payload, firm_id=firm.id, actor_id=actor_id)
    session.commit()
    service.approve_invoice(bill.id, firm_scope=firm.id, actor_id=actor_id)
    session.commit()
    line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    return session, firm.id, bill.id, actor_id, line


def _table4(session: Session, firm_id: UUID) -> dict[str, float]:
    """Return 4(A)(5), 4(B)(1), 4(B)(2), 4(D)(2) and 4(C) CGST for August."""
    summary = GstReturnService(session).gstr3b(
        firm_scope=firm_id, from_date=date(2026, 8, 1), to_date=date(2026, 8, 31)
    )
    keys = {
        "4A5": "eligible_itc",
        "4B1": "itc_reversed_blocked",
        "4B2": "itc_reversed",
        "4D2": "itc_ineligible",
        "4C": "net_itc",
    }
    out: dict[str, float] = {}
    for name, key in keys.items():
        table = summary[key]
        assert isinstance(table, dict)
        out[name] = float(table["central_tax"])
    return out


def test_an_ordinary_bill_still_claims_its_credit() -> None:
    """Nothing blocked: input tax as before, nothing on 5450."""
    session, firm_id, _, _, line = _bill()
    assert line.itc_eligibility == "ELIGIBLE"
    assert _net(session, firm_id, "1320") == D("36.00")
    assert _net(session, firm_id, "5450") == D("0.00")
    assert _table4(session, firm_id) == {
        "4A5": 36.0,
        "4B1": 0.0,
        "4B2": 0.0,
        "4D2": 0.0,
        "4C": 36.0,
    }


def test_a_rule_that_blocks_credit_books_the_tax_as_a_cost() -> None:
    """D-TAX-1: the rule's verdict reaches the line, the books and 3B."""
    session, firm_id, _, _, line = _bill(rule_blocks=True)
    assert line.itc_eligibility == "BLOCKED"
    rows = session.scalars(
        select(PurchaseInvoiceLineTax).where(
            PurchaseInvoiceLineTax.purchase_invoice_line_id == line.id
        )
    ).all()
    assert rows and all(row.recoverable is False for row in rows)
    assert _net(session, firm_id, "1320") == D("0.00"), "no CGST credit"
    assert _net(session, firm_id, "1330") == D("0.00"), "no SGST credit"
    assert _net(session, firm_id, "5450") == D("72.00"), "the tax is a cost"
    assert _net(session, firm_id, "2100") == D("-472.00"), "the supplier is owed it"
    assert _table4(session, firm_id) == {
        "4A5": 36.0,
        "4B1": 36.0,
        "4B2": 0.0,
        "4D2": 0.0,
        "4C": 0.0,
    }


def test_the_line_and_the_product_say_before_the_rule() -> None:
    """Line over product over rule; ineligible stays out of 4(A)."""
    session, firm_id, _, _, line = _bill(product_says="INELIGIBLE")
    assert line.itc_eligibility == "INELIGIBLE"
    assert _net(session, firm_id, "5450") == D("72.00")
    assert _table4(session, firm_id) == {
        "4A5": 0.0,
        "4B1": 0.0,
        "4B2": 0.0,
        "4D2": 36.0,
        "4C": 0.0,
    }

    session, firm_id, _, _, line = _bill(rule_blocks=True, line_says="ELIGIBLE")
    assert line.itc_eligibility == "ELIGIBLE"
    assert _net(session, firm_id, "1320") == D("36.00")
    assert _net(session, firm_id, "5450") == D("0.00")


def test_a_return_and_a_debit_note_take_the_blocked_share_back_off_the_cost() -> None:
    """Half the goods back, then 100 claimed: 5450 comes down, input tax never moves."""
    session, firm_id, bill_id, actor_id, line = _bill(rule_blocks=True)
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
    assert _net(session, firm_id, "5450") == D("36.00")
    assert _net(session, firm_id, "1320") == D("0.00")
    table = _table4(session, firm_id)
    assert (table["4B2"], table["4C"]) == (
        0.0,
        0.0,
    ), "nothing claimed, nothing reversed"

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
    assert _net(session, firm_id, "5450") == D("18.00")
    assert _net(session, firm_id, "1320") == D("0.00")

    returns.cancel_return(
        sent_back.id, firm_scope=firm_id, actor_id=actor_id, reason="Kept"
    )
    session.commit()
    assert _net(session, firm_id, "5450") == D("54.00")
