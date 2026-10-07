"""Delivery notes take their own codes, and Warehouse holds them.

D-UI-30, found on screen on 2026-10-07 (SC-DN-025, SC-SO-034): the Warehouse
job (`INVENTORY_MANAGER`) "receives, stores, picks and dispatches stock" and
could neither see nor dispatch a delivery note. Every note route asked for a
sales code -- `SALES_VIEW`, `SALES_CREATE`, `SALES_UPDATE`, `SALES_APPROVE`,
`SALES_CANCEL` -- and handing Warehouse those would have opened the orders,
quotations and bills to it as well.

The note routes now take the sales code they always took **or** one of three
of their own, and the approved orders a note is raised from are read under
`DELIVERY_NOTE_VIEW` the way `PURCHASE_RECEIVE` reads the purchase orders it
receives against. This migration:

* inserts `DELIVERY_NOTE_VIEW`, `DELIVERY_NOTE_CREATE` and
  `DELIVERY_NOTE_DISPATCH` where they are missing;
* grants each to every role -- system or a firm's own -- that already held
  the sales code it stands beside (`SALES_VIEW`, `SALES_CREATE`,
  `SALES_APPROVE`), so the catalogue reads the same for a role built by hand
  as for a seeded one. Nobody loses anything either way: the routes still
  accept the sales codes;
* grants `INVENTORY_MANAGER` all three. It is **not** given
  `SALES_INVOICE_CREATE` or `SALES_APPROVE`, so "Dispatch and invoice", which
  raises and approves a bill, stays out of its reach.

The codes are named rather than read from `ROLE_PERMISSION_CODES`, so a replay
next year does this change and not whatever the seed says then (the rule
`20261004_0301` followed). Nothing bumps `authorization_version`: a widening of
access is picked up at the next token refresh or sign-in.

`roles`, `permissions` and `role_permissions` live only in the platform schema,
so this is a no-op in every firm store. Every step is create-if-missing.

Revision ID: 20261007_0349
Revises: 20261006_0348
Create Date: 2026-10-07

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261007_0349"
down_revision: str | Sequence[str] | None = "20261006_0348"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Each new code, its display name, and the sales code whose holders gain it.
_CODES: tuple[tuple[str, str, str], ...] = (
    ("DELIVERY_NOTE_VIEW", "Delivery Note View", "SALES_VIEW"),
    ("DELIVERY_NOTE_CREATE", "Delivery Note Create", "SALES_CREATE"),
    ("DELIVERY_NOTE_DISPATCH", "Delivery Note Dispatch", "SALES_APPROVE"),
)

_WAREHOUSE = "INVENTORY_MANAGER"

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


def _ensure_permission(bind: sa.Connection, code: str, name: str) -> None:
    """Insert one code where this database never seeded it."""
    present = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
    ).first()
    if present is not None:
        return
    bind.execute(
        _permissions.insert().values(
            id=uuid4(),
            code=code,
            name=name,
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


def _holders(bind: sa.Connection, permission_id: object) -> list[object]:
    """Return the live roles holding one permission."""
    return [
        row[0]
        for row in bind.execute(
            sa.text(
                f"SELECT DISTINCT rp.role_id FROM {_TABLE} rp "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE rp.is_deleted = false AND r.is_deleted = false "
                "AND rp.permission_id = :permission"
            ),
            {"permission": permission_id},
        ).all()
    ]


def upgrade() -> None:
    """Seed the delivery note codes and grant them to whoever dispatches."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE) or not inspector.has_table("permissions"):
        return

    for code, name, _ in _CODES:
        _ensure_permission(bind, code, name)
    permissions = _ids(
        bind,
        "permissions",
        [code for code, _, _ in _CODES] + [sales for _, _, sales in _CODES],
    )
    warehouse = _ids(bind, "roles", [_WAREHOUSE]).get(_WAREHOUSE)

    for code, _, sales in _CODES:
        permission_id = permissions.get(code)
        if permission_id is None:
            # Present but soft-deleted: somebody retired it on purpose.
            continue
        sales_id = permissions.get(sales)
        if sales_id is not None:
            for role_id in _holders(bind, sales_id):
                _grant(bind, role_id, permission_id)
        if warehouse is not None:
            _grant(bind, warehouse, permission_id)


def downgrade() -> None:
    """Retire the grants, soft-deleted as `delete_role` retires one.

    The permission rows stay, as `20261004_0302` leaves its own: a code is
    cheap to keep and a role that held it before is not ours to guess.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true "
            "WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(
            sa.bindparam(
                "codes", value=[code for code, _, _ in _CODES], expanding=True
            )
        )
    )
