"""Rate contracts with suppliers and their releases (PG-9, backlog 86 #2).

* ``rate_contracts`` and ``rate_contract_lines``.
* ``purchase_order_lines.rate_source`` and ``rate_contract_line_id``: where a
  line's price came from and the contract line it draws on. A bare id with an
  index, as other cross-document line references are.
* ``RATE_CONTRACT_VIEW`` and ``RATE_CONTRACT_MANAGE`` seeded and the system
  roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each table,
column and index is created only in a firm store (one holding
``purchase_orders``) that lacks it. No ``firm_id`` foreign key: ``firms``
lives only in the platform store.

Revision ID: 20261005_0310
Revises: 20261005_0309
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261005_0310"
down_revision: str | Sequence[str] | None = "20261005_0309"
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

_TABLES = (
    "rate_contract_lines",
    "rate_contracts",
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


def _create_rate_contracts() -> None:
    """Create the contract header."""
    op.create_table(
        "rate_contracts",
        *_base_columns(),
        sa.Column("contract_number", sa.String(60), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", UUIDType(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_rate_contracts"),
        sa.UniqueConstraint(
            "firm_id",
            "contract_number",
            name="UQ_rate_contracts_firm_contract_number",
        ),
        _fk("rate_contracts", "vendor_id", "vendors", "RESTRICT"),
    )
    op.create_index("IX_rate_contracts_firm_id", "rate_contracts", ["firm_id"])
    op.create_index(
        "IX_rate_contracts_firm_vendor_status",
        "rate_contracts",
        ["firm_id", "vendor_id", "status"],
    )
    op.create_index(
        "IX_rate_contracts_firm_valid_from",
        "rate_contracts",
        ["firm_id", "valid_from"],
    )


def _create_rate_contract_lines() -> None:
    """Create the contract lines."""
    op.create_table(
        "rate_contract_lines",
        *_base_columns(),
        sa.Column("contract_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("uom_id", UUIDType(), nullable=True),
        sa.Column("rate", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "discount_percent",
            sa.Numeric(9, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("contracted_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_rate_contract_lines"),
        sa.UniqueConstraint(
            "contract_id",
            "line_number",
            name="UQ_rate_contract_lines_contract_line",
        ),
        _fk("rate_contract_lines", "contract_id", "rate_contracts", "CASCADE"),
        _fk("rate_contract_lines", "product_id", "products", "RESTRICT"),
        _fk("rate_contract_lines", "uom_id", "uoms", "RESTRICT"),
    )
    op.create_index(
        "IX_rate_contract_lines_firm_id", "rate_contract_lines", ["firm_id"]
    )
    op.create_index(
        "IX_rate_contract_lines_contract", "rate_contract_lines", ["contract_id"]
    )
    op.create_index(
        "IX_rate_contract_lines_firm_product",
        "rate_contract_lines",
        ["firm_id", "product_id"],
    )


def _add_order_line_columns(inspector: sa.Inspector) -> None:
    """Record a purchase order line's rate source and contract line."""
    columns = {c["name"] for c in inspector.get_columns("purchase_order_lines")}
    if "rate_source" not in columns:
        op.add_column(
            "purchase_order_lines",
            sa.Column("rate_source", sa.String(20), nullable=True),
        )
    if "rate_contract_line_id" not in columns:
        op.add_column(
            "purchase_order_lines",
            sa.Column("rate_contract_line_id", UUIDType(), nullable=True),
        )
    indexes = {i["name"] for i in inspector.get_indexes("purchase_order_lines")}
    if "IX_purchase_order_lines_rate_contract_line_id" not in indexes:
        op.create_index(
            "IX_purchase_order_lines_rate_contract_line_id",
            "purchase_order_lines",
            ["rate_contract_line_id"],
        )


def upgrade() -> None:
    """Create the tables and columns where a firm store lacks them; seed codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_orders"):
        if not inspector.has_table("rate_contracts"):
            _create_rate_contracts()
        if not inspector.has_table("rate_contract_lines"):
            _create_rate_contract_lines()
        _add_order_line_columns(inspector)
    _seed_permissions()


def downgrade() -> None:
    """Drop the tables and columns; the permissions stay."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_order_lines"):
        indexes = {i["name"] for i in inspector.get_indexes("purchase_order_lines")}
        if "IX_purchase_order_lines_rate_contract_line_id" in indexes:
            op.drop_index(
                "IX_purchase_order_lines_rate_contract_line_id",
                table_name="purchase_order_lines",
            )
        columns = {c["name"] for c in inspector.get_columns("purchase_order_lines")}
        for column in ("rate_contract_line_id", "rate_source"):
            if column in columns:
                op.drop_column("purchase_order_lines", column)
    for table in _TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
