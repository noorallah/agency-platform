"""Seed the initial system RBAC model and protect system permissions.

Revision ID: 20260729_0006
Revises: 20260728_0005
Create Date: 2026-07-29
"""

from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import (
    ROLE_PERMISSION_CODES,
    SYSTEM_PERMISSION_CODES,
    SYSTEM_ROLE_CODES,
)

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

    _seed_system_rbac(op.get_bind())


def downgrade() -> None:
    """Remove the permission classification while retaining role assignment data."""
    with op.batch_alter_table("permissions") as batch_op:
        batch_op.drop_column("is_system")


def _seed_system_rbac(connection: sa.Connection) -> None:
    roles = sa.table(
        "roles",
        sa.column("id", UUIDType()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_deleted", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    permissions = sa.table(
        "permissions",
        sa.column("id", UUIDType()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_deleted", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("id", UUIDType()),
        sa.column("role_id", UUIDType()),
        sa.column("permission_id", UUIDType()),
        sa.column("is_deleted", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )

    role_rows = connection.execute(sa.select(roles.c.id, roles.c.code)).all()
    role_ids = {str(code): role_id for role_id, code in role_rows if code is not None}
    for code in SYSTEM_ROLE_CODES:
        if code in role_ids:
            connection.execute(
                roles.update()
                .where(roles.c.id == role_ids[code])
                .values(
                    is_system=True,
                    is_deleted=False,
                    deleted_at=None,
                )
            )
            continue
        role_id = uuid4()
        role_ids[code] = role_id
        connection.execute(
            roles.insert().values(
                id=role_id,
                code=code,
                name=_display_name(code),
                description="System-defined role.",
                is_system=True,
                is_deleted=False,
            )
        )

    permission_rows = connection.execute(
        sa.select(permissions.c.id, permissions.c.code)
    ).all()
    permission_ids = {
        str(code): permission_id
        for permission_id, code in permission_rows
        if code is not None
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in permission_ids:
            connection.execute(
                permissions.update()
                .where(permissions.c.id == permission_ids[code])
                .values(
                    is_system=True,
                    is_deleted=False,
                    deleted_at=None,
                )
            )
            continue
        permission_id = uuid4()
        permission_ids[code] = permission_id
        connection.execute(
            permissions.insert().values(
                id=permission_id,
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
                is_deleted=False,
            )
        )

    assignment_rows = connection.execute(
        sa.select(
            role_permissions.c.id,
            role_permissions.c.role_id,
            role_permissions.c.permission_id,
        )
    ).all()
    assignments: dict[tuple[UUID, UUID], UUID] = {
        (role_id, permission_id): assignment_id
        for assignment_id, role_id, permission_id in assignment_rows
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids[role_code]
        for permission_code in permission_codes:
            permission_id = permission_ids[permission_code]
            key = (role_id, permission_id)
            existing_id = assignments.get(key)
            if existing_id is None:
                connection.execute(
                    role_permissions.insert().values(
                        id=uuid4(),
                        role_id=role_id,
                        permission_id=permission_id,
                        is_deleted=False,
                    )
                )
                continue
            connection.execute(
                role_permissions.update()
                .where(role_permissions.c.id == existing_id)
                .values(is_deleted=False, deleted_at=None)
            )


def _display_name(code: str) -> str:
    return code.replace("_", " ").title()
