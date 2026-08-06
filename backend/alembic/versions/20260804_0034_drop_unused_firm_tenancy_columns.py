"""Drop unused firm tenancy columns.

Revision ID: 20260804_0034
Revises: 20260804_0033
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0034"
down_revision: str | None = "20260804_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove legacy connection-level columns from firm registry."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("firms")}
    drop_candidates = [
        name
        for name in (
            "connection_profile",
            "database_host",
            "database_port",
            "connection_pool_name",
        )
        if name in existing
    ]
    if not drop_candidates:
        return
    with op.batch_alter_table("firms") as batch_op:
        for column_name in drop_candidates:
            batch_op.drop_column(column_name)


def downgrade() -> None:
    """Recreate legacy connection-level columns."""
    with op.batch_alter_table("firms") as batch_op:
        batch_op.add_column(sa.Column("connection_profile", sa.String(length=64)))
        batch_op.add_column(
            sa.Column(
                "database_host",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("'localhost'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "database_port",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5432"),
            )
        )
        batch_op.add_column(sa.Column("connection_pool_name", sa.String(length=128)))
