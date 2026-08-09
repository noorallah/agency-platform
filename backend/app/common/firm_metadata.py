"""Read the handful of firm facts that firm-owned code needs.

Document numbering needs a firm's code and the month its financial year starts.
Both live on ``firms``, which exists **only in the platform schema** — so reading
them on the request's tenant session raises ``UndefinedTable`` for every firm
whose data is not in the platform store. That is the same defect already fixed
in the routers, and it reappeared inside the shared document base because the
per-module helpers it replaced all had it too.

A schema-qualified ``platform.firms`` query is not enough: a DATABASE-mode firm
lives in a different database entirely, where no such schema exists. The lookup
has to go to the platform connection.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.firms.models import Firm
from app.identity.models import User, UserFirm

_platform: DatabaseManager | None = None


def _platform_manager() -> DatabaseManager:
    """Return a shared manager for the platform store.

    Cached because building an engine per lookup would open a connection pool
    on every document created.
    """
    global _platform
    if _platform is None:
        _platform = DatabaseManager.from_settings(Settings())
    return _platform


@dataclass(frozen=True, slots=True)
class FirmMetadata:
    """The firm facts that firm-owned services need but cannot see."""

    code: str | None
    financial_year_start: date | None


class FirmMetadataReader:
    """Resolve firm facts from wherever ``firms`` actually is."""

    def __init__(self, session: Session) -> None:
        """Bind to the caller's session and start an empty per-request cache."""
        self._session = session
        self._cache: dict[UUID, FirmMetadata] = {}

    def get(self, firm_id: UUID) -> FirmMetadata:
        """Return one firm's code and financial-year start.

        Args:
            firm_id: The firm to look up.

        Returns:
            The firm's metadata; fields are None when the firm is unknown.

        """
        cached = self._cache.get(firm_id)
        if cached is not None:
            return cached
        metadata = self._read(firm_id)
        self._cache[firm_id] = metadata
        return metadata

    def _read(self, firm_id: UUID) -> FirmMetadata:
        """Read from the caller's session when it can see ``firms``.

        The unit suite builds a single SQLite database holding every table, and
        platform-path requests already run on the platform schema. Only a
        PostgreSQL tenant session needs the separate connection, and the choice
        is made on the dialect rather than by attempting a query and recovering:
        a failed statement aborts a PostgreSQL transaction, so a
        try-and-fall-back would poison the caller's unit of work.
        """
        statement = select(Firm.code, Firm.financial_year_start).where(
            Firm.id == firm_id
        )
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            return self._materialise(self._session.execute(statement).first())
        manager = _platform_manager()
        with manager.sessions(schema=manager.config.default_schema).session() as reader:
            return self._materialise(reader.execute(statement).first())

    @staticmethod
    def _materialise(row: Row[tuple[str, date]] | None) -> FirmMetadata:
        """Turn a result row into metadata, tolerating an unknown firm."""
        if row is None:
            return FirmMetadata(code=None, financial_year_start=None)
        return FirmMetadata(code=row[0], financial_year_start=row[1])

    def exists(self, firm_id: UUID) -> bool:
        """Return whether the firm is present and not soft-deleted."""
        return self.get(firm_id).code is not None

    def active_member_count(self, firm_id: UUID, user_ids: Sequence[UUID]) -> int:
        """Count how many of ``user_ids`` are active members of the firm.

        ``user_firms`` and ``users`` are platform tables, so this cannot run on
        a tenant session either.

        Args:
            firm_id: The firm the users must belong to.
            user_ids: The users to check.

        Returns:
            How many are active, undeleted members.

        """
        if not user_ids:
            return 0
        statement = (
            select(func.count())
            .select_from(UserFirm)
            .join(User, User.id == UserFirm.user_id)
            .where(
                UserFirm.user_id.in_(list(user_ids)),
                UserFirm.firm_id == firm_id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
                User.is_deleted.is_(False),
            )
        )
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            return int(self._session.scalar(statement) or 0)
        manager = _platform_manager()
        with manager.sessions(schema=manager.config.default_schema).session() as reader:
            return int(reader.scalar(statement) or 0)
