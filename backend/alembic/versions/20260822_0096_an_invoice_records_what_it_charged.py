"""An invoice records the tax it charged, and where it was supplied.

A sales invoice line kept one ``tax_amount`` and nothing about how it was
arrived at: not the components the customer was charged, and not even the tax
profile that produced them -- ``tax_profile_id`` was written from the request
body, so a client that named none left it NULL.

A printed tax invoice has to state each component and its rate. That breakup
was computed at save time and survived only in ``tax_rule_execution_logs``,
which the retention job prunes; and because tax rules are effective-dated,
re-deriving it at print time can disagree with what the customer was billed.
So it is stored on the document that charged it.

``place_of_supply`` joins it on the header for the same reason. It decides
CGST + SGST against IGST and is copied from the customer's billing address when
the invoice is raised, rather than read through the customer at print time --
a customer who moves must not change the tax treatment of an invoice already
issued.

Revision ID: 20260822_0096
Revises: 20260821_0095
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0096"
down_revision: str | Sequence[str] | None = "20260821_0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_invoice_line_taxes"


def upgrade() -> None:
    """Add the per-line tax breakup and the invoice's place of supply."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm schemas are partly built by `Base.metadata.create_all` from the
    # sample-data and tenancy-reset scripts, so an object can already exist
    # even where `alembic_version` reads older.
    if not inspector.has_table("sales_invoices"):
        return

    columns = {column["name"] for column in inspector.get_columns("sales_invoices")}
    if "place_of_supply" not in columns:
        op.add_column(
            "sales_invoices",
            sa.Column("place_of_supply", sa.String(length=120), nullable=True),
        )

    if inspector.has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sales_invoice_line_id", sa.Uuid(), nullable=False),
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
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
            ["sales_invoice_line_id"],
            ["sales_invoice_lines.id"],
            name="FK_sales_invoice_line_taxes_sales_invoice_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "IX_sales_invoice_line_taxes_line", _TABLE, ["sales_invoice_line_id"]
    )
    op.create_index("IX_sales_invoice_line_taxes_firm", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the breakup table and the place of supply."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_index("IX_sales_invoice_line_taxes_firm", table_name=_TABLE)
        op.drop_index("IX_sales_invoice_line_taxes_line", table_name=_TABLE)
        op.drop_table(_TABLE)
    if inspector.has_table("sales_invoices"):
        columns = {column["name"] for column in inspector.get_columns("sales_invoices")}
        if "place_of_supply" in columns:
            op.drop_column("sales_invoices", "place_of_supply")
