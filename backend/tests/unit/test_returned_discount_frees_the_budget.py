"""Goods sold under an offer and returned give the offer's money back.

D-PRC-45, from the third pricing check: 10% on a line of 6 at 100.00 with a
budget of 100.00. The order was billed (60.00 claimed) and all 6 came back;
the offer, the performance report, the redemptions report and
discount-by-promotion went on reading 60.00 with 40.00 left, though an order
closed short gave its part back (D-PRC-28) and a returned free unit did
(D-PRC-8). `claims_given` now nets the share of the discount that completed
returns and approved credit notes took back -- the share a claim on the
principal reads, from the same statement (`discount_on_bills`).

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.pagination import ReportWindow
from app.credit_note.models import CreditNote, CreditNoteLine
from app.principal_claims.services import PrincipalClaimService, PrincipalClaimWrite
from app.products.models.brand import Principal
from app.promotions.models import PromotionRedemption
from app.promotions.services import PromotionCrudService, PromotionReportService
from app.promotions.services.bill_discounts import offers_took_off_line
from app.promotions.services.offer_use import offer_took_off
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.services.discount_report import DiscountReportService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services.sales_return_service import SalesReturnService
from tests.unit.test_offer_use_is_one_figure import _Shop

D = Decimal
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


class _Returns(_Shop):
    """The check's firm: 10% off at 100.00 a unit, budget 100.00."""

    def __init__(self) -> None:
        """Leave only the money offer running."""
        super().__init__()
        self.goods.status = "INACTIVE"
        self.session.commit()

    def six(self) -> SalesOrder:
        """Approve an order of 6 at 100.00: the offer takes 60.00 off."""
        return self.order("6", unit_price="100")

    def sold(self, quantity: str = "6") -> SalesInvoice:
        """Order, deliver and bill a quantity under the offer."""
        order = self.order(quantity, unit_price="100")
        return self.bill(self.note(order, quantity), quantity)

    def give_back(
        self, bill: SalesInvoice, quantity: str, *, complete: bool = True
    ) -> None:
        """Raise and approve a return of the bill's line, and complete it."""
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
        if complete:
            service.complete_return(
                row.id, firm_scope=self.firm_id, actor_id=self.actor
            )
        self.session.expire_all()

    def given(self) -> tuple[Decimal, Decimal | None]:
        """Return what the offer counts as given, and what its budget has left."""
        room = self.room(self.money)
        return room.amount_claimed, room.amount_left


def test_a_sale_returned_whole_gives_the_budget_back_in_every_reader() -> None:
    """The check's figures: 60.00 claimed, all 6 back, 0.00 given and 100 left."""
    shop = _Returns()
    bill = shop.sold()
    assert shop.given() == (D("60.0000"), D("40.0000"))

    shop.give_back(bill, "6")

    assert shop.given() == (D("0.0000"), D("100.0000"))
    reports = PromotionReportService(shop.session)
    (performance,) = (
        row
        for row in reports.performance_report(firm_scope=shop.firm_id)
        if row.code == "SCHEME"
    )
    assert (
        performance.benefit_amount,
        performance.remaining_benefit_amount,
        performance.claimed_count,
    ) == (D("0.0000"), D("100.0000"), 1)
    (register,) = reports.redemption_report(firm_scope=shop.firm_id)
    assert (register.benefit_amount, register.claimed_benefit_amount) == (
        D("0.0000"),
        D("60.0000"),
    )
    by_offer = {
        row.code: row
        for row in DiscountReportService(shop.session).by_promotion(
            shop.firm_id, ReportWindow(None, None, 1, 100)
        )
    }
    assert by_offer["SCHEME"].benefit_amount == D("0.00")
    (listed,) = PromotionCrudService(shop.session).promotion_responses([shop.money])
    assert listed.benefit_amount_claimed == D("0.0000")
    # The claim's own row is not rewritten: it says what the order claimed.
    (claim,) = shop.session.scalars(select(PromotionRedemption))
    assert (claim.status, claim.benefit_amount) == ("CLAIMED", D("60.0000"))


def test_a_part_return_gives_back_its_share_and_the_next_sale_fits() -> None:
    """2 of 6 back leaves 40.00 given, so another 60.00 fits a budget of 100."""
    shop = _Returns()
    bill = shop.sold()

    shop.give_back(bill, "2")

    assert shop.given() == (D("40.0000"), D("60.0000"))
    again = shop.six()
    assert again.status == "APPROVED"
    assert shop.given() == (D("100.0000"), D("0.0000"))


def test_a_return_that_is_not_complete_gives_nothing_back() -> None:
    """Approved and not yet received: the goods are still with the customer."""
    shop = _Returns()
    bill = shop.sold()

    shop.give_back(bill, "6", complete=False)

    assert shop.given() == (D("60.0000"), D("40.0000"))


def test_a_sale_not_yet_billed_holds_its_claim_whole() -> None:
    """A claim is made at approval; nothing has come back of an unbilled sale."""
    shop = _Returns()
    shop.six()

    assert shop.given() == (D("60.0000"), D("40.0000"))


def test_a_short_close_and_a_return_of_what_was_delivered_leave_nothing() -> None:
    """4 ordered, 2 delivered and closed (20.00 kept), those 2 returned: 0.00."""
    shop = _Returns()
    order = shop.four()
    bill = shop.bill(shop.note(order, "2"), "2")
    shop.close(order)
    assert shop.given() == (D("20.0000"), D("80.0000"))

    shop.give_back(bill, "2")

    assert shop.given() == (D("0.0000"), D("100.0000"))


def test_a_credit_note_gives_back_the_share_it_credited() -> None:
    """Half the line's charged value credited is half its discount not given."""
    shop = _Returns()
    bill = shop.sold()
    line = shop.bill_line(bill)
    note = CreditNote(
        firm_id=shop.firm_id,
        customer_id=bill.customer_id,
        branch_id=bill.branch_id,
        sales_invoice_id=bill.id,
        credit_note_number="CN-1",
        credit_note_date=date(2026, 8, 21),
        reason="RATE_DIFFERENCE",
        status="APPROVED",
        taxable_amount=D("270"),
    )
    shop.session.add(note)
    shop.session.flush()
    shop.session.add(
        CreditNoteLine(
            credit_note_id=note.id,
            firm_id=shop.firm_id,
            line_number=1,
            sales_invoice_line_id=line.id,
            product_id=line.product_id,
            taxable_amount=D("270"),
        )
    )
    shop.session.commit()

    # The line was charged 600 - 60 = 540; 270 of it is credited.
    assert shop.given() == (D("30.0000"), D("70.0000"))


@pytest.mark.parametrize(("back", "kept"), [("6", "0.00"), ("2", "40.00"), ("0", "60")])
def test_the_principals_claim_asks_for_what_the_offer_says_it_gave(
    back: str, kept: str
) -> None:
    """The offer's budget and the claim on its principal read one figure."""
    shop = _Returns()
    principal = Principal(firm_id=shop.firm_id, code="PRA", name="Principal A")
    shop.session.add(principal)
    shop.session.flush()
    shop.money.principal_id = principal.id
    shop.money.principal_share_percent = D("100")
    shop.session.commit()
    bill = shop.sold()
    if back != "0":
        shop.give_back(bill, back)

    preview = PrincipalClaimService(shop.session).preview(
        PrincipalClaimWrite(
            principal_id=principal.id,
            period_from=AUGUST[0],
            period_to=AUGUST[1],
            claim_date=AUGUST[1],
            kinds=["SCHEME"],
        ),
        firm_id=shop.firm_id,
    )

    assert preview.scheme_amount == D(kept)
    assert shop.given()[0] == D(kept)


def test_the_column_reads_an_order_line_as_the_loaded_row_is_read() -> None:
    """`offers_took_off_line` in SQL equals `offer_took_off` on the row."""
    shop = _Returns()
    order = shop.order("6", unit_price="100", bill_discount_amount="12")
    typed = shop.order("6", unit_price="100", discount_percent="5")
    for row in (order, typed):
        line = shop.order_line(row)
        in_sql = shop.session.execute(
            select(offers_took_off_line())
            .select_from(SalesOrderLine)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .where(SalesOrderLine.id == line.id)
        ).scalar_one()
        assert D(str(in_sql)) == offer_took_off(
            discount_source=line.discount_source,
            discount_amount=line.discount_amount,
            bill_discount_amount=line.bill_discount_amount,
            bill_discount_source=row.bill_discount_source,
        )
    assert shop.order_line(order).discount_source == "promotion"
    assert shop.order_line(typed).discount_source != "promotion"
