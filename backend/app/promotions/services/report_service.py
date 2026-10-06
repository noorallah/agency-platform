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

A second rule since 2026-10-06: **what a claim gave is read from one place**,
`offer_use.claims_given`. A claim's own columns say what the document claimed
at approval; an order closed short gives part of that back and a returned
free unit was not given, and the performance report used to state 4 free
units beside a budget that had counted 3 (D-PRC-34). All three reports here
take the netted figures from that statement, as the budgets do.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.pagination import WHOLE_HISTORY, ReportWindow, mapped_like
from app.core.utils.money import ZERO
from app.core.utils.quantities import at_quantity_scale
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
from app.promotions.services.coupon_crud import offer_statuses, shown_status
from app.promotions.services.offer_use import claims_given
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
        free: dict[UUID, Decimal] = {}
        customers: dict[UUID, set[UUID]] = {}
        for claim in self._session.execute(claims_given(firm_scope)).all():
            owner = group_of.get(claim.promotion_id)
            if owner is None:
                continue
            if claim.status == CLAIMED:
                claimed[owner] = claimed.get(owner, 0) + 1
                benefit[owner] = benefit.get(owner, ZERO) + Decimal(
                    str(claim.benefit_given)
                )
                free[owner] = free.get(owner, ZERO) + at_quantity_scale(
                    claim.free_given
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
                free_quantity=free.get(group, ZERO),
                # The budgets are the latest version's, counted over every
                # version's claims and floored like the count below.
                max_benefit_amount=current.max_benefit_amount,
                remaining_benefit_amount=(
                    None
                    if current.max_benefit_amount is None
                    else max(
                        current.max_benefit_amount - benefit.get(group, ZERO), ZERO
                    )
                ),
                max_free_quantity=current.max_free_quantity,
                remaining_free_quantity=(
                    None
                    if current.max_free_quantity is None
                    else max(current.max_free_quantity - free.get(group, ZERO), ZERO)
                ),
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
        # Costliest first, and by the units given where no money was: a
        # free-goods campaign takes nothing off a bill, so on money alone
        # every one of them sorted as though it had cost nothing (D-PRC-10).
        return sorted(
            records,
            key=lambda record: (
                -record.benefit_amount,
                -record.free_quantity,
                record.code,
            ),
        )

    def redemption_report(
        self, *, firm_scope: UUID, window: ReportWindow = WHOLE_HISTORY
    ) -> list[PromotionRedemptionRecord]:
        """Return every claim on an offer, newest first.

        PENDING rows are included and labelled. A claim staged against a draft
        is not a claim, but it is what the firm has currently promised, and a
        register that hid it would leave the performance report's pending
        count with nothing behind it to look at.

        Args:
            firm_scope: The firm whose claims to list.
            window: The days, on `redeemed_on`, and the page to answer; the
                claims are paged in SQL.

        Returns:
            One record per redemption row.

        """
        rows = window.fetch(
            self._session, self._redemption_statement(firm_scope, window)
        )
        if not rows:
            return mapped_like(rows, [])
        promotions = {version.id: version for version in self._promotions(firm_scope)}
        coupons = self._coupon_codes({row.coupon_id for row in rows})
        names = self._customer_names({row.customer_id for row in rows})
        # What each claim on the page gave, from the statement the budgets
        # read. A page is at most the page size, so its ids are a short list.
        given = {
            claim.id: (
                Decimal(str(claim.benefit_given)),
                at_quantity_scale(claim.free_given),
            )
            for claim in self._session.execute(
                claims_given(
                    firm_scope, PromotionRedemption.id.in_([row.id for row in rows])
                )
            ).all()
        }
        records = [
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
                # A claim gave what it claimed less what was released and
                # what came back; one given back whole (REVERSED) and a
                # draft's (PENDING) still read what the document claimed.
                benefit_amount=(
                    given.get(row.id, (row.benefit_amount, ZERO))[0]
                    if row.status == CLAIMED
                    else row.benefit_amount
                ),
                free_quantity=(
                    given.get(row.id, (ZERO, row.free_quantity))[1]
                    if row.status == CLAIMED
                    else row.free_quantity
                ),
                claimed_benefit_amount=row.benefit_amount,
                claimed_free_quantity=row.free_quantity,
                status=row.status,
            )
            for row in rows
        ]
        return mapped_like(rows, records)

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

        offers = offer_statuses(self._session, coupons)

        claimed: dict[UUID, int] = {}
        benefit: dict[UUID, Decimal] = {}
        free: dict[UUID, Decimal] = {}
        customers: dict[UUID, set[UUID]] = {}
        for claim in self._session.execute(
            claims_given(
                firm_scope,
                PromotionRedemption.status == CLAIMED,
                PromotionRedemption.coupon_id.is_not(None),
            )
        ).all():
            claimed[claim.coupon_id] = claimed.get(claim.coupon_id, 0) + 1
            benefit[claim.coupon_id] = benefit.get(claim.coupon_id, ZERO) + Decimal(
                str(claim.benefit_given)
            )
            free[claim.coupon_id] = free.get(claim.coupon_id, ZERO) + at_quantity_scale(
                claim.free_given
            )
            if claim.customer_id is not None:
                customers.setdefault(claim.coupon_id, set()).add(claim.customer_id)

        records = [
            PromotionCouponPerformanceRecord(
                coupon_id=coupon.id,
                code=coupon.code,
                promotion_id=coupon.promotion_id,
                promotion_code=getattr(promotions.get(coupon.promotion_id), "code", ""),
                status=shown_status(coupon.status, offers[coupon.id]),
                claimed_count=claimed.get(coupon.id, 0),
                customer_count=len(customers.get(coupon.id, ())),
                benefit_amount=benefit.get(coupon.id, ZERO),
                free_quantity=free.get(coupon.id, ZERO),
                max_redemptions=coupon.max_redemptions,
                remaining_redemptions=(
                    None
                    if coupon.max_redemptions is None
                    else max(coupon.max_redemptions - claimed.get(coupon.id, 0), 0)
                ),
            )
            for coupon in coupons
        ]
        return sorted(
            records,
            key=lambda record: (
                -record.benefit_amount,
                -record.free_quantity,
                record.code,
            ),
        )

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

    @staticmethod
    def _redemption_statement(
        firm_scope: UUID, window: ReportWindow
    ) -> Select[tuple[PromotionRedemption]]:
        """Select the live claim rows redeemed in ``window``, newest first."""
        return (
            select(PromotionRedemption)
            .where(
                PromotionRedemption.firm_id == firm_scope,
                PromotionRedemption.is_deleted.is_(False),
                *window.dated(PromotionRedemption.redeemed_on),
            )
            .order_by(
                PromotionRedemption.redeemed_on.desc(),
                PromotionRedemption.created_at.desc(),
                PromotionRedemption.id.desc(),
            )
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
