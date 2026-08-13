"""Make the batch part of a stock row's identity.

Stock was held per (firm, branch, warehouse, storage locator, product). Two
deliveries of the same medicine expiring eleven months apart were therefore one
number, and the questions batches exist to answer -- which units are being
recalled, which expire first, what this batch cost -- had no data behind them.
``batches`` kept its own quantity columns, maintained by its own API, that
nothing reconciled against ``inventories``: two registers of the same goods.

This is stage one of making the batch the grain:

* ``inventories.batch_id`` -- part of the row's identity, NULL where the
  product is not batch-tracked.
* ``stock_ledger_entries.batch_id`` -- the ledger could not say which batch
  moved, so batch cost and batch history were unanswerable even in principle.
  ``inventory_transactions`` already had the column and nothing ever set it.

**The unique key becomes two partial indexes, deliberately.** A single key over
``(location, product, batch_id)`` would not constrain untracked stock at all:
NULL is distinct from every other NULL in both PostgreSQL and SQLite, so a
product without batches could accumulate unlimited duplicate rows -- the exact
trap that has bitten this codebase twice this month. One index covers untracked
stock (one row per location), the other covers tracked stock (one row per
batch).

Existing rows keep ``batch_id`` NULL rather than being given an invented batch.
Stock whose origin nobody recorded has no batch, and manufacturing one would
put a fiction in the ledger.

What stage one does *not* do: goods receipt still records a batch number as free
text without creating a batch, dispatch does not pick by expiry, and
``batches`` still stores its own quantities. Those are stage two, where the
stored quantity becomes derivable and is removed.

Both tables are firm-owned: run ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260813_0070"
down_revision: str | Sequence[str] | None = "20260813_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_UNIQUE = "UQ_inventories_location_product"
_UNTRACKED = "UQ_inventories_location_product_untracked"
_TRACKED = "UQ_inventories_location_product_batch"


def upgrade() -> None:
    """Add the batch to stock identity and to the ledger."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventories"):
        return  # platform schema: firm-owned tables are not there.

    for table in ("inventories", "stock_ledger_entries"):
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "batch_id" not in columns:
            op.add_column(table, sa.Column("batch_id", UUIDType(), nullable=True))
            op.create_foreign_key(
                f"FK_{table}_batch_id",
                table,
                "batches",
                ["batch_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    indexes = {index["name"] for index in inspector.get_indexes("inventories")}
    if "IX_inventories_firm_batch" not in indexes:
        op.create_index(
            "IX_inventories_firm_batch", "inventories", ["firm_id", "batch_id"]
        )
    if "IX_stock_ledger_entries_firm_batch" not in {
        index["name"] for index in inspector.get_indexes("stock_ledger_entries")
    }:
        op.create_index(
            "IX_stock_ledger_entries_firm_batch",
            "stock_ledger_entries",
            ["firm_id", "batch_id"],
        )

    # The old key would forbid a second batch of the same product in the same
    # bay, which is precisely what this change is for.
    constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("inventories")
    }
    if _OLD_UNIQUE in constraints:
        # PostgreSQL reports a unique constraint's backing index under the same
        # name, so dropping the constraint takes the index with it. Dropping
        # both would fail on the second.
        op.drop_constraint(_OLD_UNIQUE, "inventories", type_="unique")
    elif _OLD_UNIQUE in indexes:
        op.drop_index(_OLD_UNIQUE, table_name="inventories")

    if bind.dialect.name != "postgresql":
        return
    location = ["firm_id", "branch_id", "warehouse_id", "storage_locator", "product_id"]
    if _UNTRACKED not in indexes:
        op.create_index(
            _UNTRACKED,
            "inventories",
            location,
            unique=True,
            postgresql_where=sa.text("batch_id IS NULL"),
        )
    if _TRACKED not in indexes:
        op.create_index(
            _TRACKED,
            "inventories",
            [*location, "batch_id"],
            unique=True,
            postgresql_where=sa.text("batch_id IS NOT NULL"),
        )


def downgrade() -> None:
    """Return stock to one row per product per location."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventories"):
        return
    indexes = {index["name"] for index in inspector.get_indexes("inventories")}
    for name in (_UNTRACKED, _TRACKED, "IX_inventories_firm_batch"):
        if name in indexes:
            op.drop_index(name, table_name="inventories")
    if "IX_stock_ledger_entries_firm_batch" in {
        index["name"] for index in inspector.get_indexes("stock_ledger_entries")
    }:
        op.drop_index(
            "IX_stock_ledger_entries_firm_batch", table_name="stock_ledger_entries"
        )
    for table in ("inventories", "stock_ledger_entries"):
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "batch_id" in columns:
            op.drop_constraint(f"FK_{table}_batch_id", table, type_="foreignkey")
            op.drop_column(table, "batch_id")
    # Only safe because batch-grained rows cannot exist before this revision.
    op.create_unique_constraint(
        _OLD_UNIQUE,
        "inventories",
        ["firm_id", "branch_id", "warehouse_id", "storage_locator", "product_id"],
    )
