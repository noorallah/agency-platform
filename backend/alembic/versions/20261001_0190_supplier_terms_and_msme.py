"""Supplier payment terms and MSME payment deadlines (backlog 68 rows 1-2).

* ``vendors``: ``payment_terms_days`` (NOT NULL, default 0), ``udyam_number``,
  ``msme_category`` and ``msme_written_agreement`` (NOT NULL, default false).
* ``purchase_invoices.msme_pay_by``: the last day a bill to a micro or small
  supplier may be paid, stamped when the bill is written.

Idempotent; firm-owned, so it runs per store
(``scripts/migrate_all_stores.py``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0190"
down_revision: str | Sequence[str] | None = "20261001_0184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.Column[object]], ...] = (
    (
        "vendors",
        sa.Column(
            "payment_terms_days", sa.Integer(), server_default="0", nullable=False
        ),
    ),
    ("vendors", sa.Column("udyam_number", sa.String(30), nullable=True)),
    ("vendors", sa.Column("msme_category", sa.String(10), nullable=True)),
    (
        "vendors",
        sa.Column(
            "msme_written_agreement",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    ),
    ("purchase_invoices", sa.Column("msme_pay_by", sa.Date(), nullable=True)),
)


def upgrade() -> None:
    """Add each column where its table lives and it is missing."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _COLUMNS:
        if not inspector.has_table(table):
            continue
        present = {item["name"] for item in inspector.get_columns(table)}
        if column.name not in present:
            op.add_column(table, column)


def downgrade() -> None:
    """Drop them."""
    inspector = sa.inspect(op.get_bind())
    for table, column in reversed(_COLUMNS):
        if not inspector.has_table(table):
            continue
        present = {item["name"] for item in inspector.get_columns(table)}
        if column.name in present:
            op.drop_column(table, column.name)
