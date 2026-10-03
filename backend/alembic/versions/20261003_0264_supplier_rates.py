"""Supplier rates: a standing discount and supplier price lists (BUY-3, A97).

* ``vendors.standing_discount_percent`` (0).
* ``price_lists.vendor_id``: a list naming a supplier prices purchases only.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0264
Revises: 20261003_0263
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0264"
down_revision: str | Sequence[str] | None = "20261003_0263"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the column names a table has."""
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the supplier's discount and the supplier scope on price lists."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("vendors") and "standing_discount_percent" not in (
        _columns(inspector, "vendors")
    ):
        op.add_column(
            "vendors",
            sa.Column(
                "standing_discount_percent",
                sa.Numeric(9, 4),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )
    if (
        inspector.has_table("price_lists")
        and inspector.has_table("vendors")
        and "vendor_id" not in _columns(inspector, "price_lists")
    ):
        op.add_column("price_lists", sa.Column("vendor_id", UUIDType()))
        op.create_foreign_key(
            "FK_price_lists_vendor_id",
            "price_lists",
            "vendors",
            ["vendor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "IX_price_lists_vendor", "price_lists", ["firm_id", "vendor_id"]
        )


def downgrade() -> None:
    """Drop the two columns."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("price_lists") and "vendor_id" in _columns(
        inspector, "price_lists"
    ):
        op.drop_index("IX_price_lists_vendor", table_name="price_lists")
        op.drop_constraint(
            "FK_price_lists_vendor_id", "price_lists", type_="foreignkey"
        )
        op.drop_column("price_lists", "vendor_id")
    if inspector.has_table("vendors") and "standing_discount_percent" in _columns(
        inspector, "vendors"
    ):
        op.drop_column("vendors", "standing_discount_percent")
