"""Every firm store starts with the southern states' places (decision B6).

Owner, 2026-10-02: the places of the first market are part of the build, not
a button somebody has to know about. This loads districts, towns, PIN codes
and localities for Andhra Pradesh, Telangana, Karnataka, Tamil Nadu, Kerala,
Puducherry and Lakshadweep from the India Post pack shipped with the server
(``app/sales/data/india_post_pincodes.csv.gz``) into every firm store, through
``initialise_store`` -- the same skip-not-merge loader the screen uses, so a
store that already holds a place keeps it as it is and a deleted one is not
brought back. Other states stay on Geography > *Load places from India Post*.

The platform store is skipped (it holds the firm registry, not addresses); so
is a store without the places tables. About three seconds a store.

Firm-owned: run ``scripts/migrate_all_stores.py``. Idempotent by the loader's
own rule. The downgrade removes nothing: by then firms have written addresses
against these places, and they are data, not schema.

Revision ID: 20261002_0231
Revises: 20261002_0230
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op

revision: str = "20261002_0231"
down_revision: str | Sequence[str] | None = "20261002_0230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Load the southern states into a firm store."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # `firms` lives only in the platform store; firm stores never hold it.
    if inspector.has_table("firms") or not inspector.has_table("geo_districts"):
        return
    from app.sales.services.places_pack import initialise_store

    session = Session(bind=bind)
    try:
        outcome = initialise_store(session)
        session.flush()
    finally:
        session.close()
    if outcome is not None:
        added = sum(item.localities for item in outcome.states)
        print(f"  places: {added} localities loaded for the southern states")


def downgrade() -> None:
    """Leave the places: addresses may stand on them."""
