"""A delivery charge the customer is billed, taxed with the goods.

A distributor could not bill delivery. `additional_charges` looks like the
field for it and is added **after** tax on every sales document, so a firm
using it would charge no GST on the delivery -- and under section 15(2) a
charge the seller makes for getting the goods to the buyer is part of the value
of the supply. No sales document in any seeded store carries one, so nothing
had gone out wrong; the field was simply unusable for this.

`freight_amount` is the mirror image of `bill_discount_amount`. One reduces each
line's taxable value and the other raises it, both are apportioned across the
lines by `apportion`, and both give the rounding residual to the largest line so
the shares sum exactly to the header figure. Being on the line is what makes the
tax right: a document-level figure that never touches a taxable value taxes
nothing, which is the mistake `header_discount_amount` makes on a purchase order
and which is deliberately not copied here.

`additional_charges` is left exactly as it is, outside the tax. It is for
additions that really are outside it, and silently re-taxing it would change the
meaning of every document that ever carries one.

Eight columns, all defaulting to zero, so no existing document changes.

Firm-owned: run ``scripts/migrate_all_stores.py``.

Revision ID: 20260903_0124
Revises: 20260903_0123
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0124"
down_revision: str | Sequence[str] | None = "20260903_0123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Header and line together, for each document in the sales chain. The line is
#: where the tax is charged, so a header column without one would be a figure
#: that reduces nothing.
_TABLES: tuple[str, ...] = (
    "sales_quotations",
    "sales_quotation_lines",
    "sales_orders",
    "sales_order_lines",
    "delivery_notes",
    "delivery_note_lines",
    "sales_invoices",
    "sales_invoice_lines",
)


def upgrade() -> None:
    """Add the freight column where a firm store lacks it.

    Checked per table rather than assumed absent: firm schemas are partly built
    by `Base.metadata.create_all` from the sample-data and tenancy-reset
    scripts, so a column can already exist even when `alembic_version` reads
    older.
    """
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        if "freight_amount" in {
            column["name"] for column in inspector.get_columns(table)
        }:
            continue
        op.add_column(
            table,
            sa.Column(
                "freight_amount",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Drop the freight columns, losing what any document charged for delivery."""
    inspector = sa.inspect(op.get_bind())
    for table in reversed(_TABLES):
        if not inspector.has_table(table):
            continue
        if "freight_amount" not in {
            column["name"] for column in inspector.get_columns(table)
        }:
            continue
        op.drop_column(table, "freight_amount")
