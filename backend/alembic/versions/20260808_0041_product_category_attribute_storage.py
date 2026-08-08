"""Store product category attributes in the product row.

Revision ID: 20260808_0041
Revises: 20260808_0040
Create Date: 2026-08-08 09:45:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260808_0041"
down_revision = "20260808_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("products"):
        return
    columns = {column["name"] for column in inspector.get_columns("products")}
    if "category_attribute_values" not in columns:
        op.add_column(
            "products",
            sa.Column("category_attribute_values", sa.JSON(), nullable=False, server_default="[]"),
        )
        op.execute(sa.text("UPDATE products SET category_attribute_values = '[]'::json WHERE category_attribute_values IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("products"):
        return
    columns = {column["name"] for column in inspector.get_columns("products")}
    if "category_attribute_values" in columns:
        op.drop_column("products", "category_attribute_values")
