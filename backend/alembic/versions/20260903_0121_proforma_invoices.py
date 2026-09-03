"""A statement of what an order will be charged, issued before the bill.

A buyer needs a document before the goods move -- to open a letter of credit,
to get a payment approved, to clear customs. A quotation is an offer and a tax
invoice is a demand; the thing in between had no home here.

Two tables, and **no journal or receivable column on either**. A proforma
raises no revenue, no output tax, no receivable and no stock movement, and the
absence of anywhere to record that it did is the design rather than an
oversight -- adding either column later is the first step towards a document
that looks like a bill to the books as well as to the customer.

The lines are a **snapshot** of the sales order's, not a reference to it. The
order can be edited afterwards, withdrawing its own approval as it goes, and a
document the customer is arranging payment against must not change underneath
them.

The two permission codes go in here as well. A code a router enforces and the
catalogue does not define has no permission row, so the endpoint quietly
becomes platform-admin-only.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0121
Revises: 20260903_0120
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0121"
down_revision: str | Sequence[str] | None = "20260903_0120"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "proforma_invoices"
_LINES = "proforma_invoice_lines"
_NEW_CODES = ("PROFORMA_VIEW", "PROFORMA_MANAGE")

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


def _display_name(code: str) -> str:
    """Render a permission code as a readable name."""
    return code.replace("_", " ").title()


def _external_fk(
    inspector: sa.Inspector, table: str, column: str, name: str
) -> list[sa.ForeignKeyConstraint]:
    """Declare a foreign key only where its target actually exists."""
    if not inspector.has_table(table):
        return []
    return [
        sa.ForeignKeyConstraint(
            [column], [f"{table}.id"], name=name, ondelete="RESTRICT"
        )
    ]


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP` because a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails -- `20260903_0114` had to repair every store for
    exactly that.
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _create_tables(inspector: sa.Inspector) -> None:
    """Create the proforma tables where a firm store lacks them."""
    if not inspector.has_table("sales_orders"):
        return
    if not inspector.has_table(_TABLE):
        constraints: list[sa.ForeignKeyConstraint] = []
        constraints += _external_fk(
            inspector, "customers", "customer_id", "FK_proforma_invoices_customer_id"
        )
        constraints += _external_fk(
            inspector, "branches", "branch_id", "FK_proforma_invoices_branch_id"
        )
        constraints += _external_fk(
            inspector,
            "sales_orders",
            "sales_order_id",
            "FK_proforma_invoices_sales_order_id",
        )
        op.create_table(
            _TABLE,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("customer_id", UUIDType(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("sales_order_id", UUIDType(), nullable=False),
            sa.Column("proforma_number", sa.String(length=60), nullable=False),
            sa.Column("proforma_date", sa.Date(), nullable=False),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="DRAFT"
            ),
            sa.Column("customer_reference", sa.String(length=80), nullable=True),
            sa.Column("payment_terms", sa.String(length=200), nullable=True),
            sa.Column("delivery_terms", sa.String(length=200), nullable=True),
            sa.Column("currency_code", sa.String(length=10), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column(
                "line_discount_total",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "bill_discount_amount",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column(
                "tax_total", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column(
                "grand_total", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_reason", sa.Text(), nullable=True),
            sa.Column("supersedes_id", UUIDType(), nullable=True),
            sa.UniqueConstraint(
                "firm_id", "proforma_number", name="UQ_proforma_invoices_number"
            ),
            sa.CheckConstraint("grand_total >= 0", name="CK_proforma_invoices_total"),
            sa.ForeignKeyConstraint(
                ["supersedes_id"],
                [f"{_TABLE}.id"],
                name="FK_proforma_invoices_supersedes_id",
                ondelete="RESTRICT",
            ),
            *constraints,
        )
        op.create_index("IX_proforma_invoices_firm_id", _TABLE, ["firm_id"])
        op.create_index(
            "IX_proforma_invoices_firm_customer", _TABLE, ["firm_id", "customer_id"]
        )
        op.create_index(
            "IX_proforma_invoices_firm_order", _TABLE, ["firm_id", "sales_order_id"]
        )
        op.create_index(
            "IX_proforma_invoices_firm_status", _TABLE, ["firm_id", "status"]
        )

    if inspector.has_table(_LINES):
        return
    line_constraints: list[sa.ForeignKeyConstraint] = [
        sa.ForeignKeyConstraint(
            ["proforma_invoice_id"],
            [f"{_TABLE}.id"],
            name="FK_proforma_invoice_lines_proforma_invoice_id",
            ondelete="CASCADE",
        )
    ]
    line_constraints += _external_fk(
        inspector, "products", "product_id", "FK_proforma_invoice_lines_product_id"
    )
    op.create_table(
        _LINES,
        *_base_columns(),
        sa.Column("proforma_invoice_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        # A bare UUID with no foreign key, the way every downstream document
        # in this repo records its source: the order's lines are reconciled on
        # their line number and can be re-inserted.
        sa.Column("source_sales_order_line_id", UUIDType(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "bill_discount_amount",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "proforma_invoice_id",
            "line_number",
            name="UQ_proforma_invoice_lines_number",
        ),
        sa.CheckConstraint("quantity >= 0", name="CK_proforma_invoice_lines_quantity"),
        *line_constraints,
    )
    op.create_index("IX_proforma_invoice_lines_firm", _LINES, ["firm_id"])
    op.create_index(
        "IX_proforma_invoice_lines_document", _LINES, ["proforma_invoice_id"]
    )


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the two codes and grant them where the seed says."""
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
    """Create the proforma tables and seed their permission codes."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the tables and leave the permission codes in place.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than two extra catalogue rows.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_LINES):
        op.drop_table(_LINES)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
