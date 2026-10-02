"""``FIRM_AUDIT_LOG_VIEW``: a firm's own audit trail, grantable (decision B1).

``AUDIT_LOG_VIEW`` is a platform code a firm administrator cannot grant, so
nobody but the administrator could read the firm's trail. The new code reads
a firm's trail with that firm selected and nothing else; it is granted where
the seed says (the firm administrator) and may be added to any firm role.

Platform store only (permissions and roles live there). Idempotent.

Revision ID: 20261002_0222
Revises: 20261002_0221
Create Date: 2026-10-02

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20261002_0222"
down_revision: str | Sequence[str] | None = "20261002_0221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE = "FIRM_AUDIT_LOG_VIEW"

_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_roles = sa.table("roles", sa.column("id", UUIDType()), sa.column("code", sa.String()))
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def upgrade() -> None:
    """Define the code and grant it to the seeded roles that hold it."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    permission_id = bind.execute(
        sa.select(_permissions.c.id).where(_permissions.c.code == _CODE)
    ).scalar()
    if permission_id is None:
        permission_id = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=_CODE,
                name="Firm Audit Log View",
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )
    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
    }
    granted = {
        role_id
        for (role_id,) in bind.execute(
            sa.select(_role_permissions.c.role_id).where(
                _role_permissions.c.permission_id == permission_id,
                _role_permissions.c.is_deleted.is_(False),
            )
        ).all()
    }
    for role_code, codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None or _CODE not in codes or role_id in granted:
            continue
        bind.execute(
            _role_permissions.insert().values(
                id=uuid4(),
                role_id=role_id,
                permission_id=permission_id,
                is_deleted=False,
            )
        )


def downgrade() -> None:
    """Leave the code in place, as every permission migration here does.

    Removing it would strip grants an administrator may since have made to
    custom roles.
    """
