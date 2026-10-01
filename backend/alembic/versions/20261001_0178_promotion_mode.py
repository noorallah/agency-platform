"""How matching promotions meet: combine, or the best offer only (backlog 59).

``sales_workflow_settings.promotion_mode``: COMBINE (every firm today, so the
default changes nobody's pricing) or BEST_OFFER. A firm with no settings row
combines, as before.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261001_0178
Revises: 20261001_0177
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0178"
down_revision: str | Sequence[str] | None = "20261001_0177"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_workflow_settings"
_COLUMN = "promotion_mode"


def upgrade() -> None:
    """Add the column where the table exists and it does not."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(20), nullable=False, server_default="COMBINE"),
    )


def downgrade() -> None:
    """Drop the column."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
