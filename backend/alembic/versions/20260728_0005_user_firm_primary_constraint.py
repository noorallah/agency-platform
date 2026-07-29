"""Enforce one active primary firm per user on PostgreSQL.

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIMARY_FIRM_INDEX = "UQ_user_firms_active_primary"


def upgrade() -> None:
    """Create the PostgreSQL partial unique index when it is not already present."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    index_names = {
        index["name"] for index in sa.inspect(bind).get_indexes("user_firms")
    }
    if _PRIMARY_FIRM_INDEX not in index_names:
        op.create_index(
            _PRIMARY_FIRM_INDEX,
            "user_firms",
            ["user_id"],
            unique=True,
            postgresql_where=sa.text("is_active AND is_primary AND NOT is_deleted"),
        )


def downgrade() -> None:
    """Remove the PostgreSQL partial unique index if the dialect supports it."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    index_names = {
        index["name"] for index in sa.inspect(bind).get_indexes("user_firms")
    }
    if _PRIMARY_FIRM_INDEX in index_names:
        op.drop_index(_PRIMARY_FIRM_INDEX, table_name="user_firms")
