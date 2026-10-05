"""Charges on the bill with their own GST (backlog 87 #4, SG-4).

Packing, handling or insurance on a sales invoice, taxed at a rate of its own
beside goods taxed at another: a ``sales_invoice_charges`` row per charge,
taxed through the rule engine like a line, credited to *Other charges
recovered* and declared in GSTR-1 under its own SAC. Freight (split across
the goods) and ``additional_charges`` (untaxed) are untouched.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.credit_note.schemas import CreditNoteCreate, CreditNoteLineWrite
from app.credit_note.services import CreditNoteService
from app.einvoice.services.payload import EInvoicePayloadBuilder
from app.finance.models import (
    FirmControlAccount,
    JournalEntry,
    JournalLine,
    LedgerAccount,
)
from app.finance.services.control_accounts import ControlAccountPurpose
from app.gst_returns.services import GstReturnService
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceCharge,
    SalesInvoiceLine,
)
from app.sales_invoice.schemas import (
    SalesInvoiceChargeWrite,
    SalesInvoiceCreate,
    SalesInvoiceResponse,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
)
from app.tax.models import TaxProfile
from app.tax.services.gst_template import apply_india_gst_template
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

D = Decimal
#: A Tamil Nadu firm; a buyer in the same state, and one in Karnataka.
SELLER = "33AABCU9603R1ZM"
LOCAL_BUYER = "33AAACR5055K1Z5"
OTHER_STATE_BUYER = "29AAACR5055K1Z5"
PACKING_SAC = "998540"


class _Counter:
    """A firm that types only the bill, on the GST template.

    Its one product is taxed at 5%, so a charge at 18% beside it shows the
    two rates apart.
    """

    def __init__(self, buyer_gstin: str | None = LOCAL_BUYER) -> None:
        """Build the firm, register it and its buyer, and tax the product."""
        self.session: Session = _session_factory()()
        self.setup = _Firm(self.session)
        self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.actor = uuid4()
        self.setup.firm.gst_number = SELLER
        self.setup.customer.gst_number = buyer_gstin
        self.session.commit()
        apply_india_gst_template(
            self.session, firm_id=self.setup.firm.id, actor_id=self.actor
        )
        self.setup.product.tax_profile_group_code = "GST_5_LOCAL"
        self.setup.product.hsn_sac = "33061020"
        self.session.commit()
        self.service = SalesInvoiceService(self.session)

    @property
    def firm_id(self) -> UUID:
        """Return the firm."""
        return self.setup.firm.id

    def profile(self, code: str = "GST_18_LOCAL") -> UUID:
        """Return one of the template's tax profiles."""
        found = self.session.scalar(
            select(TaxProfile.id).where(
                TaxProfile.firm_id == self.firm_id, TaxProfile.code == code
            )
        )
        assert found is not None
        return found

    def packing(self, amount: str = "100") -> SalesInvoiceChargeWrite:
        """Describe packing charged at 18%."""
        return SalesInvoiceChargeWrite(
            name="Packing",
            amount=D(amount),
            tax_profile_id=self.profile(),
            hsn_sac=PACKING_SAC,
        )

    def bill(self, **fields: object) -> SalesInvoiceCreate:
        """Describe 4 x 100 of the 5% product, with whatever else is named."""
        return SalesInvoiceCreate.model_validate(
            self.setup.bare_bill().model_dump(exclude_unset=True) | fields
        )

    def edit(self, row: SalesInvoice, **fields: object) -> SalesInvoiceCreate:
        """Describe a save of a draft that names only its line and ``fields``."""
        line = self.session.scalar(
            select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == row.id)
        )
        assert line is not None
        return SalesInvoiceCreate.model_validate(
            {
                "customer_id": row.customer_id,
                "invoice_date": row.invoice_date,
                "lines": [
                    {
                        "source_document_type": line.source_document_type,
                        "source_document_id": line.source_document_id,
                        "source_document_line_id": line.source_document_line_id,
                        "line_number": 1,
                        "current_invoice_quantity": D("4"),
                    }
                ],
            }
            | fields
        )

    def draft(self, **fields: object) -> SalesInvoice:
        """Save a bill as a draft."""
        row = self.service.create_invoice(
            self.bill(**fields), firm_id=self.firm_id, actor_id=self.actor
        )
        self.session.commit()
        return row

    def approved(self, **fields: object) -> SalesInvoice:
        """Save and approve a bill."""
        row = self.draft(**fields)
        return self.service.approve_invoice(
            row.id, firm_scope=self.firm_id, actor_id=self.actor
        )

    def charges(self, invoice_id: UUID) -> list[SalesInvoiceCharge]:
        """Return a bill's stored charges in order."""
        return list(
            self.session.scalars(
                select(SalesInvoiceCharge)
                .where(SalesInvoiceCharge.sales_invoice_id == invoice_id)
                .order_by(SalesInvoiceCharge.sequence)
            ).all()
        )

    def response(self, row: SalesInvoice) -> SalesInvoiceResponse:
        """Return the bill as the API answers it."""
        return self.service.invoice_response(row)

    def legs(self, invoice_id: UUID) -> dict[str, tuple[Decimal, Decimal]]:
        """Return (debit, credit) per account code of the bill's own journal."""
        entry = self.session.scalar(
            select(JournalEntry).where(
                JournalEntry.source_module == "sales_invoice",
                JournalEntry.source_id == invoice_id,
                JournalEntry.reversal_of_id.is_(None),
            )
        )
        assert entry is not None
        rows = self.session.execute(
            select(
                LedgerAccount.code,
                JournalLine.debit_amount,
                JournalLine.credit_amount,
            )
            .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
            .where(JournalLine.journal_entry_id == entry.id)
        ).all()
        return {code: (D(str(debit)), D(str(credit))) for code, debit, credit in rows}

    def account_code(self, purpose: ControlAccountPurpose) -> str:
        """Return the code of the account a purpose is mapped to."""
        code = self.session.scalar(
            select(LedgerAccount.code)
            .join(
                FirmControlAccount,
                FirmControlAccount.ledger_account_id == LedgerAccount.id,
            )
            .where(
                FirmControlAccount.firm_id == self.firm_id,
                FirmControlAccount.purpose == purpose.value,
            )
        )
        assert code is not None
        return code

    def gstr1(self) -> dict[str, object]:
        """Return August's outward supplies."""
        return GstReturnService(self.session).gstr1(
            firm_scope=self.firm_id,
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 31),
        )


def test_a_charge_is_taxed_at_its_own_rate_beside_the_goods() -> None:
    """Goods at 5% and packing at 18%: each taxed apart, both in the total."""
    books = _Counter()

    row = books.draft(charges=[books.packing()])

    # 400 of goods at 5% is 20; 100 of packing at 18% is 18.
    assert row.subtotal == D("400.0000")
    assert row.tax_total == D("38.0000")
    assert row.grand_total == D("538.0000")
    [charge] = books.charges(row.id)
    assert (charge.name, charge.hsn_sac, charge.sequence) == (
        "Packing",
        PACKING_SAC,
        1,
    )
    assert charge.amount == D("100.0000")
    assert charge.tax_rate_percent == D("18.0000")
    assert charge.tax_amount == D("18.0000")
    assert (charge.cgst_amount, charge.sgst_amount) == (D("9.0000"), D("9.0000"))
    assert (charge.igst_amount, charge.cess_amount) == (D("0"), D("0"))

    answer = books.response(row)
    assert answer.charges_total == D("100.0000")
    assert [(item.name, item.tax_amount) for item in answer.charges] == [
        ("Packing", D("18.0000"))
    ]
    assert answer.charges[0].id == charge.id


def test_a_charge_to_another_state_carries_igst() -> None:
    """The charge follows the supply: a Karnataka buyer is charged IGST."""
    books = _Counter(buyer_gstin=OTHER_STATE_BUYER)

    row = books.draft(charges=[books.packing()])

    [charge] = books.charges(row.id)
    assert charge.igst_amount == D("18.0000")
    assert (charge.cgst_amount, charge.sgst_amount) == (D("0"), D("0"))
    assert charge.tax_rate_percent == D("18.0000")
    assert row.tax_total == D("38.0000")


def test_a_charge_naming_no_tax_profile_is_not_taxed() -> None:
    """It is added to the bill and to nothing else."""
    books = _Counter()

    row = books.draft(
        charges=[SalesInvoiceChargeWrite(name="Handling", amount=D("50"))]
    )

    [charge] = books.charges(row.id)
    assert charge.tax_amount == D("0")
    assert charge.tax_rate_percent == D("0")
    assert row.tax_total == D("20.0000")
    assert row.grand_total == D("470.0000")


def test_the_untaxed_additions_and_freight_are_left_as_they_were() -> None:
    """A bill with no charges totals exactly as before."""
    books = _Counter()

    row = books.draft(additional_charges=D("10"))

    assert books.charges(row.id) == []
    assert row.tax_total == D("20.0000")
    assert row.grand_total == D("430.0000")
    assert books.response(row).charges == []


def test_a_charge_needs_a_name_and_at_most_ten_are_held() -> None:
    """The request refuses a blank name and an eleventh charge."""
    with pytest.raises(ValueError, match="name"):
        SalesInvoiceChargeWrite(name="   ", amount=D("1"))
    books = _Counter()
    with pytest.raises(ValueError, match="charges"):
        books.bill(charges=[books.packing().model_dump()] * 11)


def test_approval_credits_the_charge_to_its_own_account() -> None:
    """Revenue takes the goods, the charge its own account, tax by head."""
    books = _Counter()

    row = books.approved(charges=[books.packing()])

    legs = books.legs(row.id)
    assert sum(debit for debit, _ in legs.values()) == sum(
        credit for _, credit in legs.values()
    )
    receivable = books.account_code(ControlAccountPurpose.ACCOUNTS_RECEIVABLE)
    assert legs[receivable] == (D("538.00"), D("0.00"))
    assert legs[books.account_code(ControlAccountPurpose.SALES_REVENUE)] == (
        D("0.00"),
        D("400.00"),
    )
    recovered = books.account_code(ControlAccountPurpose.OTHER_CHARGES_RECOVERED)
    assert recovered == "4050"
    assert legs[recovered] == (D("0.00"), D("100.00"))
    # 10 + 9 of central tax and the same of state tax.
    assert legs[books.account_code(ControlAccountPurpose.OUTPUT_TAX_CGST)] == (
        D("0.00"),
        D("19.00"),
    )
    assert legs[books.account_code(ControlAccountPurpose.OUTPUT_TAX_SGST)] == (
        D("0.00"),
        D("19.00"),
    )


def test_a_bill_without_charges_posts_no_charges_leg() -> None:
    """The account is asked for only by a bill that carries a charge."""
    books = _Counter()
    mapping = books.session.scalar(
        select(FirmControlAccount).where(
            FirmControlAccount.firm_id == books.firm_id,
            FirmControlAccount.purpose
            == ControlAccountPurpose.OTHER_CHARGES_RECOVERED.value,
        )
    )
    assert mapping is not None
    books.session.delete(mapping)
    books.session.commit()

    row = books.approved()

    assert "4050" not in books.legs(row.id)
    with pytest.raises(ValidationError, match="OTHER_CHARGES_RECOVERED"):
        books.approved(charges=[books.packing()])


def test_gstr1_declares_the_charge_under_its_own_sac() -> None:
    """Its value and tax reach B2B and the HSN summary; 3B follows."""
    books = _Counter()
    books.approved(charges=[books.packing()])

    answer = books.gstr1()

    b2b = answer["b2b"]
    assert isinstance(b2b, list)
    # B2B states the invoice whole: 400 of goods and 100 of packing, with
    # 10 + 9 of each head.
    [invoice] = b2b[0]["invoices"]
    assert invoice["invoice_value"] == 538.0
    assert invoice["taxable_value"] == 500.0
    assert invoice["central_tax"] == 19.0
    assert invoice["state_tax"] == 19.0
    hsn = answer["hsn"]
    assert isinstance(hsn, list)
    rows = {item["hsn"]: item for item in hsn}
    assert rows[PACKING_SAC]["taxable_value"] == 100.0
    assert rows[PACKING_SAC]["central_tax"] == 9.0
    assert rows[PACKING_SAC]["state_tax"] == 9.0
    assert rows[PACKING_SAC]["quantity"] == 0.0
    assert rows[PACKING_SAC]["description"] == "Packing"
    assert rows["33061020"]["taxable_value"] == 400.0

    outward = GstReturnService(books.session).gstr3b(
        firm_scope=books.firm_id,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
    )["outward_taxable_supplies"]
    assert isinstance(outward, dict)
    assert outward["taxable_value"] == 500.0
    assert outward["central_tax"] == 19.0


def test_an_update_that_omits_the_charges_keeps_them() -> None:
    """Absent leaves them alone; an empty list clears them and the totals fall."""
    books = _Counter()
    row = books.draft(charges=[books.packing()])

    kept = books.service.update_invoice(
        row.id,
        books.edit(row, remarks="Call before delivery"),
        firm_id=books.firm_id,
        actor_id=books.actor,
    )

    assert [charge.name for charge in books.charges(kept.id)] == ["Packing"]
    assert kept.tax_total == D("38.0000")
    assert kept.grand_total == D("538.0000")

    replaced = books.service.update_invoice(
        row.id,
        books.edit(row, charges=[books.packing("200")]),
        firm_id=books.firm_id,
        actor_id=books.actor,
    )

    assert [charge.amount for charge in books.charges(row.id)] == [D("200.0000")]
    assert replaced.tax_total == D("56.0000")
    assert replaced.grand_total == D("656.0000")

    cleared = books.service.update_invoice(
        row.id,
        books.edit(row, charges=[]),
        firm_id=books.firm_id,
        actor_id=books.actor,
    )

    assert books.charges(row.id) == []
    assert cleared.tax_total == D("20.0000")
    assert cleared.grand_total == D("420.0000")


def test_a_credit_note_against_the_bill_leaves_the_charge_alone() -> None:
    """Crediting every line credits the goods and their tax, not the packing."""
    books = _Counter()
    row = books.approved(charges=[books.packing()])
    line = books.session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == row.id)
    )
    assert line is not None

    notes = CreditNoteService(books.session)
    note = notes.create_note(
        CreditNoteCreate(
            sales_invoice_id=row.id,
            credit_note_date=date(2026, 8, 5),
            lines=[
                CreditNoteLineWrite(
                    sales_invoice_line_id=line.id,
                    line_number=1,
                    quantity=D("4"),
                    taxable_amount=D("400"),
                )
            ],
        ),
        firm_id=books.firm_id,
        actor_id=books.actor,
    )
    books.session.commit()
    notes.approve_note(note.id, firm_scope=books.firm_id, actor_id=books.actor)

    assert note.total_amount == D("420.00")
    [charge] = books.charges(row.id)
    assert (charge.amount, charge.tax_amount) == (D("100.0000"), D("18.0000"))


def test_the_print_lists_the_charge_between_the_lines_and_the_total() -> None:
    """The document names the charge, and both renderers draw it."""
    books = _Counter()
    row = books.approved(charges=[books.packing()])

    printer = SalesInvoicePrintService(books.session)
    document = printer._document(row, firm_scope=books.firm_id)

    [charge] = document.taxed_charges
    assert (charge.name, charge.hsn, charge.amount) == (
        "Packing",
        PACKING_SAC,
        D("100.0000"),
    )
    assert charge.taxes == (
        ("CGST", D("9.0000"), D("9.0000")),
        ("SGST", D("9.0000"), D("9.0000")),
    )
    pdf, _ = printer.render(row.id, firm_scope=books.firm_id, reference_copy=True)
    assert pdf.startswith(b"%PDF")


def test_the_e_invoice_registers_the_charge_as_a_service_item() -> None:
    """The items add up to the invoice: the charge is one of them."""
    books = _Counter()
    row = books.approved(charges=[books.packing()])

    payload = EInvoicePayloadBuilder(books.session).build(row, firm_id=books.firm_id)

    items = payload["ItemList"]
    assert isinstance(items, list)
    packing = items[-1]
    assert (packing["IsServc"], packing["HsnCd"], packing["AssAmt"]) == (
        "Y",
        PACKING_SAC,
        100.0,
    )
    assert (packing["CgstAmt"], packing["SgstAmt"], packing["GstRt"]) == (
        9.0,
        9.0,
        18.0,
    )
    values = payload["ValDtls"]
    assert isinstance(values, dict)
    assert values["AssVal"] == 500.0
    assert values["TotInvVal"] == 538.0
    assert (
        values["AssVal"] + values["CgstVal"] + values["SgstVal"] + values["OthChrg"]
        == values["TotInvVal"]
    )
