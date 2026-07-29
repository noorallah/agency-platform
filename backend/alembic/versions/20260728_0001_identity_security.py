"""Create identity-domain platform tables.

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260728_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns() -> list[sa.Column[Any]]:
    """Return the common persistence columns defined by BaseEntity."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
    ]


def upgrade() -> None:
    """Create the identity, RBAC, token, and login-history tables."""
    op.create_table(
        "users",
        *_entity_columns(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "force_password_change",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_users"),
        sa.UniqueConstraint("email", name="UQ_users_email"),
    )
    op.create_table(
        "roles",
        *_entity_columns(),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_roles"),
        sa.UniqueConstraint("code", name="UQ_roles_code"),
    )
    op.create_table(
        "permissions",
        *_entity_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_permissions"),
        sa.UniqueConstraint("code", name="UQ_permissions_code"),
    )
    op.create_table(
        "platform_admins",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="FK_platform_admins_users"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_platform_admins"),
        sa.UniqueConstraint("user_id", name="UQ_platform_admins_user_id"),
    )
    op.create_table(
        "user_roles",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("role_id", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="FK_user_roles_roles"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="FK_user_roles_users"),
        sa.PrimaryKeyConstraint("id", name="PK_user_roles"),
        sa.UniqueConstraint("user_id", "role_id", name="UQ_user_roles_user_id"),
    )
    op.create_table(
        "role_permissions",
        *_entity_columns(),
        sa.Column("role_id", UUIDType(), nullable=False),
        sa.Column("permission_id", UUIDType(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="FK_role_permissions_permissions",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="FK_role_permissions_roles"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_role_permissions"),
        sa.UniqueConstraint(
            "role_id", "permission_id", name="UQ_role_permissions_role_id"
        ),
    )
    op.create_table(
        "password_history",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="FK_password_history_users"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_password_history"),
    )
    op.create_table(
        "refresh_tokens",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", UUIDType(), nullable=True),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name="FK_refresh_tokens_refresh_tokens",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="FK_refresh_tokens_users"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="UQ_refresh_tokens_token_hash"),
    )
    op.create_table(
        "login_history",
        *_entity_columns(),
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("attempted_email", sa.String(length=320), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="FK_login_history_users"
        ),
        sa.PrimaryKeyConstraint("id", name="PK_login_history"),
    )
    op.create_index("IX_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("IX_user_roles_role_id", "user_roles", ["role_id"])
    op.create_index("IX_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index(
        "IX_role_permissions_permission_id", "role_permissions", ["permission_id"]
    )
    op.create_index(
        "IX_password_history_user_id_created_at",
        "password_history",
        ["user_id", "created_at"],
    )
    op.create_index(
        "IX_refresh_tokens_user_id_expires_at",
        "refresh_tokens",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "IX_login_history_user_id_created_at",
        "login_history",
        ["user_id", "created_at"],
    )
    op.create_index(
        "IX_login_history_attempted_email", "login_history", ["attempted_email"]
    )

    users = sa.table(
        "users",
        sa.column("id", UUIDType()),
        sa.column("email", sa.String()),
        sa.column("full_name", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("force_password_change", sa.Boolean()),
        sa.column("failed_login_attempts", sa.Integer()),
    )
    platform_admins = sa.table(
        "platform_admins",
        sa.column("id", UUIDType()),
        sa.column("user_id", UUIDType()),
    )
    admin_user_id = UUID("00000000-0000-0000-0000-000000000001")
    admin_id = UUID("00000000-0000-0000-0000-000000000002")
    op.bulk_insert(
        users,
        [
            {
                "id": admin_user_id,
                "email": "platform-admin@agency.local",
                "full_name": "Platform Administrator",
                "password_hash": "*",
                "is_active": True,
                "force_password_change": True,
                "failed_login_attempts": 0,
            }
        ],
    )
    op.bulk_insert(platform_admins, [{"id": admin_id, "user_id": admin_user_id}])


def downgrade() -> None:
    """Drop identity tables in foreign-key dependency order."""
    op.drop_index("IX_login_history_attempted_email", table_name="login_history")
    op.drop_index("IX_login_history_user_id_created_at", table_name="login_history")
    op.drop_table("login_history")
    op.drop_index("IX_refresh_tokens_user_id_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        "IX_password_history_user_id_created_at", table_name="password_history"
    )
    op.drop_table("password_history")
    op.drop_index("IX_role_permissions_permission_id", table_name="role_permissions")
    op.drop_index("IX_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("IX_user_roles_role_id", table_name="user_roles")
    op.drop_index("IX_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("platform_admins")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
