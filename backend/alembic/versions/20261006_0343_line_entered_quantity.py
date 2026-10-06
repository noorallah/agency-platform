"""A line typed in another unit than the line it continues keeps what was typed.

``entered_quantity`` on ``sales_invoice_lines``, ``purchase_invoice_lines``,
``purchase_return_lines`` and ``sales_return_lines`` -- the quantity as typed,
in the line's own ``invoice_uom_id`` / ``return_uom_id``, where that is
another unit than the note, receipt or bill line it continues. The quantity
beside it stays in the source line's unit, which is what every cap counts.

Seven pieces of a line delivered by the box of twelve were stored only as
0.5833 of a box: priced, 699.96 where seven pieces are 700.00; moved, a
quantity a unit counted in whole numbers refuses (D-PRC-37, D-PRC-38). The
line is now priced, moved and printed from what was typed.

Null on every existing line: nothing recorded what was typed, and a line
typed in its source line's own unit needs none. A draft saved again records
it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0343
Revises: 20261006_0342
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0343"
down_revision: str | Sequence[str] | None = "20261006_0342"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "sales_invoice_lines",
    "purchase_invoice_lines",
    "purchase_return_lines",
    "sales_return_lines",
)
_COLUMN = "entered_quantity"


def upgrade() -> None:
    """Add the column where the store keeps each document."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN not in columns:
            op.add_column(table, sa.Column(_COLUMN, sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN in columns:
            op.drop_column(table, _COLUMN)
