"""A customer's GSTIN and PAN may repeat across accounts (decision A7, B5).

One company is often several customer accounts -- a branch per state shares
its PAN, a head office and its outlets may share a GSTIN. The partial unique
keys on ``customers.gst_number`` and ``customers.pan_number`` (``20260924_0161``)
refused the second account; they become plain lookup indexes, and a save that
repeats one is warned about by name instead. The code stays unique.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent.

Revision ID: 20261002_0219
Revises: 20261002_0218
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0219"
down_revision: str | Sequence[str] | None = "20261002_0218"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "customers"
_COLUMNS = ("gst_number", "pan_number")


def upgrade() -> None:
    """Drop the two unique keys and index the columns for the warning."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints(_TABLE)
    }
    for column in _COLUMNS:
        # The partial key 0161 made, and the plain one it replaced, in case a
        # store was built some other way.
        for name in (
            f"UQ_customers_firm_{column}_active",
            f"UQ_customers_firm_{column}",
        ):
            if name in indexes:
                op.drop_index(name, table_name=_TABLE)
            if name in constraints:
                op.drop_constraint(name, _TABLE, type_="unique")
        lookup = f"IX_customers_firm_{column}"
        if lookup not in indexes:
            op.create_index(lookup, _TABLE, ["firm_id", column])


def downgrade() -> None:
    """Restore the unique keys; fails where accounts now share one."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    indexes = {index["name"] for index in inspector.get_indexes(_TABLE)}
    for column in _COLUMNS:
        lookup = f"IX_customers_firm_{column}"
        if lookup in indexes:
            op.drop_index(lookup, table_name=_TABLE)
        op.create_index(
            f"UQ_customers_firm_{column}_active",
            _TABLE,
            ["firm_id", column],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            sqlite_where=sa.text("is_deleted = 0"),
        )
