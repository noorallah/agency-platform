"""A credit note records the tax it gives back, component by component.

The mirror of `20260822_0096`, and missing for the same reason it was: a sales
return line kept one ``tax_amount`` and nothing about how it was arrived at, so
the printed credit note could state a total and no breakup -- while a GST
credit note has to name each component it reverses, exactly as the invoice
names each one it charged.

Re-asking the rule engine at print time is not the answer and is why the
invoice's table exists: rules are effective-dated, so the engine can answer
differently from what was actually credited. The only honest record is what was
credited, kept on the document that credited it.

``tax_component_id`` carries no foreign key, for the reason the invoice's does
not: it says which catalogue row produced the line at the time, and the
catalogue moves on. A RESTRICT would stop a firm retiring a component and a
CASCADE would erase the evidence.

Revision ID: 20260823_0101
Revises: 20260823_0100
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0101"
down_revision: str | Sequence[str] | None = "20260823_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sales_return_line_taxes"


def upgrade() -> None:
    """Add the per-line tax breakup a credit note has to state."""
    inspector = sa.inspect(op.get_bind())
    # Firm schemas are partly built by `Base.metadata.create_all` from the
    # sample-data and tenancy-reset scripts, so the table can exist even where
    # `alembic_version` reads older; and it exists in no platform schema.
    if not inspector.has_table("sales_return_lines"):
        return
    if inspector.has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sales_return_line_id", sa.Uuid(), nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tax_component_id", sa.Uuid(), nullable=True),
        sa.Column("component_code", sa.String(length=40), nullable=False),
        sa.Column("component_label", sa.String(length=120), nullable=False),
        sa.Column(
            "percentage",
            sa.Numeric(precision=9, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "base_amount",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "included_in_price", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("recoverable", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(
            ["sales_return_line_id"],
            ["sales_return_lines.id"],
            name="FK_sales_return_line_taxes_sales_return_line_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("IX_sales_return_line_taxes_line", _TABLE, ["sales_return_line_id"])
    op.create_index("IX_sales_return_line_taxes_firm", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the breakup."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
