"""Let a firm say which buying stages it fills in by hand.

The chain is purchase order, goods receipt, supplier bill. A firm run by one
person has the supplier's bill in hand and nothing else, so this records
whether that firm types the order and the receipt itself or has the bill raise
them (backlog §38, the buying twin of ``20260902_0104``).

Three changes, all firm-owned, so platform gets none of them:

* ``purchase_workflow_settings``: one row per firm, a column per stage. No row
  is created for anybody, so every firm keeps the whole chain until somebody
  switches a stage off.
* ``purchase_orders.raised_by_purchase_invoice_id`` and
  ``goods_receipts.raised_by_purchase_invoice_id``: which bill raised the
  document, so only that bill completes it on approval and withdraws it when a
  draft is cancelled. Null for every existing row, which is correct: a person
  raised them.

Idempotent: firm stores are partly built by ``create_all``, so each object is
checked before it is created.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260928_0163"
down_revision: str | Sequence[str] | None = "20260927_0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "purchase_workflow_settings"
_STAMPED = ("purchase_orders", "goods_receipts")
_COLUMN = "raised_by_purchase_invoice_id"


def _index_name(table: str) -> str:
    """Name the index on one table's raised-by column."""
    return f"IX_{table}_{_COLUMN}"


def upgrade() -> None:
    """Create the settings table and the two raised-by columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Firm-owned: purchase orders live in firm stores only.
    if not inspector.has_table("purchase_orders"):
        return
    for table in _STAMPED:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN not in columns:
            op.add_column(table, sa.Column(_COLUMN, UUIDType(), nullable=True))
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if _index_name(table) not in indexes:
            op.create_index(_index_name(table), table, [_COLUMN])
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "purchase_order_stage",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "goods_receipt_stage",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("default_branch_id", UUIDType(), nullable=True),
        sa.Column("default_warehouse_id", UUIDType(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="PK_purchase_workflow_settings"),
        sa.UniqueConstraint("firm_id", name="UQ_purchase_workflow_settings_firm"),
    )
    op.create_index("IX_purchase_workflow_settings_firm_id", _TABLE, ["firm_id"])


def downgrade() -> None:
    """Drop the table and the columns; every firm keeps the whole chain."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_index("IX_purchase_workflow_settings_firm_id", table_name=_TABLE)
        op.drop_table(_TABLE)
    for table in _STAMPED:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if _COLUMN in columns:
            indexes = {index["name"] for index in inspector.get_indexes(table)}
            if _index_name(table) in indexes:
                op.drop_index(_index_name(table), table_name=table)
            op.drop_column(table, _COLUMN)
