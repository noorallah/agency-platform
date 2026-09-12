"""Record where a quotation or sales order line's discount rate came from.

A line stores the rate that was applied and nothing about whether somebody
typed it or the server resolved it from a promotion, a price list or the
customer's standing rate. The two look identical afterwards, and the desktop's
revise/edit paths -- written so that a revision keeps an agreed rate when the
customer master moves -- re-sent every stored rate as typed. A typed rate
outranks every arrangement, so a line moved from 12 to 18 units on
2026-09-13 kept the 2% of the ladder's first step instead of taking the 6.75%
of its third (manual plan item 9.2).

``discount_source`` is nullable and additive: ``percent``/``amount`` when the
rate was typed, ``promotion``/``price_list``/``customer``/``customer_group``
when it was resolved, ``none`` when nothing applied. Existing lines stay
NULL, which an editor treats as "re-resolve and say what it was". Both
tables are firm-owned, so run this through ``scripts/migrate_all_stores.py``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0134"
down_revision: str | Sequence[str] | None = "20260912_0133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("sales_quotation_lines", "sales_order_lines")
_COLUMN = "discount_source"


def upgrade() -> None:
    """Add the nullable column to both line tables where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            # The platform schema holds no firm-owned tables once pruned.
            continue
        if any(column["name"] == _COLUMN for column in inspector.get_columns(table)):
            continue
        op.add_column(table, sa.Column(_COLUMN, sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Drop the column from both line tables where it exists."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if inspector.has_table(table) and any(
            column["name"] == _COLUMN for column in inspector.get_columns(table)
        ):
            op.drop_column(table, _COLUMN)
