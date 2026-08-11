"""Record client crashes and server failures where support can read them.

The product ships to customers as an executable on machines nobody here can
reach. Until now a failure left `logs/application.log` on the server and nothing
at all from the client, so support got "it closed" and no way to go further.

``error_reports`` lives in the **platform** schema, unlike ``audit_logs``. The
audit trail is per firm store on purpose -- a dedicated-database firm has to keep
its own history inside its own database for the isolation and per-firm restore
guarantees to hold. Error reports are the opposite: operational telemetry for
whoever maintains the product, useless when scattered, and counted across every
firm to decide what to fix first. ``firm_id`` is therefore recorded as data
rather than used as routing.

``DIAGNOSTICS_VIEW`` is seeded here as well as added to ``PERMISSION_GROUPS``. A
code that is enforced but unseeded has no permission row, so it cannot be
attached to any role and the endpoint silently becomes platform-admin-only --
twelve codes were in that state until 2026-08-09. Adding it to the seed covers a
fresh database; this covers the ones that already exist. The reconciliation is
copied from ``20260809_0044`` and driven from ``SYSTEM_PERMISSION_CODES`` /
``ROLE_PERMISSION_CODES``, so it stays right if more codes are added later.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20260811_0065"
down_revision: str | Sequence[str] | None = "20260810_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "error_reports"

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


def upgrade() -> None:
    """Create the report table and reconcile the permission catalogue."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Platform-only, and the identity tables are how a platform target is
    # recognised -- `alembic/env.py` runs this against every schema, so without
    # this guard an unused, never-written copy of the table appears in each firm
    # store, contradicting the whole reason it lives in one place.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("error_type", sa.String(length=200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("stack_trace", sa.Text(), nullable=True),
            sa.Column("app_version", sa.String(length=50), nullable=True),
            sa.Column("build_number", sa.String(length=50), nullable=True),
            sa.Column("platform_info", sa.String(length=200), nullable=True),
            sa.Column("firm_id", UUIDType(), nullable=True),
            sa.Column("user_id", UUIDType(), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("context_label", sa.String(length=200), nullable=True),
            sa.Column("breadcrumbs", sa.JSON(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "received_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="PK_error_reports"),
        )
        op.create_index("IX_error_reports_fingerprint", _TABLE, ["fingerprint"])
        op.create_index("IX_error_reports_received_at", _TABLE, ["received_at"])
        op.create_index("IX_error_reports_request_id", _TABLE, ["request_id"])
        op.create_index("IX_error_reports_firm_id", _TABLE, ["firm_id"])

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


def downgrade() -> None:
    """Drop the report table; leave the seeded permission in place.

    Removing the code would strip grants an administrator may since have made to
    a custom role, which is more damaging than an extra catalogue row --
    the same reasoning as ``20260809_0044``.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
