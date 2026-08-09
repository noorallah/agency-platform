"""Vendor validation, service, tenancy, and API tests."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ConflictError, ResourceNotFoundError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.vendors.api.router import create_vendor, list_vendors
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.schemas.vendor import VendorListFilters
from app.vendors.services import VendorService


def _firm_scope(
    principal: Principal, session: Session, firm_id: UUID | None
) -> ResolvedFirmScope:
    """Resolve firm scope exactly as a request does, through the shared helper.

    Routers no longer carry a private resolver; membership is validated once in
    ``app.common.scope`` against the platform store.
    """
    return required_firm_scope(
        optional_firm_scope(principal=principal, db=session, x_firm_id=firm_id)
    )

def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
    row = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


def _vendor_data(code: str = "VEN-001", gstin: str = "GSTIN-001") -> VendorCreate:
    return VendorCreate.model_validate(
        {
            "code": code,
            "name": "Acme Vendors",
            "display_name": "Acme Vendors",
            "status": "ACTIVE",
            "gst_registration": True,
            "gstin": gstin,
            "pan": "PAN-001",
            "email": "vendors@acme.test",
            "mobile": "+919876543210",
            "contacts": [
                {
                    "name": "Finance Desk",
                    "mobile": "+919876543211",
                    "email": "finance@acme.test",
                    "is_primary": True,
                    "status": "ACTIVE",
                }
            ],
            "addresses": [
                {
                    "address_type": "BILLING",
                    "address_line1": "Address Line 1",
                    "is_primary": True,
                }
            ],
            "banking": [],
            "tax": [],
            "attachments": [],
            "notes": [],
        }
    )


def test_vendor_schema_normalizes_and_validates_nested_defaults() -> None:
    data = _vendor_data()
    assert data.code == "VEN-001"
    assert data.email == "vendors@acme.test"
    assert data.mobile == "+919876543210"

    invalid = data.model_dump(mode="json")
    invalid["contacts"].append(
        {
            "name": "Owner",
            "mobile": "+919876543212",
            "email": "owner@acme.test",
            "is_primary": True,
            "status": "ACTIVE",
        }
    )
    with pytest.raises(ValueError, match="primary contact"):
        VendorCreate.model_validate(invalid)


def test_vendor_service_enforces_uniqueness_scope_and_soft_delete_restore() -> None:
    factory = _session_factory()
    session = factory()
    first_firm = _firm(session, "VEN-A")
    second_firm = _firm(session, "VEN-B")
    actor_id = uuid4()
    service = VendorService(session)

    created = service.create(_vendor_data(), firm_id=first_firm.id, actor_id=actor_id)
    assert created.display_name == "Acme Vendors"
    assert created.contacts[0].is_primary is True

    with pytest.raises(ConflictError):
        service.create(_vendor_data(), firm_id=first_firm.id, actor_id=actor_id)

    second = service.create(
        _vendor_data("VEN-001", "GSTIN-XYZ"),
        firm_id=second_firm.id,
        actor_id=actor_id,
    )
    assert second.firm_id == second_firm.id

    with pytest.raises(ResourceNotFoundError, match="Vendor not found"):
        service.get(created.id, firm_scope=second_firm.id)

    update = VendorUpdate.model_validate(
        {**_vendor_data().model_dump(mode="json"), "name": "Acme Vendors Updated"}
    )
    updated = service.update(
        created.id, update, firm_scope=first_firm.id, actor_id=actor_id
    )
    assert updated.name == "Acme Vendors Updated"

    service.delete(created.id, firm_scope=first_firm.id, actor_id=actor_id)
    rows, visible_total = service.list_vendors(
        firm_scope=first_firm.id,
        filters=VendorListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="created_at",
        descending=True,
    )
    assert rows == []
    assert visible_total == 0

    restored = service.restore(created.id, firm_scope=first_firm.id, actor_id=actor_id)
    assert restored.is_deleted is False


def test_vendor_api_scope_permissions_and_listing() -> None:
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "VEN-API")
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    permissions = {"VENDOR_VIEW", "VENDOR_CREATE"}
    principal = _principal(user_id, permissions)
    session = factory()
    scope = _firm_scope(principal, session, firm.id)
    created = create_vendor(_vendor_data("VEN-API-1"), scope, session)
    assert created.data.code == "VEN-API-1"

    listed = list_vendors(
        scope=scope,
        page=1,
        page_size=20,
        search="VEN-API",
        sort_by="created_at",
        sort_direction="desc",
        status_value=None,
        category_id=None,
        type_id=None,
        business_profile_id=None,
        city_id=None,
        state_id=None,
        country_id=None,
        firm_id=None,
        created_from=None,
        created_to=None,
        include_deleted=False,
        db=session,
    )
    assert listed.pagination.total_records == 1
    with pytest.raises(AuthorizationError):
        require_permission("VENDOR_DELETE")(principal)
