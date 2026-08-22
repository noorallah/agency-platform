"""A bill can state what was given away.

`free_quantity` exists on quotation, sales order and delivery note lines: stock
moves for it, and it is correctly excluded from what is charged and taxed. The
sales invoice had no such column, so goods could be promised, ordered and
dispatched free and then not be stated on the document the customer actually
reads.

A bill that shows ten units when eleven arrived is a bill the customer queries,
and the answer -- "one was free" -- exists nowhere on it. Statutory invoices
list what was supplied, free goods included, at nil value.

Nothing about stock changes here. The delivery note moved the goods; the
invoice states what was supplied and what is being charged for.

Revision ID: 20260823_0100
Revises: 20260823_0099
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0100"
down_revision: str | Sequence[str] | None = "20260823_0099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sales_invoice_lines", "free_quantity"),
    ("sales_invoices", "total_free_quantity"),
)


def upgrade() -> None:
    """Add free quantity to the invoice line and its total to the header."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        # Firm schemas are partly built by `Base.metadata.create_all` from the
        # sample-data and tenancy-reset scripts, so a column can exist even
        # where `alembic_version` reads older; and neither table exists in the
        # platform schema.
        if not inspector.has_table(table):
            continue
        if column in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.add_column(
            table,
            sa.Column(
                column,
                sa.Numeric(precision=18, scale=4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Drop the free quantity and its total."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        if column not in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.drop_column(table, column)
