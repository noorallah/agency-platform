"""Give business features real categories instead of one bucket.

``business_features.category`` was seeded as ``OPERATIONS`` for all 21 rows by
``20260801_0011``, so it grouped nothing. It is display-only -- no gate, filter
or resolution reads it -- but the profile configuration form offers all 21
features as one flat list of checkboxes, and the picker it uses already groups
options when it has something to group by.

The picker's fallback is to split the code on its first underscore, which suits
permissions (``CUSTOMER_VIEW`` -> "Customer") and is useless for features:
``BARCODE``, ``IMEI`` and ``TERRITORY`` have no underscore at all, while
``BATCH_TRACKING`` and ``EXPIRY_TRACKING`` would land in separate groups of one.
Twenty-one features would scatter across sixteen buckets. Naming the categories
here is what makes the grouping worth having.

The categories describe *what the capability is about*, not which industry uses
it -- a feature belongs to several industries, so grouping by industry would
duplicate every row.

``business_features`` is firm-owned, so this must run against every store:
``scripts/migrate_all_stores.py``, not a bare ``alembic upgrade head``.

Only rows still at the seeded ``OPERATIONS`` are updated. A category someone has
already edited is a decision, and a migration replaying over it would silently
undo that.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0067"
down_revision: str | Sequence[str] | None = "20260812_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "business_features"
_SEEDED = "OPERATIONS"

#: What each capability is about, not who uses it.
_CATEGORIES: dict[str, tuple[str, ...]] = {
    "TRACEABILITY": (
        "BATCH_TRACKING",
        "SERIAL_NUMBER",
        "IMEI",
        "EXPIRY_TRACKING",
        "MANUFACTURING_DATE",
        "SHELF_LIFE",
    ),
    "COMPLIANCE": ("DRUG_LICENSE", "PRESCRIPTION_REQUIRED"),
    "CATALOGUE": ("BARCODE", "QR_CODE", "ATTACHMENTS"),
    "DISTRIBUTION": ("TERRITORY", "VEHICLE_TRACKING", "MULTIPLE_WAREHOUSES"),
    "SALES": ("COMMISSION", "WARRANTY"),
    "PRODUCTION": ("RECIPE_MANAGEMENT", "KITCHEN_MANAGEMENT"),
    "SERVICES": ("PROJECT_MANAGEMENT", "SERVICE_CONTRACTS"),
    "CONTROLS": ("APPROVAL_WORKFLOW",),
}

_features = sa.table(
    _TABLE,
    sa.column("code", sa.String()),
    sa.column("category", sa.String()),
)


def upgrade() -> None:
    """Replace the single seeded bucket with categories that group."""
    bind = op.get_bind()
    # Firm-owned: the platform schema does not have this table.
    if not sa.inspect(bind).has_table(_TABLE):
        return
    for category, codes in _CATEGORIES.items():
        bind.execute(
            _features.update()
            .where(
                _features.c.code.in_(codes),
                _features.c.category == _SEEDED,
            )
            .values(category=category)
        )


def downgrade() -> None:
    """Put every categorised feature back in the one bucket."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    every_code = [code for codes in _CATEGORIES.values() for code in codes]
    bind.execute(
        _features.update()
        .where(_features.c.code.in_(every_code))
        .values(category=_SEEDED)
    )
