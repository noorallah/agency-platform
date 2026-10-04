"""Supplier free-goods schemes on an item (PG-11, backlog 86 #25).

* ``supplier_schemes``: buy so many of a product, get so many free -- of the
  same product or another -- from one supplier or from every supplier, for a
  period.
* ``purchase_order_lines.scheme_id`` and ``scheme_name``: the scheme a line's
  free goods came from and its label then. A bare id with an index, as other
  cross-document references are.
* ``SUPPLIER_SCHEME_VIEW`` and ``SUPPLIER_SCHEME_MANAGE`` seeded and the
  system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: the table,
columns and index are created only in a firm store (one holding
``purchase_orders``) that lacks them. No ``firm_id`` foreign key: ``firms``
lives only in the platform store.

Revision ID: 20261005_0312
Revises: 20261005_0311
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261005_0312"
down_revision: str | Sequence[str] | None = "20261005_0311"
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

_INDEX = "IX_purchase_order_lines_scheme_id"


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


def _base_columns() -> list[sa.Column[object]]:
    """Return the columns every ``BaseEntity`` table carries."""
    return [
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
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    """Return a foreign key named for its referring column."""
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"FK_{table}_{column}", ondelete=ondelete
    )


def _create_supplier_schemes() -> None:
    """Create the scheme table."""
    op.create_table(
        "supplier_schemes",
        *_base_columns(),
        sa.Column("vendor_id", UUIDType(), nullable=True),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("buy_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("free_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("free_product_id", UUIDType(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_supplier_schemes"),
        _fk("supplier_schemes", "vendor_id", "vendors", "RESTRICT"),
        _fk("supplier_schemes", "product_id", "products", "RESTRICT"),
        _fk("supplier_schemes", "free_product_id", "products", "RESTRICT"),
    )
    op.create_index("IX_supplier_schemes_firm_id", "supplier_schemes", ["firm_id"])
    op.create_index(
        "IX_supplier_schemes_firm_product",
        "supplier_schemes",
        ["firm_id", "product_id"],
    )
    op.create_index(
        "IX_supplier_schemes_firm_vendor",
        "supplier_schemes",
        ["firm_id", "vendor_id"],
    )


def _add_order_line_columns(inspector: sa.Inspector) -> None:
    """Record the scheme a purchase order line's free goods came from."""
    columns = {c["name"] for c in inspector.get_columns("purchase_order_lines")}
    if "scheme_id" not in columns:
        op.add_column(
            "purchase_order_lines",
            sa.Column("scheme_id", UUIDType(), nullable=True),
        )
    if "scheme_name" not in columns:
        op.add_column(
            "purchase_order_lines",
            sa.Column("scheme_name", sa.String(120), nullable=True),
        )
    indexes = {i["name"] for i in inspector.get_indexes("purchase_order_lines")}
    if _INDEX not in indexes:
        op.create_index(_INDEX, "purchase_order_lines", ["scheme_id"])


def upgrade() -> None:
    """Create the table and columns where a firm store lacks them; seed codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_orders"):
        if not inspector.has_table("supplier_schemes"):
            _create_supplier_schemes()
        _add_order_line_columns(inspector)
    _seed_permissions()


def downgrade() -> None:
    """Drop the table and columns; the permissions stay."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_order_lines"):
        indexes = {i["name"] for i in inspector.get_indexes("purchase_order_lines")}
        if _INDEX in indexes:
            op.drop_index(_INDEX, table_name="purchase_order_lines")
        columns = {c["name"] for c in inspector.get_columns("purchase_order_lines")}
        for column in ("scheme_name", "scheme_id"):
            if column in columns:
                op.drop_column("purchase_order_lines", column)
    if inspector.has_table("supplier_schemes"):
        op.drop_table("supplier_schemes")
