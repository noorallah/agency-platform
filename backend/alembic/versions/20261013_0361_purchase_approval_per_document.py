"""Approval as a step of its own, per purchase document (backlog 120).

``purchase_workflow_settings`` gains ``purchase_order_approval``,
``goods_receipt_approval`` and ``purchase_invoice_approval``: whether a new
document of that kind waits for a step after its Save. Each of
``purchase_orders``, ``goods_receipts`` and ``purchase_invoices`` gains
``approval_step``, the answer stamped on the document as it is raised. The
buying twin of ``20261013_0360``.

Every column is NOT NULL and defaults to true, which is how every firm and
every document already stored behaves, so there is nothing to backfill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a column is
added only where the store holds the table and lacks it, because a firm store
is partly built by ``Base.metadata.create_all`` and can already have it.

Revision ID: 20261013_0361
Revises: 20261013_0360
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0361"
down_revision: str | Sequence[str] | None = "20261013_0360"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("purchase_workflow_settings", "purchase_order_approval"),
    ("purchase_workflow_settings", "goods_receipt_approval"),
    ("purchase_workflow_settings", "purchase_invoice_approval"),
    ("purchase_orders", "approval_step"),
    ("goods_receipts", "approval_step"),
    ("purchase_invoices", "approval_step"),
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
