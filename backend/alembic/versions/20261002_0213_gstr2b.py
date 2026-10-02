"""GSTR-2B imports and their documents; the 2B settings (backlog 78 row 3).

* ``gstr2b_imports``: one live import per firm and month, a re-import
  soft-deleting the earlier one.
* ``gstr2b_documents``: each supplier invoice and note of an import, with what
  it matched (a bill or a debit note, by bare id) and how.
* ``gst_compliance_settings.itc_claim_basis`` (``ALL``, every existing row --
  how 3B has always claimed) and ``gstr2b_tolerance`` (1.00).

No permission codes: importing and matching take ``JOURNAL_POST``, reading
``ACCOUNT_VIEW`` or ``SALES_VIEW``, as the GST filings do.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent, because firm
stores are partly built by ``Base.metadata.create_all``.

Revision ID: 20261002_0213
Revises: 20261002_0212
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0213"
down_revision: str | Sequence[str] | None = "20261002_0212"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def _money(name: str) -> sa.Column:  # type: ignore[type-arg]
    """Return a money column defaulting to nothing."""
    return sa.Column(name, sa.Numeric(18, 2), nullable=False, server_default="0")


def _settings_columns(inspector: sa.Inspector) -> None:
    """Add the two 2B settings to a store that has the settings table."""
    if not inspector.has_table("gst_compliance_settings"):
        return
    present = {c["name"] for c in inspector.get_columns("gst_compliance_settings")}
    if "itc_claim_basis" not in present:
        op.add_column(
            "gst_compliance_settings",
            sa.Column(
                "itc_claim_basis",
                sa.String(length=15),
                nullable=False,
                server_default="ALL",
            ),
        )
    if "gstr2b_tolerance" not in present:
        op.add_column(
            "gst_compliance_settings",
            sa.Column(
                "gstr2b_tolerance",
                sa.Numeric(18, 2),
                nullable=False,
                server_default="1.00",
            ),
        )


def upgrade() -> None:
    """Create the tables and columns where this store holds purchase bills."""
    inspector = sa.inspect(op.get_bind())
    _settings_columns(inspector)
    if not inspector.has_table("purchase_invoices"):
        return
    if not inspector.has_table("gstr2b_imports"):
        op.create_table(
            "gstr2b_imports",
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("return_period", sa.String(length=7), nullable=False),
            sa.Column("gstin", sa.String(length=15), nullable=True),
            sa.Column("source_name", sa.String(length=260), nullable=True),
            sa.Column(
                "document_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("skipped_sections", sa.Text(), nullable=True),
        )
        op.create_index("IX_gstr2b_imports_firm_id", "gstr2b_imports", ["firm_id"])
        op.create_index(
            "UQ_gstr2b_imports_firm_period_active",
            "gstr2b_imports",
            ["firm_id", "return_period"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            sqlite_where=sa.text("is_deleted = 0"),
        )
    if not inspector.has_table("gstr2b_documents"):
        op.create_table(
            "gstr2b_documents",
            *_base_columns(),
            sa.Column("gstr2b_import_id", UUIDType(), nullable=False),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("supplier_gstin", sa.String(length=15), nullable=False),
            sa.Column("supplier_name", sa.String(length=200), nullable=True),
            sa.Column("document_type", sa.String(length=20), nullable=False),
            sa.Column("document_number", sa.String(length=40), nullable=False),
            sa.Column("document_date", sa.Date(), nullable=False),
            _money("document_value"),
            _money("taxable_value"),
            _money("igst"),
            _money("cgst"),
            _money("sgst"),
            _money("cess"),
            sa.Column(
                "itc_available", sa.Boolean(), nullable=False, server_default="true"
            ),
            sa.Column(
                "reverse_charge", sa.Boolean(), nullable=False, server_default="false"
            ),
            sa.Column(
                "match_status",
                sa.String(length=20),
                nullable=False,
                server_default="NOT_IN_BOOKS",
            ),
            sa.Column("match_note", sa.Text(), nullable=True),
            sa.Column("purchase_invoice_id", UUIDType(), nullable=True),
            sa.Column("debit_note_id", UUIDType(), nullable=True),
            sa.ForeignKeyConstraint(
                ["gstr2b_import_id"],
                ["gstr2b_imports.id"],
                name="FK_gstr2b_documents_gstr2b_import_id",
                ondelete="CASCADE",
            ),
        )
        op.create_index("IX_gstr2b_documents_firm_id", "gstr2b_documents", ["firm_id"])
        op.create_index(
            "IX_gstr2b_documents_import", "gstr2b_documents", ["gstr2b_import_id"]
        )
        op.create_index(
            "IX_gstr2b_documents_firm_gstin",
            "gstr2b_documents",
            ["firm_id", "supplier_gstin"],
        )
        op.create_index(
            "IX_gstr2b_documents_invoice", "gstr2b_documents", ["purchase_invoice_id"]
        )


def downgrade() -> None:
    """Drop the tables and the columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table in ("gstr2b_documents", "gstr2b_imports"):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("gst_compliance_settings"):
        present = {c["name"] for c in inspector.get_columns("gst_compliance_settings")}
        for name in ("gstr2b_tolerance", "itc_claim_basis"):
            if name in present:
                op.drop_column("gst_compliance_settings", name)
