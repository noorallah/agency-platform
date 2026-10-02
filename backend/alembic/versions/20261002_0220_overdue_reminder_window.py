"""Overdue reminders stop past a window, 90 days by default (decision A12).

``messaging_settings.overdue_stop_after_days``: a bill more than this many
days past its due date gets no automatic overdue reminder, so switching
reminders on does not message a customer about every bill unpaid since the
firm began.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0220
Revises: 20261002_0219
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0220"
down_revision: str | Sequence[str] | None = "20261002_0219"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "messaging_settings"
_COLUMN = "overdue_stop_after_days"


def upgrade() -> None:
    """Add the window where the settings table lives."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Integer(), server_default="90", nullable=False),
    )


def downgrade() -> None:
    """Drop the window; every overdue bill is reminded again."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE) and _COLUMN in {
        column["name"] for column in inspector.get_columns(_TABLE)
    }:
        op.drop_column(_TABLE, _COLUMN)
