"""Payment terms on the sales order (backlog 67 row 4).

``sales_orders.payment_terms`` (the words) and ``payment_terms_days`` (the
days of credit). A new order takes the customer's days unless it says
otherwise, and the invoice inherits them rather than re-reading the customer.

Existing orders are backfilled with their customer's days -- what every bill
raised from them has been using -- only where the column is still NULL, so a
replay never overwrites terms agreed since.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0196"
down_revision: str | Sequence[str] | None = "20261001_0195"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the columns where orders live, and fill the days from the customer."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_orders"):
        return
    columns = {item["name"] for item in inspector.get_columns("sales_orders")}
    if "payment_terms" not in columns:
        op.add_column(
            "sales_orders", sa.Column("payment_terms", sa.String(200), nullable=True)
        )
    if "payment_terms_days" not in columns:
        op.add_column(
            "sales_orders", sa.Column("payment_terms_days", sa.Integer, nullable=True)
        )
    if inspector.has_table("customers"):
        op.execute(
            sa.text(
                """
                UPDATE sales_orders
                SET payment_terms_days = (
                    SELECT customers.payment_terms_days
                    FROM customers
                    WHERE customers.id = sales_orders.customer_id
                )
                WHERE payment_terms_days IS NULL
                """
            )
        )


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("sales_orders"):
        return
    columns = {item["name"] for item in inspector.get_columns("sales_orders")}
    for name in ("payment_terms_days", "payment_terms"):
        if name in columns:
            op.drop_column("sales_orders", name)
