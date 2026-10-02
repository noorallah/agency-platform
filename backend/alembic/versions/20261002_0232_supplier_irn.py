"""The supplier's IRN on a bill, and the firm's check (backlog 78 row 5).

``purchase_invoices`` gains ``supplier_irn``; ``vendors`` gains
``issues_e_invoices``; ``gst_compliance_settings`` gains ``supplier_irn_check``
(OFF or WARN -- the default).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and lacks it.

Revision ID: 20261002_0232
Revises: 20261002_0231
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0232"
down_revision: str | Sequence[str] | None = "20261002_0231"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> tuple[tuple[str, sa.Column], ...]:  # type: ignore[type-arg]
    """Return (table, column) for each column this revision adds, fresh."""
    return (
        ("purchase_invoices", sa.Column("supplier_irn", sa.String(length=64))),
        (
            "vendors",
            sa.Column(
                "issues_e_invoices",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        ),
        (
            "gst_compliance_settings",
            sa.Column(
                "supplier_irn_check",
                sa.String(length=10),
                nullable=False,
                server_default="WARN",
            ),
        ),
    )


def _present(inspector: sa.Inspector, table: str) -> set[str] | None:
    """Return the table's column names, or None where this store lacks it."""
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add each column where its table is held and lacks it."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        present = _present(inspector, table)
        if present is not None and column.name not in present:
            op.add_column(table, column)


def downgrade() -> None:
    """Drop each column where it was added."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        present = _present(inspector, table)
        if present is not None and column.name in present:
            op.drop_column(table, column.name)
