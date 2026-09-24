"""A tax execution log names the document line it decided (D-CMP-13).

Every log read ``execution_mode`` SIMULATION, a document's lines included, and
nothing said which document or line a row belonged to. The service now writes
DOCUMENT for a document line, and three nullable columns say which one:
``document_type``, ``document_id`` and ``line_number``. A line row is written
after its tax is decided, so it is named by its document and its line number
-- the key document lines are reconciled on -- rather than by an id it does not
have yet.

Logs already written are not restated: nothing about them was recorded to
restate them from with any certainty.

The same row found two template rules conditioned on transaction types no
document sends. ``EXPORT_ZERO`` asked for ``EXPORT``; it now asks for a
``destination`` of ``96``, the state code of a buyer outside India, which the
engine derives from the buyer. ``PURCHASE_INPUT_CREDIT`` asked for
``PURCHASE`` alone, so only the order got the credit; it now asks for any of
the four inward documents. Only conditions still exactly as the template wrote
them are rewritten, so a firm that edited either rule keeps its own, and a
second run finds nothing to do.

Idempotent: each column is added only where the table exists and the column is
missing, because firm stores are partly built by ``create_all``. Firm-owned, so
run it through ``scripts/migrate_all_stores.py``.

Revision ID: 20260924_0159
Revises: 20260924_0158
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260924_0159"
down_revision: str | Sequence[str] | None = "20260924_0158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "tax_rule_execution_logs"

_INWARD = ["PURCHASE", "GOODS_RECEIPT", "PURCHASE_INVOICE", "PURCHASE_RETURN"]


def _columns() -> list[sa.Column[object]]:
    """Return the columns this revision adds, freshly built each time."""
    return [
        sa.Column("document_type", sa.String(40), nullable=True),
        sa.Column("document_id", UUIDType(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    """Add each column where a store lacks it, then fix the two rules."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        existing = {column["name"] for column in inspector.get_columns(_TABLE)}
        for column in _columns():
            if column.name not in existing:
                op.add_column(_TABLE, column)
    rewrite_template_conditions(op.get_bind())


def rewrite_template_conditions(bind: sa.Connection) -> int:
    """Point the two template rules at what documents actually send.

    Returns how many conditions were rewritten, so a second run can be seen
    to find none.
    """
    inspector = sa.inspect(bind)
    if not inspector.has_table("tax_rule_conditions") or not inspector.has_table(
        "tax_rules"
    ):
        return 0
    exported = bind.execute(
        sa.text(
            """
            UPDATE tax_rule_conditions
            SET field_key = 'destination', value_text = '96'
            WHERE field_key = 'transaction_type'
              AND operator = 'EQUALS'
              AND value_text = 'EXPORT'
              AND is_deleted = false
              AND tax_rule_id IN (
                  SELECT id FROM tax_rules
                  WHERE code = 'EXPORT_ZERO' AND is_deleted = false
              )
            """
        )
    )
    inward = bind.execute(
        sa.text(
            """
            UPDATE tax_rule_conditions
            SET operator = 'IN', value_text = NULL, value_json = :values
            WHERE field_key = 'transaction_type'
              AND operator = 'EQUALS'
              AND value_text = 'PURCHASE'
              AND is_deleted = false
              AND tax_rule_id IN (
                  SELECT id FROM tax_rules
                  WHERE code = 'PURCHASE_INPUT_CREDIT' AND is_deleted = false
              )
            """
        ).bindparams(sa.bindparam("values", {"values": _INWARD}, type_=sa.JSON))
    )
    return int(exported.rowcount or 0) + int(inward.rowcount or 0)


def downgrade() -> None:
    """Drop the columns, forgetting which line each log decided.

    The rewritten conditions are left as they are: the old ones matched
    nothing a document sends, so there is nothing worth going back to.
    """
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in reversed(_columns()):
        if column.name in existing:
            op.drop_column(_TABLE, column.name)
