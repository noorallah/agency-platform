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
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.core.utils.dates import utc_now
from app.customers.models import customer as _customer_models  # noqa: F401
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.inventory.api.router import (
    create_inventory,
    list_inventory,
    list_ledger,
    list_transactions,
)
from app.inventory.models import InventoryTransaction, StockLedgerEntry
from app.inventory.schemas import (
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryListFilters,
    OpeningStockBatchCreate,
)
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import _Movement
from app.products.models import Product
from app.sales.models import territory as _geo_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.vendors.models import vendor as _vendor_models  # noqa: F401


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
    """Posting a batch creates the projection and an immutable history row."""
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
    """An issue larger than the balance is allowed and reported as negative."""
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
    """The router resolves firm scope and enforces its permission codes."""
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
    scope = _firm_scope(_principal(user_id, permissions), session, firm.id)
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
        require_permission("INVENTORY_VIEW")(
            _principal(user_id, {"OPENING_STOCK_CREATE"})
        )


def test_moving_average_cost_tracks_receipts_and_issues() -> None:
    """Stock carries a value, and issues consume it at the running average.

    stock_ledger_entries had no cost column of any kind, so stock could not be
    valued and cost of goods sold did not exist.
    """
    session = _session_factory()()
    firm = _firm(session, "VAL")
    profile = _profile(session, firm.id)
    branch, warehouse, product = _branch_warehouse_product(session, firm, profile)
    service = InventoryService(session)
    actor_id = uuid4()

    def _receive(quantity: str, unit_cost: str) -> None:
        service.record_goods_receipt(
            firm_scope=firm.id,
            actor_id=actor_id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=None,
            product_id=product.id,
            reference_number="GRN-VAL",
            transaction_date=date(2026, 8, 4),
            total_quantity=Decimal(quantity),
            unit_cost=Decimal(unit_cost),
        )

    # 10 @ 100 then 10 @ 120 averages to 110.
    _receive("10", "100")
    valuation = service.valuation_for(firm_scope=firm.id, product_id=product.id)
    assert valuation.quantity_on_hand == Decimal("10.0000")
    assert valuation.average_cost == Decimal("100.000000")
    assert valuation.total_value == Decimal("1000.0000")

    _receive("10", "120")
    session.refresh(valuation)
    assert valuation.quantity_on_hand == Decimal("20.0000")
    assert valuation.average_cost == Decimal("110.000000")
    assert valuation.total_value == Decimal("2200.0000")

    # Issuing consumes at the average and leaves it unchanged.
    service.record_delivery_note_dispatch(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number="DN-VAL",
        transaction_date=date(2026, 8, 5),
        dispatch_quantity=Decimal("5"),
    )
    session.refresh(valuation)
    assert valuation.quantity_on_hand == Decimal("15.0000")
    assert valuation.average_cost == Decimal("110.000000"), "issues must not move it"
    assert valuation.total_value == Decimal("1650.0000")

    # The cost of that issue is on the ledger: 5 x 110 is the cost of goods sold.
    issue = session.scalar(
        select(StockLedgerEntry).where(StockLedgerEntry.reference_number == "DN-VAL")
    )
    assert issue is not None
    assert issue.unit_cost == Decimal("110.000000")
    assert issue.total_cost == Decimal("550.0000")


def test_the_stock_ledger_endpoint_returns_its_rows() -> None:
    """The ledger list failed for every firm that had ever moved stock.

    ``ledger_response`` fed a ``StockLedgerEntry`` into the transaction
    builder, which reads ``entered_quantity``/``entered_uom_id``/
    ``conversion_version`` -- three columns the ledger does not have. The row is
    written correctly; only reading it back through the API raised
    AttributeError, so the endpoint 500ed as soon as one movement existed.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "LEDG")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    setup.close()

    session = factory()
    actor_id = uuid4()
    service = InventoryService(session)
    service.create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=Decimal("12"),
            reference_number="ADJ-LEDGER",
            transaction_date=date(2026, 8, 2),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    scope = _firm_scope(
        _principal(user_id, {"INVENTORY_LEDGER_VIEW"}), session, firm.id
    )
    response = list_ledger(scope=scope, db=session)

    assert response.pagination.total_records == 1
    row = response.data[0]
    assert row.reference_number == "ADJ-LEDGER"
    assert row.new_current_quantity == Decimal("12")
    # The ledger's as-entered quantity lives under its own column name.
    assert row.entered_quantity == Decimal("12")
    assert row.transaction_id is not None


def test_the_ledger_renders_every_movement_type_the_service_writes() -> None:
    """The response enum did not cover the vocabulary the writers use.

    ``/inventory/ledger`` and ``/inventory/transactions`` validated
    ``transaction_type`` against ``InventoryTransactionType``, but the service
    writes RESERVE, UNRESERVE and DISPATCH, and ``reverse_transaction`` writes
    "<TYPE>_REVERSAL", which no closed enum can enumerate. Both endpoints
    returned 500 for any firm that had reserved, dispatched or reversed stock --
    which is every firm that trades. Only an adjustment-only fixture missed it.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "LEDGV")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    user_id = uuid4()
    setup.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    setup.commit()
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    setup.close()

    session = factory()
    actor_id = uuid4()
    service = InventoryService(session)
    service.create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=Decimal("20"),
            reference_number="ADJ-VOCAB",
            transaction_date=date(2026, 8, 2),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )
    receipt = service.record_goods_receipt(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        reference_number="GRN-VOCAB",
        transaction_date=date(2026, 8, 3),
        total_quantity=Decimal("10"),
    )
    service.record_sales_order_reservation(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        reference_number="SO-VOCAB",
        transaction_date=date(2026, 8, 4),
        reserve_quantity=Decimal("5"),
    )
    service.release_sales_order_reservation(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        reference_number="SO-VOCAB",
        transaction_date=date(2026, 8, 5),
        release_quantity=Decimal("5"),
    )
    service.record_delivery_note_dispatch(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        reference_number="DN-VOCAB",
        transaction_date=date(2026, 8, 6),
        dispatch_quantity=Decimal("3"),
    )
    service.reverse_transaction(
        receipt.id, firm_scope=firm.id, actor_id=actor_id, reason="wrong goods"
    )
    session.commit()

    scope = _firm_scope(
        _principal(user_id, {"INVENTORY_LEDGER_VIEW", "INVENTORY_VIEW"}),
        session,
        firm.id,
    )

    ledger = list_ledger(scope=scope, page=1, page_size=50, db=session)
    transactions = list_transactions(scope=scope, page=1, page_size=50, db=session)

    written = {row.transaction_type for row in ledger.data}
    assert {"ADJUSTMENT", "RESERVE", "UNRESERVE", "DISPATCH"}.issubset(written)
    assert any(item.endswith("_REVERSAL") for item in written)
    assert {row.transaction_type for row in transactions.data} == written


def test_two_batches_of_one_product_are_two_stock_rows() -> None:
    """The batch is part of a stock row's identity, not a label on it.

    Two deliveries of the same medicine expiring months apart were one number,
    so "which units are being recalled" and "which expire first" had no data
    behind them.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "GRAIN")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    first = uuid4()
    second = uuid4()
    setup.close()

    session = factory()
    service = InventoryService(session)
    actor_id = uuid4()
    rows = [
        service._ensure_inventory_projection(
            firm_id=firm.id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        for batch_id in (first, second, None, first)
    ]

    assert rows[0].id != rows[1].id, "two batches must not share a stock row"
    assert rows[2].id not in {
        rows[0].id,
        rows[1].id,
    }, "untracked stock is its own row, not either batch"
    assert rows[3].id == rows[0].id, "the same batch must resolve to its own row"
    assert rows[0].batch_id == first
    assert rows[2].batch_id is None


def test_a_movement_records_the_batch_it_moved() -> None:
    """The ledger could not say which batch moved, so batch cost was unanswerable."""
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "GRAINL")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    batch_id = uuid4()
    setup.close()

    session = factory()
    service = InventoryService(session)
    actor_id = uuid4()
    inventory = service._ensure_inventory_projection(
        firm_id=firm.id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        actor_id=actor_id,
        batch_id=batch_id,
    )
    session.flush()
    transaction = service._stage_movement(
        inventory,
        actor_id=actor_id,
        movement=_Movement(
            transaction_type="GOODS_RECEIPT",
            reference_number="GRN-GRAIN-1",
            reference_type="GOODS_RECEIPT",
            transaction_date=date(2026, 8, 13),
            quantity=Decimal("10"),
            current_delta=Decimal("10"),
            unit_cost=Decimal("100"),
        ),
    )
    session.commit()

    assert (
        transaction.batch_id == batch_id
    ), "the movement takes the batch of the stock it moved"
    ledger = session.scalar(
        select(StockLedgerEntry).where(
            StockLedgerEntry.transaction_id == transaction.id
        )
    )
    assert ledger is not None
    assert ledger.batch_id == batch_id, "the ledger must be able to price a batch"


def test_product_totals_sum_across_a_product_s_batches() -> None:
    """A batch-tracked product is several rows, so its total is a sum.

    The list endpoint still returns the individual rows -- which batch stock is
    in is the reason the grain changed -- so the total has to live somewhere
    else, beside the by-branch and by-warehouse rollups.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "ROLLUP")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    setup.close()

    session = factory()
    service = InventoryService(session)
    actor_id = uuid4()
    for batch_id, quantity in ((uuid4(), "40"), (uuid4(), "60"), (None, "5")):
        inventory = service._ensure_inventory_projection(
            firm_id=firm.id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            actor_id=actor_id,
            batch_id=batch_id,
        )
        session.flush()
        service._stage_movement(
            inventory,
            actor_id=actor_id,
            movement=_Movement(
                transaction_type="GOODS_RECEIPT",
                reference_number=f"GRN-ROLLUP-{quantity}",
                reference_type="GOODS_RECEIPT",
                transaction_date=date(2026, 8, 13),
                quantity=Decimal(quantity),
                current_delta=Decimal(quantity),
                batch_id=batch_id,
            ),
        )
    session.commit()

    totals = service.stock_by_product(firm_scope=firm.id)

    assert len(totals) == 1, "one product, however many batches hold it"
    assert totals[0].scope_id == product_id
    assert totals[0].current_quantity == Decimal("105"), (
        "two batches and the untracked row must add up"
    )


def test_a_product_that_must_be_issued_from_a_batch_is_not_shipped_untracked() -> None:
    """``require_batch_on_issue`` was stored and read by nothing.

    Untracked stock is exactly what the flag forbids, so it must not be
    allocated: shipping it is shipping goods nobody can trace, which is the
    situation the flag exists to prevent.
    """
    factory = _session_factory()
    setup = factory()
    firm = _firm(setup, "MUSTBAT")
    profile = _profile(setup, firm.id)
    branch, warehouse, product = _branch_warehouse_product(setup, firm, profile)
    product.require_batch_on_issue = True
    setup.commit()
    branch_id, warehouse_id, product_id = branch.id, warehouse.id, product.id
    setup.close()

    session = factory()
    service = InventoryService(session)
    actor_id = uuid4()
    # Stock exists, but none of it is in a batch.
    inventory = service._ensure_inventory_projection(
        firm_id=firm.id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        storage_node_id=None,
        product_id=product_id,
        actor_id=actor_id,
        batch_id=None,
    )
    session.flush()
    service._stage_movement(
        inventory,
        actor_id=actor_id,
        movement=_Movement(
            transaction_type="GOODS_RECEIPT",
            reference_number="GRN-MUSTBAT",
            reference_type="GOODS_RECEIPT",
            transaction_date=date(2026, 8, 13),
            quantity=Decimal("50"),
            current_delta=Decimal("50"),
        ),
    )
    session.commit()

    with pytest.raises(ValidationError, match="only be issued from a batch"):
        service.allocate_for_dispatch(
            firm_scope=firm.id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            storage_node_id=None,
            product_id=product_id,
            quantity=Decimal("10"),
        )
