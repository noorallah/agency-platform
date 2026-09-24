"""The platform dashboard: four counts and the two panels beside them."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.dashboard import (
    RECENT_FIRMS_LIMIT,
    SYSTEM_ACTIVITY_LIMIT,
    get_dashboard,
)
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.enums import PlatformAdminScope, TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import User, UserFirm

_EPOCH = datetime(2026, 9, 1, tzinfo=UTC)


def _session() -> Session:
    """Return a session on a fresh in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _admin(user_id: UUID, scope: PlatformAdminScope) -> Principal:
    """Return a platform administrator of the given reach."""
    permissions = {"FIRM_VIEW", "USER_VIEW", "ROLE_VIEW", "PERMISSION_VIEW"}
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=[],
            permissions=sorted(permissions),
            platform_admin=True,
            platform_admin_scope=scope.value,
        ),
    )


def _world(session: Session) -> tuple[User, list[Firm]]:
    """Seven firms, one soft-deleted; a user who belongs to two of them.

    Every firm and every audit row is given its own instant, so "newest first"
    is a fact of the data rather than of the order the rows were inserted.
    """
    firms = []
    for index in range(7):
        firm = Firm(
            name=f"Firm {index}",
            code=f"F{index}",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            created_at=_EPOCH + timedelta(days=index),
        )
        firms.append(firm)
    firms[6].is_deleted = True
    session.add_all(firms)
    session.flush()
    actor = uuid4()
    user = User(
        email="narrow@example.com",
        full_name="Narrow Admin",
        password_hash="x",
        created_by=actor,
        updated_by=actor,
    )
    session.add(user)
    session.flush()
    session.add_all(
        [
            UserFirm(
                user_id=user.id,
                firm_id=firms[1].id,
                is_active=True,
                created_by=actor,
                updated_by=actor,
            ),
            UserFirm(
                user_id=user.id,
                firm_id=firms[4].id,
                is_active=True,
                created_by=actor,
                updated_by=actor,
            ),
            # A membership that ended reaches nothing.
            UserFirm(
                user_id=user.id,
                firm_id=firms[5].id,
                is_active=False,
                created_by=actor,
                updated_by=actor,
            ),
        ]
    )
    other = uuid4()
    for index in range(12):
        session.add(
            AuditLog(
                action=f"ACTION_{index}",
                entity_type="firm",
                entity_id=firms[0].id,
                actor_id=user.id if index in (2, 7) else other,
                created_at=_EPOCH + timedelta(hours=index),
            )
        )
    session.commit()
    return user, firms


def test_an_all_firms_administrator_sees_the_newest_firms_and_the_whole_trail() -> None:
    """The two panels were never filled (D-RPT-20); for full reach they are.

    Every live firm, newest first and cut at five -- the soft-deleted one,
    though newest, is not listed -- and the newest ten rows of the platform
    trail whoever wrote them.
    """
    session = _session()
    _, firms = _world(session)

    summary = get_dashboard(
        principal=_admin(uuid4(), PlatformAdminScope.ALL_FIRMS), db=session
    ).data
    assert summary is not None

    assert [firm.code for firm in summary.recent_firms] == [
        "F5",
        "F4",
        "F3",
        "F2",
        "F1",
    ]
    assert len(summary.recent_firms) == RECENT_FIRMS_LIMIT
    assert summary.recent_firms[0].id == firms[5].id
    assert summary.recent_firms[0].name == "Firm 5"
    assert [row.action for row in summary.system_activity] == [
        f"ACTION_{index}" for index in range(11, 1, -1)
    ]
    assert len(summary.system_activity) == SYSTEM_ACTIVITY_LIMIT
    # The four counts are untouched.
    assert summary.firms == 6


def test_a_platform_scoped_administrator_sees_only_their_own_firms_and_actions() -> (
    None
):
    """A `PLATFORM` designation carries no firm reach, so it is narrowed.

    It is offered the firms it holds an active membership in -- as
    `GET /api/v1/me/firms` offers it -- and only the audit rows it wrote.
    """
    session = _session()
    user, _ = _world(session)

    summary = get_dashboard(
        principal=_admin(user.id, PlatformAdminScope.PLATFORM), db=session
    ).data
    assert summary is not None

    assert [firm.code for firm in summary.recent_firms] == ["F4", "F1"]
    assert [row.action for row in summary.system_activity] == [
        "ACTION_7",
        "ACTION_2",
    ]
    assert {row.actor_id for row in summary.system_activity} == {user.id}
