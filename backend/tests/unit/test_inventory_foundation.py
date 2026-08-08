"""Inventory foundation service and authorization tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.business.models import BusinessProfile, FirmBusinessProfile
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.core.utils.dates import utc_now
from app.customers.models import customer as _customer_models  # noqa: F401
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.inventory.api.router import create_inventory, inventory_scope, list_inventory
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryListFilters,
    OpeningStockBatchCreate,
)
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import territory as _geo_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.vendors.models import vendor as _vendor_models  # noqa: F401


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


def _profile(session: Session, firm_id: UUID) -> BusinessProfile:
    profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        default_settings={},
        created_by=uuid4(),
        updated_by=uuid4(),
    )
    session.add(profile)
    session.flush()
    session.add(
        FirmBusinessProfile(
            firm_id=firm_id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=utc_now(),
            notes="Inventory test profile",
            created_by=uuid4(),
            updated_by=uuid4(),
        )
    )
    session.commit()
    return profile


def _branch_warehouse_product(
    session: Session, firm: Firm, profile: BusinessProfile
) -> tuple[Branch, Warehouse, Product]:
    actor_id = uuid4()
    branch = Branch(
        firm_id=firm.id,
        code="HO",
        name="Head Office",
        display_name="Head Office",
        business_profile_id=profile.id,
        working_hours={},
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(branch)
    session.flush()
    warehouse = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="MAIN",
        name="Main Warehouse",
        display_name="Main Warehouse",
        business_profile_id=profile.id,
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    product = Product(
        firm_id=firm.id,
        code="SKU-001",
        name="Enterprise Stock Item",
        product_type="STOCK_ITEM",
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add_all([warehouse, product])
    session.commit()
    return branch, warehouse, product


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


def test_opening_stock_post_creates_inventory_and_immutable_history() -> None:
    session = _session_factory()()
    firm = _firm(session, "INV")
    profile = _profile(session, firm.id)
    branch, warehouse, product = _branch_warehouse_product(session, firm, profile)
    service = InventoryService(session)
    actor_id = uuid4()

    batch = service.create_opening_stock_batch(
        OpeningStockBatchCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            reference_number="OS-001",
            posting_date=date(2026, 8, 1),
            remarks="Initial stock load",
            lines=[
                {
                    "product_id": product.id,
                    "quantity": "15",
                    "minimum_level": "2",
                    "reorder_level": "5",
                    "safety_stock": "1",
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    posted = service.post_opening_stock_batch(
        batch.id, firm_scope=firm.id, actor_id=actor_id
    )
    inventory = service.list_inventory(
        firm_scope=firm.id,
        filters=InventoryListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="updated_at",
        descending=True,
    )[0][0]

    assert posted.status == "POSTED"
    assert inventory.current_quantity == Decimal("15")
    assert inventory.available_quantity == Decimal("15")
    assert inventory.reorder_level == Decimal("5")
    assert len(inventory.transactions) == 1
    assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
    assert session.scalar(select(func.count()).select_from(StockLedgerEntry)) == 1


def test_adjustment_updates_projection_and_negative_stock_summary() -> None:
    session = _session_factory()()
    firm = _firm(session, "NEG")
    profile = _profile(session, firm.id)
    branch, warehouse, product = _branch_warehouse_product(session, firm, profile)
    service = InventoryService(session)
    actor_id = uuid4()

    batch = service.create_opening_stock_batch(
        OpeningStockBatchCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            reference_number="OS-NEG",
            posting_date=date(2026, 8, 1),
            lines=[{"product_id": product.id, "quantity": "5"}],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.post_opening_stock_batch(batch.id, firm_scope=firm.id, actor_id=actor_id)
    service.create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("-8"),
            reference_number="ADJ-001",
            transaction_date=date(2026, 8, 2),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    inventory = service.list_inventory(
        firm_scope=firm.id,
        filters=InventoryListFilters(),
        page=1,
        page_size=20,
        search=None,
        sort_by="updated_at",
        descending=True,
    )[0][0]
    summary = service.inventory_summary(
        firm_scope=firm.id,
        filters=InventoryListFilters(include_deleted=False),
    )

    assert inventory.current_quantity == Decimal("-3")
    assert inventory.available_quantity == Decimal("-3")
    assert summary.negative_stock_count == 1


def test_inventory_api_scope_enforces_membership_and_permissions() -> None:
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "API")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    setup.close()

    permissions = {
        "INVENTORY_VIEW",
        "OPENING_STOCK_CREATE",
        "OPENING_STOCK_UPDATE",
        "INVENTORY_LEDGER_VIEW",
        "INVENTORY_EXPORT",
        "INVENTORY_IMPORT",
        "INVENTORY_TRANSACTION_VIEW",
        "INVENTORY_ADJUST",
    }
    session = factory()
    # One SQLite session backs both the tenant and platform dependencies here.
    scope = inventory_scope(
        _principal(user_id, permissions), session, session, firm.id
    )
    created = create_inventory(
        InventoryCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            status="ACTIVE",
        ),
        scope,
        session,
    )
    listed = list_inventory(
        scope=scope,
        page=1,
        page_size=20,
        search="Enterprise",
        sort_by="updated_at",
        sort_direction="desc",
        status_value=None,
        branch_id=None,
        warehouse_id=None,
        storage_node_id=None,
        product_id=None,
        business_profile_id=None,
        low_stock_only=False,
        out_of_stock_only=False,
        negative_only=False,
        include_deleted=False,
        db=session,
    )

    assert created.data.product_id == product.id
    assert listed.pagination.total_records == 1

    with pytest.raises(AuthorizationError):
        require_permission("INVENTORY_VIEW")(_principal(user_id, {"OPENING_STOCK_CREATE"}))
