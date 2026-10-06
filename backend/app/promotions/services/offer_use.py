"""What a claim on an offer actually gave: one figure for every reader.

A redemption row says what a document **claimed** when it was approved:
``benefit_amount`` in money and ``free_quantity`` in free units. Two things
happen afterwards that make what was *given* less than that:

* the order is closed short, and the part never delivered is released
  (``released_benefit_amount``, ``released_free_quantity``; D-PRC-28);
* free goods the offer gave come back on a completed sales return (D-PRC-8);
* goods sold under the offer come back, or their bill is credited, and the
  discount on them was not given after all (D-PRC-45).

Five readers state an offer's use -- the offer itself and its budgets
(`budget_rooms`), the performance report, the redemptions report, the coupon
report and the discount-by-promotion report -- and each used to do its own
sum, so the performance report read 4 free units beside a budget that had
counted 3 (D-PRC-34). They all read `claims_given` now: one statement, one
row per claim, with the two netted figures on it. A caller groups it as it
likes and can never net differently from its neighbour.

Free units come back to the claim that gave them: the order line names the
offer (``free_promotion_id``) and the claim names the order, so a return is
netted from that order's claim on that offer and from no other.

Money comes back by the share of the order's discount that its bills passed
on and completed returns or approved credit notes then took back
(`bill_discounts.discount_came_back`) -- the statement a claim on a principal
reads, so an offer's budget, its reports and the principal's claim all say
what the customer kept. A sale approved and not yet billed has had nothing
come back, so its claim stands whole, as it did.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.promotions.models import Promotion, PromotionRedemption


def offer_took_off(
    *,
    discount_source: str | None,
    discount_amount: object,
    bill_discount_amount: object,
    bill_discount_source: str | None,
) -> Decimal:
    """Return what the firm's offers took off one order line.

    An order line records one discount and where it came from, and its share
    of the bill discount; the order says where that came from. What an offer
    gave is the line discount where the line says ``promotion`` and the
    line's share of the bill discount where the order says ``promotion`` --
    a discount somebody typed, a price list's or a customer's standing rate
    is not an offer's. One reading for the two things that pro-rate a claim:
    the part of it an order closed short gives back, and the part of it a
    bill passed on for a principal to pay.
    """
    took = Decimal("0")
    if discount_source == "promotion":
        took += Decimal(str(discount_amount or 0))
    if bill_discount_source == "promotion":
        took += Decimal(str(bill_discount_amount or 0))
    return took


def claims_given(
    firm_id: UUID,
    *where: ColumnElement[bool],
    groups: set[UUID] | None = None,
) -> Select[Any]:
    """Select every live claim of the firm with what it gave after netting.

    Columns: ``id``, ``promotion_id``, ``version_group_id``, ``coupon_id``,
    ``customer_id``, ``status``, ``redeemed_on``, ``benefit_given`` (claimed
    less released less the share returned or credited, never below zero) and
    ``free_given`` (claimed less released less returned, never below zero).
    Every status is returned; a caller counting an offer's use filters on
    CLAIMED.

    Args:
        firm_id: The firm whose claims to read.
        *where: Further conditions on ``PromotionRedemption`` or ``Promotion``.
        groups: The offers (version groups) wanted. Narrows the returns read
            as well as the claims, so pricing one budgeted offer does not sum
            every return the firm ever took.

    Returns:
        The statement, for the caller to run, wrap or group.

    """
    # Imported here: these modules' services import the promotion engine.
    from app.delivery_note.models import DeliveryNoteLine
    from app.promotions.services.bill_discounts import discount_came_back
    from app.sales_order.models import SalesOrderLine
    from app.sales_return.free_goods import free_goods_returned
    from app.sales_return.models import SalesReturn, SalesReturnLine

    came_back = (
        free_goods_returned(
            SalesOrderLine.sales_order_id.label("order_id"),
            SalesOrderLine.free_promotion_id.label("promotion_id"),
            func.sum(SalesReturnLine.free_quantity).label("units"),
        )
        .join(
            SalesOrderLine,
            SalesOrderLine.id == DeliveryNoteLine.sales_order_line_id,
        )
        .where(
            SalesReturn.firm_id == firm_id,
            SalesOrderLine.free_promotion_id.is_not(None),
        )
        .group_by(SalesOrderLine.sales_order_id, SalesOrderLine.free_promotion_id)
    )
    if groups is not None:
        came_back = came_back.where(
            SalesOrderLine.free_promotion_id.in_(
                select(Promotion.id).where(
                    Promotion.firm_id == firm_id,
                    Promotion.version_group_id.in_(groups),
                )
            )
        )
    returned = came_back.subquery("free_returned")
    free_left = (
        PromotionRedemption.free_quantity
        - PromotionRedemption.released_free_quantity
        - func.coalesce(returned.c.units, 0)
    )
    claimed_orders = (
        select(PromotionRedemption.document_id)
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .where(
            PromotionRedemption.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            PromotionRedemption.document_type == "SALES_ORDER",
            PromotionRedemption.status == "CLAIMED",
            PromotionRedemption.benefit_amount > 0,
        )
    )
    if groups is not None:
        claimed_orders = claimed_orders.where(Promotion.version_group_id.in_(groups))
    money_back = discount_came_back(
        firm_id, SalesOrderLine.sales_order_id.in_(claimed_orders)
    ).subquery("money_returned")
    # Rounded where it is worked, so two readers summing the same claims
    # cannot part by a fraction of a paisa.
    money_left = (
        PromotionRedemption.benefit_amount
        - PromotionRedemption.released_benefit_amount
        - func.round(
            PromotionRedemption.benefit_amount * func.coalesce(money_back.c.share, 0),
            4,
        )
    )
    statement = (
        select(
            PromotionRedemption.id.label("id"),
            PromotionRedemption.promotion_id.label("promotion_id"),
            Promotion.version_group_id.label("version_group_id"),
            PromotionRedemption.coupon_id.label("coupon_id"),
            PromotionRedemption.customer_id.label("customer_id"),
            PromotionRedemption.status.label("status"),
            PromotionRedemption.redeemed_on.label("redeemed_on"),
            case((money_left > 0, money_left), else_=0).label("benefit_given"),
            case((free_left > 0, free_left), else_=0).label("free_given"),
        )
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .outerjoin(
            returned,
            and_(
                returned.c.order_id == PromotionRedemption.document_id,
                returned.c.promotion_id == PromotionRedemption.promotion_id,
            ),
        )
        .outerjoin(
            money_back,
            and_(
                money_back.c.order_id == PromotionRedemption.document_id,
                PromotionRedemption.document_type == "SALES_ORDER",
            ),
        )
        .where(
            PromotionRedemption.firm_id == firm_id,
            Promotion.firm_id == firm_id,
            PromotionRedemption.is_deleted.is_(False),
            *where,
        )
    )
    if groups is not None:
        statement = statement.where(Promotion.version_group_id.in_(groups))
    return statement
