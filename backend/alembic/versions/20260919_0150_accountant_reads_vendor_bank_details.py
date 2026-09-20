"""The accountant keeps reading a supplier's bank account.

`VENDOR_VIEW_FINANCIAL_DETAILS` was seeded and enforced by no route, so a
vendor's bank accounts were served to anybody holding `VENDOR_VIEW` -- the
read-only `VIEWER` included (D-MST-10). The vendor router now withholds them
without the code.

Every seeded role that edits vendors already holds it. `ACCOUNTANT` does not,
and is the one role that reads the account as part of its job: it pays
suppliers. This grants it the read so enforcing the code takes nothing from
whoever sends the money. `VENDOR_MANAGE_BANK_DETAILS` is deliberately **not**
granted -- whoever sends the money must not be the one who says where it goes.

`seed_system_rbac` is called only by `generate_sample_data.py` and never at
startup, so a database that already exists gets its seeded rows from a
migration -- as in `20260809_0044`, `20260906_0130` and `20260906_0131`.

Nothing here bumps `authorization_version`: the next token refresh carries a
widening, and signing every accountant out mid-work to deliver one is the
worse trade. Until it does, an accountant's existing token reads a vendor with
no bank accounts shown, which is the safe direction to be briefly wrong in.

Revision ID: 20260919_0150
Revises: 20260919_0149
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0150"
down_revision: str | None = "20260919_0149"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "ACCOUNTANT"
_CODE = "VENDOR_VIEW_FINANCIAL_DETAILS"
_TABLE = "role_permissions"


def upgrade() -> None:
    """Grant the accountant the read of a vendor's bank accounts."""
    bind = op.get_bind()
    # `roles` and `permissions` live only in the platform schema; a firm store
    # has neither, and this migration runs against every store.
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
    """Take the read back off the accountant."""
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
