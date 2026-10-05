"""A walk-in cash sale: the cash customer's mark and the buyer on the bill.

Backlog §87 #2 (SG-2).

* ``customers.is_cash_sale``: marks the firm's one built-in *Cash sale*
  customer, with ``UQ_customers_cash_sale_active`` holding it to one per firm.
  No row is written here: the customer is made the first time a counter asks.
* ``sales_invoices.buyer_name`` and ``.buyer_phone``: who a walk-in bill was
  made out to, typed at the counter.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each object is
added only where its table exists and lacks it.

Revision ID: 20261005_0318
Revises: 20261005_0317
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0318"
down_revision: str | Sequence[str] | None = "20261005_0317"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "UQ_customers_cash_sale_active"


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    """Return the names of a table's columns."""
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(inspector: sa.Inspector, table: str) -> set[str | None]:
    """Return the names of a table's indexes."""
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    """Add the mark, its index and the two buyer columns where missing."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("customers"):
        if "is_cash_sale" not in _columns(inspector, "customers"):
            op.add_column(
                "customers",
                sa.Column(
                    "is_cash_sale",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
        if _INDEX not in _indexes(inspector, "customers"):
            op.create_index(
                _INDEX,
                "customers",
                ["firm_id"],
                unique=True,
                postgresql_where=sa.text("is_cash_sale = true AND is_deleted = false"),
            )
    if inspector.has_table("sales_invoices"):
        present = _columns(inspector, "sales_invoices")
        if "buyer_name" not in present:
            op.add_column("sales_invoices", sa.Column("buyer_name", sa.String(200)))
        if "buyer_phone" not in present:
            op.add_column("sales_invoices", sa.Column("buyer_phone", sa.String(30)))


def downgrade() -> None:
    """Drop the buyer columns, the index and the mark where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("sales_invoices"):
        present = _columns(inspector, "sales_invoices")
        for column in ("buyer_phone", "buyer_name"):
            if column in present:
                op.drop_column("sales_invoices", column)
    if inspector.has_table("customers"):
        if _INDEX in _indexes(inspector, "customers"):
            op.drop_index(_INDEX, table_name="customers")
        if "is_cash_sale" in _columns(inspector, "customers"):
            op.drop_column("customers", "is_cash_sale")
