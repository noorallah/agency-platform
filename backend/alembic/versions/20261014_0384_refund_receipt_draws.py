"""Which receipt a refund handed money back from (D-FIN-30).

* ``refund_receipt_draws``: one row per receipt a refund drew on, with the
  amount, so the receipt's ``unallocated_amount`` comes down by it and a
  reversed refund puts back exactly that. Both keys point at ``settlements``,
  which is firm-owned and in every firm store, so no key crosses a schema.

Refunds recorded before this revision drew on no receipt and are not gone
back over: their receipts keep reading the money as unapplied, as they did.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a firm store
is partly built by ``Base.metadata.create_all``, so the table is created only
where it is missing.

Revision ID: 20261014_0384
Revises: 20261014_0383
Create Date: 2026-10-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261014_0384"
down_revision: str | Sequence[str] | None = "20261014_0383"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "refund_receipt_draws"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP`: a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails (`20260903_0114`).
    """
    return [
        sa.Column("id", UUIDType(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUIDType(), nullable=True),
        sa.Column("updated_by", UUIDType(), nullable=True),
        sa.Column("deleted_by", UUIDType(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    ]


def upgrade() -> None:
    """Create the table where it is missing."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column(
            "refund_id",
            UUIDType(),
            sa.ForeignKey(
                "settlements.id",
                ondelete="RESTRICT",
                name="FK_refund_receipt_draws_refund_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "receipt_id",
            UUIDType(),
            sa.ForeignKey(
                "settlements.id",
                ondelete="RESTRICT",
                name="FK_refund_receipt_draws_receipt_id",
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="POSTED"),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", UUIDType(), nullable=True),
        sa.CheckConstraint("amount > 0", name="CK_refund_receipt_draws_positive"),
    )
    op.create_index("IX_refund_receipt_draws_refund", _TABLE, ["firm_id", "refund_id"])
    op.create_index(
        "IX_refund_receipt_draws_receipt", _TABLE, ["firm_id", "receipt_id"]
    )


def downgrade() -> None:
    """Drop the table: refunds name no receipt again."""
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
