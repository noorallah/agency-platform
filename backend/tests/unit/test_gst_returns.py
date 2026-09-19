"""What a firm declares for a period, read off what it actually sold.

A return is a view of the documents, so the cases that decide whether it can
be trusted are the ones where a document and a naive reading of it disagree:

- a **cancelled** invoice is not a supply, and a draft never was;
- a registered buyer is declared **invoice by invoice** and an unregistered one
  is **summarised**, because that is what the return asks for and what a buyer
  can claim credit against;
- the taxable value is what was **charged**, not the line's net amount, which
  includes the tax and would over-state every supply by its own tax;
- and a credit note lands in the period it was **issued**, whatever period the
  invoice it credits belongs to.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.credit_note.models import CreditNote, CreditNoteLine
from app.customers.models import Customer, CustomerReceivableTransaction
from app.firms.models import Firm
from app.gst_returns.services import GstReturnService
from app.gst_returns.services.gstr_service import b2cl_threshold
from app.products.models import Product
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.sales_return.models import SalesReturn, SalesReturnLine, SalesReturnLineTax

APRIL = (date(2026, 4, 1), date(2026, 4, 30))
SELLER = "29AABCU9603R1ZM"
REGISTERED_BUYER = "29AAACR5055K1Z5"


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Books:
    """A GST-registered firm with a registered and an unregistered buyer."""

    def __init__(self, session: Session, *, seller: str | None = SELLER) -> None:
        """Seed the firm, two customers and a product."""
        self.session = session
        self.firm = Firm(
            name="Filing Firm",
            code="GSTR",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            gst_number=seller,
        )
        session.add(self.firm)
        session.commit()
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-1",
            name="Branch One",
            display_name="Branch One",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        self.registered = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
            gst_number=REGISTERED_BUYER,
        )
        self.walk_in = Customer(
            firm_id=self.firm.id,
            code="C2",
            customer_type="INDIVIDUAL",
            name="Walk-in Buyer",
            display_name="Walk-in Buyer",
            currency_code="INR",
            status="ACTIVE",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            hsn_sac="33061020",
        )
        session.add_all([self.branch, self.registered, self.walk_in, self.product])
        session.commit()

    def invoice(
        self,
        number: str,
        *,
        customer: Customer | None = None,
        gross: str = "1000",
        tax: str = "180",
        status: str = "APPROVED",
        on: date = date(2026, 4, 10),
        discount: str = "0",
        freight: str = "0",
        charges: str = "0",
        interstate: bool = False,
    ) -> SalesInvoice:
        """Bill one line, taxed CGST + SGST unless asked for IGST."""
        buyer = customer or self.registered
        taxable = (
            Decimal(gross) - Decimal(discount) + Decimal(freight) + Decimal(charges)
        )
        invoice = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=buyer.id,
            branch_id=self.branch.id,
            invoice_number=number,
            invoice_date=on,
            status=status,
            grand_total=taxable + Decimal(tax),
        )
        self.session.add(invoice)
        self.session.flush()
        line = SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=self.firm.id,
            line_number=1,
            source_document_type="SALES_ORDER",
            source_document_id=uuid4(),
            source_document_number="SO-1",
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=self.product.id,
            delivered_quantity=Decimal("10"),
            current_invoice_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            gross_amount=Decimal(gross),
            discount_amount=Decimal(discount),
            freight_amount=Decimal(freight),
            charges_amount=Decimal(charges),
            tax_amount=Decimal(tax),
            net_amount=taxable + Decimal(tax),
        )
        self.session.add(line)
        self.session.flush()
        components = (
            (("IGST", Decimal(tax), Decimal("18")),)
            if interstate
            else (
                ("CGST", Decimal(tax) / 2, Decimal("9")),
                ("SGST", Decimal(tax) / 2, Decimal("9")),
            )
        )
        for index, (code, amount, rate) in enumerate(components, start=1):
            self.session.add(
                SalesInvoiceLineTax(
                    sales_invoice_line_id=line.id,
                    firm_id=self.firm.id,
                    sequence=index,
                    component_code=code,
                    component_label=code,
                    percentage=rate,
                    base_amount=taxable,
                    amount=amount,
                )
            )
        self.session.commit()
        return invoice

    def credit(
        self,
        number: str,
        invoice: SalesInvoice,
        *,
        taxable: str = "100",
        tax: str = "18",
        on: date = date(2026, 4, 20),
    ) -> CreditNote:
        """Credit some value back against an invoice, and approve it."""
        line = self.session.scalars(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == invoice.id
            )
        ).first()
        assert line is not None
        note = CreditNote(
            firm_id=self.firm.id,
            customer_id=invoice.customer_id,
            branch_id=self.branch.id,
            sales_invoice_id=invoice.id,
            credit_note_number=number,
            credit_note_date=on,
            reason="RATE_DIFFERENCE",
            status="APPROVED",
            taxable_amount=Decimal(taxable),
            tax_amount=Decimal(tax),
            total_amount=Decimal(taxable) + Decimal(tax),
        )
        self.session.add(note)
        self.session.flush()
        self.session.add(
            CreditNoteLine(
                credit_note_id=note.id,
                firm_id=self.firm.id,
                line_number=1,
                sales_invoice_line_id=line.id,
                product_id=self.product.id,
                quantity=Decimal("0"),
                taxable_amount=Decimal(taxable),
                tax_rate_percent=Decimal("18"),
                tax_amount=Decimal(tax),
                total_amount=Decimal(taxable) + Decimal(tax),
            )
        )
        self.session.commit()
        return note

    def returned(
        self,
        number: str,
        invoice: SalesInvoice,
        *,
        taxable: str = "100",
        tax: str = "18",
        on: date = date(2026, 4, 22),
        status: str = "COMPLETED",
        interstate: bool = False,
    ) -> SalesReturn:
        """Take goods back against an invoice, the tax split as it was charged."""
        source = self.session.scalars(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == invoice.id
            )
        ).first()
        assert source is not None
        row = SalesReturn(
            firm_id=self.firm.id,
            customer_id=invoice.customer_id,
            branch_id=self.branch.id,
            warehouse_id=uuid4(),
            return_number=number,
            return_date=on,
            status=status,
            subtotal=Decimal(taxable),
            tax_total=Decimal(tax),
            grand_total=Decimal(taxable) + Decimal(tax),
        )
        self.session.add(row)
        self.session.flush()
        line = SalesReturnLine(
            sales_return_id=row.id,
            firm_id=self.firm.id,
            line_number=1,
            source_document_type="SALES_INVOICE",
            source_document_id=invoice.id,
            source_document_number=invoice.invoice_number,
            source_document_line_id=source.id,
            source_document_line_number=1,
            product_id=self.product.id,
            dispatched_quantity=Decimal("10"),
            current_return_quantity=Decimal("1"),
            unit_price=Decimal(taxable),
            gross_amount=Decimal(taxable),
            tax_amount=Decimal(tax),
            net_amount=Decimal(taxable) + Decimal(tax),
        )
        self.session.add(line)
        self.session.flush()
        components = (
            (("IGST", Decimal(tax), Decimal("18")),)
            if interstate
            else (
                ("CGST", Decimal(tax) / 2, Decimal("9")),
                ("SGST", Decimal(tax) / 2, Decimal("9")),
            )
        )
        for index, (code, amount, rate) in enumerate(components, start=1):
            self.session.add(
                SalesReturnLineTax(
                    sales_return_line_id=line.id,
                    firm_id=self.firm.id,
                    sequence=index,
                    component_code=code,
                    component_label=code,
                    percentage=rate,
                    base_amount=Decimal(taxable),
                    amount=amount,
                )
            )
        self.session.commit()
        return row

    def gstr1(self) -> dict[str, object]:
        """Return April's outward supplies."""
        return GstReturnService(self.session).gstr1(
            firm_scope=self.firm.id, from_date=APRIL[0], to_date=APRIL[1]
        )

    def gstr3b(self) -> dict[str, object]:
        """Return April's summary."""
        return GstReturnService(self.session).gstr3b(
            firm_scope=self.firm.id, from_date=APRIL[0], to_date=APRIL[1]
        )


def test_a_registered_buyer_is_declared_invoice_by_invoice() -> None:
    """The buyer claims credit against the number, so it has to be there."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")

    b2b = books.gstr1()["b2b"]

    assert len(b2b) == 1
    assert b2b[0]["gstin"] == REGISTERED_BUYER
    invoices = b2b[0]["invoices"]
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "SI-1"
    assert invoices[0]["taxable_value"] == 1000.0
    assert invoices[0]["central_tax"] == 90.0
    assert invoices[0]["state_tax"] == 90.0
    assert invoices[0]["rate"] == 18.0


def test_an_unregistered_buyer_is_only_summarised() -> None:
    """No credit is claimed against it, so the number helps nobody.

    Two sales to walk-in buyers become one row for the state and rate, which
    is all the return has a column for.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", customer=books.walk_in)
    books.invoice("SI-2", customer=books.walk_in)

    answer = books.gstr1()

    assert answer["b2b"] == []
    assert len(answer["b2cs"]) == 1
    assert answer["b2cs"][0]["taxable_value"] == 2000.0
    assert answer["b2cs"][0]["central_tax"] == 180.0


def test_a_cancelled_invoice_is_not_a_supply() -> None:
    """Nor is a draft. Declaring either would file a sale that did not happen."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    books.invoice("SI-2", status="CANCELLED")
    books.invoice("SI-3", status="DRAFT")

    b2b = books.gstr1()["b2b"]

    assert [row["invoice_number"] for row in b2b[0]["invoices"]] == ["SI-1"]


def test_the_taxable_value_is_what_was_charged_not_the_net() -> None:
    """`net_amount` includes the tax.

    Declaring it as the taxable value would over-state every supply by its own
    tax, and the return would not reconcile against the sales register.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", gross="1000", discount="100", tax="162")

    invoices = books.gstr1()["b2b"][0]["invoices"]

    # 1000 less a 100 discount is 900 charged, and 162 of tax on top.
    assert invoices[0]["taxable_value"] == 900.0
    assert invoices[0]["invoice_value"] == 1062.0


def test_a_supply_outside_the_period_is_not_declared() -> None:
    """A return is for its own month, whatever else the firm has sold."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    books.invoice("SI-2", on=date(2026, 5, 3))

    b2b = books.gstr1()["b2b"]

    assert [row["invoice_number"] for row in b2b[0]["invoices"]] == ["SI-1"]


def test_the_hsn_summary_adds_up_to_the_supplies() -> None:
    """The summary reconciles against the detail above it.

    A filing where the two disagree is one nobody can defend.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    books.invoice("SI-2", customer=books.walk_in)

    answer = books.gstr1()
    hsn = answer["hsn"]

    assert len(hsn) == 1
    assert hsn[0]["hsn"] == "33061020"
    assert hsn[0]["quantity"] == 20.0
    assert hsn[0]["taxable_value"] == 2000.0
    assert hsn[0]["central_tax"] == 180.0


def test_the_document_series_records_what_was_issued() -> None:
    """So a firm cannot quietly skip a range of numbers."""
    books = _Books(_session_factory()())
    books.invoice("SI-2026-0001")
    books.invoice("SI-2026-0002")

    docs = books.gstr1()["docs"]

    assert len(docs) == 1
    assert docs[0]["prefix"] == "SI-2026"
    assert docs[0]["from"] == "SI-2026-0001"
    assert docs[0]["to"] == "SI-2026-0002"
    assert docs[0]["count"] == 2


def test_the_summary_return_matches_the_detail() -> None:
    """3B is derived from the documents, not parsed out of GSTR-1's JSON.

    Parsing a report back out of its own answer is how a summary drifts from
    the detail it summarises, so both read the invoices.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    books.invoice("SI-2", customer=books.walk_in)

    outward = books.gstr3b()["outward_taxable_supplies"]

    assert outward["taxable_value"] == 2000.0
    assert outward["central_tax"] == 180.0
    assert outward["state_tax"] == 180.0
    assert outward["integrated_tax"] == 0.0


def test_the_summary_says_it_does_not_know_the_inward_side() -> None:
    """A zero would read as "no input credit", which is a different claim."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")

    assert "Not derived" in str(books.gstr3b()["inward_supplies"])


def test_a_firm_with_no_gstin_has_no_return_to_file() -> None:
    """A return is filed *by* a GSTIN, so there is nothing to file without one."""
    books = _Books(_session_factory()(), seller=None)
    books.invoice("SI-1")

    with pytest.raises(ValidationError, match="no GST number"):
        books.gstr1()


def test_a_period_that_runs_backwards_is_refused() -> None:
    """The same guard every report in this repo carries."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError):
        GstReturnService(books.session).gstr1(
            firm_scope=books.firm.id,
            from_date=date(2026, 4, 30),
            to_date=date(2026, 4, 1),
        )


def test_one_firm_s_return_never_reads_another_firm_s_sales() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")

    with pytest.raises(ValidationError, match="no GST number"):
        # A firm that does not exist has no GSTIN, which is the first thing
        # asked -- and proves the scope is read before any sale is.
        GstReturnService(books.session).gstr1(
            firm_scope=uuid4(), from_date=APRIL[0], to_date=APRIL[1]
        )


def test_the_place_of_supply_is_read_off_the_tax_that_was_charged() -> None:
    """Not off the customer's address, which can disagree with the document.

    CGST and SGST are only chargeable within one state, so an invoice carrying
    them was a supply in the seller's own -- and that is the fact being
    declared. Reading a field the customer record does not even carry gave a
    blank place of supply on every B2CS row, which the portal rejects.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", customer=books.walk_in)

    row = books.gstr1()["b2cs"][0]

    assert row["place_of_supply"] == SELLER[:2]


def test_an_interstate_sale_to_an_unregistered_buyer_is_named_not_blanked() -> None:
    """There is nowhere left to read the state from, so say which invoice.

    The buyer has no GSTIN and the tax says the supply crossed a border. A
    blank cell would be rejected at upload with nothing to say which document
    caused it.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", customer=books.walk_in, interstate=True)

    answer = books.gstr1()

    assert answer["unplaced_invoices"] == ["SI-1"]
    assert answer["b2cs"][0]["place_of_supply"] == ""


def test_a_return_is_declared_in_rupees_and_paise() -> None:
    """Documents here are priced to four decimals; no portal accepts that."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", gross="1000.3333", tax="180.0599")

    invoice = books.gstr1()["b2b"][0]["invoices"][0]

    assert invoice["taxable_value"] == 1000.33
    assert invoice["central_tax"] == 90.03
    assert books.gstr1()["hsn"][0]["taxable_value"] == 1000.33


def test_a_credit_note_to_a_registered_buyer_is_declared_note_by_note() -> None:
    """The buyer reverses its own claim against the number."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1")
    books.credit("CN-1", invoice)

    cdnr = books.gstr1()["cdnr"]

    assert len(cdnr) == 1
    assert cdnr[0]["note_number"] == "CN-1"
    assert cdnr[0]["against_invoice"] == "SI-1"
    assert cdnr[0]["taxable_value"] == 100.0


def test_a_credit_note_to_an_unregistered_buyer_is_netted_off_the_summary() -> None:
    """It is not dropped, and it does not go in CDNR.

    There is no GSTIN to file it against and nobody to reverse a claim, so
    the return takes it off the B2CS row for the same place and rate. Dropped
    -- which it was, on the belief this system could not produce one -- 3B
    went on deducting a credit GSTR-1 never declared, and the two returns
    could not be reconciled against each other.
    """
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", customer=books.walk_in, gross="1000", tax="180")
    books.credit("CN-1", invoice, taxable="100", tax="18")

    answer = books.gstr1()

    assert answer["cdnr"] == []
    assert len(answer["b2cs"]) == 1
    assert answer["b2cs"][0]["taxable_value"] == 900.0
    assert answer["b2cs"][0]["central_tax"] == 81.0


def test_both_returns_deduct_the_same_credit_notes() -> None:
    """3B is a summary of GSTR-1, so it cannot deduct what GSTR-1 kept."""
    books = _Books(_session_factory()())
    registered = books.invoice("SI-1")
    walk_in = books.invoice("SI-2", customer=books.walk_in)
    books.credit("CN-1", registered, taxable="100", tax="18")
    books.credit("CN-2", walk_in, taxable="50", tax="9")

    one = books.gstr1()
    summary = books.gstr3b()

    declared = sum(
        invoice["taxable_value"]
        for party in one["b2b"]
        for invoice in party["invoices"]
    ) + sum(row["taxable_value"] for row in one["b2cs"])
    credited = sum(row["taxable_value"] for row in one["cdnr"])

    assert summary["credit_notes_deducted"]["taxable_value"] == 150.0
    assert summary["outward_taxable_supplies"]["taxable_value"] == declared - credited


def test_a_sales_return_to_a_registered_buyer_is_declared_in_cdnr() -> None:
    """A completed return is a credit note in GST terms (D-CMP-2).

    It credits the customer and its journal reverses the output tax, and it
    appeared in no section and no deduction -- the firm declared and paid tax
    it had already given back.
    """
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1")
    books.returned("SR-1", invoice, taxable="100", tax="18")

    cdnr = books.gstr1()["cdnr"]

    assert len(cdnr) == 1
    assert cdnr[0]["note_number"] == "SR-1"
    assert cdnr[0]["document_type"] == "SALES_RETURN"
    assert cdnr[0]["against_invoice"] == "SI-1"
    assert cdnr[0]["taxable_value"] == 100.0
    assert (cdnr[0]["central_tax"], cdnr[0]["state_tax"]) == (9.0, 9.0)


def test_a_sales_return_to_an_unregistered_buyer_comes_off_the_summary() -> None:
    """Netted off the B2CS row for its place and rate, as a credit note is."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", customer=books.walk_in, gross="300", tax="54")
    books.returned("SR-1", invoice, taxable="100", tax="18")

    answer = books.gstr1()

    assert answer["cdnr"] == []
    assert answer["b2cs"][0]["taxable_value"] == 200.0
    assert answer["b2cs"][0]["central_tax"] == 18.0


def test_the_summary_return_deducts_a_completed_sales_return() -> None:
    """3B's outward tax falls by what the return gave back, and only once done."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", gross="1000", tax="180")
    books.returned("SR-1", invoice, taxable="100", tax="18")
    # Not yet given back: an approved return has credited nobody.
    books.returned("SR-2", invoice, taxable="100", tax="18", status="APPROVED")
    books.returned("SR-3", invoice, taxable="100", tax="18", status="CANCELLED")

    summary = books.gstr3b()

    assert summary["outward_taxable_supplies"]["taxable_value"] == 900.0
    assert summary["outward_taxable_supplies"]["central_tax"] == 81.0
    assert summary["outward_taxable_supplies"]["state_tax"] == 81.0
    assert summary["credit_notes_deducted"] == {"taxable_value": 100.0, "tax": 18.0}


def test_a_return_against_a_large_interstate_bill_is_declared_in_cdnur() -> None:
    """Table 9B: the bill was declared invoice by invoice, so is its credit."""
    books = _Books(_session_factory()())
    invoice = books.invoice(
        "SI-1",
        customer=books.walk_in,
        gross="300000",
        tax="54000",
        interstate=True,
    )
    books.returned("SR-1", invoice, taxable="1000", tax="180", interstate=True)

    answer = books.gstr1()

    assert [row["note_number"] for row in answer["cdnur"]] == ["SR-1"]
    assert answer["cdnur"][0]["integrated_tax"] == 180.0
    assert answer["b2cs"] == []
    assert books.gstr3b()["outward_taxable_supplies"]["integrated_tax"] == 53820.0


def test_freight_is_declared_inside_the_taxable_value() -> None:
    """Delivery charged by the seller is taxed with the goods.

    Leaving it out of the return would declare less than the invoice charged
    tax on -- the one way a return can be wrong that nobody notices until an
    assessment.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", gross="1000", freight="200", tax="216")

    invoice = books.gstr1()["b2b"][0]["invoices"][0]

    assert invoice["taxable_value"] == 1200.0
    assert books.gstr1()["hsn"][0]["taxable_value"] == 1200.0


def test_a_line_charge_is_declared_inside_the_taxable_value() -> None:
    """`charges_amount` is taxed with the goods, so it is declared with them.

    `SalesInvoiceService._line_net_amount` hands the tax engine
    `gross - discounts + charges_amount + freight_amount`. `_taxable` had the
    freight -- added when #191 moved it inside the taxable value -- and never
    had the charges, so a return declared **less taxable value than the
    invoice charged tax on**. Its own docstring names that as the one way a
    return can be wrong that nobody notices until an assessment.

    Found by the 2026-09-03 review, the same staleness `credit_note` carried
    in #207.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-1", gross="1000", charges="100", tax="198")

    invoice = books.gstr1()["b2b"][0]["invoices"][0]
    assert invoice["taxable_value"] == 1100.0
    # And the HSN summary, which an assessment reads beside it.
    assert books.gstr1()["hsn"][0]["taxable_value"] == 1100.0


def test_freight_and_a_line_charge_are_both_declared() -> None:
    """Both, and neither one instead of the other."""
    books = _Books(_session_factory()())
    books.invoice("SI-1", gross="1000", freight="50", charges="100", tax="207")

    invoice = books.gstr1()["b2b"][0]["invoices"][0]
    assert invoice["taxable_value"] == 1150.0


def _untaxed(books: _Books, invoice: SalesInvoice, *, kind: str) -> None:
    """Make an invoice's only line a nil-rated, exempt or non-GST supply."""
    line = books.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    ).one()
    components = books.session.scalars(
        select(SalesInvoiceLineTax).where(
            SalesInvoiceLineTax.sales_invoice_line_id == line.id
        )
    ).all()
    for component in components:
        if kind == "NIL":
            component.percentage = Decimal("0")
            component.amount = Decimal("0")
        else:
            books.session.delete(component)
    line.tax_amount = Decimal("0")
    line.tax_profile_id = None if kind == "NON_GST" else uuid4()
    invoice.grand_total = Decimal(str(line.gross_amount))
    books.session.commit()


@pytest.mark.parametrize(
    ("on", "section"),
    [
        # 1,77,000 is above the Rs 1,00,000 limit in force from 1 August 2024.
        (date(2026, 4, 10), "b2cl"),
        # The same bill before that day was below the Rs 2,50,000 limit then.
        (date(2024, 7, 10), "b2cs"),
    ],
)
def test_the_b2cl_limit_is_the_one_in_force_on_the_invoice_date(
    on: date, section: str
) -> None:
    """Notification 12/2024-CT cut B2CL to Rs 1,00,000 from 1 August 2024.

    A bill between the two figures was summarised in B2CS when it had to be
    declared invoice by invoice (D-CMP-10).
    """
    books = _Books(_session_factory()())
    books.invoice(
        "SI-1",
        customer=books.walk_in,
        gross="150000",
        tax="27000",
        interstate=True,
        on=on,
    )

    answer = GstReturnService(books.session).gstr1(
        firm_scope=books.firm.id,
        from_date=on.replace(day=1),
        to_date=on.replace(day=28),
    )

    assert len(answer[section]) == 1
    assert b2cl_threshold(on) == (
        Decimal("100000") if on >= date(2024, 8, 1) else Decimal("250000")
    )


def test_untaxed_supplies_are_table_8_not_zero_rate_rows() -> None:
    """Nil-rated, exempt and non-GST sales were filed as 0% taxable (D-CMP-10)."""
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    _untaxed(books, books.invoice("SI-2", gross="200"), kind="NIL")
    _untaxed(books, books.invoice("SI-3", gross="300"), kind="EXEMPT")
    _untaxed(
        books, books.invoice("SI-4", customer=books.walk_in, gross="50"), kind="NON_GST"
    )

    answer = books.gstr1()
    summary = books.gstr3b()

    assert [
        invoice["invoice_number"]
        for party in answer["b2b"]
        for invoice in party["invoices"]
    ] == ["SI-1"]
    assert answer["b2cs"] == []
    assert answer["nil_exempt"] == [
        {
            "supply_type": "INTRA-STATE TO REGISTERED",
            "nil_rated": 200.0,
            "exempted": 300.0,
            "non_gst": 0.0,
        },
        {
            "supply_type": "INTRA-STATE TO UNREGISTERED",
            "nil_rated": 0.0,
            "exempted": 0.0,
            "non_gst": 50.0,
        },
    ]
    assert summary["outward_taxable_supplies"]["taxable_value"] == 1000.0
    assert summary["nil_rated_and_exempt_supplies"] == {"taxable_value": 500.0}
    assert summary["non_gst_supplies"] == {"taxable_value": 50.0}


def test_the_document_series_counts_what_was_cancelled() -> None:
    """Table 13 explains every number in the range (D-CMP-10).

    Counting only live bills left a cancelled number as a gap in the declared
    range with nothing to say why.
    """
    books = _Books(_session_factory()())
    books.invoice("SI-2026-0001")
    books.invoice("SI-2026-0002", status="CANCELLED")
    books.invoice("SI-2026-0003")
    books.invoice("SI-2026-0004", status="DRAFT")

    docs = books.gstr1()["docs"]

    assert docs == [
        {
            "prefix": "SI-2026",
            "from": "SI-2026-0001",
            "to": "SI-2026-0003",
            "total_number": 3,
            "cancelled": 1,
            "net_issued": 2,
            "count": 2,
        }
    ]


MAY = (date(2026, 5, 1), date(2026, 5, 31))


def _cancel(books: _Books, invoice: SalesInvoice, *, on: date) -> None:
    """Cancel a bill the way the invoice service does: a receivable credit, dated."""
    invoice.status = "CANCELLED"
    books.session.add(
        CustomerReceivableTransaction(
            firm_id=books.firm.id,
            customer_id=invoice.customer_id,
            transaction_type="CREDIT_NOTE",
            transaction_date=on,
            amount=invoice.grand_total,
            outstanding_delta=-invoice.grand_total,
            advance_delta=Decimal("0"),
            outstanding_after=Decimal("0"),
            advance_after=Decimal("0"),
            reference_type="SALES_INVOICE",
            reference_id=invoice.id,
            reference_number=invoice.invoice_number,
        )
    )
    books.session.commit()


def _returns_for(books: _Books, period: tuple[date, date]) -> tuple[dict, dict]:
    """Return GSTR-1 and GSTR-3B for one period."""
    service = GstReturnService(books.session)
    return (
        service.gstr1(firm_scope=books.firm.id, from_date=period[0], to_date=period[1]),
        service.gstr3b(
            firm_scope=books.firm.id, from_date=period[0], to_date=period[1]
        ),
    )


def test_a_month_already_due_stands_when_a_bill_in_it_is_cancelled() -> None:
    """April's return was due on 11 May; a cancellation on 20 May is May's.

    Both returns were re-derived from today's status, so cancelling a bill
    rewrote a month already filed, and no later month showed the reversal
    (D-CMP-11). The bill stays in April and May declares its cancellation.
    """
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", gross="1000", tax="180")
    _cancel(books, invoice, on=date(2026, 5, 20))

    april, april_summary = _returns_for(books, APRIL)
    may, may_summary = _returns_for(books, MAY)

    assert [doc["invoice_number"] for doc in april["b2b"][0]["invoices"]] == ["SI-1"]
    assert april_summary["outward_taxable_supplies"]["taxable_value"] == 1000.0
    assert may["b2b"] == []
    assert [(row["note_number"], row["document_type"]) for row in may["cdnr"]] == [
        ("SI-1", "CANCELLED_INVOICE")
    ]
    assert may["cdnr"][0]["note_date"] == "2026-05-20"
    assert may_summary["outward_taxable_supplies"]["taxable_value"] == -1000.0
    assert may_summary["credit_notes_deducted"] == {
        "taxable_value": 1000.0,
        "tax": 180.0,
    }


def test_a_bill_cancelled_before_its_return_is_due_is_simply_not_declared() -> None:
    """Cancelled on 5 May, April is not yet filed: it drops out, nothing in May."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1")
    _cancel(books, invoice, on=date(2026, 5, 5))

    april, _ = _returns_for(books, APRIL)
    may, may_summary = _returns_for(books, MAY)

    assert april["b2b"] == []
    assert may["cdnr"] == []
    assert may_summary["credit_notes_deducted"]["taxable_value"] == 0.0


def test_an_unregistered_buyer_s_late_cancellation_comes_off_the_summary() -> None:
    """Netted off B2CS in the month of cancellation, as a credit note is."""
    books = _Books(_session_factory()())
    invoice = books.invoice("SI-1", customer=books.walk_in, gross="300", tax="54")
    _cancel(books, invoice, on=date(2026, 5, 20))

    april, _ = _returns_for(books, APRIL)
    may, _ = _returns_for(books, MAY)

    assert april["b2cs"][0]["taxable_value"] == 300.0
    assert may["b2cs"][0]["taxable_value"] == -300.0
    assert may["b2cs"][0]["central_tax"] == -27.0


def test_a_bill_cancelled_after_its_month_was_due_counts_as_issued_there() -> None:
    """April's DOCS was filed with the bill standing (D-CMP-10 with D-CMP-11).

    A cancellation after 11 May belongs to May, so April's Table 13 must not
    count it as cancelled; one cancelled before the due date still is.
    """
    books = _Books(_session_factory()())
    late = books.invoice("SI-2026-0001")
    early = books.invoice("SI-2026-0002")
    books.invoice("SI-2026-0003")
    _cancel(books, late, on=date(2026, 5, 20))
    _cancel(books, early, on=date(2026, 5, 5))

    docs = books.gstr1()["docs"]

    assert docs[0]["total_number"] == 3
    assert docs[0]["cancelled"] == 1
    assert docs[0]["net_issued"] == 2
