"""Capital goods marked on the order line and the receipt line (D-BUY-40).

* ``purchase_order_lines.is_capital_goods`` and
  ``goods_receipt_lines.is_capital_goods``: a machine ordered and received
  like anything else, brought in by its receipt without a stock movement or
  an accrual, and capitalised by its bill. Before this only a bill completing
  its own receipt could say so, which left a firm typing its receipts no way
  to buy a fixed asset.
* Backfill: a receipt line an approved bill already capitalised -- one its
  capital-goods line bills, and which holds no stock movement -- is marked,
  so the two records of one purchase agree. Only rows still at the default.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and lacks it. No foreign key is added.

Revision ID: 20261005_0326
Revises: 20261005_0325
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0326"
down_revision: str | None = "20261005_0325"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("purchase_order_lines", "goods_receipt_lines")
_COLUMN = "is_capital_goods"


def _has_column(inspector: sa.Inspector, table: str) -> bool:
    """Say whether the table already carries the capital-goods mark."""
    return _COLUMN in {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the mark to both line tables and backfill capitalised receipts."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if inspector.has_table(table) and not _has_column(inspector, table):
            op.add_column(
                table,
                sa.Column(
                    _COLUMN,
                    sa.Boolean(),
                    server_default=sa.text("false"),
                    nullable=False,
                ),
            )
    if not (
        inspector.has_table("goods_receipt_lines")
        and inspector.has_table("purchase_invoice_lines")
        and inspector.has_table("purchase_invoices")
        and _has_column(inspector, "purchase_invoice_lines")
    ):
        return
    op.execute(
        sa.text(
            "UPDATE goods_receipt_lines SET is_capital_goods = true "
            "WHERE is_capital_goods = false "
            "AND inventory_transaction_id IS NULL "
            "AND id IN ("
            "SELECT pil.source_document_line_id "
            "FROM purchase_invoice_lines pil "
            "JOIN purchase_invoices pi ON pi.id = pil.purchase_invoice_id "
            "WHERE pil.is_capital_goods = true "
            "AND pil.is_deleted = false "
            "AND pil.source_document_type = 'GOODS_RECEIPT' "
            "AND pi.is_deleted = false "
            "AND pi.status IN ('APPROVED', 'CLOSED'))"
        )
    )


def downgrade() -> None:
    """Drop the mark from both line tables."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        if inspector.has_table(table) and _has_column(inspector, table):
            op.drop_column(table, _COLUMN)
