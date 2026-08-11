"""Firm registry service and router tests.

The firm registry had no dedicated test, and three defects were living in that
gap: a soft-deleted firm reserved its code, GST and PAN forever; a ``PUT`` that
omitted the optional tenancy fields silently re-pointed a dedicated firm at the
shared schema; and nothing stopped two firms from being routed into the same
schema, where each would read the other's rows.
"""

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    ResourceNotFoundError,
)
from app.core.security.authorization import Principal, require_platform_admin
from app.core.security.jwt import TokenClaims
from app.firms.api.router import (
    delete_firm,
    get_firm,
    list_firms,
    update_firm,
)
from app.firms.models import Firm, FirmStorageMapping
from app.firms.schemas import FirmCreate, FirmUpdate
from app.firms.services import FirmService
from app.identity.models import User, UserFirm

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal(*, platform_admin: bool = True) -> Principal:
    """Build the platform principal firm administration requires."""
    return Principal(
        subject=_ACTOR,
        roles=frozenset({"platform_admin"} if platform_admin else {"firm_user"}),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(_ACTOR),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )


def _create_payload(**overrides: object) -> FirmCreate:
    """Build a valid firm creation body."""
    payload: dict[str, object] = {
        "name": "Acme Distributors",
        "code": "ACME",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": date(2026, 4, 1),
    }
    payload.update(overrides)
    return FirmCreate(**payload)  # type: ignore[arg-type]


def _update_payload(**overrides: object) -> FirmUpdate:
    """Build a full-replacement firm update body."""
    payload: dict[str, object] = {
        "name": "Acme Distributors",
        "code": "ACME",
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": date(2026, 4, 1),
    }
    payload.update(overrides)
    return FirmUpdate(**payload)  # type: ignore[arg-type]


def _mapping(session: Session, firm_id: UUID) -> FirmStorageMapping:
    """Return the firm's storage routing row."""
    session.expire_all()
    mapping = session.scalar(
        select(FirmStorageMapping).where(FirmStorageMapping.firm_id == firm_id)
    )
    assert mapping is not None
    return mapping


class _RecordingLifecycle:
    """Capture what the tenant storage lifecycle was asked to provision."""

    def __init__(self) -> None:
        """Start with nothing provisioned."""
        self.provisioned: list[tuple[str, str | None, str | None]] = []

    def provision_new_firm(self, firm: Firm) -> None:
        """Record the routing the firm resolved to at provisioning time."""
        self.provisioned.append(
            (firm.deployment_mode, firm.database_name, firm.schema_name)
        )


def test_create_defaults_to_shared_storage_and_audits() -> None:
    """A firm with no tenancy fields lands in the shared store."""
    session = _session()
    firm = FirmService(session).create(_create_payload(), _ACTOR)

    mapping = _mapping(session, firm.id)
    assert mapping.deployment_mode == "SHARED"
    assert mapping.schema_name is None
    assert mapping.database_name is None
    assert mapping.is_active is True

    audit = session.scalars(select(AuditLog)).all()
    assert [row.action for row in audit] == ["firm.created"]
    assert audit[0].after_data == {"code": "ACME"}


def test_create_derives_dedicated_routing_without_provisioning_it() -> None:
    """Creating a dedicated firm records routing but builds nothing yet."""
    session = _session()
    lifecycle = _RecordingLifecycle()
    service = FirmService(session, storage_lifecycle=lifecycle)
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)

    mapping = _mapping(session, firm.id)
    assert (mapping.deployment_mode, mapping.schema_name) == ("SCHEMA", "firm_acme")
    # Creation must not depend on a database server being reachable, so nothing
    # is built until the explicit action runs.
    assert lifecycle.provisioned == []
    assert mapping.provisioned_at is None


def test_provision_builds_storage_against_the_stored_routing() -> None:
    """The provisioning action sees the mapping that was written at create."""
    session = _session()
    lifecycle = _RecordingLifecycle()
    service = FirmService(session, storage_lifecycle=lifecycle)
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)

    _, already = service.provision(firm.id, _ACTOR)

    assert already is False
    # Provisioning must see the mapping that was just written, not the SHARED
    # fallback the Firm properties return when no mapping is visible.
    assert lifecycle.provisioned == [("SCHEMA", "agency_platform", "firm_acme")]
    mapping = _mapping(session, firm.id)
    assert mapping.provisioned_at is not None
    assert mapping.provisioning_error is None


def test_provision_is_idempotent_and_does_not_rebuild() -> None:
    """A second call reports the firm was already provisioned and does nothing."""
    session = _session()
    lifecycle = _RecordingLifecycle()
    service = FirmService(session, storage_lifecycle=lifecycle)
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)
    service.provision(firm.id, _ACTOR)

    _, already = service.provision(firm.id, _ACTOR)

    assert already is True
    assert len(lifecycle.provisioned) == 1


def test_provision_records_the_reason_a_build_failed() -> None:
    """A failed build leaves the reason on the record instead of only in logs."""
    session = _session()

    class _FailingLifecycle:
        """Fail the way an unreachable target server does."""

        def provision_new_firm(self, firm: Firm) -> None:
            """Raise as though the host could not be reached."""
            raise BusinessRuleError("could not connect to host 10.0.0.7")

    service = FirmService(session, storage_lifecycle=_FailingLifecycle())
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)

    with pytest.raises(BusinessRuleError):
        service.provision(firm.id, _ACTOR)

    mapping = _mapping(session, firm.id)
    assert mapping.provisioned_at is None
    assert "10.0.0.7" in (mapping.provisioning_error or "")


def test_provision_refuses_a_shared_firm() -> None:
    """Shared firms live in the platform store and have nothing to build."""
    session = _session()
    service = FirmService(session, storage_lifecycle=_RecordingLifecycle())
    firm = service.create(_create_payload(), _ACTOR)

    with pytest.raises(BusinessRuleError):
        service.provision(firm.id, _ACTOR)


def test_create_rejects_duplicate_code_gst_and_pan() -> None:
    """Live firms hold their natural keys exclusively."""
    session = _session()
    service = FirmService(session)
    service.create(
        _create_payload(gst_number="27AAAAA0000A1Z5", pan_number="AAAAA0000A"), _ACTOR
    )

    with pytest.raises(ConflictError):
        service.create(_create_payload(name="Copycat"), _ACTOR)
    with pytest.raises(ConflictError):
        service.create(
            _create_payload(code="OTHER", gst_number="27AAAAA0000A1Z5"), _ACTOR
        )
    with pytest.raises(ConflictError):
        service.create(_create_payload(code="OTHER", pan_number="AAAAA0000A"), _ACTOR)


def test_deleting_a_firm_releases_its_natural_keys() -> None:
    """A soft-deleted firm must not reserve its code, GST and PAN forever.

    ``_assert_unique`` has always ignored deleted rows, but the table-wide
    UNIQUE constraints did not, so this insert failed at the database instead.
    """
    session = _session()
    service = FirmService(session)
    firm = service.create(
        _create_payload(gst_number="27AAAAA0000A1Z5", pan_number="AAAAA0000A"), _ACTOR
    )
    service.delete(firm.id, _ACTOR)

    replacement = service.create(
        _create_payload(gst_number="27AAAAA0000A1Z5", pan_number="AAAAA0000A"), _ACTOR
    )
    assert replacement.id != firm.id
    assert replacement.code == "ACME"


def test_update_without_tenancy_fields_keeps_dedicated_routing() -> None:
    """Omitted tenancy fields inherit the firm's routing instead of resetting it.

    Every tenancy field is optional on the body, so a rename used to rewrite the
    mapping to SHARED with a null schema and strand everything the firm had
    written to its dedicated schema.
    """
    session = _session()
    service = FirmService(session)
    firm = service.create(
        _create_payload(deployment_mode="SCHEMA", schema_name="wholesale_hub"), _ACTOR
    )

    service.update(firm.id, _update_payload(name="Acme Renamed"), _ACTOR)

    mapping = _mapping(session, firm.id)
    assert mapping.deployment_mode == "SCHEMA"
    assert mapping.schema_name == "wholesale_hub"


def test_update_rejects_a_storage_routing_change() -> None:
    """Re-pointing a live firm would abandon or mix its data, so it is refused."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)

    with pytest.raises(BusinessRuleError):
        service.update(firm.id, _update_payload(deployment_mode="SHARED"), _ACTOR)
    with pytest.raises(BusinessRuleError):
        service.update(
            firm.id,
            _update_payload(deployment_mode="SCHEMA", schema_name="somewhere_else"),
            _ACTOR,
        )

    mapping = _mapping(session, firm.id)
    assert (mapping.deployment_mode, mapping.schema_name) == ("SCHEMA", "firm_acme")


def test_two_firms_cannot_share_one_schema() -> None:
    """Nothing else prevents two tenants from reading each other's rows."""
    session = _session()
    service = FirmService(session)
    service.create(
        _create_payload(deployment_mode="SCHEMA", schema_name="wholesale_hub"), _ACTOR
    )

    with pytest.raises(ConflictError):
        service.create(
            _create_payload(
                name="Second Firm",
                code="SECOND",
                deployment_mode="SCHEMA",
                schema_name="wholesale_hub",
            ),
            _ACTOR,
        )


def test_a_deleted_firms_schema_is_not_handed_to_its_replacement() -> None:
    """Releasing the code must not hand over the deleted firm's data."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)
    service.delete(firm.id, _ACTOR)

    with pytest.raises(ConflictError):
        service.create(_create_payload(deployment_mode="SCHEMA"), _ACTOR)


def test_update_rejects_a_stale_if_match_version() -> None:
    """An update aimed at a version the firm has moved past is a conflict."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(), _ACTOR)
    stale_version = firm.version
    service.update(firm.id, _update_payload(name="First Rename"), _ACTOR)

    with pytest.raises(ConflictError):
        service.update(
            firm.id,
            _update_payload(name="Second Rename"),
            _ACTOR,
            expected_version=stale_version,
        )
    assert service.get(firm.id).name == "First Rename"


def test_update_audits_both_sides_of_the_change() -> None:
    """Mutations record what the firm looked like before and after."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(), _ACTOR)
    service.update(firm.id, _update_payload(name="Renamed", is_active=False), _ACTOR)

    updated = session.scalars(
        select(AuditLog).where(AuditLog.action == "firm.updated")
    ).all()
    assert len(updated) == 1
    assert updated[0].before_data == {
        "name": "Acme Distributors",
        "code": "ACME",
        "is_active": True,
    }
    assert updated[0].after_data == {
        "name": "Renamed",
        "code": "ACME",
        "is_active": False,
    }


def test_delete_refuses_an_assigned_firm_and_audits_the_soft_delete() -> None:
    """A firm someone is still assigned to cannot be removed."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(), _ACTOR)
    user = User(
        email="member@agency.local",
        full_name="Member",
        password_hash="*",
    )
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm.id, is_primary=True))
    session.commit()

    with pytest.raises(BusinessRuleError):
        service.delete(firm.id, _ACTOR)

    session.scalar(select(UserFirm).where(UserFirm.firm_id == firm.id)).is_deleted = (
        True
    )
    session.commit()
    service.delete(firm.id, _ACTOR)

    assert session.get(Firm, firm.id).is_deleted is True
    deleted = session.scalars(
        select(AuditLog).where(AuditLog.action == "firm.deleted")
    ).all()
    assert deleted[0].after_data == {"is_deleted": True}


def test_get_and_list_hide_deleted_firms() -> None:
    """Soft-deleted firms leave both the detail and the collection view."""
    session = _session()
    service = FirmService(session)
    firm = service.create(_create_payload(), _ACTOR)
    service.create(_create_payload(name="Beta Traders", code="BETA"), _ACTOR)
    service.delete(firm.id, _ACTOR)

    with pytest.raises(ResourceNotFoundError):
        service.get(firm.id)

    rows, total = service.list(1, 20, None, "created_at", True)
    assert total == 1
    assert [row.code for row in rows] == ["BETA"]

    response = list_firms(principal=_principal(), db=session)
    assert response.pagination.total_records == 1
    assert [item.code for item in response.data] == ["BETA"]


def test_list_search_matches_name_and_code_and_pages() -> None:
    """Search covers the two indexed identity fields and honours paging."""
    session = _session()
    service = FirmService(session)
    service.create(_create_payload(), _ACTOR)
    service.create(_create_payload(name="Beta Traders", code="BETA"), _ACTOR)
    service.create(_create_payload(name="Gamma Supply", code="GAMMA"), _ACTOR)

    _, by_name = service.list(1, 20, "beta", "name", False)
    assert by_name == 1
    _, by_code = service.list(1, 20, "GAMM", "name", False)
    assert by_code == 1

    first = list_firms(principal=_principal(), page=1, page_size=2, db=session)
    assert len(first.data) == 2
    assert first.pagination.total_pages == 2


def test_firm_administration_is_platform_admin_only() -> None:
    """A firm user, however privileged, cannot reach the registry."""
    dependency = require_platform_admin()
    with pytest.raises(AuthorizationError):
        dependency(_principal(platform_admin=False))
    assert dependency(_principal()) is not None


def test_router_reads_updates_and_deletes_through_the_service() -> None:
    """The handlers wire straight through to the service contract."""
    session = _session()
    principal = _principal()
    firm = FirmService(session).create(_create_payload(), _ACTOR)

    fetched = get_firm(firm_id=firm.id, principal=principal, db=session)
    assert fetched.data.code == "ACME"
    assert fetched.data.deployment_mode.value == "SHARED"

    class _Settings:
        tenancy = None

    updated = update_firm(
        firm_id=firm.id,
        data=_update_payload(name="Renamed"),
        principal=principal,
        db=session,
        settings=_Settings(),  # type: ignore[arg-type]
    )
    assert updated.data.name == "Renamed"

    response = delete_firm(firm_id=firm.id, principal=principal, db=session)
    assert response.status_code == 204
    with pytest.raises(ResourceNotFoundError):
        FirmService(session).get(firm.id)


def test_non_user_principal_cannot_act_as_an_actor() -> None:
    """A service-token subject has no user id to attribute the mutation to."""
    session = _session()
    principal = Principal(
        subject="service-token",
        roles=frozenset({"platform_admin"}),
        permissions=frozenset(),
        claims=TokenClaims(
            sub="service-token",
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
        ),
    )
    firm = FirmService(session).create(_create_payload(), _ACTOR)

    with pytest.raises(RuntimeError):
        delete_firm(firm_id=firm.id, principal=principal, db=session)
