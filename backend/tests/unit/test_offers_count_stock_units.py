"""An offer and a supplier's scheme count stock units, whatever unit a line is in.

D-PRC-39, from the third pricing check: under "buy 10 get 1" an order of
2 BOX of 12 got nothing free and no claim, the same goods typed as 24 PIECE
got 2 free, and 12 BOX got 1 BOX. A price list's breaks and a per-unit
commission already counted stock units; the promotion engine and the
supplier schemes counted the figure as typed.

One answer for both now. A quantity condition and a "buy X get Y" threshold
count **stock units**, and the free goods are a number of stock units: on
the line where they are a whole number of the line's own unit, otherwise on
a free line of the same product in its stock unit -- so 2 BOX earn 2 PIECE,
26 pieces leave, and the claim and the budget count 2.

Every case runs on a request-shaped session (autoflush off).
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.utils.pricing import resolve_supplier_free_goods
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.inventory.models import InventoryRecord
from app.promotions.models import Promotion, PromotionCondition, PromotionRedemption
from app.promotions.schemas import (
    PromotionActionType,
    PromotionEvaluationRequest,
    PromotionLineRequest,
)
from app.promotions.services import PromotionService
from app.promotions.services.promotion_service import budget_rooms
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.quotation.models import SalesQuotationLine
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderUpdate
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services.sales_return_service import SalesReturnService
from app.supplier_schemes.models import SupplierScheme
from app.supplier_schemes.schemas import SupplierSchemeCreate
from app.supplier_schemes.services import SupplierSchemeService
from tests.unit.test_lines_in_another_unit import DAY, _Shop
from tests.unit.test_promotion_budgets import _offer
from tests.unit.test_purchase_lines_in_another_unit import _Buyer

D = Decimal
TEN_PLUS_ONE = (
    PromotionActionType.FREE_QUANTITY,
    {"buy_quantity": "10", "free_quantity": "1"},
)
TWELVE_PLUS_TWELVE = (
    PromotionActionType.FREE_QUANTITY,
    {"buy_quantity": "12", "free_quantity": "12"},
)


class _Offers(_Shop):
    """The check's firm: a product kept in pieces, 12 to a box, 100.00 each."""

    def __init__(self, action: tuple[PromotionActionType, dict[str, object]]) -> None:
        """Publish one free-goods offer, uncapped."""
        super().__init__()
        self.offer: Promotion = _offer(self.setup, code="B10G1", action=action)

    def lines(self, order: SalesOrder) -> list[SalesOrderLine]:
        """Return the order's lines in order, as stored."""
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(SalesOrderLine)
                .where(
                    SalesOrderLine.sales_order_id == order.id,
                    SalesOrderLine.is_deleted.is_(False),
                )
                .order_by(SalesOrderLine.line_number)
            )
        )

    def claim(self, order: SalesOrder) -> PromotionRedemption | None:
        """Return the order's claim on the offer, pending or made."""
        self.session.expire_all()
        return self.session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.document_id == order.id,
                PromotionRedemption.is_deleted.is_(False),
            )
        ).one_or_none()

    def approve(self, order: SalesOrder) -> None:
        """Approve the order."""
        self.orders.approve_order(
            order.id, firm_scope=self.firm_id, actor_id=self.actor
        )

    def on_hand(self) -> Decimal:
        """Return how much of the product the firm holds."""
        self.session.expire_all()
        return D(
            str(
                sum(
                    row.current_quantity
                    for row in self.session.scalars(
                        select(InventoryRecord).where(
                            InventoryRecord.product_id == self.setup.product.id
                        )
                    )
                )
            )
        )


# ---- customer offers -------------------------------------------------------


def test_two_boxes_of_twelve_earn_two_free_pieces_on_a_line_of_their_own() -> None:
    """The check's order: 2 BOX is 24 bought, 2 free, stated as 2 PIECE."""
    shop = _Offers(TEN_PLUS_ONE)

    order = shop.order(sales_uom_id=shop.box)

    boxes, free = shop.lines(order)
    assert (boxes.quantity, boxes.free_quantity, boxes.base_quantity) == (
        D("2.0000"),
        D("0.0000"),
        D("24.0000"),
    )
    assert boxes.free_promotion_id is None
    assert (free.product_id, free.quantity, free.free_quantity) == (
        shop.setup.product.id,
        D("0.0000"),
        D("2.0000"),
    )
    assert (free.sales_uom_id, free.inventory_uom_id) == (shop.piece, shop.piece)
    assert (free.base_quantity, free.net_amount) == (D("2.0000"), D("0.0000"))
    assert free.free_promotion_id == shop.offer.id
    assert free.description == "Free with B10G1"
    claim = shop.claim(order)
    assert claim is not None
    assert (claim.status, claim.free_quantity) == ("PENDING", D("2.0000"))
    # The order charges for 2 boxes and nothing else.
    assert order.subtotal == D("2400.0000")


def test_the_same_goods_typed_as_pieces_earn_the_same_two() -> None:
    """24 PIECE: 2 free on the line itself, and the claim counts 2."""
    shop = _Offers(TEN_PLUS_ONE)

    order = shop.order(quantity="24", sales_uom_id=shop.piece)

    (line,) = shop.lines(order)
    assert (line.free_quantity, line.base_quantity) == (D("2.0000"), D("26.0000"))
    assert line.free_promotion_id == shop.offer.id
    claim = shop.claim(order)
    assert claim is not None and claim.free_quantity == D("2.0000")


def test_twelve_boxes_earn_fourteen_pieces_not_one_box() -> None:
    """144 bought earn 14, as 144 PIECE would; 14 is no whole number of boxes."""
    shop = _Offers(TEN_PLUS_ONE)

    order = shop.order(quantity="12", sales_uom_id=shop.box)

    boxes, free = shop.lines(order)
    assert (boxes.free_quantity, free.free_quantity) == (D("0.0000"), D("14.0000"))
    assert free.sales_uom_id == shop.piece
    claim = shop.claim(order)
    assert claim is not None and claim.free_quantity == D("14.0000")


def test_free_goods_that_make_whole_boxes_stay_on_the_box_line() -> None:
    """Buy 12 get 12: 2 BOX earn 24 pieces, which is 2 BOX on the line."""
    shop = _Offers(TWELVE_PLUS_TWELVE)

    order = shop.order(sales_uom_id=shop.box)

    (line,) = shop.lines(order)
    assert (line.quantity, line.free_quantity, line.base_quantity) == (
        D("2.0000"),
        D("2.0000"),
        D("48.0000"),
    )
    assert line.free_promotion_id == shop.offer.id
    # The claim and the budget count stock units: 24, not 2.
    claim = shop.claim(order)
    assert claim is not None and claim.free_quantity == D("24.0000")


def test_a_quantity_condition_counts_the_pieces_in_a_box() -> None:
    """A line of 20 or more: that holds for 2 BOX of 12 and not for 1."""
    shop = _Offers(TEN_PLUS_ONE)
    shop.session.add(
        PromotionCondition(
            firm_id=shop.firm_id,
            promotion_id=shop.offer.id,
            sequence=1,
            field_key="line_quantity",
            operator="GREATER_OR_EQUAL",
            value_number=D("20"),
        )
    )
    shop.session.commit()

    def simulate(quantity: str, factor: str) -> tuple[bool, Decimal]:
        """Return whether the offer applied, and the free units it gave."""
        outcome = PromotionService(shop.session).evaluate(
            PromotionEvaluationRequest(
                transaction_type="SALES_ORDER",
                transaction_date=DAY,
                lines=[
                    PromotionLineRequest(
                        line_number=1,
                        product_id=shop.setup.product.id,
                        quantity=D(quantity),
                        stock_factor=D(factor),
                        gross=D("100"),
                    )
                ],
            ),
            firm_scope=shop.firm_id,
        )
        shop.session.rollback()
        given = sum((row.free_quantity for row in outcome.applied), D("0"))
        return bool(outcome.applied), given

    assert simulate("2", "12") == (True, D("2"))
    assert simulate("1", "12") == (False, D("0"))
    assert simulate("24", "1") == (True, D("2"))
    assert simulate("2", "1") == (False, D("0"))


def test_a_free_unit_budget_counts_stock_units() -> None:
    """A budget of 3: 2 BOX take 2, and the next 2 BOX would take 2 of the 1 left."""
    shop = _Offers(TEN_PLUS_ONE)
    shop.offer.max_free_quantity = D("3")
    shop.session.commit()
    first = shop.order(sales_uom_id=shop.box)
    shop.approve(first)

    room = budget_rooms(shop.session, [shop.offer], firm_id=shop.firm_id)[shop.offer.id]
    assert (room.free_claimed, room.free_left) == (D("2.0000"), D("1.0000"))
    second = shop.order(sales_uom_id=shop.box)
    assert len(shop.lines(second)) == 1, "the offer is not quoted in part"
    assert shop.claim(second) is None


def test_the_note_of_a_box_order_ships_twenty_six_pieces() -> None:
    """Both lines delivered: 24 charged and 2 free leave the shelf."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    shop.approve(order)
    boxes, free = shop.lines(order)
    before = shop.on_hand()
    notes = DeliveryNoteService(shop.session)

    note = notes.create_note(
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
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    notes.approve_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes.dispatch_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    shop.session.expire_all()
    shipped = {
        row.line_number: (row.free_quantity, row.delivered_quantity)
        for row in shop.session.scalars(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
    }
    assert shipped == {
        1: (D("0.0000"), D("24.0000")),
        2: (D("2.0000"), D("2.0000")),
    }
    assert before - shop.on_hand() == D("26.0000")
    assert shop.orders.get_order(order.id, firm_scope=shop.firm_id).status == (
        "DELIVERED"
    )


def test_saving_the_order_again_with_its_free_line_does_not_double_it() -> None:
    """The editor sends the free line back; the engine does not add a second."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    boxes, free = shop.lines(order)

    shop.orders.update_order(
        order.id,
        SalesOrderUpdate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "branch_id": shop.setup.branch.id,
                "warehouse_id": shop.setup.warehouse.id,
                "order_date": DAY,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": boxes.product_id,
                        "quantity": "2",
                        "sales_uom_id": shop.box,
                    },
                    {
                        "line_number": 2,
                        "product_id": free.product_id,
                        "quantity": "0",
                        "free_quantity": "2",
                        "unit_price": "0",
                        "sales_uom_id": shop.piece,
                        "inventory_uom_id": shop.piece,
                    },
                ],
            }
        ),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )

    assert [(row.quantity, row.free_quantity) for row in shop.lines(order)] == [
        (D("2.0000"), D("0.0000")),
        (D("0.0000"), D("2.0000")),
    ]


def _save_again(
    shop: _Offers, order: SalesOrder, lines: list[dict[str, object]]
) -> None:
    """Save the draft again with exactly these lines."""
    shop.orders.update_order(
        order.id,
        SalesOrderUpdate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "branch_id": shop.setup.branch.id,
                "warehouse_id": shop.setup.warehouse.id,
                "order_date": DAY,
                "lines": lines,
            }
        ),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )


def _as_read(shop: _Offers, order: SalesOrder) -> list[dict[str, object]]:
    """Return the order's lines the way a client echoing the read sends them.

    Every figure the read gave, the "0 free" of the box line included --
    the fourth pricing check's request (D-PRC-48).
    """
    return [
        {
            "line_number": row.line_number,
            "product_id": row.product_id,
            "quantity": row.quantity,
            "free_quantity": row.free_quantity,
            "unit_price": row.unit_price,
            "sales_uom_id": row.sales_uom_id,
            "inventory_uom_id": row.inventory_uom_id,
        }
        for row in shop.lines(order)
    ]


def _free_line_and_claim(
    shop: _Offers, order: SalesOrder
) -> tuple[list[tuple[Decimal, Decimal, UUID | None]], Decimal | None]:
    """Return each line's (sold, free, offer named) and the claim's free units."""
    claim = shop.claim(order)
    return (
        [
            (row.quantity, row.free_quantity, row.free_promotion_id)
            for row in shop.lines(order)
        ],
        None if claim is None else claim.free_quantity,
    )


def test_an_order_sent_back_as_read_keeps_its_offer_named_and_claimed() -> None:
    """D-PRC-48: both lines echoed left the goods free and the offer unnamed."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    free_line_id = shop.lines(order)[1].id

    _save_again(shop, order, _as_read(shop, order))

    assert _free_line_and_claim(shop, order) == (
        [
            (D("2.0000"), D("0.0000"), None),
            (D("0.0000"), D("2.0000"), shop.offer.id),
        ],
        D("2.0000"),
    )
    # Reconciled on its line number, not deleted and inserted again.
    assert shop.lines(order)[1].id == free_line_id


def test_an_order_sent_back_as_read_with_more_boxes_earns_the_offer_afresh() -> None:
    """3 BOX is 36 bought and 3 free: the echoed "2 free" is not kept."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    lines = _as_read(shop, order)
    lines[0]["quantity"] = "3"

    _save_again(shop, order, lines)

    assert _free_line_and_claim(shop, order) == (
        [
            (D("3.0000"), D("0.0000"), None),
            (D("0.0000"), D("3.0000"), shop.offer.id),
        ],
        D("3.0000"),
    )


def test_an_order_saved_again_without_its_free_line_is_given_it_again() -> None:
    """The desktop's save: the box line alone, saying nothing about free goods."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    box_line = {
        "line_number": 1,
        "product_id": shop.setup.product.id,
        "quantity": "2",
        "sales_uom_id": shop.box,
    }

    _save_again(shop, order, [box_line])
    _save_again(shop, order, [box_line])

    assert _free_line_and_claim(shop, order) == (
        [
            (D("2.0000"), D("0.0000"), None),
            (D("0.0000"), D("2.0000"), shop.offer.id),
        ],
        D("2.0000"),
    )


def test_a_zero_typed_without_the_free_line_still_refuses_the_offer() -> None:
    """D-SELL-41 stands: "0 free" on the box line alone is a refusal."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)

    _save_again(
        shop,
        order,
        [
            {
                "line_number": 1,
                "product_id": shop.setup.product.id,
                "quantity": "2",
                "free_quantity": "0",
                "sales_uom_id": shop.box,
            }
        ],
    )

    assert _free_line_and_claim(shop, order) == (
        [(D("2.0000"), D("0.0000"), None)],
        None,
    )


def test_an_echoed_order_cannot_get_round_the_offers_budget() -> None:
    """A budget of 2 free units gave 4: the echoed free line escaped the count."""
    shop = _Offers(TEN_PLUS_ONE)
    shop.offer.max_free_quantity = D("2")
    shop.session.commit()
    first = shop.order(sales_uom_id=shop.box)
    second = shop.order(sales_uom_id=shop.box)
    echoed = _as_read(shop, second)
    assert len(echoed) == 2, "both drafts were quoted the offer"
    shop.approve(first)

    _save_again(shop, second, echoed)

    # The budget is spent, so the order is priced without the offer.
    assert _free_line_and_claim(shop, second) == (
        [(D("2.0000"), D("0.0000"), None)],
        None,
    )
    shop.approve(second)
    room = budget_rooms(shop.session, [shop.offer], firm_id=shop.firm_id)[shop.offer.id]
    assert (room.free_claimed, room.free_left) == (D("2.0000"), D("0.0000"))


def test_free_units_on_the_line_itself_sent_back_as_read_stay_the_offers() -> None:
    """24 PIECE with the offer's 2 free: echoed, the 2 stayed and the claim went."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(quantity="24", sales_uom_id=shop.piece)

    _save_again(shop, order, _as_read(shop, order))

    assert _free_line_and_claim(shop, order) == (
        [(D("24.0000"), D("2.0000"), shop.offer.id)],
        D("2.0000"),
    )
    # A figure that is not the offer's is typed, and stands as typed.
    lines = _as_read(shop, order)
    lines[0]["free_quantity"] = "5"
    _save_again(shop, order, lines)
    assert _free_line_and_claim(shop, order)[0] == [(D("24.0000"), D("5.0000"), None)]


def test_a_free_line_a_person_typed_stays_theirs_when_saved_again() -> None:
    """No offer is named on a typed free-only line, so it is never dropped."""
    shop = _Offers(TEN_PLUS_ONE)
    order = shop.order(sales_uom_id=shop.box)
    typed = _as_read(shop, order)
    typed[1]["free_quantity"] = "5"
    typed[1]["line_number"] = 3
    # Line 3 is new to the order: a free-only line somebody added by hand.
    _save_again(shop, order, [typed[0] | {"free_quantity": None}, typed[1]])
    assert [
        (row.line_number, row.free_quantity, row.free_promotion_id)
        for row in shop.lines(order)
    ] == [(1, D("0.0000"), None), (3, D("5.0000"), None)]

    _save_again(shop, order, _as_read(shop, order))

    assert [
        (row.line_number, row.free_quantity, row.free_promotion_id)
        for row in shop.lines(order)
    ] == [(1, D("0.0000"), None), (3, D("5.0000"), None)]


def test_a_quotation_by_the_box_shows_the_two_free_pieces() -> None:
    """A quotation quotes what the order will give: 2 PIECE free, claiming none."""
    shop = _Offers(TEN_PLUS_ONE)

    quotation = QuotationService(shop.session).create_quotation(
        QuotationCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "branch_id": shop.setup.branch.id,
                "warehouse_id": shop.setup.warehouse.id,
                "quotation_date": DAY,
                "valid_until": DAY,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": shop.setup.product.id,
                        "quantity": "2",
                        "sales_uom_id": shop.box,
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    shop.session.expire_all()
    boxes, free = shop.session.scalars(
        select(SalesQuotationLine)
        .where(SalesQuotationLine.sales_quotation_id == quotation.id)
        .order_by(SalesQuotationLine.line_number)
    ).all()
    assert (boxes.quantity, boxes.free_quantity) == (D("2.0000"), D("0.0000"))
    assert (free.quantity, free.free_quantity, free.sales_uom_id) == (
        D("0.0000"),
        D("2.0000"),
        shop.piece,
    )
    assert shop.session.scalars(select(PromotionRedemption)).all() == []


# ---- what a claim gave, in stock units -------------------------------------


def _ship(shop: _Offers, order: SalesOrder, quantity: str) -> DeliveryNoteLine:
    """Deliver part of the order's one line, saying nothing about free goods."""
    notes = DeliveryNoteService(shop.session)
    note = notes.create_note(
        DeliveryNoteCreate.model_validate(
            {
                "sales_order_id": order.id,
                "delivery_date": DAY,
                "lines": [
                    {
                        "sales_order_line_id": shop.lines(order)[0].id,
                        "line_number": 1,
                        "current_delivery_quantity": quantity,
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    notes.approve_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes.dispatch_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    shop.session.expire_all()
    return shop.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    ).one()


def _free_given(shop: _Offers) -> Decimal:
    """Return the free units the offer counts as given."""
    shop.session.expire_all()
    rooms = budget_rooms(shop.session, [shop.offer], firm_id=shop.firm_id)
    return rooms[shop.offer.id].free_claimed


def test_a_free_box_that_comes_back_is_twelve_units_off_the_claim() -> None:
    """2 BOX free is 24 claimed; 1 free BOX returned leaves 12 given."""
    shop = _Offers(TWELVE_PLUS_TWELVE)
    order = shop.order(sales_uom_id=shop.box)
    shop.approve(order)
    shipped = _ship(shop, order, "2")
    assert (shipped.free_quantity, shipped.delivered_quantity) == (
        D("2.0000"),
        D("48.0000"),
    )
    assert _free_given(shop) == D("24.0000")
    returns = SalesReturnService(shop.session)

    row = returns.create_return(
        SalesReturnCreate(
            warehouse_id=shop.setup.warehouse.id,
            return_date=DAY,
            lines=[
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=shipped.delivery_note_id,
                    source_document_line_id=shipped.id,
                    line_number=1,
                    current_return_quantity=D("1"),
                    free_quantity=D("1"),
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    returns.approve_return(row.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    returns.complete_return(row.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    assert _free_given(shop) == D("12.0000")


def test_a_short_close_keeps_the_free_boxes_shipped_as_stock_units() -> None:
    """4 BOX earn 4 BOX free (48); 2 shipped with 2 free and closed: 24 kept."""
    shop = _Offers(TWELVE_PLUS_TWELVE)
    order = shop.order(quantity="4", sales_uom_id=shop.box)
    shop.approve(order)
    assert _free_given(shop) == D("48.0000")
    assert _ship(shop, order, "2").free_quantity == D("2.0000")

    shop.orders.close_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    claim = shop.claim(order)
    assert claim is not None
    assert (claim.status, claim.free_quantity, claim.released_free_quantity) == (
        "CLAIMED",
        D("48.0000"),
        D("24.0000"),
    )
    assert _free_given(shop) == D("24.0000")


# ---- supplier schemes ------------------------------------------------------


def test_the_scheme_rule_counts_stock_units_and_gives_whole_line_units() -> None:
    """`resolve_supplier_free_goods`, the one place the figure is worked."""

    def resolve(quantity: str, factor: str, free: str = "1") -> tuple[Decimal, ...]:
        """Return (on the line, of another product, own stock units)."""
        answer = resolve_supplier_free_goods(
            typed=None,
            quantity=D(quantity),
            buy_quantity=D("10"),
            scheme_free_quantity=D(free),
            stock_factor=D(factor),
        )
        return (
            answer.free_quantity,
            answer.other_product_quantity,
            answer.own_stock_quantity,
        )

    # 2 BOX of 12: 24 bought, 2 pieces earned, no whole box.
    assert resolve("2", "12") == (D("0"), D("0"), D("2"))
    # 24 PIECE, and a line with no unit: 2 on the line, as before.
    assert resolve("24", "1") == (D("2"), D("0"), D("0"))
    # 10+6 on 2 BOX: 12 pieces earned is 1 BOX on the line.
    assert resolve("2", "12", "6") == (D("1.0000"), D("0"), D("0"))
    # 1 BOX of 12 under 10+1: 1 piece, on a line of its own.
    assert resolve("1", "12") == (D("0"), D("0"), D("1"))


def _scheme(buyer: _Buyer, *, buy: str = "10", free: str = "1") -> SupplierScheme:
    """Give the buyer's supplier a scheme on the product."""
    return SupplierSchemeService(buyer.session).create(
        SupplierSchemeCreate.model_validate(
            {
                "product_id": buyer.firm.product.id,
                "vendor_id": buyer.firm.vendor.id,
                "buy_quantity": buy,
                "free_quantity": free,
                "valid_from": "2026-04-01",
            }
        ),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )


def _order_lines(buyer: _Buyer, order_id: UUID) -> list[PurchaseOrderLine]:
    """Return a purchase order's lines in order, as stored."""
    buyer.session.expire_all()
    return list(
        buyer.session.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order_id)
            .order_by(PurchaseOrderLine.line_number)
        )
    )


def test_a_purchase_by_the_box_is_offered_its_free_pieces_as_a_line() -> None:
    """2 BOX under 10+1: nothing on the box line, 2 PIECE suggested, kept in PIECE."""
    buyer = _Buyer()
    scheme = _scheme(buyer)
    service = PurchaseService(buyer.session)

    preview = service.preview_order(
        PurchaseOrderCreate.model_validate(buyer.order_payload()),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )

    assert preview.order.lines[0].free_quantity == D("0")
    (suggestion,) = preview.scheme_suggestions
    assert (
        suggestion.line_number,
        suggestion.scheme_id,
        suggestion.free_product_id,
        suggestion.free_quantity,
        suggestion.free_uom_id,
        suggestion.existing_line_number,
    ) == (1, scheme.id, buyer.firm.product.id, D("2"), buyer.piece, None)
    # The client adds the line as it adds another product's gift, naming no
    # unit; the product buys by the BOX, and the free line is still pieces.
    payload = buyer.order_payload()
    payload["lines"].append(  # type: ignore[attr-defined]
        {
            "product_id": buyer.firm.product.id,
            "ordered_quantity": "0",
            "free_quantity": "2",
            "scheme_id": str(scheme.id),
            "warehouse_id": buyer.firm.warehouse.id,
        }
    )
    order = service.create_order(
        PurchaseOrderCreate.model_validate(payload),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    boxes, free = _order_lines(buyer, order.id)
    assert (boxes.purchase_uom_id, boxes.ordered_quantity, boxes.free_quantity) == (
        buyer.box,
        D("2.0000"),
        D("0.0000"),
    )
    assert (free.purchase_uom_id, free.inventory_uom_id) == (buyer.piece, buyer.piece)
    assert (free.ordered_quantity, free.free_quantity, free.net_amount) == (
        D("0.0000"),
        D("2.0000"),
        D("0.0000"),
    )
    assert (free.scheme_id, free.scheme_name) == (scheme.id, "10+1")
    again = service.preview_order(
        PurchaseOrderCreate.model_validate(payload),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    (carried,) = again.scheme_suggestions
    assert (carried.existing_line_number, carried.free_quantity) == (2, D("2"))


@pytest.mark.parametrize(
    ("line", "free"),
    [
        (
            {"ordered_quantity": "24", "purchase_uom_id": "PIECE", "unit_price": "60"},
            "2",
        ),
        ({"ordered_quantity": "2"}, "0"),
    ],
)
def test_a_purchase_line_takes_its_scheme_in_stock_units(
    line: dict[str, str], free: str
) -> None:
    """24 PIECE take 2 on the line; 2 BOX take none there (they are offered)."""
    buyer = _Buyer()
    scheme = _scheme(buyer)
    if line.get("purchase_uom_id") == "PIECE":
        line = line | {"purchase_uom_id": str(buyer.piece)}

    order = buyer.order(approve=False, **line)

    stored = buyer.order_line(order)
    assert stored.free_quantity == D(free)
    assert stored.scheme_id == (scheme.id if free != "0" else None)


def test_scheme_goods_that_make_a_whole_box_go_on_the_box_line() -> None:
    """10+6 on 2 BOX: 12 pieces earned is 1 BOX free, 36 pieces in all."""
    buyer = _Buyer()
    scheme = _scheme(buyer, free="6")

    order = buyer.order(approve=False)

    stored = buyer.order_line(order)
    assert (stored.free_quantity, stored.scheme_id) == (D("1.0000"), scheme.id)
    preview = PurchaseService(buyer.session).preview_order(
        PurchaseOrderCreate.model_validate(buyer.order_payload()),
        firm_id=buyer.firm_id,
        actor_id=buyer.actor,
    )
    assert preview.scheme_suggestions == []
