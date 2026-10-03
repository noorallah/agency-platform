"""A supplier bill past tolerance over its order waits (BUY-10, decision A99).

* ``purchase_workflow_settings.bill_price_tolerance_percent`` and
  ``bill_tolerance_amount`` (both null: no check).
* ``PURCHASE_APPROVE_OVER_TOLERANCE`` seeded and the system roles reconciled,
  the shape of ``20261003_0248``.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0265
Revises: 20261003_0264
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0265"
down_revision: str | Sequence[str] | None = "20261003_0264"
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


def _seed_permissions() -> None:
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

    role_ids = {
        code: role_id
        for role_id, code in bind.execute(sa.select(_roles.c.id, _roles.c.code)).all()
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


def upgrade() -> None:
    """Add the two tolerances and seed the permission."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_workflow_settings"):
        have = {c["name"] for c in inspector.get_columns("purchase_workflow_settings")}
        if "bill_price_tolerance_percent" not in have:
            op.add_column(
                "purchase_workflow_settings",
                sa.Column("bill_price_tolerance_percent", sa.Numeric(7, 4)),
            )
        if "bill_tolerance_amount" not in have:
            op.add_column(
                "purchase_workflow_settings",
                sa.Column("bill_tolerance_amount", sa.Numeric(18, 2)),
            )
    _seed_permissions()


def downgrade() -> None:
    """Drop the two tolerances; the permission stays, as system codes do."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_workflow_settings"):
        have = {c["name"] for c in inspector.get_columns("purchase_workflow_settings")}
        for column in ("bill_price_tolerance_percent", "bill_tolerance_amount"):
            if column in have:
                op.drop_column("purchase_workflow_settings", column)
