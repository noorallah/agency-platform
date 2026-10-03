"""Formal amendment of an approved purchase order (BUY-8, decision A102).

* ``purchase_orders.revision_number`` (0 = as first approved).
* ``purchase_order_revisions``: each earlier version -- the header terms and
  lines as they stood, the total and why it changed.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0268
Revises: 20261003_0267
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0268"
down_revision: str | Sequence[str] | None = "20261003_0267"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_order_revisions"


def upgrade() -> None:
    """Add the counter and the revisions table where missing."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("purchase_orders"):
        return
    if "revision_number" not in {
        c["name"] for c in inspector.get_columns("purchase_orders")
    }:
        op.add_column(
            "purchase_orders",
            sa.Column(
                "revision_number",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
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
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("purchase_order_id", UUIDType(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("grand_total", sa.Numeric(18, 4), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_purchase_order_revisions"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name="FK_purchase_order_revisions_purchase_order_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "purchase_order_id",
            "revision_number",
            name="UQ_purchase_order_revisions_order_revision",
        ),
    )
    op.create_index("IX_purchase_order_revisions_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_purchase_order_revisions_purchase_order_id", _TABLE, ["purchase_order_id"]
    )


def downgrade() -> None:
    """Drop the table and the counter."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("purchase_orders") and "revision_number" in {
        c["name"] for c in inspector.get_columns("purchase_orders")
    }:
        op.drop_column("purchase_orders", "revision_number")
