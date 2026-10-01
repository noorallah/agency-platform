"""A debit note to a supplier, with no goods going back (backlog 65 row 6).

* ``debit_notes`` and ``debit_note_lines``: a claim against one approved
  supplier bill and lines within it, reversing the input tax at the rate the
  bill charged. Moves no stock -- a purchase return covers goods going back.
* ``DEBIT_NOTE_VIEW``, ``DEBIT_NOTE_MANAGE`` and ``DEBIT_NOTE_APPROVE`` in the
  platform store, with every system role's grants reconciled -- the shape of
  ``20261001_0180``.

Idempotent throughout; firm-owned parts run per store
(``scripts/migrate_all_stores.py``). Cross-schema foreign keys are declared
only where the target exists in the store being migrated.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

revision: str = "20261001_0182"
down_revision: str | Sequence[str] | None = "20261001_0181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "debit_notes"
_LINES = "debit_note_lines"


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
    """Return the columns every entity carries, timestamps defaulted."""
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
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _create_notes(inspector: sa.Inspector) -> None:
    """Create the debit note header table where a firm store lacks it."""
    if inspector.has_table(_TABLE):
        return
    constraints: list[sa.ForeignKeyConstraint] = []
    constraints += _external_fk(
        inspector, "vendors", "vendor_id", "FK_debit_notes_vendor_id"
    )
    constraints += _external_fk(
        inspector, "branches", "branch_id", "FK_debit_notes_branch_id"
    )
    constraints += _external_fk(
        inspector,
        "purchase_invoices",
        "purchase_invoice_id",
        "FK_debit_notes_purchase_invoice_id",
    )
    constraints += _external_fk(
        inspector,
        "journal_entries",
        "journal_entry_id",
        "FK_debit_notes_journal_entry_id",
    )
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("vendor_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("purchase_invoice_id", UUIDType(), nullable=False),
        sa.Column("debit_note_number", sa.String(length=80), nullable=False),
        sa.Column("debit_note_date", sa.Date(), nullable=False),
        sa.Column(
            "reason", sa.String(length=40), nullable=False, server_default="OTHER"
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "taxable_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "total_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_debit_notes"),
        sa.UniqueConstraint(
            "firm_id", "debit_note_number", name="UQ_debit_notes_number"
        ),
        sa.CheckConstraint("total_amount >= 0", name="CK_debit_notes_total"),
        *constraints,
    )
    op.create_index("IX_debit_notes_firm_id", _TABLE, ["firm_id"])
    op.create_index("IX_debit_notes_firm_vendor", _TABLE, ["firm_id", "vendor_id"])
    op.create_index(
        "IX_debit_notes_firm_invoice", _TABLE, ["firm_id", "purchase_invoice_id"]
    )
    op.create_index("IX_debit_notes_firm_status", _TABLE, ["firm_id", "status"])


def _create_lines(inspector: sa.Inspector) -> None:
    """Create the debit note line table where a firm store lacks it."""
    if inspector.has_table(_LINES):
        return
    constraints: list[sa.ForeignKeyConstraint] = [
        sa.ForeignKeyConstraint(
            ["debit_note_id"],
            [f"{_TABLE}.id"],
            name="FK_debit_note_lines_debit_note_id",
            ondelete="CASCADE",
        )
    ]
    constraints += _external_fk(
        inspector,
        "purchase_invoice_lines",
        "purchase_invoice_line_id",
        "FK_debit_note_lines_purchase_invoice_line_id",
    )
    constraints += _external_fk(
        inspector, "products", "product_id", "FK_debit_note_lines_product_id"
    )
    op.create_table(
        _LINES,
        *_base_columns(),
        sa.Column("debit_note_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("purchase_invoice_line_id", UUIDType(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="PK_debit_note_lines"),
        sa.CheckConstraint("taxable_amount >= 0", name="CK_debit_note_lines_taxable"),
        sa.CheckConstraint("quantity >= 0", name="CK_debit_note_lines_quantity"),
        *constraints,
    )
    op.create_index("IX_debit_note_lines_firm_id", _LINES, ["firm_id"])
    op.create_index(
        "IX_debit_note_lines_note", _LINES, ["debit_note_id", "line_number"]
    )
    op.create_index(
        "IX_debit_note_lines_source", _LINES, ["firm_id", "purchase_invoice_line_id"]
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
    """Create the debit note tables and seed their permission codes."""
    inspector = sa.inspect(op.get_bind())
    # A firm store is one that holds the bills a note claims against.
    if inspector.has_table("purchase_invoices"):
        _create_notes(inspector)
        _create_lines(sa.inspect(op.get_bind()))
    _seed_permissions(inspector)


def downgrade() -> None:
    """Drop the tables; the permission codes stay, as every such migration's do."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_LINES):
        op.drop_table(_LINES)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
