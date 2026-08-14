"""Give a quotation somewhere to live.

The Sales module has advertised a Quotations tab since it was written and there
has never been anything behind it: no table, no endpoint, and a
`SALES_QUOTATION_CREATE` permission code seeded and enforced nowhere.

A quotation is an offer, and an offer commits nothing -- no stock reservation,
no customer balance, no journal. The only thing it owns that an order does not
is ``valid_until``, because a price offered in April is not a price offered in
December.

Four tables, all firm-owned: run ``scripts/migrate_all_stores.py``.

``converted_sales_order_id`` is a bare id with no foreign key, the convention
every cross-document reference here follows -- and the order it names is
created by ``SalesOrderService``, which may reconcile its own lines.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260814_0086"
down_revision: str | Sequence[str] | None = "20260814_0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_QUOTATIONS = "sales_quotations"
_LINES = "sales_quotation_lines"
_ATTACHMENTS = "sales_quotation_attachments"
_NOTES = "sales_quotation_notes"


def _has(table: str) -> bool:
    """Return whether a table exists in this store, asked for now."""
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
        ["sales_quotation_id"],
        [f"{_QUOTATIONS}.id"],
        name=f"FK_{table}_sales_quotation_id",
        ondelete="CASCADE",
    )


def _create_quotations() -> None:
    """Create the quotation header."""
    op.create_table(
        _QUOTATIONS,
        *_entity_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("customer_id", UUIDType(), nullable=False),
        sa.Column("salesman_id", UUIDType(), nullable=True),
        sa.Column("territory_id", UUIDType(), nullable=True),
        sa.Column("branch_id", UUIDType(), nullable=False),
        sa.Column("warehouse_id", UUIDType(), nullable=False),
        sa.Column("business_profile_id", UUIDType(), nullable=True),
        sa.Column("quotation_number", sa.String(length=60), nullable=False),
        sa.Column("quotation_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("customer_reference", sa.String(length=80), nullable=True),
        sa.Column("reference_number", sa.String(length=80), nullable=True),
        sa.Column("payment_terms", sa.String(length=200), nullable=True),
        sa.Column("delivery_terms", sa.String(length=200), nullable=True),
        sa.Column("currency_code", sa.String(length=10), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="DRAFT"
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
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_sales_order_id", UUIDType(), nullable=True),
        sa.Column("converted_sales_order_number", sa.String(length=60), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "firm_id",
            "quotation_number",
            name="UQ_sales_quotations_firm_quotation_number",
        ),
    )
    op.create_index("IX_sales_quotations_firm_id", _QUOTATIONS, ["firm_id"])
    op.create_index(
        "IX_sales_quotations_firm_status", _QUOTATIONS, ["firm_id", "status"]
    )
    op.create_index(
        "IX_sales_quotations_firm_date", _QUOTATIONS, ["firm_id", "quotation_date"]
    )
    op.create_index(
        "IX_sales_quotations_firm_customer",
        _QUOTATIONS,
        ["firm_id", "customer_id"],
    )
    op.create_index(
        "IX_sales_quotations_firm_valid_until",
        _QUOTATIONS,
        ["firm_id", "valid_until"],
    )


def _create_lines() -> None:
    """Create the quotation lines."""
    op.create_table(
        _LINES,
        *_entity_columns(),
        sa.Column("sales_quotation_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUIDType(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "free_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("sales_uom_id", UUIDType(), nullable=True),
        sa.Column("inventory_uom_id", UUIDType(), nullable=True),
        sa.Column("packaging_type_id", UUIDType(), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column(
            "discount_percent", sa.Numeric(9, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "discount_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "gross_amount", sa.Numeric(18, 4), nullable=False, server_default="0"
        ),
        sa.Column("tax_profile_id", UUIDType(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("warehouse_id", UUIDType(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "sales_quotation_id",
            "line_number",
            name="UQ_sales_quotation_lines_quotation_line",
        ),
        _child_fk(_LINES),
    )
    op.create_index("IX_sales_quotation_lines_firm_id", _LINES, ["firm_id"])
    op.create_index(
        "IX_sales_quotation_lines_sales_quotation_id",
        _LINES,
        ["sales_quotation_id"],
    )
    op.create_index(
        "IX_sales_quotation_lines_firm_product", _LINES, ["firm_id", "product_id"]
    )


def _create_attachments() -> None:
    """Create the quotation attachments."""
    op.create_table(
        _ATTACHMENTS,
        *_entity_columns(),
        sa.Column("sales_quotation_id", UUIDType(), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "attachment_kind",
            sa.String(length=40),
            nullable=False,
            server_default="QUOTATION_FILE",
        ),
        _child_fk(_ATTACHMENTS),
    )
    op.create_index("IX_sales_quotation_attachments_firm_id", _ATTACHMENTS, ["firm_id"])
    op.create_index(
        "IX_sales_quotation_attachments_sales_quotation_id",
        _ATTACHMENTS,
        ["sales_quotation_id"],
    )


def _create_notes() -> None:
    """Create the quotation notes."""
    op.create_table(
        _NOTES,
        *_entity_columns(),
        sa.Column("sales_quotation_id", UUIDType(), nullable=False),
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
    op.create_index("IX_sales_quotation_notes_firm_id", _NOTES, ["firm_id"])
    op.create_index(
        "IX_sales_quotation_notes_sales_quotation_id", _NOTES, ["sales_quotation_id"]
    )


def upgrade() -> None:
    """Create the four quotation tables, skipping any that exist.

    The sample-data and tenancy-reset scripts build firm stores with
    ``Base.metadata.create_all``, so a table can already be there while
    ``alembic_version`` reads older.
    """
    if not _has(_QUOTATIONS):
        _create_quotations()
    if _has(_QUOTATIONS) and not _has(_LINES):
        _create_lines()
    if _has(_QUOTATIONS) and not _has(_ATTACHMENTS):
        _create_attachments()
    if _has(_QUOTATIONS) and not _has(_NOTES):
        _create_notes()


def downgrade() -> None:
    """Drop the four tables, children before the header they cascade from."""
    for table in (_NOTES, _ATTACHMENTS, _LINES, _QUOTATIONS):
        if _has(table):
            op.drop_table(table)
