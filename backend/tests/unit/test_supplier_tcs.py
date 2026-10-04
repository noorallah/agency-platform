"""PG-6 (§86 #9): TCS a supplier charged, recorded on the bill.

A supplier selling the firm more than 50 lakh a year may charge TCS under
206C(1H) on top of the bill. The bill carries the rate and the amount -- typed,
or the rate on the grand total including GST -- outside GST's taxable value.
Approving posts Dr TCS Receivable and adds it to the payable; cancelling takes
it back; what the bill owes, the payables report and the *TCS paid to
suppliers* report all count it.

Sessions are shaped like a request's (no autoflush), as in the PG-3 tests.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import event

from app.finance.services.control_accounts import ControlAccountPurpose
from app.purchase_invoice.api.router import tcs_paid_to_suppliers
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoicePaymentNow,
)
from app.purchase_invoice.services.payables_report import PayablesReportService
from app.purchase_invoice.services.tcs_paid_report import (
    TcsPaidReportService,
    quarter_of,
)
from app.settlements.schemas import SettlementMethodEnum
from app.settlements.services import PaymentService
from tests.unit.test_cash_purchase import _chain_firm, _scope
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers


def _bill_data(
    firm: _Firm,
    *,
    number: str = "S-1",
    quantity: str = "10",
    on: date | None = None,
    **tcs: str | None,
) -> PurchaseInvoiceCreate:
    """Build a product bill (10 at 100, no GST) with the TCS fields given."""
    data = firm.product_bill(quantity=quantity, number=number).model_dump(
        exclude_unset=True
    )
    if on is not None:
        data["invoice_date"] = on
        data["supplier_invoice_date"] = on
    data.update(tcs)
    return PurchaseInvoiceCreate.model_validate(data)


def _create(firm: _Firm, data: PurchaseInvoiceCreate) -> PurchaseInvoice:
    """Save a draft bill."""
    return firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )


def _approved(firm: _Firm, data: PurchaseInvoiceCreate) -> PurchaseInvoice:
    """Save and approve a bill."""
    bill = _create(firm, data)
    return firm.bills().approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _owed(firm: _Firm, bill_id: UUID) -> Decimal:
    """Return what one bill still owes the supplier."""
    for record in PaymentService(firm.session).outstanding_invoices(
        firm_id=firm.firm.id, party_id=firm.vendor.id
    ):
        if record.invoice_id == bill_id:
            return record.outstanding_amount
    return Decimal("0")


def test_the_rate_alone_works_out_the_amount_on_the_grand_total() -> None:
    firm = _chain_firm()

    bill = _create(firm, _bill_data(firm, tcs_rate_percent="0.1"))

    assert bill.grand_total == Decimal("1000.0000")
    assert bill.tcs_rate_percent == Decimal("0.1")
    assert bill.tcs_amount == Decimal("1.00")
    response = firm.bills().invoice_response(bill)
    assert response.amount_owed == Decimal("1001.00")


def test_a_typed_amount_wins_over_the_rate() -> None:
    firm = _chain_firm()

    bill = _create(firm, _bill_data(firm, tcs_rate_percent="0.1", tcs_amount="2.50"))

    assert bill.tcs_rate_percent == Decimal("0.1")
    assert bill.tcs_amount == Decimal("2.50")


def test_tcs_leaves_the_gst_taxable_value_and_the_tax_alone() -> None:
    firm = _chain_firm()
    plain = _create(firm, _bill_data(firm, number="S-PLAIN"))
    charged = _create(firm, _bill_data(firm, number="S-TCS", tcs_rate_percent="1"))

    assert plain.tcs_amount == Decimal("0")
    assert charged.tcs_amount == Decimal("10.00")
    assert (charged.subtotal, charged.tax_total, charged.grand_total) == (
        plain.subtotal,
        plain.tax_total,
        plain.grand_total,
    )
    service = firm.bills()

    def lines(bill: PurchaseInvoice) -> list[tuple[Decimal, Decimal]]:
        """Return each line's taxable value and tax."""
        return [
            (line.gross_amount, line.tax_amount)
            for line in service.invoice_response(bill).lines
        ]

    assert lines(charged) == lines(plain)


def test_an_edit_naming_neither_field_keeps_them_and_the_rate_follows_the_total() -> (
    None
):
    firm = _chain_firm()
    by_rate = _create(firm, _bill_data(firm, number="S-R", tcs_rate_percent="1"))
    typed = _create(firm, _bill_data(firm, number="S-T", tcs_amount="7.00"))

    by_rate = firm.bills().update_invoice(
        by_rate.id,
        _bill_data(firm, number="S-R", quantity="20"),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    typed = firm.bills().update_invoice(
        typed.id,
        _bill_data(firm, number="S-T", quantity="20"),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )

    assert (by_rate.tcs_rate_percent, by_rate.tcs_amount) == (
        Decimal("1"),
        Decimal("20.00"),
    )
    assert (typed.tcs_rate_percent, typed.tcs_amount) == (None, Decimal("7.00"))

    cleared = firm.bills().update_invoice(
        typed.id,
        _bill_data(firm, number="S-T", tcs_amount=None),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )
    assert cleared.tcs_amount == Decimal("0")


def test_approving_posts_the_tcs_to_tcs_receivable_and_the_payable() -> None:
    firm = _chain_firm()

    bill = _approved(firm, _bill_data(firm, tcs_rate_percent="0.1"))

    assert bill.status == "APPROVED"
    assert firm.balance(ControlAccountPurpose.TCS_RECEIVABLE) == Decimal("1.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-1001.00")


def test_what_the_bill_owes_includes_the_tcs_and_paying_it_clears_both() -> None:
    firm = _chain_firm()
    bill = _approved(firm, _bill_data(firm, tcs_amount="2.50"))

    assert _owed(firm, bill.id) == Decimal("1002.50")

    report = PayablesReportService(firm.session).report(
        firm.firm.id, as_of=date(2026, 8, 31), months=3
    )
    assert report.total.total == Decimal("1002.50")
    assert report.books_check.difference == Decimal("0.00")


def test_approve_and_pay_pays_the_bill_with_its_tcs() -> None:
    firm = _chain_firm()
    bill = _create(firm, _bill_data(firm, tcs_amount="2.50"))

    firm.bills().approve_and_pay(
        bill.id,
        PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH),
        firm_scope=firm.firm.id,
        actor_id=firm.actor_id,
    )

    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == Decimal("-1002.50")
    assert _owed(firm, bill.id) == Decimal("0")


def test_cancelling_the_bill_reverses_the_tcs() -> None:
    firm = _chain_firm()
    bill = _approved(firm, _bill_data(firm, tcs_amount="2.50"))

    firm.bills().cancel_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id, reason="Wrong"
    )

    assert firm.balance(ControlAccountPurpose.TCS_RECEIVABLE) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert TcsPaidReportService(firm.session).rows(firm.firm.id) == []


def test_quarters_follow_the_financial_year() -> None:
    assert quarter_of(date(2026, 4, 1)) == "Q1 2026-27"
    assert quarter_of(date(2026, 9, 30)) == "Q2 2026-27"
    assert quarter_of(date(2026, 12, 31)) == "Q3 2026-27"
    assert quarter_of(date(2027, 3, 31)) == "Q4 2026-27"


def test_the_report_lists_each_bill_and_closes_each_quarter() -> None:
    firm = _chain_firm()
    firm.vendor.pan = "AAACV1234A"
    firm.session.commit()
    _approved(firm, _bill_data(firm, number="S-A", tcs_rate_percent="0.1"))
    _approved(firm, _bill_data(firm, number="S-B", tcs_amount="2.00"))
    _approved(
        firm,
        _bill_data(firm, number="S-C", on=date(2026, 10, 5), tcs_amount="3.00"),
    )
    _create(firm, _bill_data(firm, number="S-DRAFT", tcs_amount="9.00"))
    _approved(firm, _bill_data(firm, number="S-NONE"))

    response = tcs_paid_to_suppliers(
        scope=_scope(firm, "PURCHASE_VIEW"),  # type: ignore[arg-type]
        from_date=date(2026, 4, 1),
        to_date=date(2027, 3, 31),
        db=firm.session,
    )

    rows = [
        (row.row_type, row.quarter, row.vendor_pan, row.base_amount, row.tcs_amount)
        for row in response.data
    ]
    assert rows == [
        ("BILL", "Q2 2026-27", "AAACV1234A", Decimal("1000.00"), Decimal("1.00")),
        ("BILL", "Q2 2026-27", "AAACV1234A", Decimal("1000.00"), Decimal("2.00")),
        ("QUARTER_TOTAL", "Q2 2026-27", None, Decimal("2000.00"), Decimal("3.00")),
        ("BILL", "Q3 2026-27", "AAACV1234A", Decimal("1000.00"), Decimal("3.00")),
        ("QUARTER_TOTAL", "Q3 2026-27", None, Decimal("1000.00"), Decimal("3.00")),
    ]
    assert response.data[0].tcs_rate_percent == Decimal("0.1")
    assert response.data[0].vendor_name == "Vendor"


def test_the_report_reads_one_statement_whatever_it_holds() -> None:
    firm = _chain_firm()
    service = TcsPaidReportService(firm.session)

    def count() -> int:
        """Count the statements one read of the report sends."""
        seen: list[str] = []

        def note(*args: object) -> None:
            """Record one statement."""
            seen.append(str(args[2]))

        engine = firm.session.get_bind()
        event.listen(engine, "before_cursor_execute", note)
        try:
            service.rows(firm.firm.id)
        finally:
            event.remove(engine, "before_cursor_execute", note)
        return len(seen)

    _approved(firm, _bill_data(firm, number="S-1", tcs_amount="1.00"))
    one = count()
    for number in ("S-2", "S-3", "S-4"):
        _approved(firm, _bill_data(firm, number=number, tcs_amount="1.00"))

    assert count() == one == 1
