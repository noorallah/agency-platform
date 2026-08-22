"""A discount on the whole bill, reaching the lines so it reduces the tax.

A firm that gives ten percent off an order should not have to type it on every
line. The header carries what was agreed and each line carries its share --
stored, not derived at print time, because tax is charged per line and the
share is what the tax was computed on.

The share on the line is what makes this different from the purchase order's
``header_discount_amount``, which is subtracted after tax and so reduces no
taxable value at all. That shape is deliberately not copied here: a deduction
the tax never saw is a deduction the customer pays tax on.

``sales_returns`` gets the line column but no header pair. A return credits
what a line was actually billed at, so its share is inherited from the invoice
line rather than negotiated again -- crediting the undiscounted figure would
hand back more than was ever charged.

Revision ID: 20260823_0099
Revises: 20260823_0098
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0099"
down_revision: str | Sequence[str] | None = "20260823_0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The four documents where a bill discount is negotiated.
_HEADERS: tuple[str, ...] = (
    "sales_quotations",
    "sales_orders",
    "delivery_notes",
    "sales_invoices",
)

#: Every line table that has to carry a share, returns included.
_LINES: tuple[str, ...] = (
    "sales_quotation_lines",
    "sales_order_lines",
    "delivery_note_lines",
    "sales_invoice_lines",
    "sales_return_lines",
)


def _add(table: str, column: sa.Column[object], inspector: sa.Inspector) -> None:
    """Add one column unless the table is absent or already has it.

    Firm schemas are partly built by `Base.metadata.create_all` from the
    sample-data and tenancy-reset scripts, so an object can exist even where
    `alembic_version` reads older; and none of these tables exists in the
    platform schema.
    """
    if not inspector.has_table(table):
        return
    if column.name in {item["name"] for item in inspector.get_columns(table)}:
        return
    op.add_column(table, column)


def upgrade() -> None:
    """Add the bill discount to the headers and its share to the lines."""
    inspector = sa.inspect(op.get_bind())
    for table in _HEADERS:
        _add(
            table,
            sa.Column(
                "bill_discount_percent",
                sa.Numeric(precision=9, scale=4),
                nullable=False,
                server_default="0",
            ),
            inspector,
        )
        _add(
            table,
            sa.Column(
                "bill_discount_amount",
                sa.Numeric(precision=18, scale=4),
                nullable=False,
                server_default="0",
            ),
            inspector,
        )
    for table in _LINES:
        _add(
            table,
            sa.Column(
                "bill_discount_amount",
                sa.Numeric(precision=18, scale=4),
                nullable=False,
                server_default="0",
            ),
            inspector,
        )


def downgrade() -> None:
    """Drop the bill discount and every line's share of it."""
    inspector = sa.inspect(op.get_bind())
    for table in _HEADERS + _LINES:
        if not inspector.has_table(table):
            continue
        names = {item["name"] for item in inspector.get_columns(table)}
        for column in ("bill_discount_percent", "bill_discount_amount"):
            if column in names:
                op.drop_column(table, column)
