"""Approval as a step of its own, per sales document (backlog 119).

``sales_workflow_settings`` gains ``sales_order_approval``,
``delivery_note_approval`` and ``sales_invoice_approval``: whether a new
document of that kind waits for somebody who holds the approve code. Each of
``sales_orders``, ``delivery_notes`` and ``sales_invoices`` gains
``approval_step``, the answer stamped on the document as it is raised.

Every column is NOT NULL and defaults to true, which is how every firm and
every document already stored behaves, so there is nothing to backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a column is
added only where the store holds the table and lacks it, because a firm store
is partly built by ``Base.metadata.create_all`` and can already have it.

Revision ID: 20261013_0360
Revises: 20261013_0359
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0360"
down_revision: str | Sequence[str] | None = "20261013_0359"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sales_workflow_settings", "sales_order_approval"),
    ("sales_workflow_settings", "delivery_note_approval"),
    ("sales_workflow_settings", "sales_invoice_approval"),
    ("sales_orders", "approval_step"),
    ("delivery_notes", "approval_step"),
    ("sales_invoices", "approval_step"),
)


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    """Say whether the store's table already has the column."""
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    """Add each column where a store holds the table and lacks it."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if not _has_column(inspector, table, column):
            op.add_column(
                table,
                sa.Column(
                    column,
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )


def downgrade() -> None:
    """Drop each column where a store has it."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if _has_column(inspector, table, column):
            op.drop_column(table, column)
