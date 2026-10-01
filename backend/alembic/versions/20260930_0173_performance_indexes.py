"""Indexes for the lists and lookups that scanned whole tables (backlog 56 C).

Found surveying the backend at a mid-size distributor's volume (about 100,000
invoices and 1.5 million stock movements over two years):

* a stock row's movements (``inventory_id`` on both movement tables) --
  read by table scan on every Inventory list page;
* the default newest-first sort of the movement lists and the invoice list;
* the movement number check, and the dispatch cost read that looks a
  document up by type and number on every invoice approval;
* the journal list's date filter;
* the receivable row a reversal or a GSTR cancellation date looks up by its
  reference.

Nothing changes in the data. Each index is created only where its table is
and it is not already there, so the migration is safe to replay; run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0173"
down_revision: str | Sequence[str] | None = "20260930_0169"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (index name, table, columns)
INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "IX_inventory_transactions_inventory",
        "inventory_transactions",
        ("inventory_id",),
    ),
    (
        "IX_inventory_transactions_firm_created",
        "inventory_transactions",
        ("firm_id", "created_at"),
    ),
    (
        "IX_inventory_transactions_firm_number",
        "inventory_transactions",
        ("firm_id", "reference_number"),
    ),
    ("IX_stock_ledger_entries_inventory", "stock_ledger_entries", ("inventory_id",)),
    (
        "IX_stock_ledger_entries_firm_created",
        "stock_ledger_entries",
        ("firm_id", "created_at"),
    ),
    (
        "IX_stock_ledger_entries_reference",
        "stock_ledger_entries",
        ("reference_type", "reference_number"),
    ),
    ("IX_journal_entries_firm_date", "journal_entries", ("firm_id", "journal_date")),
    ("IX_sales_invoices_firm_created", "sales_invoices", ("firm_id", "created_at")),
    (
        "IX_customer_ar_tx_reference",
        "customer_receivable_transactions",
        ("reference_type", "reference_id"),
    ),
)


def upgrade() -> None:
    """Create each index where its table is and it is missing."""
    inspector = sa.inspect(op.get_bind())
    for name, table, columns in INDEXES:
        if not inspector.has_table(table):
            continue
        if any(index["name"] == name for index in inspector.get_indexes(table)):
            continue
        op.create_index(name, table, list(columns))


def downgrade() -> None:
    """Drop the indexes this migration added."""
    inspector = sa.inspect(op.get_bind())
    for name, table, _ in reversed(INDEXES):
        if not inspector.has_table(table):
            continue
        if any(index["name"] == name for index in inspector.get_indexes(table)):
            op.drop_index(name, table_name=table)
