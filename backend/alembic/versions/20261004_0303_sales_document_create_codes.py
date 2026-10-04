"""A sales order and a sales invoice are raised under their own codes.

D-ROLE-2, found live on 2026-10-04: `SALES_EXECUTIVE` has held
`SALES_ORDER_CREATE` and `SALES_INVOICE_CREATE`, and `BILLING_EXECUTIVE`
`SALES_INVOICE_CREATE`, since the identity seed was written -- and
`POST /sales-orders` and `POST /sales-invoices` asked for `SALES_CREATE`, which
neither holds. Field Sales could raise a quotation and nothing after it;
Counter Sales could not raise a bill at all.

The two create routes (and their previews) now take the per-document code, as
`POST /quotations` has taken `SALES_QUOTATION_CREATE` since 2026-08-14, and
"dispatch and invoice" on a delivery note asks for `SALES_INVOICE_CREATE` for
the bill it raises. Editing a draft takes `SALES_UPDATE` as before, or the
create code for the draft the caller raised. This migration grants
`SALES_ORDER_CREATE` and `SALES_INVOICE_CREATE` to every role -- system or a
firm's own -- that holds `SALES_CREATE`, so nobody loses the order or the bill
they could raise yesterday. For the seeded roles that changes nothing:
`SALES_MANAGER`, `FIRM_ADMIN`, `FIRM_MANAGER`, `PLATFORM_ADMIN` and
`SUPPORT_ADMIN` take both through the sales group already. A firm's own role
built with `SALES_CREATE` and without the new codes is the case it is for.

Both codes have been seeded since `20260809_0044`; they are inserted here where
missing all the same, since a grant to a code that is not there is no grant.
The codes are named rather than read from `ROLE_PERMISSION_CODES`, so a replay
next year does this change and not whatever the seed says then. Nothing bumps
`authorization_version`: a widening of access is picked up at the next token
refresh or sign-in.

`roles`, `permissions` and `role_permissions` live only in the platform schema,
so this is a no-op in every firm store. Every step is create-if-missing.

Revision ID: 20261004_0303
Revises: 20261004_0302
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261004_0303"
down_revision: str | Sequence[str] | None = "20261004_0302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The code the two create routes took before.
_PREVIOUS_CODE = "SALES_CREATE"

#: What a holder of the previous code gains, with the name each is seeded under.
_CODES = {
    "SALES_ORDER_CREATE": "Sales Order Create",
    "SALES_INVOICE_CREATE": "Sales Invoice Create",
}

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


def _ids(bind: sa.Connection, codes: list[str]) -> dict[str, object]:
    """Map each live permission code to its id."""
    return dict(
        bind.execute(
            sa.text(
                "SELECT code, id FROM permissions "
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


def upgrade() -> None:
    """Grant the per-document create codes to every holder of `SALES_CREATE`."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE) or not inspector.has_table("permissions"):
        return

    for code, name in _CODES.items():
        _ensure_permission(bind, code, name)
    permissions = _ids(bind, [_PREVIOUS_CODE, *_CODES])
    previous_id = permissions.get(_PREVIOUS_CODE)
    if previous_id is None:
        return
    holders = [
        row[0]
        for row in bind.execute(
            sa.text(
                f"SELECT DISTINCT rp.role_id FROM {_TABLE} rp "
                "JOIN roles r ON r.id = rp.role_id "
                "WHERE rp.is_deleted = false AND r.is_deleted = false "
                "AND rp.permission_id = :previous"
            ),
            {"previous": previous_id},
        ).all()
    ]
    for role_id in holders:
        for code in _CODES:
            # Absent only when present but soft-deleted: retired on purpose.
            permission_id = permissions.get(code)
            if permission_id is not None:
                _grant(bind, role_id, permission_id)


def downgrade() -> None:
    """Leave the grants where they are.

    Both codes were seeded, and held by `SALES_EXECUTIVE`, `BILLING_EXECUTIVE`
    and the sales group, long before this revision, so nothing here can tell a
    grant it made from one that was already there. Retiring them all would
    take the quotation-to-bill path away from the roles that always had the
    codes; leaving them grants nothing the old routes asked for.
    """
