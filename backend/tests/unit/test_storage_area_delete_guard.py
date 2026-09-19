"""A storage area holding stock is not deleted, nor a place a document names.

D-MST-8: ``delete_storage_node`` checked only for live children, while stock
is held per node and every movement naming a deleted node is refused -- so
`T0919P81V-BIN` was deleted holding 5 and the transfer back out answered
"Storage node does not belong to the selected warehouse." The warehouse and
the branch looked at stock and at warehouses, and at no document in flight.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.branches.schemas import (
    BranchCreate,
    BulkIdsRequest,
    StorageNodeCreate,
    WarehouseCreate,
)
from app.branches.services import BranchWarehouseService
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.sales_order.models import SalesOrder, SalesOrderLine


class _Setup:
    """A firm with one branch, one warehouse and one bin in it."""

    def __init__(self) -> None:
        """Build the places through the service, as the screens do."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session: Session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.firm = Firm(
            name="Bins Firm",
            code="BINS",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        self.actor = uuid4()
        self.service = BranchWarehouseService(self.session)
        self.branch: Branch = self.service.create_branch(
            BranchCreate.model_validate(
                {"code": "HO", "name": "Head office", "currency_code": "INR"}
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        self.warehouse: Warehouse = self.service.create_warehouse(
            WarehouseCreate.model_validate(
                {"branch_id": self.branch.id, "code": "MAIN", "name": "Main"}
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        self.bin: WarehouseStorageNode = self.service.create_storage_node(
            StorageNodeCreate.model_validate(
                {
                    "warehouse_id": self.warehouse.id,
                    "node_type": "BIN",
                    "code": "BIN-1",
                    "name": "Bin 1",
                }
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="BIN-P",
            name="Binned",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        self.session.add(self.product)
        self.session.commit()

    def stock_in_bin(self, on_hand: str) -> InventoryRecord:
        """Put a quantity of the product in the bin."""
        row = InventoryRecord(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            storage_node_id=self.bin.id,
            storage_locator="BIN-1",
            product_id=self.product.id,
            current_quantity=Decimal(on_hand),
            available_quantity=Decimal(on_hand),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def order(self, number: str, status: str, *, node_id: UUID | None = None) -> None:
        """Add a one-line sales order shipping from this warehouse."""
        order = SalesOrder(
            firm_id=self.firm.id,
            customer_id=uuid4(),
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            order_number=number,
            order_date=date(2026, 9, 19),
            status=status,
        )
        self.session.add(order)
        self.session.flush()
        self.session.add(
            SalesOrderLine(
                sales_order_id=order.id,
                firm_id=self.firm.id,
                line_number=1,
                product_id=self.product.id,
                quantity=Decimal("1"),
                warehouse_id=self.warehouse.id,
                storage_node_id=node_id,
            )
        )
        self.session.commit()

    def delete_bin(self) -> None:
        """Delete the bin as the storage screen does."""
        self.service.delete_storage_node(
            self.bin.id, firm_scope=self.firm.id, actor_id=self.actor
        )


def test_a_bin_holding_stock_is_refused_by_quantity() -> None:
    """The refusal names how much, of what, and the bin stays."""
    setup = _Setup()
    setup.stock_in_bin("5")

    with pytest.raises(ValidationError) as refused:
        setup.delete_bin()
    setup.session.rollback()

    message = str(refused.value)
    assert "BIN-1 cannot be deleted" in message
    assert "holds 5 in MAIN / BIN-1 (BIN-P)" in message
    setup.session.refresh(setup.bin)
    assert setup.bin.is_deleted is False


def test_a_bin_an_open_order_line_names_is_refused() -> None:
    """The line would fail at dispatch exactly as a movement does."""
    setup = _Setup()
    setup.order("SO-BIN", "APPROVED", node_id=setup.bin.id)

    with pytest.raises(ValidationError, match="1 sales order \\(SO-BIN\\)"):
        setup.delete_bin()


def test_an_emptied_bin_is_deleted_and_the_delete_is_audited() -> None:
    """Back at nothing, the bin goes -- and the trail now says who removed it."""
    setup = _Setup()
    row = setup.stock_in_bin("5")
    row.current_quantity = Decimal("0")
    row.available_quantity = Decimal("0")
    setup.session.commit()
    setup.order("SO-DONE", "CANCELLED", node_id=setup.bin.id)

    setup.delete_bin()

    setup.session.refresh(setup.bin)
    assert setup.bin.is_deleted is True
    audit = setup.session.scalar(
        select(AuditLog).where(AuditLog.action == "warehouse.storage_node.deleted")
    )
    assert audit is not None
    assert audit.entity_id == setup.bin.id
    assert audit.firm_id == setup.firm.id


def test_a_warehouse_an_open_document_names_is_refused_singly_and_in_bulk() -> None:
    """No stock in it, but an approved order still has to ship from it."""
    setup = _Setup()
    setup.order("SO-WH", "APPROVED")

    with pytest.raises(ValidationError) as refused:
        setup.service.delete_warehouse(
            setup.warehouse.id, firm_scope=setup.firm.id, actor_id=setup.actor
        )
    setup.session.rollback()
    assert "MAIN cannot be deleted" in str(refused.value)
    assert "1 sales order (SO-WH)" in str(refused.value)

    with pytest.raises(ValidationError, match="SO-WH"):
        setup.service.bulk_delete_warehouses(
            BulkIdsRequest(ids=[setup.warehouse.id]),
            firm_scope=setup.firm.id,
            actor_id=setup.actor,
        )
    setup.session.rollback()
    setup.session.refresh(setup.warehouse)
    assert setup.warehouse.is_deleted is False


def test_a_branch_an_open_document_names_is_refused() -> None:
    """Its warehouses gone, a branch is still held by what was raised under it."""
    setup = _Setup()
    setup.order("SO-BR", "DRAFT")
    # The warehouse is retired directly, so the branch's own check is reached.
    setup.warehouse.is_deleted = True
    setup.session.commit()

    with pytest.raises(ValidationError, match="HO cannot be deleted"):
        setup.service.delete_branch(
            setup.branch.id, firm_scope=setup.firm.id, actor_id=setup.actor
        )
    setup.session.rollback()
    setup.session.refresh(setup.branch)
    assert setup.branch.is_deleted is False
