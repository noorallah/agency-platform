"""A principal's scheme is claimed off what was billed, not off the order.

D-PRC-27: the claim read each redemption's ``benefit_amount`` -- what the
offer took off the **order** when it was approved -- so a 10% offer of which
the principal bears half claimed 20.00 for an order of 4 at 100.00 that was
never delivered, 20.00 for one closed after half was delivered (10.00 of
discount passed on), and 20.00 for one billed and returned in full.

The firm claims what it gave. Each case here is the check's own: order A
approved and left, order B half delivered, closed and billed, order C billed
and returned whole. Every case runs on a request-shaped session.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.credit_note.models import CreditNote, CreditNoteLine
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.principal_claims.models import PrincipalClaimLine
from app.principal_claims.services import (
    PrincipalClaimPreview,
    PrincipalClaimService,
    PrincipalClaimWrite,
)
from app.principal_claims.services.passed_on import scheme_bill_source
from app.products.models.brand import Principal
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.schemas import PromotionActionType
from app.promotions.services.promotion_service import budget_rooms
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services.sales_return_service import SalesReturnService
from tests.unit.test_lines_in_another_unit import box_of_twelve
from tests.unit.test_order_bill_discount_reaches_the_bill import DAY, _Trade
from tests.unit.test_promotion_budgets import _offer
from tests.unit.test_promotions import _promotion

D = Decimal
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))
SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))


class _Scheme(_Trade):
    """A firm passing on principal A's 10% offer, of which A bears half."""

    def __init__(self) -> None:
        """Publish the offer P10 on the firm's product."""
        super().__init__()
        self.principal = Principal(firm_id=self.firm_id, code="PRA", name="Principal A")
        self.session.add(self.principal)
        self.session.flush()
        self.offer: Promotion = _promotion(
            self.session,
            firm_id=self.firm_id,
            code="P10",
            actions=[(PromotionActionType.LINE_DISCOUNT_PERCENT, {"percent": "10"})],
        )
        self.offer.principal_id = self.principal.id
        self.offer.principal_share_percent = D("50")
        self.session.commit()

    def four(self) -> SalesOrder:
        """Approve an order of 4 at 100.00: the offer takes 40.00 off."""
        return self.order("4", unit_price="100")

    def redemption(self, order: SalesOrder) -> PromotionRedemption:
        """Return the order's claim on the offer."""
        return self.session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.document_id == order.id,
                PromotionRedemption.status == "CLAIMED",
            )
        ).one()

    def write(
        self, period: tuple[date, date] = AUGUST, kinds: tuple[str, ...] = ("SCHEME",)
    ) -> PrincipalClaimWrite:
        """Describe a period's claim on principal A."""
        return PrincipalClaimWrite(
            principal_id=self.principal.id,
            period_from=period[0],
            period_to=period[1],
            claim_date=period[1],
            kinds=list(kinds),
        )

    def preview(self, period: tuple[date, date] = AUGUST) -> PrincipalClaimPreview:
        """Preview a period's scheme claim on principal A."""
        return PrincipalClaimService(self.session).preview(
            self.write(period), firm_id=self.firm_id
        )

    def give_back(self, bill: SalesInvoice, quantity: str) -> None:
        """Raise, approve and complete a return of the bill's line."""
        service = SalesReturnService(self.session)
        row = service.create_return(
            SalesReturnCreate(
                warehouse_id=self.setup.warehouse.id,
                return_date=date(2026, 8, 20),
                lines=[
                    SalesReturnLineWrite(
                        source_document_type=SalesReturnSourceType.SALES_INVOICE,
                        source_document_id=bill.id,
                        source_document_line_id=self.bill_line(bill).id,
                        line_number=1,
                        current_return_quantity=D(quantity),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.approve_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        service.complete_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()


def _amounts(preview: PrincipalClaimPreview) -> list[tuple[str, Decimal]]:
    """Return each line's document and amount."""
    return [(line.source_number, line.amount) for line in preview.lines]


def test_an_order_approved_and_never_billed_claims_nothing() -> None:
    """Order A: 40.00 claimed on the offer, nothing passed on to anybody."""
    firm = _Scheme()
    order = firm.four()

    assert firm.redemption(order).benefit_amount == D("40.0000")
    preview = firm.preview()
    assert (preview.scheme_amount, preview.lines) == (D("0"), [])


def test_an_order_closed_after_half_was_billed_claims_half() -> None:
    """Order B: 2 of 4 delivered and billed is 20.00 passed on, 10.00 claimed."""
    firm = _Scheme()
    order = firm.four()
    bill = firm.bill(firm.note(order, "2"), "2")
    firm.orders.close_order(order.id, firm_scope=firm.firm_id, actor_id=firm.actor)

    assert firm.bill_line(bill).discount_amount == D("20.0000")
    preview = firm.preview()
    assert preview.scheme_amount == D("10.00")
    (line,) = preview.lines
    assert (line.kind, line.source_number, line.source_date, line.amount) == (
        "SCHEME",
        bill.invoice_number,
        DAY,
        D("10.00"),
    )
    assert line.description == f"Promotion P10 on order {order.order_number}"
    assert line.source_id == scheme_bill_source(firm.redemption(order).id, bill.id)


def test_an_order_billed_and_returned_whole_claims_nothing() -> None:
    """Order C: all 4 came back, so the customer kept none of the discount."""
    firm = _Scheme()
    order = firm.four()
    bill = firm.bill(firm.note(order, "4"), "4")
    assert _amounts(firm.preview()) == [(bill.invoice_number, D("20.00"))]

    firm.give_back(bill, "4")

    assert firm.preview().lines == []


def test_a_part_return_takes_the_same_share_of_the_discount_back() -> None:
    """1 of 4 back leaves three quarters of 40.00 passed on: 15.00 claimed."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")

    firm.give_back(bill, "1")

    assert _amounts(firm.preview()) == [(bill.invoice_number, D("15.00"))]


def test_a_credit_note_takes_its_share_of_the_discount_back() -> None:
    """Half the bill line's value credited is half its discount not given."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")
    line = firm.bill_line(bill)
    note = CreditNote(
        firm_id=firm.firm_id,
        customer_id=bill.customer_id,
        branch_id=bill.branch_id,
        sales_invoice_id=bill.id,
        credit_note_number="CN-1",
        credit_note_date=date(2026, 8, 21),
        reason="RATE_DIFFERENCE",
        status="APPROVED",
        taxable_amount=D("180"),
    )
    firm.session.add(note)
    firm.session.flush()
    firm.session.add(
        CreditNoteLine(
            credit_note_id=note.id,
            firm_id=firm.firm_id,
            line_number=1,
            sales_invoice_line_id=line.id,
            product_id=line.product_id,
            taxable_amount=D("180"),
        )
    )
    firm.session.commit()

    # The line was charged 400 - 40 = 360; 180 of it is credited.
    assert _amounts(firm.preview()) == [(bill.invoice_number, D("10.00"))]


def test_two_part_bills_are_two_sources_and_sum_to_the_order() -> None:
    """Notes of 1 and 3 billed apart: 5.00 and 15.00, each its own source."""
    firm = _Scheme()
    order = firm.four()
    first = firm.bill(firm.note(order, "1"), "1")
    second = firm.bill(firm.note(order, "3"), "3")

    preview = firm.preview()

    assert sorted(_amounts(preview)) == sorted(
        [(first.invoice_number, D("5.00")), (second.invoice_number, D("15.00"))]
    )
    assert len({line.source_id for line in preview.lines}) == 2
    assert preview.scheme_amount == D("20.00")


def test_a_draft_or_cancelled_bill_has_passed_nothing_on() -> None:
    """Only a bill that stands gave the customer anything."""
    firm = _Scheme()
    order = firm.four()
    note = firm.note(order, "4")
    firm.bill(note, "2", approve=False)
    assert firm.preview().lines == []

    standing = firm.bill(note, "2")
    assert _amounts(firm.preview()) == [(standing.invoice_number, D("10.00"))]


def test_a_part_billed_in_a_later_period_is_claimed_in_that_period() -> None:
    """August's bill on August's claim; September's is left for September's."""
    firm = _Scheme()
    order = firm.four()
    first = firm.bill(firm.note(order, "1"), "1")
    later = firm.bill(firm.note(order, "3"), "3", invoice_date=date(2026, 9, 3))
    service = PrincipalClaimService(firm.session)

    claim = service.raise_claim(firm.write(), firm_id=firm.firm_id, actor_id=firm.actor)

    assert claim.total_amount == D("5.00")
    (held,) = firm.session.scalars(
        select(PrincipalClaimLine).where(PrincipalClaimLine.claim_id == claim.id)
    )
    assert (held.source_number, held.amount) == (first.invoice_number, D("5.00"))
    assert firm.preview().lines == []
    assert _amounts(firm.preview(SEPTEMBER)) == [(later.invoice_number, D("15.00"))]


def test_the_discount_of_one_bill_is_never_claimed_twice() -> None:
    """A claim holds the bill's source; a second period's preview leaves it."""
    firm = _Scheme()
    bill = firm.bill(firm.note(firm.four(), "4"), "4")
    service = PrincipalClaimService(firm.session)
    service.raise_claim(firm.write(), firm_id=firm.firm_id, actor_id=firm.actor)

    wide = (date(2026, 7, 1), date(2026, 9, 30))

    assert firm.preview(wide).lines == []
    assert bill.invoice_date == DAY


def test_a_redemption_an_old_claim_holds_whole_is_not_claimed_again() -> None:
    """A claim raised under the old rule keeps the redemption: no second claim."""
    firm = _Scheme()
    order = firm.four()
    firm.bill(firm.note(order, "4"), "4")
    service = PrincipalClaimService(firm.session)
    claim = service.raise_claim(firm.write(), firm_id=firm.firm_id, actor_id=firm.actor)
    held = firm.session.scalars(
        select(PrincipalClaimLine).where(PrincipalClaimLine.claim_id == claim.id)
    ).one()
    # As it was written before the bills were read: the redemption itself.
    held.source_id = _redemption_id(firm, order)
    firm.session.commit()

    assert firm.preview().lines == []


def _redemption_id(firm: _Scheme, order: SalesOrder) -> UUID:
    """Return the id of the order's claim on the offer."""
    return firm.redemption(order).id


def test_an_offer_the_firm_funds_itself_is_claimed_from_nobody() -> None:
    """No principal on the offer, no line on the principal's claim."""
    firm = _Scheme()
    firm.offer.principal_id = None
    firm.session.commit()
    firm.bill(firm.note(firm.four(), "4"), "4")

    assert firm.preview().lines == []


# ---- D-PRC-82: a discount is given on the units charged ---------------------


class _FreeBeside(_Scheme):
    """The eighth check's sale: 24 at 100.00 under the 10% offer, 2 typed free.

    The offer takes 240.00 off, of which principal A bears 120.00, and has
    1,000.00 to give. The note line's ``ordered_quantity`` reads 26.
    """

    def __init__(self) -> None:
        """Give the offer a budget in money."""
        super().__init__()
        self.offer.max_benefit_amount = D("1000")
        self.session.commit()

    def shipped(self, free: str | None = "2") -> DeliveryNote:
        """Approve the order of 24 and ship all of it on one note."""
        fields = {} if free is None else {"free_quantity": free}
        return self.note(self.order("24", unit_price="100", **fields), "24")

    def off_the_note(
        self, note: DeliveryNote, quantity: str, *, free: str | None = None
    ) -> None:
        """Complete a return of the note's line: so many units, so many free."""
        service = SalesReturnService(self.session)
        row = service.create_return(
            SalesReturnCreate(
                warehouse_id=self.setup.warehouse.id,
                return_date=date(2026, 8, 20),
                lines=[
                    SalesReturnLineWrite(
                        source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=self.note_line(note).id,
                        line_number=1,
                        current_return_quantity=D(quantity),
                        free_quantity=None if free is None else D(free),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.approve_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        service.complete_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()

    def budget(self) -> tuple[Decimal, Decimal | None]:
        """Return what the offer counts as given, and what it has left."""
        self.session.expire_all()
        room = budget_rooms(self.session, [self.offer], firm_id=self.firm_id)[
            self.offer.id
        ]
        return room.amount_claimed, room.amount_left


def test_free_units_beside_a_discount_carry_none_of_it() -> None:
    """24 + 2 free billed whole: 240.00 passed on, 120.00 claimed, not 110.76."""
    firm = _FreeBeside()
    note = firm.shipped()
    assert firm.note_line(note).ordered_quantity == D("26.0000")

    bill = firm.bill(note, "24")

    assert firm.bill_line(bill).discount_amount == D("240.0000")
    assert _amounts(firm.preview()) == [(bill.invoice_number, D("120.00"))]
    assert firm.budget() == (D("240.0000"), D("760.0000"))


def test_two_bills_of_a_note_with_free_units_claim_sixty_each() -> None:
    """The check's two bills of 12: 60.00 a bill where it read 55.38."""
    firm = _FreeBeside()
    note = firm.shipped()

    first = firm.bill(note, "12")
    second = firm.bill(note, "12")

    assert sorted(_amounts(firm.preview())) == sorted(
        [(first.invoice_number, D("60.00")), (second.invoice_number, D("60.00"))]
    )


def test_the_same_sale_with_nothing_free_claims_the_same() -> None:
    """The control: 24 and nothing free is 60.00 a bill, as it always was."""
    firm = _FreeBeside()
    note = firm.shipped(free=None)
    assert firm.note_line(note).ordered_quantity == D("24.0000")

    firm.bill(note, "12")
    firm.bill(note, "12")

    assert [amount for _, amount in _amounts(firm.preview())] == [D("60.00")] * 2


def test_charged_units_returned_take_their_share_of_the_discount_back() -> None:
    """6 of the 24 charged back: a quarter of 240.00, so 90.00 is claimed."""
    firm = _FreeBeside()
    note = firm.shipped()
    bill = firm.bill(note, "24")

    firm.off_the_note(note, "6")

    assert _amounts(firm.preview()) == [(bill.invoice_number, D("90.00"))]
    assert firm.budget() == (D("180.0000"), D("820.0000"))


def test_free_units_returned_alone_take_no_discount_back() -> None:
    """The 2 free come back on their own: the customer kept all 240.00."""
    firm = _FreeBeside()
    note = firm.shipped()
    bill = firm.bill(note, "24")

    firm.off_the_note(note, "0", free="2")

    assert _amounts(firm.preview()) == [(bill.invoice_number, D("120.00"))]
    assert firm.budget() == (D("240.0000"), D("760.0000"))


def test_a_sale_with_free_units_returned_whole_gives_the_budget_back_whole() -> None:
    """24 back, then the 2 free: 0 claimed of 1,000.00 where 18.4615 was left."""
    firm = _FreeBeside()
    note = firm.shipped()
    firm.bill(note, "12")
    firm.bill(note, "12")

    firm.off_the_note(note, "24")
    firm.off_the_note(note, "0", free="2")

    assert firm.preview().lines == []
    assert firm.budget() == (D("0.0000"), D("1000.0000"))


def test_a_box_line_with_its_free_pieces_on_a_line_of_their_own() -> None:
    """2 BOX of 12 and 2 free PIECE: 240.00 off, 120.00 claimed, 0 once back.

    The note's box line reads ``ordered_quantity`` 24 -- stock units -- beside
    a ``current_delivery_quantity`` of 2 BOX.
    """
    firm = _FreeBeside()
    _, box, _ = box_of_twelve(firm.session, firm.setup)
    _offer(
        firm.setup,
        code="B10G1",
        action=(
            PromotionActionType.FREE_QUANTITY,
            {"buy_quantity": "10", "free_quantity": "1"},
        ),
        priority=20,
    )
    order = firm.orders.create_order(
        SalesOrderCreate.model_validate(
            {
                "customer_id": firm.setup.customer.id,
                "branch_id": firm.setup.branch.id,
                "warehouse_id": firm.setup.warehouse.id,
                "order_date": DAY,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": firm.setup.product.id,
                        "quantity": "2",
                        "sales_uom_id": box,
                    }
                ],
            }
        ),
        firm_id=firm.firm_id,
        actor_id=firm.actor,
    )
    firm.orders.approve_order(order.id, firm_scope=firm.firm_id, actor_id=firm.actor)
    boxes, free = firm.session.scalars(
        select(SalesOrderLine)
        .where(SalesOrderLine.sales_order_id == order.id)
        .order_by(SalesOrderLine.line_number)
    )
    assert (boxes.quantity, boxes.discount_amount) == (D("2.0000"), D("240.0000"))
    assert (free.quantity, free.free_quantity) == (D("0.0000"), D("2.0000"))
    note = firm.notes.create_note(
        DeliveryNoteCreate.model_validate(
            {
                "sales_order_id": order.id,
                "delivery_date": DAY,
                "lines": [
                    {
                        "sales_order_line_id": boxes.id,
                        "line_number": 1,
                        "current_delivery_quantity": "2",
                    },
                    {
                        "sales_order_line_id": free.id,
                        "line_number": 2,
                        "current_delivery_quantity": "0",
                    },
                ],
            }
        ),
        firm_id=firm.firm_id,
        actor_id=firm.actor,
    )
    firm.notes.approve_note(note.id, firm_scope=firm.firm_id, actor_id=firm.actor)
    firm.notes.dispatch_note(note.id, firm_scope=firm.firm_id, actor_id=firm.actor)
    firm.session.expire_all()
    sent = {
        row.line_number: row
        for row in firm.session.scalars(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
    }
    assert sent[1].ordered_quantity == D("24.0000")
    assert sent[1].current_delivery_quantity == D("2.0000")
    bills = []
    for _ in range(2):
        row = firm.bills.create_invoice(
            SalesInvoiceCreate.model_validate(
                {
                    "customer_id": firm.setup.customer.id,
                    "invoice_date": DAY,
                    "lines": [
                        {
                            "source_document_type": "DELIVERY_NOTE",
                            "source_document_id": note.id,
                            "source_document_line_id": sent[1].id,
                            "line_number": 1,
                            "current_invoice_quantity": "1",
                        }
                    ],
                }
            ),
            firm_id=firm.firm_id,
            actor_id=firm.actor,
        )
        firm.bills.approve_invoice(row.id, firm_scope=firm.firm_id, actor_id=firm.actor)
        bills.append(row.invoice_number)
    firm.session.expire_all()

    assert sorted(_amounts(firm.preview())) == sorted(
        (number, D("60.00")) for number in bills
    )
    assert firm.budget() == (D("240.0000"), D("760.0000"))

    service = SalesReturnService(firm.session)
    back = service.create_return(
        SalesReturnCreate(
            warehouse_id=firm.setup.warehouse.id,
            return_date=date(2026, 8, 20),
            lines=[
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=sent[1].id,
                    line_number=1,
                    current_return_quantity=D("2"),
                ),
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=sent[2].id,
                    line_number=2,
                    current_return_quantity=D("0"),
                    free_quantity=D("2"),
                ),
            ],
        ),
        firm_id=firm.firm_id,
        actor_id=firm.actor,
    )
    service.approve_return(back.id, firm_scope=firm.firm_id, actor_id=firm.actor)
    service.complete_return(back.id, firm_scope=firm.firm_id, actor_id=firm.actor)

    assert firm.preview().lines == []
    assert firm.budget() == (D("0.0000"), D("1000.0000"))
