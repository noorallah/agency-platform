"""Carry a purchase order's whole-order discount on its lines (D-BUY-19).

``purchase_orders.header_discount_amount`` was subtracted from the grand total
**after** tax, so it lowered no taxable value -- the input tax was overstated
by the tax on the discount -- and nothing downstream inherited it, so the
goods receipt valued the stock and the bill charged the supplier's full price.

The discount is now split across the order's lines before tax, the way a sales
document's bill discount is, and each receipt, bill and return line inherits
its share pro-rated by the quantity it covers. This adds the column that holds
that share on the four line tables.

Zero for every existing row, which is what they were computed with: an order
saved before this keeps the totals it was approved at until somebody edits
it, and its downstream documents inherit nothing, exactly as before.

Firm-owned, so platform gets none of it. Idempotent: firm stores are partly
built by ``create_all``, so each column is checked before it is added.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0165"
down_revision: str | Sequence[str] | None = "20260928_0164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "purchase_order_lines",
    "goods_receipt_lines",
    "purchase_invoice_lines",
    "purchase_return_lines",
)
_COLUMN = "bill_discount_amount"


def upgrade() -> None:
    """Add the share column to each purchase line table that exists here."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN not in columns:
            op.add_column(
                table,
                sa.Column(
                    _COLUMN,
                    sa.Numeric(18, 4),
                    server_default=sa.text("0"),
                    nullable=False,
                ),
            )


def downgrade() -> None:
    """Drop the share column; the discount goes back to the header alone."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN in columns:
            op.drop_column(table, _COLUMN)
