"""Add optimistic-concurrency versions to shared entity tables.

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260728_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_TABLES = (
    "users",
    "platform_admins",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "password_history",
    "refresh_tokens",
    "login_history",
)


def upgrade() -> None:
    """Add a non-null version to all current BaseEntity tables."""
    for table_name in _ENTITY_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )


def downgrade() -> None:
    """Remove the shared optimistic-concurrency version columns."""
    for table_name in reversed(_ENTITY_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("version")
