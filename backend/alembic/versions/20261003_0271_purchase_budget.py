"""Purchase budgets (BUY-14, decision A106).

* ``purchase_budgets``: month, optional branch and category, amount.
* ``purchase_workflow_settings.budget_policy`` -- ``WARN`` (default) or
  ``NEEDS_APPROVAL``.
* ``PURCHASE_APPROVE_OVER_BUDGET`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0271
Revises: 20261003_0270
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0271"
down_revision: str | Sequence[str] | None = "20261003_0270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_budgets"

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


def _seed_permissions() -> None:
    """Insert missing system permissions and reconcile system role grants."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Identity tables live only in the platform schema.
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return

    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
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
        for permission_code in permission_codes:
            permission_id = existing.get(permission_code)
            if permission_id is None or (role_id, permission_id) in granted:
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
    """Create the table and the policy where missing; seed the permission."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_workflow_settings") and "budget_policy" not in {
        c["name"] for c in inspector.get_columns("purchase_workflow_settings")
    }:
        op.add_column(
            "purchase_workflow_settings",
            sa.Column(
                "budget_policy", sa.String(20), nullable=False, server_default="WARN"
            ),
        )
    if not inspector.has_table(_TABLE) and inspector.has_table("purchase_orders"):
        op.create_table(
            _TABLE,
            sa.Column("id", UUIDType(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", UUIDType(), nullable=True),
            sa.Column("created_by", UUIDType(), nullable=True),
            sa.Column("updated_by", UUIDType(), nullable=True),
            sa.Column(
                "version", sa.Integer(), server_default=sa.text("0"), nullable=False
            ),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("budget_month", sa.Date(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=True),
            sa.Column("product_category_id", UUIDType(), nullable=True),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.PrimaryKeyConstraint("id", name="PK_purchase_budgets"),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="FK_purchase_budgets_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["product_category_id"],
                ["product_categories.id"],
                name="FK_purchase_budgets_product_category_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index("IX_purchase_budgets_firm_id", _TABLE, ["firm_id"])
        op.create_index(
            "IX_purchase_budgets_firm_month", _TABLE, ["firm_id", "budget_month"]
        )
    _seed_permissions()


def downgrade() -> None:
    """Drop the table and the policy; the permission stays."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if inspector.has_table("purchase_workflow_settings") and "budget_policy" in {
        c["name"] for c in inspector.get_columns("purchase_workflow_settings")
    }:
        op.drop_column("purchase_workflow_settings", "budget_policy")
