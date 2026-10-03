"""Repacking and bulk breaking (STK-4, decision A114).

``repacks`` and ``repack_lines``: goods consumed and produced in one
warehouse, the value carried and the wastage written off.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0278
Revises: 20261003_0277
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0278"
down_revision: str | Sequence[str] | None = "20261003_0277"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create both tables where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("inventory_transactions"):
        return
    if not inspector.has_table("repacks"):
        op.create_table(
            "repacks",
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("repack_number", sa.String(60), nullable=False),
            sa.Column("repack_date", sa.Date(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("warehouse_id", UUIDType(), nullable=False),
            sa.Column(
                "wastage_percent",
                sa.Numeric(7, 4),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column(
                "consumed_value",
                sa.Numeric(18, 4),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column(
                "wastage_value",
                sa.Numeric(18, 4),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_repacks"),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="FK_repacks_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="FK_repacks_warehouse_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_repacks_firm_id", "repacks", ["firm_id"])
        op.create_index("IX_repacks_firm_date", "repacks", ["firm_id", "repack_date"])
    if not inspector.has_table("repack_lines"):
        op.create_table(
            "repack_lines",
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("repack_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("batch_id", UUIDType(), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column(
                "value", sa.Numeric(18, 4), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_repack_lines"),
            sa.ForeignKeyConstraint(
                ["repack_id"],
                ["repacks.id"],
                name="FK_repack_lines_repack_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_repack_lines_product_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["batch_id"],
                ["batches.id"],
                name="FK_repack_lines_batch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["inventory_transaction_id"],
                ["inventory_transactions.id"],
                name="FK_repack_lines_inventory_transaction_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index("IX_repack_lines_firm_id", "repack_lines", ["firm_id"])
        op.create_index("IX_repack_lines_repack", "repack_lines", ["repack_id"])


def downgrade() -> None:
    """Drop both tables."""
    inspector = sa.inspect(op.get_bind())
    for table in ("repack_lines", "repacks"):
        if inspector.has_table(table):
            op.drop_table(table)
