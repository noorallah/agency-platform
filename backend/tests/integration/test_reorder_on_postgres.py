"""The below-reorder report on PostgreSQL, which the unit suite cannot be.

The report grouped stock rows by warehouse and product and took
``max(branch_id)`` of each group. SQLite takes the max of anything; PostgreSQL
has no ``max(uuid)`` and refused the statement, so the report answered 503 on
every deployed store from the day it was written while the SQLite suite stayed
green. The quick check found it on its first run, 2026-10-02.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.inventory.models import InventoryRecord
from app.products.models import Product
from app.purchase.services.reorder import ReorderService
from tests.unit.test_purchase_invoice_module import _branch, _firm, _warehouse


def test_stock_below_its_level_is_reported(temp_session: Session) -> None:
    """Two stock rows in one warehouse, 2 + 1 available against a level of 5."""
    firm = _firm(temp_session)
    branch = _branch(temp_session, firm_id=firm.id)
    warehouse = _warehouse(temp_session, firm_id=firm.id, branch_id=branch.id)
    product = Product(
        firm_id=firm.id,
        code="SKU-RE-1",
        name="Reordered",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    temp_session.add(product)
    temp_session.flush()
    for locator, available, level in (("A-1", "2", "5"), ("A-2", "1", None)):
        temp_session.add(
            InventoryRecord(
                firm_id=firm.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                storage_locator=locator,
                product_id=product.id,
                current_quantity=Decimal(available),
                available_quantity=Decimal(available),
                reorder_level=None if level is None else Decimal(level),
            )
        )
    temp_session.flush()

    [row] = ReorderService(temp_session).below_reorder(firm.id)

    assert row.product_id == product.id
    assert row.available_quantity == Decimal("3")
    assert row.reorder_level == Decimal("5")
