"""Commission on net sales, and a paid period's shortfall clawed back (D-TER-3).

A credit note, a completed sales return and the refund that follows them took
nothing off commission: a bill credited in full went on earning its rate. The
report now measures each bill net of what has been credited against it, and
where the period was already **paid**, the shortfall is carried onto the
person's next accrual rather than the paid row being rewritten.

Two objects hold that:

- ``commission_payouts.clawback_amount`` -- what a payout recovered from
  earlier paid payouts, which came off its payable. NOT NULL with a server
  default of zero, so every existing row reads as having recovered nothing,
  which is true.
- ``commission_clawbacks`` -- one row per (carrying payout, paid payout)
  saying how much came off which. A link table rather than a tally on the paid
  row, so cancelling the carrier releases the recovery without the paid row
  moving.

Idempotent: the column is added and the table created only where
``commission_payouts`` exists (the platform schema holds no firm data once
pruned) and each is missing, because firm stores are partly built by
``create_all``. Both are firm-owned, so run this through
``scripts/migrate_all_stores.py``.

Revision ID: 20260920_0150
Revises: 20260919_0149
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20260920_0150"
down_revision: str | Sequence[str] | None = "20260919_0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAYOUTS = "commission_payouts"
_COLUMN = "clawback_amount"
_TABLE = "commission_clawbacks"


def _base_columns() -> list[sa.Column]:
    """Return the columns every entity in this repo carries.

    The two timestamps carry `CURRENT_TIMESTAMP` because a hand-written
    `create_table` that omits it builds a NOT NULL column with no default, and
    the first insert fails.
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
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    """Add the column and create the table where a firm store lacks them."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_PAYOUTS):
        return
    existing = {column["name"] for column in inspector.get_columns(_PAYOUTS)}
    if _COLUMN not in existing:
        op.add_column(
            _PAYOUTS,
            sa.Column(_COLUMN, sa.Numeric(18, 2), nullable=False, server_default="0"),
        )
    if inspector.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        *_base_columns(),
        sa.Column("firm_id", UUIDType(), nullable=False),
        sa.Column("payout_id", UUIDType(), nullable=False),
        sa.Column("source_payout_id", UUIDType(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="CK_commission_clawbacks_positive"),
        sa.ForeignKeyConstraint(
            ["payout_id"],
            [f"{_PAYOUTS}.id"],
            name="FK_commission_clawbacks_payout_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_payout_id"],
            [f"{_PAYOUTS}.id"],
            name="FK_commission_clawbacks_source_payout_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("IX_commission_clawbacks_firm_id", _TABLE, ["firm_id"])
    op.create_index(
        "IX_commission_clawbacks_firm_payout", _TABLE, ["firm_id", "payout_id"]
    )
    op.create_index(
        "IX_commission_clawbacks_firm_source", _TABLE, ["firm_id", "source_payout_id"]
    )


def downgrade() -> None:
    """Drop the table and the column, forgetting what was recovered."""
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
    if not inspector.has_table(_PAYOUTS):
        return
    existing = {column["name"] for column in inspector.get_columns(_PAYOUTS)}
    if _COLUMN in existing:
        op.drop_column(_PAYOUTS, _COLUMN)
