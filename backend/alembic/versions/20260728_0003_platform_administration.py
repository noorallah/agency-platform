"""Add platform administration, firm, and audit persistence.

Revision ID: 20260728_0003
Revises: 20260728_0002
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260728_0003"
down_revision: str | None = "20260728_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns() -> list[sa.Column[Any]]:
    """Return common BaseEntity columns for new tables."""
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
    """Create firm, user-firm, and audit tables and identity extensions."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True)))
    with op.batch_alter_table("roles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_system",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
    op.create_table(
        "firms",
        *_entity_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("gst_number", sa.String(32)),
        sa.Column("pan_number", sa.String(32)),
        sa.Column("address_line1", sa.String(250)),
        sa.Column("address_line2", sa.String(250)),
        sa.Column("city", sa.String(100)),
        sa.Column("postal_code", sa.String(24)),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("state", sa.String(100)),
        sa.Column("contact_name", sa.String(200)),
        sa.Column("contact_email", sa.String(320)),
        sa.Column("contact_phone", sa.String(20)),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("financial_year_start", sa.Date(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("notes", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="PK_firms"),
        sa.UniqueConstraint("code", name="UQ_firms_code"),
        sa.UniqueConstraint("gst_number", name="UQ_firms_gst_number"),
        sa.UniqueConstraint("pan_number", name="UQ_firms_pan_number"),
    )
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
    op.create_table(
        "audit_logs",
        *_entity_columns(),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", UUIDType(), nullable=False),
        sa.Column("actor_id", UUIDType()),
        sa.Column("before_data", sa.JSON()),
        sa.Column("after_data", sa.JSON()),
        sa.PrimaryKeyConstraint("id", name="PK_audit_logs"),
    )
    op.create_index("IX_user_firms_user_id", "user_firms", ["user_id"])
    op.create_index("IX_user_firms_firm_id", "user_firms", ["firm_id"])
    op.create_index(
        "IX_audit_logs_entity_type_entity_id",
        "audit_logs",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    """Remove platform administration persistence changes."""
    op.drop_index("IX_audit_logs_entity_type_entity_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("IX_user_firms_firm_id", table_name="user_firms")
    op.drop_index("IX_user_firms_user_id", table_name="user_firms")
    op.drop_table("user_firms")
    op.drop_table("firms")
    with op.batch_alter_table("roles") as batch_op:
        batch_op.drop_column("is_system")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("expires_at")
