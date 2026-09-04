"""What the firm's offers were claimed, and what they cost.

`promotion_redemptions` has recorded every claim and its benefit since the
module shipped, and nothing read it in aggregate -- so a firm could run a
campaign and had no way to ask what it had given away. The ledger was
complete; the question had nowhere to be asked.

One rule shapes all three reports here, and it is the rule the rest of this
module already turns on: **an offer's identity is its `version_group_id`, not
the row**. An ACTIVE promotion is superseded rather than edited, so the row is
only the version that happens to be current. Counting per row would split one
campaign into a handful of small ones every time somebody fixed a typo in its
name, and would report a limit as untouched the moment it was edited -- which
is three of the defects this module has already had. `PromotionService._claimed`
counts across the version group for exactly that reason, and a report that did
not would disagree with the engine that refuses the claim.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils.money import ZERO
from app.customers.models import Customer
from app.promotions.models import (
    Promotion,
    PromotionCoupon,
    PromotionRedemption,
)
from app.promotions.schemas import (
    PromotionCouponPerformanceRecord,
    PromotionPerformanceRecord,
    PromotionRedemptionRecord,
    PromotionStatus,
)
from app.promotions.services.redemption_service import CLAIMED, PENDING, REVERSED


class PromotionReportService:
    """Read what the firm's offers have actually done."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request unit of work."""
        self._session = session

    def performance_report(
        self, *, firm_scope: UUID
    ) -> list[PromotionPerformanceRecord]:
        """Return one row per offer, with what it was claimed and cost.

        Args:
            firm_scope: The firm whose offers to total.

        Returns:
            One record per `version_group_id`, costliest first. An offer
            nobody has claimed still appears, with zeroes -- a campaign that
            reached nobody is the thing the reader most wants to find, and
            leaving it out would answer only about the offers that worked.

        """
        promotions = self._promotions(firm_scope)
        if not promotions:
            return []

        # Which group each version belongs to, so a claim naming any version
        # is counted against the campaign as a whole.
        group_of = {version.id: version.version_group_id for version in promotions}
        latest: dict[UUID, Promotion] = {}
        versions: dict[UUID, int] = {}
        for version in promotions:
            key = version.version_group_id
            versions[key] = versions.get(key, 0) + 1
            held = latest.get(key)
            if held is None or version.version_number > held.version_number:
                latest[key] = version

        claimed: dict[UUID, int] = {}
        pending: dict[UUID, int] = {}
        reversed_: dict[UUID, int] = {}
        benefit: dict[UUID, Decimal] = {}
        customers: dict[UUID, set[UUID]] = {}
        for claim in self._redemptions(firm_scope):
            owner = group_of.get(claim.promotion_id)
            if owner is None:
                continue
            if claim.status == CLAIMED:
                claimed[owner] = claimed.get(owner, 0) + 1
                benefit[owner] = benefit.get(owner, ZERO) + Decimal(
                    str(claim.benefit_amount)
                )
                if claim.customer_id is not None:
                    customers.setdefault(owner, set()).add(claim.customer_id)
            elif claim.status == PENDING:
                pending[owner] = pending.get(owner, 0) + 1
            elif claim.status == REVERSED:
                reversed_[owner] = reversed_.get(owner, 0) + 1

        records = [
            PromotionPerformanceRecord(
                version_group_id=group,
                code=current.code,
                name=current.name,
                status=PromotionStatus(current.status),
                version_count=versions[group],
                claimed_count=claimed.get(group, 0),
                pending_count=pending.get(group, 0),
                reversed_count=reversed_.get(group, 0),
                customer_count=len(customers.get(group, ())),
                benefit_amount=benefit.get(group, ZERO),
                max_redemptions=current.max_redemptions,
                # Null stays null: an uncapped campaign has no remaining
                # count, which is a different answer from having none left.
                # Floored at zero rather than reported negative -- a limit
                # lowered below what has already been claimed leaves nothing
                # available, not a debt.
                remaining_redemptions=(
                    None
                    if current.max_redemptions is None
                    else max(current.max_redemptions - claimed.get(group, 0), 0)
                ),
            )
            for group, current in latest.items()
        ]
        return sorted(records, key=lambda record: (-record.benefit_amount, record.code))

    def redemption_report(self, *, firm_scope: UUID) -> list[PromotionRedemptionRecord]:
        """Return every claim on an offer, newest first.

        PENDING rows are included and labelled. A claim staged against a draft
        is not a claim, but it is what the firm has currently promised, and a
        register that hid it would leave the performance report's pending
        count with nothing behind it to look at.

        Args:
            firm_scope: The firm whose claims to list.

        Returns:
            One record per redemption row.

        """
        rows = self._redemptions(firm_scope)
        if not rows:
            return []
        promotions = {version.id: version for version in self._promotions(firm_scope)}
        coupons = self._coupon_codes({row.coupon_id for row in rows})
        names = self._customer_names({row.customer_id for row in rows})
        return [
            PromotionRedemptionRecord(
                redemption_id=row.id,
                promotion_id=row.promotion_id,
                promotion_code=getattr(promotions.get(row.promotion_id), "code", ""),
                promotion_name=getattr(
                    promotions.get(row.promotion_id), "name", str(row.promotion_id)
                ),
                coupon_code=coupons.get(row.coupon_id) if row.coupon_id else None,
                customer_id=row.customer_id,
                customer_name=names.get(row.customer_id) if row.customer_id else None,
                document_type=row.document_type,
                document_id=row.document_id,
                document_number=row.document_number,
                redeemed_on=row.redeemed_on,
                benefit_amount=row.benefit_amount,
                status=row.status,
            )
            for row in rows
        ]

    def coupon_report(
        self, *, firm_scope: UUID
    ) -> list[PromotionCouponPerformanceRecord]:
        """Return what each coupon code was claimed, and what it cost.

        Counted per coupon rather than per offer, which is the whole point:
        one promotion reached by ten codes reports a single number on the
        performance report, and which codes people actually presented is a
        different question about the same campaign.

        Args:
            firm_scope: The firm whose coupons to total.

        Returns:
            One record per coupon, costliest first.

        """
        coupons = list(
            self._session.scalars(
                select(PromotionCoupon).where(
                    PromotionCoupon.firm_id == firm_scope,
                    PromotionCoupon.is_deleted.is_(False),
                )
            ).all()
        )
        if not coupons:
            return []
        promotions = {version.id: version for version in self._promotions(firm_scope)}

        claimed: dict[UUID, int] = {}
        benefit: dict[UUID, Decimal] = {}
        customers: dict[UUID, set[UUID]] = {}
        for claim in self._redemptions(firm_scope):
            if claim.coupon_id is None or claim.status != CLAIMED:
                continue
            claimed[claim.coupon_id] = claimed.get(claim.coupon_id, 0) + 1
            benefit[claim.coupon_id] = benefit.get(claim.coupon_id, ZERO) + Decimal(
                str(claim.benefit_amount)
            )
            if claim.customer_id is not None:
                customers.setdefault(claim.coupon_id, set()).add(claim.customer_id)

        records = [
            PromotionCouponPerformanceRecord(
                coupon_id=coupon.id,
                code=coupon.code,
                promotion_id=coupon.promotion_id,
                promotion_code=getattr(promotions.get(coupon.promotion_id), "code", ""),
                status=coupon.status,
                claimed_count=claimed.get(coupon.id, 0),
                customer_count=len(customers.get(coupon.id, ())),
                benefit_amount=benefit.get(coupon.id, ZERO),
                max_redemptions=coupon.max_redemptions,
                remaining_redemptions=(
                    None
                    if coupon.max_redemptions is None
                    else max(coupon.max_redemptions - claimed.get(coupon.id, 0), 0)
                ),
            )
            for coupon in coupons
        ]
        return sorted(records, key=lambda record: (-record.benefit_amount, record.code))

    def _promotions(self, firm_scope: UUID) -> list[Promotion]:
        """Every version of every offer this firm has declared.

        Every version, not the live one: a claim names the version that was
        current when the document was priced, and dropping the superseded
        rows would orphan it.
        """
        return list(
            self._session.scalars(
                select(Promotion).where(
                    Promotion.firm_id == firm_scope,
                    Promotion.is_deleted.is_(False),
                )
            ).all()
        )

    def _redemptions(self, firm_scope: UUID) -> list[PromotionRedemption]:
        """Every live claim row, newest first."""
        return list(
            self._session.scalars(
                select(PromotionRedemption)
                .where(
                    PromotionRedemption.firm_id == firm_scope,
                    PromotionRedemption.is_deleted.is_(False),
                )
                .order_by(
                    PromotionRedemption.redeemed_on.desc(),
                    PromotionRedemption.created_at.desc(),
                )
            ).all()
        )

    def _coupon_codes(self, ids: set[UUID | None]) -> dict[UUID, str]:
        """Read the coupon codes in one query rather than one per row."""
        wanted = [value for value in ids if value is not None]
        if not wanted:
            return {}
        return {
            row.id: row.code
            for row in self._session.scalars(
                select(PromotionCoupon).where(PromotionCoupon.id.in_(wanted))
            ).all()
        }

    def _customer_names(self, ids: set[UUID | None]) -> dict[UUID, str]:
        """Read the customer names in one query rather than one per row."""
        wanted = [value for value in ids if value is not None]
        if not wanted:
            return {}
        return {
            row.id: row.display_name
            for row in self._session.scalars(
                select(Customer).where(Customer.id.in_(wanted))
            ).all()
        }
