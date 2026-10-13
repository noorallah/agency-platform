"""A clearance discount at collection takes a code of its own (row F4).

* ``CLEARANCE_DISCOUNT_GIVE`` seeded: waiving part of a due as a discount on
  a receipt beyond the customer's terms, and moving the firm's ceiling on it.
* The system roles reconciled, which gives the code to the firm's
  administrator. ``FIRM_MANAGER`` is not given it; nothing is taken from any
  role, because the code that used to decide this, ``PARTY_ADJUSTMENT_APPROVE``,
  still approves a write-off and every holder keeps it.

Platform data only: the identity tables live in the platform schema, so on a
firm store this does nothing. Idempotent: the code and each grant are inserted
only where missing. ``seed_system_rbac`` runs only from the sample-data
script, never at startup, so a database that already exists gets the code
from here or not at all.

Revision ID: 20261013_0371
Revises: 20261013_0370
Create Date: 2026-10-13

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261013_0371"
down_revision: str | Sequence[str] | None = "20261013_0370"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def upgrade() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        permission_id = uuid4()
        existing[code] = permission_id
        bind.execute(
            _permissions.insert().values(
                id=permission_id,
                code=code,
                name=_display_name(code),
                description="System-defined permission.",
                is_system=True,
                is_active=True,
                is_deleted=False,
            )
        )

    # The platform's own roles only: a firm may have named a role of its own
    # with a system role's code.
    role_ids = {
        code: role_id
        for role_id, code in bind.execute(
            sa.select(_roles.c.id, _roles.c.code).where(
                _roles.c.firm_id.is_(None), _roles.c.is_deleted.is_(False)
            )
        ).all()
    }
    granted = {
        (role_id, permission_id)
        for role_id, permission_id in bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        ).all()
    }
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for permission_code in permission_codes:
            permission_id = existing.get(permission_code)
            if permission_id is None or (role_id, permission_id) in granted:
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
    """Leave the permission in place: a grant may already rest on it."""
