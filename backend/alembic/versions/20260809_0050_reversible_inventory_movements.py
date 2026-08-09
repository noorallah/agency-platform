"""Make document inventory movements reversible.

Cancelling a COMPLETED goods receipt or purchase return left the stock movement
posted: neither cancel path reversed inventory, so a cancelled receipt still
added stock the firm never accepted and a cancelled return still removed stock
it still held. ``purchase_return_lines`` did not even record which movement it
had produced, so the rows were unlinkable after the fact.

This revision adds ``purchase_return_lines.inventory_transaction_id`` — mirroring
the column ``goods_receipt_lines`` already had — and
``inventory_transactions.reversal_of_transaction_id``, which links a reversing
movement to the one it undoes so the ledger keeps both halves and a movement
cannot be reversed twice.

Both columns are nullable and no data is backfilled: movements posted before
this revision have no reversal, which is exactly what a null means.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0050"
down_revision: str | Sequence[str] | None = "20260809_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the reversal link and the purchase-return movement reference."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_transactions"):
        columns = {c["name"] for c in inspector.get_columns("inventory_transactions")}
        if "reversal_of_transaction_id" not in columns:
            op.add_column(
                "inventory_transactions",
                sa.Column("reversal_of_transaction_id", sa.Uuid(), nullable=True),
            )
            op.create_index(
                "IX_inventory_transactions_reversal_of",
                "inventory_transactions",
                ["reversal_of_transaction_id"],
            )
            op.create_foreign_key(
                "FK_inventory_transactions_reversal_of",
                "inventory_transactions",
                "inventory_transactions",
                ["reversal_of_transaction_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    if inspector.has_table("purchase_return_lines"):
        columns = {c["name"] for c in inspector.get_columns("purchase_return_lines")}
        if "inventory_transaction_id" not in columns:
            op.add_column(
                "purchase_return_lines",
                sa.Column("inventory_transaction_id", sa.Uuid(), nullable=True),
            )
            # inventory_transactions is firm-owned and lives in the same store as
            # purchase_return_lines, but guard anyway: firm schemas are partly
            # built by create_all, so the target is not guaranteed to be present.
            if inspector.has_table("inventory_transactions"):
                op.create_foreign_key(
                    "FK_purchase_return_lines_inventory_transaction",
                    "purchase_return_lines",
                    "inventory_transactions",
                    ["inventory_transaction_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> None:
    """Drop the reversal link and the purchase-return movement reference."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("purchase_return_lines"):
        columns = {c["name"] for c in inspector.get_columns("purchase_return_lines")}
        if "inventory_transaction_id" in columns:
            constraints = {
                c["name"]
                for c in inspector.get_foreign_keys("purchase_return_lines")
                if c.get("name")
            }
            if "FK_purchase_return_lines_inventory_transaction" in constraints:
                op.drop_constraint(
                    "FK_purchase_return_lines_inventory_transaction",
                    "purchase_return_lines",
                    type_="foreignkey",
                )
            op.drop_column("purchase_return_lines", "inventory_transaction_id")

    if inspector.has_table("inventory_transactions"):
        columns = {c["name"] for c in inspector.get_columns("inventory_transactions")}
        if "reversal_of_transaction_id" in columns:
            constraints = {
                c["name"]
                for c in inspector.get_foreign_keys("inventory_transactions")
                if c.get("name")
            }
            if "FK_inventory_transactions_reversal_of" in constraints:
                op.drop_constraint(
                    "FK_inventory_transactions_reversal_of",
                    "inventory_transactions",
                    type_="foreignkey",
                )
            indexes = {
                i["name"] for i in inspector.get_indexes("inventory_transactions")
            }
            if "IX_inventory_transactions_reversal_of" in indexes:
                op.drop_index(
                    "IX_inventory_transactions_reversal_of",
                    table_name="inventory_transactions",
                )
            op.drop_column("inventory_transactions", "reversal_of_transaction_id")
