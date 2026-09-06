"""A firm administrator can read its own firm's audit trail.

The Settings module is offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW` or
`DIAGNOSTICS_VIEW`, and both its tabs demand one of the latter two. A firm
administrator held only the first, so the module was offered and every tab in
it refused: it opened empty.

`audit_scope` in `app/common/audit/api/router.py` reads **one** trail, chosen
by firm context -- with `X-Firm-ID` a caller gets that firm's and nothing else,
and the membership check still applies. So this grants a firm administrator
their own firm's history and reaches no further.

`DIAGNOSTICS_VIEW` deliberately stays out. Error reports are operational
telemetry for whoever maintains the product, kept in one place rather than
scattered across firm stores, and `firm_id` on them is recorded as data rather
than used as routing.

`seed_system_rbac` is called only by `generate_sample_data.py` and never at
startup, so a database that already exists gets its seeded rows from a
migration -- as in `20260809_0044`, `20260905_0129` and `20260906_0130`.

Nothing here bumps `authorization_version`: signing every firm administrator
out mid-work to deliver a widening of their access is the worse trade, and the
next token refresh carries it.

Revision ID: 20260906_0131
Revises: 20260906_0130
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260906_0131"
down_revision: str | None = "20260906_0130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "FIRM_ADMIN"
_CODE = "AUDIT_LOG_VIEW"
_TABLE = "role_permissions"


def upgrade() -> None:
    """Grant the firm administrator the audit-log read."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return

    role_id = bind.execute(
        sa.text("SELECT id FROM roles WHERE code = :code AND is_deleted = false"),
        {"code": _ROLE},
    ).scalar()
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code AND is_deleted = false"),
        {"code": _CODE},
    ).scalar()
    if role_id is None or permission_id is None:
        return

    existing = bind.execute(
        sa.text(
            f"SELECT id, is_deleted FROM {_TABLE} "
            "WHERE role_id = :role AND permission_id = :permission"
        ),
        {"role": role_id, "permission": permission_id},
    ).first()
    if existing is None:
        op.bulk_insert(
            sa.table(
                _TABLE,
                sa.column("id", UUIDType()),
                sa.column("role_id", UUIDType()),
                sa.column("permission_id", UUIDType()),
            ),
            [{"id": uuid4(), "role_id": role_id, "permission_id": permission_id}],
        )
    elif existing[1]:
        # Restored rather than re-inserted: the unique key on
        # (role_id, permission_id) ignores the soft delete.
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET is_deleted = false, deleted_at = NULL, "
                "deleted_by = NULL WHERE id = :id"
            ),
            {"id": existing[0]},
        )


def downgrade() -> None:
    """Take the audit-log read back off the firm administrator."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true "
            "WHERE role_id = (SELECT id FROM roles WHERE code = :role) "
            "AND permission_id = (SELECT id FROM permissions WHERE code = :code)"
        ),
        {"role": _ROLE, "code": _CODE},
    )
