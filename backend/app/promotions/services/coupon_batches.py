"""Mint a campaign's single-use coupon codes at once (SEL-5, decision A70).

A leaflet drop, an SMS campaign or a dealer meet hands out hundreds of codes,
each good for one claim; typing them one by one was the only way. A batch
mints them against one offer -- ``PREFIX-XXXXXXXX``, eight characters from an
alphabet with no 0/O or 1/I/L, since a code is read off paper and typed at a
counter -- each claimable once in all and once per customer, and the offer's
codes come back as a CSV to merge into the campaign.

The codes are random rather than sequential: a sequential code invites the
next one to be guessed. The key on coupon codes covers retired codes too, so a
candidate clashing with any code the firm ever minted is drawn again.
"""

import csv
import io
import secrets
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.promotions.models import Promotion, PromotionCoupon, PromotionRedemption

#: Letters and digits a person cannot misread: no 0/O, 1/I/L.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
RANDOM_LENGTH = 8
#: The most codes one batch mints.
MAX_BATCH = 5000


def _candidate(prefix: str) -> str:
    """Return one random code with the prefix."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(RANDOM_LENGTH))
    return f"{prefix}-{body}" if prefix else body


class CouponBatchService:
    """Mint and export a promotion's single-use codes."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def generate(
        self,
        promotion_id: UUID,
        *,
        count: int,
        prefix: str,
        firm_id: UUID,
        actor_id: UUID,
        description: str | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> list[str]:
        """Mint ``count`` single-use codes against the offer, all or none.

        Raises:
            ValidationError: If the count or prefix is out of bounds or the
                window ends before it starts.
            ResourceNotFoundError: If the offer is not the firm's.

        """
        if not 1 <= count <= MAX_BATCH:
            raise ValidationError(f"Generate between 1 and {MAX_BATCH} codes.")
        prefix = prefix.strip().upper()
        if len(prefix) > 12 or not all(c.isalnum() and c.isascii() for c in prefix):
            raise ValidationError(
                "A prefix is up to 12 letters and digits, such as DIWALI26."
            )
        if effective_from and effective_to and effective_to < effective_from:
            raise ValidationError("A coupon cannot end before it starts.")
        promotion = self._promotion(promotion_id, firm_id=firm_id)

        codes: set[str] = set()
        for _ in range(10):
            wanted = count - len(codes)
            if wanted == 0:
                break
            fresh = {_candidate(prefix) for _ in range(wanted)} - codes
            taken = set(
                self._session.scalars(
                    select(PromotionCoupon.code).where(
                        PromotionCoupon.firm_id == firm_id,
                        PromotionCoupon.code.in_(fresh),
                    )
                )
            )
            codes |= fresh - taken
        if len(codes) < count:
            raise ValidationError(
                "Could not draw enough unused codes; try a different prefix."
            )
        ordered = sorted(codes)
        label = description or f"Batch of {count}, {prefix or 'no prefix'}"
        self._session.add_all(
            PromotionCoupon(
                firm_id=firm_id,
                promotion_id=promotion.id,
                code=code,
                description=label,
                status="ACTIVE",
                max_redemptions=1,
                max_redemptions_per_customer=1,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=actor_id,
                updated_by=actor_id,
            )
            for code in ordered
        )
        self._session.flush()
        record_audit(
            self._session,
            action="promotion.coupons.generated",
            entity_type="promotion",
            entity_id=promotion.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={
                "count": count,
                "prefix": prefix,
                "first": ordered[0],
                "last": ordered[-1],
            },
        )
        self._session.commit()
        return ordered

    def export_csv(self, promotion_id: UUID, *, firm_id: UUID) -> tuple[str, str]:
        """Return the offer's live codes as CSV, and a file name."""
        promotion = self._promotion(promotion_id, firm_id=firm_id)
        claimed = (
            select(
                PromotionRedemption.coupon_id,
                func.count().label("claims"),
            )
            .where(
                PromotionRedemption.status == "CLAIMED",
                PromotionRedemption.is_deleted.is_(False),
            )
            .group_by(PromotionRedemption.coupon_id)
            .subquery()
        )
        rows = self._session.execute(
            select(
                PromotionCoupon.code,
                PromotionCoupon.status,
                PromotionCoupon.max_redemptions,
                func.coalesce(claimed.c.claims, 0),
                PromotionCoupon.effective_from,
                PromotionCoupon.effective_to,
                PromotionCoupon.description,
            )
            .outerjoin(claimed, claimed.c.coupon_id == PromotionCoupon.id)
            .where(
                PromotionCoupon.firm_id == firm_id,
                PromotionCoupon.promotion_id == promotion.id,
                PromotionCoupon.is_deleted.is_(False),
            )
            .order_by(PromotionCoupon.code)
        ).all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["Code", "Status", "Uses allowed", "Used", "From", "Until", "Description"]
        )
        for code, state, allowed, used, start, end, text in rows:
            writer.writerow(
                [
                    code,
                    state,
                    "" if allowed is None else allowed,
                    used,
                    start.isoformat() if start else "",
                    end.isoformat() if end else "",
                    text or "",
                ]
            )
        return buffer.getvalue(), f"coupons-{promotion.code}.csv"

    def _promotion(self, promotion_id: UUID, *, firm_id: UUID) -> Promotion:
        """Return the firm's live offer or raise."""
        row = self._session.scalar(
            select(Promotion).where(
                Promotion.id == promotion_id,
                Promotion.firm_id == firm_id,
                Promotion.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Promotion not found.")
        return row
