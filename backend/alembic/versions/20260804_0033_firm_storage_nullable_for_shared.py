"""Allow shared firms to omit dedicated storage fields.

Revision ID: 20260804_0033
Revises: 20260804_0032
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0033"
down_revision: str | None = "20260804_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make schema_name/database_name optional for SHARED deployment mode."""
    op.execute(
        sa.text(
            "UPDATE firms SET schema_name = NULL, database_name = NULL "
            "WHERE deployment_mode = 'SHARED'"
        )
    )
    with op.batch_alter_table("firms") as batch_op:
        batch_op.alter_column(
            "schema_name",
            nullable=True,
            server_default=None,
            existing_type=sa.String(length=128),
        )
        batch_op.alter_column(
            "database_name",
            nullable=True,
            server_default=None,
            existing_type=sa.String(length=128),
        )


def downgrade() -> None:
    """Restore non-null defaults on dedicated storage fields."""
    op.execute(
        sa.text(
            "UPDATE firms SET schema_name = 'firm_shared', "
            "database_name = 'erp_shared' "
            "WHERE schema_name IS NULL OR database_name IS NULL"
        )
    )
    with op.batch_alter_table("firms") as batch_op:
        batch_op.alter_column(
            "schema_name",
            nullable=False,
            server_default=sa.text("'firm_shared'"),
            existing_type=sa.String(length=128),
        )
        batch_op.alter_column(
            "database_name",
            nullable=False,
            server_default=sa.text("'erp_shared'"),
            existing_type=sa.String(length=128),
        )
