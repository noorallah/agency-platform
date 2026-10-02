"""Customer returns held in quarantine until checked (STK-13, decision A62).

`batch_sale_settings.hold_returns_for_check`: when a firm turns it on, the
sellable part of a completed sales return lands in quarantine instead of on
the shelf, and is released through the ordinary quarantine release. Off for
every firm, so nothing changes until a firm chooses it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0244
Revises: 20261003_0243
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0244"
down_revision: str | Sequence[str] | None = "20261003_0243"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "batch_sale_settings"
_COLUMN = "hold_returns_for_check"


def upgrade() -> None:
    """Add the switch, off, where the settings table exists and lacks it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    """Drop the switch."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
