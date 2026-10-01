"""Typing a rate that includes GST on orders and quotations (backlog 64 row 4).

* ``sales_orders.rate_includes_tax`` and ``sales_quotations.rate_includes_tax``:
  the document's own switch. False on every document already written, which is
  what each of them meant.
* ``entered_rate`` and ``entered_discount_amount`` on ``sales_order_lines`` and
  ``sales_quotation_lines``: the rate and the discount amount as typed, GST
  included, beside the pre-tax figures they derived to. Null on every line
  already written.

Idempotent; firm-owned, so it runs per store (``scripts/migrate_all_stores.py``)
and touches only the tables a store holds.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0207"
down_revision: str | Sequence[str] | None = "20261001_0206"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[tuple[str, sa.Column]]:
    """Return each table and the column it gains, built fresh per call."""
    columns: list[tuple[str, sa.Column]] = []
    for table in ("sales_orders", "sales_quotations"):
        columns.append(
            (
                table,
                sa.Column(
                    "rate_includes_tax",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
        )
    for table in ("sales_order_lines", "sales_quotation_lines"):
        columns.append((table, sa.Column("entered_rate", sa.Numeric(18, 4))))
        columns.append((table, sa.Column("entered_discount_amount", sa.Numeric(18, 4))))
    return columns


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    """Return whether a table this store holds already has the column."""
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    """Add the columns wherever their table exists without them."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and not _has_column(
            inspector, table, column.name
        ):
            op.add_column(table, column)


def downgrade() -> None:
    """Drop the columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and _has_column(inspector, table, column.name):
            op.drop_column(table, column.name)
