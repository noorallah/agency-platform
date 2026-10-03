"""Kits and combo packs (STK-15, decision A134).

``product_kit_components``: what goes into one kit, a product of type
``BUNDLE``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0296
Revises: 20261003_0295
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0296"
down_revision: str | Sequence[str] | None = "20261003_0295"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the component table where a store keeps products."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("products") or inspector.has_table(
        "product_kit_components"
    ):
        return
    op.create_table(
        "product_kit_components",
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
        sa.Column("kit_product_id", UUIDType(), nullable=False),
        sa.Column("component_product_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.PrimaryKeyConstraint("id", name="PK_product_kit_components"),
        sa.ForeignKeyConstraint(
            ["kit_product_id"],
            ["products.id"],
            name="FK_product_kit_components_kit_product_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_product_id"],
            ["products.id"],
            name="FK_product_kit_components_component_product_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "IX_product_kit_components_firm_id", "product_kit_components", ["firm_id"]
    )
    op.create_index(
        "IX_product_kit_components_kit_product_id",
        "product_kit_components",
        ["kit_product_id"],
    )
    op.create_index(
        "UQ_product_kit_components_kit_component_active",
        "product_kit_components",
        ["kit_product_id", "component_product_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    """Drop the component table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("product_kit_components"):
        op.drop_table("product_kit_components")
