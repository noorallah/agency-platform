"""A quotation keeps the coupon the customer presented (D-SELL-43).

* ``sales_quotations.coupon_code``, so a quote is priced with the coupon's
  offer and the order it becomes carries the same code.

Nothing is backfilled: no quotation could hold a coupon before. Idempotent;
run per store (``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0170"
down_revision: str | Sequence[str] | None = "20260930_0173"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """Return whether ``table`` exists here and already has ``column``."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return True  # not a store that holds quotations; nothing to add
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    """Add the coupon column where it is missing."""
    if not _has_column("sales_quotations", "coupon_code"):
        op.add_column(
            "sales_quotations", sa.Column("coupon_code", sa.String(40), nullable=True)
        )


def downgrade() -> None:
    """Drop the coupon column."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("sales_quotations") and any(
        item["name"] == "coupon_code"
        for item in inspector.get_columns("sales_quotations")
    ):
        op.drop_column("sales_quotations", "coupon_code")
