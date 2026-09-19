"""A master id written onto a record must be a live row of the same firm.

D-MST-3: `customer_group_id`, `category_id`, `type_id`, `business_profile_id`,
`branch_type_id` and `warehouse_type_id` were written straight through. In the
shared store one firm's customer took another firm's 50% segment, and the
order priced at half; a segment retired a second earlier was accepted too.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import BranchType, WarehouseType
from app.branches.schemas import (
    BranchCreate,
    BranchUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.branches.services import BranchWarehouseService
from app.business.models import BusinessProfile
from app.core.database.base import Base
from app.core.database.entity import BaseEntity
from app.core.exceptions import ResourceNotFoundError
from app.customers.models import Customer, CustomerGroup
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.quotation.services import QuotationService
from app.sales_order.services import SalesOrderService
from app.vendors.models import Vendor, VendorCategory, VendorType
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.services import VendorService


def _session() -> Session:
    """Open one in-memory database holding the whole schema -- a shared store."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Add one firm."""
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


def _master(
    session: Session,
    model: type[BaseEntity],
    firm: Firm,
    code: str,
    *,
    deleted: bool = False,
) -> UUID:
    """Add one small master row for a firm, optionally already retired."""
    row = model(firm_id=firm.id, code=code, name=code, is_deleted=deleted)
    session.add(row)
    session.commit()
    return UUID(str(row.id))


def _customer(code: str, **fields: object) -> dict[str, object]:
    """Build the smallest customer payload."""
    return {
        "code": code,
        "customer_type": "BUSINESS",
        "name": code,
        "currency_code": "INR",
        **fields,
    }


def _vendor(code: str, **fields: object) -> dict[str, object]:
    """Build the smallest vendor payload."""
    return {"code": code, "name": code, **fields}


def _branch(code: str, **fields: object) -> dict[str, object]:
    """Build the smallest branch payload."""
    return {"code": code, "name": code, "currency_code": "INR", **fields}


def _refused(call: Callable[[], object], session: Session, label: str) -> None:
    """Assert the call is refused as not found, and leave the session clean."""
    with pytest.raises(ResourceNotFoundError, match=f"{label} not found"):
        call()
    session.rollback()


def test_a_customer_takes_only_its_own_firms_live_segment() -> None:
    """Create, import and update all refuse a foreign or retired segment."""
    session = _session()
    ours, theirs = _firm(session, "MR1A"), _firm(session, "MR1B")
    own = _master(session, CustomerGroup, ours, "OWN")
    foreign = _master(session, CustomerGroup, theirs, "FOREIGN")
    retired = _master(session, CustomerGroup, ours, "RETIRED", deleted=True)
    service = CustomerService(session)
    actor = uuid4()

    for bad in (foreign, retired, uuid4()):
        payload = CustomerCreate.model_validate(
            _customer("MR1-BAD", customer_group_id=bad)
        )
        _refused(
            lambda payload=payload: service.create(
                payload, firm_id=ours.id, actor_id=actor
            ),
            session,
            "Customer segment",
        )
        plain = CustomerCreate.model_validate(_customer("MR1-PLAIN"))
        _refused(
            lambda plain=plain, payload=payload: service.import_customers(
                [plain, payload], firm_id=ours.id, actor_id=actor
            ),
            session,
            "Customer segment",
        )
    assert session.query(Customer).count() == 0

    customer = service.create(
        CustomerCreate.model_validate(_customer("MR1-OK", customer_group_id=own)),
        firm_id=ours.id,
        actor_id=actor,
    )
    assert customer.customer_group_id == own
    _refused(
        lambda: service.update(
            customer.id,
            CustomerUpdate.model_validate(
                _customer("MR1-OK", customer_group_id=foreign)
            ),
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Customer segment",
    )
    cleared = service.update(
        customer.id,
        CustomerUpdate.model_validate(_customer("MR1-OK", customer_group_id=None)),
        firm_scope=ours.id,
        actor_id=actor,
    )
    assert cleared.customer_group_id is None


def test_a_record_already_holding_a_retired_segment_still_saves() -> None:
    """Only a reference that is changing is judged."""
    session = _session()
    firm = _firm(session, "MR2")
    retired = _master(session, CustomerGroup, firm, "GONE", deleted=True)
    customer = Customer(
        firm_id=firm.id,
        code="MR2-C",
        customer_type="BUSINESS",
        name="Old",
        display_name="Old",
        currency_code="INR",
        status="ACTIVE",
        customer_group_id=retired,
    )
    session.add(customer)
    session.commit()

    saved = CustomerService(session).update(
        customer.id,
        CustomerUpdate.model_validate(
            _customer("MR2-C", name="Renamed", customer_group_id=retired)
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert saved.name == "Renamed"
    assert saved.customer_group_id == retired


def test_an_order_and_a_quotation_read_only_the_customers_own_live_segment() -> None:
    """A foreign or retired segment already on a customer prices nothing."""
    session = _session()
    ours, theirs = _firm(session, "MR3A"), _firm(session, "MR3B")
    rows = {
        "own": CustomerGroup(
            firm_id=ours.id,
            code="OWN",
            name="Own",
            default_discount_percent=Decimal("5"),
        ),
        "foreign": CustomerGroup(
            firm_id=theirs.id,
            code="HALF",
            name="Half price",
            default_discount_percent=Decimal("50"),
        ),
        "retired": CustomerGroup(
            firm_id=ours.id,
            code="GONE",
            name="Gone",
            default_discount_percent=Decimal("25"),
            is_deleted=True,
        ),
    }
    session.add_all(rows.values())
    session.commit()
    customers: dict[str, Customer] = {}
    for key, group in rows.items():
        customers[key] = Customer(
            firm_id=ours.id,
            code=f"MR3-{key}",
            customer_type="BUSINESS",
            name=key,
            display_name=key,
            currency_code="INR",
            status="ACTIVE",
            customer_group_id=group.id,
        )
    session.add_all(customers.values())
    session.commit()

    for service in (SalesOrderService(session), QuotationService(session)):
        assert service._customer_group(customers["own"].id) == (
            rows["own"].id,
            Decimal("5.0000"),
        )
        assert service._customer_group(customers["foreign"].id) == (None, None)
        assert service._customer_group(customers["retired"].id) == (None, None)


def test_a_vendor_takes_only_its_own_firms_category_type_and_a_live_profile() -> None:
    """The form, the import and both bulk reassignments agree."""
    session = _session()
    ours, theirs = _firm(session, "MR4A"), _firm(session, "MR4B")
    own_category = _master(session, VendorCategory, ours, "OWNCAT")
    foreign_category = _master(session, VendorCategory, theirs, "FORCAT")
    retired_type = _master(session, VendorType, ours, "GONETYPE", deleted=True)
    foreign_type = _master(session, VendorType, theirs, "FORTYPE")
    dead_profile = BusinessProfile(
        code="DEAD", name="Dead", industry_type="GENERIC", is_deleted=True
    )
    live_profile = BusinessProfile(code="LIVE", name="Live", industry_type="GENERIC")
    session.add_all([dead_profile, live_profile])
    session.commit()
    service = VendorService(session)
    actor = uuid4()

    for field, bad, label in (
        ("category_id", foreign_category, "Vendor category"),
        ("type_id", retired_type, "Vendor type"),
        ("type_id", foreign_type, "Vendor type"),
        ("business_profile_id", dead_profile.id, "Business profile"),
    ):
        payload = VendorCreate.model_validate(_vendor("MR4-BAD", **{field: bad}))
        _refused(
            lambda payload=payload: service.create(
                payload, firm_id=ours.id, actor_id=actor
            ),
            session,
            label,
        )
        _refused(
            lambda payload=payload: service.import_vendors(
                [VendorCreate.model_validate(_vendor("MR4-PLAIN")), payload],
                firm_id=ours.id,
                actor_id=actor,
            ),
            session,
            label,
        )
    assert session.query(Vendor).count() == 0

    # A profile has no firm: any firm in the store may name a live one.
    vendor = service.create(
        VendorCreate.model_validate(
            _vendor(
                "MR4-OK",
                category_id=own_category,
                business_profile_id=live_profile.id,
            )
        ),
        firm_id=ours.id,
        actor_id=actor,
    )
    _refused(
        lambda: service.update(
            vendor.id,
            VendorUpdate.model_validate(
                _vendor("MR4-OK", category_id=foreign_category)
            ),
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Vendor category",
    )
    _refused(
        lambda: service.bulk_category(
            ids=[vendor.id],
            category_id=foreign_category,
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Vendor category",
    )
    _refused(
        lambda: service.bulk_profile(
            ids=[vendor.id],
            business_profile_id=dead_profile.id,
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Business profile",
    )
    session.refresh(vendor)
    assert vendor.category_id == own_category
    assert vendor.business_profile_id == live_profile.id
    assert (
        service.bulk_category(
            ids=[vendor.id], category_id=None, firm_scope=ours.id, actor_id=actor
        )
        == 1
    )


def test_a_branch_and_a_warehouse_take_only_their_own_firms_type() -> None:
    """Branch type and warehouse type, on create and on update."""
    session = _session()
    ours, theirs = _firm(session, "MR5A"), _firm(session, "MR5B")
    own_branch_type = _master(session, BranchType, ours, "OWNBT")
    foreign_branch_type = _master(session, BranchType, theirs, "FORBT")
    own_warehouse_type = _master(session, WarehouseType, ours, "OWNWT")
    retired_warehouse_type = _master(
        session, WarehouseType, ours, "GONEWT", deleted=True
    )
    service = BranchWarehouseService(session)
    actor = uuid4()

    _refused(
        lambda: service.create_branch(
            BranchCreate.model_validate(
                _branch("MR5-BAD", branch_type_id=foreign_branch_type)
            ),
            firm_id=ours.id,
            actor_id=actor,
        ),
        session,
        "Branch type",
    )
    branch = service.create_branch(
        BranchCreate.model_validate(_branch("MR5-BR", branch_type_id=own_branch_type)),
        firm_id=ours.id,
        actor_id=actor,
    )
    _refused(
        lambda: service.update_branch(
            branch.id,
            BranchUpdate.model_validate(
                _branch("MR5-BR", branch_type_id=foreign_branch_type)
            ),
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Branch type",
    )

    _refused(
        lambda: service.create_warehouse(
            WarehouseCreate.model_validate(
                {
                    "branch_id": branch.id,
                    "code": "MR5-BADWH",
                    "name": "Bad",
                    "warehouse_type_id": retired_warehouse_type,
                }
            ),
            firm_id=ours.id,
            actor_id=actor,
        ),
        session,
        "Warehouse type",
    )
    warehouse = service.create_warehouse(
        WarehouseCreate.model_validate(
            {
                "branch_id": branch.id,
                "code": "MR5-WH",
                "name": "Good",
                "warehouse_type_id": own_warehouse_type,
            }
        ),
        firm_id=ours.id,
        actor_id=actor,
    )
    _refused(
        lambda: service.update_warehouse(
            warehouse.id,
            WarehouseUpdate.model_validate(
                {
                    "code": "MR5-WH",
                    "name": "Good",
                    "warehouse_type_id": retired_warehouse_type,
                }
            ),
            firm_scope=ours.id,
            actor_id=actor,
        ),
        session,
        "Warehouse type",
    )
    session.refresh(warehouse)
    assert warehouse.warehouse_type_id == own_warehouse_type
