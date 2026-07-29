"""Ensure Phase 5 identity extensions exist on every migration path.

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns() -> list[sa.Column[Any]]:
    """Return all BaseEntity columns required by a new Phase 5 association."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUIDType()),
        sa.Column("updated_by", UUIDType()),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    """Reconcile Phase 5 identity fields and user-firm table if absent.

    Revision 0003 creates these objects for a fresh database. The guarded
    operations additionally protect environments whose earlier Phase 5 revision
    was applied from an incomplete artifact.
    """
    if op.get_context().as_sql:
        raise RuntimeError(
            "Revision 20260728_0004 requires online execution because it "
            "inspects the live schema before applying repairs."
        )
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    _add_column_if_missing(
        inspector,
        table_names,
        "users",
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    _add_column_if_missing(
        inspector,
        table_names,
        "roles",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    if "user_firms" not in table_names:
        _create_user_firms()


def downgrade() -> None:
    """Retain reconciled objects because their prior state cannot be inferred."""


def _add_column_if_missing(
    inspector: sa.Inspector,
    table_names: set[str],
    table_name: str,
    column: sa.Column[Any],
) -> None:
    """Add a Phase 5 field only when its preceding revision did not create it."""
    if table_name not in table_names:
        raise RuntimeError(f"Required identity table {table_name!r} does not exist.")
    column_names = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in column_names:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(column)


def _create_user_firms() -> None:
    """Create the complete BaseEntity-backed user-firm association table."""
    op.create_table(
        "user_firms",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="FK_user_firms_users"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"], name="FK_user_firms_firms"),
        sa.PrimaryKeyConstraint("id", name="PK_user_firms"),
        sa.UniqueConstraint("user_id", "firm_id", name="UQ_user_firms_user_id"),
    )
    op.create_index("IX_user_firms_user_id", "user_firms", ["user_id"])
    op.create_index("IX_user_firms_firm_id", "user_firms", ["firm_id"])
