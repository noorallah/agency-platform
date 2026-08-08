"""Audit trail scope, filtering, and pagination tests."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.api.router import audit_scope, list_audit_logs
from app.common.audit.models import AuditLog
from app.common.audit.services import record_audit
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, BusinessRuleError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.core.utils.dates import utc_now
from app.firms.models import Firm
from app.identity.models import UserFirm


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _principal(
    user_id: UUID, permissions: set[str], roles: set[str] | None = None
) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(roles or set()),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def _event(
    session: Session,
    *,
    action: str,
    entity_type: str,
    firm_id: UUID | None,
    actor_id: UUID,
    days_ago: int = 0,
) -> AuditLog:
    if days_ago:
        # Recorded events are immutable, so a backdated one has to be inserted
        # with its timestamp rather than written and then adjusted.
        row = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=uuid4(),
            actor_id=actor_id,
            firm_id=firm_id,
            created_at=utc_now() - timedelta(days=days_ago),
        )
        session.add(row)
        session.commit()
        return row
    record_audit(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=uuid4(),
        actor_id=actor_id,
        firm_id=firm_id,
    )
    session.commit()
    row = session.query(AuditLog).order_by(AuditLog.created_at.desc()).first()
    assert row is not None
    return row


def test_audit_scope_requires_platform_authority_without_a_firm() -> None:
    """The platform trail is readable only with platform authority."""
    factory = _session_factory()
    session = factory()
    user_id = uuid4()

    with pytest.raises(AuthorizationError, match="platform authority"):
        audit_scope(_principal(user_id, {"AUDIT_LOG_VIEW"}), session, None)

    scope = audit_scope(
        _principal(user_id, {"AUDIT_LOG_VIEW"}, {"platform_admin"}), session, None
    )
    assert scope.firm_id is None


def test_audit_scope_requires_membership_for_a_firm_trail() -> None:
    """A firm trail is readable only by a member of that firm."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "ONE")
    other = _firm(session, "TWO")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    principal = _principal(user_id, {"AUDIT_LOG_VIEW"})
    with pytest.raises(AuthorizationError, match="not authorized"):
        audit_scope(principal, session, other.id)

    scope = audit_scope(principal, session, firm.id)
    assert scope.firm_id == firm.id


def test_firm_trail_excludes_other_firms_and_platform_events() -> None:
    """A firm-scoped read never returns another firm's or platform events."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "ONE")
    other = _firm(session, "TWO")
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=firm.id,
        actor_id=user_id,
    )
    _event(
        session,
        action="customer.updated",
        entity_type="customer",
        firm_id=other.id,
        actor_id=user_id,
    )
    _event(
        session,
        action="user.created",
        entity_type="user",
        firm_id=None,
        actor_id=user_id,
    )

    scope = audit_scope(_principal(user_id, {"AUDIT_LOG_VIEW"}), session, firm.id)
    page = list_audit_logs(scope, db=session)
    assert page.pagination.total_records == 1
    assert page.data[0].action == "customer.created"
    assert page.data[0].firm_id == firm.id


def test_platform_trail_returns_every_event_in_its_own_store() -> None:
    """Without a firm scope the reader returns the whole store it is pointed at."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "ONE")
    actor_id = uuid4()
    _event(
        session,
        action="user.created",
        entity_type="user",
        firm_id=None,
        actor_id=actor_id,
    )
    _event(
        session,
        action="firm.created",
        entity_type="firm",
        firm_id=firm.id,
        actor_id=actor_id,
    )

    scope = audit_scope(
        _principal(actor_id, {"AUDIT_LOG_VIEW"}, {"platform_admin"}), session, None
    )
    page = list_audit_logs(scope, db=session)
    assert page.pagination.total_records == 2


def test_audit_filters_and_pagination() -> None:
    """Filters narrow the trail and pagination reports accurate totals."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "ONE")
    user_id = uuid4()
    other_actor = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()

    for index in range(5):
        _event(
            session,
            action=f"customer.action{index}",
            entity_type="customer",
            firm_id=firm.id,
            actor_id=user_id,
        )
    _event(
        session,
        action="product.created",
        entity_type="product",
        firm_id=firm.id,
        actor_id=other_actor,
    )
    _event(
        session,
        action="product.archived",
        entity_type="product",
        firm_id=firm.id,
        actor_id=user_id,
        days_ago=10,
    )

    scope = audit_scope(_principal(user_id, {"AUDIT_LOG_VIEW"}), session, firm.id)

    by_type = list_audit_logs(scope, entity_type="customer", db=session)
    assert by_type.pagination.total_records == 5

    by_actor = list_audit_logs(scope, actor_id=other_actor, db=session)
    assert by_actor.pagination.total_records == 1
    assert by_actor.data[0].action == "product.created"

    # Date bounds are inclusive UTC calendar days, so the reference day must
    # come from UTC too: a local 'today' can be a day ahead of the stamps.
    utc_today = utc_now().date()
    recent = list_audit_logs(scope, date_from=utc_today, db=session)
    assert recent.pagination.total_records == 6
    today_only = list_audit_logs(scope, date_to=utc_today, db=session)
    assert today_only.pagination.total_records == 7

    first = list_audit_logs(scope, page=1, page_size=3, db=session)
    assert len(first.data) == 3
    assert first.pagination.total_records == 7
    assert first.pagination.total_pages == 3


def test_audit_rows_reject_update_and_delete_through_the_orm() -> None:
    """The ORM guard refuses to mutate a recorded event."""
    factory = _session_factory()
    session = factory()
    firm = _firm(session, "ONE")
    row = _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    row.action = "customer.tampered"
    with pytest.raises(BusinessRuleError, match="append-only"):
        session.commit()
    session.rollback()

    session.delete(row)
    with pytest.raises(BusinessRuleError, match="append-only"):
        session.commit()
    session.rollback()
