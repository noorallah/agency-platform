"""Trigram indexes for the Ctrl+K search (PLT-3).

The global search asks ``column ILIKE '%text%'`` on names, codes and document
numbers. A B-tree index cannot answer a match in the middle of a value, so on
a firm the size of PERF01 every keystroke read every row. A GIN index with
``gin_trgm_ops`` can.

``pg_trgm`` is installed once per database into ``public`` and the operator
class is named there, so a database holding several firm schemas indexes each
of them with the one extension. It is a trusted extension (PostgreSQL 13+),
so the database owner may install it; where it still cannot be installed the
migration logs that and carries on -- search stays correct, only slower.

PostgreSQL only: SQLite has no GIN, and the unit suite searches a dozen rows.
Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0250
Revises: 20261003_0249
Create Date: 2026-10-03

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from alembic import op

revision: str = "20261003_0250"
down_revision: str | Sequence[str] | None = "20261003_0249"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: The columns the search reads most, on the tables that grow with the firm.
SEARCHED: dict[str, tuple[str, ...]] = {
    "customers": ("name", "code"),
    "vendors": ("name", "code"),
    "products": ("name", "code", "barcode"),
    "sales_invoices": ("invoice_number",),
    "sales_orders": ("order_number",),
    "delivery_notes": ("delivery_note_number",),
    "purchase_orders": ("po_number",),
    "purchase_invoices": ("invoice_number", "supplier_invoice_number"),
    "goods_receipts": ("grn_number",),
    "sales_quotations": ("quotation_number",),
    "settlements": ("settlement_number",),
}


def _name(table: str, column: str) -> str:
    """Return the index name for one column."""
    return f"IX_{table}_{column}_trgm"


def upgrade() -> None:
    """Install pg_trgm and index each searched column that exists here."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    present = {
        table: [
            column
            for column in columns
            if column in {c["name"] for c in inspector.get_columns(table)}
        ]
        for table, columns in SEARCHED.items()
        if inspector.has_table(table)
    }
    if not any(present.values()):
        return
    try:
        with bind.begin_nested():
            bind.execute(
                sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
            )
    except DBAPIError as error:
        logger.warning(
            "pg_trgm could not be installed (%s); search keeps working, "
            "only without trigram indexes.",
            str(error).splitlines()[0],
        )
        return
    for table, columns in present.items():
        for column in columns:
            bind.execute(
                sa.text(
                    f'CREATE INDEX IF NOT EXISTS "{_name(table, column)}" '
                    f'ON "{table}" USING gin ("{column}" public.gin_trgm_ops)'
                )
            )


def downgrade() -> None:
    """Drop the indexes; the extension is left for anything else using it."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, columns in SEARCHED.items():
        for column in columns:
            bind.execute(sa.text(f'DROP INDEX IF EXISTS "{_name(table, column)}"'))
