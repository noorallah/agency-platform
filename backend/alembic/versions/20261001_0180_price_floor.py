"""Warn on, or refuse, a sale below cost or minimum price (backlog 64 row 2).

* ``minimum_selling_price`` on ``products``.
* ``price_floor_settings``, one row per firm: OFF, WARN or BLOCK, and whether
  cost is a floor too. A firm with no row warns.
* ``SALES_PRICE_OVERRIDE`` in the platform store, with every system role's
  grants reconciled -- the shape of ``20260930_0168``.

Idempotent throughout; firm-owned parts run per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261001_0180"
down_revision: str | Sequence[str] | None = "20261001_0179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_minimum_price(inspector: sa.Inspector) -> None:
    """Add the minimum selling price to products, where products live."""
    if not inspector.has_table("products"):
        return
    columns = {column["name"] for column in inspector.get_columns("products")}
    if "minimum_selling_price" not in columns:
        op.add_column(
            "products",
            sa.Column("minimum_selling_price", sa.Numeric(18, 2), nullable=True),
        )


def _create_settings(inspector: sa.Inspector) -> None:
    """Create the per-firm policy table in a firm store that lacks it."""
    if not inspector.has_table("products"):
        return
    if inspector.has_table("price_floor_settings"):
        return
    op.create_table(
        "price_floor_settings",
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
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("enforcement", sa.String(10), server_default="WARN", nullable=False),
        sa.Column(
            "include_cost", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="PK_price_floor_settings"),
    )
    op.create_index(
        "IX_price_floor_settings_firm_id", "price_floor_settings", ["firm_id"]
    )
    op.create_index(
        "UQ_price_floor_settings_firm_active",
        "price_floor_settings",
        ["firm_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
        sqlite_where=sa.text("NOT is_deleted"),
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
_roles = sa.table("roles", sa.column("id", UUIDType()), sa.column("code", sa.String()))
_role_permissions = sa.table(
    "role_permissions",
    sa.column("id", UUIDType()),
    sa.column("role_id", UUIDType()),
    sa.column("permission_id", UUIDType()),
    sa.column("is_deleted", sa.Boolean()),
)


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Insert missing system permissions and reconcile system role grants."""
    if not inspector.has_table("permissions") or not inspector.has_table("roles"):
        return
    bind = op.get_bind()
    existing = {
        code: permission_id
        for permission_id, code in bind.execute(
            sa.select(_permissions.c.id, _permissions.c.code)
        ).all()
    }
    for code in SYSTEM_PERMISSION_CODES:
        if code in existing:
            continue
        existing[code] = uuid4()
        bind.execute(
            _permissions.insert().values(
                id=existing[code],
                code=code,
                name=code.replace("_", " ").title(),
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
    granted = set(
        bind.execute(
            sa.select(
                _role_permissions.c.role_id, _role_permissions.c.permission_id
            ).where(_role_permissions.c.is_deleted.is_(False))
        )
        .tuples()
        .all()
    )
    for role_code, codes in ROLE_PERMISSION_CODES.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in codes:
            permission_id = existing.get(code)
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
    """Add the minimum price, the policy table and the override permission."""
    inspector = sa.inspect(op.get_bind())
    _add_minimum_price(inspector)
    _create_settings(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the policy table and the minimum price.

    The permission stays, as every permission migration here leaves it.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("price_floor_settings"):
        op.drop_table("price_floor_settings")
    if inspector.has_table("products"):
        columns = {column["name"] for column in inspector.get_columns("products")}
        if "minimum_selling_price" in columns:
            op.drop_column("products", "minimum_selling_price")
