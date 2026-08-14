"""Give returned goods somewhere to go.

A customer could always be credit-noted for goods they sent back, which moved
the money. Nothing put the units back on the shelf: inventory went on counting
them as sold, so stock understated what the firm held from that moment on and
the only correction was a manual adjustment nobody knew to make.

Five tables, the mirror of ``purchase_returns`` on the sales side. All of them
are firm-owned: run ``scripts/migrate_all_stores.py``.

Foreign keys are declared only between tables this store owns. ``firms`` lives
in the platform schema and ``customers``/``products`` in a firm one, so a
constraint naming them would build in one deployment mode and fail in another
-- the rule ``_external_fk`` in `20260809_0042` exists for.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260814_0084"
down_revision: str | Sequence[str] | None = "20260814_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETURNS = "sales_returns"
_SOURCES = "sales_return_sources"
_LINES = "sales_return_lines"
_ATTACHMENTS = "sales_return_attachments"
_NOTES = "sales_return_notes"


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asked for now.

    A fresh inspector per call: a cached one answers from the schema as it was
    when it was built, which is how a migration that creates a table then asks
    whether it exists gets told no.
    """
    return sa.inspect(op.get_bind()).has_table(table)


def _entity_columns() -> list[sa.Column]:
    """Return the columns every business entity carries."""
    return [
        sa.Column("id", UUIDType(), primary_key=True),
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
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
    ]


def _child_fk(table: str) -> sa.ForeignKeyConstraint:
    """Return the cascade back to the header, named on the referring column."""
    return sa.ForeignKeyConstraint(
        ["sales_return_id"],
        [f"{_RETURNS}.id"],
        name=f"FK_{table}_sales_return_id",
        ondelete="CASCADE",
    )


def _create_returns() -> None:
    """Create the sales return header."""
    op.create_table(
        _RETURNS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("warehouse_id", UUIDType(), nullable=False),
        sa.Column("salesman_id", UUIDType(), nullable=True),
        sa.Column("territory_id", UUIDType(), nullable=True),
        sa.Column("business_profile_id", UUIDType(), nullable=True),
        sa.Column("return_number", sa.String(length=60), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("customer_return_number", sa.String(length=120), nullable=True),
        sa.Column("customer_return_date", sa.Date(), nullable=True),
        sa.Column(
            "reference_delivery_note_number", sa.String(length=80), nullable=True
        ),
        sa.Column("reference_invoice_number", sa.String(length=80), nullable=True),
        sa.Column("return_reason", sa.String(length=80), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("reference_number", sa.String(length=120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "allow_over_return",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "over_return_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
        ),
        sa.Column(
            "total_source_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_already_returned_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_current_return_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_restock_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "line_discount_total",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "additional_charges",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("round_off", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("journal_entry_id", UUIDType(), nullable=True),
        sa.Column("cost_journal_entry_id", UUIDType(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "firm_id", "return_number", name="UQ_sales_returns_firm_return_number"
        ),
    )
    op.create_index("IX_sales_returns_firm_id", _RETURNS, ["firm_id"])
    op.create_index("IX_sales_returns_firm_status", _RETURNS, ["firm_id", "status"])
    op.create_index("IX_sales_returns_firm_date", _RETURNS, ["firm_id", "return_date"])
    op.create_index(
        "IX_sales_returns_firm_customer", _RETURNS, ["firm_id", "customer_id"]
    )
    op.create_index("IX_sales_returns_firm_branch", _RETURNS, ["firm_id", "branch_id"])
    op.create_index(
        "IX_sales_returns_firm_warehouse", _RETURNS, ["firm_id", "warehouse_id"]
    )


def _create_sources() -> None:
    """Create the documents a return was raised against."""
    op.create_table(
        _SOURCES,
        *_entity_columns(),
        sa.Column("sales_return_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("source_document_type", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", UUIDType(), nullable=False),
        sa.Column("source_document_number", sa.String(length=80), nullable=False),
        sa.Column("source_document_date", sa.Date(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.UniqueConstraint(
            "sales_return_id",
            "source_document_type",
            "source_document_id",
            name="UQ_sales_return_sources_document",
        ),
        _child_fk(_SOURCES),
    )
    op.create_index("IX_sales_return_sources_firm_id", _SOURCES, ["firm_id"])
    op.create_index(
        "IX_sales_return_sources_sales_return_id", _SOURCES, ["sales_return_id"]
    )


def _create_lines() -> None:
    """Create the return lines."""
    op.create_table(
        _LINES,
        *_entity_columns(),
        sa.Column("sales_return_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("source_document_type", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", UUIDType(), nullable=False),
        sa.Column("source_document_number", sa.String(length=80), nullable=False),
        sa.Column("source_document_line_id", UUIDType(), nullable=False),
        sa.Column("source_document_line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "dispatched_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "already_returned_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_return_quantity",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "restock_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "scrap_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("item_condition", sa.String(length=80), nullable=True),
        sa.Column("is_damaged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_expired", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "charges_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_profile_id", UUIDType(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("packaging_type_id", UUIDType(), nullable=True),
        sa.Column("sales_uom_id", UUIDType(), nullable=True),
        sa.Column("return_uom_id", UUIDType(), nullable=True),
        sa.Column(
            "conversion_factor",
            sa.Numeric(24, 10),
            nullable=False,
            server_default="1",
        ),
        sa.Column("conversion_version", sa.Integer(), nullable=True),
        sa.Column("warehouse_id", UUIDType(), nullable=True),
        sa.Column("storage_node_id", UUIDType(), nullable=True),
        sa.Column("batch_number", sa.String(length=120), nullable=True),
        sa.Column("batch_id", UUIDType(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("manufacturing_date", sa.Date(), nullable=True),
        sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "sales_return_id",
            "line_number",
            name="UQ_sales_return_lines_return_line",
        ),
        _child_fk(_LINES),
    )
    op.create_index("IX_sales_return_lines_firm_id", _LINES, ["firm_id"])
    op.create_index(
        "IX_sales_return_lines_sales_return_id", _LINES, ["sales_return_id"]
    )
    op.create_index("IX_sales_return_lines_batch_id", _LINES, ["batch_id"])
    op.create_index(
        "IX_sales_return_lines_firm_product", _LINES, ["firm_id", "product_id"]
    )
    op.create_index(
        "IX_sales_return_lines_firm_source",
        _LINES,
        ["firm_id", "source_document_line_id"],
    )


def _create_attachments() -> None:
    """Create the return attachments."""
    op.create_table(
        _ATTACHMENTS,
        *_entity_columns(),
        sa.Column("sales_return_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="SALES_RETURN_FILE",
        ),
        _child_fk(_ATTACHMENTS),
    )
    op.create_index("IX_sales_return_attachments_firm_id", _ATTACHMENTS, ["firm_id"])
    op.create_index(
        "IX_sales_return_attachments_sales_return_id",
        _ATTACHMENTS,
        ["sales_return_id"],
    )


def _create_notes() -> None:
    """Create the return notes."""
    op.create_table(
        _NOTES,
        *_entity_columns(),
        sa.Column("sales_return_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "note_type",
            sa.String(length=30),
            nullable=False,
            server_default="INTERNAL",
        ),
        sa.Column("note", sa.Text(), nullable=False),
        _child_fk(_NOTES),
    )
    op.create_index("IX_sales_return_notes_firm_id", _NOTES, ["firm_id"])
    op.create_index(
        "IX_sales_return_notes_sales_return_id", _NOTES, ["sales_return_id"]
    )


def upgrade() -> None:
    """Create the five sales return tables, skipping any that exist.

    The sample-data and tenancy-reset scripts build firm stores with
    ``Base.metadata.create_all``, so a table can already be there while
    ``alembic_version`` reads older. Each step checks first.
    """
    if not _has(_RETURNS):
        _create_returns()
    if _has(_RETURNS) and not _has(_SOURCES):
        _create_sources()
    if _has(_RETURNS) and not _has(_LINES):
        _create_lines()
    if _has(_RETURNS) and not _has(_ATTACHMENTS):
        _create_attachments()
    if _has(_RETURNS) and not _has(_NOTES):
        _create_notes()


def downgrade() -> None:
    """Drop the five tables, children before the header they cascade from."""
    for table in (_NOTES, _ATTACHMENTS, _LINES, _SOURCES, _RETURNS):
        if _has(table):
            op.drop_table(table)
