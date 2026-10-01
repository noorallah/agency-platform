"""The ship-to address chosen per document (backlog 67 row 3).

``shipping_address_id`` on ``sales_orders``, ``delivery_notes`` and
``sales_invoices``: one of the customer's own addresses, picked on the order
(default shipping preselected) and inherited down the chain. A bare id with no
foreign key, validated by the service when it is set, like every other
reference between sales documents.

Existing documents are backfilled with their customer's default shipping
address -- the address they have always printed -- only where the column is
still NULL, so a replay never overwrites one chosen since.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261001_0195"
down_revision: str | Sequence[str] | None = "20261001_0193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("sales_orders", "delivery_notes", "sales_invoices")


def upgrade() -> None:
    """Add the column where the documents live, and fill it from the default."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if "shipping_address_id" not in columns:
            op.add_column(
                table, sa.Column("shipping_address_id", UUIDType(), nullable=True)
            )
        if inspector.has_table("customer_addresses"):
            # The default shipping address, else the oldest SHIPPING one --
            # what ``default_shipping_address_id`` answers today.
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table} AS doc
                    SET shipping_address_id = (
                        SELECT address.id
                        FROM customer_addresses AS address
                        WHERE address.customer_id = doc.customer_id
                          AND address.is_deleted = false
                          AND (
                              address.is_default_shipping = true
                              OR address.address_type = 'SHIPPING'
                          )
                        ORDER BY
                          CASE WHEN address.is_default_shipping THEN 0 ELSE 1 END,
                          address.created_at,
                          address.id
                        LIMIT 1
                    )
                    WHERE doc.shipping_address_id IS NULL
                    """
                )
            )


def downgrade() -> None:
    """Drop it."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if "shipping_address_id" in columns:
            op.drop_column(table, "shipping_address_id")
