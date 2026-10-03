"""The tax rule that decided each document line, kept on the line (GST-8).

``tax_rule_code`` and ``tax_rule_version`` on the nine line tables whose tax
``TaxRuleService.simulate`` decides. Lines written before stay null: the rule
that decided them is in the execution log only while it lasts, and guessing
it now would put an answer on the line nobody gave (decision A85).

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261003_0257
Revises: 20261003_0256
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_0257"
down_revision: str | Sequence[str] | None = "20261003_0256"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "sales_quotation_lines",
    "sales_order_lines",
    "delivery_note_lines",
    "sales_invoice_lines",
    "sales_return_lines",
    "purchase_order_lines",
    "goods_receipt_lines",
    "purchase_invoice_lines",
    "purchase_return_lines",
)


def upgrade() -> None:
    """Add the two columns to every line table that has the table."""
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if not inspector.has_table(table):
            continue
        have = {column["name"] for column in inspector.get_columns(table)}
        if "tax_rule_code" not in have:
            op.add_column(table, sa.Column("tax_rule_code", sa.String(50)))
        if "tax_rule_version" not in have:
            op.add_column(table, sa.Column("tax_rule_version", sa.Integer()))


def downgrade() -> None:
    """Drop the two columns where they exist."""
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if not inspector.has_table(table):
            continue
        have = {column["name"] for column in inspector.get_columns(table)}
        for column in ("tax_rule_code", "tax_rule_version"):
            if column in have:
                op.drop_column(table, column)
