"""An invoice line keeps the HSN or SAC code it was billed under (D-CMP-22).

* ``sales_invoice_lines.hsn_sac``, stamped from the product when a line is
  written, so correcting a product's code no longer rewrites the HSN summary
  of a month already filed or reprints an old bill with a new code.

Backfilled from each product's code as it stands today: that is the code
every existing line has been filed and printed under until now, so it is the
best record there is. Only lines still without one are touched, so a replay
cannot overwrite a stamped code. Idempotent; run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0171"
down_revision: str | Sequence[str] | None = "20260930_0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str] | None:
    """Return a table's column names here, or None when it is not here."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return None
    return {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the column where missing and fill it for lines that have none."""
    columns = _columns("sales_invoice_lines")
    if columns is None:
        return  # not a store that holds invoices
    if "hsn_sac" not in columns:
        op.add_column(
            "sales_invoice_lines", sa.Column("hsn_sac", sa.String(20), nullable=True)
        )
    if _columns("products") is None:
        return
    op.execute(
        sa.text(
            "UPDATE sales_invoice_lines SET hsn_sac = ("
            " SELECT NULLIF(TRIM(products.hsn_sac), '') FROM products"
            " WHERE products.id = sales_invoice_lines.product_id"
            ") WHERE hsn_sac IS NULL"
        )
    )


def downgrade() -> None:
    """Drop the column."""
    columns = _columns("sales_invoice_lines")
    if columns is not None and "hsn_sac" in columns:
        op.drop_column("sales_invoice_lines", "hsn_sac")
