"""Seed the initial system RBAC model and protect system permissions.

Revision ID: 20260729_0006
Revises: 20260728_0005
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op
from app.identity.system_seed import seed_system_rbac

revision: str = "20260729_0006"
down_revision: str | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add permission classification and create the initial system RBAC records."""
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_system",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )

    session = Session(bind=op.get_bind())
    try:
        seed_system_rbac(session)
        session.flush()
    finally:
        session.close()


def downgrade() -> None:
    """Remove the permission classification while retaining role assignment data."""
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.drop_column("is_system")
