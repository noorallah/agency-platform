"""Receiving goods takes its own code, `PURCHASE_RECEIVE`.

D-ROLE-3, found live on 2026-10-04: completing a goods receipt was gated on
`PURCHASE_APPROVE` -- the code that approves orders and bills -- so the jobs
that receive goods could not. Purchasing (`PURCHASE_EXECUTIVE`) raised a
receipt and was refused at Complete; Warehouse (`INVENTORY_MANAGER`) could not
raise one at all, holding no `PURCHASE_CREATE`.

Raising, editing and completing a receipt now take `PURCHASE_RECEIVE`, and a
receiver reads the receipts and the orders it receives against under the same
code. This migration:

* inserts the permission where it is missing;
* grants it to every role -- system or a firm's own -- that already held
  `PURCHASE_CREATE`, `PURCHASE_UPDATE` or `PURCHASE_APPROVE`, the three codes
  the receipt routes took before. Nobody loses a receipt action they had; a
  role that could raise a receipt can now also complete it, which is the fix.
  For the seeded roles that is `PURCHASE_MANAGER`, `PURCHASE_EXECUTIVE`,
  `FIRM_ADMIN`, `FIRM_MANAGER`, `PLATFORM_ADMIN` and `SUPPORT_ADMIN`, exactly
  the roles `system_seed.py` gives it through the purchase group;
* grants `INVENTORY_MANAGER` the code, and `TAX_VIEW` and `UOM_VIEW`, which the
  receipt editor's lines read (`/tax-framework/profiles`,
  `/uom-framework/uoms`). It is **not** given `PURCHASE_CREATE`: ordering is
  not the storeman's.

The codes are named rather than read from `ROLE_PERMISSION_CODES`, so a replay
next year does this change and not whatever the seed says then (the rule
`20261004_0301` followed). Nothing bumps `authorization_version`: a widening of
access is picked up at the next token refresh or sign-in.

`roles`, `permissions` and `role_permissions` live only in the platform schema,
so this is a no-op in every firm store. Every step is create-if-missing.

Revision ID: 20261004_0302
Revises: 20261004_0301
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261004_0302"
down_revision: str | Sequence[str] | None = "20261004_0301"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CODE = "PURCHASE_RECEIVE"

#: The codes the receipt routes took before; a role holding any gains the new one.
_PREVIOUS_CODES = ("PURCHASE_CREATE", "PURCHASE_UPDATE", "PURCHASE_APPROVE")

#: What Warehouse gains by name.
_INVENTORY_MANAGER_CODES = (_CODE, "TAX_VIEW", "UOM_VIEW")

_TABLE = "role_permissions"

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
_grants = sa.table(
    _TABLE,
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
)


def _ids(bind: sa.Connection, table: str, codes: list[str]) -> dict[str, object]:
    """Map each live code in `table` to its id."""
    return dict(
        bind.execute(
            sa.text(
                f"SELECT code, id FROM {table} "
                "WHERE code IN :codes AND is_deleted = false"
            ).bindparams(sa.bindparam("codes", value=codes, expanding=True))
        ).all()
    )


def _ensure_permission(bind: sa.Connection) -> None:
    """Insert `PURCHASE_RECEIVE` where this database never seeded it."""
    present = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": _CODE}
    ).first()
    if present is not None:
        return
    bind.execute(
        _permissions.insert().values(
            id=uuid4(),
            code=_CODE,
            name="Purchase Receive",
            description="System-defined permission.",
            is_system=True,
            is_active=True,
            is_deleted=False,
        )
    )


def _grant(bind: sa.Connection, role_id: object, permission_id: object) -> None:
    """Grant one code to one role, restoring a soft-deleted grant."""
    existing = bind.execute(
        sa.text(
            f"SELECT id, is_deleted FROM {_TABLE} "
            "WHERE role_id = :role AND permission_id = :permission"
        ),
        {"role": role_id, "permission": permission_id},
    ).first()
    if existing is None:
        op.bulk_insert(
            _grants,
            [{"id": uuid4(), "role_id": role_id, "permission_id": permission_id}],
        )
    elif existing[1]:
        # Restored rather than re-inserted: the unique key on
        # (role_id, permission_id) ignores the soft delete.
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET is_deleted = false, "
                "deleted_at = NULL, deleted_by = NULL WHERE id = :id"
            ),
            {"id": existing[0]},
        )


def upgrade() -> None:
    """Seed `PURCHASE_RECEIVE` and grant it to the roles that receive goods."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE) or not inspector.has_table("permissions"):
        return

    _ensure_permission(bind)
    permissions = _ids(bind, "permissions", [*_PREVIOUS_CODES, "TAX_VIEW", "UOM_VIEW"])
    permissions.update(_ids(bind, "permissions", [_CODE]))
    receive_id = permissions.get(_CODE)
    if receive_id is None:
        # Present but soft-deleted: somebody retired it on purpose.
        return

    previous_ids = [permissions[c] for c in _PREVIOUS_CODES if c in permissions]
    holders: list[object] = []
    if previous_ids:
        holders = [
            row[0]
            for row in bind.execute(
                sa.text(
                    f"SELECT DISTINCT rp.role_id FROM {_TABLE} rp "
                    "JOIN roles r ON r.id = rp.role_id "
                    "WHERE rp.is_deleted = false AND r.is_deleted = false "
                    "AND rp.permission_id IN :ids"
                ).bindparams(sa.bindparam("ids", value=previous_ids, expanding=True))
            ).all()
        ]
    for role_id in holders:
        _grant(bind, role_id, receive_id)

    warehouse = _ids(bind, "roles", ["INVENTORY_MANAGER"]).get("INVENTORY_MANAGER")
    if warehouse is None:
        return
    for code in _INVENTORY_MANAGER_CODES:
        permission_id = permissions.get(code)
        if permission_id is not None:
            _grant(bind, warehouse, permission_id)


def downgrade() -> None:
    """Retire the grants, soft-deleted as `delete_role` retires one.

    The permission row stays, as `20261003_0273` leaves its own: a code is
    cheap to keep and a role that held it before is not ours to guess.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true "
            "WHERE permission_id IN (SELECT id FROM permissions WHERE code = :code)"
        ),
        {"code": _CODE},
    )
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true "
            "WHERE role_id IN (SELECT id FROM roles WHERE code = 'INVENTORY_MANAGER') "
            "AND permission_id IN "
            "(SELECT id FROM permissions WHERE code IN ('TAX_VIEW', 'UOM_VIEW'))"
        )
    )
