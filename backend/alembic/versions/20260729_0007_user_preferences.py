"""Add versioned preferences owned by individual users.

Revision ID: 20260729_0007
Revises: 20260729_0006
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260729_0007"
down_revision: str | None = "20260729_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the per-user preference document table."""
    op.create_table(
        "user_preferences",
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column(
            "preferences_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "preferred_theme",
            sa.String(length=32),
            nullable=False,
            server_default="light",
        ),
        sa.Column(
            "language", sa.String(length=16), nullable=False, server_default="en"
        ),
        sa.Column(
            "date_format",
            sa.String(length=32),
            nullable=False,
            server_default="yyyy-MM-dd",
        ),
        sa.Column(
            "time_format", sa.String(length=16), nullable=False, server_default="24h"
        ),
        sa.Column(
            "number_format",
            sa.String(length=32),
            nullable=False,
            server_default="1,234.56",
        ),
        sa.Column(
            "currency_format",
            sa.String(length=32),
            nullable=False,
            server_default="symbol",
        ),
        sa.Column("default_firm_id", UUIDType(), nullable=True),
        sa.Column(
            "default_landing_page",
            sa.String(length=100),
            nullable=False,
            server_default="dashboard",
        ),
        sa.Column("rows_per_page", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("notification_preferences", sa.JSON(), nullable=False),
        sa.Column("dashboard_layout", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["default_firm_id"], ["firms.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "IX_user_preferences_user_id", "user_preferences", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Drop versioned user preferences."""
    op.drop_index("IX_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
