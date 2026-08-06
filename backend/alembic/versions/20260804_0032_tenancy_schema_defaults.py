"""Align firm tenancy defaults to the two-schema shared model.

Revision ID: 20260804_0032
Revises: 20260804_0031
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0032"
down_revision: str | None = "20260804_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Use firm_shared as the default schema for new SHARED firms."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.alter_column(
            "schema_name",
            server_default=sa.text("'firm_shared'"),
            existing_type=sa.String(length=128),
        )


def downgrade() -> None:
    """Restore the previous shared-schema default."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.alter_column(
            "schema_name",
            server_default=sa.text("'public'"),
            existing_type=sa.String(length=128),
        )
