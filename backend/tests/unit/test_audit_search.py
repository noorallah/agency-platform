"""One search box across the audit trail (PLT-8, decision A77).

``search`` matches part of an action or a record type, or the name or email
of who did it -- and, for a row about a person, who it was done to. Names are
read from the platform store, the only one with ``users``.
"""

# ruff: noqa: D103

from uuid import uuid4

from app.common.audit.api.router import audit_scope, list_audit_logs
from app.common.audit.services import record_audit
from app.identity.models import User
from tests.unit.test_audit_trail_api import _event, _principal, _session_factory


def _people(session: object) -> tuple[User, User]:
    asha = User(
        full_name="Asha Kumar",
        email="asha@agency.local",
        password_hash="x",
        is_active=True,
    )
    ravi = User(
        full_name="Ravi Shankar",
        email="ravi@traders.example",
        password_hash="x",
        is_active=True,
    )
    session.add_all([asha, ravi])  # type: ignore[attr-defined]
    session.commit()  # type: ignore[attr-defined]
    return asha, ravi


def _search(session: object, actor: User, text: str) -> list[str]:
    scope = audit_scope(
        _principal(actor.id, {"AUDIT_LOG_VIEW"}, platform_admin=True), session, None  # type: ignore[arg-type]
    )
    page = list_audit_logs(scope, search=text, db=session, platform_db=session)  # type: ignore[arg-type]
    return sorted(row.action for row in page.data)


def test_one_box_finds_actions_record_types_and_people() -> None:
    session = _session_factory()()
    asha, ravi = _people(session)
    _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=None,
        actor_id=asha.id,
    )
    _event(
        session,
        action="invoice.approved",
        entity_type="sales_invoice",
        firm_id=None,
        actor_id=ravi.id,
    )
    record_audit(
        session,
        action="user.roles_set",
        entity_type="user",
        entity_id=ravi.id,
        actor_id=asha.id,
        firm_id=None,
    )
    session.commit()

    # Part of an action, whatever its case.
    assert _search(session, asha, "APPROV") == ["invoice.approved"]
    # Part of a record type.
    assert _search(session, asha, "sales_inv") == ["invoice.approved"]
    # A person's name: what Ravi did, and what was done to Ravi.
    assert _search(session, asha, "ravi") == ["invoice.approved", "user.roles_set"]
    # An email.
    assert _search(session, asha, "agency.local") == [
        "customer.created",
        "user.roles_set",
    ]
    assert _search(session, asha, "nobody-at-all") == []


def test_wildcards_typed_in_the_box_are_literal() -> None:
    session = _session_factory()()
    asha, _ = _people(session)
    _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=None,
        actor_id=asha.id,
    )
    assert _search(session, asha, "%") == []
    assert _search(session, asha, "   ") == ["customer.created"]


def test_search_keeps_to_the_firms_own_trail() -> None:
    session = _session_factory()()
    asha, _ = _people(session)
    firm_a, firm_b = uuid4(), uuid4()
    _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=firm_a,
        actor_id=asha.id,
    )
    _event(
        session,
        action="customer.created",
        entity_type="customer",
        firm_id=firm_b,
        actor_id=asha.id,
    )
    from app.common.audit.schemas import AuditLogFilters
    from app.common.audit.services import AuditLogReader

    rows, total = AuditLogReader(session).list_events(
        firm_scope=firm_a,
        filters=AuditLogFilters(search="asha", search_people=[asha.id]),
        page=1,
        page_size=20,
    )
    assert total == 1 and rows[0].firm_id == firm_a
