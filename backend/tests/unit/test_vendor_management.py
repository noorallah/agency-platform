"""Vendor validation, service, tenancy, and API tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.purchase_invoice.models import PurchaseInvoice
from app.vendors.api.router import create_vendor, list_vendors
from app.vendors.schemas import (
    VendorCategoryWrite,
    VendorCreate,
    VendorTypeWrite,
    VendorUpdate,
)
from app.vendors.schemas.vendor import VendorListFilters
from app.vendors.services import VendorService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


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
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str) -> Firm:
    """Create an owning firm."""
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
    """Build a principal carrying the given permissions."""
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
    """Build a valid vendor creation payload."""
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
    """Nested payloads normalise and reject more than one default row."""
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
    """Codes are unique per firm and a soft delete is reversible."""
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
    """The router resolves firm scope and enforces its permission codes."""
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


def test_bulk_vendor_operations_are_audited() -> None:
    """All five bulk endpoints wrote nothing at all.

    Whether a change reached the audit trail depended on which button the user
    pressed: the row menu recorded it, the toolbar did not.
    """
    session = _session_factory()()
    firm = _firm(session, "VBULK")
    actor_id = uuid4()
    service = VendorService(session)
    first = service.create(
        _vendor_data("VEN-B1", "GSTIN-B1"), firm_id=firm.id, actor_id=actor_id
    )
    second = service.create(
        _vendor_data("VEN-B2", "GSTIN-B2"), firm_id=firm.id, actor_id=actor_id
    )

    service.bulk_status(
        ids=[first.id, second.id],
        status="INACTIVE",
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    updated = session.scalars(
        select(AuditLog).where(AuditLog.action == "vendor.updated")
    ).all()
    assert {row.entity_id for row in updated} == {first.id, second.id}

    service.bulk_delete(ids=[first.id], firm_scope=firm.id, actor_id=actor_id)
    deleted = session.scalars(
        select(AuditLog).where(AuditLog.action == "vendor.deleted")
    ).all()
    assert [row.entity_id for row in deleted] == [first.id]
    assert all(row.firm_id == firm.id for row in deleted)

    service.bulk_restore(ids=[first.id], firm_scope=firm.id, actor_id=actor_id)
    restored = session.scalars(
        select(AuditLog).where(AuditLog.action == "vendor.restored")
    ).all()
    assert [row.entity_id for row in restored] == [first.id]


def test_the_vendor_masters_page_and_search() -> None:
    """Both lists returned every row and ignored `search` until 2026-08-22.

    Nothing noticed because the only caller was a dropdown, and there was no
    screen: `vendors.category_id` and `vendors.type_id` have always existed and
    nothing in the desktop could set either, nor create the row to point at.
    A `ResourceManagementPage` has a search box, and a search box that filters
    nothing is worse than none.
    """
    session = _session_factory()()
    firm = _firm(session, "VEN-CAT")
    actor_id = uuid4()
    service = VendorService(session)

    for code, name in (
        ("RAW", "Raw material"),
        ("PACK", "Packaging"),
        ("SERV", "Services"),
    ):
        service.create_category(
            VendorCategoryWrite(code=code, name=name),
            firm_id=firm.id,
            actor_id=actor_id,
        )
    service.create_type(
        VendorTypeWrite(code="LOCAL", name="Local supplier"),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    rows, total = service.list_categories(firm_id=firm.id, page=1, page_size=2)
    assert total == 3
    assert [row.code for row in rows] == ["PACK", "RAW"], "ordered by name"

    rows, total = service.list_categories(firm_id=firm.id, page=2, page_size=2)
    assert [row.code for row in rows] == ["SERV"]

    rows, total = service.list_categories(firm_id=firm.id, search="pack")
    assert total == 1
    assert rows[0].code == "PACK"

    rows, total = service.list_categories(firm_id=firm.id, search="RAW")
    assert [row.code for row in rows] == ["RAW"], "the code matches as well"

    rows, total = service.list_types(firm_id=firm.id)
    assert total == 1
    assert rows[0].code == "LOCAL"


def test_a_master_belongs_to_its_firm_alone() -> None:
    """The paging rewrite must not widen what a firm can see.

    Both queries filter on `firm_id`, and the count has to filter on it too --
    a total taken across firms would page one firm's list by another's size.
    """
    session = _session_factory()()
    mine = _firm(session, "VEN-MINE")
    theirs = _firm(session, "VEN-THEIRS")
    actor_id = uuid4()
    service = VendorService(session)

    service.create_category(
        VendorCategoryWrite(code="RAW", name="Raw material"),
        firm_id=mine.id,
        actor_id=actor_id,
    )
    service.create_category(
        VendorCategoryWrite(code="RAW", name="Raw material"),
        firm_id=theirs.id,
        actor_id=actor_id,
    )

    rows, total = service.list_categories(firm_id=mine.id)
    assert total == 1
    assert rows[0].firm_id == mine.id


def test_a_vendor_with_an_open_bill_cannot_be_deleted() -> None:
    """The vendor twin of D-FIN-1: a supplier still owed could be deleted.

    The payable control account then carried money owed to nobody on the
    vendor list. An approved bill still owing, or one still in draft, has to be
    settled or cancelled first -- and the bulk delete asks the same question
    before it commits anything.
    """
    session = _session_factory()()
    firm = _firm(session, "VOWED")
    actor_id = uuid4()
    service = VendorService(session)
    owed = service.create(
        _vendor_data("VEN-OW", "GSTIN-OW"), firm_id=firm.id, actor_id=actor_id
    )
    drafted = service.create(
        _vendor_data("VEN-DR", "GSTIN-DR"), firm_id=firm.id, actor_id=actor_id
    )
    square = service.create(
        _vendor_data("VEN-SQ", "GSTIN-SQ"), firm_id=firm.id, actor_id=actor_id
    )
    for vendor, number, status, total in (
        (owed, "PI-1", "APPROVED", Decimal("1180.00")),
        (drafted, "PI-2", "DRAFT", Decimal("590.00")),
    ):
        session.add(
            PurchaseInvoice(
                firm_id=firm.id,
                vendor_id=vendor.id,
                branch_id=uuid4(),
                invoice_number=number,
                invoice_date=date(2026, 9, 1),
                supplier_invoice_number=f"S-{number}",
                supplier_invoice_date=date(2026, 9, 1),
                status=status,
                grand_total=total,
            )
        )
    session.commit()

    with pytest.raises(
        ValidationError, match=r"VEN-OW cannot be deleted: it is owed 1,180.00"
    ):
        service.delete(owed.id, firm_scope=firm.id, actor_id=actor_id)
    session.rollback()
    with pytest.raises(ValidationError, match=r"has 1 open bill \(PI-2\)"):
        service.delete(drafted.id, firm_scope=firm.id, actor_id=actor_id)
    session.rollback()
    with pytest.raises(ValidationError, match="VEN-OW cannot be deleted"):
        service.bulk_delete(
            ids=[square.id, owed.id], firm_scope=firm.id, actor_id=actor_id
        )
    session.rollback()
    # The batch left even its settled first row alone.
    assert square.is_deleted is False
    assert owed.is_deleted is False
    assert drafted.is_deleted is False

    service.delete(square.id, firm_scope=firm.id, actor_id=actor_id)
    assert square.is_deleted is True
