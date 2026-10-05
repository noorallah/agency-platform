"""Free goods can go back on a purchase return (D-BUY-56).

``purchase_return_lines.free_quantity`` -- the free goods a line sends back
beside its charged units. A return was capped at the receipt line's accepted
quantity, so goods that came in free could never be returned, and a line of
free goods alone could not be returned at all; the only way to take them off
the books was a write-off.

``current_return_quantity`` stays the charged units, which every price, tax,
billing and credit figure is worked on; the free ones are credited nothing
and leave stock with them. Zero by default, which is what every line written
before this revision sent back.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261005_0329
Revises: 20261005_0328
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0329"
down_revision: str | Sequence[str] | None = "20261005_0328"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_return_lines"
_COLUMN = "free_quantity"


def upgrade() -> None:
    """Add the column where the store keeps purchase returns."""
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
