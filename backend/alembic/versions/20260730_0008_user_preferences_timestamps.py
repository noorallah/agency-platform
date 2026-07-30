"""Set database defaults for user preference audit timestamps.

Revision ID: 20260730_0008
Revises: 20260729_0007
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260730_0008"
down_revision: str | None = "20260729_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply timestamp defaults required by the shared BaseEntity contract."""
    for column_name in ("created_at", "updated_at"):
        op.alter_column(
            "user_preferences",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def downgrade() -> None:
    """Remove the timestamp defaults introduced by this repair."""
    for column_name in ("created_at", "updated_at"):
        op.alter_column(
            "user_preferences",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
