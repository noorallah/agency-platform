"""A customer carries a standing discount, and a document records the one it used.

``customers.default_discount_percent`` is the rate a sales line starts at.
Whoever raises the document overrides it freely -- it is a starting point, not
a rule -- so what the line ends up at is already stored on the line.

The snapshot beside it on the three documents that consult the customer answers
a different question: what the customer's standing rate *was* when the document
was raised. Without it, a line discounted at 5% against a customer who is on
10% today looks like a mistake rather than a decision, and the master row has
long since been edited. The sales invoice deliberately has no such column: it
inherits the discount from the line it bills rather than re-reading the
customer, so a snapshot there would name a figure the invoice never consulted.

Both are NOT NULL with a server default of zero, and zero means "no standing
arrangement" -- the same reading ``credit_limit`` takes.

Revision ID: 20260823_0098
Revises: 20260822_0097
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0098"
down_revision: str | Sequence[str] | None = "20260822_0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Table to column. The three documents that read the customer's rate carry a
#: snapshot of it; the customer master carries the rate itself.
_COLUMNS: dict[str, str] = {
    "customers": "default_discount_percent",
    "sales_quotations": "customer_discount_percent",
    "sales_orders": "customer_discount_percent",
    "delivery_notes": "customer_discount_percent",
}


def upgrade() -> None:
    """Add the standing discount and the three document snapshots."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in _COLUMNS.items():
        # Firm schemas are partly built by `Base.metadata.create_all` from the
        # sample-data and tenancy-reset scripts, so a column can already exist
        # even where `alembic_version` reads older; and none of these tables
        # exists in the platform schema at all.
        if not inspector.has_table(table):
            continue
        if column in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.add_column(
            table,
            sa.Column(
                column,
                sa.Numeric(precision=9, scale=4),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Drop the standing discount and the snapshots."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in _COLUMNS.items():
        if not inspector.has_table(table):
            continue
        if column not in {item["name"] for item in inspector.get_columns(table)}:
            continue
        op.drop_column(table, column)
