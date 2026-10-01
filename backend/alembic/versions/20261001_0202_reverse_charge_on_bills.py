"""Reverse charge on purchase bills (backlog 68 row 8).

* ``purchase_invoice_line_taxes.reverse_charge``: the component is owed by the
  firm itself rather than charged by the supplier. False on every row already
  written, which is what each of them was.
* ``purchase_invoices.reverse_charge_tax_total``: that tax summed for the bill,
  outside ``tax_total`` and the payable. Zero on every bill already written.
* ``purchase_invoices.self_invoice_number``: the self-invoice raised for the
  supply (rule 47A), from its own series; unique per firm where set.
* ``gst_payments.reverse_charge_{igst,cgst,sgst,cess}``: the month's reverse
  charge, paid in cash only. Zero on every settlement already recorded.

Idempotent; firm-owned, so it runs per store (``scripts/migrate_all_stores.py``)
and touches only the tables a store holds.

Revision ID: 20261001_0202
Revises: 20261001_0201
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0202"
down_revision: str | Sequence[str] | None = "20261001_0201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "UQ_purchase_invoices_firm_self_invoice_number"


def _money(name: str, scale: int) -> sa.Column:
    """Return a NOT NULL money column defaulting to zero."""
    return sa.Column(
        name,
        sa.Numeric(18, scale),
        nullable=False,
        server_default=sa.text("0"),
    )


def _columns() -> list[tuple[str, sa.Column]]:
    """Return each table and the column it gains, built fresh per call."""
    return [
        (
            "purchase_invoice_line_taxes",
            sa.Column(
                "reverse_charge",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        ("purchase_invoices", _money("reverse_charge_tax_total", 4)),
        (
            "purchase_invoices",
            sa.Column("self_invoice_number", sa.String(60), nullable=True),
        ),
        *(
            ("gst_payments", _money(f"reverse_charge_{head}", 2))
            for head in ("igst", "cgst", "sgst", "cess")
        ),
    ]


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    """Return whether a table this store holds already has the column."""
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    """Add the columns, and the self-invoice key, wherever they are missing."""
    inspector = sa.inspect(op.get_bind())
    for table, column in _columns():
        if inspector.has_table(table) and not _has_column(
            inspector, table, column.name
        ):
            op.add_column(table, column)
    if inspector.has_table("purchase_invoices") and not any(
        index["name"] == _INDEX
        for index in sa.inspect(op.get_bind()).get_indexes("purchase_invoices")
    ):
        op.create_index(
            _INDEX,
            "purchase_invoices",
            ["firm_id", "self_invoice_number"],
            unique=True,
            postgresql_where=sa.text("self_invoice_number IS NOT NULL"),
            sqlite_where=sa.text("self_invoice_number IS NOT NULL"),
        )


def downgrade() -> None:
    """Drop the key and the columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("purchase_invoices") and any(
        index["name"] == _INDEX for index in inspector.get_indexes("purchase_invoices")
    ):
        op.drop_index(_INDEX, table_name="purchase_invoices")
    for table, column in _columns():
        if inspector.has_table(table) and _has_column(inspector, table, column.name):
            op.drop_column(table, column.name)
