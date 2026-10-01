"""Typing a rate that includes GST (backlog 64 row 4).

* ``sales_workflow_settings.rate_includes_tax``: the firm's default for a new
  counter bill's "Rate includes GST" switch. False, so nothing changes for a
  firm until it chooses.
* ``sales_invoices.rate_includes_tax``: the bill's own switch. False on every
  bill already written, which is what each of them meant.
* ``sales_invoice_lines.entered_rate``: the rate as typed, GST included, beside
  the pre-tax ``unit_price`` it derived to. Null on every line already written.

Idempotent; firm-owned, so it runs per store (``scripts/migrate_all_stores.py``)
and touches only the tables a store holds.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0200"
down_revision: str | Sequence[str] | None = "20261001_0199"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[tuple[str, sa.Column]]:
    """Return each table and the column it gains, built fresh per call."""
    return [
        (
            "sales_workflow_settings",
            sa.Column(
                "rate_includes_tax",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        (
            "sales_invoices",
            sa.Column(
                "rate_includes_tax",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        (
            "sales_invoice_lines",
            sa.Column("entered_rate", sa.Numeric(18, 4), nullable=True),
        ),
    ]


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    """Return whether a table this store holds already has the column."""
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    """Add the three columns wherever their table exists without them."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and not _has_column(
            inspector, table, column.name
        ):
            op.add_column(table, column)


def downgrade() -> None:
    """Drop the three columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and _has_column(inspector, table, column.name):
            op.drop_column(table, column.name)
