"""Drop the two-source check PG-5 left on TDS challan items (D-FIN-25).

``20261005_0307`` let a challan item name a purchase bill, replacing the check
"a receipt-side settlement or an expense" with "exactly one of settlement,
expense or bill". It looked the old check up as
``CK_tds_challan_items_one_source`` -- but ``alembic/env.py`` hands the
metadata's naming convention to ``op``, so the check had been deployed as
``CK_tds_challan_items_CK_tds_challan_items_one_source``. The lookup missed,
nothing was dropped, and every migrated store kept **both** checks: an item
naming only a bill satisfies the new one and fails the old, so TDS deducted on
a bill could not be put on a challan.

The stale check is found here by what it says, not by its name: it speaks of
the settlement and the expense and never of the bill.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent: a store with no
such check is left alone. There is no downgrade -- putting the check back
would refuse rows written since.

Revision ID: 20261005_0323
Revises: 20261005_0322
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_0323"
down_revision: str | Sequence[str] | None = "20261005_0322"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ITEMS = "tds_challan_items"


def stale_source_checks(
    inspector: sa.Inspector, schema: str | None = None
) -> list[str]:
    """Return the names of the checks that still forbid a bill-only item."""
    names = []
    for check in inspector.get_check_constraints(_ITEMS, schema=schema):
        told = str(check.get("sqltext") or "")
        name = check.get("name")
        if (
            name is not None
            and "settlement_id" in told
            and "expense_id" in told
            and "purchase_invoice_id" not in told
        ):
            names.append(name)
    return names


def upgrade() -> None:
    """Drop every check that names the two old sources and not the bill."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_ITEMS):
        return
    for name in stale_source_checks(inspector):
        # `op.f` passes the name through as deployed; without it the naming
        # convention is applied again and the drop misses, as 0307's did.
        op.drop_constraint(op.f(name), _ITEMS, type_="check")


def downgrade() -> None:
    """Leave the table as it is: the old check would refuse live rows."""
