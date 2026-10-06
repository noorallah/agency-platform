"""Record what a customer claimed from an offer, and give it back if they don't.

A claim has three states and they are not the same fact.

**PENDING** is written when a document is priced, because that is when the
engine knows which offers applied and what each was worth. It counts against no
limit: a draft somebody edits five times and never approves has claimed
nothing.

A budget is a limit too. An offer may cap what it gives in money
(`max_benefit_amount`) and in free units (`max_free_quantity`), and both are
counted here exactly as the number of claims is: from CLAIMED rows across the
version group, under the same lock. A claim that would take the offer past
either is refused **whole** -- giving the part that was left would approve a
document at a price nobody saw.

"Approved" means the document a person approves. A counter bill raises a
sales order nobody typed and approves it at every save, so that order's claims
stay PENDING until the **bill** is approved (D-SELL-85); the rows are still
the order's, so every reader counts one claim per sale.

**CLAIMED** is written when the document is approved, under a row lock on the
offer, because approval is the moment two people can be racing for the last one
of something. The loser is refused rather than quietly given a benefit the
campaign had run out of.

**REVERSED** is written when the document is cancelled. Not deleted: what a
customer claimed and what they gave back are two facts, and a ledger that
forgets the first cannot explain the second. Only a claim can be reversed: a
PENDING row whose document is withdrawn was never a claim, so it is dropped
as a re-pricing drops it, and the reports count no reversal for it.

**Released** is the same fact for part of a claim. An order closed short
keeps what its notes delivered and gives back the rest (D-PRC-28): the row
stays CLAIMED -- an offer limited to one use was used -- and
``released_benefit_amount`` / ``released_free_quantity`` record what went
back, with an audit row of their own. A claim none of which was delivered is
REVERSED, as a cancellation's is. What a claim *gave* is the difference, and
every reader takes it from `offer_use.claims_given`.

Booking at approval rather than while the document is priced is the load-bearing
decision. Pricing runs on the caller's session and must never commit, so a
counter incremented there would either publish a half-written order or count a
draft nobody ever approved.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.core.utils.dates import utc_now
from app.core.utils.money import ZERO, quantize_money
from app.promotions.models import (
    Promotion,
    PromotionCoupon,
    PromotionRedemption,
)
from app.promotions.schemas import PromotionApplication
from app.promotions.services.promotion_service import budget_room

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
            # Stamped like every other soft delete; the row said deleted and
            # never said when (D-SELL-22).
            existing.deleted_at = utc_now()
            existing.deleted_by = actor_id
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
                    free_quantity=application.free_quantity,
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
            promotion = self._session.get(Promotion, row.promotion_id)
            if promotion is None:
                continue
            # The whole version group is held, not the row this claim was
            # priced against: an order priced before an edit claims the old
            # revision and one priced after claims the new, and a lock on
            # each row alone would let both through at once (D-SELL-15). In
            # id order, so two approvals lock a group the same way round.
            self._session.scalars(
                select(Promotion.id)
                .where(
                    Promotion.firm_id == firm_id,
                    Promotion.version_group_id == promotion.version_group_id,
                )
                .order_by(Promotion.id)
                .with_for_update()
            ).all()
            self._assert_room(promotion, row, firm_id=firm_id)
            row.status = CLAIMED
            row.updated_by = actor_id
        self._session.flush()

    def has_run_out(self, *, firm_id: UUID, document_ids: list[UUID]) -> bool:
        """Say whether any offer these documents priced with has none left.

        Asked when a draft is saved again, without a lock and without
        refusing: a document whose claim would be refused at approval has to
        be priced again without the offer, and a save that changed nothing
        else would otherwise keep the price it can never be approved at
        (D-SELL-85). The answer at approval is still `claim`'s, under the
        lock.
        """
        if not document_ids:
            return False
        for row in self._session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.document_id.in_(document_ids),
                PromotionRedemption.status == PENDING,
                PromotionRedemption.is_deleted.is_(False),
            )
        ).all():
            promotion = self._session.get(Promotion, row.promotion_id)
            if promotion is None:
                continue
            try:
                self._assert_room(promotion, row, firm_id=firm_id, lock=False)
            except ValidationError:
                return True
        return False

    def reverse(self, *, firm_id: UUID, document_id: UUID, actor_id: UUID) -> None:
        """Give back everything this document claimed.

        A claim is REVERSED and kept. A PENDING row is dropped: nothing was
        claimed, so there is nothing to reverse, and a counter bill priced
        again without its offer used to leave a REVERSED row the performance
        report counted as a claim given back.
        """
        now = utc_now()
        for row in self._session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.document_id == document_id,
                PromotionRedemption.status.in_((PENDING, CLAIMED)),
                PromotionRedemption.is_deleted.is_(False),
            )
        ).all():
            if row.status == PENDING:
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = actor_id
            else:
                row.status = REVERSED
                row.reversed_at = now
            row.updated_by = actor_id
        self._session.flush()

    def claimed_promotions(self, *, firm_id: UUID, document_id: UUID) -> list[UUID]:
        """Return the offers this document holds a live claim on."""
        return list(
            self._session.scalars(
                select(PromotionRedemption.promotion_id).where(
                    PromotionRedemption.firm_id == firm_id,
                    PromotionRedemption.document_id == document_id,
                    PromotionRedemption.status == CLAIMED,
                    PromotionRedemption.is_deleted.is_(False),
                )
            ).all()
        )

    def release_undelivered(
        self,
        *,
        firm_id: UUID,
        document_id: UUID,
        delivered: Mapping[UUID, tuple[Decimal, Decimal]],
        actor_id: UUID,
    ) -> None:
        """Keep what an order delivered of each claim and give back the rest.

        Called when an order with notes or bills against it is closed short.
        ``delivered`` says, per promotion, the share of the offer's money
        that reached a delivery (between 0 and 1) and the free units the
        offer gave that were delivered. The claim keeps that and releases
        what is left; a claim none of which was delivered is reversed, as a
        cancelled order's is. Worked from the claim's own figures each time,
        so calling it again changes nothing.

        Staged, never committed: the close owns the transaction.
        """
        now = utc_now()
        for row in self._session.scalars(
            select(PromotionRedemption).where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.document_id == document_id,
                PromotionRedemption.status == CLAIMED,
                PromotionRedemption.is_deleted.is_(False),
            )
        ).all():
            share, free_delivered = delivered.get(row.promotion_id, (ZERO, ZERO))
            share = min(max(share, ZERO), Decimal("1"))
            claimed = Decimal(str(row.benefit_amount))
            claimed_free = Decimal(str(row.free_quantity))
            kept = quantize_money(claimed * share)
            kept_free = min(max(free_delivered, ZERO), claimed_free)
            before: dict[str, object] = {
                "status": row.status,
                "released_benefit_amount": str(
                    quantize_money(Decimal(str(row.released_benefit_amount or 0)))
                ),
                "released_free_quantity": str(
                    quantize_money(Decimal(str(row.released_free_quantity or 0)))
                ),
            }
            if kept <= ZERO and kept_free <= ZERO:
                row.status = REVERSED
                row.reversed_at = now
                action = "promotion_redemption.reversed"
            else:
                row.released_benefit_amount = claimed - kept
                row.released_free_quantity = claimed_free - kept_free
                action = "promotion_redemption.released"
            after: dict[str, object] = {
                "status": row.status,
                "released_benefit_amount": str(
                    quantize_money(Decimal(str(row.released_benefit_amount or 0)))
                ),
                "released_free_quantity": str(
                    quantize_money(Decimal(str(row.released_free_quantity or 0)))
                ),
            }
            if after == before:
                continue
            if row.status == CLAIMED:
                row.released_at = now
            row.updated_by = actor_id
            record_audit(
                self._session,
                action=action,
                entity_type="promotion_redemption",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_id,
                before_data=before,
                after_data={
                    **after,
                    "document_number": row.document_number,
                    "benefit_amount": str(row.benefit_amount),
                    "free_quantity": str(row.free_quantity),
                    "reason": "The order was closed short.",
                },
            )
        self._session.flush()

    def _assert_room(
        self,
        promotion: Promotion,
        row: PromotionRedemption,
        *,
        firm_id: UUID,
        lock: bool = True,
    ) -> None:
        """Refuse the claim when the offer has none left.

        Counted here rather than trusted from pricing time, because the whole
        point of the lock is that the answer may have changed since. ``lock``
        is false only for `has_run_out`, which asks and claims nothing.
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
        # The budget, in money and in free units. The same sum pricing
        # reads, taken again here because the lock is what makes it true.
        overrun = budget_room(self._session, promotion, firm_id=firm_id).overrun(
            Decimal(str(row.benefit_amount)), Decimal(str(row.free_quantity))
        )
        if overrun is not None:
            raise ValidationError(
                f"Promotion {promotion.code} {overrun} Re-save the document to "
                "price it without."
            )
        if row.coupon_id is None:
            return
        wanted = select(PromotionCoupon).where(PromotionCoupon.id == row.coupon_id)
        coupon = self._session.scalar(wanted.with_for_update() if lock else wanted)
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
        """Count live claims on one offer. Reversed and pending count nothing.

        Counted across the offer's whole **version group**, as pricing counts
        them (`PromotionService._claimed`). A published promotion is
        superseded rather than edited, so counting the claimed row alone
        stopped every claim on an earlier revision counting against the limit
        the moment the offer was edited -- a campaign limited to one was
        claimed twice (D-SELL-15, 2026-09-19).
        """
        group = select(Promotion.version_group_id).where(Promotion.id == promotion_id)
        statement = (
            select(func.count())
            .select_from(PromotionRedemption)
            .where(
                PromotionRedemption.firm_id == firm_id,
                PromotionRedemption.promotion_id.in_(
                    select(Promotion.id).where(
                        Promotion.firm_id == firm_id,
                        Promotion.version_group_id == group.scalar_subquery(),
                    )
                ),
                PromotionRedemption.status == CLAIMED,
                PromotionRedemption.is_deleted.is_(False),
            )
        )
        if customer_id is not None:
            statement = statement.where(PromotionRedemption.customer_id == customer_id)
        if coupon_id is not None:
            statement = statement.where(PromotionRedemption.coupon_id == coupon_id)
        return int(self._session.scalar(statement) or 0)
