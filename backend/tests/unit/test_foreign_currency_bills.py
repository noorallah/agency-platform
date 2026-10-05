"""PG-12 part A (§86 #4, #5): foreign-currency bills and exchange gain or loss.

A supplier abroad bills 10 units at 100 USD. The bill is stored as typed and
carries the rate it was booked at; the ledger posts rupees at that rate. A
payment in USD at the day's rate clears the payable at the bill's rupee value
and posts the difference to *Exchange Gain/Loss*. A period-end revaluation
restates what is still owed and reverses itself the next day.

Sessions are shaped like a request's (no autoflush), as in the PG-3 tests.
"""

# ruff: noqa: D103

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry, JournalLine
from app.finance.schemas.fx_revaluation import FxRevaluationRequest
from app.finance.services.control_accounts import ControlAccountPurpose
from app.finance.services.fx_revaluation import FxRevaluationService
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoicePaymentNow,
)
from app.purchase_invoice.services.payables_report import PayablesReportService
from app.settlements.models import Settlement, SettlementAllocation
from app.settlements.schemas import (
    OutstandingInvoiceRecord,
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService
from tests.unit.test_cash_purchase import _chain_firm
from tests.unit.test_purchase_chain_synthesis import _Firm

pytestmark = pytest.mark.typed_document_numbers

PAID_ON = date(2026, 8, 20)
AS_OF = date(2026, 8, 31)


def _bill_data(
    firm: _Firm, *, number: str = "S-1", **fields: object
) -> PurchaseInvoiceCreate:
    """Build a product bill (10 at 100, no GST) with the given header fields."""
    data = firm.product_bill(number=number).model_dump(exclude_unset=True)
    data.update(fields)
    return PurchaseInvoiceCreate.model_validate(data)


def _usd_bill(
    firm: _Firm, *, number: str = "S-USD", rate: str = "83"
) -> PurchaseInvoice:
    """Save and approve a bill of 1,000 USD at a rate."""
    data = _bill_data(firm, number=number, currency_code="usd", exchange_rate=rate)
    assert isinstance(data, PurchaseInvoiceCreate)
    bill = firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    return firm.bills().approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )


def _pay(firm: _Firm, bill: PurchaseInvoice, *, amount: str, rate: str) -> Settlement:
    """Pay part or all of a USD bill in USD at the day's rate."""
    settlement = PaymentService(firm.session).create(
        SettlementCreate(
            party_id=firm.vendor.id,
            settlement_date=PAID_ON,
            amount=Decimal(amount),
            method=SettlementMethodEnum.CASH,
            currency_code="USD",
            exchange_rate=Decimal(rate),
            allocations=[
                SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal(amount))
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    return settlement


def _record(firm: _Firm, bill_id: UUID) -> OutstandingInvoiceRecord | None:
    """Return what one bill still owes, or None once it owes nothing."""
    for record in PaymentService(firm.session).outstanding_invoices(
        firm_id=firm.firm.id, party_id=firm.vendor.id
    ):
        if record.invoice_id == bill_id:
            return record
    return None


def _journal(firm: _Firm, source_id: UUID) -> list[tuple[str, Decimal, Decimal]]:
    """Return a document's posted lines as (account code, debit, credit)."""
    from app.finance.models import LedgerAccount

    rows = firm.session.execute(
        select(LedgerAccount.code, JournalLine.debit_amount, JournalLine.credit_amount)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(
            JournalEntry.source_id == source_id,
            JournalEntry.reversal_of_id.is_(None),
        )
        .order_by(LedgerAccount.code)
    ).all()
    return [(code, Decimal(debit), Decimal(credit)) for code, debit, credit in rows]


def test_a_usd_bill_is_kept_as_typed_and_posts_rupees_at_its_rate() -> None:
    firm = _chain_firm()

    bill = _usd_bill(firm)

    assert (bill.currency_code, bill.exchange_rate) == ("USD", Decimal("83"))
    assert bill.grand_total == Decimal("1000.0000")
    assert bill.base_grand_total == Decimal("83000.00")
    response = firm.bills().invoice_response(bill)
    assert response.amount_owed == Decimal("1000.00")
    assert response.base_grand_total == Decimal("83000.00")
    assert response.base_amount_owed == Decimal("83000.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-83000.00")
    # The receipt the bill raised valued the stock in rupees at the same
    # rate, so the accrual clears with no price variance.
    assert firm.balance(ControlAccountPurpose.INVENTORY) == Decimal("83000.00")
    assert firm.balance(ControlAccountPurpose.GOODS_RECEIVED_NOT_INVOICED) == 0
    assert firm.balance(ControlAccountPurpose.PURCHASE_PRICE_VARIANCE) == 0
    record = _record(firm, bill.id)
    assert record is not None
    assert (record.outstanding_amount, record.currency_outstanding) == (
        Decimal("83000.00"),
        Decimal("1000.00"),
    )
    assert record.currency_code == "USD"


def test_paying_in_full_at_a_higher_rate_posts_a_loss() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    settlement = _pay(firm, bill, amount="1000", rate="84")

    assert settlement.amount == Decimal("84000.00")
    assert (settlement.currency_code, settlement.currency_amount) == (
        "USD",
        Decimal("1000.00"),
    )
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == Decimal("1000.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == Decimal("-84000.00")
    assert _record(firm, bill.id) is None
    allocation = firm.session.scalars(
        select(SettlementAllocation).where(
            SettlementAllocation.settlement_id == settlement.id
        )
    ).one()
    assert (allocation.amount, allocation.base_amount, allocation.currency_amount) == (
        Decimal("84000.00"),
        Decimal("83000.00"),
        Decimal("1000.00"),
    )


def test_paying_in_full_at_a_lower_rate_posts_a_gain() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    _pay(firm, bill, amount="1000", rate="82")

    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == Decimal("-1000.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == Decimal("-82000.00")


def test_a_part_payment_settles_in_proportion_in_both_currencies() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    _pay(firm, bill, amount="400", rate="84")

    # 400 USD cost 33,600 and cleared 33,200 of the bill's rupee value.
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == Decimal("400.00")
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-49800.00")
    record = _record(firm, bill.id)
    assert record is not None
    assert (record.outstanding_amount, record.currency_outstanding) == (
        Decimal("49800.00"),
        Decimal("600.00"),
    )

    # The rest at another rate leaves nothing behind in either currency.
    _pay(firm, bill, amount="600", rate="82.5")

    assert _record(firm, bill.id) is None
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0
    # 600 at 82.5 is 49,500 against 49,800 still owed: a gain of 300.
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == Decimal("100.00")


def test_reversing_the_payment_reverses_the_gain_or_loss() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    settlement = _pay(firm, bill, amount="1000", rate="84")

    PaymentService(firm.session).reverse(
        settlement.id, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    firm.session.commit()

    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == 0
    assert firm.balance(ControlAccountPurpose.CASH) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-83000.00")
    record = _record(firm, bill.id)
    assert record is not None
    assert record.currency_outstanding == Decimal("1000.00")


def test_revaluation_posts_the_unrealised_difference_and_reverses_it() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    result = FxRevaluationService(firm.session).revalue(
        FxRevaluationRequest(as_of=AS_OF, rates={"usd": Decimal("84.1")}),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()

    assert [(line.invoice_id, line.difference) for line in result.lines] == [
        (bill.id, Decimal("1100.00"))
    ]
    assert result.total_difference == Decimal("1100.00")
    entry = firm.session.get(JournalEntry, result.journal_entry_id)
    reversal = firm.session.get(JournalEntry, result.reversal_journal_entry_id)
    assert entry is not None and reversal is not None
    assert entry.journal_date == AS_OF
    assert reversal.journal_date == AS_OF + timedelta(days=1)
    assert reversal.reversal_of_id == entry.id
    # Posted and taken back: nothing stands once both are counted, and the
    # bill still owes its own rupee value.
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == Decimal("-83000.00")
    record = _record(firm, bill.id)
    assert record is not None
    assert record.outstanding_amount == Decimal("83000.00")

    with pytest.raises(ValidationError, match="already revalued"):
        FxRevaluationService(firm.session).revalue(
            FxRevaluationRequest(as_of=AS_OF, rates={"USD": Decimal("85")}),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_payables_agree_with_the_books_on_the_day_they_are_revalued() -> None:
    """D-FIN-27: the period end read "does not agree" by the revaluation.

    The revaluation is dated the period end and reversed the next day, so
    the day the payables are read against the books is the one day the
    account holds it. The bills stay at their booked rate.
    """
    firm = _chain_firm()
    _usd_bill(firm)
    FxRevaluationService(firm.session).revalue(
        FxRevaluationRequest(as_of=AS_OF, rates={"USD": Decimal("84.1")}),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    reports = PayablesReportService(firm.session)

    on_the_day = reports.report(firm.firm.id, as_of=AS_OF)
    assert on_the_day.total.total == Decimal("83000.00")
    check = on_the_day.books_check
    # The account really does hold the restated figure, and says why.
    assert check.ledger_balance == Decimal("84100.00")
    assert check.difference == Decimal("0.00")
    assert check.unrealised_revaluation == Decimal("1100.00")
    assert check.note is not None and "1100.00 of unrealised" in check.note

    for other_day in (AS_OF - timedelta(days=1), AS_OF + timedelta(days=1)):
        check = reports.report(firm.firm.id, as_of=other_day).books_check
        assert check.ledger_balance == Decimal("83000.00")
        assert check.unrealised_revaluation == Decimal("0.00")
        assert (check.difference, check.note) == (Decimal("0.00"), None)

    # One supplier's check reads its own documents and never held it.
    one = reports.report(firm.firm.id, as_of=AS_OF, vendor_id=firm.vendor.id)
    assert one.books_check.ledger_balance == Decimal("83000.00")
    assert one.books_check.difference == Decimal("0.00")
    # A real difference is still one: the allowance is the revaluation only.
    assert reports._unrealised_revaluation(firm.firm.id, AS_OF) == Decimal("1100.00")


def test_a_bill_typed_alone_with_no_rate_is_refused_as_a_bill() -> None:
    """D-BUY-51: the refusal named a purchase order nobody had typed.

    This firm types only the bill, which raises its order behind itself; the
    order asked for the rate first, in its own words.
    """
    firm = _chain_firm()
    data = _bill_data(firm, number="S-NORATE", currency_code="USD")
    assert isinstance(data, PurchaseInvoiceCreate)
    with pytest.raises(ValidationError) as refusal:
        firm.bills().create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)
    assert str(refusal.value.message) == (
        "A bill in USD needs its exchange rate: the rupees one USD was worth "
        "on the bill's date."
    )


def test_a_rupee_bill_posts_and_reads_exactly_as_before() -> None:
    firm = _chain_firm()
    data = _bill_data(firm, number="S-INR")
    assert isinstance(data, PurchaseInvoiceCreate)
    bill = firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    bill = firm.bills().approve_invoice(
        bill.id, firm_scope=firm.firm.id, actor_id=firm.actor_id
    )

    assert (bill.currency_code, bill.exchange_rate) == (None, None)
    assert (bill.base_tax_total, bill.base_grand_total) == (None, None)
    # Dr goods received not invoiced (2300), Cr payables (2100): the PG-3
    # expectation, with no exchange leg.
    assert _journal(firm, bill.id) == [
        ("2100", Decimal("0.00"), Decimal("1000.00")),
        ("2300", Decimal("1000.00"), Decimal("0.00")),
    ]
    response = firm.bills().invoice_response(bill)
    assert (response.amount_owed, response.base_amount_owed) == (
        Decimal("1000.00"),
        Decimal("1000.00"),
    )
    record = _record(firm, bill.id)
    assert record is not None
    assert record.outstanding_amount == Decimal("1000.00")
    assert (record.currency_code, record.currency_outstanding) == (None, None)

    settlement = PaymentService(firm.session).create(
        SettlementCreate(
            party_id=firm.vendor.id,
            settlement_date=PAID_ON,
            amount=Decimal("1000"),
            method=SettlementMethodEnum.CASH,
            allocations=[
                SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal("1000"))
            ],
        ),
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )
    firm.session.commit()
    assert settlement.currency_code is None
    assert firm.balance(ControlAccountPurpose.EXCHANGE_GAIN_LOSS) == 0
    assert firm.balance(ControlAccountPurpose.ACCOUNTS_PAYABLE) == 0


def test_a_foreign_currency_needs_its_rate() -> None:
    firm = _chain_firm()
    data = _bill_data(firm, number="S-NORATE", currency_code="USD")
    assert isinstance(data, PurchaseInvoiceCreate)

    with pytest.raises(ValidationError, match="exchange rate"):
        firm.bills().create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)


def test_a_new_bill_starts_in_the_suppliers_currency() -> None:
    firm = _chain_firm()
    firm.vendor.currency_code = "USD"
    firm.session.commit()
    data = _bill_data(firm, number="S-VENDOR")
    assert isinstance(data, PurchaseInvoiceCreate)

    with pytest.raises(ValidationError, match="exchange rate"):
        firm.bills().create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)
    firm.session.rollback()

    data = _bill_data(firm, number="S-VENDOR", exchange_rate="83")
    assert isinstance(data, PurchaseInvoiceCreate)
    bill = firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    assert bill.currency_code == "USD"


def test_tcs_is_refused_and_tds_is_not_deducted_on_a_foreign_bill() -> None:
    firm = _chain_firm()
    data = _bill_data(
        firm,
        number="S-TCS",
        currency_code="USD",
        exchange_rate="83",
        tcs_rate_percent="0.1",
    )
    assert isinstance(data, PurchaseInvoiceCreate)
    with pytest.raises(ValidationError, match="TCS"):
        firm.bills().create_invoice(data, firm_id=firm.firm.id, actor_id=firm.actor_id)
    firm.session.rollback()

    data = _bill_data(firm, number="S-TDS", currency_code="USD", exchange_rate="83")
    assert isinstance(data, PurchaseInvoiceCreate)
    bill = firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    with pytest.raises(ValidationError, match="TDS"):
        firm.bills().approve_invoice(
            bill.id,
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
            tds_amount=Decimal("10"),
        )


def test_rupees_are_refused_against_a_foreign_bill() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)

    with pytest.raises(ValidationError, match="is in USD"):
        PaymentService(firm.session).create(
            SettlementCreate(
                party_id=firm.vendor.id,
                settlement_date=PAID_ON,
                amount=Decimal("1000"),
                method=SettlementMethodEnum.CASH,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=bill.id, amount=Decimal("1000")
                    )
                ],
            ),
            firm_id=firm.firm.id,
            actor_id=firm.actor_id,
        )
    firm.session.rollback()

    data = _bill_data(firm, number="S-NOW", currency_code="USD", exchange_rate="83")
    assert isinstance(data, PurchaseInvoiceCreate)
    draft = firm.bills().create_invoice(
        data, firm_id=firm.firm.id, actor_id=firm.actor_id
    )
    with pytest.raises(ValidationError, match="Payments"):
        firm.bills().approve_and_pay(
            draft.id,
            PurchaseInvoicePaymentNow(method=SettlementMethodEnum.CASH),
            firm_scope=firm.firm.id,
            actor_id=firm.actor_id,
        )


def test_the_payables_report_shows_rupees_and_agrees_with_the_books() -> None:
    firm = _chain_firm()
    bill = _usd_bill(firm)
    service = PayablesReportService(firm.session)

    report = service.report(firm.firm.id, as_of=AS_OF, months=3)
    assert report.total.total == Decimal("83000.00")
    assert report.books_check.difference == Decimal("0.00")

    _pay(firm, bill, amount="400", rate="84")

    report = service.report(firm.firm.id, as_of=AS_OF, months=3)
    assert report.total.total == Decimal("49800.00")
    assert report.books_check.difference == Decimal("0.00")
