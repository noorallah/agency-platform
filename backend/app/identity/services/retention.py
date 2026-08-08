"""Retention for identity tables that would otherwise grow without bound.

``refresh_tokens``, ``login_history`` and ``password_history`` are append-heavy
and nothing ever removed rows from them. Each is pruned on a different rule:

* refresh tokens matter only until they expire or are revoked;
* login history is a security record, so it is kept for a retention window;
* password history only needs the most recent N hashes per user, which is what
  the reuse check reads.
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.utils.dates import utc_now
from app.identity.models import LoginHistory, PasswordHistory, RefreshToken


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """Report how many rows each rule removed."""

    refresh_tokens: int
    login_history: int
    password_history: int

    @property
    def total(self) -> int:
        """Return the combined number of removed rows."""
        return self.refresh_tokens + self.login_history + self.password_history


class IdentityRetentionService:
    """Prune identity records that are no longer operationally useful."""

    def __init__(self, session: Session) -> None:
        """Bind the service to one unit of work."""
        self._session = session

    def purge(
        self,
        *,
        refresh_token_grace_days: int = 7,
        login_history_days: int = 365,
        password_history_keep: int = 10,
        dry_run: bool = False,
    ) -> RetentionResult:
        """Remove expired tokens and history beyond the retention window."""
        now = utc_now()
        token_cutoff = now - timedelta(days=refresh_token_grace_days)
        login_cutoff = now - timedelta(days=login_history_days)

        # Keep recently-revoked tokens briefly so reuse detection can still see
        # them; a token revoked long ago can no longer tell us anything useful.
        token_ids = list(
            self._session.scalars(
                select(RefreshToken.id).where(
                    or_(
                        RefreshToken.expires_at < token_cutoff,
                        RefreshToken.revoked_at < token_cutoff,
                    )
                )
            ).all()
        )
        login_ids = list(
            self._session.scalars(
                select(LoginHistory.id).where(LoginHistory.created_at < login_cutoff)
            ).all()
        )
        password_ids = self._stale_password_history(password_history_keep)

        result = RetentionResult(
            refresh_tokens=len(token_ids),
            login_history=len(login_ids),
            password_history=len(password_ids),
        )
        if dry_run or result.total == 0:
            return result

        # A rotated token may still be referenced by its successor.
        if token_ids:
            self._session.execute(
                update(RefreshToken)
                .where(RefreshToken.replaced_by_id.in_(token_ids))
                .values(replaced_by_id=None)
            )
            self._session.execute(
                delete(RefreshToken).where(RefreshToken.id.in_(token_ids))
            )
        if login_ids:
            self._session.execute(
                delete(LoginHistory).where(LoginHistory.id.in_(login_ids))
            )
        if password_ids:
            self._session.execute(
                delete(PasswordHistory).where(PasswordHistory.id.in_(password_ids))
            )
        self._session.commit()
        return result

    def _stale_password_history(self, keep: int) -> list[UUID]:
        """Return history rows beyond the newest `keep` entries for each user."""
        if keep < 1:
            raise ValueError("password_history_keep must be at least 1.")
        stale: list[UUID] = []
        user_ids = self._session.scalars(
            select(PasswordHistory.user_id)
            .group_by(PasswordHistory.user_id)
            .having(func.count() > keep)
        ).all()
        for user_id in user_ids:
            stale.extend(
                self._session.scalars(
                    select(PasswordHistory.id)
                    .where(PasswordHistory.user_id == user_id)
                    .order_by(PasswordHistory.created_at.desc())
                    .offset(keep)
                ).all()
            )
        return stale
