"""The Bill collector role and the code that reads his own bills (backlog 123).

* ``COLLECTION_OWN_VIEW`` seeded: reading the bills handed to oneself.
* ``BILL_COLLECTOR``, a seventeenth system role holding that code and nothing
  else, and the system roles reconciled so the firm's administrator, manager,
  accountant and read-only user hold the code too.
* The ``bill-collector`` job template, so a firm hires one by name.

Platform data only: the identity tables live in the platform schema, so on a
firm store this does nothing. Idempotent: the role, the code, each grant and
the template are inserted only where missing. ``seed_system_rbac`` runs only
from the sample-data script, never at startup, so a database that already
exists gets the role from here or not at all.

Revision ID: 20261013_0363
Revises: 20261013_0362
Create Date: 2026-10-13

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import (
    ROLE_PERMISSION_CODES,
    SYSTEM_PERMISSION_CODES,
    SYSTEM_USER_TEMPLATES,
)

revision: str = "20261013_0363"
down_revision: str | Sequence[str] | None = "20261013_0362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "BILL_COLLECTOR"
_TEMPLATE = "bill-collector"

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
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_system", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)
_templates = sa.table(
    "user_templates",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_active", sa.Boolean()),
    sa.column("is_system", sa.Boolean()),
)
_template_roles = sa.table(
    "user_template_roles",
    sa.column("id", UUIDType()),
    sa.column("template_id", UUIDType()),
    sa.column("role_id", UUIDType()),
)


def _display_name(code: str) -> str:
    """Render a system code as a readable name."""
    return code.replace("_", " ").title()


def _seed_role(bind: sa.engine.Connection) -> None:
    """Insert the system role where the platform lacks it."""
    present = bind.execute(
        sa.select(_roles.c.id).where(
            _roles.c.code == _ROLE,
            _roles.c.firm_id.is_(None),
            _roles.c.is_deleted.is_(False),
        )
    ).first()
    if present is not None:
        return
    bind.execute(
        _roles.insert().values(
            id=uuid4(),
            code=_ROLE,
            name=_display_name(_ROLE),
            description="System-defined role.",
            firm_id=None,
            is_system=True,
            is_active=True,
            is_deleted=False,
        )
    )


def _seed_permissions(bind: sa.engine.Connection) -> None:
    """Insert missing system permissions and reconcile system role grants."""
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


def _seed_template(bind: sa.engine.Connection) -> None:
    """Insert the job template where the platform lacks it."""
    present = bind.execute(
        sa.select(_templates.c.id).where(
            _templates.c.code == _TEMPLATE, _templates.c.firm_id.is_(None)
        )
    ).first()
    role_id = bind.execute(
        sa.select(_roles.c.id).where(
            _roles.c.code == _ROLE,
            _roles.c.firm_id.is_(None),
            _roles.c.is_deleted.is_(False),
        )
    ).scalar()
    if present is not None or role_id is None:
        return
    name, description = next(
        (name, description)
        for code, name, description, _ in SYSTEM_USER_TEMPLATES
        if code == _TEMPLATE
    )
    template_id = uuid4()
    bind.execute(
        _templates.insert().values(
            id=template_id,
            code=_TEMPLATE,
            name=name,
            description=description,
            firm_id=None,
            is_active=True,
            is_system=True,
        )
    )
    bind.execute(
        _template_roles.insert().values(
            id=uuid4(), template_id=template_id, role_id=role_id
        )
    )


def upgrade() -> None:
    """Seed the role, the code, the grants and the job template."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    _seed_role(bind)
    _seed_permissions(bind)
    if inspector.has_table("user_templates"):
        _seed_template(bind)


def downgrade() -> None:
    """Leave the role, the code and the template in place.

    People may hold the role by now; taking it away is an administrator's
    act, not a downgrade's.
    """
