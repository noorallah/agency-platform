"""Manage the codes a customer presents to claim an offer.

Separate from the promotion catalogue because the two are edited by different
people at different times: an offer is agreed once, and codes for it are minted
per campaign, per channel, or per customer.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.promotions.models import Promotion, PromotionCoupon, PromotionRedemption
from app.promotions.schemas import (
    PromotionCouponResponse,
    PromotionCouponWrite,
    PromotionStatus,
)

_ACTIVE = PromotionStatus.ACTIVE.value
_INACTIVE = PromotionStatus.INACTIVE.value


def offer_statuses(
    session: Session, coupons: Sequence[PromotionCoupon]
) -> dict[UUID, str]:
    """Return the status of the offer each coupon reaches, in one read.

    The offer is its `version_group_id`, not the row the code was minted
    against: a published offer is superseded rather than edited, so that row
    reads INACTIVE the moment anybody edits it while the offer itself is
    still running. The live revision is the newest one not retired, which is
    the one `PromotionService._coupon_reaches` lets the code claim.

    Args:
        session: The firm's session.
        coupons: The coupons being shown.

    Returns:
        The live revision's status per coupon id; INACTIVE where no revision
        of the offer is left.

    """
    groups = {
        coupon.id: coupon.promotion.version_group_id
        for coupon in coupons
        if coupon.promotion is not None
    }
    if not groups:
        return {coupon.id: _INACTIVE for coupon in coupons}
    live: dict[UUID, str] = {}
    for group, status in session.execute(
        select(Promotion.version_group_id, Promotion.status)
        .where(
            Promotion.version_group_id.in_(set(groups.values())),
            Promotion.is_deleted.is_(False),
        )
        .order_by(Promotion.version_number.asc())
    ):
        # Ascending, so the newest revision is the one left standing.
        live[group] = status
    return {
        coupon.id: live.get(groups.get(coupon.id, coupon.id), _INACTIVE)
        for coupon in coupons
    }


def shown_status(own_status: str, offer_status: str) -> str:
    """Return the status a coupon reads as, which follows its offer.

    A code switched off reads as it was set. A code left ACTIVE reads as its
    offer does, because that is what presenting it will do: with the offer
    switched off it gives nothing, and a list calling it ACTIVE says the
    opposite (D-PRC-16). Derived on every read and stored nowhere, so
    switching the offer back on brings its codes back with it.
    """
    if own_status != _ACTIVE or offer_status == _ACTIVE:
        return own_status
    return offer_status


class CouponService:
    """Create, read and retire a firm's coupons."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def list_coupons(
        self, *, firm_scope: UUID, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[PromotionCoupon], int]:
        """List a firm's coupons, newest first."""
        statement = select(PromotionCoupon).where(
            PromotionCoupon.firm_id == firm_scope,
            PromotionCoupon.is_deleted.is_(False),
        )
        count = (
            select(func.count())
            .select_from(PromotionCoupon)
            .where(
                PromotionCoupon.firm_id == firm_scope,
                PromotionCoupon.is_deleted.is_(False),
            )
        )
        if search:
            token = f"%{search.strip()}%"
            statement = statement.where(PromotionCoupon.code.ilike(token))
            count = count.where(PromotionCoupon.code.ilike(token))
        rows = list(
            self._session.scalars(
                # The id breaks the tie: two coupons minted in one transaction
                # share a timestamp, and a sort that is not total pages them
                # unstably -- a row appearing twice and another never.
                statement.order_by(
                    PromotionCoupon.created_at.desc(), PromotionCoupon.id.desc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, int(self._session.scalar(count) or 0)

    def get_coupon(self, coupon_id: UUID, *, firm_scope: UUID) -> PromotionCoupon:
        """Fetch one coupon, scoped to the firm."""
        row = self._session.scalar(
            select(PromotionCoupon).where(
                PromotionCoupon.id == coupon_id,
                PromotionCoupon.firm_id == firm_scope,
                PromotionCoupon.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Coupon not found.")
        return row

    def create_coupon(
        self, data: PromotionCouponWrite, *, firm_id: UUID, actor_id: UUID
    ) -> PromotionCoupon:
        """Mint one coupon against an existing offer."""
        code = data.code.strip().upper()
        promotion = self._session.scalar(
            select(Promotion).where(
                Promotion.id == data.promotion_id,
                Promotion.firm_id == firm_id,
                Promotion.is_deleted.is_(False),
            )
        )
        if promotion is None:
            raise ValidationError("A coupon must name a promotion of this firm.")
        existing = self._session.scalar(
            select(PromotionCoupon).where(
                PromotionCoupon.firm_id == firm_id,
                PromotionCoupon.code == code,
                PromotionCoupon.is_deleted.is_(False),
            )
        )
        if existing is not None:
            raise ConflictError("A coupon with this code already exists.")
        row = PromotionCoupon(
            firm_id=firm_id,
            promotion_id=promotion.id,
            code=code,
            description=data.description,
            status=data.status.value,
            max_redemptions=data.max_redemptions,
            max_redemptions_per_customer=data.max_redemptions_per_customer,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="promotion.coupon.created",
            entity_type="promotion_coupon",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "promotion_id": str(row.promotion_id)},
        )
        self._session.commit()
        return row

    def update_coupon(
        self,
        coupon_id: UUID,
        data: PromotionCouponWrite,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> PromotionCoupon:
        """Change a coupon's limits, window or status.

        The code itself is fixed once minted: it is on a leaflet somebody is
        holding, and a claim already made names it.

        **Only what the caller named is written.** Every field on the write
        model carries a default -- `status` defaults to ACTIVE and each limit
        to None -- so assigning them all turned an omission into an
        instruction: correcting a coupon's wording switched a paused one back
        on, removed its total cap, removed its per-customer cap and removed
        its effective window, in one call. That is the same full-dump defect
        `update_order` and `VendorUpdate` carried, in the shape that gives
        money away. Absent means leave alone; an explicit null still clears,
        so a limit can still be lifted on purpose.
        """
        row = self.get_coupon(coupon_id, firm_scope=firm_scope)
        named = data.model_dump(exclude_unset=True)
        if "description" in named:
            row.description = data.description
        if "status" in named:
            row.status = data.status.value
        if "max_redemptions" in named:
            row.max_redemptions = data.max_redemptions
        if "max_redemptions_per_customer" in named:
            row.max_redemptions_per_customer = data.max_redemptions_per_customer
        if "effective_from" in named:
            row.effective_from = data.effective_from
        if "effective_to" in named:
            row.effective_to = data.effective_to
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="promotion.coupon.updated",
            entity_type="promotion_coupon",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"code": row.code, "status": row.status},
        )
        self._session.commit()
        return row

    def delete_coupon(
        self, coupon_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> None:
        """Retire a coupon without forgetting what it already gave away."""
        row = self.get_coupon(coupon_id, firm_scope=firm_scope)
        row.is_deleted = True
        row.updated_by = actor_id
        record_audit(
            self._session,
            action="promotion.coupon.deleted",
            entity_type="promotion_coupon",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code, "status": row.status},
        )
        self._session.commit()

    def coupon_response(self, row: PromotionCoupon) -> PromotionCouponResponse:
        """Build one coupon's API response."""
        return self.coupon_responses([row])[0]

    def coupon_responses(
        self, rows: Sequence[PromotionCoupon]
    ) -> list[PromotionCouponResponse]:
        """Build a page of responses, with what was claimed and the status.

        The count is read rather than stored, for the reason the limits are:
        the redemption ledger is the record, and a second copy of a number is
        one that can disagree with it. It and the offers' statuses are each
        read once for the page.
        """
        if not rows:
            return []
        claimed: dict[UUID, int] = {
            coupon_id: int(count)
            for coupon_id, count in self._session.execute(
                select(PromotionRedemption.coupon_id, func.count())
                .where(
                    PromotionRedemption.coupon_id.in_([row.id for row in rows]),
                    PromotionRedemption.status == "CLAIMED",
                    PromotionRedemption.is_deleted.is_(False),
                )
                .group_by(PromotionRedemption.coupon_id)
            )
        }
        offers = offer_statuses(self._session, rows)
        return [
            PromotionCouponResponse(
                id=row.id,
                promotion_id=row.promotion_id,
                promotion_code=row.promotion.code if row.promotion else "",
                code=row.code,
                description=row.description,
                status=shown_status(row.status, offers[row.id]),
                own_status=row.status,
                offer_status=offers[row.id],
                max_redemptions=row.max_redemptions,
                max_redemptions_per_customer=row.max_redemptions_per_customer,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                redemption_count=claimed.get(row.id, 0),
                version=row.version,
            )
            for row in rows
        ]
