"""Job roles can read the masters their own documents are typed from.

D-ROLE-1, found live on 2026-10-04: the Purchasing job (`PURCHASE_EXECUTIVE`)
opened a purchase order and was told "An order needs a vendor to buy from and a
product to buy", because the server refused it `GET /vendors`, `/products`,
`/branches` and `/warehouses`. The master view codes are enforced (D-MST-10)
and were never granted to the job roles whose editors read them. The same gap
ran through the sales, stock and billing roles.

What each role gains was derived from the desktop editors -- which master lists
each document's screen loads -- and the code each of those routes enforces.
`app/identity/system_seed.py` carries the reason beside every code, and
`tests/unit/test_job_roles_read_their_masters.py` asks the question per
document so the next gap fails the build.

`PURCHASE_MANAGER` also gains the vendor master writes its job template
promises ("owns the vendor masters"), less the bank account codes, which stay
with whoever pays.

`seed_system_rbac` runs only from the sample-data script, never at startup, so
a database that exists gets its seeded rows here -- the rule `20260906_0130`
followed. The codes are named rather than read from `ROLE_PERMISSION_CODES`,
so a replay next year does this change and not whatever the seed says then.

Nothing bumps `authorization_version`: a widening of access is picked up at
the next token refresh or sign-in, not by signing everybody out.

`roles`, `permissions` and `role_permissions` live only in the platform schema,
so this is a no-op in every firm store.

Revision ID: 20261004_0301
Revises: 20261004_0300
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261004_0301"
down_revision: str | Sequence[str] | None = "20261004_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURCHASE_MASTERS = (
    "VENDOR_VIEW",
    "PRODUCT_VIEW",
    "BRANCH_VIEW",
    "WAREHOUSE_VIEW",
    "TAX_VIEW",
    "UOM_VIEW",
)

#: What each seeded role gains.
_GRANTS: dict[str, tuple[str, ...]] = {
    "PURCHASE_EXECUTIVE": _PURCHASE_MASTERS,
    "PURCHASE_MANAGER": _PURCHASE_MASTERS
    + (
        "VENDOR_CREATE",
        "VENDOR_UPDATE",
        "VENDOR_DELETE",
        "VENDOR_RESTORE",
        "VENDOR_IMPORT",
        "VENDOR_EXPORT",
        "VENDOR_MANAGE_CATEGORIES",
    ),
    "INVENTORY_MANAGER": (
        "PRODUCT_VIEW",
        "BRANCH_VIEW",
        "WAREHOUSE_VIEW",
        "VENDOR_VIEW",
        "CUSTOMER_VIEW",
    ),
    "SALES_MANAGER": ("BRANCH_VIEW", "WAREHOUSE_VIEW", "TAX_VIEW", "UOM_VIEW"),
    "SALES_EXECUTIVE": ("PRODUCT_VIEW", "BRANCH_VIEW", "WAREHOUSE_VIEW"),
    "BILLING_EXECUTIVE": ("CUSTOMER_VIEW", "PRODUCT_VIEW"),
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
    """Grant each job role the master view codes its documents need."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
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
    """Take the grants back off, soft-deleted as `delete_role` retires one."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
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
