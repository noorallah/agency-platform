"""A salesman earns on what is collected, at a rate the firm dates.

`COMMISSION` has been a declared business feature with no code behind it since
the framework was written -- one of the seven marked `is_implemented = false`
by `20260810_0059`. This is the first table behind it.

The rate is flat, per salesman, and effective-dated, with one firm-wide default
for anybody who has no rule of their own (`salesman_id IS NULL`). Dating it is
what lets a rate change without rewriting what was already earned, the same
reason `uom_conversion_rules` and `tax_profiles` are dated.

`salesman_id` references `users`, which exists **only in the platform schema**,
so the constraint is declared only where the target is actually present -- the
`_external_fk` shape from `20260809_0042`. `firm_id` carries no foreign key at
all, because `firms` is platform-only and no firm-owned table in `firm_shared`
references it.

The two permission codes go in here as well. A code a router enforces and the
catalogue does not define has no permission row, so it cannot be attached to
any role and the endpoint quietly becomes platform-admin-only -- the state
twelve codes were in until `20260809_0044`, whose reconciliation shape this
copies.

Revision ID: 20260823_0102
Revises: 20260823_0101
Create Date: 2026-08-23
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260823_0102"
down_revision: str | Sequence[str] | None = "20260823_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "commission_rules"

#: The codes `app/commission/api/router.py` enforces.
_NEW_CODES = ("COMMISSION_VIEW", "COMMISSION_MANAGE")

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


def _create_table(inspector: sa.Inspector) -> None:
    """Create the rule table where it is not already present.

    Firm schemas are partly built by ``Base.metadata.create_all`` from the
    sample-data and tenancy-reset scripts, so the table can exist even where
    ``alembic_version`` reads older.
    """
    if inspector.has_table(_TABLE):
        return
    salesman_fk: list[sa.ForeignKeyConstraint] = []
    if inspector.has_table("users"):
        salesman_fk.append(
            sa.ForeignKeyConstraint(
                ["salesman_id"],
                ["users.id"],
                name="FK_commission_rules_salesman_id",
                ondelete="RESTRICT",
            )
        )
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("salesman_id", sa.Uuid(), nullable=True),
        sa.Column(
            "percentage",
            sa.Numeric(precision=9, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="ACTIVE"
        ),
        sa.CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="CK_commission_rules_percentage_range",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="CK_commission_rules_effective_window",
        ),
        *salesman_fk,
    )
    op.create_index("IX_commission_rules_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_commission_rules_firm_salesman", _TABLE, ["firm_id", "salesman_id"]
    )
    op.create_index("IX_commission_rules_firm_status", _TABLE, ["firm_id", "status"])


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert the two codes and grant them where the seed says they belong."""
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code).where(
                _permissions.c.code.in_(_NEW_CODES)
            )
        ).all()
    }
    for code in _NEW_CODES:
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
        for code in _NEW_CODES:
            if code not in permission_codes:
                continue
            permission_id = existing[code]
            if (role_id, permission_id) in granted:
                continue
            bind.execute(
                _role_permissions.insert().values(
                    id=uuid4(),
                    role_id=role_id,
                    permission_id=permission_id,
                    is_deleted=False,
                )
            )


def upgrade() -> None:
    """Create the commission rule table and seed its permission codes."""
    inspector = sa.inspect(op.get_bind())
    _create_table(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the rule table and leave the permission codes in place.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than two extra catalogue rows --
    the reasoning `20260809_0044` recorded and the same choice.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
