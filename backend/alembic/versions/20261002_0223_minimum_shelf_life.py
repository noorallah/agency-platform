"""A customer's minimum shelf life (backlog 79 row 6).

* ``customers.minimum_shelf_life_days``: how many days goods must have left
  when they reach this customer. Earliest-expiry allocation passes over a batch
  with less; None asks nothing.
* ``batch_sale_settings.shelf_life_policy``: what a batch chosen by hand with
  less does -- BLOCK (the default) refuses the dispatch, WARN records it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0223
Revises: 20261002_0222
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0223"
down_revision: str | Sequence[str] | None = "20261002_0222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("customers", sa.Column("minimum_shelf_life_days", sa.Integer(), nullable=True)),
    (
        "batch_sale_settings",
        sa.Column(
            "shelf_life_policy", sa.String(10), server_default="BLOCK", nullable=False
        ),
    ),
)


def upgrade() -> None:
    """Add each column where its table lives and it is missing."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if column.name in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.add_column(table, column)


def downgrade() -> None:
    """Drop the two columns."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if inspector.has_table(table) and column.name in {
            item["name"] for item in inspector.get_columns(table)
        }:
            op.drop_column(table, column.name)
