"""The ageing bands a firm reads what it is owed and owes in (backlog ACC-6).

An ageing splits what is unpaid by how many days past due it is. Which
columns are worth reading is the firm's own call: a distributor on 15-day
terms wants 0-15 / 16-30 / 31-45 / 45+, one on 60-day terms wants 0-60 and
beyond. Tally lets each report choose its periods and Zoho Books keeps a
firm-wide set of aging intervals; here a firm keeps one set, and the customer
and vendor ageing both read it, so both sides of the books are aged alike.

The bands are stated as their boundaries after zero: ``30,60,90`` is 0-29,
30-59, 60-89 and 90 and over -- the default, and what a firm with no row gets.
The last band is always open-ended, because a debt older than every boundary
still has to appear somewhere.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.exceptions import ValidationError
from app.finance.models import AgeingSettings

#: The boundaries a firm with no row is aged in.
DEFAULT_BUCKET_DAYS: tuple[int, ...] = (30, 60, 90)

#: At most this many boundaries -- six columns of money is already a wide row.
MAX_BOUNDARIES = 5

#: No boundary past ten years: a band nobody can fall into is a typing slip.
MAX_DAYS = 3650


def bucket_bounds(session: Session, firm_id: UUID) -> tuple[int, ...]:
    """Return the lower edge of each band, starting at zero.

    ``(0, 30, 60, 90)`` for a firm on the defaults: the band an amount falls
    in is the last whose lower edge its days past due reach.
    """
    return (0, *AgeingSettingsService(session).bucket_days(firm_id))


def band_label(bounds: tuple[int, ...], index: int) -> str:
    """Name one band the way a report column heads it: ``0-29`` or ``90+``."""
    lower = bounds[index]
    if index + 1 < len(bounds):
        return f"{lower}-{bounds[index + 1] - 1}"
    return f"{lower}+"


def parse_bucket_days(value: list[int]) -> tuple[int, ...]:
    """Check a firm's boundaries and return them in order.

    Raises:
        ValidationError: If there are none or too many, one is out of range,
            or they do not rise.

    """
    if not value:
        raise ValidationError("Give at least one boundary, such as 30.")
    if len(value) > MAX_BOUNDARIES:
        raise ValidationError(
            f"Give at most {MAX_BOUNDARIES} boundaries: "
            f"that is {MAX_BOUNDARIES + 1} columns."
        )
    for day in value:
        if day < 1 or day > MAX_DAYS:
            raise ValidationError(
                f"Each boundary is a number of days from 1 to {MAX_DAYS}; "
                f"{day} is not."
            )
    for earlier, later in zip(value, value[1:], strict=False):
        if later <= earlier:
            raise ValidationError(
                "Each boundary must be larger than the one before it: "
                f"{later} comes after {earlier}."
            )
    return tuple(value)


class AgeingSettingsService:
    """Read and change a firm's ageing bands."""

    def __init__(self, session: Session) -> None:
        """Bind to the firm's store."""
        self._session = session

    def bucket_days(self, firm_id: UUID) -> tuple[int, ...]:
        """Return the firm's boundaries, the defaults when it has never said."""
        row = self._settings(firm_id)
        if row is None:
            return DEFAULT_BUCKET_DAYS
        try:
            return parse_bucket_days(
                [int(part) for part in row.bucket_days.split(",") if part.strip()]
            )
        except (ValueError, ValidationError):
            # Only a hand edit of the table gets here; an unreadable setting
            # must not take every ageing report down with it.
            return DEFAULT_BUCKET_DAYS

    def set_bucket_days(
        self, firm_id: UUID, value: list[int], *, actor_id: UUID
    ) -> tuple[int, ...]:
        """Record the firm's boundaries, with the change on its audit trail.

        Raises:
            ValidationError: If the boundaries are not usable bands.

        """
        days = parse_bucket_days(value)
        stored = ",".join(str(day) for day in days)
        row = self._settings(firm_id)
        before = None if row is None else row.bucket_days
        if row is None:
            row = AgeingSettings(
                firm_id=firm_id, created_by=actor_id, updated_by=actor_id
            )
            self._session.add(row)
        row.bucket_days = stored
        row.updated_by = actor_id
        self._session.flush()
        record_audit(
            self._session,
            action="finance.ageing_settings.updated",
            entity_type="ageing_settings",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            before_data={"bucket_days": before},
            after_data={"bucket_days": stored},
        )
        return days

    def _settings(self, firm_id: UUID) -> AgeingSettings | None:
        """Return the firm's live settings row, if it has one."""
        return self._session.scalar(
            select(AgeingSettings).where(
                AgeingSettings.firm_id == firm_id,
                AgeingSettings.is_deleted.is_(False),
            )
        )
