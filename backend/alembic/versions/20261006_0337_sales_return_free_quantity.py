"""Free goods can come back on a sales return (D-PRC-8).

``sales_return_lines.free_quantity`` -- the free goods a line brings back
beside its charged units. A return was capped at what the source line
charged for, so the thirteenth unit of "buy 12 get 1" could never come back:
the customer returned everything charged and the free unit had nowhere to go
but a stock adjustment. The selling twin of ``purchase_return_lines
.free_quantity`` (D-BUY-56, ``20261005_0329``).

``current_return_quantity`` stays the charged units, which every price, tax,
billing and credit figure is worked on; the free ones are credited nothing
and arrive in stock with them. Zero by default, which is what every line
written before this revision brought back.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261006_0337
Revises: 20261006_0336
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0337"
down_revision: str | Sequence[str] | None = "20261006_0336"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_return_lines"
_COLUMN = "free_quantity"


def upgrade() -> None:
    """Add the column where the store keeps sales returns."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN, sa.Numeric(18, 4), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
