"""Photos and documents kept with stock movements and count sheets (STK-9).

``stock_attachments``: one row per file, naming either the movement it backs
(an adjustment, a write-off, a transfer) or the count sheet, never both. Like
``delivery_note_attachments`` it records where the file is, not the file.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: created only in
a store that holds movements and lacks it.

Revision ID: 20261003_0246
Revises: 20261003_0245
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0246"
down_revision: str | Sequence[str] | None = "20261003_0245"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "stock_attachments"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("inventory_transactions") or inspector.has_table(_TABLE):
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
        sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
        sa.Column("physical_count_id", UUIDType(), nullable=True),
        sa.Column("file_name", sa.String(260), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("caption", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_stock_attachments"),
        sa.ForeignKeyConstraint(
            ["inventory_transaction_id"],
            ["inventory_transactions.id"],
            name="FK_stock_attachments_inventory_transaction_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["physical_count_id"],
            ["physical_counts.id"],
            name="FK_stock_attachments_physical_count_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(inventory_transaction_id IS NULL) <> (physical_count_id IS NULL)",
            name="CK_stock_attachments_one_parent",
        ),
    )
    op.create_index("IX_stock_attachments_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_stock_attachments_movement", _TABLE, ["inventory_transaction_id"]
    )
    op.create_index("IX_stock_attachments_count", _TABLE, ["physical_count_id"])


def downgrade() -> None:
    """Drop the table; the files themselves are untouched."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
