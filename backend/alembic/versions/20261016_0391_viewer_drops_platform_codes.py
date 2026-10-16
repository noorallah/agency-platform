"""The seeded Viewer gives up the platform's permission codes (D-IDN-17).

``VIEWER`` was seeded as every ``*_VIEW`` code, which swept in ``FIRM_VIEW``
and ``DIAGNOSTICS_VIEW`` (and, before it was excluded by name,
``PLATFORM_VIEW``): platform codes the Firm admin does not hold. The Viewer
was offered the platform's Firm settings and Business profile screens.

This revision soft-deletes those grants on the system ``VIEWER`` role only;
custom roles and every other system role are left alone. The codes are frozen
here as ``PLATFORM_PERMISSION_CODES`` read on 2026-10-16, so the revision means
the same thing however that set changes later. Platform data only; idempotent,
because only live grants are touched.

Revision ID: 20261016_0391
Revises: 20261015_0390
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261016_0391"
down_revision: str | Sequence[str] | None = "20261015_0390"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLATFORM_CODES = (
    "AUDIT_LOG_VIEW",
    "CHANGE_FINANCIAL_YEAR",
    "DATABASE_MAINTENANCE",
    "DELETE_TRANSACTION",
    "DIAGNOSTICS_VIEW",
    "EDIT_POSTED_TRANSACTION",
    "FIRM_ACTIVATE",
    "FIRM_CREATE",
    "FIRM_DEACTIVATE",
    "FIRM_DELETE",
    "FIRM_UPDATE",
    "FIRM_VIEW",
    "LICENSE_MANAGE",
    "PLATFORM_SETTINGS",
    "PLATFORM_VIEW",
    "RESTORE_BACKUP",
    "SETTINGS_UPDATE",
    "SETTINGS_VIEW",
    "SYSTEM_BACKUP",
    "SYSTEM_CONFIGURATION",
    "SYSTEM_RESTORE",
    "VOID_INVOICE",
)

_permissions = sa.table(
    "permissions",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
)
_roles = sa.table(
    "roles",
    sa.column("id", UUIDType()),
    sa.column("code", sa.String()),
    sa.column("firm_id", UUIDType()),
    sa.column("is_system", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
    sa.column("deleted_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("version", sa.Integer()),
)


def upgrade() -> None:
    """Soft-delete the system Viewer's live grants of platform codes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not all(
        inspector.has_table(name)
        for name in ("permissions", "roles", "role_permissions")
    ):
        return
    viewer = sa.select(_roles.c.id).where(
        _roles.c.code == "VIEWER",
        _roles.c.is_system.is_(True),
        _roles.c.firm_id.is_(None),
    )
    platform_codes = sa.select(_permissions.c.id).where(
        _permissions.c.code.in_(_PLATFORM_CODES)
    )
    bind.execute(
        _role_permissions.update()
        .where(
            _role_permissions.c.role_id.in_(viewer),
            _role_permissions.c.permission_id.in_(platform_codes),
            _role_permissions.c.is_deleted.is_(False),
        )
        .values(
            is_deleted=True,
            deleted_at=sa.func.now(),
            updated_at=sa.func.now(),
            version=_role_permissions.c.version + 1,
        )
    )


def downgrade() -> None:
    """Leave the grants withdrawn.

    Restoring them would hand a firm's read-only role the platform's screens
    again, which is the defect this revision fixes.
    """
