"""The accountant reads the firm's financial years and periods (R-1).

Ledgers, Trial Balance, Profit & Loss, Cash Flow, Balance Sheet and the
Income-tax block schedule each list the firm's accounting periods or years
before anything else, and that read needs ``FINANCIAL_YEAR_VIEW``. The seeded
``ACCOUNTANT`` role held every statement code but not that one, so each of
those screens opened on a refusal.

* ``FINANCIAL_YEAR_VIEW`` granted to the system ``ACCOUNTANT`` role. A firm's
  own roles are left as their administrator made them.

Platform data only: identity tables live in the platform schema.
Idempotent: the grant is inserted only where missing.

Revision ID: 20261017_0393
Revises: 20261016_0392
Create Date: 2026-10-17

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261017_0393"
down_revision: str | Sequence[str] | None = "20261016_0392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE = "FINANCIAL_YEAR_VIEW"
_ROLE = "ACCOUNTANT"

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
    sa.column("is_deleted", sa.Boolean()),
)
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def upgrade() -> None:
    """Grant ``FINANCIAL_YEAR_VIEW`` to the system ``ACCOUNTANT`` role."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (
        inspector.has_table("permissions")
        and inspector.has_table("roles")
        and inspector.has_table("role_permissions")
    ):
        return
    permission_id = bind.scalar(
        sa.select(_permissions.c.id).where(_permissions.c.code == _CODE)
    )
    if permission_id is None:
        # The startup seed inserts every code; nothing to grant until it has.
        return
    role_ids = {
        role_id
        for (role_id,) in bind.execute(
            sa.select(_roles.c.id).where(
                _roles.c.code == _ROLE,
                _roles.c.firm_id.is_(None),
                _roles.c.is_deleted.is_(False),
            )
        )
    }
    granted = {
        role_id
        for (role_id,) in bind.execute(
            sa.select(_role_permissions.c.role_id).where(
                _role_permissions.c.permission_id == permission_id,
                _role_permissions.c.is_deleted.is_(False),
            )
        )
    }
    for role_id in role_ids - granted:
        bind.execute(
            _role_permissions.insert().values(
                id=uuid4(),
                role_id=role_id,
                permission_id=permission_id,
                is_deleted=False,
            )
        )


def downgrade() -> None:
    """Leave the grant: a user may already rely on it."""
