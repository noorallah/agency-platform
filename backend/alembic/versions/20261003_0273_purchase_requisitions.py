"""Purchase requisitions (BUY-7, decision A109).

* ``purchase_requisitions`` and ``purchase_requisition_lines``.
* ``PURCHASE_REQUISITION_CREATE`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0273
Revises: 20261003_0272
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0273"
down_revision: str | Sequence[str] | None = "20261003_0272"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    """Create both tables where a firm store lacks them; seed the permission."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("purchase_requisitions") and inspector.has_table(
        "purchase_orders"
    ):
        op.create_table(
            "purchase_requisitions",
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
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("warehouse_id", UUIDType(), nullable=False),
            sa.Column("requisition_number", sa.String(60), nullable=False),
            sa.Column("requisition_date", sa.Date(), nullable=False),
            sa.Column("needed_by", sa.Date(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("approved_by", UUIDType(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_purchase_requisitions"),
            sa.ForeignKeyConstraint(
                ["branch_id"],
                ["branches.id"],
                name="FK_purchase_requisitions_branch_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["warehouse_id"],
                ["warehouses.id"],
                name="FK_purchase_requisitions_warehouse_id",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "IX_purchase_requisitions_firm_id", "purchase_requisitions", ["firm_id"]
        )
        op.create_index(
            "IX_purchase_requisitions_firm_status",
            "purchase_requisitions",
            ["firm_id", "status"],
        )
        op.create_index(
            "IX_purchase_requisitions_firm_date",
            "purchase_requisitions",
            ["firm_id", "requisition_date"],
        )
    if not inspector.has_table("purchase_requisition_lines") and inspector.has_table(
        "purchase_orders"
    ):
        op.create_table(
            "purchase_requisition_lines",
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
            sa.Column("requisition_id", UUIDType(), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("product_id", UUIDType(), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            sa.Column("vendor_id", UUIDType(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("purchase_order_id", UUIDType(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="PK_purchase_requisition_lines"),
            sa.ForeignKeyConstraint(
                ["requisition_id"],
                ["purchase_requisitions.id"],
                name="FK_purchase_requisition_lines_requisition_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="FK_purchase_requisition_lines_product_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["vendor_id"],
                ["vendors.id"],
                name="FK_purchase_requisition_lines_vendor_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["purchase_order_id"],
                ["purchase_orders.id"],
                name="FK_purchase_requisition_lines_purchase_order_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "IX_purchase_requisition_lines_firm_id",
            "purchase_requisition_lines",
            ["firm_id"],
        )
        op.create_index(
            "IX_purchase_requisition_lines_requisition",
            "purchase_requisition_lines",
            ["requisition_id"],
        )
    _seed_permissions()


def downgrade() -> None:
    """Drop both tables; the permission stays."""
    inspector = sa.inspect(op.get_bind())
    for table in ("purchase_requisition_lines", "purchase_requisitions"):
        if inspector.has_table(table):
            op.drop_table(table)
