"""Output tax owed head by head, and reverse charge on purchases.

Backlog 63.3: every sales document credited one `OUTPUT_TAX` account while
purchases already split input tax by head (D-CMP-20), so the ledger could not
say how much CGST the firm owed. Output tax now posts per head -- IGST, CGST,
SGST each to its own account -- and every reversal mirrors the split. History
in the single account is left as posted, and the GST payment clears both.

Backlog 68 row 8: a bill whose tax resolves as reverse charge owes the tax
itself. The supplier's payable excludes it; the tax is credited to
reverse-charge payable per head and claimed back as input credit; a
self-invoice is numbered from its own series; GSTR-3B reports it in 3.1(d)
and 4(A)(3); and the GST payment pays it in cash, never by credit.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.business.models import BusinessProfile
from app.credit_note.services import CreditNoteService
from app.finance.models import (
    FirmControlAccount,
    GLPosting,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)
from app.finance.services.control_accounts import (
    ControlAccountPurpose,
    output_tax_purpose,
    rcm_payable_purpose,
)
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.journal_engine import JournalEntryEngine
from app.finance.services.opening_setup import seed_finance_setup
from app.gst_returns.services import gstr_service
from app.gst_returns.services.gst_payment_service import GstPaymentService
from app.purchase_invoice.models import PurchaseInvoiceLine, PurchaseInvoiceLineTax
from app.purchase_invoice.services import PurchaseInvoiceService
from app.sales.models import GeoCountry
from app.sales_invoice.models import SalesInvoiceLineTax
from app.sales_invoice.services import SalesInvoiceService
from app.tax.schemas import TaxRuleWrite
from app.tax.services.tax_rule_service import TaxRuleService
from tests.unit import test_credit_note as credit_notes
from tests.unit import test_purchase_invoice_module as bills
from tests.unit import test_sales_invoice_module as sales
from tests.unit.test_gst_payment import _summary
from tests.unit.test_settlements import _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers

D = Decimal
ZERO = D("0.00")


def _net(session: Session, firm_id: UUID, code: str) -> Decimal:
    """Return debit less credit posted to one account code."""
    value = session.scalar(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount - GLPosting.credit_amount), 0)
        )
        .join(LedgerAccount, LedgerAccount.id == GLPosting.ledger_account_id)
        .where(LedgerAccount.firm_id == firm_id, LedgerAccount.code == code)
    )
    return D(str(value)).quantize(D("0.01"))


def _legs(session: Session, entry_id: UUID) -> dict[str, tuple[Decimal, Decimal]]:
    """Return (debit, credit) per account code for one journal."""
    rows = session.execute(
        select(LedgerAccount.code, JournalLine.debit_amount, JournalLine.credit_amount)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(JournalLine.journal_entry_id == entry_id)
    ).all()
    return {code: (D(str(debit)), D(str(credit))) for code, debit, credit in rows}


# --- the purposes ----------------------------------------------------------


def test_each_gst_head_has_its_own_output_and_reverse_charge_account() -> None:
    assert output_tax_purpose("IGST") is ControlAccountPurpose.OUTPUT_TAX_IGST
    assert output_tax_purpose("cgst") is ControlAccountPurpose.OUTPUT_TAX_CGST
    assert output_tax_purpose("UTGST") is ControlAccountPurpose.OUTPUT_TAX_SGST
    assert output_tax_purpose("CESS") is ControlAccountPurpose.OUTPUT_TAX
    assert output_tax_purpose(None) is ControlAccountPurpose.OUTPUT_TAX
    assert rcm_payable_purpose("SGST") is ControlAccountPurpose.RCM_PAYABLE_SGST
    assert rcm_payable_purpose("CESS") is ControlAccountPurpose.RCM_PAYABLE


def test_a_new_firm_gets_the_new_accounts_through_the_seed() -> None:
    books = _Books(_session_factory()())
    mapped = set(
        books.session.scalars(
            select(FirmControlAccount.purpose).where(
                FirmControlAccount.firm_id == books.firm.id
            )
        ).all()
    )
    for purpose in (
        "OUTPUT_TAX_IGST",
        "OUTPUT_TAX_CGST",
        "OUTPUT_TAX_SGST",
        "RCM_PAYABLE",
        "RCM_PAYABLE_IGST",
        "RCM_PAYABLE_CGST",
        "RCM_PAYABLE_SGST",
    ):
        assert purpose in mapped


# --- output tax split on the sales side -----------------------------------


@pytest.mark.parametrize(
    ("buyer_gstin", "heads"),
    [
        # Within Tamil Nadu: central and state tax, each to its own account.
        ("33AAACR5055K1Z5", {"2220": D("90.00"), "2230": D("90.00")}),
        # To Karnataka: integrated tax.
        ("29AAACR5055K1Z5", {"2210": D("180.00")}),
    ],
)
def test_an_approved_invoice_owes_its_tax_head_by_head(
    buyer_gstin: str, heads: dict[str, Decimal]
) -> None:
    session, invoice = sales._interstate_bill(
        buyer_gstin=buyer_gstin, billing_state=None
    )
    actor_id = uuid4()
    seed_finance_setup(
        session,
        firm_id=invoice.firm_id,
        year_starts_on=date(2026, 4, 1),
        actor_id=actor_id,
    )
    session.commit()
    service = SalesInvoiceService(session)
    service.approve_invoice(invoice.id, firm_scope=invoice.firm_id, actor_id=actor_id)
    session.commit()

    entry = session.scalars(
        select(JournalEntry).where(
            JournalEntry.source_module == "sales_invoice",
            JournalEntry.source_id == invoice.id,
        )
    ).one()
    legs = _legs(session, entry.id)
    for code, amount in heads.items():
        assert legs[code] == (ZERO, amount)
    assert "2200" not in legs, "nothing on the single account any more"

    # Cancelling mirrors the split: every head back to nothing.
    service.cancel_invoice(
        invoice.id, firm_scope=invoice.firm_id, actor_id=actor_id, reason="test"
    )
    session.commit()
    for code in heads:
        assert _net(session, invoice.firm_id, code) == ZERO


def test_a_credit_note_reverses_the_heads_its_invoice_charged() -> None:
    books = credit_notes._Books(credit_notes._session_factory()())
    for sequence, code in enumerate(("CGST", "SGST"), start=1):
        books.session.add(
            SalesInvoiceLineTax(
                sales_invoice_line_id=books.line.id,
                firm_id=books.firm.id,
                sequence=sequence,
                component_code=code,
                component_label=code,
                percentage=D("9"),
                base_amount=D("1000"),
                amount=D("90"),
            )
        )
    books.session.commit()

    note = books.approved("100")

    assert note.journal_entry_id is not None
    legs = _legs(books.session, note.journal_entry_id)
    assert legs["2220"] == (D("9.00"), ZERO)
    assert legs["2230"] == (D("9.00"), ZERO)
    assert "2200" not in legs

    CreditNoteService(books.session).cancel_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    assert _net(books.session, books.firm.id, "2220") == ZERO
    assert _net(books.session, books.firm.id, "2230") == ZERO


def test_a_sales_return_reverses_output_tax_per_head_and_its_mirror_restores_it() -> (
    None
):
    books = _Books(_session_factory()())
    posting = DocumentPostingService(books.session)
    entry = posting.post_sales_return(
        firm_id=books.firm.id,
        return_id=uuid4(),
        return_number="SR-1",
        return_date=date(2026, 4, 20),
        taxable_amount=D("500"),
        tax_amount=D("90"),
        total_amount=D("590"),
        actor_id=books.actor_id,
        tax_by_component={"CGST": D("45"), "SGST": D("45")},
    )
    assert entry is not None
    legs = _legs(books.session, entry.id)
    assert legs["2220"] == (D("45.00"), ZERO)
    assert legs["2230"] == (D("45.00"), ZERO)
    assert "2200" not in legs

    JournalEntryEngine(books.session).reverse_entry(
        entry.id,
        firm_id=books.firm.id,
        reference_number="SR-1-REV",
        actor_id=books.actor_id,
    )
    assert _net(books.session, books.firm.id, "2220") == ZERO
    assert _net(books.session, books.firm.id, "2230") == ZERO


def test_the_heads_sum_exactly_to_the_tax_the_customer_was_charged() -> None:
    # 36.855 + 36.855 at four decimals: rounding the parts would credit 73.72
    # against a receivable of 73.71's tax. The residual goes on the largest.
    books = _Books(_session_factory()())
    entry = DocumentPostingService(books.session).post_sales_invoice(
        firm_id=books.firm.id,
        invoice_id=uuid4(),
        invoice_number="SI-R",
        invoice_date=date(2026, 4, 20),
        taxable_amount=D("409.50"),
        tax_amount=D("73.71"),
        total_amount=D("483.21"),
        actor_id=books.actor_id,
        tax_by_component={"CGST": D("36.855"), "SGST": D("36.855")},
    )
    legs = _legs(books.session, entry.id)
    assert legs["2220"][1] + legs["2230"][1] == D("73.71")


# --- history in the single account, and the GST payment -------------------


def test_a_firm_with_history_in_the_single_account_clears_both_when_it_pays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave history as posted; the payment clears the old account and the heads.

    An invoice approved before the split credited 2200 (no component map);
    one after it credited 2210. The month owes 360 of IGST: 180 is debited
    to the head (what the month's documents put there) and the rest to 2200.
    """
    books = _Books(_session_factory()())
    posting = DocumentPostingService(books.session)
    for number, components in (("SI-OLD", None), ("SI-NEW", {"IGST": D("180")})):
        posting.post_sales_invoice(
            firm_id=books.firm.id,
            invoice_id=uuid4(),
            invoice_number=number,
            invoice_date=date(2026, 4, 10),
            taxable_amount=D("1000"),
            tax_amount=D("180"),
            total_amount=D("1180"),
            actor_id=books.actor_id,
            tax_by_component=components,
        )
    books.session.commit()
    assert _net(books.session, books.firm.id, "2200") == D("-180.00")
    assert _net(books.session, books.firm.id, "2210") == D("-180.00")
    monkeypatch.setattr(
        gstr_service.GstReturnService,
        "gstr3b",
        _summary({"igst": D("360")}, {"igst": D("100")}),
    )

    bank = books.session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == books.firm.id, LedgerAccount.code == "1010"
        )
    )
    assert bank is not None
    GstPaymentService(books.session).record(
        books.firm.id,
        "2026-04",
        payment_date=date(2026, 5, 20),
        money_account_id=bank,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert _net(books.session, books.firm.id, "2200") == ZERO
    assert _net(books.session, books.firm.id, "2210") == ZERO
    assert _net(books.session, books.firm.id, "1010") == D("-260.00")


# --- reverse charge on a purchase bill -------------------------------------


def _reverse_charge_rule(session: Session, *, firm_id: UUID, actor_id: UUID) -> None:
    """Make every purchase reverse charge: GTA freight, say."""
    country = session.scalars(select(GeoCountry).where(GeoCountry.code == "IN")).one()
    profile = session.scalars(
        select(BusinessProfile).where(BusinessProfile.code == "GENERIC")
    ).one()
    from app.tax.models import TaxProfile

    tax_profile = session.scalars(
        select(TaxProfile).where(TaxProfile.code == "GST_18_LOCAL")
    ).one()
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=profile.id,
            code="RCM_GTA",
            name="Reverse charge on freight",
            priority=10,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": tax_profile.id,
                },
                {"sequence": 2, "action_type": "REVERSE_CHARGE"},
            ],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )


def _reverse_charge_bill() -> tuple[Session, PurchaseInvoiceService, UUID, UUID, UUID]:
    """Bill 4 x 100 under reverse charge: CGST 36 + SGST 36 owed by the firm."""
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
    bills._gst_profile(session, firm=firm, actor_id=actor_id)
    _reverse_charge_rule(session, firm_id=firm.id, actor_id=actor_id)
    product = session.get(bills.Product, po_line.product_id)
    assert product is not None
    product.tax_profile_group_code = "GST_18_LOCAL"
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    session.commit()
    service = PurchaseInvoiceService(session)
    bill = service.create_invoice(
        bills._bill_of(
            receipt, receipt_line, number="GTA-1", quantity="4", on=date(2026, 8, 2)
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()
    return session, service, firm.id, bill.id, actor_id


def test_a_reverse_charge_bill_owes_the_tax_itself_and_claims_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, service, firm_id, bill_id, actor_id = _reverse_charge_bill()
    bill = service.get_invoice(bill_id, firm_scope=firm_id)

    # The supplier charged no tax: the payable is the goods alone.
    assert bill.tax_total == D("0")
    assert bill.reverse_charge_tax_total == D("72.0000")
    assert bill.grand_total == D("400.0000")
    rows = list(
        session.scalars(
            select(PurchaseInvoiceLineTax)
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .where(PurchaseInvoiceLine.purchase_invoice_id == bill_id)
        ).all()
    )
    assert {row.component_code for row in rows} == {"CGST", "SGST"}
    assert all(row.reverse_charge for row in rows)
    assert bill.self_invoice_number is None, "numbered when the liability arises"

    service.approve_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()
    bill = service.get_invoice(bill_id, firm_scope=firm_id)
    assert bill.self_invoice_number is not None
    # Its own series and prefix, never the sales invoice's SI (D-BUY-58).
    assert bill.self_invoice_number.startswith("RSI-")
    assert len(bill.self_invoice_number) <= 16, "rule 46(b)"
    assert bill.self_invoice_number != bill.invoice_number
    assert service.invoice_response(bill).self_invoice_number == (
        bill.self_invoice_number
    )

    posted = bills._postings(session, module="purchase_invoice", source_id=bill_id)
    assert posted["2100"] == (ZERO, D("400.00")), "the payable excludes the tax"
    assert posted["1320"] == (D("36.00"), ZERO), "CGST claimed as credit"
    assert posted["1330"] == (D("36.00"), ZERO), "SGST claimed as credit"
    assert posted["2270"] == (ZERO, D("36.00")), "CGST owed under reverse charge"
    assert posted["2280"] == (ZERO, D("36.00")), "SGST owed under reverse charge"

    # GSTR-3B: 3.1(d) the supply and its tax, 4(A)(3) the credit, and not
    # in 4(A)(5) as though the supplier had charged it.
    summary = gstr_service.GstReturnService(session).gstr3b(
        firm_scope=firm_id, from_date=date(2026, 8, 1), to_date=date(2026, 8, 31)
    )
    inward = summary["inward_reverse_charge"]
    assert isinstance(inward, dict)
    assert inward["taxable_value"] == 400.0
    assert (inward["central_tax"], inward["state_tax"]) == (36.0, 36.0)
    rcm_itc = summary["itc_reverse_charge"]
    assert isinstance(rcm_itc, dict)
    assert (rcm_itc["central_tax"], rcm_itc["state_tax"]) == (36.0, 36.0)
    eligible = summary["eligible_itc"]
    assert isinstance(eligible, dict)
    assert (eligible["central_tax"], eligible["state_tax"]) == (0.0, 0.0)

    # The GST payment pays the reverse charge in cash, though 72 of credit
    # sits beside it: credit is never set against it, and carries forward.
    payments = GstPaymentService(session)
    preview = payments.preview(firm_id, "2026-08", payment_date=date(2026, 9, 20))
    assert (
        preview.reverse_charge["cgst"] == preview.reverse_charge["sgst"] == D("36.00")
    )
    assert preview.cash_total == D("72.00")
    assert preview.set_off.used("cgst") == preview.set_off.used("sgst") == ZERO
    assert preview.set_off.carried("cgst") == D("36.00")

    bank = session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.firm_id == firm_id, LedgerAccount.code == "1010"
        )
    )
    assert bank is not None
    row = payments.record(
        firm_id,
        "2026-08",
        payment_date=date(2026, 9, 20),
        money_account_id=bank,
        actor_id=actor_id,
    )
    session.commit()
    assert (row.reverse_charge_cgst, row.reverse_charge_sgst) == (
        D("36.00"),
        D("36.00"),
    )
    assert _net(session, firm_id, "2270") == ZERO
    assert _net(session, firm_id, "2280") == ZERO
    assert _net(session, firm_id, "1010") == D("-72.00")
    assert _net(session, firm_id, "1320") == D("36.00"), "credit carried forward"


def test_cancelling_a_reverse_charge_bill_reverses_all_of_it() -> None:
    session, service, firm_id, bill_id, actor_id = _reverse_charge_bill()
    service.approve_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()
    number = service.get_invoice(bill_id, firm_scope=firm_id).self_invoice_number

    service.cancel_invoice(bill_id, firm_scope=firm_id, actor_id=actor_id)
    session.commit()

    for code in ("2100", "1320", "1330", "2270", "2280"):
        assert _net(session, firm_id, code) == ZERO, code
    assert (
        service.get_invoice(bill_id, firm_scope=firm_id).self_invoice_number == number
    ), "a cancelled self-invoice keeps its number, as a cancelled voucher does"


def test_the_odd_paisa_sits_on_the_head_the_returns_put_it_on() -> None:
    """36.855 + 36.855 is booked as the return files it, not the other way round.

    The residual used to go on the largest head, which on two equal halves is
    the first: the ledger read CGST 36.85 / SGST 36.86 while GSTR-1 and 3B
    filed CGST 36.86 / SGST 36.85 (D-SELL-48, 2026-10-05).
    """
    from app.finance.services.document_posting import _split_by_purpose
    from app.tax.services.gst_buckets import GstBuckets, settle_to_ledger

    halves = {"CGST": D("36.8550"), "SGST": D("36.8550")}

    booked = _split_by_purpose(
        D("73.71"),
        halves,
        purpose_of=output_tax_purpose,
        fallback=ControlAccountPurpose.OUTPUT_TAX,
    )

    filed = settle_to_ledger(
        [
            GstBuckets(
                cgst=halves["CGST"],
                sgst=halves["SGST"],
                igst=D("0"),
                cess=D("0"),
                rate=D("18"),
            )
        ]
    )[0]
    assert booked == {
        ControlAccountPurpose.OUTPUT_TAX_CGST: D("36.86"),
        ControlAccountPurpose.OUTPUT_TAX_SGST: D("36.85"),
    }
    assert (filed.cgst, filed.sgst) == (D("36.86"), D("36.85"))
    assert sum(booked.values()) == D("73.71")


def test_a_split_naming_no_gst_head_keeps_the_residual_on_the_largest() -> None:
    """Cess alone, or a firm's own component, has no head to prefer."""
    from app.finance.services.document_posting import _split_by_purpose

    booked = _split_by_purpose(
        D("10.01"),
        {"CESS": D("10.0000")},
        purpose_of=output_tax_purpose,
        fallback=ControlAccountPurpose.OUTPUT_TAX,
    )
    assert booked == {ControlAccountPurpose.OUTPUT_TAX: D("10.01")}
