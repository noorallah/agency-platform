"""Manage the codes a customer presents to claim an offer.

Separate from the promotion catalogue because the two are edited by different
people at different times: an offer is agreed once, and codes for it are minted
per campaign, per channel, or per customer.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.promotions.models import Promotion, PromotionCoupon, PromotionRedemption
from app.promotions.schemas import PromotionCouponResponse, PromotionCouponWrite


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
        """
        row = self.get_coupon(coupon_id, firm_scope=firm_scope)
        row.description = data.description
        row.status = data.status.value
        row.max_redemptions = data.max_redemptions
        row.max_redemptions_per_customer = data.max_redemptions_per_customer
        row.effective_from = data.effective_from
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
        """Build the API response, including how much has been claimed.

        The count is read rather than stored, for the reason the limits are:
        the redemption ledger is the record, and a second copy of a number is
        one that can disagree with it.
        """
        claimed = int(
            self._session.scalar(
                select(func.count())
                .select_from(PromotionRedemption)
                .where(
                    PromotionRedemption.coupon_id == row.id,
                    PromotionRedemption.status == "CLAIMED",
                    PromotionRedemption.is_deleted.is_(False),
                )
            )
            or 0
        )
        return PromotionCouponResponse(
            id=row.id,
            promotion_id=row.promotion_id,
            promotion_code=row.promotion.code if row.promotion else "",
            code=row.code,
            description=row.description,
            status=row.status,
            max_redemptions=row.max_redemptions,
            max_redemptions_per_customer=row.max_redemptions_per_customer,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            redemption_count=claimed,
            version=row.version,
        )
