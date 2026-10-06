"""An order's bill discount and free goods reach the note and the bill.

D-PRC-1: an order approved at 5,265.16 -- a 7.5% line offer and an offer of
200 off the bill -- was delivered and billed at 5,501.16, because the delivery
note read only a bill discount typed on itself and the bill inherited the
note. A typed 100 off and a typed 10% were lost the same way; freight was
carried. Each downstream line now takes its source line's share of the
discount by the quantity it continues, so part deliveries and part bills sum
back to the order's figure exactly, and the tax and the journal follow.

D-PRC-4: an order of 12 with 1 free shipped 12 unless the note stated the free
unit again, because the note line's ``free_quantity`` defaulted to zero.
Silence now takes the order line's free goods in whole units.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils.pricing import continued_free_goods, continued_share
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.identity.models import Role, User, UserRole
from app.promotions.models import PromotionRedemption
from app.promotions.schemas import PromotionActionType
from app.sales_invoice.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceLineTax,
)
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services.discount_limit import DiscountLimitService
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services.sales_return_service import SalesReturnService
from app.tax.services.gst_template import apply_india_gst_template
from tests.unit.test_promotions import _promotion
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

D = Decimal
DAY = date(2026, 8, 4)
PRICE = D("84")


class _Trade:
    """A Tamil Nadu firm selling one product at 84.00 plus 18% to a local buyer."""

    def __init__(self, *, counter: bool = False, notes: bool = True) -> None:
        """Build the firm on the GST template.

        ``counter`` types only the bill; ``notes`` off types the order and
        the bill, and the bill raises the delivery note itself.
        """
        self.session: Session = _request_session()
        self.setup = _Firm(self.session)
        if counter:
            self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        elif not notes:
            self.setup.stages(quotation=False, sales_order=True, delivery_note=False)
        self.actor = uuid4()
        self.setup.firm.gst_number = "33AABCU9603R1ZM"
        self.setup.customer.gst_number = "33AAACR5055K1Z5"
        self.session.commit()
        apply_india_gst_template(
            self.session, firm_id=self.setup.firm.id, actor_id=self.actor
        )
        self.setup.product.tax_profile_group_code = "GST_18_LOCAL"
        self.setup.product.hsn_sac = "34022010"
        self.session.commit()
        self.orders = SalesOrderService(self.session)
        self.notes = DeliveryNoteService(self.session)
        self.bills = SalesInvoiceService(self.session)

    @property
    def firm_id(self) -> UUID:
        """Return the firm."""
        return self.setup.firm.id

    def offers(self) -> None:
        """Publish 7.5% off the line and 200 off the bill, as the check ran."""
        _promotion(
            self.session,
            firm_id=self.firm_id,
            code="BULK5",
            priority=10,
            actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "7.5"})],
        )
        _promotion(
            self.session,
            firm_id=self.firm_id,
            code="BIGORDER",
            priority=20,
            actions=[(PromotionActionType.BILL_DISCOUNT_AMOUNT, {"amount": "200"})],
        )
        self.session.commit()

    def order(self, quantity: str, **fields: object) -> SalesOrder:
        """Raise and approve an order of the product at 84.00.

        ``unit_price``, ``discount_percent`` and ``discount_amount`` are the
        line's; anything else named is the order's own.
        """
        free = fields.pop("free_quantity", None)
        price = D(str(fields.pop("unit_price", PRICE)))
        typed = {
            name: D(str(fields.pop(name)))
            for name in ("discount_percent", "discount_amount")
            if name in fields
        }
        row = self.orders.create_order(
            SalesOrderCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "branch_id": self.setup.branch.id,
                    "warehouse_id": self.setup.warehouse.id,
                    "order_date": DAY,
                    "lines": [
                        SalesOrderLineWrite(
                            line_number=1,
                            product_id=self.setup.product.id,
                            quantity=D(quantity),
                            unit_price=price,
                            free_quantity=None if free is None else D(str(free)),
                            **typed,
                        )
                    ],
                }
                | fields
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        return self.orders.approve_order(
            row.id, firm_scope=self.firm_id, actor_id=self.actor
        )

    def order_line(self, order: SalesOrder) -> SalesOrderLine:
        """Return the order's one line."""
        line = self.session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert line is not None
        return line

    def note(
        self, order: SalesOrder, quantity: str, *, ship: bool = True, **fields: object
    ) -> DeliveryNote:
        """Raise, approve and dispatch a note that names only what it ships."""
        line_fields = {
            name: fields.pop(name) for name in ("free_quantity",) if name in fields
        }
        row = self.notes.create_note(
            DeliveryNoteCreate.model_validate(
                {
                    "sales_order_id": order.id,
                    "delivery_date": DAY,
                    "lines": [
                        DeliveryNoteLineWrite.model_validate(
                            {
                                "sales_order_line_id": self.order_line(order).id,
                                "line_number": 1,
                                "current_delivery_quantity": D(quantity),
                            }
                            | line_fields
                        )
                    ],
                }
                | fields
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        if ship:
            self.notes.approve_note(
                row.id, firm_scope=self.firm_id, actor_id=self.actor
            )
            self.notes.dispatch_note(
                row.id, firm_scope=self.firm_id, actor_id=self.actor
            )
        self.session.expire_all()
        return self.notes.get_note(row.id, firm_scope=self.firm_id)

    def note_line(self, note: DeliveryNote) -> DeliveryNoteLine:
        """Return the note's one line."""
        line = self.session.scalar(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
        assert line is not None
        return line

    def bill(
        self,
        note: DeliveryNote,
        quantity: str,
        *,
        approve: bool = True,
        **fields: object,
    ) -> SalesInvoice:
        """Bill a note's line for a quantity, saying nothing else."""
        row = self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        SalesInvoiceLineWrite(
                            source_document_type="DELIVERY_NOTE",
                            source_document_id=note.id,
                            source_document_line_id=self.note_line(note).id,
                            line_number=1,
                            current_invoice_quantity=D(quantity),
                        )
                    ],
                }
                | fields
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        if approve:
            self.bills.approve_invoice(
                row.id, firm_scope=self.firm_id, actor_id=self.actor
            )
        self.session.expire_all()
        return self.bills.get_invoice(row.id, firm_scope=self.firm_id)

    def bill_of_order(self, order: SalesOrder, quantity: str) -> SalesInvoice:
        """Bill part of an order straight off it, and approve the bill.

        For a firm that types no delivery notes: the bill raises the note.
        """
        row = self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        SalesInvoiceLineWrite(
                            source_document_type="SALES_ORDER",
                            source_document_id=order.id,
                            source_document_line_id=self.order_line(order).id,
                            line_number=1,
                            current_invoice_quantity=D(quantity),
                        )
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        self.bills.approve_invoice(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()
        return self.bills.get_invoice(row.id, firm_scope=self.firm_id)

    def bill_line(self, bill: SalesInvoice) -> SalesInvoiceLine:
        """Return the bill's one line."""
        line = self.session.scalar(
            select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
        )
        assert line is not None
        return line

    def legs(self, bill: SalesInvoice) -> dict[str, tuple[Decimal, Decimal]]:
        """Return (debit, credit) per account code of the bill's own journal."""
        entry = self.session.scalar(
            select(JournalEntry).where(
                JournalEntry.source_module == "sales_invoice",
                JournalEntry.source_id == bill.id,
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

    def heads(self, bill: SalesInvoice) -> dict[str, Decimal]:
        """Return the tax the bill charged under each head."""
        rows = self.session.execute(
            select(SalesInvoiceLineTax.component_code, SalesInvoiceLineTax.amount)
            .join(
                SalesInvoiceLine,
                SalesInvoiceLine.id == SalesInvoiceLineTax.sales_invoice_line_id,
            )
            .where(SalesInvoiceLine.sales_invoice_id == bill.id)
        ).all()
        totals: dict[str, Decimal] = {}
        for code, amount in rows:
            totals[code] = totals.get(code, D("0")) + D(str(amount))
        return totals

    def counter_bill(self, quantity: str, **fields: object) -> SalesInvoice:
        """Save a draft bill typed straight in: a customer, a product, a price.

        ``line_discount_amount`` is typed on the line; the rest on the bill.
        """
        off = fields.pop("line_discount_amount", None)
        row = self.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        SalesInvoiceLineWrite(
                            product_id=self.setup.product.id,
                            line_number=1,
                            current_invoice_quantity=D(quantity),
                            unit_price=PRICE,
                            discount_amount=None if off is None else D(str(off)),
                        )
                    ],
                }
                | fields
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        self.session.expire_all()
        return self.bills.get_invoice(row.id, firm_scope=self.firm_id)

    def resave(
        self, bill: SalesInvoice, quantity: str, **fields: object
    ) -> SalesInvoice:
        """Send a draft bill's own line back, with whatever header is named."""
        line = self.bill_line(bill)
        self.bills.update_invoice(
            bill.id,
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": bill.customer_id,
                    "invoice_date": bill.invoice_date,
                    "lines": [
                        {
                            "source_document_type": line.source_document_type,
                            "source_document_id": line.source_document_id,
                            "source_document_line_id": line.source_document_line_id,
                            "line_number": 1,
                            "current_invoice_quantity": D(quantity),
                        }
                    ],
                }
                | fields
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        self.session.expire_all()
        return self.bills.get_invoice(bill.id, firm_scope=self.firm_id)

    def own_order(self, bill: SalesInvoice) -> SalesOrder:
        """Return the live order a counter bill raised for itself."""
        order = self.session.scalar(
            select(SalesOrder).where(
                SalesOrder.raised_by_sales_invoice_id == bill.id,
                SalesOrder.status.not_in(("CANCELLED", "CLOSED")),
            )
        )
        assert order is not None
        return order

    def person(self, role_code: str, limit: str) -> UUID:
        """Create somebody whose one role may discount ``limit`` percent."""
        user = User(
            email=f"{uuid4().hex[:8]}@trade.test",
            full_name="Trade person",
            password_hash="x",
        )
        role = Role(code=role_code, name=role_code.title())
        self.session.add_all([user, role])
        self.session.flush()
        self.session.add(
            UserRole(user_id=user.id, role_id=role.id, firm_id=self.firm_id)
        )
        self.session.commit()
        DiscountLimitService(self.session).replace_limits(
            [(role_code, D(limit))], firm_id=self.firm_id, actor_id=self.actor
        )
        return user.id


def test_a_slice_of_a_share_sums_back_to_the_share() -> None:
    """Three parts of 100.00 over 7 units take 42.8571, 28.5715 and 28.5714."""
    parts = [
        continued_share(D("100"), before=D(before), part=D(part), whole=D("7"))
        for before, part in (("0", "3"), ("3", "2"), ("5", "2"))
    ]
    assert parts == [D("42.8571"), D("28.5715"), D("28.5714")]
    assert sum(parts) == D("100.0000")
    # Past the whole, and of nothing, there is nothing left to take.
    assert continued_share(D("100"), before=D("7"), part=D("1"), whole=D("7")) == 0
    assert continued_share(D("0"), before=D("0"), part=D("1"), whole=D("7")) == 0


def test_free_goods_go_in_whole_units_and_the_last_part_takes_the_rest() -> None:
    """1 free on 10 leaves with the delivery that completes the line."""

    def take(before: str, part: str, already: str, offered: str = "1") -> Decimal:
        return continued_free_goods(
            D(offered),
            before=D(before),
            part=D(part),
            whole=D("10"),
            already=D(already),
        )

    assert [take("0", "4", "0"), take("4", "3", "0"), take("7", "3", "0")] == [0, 0, 1]
    assert [take("0", "5", "0", "2"), take("5", "5", "1", "2")] == [1, 1]
    # Already gone: nothing goes twice.
    assert take("5", "5", "2", "2") == 0
    # A gift line charges for nothing and gives what is left of it whole.
    assert continued_free_goods(
        D("3"), before=D("0"), part=D("0"), whole=D("0"), already=D("1")
    ) == D("2")


def test_an_offers_bill_discount_reaches_the_note_the_bill_and_the_books() -> None:
    """The reproduction: 60 at 84 less 7.5% less 200 is 5,265.16 all the way."""
    trade = _Trade()
    trade.offers()
    order = trade.order("60")
    assert order.bill_discount_amount == D("200.0000")
    assert order.bill_discount_source == "promotion"
    assert order.grand_total == D("5265.1600")

    note = trade.note(order, "60")
    assert note.bill_discount_amount == D("200.0000")
    assert trade.note_line(note).bill_discount_amount == D("200.0000")
    assert note.grand_total == D("5265.1600")

    bill = trade.bill(note, "60")
    assert bill.bill_discount_amount == D("200.0000")
    assert bill.bill_discount_source == "inherited"
    assert bill.subtotal == D("4462.0000")
    assert bill.tax_total == D("803.1600")
    assert bill.grand_total == D("5265.1600")
    assert trade.heads(bill) == {"CGST": D("401.5800"), "SGST": D("401.5800")}
    legs = trade.legs(bill)
    assert sum(debit for debit, _ in legs.values()) == D("5265.16")
    assert sorted(credit for _, credit in legs.values() if credit) == [
        D("401.58"),
        D("401.58"),
        D("4462.00"),
    ]
    # What the offer is reported to have given is what came off the bill.
    claimed = trade.session.scalars(
        select(PromotionRedemption.benefit_amount).where(
            PromotionRedemption.status == "CLAIMED"
        )
    ).all()
    assert sorted(D(str(value)) for value in claimed) == [D("200.0000"), D("378.0000")]
    assert bill.bill_discount_amount + trade.bill_line(bill).discount_amount == D(
        "578.0000"
    )


@pytest.mark.parametrize(
    ("typed", "total"),
    [
        ({"bill_discount_amount": "100"}, "873.2000"),
        ({"bill_discount_percent": "10", "freight_amount": "50"}, "951.0800"),
    ],
)
def test_a_typed_bill_discount_reaches_the_bill(
    typed: dict[str, str], total: str
) -> None:
    """10 at 84 with 100 off is 873.20, and with 10% and freight 50 is 951.08."""
    trade = _Trade()
    order = trade.order("10", **typed)
    assert order.grand_total == D(total)

    note = trade.note(order, "10")
    bill = trade.bill(note, "10")

    assert note.grand_total == D(total)
    assert bill.grand_total == D(total)
    assert bill.bill_discount_amount == order.bill_discount_amount
    assert bill.bill_discount_percent == order.bill_discount_percent
    assert bill.bill_discount_source == "inherited"


def test_two_notes_and_two_bills_sum_to_the_order_exactly() -> None:
    """7 at 84 with 100 off, delivered 3 then 4 and billed apart, is 575.84."""
    trade = _Trade()
    order = trade.order("7", bill_discount_amount="100")
    assert (order.tax_total, order.grand_total) == (D("87.8400"), D("575.8400"))

    first = trade.note(order, "3")
    second = trade.note(order, "4")
    assert [first.bill_discount_amount, second.bill_discount_amount] == [
        D("42.8571"),
        D("57.1429"),
    ]
    bills = [trade.bill(first, "3"), trade.bill(second, "4")]

    assert sum(bill.bill_discount_amount for bill in bills) == D("100.0000")
    assert sum(bill.tax_total for bill in bills) == order.tax_total
    assert sum(bill.grand_total for bill in bills) == order.grand_total
    owed = [sum(debit for debit, _ in trade.legs(bill).values()) for bill in bills]
    assert sum(owed) == D("575.84")


def test_one_note_billed_in_two_parts_sums_to_the_note() -> None:
    """A note of 7 carrying 100.00 off, billed 3 then 4, is billed 100.00 off."""
    trade = _Trade()
    order = trade.order("7", bill_discount_amount="100")
    note = trade.note(order, "7")

    bills = [trade.bill(note, "3"), trade.bill(note, "4")]

    assert [bill.bill_discount_amount for bill in bills] == [
        D("42.8571"),
        D("57.1429"),
    ]
    assert sum(bill.grand_total for bill in bills) == order.grand_total


def test_a_figure_typed_downstream_replaces_what_the_order_gave() -> None:
    """Typed on the note or the bill, zero included, it is that document's own."""
    trade = _Trade()
    order = trade.order("10", bill_discount_amount="100")

    refused = trade.note(order, "4", bill_discount_amount="0")
    assert refused.bill_discount_amount == D("0.0000")
    # The bill of that note has nothing to inherit, and may type its own.
    own = trade.bill(refused, "4", approve=False, bill_discount_amount="25")
    assert (own.bill_discount_amount, own.bill_discount_source) == (
        D("25.0000"),
        "typed",
    )

    rest = trade.note(order, "6")
    assert rest.bill_discount_amount == D("60.0000")
    waived = trade.bill(rest, "6", approve=False, bill_discount_percent="0")
    assert (waived.bill_discount_amount, waived.bill_discount_source) == (
        D("0.0000"),
        "typed",
    )


def test_resaving_a_bill_with_the_rate_it_was_shown_moves_nothing() -> None:
    """An editor sends back the rate the bill reads; the shares stay the order's."""
    trade = _Trade()
    order = trade.order("7", bill_discount_amount="100")
    note = trade.note(order, "7")
    draft = trade.bill(note, "3", approve=False)
    assert draft.bill_discount_percent == D("17.0068")

    again = trade.resave(draft, "3", bill_discount_percent="17.0068")
    silent = trade.resave(again, "3")
    cleared = trade.resave(silent, "3", bill_discount_percent=None)

    for row in (again, silent, cleared):
        assert row.bill_discount_amount == D("42.8571")
        assert row.bill_discount_source == "inherited"
    # A typed figure is kept by an edit that leaves it out; a zero too.
    typed = trade.resave(cleared, "3", bill_discount_percent="5")
    assert typed.bill_discount_source == "typed"
    assert trade.resave(typed, "3").bill_discount_amount == D("12.6000")
    waived = trade.resave(typed, "3", bill_discount_amount="0")
    kept = trade.resave(waived, "3")
    assert (kept.bill_discount_amount, kept.bill_discount_source) == (
        D("0.0000"),
        "typed",
    )


def test_a_return_of_part_of_the_bill_credits_the_discounted_value() -> None:
    """2 of 10 billed at 84 with 100 off come back at 148.00 plus tax."""
    trade = _Trade()
    order = trade.order("10", bill_discount_amount="100")
    note = trade.note(order, "10")
    trade.bill(note, "10")
    returns = SalesReturnService(trade.session)

    row = returns.create_return(
        SalesReturnCreate(
            warehouse_id=trade.setup.warehouse.id,
            return_date=date(2026, 8, 5),
            lines=[
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=trade.note_line(note).id,
                    line_number=1,
                    current_return_quantity=D("2"),
                )
            ],
        ),
        firm_id=trade.firm_id,
        actor_id=trade.actor,
    )

    # 2 x 84 less a fifth of the 100.00 the order took off, plus 18%.
    assert row.subtotal == D("148.0000")
    assert row.grand_total == D("174.6400")


def test_a_counter_bill_charges_what_its_hidden_order_agreed() -> None:
    """Stages off: the bill, its note and its order all read 5,265.16."""
    trade = _Trade(counter=True)
    trade.offers()

    draft = trade.counter_bill("60")
    assert draft.grand_total == D("5265.1600")
    assert draft.bill_discount_amount == D("200.0000")
    assert draft.bill_discount_source == "inherited"
    assert trade.own_order(draft).grand_total == D("5265.1600")

    # A save that changes nothing leaves the offer's 200 the offer's.
    again = trade.resave(draft, "60")
    assert again.grand_total == D("5265.1600")
    assert trade.own_order(again).bill_discount_source == "promotion"
    # Cut to 30 the order is priced afresh, and the offer gives its 200 again.
    cut = trade.resave(again, "30")
    assert trade.own_order(cut).bill_discount_source == "promotion"
    assert cut.grand_total == trade.own_order(cut).grand_total == D("2514.5800")

    trade.bills.approve_invoice(cut.id, firm_scope=trade.firm_id, actor_id=trade.actor)
    trade.session.expire_all()
    assert sum(debit for debit, _ in trade.legs(cut).values()) == D("2514.58")
    statuses = trade.session.scalars(
        select(PromotionRedemption.status).where(
            PromotionRedemption.document_id == trade.own_order(cut).id
        )
    ).all()
    assert sorted(statuses) == ["CLAIMED", "CLAIMED"]


def test_a_counter_bills_typed_discount_survives_an_edit_that_omits_it() -> None:
    """Typed on the bill it is typed on its order, and an edit keeps the rate."""
    trade = _Trade(counter=True)
    draft = trade.counter_bill("10", bill_discount_amount="100")
    assert draft.grand_total == D("873.2000")
    assert trade.own_order(draft).bill_discount_source == "typed"

    same = trade.resave(draft, "10")
    assert same.grand_total == D("873.2000")
    grown = trade.resave(same, "20")
    assert trade.own_order(grown).bill_discount_source == "typed"
    assert grown.bill_discount_percent == same.bill_discount_percent


def test_an_inherited_bill_discount_is_not_judged_against_the_approver() -> None:
    """An offer's 200 is nobody's hand: a 1% approver passes the bill."""
    trade = _Trade()
    trade.offers()
    order = trade.order("60")
    note = trade.note(order, "60")
    clerk = trade.person("BILLING_CLERK", "1")

    inherited = trade.bill(note, "30", approve=False)
    trade.bills.approve_invoice(inherited.id, firm_scope=trade.firm_id, actor_id=clerk)

    # 100 would be the share this half inherits sent back; 150 is typed.
    typed = trade.bill(note, "30", approve=False, bill_discount_amount="150")
    with pytest.raises(ValidationError, match="above your limit of 1.00%"):
        trade.bills.approve_invoice(typed.id, firm_scope=trade.firm_id, actor_id=clerk)


def test_a_note_that_says_nothing_ships_the_orders_free_goods() -> None:
    """D-PRC-4: 12 + 1 free ships 13, completes the order and bills 12 + 1."""
    trade = _Trade()
    order = trade.order("12", free_quantity="1")

    note = trade.note(order, "12")

    line = trade.note_line(note)
    assert (line.free_quantity, line.delivered_quantity) == (D("1.0000"), D("13.0000"))
    trade.session.expire_all()
    assert trade.orders.get_order(order.id, firm_scope=trade.firm_id).status == (
        "DELIVERED"
    )
    bill = trade.bill(note, "12")
    assert trade.bill_line(bill).free_quantity == D("1.0000")


def test_part_deliveries_share_the_free_goods_in_whole_units() -> None:
    """10 + 2 free in two notes of 5 ships 6 and 6; a typed 0 ships none."""
    trade = _Trade()
    order = trade.order("10", free_quantity="2")

    first = trade.note(order, "5")
    second = trade.note(order, "5")

    assert [trade.note_line(note).free_quantity for note in (first, second)] == [
        D("1.0000"),
        D("1.0000"),
    ]

    other = trade.order("10", free_quantity="1")
    parts = [trade.note(other, quantity) for quantity in ("4", "3")]
    refused = trade.note(other, "2", free_quantity="0")
    last = trade.note(other, "1")
    assert [
        trade.note_line(note).free_quantity for note in (*parts, refused, last)
    ] == [D("0.0000"), D("0.0000"), D("0.0000"), D("1.0000")]


def test_part_bills_state_the_free_goods_in_whole_units() -> None:
    """A note of 10 + 1 free billed 4 then 6 reads 4, then 6 + 1 free."""
    trade = _Trade()
    order = trade.order("10", free_quantity="1")
    note = trade.note(order, "10")

    bills = [trade.bill(note, "4"), trade.bill(note, "6")]

    assert [trade.bill_line(bill).free_quantity for bill in bills] == [
        D("0.0000"),
        D("1.0000"),
    ]


def test_a_note_line_of_nothing_is_still_refused() -> None:
    """Silence about free goods on a line with none to inherit ships nothing."""
    trade = _Trade()
    order = trade.order("10")

    with pytest.raises(ValidationError, match="delivers a quantity of 0"):
        trade.note(order, "0", ship=False)


@pytest.mark.parametrize(
    "typed", [{"discount_amount": "100"}, {"discount_percent": "10"}]
)
def test_part_bills_of_an_order_share_its_line_discount(typed: dict[str, str]) -> None:
    """D-PRC-22: 10 at 100 less 100 a line and 90 a bill, billed 4 then 6.

    With the delivery-note stage off each part bill took the whole 100.00 off
    its line: 311.52 + 526.28 = 837.80 against the order's 955.80, the
    customer under-billed 118.00 and 18.00 of GST never charged.
    """
    trade = _Trade(notes=False)
    order = trade.order("10", unit_price="100", bill_discount_amount="90", **typed)
    assert order.grand_total == D("955.8000")
    assert trade.order_line(order).discount_amount == D("100.0000")

    bills = [trade.bill_of_order(order, "4"), trade.bill_of_order(order, "6")]

    lines = [trade.bill_line(bill) for bill in bills]
    assert [line.discount_percent for line in lines] == [D("10.0000"), D("10.0000")]
    assert [trade.bill_line(bill).discount_amount for bill in bills] == [
        D("40.0000"),
        D("60.0000"),
    ]
    assert [bill.bill_discount_amount for bill in bills] == [
        D("36.0000"),
        D("54.0000"),
    ]
    assert [bill.grand_total for bill in bills] == [D("382.3200"), D("573.4800")]
    assert sum(bill.tax_total for bill in bills) == order.tax_total == D("145.8000")
    owed = [sum(debit for debit, _ in trade.legs(bill).values()) for bill in bills]
    assert owed == [D("382.32"), D("573.48")]
    trade.session.expire_all()
    assert trade.orders.get_order(order.id, firm_scope=trade.firm_id).status == (
        "DELIVERED"
    )


def test_three_part_bills_of_an_order_sum_to_its_line_discount_exactly() -> None:
    """100.00 off 3 at 100 is 33.3333%; three bills of 1 still take 100.00."""
    trade = _Trade(notes=False)
    order = trade.order("3", unit_price="100", discount_amount="100")

    bills = [trade.bill_of_order(order, "1") for _ in range(3)]

    assert [trade.bill_line(bill).discount_amount for bill in bills] == [
        D("33.3333"),
        D("33.3334"),
        D("33.3333"),
    ]
    assert sum(bill.grand_total for bill in bills) == order.grand_total
    assert sum(bill.tax_total for bill in bills) == order.tax_total


def test_notes_a_person_types_share_the_line_discount_exactly() -> None:
    """Stages on: notes of 1, 1 and 1, each billed, take 100.00 between them."""
    trade = _Trade()
    order = trade.order("3", unit_price="100", discount_amount="100")

    notes = [trade.note(order, "1") for _ in range(3)]
    bills = [trade.bill(note, "1") for note in notes]

    assert sum(trade.note_line(note).discount_amount for note in notes) == D("100.0000")
    assert sum(trade.bill_line(bill).discount_amount for bill in bills) == D("100.0000")
    assert sum(bill.grand_total for bill in bills) == order.grand_total


def test_one_note_billed_in_three_parts_shares_its_line_discount_exactly() -> None:
    """A note of 3 with 100.00 off its line, billed 1, 1 and 1, bills 100.00 off."""
    trade = _Trade()
    order = trade.order("3", unit_price="100", discount_amount="100")
    note = trade.note(order, "3")

    bills = [trade.bill(note, "1") for _ in range(3)]

    assert sum(trade.bill_line(bill).discount_amount for bill in bills) == D("100.0000")
    assert sum(bill.grand_total for bill in bills) == order.grand_total


def test_a_counter_bill_takes_the_whole_of_a_typed_line_amount() -> None:
    """Stages off: 3 at 84 with 100.00 typed off the line is 100.00, not 99.9999."""
    trade = _Trade(counter=True)

    draft = trade.counter_bill("3", line_discount_amount="100")

    assert trade.bill_line(draft).discount_amount == D("100.0000")
    assert draft.grand_total == trade.own_order(draft).grand_total


def test_part_bills_of_an_order_share_its_free_goods_in_whole_units() -> None:
    """Note stage off: 10 + 1 free billed 4 then 6 ships 4, then 6 and the gift."""
    trade = _Trade(notes=False)
    order = trade.order("10", free_quantity="1")

    bills = [trade.bill_of_order(order, "4"), trade.bill_of_order(order, "6")]

    assert [trade.bill_line(bill).free_quantity for bill in bills] == [
        D("0.0000"),
        D("1.0000"),
    ]
