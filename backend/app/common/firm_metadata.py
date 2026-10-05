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

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Row, func, or_, select
from sqlalchemy.orm import Session

from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.utils.dates import business_date, business_today
from app.firms.models import Firm
from app.identity.models import PlatformAdmin, Role, User, UserFirm, UserRole

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


@contextmanager
def platform_reader() -> Generator[Session]:
    """Open a read session against the **platform** store.

    Some tables exist only there -- `firms`, `user_firms`, `users` -- while a
    firm-owned service runs on a tenant session whose `search_path` cannot see
    them. Querying one from that session raises
    `relation "<firm schema>.users" does not exist`, and this codebase has now
    hit that three times: every firm-owned router before 2026-08-09, the
    business-profile assignment endpoints, and territory search.

    Reach for this whenever a firm-owned service needs a platform fact.
    """
    manager = _platform_manager()
    with manager.sessions(schema=manager.config.default_schema).session() as reader:
        yield reader


@dataclass(frozen=True, slots=True)
class FirmMetadata:
    """The firm facts that firm-owned services need but cannot see."""

    code: str | None
    financial_year_start: date | None
    #: What the firm is called and its GST number. Both are platform facts a
    #: firm-owned service cannot read for itself, and both are needed the
    #: moment a document has to be presented to somebody outside the firm --
    #: an e-invoice payload names the seller.
    name: str | None = None
    gst_number: str | None = None
    #: The firm's own currency -- what a customer or vendor imported from a
    #: file trades in when the file does not say.
    currency_code: str | None = None
    #: The firm's PAN and TAN: a TDS return names the deductor by both
    #: (backlog 53.1).
    pan_number: str | None = None
    tan_number: str | None = None
    #: The firm's country (ISO 3166 alpha-2). It decides the time zone the
    #: firm's calendar day is read in (D-CFG-25); the firm carries no zone of
    #: its own.
    country: str | None = None


@dataclass(frozen=True, slots=True)
class FirmMember:
    """One person who belongs to a firm."""

    user_id: UUID
    full_name: str
    email: str


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
        statement = select(
            Firm.code,
            Firm.financial_year_start,
            Firm.name,
            Firm.gst_number,
            Firm.currency_code,
            Firm.pan_number,
            Firm.tan_number,
            Firm.country,
        ).where(Firm.id == firm_id)
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            return self._materialise(self._session.execute(statement).first())
        with platform_reader() as reader:
            return self._materialise(reader.execute(statement).first())

    @staticmethod
    def _materialise(
        row: (
            Row[tuple[str, date, str, str | None, str, str | None, str | None, str]]
            | None
        ),
    ) -> FirmMetadata:
        """Turn a result row into metadata, tolerating an unknown firm."""
        if row is None:
            return FirmMetadata(code=None, financial_year_start=None)
        return FirmMetadata(
            code=row[0],
            financial_year_start=row[1],
            name=row[2],
            gst_number=row[3],
            currency_code=row[4],
            pan_number=row[5],
            tan_number=row[6],
            country=row[7],
        )

    def today(self, firm_id: UUID) -> date:
        """Return today's date on the firm's own calendar (D-CFG-25)."""
        return business_today(self.get(firm_id).country)

    def exists(self, firm_id: UUID) -> bool:
        """Return whether the firm is present and not soft-deleted."""
        return self.get(firm_id).code is not None

    def role_codes(self, firm_id: UUID, user_id: UUID) -> frozenset[str]:
        """Return the codes of the roles a user holds in a firm.

        A role assigned with no firm counts everywhere, as it does when the
        token is issued. A platform administrator is reported as the reserved
        ``platform_admin`` code, so a caller can tell the designation apart
        from a role -- no role code can spell it (``create_role`` refuses it).
        ``roles``, ``user_roles`` and ``platform_admins`` are platform tables.
        """
        roles = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                or_(UserRole.firm_id == firm_id, UserRole.firm_id.is_(None)),
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
                Role.is_active.is_(True),
            )
        )
        admin = select(PlatformAdmin.id).where(
            PlatformAdmin.user_id == user_id, PlatformAdmin.is_deleted.is_(False)
        )
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            codes = set(self._session.scalars(roles))
            is_admin = self._session.scalar(admin) is not None
        else:
            with platform_reader() as reader:
                codes = set(reader.scalars(roles))
                is_admin = reader.scalar(admin) is not None
        if is_admin:
            codes.add("platform_admin")
        return frozenset(codes)

    def active_members(self, firm_id: UUID) -> list["FirmMember"]:
        """List a firm's active members, in name order.

        Territory assignment needs the firm's people **by name**: the only
        endpoint that lists users is guarded by `USER_VIEW`, a platform-admin
        permission the roles that run territories do not hold, so the desktop
        was left asking for a raw user id. The query lives here rather than in
        the sales service because `users` and `user_firms` are platform tables
        and this module is the one place allowed to read them.

        Args:
            firm_id: The firm whose members to list.

        Returns:
            The active, undeleted members whose account is switched on.

        """
        statement = (
            select(User.id, User.full_name, User.email)
            .join(UserFirm, UserFirm.user_id == User.id)
            .where(
                UserFirm.firm_id == firm_id,
                UserFirm.is_active.is_(True),
                UserFirm.is_deleted.is_(False),
                User.is_deleted.is_(False),
                # A switched-off account is nobody to assign work to
                # (D-IDN-10): it cannot sign in, so it was listed and picked.
                User.is_active.is_(True),
            )
            .order_by(User.full_name, User.email)
        )
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            rows = list(self._session.execute(statement))
        else:
            with platform_reader() as reader:
                rows = list(reader.execute(statement))
        return [
            FirmMember(user_id=row[0], full_name=row[1] or "", email=row[2] or "")
            for row in rows
        ]

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
                User.is_active.is_(True),
            )
        )
        bind = self._session.get_bind()
        if bind.dialect.name != "postgresql":
            return int(self._session.scalar(statement) or 0)
        manager = _platform_manager()
        with manager.sessions(schema=manager.config.default_schema).session() as reader:
            return int(reader.scalar(statement) or 0)


#: Where one session remembers the countries it has looked up.
_COUNTRIES_KEY = "firm_countries"


def _firm_country(session: Session, firm_id: UUID | None) -> str | None:
    """Return the firm's country, read once per session; None when unknown.

    ``firms`` is a platform table, so on PostgreSQL each lookup opens the
    platform store, and a list that asks "is this row overdue today" row by
    row would pay that per row. Remembered on ``session.info`` -- a request's
    session lives for one request -- rather than process-wide, so a firm's
    country changing is seen by the next request and nothing leaks between
    stores that happen to share a firm id.
    """
    if firm_id is None:
        return None
    known: dict[UUID, str | None] = session.info.setdefault(_COUNTRIES_KEY, {})
    if firm_id not in known:
        known[firm_id] = FirmMetadataReader(session).get(firm_id).country
    return known[firm_id]


def firm_today(session: Session, firm_id: UUID | None) -> date:
    """Return today's date as the firm's own calendar has it (D-CFG-25).

    **This is "today" for every business date** -- the cap on a date somebody
    typed, a report's default as-of day, the date the server puts on a
    document. `utc_now().date()` is the UTC day, and for a firm in India that
    is yesterday from midnight to 05:30: a refund dated today was refused as
    future-dated, an opening bill could not be dated today, and the stock
    valuation left out everything entered since midnight. The clock is still
    `utc_now()`; only the day it is read as belongs to the firm.

    The zone comes from the firm's country (``business_zone``), and a firm
    with none known -- or no firm at all -- reads the UTC day.
    """
    return business_today(_firm_country(session, firm_id))


def firm_date_of(session: Session, firm_id: UUID | None, instant: datetime) -> date:
    """Return the day a stored instant falls on in the firm's calendar.

    For setting a timestamp beside a business date: goods received at 01:00
    on the 6th in India were stamped 19:30 UTC on the 5th, and read by its
    UTC date that is the day *before* a delivery note dated the 6th.
    """
    return business_date(instant, _firm_country(session, firm_id))
