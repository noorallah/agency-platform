"""A batch carries its own MRP and selling price (backlog 79 row 7).

* ``batches.mrp`` and ``batches.selling_price``, per stock unit: the MRP the
  manufacturer printed on this batch (with tax) and the rate it is sold at
  (before tax), as Marg and Busy keep them.
* ``goods_receipt_lines.mrp`` and ``.selling_price``: captured on the receipt
  and handed to the batch it creates or names.
* ``batch_sale_settings.price_from_batch``: whether a line with a chosen batch
  takes the batch's rate. Off.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0225
Revises: 20261002_0224
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0225"
down_revision: str | Sequence[str] | None = "20261002_0224"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> tuple[tuple[str, sa.Column], ...]:
    """Return each table and the column it gains, built fresh per call."""
    return (
        ("batches", sa.Column("mrp", sa.Numeric(18, 2), nullable=True)),
        ("batches", sa.Column("selling_price", sa.Numeric(18, 2), nullable=True)),
        ("goods_receipt_lines", sa.Column("mrp", sa.Numeric(18, 2), nullable=True)),
        (
            "goods_receipt_lines",
            sa.Column("selling_price", sa.Numeric(18, 2), nullable=True),
        ),
        (
            "batch_sale_settings",
            sa.Column(
                "price_from_batch",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        ),
    )


def upgrade() -> None:
    """Add each column where its table lives and it is missing."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if not inspector.has_table(table):
            continue
        if column.name in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.add_column(table, column)


def downgrade() -> None:
    """Drop the columns."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and column.name in {
            item["name"] for item in inspector.get_columns(table)
        }:
            op.drop_column(table, column.name)
