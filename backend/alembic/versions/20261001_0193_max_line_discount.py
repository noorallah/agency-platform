"""A cap on the combined offer discount per line (backlog 59 item 3).

``sales_workflow_settings.max_line_discount_percent``: in Combine mode, the
most the matching offers together may take off one line, as a percentage of
its gross. Nullable, and null is no cap -- so no firm's pricing changes.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261001_0193
Revises: 20261001_0185
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0193"
down_revision: str | Sequence[str] | None = "20261001_0185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_workflow_settings"
_COLUMN = "max_line_discount_percent"


def upgrade() -> None:
    """Add the column where the table exists and it does not."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
