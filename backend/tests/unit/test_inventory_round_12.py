"""Inventory round 12: what the levels, references and figures accept.

D-STK-68: an opening-stock reference of only spaces was saved empty.
D-STK-69: a figure too large for its column was answered as an outage.
D-STK-70: a stock row that was removed could still have its levels written.
D-STK-71: inventory's own writes brought a service into stock.
D-STK-72: an opening-stock line took levels the stock row itself refuses.
"""

import asyncio
import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select
from sqlalchemy.exc import DataError, OperationalError

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.exceptions.handlers import database_error_handler
from app.inventory.models import InventoryRecord
from app.inventory.schemas.inventory import (
    InventoryAdjustmentCreate,
    InventoryCreate,
    InventoryUpdate,
    OpeningStockBatchCreate,
    OpeningStockImportRequest,
    StockQuarantineCreate,
    StockWriteOffCreate,
)
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.repacking import RepackService, RepackWrite
from app.products.models import Product
from tests.unit.test_inventory_foundation import (
    _branch_warehouse_product,
    _firm,
    _profile,
    _session_factory,
)

pytestmark = pytest.mark.typed_document_numbers

ON = date(2026, 8, 1)
HUGE = "999999999999999999"


class _World:
    """One firm with a branch, a warehouse, a stock item and a service."""

    def __init__(self, code: str) -> None:
        """Build the firm and its masters."""
        self.session = _session_factory()()
        self.firm = _firm(self.session, code)
        profile = _profile(self.session, self.firm.id)
        self.branch, self.warehouse, self.product = _branch_warehouse_product(
            self.session, self.firm, profile
        )
        self.actor_id = uuid4()
        self.service = Product(
            firm_id=self.firm.id,
            code="SRV-001",
            name="Installation",
            product_type="SERVICE",
            status="ACTIVE",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.session.add(self.service)
        self.session.commit()
        self.inventory = InventoryService(self.session)

    def place(self, product: Product | None = None) -> dict[str, object]:
        """Return the keys that name a product in the warehouse."""
        return {
            "branch_id": self.branch.id,
            "warehouse_id": self.warehouse.id,
            "product_id": (product or self.product).id,
        }

    def opening(self, reference: str, **line: object) -> OpeningStockBatchCreate:
        """Return an opening-stock document of one line."""
        return OpeningStockBatchCreate(
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            reference_number=reference,
            posting_date=ON,
            lines=[{"product_id": self.product.id, "quantity": "5", **line}],
        )

    def rows(self, product: Product) -> list[InventoryRecord]:
        """Return the stock rows a product holds, removed ones left out."""
        return list(
            self.session.scalars(
                select(InventoryRecord).where(
                    InventoryRecord.product_id == product.id,
                    InventoryRecord.is_deleted.is_(False),
                )
            ).all()
        )


@pytest.mark.parametrize("typed", ["   ", " X ", "\t\n"])
def test_an_opening_reference_of_spaces_is_refused(typed: str) -> None:
    """Spaces are not a reference: the document was saved under an empty one."""
    world = _World("R12A")
    with pytest.raises(SchemaError, match="reference number"):
        world.opening(typed)
    with pytest.raises(SchemaError, match="reference number"):
        OpeningStockImportRequest(
            reference_number=typed,
            posting_date=ON,
            branch_id=world.branch.id,
            warehouse_id=world.warehouse.id,
            lines=[{"product_id": world.product.id, "quantity": "1"}],
        )


def test_an_opening_reference_is_kept_without_the_spaces_around_it() -> None:
    """What is typed with spaces around it is the reference inside them."""
    world = _World("R12B")
    batch = world.inventory.create_opening_stock_batch(
        world.opening("  os-12  "), firm_id=world.firm.id, actor_id=world.actor_id
    )
    assert batch.reference_number == "OS-12"


@pytest.mark.parametrize(
    "levels",
    [
        {"minimum_level": "9", "maximum_level": "3"},
        {"reorder_level": "9", "maximum_level": "3"},
    ],
)
def test_an_opening_line_holds_its_levels_to_the_stock_rows_rule(
    levels: dict[str, str],
) -> None:
    """The line is a second way to write the levels, so it refuses the same."""
    world = _World("R12C")
    with pytest.raises(SchemaError, match="level"):
        world.opening("OS-LV", **levels)
    with pytest.raises(SchemaError, match="level"):
        InventoryCreate(**world.place(), **levels)


def test_a_figure_too_large_for_its_column_is_refused_by_name() -> None:
    """Every stock figure stops at what a Numeric(18, 4) column holds."""
    world = _World("R12D")
    place = world.place()
    dated = {**place, "transaction_date": ON}
    with pytest.raises(SchemaError, match="maximum_level"):
        InventoryUpdate(**place, maximum_level=HUGE)
    with pytest.raises(SchemaError, match="quantity"):
        world.opening("OS-HG", quantity=HUGE)
    with pytest.raises(SchemaError, match="unit_cost"):
        world.opening("OS-HC", unit_cost=HUGE)
    with pytest.raises(SchemaError, match="quantity"):
        InventoryAdjustmentCreate(**dated, quantity=HUGE)
    with pytest.raises(SchemaError, match="quantity"):
        InventoryAdjustmentCreate(**dated, quantity=f"-{HUGE}")
    with pytest.raises(SchemaError, match="quantity"):
        StockWriteOffCreate(**dated, quantity=HUGE, reason="DAMAGE")
    with pytest.raises(SchemaError, match="quantity"):
        StockQuarantineCreate(**dated, quantity=HUGE, action="HOLD")
    with pytest.raises(SchemaError, match="worth more than can be recorded"):
        world.opening("OS-HW", quantity="99999999999999", unit_cost="999999999999")
    assert InventoryUpdate(**place, maximum_level="99999999999999").maximum_level == (
        Decimal("99999999999999")
    )


def test_a_value_the_database_refuses_is_the_requests_fault() -> None:
    """A numeric overflow is a 422; a lost connection is still a 503."""
    refused = asyncio.run(
        database_error_handler(
            None,  # type: ignore[arg-type]
            DataError("INSERT", {}, Exception("numeric field overflow")),
        )
    )
    assert refused.status_code == 422
    assert "too large" in json.dumps(json.loads(bytes(refused.body)))
    outage = asyncio.run(
        database_error_handler(
            None,  # type: ignore[arg-type]
            OperationalError("SELECT", {}, Exception("connection refused")),
        )
    )
    assert outage.status_code == 503


def test_a_removed_stock_row_cannot_have_its_levels_written() -> None:
    """A row nobody can list is not one somebody can edit."""
    world = _World("R12E")
    row = world.inventory.create_inventory_record(
        InventoryCreate(**world.place(), reorder_level="4"),
        firm_id=world.firm.id,
        actor_id=world.actor_id,
    )
    row.is_deleted = True
    world.session.commit()
    with pytest.raises(ResourceNotFoundError):
        world.inventory.update_inventory_record(
            row.id,
            InventoryUpdate(**world.place(), reorder_level="7"),
            firm_scope=world.firm.id,
            actor_id=world.actor_id,
        )
    world.session.refresh(row)
    assert row.reorder_level == Decimal("4")


def test_a_service_is_not_brought_into_stock() -> None:
    """A row by hand, an adjustment upwards, opening stock and a repack."""
    world = _World("R12F")
    place = world.place(world.service)
    says = "never held as stock"
    with pytest.raises(ValidationError, match=says):
        world.inventory.create_inventory_record(
            InventoryCreate(**place), firm_id=world.firm.id, actor_id=world.actor_id
        )
    adjustment = InventoryAdjustmentCreate(**place, quantity="5", transaction_date=ON)
    with pytest.raises(ValidationError, match=says):
        world.inventory.assert_postable(adjustment, firm_scope=world.firm.id)
    with pytest.raises(ValidationError, match=says):
        world.inventory.create_adjustment(
            adjustment, firm_scope=world.firm.id, actor_id=world.actor_id
        )
    with pytest.raises(ValidationError, match=says):
        world.inventory.create_opening_stock_batch(
            OpeningStockBatchCreate(
                branch_id=world.branch.id,
                warehouse_id=world.warehouse.id,
                reference_number="OS-SRV",
                posting_date=ON,
                lines=[{"product_id": world.service.id, "quantity": "3"}],
            ),
            firm_id=world.firm.id,
            actor_id=world.actor_id,
        )
    with pytest.raises(ValidationError, match=says):
        RepackService(world.session).post(
            RepackWrite(
                repack_date=ON,
                branch_id=world.branch.id,
                warehouse_id=world.warehouse.id,
                lines=[
                    {
                        "kind": "CONSUME",
                        "product_id": world.product.id,
                        "quantity": "1",
                    },
                    {
                        "kind": "PRODUCE",
                        "product_id": world.service.id,
                        "quantity": "1",
                    },
                ],
            ),
            firm_id=world.firm.id,
            actor_id=world.actor_id,
        )
    world.session.rollback()
    assert world.rows(world.service) == []


def test_a_service_already_in_stock_can_still_be_taken_out() -> None:
    """Only the way in is closed: a firm that holds some adjusts it away."""
    world = _World("R12G")
    world.session.add(
        InventoryRecord(
            firm_id=world.firm.id,
            branch_id=world.branch.id,
            warehouse_id=world.warehouse.id,
            storage_locator="ROOT",
            product_id=world.service.id,
            current_quantity=Decimal("3"),
            available_quantity=Decimal("3"),
            reserved_quantity=Decimal("0"),
            blocked_quantity=Decimal("0"),
            damaged_quantity=Decimal("0"),
            quarantine_quantity=Decimal("0"),
            in_transit_quantity=Decimal("0"),
            status="ACTIVE",
            created_by=world.actor_id,
            updated_by=world.actor_id,
        )
    )
    world.session.commit()
    world.inventory.create_adjustment(
        InventoryAdjustmentCreate(
            **world.place(world.service), quantity="-3", transaction_date=ON
        ),
        firm_scope=world.firm.id,
        actor_id=world.actor_id,
    )
    assert world.rows(world.service)[0].current_quantity == Decimal("0")
