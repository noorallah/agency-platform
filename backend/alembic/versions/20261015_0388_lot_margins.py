"""Retail and wholesale margins, and the class a price level stands for (L3).

Row L3 of ``docs/CUSTOMER_BUILD_TASKS.md``, step 1 of
``docs/design/LOT_MARGINS_DESIGN.md``:

* ``retail_margin_percent`` and ``wholesale_margin_percent`` on
  ``firm_goods_types`` (the pair a new product of the type starts with),
  ``products`` (the product's own), ``goods_receipt_lines`` (the pair a
  receipt line used) and ``batches`` (the pair a lot was priced at). A
  mark-up on the purchase price, Numeric(9,4), null for no margin set.
* ``price_levels.trade_class``: ``RETAILER`` or ``STOCKIST`` on the two
  levels that stand for a customer's kind, null on every other level.

Nothing is backfilled: a product with no pair works out no price.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and the column does not.

Revision ID: 20261015_0388
Revises: 20261014_0387
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261015_0388"
down_revision: str | Sequence[str] | None = "20261014_0387"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MARGIN_TABLES = ("firm_goods_types", "products", "goods_receipt_lines", "batches")
_MARGINS = ("retail_margin_percent", "wholesale_margin_percent")


def _columns() -> dict[str, list[tuple[str, sa.types.TypeEngine[object]]]]:
    """Return each table and the columns this revision gives it."""
    columns: dict[str, list[tuple[str, sa.types.TypeEngine[object]]]] = {
        table: [(name, sa.Numeric(9, 4)) for name in _MARGINS]
        for table in _MARGIN_TABLES
    }
    columns["price_levels"] = [("trade_class", sa.String(length=20))]
    return columns


def upgrade() -> None:
    """Add the margin pairs and the level's trade class where missing."""
    inspector = sa.inspect(op.get_bind())
    for table, wanted in _columns().items():
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, kind in wanted:
            if name not in present:
                op.add_column(table, sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    """Drop the margin pairs and the level's trade class where present."""
    inspector = sa.inspect(op.get_bind())
    for table, wanted in _columns().items():
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, _ in wanted:
            if name in present:
                op.drop_column(table, name)
