"""Enhance firm registry for pluggable multi-tenant deployment modes.

Revision ID: 20260804_0031
Revises: 20260803_0030
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0031"
down_revision: str | None = "20260803_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add deployment and connection metadata to firm registry."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.add_column(
            sa.Column(
                "deployment_mode",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'SHARED'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "database_name",
                sa.String(length=128),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "schema_name",
                sa.String(length=128),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "database_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'postgresql'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'ACTIVE'"),
            )
        )
        batch_op.add_column(sa.Column("created_date", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("updated_date", sa.DateTime(timezone=True)))
    op.execute(
        sa.text("UPDATE firms SET created_date = created_at WHERE created_date IS NULL")
    )
    op.execute(
        sa.text("UPDATE firms SET updated_date = updated_at WHERE updated_date IS NULL")
    )


def downgrade() -> None:
    """Remove multi-tenant deployment metadata from firm registry."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.drop_column("updated_date")
        batch_op.drop_column("created_date")
        batch_op.drop_column("status")
        batch_op.drop_column("database_type")
        batch_op.drop_column("schema_name")
        batch_op.drop_column("database_name")
        batch_op.drop_column("deployment_mode")
