"""Harden authorization boundaries, lifecycle audit, and audit immutability.

Revision ID: 20260801_0010
Revises: 20260731_0009
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0010"
down_revision: str | None = "20260731_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIFECYCLE_TABLES = (
    "users",
    "roles",
    "permissions",
    "platform_admins",
    "user_roles",
    "role_permissions",
    "password_history",
    "refresh_tokens",
    "login_history",
    "firms",
    "user_firms",
    "user_preferences",
    "customers",
    "customer_addresses",
    "customer_contacts",
)


def upgrade() -> None:
    """Add scope/version fields and enforce append-only audit storage."""
    for table_name in _LIFECYCLE_TABLES:
        op.add_column(table_name, sa.Column("deleted_by", sa.Uuid(), nullable=True))

    op.add_column(
        "users",
        sa.Column(
            "authorization_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("roles", sa.Column("firm_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "FK_roles_firms", "roles", "firms", ["firm_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("IX_roles_firm_id", "roles", ["firm_id"])

    with op.batch_alter_table("user_roles") as batch_op:
        batch_op.drop_constraint("UQ_user_roles_user_id", type_="unique")
        batch_op.add_column(sa.Column("firm_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "FK_user_roles_firms", "firms", ["firm_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_unique_constraint(
            "UQ_user_roles_user_role_firm", ["user_id", "role_id", "firm_id"]
        )
        batch_op.create_index("IX_user_roles_firm_id", ["firm_id"])

    op.add_column("audit_logs", sa.Column("firm_id", sa.Uuid(), nullable=True))
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(45), nullable=True))
    op.add_column(
        "audit_logs", sa.Column("application_version", sa.String(50), nullable=True)
    )
    op.create_index("IX_audit_logs_firm_id", "audit_logs", ["firm_id"])

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions "
            "WHERE role_id IN (SELECT id FROM roles WHERE code = 'FIRM_ADMIN') "
            "AND permission_id IN ("
            "SELECT id FROM permissions WHERE code IN ("
            "'PLATFORM_VIEW', 'PLATFORM_SETTINGS', 'SYSTEM_CONFIGURATION', "
            "'SYSTEM_BACKUP', 'SYSTEM_RESTORE', 'LICENSE_MANAGE', "
            "'FIRM_CREATE', 'FIRM_VIEW', 'FIRM_UPDATE', 'FIRM_DELETE', "
            "'FIRM_ACTIVATE', 'FIRM_DEACTIVATE', 'AUDIT_LOG_VIEW', "
            "'DELETE_TRANSACTION', 'VOID_INVOICE', 'EDIT_POSTED_TRANSACTION', "
            "'CHANGE_FINANCIAL_YEAR', 'RESTORE_BACKUP', 'DATABASE_MAINTENANCE'))"
        )
    )

    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "CREATE OR REPLACE FUNCTION reject_audit_log_mutation() "
                "RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN "
                "RAISE EXCEPTION 'audit_logs is append-only'; END; $$"
            )
        )
        connection.execute(
            sa.text("DROP TRIGGER IF EXISTS TR_audit_logs_append_only ON audit_logs")
        )
        connection.execute(
            sa.text(
                "CREATE TRIGGER TR_audit_logs_append_only "
                "BEFORE UPDATE OR DELETE ON audit_logs "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
            )
        )


def downgrade() -> None:
    """Remove hardening fields and append-only enforcement where reversible."""
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text("DROP TRIGGER TR_audit_logs_append_only ON audit_logs")
        )
        connection.execute(sa.text("DROP FUNCTION reject_audit_log_mutation()"))

    op.drop_index("IX_audit_logs_firm_id", table_name="audit_logs")
    op.drop_column("audit_logs", "application_version")
    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "firm_id")

    with op.batch_alter_table("user_roles") as batch_op:
        batch_op.drop_index("IX_user_roles_firm_id")
        batch_op.drop_constraint("UQ_user_roles_user_role_firm", type_="unique")
        batch_op.drop_constraint("FK_user_roles_firms", type_="foreignkey")
        batch_op.drop_column("firm_id")
        batch_op.create_unique_constraint(
            "UQ_user_roles_user_id", ["user_id", "role_id"]
        )

    op.drop_index("IX_roles_firm_id", table_name="roles")
    op.drop_constraint("FK_roles_firms", "roles", type_="foreignkey")
    op.drop_column("roles", "firm_id")
    op.drop_column("users", "authorization_version")
    for table_name in reversed(_LIFECYCLE_TABLES):
        op.drop_column(table_name, "deleted_by")
