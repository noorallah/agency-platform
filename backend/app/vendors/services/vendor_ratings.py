"""Record and read people's ratings of a supplier (BUY-15, decision A74).

See :mod:`app.vendors.models.vendor_rating` for why opinion is kept apart
from the computed supplier performance.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.common.firm_metadata import firm_date_of
from app.core.exceptions import ResourceNotFoundError
from app.core.utils.dates import utc_now
from app.vendors.models import Vendor
from app.vendors.models.vendor_rating import RATING_CRITERIA, VendorRating
from app.vendors.schemas.rating import (
    VendorRatingResponse,
    VendorRatingSummary,
    VendorRatingWrite,
)


class VendorRatingService:
    """Keep one live rating per person per supplier, and average them."""

    def __init__(self, session: Session) -> None:
        """Bind the service to the request's firm store."""
        self._session = session

    def summary(
        self, vendor_id: UUID, *, firm_id: UUID, reader_id: UUID
    ) -> VendorRatingSummary:
        """Return every live rating, the averages and the reader's own."""
        self._vendor(vendor_id, firm_id=firm_id)
        rows = list(
            self._session.scalars(
                select(VendorRating)
                .where(
                    VendorRating.firm_id == firm_id,
                    VendorRating.vendor_id == vendor_id,
                    VendorRating.is_deleted.is_(False),
                )
                .order_by(VendorRating.rated_on.desc(), VendorRating.created_at.desc())
            )
        )
        averages: dict[str, Decimal | None] = {}
        for name in RATING_CRITERIA:
            scores = [getattr(row, name) for row in rows]
            averages[name] = (
                None
                if not scores
                else (Decimal(sum(scores)) / len(scores)).quantize(Decimal("0.1"))
            )
        known = [value for value in averages.values() if value is not None]
        overall = (
            None
            if not known
            else (sum(known, Decimal("0")) / len(known)).quantize(Decimal("0.1"))
        )
        responses = [VendorRatingResponse.model_validate(row) for row in rows]
        mine = next((r for r in responses if r.rated_by == reader_id), None)
        return VendorRatingSummary(
            count=len(rows),
            averages=averages,
            overall=overall,
            ratings=responses,
            mine=mine,
        )

    def rate(
        self,
        vendor_id: UUID,
        data: VendorRatingWrite,
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> VendorRating:
        """Record the caller's rating, replacing their earlier one."""
        self._vendor(vendor_id, firm_id=firm_id)
        earlier = self._session.scalar(
            select(VendorRating).where(
                VendorRating.firm_id == firm_id,
                VendorRating.vendor_id == vendor_id,
                VendorRating.rated_by == actor_id,
                VendorRating.is_deleted.is_(False),
            )
        )
        now = utc_now()
        before = None
        if earlier is not None:
            before = {name: getattr(earlier, name) for name in RATING_CRITERIA}
            earlier.is_deleted = True
            earlier.deleted_at = now
            earlier.deleted_by = actor_id
            # The partial key is checked per statement: the old row must be
            # out of the live set before the new one goes in.
            self._session.flush()
        row = VendorRating(
            firm_id=firm_id,
            vendor_id=vendor_id,
            rated_by=actor_id,
            rated_on=firm_date_of(self._session, firm_id, now),
            **data.model_dump(),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._session.add(row)
        self._session.flush()
        record_audit(
            self._session,
            action="vendor.rated",
            entity_type="vendor",
            entity_id=vendor_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data=before,
            after_data={name: getattr(row, name) for name in RATING_CRITERIA},
        )
        self._session.commit()
        return row

    def withdraw(self, vendor_id: UUID, *, firm_id: UUID, actor_id: UUID) -> None:
        """Take back the caller's own rating; it stays on file as history."""
        row = self._session.scalar(
            select(VendorRating).where(
                VendorRating.firm_id == firm_id,
                VendorRating.vendor_id == vendor_id,
                VendorRating.rated_by == actor_id,
                VendorRating.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("You have not rated this supplier.")
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.deleted_by = actor_id
        record_audit(
            self._session,
            action="vendor.rating_withdrawn",
            entity_type="vendor",
            entity_id=vendor_id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={name: getattr(row, name) for name in RATING_CRITERIA},
        )
        self._session.commit()

    def _vendor(self, vendor_id: UUID, *, firm_id: UUID) -> Vendor:
        """Return the firm's live supplier or raise."""
        row = self._session.scalar(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.firm_id == firm_id,
                Vendor.is_deleted.is_(False),
            )
        )
        if row is None:
            raise ResourceNotFoundError("Supplier not found.")
        return row
