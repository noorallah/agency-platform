"""A bill straight off an order takes what is typed on its lines.

D-PRC-46, from the third pricing check ("Gaps noticed"): with the
delivery-note stage off, a discount typed on the line of a bill raised
straight off an order was accepted and ignored -- the bill saved at the
order's 1,180.00 and was approved. The bill raises its own note there, and
its lines were rebuilt from that note alone.

A bill of a note a person typed takes such a figure: it replaces what the
line inherits (a zero included, since #1237) and the bill's approver is
judged for it. A bill that raises its own note is the same bill, so it now
does the same, and each case here is checked against its twin on a firm
that types its notes.

Section D item 3 of the same check is here too: a counter bill whose bill
discount was typed answered ``bill_discount_source: inherited``.

Every case runs on a request-shaped session (autoflush off).
"""

from decimal import Decimal
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from tests.unit.test_order_bill_discount_reaches_the_bill import DAY, _Trade

D = Decimal


class _Firm(_Trade):
    """A firm selling 10 at 100.00 plus 18%: an order of 1,180.00."""

    def __init__(self, *, notes: bool) -> None:
        """Approve the check's order; ``notes`` says who raises the note."""
        super().__init__(notes=notes)
        self.types_notes = notes
        self.sale = self.order("10", unit_price="100")
        assert self.sale.grand_total == D("1180.0000")

    def billed(self, *, by: UUID | None = None, **line: object) -> SalesInvoice:
        """Bill the whole order with what the bill line types; a draft.

        Off the order where the firm types no notes, off the note it typed
        where it does: the same request either way.
        """
        if self.types_notes:
            note = self.note(self.sale, "10")
            source: dict[str, object] = {
                "source_document_type": "DELIVERY_NOTE",
                "source_document_id": note.id,
                "source_document_line_id": self.note_line(note).id,
            }
        else:
            source = {
                "source_document_type": "SALES_ORDER",
                "source_document_id": self.sale.id,
                "source_document_line_id": self.order_line(self.sale).id,
            }
        row = self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        SalesInvoiceLineWrite.model_validate(
                            source
                            | {"line_number": 1, "current_invoice_quantity": "10"}
                            | line
                        )
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=by or self.actor,
        )
        self.session.expire_all()
        return self.bills.get_invoice(row.id, firm_scope=self.firm_id)

    def read(self, bill: SalesInvoice) -> tuple[Decimal, Decimal, Decimal, str | None]:
        """Return the bill line's price and discount, the total and the source."""
        line = self.bill_line(bill)
        return (
            line.unit_price,
            line.discount_amount,
            bill.grand_total,
            line.discount_source,
        )


TYPED = [
    ({"discount_percent": "10"}, "100.0000", "1062.0000"),
    ({"discount_amount": "100"}, "100.0000", "1062.0000"),
    ({"discount_percent": "0"}, "0.0000", "1180.0000"),
    ({}, "0.0000", "1180.0000"),
]


@pytest.mark.parametrize(("line", "off", "total"), TYPED)
def test_a_discount_typed_on_a_bill_of_an_order_takes_effect(
    line: dict[str, str], off: str, total: str
) -> None:
    """The check's bill: 10% typed is 1,062.00, not the order's 1,180.00."""
    firm = _Firm(notes=False)

    bill = firm.billed(**line)

    assert (firm.bill_line(bill).discount_amount, bill.grand_total) == (
        D(off),
        D(total),
    )


@pytest.mark.parametrize(
    "line",
    [
        {"discount_percent": "10"},
        {"discount_amount": "100"},
        {"discount_percent": "0"},
        {"unit_price": "90"},
        {"unit_price": "90", "discount_percent": "5"},
        {},
    ],
)
def test_a_bill_of_an_order_reads_as_the_bill_of_a_note_would(
    line: dict[str, str],
) -> None:
    """One request, two firms: the bill is the same whoever raised the note."""
    off_the_order = _Firm(notes=False)
    off_the_note = _Firm(notes=True)

    assert off_the_order.read(off_the_order.billed(**line)) == off_the_note.read(
        off_the_note.billed(**line)
    )


def test_a_zero_typed_on_the_bill_refuses_the_orders_own_discount() -> None:
    """The order gave 10%; the bill line says 0 and charges the full 1,180.00."""
    firm = _Trade(notes=False)
    order = firm.order("10", unit_price="100", discount_percent="10")
    assert order.grand_total == D("1062.0000")

    def bill(**line: object) -> SalesInvoice:
        """Bill the order straight off it."""
        row = firm.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": firm.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        SalesInvoiceLineWrite.model_validate(
                            {
                                "source_document_type": "SALES_ORDER",
                                "source_document_id": order.id,
                                "source_document_line_id": firm.order_line(order).id,
                                "line_number": 1,
                                "current_invoice_quantity": "5",
                            }
                            | line
                        )
                    ],
                }
            ),
            firm_id=firm.firm_id,
            actor_id=firm.actor,
        )
        firm.session.expire_all()
        return firm.bills.get_invoice(row.id, firm_scope=firm.firm_id)

    # Silent, half the order is half its deal; a typed zero charges it whole.
    assert bill().grand_total == D("531.0000")
    assert bill(discount_percent="0").grand_total == D("590.0000")


@pytest.mark.parametrize("notes", [False, True])
def test_the_typed_discount_is_judged_against_the_bills_approver(notes: bool) -> None:
    """10% typed by somebody limited to 5% is refused at the bill's approval."""
    firm = _Firm(notes=notes)
    manager = firm.person("SALES_MANAGER", "5")
    bill = firm.billed(discount_percent="10")

    with pytest.raises(ValidationError) as refused:
        firm.bills.approve_invoice(bill.id, firm_scope=firm.firm_id, actor_id=manager)
    firm.session.rollback()

    assert str(refused.value.message) == (
        "Line 1 carries a discount of 10.00%, above your limit of 5.00%. It "
        "needs approval by someone allowed at least 10.00%."
    )
    # Within the limit, and with nothing typed, the same person approves.
    firm.bills.cancel_invoice(
        bill.id, firm_scope=firm.firm_id, actor_id=firm.actor, reason="Typed wrong"
    )
    firm.session.expire_all()
    within = firm.billed(discount_percent="5") if not notes else None
    if within is not None:
        approved = firm.bills.approve_invoice(
            within.id, firm_scope=firm.firm_id, actor_id=manager
        )
        assert approved.status == "APPROVED"


# ---- section D item 3 ------------------------------------------------------


def test_a_counter_bill_with_a_typed_bill_discount_says_typed() -> None:
    """100.00 typed on a counter bill reads typed; the row is as it was."""
    trade = _Trade(counter=True)

    draft = trade.counter_bill("10", bill_discount_amount="100")

    answer = trade.bills.invoice_response(draft)
    assert (answer.bill_discount_source, answer.bill_discount_typed_as) == (
        "typed",
        "amount",
    )
    assert answer.bill_discount_amount == D("100.0000")
    # What the rules read is untouched: it is the order's share, inherited.
    assert draft.bill_discount_source == "inherited"
    assert trade.own_order(draft).bill_discount_source == "typed"
    percent = trade.counter_bill("10", bill_discount_percent="10")
    answer = trade.bills.invoice_response(percent)
    assert (answer.bill_discount_source, answer.bill_discount_typed_as) == (
        "typed",
        "percent",
    )


def test_a_counter_bill_whose_discount_an_offer_gave_still_says_inherited() -> None:
    """An offer's 200 is nobody's hand, on the response as in the rules."""
    trade = _Trade(counter=True)
    trade.offers()

    draft = trade.counter_bill("60")

    answer = trade.bills.invoice_response(draft)
    assert (answer.bill_discount_source, answer.bill_discount_typed_as) == (
        "inherited",
        None,
    )
    assert answer.bill_discount_amount == D("200.0000")


def test_a_typed_counter_bill_is_still_judged_against_the_approver() -> None:
    """What is judged did not move: 100.00 off 840.00 is over a 5% limit."""
    trade = _Trade(counter=True)
    manager = trade.person("SALES_MANAGER", "5")
    draft = trade.counter_bill("10", bill_discount_amount="100")

    with pytest.raises(ValidationError, match="above your limit of 5.00%"):
        trade.bills.approve_invoice(
            draft.id, firm_scope=trade.firm_id, actor_id=manager
        )
