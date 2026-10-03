"""Received goods wait for an inspection (BUY-9, decision A100).

* ``inspection_required`` on ``products`` and ``product_categories``.
* The inspection columns on ``goods_receipt_lines``: status, the hold
  movement, held / passed / rejected quantities, the rejected action, who and
  when, remarks.
* ``PURCHASE_INSPECT`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0266
Revises: 20261003_0265
Create Date: 2026-10-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261003_0266"
down_revision: str | Sequence[str] | None = "20261003_0265"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLAG = "inspection_required"

_LINE_COLUMNS = (
    ("inspection_status", lambda: sa.String(20)),
    ("inspection_transaction_id", lambda: UUIDType()),
    ("inspection_quantity", lambda: sa.Numeric(18, 4)),
    ("inspection_passed_quantity", lambda: sa.Numeric(18, 4)),
    ("inspection_rejected_quantity", lambda: sa.Numeric(18, 4)),
    ("inspection_rejected_action", lambda: sa.String(20)),
    ("inspected_at", lambda: sa.DateTime(timezone=True)),
    ("inspected_by", lambda: UUIDType()),
    ("inspection_remarks", lambda: sa.Text()),
)

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
    """Add the flags and the line columns, and seed the permission."""
    inspector = sa.inspect(op.get_bind())
    for table in ("products", "product_categories"):
        if not inspector.has_table(table):
            continue
        if _FLAG not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(
                table,
                sa.Column(
                    _FLAG, sa.Boolean(), nullable=False, server_default=sa.false()
                ),
            )
    if inspector.has_table("goods_receipt_lines"):
        have = {c["name"] for c in inspector.get_columns("goods_receipt_lines")}
        for name, kind in _LINE_COLUMNS:
            if name not in have:
                op.add_column("goods_receipt_lines", sa.Column(name, kind()))
        foreign_keys = {
            fk["name"] for fk in inspector.get_foreign_keys("goods_receipt_lines")
        }
        name = "FK_goods_receipt_lines_inspection_transaction_id"
        if name not in foreign_keys and inspector.has_table("inventory_transactions"):
            op.create_foreign_key(
                name,
                "goods_receipt_lines",
                "inventory_transactions",
                ["inspection_transaction_id"],
                ["id"],
                ondelete="SET NULL",
            )
    _seed_permissions()


def downgrade() -> None:
    """Drop the columns; the permission stays, as system codes do."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("goods_receipt_lines"):
        foreign_keys = {
            fk["name"] for fk in inspector.get_foreign_keys("goods_receipt_lines")
        }
        name = "FK_goods_receipt_lines_inspection_transaction_id"
        if name in foreign_keys:
            op.drop_constraint(name, "goods_receipt_lines", type_="foreignkey")
        have = {c["name"] for c in inspector.get_columns("goods_receipt_lines")}
        for column, _ in _LINE_COLUMNS:
            if column in have:
                op.drop_column("goods_receipt_lines", column)
    for table in ("products", "product_categories"):
        if inspector.has_table(table) and _FLAG in {
            c["name"] for c in inspector.get_columns(table)
        }:
            op.drop_column(table, _FLAG)
