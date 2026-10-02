"""How a receipt's or payment's money moved (backlog ACC-3, §74.1 row 12).

``settlements`` gains ``payment_mode`` (CASH, CHEQUE, UPI, BANK_TRANSFER,
CARD, DEMAND_DRAFT, OTHER) and ``instrument_date``, the cheque's own date,
beside the existing ``instrument_reference``. Cash settlements already
recorded are marked CASH; a bank one keeps no mode, which the reports read as
*Bank (mode not recorded)* rather than guessing.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: each column is
added only where it is missing, and the backfill touches only cash rows with
no mode.

Revision ID: 20261002_0236
Revises: 20261002_0235
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0236"
down_revision: str | Sequence[str] | None = "20261002_0235"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "settlements"


def _columns() -> tuple[sa.Column, ...]:  # type: ignore[type-arg]
    """Return the columns this revision adds, fresh each call."""
    return (
        sa.Column("payment_mode", sa.String(length=20)),
        sa.Column("instrument_date", sa.Date()),
    )


def upgrade() -> None:
    """Add each column where settlements are held, then mark cash as cash."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name not in present:
            op.add_column(_TABLE, column)
    op.execute(
        f"UPDATE {_TABLE} SET payment_mode = 'CASH' "
        "WHERE method = 'CASH' AND payment_mode IS NULL"
    )


def downgrade() -> None:
    """Drop each column where it was added."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    present = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in _columns():
        if column.name in present:
            op.drop_column(_TABLE, column.name)
