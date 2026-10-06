"""What a claim on an offer actually gave: one figure for every reader.

A redemption row says what a document **claimed** when it was approved:
``benefit_amount`` in money and ``free_quantity`` in free units. Two things
happen afterwards that make what was *given* less than that:

* the order is closed short, and the part never delivered is released
  (``released_benefit_amount``, ``released_free_quantity``; D-PRC-28);
* free goods the offer gave come back on a completed sales return (D-PRC-8).

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
    less released) and ``free_given`` (claimed less released less returned,
    never below zero). Every status is returned; a caller counting an
    offer's use filters on CLAIMED.

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
    statement = (
        select(
            PromotionRedemption.id.label("id"),
            PromotionRedemption.promotion_id.label("promotion_id"),
            Promotion.version_group_id.label("version_group_id"),
            PromotionRedemption.coupon_id.label("coupon_id"),
            PromotionRedemption.customer_id.label("customer_id"),
            PromotionRedemption.status.label("status"),
            PromotionRedemption.redeemed_on.label("redeemed_on"),
            (
                PromotionRedemption.benefit_amount
                - PromotionRedemption.released_benefit_amount
            ).label("benefit_given"),
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
