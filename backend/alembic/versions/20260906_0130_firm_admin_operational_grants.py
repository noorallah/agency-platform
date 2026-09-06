"""A firm administrator can reach its own firm's modules.

Five permission groups shipped with a module, a screen and a seeded gate, and
none of them was added to `_operational_permissions` in `app/identity/
system_seed.py` -- the list `FIRM_ADMIN` and `FIRM_MANAGER` are built from. So
the role whose description is running the firm and every module could not open
Credit Notes, Proforma, E-Invoice, Loyalty or TCS at all.

`SALES_MANAGER` names most of those codes individually, so the screens were
reachable by somebody, which is why nobody noticed.

`seed_system_rbac` is called only by `generate_sample_data.py` and never at
startup, so a database that already exists gets its seeded rows from a
migration -- the same rule the permission codes followed in `20260809_0044` and
the job templates in `20260905_0129`.

The twelve codes are named here rather than read from `ROLE_PERMISSION_CODES`.
A migration is a record of one change on one date; reading the live seed would
make a replay next year do whatever the seed says then, which is a different
change wearing this one's revision id.

Existing sessions keep the claims their token was minted with. Nothing here
bumps `authorization_version`, deliberately -- that would sign every firm
administrator out mid-work to deliver a *widening* of their access. They pick
it up on their next token refresh, or immediately by signing out and in.

`roles`, `permissions` and `role_permissions` live only in the platform schema
(`_PLATFORM_TABLES` in `app/core/tenancy/lifecycle.py`), so this is a no-op in
every firm store.

Revision ID: 20260906_0130
Revises: 20260905_0129
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260906_0130"
down_revision: str | None = "20260905_0129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The roles that run a firm's business.
_ROLES = ("FIRM_ADMIN", "FIRM_MANAGER")

#: What they were missing. Grouped as they are in `PERMISSION_GROUPS`.
_CODES = (
    # credit_note -- reverses tax on a declared supply
    "CREDIT_NOTE_VIEW",
    "CREDIT_NOTE_MANAGE",
    "CREDIT_NOTE_APPROVE",
    # proforma -- states what an approved order will be charged
    "PROFORMA_VIEW",
    "PROFORMA_MANAGE",
    # einvoice -- registers an invoice with the tax authority
    "EINVOICE_VIEW",
    "EINVOICE_MANAGE",
    # loyalty -- the firm's own points scheme
    "LOYALTY_VIEW",
    "LOYALTY_MANAGE",
    "LOYALTY_MANAGE_SETTINGS",
    # tcs -- tax collected at source, 206C(1H)
    "TCS_VIEW",
    "TCS_MANAGE",
)

_TABLE = "role_permissions"


def upgrade() -> None:
    """Grant the five operational groups to the two firm-wide roles."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return

    roles = dict(
        bind.execute(
            sa.text(
                "SELECT code, id FROM roles "
                "WHERE code IN :codes AND is_deleted = false"
            ).bindparams(sa.bindparam("codes", value=list(_ROLES), expanding=True))
        ).all()
    )
    permissions = dict(
        bind.execute(
            sa.text(
                "SELECT code, id FROM permissions "
                "WHERE code IN :codes AND is_deleted = false"
            ).bindparams(sa.bindparam("codes", value=list(_CODES), expanding=True))
        ).all()
    )

    grants = sa.table(
        _TABLE,
        sa.column("id", UUIDType()),
        sa.column("role_id", UUIDType()),
        sa.column("permission_id", UUIDType()),
    )
    for role_code in _ROLES:
        role_id = roles.get(role_code)
        if role_id is None:
            continue
        for permission_code in _CODES:
            permission_id = permissions.get(permission_code)
            if permission_id is None:
                # A code this database has never seeded. Nothing to grant, and
                # inserting a dangling row would break the foreign key.
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
    """Take the five groups back off the two roles.

    Soft-deleted rather than removed, which is how `delete_role` and its
    siblings retire a grant -- and it leaves the row for anybody asking later
    what happened.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET is_deleted = true "
            "WHERE role_id IN (SELECT id FROM roles WHERE code IN :roles) "
            "AND permission_id IN "
            "(SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(
            sa.bindparam("roles", value=list(_ROLES), expanding=True),
            sa.bindparam("codes", value=list(_CODES), expanding=True),
        )
    )
