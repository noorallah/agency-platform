"""A firm owns how its documents print.

The statutory spine of a tax invoice is fixed -- both parties' GSTINs, the HSN
per line, the rate and amount per tax component, the summary and the total in
words are what make it a tax invoice, and a firm that could switch them off
could configure itself out of compliance. Everything around that spine is the
firm's: its letterhead wording, its bank block, its terms and declaration,
which optional columns it wants, and what paper it prints on.

One row per firm per document type, so the same table serves a delivery note
or a purchase order when either learns to print. A firm with no row still
prints a correct bill on the platform defaults, which is why nothing is seeded
here.

Revision ID: 20260822_0097
Revises: 20260822_0096
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0097"
down_revision: str | Sequence[str] | None = "20260822_0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "document_print_templates"


def upgrade() -> None:
    """Create the per-firm print template table."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column(
            "title_text",
            sa.String(length=60),
            nullable=False,
            server_default="TAX INVOICE",
        ),
        sa.Column(
            "accent_color",
            sa.String(length=9),
            nullable=False,
            server_default="#0B3D6B",
        ),
        sa.Column("header_note", sa.Text(), nullable=True),
        sa.Column(
            "show_bank_details", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("bank_details", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("declaration", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.String(length=200), nullable=True),
        sa.Column("footer_note", sa.Text(), nullable=True),
        sa.Column("signatory_text", sa.String(length=200), nullable=True),
        sa.Column(
            "show_discount_column",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "show_batch_column", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "show_expiry_column",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("copy_labels", sa.JSON(), nullable=True),
        sa.Column(
            "page_size", sa.String(length=10), nullable=False, server_default="A4"
        ),
        sa.Column("margin_mm", sa.Numeric(6, 2), nullable=False, server_default="12"),
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
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
    )
    op.create_index("IX_document_print_templates_firm", _TABLE, ["firm_id"])
    # One live template per firm per document type. Partial, so a soft-deleted
    # row cannot hold the pair hostage -- the shape `UQ_firms_code_active` uses.
    op.create_index(
        "UQ_document_print_templates_firm_type",
        _TABLE,
        ["firm_id", "document_type"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    """Drop the print template table."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    op.drop_index("UQ_document_print_templates_firm_type", table_name=_TABLE)
    op.drop_index("IX_document_print_templates_firm", table_name=_TABLE)
    op.drop_table(_TABLE)
