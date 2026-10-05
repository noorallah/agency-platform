"""Field Sales may add a customer (D-SELL-57).

Found driving selling on 2026-10-05: with *New outlets need approval* on, a
Field Sales user (`SALES_EXECUTIVE`) was refused `POST /customers` (403), and
every seeded role that held `CUSTOMER_CREATE` also held `CUSTOMER_APPROVE` --
so no customer anybody added ever started PENDING, and the setting could not
be reached with the jobs a firm starts with. The salesman now holds
`CUSTOMER_CREATE` and still not `CUSTOMER_APPROVE`.

The code is named rather than read from `ROLE_PERMISSION_CODES`, as in
`20261004_0305`. `roles`, `permissions` and `role_permissions` live only in the
platform schema, so this is a no-op in every firm store. Idempotent: a grant
already there is left, and one retired by a soft delete is restored.

Revision ID: 20261005_0332
Revises: 20261005_0331
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261005_0332"
down_revision: str | Sequence[str] | None = "20261005_0331"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: What each seeded role gains.
_GRANTS: dict[str, tuple[str, ...]] = {
    "SALES_EXECUTIVE": ("CUSTOMER_CREATE",),
}

_TABLE = "role_permissions"


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


def upgrade() -> None:
    """Grant Field Sales the code that adds a customer."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not all(inspector.has_table(name) for name in (_TABLE, "roles", "permissions")):
        return

    roles = _ids(bind, "roles", list(_GRANTS))
    permissions = _ids(
        bind, "permissions", sorted({c for codes in _GRANTS.values() for c in codes})
    )
    grants = sa.table(
        _TABLE,
        sa.column("id", UUIDType()),
        sa.column("role_id", UUIDType()),
        sa.column("permission_id", UUIDType()),
    )
    for role_code, codes in _GRANTS.items():
        role_id = roles.get(role_code)
        if role_id is None:
            continue
        for permission_code in codes:
            permission_id = permissions.get(permission_code)
            if permission_id is None:
                # A code this database never seeded: nothing to grant, and a
                # dangling row would break the foreign key.
                continue
            existing = bind.execute(
                sa.text(
                    f"SELECT id, is_deleted FROM {_TABLE} "
                    "WHERE role_id = :role AND permission_id = :permission"
                ),
                {"role": role_id, "permission": permission_id},
            ).first()
            if existing is None:
                op.bulk_insert(
                    grants,
                    [
                        {
                            "id": uuid4(),
                            "role_id": role_id,
                            "permission_id": permission_id,
                        }
                    ],
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


def downgrade() -> None:
    """Take the grant back off, soft-deleted as `delete_role` retires one."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not all(inspector.has_table(name) for name in (_TABLE, "roles", "permissions")):
        return
    for role_code, codes in _GRANTS.items():
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET is_deleted = true "
                "WHERE role_id IN (SELECT id FROM roles WHERE code = :role) "
                "AND permission_id IN "
                "(SELECT id FROM permissions WHERE code IN :codes)"
            ).bindparams(
                sa.bindparam("role", value=role_code),
                sa.bindparam("codes", value=list(codes), expanding=True),
            )
        )
