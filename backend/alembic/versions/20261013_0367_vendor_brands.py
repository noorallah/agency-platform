"""The brands a supplier may sell (backlog 129, row M11).

* ``vendor_brands``: one row per supplier and brand. A supplier with no row
  is not limited to any brand, so no existing supplier changes.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table is
created only where the store holds ``vendors`` and ``brands`` and lacks it,
because a firm store is partly built by ``Base.metadata.create_all`` and can
already have it. No row is written.

Revision ID: 20261013_0367
Revises: 20261013_0366
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0367"
down_revision: str | Sequence[str] | None = "20261013_0366"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "vendor_brands"


def upgrade() -> None:
    """Create the link between a supplier and the brands it may sell."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        return
    if not (inspector.has_table("vendors") and inspector.has_table("brands")):
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
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("brand_id", UUIDType(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_vendor_brands"),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name="FK_vendor_brands_vendor_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
            name="FK_vendor_brands_brand_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "UQ_vendor_brands_vendor_brand",
        _TABLE,
        ["vendor_id", "brand_id"],
        unique=True,
    )
    op.create_index("IX_vendor_brands_brand_id", _TABLE, ["brand_id"])
    op.create_index("ix_vendor_brands_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the link; no supplier is limited to a brand."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
