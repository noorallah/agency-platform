"""A customer's GST registration type (backlog 75 row 2).

``gst_registration_type`` on ``customers``, and
``buyer_gst_registration_type`` on ``sales_invoices`` -- the type stamped on a
bill with its place of supply, so re-classifying a customer later does not
refile bills already issued. Both: REGULAR, COMPOSITION, UNREGISTERED,
SEZ_WITH_PAYMENT, SEZ_WITHOUT_PAYMENT, DEEMED_EXPORT or OVERSEAS. NULL on every
existing customer, which reads its type off the GSTIN as before.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0184"
down_revision: str | Sequence[str] | None = "20261001_0181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUMNS = (
    ("customers", "gst_registration_type"),
    ("sales_invoices", "buyer_gst_registration_type"),
)


def upgrade() -> None:
    """Add both columns where their tables live."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in columns:
            op.add_column(table, sa.Column(column, sa.String(30), nullable=True))


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column in columns:
            op.drop_column(table, column)
