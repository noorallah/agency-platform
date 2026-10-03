"""Custom fields on documents (MST-6, decision A132).

* A value table per document: quotations, sales orders, delivery notes,
  sales invoices, purchase orders and purchase invoices.
* ``attribute_definitions.show_on_print``: whether a field prints on the
  document.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0294
Revises: 20261003_0293
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261003_0294"
down_revision: str | Sequence[str] | None = "20261003_0293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (value table, owner column, owner table)
_TABLES = (
    ("quotation_attribute_values", "quotation_id", "sales_quotations"),
    ("sales_order_attribute_values", "sales_order_id", "sales_orders"),
    ("delivery_note_attribute_values", "delivery_note_id", "delivery_notes"),
    ("sales_invoice_attribute_values", "sales_invoice_id", "sales_invoices"),
    ("purchase_order_attribute_values", "purchase_order_id", "purchase_orders"),
    ("purchase_invoice_attribute_values", "purchase_invoice_id", "purchase_invoices"),
)


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    """Return the columns every entity carries, timestamps defaulted."""
    return [
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    ]


def upgrade() -> None:
    """Add the print flag and the value tables where a store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("attribute_definitions"):
        columns = {
            column["name"] for column in inspector.get_columns("attribute_definitions")
        }
        if "show_on_print" not in columns:
            op.add_column(
                "attribute_definitions",
                sa.Column(
                    "show_on_print",
                    sa.Boolean(),
                    server_default=sa.text("false"),
                    nullable=False,
                ),
            )
    # The platform store keeps some document tables but not the field
    # definitions; a value table needs both ends of its keys.
    if not inspector.has_table("attribute_definitions"):
        return
    for table, owner, owner_table in _TABLES:
        if not inspector.has_table(owner_table) or inspector.has_table(table):
            continue
        op.create_table(
            table,
            *_base_columns(),
            sa.Column("firm_id", UUIDType(), nullable=False),
            sa.Column("attribute_definition_id", UUIDType(), nullable=False),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Numeric(18, 6), nullable=True),
            sa.Column("value_date", sa.Date(), nullable=True),
            sa.Column("value_boolean", sa.Boolean(), nullable=True),
            sa.Column(owner, UUIDType(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=f"PK_{table}"),
            sa.ForeignKeyConstraint(
                ["attribute_definition_id"],
                ["attribute_definitions.id"],
                name=f"FK_{table}_attribute_definition_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                [owner],
                [f"{owner_table}.id"],
                name=f"FK_{table}_{owner}",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                owner, "attribute_definition_id", name=f"UQ_{table}_owner_attribute"
            ),
        )
        op.create_index(f"IX_{table}_firm_id", table, ["firm_id"])
        op.create_index(
            f"IX_{table}_attribute_definition_id", table, ["attribute_definition_id"]
        )
        op.create_index(f"IX_{table}_{owner}", table, [owner])
        op.create_index(f"IX_{table}_firm_text", table, ["firm_id", "value_text"])


def downgrade() -> None:
    """Drop the value tables and the print flag."""
    inspector = sa.inspect(op.get_bind())
    for table, _, _ in _TABLES:
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("attribute_definitions"):
        columns = {
            column["name"] for column in inspector.get_columns("attribute_definitions")
        }
        if "show_on_print" in columns:
            op.drop_column("attribute_definitions", "show_on_print")
