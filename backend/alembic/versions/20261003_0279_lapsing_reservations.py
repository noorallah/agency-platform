"""Stock held for an order that never ships lapses (STK-12, decision A115).

* ``sales_workflow_settings.reservation_lapse_days`` -- null: never.
* ``sales_orders.reservation_lapsed_at`` -- when an order's hold lapsed.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0279
Revises: 20261003_0278
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0279"
down_revision: str | Sequence[str] | None = "20261003_0278"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("sales_workflow_settings", "reservation_lapse_days", sa.Integer),
    ("sales_orders", "reservation_lapsed_at", lambda: sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    """Add both columns where missing."""
    inspector = sa.inspect(op.get_bind())
    for table, column, kind in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, kind()))


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    for table, column, _ in _COLUMNS:
        if inspector.has_table(table) and column in {
            c["name"] for c in inspector.get_columns(table)
        }:
            op.drop_column(table, column)
