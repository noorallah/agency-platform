"""Record on a delivery note the bill that raised it (D-CFG-16).

With the delivery-note stage off, a bill raises its own note and dispatches it
when the bill is approved (D-SELL-13). Which notes a bill could treat that way
was decided by the firm's stage **now**, so a draft bill adopted any approved,
undispatched note of its order -- one a person raised before the stage was
switched off included -- billed it undispatched, dispatched it on approval and
cancelled it with the draft.

``raised_by_sales_invoice_id`` names the bill that raised the note, and only
that bill may do any of the three. A bare, nullable, indexed id, like every
source reference in the sales chain: the invoice module depends on the
delivery-note module, never the other way round.

Backfill, only where still NULL: a note is stamped with the bill that names it
when that bill was recorded as raising its own note (``allow_direct_sales_order``)
**and** both were written in one transaction -- ``created_at`` is the
transaction's timestamp on PostgreSQL, so equal values mean the chain raised
the note in the bill's own save. A note a person raised earlier has an earlier
``created_at`` and stays NULL, which is the point. Drafts saved before this
revision therefore keep dispatching the notes they raised.

Idempotent: the column and index are added only where ``delivery_notes``
exists and lacks them, because firm stores are partly built by ``create_all``.
The table is firm-owned, so run this through ``scripts/migrate_all_stores.py``.

Revision ID: 20260919_0146
Revises: 20260919_0142
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260919_0146"
down_revision: str | Sequence[str] | None = "20260919_0142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "delivery_notes"
_COLUMN = "raised_by_sales_invoice_id"
_INDEX = "IX_delivery_notes_raised_by_sales_invoice_id"

#: Pairs to stamp: the note, and the bill that raised it in its own save.
_RAISED_TOGETHER = sa.text(
    """
    SELECT DISTINCT n.id AS note_id, i.id AS invoice_id
    FROM delivery_notes n
    JOIN sales_invoice_sources s
      ON s.source_document_id = n.id
     AND s.source_document_type = 'DELIVERY_NOTE'
     AND s.is_deleted = false
    JOIN sales_invoices i
      ON i.id = s.sales_invoice_id
     AND i.allow_direct_sales_order = true
     AND i.created_at = n.created_at
    WHERE n.raised_by_sales_invoice_id IS NULL
    """
)


def upgrade() -> None:
    """Add the column and index where missing, then stamp the chain's notes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        # The platform schema holds no firm-owned tables once pruned.
        return
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, UUIDType(), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN])
    if not (
        inspector.has_table("sales_invoices")
        and inspector.has_table("sales_invoice_sources")
    ):
        return
    pairs = bind.execute(_RAISED_TOGETHER).mappings().all()
    for pair in pairs:
        bind.execute(
            sa.text(
                f"UPDATE {_TABLE} SET {_COLUMN} = :invoice_id "
                f"WHERE id = :note_id AND {_COLUMN} IS NULL"
            ),
            {"invoice_id": pair["invoice_id"], "note_id": pair["note_id"]},
        )


def downgrade() -> None:
    """Drop the index and the column where they exist."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
