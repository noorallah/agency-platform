"""A date the server puts on a document is the firm's own day (D-CFG-25).

The second half of the class. The first pass moved the "not in the future"
checks and the report defaults; a live check the same night showed what was
left: a tax invoice the server dates itself at 01:00 in India was dated
**yesterday**, and a bill cancelled at that hour was undone the day before.

Every case freezes the clock at 19:30 UTC on the 5th -- 01:00 on the 6th in
India -- for a firm whose country is ``IN``.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils import dates
from app.customers.models import CustomerReceivableTransaction
from app.delivery_note.api.router import dispatch_and_invoice_delivery_note
from app.document_framework.schemas import DocumentNumberingRuleCreate
from app.finance.models import AccountingPeriod, JournalEntry
from app.finance.schemas import AccountingPeriodCreate
from app.finance.services import FinanceService, JournalEntryEngine, JournalLineData
from app.finance.services.opening_setup import seed_finance_setup
from app.gst_returns.models import GstReturnType
from app.inventory.models import InventoryTransaction
from app.loyalty.services.loyalty_service import LoyaltyService
from app.products.services.kits import KitAssemblyWrite, KitService
from app.purchase.services.requisitions import PurchaseRequisitionService
from app.sales_invoice.models import SalesInvoice
from app.vendors.models.vendor_rating import VendorRating
from app.vendors.services.vendor_ratings import VendorRatingService
from tests.unit.test_document_framework import _numbering_setup
from tests.unit.test_finance_module import _engine_book
from tests.unit.test_gst_dispatch_policy import _Shop as _DispatchShop
from tests.unit.test_inventory_foundation import (
    _branch_warehouse_product,
    _costed_stock,
    _profile,
)
from tests.unit.test_inventory_foundation import _firm as _stock_firm
from tests.unit.test_inventory_foundation import _session_factory as _stock_session
from tests.unit.test_kits import _session_factory as _kit_session
from tests.unit.test_kits import _Shop as _KitShop
from tests.unit.test_loyalty import _Books as _LoyaltyBooks
from tests.unit.test_loyalty import _session_factory as _loyalty_session
from tests.unit.test_purchase_chain_synthesis import _Firm as _BuyingFirm
from tests.unit.test_purchase_requisitions import _raise as _raise_requisition
from tests.unit.test_quotation_module import _session_factory as _quotation_session
from tests.unit.test_quotation_module import _Setup as _Quoting
from tests.unit.test_sales_invoice_module import (
    _firm as _invoice_firm,
)
from tests.unit.test_sales_invoice_module import (
    _invoice_from_sales_order,
)
from tests.unit.test_sales_invoice_module import (
    _session_factory as _invoice_session,
)
from tests.unit.test_tax_calendar import _firm as _filing_firm
from tests.unit.test_vendor_ratings import _scores, _supplier

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

#: 19:30 UTC on the 5th: 01:00 on the 6th in India.
ONE_IN_THE_MORNING = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)
THE_5TH = date(2026, 10, 5)
THE_6TH = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def _one_in_the_morning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the clock the business day is read from."""
    monkeypatch.setattr(dates, "utc_now", lambda: ONE_IN_THE_MORNING)


def _period_of(session: Session, firm_id: UUID, day: date) -> UUID:
    """Return the accounting period the firm's books hold ``day`` in."""
    period = session.scalar(
        select(AccountingPeriod.id).where(
            AccountingPeriod.firm_id == firm_id,
            AccountingPeriod.starts_on <= day,
            AccountingPeriod.ends_on >= day,
            AccountingPeriod.is_deleted.is_(False),
        )
    )
    assert period is not None
    return period


def test_an_invoice_the_server_dates_carries_the_firms_today() -> None:
    """Dispatch and invoice at 01:00: the tax invoice was dated yesterday."""
    shop = _DispatchShop()
    note = shop.note(quantity="3")

    bill = dispatch_and_invoice_delivery_note(
        note_id=note.id,
        scope=shop.scope(
            "SALES_APPROVE", "SALES_INVOICE_CREATE"
        ),  # type: ignore[arg-type]
        db=shop.session,
    ).data

    assert bill is not None
    assert bill.invoice_date == THE_6TH
    posted = shop.session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "sales_invoice",
            JournalEntry.source_id == bill.id,
        )
    )
    assert posted is not None
    assert posted.journal_date == THE_6TH
    assert posted.accounting_period_id == _period_of(
        shop.session, shop.firm.id, THE_6TH
    )


def test_a_bill_cancelled_after_midnight_is_undone_on_the_firms_today() -> None:
    """The mirror journal and the statement row: the 6th, not the 5th."""
    session = _invoice_session()()
    firm = _invoice_firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())

    service.cancel_invoice(
        invoice_id, firm_scope=firm.id, actor_id=uuid4(), reason="raised twice"
    )

    reversal = session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "sales_invoice",
            JournalEntry.reversal_of_id.is_not(None),
        )
    )
    assert reversal is not None
    assert reversal.journal_date == THE_6TH
    assert reversal.accounting_period_id == _period_of(session, firm.id, THE_6TH)
    credited = session.scalar(
        select(CustomerReceivableTransaction.transaction_date).where(
            CustomerReceivableTransaction.reference_id == invoice_id,
            CustomerReceivableTransaction.transaction_type == "CREDIT_NOTE",
        )
    )
    assert credited == THE_6TH


def test_a_bill_dated_ahead_is_never_undone_before_itself() -> None:
    """D-FIN-5 still holds: a bill dated the 7th is reversed on the 7th."""
    session = _invoice_session()()
    firm = _invoice_firm(session)
    service, invoice_id = _invoice_from_sales_order(session, firm_id=firm.id)
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    ahead = date(2026, 10, 7)
    bill = session.get(SalesInvoice, invoice_id)
    assert bill is not None
    bill.invoice_date = ahead
    session.commit()
    service.approve_invoice(invoice_id, firm_scope=firm.id, actor_id=uuid4())

    service.cancel_invoice(
        invoice_id, firm_scope=firm.id, actor_id=uuid4(), reason="raised twice"
    )

    reversal = session.scalar(
        select(JournalEntry).where(JournalEntry.reversal_of_id.is_not(None))
    )
    assert reversal is not None
    assert reversal.journal_date == ahead


def test_a_journal_reversed_with_no_date_lands_in_the_firms_period() -> None:
    """Reversed at 01:00 on the 1st of a month: the new month, not the old one."""
    session, firm_id, actor, book = _engine_book()
    finance = FinanceService(session)
    september, october = (
        finance.create_accounting_period(
            AccountingPeriodCreate(
                financial_year_id=book.year.id,
                period_number=number,
                code=f"P{number}",
                name=name,
                starts_on=starts,
                ends_on=ends,
            ),
            firm_id=firm_id,
            actor_id=actor,
        )
        for number, name, starts, ends in (
            (6, "September 2026", date(2026, 9, 1), date(2026, 9, 30)),
            (7, "October 2026", date(2026, 10, 1), date(2026, 10, 31)),
        )
    )
    engine = JournalEntryEngine(session)
    entry = engine.create_entry(
        firm_id=firm_id,
        journal_type_id=book.journal_type.id,
        voucher_type_id=book.voucher_type.id,
        accounting_period_id=book.period.id,
        journal_date=date(2026, 4, 10),
        reference_number="JV-NIGHT",
        description="A sale",
        lines=[
            JournalLineData(
                ledger_account_id=book.cash.id, debit_amount=Decimal("100")
            ),
            JournalLineData(
                ledger_account_id=book.sales.id, credit_amount=Decimal("100")
            ),
        ],
        actor_id=actor,
    )
    engine.post_entry(entry.id, firm_id=firm_id, actor_id=actor)

    # 19:30 UTC on 30 September is 01:00 on 1 October in India.
    dates_at = datetime(2026, 9, 30, 19, 30, tzinfo=UTC)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dates, "utc_now", lambda: dates_at)
        reversal = engine.reverse_entry(
            entry.id,
            firm_id=firm_id,
            reference_number="JV-NIGHT-REV",
            actor_id=actor,
        )

    assert reversal.journal_date == date(2026, 10, 1)
    assert reversal.accounting_period_id == october.id != september.id


def test_a_number_issued_on_the_night_of_31_march_belongs_to_the_new_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """01:00 on 1 April in India: UTC still called it the old financial year."""
    monkeypatch.setattr(
        dates, "utc_now", lambda: datetime(2027, 3, 31, 19, 30, tzinfo=UTC)
    )
    service, firm_id, type_id, actor_id = _numbering_setup()
    rule = service.create_numbering_rule(
        firm_id,
        DocumentNumberingRuleCreate(
            document_type_id=type_id,
            code="DEFAULT",
            name="Default Numbering",
            prefix="NUM",
            include_financial_year=True,
        ),
        actor_id,
    )

    assert "2027-2028" in service.preview_number(rule.id, firm_id=firm_id)
    assert "2027-2028" in service.reserve_number(
        rule.id, firm_id=firm_id, actor_id=actor_id
    )


def test_goodwill_points_are_dated_the_firms_today() -> None:
    """Points given by hand at 01:00 were earned yesterday."""
    books = _LoyaltyBooks(_loyalty_session()())

    given = LoyaltyService(books.session).adjust(
        firm_scope=books.firm.id,
        customer_id=books.customer.id,
        points=Decimal("100"),
        reason="Goodwill after a late delivery.",
        actor_id=books.actor_id,
    )

    assert given.earned_on == THE_6TH


def test_a_stock_reversal_is_dated_the_firms_today() -> None:
    """The goods went back on the 6th; the ledger said the 5th."""
    session = _stock_session()()
    firm = _stock_firm(session, "NIGHT")
    profile = _profile(session, firm.id)
    branch, warehouse, product = _branch_warehouse_product(session, firm, profile)
    actor_id = uuid4()
    service = _costed_stock(session, firm, branch, warehouse, product, actor_id)
    receipt = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_number == "GRN-WO"
        )
    )
    assert receipt is not None

    reversal = service.reverse_transaction(
        receipt.id, firm_scope=firm.id, actor_id=actor_id, reason="wrong goods"
    )

    assert reversal.transaction_date == THE_6TH


def test_an_order_raised_from_a_quotation_is_dated_the_firms_today() -> None:
    """Converted with no date typed."""
    setup = _Quoting(_quotation_session()())
    row = setup.accepted(quotation_date=THE_5TH)

    _, order = setup.service.convert_quotation(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )

    assert order.order_date == THE_6TH


def test_orders_raised_from_a_requisition_are_dated_the_firms_today() -> None:
    """One per supplier, each dated the day it was raised."""
    firm = _BuyingFirm(_stock_session()(), code="REQNT")
    firm.product.preferred_vendor_id = firm.vendor.id
    firm.session.commit()
    requisition = _raise_requisition(
        firm, [{"product_id": firm.product.id, "quantity": "10"}]
    )
    service = PurchaseRequisitionService(firm.session)
    service.submit(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]
    service.approve(requisition.id, firm_id=firm.firm.id, actor_id=firm.actor_id)  # type: ignore[attr-defined]

    orders = service.convert_to_orders(
        requisition.id,  # type: ignore[attr-defined]
        firm_id=firm.firm.id,
        actor_id=firm.actor_id,
    )

    assert [order.purchase_date for order in orders] == [THE_6TH]


def test_kits_assembled_with_no_date_move_stock_on_the_firms_today() -> None:
    """The repack's movements are dated the 6th."""
    shop = _KitShop(_kit_session()())

    KitService(shop.session).assemble(
        shop.pack.id,
        KitAssemblyWrite(
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            quantity=Decimal("3"),
        ),
        firm_id=shop.firm.id,
        actor_id=shop.actor,
    )

    moved = shop.session.scalars(
        select(InventoryTransaction.transaction_date).where(
            InventoryTransaction.product_id == shop.pack.id
        )
    ).all()
    assert moved and set(moved) == {THE_6TH}


def test_a_supplier_rating_is_dated_the_firms_today() -> None:
    """Rated at 01:00 on the 6th."""
    session, firm, vendor_id = _supplier()

    VendorRatingService(session).rate(  # type: ignore[arg-type]
        vendor_id,  # type: ignore[arg-type]
        _scores(4),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=uuid4(),
    )

    rated_on = session.scalar(select(VendorRating.rated_on))  # type: ignore[attr-defined]
    assert rated_on == THE_6TH


def test_a_return_filed_today_is_not_called_future() -> None:
    """September's GSTR-1 marked filed on the 6th at 01:00; the 7th is refused."""
    calendar, session, firm_id, actor_id = _filing_firm()

    with pytest.raises(ValidationError, match="in the future"):
        calendar.mark_filed(
            firm_id,
            return_type=GstReturnType.GSTR1,
            return_period="2026-09",
            filed_on=date(2026, 10, 7),
            actor_id=actor_id,
        )
    session.rollback()

    filed = calendar.mark_filed(
        firm_id,
        return_type=GstReturnType.GSTR1,
        return_period="2026-09",
        filed_on=THE_6TH,
        actor_id=actor_id,
    )
    assert filed.filed_on == THE_6TH
