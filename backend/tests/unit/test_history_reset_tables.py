"""Guard the table names the history reset is configured with.

``reset_history`` deletes a firm's trading history table by table. It used to
skip any name the database did not have, silently, and three of the names were
wrong: ``purchase_order_attachments`` and ``purchase_order_notes`` (harmless,
because those rows cascade from the order) and ``inventory_records`` -- really
``inventories``, and not harmless at all.

That one meant every regeneration deleted the movements, the ledger and the
valuation and left the stock projection standing. On-hand grew by a run's worth
each time and no ledger entry explained the balance; one store reached 4,547
units on hand with 700 accounted for.

The script now refuses to run on an unknown name, which turns the next typo
into a failed run instead of a quiet half-reset. This turns it into a failed
build instead, without needing a database: every configured name is checked
against the ORM metadata, which is the same set of tables a migrated store has.
"""

import sys
from pathlib import Path

from app.core.database.base import Base

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_transaction_history import (  # noqa: E402
    CHILD_TABLES,
    RESET_ORDER,
)


def _known_tables() -> set[str]:
    """Return every table the application declares.

    ``tests/conftest.py`` imports all model modules, so the metadata is
    complete regardless of which test ran first.
    """
    return set(Base.metadata.tables.keys())


def test_every_reset_table_is_a_real_table() -> None:
    """A name that matches no table clears nothing and says nothing."""
    unknown = sorted(set(RESET_ORDER) - _known_tables())
    assert not unknown, (
        f"reset_history would skip {unknown}: the rows it means to clear would "
        "survive the reset. Check the model's __tablename__."
    )


def test_every_child_table_and_its_parent_are_real_tables() -> None:
    """The child-table sweep runs before the main loop and is easy to miss."""
    known = _known_tables()
    unknown = sorted(
        name
        for table, _column, parent in CHILD_TABLES
        for name in (table, parent)
        if name not in known
    )
    assert not unknown, f"CHILD_TABLES names no such table: {unknown}"


def test_the_stock_projection_is_reset_with_its_ledger() -> None:
    """The three inventory tables have to go together, in this order.

    Clearing the movements and keeping the balance is the specific failure this
    module exists to prevent, and ``inventory_transactions`` holds a RESTRICT
    foreign key to ``inventories``, so the order is load-bearing too.
    """
    for table in ("stock_ledger_entries", "inventory_transactions", "inventories"):
        assert table in RESET_ORDER, f"{table} must be reset with the others"
    order = list(RESET_ORDER)
    assert order.index("stock_ledger_entries") < order.index("inventory_transactions")
    assert order.index("inventory_transactions") < order.index("inventories")


def test_no_master_table_is_reset() -> None:
    """Trading history goes; what a firm trades with stays."""
    masters = {
        "products",
        "customers",
        "vendors",
        "branches",
        "warehouses",
        "uoms",
        "uom_conversion_rules",
        "tax_profiles",
        "business_profiles",
    }
    caught = sorted(masters & set(RESET_ORDER))
    assert not caught, f"reset_history would delete master data: {caught}"
