"""Expiry rules per product and category (STK-5, decision A113).

``expiry_stop_sale_days``, ``expiry_alert_days`` and ``expiry_return_days`` on
``products`` and ``product_categories``, all nullable: blank inherits the
category's, then the firm's.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0277
Revises: 20261003_0276
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0277"
down_revision: str | Sequence[str] | None = "20261003_0276"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("products", "product_categories")
_COLUMNS = ("expiry_stop_sale_days", "expiry_alert_days", "expiry_return_days")


def upgrade() -> None:
    """Add the three day counts where missing."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for column in _COLUMNS:
            if column not in have:
                op.add_column(table, sa.Column(column, sa.Integer()))


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for column in _COLUMNS:
            if column in have:
                op.drop_column(table, column)
