"""Guards for what made the busiest screens slow at a real firm's volume.

Backlog 56 C, `docs/PERFORMANCE_AT_VOLUME.md`. Each of these was found by
reading the code against two years of a mid-size distributor's data; none of
them shows in a test database of a few dozen rows, which is why they are
pinned here rather than left to a timing run to rediscover.
"""

from sqlalchemy import inspect

from app.core.database.base import Base
from app.inventory.models import InventoryRecord, InventoryTransaction

#: Collections that grow with every movement a firm ever makes.
GROWING = (
    (InventoryRecord, "transactions"),
    (InventoryRecord, "ledger_entries"),
    (InventoryTransaction, "ledger_entries"),
)

#: (table, columns) that a hot list or look-up filters or sorts on.
INDEXED = (
    ("inventory_transactions", ("inventory_id",)),
    ("inventory_transactions", ("firm_id", "created_at")),
    ("inventory_transactions", ("firm_id", "reference_number")),
    ("stock_ledger_entries", ("inventory_id",)),
    ("stock_ledger_entries", ("firm_id", "created_at")),
    ("stock_ledger_entries", ("reference_type", "reference_number")),
    ("journal_entries", ("firm_id", "journal_date")),
    ("sales_invoices", ("firm_id", "created_at")),
    ("customer_receivable_transactions", ("reference_type", "reference_id")),
)


def test_a_growing_history_is_never_loaded_with_its_row() -> None:
    """A stock row loaded its every movement on each read (lazy="selectin").

    That made the Inventory list, and every dispatch, receipt and adjustment,
    slower every year. The history is read only when something asks for it.
    """
    for model, name in GROWING:
        lazy = inspect(model).relationships[name].lazy
        assert lazy != "selectin", f"{model.__name__}.{name} is {lazy}"
        assert lazy != "joined", f"{model.__name__}.{name} is {lazy}"


def test_every_hot_lookup_has_an_index() -> None:
    """Each filter and sort the busy lists use has an index leading with it."""
    missing = []
    for table_name, columns in INDEXED:
        table = Base.metadata.tables[table_name]
        leading = [
            tuple(column.name for column in index.columns)[: len(columns)]
            for index in table.indexes
        ]
        leading += [
            tuple(column.name for column in constraint.columns)[: len(columns)]
            for constraint in table.constraints
            if hasattr(constraint, "columns") and len(constraint.columns) > 0
        ]
        if columns not in leading:
            missing.append(f"{table_name}{columns}")
    assert missing == []
