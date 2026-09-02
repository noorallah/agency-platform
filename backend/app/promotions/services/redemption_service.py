"""Record what a customer claimed from an offer, and give it back if they don't.

A claim has three states and they are not the same fact.

**PENDING** is written when a document is priced, because that is when the
engine knows which offers applied and what each was worth. It counts against no
limit: a draft somebody edits five times and never approves has claimed
nothing.

**CLAIMED** is written when the document is approved, under a row lock on the
offer, because approval is the moment two people can be racing for the last one
of something. The loser is refused rather than quietly given a benefit the
campaign had run out of.

**REVERSED** is written when the document is cancelled. Not deleted: what a
customer claimed and what they gave back are two facts, and a ledger that
forgets the first cannot explain the second.

Booking at approval rather than while the document is priced is the load-bearing
decision. Pricing runs on the caller's session and must never commit, so a
counter incremented there would either publish a half-written order or count a
draft nobody ever approved.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.promotions.models import (
    Promotion,
    PromotionCoupon,
    PromotionRedemption,
)
from app.promotions.schemas import PromotionApplication

PENDING = "PENDING"
CLAIMED = "CLAIMED"
REVERSED = "REVERSED"


class RedemptionService:
    """Stage, claim and reverse the offers a document takes."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def stage(
        self,
        applications: list[PromotionApplication],
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        document_type: str,
        document_id: UUID,
        document_number: str | None,
        on: date,
        actor_id: UUID,
    ) -> None:
        """Record what this document took, replacing whatever it took before.

        Replaced rather than merged, because re-pricing a document is the
        document saying what it takes now. A claim already made stands: only
        PENDING rows are rewritten, so an approved order that is somehow
        re-priced cannot quietly un-claim what it already counted.
        """
        for existing in self._session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.document_id == document_id,
                PromotionRedemption.status == PENDING,
                PromotionRedemption.is_deleted.is_(False),
            )
        ).all():
            existing.is_deleted = True
            existing.updated_by = actor_id
        self._session.flush()
        for application in applications:
            self._session.add(
                PromotionRedemption(
                    firm_id=firm_id,
                    promotion_id=application.promotion_id,
                    coupon_id=application.coupon_id,
                    customer_id=customer_id,
                    document_type=document_type,
                    document_id=document_id,
                    document_number=document_number,
                    redeemed_on=on,
                    benefit_amount=application.benefit_amount,
                    status=PENDING,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
        self._session.flush()

    def claim(self, *, firm_id: UUID, document_id: UUID, actor_id: UUID) -> None:
        """Turn this document's pending claims into real ones.

        The offer row is locked first, so two documents approving at once
        cannot both take the last of something. The loser is refused with a
        sentence naming the offer rather than being given a benefit the
        campaign had run out of -- the price is not silently changed underneath
        somebody either, because re-pricing is a separate act.
        """
        pending = list(
            self._session.scalars(
                select(PromotionRedemption).where(
                    PromotionRedemption.firm_id == firm_id,
                    PromotionRedemption.document_id == document_id,
                    PromotionRedemption.status == PENDING,
                    PromotionRedemption.is_deleted.is_(False),
                )
            ).all()
        )
        for row in pending:
            promotion = self._session.scalar(
                select(Promotion)
                .where(Promotion.id == row.promotion_id)
                .with_for_update()
            )
            if promotion is None:
                continue
            self._assert_room(promotion, row, firm_id=firm_id)
            row.status = CLAIMED
            row.updated_by = actor_id
        self._session.flush()

    def reverse(self, *, firm_id: UUID, document_id: UUID, actor_id: UUID) -> None:
        """Give back everything this document claimed."""
        for row in self._session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.document_id == document_id,
                PromotionRedemption.status.in_((PENDING, CLAIMED)),
                PromotionRedemption.is_deleted.is_(False),
            )
        ).all():
            row.status = REVERSED
            row.reversed_at = utc_now()
            row.updated_by = actor_id
        self._session.flush()

    def _assert_room(
        self, promotion: Promotion, row: PromotionRedemption, *, firm_id: UUID
    ) -> None:
        """Refuse the claim when the offer has none left.

        Counted here rather than trusted from pricing time, because the whole
        point of the lock is that the answer may have changed since.
        """
        if promotion.max_redemptions is not None:
            total = self._count(firm_id=firm_id, promotion_id=promotion.id)
            if total >= promotion.max_redemptions:
                raise ValidationError(
                    f"Promotion {promotion.code} has been claimed as often as "
                    "it allows. Re-save the document to price it without."
                )
        if promotion.max_redemptions_per_customer is not None and row.customer_id:
            mine = self._count(
                firm_id=firm_id,
                promotion_id=promotion.id,
                customer_id=row.customer_id,
            )
            if mine >= promotion.max_redemptions_per_customer:
                raise ValidationError(
                    f"This customer has claimed promotion {promotion.code} as "
                    "often as they may. Re-save the document to price it without."
                )
        if row.coupon_id is None:
            return
        coupon = self._session.scalar(
            select(PromotionCoupon)
            .where(PromotionCoupon.id == row.coupon_id)
            .with_for_update()
        )
        if coupon is None:
            return
        if coupon.max_redemptions is not None:
            used = self._count(
                firm_id=firm_id, promotion_id=promotion.id, coupon_id=coupon.id
            )
            if used >= coupon.max_redemptions:
                raise ValidationError(
                    f"Coupon {coupon.code} has been used as often as it "
                    "allows. Re-save the document to price it without."
                )
        if coupon.max_redemptions_per_customer is not None and row.customer_id:
            mine = self._count(
                firm_id=firm_id,
                promotion_id=promotion.id,
                coupon_id=coupon.id,
                customer_id=row.customer_id,
            )
            if mine >= coupon.max_redemptions_per_customer:
                raise ValidationError(
                    f"This customer has used coupon {coupon.code} as often as "
                    "they may. Re-save the document to price it without."
                )

    def _count(
        self,
        *,
        firm_id: UUID,
        promotion_id: UUID,
        customer_id: UUID | None = None,
        coupon_id: UUID | None = None,
    ) -> int:
        """Count live claims. A reversal and a pending row both count nothing."""
        statement = (
            select(func.count())
            .select_from(PromotionRedemption)
            .where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.promotion_id == promotion_id,
                PromotionRedemption.status == CLAIMED,
                PromotionRedemption.is_deleted.is_(False),
            )
        )
        if customer_id is not None:
            statement = statement.where(PromotionRedemption.customer_id == customer_id)
        if coupon_id is not None:
            statement = statement.where(PromotionRedemption.coupon_id == coupon_id)
        return int(self._session.scalar(statement) or 0)
