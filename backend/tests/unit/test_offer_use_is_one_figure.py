"""What an offer gave is one figure, whoever reads it.

Three findings of the second pricing check, all about the same number.

D-PRC-28: an order of 4 at 100.00 under a 10% offer (budget 100.00) and under
buy 2 get 1 (budget 5) claimed 40.00 and 2 free units; a note of 2 shipped
20.00 of discount and 1 free unit; the order was closed. Both budgets went on
reading 40.00 and 2. Closing now keeps what was delivered and gives back the
rest, on the claim's own row.

D-PRC-32: an offer that gave a document nothing -- its free quantity typed
over by hand, its gift product retired -- still recorded a claim of 0 and 0,
which used up "once a customer" for nothing.

D-PRC-34: after a free unit came back and was given again the offer read 3
free units claimed of 3, and the performance report 4. Every reader now takes
its figures from `claims_given`.

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.common.audit.models import AuditLog
from app.core.exceptions import ValidationError
from app.core.pagination import ReportWindow
from app.promotions.models import Promotion, PromotionRedemption
from app.promotions.schemas import PromotionEvaluationRequest, PromotionLineRequest
from app.promotions.services import (
    PromotionCrudService,
    PromotionReportService,
    PromotionService,
)
from app.promotions.services.promotion_service import BudgetRoom, budget_rooms
from app.sales_invoice.models import SalesInvoice
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services.discount_report import DiscountReportService
from app.sales_order.models import SalesOrder
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services.sales_return_service import SalesReturnService
from tests.unit.test_order_bill_discount_reaches_the_bill import DAY, _Trade
from tests.unit.test_promotion_budgets import TWO_PLUS_ONE, _offer
from tests.unit.test_promotion_references import _stored_gift_offer

D = Decimal


class _Shop(_Trade):
    """A firm selling at 100.00 under a 10% offer and a buy 2 get 1."""

    def __init__(self, *, counter: bool = False) -> None:
        """Publish both offers, each with the check's budget."""
        super().__init__(counter=counter)
        self.money: Promotion = _offer(self.setup, code="SCHEME", value="100")
        self.goods: Promotion = _offer(
            self.setup, code="FREEC", action=TWO_PLUS_ONE, free="5", priority=20
        )

    def four(self) -> SalesOrder:
        """Approve an order of 4 at 100.00: 40.00 off and 2 free."""
        return self.order("4", unit_price="100")

    def room(self, offer: Promotion) -> BudgetRoom:
        """Return what the offer's budgets count as given."""
        self.session.expire_all()
        return budget_rooms(self.session, [offer], firm_id=self.firm_id)[offer.id]

    def claims(self, order: SalesOrder) -> dict[str, PromotionRedemption]:
        """Return the order's claims by offer code, whatever their status."""
        self.session.expire_all()
        codes = {self.money.id: "SCHEME", self.goods.id: "FREEC"}
        return {
            codes[row.promotion_id]: row
            for row in self.session.scalars(
                select(PromotionRedemption).where(
                    PromotionRedemption.document_id == order.id,
                    PromotionRedemption.is_deleted.is_(False),
                )
            )
        }

    def close(self, order: SalesOrder) -> None:
        """Close the order short."""
        self.orders.close_order(order.id, firm_scope=self.firm_id, actor_id=self.actor)

    def audits(self, action: str) -> list[AuditLog]:
        """Return the audit rows written for one action."""
        return list(
            self.session.scalars(select(AuditLog).where(AuditLog.action == action))
        )


def test_closing_an_order_short_keeps_what_was_delivered_and_frees_the_rest() -> None:
    """40.00 and 2 claimed, 20.00 and 1 delivered: 20.00 and 1 go back."""
    shop = _Shop()
    order = shop.four()
    assert (
        shop.room(shop.money).amount_claimed,
        shop.room(shop.goods).free_claimed,
    ) == (
        D("40.0000"),
        D("2.0000"),
    )
    note = shop.note(order, "2")
    assert shop.note_line(note).free_quantity == D("1.0000")
    with pytest.raises(ValidationError, match="cannot be cancelled while"):
        shop.orders.cancel_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    shop.session.rollback()

    shop.close(order)

    assert (
        shop.room(shop.money).amount_claimed,
        shop.room(shop.money).amount_left,
    ) == (
        D("20.0000"),
        D("80.0000"),
    )
    assert (shop.room(shop.goods).free_claimed, shop.room(shop.goods).free_left) == (
        D("1.0000"),
        D("4.0000"),
    )
    claims = shop.claims(order)
    assert {
        code: (
            row.status,
            row.benefit_amount,
            row.released_benefit_amount,
            row.free_quantity,
            row.released_free_quantity,
        )
        for code, row in claims.items()
    } == {
        "SCHEME": ("CLAIMED", D("40.0000"), D("20.0000"), D("0.0000"), D("0.0000")),
        "FREEC": ("CLAIMED", D("0.0000"), D("0.0000"), D("2.0000"), D("1.0000")),
    }
    assert all(row.released_at is not None for row in claims.values())
    released = shop.audits("promotion_redemption.released")
    assert {row.entity_id for row in released} == {row.id for row in claims.values()}
    assert {str(row.after_data["reason"]) for row in released} == {
        "The order was closed short."
    }


def test_an_order_closed_with_nothing_shipped_gives_its_claims_back_whole() -> None:
    """A note still a draft delivered nothing: both claims are reversed."""
    shop = _Shop()
    order = shop.four()
    shop.note(order, "2", ship=False)

    shop.close(order)

    assert {code: row.status for code, row in shop.claims(order).items()} == {
        "SCHEME": "REVERSED",
        "FREEC": "REVERSED",
    }
    assert (
        shop.room(shop.money).amount_claimed,
        shop.room(shop.goods).free_claimed,
    ) == (
        D("0"),
        D("0"),
    )
    assert len(shop.audits("promotion_redemption.reversed")) == 2


def test_an_order_closed_after_everything_shipped_releases_nothing() -> None:
    """All 4 delivered: the claims stand whole and no audit row is written."""
    shop = _Shop()
    order = shop.four()
    shop.note(order, "4")

    shop.close(order)

    assert (
        shop.room(shop.money).amount_claimed,
        shop.room(shop.goods).free_claimed,
    ) == (
        D("40.0000"),
        D("2.0000"),
    )
    assert shop.audits("promotion_redemption.released") == []
    assert all(row.released_at is None for row in shop.claims(order).values())


def test_one_use_stays_used_when_part_was_delivered_and_frees_when_none_was() -> None:
    """A count limit is a claim made, not an amount: a part delivery used it."""
    shop = _Shop()
    shop.money.max_redemptions = 1
    shop.session.commit()
    first = shop.four()
    shop.note(first, "2")
    shop.close(first)

    second = shop.four()
    assert "SCHEME" not in shop.claims(second), "the one use was used"

    other = _Shop()
    other.money.max_redemptions = 1
    other.session.commit()
    unshipped = other.four()
    other.note(unshipped, "2", ship=False)
    other.close(unshipped)

    again = other.four()
    assert other.claims(again)["SCHEME"].status == "CLAIMED"


def test_the_reports_read_what_the_budget_reads_after_a_short_close() -> None:
    """Performance, the register and discount-by-promotion all say 20 and 1."""
    shop = _Shop()
    order = shop.four()
    shop.note(order, "2")
    shop.close(order)
    reports = PromotionReportService(shop.session)

    performance = {
        row.code: row for row in reports.performance_report(firm_scope=shop.firm_id)
    }
    assert (
        performance["SCHEME"].benefit_amount,
        performance["SCHEME"].remaining_benefit_amount,
        performance["SCHEME"].claimed_count,
    ) == (D("20.0000"), D("80.0000"), 1)
    assert (
        performance["FREEC"].free_quantity,
        performance["FREEC"].remaining_free_quantity,
    ) == (D("1.0000"), D("4.0000"))
    register = {
        row.promotion_code: row
        for row in reports.redemption_report(firm_scope=shop.firm_id)
    }
    assert (
        register["SCHEME"].benefit_amount,
        register["SCHEME"].claimed_benefit_amount,
        register["FREEC"].free_quantity,
        register["FREEC"].claimed_free_quantity,
    ) == (D("20.0000"), D("40.0000"), D("1.0000"), D("2.0000"))
    by_offer = {
        row.code: row
        for row in DiscountReportService(shop.session).by_promotion(
            shop.firm_id, ReportWindow(None, None, 1, 100)
        )
    }
    assert (by_offer["SCHEME"].benefit_amount, by_offer["SCHEME"].free_quantity) == (
        D("20.00"),
        D("0"),
    )
    assert (by_offer["FREEC"].benefit_amount, by_offer["FREEC"].free_quantity) == (
        D("0.00"),
        D("1.0000"),
    )
    listed = {
        row.code: row
        for row in PromotionCrudService(shop.session).promotion_responses(
            [shop.money, shop.goods]
        )
    }
    assert (
        listed["SCHEME"].benefit_amount_claimed,
        listed["FREEC"].free_quantity_claimed,
    ) == (D("20.0000"), D("1.0000"))


# ---- D-PRC-32 --------------------------------------------------------------


def _typed_free_order(shop: _Shop) -> SalesOrder:
    """Approve an order of 4 with one free unit typed by hand."""
    return shop.order("4", unit_price="100", free_quantity="1")


def test_an_offer_whose_free_goods_were_typed_over_records_no_claim() -> None:
    """Buy 2 get 1 matched, the line said 1 free by hand: nothing claimed."""
    shop = _Shop()
    shop.goods.max_redemptions_per_customer = 1
    shop.session.commit()

    typed = _typed_free_order(shop)

    assert "FREEC" not in shop.claims(typed)
    line = shop.order_line(typed)
    assert (line.free_quantity, line.free_promotion_id) == (D("1.0000"), None)
    # The customer's one turn was not used up by an offer that gave nothing.
    untyped = shop.four()
    assert shop.claims(untyped)["FREEC"].free_quantity == D("2.0000")


def test_the_trace_says_why_an_offer_that_matched_gave_nothing() -> None:
    """Not applied, with the reason, and not in what the document took."""
    shop = _Shop()

    outcome = PromotionService(shop.session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=DAY,
            customer_id=shop.setup.customer.id,
            lines=[
                PromotionLineRequest(
                    line_number=1,
                    product_id=shop.setup.product.id,
                    quantity=D("4"),
                    gross=D("400"),
                    free_typed=True,
                )
            ],
        ),
        firm_scope=shop.firm_id,
    )

    assert [item.code for item in outcome.applied] == ["SCHEME"]
    reasons = {item.code: (item.matched, item.reason) for item in outcome.decisions}
    assert reasons["FREEC"] == (
        False,
        "A free quantity was typed on the line this offer matched, so the "
        "offer's own was not given and nothing is claimed.",
    )


def test_an_offer_whose_gift_is_gone_records_no_claim() -> None:
    """The gift is no product of the firm's: nothing given, nothing claimed."""
    shop = _Shop()
    shop.money.status = shop.goods.status = "INACTIVE"
    shop.session.commit()
    gone = _stored_gift_offer(shop.setup, UUID(int=1))

    order = shop.order("9", unit_price="100")

    shop.session.expire_all()
    assert (
        shop.session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.document_id == order.id
            )
        ).all()
        == []
    )
    outcome = PromotionService(shop.session).evaluate(
        PromotionEvaluationRequest(
            transaction_type="SALES_ORDER",
            transaction_date=DAY,
            customer_id=shop.setup.customer.id,
            lines=[
                PromotionLineRequest(
                    line_number=1,
                    product_id=shop.setup.product.id,
                    quantity=D("9"),
                    gross=D("900"),
                )
            ],
        ),
        firm_scope=shop.firm_id,
    )
    assert outcome.applied == []
    said = [item.reason for item in outcome.decisions if item.code == gone.code]
    assert said == [
        "This offer gave nothing on this document, so nothing is claimed.",
        "The product this offer gives away is not one of this firm's "
        "products any more, so nothing was given.",
    ]


# ---- D-PRC-34 --------------------------------------------------------------


class _Counter(_Shop):
    """The same shop billing at the counter, with 3 free units to give."""

    def __init__(self) -> None:
        """Turn the stages off and cap the free goods at 3."""
        super().__init__(counter=True)
        self.money.status = "INACTIVE"
        self.goods.max_free_quantity = D("3")
        self.session.commit()

    def sell(self, quantity: str) -> SalesInvoice:
        """Bill a quantity at 100.00 and approve the bill."""
        row = self.bills.create_invoice(
            SalesInvoiceCreate(
                customer_id=self.setup.customer.id,
                invoice_date=DAY,
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=self.setup.product.id,
                        line_number=1,
                        current_invoice_quantity=D(quantity),
                        unit_price=D("100"),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        self.bills.approve_invoice(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()
        return self.bills.get_invoice(row.id, firm_scope=self.firm_id)

    def free_unit_back(self, bill: SalesInvoice) -> None:
        """Return one unit of the bill's line, stated as the free one."""
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
                        current_return_quantity=D("1"),
                        free_quantity=D("1"),
                    )
                ],
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )
        service.approve_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        service.complete_return(row.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()


def test_a_free_unit_that_came_back_is_netted_in_every_report() -> None:
    """2 + 1 given, 1 back, 1 given again: 3 of 3 everywhere, never 4."""
    counter = _Counter()
    first = counter.sell("4")
    counter.sell("2")
    assert counter.room(counter.goods).free_claimed == D("3.0000")
    counter.free_unit_back(first)
    assert counter.room(counter.goods).free_left == D("1.0000")
    counter.sell("2")
    reports = PromotionReportService(counter.session)

    assert (
        counter.room(counter.goods).free_claimed,
        counter.room(counter.goods).free_left,
    ) == (D("3.0000"), D("0.0000"))
    (performance,) = (
        row
        for row in reports.performance_report(firm_scope=counter.firm_id)
        if row.code == "FREEC"
    )
    assert (
        performance.free_quantity,
        performance.max_free_quantity,
        performance.remaining_free_quantity,
        performance.claimed_count,
    ) == (D("3.0000"), D("3.0000"), D("0.0000"), 3)
    register = reports.redemption_report(firm_scope=counter.firm_id)
    assert sorted(row.free_quantity for row in register) == [
        D("1.0000"),
        D("1.0000"),
        D("1.0000"),
    ]
    assert sorted(row.claimed_free_quantity for row in register) == [
        D("1.0000"),
        D("1.0000"),
        D("2.0000"),
    ]
    (by_offer,) = DiscountReportService(counter.session).by_promotion(
        counter.firm_id, ReportWindow(None, None, 1, 100)
    )
    assert (by_offer.code, by_offer.claims, by_offer.free_quantity) == (
        "FREEC",
        3,
        D("3.0000"),
    )


def test_a_counter_bill_priced_again_without_its_offer_leaves_no_reversal() -> None:
    """Its claim was pending, never made: nothing reads as given back."""
    counter = _Counter()
    counter.goods.max_free_quantity = D("2")
    counter.session.commit()
    draft = counter.bills.create_invoice(
        SalesInvoiceCreate(
            customer_id=counter.setup.customer.id,
            invoice_date=DAY,
            lines=[
                SalesInvoiceLineWrite(
                    product_id=counter.setup.product.id,
                    line_number=1,
                    current_invoice_quantity=D("4"),
                    unit_price=D("100"),
                )
            ],
        ),
        firm_id=counter.firm_id,
        actor_id=uuid4(),
    )
    counter.session.expire_all()
    # Another bill takes the two free units the draft was priced with.
    counter.sell("4")

    counter.resave(counter.bills.get_invoice(draft.id, firm_scope=counter.firm_id), "4")

    (performance,) = (
        row
        for row in PromotionReportService(counter.session).performance_report(
            firm_scope=counter.firm_id
        )
        if row.code == "FREEC"
    )
    assert (
        performance.claimed_count,
        performance.pending_count,
        performance.reversed_count,
    ) == (1, 0, 0)
