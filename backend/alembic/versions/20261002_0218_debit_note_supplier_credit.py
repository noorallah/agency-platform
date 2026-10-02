"""A debit note's excess over its bill is supplier credit (decision A4).

`supplier_credit_applications` and `supplier_credit_refunds` name their source:
a purchase return, as before, or now a debit note. `purchase_return_id` becomes
nullable, `debit_note_id` is added, and a check holds exactly one of the two.
Existing rows all name a return, so they satisfy it.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0218
Revises: 20261002_0217
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.database.types import UUIDType

revision: str = "20261002_0218"
down_revision: str | Sequence[str] | None = "20261002_0217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("supplier_credit_applications", "supplier_credit_refunds")


def _widen(inspector: sa.Inspector, table: str) -> None:
    """Let one table name a debit note as its source."""
    if not inspector.has_table(table):
        return
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    if not columns["purchase_return_id"]["nullable"]:
        op.alter_column(table, "purchase_return_id", nullable=True)
    if "debit_note_id" not in columns:
        op.add_column(table, sa.Column("debit_note_id", UUIDType(), nullable=True))
        if inspector.has_table("debit_notes"):
            op.create_foreign_key(
                f"FK_{table}_debit_note_id",
                table,
                "debit_notes",
                ["debit_note_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    indexes = {index["name"] for index in inspector.get_indexes(table)}
    index = f"IX_{table}_debit_note"
    if index not in indexes:
        op.create_index(index, table, ["firm_id", "debit_note_id"])
    checks = {check["name"] for check in inspector.get_check_constraints(table)}
    check = f"CK_{table}_one_source"
    if check not in checks:
        op.create_check_constraint(
            check, table, "(purchase_return_id IS NULL) <> (debit_note_id IS NULL)"
        )


def upgrade() -> None:
    """Add the debit note as a second source of supplier credit."""
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        _widen(inspector, table)


def downgrade() -> None:
    """Drop the debit note source; refused while any row names one."""
    inspector = sa.inspect(op.get_bind())
    bind = op.get_bind()
    for table in _TABLES:
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "debit_note_id" not in columns:
            continue
        held = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE debit_note_id IS NOT NULL")
        ).scalar()
        if held:
            raise RuntimeError(
                f"{table} holds {held} row(s) naming a debit note; they would "
                "be lost by this downgrade."
            )
        op.drop_constraint(f"CK_{table}_one_source", table, type_="check")
        op.drop_column(table, "debit_note_id")
        op.alter_column(table, "purchase_return_id", nullable=False)
