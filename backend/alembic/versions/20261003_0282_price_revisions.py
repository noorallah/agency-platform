"""Price revisions with an effective date (MST-2, decision A119).

``product_price_revisions``: per product and date, any of selling price,
purchase price and MRP; one live revision per product per date.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0282
Revises: 20261003_0281
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0282"
down_revision: str | Sequence[str] | None = "20261003_0281"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "product_price_revisions"


def upgrade() -> None:
    """Create the table where a firm store lacks it."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) or not inspector.has_table("products"):
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
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("selling_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("purchase_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("mrp", sa.Numeric(18, 4), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_product_price_revisions"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="FK_product_price_revisions_product_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_product_price_revisions_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "UQ_product_price_revisions_dated_active",
        _TABLE,
        ["product_id", "effective_from"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
