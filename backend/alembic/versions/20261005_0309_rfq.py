"""Requests for quotation and supplier quotations (PG-8, backlog 86 #1).

* ``rfqs``, ``rfq_lines``, ``rfq_suppliers``, ``supplier_quotations`` and
  ``supplier_quotation_lines``.
* ``RFQ_VIEW`` and ``RFQ_MANAGE`` seeded and the system roles reconciled.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each table is
created only in a firm store (one holding ``purchase_orders``) that lacks it.
No ``firm_id`` foreign key: ``firms`` lives only in the platform store.

Revision ID: 20261005_0309
Revises: 20261005_0308
Create Date: 2026-10-05

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261005_0309"
down_revision: str | Sequence[str] | None = "20261005_0308"
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
    "supplier_quotation_lines",
    "supplier_quotations",
    "rfq_suppliers",
    "rfq_lines",
    "rfqs",
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


def _create_rfqs() -> None:
    """Create the RFQ header."""
    op.create_table(
        "rfqs",
        *_base_columns(),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("warehouse_id", UUIDType(), nullable=False),
        sa.Column("rfq_number", sa.String(60), nullable=False),
        sa.Column("rfq_date", sa.Date(), nullable=False),
        sa.Column("required_by", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_requisition_id", UUIDType(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by", UUIDType(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_rfqs"),
        sa.UniqueConstraint("firm_id", "rfq_number", name="UQ_rfqs_firm_rfq_number"),
        _fk("rfqs", "branch_id", "branches", "RESTRICT"),
        _fk("rfqs", "warehouse_id", "warehouses", "RESTRICT"),
        _fk("rfqs", "source_requisition_id", "purchase_requisitions", "SET NULL"),
    )
    op.create_index("IX_rfqs_firm_id", "rfqs", ["firm_id"])
    op.create_index("IX_rfqs_firm_status", "rfqs", ["firm_id", "status"])
    op.create_index("IX_rfqs_firm_date", "rfqs", ["firm_id", "rfq_date"])
    op.create_index("IX_rfqs_source_requisition_id", "rfqs", ["source_requisition_id"])


def _create_rfq_lines() -> None:
    """Create the RFQ lines."""
    op.create_table(
        "rfq_lines",
        *_base_columns(),
        sa.Column("rfq_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("uom_id", UUIDType(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("selected_quotation_line_id", UUIDType(), nullable=True),
        sa.Column("selection_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_rfq_lines"),
        sa.UniqueConstraint("rfq_id", "line_number", name="UQ_rfq_lines_rfq_line"),
        _fk("rfq_lines", "rfq_id", "rfqs", "CASCADE"),
        _fk("rfq_lines", "product_id", "products", "RESTRICT"),
        _fk("rfq_lines", "uom_id", "uoms", "RESTRICT"),
    )
    op.create_index("IX_rfq_lines_firm_id", "rfq_lines", ["firm_id"])
    op.create_index("IX_rfq_lines_rfq", "rfq_lines", ["rfq_id"])


def _create_rfq_suppliers() -> None:
    """Create the invited suppliers."""
    op.create_table(
        "rfq_suppliers",
        *_base_columns(),
        sa.Column("rfq_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("purchase_order_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_rfq_suppliers"),
        sa.UniqueConstraint("rfq_id", "vendor_id", name="UQ_rfq_suppliers_rfq_vendor"),
        _fk("rfq_suppliers", "rfq_id", "rfqs", "CASCADE"),
        _fk("rfq_suppliers", "vendor_id", "vendors", "RESTRICT"),
        _fk("rfq_suppliers", "purchase_order_id", "purchase_orders", "SET NULL"),
    )
    op.create_index("IX_rfq_suppliers_firm_id", "rfq_suppliers", ["firm_id"])
    op.create_index("IX_rfq_suppliers_rfq", "rfq_suppliers", ["rfq_id"])


def _create_supplier_quotations() -> None:
    """Create the supplier quotations."""
    op.create_table(
        "supplier_quotations",
        *_base_columns(),
        sa.Column("rfq_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("quote_ref", sa.String(80), nullable=True),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_supplier_quotations"),
        sa.UniqueConstraint(
            "rfq_id", "vendor_id", name="UQ_supplier_quotations_rfq_vendor"
        ),
        _fk("supplier_quotations", "rfq_id", "rfqs", "CASCADE"),
        _fk("supplier_quotations", "vendor_id", "vendors", "RESTRICT"),
    )
    op.create_index(
        "IX_supplier_quotations_firm_id", "supplier_quotations", ["firm_id"]
    )
    op.create_index("IX_supplier_quotations_rfq", "supplier_quotations", ["rfq_id"])


def _create_supplier_quotation_lines() -> None:
    """Create the quoted rates."""
    op.create_table(
        "supplier_quotation_lines",
        *_base_columns(),
        sa.Column("quotation_id", UUIDType(), nullable=False),
        sa.Column("rfq_line_id", UUIDType(), nullable=False),
        sa.Column("rate", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "discount_percent",
            sa.Numeric(9, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_supplier_quotation_lines"),
        sa.UniqueConstraint(
            "quotation_id",
            "rfq_line_id",
            name="UQ_supplier_quotation_lines_quotation_rfq_line",
        ),
        _fk(
            "supplier_quotation_lines", "quotation_id", "supplier_quotations", "CASCADE"
        ),
        _fk("supplier_quotation_lines", "rfq_line_id", "rfq_lines", "CASCADE"),
    )
    op.create_index(
        "IX_supplier_quotation_lines_firm_id", "supplier_quotation_lines", ["firm_id"]
    )
    op.create_index(
        "IX_supplier_quotation_lines_quotation",
        "supplier_quotation_lines",
        ["quotation_id"],
    )


def upgrade() -> None:
    """Create the five tables where a firm store lacks them; seed the codes."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_orders"):
        for table, create in (
            ("rfqs", _create_rfqs),
            ("rfq_lines", _create_rfq_lines),
            ("rfq_suppliers", _create_rfq_suppliers),
            ("supplier_quotations", _create_supplier_quotations),
            ("supplier_quotation_lines", _create_supplier_quotation_lines),
        ):
            if not inspector.has_table(table):
                create()
    _seed_permissions()


def downgrade() -> None:
    """Drop the five tables; the permissions stay."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
