"""Named price levels and fixed rates on price lists (SEL-9, decision A89).

* ``price_levels`` -- Retail, Wholesale, Dealer -- and ``product_price_levels``,
  one product's price at one level.
* ``customers.price_level_id`` and ``customer_groups.price_level_id``.
* ``price_list_items.rate``: a fixed price on a list, beside its discount.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0260
Revises: 20261003_0259
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0260"
down_revision: str | Sequence[str] | None = "20261003_0259"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries, firm included."""
    return [
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
    ]


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the column names a table has."""
    return {column["name"] for column in inspector.get_columns(table)}


def _levels(inspector: sa.Inspector) -> None:
    """Create the two level tables where missing."""
    if not inspector.has_table("price_levels"):
        op.create_table(
            "price_levels",
            *_base(),
            sa.Column("code", sa.String(30), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column(
                "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="PK_price_levels"),
        )
        op.create_index("IX_price_levels_firm_id", "price_levels", ["firm_id"])
        op.create_index(
            "UQ_price_levels_firm_code_active",
            "price_levels",
            ["firm_id", "code"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
    if not inspector.has_table("product_price_levels") and inspector.has_table(
        "products"
    ):
        op.create_table(
            "product_price_levels",
            *_base(),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("price_level_id", UUIDType(), nullable=False),
            sa.Column("rate", sa.Numeric(18, 4), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_product_price_levels"),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_product_price_levels_product_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["price_level_id"],
                ["price_levels.id"],
                name="FK_product_price_levels_price_level_id",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "IX_product_price_levels_firm_id", "product_price_levels", ["firm_id"]
        )
        op.create_index(
            "IX_product_price_levels_product",
            "product_price_levels",
            ["firm_id", "product_id"],
        )
        op.create_index(
            "UQ_product_price_levels_level_product_active",
            "product_price_levels",
            ["price_level_id", "product_id"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def _level_column(inspector: sa.Inspector, table: str) -> None:
    """Give a table its price level, keyed to the levels."""
    if not inspector.has_table(table) or "price_level_id" in _columns(inspector, table):
        return
    op.add_column(table, sa.Column("price_level_id", UUIDType()))
    op.create_foreign_key(
        f"FK_{table}_price_level_id",
        table,
        "price_levels",
        ["price_level_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    """Add the levels, the customer and group levels, and list rates."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        return
    _levels(inspector)
    _level_column(inspector, "customers")
    _level_column(inspector, "customer_groups")
    if inspector.has_table("price_list_items") and "rate" not in _columns(
        inspector, "price_list_items"
    ):
        op.add_column("price_list_items", sa.Column("rate", sa.Numeric(18, 4)))


def downgrade() -> None:
    """Drop the list rates, the level columns and the level tables."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("price_list_items") and "rate" in _columns(
        inspector, "price_list_items"
    ):
        op.drop_column("price_list_items", "rate")
    for table in ("customer_groups", "customers"):
        if inspector.has_table(table) and "price_level_id" in _columns(
            inspector, table
        ):
            op.drop_constraint(f"FK_{table}_price_level_id", table, type_="foreignkey")
            op.drop_column(table, "price_level_id")
    for table in ("product_price_levels", "price_levels"):
        if inspector.has_table(table):
            op.drop_table(table)
