"""Row P5 (COL-12): one customer pays another customer's bill.

Two independent shops, no parent between them. The receipt is the payer's --
one journal, one number -- and names the customer it pays for. The bill is
closed; the bill's customer's account reads *Paid by* the payer and the
payer's account reads *Paid for* that customer, and the payer ends where it
stood. Money a customer already holds on account clears another customer's
bill the same way, with no journal, and reversing the receipt puts both
accounts back.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerReceivableTransaction
from app.settlements.api.router import _to_response
from app.settlements.models import Settlement
from app.settlements.schemas import (
    SettlementAllocateRequest,
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService, ReceiptService
from app.settlements.services.receipt_print import ReceiptPrintService
from tests.unit.test_invoice_print import _text_of
from tests.unit.test_receipt_over_shops import _Chain, _receivable_journals
from tests.unit.test_settlements import WHEN

pytestmark = pytest.mark.typed_document_numbers

ZERO = Decimal("0.00")


class _Shops(_Chain):
    """The seeded books with two shops that have nothing to do with each other."""

    def __init__(self) -> None:
        """Seed the books and add shop A and shop B, neither under anybody."""
        super().__init__()
        self.a = self._independent("A1", "Shop A")
        self.b = self._independent("B1", "Shop B")
        self.session.commit()

    def _independent(self, code: str, name: str) -> Customer:
        """Add one customer with no parent."""
        row = Customer(
            firm_id=self.firm.id,
            code=code,
            customer_type="BUSINESS",
            name=name,
            display_name=name,
            currency_code="INR",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def pays_for(
        self,
        payer: Customer,
        other: Customer | None,
        amount: str,
        parts: list[tuple[object, str]],
    ) -> Settlement:
        """Record a receipt from ``payer`` naming ``other`` as paid for."""
        row = ReceiptService(self.session).create(
            SettlementCreate(
                party_id=payer.id,
                paid_for_customer_id=None if other is None else other.id,
                settlement_date=WHEN,
                amount=Decimal(amount),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(
                        invoice_id=bill.id,  # type: ignore[attr-defined]
                        amount=Decimal(part),
                    )
                    for bill, part in parts
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )
        self.session.commit()
        return row

    def rows(
        self, customer: Customer, kind: str
    ) -> list[CustomerReceivableTransaction]:
        """Return a customer's rows of one kind."""
        return list(
            self.session.scalars(
                select(CustomerReceivableTransaction).where(
                    CustomerReceivableTransaction.customer_id == customer.id,
                    CustomerReceivableTransaction.transaction_type == kind,
                )
            )
        )


def test_shop_a_pays_shop_bs_bill_and_both_accounts_say_so() -> None:
    """The row's own trial: 5,000 from A for B's bill."""
    shops = _Shops()
    bill = shops.bill(shops.b, "SI-B", "5000.00")
    journals = _receivable_journals(shops)

    settlement = shops.pays_for(shops.a, shops.b, "5000.00", [(bill, "5000.00")])

    # One receipt, A's, one journal for the money.
    assert _receivable_journals(shops) == journals + 1
    assert settlement.customer_id == shops.a.id
    assert settlement.allocated_amount == Decimal("5000.00")
    assert settlement.unallocated_amount == ZERO
    # The bill is paid; B owes nothing; A stands where it stood.
    assert shops.owes(shops.b) == {}
    assert shops.stands(shops.b) == (ZERO, ZERO)
    assert shops.stands(shops.a) == (ZERO, ZERO)
    assert shops.closing(shops.b) == ZERO
    assert shops.closing(shops.a) == ZERO
    shops.ledger_agrees(shops.a)
    shops.ledger_agrees(shops.b)
    # B's account says who paid; A's says whom it paid for.
    (taken,) = shops.rows(shops.b, "RECEIPT")
    assert taken.reference_id == settlement.id
    assert taken.remarks == "Paid by A1 Shop A, applied to SI-B."
    (given,) = shops.rows(shops.a, "RECEIPT_TRANSFER")
    assert given.reference_id == settlement.id
    assert given.amount == Decimal("5000.00")
    assert given.remarks == "Paid for B1 Shop B: SI-B."
    # The receipt's page says whose bill it cleared.
    response = _to_response(ReceiptService(shops.session), settlement)
    assert response.party_code == "A1"
    assert [(item.party_code, item.party_name) for item in response.allocations] == [
        ("B1", "Shop B")
    ]


def test_reversing_the_receipt_restores_both_accounts() -> None:
    """Taken back, B owes its bill again and A is untouched."""
    shops = _Shops()
    own = shops.bill(shops.a, "SI-A", "300.00")
    bill = shops.bill(shops.b, "SI-B", "5000.00")
    settlement = shops.pays_for(shops.a, shops.b, "5000.00", [(bill, "5000.00")])
    # A still owes its own bill: the money was not for it.
    assert shops.stands(shops.a) == (Decimal("300.00"), ZERO)
    assert shops.owes(shops.a) == {"SI-A": Decimal("300.00")}

    ReceiptService(shops.session).reverse(
        settlement.id, firm_id=shops.firm.id, actor_id=shops.actor_id, reason="Bounced"
    )
    shops.session.commit()

    assert shops.stands(shops.b) == (Decimal("5000.00"), ZERO)
    assert shops.owes(shops.b) == {"SI-B": Decimal("5000.00")}
    assert shops.stands(shops.a) == (Decimal("300.00"), ZERO)
    shops.ledger_agrees(shops.a)
    shops.ledger_agrees(shops.b)
    assert own.id is not None


def test_one_receipt_pays_the_payers_own_bill_and_anothers() -> None:
    """Part for A's own bill, part for B's, and the rest held by A."""
    shops = _Shops()
    own = shops.bill(shops.a, "SI-A", "300.00")
    first = shops.bill(shops.b, "SI-B1", "400.00")
    second = shops.bill(shops.b, "SI-B2", "250.00")

    settlement = shops.pays_for(
        shops.a,
        shops.b,
        "1000.00",
        [(own, "300.00"), (first, "400.00"), (second, "250.00")],
    )

    assert settlement.unallocated_amount == Decimal("50.00")
    assert shops.stands(shops.a) == (ZERO, Decimal("50.00"))
    assert shops.stands(shops.b) == (ZERO, ZERO)
    assert shops.owes(shops.a) == {}
    assert shops.owes(shops.b) == {}
    (given,) = shops.rows(shops.a, "RECEIPT_TRANSFER")
    assert given.amount == Decimal("650.00")
    assert given.remarks == "Paid for B1 Shop B: SI-B1, SI-B2."
    shops.ledger_agrees(shops.a)
    shops.ledger_agrees(shops.b)

    ReceiptService(shops.session).reverse(
        settlement.id, firm_id=shops.firm.id, actor_id=shops.actor_id
    )
    shops.session.commit()
    assert shops.stands(shops.a) == (Decimal("300.00"), ZERO)
    assert shops.stands(shops.b) == (Decimal("650.00"), ZERO)
    shops.ledger_agrees(shops.a)
    shops.ledger_agrees(shops.b)


def test_money_held_on_account_clears_another_customers_bill() -> None:
    """The row's second trial: A's advance of 10,000 clears a bill of B."""
    shops = _Shops()
    advance = shops.pays_for(shops.a, None, "10000.00", [])
    assert shops.stands(shops.a) == (ZERO, Decimal("10000.00"))
    bill = shops.bill(shops.b, "SI-B", "10000.00")
    journals = _receivable_journals(shops)

    ReceiptService(shops.session).allocate(
        advance.id,
        invoice_id=bill.id,
        amount=Decimal("10000.00"),
        firm_id=shops.firm.id,
        actor_id=shops.actor_id,
        paid_for_customer_id=shops.b.id,
    )

    # No journal typed and none posted: the money arrived once.
    assert _receivable_journals(shops) == journals
    assert shops.stands(shops.a) == (ZERO, ZERO)
    assert shops.stands(shops.b) == (ZERO, ZERO)
    assert shops.owes(shops.b) == {}
    (given,) = shops.rows(shops.a, "RECEIPT_TRANSFER")
    assert given.remarks == "Paid for B1 Shop B: SI-B."
    (taken,) = shops.rows(shops.b, "RECEIPT")
    assert taken.remarks == "Paid by A1 Shop A, applied to SI-B."
    shops.ledger_agrees(shops.a)
    shops.ledger_agrees(shops.b)

    ReceiptService(shops.session).reverse(
        advance.id, firm_id=shops.firm.id, actor_id=shops.actor_id
    )
    shops.session.commit()
    assert shops.stands(shops.a) == (ZERO, ZERO)
    assert shops.stands(shops.b) == (Decimal("10000.00"), ZERO)


def test_another_customers_bill_is_refused_unless_it_is_named() -> None:
    """A bill's id alone never lets one customer's money reach a stranger's."""
    shops = _Shops()
    bill = shops.bill(shops.b, "SI-B", "500.00")

    with pytest.raises(ValidationError, match="does not belong"):
        shops.pays_for(shops.a, None, "500.00", [(bill, "500.00")])
    shops.session.rollback()

    advance = shops.pays_for(shops.a, None, "500.00", [])
    with pytest.raises(ValidationError, match="does not belong"):
        ReceiptService(shops.session).allocate(
            advance.id,
            invoice_id=bill.id,
            amount=Decimal("500.00"),
            firm_id=shops.firm.id,
            actor_id=shops.actor_id,
        )
    shops.session.rollback()
    # Naming a third customer does not open B's bill either.
    with pytest.raises(ValidationError, match="does not belong"):
        shops.pays_for(shops.a, shops.shops[0], "500.00", [(bill, "500.00")])
    shops.session.rollback()
    assert shops.owes(shops.b) == {"SI-B": Decimal("500.00")}


def test_more_than_the_bill_owes_is_refused() -> None:
    """The other customer's bill takes no more than it owes."""
    shops = _Shops()
    bill = shops.bill(shops.b, "SI-B", "500.00")

    with pytest.raises(ValidationError, match="500.00 outstanding"):
        shops.pays_for(shops.a, shops.b, "600.00", [(bill, "600.00")])


def test_only_a_receipt_names_a_customer_paid_for() -> None:
    """A payment to a supplier and its allocation refuse the field by name."""
    shops = _Shops()
    with pytest.raises(ValidationError, match="Only a receipt"):
        PaymentService(shops.session).create(
            SettlementCreate(
                party_id=shops.vendor.id,
                paid_for_customer_id=shops.b.id,
                settlement_date=WHEN,
                amount=Decimal("10.00"),
                method=SettlementMethodEnum.BANK,
            ),
            firm_id=shops.firm.id,
            actor_id=shops.actor_id,
        )
    assert (
        SettlementAllocateRequest.model_validate(
            {
                "invoice_id": str(shops.b.id),
                "amount": "1.00",
                "paid_for_customer_id": str(shops.b.id),
            }
        ).paid_for_customer_id
        == shops.b.id
    )


def test_a_shop_can_pay_for_a_sibling_when_it_names_it() -> None:
    """Backlog 126 refused it by the bill's id; named, it is the same act."""
    shops = _Shops()
    bill = shops.bill(shops.shops[1], "SI-2", "120.00")

    shops.pays_for(shops.shops[0], shops.shops[1], "120.00", [(bill, "120.00")])

    assert shops.owes(shops.shops[1]) == {}
    assert shops.stands(shops.shops[0]) == (ZERO, ZERO)
    (given,) = shops.rows(shops.shops[0], "RECEIPT_TRANSFER")
    assert given.remarks == "Paid for S2 Shop S2: SI-2."


def test_a_parent_naming_its_own_shop_is_still_a_parents_receipt() -> None:
    """Naming a shop under the payer changes nothing about backlog 126."""
    shops = _Shops()
    bill = shops.bill(shops.shops[0], "SI-1", "100.00")

    shops.pays_for(shops.parent, shops.shops[0], "100.00", [(bill, "100.00")])

    assert shops.rows(shops.parent, "RECEIPT_TRANSFER") == []
    (taken,) = shops.rows(shops.shops[0], "RECEIPT")
    assert taken.remarks == "Paid by C1 Customer One."


def test_the_printed_receipt_says_whom_it_was_paid_for() -> None:
    """Received from the payer, paid for the bill's customer."""
    shops = _Shops()
    bill = shops.bill(shops.b, "SI-B", "5000.00")
    settlement = shops.pays_for(shops.a, shops.b, "5000.00", [(bill, "5000.00")])

    pdf, _ = ReceiptPrintService(shops.session).render(
        settlement.id, firm_scope=shops.firm.id
    )
    text = _text_of(pdf)
    assert "Received from | Shop A" in text
    assert "Paid for | Shop B" in text

    own = shops.bill(shops.a, "SI-A", "10.00")
    plain = shops.pays_for(shops.a, None, "10.00", [(own, "10.00")])
    pdf, _ = ReceiptPrintService(shops.session).render(
        plain.id, firm_scope=shops.firm.id
    )
    assert "Paid for" not in _text_of(pdf)
