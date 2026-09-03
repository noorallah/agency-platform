"""A credit note that states its lines and reverses the tax it charged.

A credit note already existed as a row in `customer_receivable_transactions`.
It reduced what the customer owed and booked the whole figure to sales
returns, reversing **no output tax at all** -- so a firm agreeing a rate
difference after invoicing credited the customer the gross amount and went on
declaring tax on a price nobody paid.

`credit_notes` and `credit_note_lines` are the document that closes it. Each
line names the invoice line it credits, which is the only thing that knows the
rate the tax was charged at.

Deliberately **not** a sales return: a return is goods coming back, and stock
moves with them. This moves none.

The three permission codes go in here too. A code a router enforces and the
catalogue does not define has no permission row, so the endpoint quietly
becomes platform-admin-only. `CREDIT_NOTE_APPROVE` is not granted to
`SALES_MANAGER`: approving reverses tax the firm has declared.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0118
Revises: 20260903_0117
Create Date: 2026-09-03

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES

revision: str = "20260903_0118"
down_revision: str | Sequence[str] | None = "20260903_0117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "credit_notes"
_LINES = "credit_note_lines"
_NEW_CODES = ("CREDIT_NOTE_VIEW", "CREDIT_NOTE_MANAGE", "CREDIT_NOTE_APPROVE")

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
    """Create the credit note tables where a firm store lacks them."""
    if not inspector.has_table("sales_invoices"):
        return
    if not inspector.has_table(_TABLE):
        constraints: list[sa.ForeignKeyConstraint] = []
        constraints += _external_fk(
            inspector, "customers", "customer_id", "FK_credit_notes_customer_id"
        )
        constraints += _external_fk(
            inspector, "branches", "branch_id", "FK_credit_notes_branch_id"
        )
        constraints += _external_fk(
            inspector,
            "sales_invoices",
            "sales_invoice_id",
            "FK_credit_notes_sales_invoice_id",
        )
        constraints += _external_fk(
            inspector,
            "journal_entries",
            "journal_entry_id",
            "FK_credit_notes_journal_entry_id",
        )
        op.create_table(
            _TABLE,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("customer_id", UUIDType(), nullable=False),
            sa.Column("branch_id", UUIDType(), nullable=False),
            sa.Column("sales_invoice_id", UUIDType(), nullable=False),
            sa.Column("credit_note_number", sa.String(length=80), nullable=False),
            sa.Column("credit_note_date", sa.Date(), nullable=False),
            sa.Column(
                "reason", sa.String(length=40), nullable=False, server_default="OTHER"
            ),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="DRAFT"
            ),
            sa.Column(
                "taxable_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column(
                "tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column(
                "total_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
            ),
            sa.Column("salesman_id", UUIDType(), nullable=True),
            sa.Column("territory_id", UUIDType(), nullable=True),
            sa.Column("reference_number", sa.String(length=120), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("journal_entry_id", UUIDType(), nullable=True),
            sa.Column("receivable_transaction_id", UUIDType(), nullable=True),
            sa.UniqueConstraint(
                "firm_id", "credit_note_number", name="UQ_credit_notes_number"
            ),
            sa.CheckConstraint("total_amount >= 0", name="CK_credit_notes_total"),
            *constraints,
        )
        op.create_index("IX_credit_notes_firm_id", _TABLE, ["firm_id"])
        op.create_index(
            "IX_credit_notes_firm_customer", _TABLE, ["firm_id", "customer_id"]
        )
        op.create_index(
            "IX_credit_notes_firm_invoice", _TABLE, ["firm_id", "sales_invoice_id"]
        )
        op.create_index("IX_credit_notes_firm_status", _TABLE, ["firm_id", "status"])

    if inspector.has_table(_LINES):
        return
    line_constraints: list[sa.ForeignKeyConstraint] = [
        sa.ForeignKeyConstraint(
            ["credit_note_id"],
            [f"{_TABLE}.id"],
            name="FK_credit_note_lines_credit_note_id",
            ondelete="CASCADE",
        )
    ]
    line_constraints += _external_fk(
        inspector,
        "sales_invoice_lines",
        "sales_invoice_line_id",
        "FK_credit_note_lines_sales_invoice_line_id",
    )
    line_constraints += _external_fk(
        inspector, "products", "product_id", "FK_credit_note_lines_product_id"
    )
    op.create_table(
        _LINES,
        *_base_columns(),
        sa.Column("credit_note_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("sales_invoice_line_id", UUIDType(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "taxable_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "total_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_profile_id", UUIDType(), nullable=True),
        sa.Column(
            "tax_rate_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.CheckConstraint("taxable_amount >= 0", name="CK_credit_note_lines_taxable"),
        sa.CheckConstraint("quantity >= 0", name="CK_credit_note_lines_quantity"),
        *line_constraints,
    )
    op.create_index("IX_credit_note_lines_firm_id", _LINES, ["firm_id"])
    op.create_index(
        "IX_credit_note_lines_note", _LINES, ["credit_note_id", "line_number"]
    )
    op.create_index(
        "IX_credit_note_lines_source", _LINES, ["firm_id", "sales_invoice_line_id"]
    )


def _seed_permissions(inspector: sa.Inspector) -> None:
    """Define the three codes and grant them where the seed says."""
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
    """Create the credit note tables and seed their permission codes."""
    inspector = sa.inspect(op.get_bind())
    _create_tables(inspector)
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the tables and leave the permission codes in place.

    Removing the codes would strip grants an administrator may since have made
    to custom roles, which is more damaging than three extra catalogue rows.
    """
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_LINES):
        op.drop_table(_LINES)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
