"""A customer that is also a supplier (ACC-11, decision A86).

``customers.linked_vendor_id`` names the supplier record of the same business;
``UQ_customers_linked_vendor_active`` keeps a supplier linked to one live
customer at most.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0258
Revises: 20261003_0257
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0258"
down_revision: str | Sequence[str] | None = "20261003_0257"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the link, its key and its index where missing."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers") or not inspector.has_table("vendors"):
        return
    have = {column["name"] for column in inspector.get_columns("customers")}
    if "linked_vendor_id" not in have:
        op.add_column("customers", sa.Column("linked_vendor_id", UUIDType()))
        op.create_foreign_key(
            "FK_customers_linked_vendor_id",
            "customers",
            "vendors",
            ["linked_vendor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    indexes = {index["name"] for index in inspector.get_indexes("customers")}
    if "UQ_customers_linked_vendor_active" not in indexes:
        op.create_index(
            "UQ_customers_linked_vendor_active",
            "customers",
            ["linked_vendor_id"],
            unique=True,
            postgresql_where=sa.text(
                "linked_vendor_id IS NOT NULL AND is_deleted = false"
            ),
        )


def downgrade() -> None:
    """Drop the index, the key and the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        return
    indexes = {index["name"] for index in inspector.get_indexes("customers")}
    if "UQ_customers_linked_vendor_active" in indexes:
        op.drop_index("UQ_customers_linked_vendor_active", table_name="customers")
    have = {column["name"] for column in inspector.get_columns("customers")}
    if "linked_vendor_id" in have:
        op.drop_constraint(
            "FK_customers_linked_vendor_id", "customers", type_="foreignkey"
        )
        op.drop_column("customers", "linked_vendor_id")
