"""Input credit given up on stock given away or written off (D-CMP-24, row G1).

``stock_adjustment_reasons.reverses_input_credit``: the firm's switch, per
reason, for whether stock leaving under it gives up the input credit taken on
it (CGST section 17(5)(h)). Added off, then switched on for the system reasons
the section names -- FREE_TO_CUSTOMER, SAMPLE, LOSS, DAMAGE, EXPIRY -- and
only in the run that adds the column, so a firm's later choice is never
overwritten on replay.

``itc_reversals`` gains ``basis`` (RULE37 for every row there is, STOCK for
the new ones), ``inventory_transaction_id``, ``reason_code`` and
``stock_value``; ``purchase_invoice_id`` becomes optional, because a stock
row names a movement and its bill only as where the rates were read.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where its table exists and lacks it, because a firm store is partly
built by ``Base.metadata.create_all``; the foreign key is declared only where
its target exists in this store.

Revision ID: 20261013_0375
Revises: 20261013_0374
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261013_0375"
down_revision: str | Sequence[str] | None = "20261013_0374"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS = "stock_adjustment_reasons"
_SWITCH = "reverses_input_credit"
_REVERSALS = "itc_reversals"
_MOVEMENT_KEY = "FK_itc_reversals_inventory_transaction_id"
_MOVEMENT_INDEX = "IX_itc_reversals_movement"


def _columns(table: str) -> set[str] | None:
    """Return a table's column names; None where the table is not here."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    """Add the switch and let a reversal name a stock movement."""
    reasons = _columns(_REASONS)
    if reasons is not None and _SWITCH not in reasons:
        op.add_column(
            _REASONS,
            sa.Column(
                _SWITCH,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.execute(
            sa.text(
                f"UPDATE {_REASONS} SET {_SWITCH} = true "
                "WHERE is_system = true AND code IN "
                "('FREE_TO_CUSTOMER', 'SAMPLE', 'LOSS', 'DAMAGE', 'EXPIRY')"
            )
        )
    reversals = _columns(_REVERSALS)
    if reversals is None:
        return
    inspector = sa.inspect(op.get_bind())
    if "basis" not in reversals:
        op.add_column(
            _REVERSALS,
            sa.Column(
                "basis", sa.String(length=10), nullable=False, server_default="RULE37"
            ),
        )
    if "inventory_transaction_id" not in reversals:
        op.add_column(
            _REVERSALS,
            sa.Column("inventory_transaction_id", UUIDType(), nullable=True),
        )
        if inspector.has_table("inventory_transactions"):
            op.create_foreign_key(
                _MOVEMENT_KEY,
                _REVERSALS,
                "inventory_transactions",
                ["inventory_transaction_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if "reason_code" not in reversals:
        op.add_column(
            _REVERSALS, sa.Column("reason_code", sa.String(length=40), nullable=True)
        )
    if "stock_value" not in reversals:
        op.add_column(
            _REVERSALS,
            sa.Column("stock_value", sa.Numeric(18, 4), nullable=True),
        )
    op.alter_column(
        _REVERSALS, "purchase_invoice_id", existing_type=UUIDType(), nullable=True
    )
    present = {index["name"] for index in inspector.get_indexes(_REVERSALS)}
    if _MOVEMENT_INDEX not in present:
        op.create_index(_MOVEMENT_INDEX, _REVERSALS, ["inventory_transaction_id"])


def downgrade() -> None:
    """Take the columns off again; rows that name no bill go with them."""
    reversals = _columns(_REVERSALS)
    if reversals is not None:
        inspector = sa.inspect(op.get_bind())
        present = {index["name"] for index in inspector.get_indexes(_REVERSALS)}
        if _MOVEMENT_INDEX in present:
            op.drop_index(_MOVEMENT_INDEX, table_name=_REVERSALS)
        if "basis" in reversals:
            op.execute(sa.text(f"DELETE FROM {_REVERSALS} WHERE basis = 'STOCK'"))
        keys = {key["name"] for key in inspector.get_foreign_keys(_REVERSALS)}
        if _MOVEMENT_KEY in keys:
            op.drop_constraint(_MOVEMENT_KEY, _REVERSALS, type_="foreignkey")
        for column in ("stock_value", "reason_code", "inventory_transaction_id"):
            if column in reversals:
                op.drop_column(_REVERSALS, column)
        if "basis" in reversals:
            op.drop_column(_REVERSALS, "basis")
        op.alter_column(
            _REVERSALS,
            "purchase_invoice_id",
            existing_type=UUIDType(),
            nullable=False,
        )
    reasons = _columns(_REASONS)
    if reasons is not None and _SWITCH in reasons:
        op.drop_column(_REASONS, _SWITCH)
