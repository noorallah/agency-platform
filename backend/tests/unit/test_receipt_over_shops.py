"""Backlog 126 (row M8): one receipt from a parent spread over its shops' bills.

A chain pays from its head office: one cheque for the bills of several
shops. The receipt is the parent's -- one journal, one number -- and each
shop's account comes down by what the cheque cleared there, by a row of its
own that names the receipt. What is not set against a bill stays on the
parent's account until it is, and reversing the receipt puts every account
back by its own row. A shop can still pay for itself.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.customers.schemas.customer import (
    CustomerReceivableTransactionCreate,
    CustomerReceivableTransactionType,
)
from app.customers.services.customer_service import CustomerService
from app.customers.services.statement_service import CustomerStatementService
from app.finance.models import GLPosting, JournalEntry
from app.sales_invoice.models import SalesInvoice
from app.settlements.api.router import (
    _to_response,
    customer_outstanding_invoices,
)
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService, RefundService
from tests.unit import test_sales_order_module as sales
from tests.unit.test_settlements import WHEN, _Books, _session_factory

pytestmark = pytest.mark.typed_document_numbers


class _Chain(_Books):
    """The seeded customer as a parent, with three shops under it."""

    def __init__(self) -> None:
        """Seed the parent's books and add the shops."""
        super().__init__(_session_factory()())
        self.parent = self.customer
        self.shops = [self._shop(code) for code in ("S1", "S2", "S3")]
        self.session.commit()

    def _shop(self, code: str) -> Customer:
        """Add one shop under the parent."""
        row = Customer(
            firm_id=self.firm.id,
            code=code,
            customer_type="BUSINESS",
            name=f"Shop {code}",
            display_name=f"Shop {code}",
            currency_code="INR",
            status="ACTIVE",
            parent_customer_id=self.parent.id,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def bill(self, owner: Customer, number: str, total: str) -> SalesInvoice:
        """Raise one approved bill on a customer, on its account too."""
        row = SalesInvoice(
            firm_id=self.firm.id,
            customer_id=owner.id,
            branch_id=self.branch_id,
            invoice_number=number,
            invoice_date=WHEN,
            status="APPROVED",
            grand_total=Decimal(total),
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        CustomerService(self.session).post_receivable_transaction(
            owner.id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.INVOICE,
                amount=Decimal(total),
                transaction_date=WHEN,
                reference_number=number,
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def receipt(
        self, payer: Customer, amount: str, parts: list[tuple[SalesInvoice, str]]
    ) -> Settlement:
        """Record one receipt from ``payer`` set against ``parts``."""
        row = ReceiptService(self.session).create(
            SettlementCreate(
                party_id=payer.id,
                settlement_date=WHEN,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal(part))
                    for bill, part in parts
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def stands(self, customer: Customer) -> tuple[Decimal, Decimal]:
        """Return what a customer owes and holds on account."""
        self.session.refresh(customer)
        return customer.current_outstanding, customer.unapplied_advance_balance

    def ledger_agrees(self, customer: Customer) -> None:
        """Check a customer's rows sum to the balances it carries."""
        owed, held = self.session.execute(
            select(
                func.coalesce(
                    func.sum(CustomerReceivableTransaction.outstanding_delta), 0
                ),
                func.coalesce(func.sum(CustomerReceivableTransaction.advance_delta), 0),
            ).where(CustomerReceivableTransaction.customer_id == customer.id)
        ).one()
        assert (Decimal(str(owed)), Decimal(str(held))) == self.stands(customer)

    def owes(self, customer: Customer) -> dict[str, Decimal]:
        """Return what each of a customer's bills still owes, by number."""
        return {
            row.invoice_number: row.outstanding_amount
            for row in ReceiptService(self.session).outstanding_invoices(
                firm_id=self.firm.id, party_id=customer.id
            )
        }

    def allocate(self, settlement: Settlement, bill: SalesInvoice, part: str) -> None:
        """Set part of a receipt's unspread money against a bill."""
        ReceiptService(self.session).allocate(
            settlement.id,
            invoice_id=bill.id,
            amount=Decimal(part),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )

    def closing(self, customer: Customer) -> Decimal:
        """Return the closing balance of a customer's statement for the day."""
        return (
            CustomerStatementService(self.session)
            .statement(
                customer.id, firm_scope=self.firm.id, from_date=WHEN, to_date=WHEN
            )
            .closing_balance
        )


def _receivable_journals(chain: _Chain) -> int:
    """Count the firm's journals."""
    return int(
        chain.session.scalar(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.firm_id == chain.firm.id
            )
        )
        or 0
    )


def test_one_receipt_closes_bills_of_three_shops() -> None:
    """The row's own trial: three shops' bills, one receipt, each account right."""
    chain = _Chain()
    bills = [
        chain.bill(shop, f"SI-{index}", total)
        for index, (shop, total) in enumerate(
            zip(chain.shops, ("100.00", "250.00", "400.00"), strict=True), start=1
        )
    ]
    journals = _receivable_journals(chain)

    settlement = chain.receipt(
        chain.parent,
        "750.00",
        [(bills[0], "100.00"), (bills[1], "250.00"), (bills[2], "400.00")],
    )

    # One receipt, one journal, for the whole cheque.
    assert _receivable_journals(chain) == journals + 1
    posted = chain.postings(settlement)
    assert posted["1100"] == (Decimal("0.00"), Decimal("750.00"))
    assert settlement.customer_id == chain.parent.id
    assert settlement.allocated_amount == Decimal("750.00")
    assert settlement.unallocated_amount == Decimal("0.00")
    # Each shop owes nothing and holds nothing; the parent's account did not
    # move, because none of the money was for it.
    for shop in chain.shops:
        assert chain.stands(shop) == (Decimal("0.00"), Decimal("0.00"))
        assert chain.owes(shop) == {}
        assert chain.closing(shop) == Decimal("0.00")
        chain.ledger_agrees(shop)
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("0.00"))
    # Each shop's row names the receipt and who paid.
    row = chain.session.scalars(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.customer_id == chain.shops[1].id,
            CustomerReceivableTransaction.transaction_type == "RECEIPT",
        )
    ).one()
    assert row.reference_id == settlement.id
    assert row.reference_number == settlement.settlement_number
    assert row.amount == Decimal("250.00")
    assert row.remarks == "Paid by C1 Customer One."


def test_what_is_not_spread_stays_on_the_parents_account() -> None:
    """The parent's own bill and the money over are the parent's."""
    chain = _Chain()
    own = chain.bill(chain.parent, "SI-P", "300.00")
    shop_bill = chain.bill(chain.shops[0], "SI-1", "100.00")

    settlement = chain.receipt(
        chain.parent, "600.00", [(own, "300.00"), (shop_bill, "100.00")]
    )

    assert settlement.unallocated_amount == Decimal("200.00")
    # 500 was the parent's: 300 off what it owed, 200 held on account.
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("200.00"))
    assert chain.stands(chain.shops[0]) == (Decimal("0.00"), Decimal("0.00"))
    chain.ledger_agrees(chain.parent)
    chain.ledger_agrees(chain.shops[0])


def test_money_left_on_the_parent_is_spread_to_a_shop_later() -> None:
    """Mapped afterwards: the parent's advance goes, the shop's bill closes."""
    chain = _Chain()
    settlement = chain.receipt(chain.parent, "500.00", [])
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("500.00"))
    bill = chain.bill(chain.shops[2], "SI-3", "180.00")
    journals = _receivable_journals(chain)

    chain.allocate(settlement, bill, "180.00")

    chain.session.refresh(settlement)
    assert settlement.allocated_amount == Decimal("180.00")
    assert settlement.unallocated_amount == Decimal("320.00")
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("320.00"))
    assert chain.stands(chain.shops[2]) == (Decimal("0.00"), Decimal("0.00"))
    assert chain.owes(chain.shops[2]) == {}
    # Applying money already received posts nothing.
    assert _receivable_journals(chain) == journals
    moved = chain.session.scalars(
        select(CustomerReceivableTransaction).where(
            CustomerReceivableTransaction.transaction_type == "RECEIPT_TRANSFER"
        )
    ).one()
    assert moved.customer_id == chain.parent.id
    assert (moved.outstanding_delta, moved.advance_delta) == (
        Decimal("0.00"),
        Decimal("-180.00"),
    )
    assert moved.remarks == "Moved to S3 Shop S3 for SI-3."
    chain.ledger_agrees(chain.parent)
    chain.ledger_agrees(chain.shops[2])


def test_money_that_came_off_the_parents_balance_goes_back_on_it() -> None:
    """Spread to a shop, the parent owes again what that money had covered."""
    chain = _Chain()
    own = chain.bill(chain.parent, "SI-P", "300.00")
    # 500 on account while 300 is owed: 300 off the balance, 200 held.
    settlement = chain.receipt(chain.parent, "500.00", [])
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("200.00"))
    bill = chain.bill(chain.shops[0], "SI-1", "400.00")

    chain.allocate(settlement, bill, "400.00")

    # The advance went first; the other 200 is owed by the parent again.
    assert chain.stands(chain.parent) == (Decimal("200.00"), Decimal("0.00"))
    assert chain.stands(chain.shops[0]) == (Decimal("0.00"), Decimal("0.00"))
    assert chain.closing(chain.parent) == Decimal("200.00")
    chain.ledger_agrees(chain.parent)
    # The 100 left covers 100 of the parent's own bill without touching an
    # advance that is no longer there.
    chain.allocate(settlement, own, "100.00")
    chain.session.refresh(settlement)
    assert settlement.unallocated_amount == Decimal("0.00")
    assert chain.stands(chain.parent) == (Decimal("200.00"), Decimal("0.00"))
    assert chain.owes(chain.parent) == {"SI-P": Decimal("200.00")}
    chain.ledger_agrees(chain.parent)


def test_reversing_the_receipt_puts_every_account_back() -> None:
    """A bounced cheque: the shops owe again, the parent holds nothing."""
    chain = _Chain()
    first = chain.bill(chain.shops[0], "SI-1", "100.00")
    second = chain.bill(chain.shops[1], "SI-2", "250.00")
    settlement = chain.receipt(chain.parent, "500.00", [(first, "100.00")])
    chain.allocate(settlement, second, "250.00")
    chain.session.commit()
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("150.00"))

    ReceiptService(chain.session).reverse(
        settlement.id,
        firm_id=chain.firm.id,
        actor_id=chain.actor_id,
        reason="Cheque bounced",
    )
    chain.session.commit()

    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("0.00"))
    assert chain.stands(chain.shops[0]) == (Decimal("100.00"), Decimal("0.00"))
    assert chain.stands(chain.shops[1]) == (Decimal("250.00"), Decimal("0.00"))
    assert chain.owes(chain.shops[0]) == {"SI-1": Decimal("100.00")}
    assert chain.owes(chain.shops[1]) == {"SI-2": Decimal("250.00")}
    for customer in (chain.parent, *chain.shops):
        chain.ledger_agrees(customer)
    # Receivables in the ledger are back where the two bills left them --
    # nothing: these fixtures raise bills without a journal.
    net = chain.session.execute(
        select(
            func.coalesce(func.sum(GLPosting.debit_amount), 0),
            func.coalesce(func.sum(GLPosting.credit_amount), 0),
        ).where(
            GLPosting.ledger_account_id.in_(
                select(GLPosting.ledger_account_id).where(
                    GLPosting.journal_entry_id == settlement.journal_entry_id
                )
            )
        )
    ).one()
    assert net[0] == net[1]


def test_a_shop_still_pays_for_itself() -> None:
    """Answer A10: both. A shop's own receipt is a receipt like any other."""
    chain = _Chain()
    bill = chain.bill(chain.shops[0], "SI-1", "100.00")

    settlement = chain.receipt(chain.shops[0], "100.00", [(bill, "100.00")])

    assert settlement.customer_id == chain.shops[0].id
    assert chain.stands(chain.shops[0]) == (Decimal("0.00"), Decimal("0.00"))
    assert chain.stands(chain.parent) == (Decimal("0.00"), Decimal("0.00"))


def test_a_shop_cannot_pay_for_a_sibling_or_for_its_parent() -> None:
    """Only the parent's money reaches across the family."""
    chain = _Chain()
    sibling = chain.bill(chain.shops[1], "SI-2", "100.00")
    parents = chain.bill(chain.parent, "SI-P", "100.00")

    for bill in (sibling, parents):
        with pytest.raises(ValidationError, match="does not belong to this party"):
            chain.receipt(chain.shops[0], "100.00", [(bill, "100.00")])
        chain.session.rollback()
    on_account = chain.receipt(chain.shops[0], "100.00", [])
    with pytest.raises(ValidationError, match="does not belong to this customer"):
        chain.allocate(on_account, sibling, "100.00")


def test_a_stranger_is_still_refused() -> None:
    """A customer outside the family is not the parent's to pay for."""
    chain = _Chain()
    stranger = Customer(
        firm_id=chain.firm.id,
        code="X1",
        customer_type="BUSINESS",
        name="Stranger",
        display_name="Stranger",
        currency_code="INR",
        status="ACTIVE",
        created_by=chain.actor_id,
        updated_by=chain.actor_id,
    )
    chain.session.add(stranger)
    chain.session.commit()
    bill = chain.bill(stranger, "SI-X", "100.00")

    with pytest.raises(ValidationError, match="does not belong to this party"):
        chain.receipt(chain.parent, "100.00", [(bill, "100.00")])


def test_a_shops_bill_cannot_be_overpaid_and_nothing_is_written() -> None:
    """More than the bill owes is refused whole."""
    chain = _Chain()
    bill = chain.bill(chain.shops[0], "SI-1", "100.00")
    before = chain.session.scalar(select(func.count(Settlement.id)))

    with pytest.raises(ValidationError, match="SI-1 has 100.00 outstanding"):
        chain.receipt(chain.parent, "500.00", [(bill, "100.01")])
    chain.session.rollback()

    assert chain.session.scalar(select(func.count(Settlement.id))) == before
    assert chain.stands(chain.shops[0]) == (Decimal("100.00"), Decimal("0.00"))


def test_an_advance_refunded_since_cannot_be_moved_to_a_shop() -> None:
    """Money the parent no longer holds is not spread."""
    chain = _Chain()
    settlement = chain.receipt(chain.parent, "500.00", [])
    RefundService(chain.session).create(
        SettlementCreate(
            party_id=chain.parent.id,
            settlement_date=WHEN,
            amount=Decimal("400.00"),
            method=SettlementMethodEnum.BANK,
        ),
        firm_id=chain.firm.id,
        actor_id=chain.actor_id,
    )
    chain.session.commit()
    bill = chain.bill(chain.shops[0], "SI-1", "300.00")

    with pytest.raises(ValidationError, match="holds only 100.00 on account"):
        chain.allocate(settlement, bill, "300.00")
    chain.session.rollback()

    assert chain.stands(chain.shops[0]) == (Decimal("300.00"), Decimal("0.00"))


def test_a_transfer_row_cannot_be_posted_by_hand() -> None:
    """The type is the receipt service's own."""
    chain = _Chain()

    with pytest.raises(ValidationError, match="Unsupported"):
        CustomerService(chain.session).post_receivable_transaction(
            chain.parent.id,
            CustomerReceivableTransactionCreate(
                transaction_type=CustomerReceivableTransactionType.RECEIPT_TRANSFER,
                amount=Decimal("10.00"),
                transaction_date=WHEN,
            ),
            firm_scope=chain.firm.id,
            actor_id=chain.actor_id,
        )


def _view(chain: _Chain) -> object:
    """Return a scope that may read receipts."""
    return sales.ResolvedFirmScope(
        principal=sales._principal(chain.actor_id, {"RECEIPT_VIEW"}),
        firm_id=chain.firm.id,
    )


def test_the_bills_a_parents_receipt_may_clear_name_their_shop() -> None:
    """The list for a parent holds its shops' bills, each saying whose."""
    chain = _Chain()
    chain.bill(chain.parent, "SI-P", "300.00")
    chain.bill(chain.shops[1], "SI-2", "250.00")
    chain.bill(chain.shops[0], "SI-1", "100.00")

    family = customer_outstanding_invoices(
        chain.parent.id, _view(chain), True, chain.session  # type: ignore[arg-type]
    ).data
    alone = customer_outstanding_invoices(
        chain.parent.id, _view(chain), False, chain.session  # type: ignore[arg-type]
    ).data
    shop = customer_outstanding_invoices(
        chain.shops[0].id, _view(chain), True, chain.session  # type: ignore[arg-type]
    ).data

    assert [(row.invoice_number, row.party_code) for row in family] == [
        ("SI-P", "C1"),
        ("SI-1", "S1"),
        ("SI-2", "S2"),
    ]
    assert family[1].party_id == chain.shops[0].id
    assert family[1].party_name == "Shop S1"
    assert [(row.invoice_number, row.party_code) for row in alone] == [("SI-P", None)]
    # A shop sees its own bills and nobody else's.
    assert [(row.invoice_number, row.party_code) for row in shop] == [("SI-1", "S1")]


def test_a_receipts_answer_says_which_shop_each_bill_is() -> None:
    """A shop's bill is named on the allocation; the parent's own is not."""
    chain = _Chain()
    own = chain.bill(chain.parent, "SI-P", "300.00")
    shop_bill = chain.bill(chain.shops[0], "SI-1", "100.00")
    settlement = chain.receipt(
        chain.parent, "400.00", [(own, "300.00"), (shop_bill, "100.00")]
    )

    answer = _to_response(ReceiptService(chain.session), settlement)

    named = {
        row.invoice_number: (row.party_id, row.party_code) for row in answer.allocations
    }
    assert named == {
        "SI-P": (None, None),
        "SI-1": (chain.shops[0].id, "S1"),
    }
    assert answer.party_code == "C1"


def test_a_payment_never_reaches_across_a_family() -> None:
    """Shops are a customer's; a supplier's payment asks nothing about them."""
    chain = _Chain()

    assert (
        PaymentService(chain.session).shop_ids(
            firm_id=chain.firm.id, party_id=chain.vendor.id
        )
        == []
    )
