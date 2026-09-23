"""A bill's line keeps the tax components it was charged (D-CMP-20).

A purchase invoice line kept one ``tax_amount`` and nothing about how it was
arrived at. GSTR-3B claims input credit under IGST separately from CGST and
SGST, and the ledger has to carry each component to its own input-tax
account; neither can be derived from one total. The breakup was computed by
the rule engine at save time and survived only in ``tax_rule_execution_logs``,
which the retention job prunes -- and tax rules are effective-dated, so
re-deriving it later can disagree with what the supplier charged. So it is
stored on the document that charged it, mirroring ``sales_invoice_line_taxes``
(``20260822_0096``) exactly.

Idempotent: the table is created only where it is missing. Firm-owned, so run
it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0155
Revises: 20260923_0154
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0155"
down_revision: str | Sequence[str] | None = "20260923_0154"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_invoice_line_taxes"


def upgrade() -> None:
    """Add the per-line tax breakup to purchase invoices."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm schemas are partly built by `Base.metadata.create_all` from the
    # sample-data and tenancy-reset scripts, so an object can already exist
    # even where `alembic_version` reads older.
    if not inspector.has_table("purchase_invoice_lines"):
        return
    if inspector.has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("purchase_invoice_line_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        # No foreign key: this says which catalogue row produced the line at
        # the time, and the catalogue moves on. A RESTRICT would stop a firm
        # retiring a component and a CASCADE would erase the evidence; the
        # code, label and percentage beside it are the record.
        sa.Column("tax_component_id", sa.Uuid(), nullable=True),
        sa.Column("component_code", sa.String(length=40), nullable=False),
        sa.Column("component_label", sa.String(length=120), nullable=False),
        sa.Column("percentage", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("base_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "included_in_price",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "recoverable", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        # `BaseEntity` leaves both to the database -- no Python default -- so
        # the column has to carry the server default or the first insert fails
        # on a NOT NULL it cannot satisfy.
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # `BaseEntity` maps this beside `deleted_at`; leaving it out builds a
        # table the ORM cannot insert into, which SQLite-backed unit tests
        # never see because they build from the metadata rather than from here.
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["purchase_invoice_line_id"],
            ["purchase_invoice_lines.id"],
            name="FK_purchase_invoice_line_taxes_purchase_invoice_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "IX_purchase_invoice_line_taxes_line", _TABLE, ["purchase_invoice_line_id"]
    )
    op.create_index("IX_purchase_invoice_line_taxes_firm", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the breakup table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_index("IX_purchase_invoice_line_taxes_firm", table_name=_TABLE)
        op.drop_index("IX_purchase_invoice_line_taxes_line", table_name=_TABLE)
        op.drop_table(_TABLE)
