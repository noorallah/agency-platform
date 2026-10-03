"""A supplier's catalogue, dated rows per product (BUY-4, decision A101).

``supplier_products``: per supplier and product, their code and name, price,
pack size, minimum order and lead time, from an ``effective_from`` -- never
overwritten, so the history stays. One live row per supplier, product and
date.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0267
Revises: 20261003_0266
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0267"
down_revision: str | Sequence[str] | None = "20261003_0266"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "supplier_products"


def upgrade() -> None:
    """Create the table in a firm store that lacks it."""
    inspector = sa.inspect(op.get_bind())
    if (
        inspector.has_table(_TABLE)
        or not inspector.has_table("vendors")
        or not inspector.has_table("products")
    ):
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
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("supplier_product_code", sa.String(120), nullable=True),
        sa.Column("supplier_product_name", sa.String(200), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("pack_size", sa.Numeric(18, 4), nullable=True),
        sa.Column("minimum_order_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_supplier_products"),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name="FK_supplier_products_vendor_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="FK_supplier_products_product_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_supplier_products_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_supplier_products_vendor_product",
        _TABLE,
        ["firm_id", "vendor_id", "product_id", "effective_from"],
    )
    op.create_index(
        "UQ_supplier_products_dated_active",
        _TABLE,
        ["vendor_id", "product_id", "effective_from"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the table."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
